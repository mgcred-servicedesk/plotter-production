"""
Camada de dados do dashboard — acesso ao Supabase.

Cada loader expoe uma API publica (``carregar_*``) que
delega para duas funcoes cacheadas separadas — uma para
o mes corrente (TTL curto) e outra para o historico
(TTL longo) — via ``_eh_mes_atual``.

``consolidar_dados`` aplica as regras de negocio (pontos,
emissoes, seguros, Super Conta) sobre os contratos pagos.
``carregar_periodo_dashboard`` compoe esse resultado com os
demais frames do periodo e e o entrypoint usado pelo ``main``
do dashboard.

O cache lida com side-effects (ex: diagnostico em
``session_state``) na funcao wrapper externa, nunca
dentro de ``@st.cache_data`` — Streamlit nao garante
side-effects em funcoes cacheadas.
"""

import logging
import time
import uuid
import calendar
from datetime import date, datetime
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple

import pandas as pd
import streamlit as st
from postgrest.exceptions import APIError

from src.config.settings import NOMES_DISPLAY_PRODUTO
from src.config.supabase_client import get_supabase_client
from src.dashboard.kpis.detalhes_cards import aplicar_conta_valor
from src.dashboard.kpis.gerais import (
    excluir_lojas_backoffice,
    excluir_supervisores,
    filtrar_janela_recente,
)
from src.dashboard.rls import _obter_perfil_efetivo, aplicar_rls
from src.shared.dias_uteis import carregar_feriados

logger = logging.getLogger(__name__)


_PAGE_SIZE = 1000

