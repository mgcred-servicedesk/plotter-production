"""
Camada de dados do dashboard — acesso ao Supabase.

Cada loader expoe uma API publica (``carregar_*``) que
delega para duas funcoes cacheadas separadas — uma para
o mes corrente (TTL curto) e outra para o historico
(TTL longo) — via ``_eh_mes_atual``.

``consolidar_dados`` aplica as regras de negocio (pontos,
emissoes, seguros, Super Conta) sobre os contratos pagos
e e o entrypoint usado pelo ``main`` do dashboard.

O cache lida com side-effects (ex: diagnostico em
``session_state``) na funcao wrapper externa, nunca
dentro de ``@st.cache_data`` — Streamlit nao garante
side-effects em funcoes cacheadas.
"""

from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from src.config.supabase_client import get_supabase_client
from src.dashboard.rls import _obter_perfil_efetivo


_PAGE_SIZE = 1000

# Janela (dias de calendario) do detalhe de digitacao. Os quadros que o
# consomem — "Ultimo Dia" e "Ultimos 7 Dias" (este, apos o recorte RLS
# client-side) — so precisam da semana recente. 14 cobre com folga os 7
# dias-com-dado exibidos + 1 dia-base da Var. % incluindo fins de semana,
# sem trazer o mes inteiro (RPC migration 042). Tunavel: menor = menos
# payload, porem maior risco de escopo pouco ativo ficar curto.
_DIGITACAO_DETALHE_DIAS_RECENTES = 14


# Colunas de v_contratos_dashboard consumidas pelo dashboard, mapeadas
# para os nomes canonicos do DataFrame. Usado no select explicito de
# _fetch_contratos_pagos (evita "*" e reduz o payload do PostgREST).
_COLS_CONTRATOS_PAGOS = {
    "contrato_id": "CONTRATO_ID",
    "num_proposta": "NUM_PROPOSTA",
    "data_status_pagamento": "DATA",
    "data_cadastro": "DATA_CADASTRO",
    "loja": "LOJA",
    "regiao": "REGIAO",
    "regiao_atual": "REGIAO_ATUAL",
    "consultor": "CONSULTOR",
    "produto": "PRODUTO",
    "tipo_produto": "TIPO_PRODUTO",
    "subtipo": "SUBTIPO",
    "tipo_operacao": "TIPO OPER.",
    "valor": "VALOR",
    "prazo": "PRAZO",
    "valor_parcela": "VALOR_PARCELA",
    "banco": "BANCO",
    "convenio": "CONVENIO",
    "sub_status_banco": "SUB_STATUS",
    "categoria_codigo": "categoria_codigo",
    "grupo_dashboard": "grupo_dashboard",
    "grupo_meta": "grupo_meta",
    "conta_valor": "conta_valor",
    "conta_pontuacao": "conta_pontuacao",
    "created_at": "CREATED_AT",
}


# Fallback TIPO_PRODUTO → categoria, usado quando
# produtos.categoria_id esta NULL no banco (ver
# _preencher_categoria_fallback e migration 061).
_TIPO_PARA_CATEGORIA = {
    "CNC": "CNC",
    "CNC 13º": "CNC_13",
    "CNC 13": "CNC_13",
    "CNC ANT": "ANT_BENEF",
    "ANT. DE BENEF.": "ANT_BENEF",
    "SAQUE": "SAQUE",
    "SAQUE BENEFICIO": "SAQUE_BENEFICIO",
    "CONSIG": "CONSIG_BMG",
    "CONSIG BMG": "CONSIG_BMG",
    "CONSIG PRIV": "CONSIG_PRIV",
    "CLT": "CONSIG_PRIV",
    "CONSIG ITAU": "CONSIG_ITAU",
    "CONSIG Itau": "CONSIG_ITAU",
    "CONSIG C6": "CONSIG_C6",
    "FGTS": "FGTS",
    "EMISSAO": "CARTAO",
    "EMISSAO CB": "CARTAO",
    "EMISSAO CC": "CARTAO",
    "Portabilidade": "PORTABILIDADE",
    "PORTABILIDADE": "PORTABILIDADE",
}


# Portabilidade herda os pontos do CONSIG do banco origem.
# Chaves normalizadas (strip + upper). CONSIG_PRIV nao entra:
# Privado nao se aplica a portabilidade.
_PORTAB_BANCO_TO_CONSIG = {
    "BMG": "CONSIG_BMG",
    "BANCO BMG": "CONSIG_BMG",
    "C6 BANK": "CONSIG_C6",
    "C6": "CONSIG_C6",
    "BANCO C6": "CONSIG_C6",
    "ITAU": "CONSIG_ITAU",
    "ITAÚ": "CONSIG_ITAU",
    "BANCO ITAU": "CONSIG_ITAU",
    "BANCO ITAÚ": "CONSIG_ITAU",
}


# ══════════════════════════════════════════════════════
# Helpers internos
# ══════════════════════════════════════════════════════


def _sb():
    """Atalho para obter o cliente Supabase."""
    return get_supabase_client()


def _ttl_periodo(
    mes: int,
    ano: int,
    ttl_atual: int,
    ttl_historico: int,
) -> int:
    """Retorna TTL curto para periodo vigente, longo para historico."""
    hoje = datetime.now()
    if mes == hoje.month and ano == hoje.year:
        return ttl_atual
    return ttl_historico


def _eh_mes_atual(mes: int, ano: int) -> bool:
    """Retorna True se mes/ano corresponde ao mes corrente."""
    hoje = datetime.now()
    return mes == hoje.month and ano == hoje.year


def _paginar_keyset(montar_query: Callable, coluna_chave: str) -> List[dict]:
    """Pagina por cursor: WHERE chave > ultimo ORDER BY chave LIMIT N.

    Substitui a paginacao por OFFSET: com OFFSET cada pagina reordena o
    resultset inteiro (sort que spilla para temp files no Postgres —
    dreno do Disk IO Budget, ver migration 054); com cursor todo request
    e um top-N de no maximo _PAGE_SIZE linhas, que cabe em work_mem.

    ``montar_query`` deve devolver a query base ja com ``.order(
    coluna_chave)`` e ``.limit(_PAGE_SIZE)``; ``coluna_chave`` deve ser
    UNICA (PK/UNIQUE) — chave repetida faria linhas serem puladas entre
    paginas.
    """
    all_data: List[dict] = []
    ultimo = None
    while True:
        query = montar_query()
        if ultimo is not None:
            query = query.gt(coluna_chave, ultimo)
        batch = query.execute().data or []
        all_data.extend(batch)
        if len(batch) < _PAGE_SIZE:
            return all_data
        ultimo = batch[-1][coluna_chave]


# ══════════════════════════════════════════════════════
# Categorias e periodos
# ══════════════════════════════════════════════════════


@st.cache_data(ttl=86400)
def carregar_categorias() -> pd.DataFrame:
    """Carrega categorias_produto do banco. TTL 24h — raramente muda."""
    resp = (
        _sb()
        .table("categorias_produto")
        .select("*")
        .eq("ativo", True)
        .order("ordem")
        .execute()
    )
    return pd.DataFrame(resp.data or [])


def _preencher_categoria_fallback(df: pd.DataFrame) -> pd.DataFrame:
    """Preenche categoria (e derivados) quando o banco veio sem ela.

    O ETL sobrescreve ``produtos`` a cada import e, quando a planilha de
    origem renomeia um tipo (ex: ``CONSIG PRIV`` -> ``CLT``,
    ``CNC ANT`` -> ``ANT. DE BENEF.``), grava ``categoria_id = NULL``
    (ver ``database/migrations/061``). Sem este fallback as linhas ficam
    com ``categoria_codigo``/``grupo_dashboard`` vazios e desaparecem de
    tudo que agrupa por produto — inclusive dos filtros da aba
    Analiticos. Corrigir na origem (ETL) segue sendo o definitivo.

    Muta e devolve ``df``. So preenche colunas que ja existem no frame
    (em analise/cancelados nao trazem ``grupo_meta`` nem
    ``conta_pontuacao``).
    """
    if df.empty or "categoria_codigo" not in df.columns:
        return df

    # Normaliza NaN → "" antes da máscara: contratos com categoria_id NULL
    # no banco chegam como NaN (float) e quebram diagnósticos posteriores
    # (sorted misturando float/str). Ex.: Maio/2025 tinha 13 linhas
    # PAPCARD/CONTA SIMPLES sem categoria.
    df["categoria_codigo"] = df["categoria_codigo"].fillna("")
    mask_sem_cat = df["categoria_codigo"] == ""
    if not mask_sem_cat.any() or "TIPO_PRODUTO" not in df.columns:
        return df

    df.loc[mask_sem_cat, "categoria_codigo"] = (
        df.loc[mask_sem_cat, "TIPO_PRODUTO"]
        .map(_TIPO_PARA_CATEGORIA)
        .fillna("")
    )

    # Preencher grupo_dashboard, grupo_meta, conta_valor,
    # conta_pontuacao a partir das categorias do banco
    categorias = carregar_categorias()
    if categorias.empty:
        return df

    cat_map = categorias.set_index("codigo")
    preenchidos = mask_sem_cat & (df["categoria_codigo"] != "")

    for campo in [
        "grupo_dashboard",
        "grupo_meta",
        "conta_valor",
        "conta_pontuacao",
    ]:
        if campo in cat_map.columns and campo in df.columns:
            df.loc[preenchidos, campo] = (
                df.loc[preenchidos, "categoria_codigo"]
                .map(cat_map[campo])
            )

    return df


@st.cache_data(ttl=86400)
def carregar_periodo(mes: int, ano: int) -> Optional[dict]:
    """Busca o periodo correspondente a mes/ano. TTL 24h — imutavel."""
    resp = (
        _sb()
        .table("periodos")
        .select("id, mes, ano, referencia")
        .eq("mes", mes)
        .eq("ano", ano)
        .limit(1)
        .execute()
    )
    return resp.data[0] if resp.data else None


@st.cache_data(ttl=900)
def carregar_ultimo_periodo() -> Optional[dict]:
    """Retorna o periodo mais recente cadastrado. TTL 15min."""
    resp = (
        _sb()
        .table("periodos")
        .select("mes, ano")
        .order("ano", desc=True)
        .order("mes", desc=True)
        .limit(1)
        .execute()
    )
    return resp.data[0] if resp.data else None


# ══════════════════════════════════════════════════════
# Contratos pagos
# ══════════════════════════════════════════════════════


def carregar_contratos_pagos(
    mes: int,
    ano: int,
) -> pd.DataFrame:
    """Carrega contratos pagos via view v_contratos_dashboard.

    TTL real: 30min para mes corrente, 24h para historico.
    """
    if _eh_mes_atual(mes, ano):
        return _contratos_pagos_atual(mes, ano)
    return _contratos_pagos_historico(mes, ano)


def _fetch_contratos_pagos(mes: int, ano: int) -> pd.DataFrame:
    """Executa a query de contratos pagos sem cache."""
    periodo = carregar_periodo(mes, ano)
    if not periodo:
        return pd.DataFrame()

    # select explicito (em vez de "*"): so as colunas consumidas pelo
    # dashboard trafegam do PostgREST. "id" entra apenas como cursor da
    # paginacao keyset (nao e mapeado para o DataFrame).
    colunas = "id," + ",".join(_COLS_CONTRATOS_PAGOS)
    all_data = _paginar_keyset(
        lambda: (
            _sb()
            .from_("v_contratos_dashboard")
            .select(colunas)
            .eq("periodo_id", periodo["id"])
            .order("id")
            .limit(_PAGE_SIZE)
        ),
        "id",
    )

    if not all_data:
        return pd.DataFrame()

    # Monta o DataFrame direto da resposta (sem loop linha-a-linha).
    # reindex garante a presenca/ordem das colunas-fonte mesmo que o
    # PostgREST omita alguma chave; rename aplica os nomes canonicos.
    df = (
        pd.DataFrame(all_data)
        .reindex(columns=list(_COLS_CONTRATOS_PAGOS))
        .rename(columns=_COLS_CONTRATOS_PAGOS)
    )

    # Numericos: VALOR_PARCELA nulo -> 0 (espelha o antigo `or 0`).
    # Colunas de texto e flags (conta_valor/conta_pontuacao) ficam
    # como vieram — None de LEFT JOIN preservado, como antes.
    df["VALOR"] = pd.to_numeric(df["VALOR"], errors="coerce").fillna(0.0)
    df["VALOR_PARCELA"] = pd.to_numeric(
        df["VALOR_PARCELA"], errors="coerce"
    ).fillna(0.0)

    # Datas: DATA_CADASTRO chega como texto ISO ('yyyy-mm-dd'); normaliza
    # para datetime64 como nos loaders de em_analise/cancelados.
    df["DATA"] = pd.to_datetime(df["DATA"], errors="coerce")
    df["DATA_CADASTRO"] = pd.to_datetime(
        df["DATA_CADASTRO"], errors="coerce"
    )
    df["CREATED_AT"] = pd.to_datetime(
        df["CREATED_AT"], errors="coerce", utc=True
    )

    return df


@st.cache_data(ttl=1800)
def _contratos_pagos_atual(mes: int, ano: int) -> pd.DataFrame:
    """Contratos pagos — mes corrente. TTL 30min."""
    return _fetch_contratos_pagos(mes, ano)


@st.cache_data(ttl=86400)
def _contratos_pagos_historico(mes: int, ano: int) -> pd.DataFrame:
    """Contratos pagos — historico. TTL 24h."""
    return _fetch_contratos_pagos(mes, ano)


# ══════════════════════════════════════════════════════
# Contratos em analise
# ══════════════════════════════════════════════════════


def carregar_contratos_em_analise(
    mes: int,
    ano: int,
) -> pd.DataFrame:
    """Carrega contratos em analise via RPC obter_contratos_em_analise.

    TTL real: 15min para mes corrente, 6h para historico.
    """
    if _eh_mes_atual(mes, ano):
        return _contratos_em_analise_atual(mes, ano)
    return _contratos_em_analise_historico(mes, ano)


def _fetch_contratos_em_analise(mes: int, ano: int) -> pd.DataFrame:
    """Executa a RPC de contratos em analise sem cache.

    Variante _json (migration 057): uma execucao devolve o resultado
    inteiro agregado em JSON. O .range() antigo fazia o PostgREST
    reexecutar a funcao inteira a cada pagina de 1000 linhas.
    """
    resp = (
        _sb()
        .rpc(
            "obter_contratos_em_analise_json",
            {"p_mes": mes, "p_ano": ano},
        )
        .execute()
    )
    all_data = resp.data or []

    if not all_data:
        return pd.DataFrame()

    rows = []
    for c in all_data:
        rows.append(
            {
                "CONTRATO_ID": c.get("contrato_id"),
                "NUM_PROPOSTA": c.get("num_proposta", ""),
                "DATA_CADASTRO": c.get("data_cadastro"),
                "LOJA": c.get("loja", ""),
                "REGIAO": c.get("regiao", ""),
                "REGIAO_ATUAL": c.get("regiao_atual", ""),
                "CONSULTOR": c.get("consultor", ""),
                "PRODUTO": c.get("produto", ""),
                "TIPO_PRODUTO": c.get("tipo_produto", ""),
                "SUBTIPO": c.get("subtipo", ""),
                "TIPO OPER.": c.get("tipo_operacao", ""),
                "VALOR": float(c.get("valor", 0)),
                "BANCO": c.get("banco", ""),
                "STATUS_BANCO": c.get("status_banco", ""),
                "SUB_STATUS": c.get("sub_status_banco", ""),
                "categoria_codigo": c.get("categoria_codigo", ""),
                "grupo_dashboard": c.get("grupo_dashboard"),
                "conta_valor": c.get("conta_valor", True),
            }
        )

    df = pd.DataFrame(rows)

    if "DATA_CADASTRO" in df.columns:
        df["DATA_CADASTRO"] = pd.to_datetime(
            df["DATA_CADASTRO"], errors="coerce"
        )

    return _preencher_categoria_fallback(df)


@st.cache_data(ttl=900)
def _contratos_em_analise_atual(mes: int, ano: int) -> pd.DataFrame:
    """Contratos em analise — mes corrente. TTL 15min."""
    return _fetch_contratos_em_analise(mes, ano)


@st.cache_data(ttl=21600)
def _contratos_em_analise_historico(mes: int, ano: int) -> pd.DataFrame:
    """Contratos em analise — historico. TTL 6h."""
    return _fetch_contratos_em_analise(mes, ano)


# ══════════════════════════════════════════════════════
# Digitacao diaria (todos os status)
# ══════════════════════════════════════════════════════


def carregar_digitacao_diaria(mes: int, ano: int) -> pd.DataFrame:
    """Carrega a digitacao diaria via RPC obter_digitacao_diaria.

    Conta todos os contratos cadastrados por dia (qualquer status,
    inclusive cancelados e em analise) no mes/ano. O RPC e SECURITY
    INVOKER e a RLS server-side (pol_contratos_select) ja restringe
    o agregado ao escopo do perfil logado — nao precisa aplicar_rls.

    TTL real: 15min para mes corrente, 6h para historico.

    Colunas: data_cadastro (datetime), qtd_digitada (int),
    valor_digitado (float). Minusculas e sem renomear — consumidas
    por kpis.detalhes_cards.detalhe_digitacao_diaria.
    """
    if _eh_mes_atual(mes, ano):
        return _digitacao_diaria_atual(mes, ano)
    return _digitacao_diaria_historico(mes, ano)