# Plano de tentativas de UMA pagina do keyset: (limite, espera_antes).
# So entra em acao no erro 57014 (statement_timeout) — ver
# _e_timeout_statement. O Supabase roda em compute Nano e a paginacao de
# v_contratos_dashboard mede ~1-2s por pagina em repouso, mas ja foi
# medida em 4s sob contencao (ETL do angry-man escrevendo em contratos);
# com o teto de 15s por statement, uma rajada de escrita concorrente
# cancela a pagina e derruba a carga inteira do dashboard.
#
# A 3a tentativa reduz o lote: menos linhas por statement = menos
# trabalho por transacao, entao a pagina cabe no teto mesmo com o banco
# ocupado. Quem pagina PRECISA comparar len(batch) com o limite
# efetivamente usado (nao com _PAGE_SIZE) — por isso _executar_pagina
# devolve os dois.
_TENTATIVAS_PAGINA: Tuple[Tuple[int, float], ...] = (
    (_PAGE_SIZE, 0.0),
    (_PAGE_SIZE, 1.5),
    (_PAGE_SIZE // 4, 4.0),
)

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
    # VALOR = valor CONSOLIDADO (migration 067). Igual ao VLR BASE em
    # toda linha que nao e Cobranca Consignavel; VLR BRUTO nas que sao
    # (GREATEST, nunca reduz). Todo KPI de producao e a pontuacao
    # (VALOR x PTS) leem esta coluna — ver business-rules.md.
    "valor_consolidado": "VALOR",
    # VLR BASE cru, so para auditoria/exibicao. NAO passa pelas regras
    # da consolidacao (conta_valor/emissao zeram VALOR, nao
    # VALOR_BASE): nunca somar VALOR_BASE como producao.
    "valor": "VALOR_BASE",
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


def _e_timeout_statement(exc: APIError) -> bool:
    """True se a APIError for o cancelamento por statement_timeout.

    57014 (``query_canceled``) e o unico erro que vale reexecutar: e
    transitorio por definicao — o planejamento e a query nao mudaram,
    o banco e que estava ocupado demais para entregar dentro do teto.
    Qualquer outro codigo (permissao, coluna inexistente, sintaxe) e
    deterministico e sobe intacto; retentar so atrasaria o erro.
    """
    return str(getattr(exc, "code", "")) == "57014"


def _executar_pagina(
    montar_pagina: Callable[[int], Any],
    rotulo: str,
) -> Tuple[List[dict], int]:
    """Executa uma pagina do keyset, reexecutando em statement_timeout.

    Devolve ``(linhas, limite_usado)``. O limite VOLTA junto porque a
    ultima tentativa reduz o lote: quem pagina decide o fim do resultset
    por ``len(linhas) < limite_usado``, e comparar com ``_PAGE_SIZE``
    encerraria a paginacao cedo — truncando dados em silencio — sempre
    que uma pagina reduzida viesse cheia.

    Esgotadas as tentativas, o ultimo 57014 sobe: timeout persistente e
    sintoma de banco degradado, nao algo para mascarar com resultado
    parcial.
    """
    ultimo_erro: Optional[APIError] = None
    total = len(_TENTATIVAS_PAGINA)

    for tentativa, (limite, espera) in enumerate(_TENTATIVAS_PAGINA, 1):
        if espera:
            time.sleep(espera)
        try:
            return (montar_pagina(limite).execute().data or []), limite
        except APIError as exc:
            if not _e_timeout_statement(exc):
                raise
            ultimo_erro = exc
            logger.warning(
                "statement_timeout em %s (tentativa %d/%d, limite %d)",
                rotulo,
                tentativa,
                total,
                limite,
            )

    logger.error("statement_timeout persistente em %s — desisto", rotulo)
    raise ultimo_erro  # type: ignore[misc]


def _paginar_keyset(
    montar_query: Callable[[int], Any], coluna_chave: str
) -> List[dict]:
    """Pagina por cursor: WHERE chave > ultimo ORDER BY chave LIMIT N.

    Substitui a paginacao por OFFSET: com OFFSET cada pagina reordena o
    resultset inteiro (sort que spilla para temp files no Postgres —
    dreno do Disk IO Budget, ver migration 054); com cursor todo request
    e um top-N de no maximo _PAGE_SIZE linhas, que cabe em work_mem.

    ``montar_query`` recebe o LIMITE da pagina e devolve a query base ja
    com ``.order(coluna_chave)`` e ``.limit(<limite>)`` — o limite e
    parametro (nao ``_PAGE_SIZE`` fixo) porque o retry de
    ``_executar_pagina`` reduz o lote na ultima tentativa.
    ``coluna_chave`` deve ser UNICA (PK/UNIQUE) — chave repetida faria
    linhas serem puladas entre paginas.
    """
    all_data: List[dict] = []
    ultimo = None
    while True:

        def montar_pagina(limite: int, _ultimo=ultimo):
            query = montar_query(limite)
            if _ultimo is not None:
                query = query.gt(coluna_chave, _ultimo)
            return query

        batch, limite_usado = _executar_pagina(montar_pagina, coluna_chave)
        all_data.extend(batch)
        if len(batch) < limite_usado:
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


def aplicar_nomes_display_produto(frame: pd.DataFrame) -> pd.DataFrame:
    """Troca as chaves internas de ``grupo_dashboard`` pelo rotulo de UI.

    ``NOMES_DISPLAY_PRODUTO`` mapeia a chave de dados (ex: ``PACK``) para
    o nome amigavel exibido na interface, sem alterar nada no banco. A
    troca acontece na fronteira de carga — antes de qualquer calculo ou
    renderizacao — para que todos os agrupamentos e joins por produto
    usem um vocabulario unico.

    Aplicavel a qualquer frame que exponha ``grupo_dashboard``: contratos
    pagos, em analise, cancelados e a propria tabela de ``categorias``.
    Nao muta o frame recebido — devolve copia (via ``assign``) quando ha
    o que renomear e o proprio objeto quando nao ha (vazio ou sem a
    coluna).
    """
    if frame.empty or "grupo_dashboard" not in frame.columns:
        return frame
    return frame.assign(
        grupo_dashboard=frame["grupo_dashboard"].replace(NOMES_DISPLAY_PRODUTO)
    )


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
        lambda limite: (
            _sb()
            .from_("v_contratos_dashboard")
            .select(colunas)
            .eq("periodo_id", periodo["id"])
            .order("id")
            .limit(limite)
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
    # VALOR_BASE (VLR BASE) segue o mesmo tratamento do VALOR. A view
    # garante valor_consolidado >= valor e nenhum NULL; o fillna e a
    # mesma rede que ja existia para VALOR.
    df["VALOR_BASE"] = pd.to_numeric(
        df["VALOR_BASE"], errors="coerce"
    ).fillna(0.0)
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
# Contratos pagos por intervalo de datas
#
# O dashboard e mensal (um periodo por mes), mas a aba de Gestao
# precisa apurar faixas livres — inclusive cruzando meses anteriores
# ao selecionado na sidebar. Como `contratos.periodo_id` e DERIVADO de
# `data_status_pagamento` (ver schema.sql), o conjunto de periodos que
# cobre um intervalo de PAGAMENTO e exato: nenhum contrato pago dentro
# da faixa mora fora desses meses.
#
# Por CADASTRO a garantia nao vale — um contrato cadastrado em maio e
# pago em julho vive no periodo de julho. Por isso o modo de cadastro
# varre do mes inicial ate o mes corrente (ver
# :func:`meses_do_intervalo`), e ainda assim nao alcanca o que for
# pago depois de hoje. A aba avisa.
# ══════════════════════════════════════════════════════

# Teto de meses por consulta. O Supabase esta em compute Nano: varrer
# ano e meio de contratos de uma vez derruba a instancia antes de
# devolver resposta. Preferimos recusar com mensagem clara.
MAX_MESES_INTERVALO = 12

CAMPO_PAGAMENTO = "DATA"
CAMPO_CADASTRO = "DATA_CADASTRO"


def meses_do_intervalo(
    data_ini,
    data_fim,
    campo: str = CAMPO_PAGAMENTO,
    hoje=None,
) -> List[Tuple[int, int]]:
    """Meses (mes, ano) a carregar para cobrir o intervalo.

    Por PAGAMENTO, os meses de ``data_ini`` a ``data_fim`` bastam —
    ``periodo_id`` deriva da data de pagamento. Por CADASTRO, o alvo
    pode ter sido pago em qualquer mes posterior, entao a varredura vai
    de ``data_ini`` ate o mes corrente.

    Retorna [] se o intervalo for invalido (fim antes do inicio).
    """
    if data_ini is None or data_fim is None or data_fim < data_ini:
        return []

    limite = data_fim
    if campo == CAMPO_CADASTRO:
        hoje = hoje or datetime.now().date()
        limite = max(data_fim, hoje)

    meses: List[Tuple[int, int]] = []
    mes, ano = data_ini.month, data_ini.year
    while (ano, mes) <= (limite.year, limite.month):
        meses.append((mes, ano))
        mes += 1
        if mes > 12:
            mes, ano = 1, ano + 1
    return meses


def filtrar_por_intervalo(
    df: pd.DataFrame,
    data_ini,
    data_fim,
    campo: str = CAMPO_PAGAMENTO,
) -> pd.DataFrame:
    """Recorta o DataFrame pelo intervalo, na coluna de data escolhida.

    Limites INCLUSIVOS nas duas pontas, para casar com a leitura de
    quem digita "de 01/05 a 31/05" — e com os limiares da aba de
    Gestao, que tambem sao inclusivos. Linhas sem data saem.
    """
    if df.empty or campo not in df.columns:
        return df
    datas = pd.to_datetime(df[campo], errors="coerce").dt.date
    dentro = datas.notna() & (datas >= data_ini) & (datas <= data_fim)
    return df[dentro].copy()


def carregar_contratos_pagos_intervalo(
    data_ini,
    data_fim,
    campo: str = CAMPO_PAGAMENTO,
) -> Tuple[pd.DataFrame, str]:
    """Contratos pagos num intervalo livre de datas.

    Compoe os periodos mensais ja cacheados por
    :func:`carregar_contratos_pagos` — sem query nova e sem cache
    proprio, para nao manter uma segunda copia dos mesmos contratos em
    memoria (o Supabase esta em compute Nano).

    Args:
        data_ini, data_fim: limites inclusivos (``datetime.date``).
        campo: ``DATA`` (pagamento, padrao) ou ``DATA_CADASTRO``.

    Returns:
        ``(df, aviso)``. ``aviso`` traz o motivo quando o resultado vem
        vazio ou limitado — nunca devolvemos vazio silencioso.
    """
    meses = meses_do_intervalo(data_ini, data_fim, campo)
    if not meses:
        return pd.DataFrame(), "Intervalo invalido: fim anterior ao inicio."
    if len(meses) > MAX_MESES_INTERVALO:
        return (
            pd.DataFrame(),
            f"Intervalo exige varrer {len(meses)} meses (maximo "
            f"{MAX_MESES_INTERVALO}). Reduza a faixa de datas.",
        )

    partes = []
    for mes, ano in meses:
        parte = carregar_contratos_pagos(mes, ano)
        if not parte.empty:
            partes.append(parte)
    if not partes:
        return pd.DataFrame(), "Nenhum contrato pago nos meses do intervalo."

    df = pd.concat(partes, ignore_index=True)
    df = _preencher_categoria_fallback(df)
    return filtrar_por_intervalo(df, data_ini, data_fim, campo), ""


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


@st.cache_data(ttl=1800)
def carregar_headcount_ponderado(mes: int, ano: int) -> pd.DataFrame:
    """Headcount PONDERADO da competencia, por loja (migration 091).

    Retorna [LOJA, PESO, CABECAS, DU_COMPETENCIA, REGIAO, REGIAO_ATUAL].

    ``PESO`` e o gente-mes da loja na competencia: dias uteis em que a
    pessoa tinha vinculo com a loja, nao estava afastada e nao era
    supervisora, sobre os DU do mes (R2), rateados entre lojas quando
    houve transferencia (R3) — de modo que a soma devolva UMA pessoa,
    nunca duas. ``CABECAS`` e a contagem inteira point-in-time, para
    auditoria; nao e o denominador.

    E a MESMA fonte que o Caderno publica em ``weightedHeadcount``
    (migration 092). Existe para que dashboard e Caderno parem de
    responder numeros diferentes a "quantos consultores dividem esta
    producao".

    Dois filtros que a 091 NAO aplica e o Caderno reaplica, replicados
    aqui pelo mesmo motivo: a 091 responde "quem estava onde", nao "o
    que entra na media". Loja inativa sai (via ``carregar_lojas_ativas``)
    e backoffice sai (``LOJAS_BACKOFFICE``) — sem o segundo, o
    denominador do dashboard ficaria maior que o do Caderno exatamente
    pelo VAI E VEM. Supervisores ja saem dentro da propria 091, pelo
    ledger ``supervisor_vigencia``.

    REGIAO := regiao ATUAL da loja, como em ``carregar_lojas_ativas``: o
    ledger nao guarda regiao de proposito (a regiao point-in-time mora em
    ``loja_regiao_vigencia``). Carrega global; recorte por perfil
    client-side (``aplicar_rls``). TTL 30min — reflete upload do
    angry-man e rematerializacao sem esperar horas.
    """
    cols = [
        "LOJA", "PESO", "CABECAS", "DU_COMPETENCIA", "REGIAO", "REGIAO_ATUAL",
    ]
    resp = _sb().rpc(
        "fn_headcount_ponderado", {"p_mes": mes, "p_ano": ano}
    ).execute()
    linhas = resp.data or []
    if not linhas:
        return pd.DataFrame(columns=cols)

    df = pd.DataFrame(linhas).rename(
        columns={
            "loja": "LOJA",
            "peso": "PESO",
            "cabecas": "CABECAS",
            "du_competencia": "DU_COMPETENCIA",
        }
    )
    if "LOJA" not in df.columns:
        return pd.DataFrame(columns=cols)

    df["LOJA"] = df["LOJA"].fillna("").astype(str)
    df["PESO"] = pd.to_numeric(
        df.get("PESO"), errors="coerce"
    ).fillna(0.0).astype(float)
    df["CABECAS"] = pd.to_numeric(
        df.get("CABECAS"), errors="coerce"
    ).fillna(0).astype(int)
    df["DU_COMPETENCIA"] = pd.to_numeric(
        df.get("DU_COMPETENCIA"), errors="coerce"
    ).fillna(0).astype(int)

    df = excluir_lojas_backoffice(df)
    df_lojas = carregar_lojas_ativas()
    if df.empty or df_lojas.empty:
        return pd.DataFrame(columns=cols)

    df = df.merge(df_lojas, on="LOJA", how="inner")
    df["REGIAO"] = df["REGIAO_ATUAL"]
    return df.reindex(columns=cols).reset_index(drop=True)


# ══════════════════════════════════════════════════════
# Vinculos individuais (denominador por pessoa)
# ══════════════════════════════════════════════════════

# Base do denominador individual, publicada em TODA linha que sai
# daqui. Sao dias de VINCULO, nao dias trabalhados: ferias, faltas e
# afastamentos nao sao descontados — `consultor_afastamento` nao e
# consultado nesta apuracao, de proposito (ver docstring abaixo).
BASE_DIAS_VINCULO = "ELIGIBLE_LINK_DAYS"
COBERTURA_AFASTAMENTO_NENHUMA = "NONE"


def carregar_vinculos_consultores(
    mes: int,
    ano: int,
    ate: Optional[date] = None,
) -> pd.DataFrame:
    """Dias uteis ELEGIVEIS por (consultor, loja) na competencia.

    Retorna ``[CONSULTOR, LOJA, REGIAO, REGIAO_ATUAL, DIAS_ELEGIVEIS,
    DU_COMPETENCIA, DU_DECORRIDOS, BASE_DIAS, COBERTURA_AFASTAMENTO]``.

    ``ate`` e a DATA DE REFERENCIA da apuracao: dias uteis posteriores
    a ela nao entram em ``DIAS_ELEGIVEIS``. Sem isso, no mes em curso o
    denominador contava o mes INTEIRO — dias que ainda nao aconteceram
    — contra um numerador que so tem a producao ate hoje, e o R$/dia
    saia dividido por ``DU_total/DU_decorridos`` (10,5x no 2o dia util
    de 09/2026). E a mesma convencao do ``du_decorridos`` que
    ``kpis/gerais.py`` e o ``app.py`` ja aplicam em toda media por dia
    util; passe o ULTIMO DIA COM DADO, nao ``today``, para que atraso
    de ETL nao invente um dia util sem producao. Competencia fechada
    nao muda: ``ate`` posterior ao fim do mes nao trunca nada.

    E o **denominador por pessoa** que ``fn_headcount_ponderado`` (091)
    nao devolve: aquela funcao agrega por LOJA, e por isso o dashboard
    ate hoje nao conseguia perguntar "quanto essa pessoa produz por dia
    de casa". A fonte e a mesma — o ledger ``consultor_vigencia``
    (086/087) —, lido direto pelo PostgREST como
    ``carregar_supervisores`` ja faz com ``supervisor_vigencia``. Sao
    ~400 linhas no ledger inteiro: nao ha o que paginar nem RPC a criar.

    Diferencas DELIBERADAS em relacao a 091, todas na direcao de
    "menos regra derivada, mais fato":

    - **Sem desconto de afastamento.** A 091 tira os dias de
      ``consultor_afastamento``; aqui nao. A cobertura desse ledger e
      parcial, e misturar ausencia real com ausencia nao registrada
      produziria um numero que ninguem consegue auditar. Por isso toda
      linha carrega ``COBERTURA_AFASTAMENTO = 'NONE'``.
    - **Sem piso de 50%.** A 091 aplica piso quando a reducao e
      INFERIDA (R2), para nao punir a loja por uma janela que o ETL
      deduziu da producao. O piso protege a MEDIA da loja; num numero
      individual ele inventaria dias que a pessoa nao teve.
    - **Sem rateio.** A 091 divide o peso da pessoa entre as lojas
      (R3) para que a soma devolva uma pessoa, nunca duas. Aqui a
      transferencia vira dois segmentos com os dias reais de cada loja
      — a soma continua sendo o mes da pessoa, sem sobreposicao,
      porque o ledger proibe janelas sobrepostas (087, check 4).

    Os dois filtros que ``carregar_headcount_ponderado`` reaplica sobre
    a 091 valem aqui pelo mesmo motivo (o ledger responde "quem estava
    onde", nao "o que entra na media"): loja inativa sai pelo inner
    join com ``carregar_lojas_ativas`` e backoffice sai por
    ``excluir_lojas_backoffice``. Supervisor sai pela ancora da
    competencia — o papel vigente no ULTIMO DIA vale pelo mes inteiro,
    a MESMA regra de ``carregar_supervisores`` e da migration 085, para
    que numerador e denominador nunca discordem sobre quem era
    supervisor.

    REGIAO := regiao ATUAL da loja, como nos demais loaders de
    cadastro. Carrega global; recorte por perfil client-side
    (``aplicar_rls``). TTL 30min no mes corrente (reflete upload do
    angry-man), 24h no historico.
    """
    if _eh_mes_atual(mes, ano):
        return _vinculos_consultores_atual(mes, ano, ate)
    return _vinculos_consultores_historico(mes, ano, ate)


_COLS_VINCULOS = [
    "CONSULTOR",
    "LOJA",
    "REGIAO",
    "REGIAO_ATUAL",
    "DIAS_ELEGIVEIS",
    "DU_COMPETENCIA",
    "DU_DECORRIDOS",
    "BASE_DIAS",
    "COBERTURA_AFASTAMENTO",
]


def _dias_uteis_competencia(mes: int, ano: int) -> List[date]:
    """Dias uteis da competencia: seg-sex menos feriados.

    Mesma definicao de ``src/shared/dias_uteis.py`` e da 091 — os DU do
    mes precisam ser UM numero so no projeto inteiro.
    """
    ini = date(ano, mes, 1)
    fim = date(ano, mes, calendar.monthrange(ano, mes)[1])
    feriados = carregar_feriados(mes, ano)
    return [
        d.date()
        for d in pd.bdate_range(ini, fim)
        if d.date() not in feriados
    ]


def _fetch_vinculos_consultores(
    mes: int,
    ano: int,
    ate: Optional[date] = None,
) -> pd.DataFrame:
    """Le o ledger e conta os dias uteis cobertos por cada janela.

    ``ate`` corta os dias uteis ainda nao decorridos (ver a docstring
    publica). O corte e por DIA, nunca por proporcao: quem foi admitido
    depois da referencia fica com zero dias — e nao com uma fracao de
    dia que nunca existiu.
    """
    dias = _dias_uteis_competencia(mes, ano)
    if not dias:
        return pd.DataFrame(columns=_COLS_VINCULOS)
    du_total = len(dias)
    if ate is not None:
        dias = [d for d in dias if d <= ate]
    if not dias:
        return pd.DataFrame(columns=_COLS_VINCULOS)
    du_decorridos = len(dias)
    # `fim` e o ultimo dia CONSIDERADO: o filtro no servidor ja deixa
    # de trazer quem so tem vinculo depois da referencia.
    ini, fim = date(ano, mes, 1), dias[-1]

    # Janela do ledger e meio-aberta [inicio, fim): sobrepoe a
    # competencia se comecou ate o ultimo dia dela E ainda nao tinha
    # encerrado no primeiro. O filtro no servidor evita trazer o
    # historico inteiro para contar dias de um mes so.
    resp = (
        _sb()
        .table("consultor_vigencia")
        .select(
            "nome, nome_normalizado, vigencia_inicio, vigencia_fim,"
            " lojas(nome)"
        )
        .lte("vigencia_inicio", fim.isoformat())
        .or_(
            f"vigencia_fim.is.null,vigencia_fim.gt.{ini.isoformat()}"
        )
        .execute()
    )
    linhas = resp.data or []
    if not linhas:
        return pd.DataFrame(columns=_COLS_VINCULOS)

    registros = []
    for linha in linhas:
        loja = (linha.get("lojas") or {}).get("nome") or ""
        if not loja:
            continue
        v_ini = pd.to_datetime(linha.get("vigencia_inicio")).date()
        v_fim_raw = linha.get("vigencia_fim")
        v_fim = pd.to_datetime(v_fim_raw).date() if v_fim_raw else None
        cobertos = sum(
            1
            for d in dias
            if d >= v_ini and (v_fim is None or d < v_fim)
        )
        if cobertos == 0:
            continue
        registros.append(
            {
                "_key": linha.get("nome_normalizado") or "",
                "CONSULTOR": (linha.get("nome") or "").strip(),
                "LOJA": loja,
                "DIAS_ELEGIVEIS": cobertos,
                "_inicio": v_ini,
            }
        )
    if not registros:
        return pd.DataFrame(columns=_COLS_VINCULOS)

    df = pd.DataFrame(registros)
    # Grafia de exibicao: a da janela mais recente. Duas janelas da
    # mesma pessoa na mesma loja (ex.: correcao manual partindo o
    # periodo) somam os dias — sem sobreposicao, garantida pelo ledger.
    df = df.sort_values("_inicio")
    agrupado = (
        df.groupby(["_key", "LOJA"], as_index=False)
        .agg(
            CONSULTOR=("CONSULTOR", "last"),
            DIAS_ELEGIVEIS=("DIAS_ELEGIVEIS", "sum"),
        )
    )

    df_sup = carregar_supervisores(mes, ano)
    if not df_sup.empty and "SUPERVISOR" in df_sup.columns:
        sups = {
            " ".join(str(nome).upper().split())
            for nome in df_sup["SUPERVISOR"].fillna("")
        }
        agrupado = agrupado[~agrupado["_key"].isin(sups)]

    agrupado = excluir_lojas_backoffice(agrupado)
    df_lojas = carregar_lojas_ativas()
    if agrupado.empty or df_lojas.empty:
        return pd.DataFrame(columns=_COLS_VINCULOS)

    saida = agrupado.merge(df_lojas, on="LOJA", how="inner")
    saida["REGIAO"] = saida["REGIAO_ATUAL"]
    saida["DU_COMPETENCIA"] = du_total
    saida["DU_DECORRIDOS"] = du_decorridos
    saida["BASE_DIAS"] = BASE_DIAS_VINCULO
    saida["COBERTURA_AFASTAMENTO"] = COBERTURA_AFASTAMENTO_NENHUMA
    return saida.reindex(columns=_COLS_VINCULOS).reset_index(drop=True)


@st.cache_data(ttl=1800)
def _vinculos_consultores_atual(
    mes: int, ano: int, ate: Optional[date] = None
) -> pd.DataFrame:
    """Vinculos — mes corrente. TTL 30min.

    ``ate`` entra na chave de cache: avancar a data de referencia
    (novo dia util com dado) recarrega, em vez de servir o
    denominador de ontem.
    """
    return _fetch_vinculos_consultores(mes, ano, ate)


@st.cache_data(ttl=86400)
def _vinculos_consultores_historico(
    mes: int, ano: int, ate: Optional[date] = None
) -> pd.DataFrame:
    """Vinculos — historico. TTL 24h."""
    return _fetch_vinculos_consultores(mes, ano, ate)


# ══════════════════════════════════════════════════════
# Supervisores
# ══════════════════════════════════════════════════════


@st.cache_data(ttl=1800)
def carregar_supervisores(mes: int, ano: int) -> pd.DataFrame:
    """Supervisores vigentes NA COMPETENCIA (mes/ano). TTL 30min
    (reflete uploads do angry-man sem esperar horas).

    Le o ledger ``supervisor_vigencia`` (migration 076), nao a tabela
    ``supervisores`` — esta e a foto do PRESENTE e, usada como filtro,
    reescrevia a historia: uma promocao apagava retroativamente os meses
    em que a pessoa vendia como consultora, e uma saida da supervisao
    devolvia aos rankings os meses em que ela supervisionava.

    Ancora (revisada em 2026-08-18): o papel vigente no ULTIMO DIA da
    competencia vale para o mes inteiro — quem fechou o mes responde por
    ele. A regra anterior (1o dia) atribuia agosto/2026 a duas
    supervisoras DESLIGADAS em 04/08, enquanto quem assumiu e fechou o
    mes so entraria em setembro. Mesma regra da
    ``obter_caderno_fechamento`` (migration 085) — producao e headcount
    nao podem discordar sobre quem era supervisor.

    REGIAO vem da regiao ATUAL da loja: o ledger nao guarda regiao de
    proposito (seria uma segunda fonte de verdade; a regiao
    point-in-time mora em ``loja_regiao_vigencia``).
    """
    # Ultimo dia da competencia. Janela meio-aberta [inicio, fim): quem
    # encerra exatamente nesse dia nao o cobre, e o mes fica com o sucessor.
    ancora = "{:04d}-{:02d}-{:02d}".format(
        ano, mes, calendar.monthrange(ano, mes)[1]
    )
    resp = (
        _sb()
        .table("supervisor_vigencia")
        .select("nome, lojas(nome, regioes(nome))")
        .lte("vigencia_inicio", ancora)
        .or_(f"vigencia_fim.is.null,vigencia_fim.gt.{ancora}")
        .execute()
    )

    if not resp.data:
        return pd.DataFrame(columns=["SUPERVISOR", "LOJA", "REGIAO"])

    rows = []
    for s in resp.data:
        loja = s.get("lojas") or {}
        regiao = loja.get("regioes") or {}
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
    # Cache version bump = 4 (VALOR passa a vir de valor_consolidado —
    # migration 067; os caches de 24h do historico guardariam o VLR
    # BASE antigo)
    if _eh_mes_atual(mes, ano):
        resultado = _consolidar_atual(mes, ano, _cache_version=4)
    else:
        resultado = _consolidar_historico(mes, ano, _cache_version=4)

    df, df_metas, df_supervisores, diag = resultado

    # Side-effect: diagnostico no session_state
    if diag:
        st.session_state["_diag_pontuacao"] = diag

    return df, df_metas, df_supervisores


@st.cache_data(ttl=1800)
def _consolidar_atual(
    mes: int,
    ano: int,
    _cache_version: int = 4,  # bump v4: VALOR = valor_consolidado
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Optional[dict]]:
    """Consolidacao — mes corrente. TTL 30min."""
    return _executar_consolidacao(mes, ano)


@st.cache_data(ttl=86400)
def _consolidar_historico(
    mes: int,
    ano: int,
    _cache_version: int = 4,  # bump v4: VALOR = valor_consolidado
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
    df_supervisores = carregar_supervisores(mes, ano)

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
# Carga do periodo do dashboard
# ══════════════════════════════════════════════════════


class DadosPeriodo(NamedTuple):
    """Conjunto de frames que o dashboard carrega para um (mes, ano).

    NamedTuple (e nao dataclass) para continuar desempacotavel como a
    tupla que substituiu, sem obrigar o chamador a mudar de estilo:
    ``df, df_metas, ... = carregar_periodo_dashboard(...)`` segue valido,
    e ``dados.df_cancelados`` fica disponivel quando o nome ajuda mais que
    a posicao. Sao sete frames e cinco deles tem o mesmo tipo — posicao
    sozinha e frageil demais.
    """

    df: pd.DataFrame
    df_metas: pd.DataFrame
    df_sup: pd.DataFrame
    categorias: pd.DataFrame
    df_metas_produto: pd.DataFrame
    df_analise: pd.DataFrame
    df_cancelados: pd.DataFrame


def carregar_periodo_dashboard(
    mes: int,
    ano: int,
    on_progress: Optional[Callable[[str], None]] = None,
) -> DadosPeriodo:
    """Carrega e normaliza todos os frames de um periodo do dashboard.

    Orquestra os loaders do periodo (pagos + metas + supervisores,
    categorias, metas por produto, pipeline em analise e cancelados) e
    deixa os frames prontos para consumo: regras do pipeline aplicadas e
    vocabulario de produto ja normalizado.

    ``on_progress``, se informado, e chamado com um rotulo curto antes de
    cada etapa de carga. A funcao nao conhece Streamlit: quem exibe o
    progresso (``st.status``, barra, log) decide o formato do rotulo e o
    ciclo de vida do widget. Sem callback, a carga e silenciosa.

    Nao aplica RLS — o recorte por perfil e responsabilidade do chamador
    (``aplicar_rls`` / ``aplicar_rls_metas``), que precisa dos frames
    completos para os snapshots pre-RLS.

    Cache: nenhum aqui. Cada loader chamado ja tem a propria politica de
    TTL (``_atual`` vs ``_historico``); acrescentar cache nesta camada so
    duplicaria a chave (mes, ano) com invalidacao mais grossa.
    """

    def _progresso(label: str) -> None:
        if on_progress is not None:
            on_progress(label)

    _progresso("Carregando contratos pagos...")
    df, df_metas, df_sup = consolidar_dados(mes, ano)

    _progresso("Carregando categorias e metas...")
    categorias = carregar_categorias()
    df_metas_produto = carregar_metas_produto(mes, ano)

    _progresso("Carregando pipeline em analise...")
    df_analise = carregar_contratos_em_analise(mes, ano)

    _progresso("Carregando cancelados...")
    df_cancelados = carregar_contratos_cancelados(mes, ano)

    # Regras do pipeline, identicas para analise e cancelados:
    # 1. zerar o VALOR do que conta so como quantidade (emissoes
    #    por conta_valor=False ou por TIPO OPER.);
    # 2. manter apenas a janela recente de DATA_CADASTRO.
    # Um unico instante de referencia para os dois DataFrames.
    agora_janela = datetime.now()
    df_analise = filtrar_janela_recente(
        aplicar_conta_valor(df_analise), referencia=agora_janela
    )
    df_cancelados = filtrar_janela_recente(
        aplicar_conta_valor(df_cancelados), referencia=agora_janela
    )

    # Nomes de display: substitui as chaves internas de grupo_dashboard
    # (ex: 'PACK') pelo rotulo amigavel, antes de qualquer calculo ou
    # renderizacao. Aplica em todos os frames que expoem a coluna.
    df = aplicar_nomes_display_produto(df)
    categorias = aplicar_nomes_display_produto(categorias)
    df_analise = aplicar_nomes_display_produto(df_analise)
    df_cancelados = aplicar_nomes_display_produto(df_cancelados)

    return DadosPeriodo(
        df=df,
        df_metas=df_metas,
        df_sup=df_sup,
        categorias=categorias,
        df_metas_produto=df_metas_produto,
        df_analise=df_analise,
        df_cancelados=df_cancelados,
    )


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
        lambda limite: (
            _sb()
            .from_("v_pagamentos_online_efetivo")
            .select("*")
            .order("proposta")
            .limit(limite)
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

# Rotulos de vigencia de cada lead frente ao mes selecionado
# (`_marcar_vigencia_reconquista`). Publicos: a UI compara contra eles
# para destacar/filtrar sem reescrever a regra.
VIGENCIA_VIGENTE = "Vigente"
VIGENCIA_PROXIMA = "Próxima"
VIGENCIA_HISTORICO = "Histórico"
VIGENCIA_FUTURA = "Futura"
VIGENCIA_SEM_REF = "Sem referência"


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


def _chave_apuracao(ano: int, mes: int) -> int:
    """Mes como inteiro monotonico (ano*12 + mes) — compara e ordena."""
    return int(ano) * 12 + int(mes)


def _marcar_vigencia_reconquista(
    clientes: pd.DataFrame, mes: int, ano: int
) -> pd.DataFrame:
    """Anota cada lead com a apuracao a que pertence e a vigencia dela.

    A separacao ja existe no dado — a view deriva `ref_ano`/`ref_mes` de
    dt_fim_relacionamento e a campanha tem defasagem de 1 mes
    (business-rules.md), entao ``apuracao = ref + 1``. Aqui isso so vira
    rotulo, por linha:

      * ``apuracao_key`` — ano*12+mes da apuracao (ordenacao);
      * ``apuracao_ref`` — rotulo ``MM/AAAA`` da apuracao;
      * ``vigencia``     — posicao frente ao (mes, ano) selecionado:
        VIGENTE (a que os KPIs apuram), PROXIMA (esteira ja acumulando,
        a mesma da previa), HISTORICO, FUTURA.

    Colunas derivadas, nao existem na view. Nenhum KPI le daqui.
    """
    if clientes is None or clientes.empty:
        return pd.DataFrame() if clientes is None else clientes.copy()

    df = clientes.copy()
    if "ref_ano" not in df.columns or "ref_mes" not in df.columns:
        df["apuracao_key"] = -1
        df["apuracao_ref"] = "—"
        df["vigencia"] = VIGENCIA_SEM_REF
        return df

    apuracao = (
        pd.to_numeric(df["ref_ano"], errors="coerce") * 12
        + pd.to_numeric(df["ref_mes"], errors="coerce")
        + 1  # defasagem de 1 mes: dt_fim em M -> apuracao em M+1
    )
    valido = apuracao.notna()

    df["apuracao_key"] = apuracao.fillna(-1).astype(int)
    mes_ap = ((df["apuracao_key"] - 1) % 12) + 1
    ano_ap = (df["apuracao_key"] - mes_ap) // 12
    df["apuracao_ref"] = (
        mes_ap.astype(str).str.zfill(2) + "/" + ano_ap.astype(str)
    ).where(valido, "—")

    selecionada = _chave_apuracao(ano, mes)
    vigencia = pd.Series(VIGENCIA_FUTURA, index=df.index)
    vigencia[df["apuracao_key"] < selecionada] = VIGENCIA_HISTORICO
    vigencia[df["apuracao_key"] == selecionada + 1] = VIGENCIA_PROXIMA
    vigencia[df["apuracao_key"] == selecionada] = VIGENCIA_VIGENTE
    vigencia[~valido] = VIGENCIA_SEM_REF
    df["vigencia"] = vigencia
    return df


@st.cache_data(ttl=600)
def _reconquista_todos() -> pd.DataFrame:
    """Base de Reconquista INTEIRA (todas as apuracoes). TTL 10min.

    Substitui os fetches filtrados por mes. A tabela e truncada e
    realimentada a cada import e cabe em poucos milhares de linhas
    (3,2k em 8 apuracoes, 08/2026), entao pagina-la uma vez e fatiar em
    pandas custa menos que tres consultas por periodo selecionado — e,
    dentro do TTL, trocar de mes deixa de bater no Supabase (plano Nano,
    ver migration 054). Se um dia a base crescer uma ordem de grandeza,
    o filtro volta para o servidor.

    Cursor keyset por ``co_adesao`` (UNIQUE, migration 028): cada
    request e um top-N que cabe em work_mem, sem OFFSET.
    """
    return pd.DataFrame(
        _paginar_keyset(
            lambda limite: (
                _sb()
                .from_("v_reconquista")
                .select("*")
                .order("co_adesao")
                .limit(limite)
            ),
            "co_adesao",
        )
    )


def _fatiar_ref(
    todos: pd.DataFrame, ref_ano: int, ref_mes: int
) -> pd.DataFrame:
    """Recorte de um mes de referencia (dt_fim_relacionamento) da base."""
    if todos is None or todos.empty:
        return pd.DataFrame()
    if "ref_ano" not in todos.columns or "ref_mes" not in todos.columns:
        return pd.DataFrame()
    return todos[
        (todos["ref_ano"] == ref_ano) & (todos["ref_mes"] == ref_mes)
    ].copy()


@st.cache_data(ttl=600)
def _reconquista_cache(mes: int, ano: int) -> dict:
    """Detalhe cacheado do mes de referencia (defasado). TTL 10min.

    Inclui tambem o detalhe do mes de referencia ANTERIOR
    (`clientes_ant`), usado para a variacao periodo-a-periodo. Os tres
    recortes saem da MESMA base (`_reconquista_todos`) — antes eram tres
    consultas ao Supabase.
    """
    ref_mes, ref_ano = _mes_apuracao_anterior(mes, ano)
    prev_mes, prev_ano = _mes_apuracao_anterior(ref_mes, ref_ano)
    todos = _reconquista_todos()
    return {
        "ref_mes": ref_mes,
        "ref_ano": ref_ano,
        "clientes": _fatiar_ref(todos, ref_ano, ref_mes),
        "clientes_ant": _fatiar_ref(todos, prev_ano, prev_mes),
        # Esteira da PROXIMA apuracao: o proprio mes selecionado e o
        # ref dela (a apuracao seguinte exibe dt_fim deste mes). Usado
        # para a previa antecipada das promessas que ja se acumulam.
        "clientes_prox": _fatiar_ref(todos, ano, mes),
    }


def _filtro_rls_reconquista() -> Callable | None:
    """Funcao de recorte por perfil dos detalhes de Reconquista.

    A view expoe `regiao`, `loja` e `consultor` em texto.
    Admin/gestor veem tudo; demais perfis sao restritos ao seu
    escopo (regiao/loja/consultor). Devolve ``None`` quando nao ha
    recorte a aplicar — o chamador entrega o frame como veio.

    Extraida de `_filtrar_rls_reconquista` para que a lista completa
    (`clientes_todos`) passe pelo MESMO recorte dos cortes mensais:
    RLS antes de render, sem uma segunda implementacao para divergir.
    """
    perfil = _obter_perfil_efetivo()
    if not perfil or perfil["perfil"] in ("admin", "gestor"):
        return None

    escopo = perfil.get("escopo") or []
    if not escopo:
        return None

    coluna = {
        "gerente_comercial": "regiao",
        "supervisor": "loja",
        "consultor": "consultor",
    }.get(perfil["perfil"])
    if not coluna:
        return None

    def _filtra(df):
        if df is None or df.empty or coluna not in df.columns:
            return df
        return df[df[coluna].isin(escopo)].copy()

    return _filtra


def _filtrar_rls_reconquista(dados: dict) -> dict:
    """Aplica RLS sobre `clientes`/`clientes_ant`/`clientes_prox`."""
    _filtra = _filtro_rls_reconquista()
    if _filtra is None:
        return dados

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
    # As 4 chaves do acelerador entram aqui so para o dict ter schema
    # estavel (a previa tambem usa estes totais); quem preenche de fato
    # e `carregar_reconquista`, sob o gate.
    vazio = {
        "total": 0, "total_geral": 0, "nao_elegivel": 0,
        "efetivadas": 0, "promessas": 0, "sem_reconquista": 0,
        "conversao": 0.0, "faixa": _faixa_premio_conversao(0.0),
        "cobranca_consignavel": 0, "acelerador_no_escopo": False,
        "acelerador_perfil": None, "faixa_agregada": None,
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
        "cobranca_consignavel": 0,      # ver comentario em `vazio`
        "acelerador_no_escopo": False,  # idem
        "acelerador_perfil": None,      # idem
        "faixa_agregada": None,         # idem
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


def _por_consultor_reconquista(clientes: pd.DataFrame) -> pd.DataFrame:
    """Espelha `_por_loja_reconquista` agrupando por consultor.

    Consultor e agregado por NOME (soma a producao da pessoa mesmo
    transferida de loja — ver docs/agents/rls.md, nota nome x id).
    """
    if clientes is None or clientes.empty or "consultor" not in clientes.columns:
        return pd.DataFrame()

    df = clientes[_mask_elegivel(clientes)].copy()  # so elegiveis na apuracao
    if df.empty:
        return pd.DataFrame()
    df["_efet"] = (df["status"] == "EFETIVADA").astype(int)
    df["_prom"] = (df["status"] == "PROMESSA").astype(int)
    df["_sem"] = (df["status"] == "SEM RECONQUISTA").astype(int)

    g = (
        df.groupby("consultor", dropna=False)
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


# ══════════════════════════════════════════════════════
# Acelerador combinado: Reconquista + Cobranca Consignavel
#
# Vigente a partir da apuracao de 08/2026 e SO para os perfis
# consultor/supervisor (gate `_acelerador_no_escopo`). O
# atingimento e individual do consultor: EFETIVADA do mes +
# Cobranca Consignavel do mes -> faixa, resolvida pela RPC
# `obter_faixa_acelerador_reconquista` (migration 066), que
# devolve SO o rotulo — o valor do premio e resolvido fora do
# dashboard (decisao de negocio). O supervisor ganha 70% sobre
# CADA consultor, entao a visao dele e a mesma quebra por
# consultor recortada pelo seu escopo de lojas.
# Ver docs/agents/business-rules.md.
# ══════════════════════════════════════════════════════

# Primeira apuracao (ano, mes) em que a regra vale.
_ACELERADOR_INICIO = (2026, 8)

# Perfis para os quais o acelerador e apurado.
_ACELERADOR_PERFIS = ("consultor", "supervisor")

# Colunas de v_contratos_dashboard usadas na Cobranca Consignavel.
# contrato_id/num_proposta identificam a proposta na listagem (Nº ADE,
# mesmo padrao de _COLS_CONTRATOS_PAGOS). tipo_operacao/subtipo/
# categoria_codigo nao entram em mascara nenhuma desde a migration 067
# (o criterio virou filtro server-side) — ficam para o CSV de auditoria.
_COLS_COBRANCA_CONSIGNAVEL = {
    "contrato_id": "CONTRATO_ID",
    "num_proposta": "NUM_PROPOSTA",
    "consultor": "CONSULTOR",
    "loja": "LOJA",
    "regiao": "REGIAO",
    "regiao_atual": "REGIAO_ATUAL",
    "tipo_operacao": "TIPO OPER.",
    "subtipo": "SUBTIPO",
    "banco": "BANCO",
    "categoria_codigo": "CATEGORIA_CODIGO",
    # Mesmo vocabulario de _COLS_CONTRATOS_PAGOS: VALOR e sempre o
    # consolidado (o que conta como producao), VALOR_BASE e o VLR BASE
    # cru. VALOR_BRUTO entra aqui — e nao no frame principal — porque a
    # sub-aba exibe o trio Base/Bruto/Considerado para auditoria.
    "valor_consolidado": "VALOR",
    "valor": "VALOR_BASE",
    "valor_bruto": "VALOR_BRUTO",
    "data_status_pagamento": "DATA",
}

_COLS_ACELERADOR = [
    "consultor",
    "efetivadas",
    "cobranca_consignavel",
    "total_acelerador",
    "faixa_rotulo",
]


def _norm_texto(serie: pd.Series) -> pd.Series:
    """Normaliza texto para comparacao: str + strip + upper.

    Replica `_norm` de tabs/produtos.py em vez de importar: a camada de
    dados nao depende da camada de UI (ver docs/agents/architecture.md).
    """
    return serie.astype(str).str.strip().str.upper()


def _acelerador_vigente(mes: int, ano: int) -> bool:
    """Gate de VIGENCIA (sem perfil): so a data importa.

    Usado pela contagem agregada de Cobranca Consignavel (card), que
    e visivel a qualquer perfil a partir de 08/2026 — RLS normal de
    cada um (admin/gestor veem tudo, gerente_comercial a regiao,
    supervisor a loja, consultor so ele) ja escopa o numero.
    """
    return (ano, mes) >= _ACELERADOR_INICIO


def _acelerador_no_escopo(mes: int, ano: int) -> bool:
    """Gate do acelerador DETALHADO: perfil consultor/supervisor +
    apuracao >= 08/2026.

    Mais restrito que `_acelerador_vigente`: governa a FAIXA (rotulo)
    e a quebra `por_consultor` — decisao de produto de que atingimento
    de faixa e informacao de quem pontua (consultor/supervisor), nao
    visao gerencial. A contagem agregada (card) usa `_acelerador_vigente`.
    """
    perfil = _obter_perfil_efetivo()
    if not perfil or perfil.get("perfil") not in _ACELERADOR_PERFIS:
        return False
    return _acelerador_vigente(mes, ano)


def carregar_cobranca_consignavel(mes: int, ano: int) -> pd.DataFrame:
    """Contratos de Cobranca Consignavel do mes — GLOBAL, sem RLS.

    O recorte por perfil e do consumidor (`aplicar_rls`), como em
    `carregar_periodo_dashboard`: cachear pos-RLS envenenaria a chave
    entre perfis. TTL real: 30min no mes corrente, 24h no historico.
    """
    if _eh_mes_atual(mes, ano):
        return _cobranca_consignavel_atual(mes, ano)
    return _cobranca_consignavel_historico(mes, ano)


def _fetch_cobranca_consignavel(mes: int, ano: int) -> pd.DataFrame:
    """Executa a query da Cobranca Consignavel sem cache.

    O criterio de negocio vive em `fn_eh_cobranca_consignavel`
    (migration 067), exposto como `is_cobranca_consignavel` em
    `v_contratos_dashboard`: TIPO OPER. = CONTRATO NOVO, SUBTIPO =
    NOVO (MARGEM COMPLEMENTAR fora), categoria_codigo = CONSIG_BMG,
    banco BMG e |VLR BRUTO - VLR BASE| > 0,005. Ver
    docs/agents/business-rules.md — **nao reimplementar a mascara
    aqui**: duas fontes do mesmo criterio, em duas linguagens, e
    exatamente o drift que a 067 existe para eliminar.

    O filtro e server-side, entao esta funcao traz apenas as linhas
    que ja qualificam — antes da 067 ela paginava o periodo INTEIRO
    (~16k linhas) para ficar com algumas dezenas.

    Resta em Python so a reconferencia de mes: o recorte server-side e
    por `periodo_id`, que e DERIVADO de `data_status_pagamento` (ver
    schema.sql); linha com DATA fora do mes indicaria `periodo_id`
    inconsistente.
    """
    vazio = pd.DataFrame(columns=list(_COLS_COBRANCA_CONSIGNAVEL.values()))
    periodo = carregar_periodo(mes, ano)
    if not periodo:
        return vazio

    colunas = "id," + ",".join(_COLS_COBRANCA_CONSIGNAVEL)
    try:
        all_data = _paginar_keyset(
            lambda limite: (
                _sb()
                .from_("v_contratos_dashboard")
                .select(colunas)
                .eq("periodo_id", periodo["id"])
                .eq("status_pagamento_cliente", "PAGO AO CLIENTE")
                .eq("is_cobranca_consignavel", True)
                .order("id")
                .limit(limite)
            ),
            "id",
        )
    except Exception:
        # `is_cobranca_consignavel`/`valor_consolidado` dependem da
        # migration 067 estar aplicada. Enquanto nao estiver, loga o erro
        # e devolve vazio (Cobranca Consignavel = 0) em vez de derrubar a
        # aba inteira de Reconquista. Degradar aqui e aceitavel porque o
        # zero e o caso NEUTRO documentado de um contador de acelerador
        # (business-rules.md) — diferente do frame principal de pagos,
        # que falha alto de proposito (nao ha "producao neutra").
        logger.exception(
            "Falha ao carregar Cobranca Consignavel (%02d/%d)", mes, ano
        )
        return vazio

    if not all_data:
        return vazio

    df = (
        pd.DataFrame(all_data)
        .reindex(columns=list(_COLS_COBRANCA_CONSIGNAVEL))
        .rename(columns=_COLS_COBRANCA_CONSIGNAVEL)
    )
    df["VALOR"] = pd.to_numeric(df["VALOR"], errors="coerce").fillna(0.0)
    df["VALOR_BASE"] = pd.to_numeric(
        df["VALOR_BASE"], errors="coerce"
    ).fillna(0.0)
    # VLR BRUTO ausente => cai no VLR BASE (mesmo efeito do COALESCE da
    # view). Note que o fallback e VALOR_BASE, nao VALOR: este ultimo ja
    # e o consolidado desde a 067.
    df["VALOR_BRUTO"] = pd.to_numeric(
        df["VALOR_BRUTO"], errors="coerce"
    ).fillna(df["VALOR_BASE"])
    df["DATA"] = pd.to_datetime(df["DATA"], errors="coerce")

    # Unica mascara que sobrou em Python: o criterio esta no servidor.
    mask = (df["DATA"].dt.month == mes) & (df["DATA"].dt.year == ano)
    return df[mask].reset_index(drop=True)


@st.cache_data(ttl=1800)
def _cobranca_consignavel_atual(mes: int, ano: int) -> pd.DataFrame:
    """Cobranca Consignavel — mes corrente. TTL 30min."""
    return _fetch_cobranca_consignavel(mes, ano)


@st.cache_data(ttl=86400)
def _cobranca_consignavel_historico(mes: int, ano: int) -> pd.DataFrame:
    """Cobranca Consignavel — historico. TTL 24h."""
    return _fetch_cobranca_consignavel(mes, ano)


def _por_consultor_cobranca_consignavel(
    contratos: pd.DataFrame,
) -> pd.DataFrame:
    """Contagem de Cobranca Consignavel por consultor (frame ja pos-RLS)."""
    cols = ["consultor", "cobranca_consignavel"]
    if (
        contratos is None
        or contratos.empty
        or "CONSULTOR" not in contratos.columns
    ):
        return pd.DataFrame(columns=cols)
    return (
        contratos.groupby("CONSULTOR", dropna=False)
        .size()
        .reset_index(name="cobranca_consignavel")
        .rename(columns={"CONSULTOR": "consultor"})
    )


def carregar_faixa_acelerador(qtd: int, mes: int, ano: int) -> Dict:
    """Faixa do acelerador: `{rotulo, is_fallback, is_deflator}`.

    `is_deflator` diz se a faixa e a de desconto sobre o premio — vem da
    tabela (migration 066), nunca de limiar hardcoded no consumidor.
    Cacheada por (qtd, mes, ano) — as faixas sao configuracao, TTL real
    6h no mes corrente e 24h no historico (mesmo perfil de `pontuacao`).
    """
    if _eh_mes_atual(mes, ano):
        return _faixa_acelerador_atual(qtd, mes, ano)
    return _faixa_acelerador_historico(qtd, mes, ano)


def _fetch_faixa_acelerador(qtd: int, mes: int, ano: int) -> Dict:
    """Executa a RPC sem cache. Sem faixa cadastrada => rotulo vazio."""
    vazio = {"rotulo": "", "is_fallback": False, "is_deflator": False}
    try:
        resp = (
            _sb()
            .rpc(
                "obter_faixa_acelerador_reconquista",
                {"p_qtd": int(qtd), "p_mes": int(mes), "p_ano": int(ano)},
            )
            .execute()
        )
    except Exception:
        # Depende da migration 066. Enquanto nao aplicada, loga e degrada
        # para "sem faixa" — a contagem continua sendo exibida.
        logger.exception(
            "Falha ao resolver faixa do acelerador (qtd=%s, %02d/%d)",
            qtd,
            mes,
            ano,
        )
        return vazio

    linhas = resp.data or []
    if isinstance(linhas, dict):
        linhas = [linhas]
    if not linhas:
        return vazio
    return {
        "rotulo": linhas[0].get("rotulo") or "",
        "is_fallback": bool(linhas[0].get("is_fallback")),
        "is_deflator": bool(linhas[0].get("is_deflator")),
    }


@st.cache_data(ttl=21600)
def _faixa_acelerador_atual(qtd: int, mes: int, ano: int) -> Dict:
    """Faixa do acelerador — mes corrente. TTL 6h."""
    return _fetch_faixa_acelerador(qtd, mes, ano)


@st.cache_data(ttl=86400)
def _faixa_acelerador_historico(qtd: int, mes: int, ano: int) -> Dict:
    """Faixa do acelerador — historico. TTL 24h."""
    return _fetch_faixa_acelerador(qtd, mes, ano)


def _faixas_acelerador_por_qtd(qtds, mes: int, ano: int) -> Dict[int, str]:
    """Resolve o rotulo de cada contagem DISTINTA (1 RPC por valor unico).

    Uma chamada por consultor seria O(n) RPCs para pouquissimos valores
    distintos; o dedupe + cache mantem o custo em ~1 chamada por faixa.
    """
    unicos = sorted({int(q) for q in qtds})
    return {q: carregar_faixa_acelerador(q, mes, ano)["rotulo"] for q in unicos}


def _faixa_agregada_acelerador(
    totais: Dict,
    mes: int,
    ano: int,
) -> Optional[Dict]:
    """Faixa do total AGREGADO do escopo: `{rotulo, is_deflator}` ou None.

    Alimenta a barra-resumo, que so faz sentido para o perfil `consultor`
    — o premio do supervisor e por consultor individual, entao a soma da
    equipe enganaria. Quem decide exibir e a UI, por
    `totais["acelerador_perfil"]`. None = sem faixa resolvida (fora do
    gate ou periodo sem faixas): nao inventar faixa default.
    """
    if not totais.get("acelerador_no_escopo"):
        return None
    total = int(totais.get("efetivadas", 0) or 0) + int(
        totais.get("cobranca_consignavel", 0) or 0
    )
    faixa = carregar_faixa_acelerador(total, mes, ano)
    if not faixa.get("rotulo"):
        return None
    return {
        "rotulo": faixa["rotulo"],
        "is_deflator": bool(faixa.get("is_deflator")),
    }


def _juntar_producao(
    nomes: pd.DataFrame, rec: pd.DataFrame, cobr: pd.DataFrame
) -> pd.DataFrame:
    """Junta `efetivadas`/`cobranca_consignavel` a um conjunto de nomes.

    Devolve exatamente as linhas de `nomes` (dedupe por nome
    normalizado) — quem nao tem correspondencia em `rec`/`cobr` entra
    com 0, nunca adiciona linha nova. Merge por `_norm_texto`: as
    fontes podem vir com grafia levemente diferente do cadastro.
    """
    base = nomes[["consultor"]].copy()
    base["_key"] = _norm_texto(base["consultor"])
    base = base.drop_duplicates(subset="_key", keep="first")
    for frame, coluna in ((rec, "efetivadas"), (cobr, "cobranca_consignavel")):
        if frame.empty:
            base[coluna] = 0
            continue
        aux = frame[["consultor", coluna]].copy()
        aux["_key"] = _norm_texto(aux["consultor"])
        aux = (
            aux.drop(columns=["consultor"])
            .groupby("_key", as_index=False)
            .sum()
        )
        base = base.merge(aux, on="_key", how="left")

    base["efetivadas"] = base["efetivadas"].fillna(0).astype(int)
    base["cobranca_consignavel"] = (
        base["cobranca_consignavel"].fillna(0).astype(int)
    )
    return base.drop(columns=["_key"]).reset_index(drop=True)


def _por_consultor_acelerador(
    clientes: pd.DataFrame,
    mes: int,
    ano: int,
) -> pd.DataFrame:
    """Quebra por consultor: efetivadas + cobranca consignavel -> faixa.

    Fora do gate (`_acelerador_no_escopo`) devolve frame vazio — nao e
    erro, e o recurso desligado para o perfil/periodo. O universo inclui
    os consultores ativos do escopo (via `carregar_consultores_ativos`),
    para que quem nao pontuou apareca com a faixa minima em vez de
    sumir da visao do supervisor.

    Supervisor nunca entra no universo/esqueleto acima (regra geral de
    "Exclusao de supervisores", business-rules.md — o cadastro de
    `consultores` duplica a maioria dos supervisores como consultor
    ativo da propria loja). Isso exclui so o NOME zerado da lista, nao
    producao real: se o supervisor tiver alguma efetivada de
    reconquista ou contrato de Cobranca Consignavel em nome dele, essa
    producao aparece como linha separada, rotulada
    "<nome> (Supervisor)", sempre depois dos consultores reais (nunca
    entra no sort por producao). Sem producao propria, o nome e
    omitido — nao ha meta de venda pra supervisor, a funcao dele e
    cobrar a producao da equipe. Mesmo padrao ja usado em
    `tabs/produtos.py` (ver business-rules.md, "Produção de supervisor
    — conta pro total, marcada, fora do ranking").
    """
    vazio = pd.DataFrame(columns=_COLS_ACELERADOR)
    if not _acelerador_no_escopo(mes, ano):
        return vazio

    # RLS aqui, nunca dentro do cache: as fontes sao globais.
    contratos = aplicar_rls(carregar_cobranca_consignavel(mes, ano))
    cobr = _por_consultor_cobranca_consignavel(contratos)

    rec = _por_consultor_reconquista(clientes)
    rec = (
        rec[["consultor", "efetivadas"]]
        if not rec.empty
        else pd.DataFrame(columns=["consultor", "efetivadas"])
    )

    df_sup = carregar_supervisores(mes, ano)
    sup_keys = (
        set(_norm_texto(df_sup["SUPERVISOR"]))
        if "SUPERVISOR" in df_sup.columns
        else set()
    )

    universo = aplicar_rls(carregar_consultores_ativos())
    universo = excluir_supervisores(universo, df_sup)
    universo = (
        universo[["CONSULTOR"]].rename(columns={"CONSULTOR": "consultor"})
        if "CONSULTOR" in universo.columns
        else pd.DataFrame(columns=["consultor"])
    )

    # Universo = SO consultores ativos, sem supervisor. `rec`/`cobr` so
    # enriquecem contagem de quem ja esta no universo — nunca adicionam
    # linha nova aqui (o bloco de producao de supervisor e tratado a
    # parte, abaixo). Sem essa restricao, um consultor desligado com
    # cliente elegivel de reconquista no periodo (mesmo sem EFETIVADA,
    # so aparecer no frame ja basta) ou contrato de cobranca
    # consignavel pago no mes voltava a aparecer na tabela.
    cols_prod = ["consultor", "efetivadas", "cobranca_consignavel"]
    base = (
        _juntar_producao(universo, rec, cobr)
        if not universo.empty
        else pd.DataFrame(columns=cols_prod)
    )

    # Producao do proprio supervisor: so vira linha (marcada) se rec/cobr
    # tiver alguma contagem em nome dele; sem producao, fica de fora.
    bloco_sup = pd.DataFrame(columns=cols_prod)
    if sup_keys:
        candidatos = set()
        for frame in (rec, cobr):
            if not frame.empty:
                candidatos |= set(_norm_texto(frame["consultor"])) & sup_keys
        if candidatos:
            nomes_sup = (
                df_sup[["SUPERVISOR"]]
                .rename(columns={"SUPERVISOR": "consultor"})
                .drop_duplicates()
            )
            nomes_sup = nomes_sup[
                _norm_texto(nomes_sup["consultor"]).isin(candidatos)
            ]
            bloco_sup = _juntar_producao(nomes_sup, rec, cobr)
            bloco_sup = bloco_sup[
                (bloco_sup["efetivadas"] + bloco_sup["cobranca_consignavel"])
                > 0
            ].copy()

    if base.empty and bloco_sup.empty:
        return vazio

    for frame in (base, bloco_sup):
        frame["total_acelerador"] = (
            frame["efetivadas"] + frame["cobranca_consignavel"]
        )

    faixas = _faixas_acelerador_por_qtd(
        pd.concat([base["total_acelerador"], bloco_sup["total_acelerador"]]),
        mes,
        ano,
    )
    base["faixa_rotulo"] = base["total_acelerador"].map(faixas).fillna("")
    bloco_sup["faixa_rotulo"] = (
        bloco_sup["total_acelerador"].map(faixas).fillna("")
    )
    bloco_sup["consultor"] = bloco_sup["consultor"] + " (Supervisor)"

    base = base.sort_values(
        ["total_acelerador", "consultor"], ascending=[False, True]
    )
    return (
        pd.concat([base, bloco_sup], ignore_index=True)[_COLS_ACELERADOR]
        .reset_index(drop=True)
    )


def carregar_reconquista(mes: int, ano: int) -> Dict:
    """Dados de reconquista do mes de apuracao (mes, ano).

    Aplica a defasagem de 1 mes (exibe dt_fim_relacionamento do
    mes anterior) e RLS por perfil. Estrutura:
        {
            "ref_mes": int, "ref_ano": int,
            "totais":   dict,        # elegiveis/efetivadas/conversao/faixa
                                     # + cobranca_consignavel do mes,
                                     # faixa_agregada e acelerador_perfil
            "apuracao_mes": int, "apuracao_ano": int,  # (mes, ano) pedido
            "por_loja": DataFrame,   # quebra por loja (elegiveis)
            "por_consultor": DataFrame,  # acelerador combinado por consultor
            "clientes": DataFrame,   # detalhe (TODOS os clientes + flag)
            "clientes_todos": DataFrame,  # TODAS as apuracoes, marcadas
                                     # com apuracao_ref/vigencia
            "cobranca_consignavel_contratos": DataFrame,  # propostas RLS'd
                                     # que compoem totais["cobranca_consignavel"]
                                     # (vazio fora da vigencia)
            "prox":     dict,        # previa da apuracao seguinte (mes+1)
        }

    Conversao/apuracao contam so ELEGIVEL; `clientes` mantem todos.
    TTL 10min no fetch; KPIs derivados apos a RLS.

    `clientes` continua sendo o corte da apuracao vigente — e dele que
    saem os KPIs. `clientes_todos` e a MESMA base sem o filtro de mes,
    para o analitico poder navegar o historico inteiro; nenhum KPI le
    dessa chave (a apuracao da campanha e mensal por definicao).

    O acelerador combinado e apurado sobre o proprio (mes, ano) — sem a
    defasagem, que so vale para a esteira de reconquista. Dois gates
    diferentes:
      - `totais["cobranca_consignavel"]` (contagem/card): vale para
        QUALQUER perfil a partir de 08/2026 (`_acelerador_vigente`) —
        RLS normal escopa o numero por perfil.
      - `por_consultor` (quebra detalhada + faixa) e
        `totais["faixa_agregada"]`: exclusivos de consultor/supervisor
        (`_acelerador_no_escopo`) — decisao de produto, premio/faixa e
        informacao de quem pontua, nao visao gerencial.

    `totais["faixa_agregada"]` (`{rotulo, is_deflator}` ou None) e a
    faixa do total do escopo inteiro, para a barra-resumo; a UI deve
    exibi-la apenas para `totais["acelerador_perfil"] == "consultor"`,
    porque o premio do supervisor e por consultor individual (a soma da
    equipe nao significa faixa dele).
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

    # Acelerador combinado (Reconquista EFETIVADA + Cobranca
    # Consignavel). A CONTAGEM (card) vale pra qualquer perfil a
    # partir da vigencia (RLS natural escopa o numero); a FAIXA e a
    # quebra `por_consultor` continuam exclusivas de
    # consultor/supervisor (`_acelerador_no_escopo`) — decisao de
    # produto: premio/faixa e informacao de quem pontua, quantidade e
    # visao gerencial aberta.
    perfil = _obter_perfil_efetivo()
    por_consultor = _por_consultor_acelerador(clientes, mes, ano)
    totais["acelerador_no_escopo"] = _acelerador_no_escopo(mes, ano)
    totais["acelerador_perfil"] = perfil.get("perfil") if perfil else None
    if _acelerador_vigente(mes, ano):
        contratos_consignavel = aplicar_rls(
            carregar_cobranca_consignavel(mes, ano)
        )
        totais["cobranca_consignavel"] = (
            len(contratos_consignavel)
            if contratos_consignavel is not None
            else 0
        )
    else:
        contratos_consignavel = pd.DataFrame()
        totais["cobranca_consignavel"] = 0
    # Faixa do total agregado (barra-resumo). Depende das duas chaves
    # acima, entao vem depois delas.
    totais["faixa_agregada"] = _faixa_agregada_acelerador(totais, mes, ano)

    # Lista completa para o analitico: mesma base e MESMO recorte de RLS
    # dos cortes mensais, so que sem o filtro de mes e ja marcada com a
    # apuracao/vigencia de cada lead. Sai da base cacheada — nao ha
    # fetch adicional.
    _filtra_rls = _filtro_rls_reconquista()
    _todos = _reconquista_todos()
    if _filtra_rls is not None:
        _todos = _filtra_rls(_todos)
    clientes_todos = _marcar_vigencia_reconquista(_todos, mes, ano)

    return {
        "ref_mes": dados.get("ref_mes"),
        "ref_ano": dados.get("ref_ano"),
        "apuracao_mes": mes,
        "apuracao_ano": ano,
        "totais": totais,
        "por_loja": _por_loja_reconquista(clientes),
        "por_consultor": por_consultor,
        "clientes": clientes,
        "clientes_todos": clientes_todos,
        "cobranca_consignavel_contratos": contratos_consignavel,
        "prox": prox,
    }


# ══════════════════════════════════════════════════════
# Presets da aba de Gestao
# ══════════════════════════════════════════════════════


def _uuid_valido(valor: str) -> bool:
    """True quando ``valor`` e um UUID bem formado."""
    try:
        uuid.UUID(str(valor))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


@st.cache_data(ttl=300, show_spinner=False)
def carregar_presets_gestao(usuario_id: str) -> list[dict]:
    """Presets da aba de Gestao visiveis para ``usuario_id``.

    Traz os proprios mais os que outros marcaram como
    ``compartilhado``. O recorte por dono e feito AQUI, na
    aplicacao: a chave do dashboard e service_role (BYPASSRLS), entao
    as policies da migracao 064 nao chegam a rodar — sao rede de
    seguranca para acesso futuro com chave anon. Ver rls.md.

    Retorna lista de dicts ``[id, usuario_id, nome, compartilhado,
    config, proprio]``, ordenada pelos proprios primeiro. TTL 5min;
    mutacoes invalidam via :func:`_invalidar_cache_presets`.
    """
    if not _uuid_valido(usuario_id):
        return []
    resp = (
        _sb()
        .table("gestao_presets")
        .select("id, usuario_id, nome, compartilhado, config")
        # usuario_id vai interpolado no filtro do PostgREST — validado
        # como UUID acima, para que nenhum texto arbitrario da sessao
        # chegue a compor a expressao.
        .or_(f"usuario_id.eq.{usuario_id},compartilhado.is.true")
        .order("nome")
        .execute()
    )
    presets = []
    for row in resp.data or []:
        presets.append({**row, "proprio": row.get("usuario_id") == usuario_id})
    return sorted(presets, key=lambda p: (not p["proprio"], p["nome"]))


def salvar_preset_gestao(
    usuario_id: str,
    nome: str,
    config: dict,
    compartilhado: bool = False,
) -> tuple[bool, str]:
    """Cria ou sobrescreve um preset do proprio usuario.

    Sobrescreve pelo par (usuario_id, nome) — a constraint
    ``uq_gestao_presets_dono_nome``. Salvar com um nome que ja existe
    e uma ATUALIZACAO deliberada; quem chama deve confirmar antes.
    Nunca toca preset de outro dono.
    """
    nome = (nome or "").strip()
    if not _uuid_valido(usuario_id):
        return False, "Sessao sem usuario identificado."
    if not nome:
        return False, "Informe um nome para o preset."
    if len(nome) > 60:
        return False, "Nome muito longo (maximo 60 caracteres)."

    try:
        (
            _sb()
            .table("gestao_presets")
            .upsert(
                {
                    "usuario_id": usuario_id,
                    "nome": nome,
                    "config": config,
                    "compartilhado": bool(compartilhado),
                },
                on_conflict="usuario_id,nome",
            )
            .execute()
        )
    except Exception as exc:
        logger.exception("Falha ao salvar preset de Gestao")
        return False, f"Nao foi possivel salvar o preset: {exc}"

    _invalidar_cache_presets()
    return True, f"Preset '{nome}' salvo."


def excluir_preset_gestao(usuario_id: str, preset_id: str) -> tuple[bool, str]:
    """Apaga um preset, desde que pertenca ao proprio usuario.

    O filtro por ``usuario_id`` na propria query e o que impede apagar
    preset alheio — com service_role a policy de DELETE nao roda.
    """
    if not _uuid_valido(usuario_id) or not _uuid_valido(preset_id):
        return False, "Preset invalido."
    try:
        (
            _sb()
            .table("gestao_presets")
            .delete()
            .eq("id", preset_id)
            .eq("usuario_id", usuario_id)
            .execute()
        )
    except Exception as exc:
        logger.exception("Falha ao excluir preset de Gestao")
        return False, f"Nao foi possivel excluir o preset: {exc}"

    _invalidar_cache_presets()
    return True, "Preset excluido."


def _invalidar_cache_presets() -> None:
    """Invalida o cache de :func:`carregar_presets_gestao`."""
    try:
        carregar_presets_gestao.clear()
    except Exception:
        pass