def _fetch_digitacao_diaria(mes: int, ano: int) -> pd.DataFrame:
    """Executa a RPC de digitacao diaria sem cache.

    Resultado e um agregado por dia (<= 31 linhas), entao nao ha
    paginacao como nas RPCs de nivel-contrato.
    """
    resp = (
        _sb()
        .rpc(
            "obter_digitacao_diaria",
            {"p_mes": mes, "p_ano": ano},
        )
        .execute()
    )
    data = resp.data or []
    if not data:
        return pd.DataFrame(
            columns=["data_cadastro", "qtd_digitada", "valor_digitado"]
        )

    df = pd.DataFrame(
        [
            {
                "data_cadastro": r.get("data_cadastro"),
                "qtd_digitada": int(r.get("qtd_digitada", 0) or 0),
                "valor_digitado": float(r.get("valor_digitado", 0) or 0),
            }
            for r in data
        ]
    )
    df["data_cadastro"] = pd.to_datetime(
        df["data_cadastro"], errors="coerce"
    )
    return df


@st.cache_data(ttl=900)
def _digitacao_diaria_atual(mes: int, ano: int) -> pd.DataFrame:
    """Digitacao diaria — mes corrente. TTL 15min."""
    return _fetch_digitacao_diaria(mes, ano)


@st.cache_data(ttl=21600)
def _digitacao_diaria_historico(mes: int, ano: int) -> pd.DataFrame:
    """Digitacao diaria — historico. TTL 6h."""
    return _fetch_digitacao_diaria(mes, ano)


# ══════════════════════════════════════════════════════
# Digitacao diaria detalhada (por regiao x produto)
# ══════════════════════════════════════════════════════


def carregar_digitacao_diaria_detalhe(
    mes: int,
    ano: int,
    dias_recentes: Optional[int] = _DIGITACAO_DETALHE_DIAS_RECENTES,
) -> pd.DataFrame:
    """Carrega a digitacao diaria detalhada (RPC
    obter_digitacao_diaria_detalhe).

    Mesma base do agregado ``carregar_digitacao_diaria`` (contratos
    direto, TODOS os status), quebrada por dia x regiao x loja x
    grupo_dashboard x categoria_codigo — alimenta o pivot do "Ultimo Dia
    Apurado" E, apos o recorte RLS client-side, a serie "Ultimos 7 Dias".
    A soma do detalhe bate com o agregado do mesmo dia.

    ``dias_recentes`` (default ``_DIGITACAO_DETALHE_DIAS_RECENTES``)
    limita a JANELA aos ultimos N dias de calendario (RPC migration 042),
    evitando trazer o mes inteiro — ambos os consumidores so usam a
    semana recente. ``None`` traz o mes inteiro (retrocompativel). Entra
    na chave de cache.

    TTL real: 15min para mes corrente, 6h para historico.

    Colunas mapeadas para reuso direto pelas funcoes de pivot/ultimo
    dia: ``DATA_CADASTRO`` (datetime), ``REGIAO``, ``LOJA``,
    ``grupo_dashboard``, ``categoria_codigo``, ``VALOR`` (bruto, =
    valor_digitado), ``qtd_digitada``. SEM ``conta_valor`` — digitacao e
    volume bruto. ``categoria_codigo`` permite desmembrar o grupo 'PACK'
    em colunas granulares no pivot (RPC migration 041).
    """
    if _eh_mes_atual(mes, ano):
        return _digitacao_detalhe_atual(mes, ano, dias_recentes)
    return _digitacao_detalhe_historico(mes, ano, dias_recentes)


def _fetch_digitacao_diaria_detalhe(
    mes: int,
    ano: int,
    dias_recentes: Optional[int] = None,
) -> pd.DataFrame:
    """Executa a RPC de digitacao detalhada sem cache.

    Resultado e agregado por (dia, regiao, loja, grupo_dashboard,
    categoria_codigo). Ao contrario do agregado diario (<= 31 linhas), a
    granularidade dia x regiao x loja x produto pode passar de 1000
    linhas — o limite default do PostgREST. Sem paginacao, a resposta era
    truncada e, como a RPC ordena por data ascendente, os dias mais
    recentes (e regioes) sumiam. Paginamos com ``.range`` como em
    ``_fetch_contratos_cancelados``.

    ``dias_recentes`` (None = mes inteiro) e repassado a RPC como
    ``p_dias_recentes`` (migration 042); omitido quando None para usar o
    DEFAULT NULL da funcao.
    """
    cols = [
        "DATA_CADASTRO",
        "REGIAO",
        "REGIAO_ATUAL",
        "LOJA",
        "grupo_dashboard",
        "categoria_codigo",
        "VALOR",
        "qtd_digitada",
    ]
    params: Dict[str, int] = {"p_mes": mes, "p_ano": ano}
    if dias_recentes is not None:
        params["p_dias_recentes"] = dias_recentes
    # Variante _json (migration 057): execucao unica, sem reexecucao
    # da funcao por pagina.
    resp = _sb().rpc("obter_digitacao_diaria_detalhe_json", params).execute()
    all_data = resp.data or []

    if not all_data:
        return pd.DataFrame(columns=cols)

    df = pd.DataFrame(
        [
            {
                "DATA_CADASTRO": r.get("data_cadastro"),
                "REGIAO": r.get("regiao", "") or "",
                "REGIAO_ATUAL": r.get("regiao_atual", "") or "",
                "LOJA": r.get("loja", "") or "",
                "grupo_dashboard": r.get("grupo_dashboard"),
                # None enquanto a migration 041 nao roda → o helper de
                # split cai no fallback grupo_dashboard (sem quebrar).
                "categoria_codigo": r.get("categoria_codigo"),
                "VALOR": float(r.get("valor_digitado", 0) or 0),
                "qtd_digitada": int(r.get("qtd_digitada", 0) or 0),
            }
            for r in all_data
        ]
    )
    df["DATA_CADASTRO"] = pd.to_datetime(df["DATA_CADASTRO"], errors="coerce")
    return df


@st.cache_data(ttl=900)
def _digitacao_detalhe_atual(
    mes: int, ano: int, dias_recentes: Optional[int] = None
) -> pd.DataFrame:
    """Digitacao detalhada — mes corrente. TTL 15min."""
    return _fetch_digitacao_diaria_detalhe(mes, ano, dias_recentes)


@st.cache_data(ttl=21600)
def _digitacao_detalhe_historico(
    mes: int, ano: int, dias_recentes: Optional[int] = None
) -> pd.DataFrame:
    """Digitacao detalhada — historico. TTL 6h."""
    return _fetch_digitacao_diaria_detalhe(mes, ano, dias_recentes)


# ══════════════════════════════════════════════════════
# Contratos cancelados
# ══════════════════════════════════════════════════════


def carregar_contratos_cancelados(
    mes: int,
    ano: int,
) -> pd.DataFrame:
    """Carrega cancelados via RPC obter_cancelados_classificados.

    Traz a coluna ``CLASSIFICACAO`` (redigitada/recuperada/liquido).
    TTL real: 15min para mes corrente, 6h para historico.
    """
    if _eh_mes_atual(mes, ano):
        return _contratos_cancelados_atual(mes, ano)
    return _contratos_cancelados_historico(mes, ano)


def _fetch_contratos_cancelados(mes: int, ano: int) -> pd.DataFrame:
    """Executa a RPC de contratos cancelados sem cache.

    Usa ``obter_cancelados_classificados_json`` (migration 057), que
    alem das colunas de cancelados traz ``classificacao`` (redigitada/
    recuperada/liquido) — matching feito no banco, sem expor o nome do
    cliente. Execucao unica: o .range() antigo fazia o PostgREST
    reexecutar a funcao (~2,6 s) a cada pagina de 1000 linhas.
    """
    resp = (
        _sb()
        .rpc(
            "obter_cancelados_classificados_json",
            {"p_mes": mes, "p_ano": ano},
        )
        .execute()
    )
    all_data = resp.data or []

    if not all_data:
        return pd.DataFrame()

    rows = []
    for c in all_data:
        rows.append(
            {
                "CONTRATO_ID": c.get("contrato_id"),
                "NUM_PROPOSTA": c.get("num_proposta", ""),
                "DATA_CADASTRO": c.get("data_cadastro"),
                "LOJA": c.get("loja", ""),
                "REGIAO": c.get("regiao", ""),
                "REGIAO_ATUAL": c.get("regiao_atual", ""),
                "CONSULTOR": c.get("consultor", ""),
                "PRODUTO": c.get("produto", ""),
                "TIPO_PRODUTO": c.get("tipo_produto", ""),
                "SUBTIPO": c.get("subtipo", ""),
                "TIPO OPER.": c.get("tipo_operacao", ""),
                "VALOR": float(c.get("valor", 0)),
                "BANCO": c.get("banco", ""),
                "STATUS_BANCO": c.get("status_banco", ""),
                "SUB_STATUS": c.get("sub_status_banco", ""),
                "STATUS_PAG": c.get(
                    "status_pagamento_cliente", ""
                ),
                "CLASSIFICACAO": c.get(
                    "classificacao", "liquido"
                ),
                "RECUPERADA_OUTRO": bool(
                    c.get("recuperada_outro", False)
                ),
                "RECUPERADA_OUTRA_LOJA": bool(
                    c.get("recuperada_outra_loja", False)
                ),
                "RECUPERADA_OUTRA_REGIAO": bool(
                    c.get("recuperada_outra_regiao", False)
                ),
                "categoria_codigo": c.get(
                    "categoria_codigo", ""
                ),
                "grupo_dashboard": c.get("grupo_dashboard"),
                "conta_valor": c.get("conta_valor", True),
            }
        )

    df = pd.DataFrame(rows)

    if "DATA_CADASTRO" in df.columns:
        df["DATA_CADASTRO"] = pd.to_datetime(
            df["DATA_CADASTRO"], errors="coerce"
        )

    return _preencher_categoria_fallback(df)


@st.cache_data(ttl=900)
def _contratos_cancelados_atual(mes: int, ano: int) -> pd.DataFrame:
    """Contratos cancelados — mes corrente. TTL 15min."""
    return _fetch_contratos_cancelados(mes, ano)


@st.cache_data(ttl=21600)
def _contratos_cancelados_historico(mes: int, ano: int) -> pd.DataFrame:
    """Contratos cancelados — historico. TTL 6h."""
    return _fetch_contratos_cancelados(mes, ano)


# ══════════════════════════════════════════════════════
# Pontuacao efetiva (mensal)
# ══════════════════════════════════════════════════════


def carregar_pontuacao_efetiva(
    mes: int,
    ano: int,
) -> pd.DataFrame:
    """Carrega pontuacao efetiva via funcao SQL.

    TTL real: 6h para mes corrente, 24h para historico.
    """
    if _eh_mes_atual(mes, ano):
        return _pontuacao_atual(mes, ano)
    return _pontuacao_historico(mes, ano)


def _fetch_pontuacao(mes: int, ano: int) -> pd.DataFrame:
    """Executa a RPC de pontuacao sem cache."""
    resp = (
        _sb()
        .rpc(
            "obter_pontuacao_periodo",
            {"p_mes": mes, "p_ano": ano},
        )
        .execute()
    )
    return pd.DataFrame(resp.data or [])


@st.cache_data(ttl=21600)
def _pontuacao_atual(mes: int, ano: int) -> pd.DataFrame:
    """Pontuacao — mes corrente. TTL 6h."""
    return _fetch_pontuacao(mes, ano)


@st.cache_data(ttl=86400)
def _pontuacao_historico(mes: int, ano: int) -> pd.DataFrame:
    """Pontuacao — historico. TTL 24h."""
    return _fetch_pontuacao(mes, ano)


# ══════════════════════════════════════════════════════
# Metas (GERAL / LOJA)
# ══════════════════════════════════════════════════════


def carregar_metas(mes: int, ano: int) -> pd.DataFrame:
    """Carrega metas GERAL/LOJA do periodo.

    TTL real: 6h para mes corrente, 24h para historico.
    """
    if _eh_mes_atual(mes, ano):
        return _metas_atual(mes, ano)
    return _metas_historico(mes, ano)


def _reanexar_regiao(
    df_pivot: pd.DataFrame, fonte: pd.DataFrame
) -> pd.DataFrame:
    """Reanexa REGIAO (e REGIAO_ATUAL quando presente) perdidas no pivot
    indexado por LOJA.

    Permite o filtro RLS por regiao sem depender de contratos. `fonte`
    e o DataFrame nao-pivotado que ainda carrega LOJA + REGIAO (e,
    quando disponivel, REGIAO_ATUAL). REGIAO_ATUAL so e reanexada se a
    fonte a tiver, para o recorte RLS do gerente pelo organograma atual.
    """
    cols = ["LOJA", "REGIAO"]
    if "REGIAO_ATUAL" in fonte.columns:
        cols.append("REGIAO_ATUAL")
    regiao_por_loja = fonte[cols].drop_duplicates("LOJA")
    return df_pivot.merge(regiao_por_loja, on="LOJA", how="left")


def _fetch_metas(mes: int, ano: int) -> pd.DataFrame:
    """Executa a query de metas GERAL/LOJA sem cache.

    Usa a RPC obter_metas_geral_loja (migration 045), que resolve a
    REGIAO vigente na COMPETENCIA da meta (point-in-time via
    loja_regiao_vigencia) e devolve REGIAO_ATUAL (organograma atual,
    p/ o recorte RLS do gerente) e loja_ativa. Requer a 045 aplicada.
    """
    colunas_vazio = [
        "LOJA", "REGIAO", "REGIAO_ATUAL", "META_PRATA", "META_OURO"
    ]

    resp = (
        _sb()
        .rpc("obter_metas_geral_loja", {"p_mes": mes, "p_ano": ano})
        .execute()
    )

    if not resp.data:
        return pd.DataFrame(columns=colunas_vazio)

    # Mes corrente: conta apenas lojas ativas (loja recem-aberta entra;
    # loja inativa nao). Historico: preserva todas as lojas que tinham
    # meta, mesmo que hoje estejam inativas.
    filtrar_ativas = _eh_mes_atual(mes, ano)

    rows = []
    for m in resp.data:
        if filtrar_ativas and not m.get("loja_ativa", True):
            continue
        rows.append(
            {
                "LOJA": m.get("loja", ""),
                "REGIAO": m.get("regiao", "") or "",
                "REGIAO_ATUAL": m.get("regiao_atual", "") or "",
                "nivel": m.get("nivel"),
                "valor": float(m.get("valor", 0)),
            }
        )

    df_geral_loja = pd.DataFrame(rows)

    if not df_geral_loja.empty:
        df_pivot = df_geral_loja.pivot_table(
            index="LOJA",
            columns="nivel",
            values="valor",
            aggfunc="sum",
        ).reset_index()

        rename_map = {}
        if "PRATA" in df_pivot.columns:
            rename_map["PRATA"] = "META_PRATA"
        if "OURO" in df_pivot.columns:
            rename_map["OURO"] = "META_OURO"
        if "BRONZE" in df_pivot.columns:
            rename_map["BRONZE"] = "META_BRONZE"
        df_pivot = df_pivot.rename(columns=rename_map)

        for col in ["META_PRATA", "META_OURO"]:
            if col not in df_pivot.columns:
                df_pivot[col] = 0

        # Reanexa REGIAO (perdida no pivot indexado por LOJA) para
        # permitir filtro RLS por regiao sem depender de contratos.
        df_pivot = _reanexar_regiao(df_pivot, df_geral_loja)

        return df_pivot

    return pd.DataFrame(columns=colunas_vazio)


@st.cache_data(ttl=21600)
def _metas_atual(mes: int, ano: int) -> pd.DataFrame:
    """Metas GERAL/LOJA — mes corrente. TTL 6h."""
    return _fetch_metas(mes, ano)


@st.cache_data(ttl=86400)
def _metas_historico(mes: int, ano: int) -> pd.DataFrame:
    """Metas GERAL/LOJA — historico. TTL 24h."""
    return _fetch_metas(mes, ano)


# ══════════════════════════════════════════════════════
# Metas por produto
# ══════════════════════════════════════════════════════


def carregar_metas_produto(
    mes: int,
    ano: int,
) -> pd.DataFrame:
    """Carrega metas por produto do periodo.

    TTL real: 6h para mes corrente, 24h para historico.
    """
    if _eh_mes_atual(mes, ano):
        return _metas_produto_atual(mes, ano)
    return _metas_produto_historico(mes, ano)


def _fetch_metas_produto(mes: int, ano: int) -> pd.DataFrame:
    """Executa a query de metas por produto sem cache."""
    periodo = carregar_periodo(mes, ano)
    if not periodo:
        return pd.DataFrame()

    query = (
        _sb()
        .table("metas")
        .select(
            "produto, escopo, nivel, valor, "
            "lojas!inner(nome, regioes(nome))"
        )
        .eq("periodo_id", periodo["id"])
        .eq("escopo", "LOJA")
        .is_("nivel", "null")
    )
    # Mes corrente: apenas lojas ativas. Historico: todas (ver
    # _fetch_metas).
    if _eh_mes_atual(mes, ano):
        query = query.eq("lojas.ativo", True)
    resp = query.execute()

    if not resp.data:
        return pd.DataFrame()

    rows = []
    for m in resp.data:
        loja = m.get("lojas") or {}
        regiao = (loja.get("regioes") or {}).get("nome", "")
        rows.append(
            {
                "LOJA": loja.get("nome", ""),
                "REGIAO": regiao,
                "produto_meta": m["produto"],
                "valor": float(m.get("valor", 0)),
            }
        )

    df = pd.DataFrame(rows)

    # Deduplicar por (LOJA, produto_meta) — constraint
    # UNIQUE com nivel NULL nao impede duplicatas no PG
    df = df.drop_duplicates(
        subset=["LOJA", "produto_meta"], keep="first"
    )

    # Pivotar para ter uma coluna por produto_meta
    if not df.empty:
        df_pivot = df.pivot_table(
            index="LOJA",
            columns="produto_meta",
            values="valor",
            aggfunc="sum",
            fill_value=0,
        ).reset_index()

        # Reanexa REGIAO para o filtro RLS por regiao.
        df_pivot = _reanexar_regiao(df_pivot, df)
        return df_pivot

    return pd.DataFrame(columns=["LOJA", "REGIAO"])


@st.cache_data(ttl=21600)
def _metas_produto_atual(mes: int, ano: int) -> pd.DataFrame:
    """Metas por produto — mes corrente. TTL 6h."""
    return _fetch_metas_produto(mes, ano)


@st.cache_data(ttl=86400)
def _metas_produto_historico(mes: int, ano: int) -> pd.DataFrame:
    """Metas por produto — historico. TTL 24h."""
    return _fetch_metas_produto(mes, ano)


# ══════════════════════════════════════════════════════
# Metas por produto — escopo CONSULTOR
# ══════════════════════════════════════════════════════


def carregar_metas_produto_consultor(
    mes: int,
    ano: int,
) -> pd.DataFrame:
    """Carrega metas por produto com escopo CONSULTOR.

    Retorna o mesmo formato pivotado de carregar_metas_produto
    (LOJA | MIX | CNC | ...), mas com os valores por consultor
    em vez de por loja. Usado quando o perfil logado é consultor.

    TTL real: 6h para mes corrente, 24h para historico.
    """
    if _eh_mes_atual(mes, ano):
        return _metas_produto_consultor_atual(mes, ano)
    return _metas_produto_consultor_historico(mes, ano)


def _fetch_metas_produto_consultor(mes: int, ano: int) -> pd.DataFrame:
    """Executa a query de metas por produto (escopo CONSULTOR) sem cache."""
    periodo = carregar_periodo(mes, ano)
    if not periodo:
        return pd.DataFrame()

    resp = (
        _sb()
        .table("metas")
        .select("produto, escopo, nivel, valor, lojas(nome)")
        .eq("periodo_id", periodo["id"])
        .eq("escopo", "CONSULTOR")
        .is_("nivel", "null")
        .execute()
    )

    if not resp.data:
        return pd.DataFrame()

    rows = []
    for m in resp.data:
        loja = m.get("lojas") or {}
        rows.append(
            {
                "LOJA": loja.get("nome", ""),
                "produto_meta": m["produto"],
                "valor": float(m.get("valor", 0)),
            }
        )

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["LOJA", "produto_meta"], keep="first")

    if not df.empty:
        df_pivot = df.pivot_table(
            index="LOJA",
            columns="produto_meta",
            values="valor",
            aggfunc="sum",
            fill_value=0,
        ).reset_index()
        return df_pivot

    return pd.DataFrame(columns=["LOJA"])


@st.cache_data(ttl=21600)
def _metas_produto_consultor_atual(mes: int, ano: int) -> pd.DataFrame:
    """Metas por produto (CONSULTOR) — mes corrente. TTL 6h."""
    return _fetch_metas_produto_consultor(mes, ano)


@st.cache_data(ttl=86400)
def _metas_produto_consultor_historico(mes: int, ano: int) -> pd.DataFrame:
    """Metas por produto (CONSULTOR) — historico. TTL 24h."""
    return _fetch_metas_produto_consultor(mes, ano)


# ══════════════════════════════════════════════════════
# Lojas, regioes e consultores de cadastro
# ══════════════════════════════════════════════════════


@st.cache_data(ttl=86400)
def carregar_lojas_regioes() -> tuple[list[str], list[str]]:
    """Retorna (lojas, regioes) para selects de configuracao. TTL 24h."""
    resp = (
        _sb()
        .table("lojas")
        .select("nome, regioes(nome)")
        .order("nome")
        .execute()
    )
    lojas: list[str] = []
    regioes_set: set[str] = set()
    for row in resp.data or []:
        lojas.append(row.get("nome", ""))
        reg = (row.get("regioes") or {}).get("nome", "")
        if reg:
            regioes_set.add(reg)
    return sorted(lojas), sorted(regioes_set)


@st.cache_data(ttl=86400)
def carregar_lojas_ativas() -> pd.DataFrame:
    """Lojas ATIVAS com a regiao atual, para filtros por escopo.

    Retorna DataFrame [LOJA, REGIAO_ATUAL] das lojas com ativo=true
    (regiao atual via regioes(nome)). Permite listar as lojas da regiao
    do gerente mesmo SEM producao ou meta no periodo. Carrega global; o
    recorte por perfil e client-side (aplicar_rls por REGIAO_ATUAL).
    TTL 24h.
    """
    resp = (
        _sb()
        .table("lojas")
        .select("nome, regioes(nome)")
        .eq("ativo", True)
        .order("nome")
        .execute()
    )
    rows = []
    for row in resp.data or []:
        rows.append(
            {
                "LOJA": row.get("nome", "") or "",
                "REGIAO_ATUAL": (row.get("regioes") or {}).get("nome", "")
                or "",
            }
        )
    return pd.DataFrame(rows, columns=["LOJA", "REGIAO_ATUAL"])


def carregar_universo_lojas(mes: int, ano: int) -> pd.DataFrame:
    """Universo de lojas do periodo p/ visoes de controle (sem producao).

    Mes corrente: lojas ATIVAS (organograma de hoje; REGIAO := regiao
    atual). Historico: lojas com meta no periodo — mesmo proxy
    point-in-time ja aceito em _fetch_metas (preserva lojas que tinham
    meta, mesmo inativas hoje). Retorna [LOJA, REGIAO, REGIAO_ATUAL];
    carrega global, recorte por perfil client-side (aplicar_rls).
    Reusa loaders cacheados — sem fetch adicional.
    """
    cols = ["LOJA", "REGIAO", "REGIAO_ATUAL"]
    if _eh_mes_atual(mes, ano):
        df_ativas = carregar_lojas_ativas()
        if df_ativas.empty:
            return pd.DataFrame(columns=cols)
        df_u = df_ativas.copy()
        df_u["REGIAO"] = df_u["REGIAO_ATUAL"]
        return df_u[cols]

    df_metas = carregar_metas(mes, ano)
    if df_metas.empty or "LOJA" not in df_metas.columns:
        return pd.DataFrame(columns=cols)
    df_u = df_metas.reindex(columns=cols, fill_value="")
    return df_u.drop_duplicates(subset=["LOJA"]).reset_index(drop=True)


# ══════════════════════════════════════════════════════
# Metas individuais por consultor
# ══════════════════════════════════════════════════════


def _fetch_metas_consultor(
    mes: int, ano: int, loja: str,
) -> dict:
    """
    Carrega Meta Prata/Ouro individuais (escopo CONSULTOR)
    da loja informada.
    """
    periodo = carregar_periodo(mes, ano)
    if not periodo or not loja:
        return {"meta_prata": 0.0, "meta_ouro": 0.0}

    resp = (
        _sb()
        .table("metas")
        .select("produto, escopo, nivel, valor, lojas(nome)")
        .eq("periodo_id", periodo["id"])
        .eq("escopo", "CONSULTOR")
        .eq("produto", "GERAL")
        .in_("nivel", ["PRATA", "OURO"])
        .execute()
    )

    meta_prata = 0.0
    meta_ouro = 0.0
    for m in resp.data or []:
        loja_m = (m.get("lojas") or {}).get("nome", "")
        if loja_m != loja:
            continue
        valor = float(m.get("valor", 0) or 0)
        if m.get("nivel") == "PRATA":
            meta_prata = valor
        elif m.get("nivel") == "OURO":
            meta_ouro = valor

    return {"meta_prata": meta_prata, "meta_ouro": meta_ouro}


@st.cache_data(ttl=21600)
def _metas_consultor_atual(
    mes: int, ano: int, loja: str,
) -> dict:
    """Metas CONSULTOR — mes corrente. TTL 6h."""
    return _fetch_metas_consultor(mes, ano, loja)


@st.cache_data(ttl=86400)
def _metas_consultor_historico(
    mes: int, ano: int, loja: str,
) -> dict:
    """Metas CONSULTOR — historico. TTL 24h."""
    return _fetch_metas_consultor(mes, ano, loja)


def carregar_metas_consultor(
    mes: int, ano: int, loja: str,
) -> dict:
    """
    Retorna ``{"meta_prata": float, "meta_ouro": float}``
    com as metas individuais (escopo CONSULTOR) para a
    loja do consultor logado.
    """
    if _eh_mes_atual(mes, ano):
        return _metas_consultor_atual(mes, ano, loja)
    return _metas_consultor_historico(mes, ano, loja)


def _status_consultor_ativo(status) -> bool:
    """True se o status do cadastro indica consultor ativo.

    Match por prefixo ("Ativo (a)") — substring aceitaria "Inativo (a)".
    Status vazio/nulo conta como ativo (linhas legadas sem status).
    """
    s = (status or "").strip().lower()
    return not s or s.startswith("ativo")


def _colapsar_cadastro_recente(rows: list[dict]) -> list[dict]:
    """Colapsa cadastro duplicado: 1 registro por nome normalizado,
    vencendo o de ``updated_at`` mais recente.

    A tabela ``consultores`` tem nomes duplicados (ex.: desligamento
    registrado em linha nova, deixando o 'Ativo (a)' antigo orfao) —
    sem o colapso, a pessoa segue no universo de ativos indevidamente.
    Comparacao lexicografica funciona: timestamps ISO 8601 em UTC.
    """
    por_nome: dict[str, dict] = {}
    for row in rows:
        nome = " ".join(str(row.get("nome") or "").upper().split())
        if not nome:
            continue
        atual = por_nome.get(nome)
        if atual is None or (
            (row.get("updated_at") or "") > (atual.get("updated_at") or "")
        ):
            por_nome[nome] = row
    return [por_nome[k] for k in sorted(por_nome)]


@st.cache_data(ttl=1800)
def carregar_consultores_cadastro() -> list[str]:
    """
    Retorna lista ordenada de nomes de consultores
    cadastrados em ``consultores`` (ativos).

    Cadastro duplicado colapsa no registro mais recente
    (``updated_at``) antes do filtro de status. Usado em
    selects de configuracao (cadastro de usuario e
    'Visualizar Como'). TTL 30min — reflete uploads do
    angry-man sem esperar um dia.
    """
    resp = (
        _sb()
        .table("consultores")
        .select("nome, status, updated_at")
        .order("nome")
        .execute()
    )
    nomes: list[str] = []
    for row in _colapsar_cadastro_recente(resp.data or []):
        if not _status_consultor_ativo(row.get("status")):
            continue
        nome = row.get("nome", "")
        if nome:
            nomes.append(nome)
    return sorted(set(nomes))


@st.cache_data(ttl=1800)
def carregar_consultores_ativos() -> pd.DataFrame:
    """Consultores ATIVOS com loja-base e regiao atual.

    Retorna DataFrame [CONSULTOR, LOJA, REGIAO, REGIAO_ATUAL] dos
    consultores com status ativo e loja-base ativa (mesmo criterio de
    status de carregar_consultores_cadastro). Universo p/ visoes de
    controle (consultor sem producao no periodo). REGIAO := regiao
    ATUAL da loja-base — o cadastro de consultores nao tem vigencia
    temporal, entao meses historicos refletem o organograma de hoje.
    Nomes duplicados colapsam no registro de ``updated_at`` mais
    recente (desligamento novo vence 'Ativo (a)' antigo). Carrega
    global; recorte por perfil client-side (aplicar_rls). TTL 24h.
    """
    cols = ["CONSULTOR", "LOJA", "REGIAO", "REGIAO_ATUAL"]
    resp = (
        _sb()
        .table("consultores")
        .select(
            "nome, status, updated_at, lojas(nome, ativo, regioes(nome))"
        )
        .order("nome")
        .execute()
    )
    rows = []
    for row in _colapsar_cadastro_recente(resp.data or []):
        if not _status_consultor_ativo(row.get("status")):
            continue
        nome = (row.get("nome") or "").strip()
        if not nome:
            continue
        loja = row.get("lojas") or {}
        if not loja.get("ativo", True):
            continue
        regiao = (loja.get("regioes") or {}).get("nome", "") or ""
        rows.append(
            {
                "CONSULTOR": nome,
                "LOJA": loja.get("nome", "") or "",
                "REGIAO": regiao,
                "REGIAO_ATUAL": regiao,
            }
        )
    df = pd.DataFrame(rows, columns=cols)
    if not df.empty:
        df = df.drop_duplicates(subset=["CONSULTOR"]).reset_index(drop=True)
    return df


# ══════════════════════════════════════════════════════
# Supervisores
# ══════════════════════════════════════════════════════


@st.cache_data(ttl=1800)
def carregar_supervisores() -> pd.DataFrame:
    """Carrega supervisores com suas lojas e regioes. TTL 30min
    (reflete uploads do angry-man sem esperar horas)."""
    resp = (
        _sb().table("supervisores").select("nome, lojas(nome), regioes(nome)").execute()
    )

    if not resp.data:
        return pd.DataFrame(columns=["SUPERVISOR", "LOJA", "REGIAO"])

    rows = []
    for s in resp.data:
        loja = s.get("lojas") or {}
        regiao = s.get("regioes") or {}
        rows.append(
            {
                "SUPERVISOR": s.get("nome", ""),
                "LOJA": loja.get("nome", ""),
                "REGIAO": regiao.get("nome", ""),
            }
        )

    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════
# Consolidacao: aplicacao das regras de negocio
# ══════════════════════════════════════════════════════


def consolidar_dados(
    mes: int,
    ano: int,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Carrega, consolida e aplica pontuacao/regras.

    Delega o processamento pesado para a camada de cache
    e popula o diagnostico no session_state (side-effect
    que nao pode viver dentro de cache_data).

    TTL real: 30min para mes corrente, 24h para historico.

    Returns:
        (df_consolidado, df_metas, df_supervisores)
    """
    # Cache version bump = 3 (forca recalculo apos fix super_conta)
    if _eh_mes_atual(mes, ano):
        resultado = _consolidar_atual(mes, ano, _cache_version=3)
    else:
        resultado = _consolidar_historico(mes, ano, _cache_version=3)

    df, df_metas, df_supervisores, diag = resultado

    # Side-effect: diagnostico no session_state
    if diag:
        st.session_state["_diag_pontuacao"] = diag

    return df, df_metas, df_supervisores


@st.cache_data(ttl=1800)
def _consolidar_atual(
    mes: int,
    ano: int,
    _cache_version: int = 3,  # bump v3: fix super conta
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Optional[dict]]:
    """Consolidacao — mes corrente. TTL 30min."""
    return _executar_consolidacao(mes, ano)


@st.cache_data(ttl=86400)
def _consolidar_historico(
    mes: int,
    ano: int,
    _cache_version: int = 3,  # bump v3: fix super conta
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Optional[dict]]:
    """Consolidacao — historico. TTL 24h."""
    return _executar_consolidacao(mes, ano)


def _executar_consolidacao(
    mes: int,
    ano: int,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Optional[dict]]:
    """Consolidacao cacheada — pura, sem side-effects."""
    df = carregar_contratos_pagos(mes, ano)
    df_pontos = carregar_pontuacao_efetiva(mes, ano)
    df_metas = carregar_metas(mes, ano)
    df_supervisores = carregar_supervisores()

    if df.empty:
        return df, df_metas, df_supervisores, None

    df = _preencher_categoria_fallback(df)

    # Mapear pontos por categoria_codigo
    if not df_pontos.empty:
        mapa_pontos = dict(
            zip(
                df_pontos["categoria_codigo"],
                df_pontos["pontos"].astype(float),
            )
        )
        df["PONTOS"] = df["categoria_codigo"].map(mapa_pontos).fillna(0)
    else:
        mapa_pontos = {}
        df["PONTOS"] = 0

    # PORTABILIDADE herda a pontuacao do CONSIG do banco origem.
    # Regra: Portabilidade BMG -> CONSIG_BMG, C6 -> CONSIG_C6,
    # Itau -> CONSIG_ITAU. CONSIG_PRIV nao se aplica a portabilidade
    # (produto distinto). Bancos sem mapeamento permanecem com 0.
    # Resolvido em codigo (nao via tabela pontuacao) porque o
    # diferencial e o BANCO do contrato, granularidade maior que
    # categoria.
    if "BANCO" in df.columns:
        mask_portab = df["categoria_codigo"] == "PORTABILIDADE"
        if mask_portab.any():
            banco_norm = (
                df.loc[mask_portab, "BANCO"]
                .astype(str).str.strip().str.upper()
            )
            consig_alvo = banco_norm.map(_PORTAB_BANCO_TO_CONSIG)
            pts_alias = consig_alvo.map(mapa_pontos)
            df.loc[mask_portab, "PONTOS"] = pts_alias.fillna(0).astype(
                float
            )

    # ── Diagnostico de mapeamento ──────────────────
    total = len(df)
    sem_cat = (df["categoria_codigo"] == "").sum()
    com_cat = total - sem_cat
    com_pontos = (df["PONTOS"] > 0).sum()
    sem_pontos = com_cat - com_pontos

    tipos_sem_cat: list = []
    if sem_cat > 0 and "TIPO_PRODUTO" in df.columns:
        tipos_sem_cat = (
            df.loc[df["categoria_codigo"] == "", "TIPO_PRODUTO"]
            .value_counts()
            .reset_index()
            .rename(columns={"TIPO_PRODUTO": "tipo", "count": "qtd"})
            .to_dict(orient="records")
        )

    diag = {
        "total_contratos": total,
        "sem_categoria": int(sem_cat),
        "com_categoria": int(com_cat),
        "com_pontos_mapeados": int(com_pontos),
        "sem_pontos_mapeados": int(sem_pontos),
        "categorias_no_contrato": (
            sorted(df["categoria_codigo"].unique().tolist())
        ),
        "categorias_na_pontuacao": sorted(mapa_pontos.keys()),
        "mapa_pontos": mapa_pontos,
        "tipos_sem_categoria": tipos_sem_cat,
    }
    # ───────────────────────────────────────────────

    # Aplicar regras de exclusao:
    # Produtos com conta_valor=false → VALOR = 0
    # Produtos com conta_pontuacao=false → pontos = 0
    mask_sem_valor = df["conta_valor"] == False  # noqa
    mask_sem_pontos = df["conta_pontuacao"] == False  # noqa

    df.loc[mask_sem_valor, "VALOR"] = 0
    df["pontos"] = df["VALOR"] * df["PONTOS"]
    df.loc[mask_sem_pontos, "pontos"] = 0

    # Super Conta: CNC com subtipo especifico — conta valor/pontos
    # como CNC e tambem e contado como producao Super Conta
    # Usar strip() e upper() para ser robusto contra espacos
    df["is_super_conta"] = (
        df["SUBTIPO"]
        .astype(str)
        .str.strip()
        .str.upper() == "SUPER CONTA"
    )

    # Classificacoes por TIPO OPER. (mesma logica do dashboard original)
    col_tipo_oper = "TIPO OPER."

    # Emissao de cartao: contam apenas quantidade
    df["is_emissao_cartao"] = (
        df[col_tipo_oper].isin(["CARTÃO BENEFICIO", "Venda Pré-Adesão"])
        if col_tipo_oper in df.columns
        else False
    )

    # Zerar valor/pontos de emissoes nao cobertas por conta_valor=false
    # (ex: Venda Pre-Adesao com produto CONSIG tem categoria CONSIG_BMG
    # que possui conta_valor=true, mas o TIPO OPER. indica emissao)
    mask_emissao = df["is_emissao_cartao"]
    if mask_emissao.any():
        df.loc[mask_emissao, "VALOR"] = 0
        df.loc[mask_emissao, "pontos"] = 0

    # Seguros: contam apenas quantidade (valor/pontos ja zerados acima)
    # Fallback para categoria_codigo caso tipo_operacao nao esteja preenchido
    df["is_bmg_med"] = (
        (df[col_tipo_oper] == "BMG MED")
        if col_tipo_oper in df.columns
        else (df["categoria_codigo"] == "BMG_MED")
    )
    df["is_seguro_vida"] = (
        (df[col_tipo_oper] == "Seguro")
        if col_tipo_oper in df.columns
        else (df["categoria_codigo"] == "SEGURO_VIDA")
    )

    return df, df_metas, df_supervisores, diag


# ══════════════════════════════════════════════════════
# Pagamentos online (extrator DNA — estimativa do dia)
#
# Fonte: view v_pagamentos_online_efetivo. A view ja aplica
# o filtro Agrupamento='Paga', o calculo de valor_producao e
# a exclusao das ADEs ja consolidadas em `contratos`.
#
# Ingestao via angry-man (TRUNCATE+INSERT horario). TTL
# de cache curto (5 min) — menor que o ciclo de importacao
# para nao mostrar dado anterior por muito tempo.
# ══════════════════════════════════════════════════════


def carregar_pagamentos_online() -> pd.DataFrame:
    """Carrega pagamentos online via v_pagamentos_online_efetivo.

    TTL: 5min. Sempre snapshot atual — a view nao depende de
    periodo (mes/ano).
    """
    return _pagamentos_online_cache()


@st.cache_data(ttl=300)
def _pagamentos_online_cache() -> pd.DataFrame:
    """Pagamentos online — snapshot do dia. TTL 5min."""
    return _fetch_pagamentos_online()


def _fetch_pagamentos_online() -> pd.DataFrame:
    """Executa a query da view sem cache, paginada.

    Cursor keyset por ``proposta`` (PK de pagamentos_online). A ordem
    antiga (data_status desc) foi dispensada: a aba so agrega
    (max/sum/len) — nenhum consumidor depende da ordem das linhas.
    """
    all_data = _paginar_keyset(
        lambda: (
            _sb()
            .from_("v_pagamentos_online_efetivo")
            .select("*")
            .order("proposta")
            .limit(_PAGE_SIZE)
        ),
        "proposta",
    )

    if not all_data:
        return pd.DataFrame()

    rows = []
    for r in all_data:
        rows.append(
            {
                "PROPOSTA": r.get("proposta", ""),
                "DATA_IMPLANTACAO": r.get("data_implantacao"),
                "DATA_STATUS": r.get("data_status"),
                "CLIENTE": r.get("cliente", ""),
                "GRUPO_PRODUTO": r.get("grupo_produto", ""),
                "PRODUTO": r.get("produto", ""),
                "LOJA_CODIGO": r.get("loja_codigo", ""),
                "LOJA": r.get("loja_nome") or "",
                "REGIAO_ID": r.get("regiao_id"),
                "CONSULTOR": r.get("usuario_nome") or "",
                "VALOR_LIQ_DIGITADO": float(
                    r.get("valor_liquido_digitado") or 0
                ),
                "VALOR_LIQ_APROVADO": float(
                    r.get("valor_liquido_aprovado") or 0
                ),
                "VALOR_SEGURO_APROVADO": float(
                    r.get("valor_seguro_aprovado") or 0
                ),
                "VALOR": float(r.get("valor_producao") or 0),
                "IMPORTED_AT": r.get("imported_at"),
            }
        )

    df = pd.DataFrame(rows)

    if "DATA_IMPLANTACAO" in df.columns:
        df["DATA_IMPLANTACAO"] = pd.to_datetime(
            df["DATA_IMPLANTACAO"], errors="coerce"
        )
    if "DATA_STATUS" in df.columns:
        df["DATA_STATUS"] = pd.to_datetime(
            df["DATA_STATUS"], errors="coerce"
        )
    if "IMPORTED_AT" in df.columns:
        df["IMPORTED_AT"] = pd.to_datetime(
            df["IMPORTED_AT"], errors="coerce", utc=True
        )

    return df


# ══════════════════════════════════════════════════════
# Reconquista MG CRED (v2)
#
# Export unico, 1 linha por cliente (co_adesao), ja
# classificado em `status` (EFETIVADA/PROMESSA/SEM
# RECONQUISTA). Fonte: view `v_reconquista`. A apuracao e
# MENSAL pelo mes de dt_fim_relacionamento (ref_ano/ref_mes),
# com DEFASAGEM de 1 mes: a apuracao do mes M exibe os
# contratos cujo dt_fim caiu em M-1 (os de M so entram na
# esteira no mes seguinte).
#
# KPIs (3 estados + taxa) e a quebra por loja sao derivados
# em pandas a partir da view detalhada. Ver
# docs/agents/business-rules.md.
# ══════════════════════════════════════════════════════

def _faixa_premio_conversao(pct: float) -> Dict:
    """Mapeia % de conversao -> faixa de premio/deflator sobre premio CNC.

    Substitui a meta fixa: o percentual alcancado sobre a base ELEGIVEL
    define o ajuste (indicador — nao calcula R$). Faixas (tabela de
    negocio, limite superior inclusivo nas negativas):
        0 a 10%      -> -20%
        10,1 a 20%   -> -10%
        20,1 a 29,99 ->   0
        30 a 39,99   -> +10%
        >= 40        -> +20%
    Retorna {ajuste_pct, rotulo, cor}.
    """
    if pct <= 10:
        ajuste = -20
    elif pct <= 20:
        ajuste = -10
    elif pct < 30:
        ajuste = 0
    elif pct < 40:
        ajuste = 10
    else:
        ajuste = 20

    if ajuste < 0:
        cor = "#E5484D" if ajuste <= -20 else "#E5844D"
        rotulo = f"{ajuste}% sobre prêmio CNC"
    elif ajuste == 0:
        cor = "var(--mg-text-muted)"
        rotulo = "0 (neutro)"
    else:
        cor = "#10A37F" if ajuste >= 20 else "#3E9B4F"
        rotulo = f"+{ajuste}% sobre prêmio CNC"
    return {"ajuste_pct": ajuste, "rotulo": rotulo, "cor": cor}


def _mask_elegivel(clientes: pd.DataFrame) -> pd.Series:
    """Mascara ELEGIVEL. Sem coluna ou valor ausente/NULL => ELEGIVEL
    (decisao: interim conta como elegivel). NAO ELEGIVEL (com/sem
    acento) sai da apuracao."""
    if clientes is None or clientes.empty:
        return pd.Series([], dtype=bool)
    if "flag_elegibilidade" not in clientes.columns:
        return pd.Series(True, index=clientes.index)
    norm = (
        clientes["flag_elegibilidade"].fillna("").astype(str)
        .str.upper().str.strip()
    )
    return ~norm.str.startswith(("NAO", "NÃO"))


def _mes_apuracao_anterior(mes: int, ano: int) -> Tuple[int, int]:
    """Defasagem de 1 mes: apuracao de (mes, ano) -> mes anterior."""
    ref_mes = mes - 1
    ref_ano = ano
    if ref_mes == 0:
        ref_mes = 12
        ref_ano = ano - 1
    return ref_mes, ref_ano


def _mes_apuracao_seguinte(mes: int, ano: int) -> Tuple[int, int]:
    """Apuracao seguinte de (mes, ano) -> mes posterior (rollover dez->jan)."""
    prox_mes = mes + 1
    prox_ano = ano
    if prox_mes == 13:
        prox_mes = 1
        prox_ano = ano + 1
    return prox_mes, prox_ano


def _fetch_reconquista(ref_ano: int, ref_mes: int) -> List[dict]:
    """Pagina v_reconquista filtrada pelo periodo de referencia.

    Cursor keyset por ``co_adesao`` (UNIQUE, migration 028). Corrige a
    paginacao anterior, que usava OFFSET sem ORDER BY — ordem instavel
    podia repetir/perder linhas entre paginas.
    """
    return _paginar_keyset(
        lambda: (
            _sb()
            .from_("v_reconquista")
            .select("*")
            .eq("ref_ano", ref_ano)
            .eq("ref_mes", ref_mes)
            .order("co_adesao")
            .limit(_PAGE_SIZE)
        ),
        "co_adesao",
    )


@st.cache_data(ttl=600)
def _reconquista_cache(mes: int, ano: int) -> dict:
    """Detalhe cacheado do mes de referencia (defasado). TTL 10min.

    Inclui tambem o detalhe do mes de referencia ANTERIOR
    (`clientes_ant`), usado para a variacao periodo-a-periodo.
    """
    ref_mes, ref_ano = _mes_apuracao_anterior(mes, ano)
    prev_mes, prev_ano = _mes_apuracao_anterior(ref_mes, ref_ano)
    return {
        "ref_mes": ref_mes,
        "ref_ano": ref_ano,
        "clientes": pd.DataFrame(_fetch_reconquista(ref_ano, ref_mes)),
        "clientes_ant": pd.DataFrame(_fetch_reconquista(prev_ano, prev_mes)),
        # Esteira da PROXIMA apuracao: o proprio mes selecionado e o
        # ref dela (a apuracao seguinte exibe dt_fim deste mes). Usado
        # para a previa antecipada das promessas que ja se acumulam.
        "clientes_prox": pd.DataFrame(_fetch_reconquista(ano, mes)),
    }


def _filtrar_rls_reconquista(dados: dict) -> dict:
    """Aplica RLS sobre os detalhes (`clientes`/`clientes_ant`).

    A view expoe `regiao`, `loja` e `consultor` em texto.
    Admin/gestor veem tudo; demais perfis sao restritos ao seu
    escopo (regiao/loja/consultor).
    """
    perfil = _obter_perfil_efetivo()
    if not perfil or perfil["perfil"] in ("admin", "gestor"):
        return dados

    escopo = perfil.get("escopo") or []
    if not escopo:
        return dados

    coluna = {
        "gerente_comercial": "regiao",
        "supervisor": "loja",
        "consultor": "consultor",
    }.get(perfil["perfil"])
    if not coluna:
        return dados

    def _filtra(df):
        if df is None or df.empty or coluna not in df.columns:
            return df
        return df[df[coluna].isin(escopo)].copy()

    return {
        **dados,
        "clientes": _filtra(dados.get("clientes")),
        "clientes_ant": _filtra(dados.get("clientes_ant")),
        "clientes_prox": _filtra(dados.get("clientes_prox")),
    }


def _totais_reconquista(clientes: pd.DataFrame) -> Dict:
    """KPIs do mes sobre a base ELEGIVEL: contagem por estado +
    conversao (= EFETIVADA / elegiveis) + faixa de premio/deflator.

    Somente ELEGIVEL contam na conversao (NULL/sem flag => ELEGIVEL);
    os NAO ELEGIVEL seguem visiveis nos analiticos, so fora da conta.
    """
    vazio = {
        "total": 0, "total_geral": 0, "nao_elegivel": 0,
        "efetivadas": 0, "promessas": 0, "sem_reconquista": 0,
        "conversao": 0.0, "faixa": _faixa_premio_conversao(0.0),
    }
    if clientes is None or clientes.empty or "status" not in clientes.columns:
        return vazio

    total_geral = len(clientes)
    eleg = clientes[_mask_elegivel(clientes)]
    total = len(eleg)
    if total == 0:
        return {**vazio, "total_geral": total_geral, "nao_elegivel": total_geral}

    vc = eleg["status"].value_counts()
    efetivadas = int(vc.get("EFETIVADA", 0))
    conversao = efetivadas / total * 100
    return {
        "total": total,                    # base elegivel (denominador)
        "total_geral": total_geral,        # todos (contexto)
        "nao_elegivel": total_geral - total,
        "efetivadas": efetivadas,
        "promessas": int(vc.get("PROMESSA", 0)),
        "sem_reconquista": int(vc.get("SEM RECONQUISTA", 0)),
        "conversao": conversao,
        "faixa": _faixa_premio_conversao(conversao),
    }


def _por_loja_reconquista(clientes: pd.DataFrame) -> pd.DataFrame:
    """Quebra por loja/regiao sobre a base ELEGIVEL: 3 estados +
    conversao (EFETIVADA / elegiveis da loja) + faixa."""
    if clientes is None or clientes.empty or "loja" not in clientes.columns:
        return pd.DataFrame()

    df = clientes[_mask_elegivel(clientes)].copy()  # so elegiveis na apuracao
    if df.empty:
        return pd.DataFrame()
    df["_efet"] = (df["status"] == "EFETIVADA").astype(int)
    df["_prom"] = (df["status"] == "PROMESSA").astype(int)
    df["_sem"] = (df["status"] == "SEM RECONQUISTA").astype(int)

    g = (
        df.groupby(["loja", "regiao"], dropna=False)
        .agg(
            total_clientes=("co_adesao", "count"),
            efetivadas=("_efet", "sum"),
            promessas=("_prom", "sum"),
            sem_reconquista=("_sem", "sum"),
            saldo_medio=("saldo_contabil", "mean"),
            dias_atraso_medio=("dias_atraso", "mean"),
        )
        .reset_index()
    )
    g["conversao_pct"] = (
        g["efetivadas"] * 100.0
        / g["total_clientes"].where(g["total_clientes"] > 0)
    ).round(1)
    g["faixa"] = g["conversao_pct"].fillna(0.0).map(
        lambda p: _faixa_premio_conversao(p)["rotulo"]
    )
    return g.sort_values("efetivadas", ascending=False)


def carregar_reconquista(mes: int, ano: int) -> Dict:
    """Dados de reconquista do mes de apuracao (mes, ano).

    Aplica a defasagem de 1 mes (exibe dt_fim_relacionamento do
    mes anterior) e RLS por perfil. Estrutura:
        {
            "ref_mes": int, "ref_ano": int,
            "totais":   dict,        # elegiveis/efetivadas/conversao/faixa
            "por_loja": DataFrame,   # quebra por loja (elegiveis)
            "clientes": DataFrame,   # detalhe (TODOS os clientes + flag)
            "prox":     dict,        # previa da apuracao seguinte (mes+1)
        }

    Conversao/apuracao contam so ELEGIVEL; `clientes` mantem todos.
    TTL 10min no fetch; KPIs derivados apos a RLS.
    """
    dados = _filtrar_rls_reconquista(_reconquista_cache(mes, ano))
    clientes = dados.get("clientes", pd.DataFrame())
    clientes_ant = dados.get("clientes_ant", pd.DataFrame())
    clientes_prox = dados.get("clientes_prox", pd.DataFrame())

    totais = _totais_reconquista(clientes)
    # Promessas do periodo anterior (so elegiveis) p/ a variacao.
    if (
        clientes_ant is not None
        and not clientes_ant.empty
        and "status" in clientes_ant.columns
    ):
        _ant_eleg = clientes_ant[_mask_elegivel(clientes_ant)]
        totais["promessas_anterior"] = int(
            (_ant_eleg["status"] == "PROMESSA").sum()
        )
    else:
        totais["promessas_anterior"] = 0

    # Previa da proxima apuracao (mes+1): exibe os clientes cujo
    # dt_fim caiu no mes selecionado, ja na esteira mas ainda sem a
    # virada da macica (EFETIVADA tende a 0 ate la). O ref da previa
    # e o proprio (mes, ano).
    prox_apur_mes, prox_apur_ano = _mes_apuracao_seguinte(mes, ano)
    prox = {
        "ref_mes": mes,
        "ref_ano": ano,
        "apuracao_mes": prox_apur_mes,
        "apuracao_ano": prox_apur_ano,
        "totais": _totais_reconquista(clientes_prox),
    }

    return {
        "ref_mes": dados.get("ref_mes"),
        "ref_ano": dados.get("ref_ano"),
        "totais": totais,
        "por_loja": _por_loja_reconquista(clientes),
        "clientes": clientes,
        "prox": prox,
    }
