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
import calendar
from datetime import date, datetime
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple

import pandas as pd
import streamlit as st
from postgrest.exceptions import APIError

from src.config.supabase_client import get_supabase_client
from src.dashboard.kpis.detalhes_cards import aplicar_conta_valor
from src.dashboard.kpis.gerais import (
    excluir_lojas_backoffice,
    excluir_supervisores,
    filtrar_janela_recente,
)
# Regras da Reconquista/acelerador — extraidas na Etapa 2 da revisao
# de 09/2026. Os nomes seguem importaveis DAQUI de proposito: e o que
# `tabs/analiticos.py` (VIGENCIA_VIGENTE) e `tests/test_loaders.py`
# ja importavam, e a etapa preserva as interfaces publicas. Dai a
# supressao do F401 abaixo: para o ruff isso e import sem uso; para
# quem importa loaders, e a fachada continuando a existir.
# Presets da aba de Gestao — a unica escrita do dashboard, movida para
# modulo proprio na Etapa 2 da revisao de 09/2026 (loaders e a camada
# de LEITURA). Re-exportados daqui porque e de onde
# `tabs/gestao_consultores.py` ja os importava.
from src.dashboard.presets_gestao import (  # noqa: F401
    carregar_presets_gestao,
    excluir_preset_gestao,
    salvar_preset_gestao,
)
from src.dashboard.kpis.reconquista import (  # noqa: F401
    VIGENCIA_FUTURA,
    VIGENCIA_HISTORICO,
    VIGENCIA_PROXIMA,
    VIGENCIA_SEM_REF,
    VIGENCIA_VIGENTE,
    _acelerador_vigente,
    _fatiar_ref,
    _juntar_producao,
    _marcar_vigencia_reconquista,
    _mask_elegivel,
    _mes_apuracao_anterior,
    _mes_apuracao_seguinte,
    _norm_texto,
    _por_consultor_cobranca_consignavel,
    _por_consultor_reconquista,
    _por_loja_reconquista,
    _totais_reconquista,
)
from src.dashboard.kpis.consolidacao import (
    aplicar_nomes_display_produto,
    consolidar_pontuacao,
    preencher_categoria_fallback,
)
# `_filtro_rls_reconquista` / `_filtrar_rls_reconquista` mudaram para
# `rls.py` na Etapa 2 (recorte por perfil e autorizacao, nao carga).
# Re-exportados daqui porque e de onde `tests/test_loaders.py` os
# importava.
from src.dashboard.rls import (  # noqa: F401
    _filtrar_rls_reconquista,
    _filtro_rls_reconquista,
    _obter_perfil_efetivo,
    aplicar_rls,
)
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


def _preencher_categoria_fallback(df: pd.DataFrame) -> pd.DataFrame:
    """Fachada: injeta o loader de categorias na regra de consolidacao.

    A regra vive em ``kpis/consolidacao.py`` (Etapa 2 da revisao de
    09/2026) e recebe ``carregar_categorias`` como **callable**, nao
    como frame: assim a consulta a categorias so acontece quando ha
    linha sem categoria para preencher — carregar sempre acrescentaria
    uma consulta por consolidacao no caso comum.

    Mantida aqui com o mesmo nome e a mesma assinatura de antes: e o
    que os quatro call sites de ``loaders.py`` e ``tests/test_loaders.py``
    importam.
    """
    return preencher_categoria_fallback(df, carregar_categorias)


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


# Aceleradores do escopo CONSULTOR: metas em QUANTIDADE de contratos,
# nao em R$ (ao contrario dos produtos monetarios, que vem com
# ``nivel`` NULL). Explicitos aqui para que o pivot devolva a coluna
# mesmo quando o periodo nao tiver a linha correspondente no banco —
# consumidor le ``df[col]`` sem precisar checar existencia.
_ACELERADORES_META_CONSULTOR = (
    "BMG_MED",
    "EMISSAO",
    "SUPER_CONTA",
    "VIDA_FAMILIAR",
)

# Colunas por nivel garantidas no retorno (0.0 quando ausentes).
# Convencao: PRATA e a BASE (coluna com o nome nu do produto) e OURO e
# CONTEXTO (sufixo ``_OURO``) — a leitura mais comum e a meta de
# entrada, entao ela fica sem sufixo. BRONZE nao vira coluna: e sempre
# 0 no banco e nao alimenta criterio nenhum.
_COLUNAS_NIVEL_META_CONSULTOR = (
    ("META_PRATA", "META_OURO")
    + _ACELERADORES_META_CONSULTOR
    + tuple(f"{p}_OURO" for p in _ACELERADORES_META_CONSULTOR)
)


def _coluna_meta_consultor(produto: str, nivel) -> Optional[str]:
    """Nome da coluna do pivot para o par (produto, nivel).

    O par inteiro define a coluna — nunca so o produto. Sem isso,
    BRONZE/PRATA/OURO do mesmo produto colapsariam numa coluna unica e
    seriam SOMADOS pelo pivot (ex.: 0+6+12=18 contratos de acelerador),
    bug silencioso que nenhum consumidor teria como detectar.

    - ``nivel`` NULL: meta monetaria (R$) — coluna e o proprio produto.
    - ``GERAL``: meta de pontos — ``META_PRATA`` / ``META_OURO``.
    - demais produtos: acelerador em qtd de contratos — ``PRODUTO``
      (PRATA) e ``PRODUTO_OURO`` (OURO).
    - ``BRONZE``: devolve ``None`` (linha descartada).
    """
    if not nivel:
        return produto
    if nivel == "PRATA":
        return "META_PRATA" if produto == "GERAL" else produto
    if nivel == "OURO":
        return "META_OURO" if produto == "GERAL" else f"{produto}_OURO"
    return None


def carregar_metas_produto_consultor(
    mes: int,
    ano: int,
) -> pd.DataFrame:
    """Carrega metas por produto com escopo CONSULTOR.

    Escopo CONSULTOR e chaveado por ``loja_id`` (a tabela ``metas`` nao
    tem ``consultor_id``): cada linha e o alvo INDIVIDUAL de cada
    consultor daquela loja. Usado quando o perfil logado e consultor ou
    quando outro perfil filtrou ate um consultor especifico.

    Retorna pivot indexado por loja com tres familias de coluna, em
    tres unidades diferentes — nunca some colunas de familias
    distintas:

    - ``LOJA``;
    - ``CLT``, ``CNC``, ``CONSIGNADO``, ``FGTS``,
      ``FGTS_ANT_BENEF_13``, ``SAQUE`` — R$ (linhas de ``nivel`` NULL);
    - ``META_PRATA`` / ``META_OURO`` — pontos (produto ``GERAL``);
    - ``BMG_MED``, ``EMISSAO``, ``SUPER_CONTA``, ``VIDA_FAMILIAR`` e os
      pares ``*_OURO`` — quantidade de contratos (aceleradores).

    ``MIX`` nao existe neste escopo (so no escopo LOJA); quem precisa
    do alvo de mix soma os produtos componentes (ver
    ``PRODUTOS_DASHBOARD_COL_META`` em ``kpis/gerais.py``).

    TTL real: 6h para mes corrente, 24h para historico.
    """
    if _eh_mes_atual(mes, ano):
        return _metas_produto_consultor_atual(mes, ano, cache_version=1)
    return _metas_produto_consultor_historico(mes, ano, cache_version=1)


def _fetch_metas_produto_consultor(mes: int, ano: int) -> pd.DataFrame:
    """Executa a query de metas por produto (CONSULTOR) sem cache.

    Traz TODOS os niveis (NULL, PRATA, OURO; BRONZE e descartado no
    mapeamento de coluna). O filtro ``is_("nivel", "null")`` que existia
    aqui escondia do dashboard inteiro as metas de ponto (``GERAL``) e
    as de acelerador.

    Paginado por keyset em ``id`` (PK): sem o filtro de nivel sao ~940
    linhas por periodo (09/2026, 47 lojas) contra o teto default de
    1000 do PostgREST — a proxima leva de lojas truncaria o resultado
    em silencio.
    """
    periodo = carregar_periodo(mes, ano)
    if not periodo:
        return pd.DataFrame()

    all_data = _paginar_keyset(
        lambda limite: (
            _sb()
            .table("metas")
            .select("id, produto, escopo, nivel, valor, lojas(nome)")
            .eq("periodo_id", periodo["id"])
            .eq("escopo", "CONSULTOR")
            .order("id")
            .limit(limite)
        ),
        "id",
    )

    if not all_data:
        return pd.DataFrame()

    rows = []
    for m in all_data:
        coluna = _coluna_meta_consultor(m["produto"], m.get("nivel"))
        if coluna is None:
            continue
        loja = m.get("lojas") or {}
        rows.append(
            {
                "LOJA": loja.get("nome", ""),
                "coluna_meta": coluna,
                "valor": float(m.get("valor", 0) or 0),
            }
        )

    df = pd.DataFrame(rows)

    # Deduplicar por (LOJA, coluna_meta) — a constraint UNIQUE nao
    # impede duplicatas quando ``nivel`` e NULL no PG. A chave inclui o
    # nivel porque ``coluna_meta`` ja o codifica: assim cada celula do
    # pivot vem de UMA linha do banco e o aggfunc nunca mistura niveis.
    if not df.empty:
        df = df.drop_duplicates(
            subset=["LOJA", "coluna_meta"], keep="first"
        )

    if not df.empty:
        df_pivot = df.pivot_table(
            index="LOJA",
            columns="coluna_meta",
            values="valor",
            aggfunc="first",
            fill_value=0,
        ).reset_index()
        # Colunas de nivel sempre presentes (mesmo periodo sem a linha),
        # no mesmo espirito de _fetch_metas. As monetarias ficam como
        # estao: forcar 0 onde antes a coluna faltava trocaria "criterio
        # ignorado" por "meta zero" no consumidor.
        for col in _COLUNAS_NIVEL_META_CONSULTOR:
            if col not in df_pivot.columns:
                df_pivot[col] = 0.0
        return df_pivot

    return pd.DataFrame(columns=["LOJA"])


@st.cache_data(ttl=21600)
def _metas_produto_consultor_atual(
    mes: int,
    ano: int,
    cache_version: int = 1,  # bump v1: colunas de nivel (META_PRATA...)
) -> pd.DataFrame:
    """Metas por produto (CONSULTOR) — mes corrente. TTL 6h.

    ``cache_version`` entra na chave do cache porque o corpo DESTA
    funcao e uma delegacao de uma linha: o ``st.cache_data`` versiona a
    funcao decorada, nao as que ela chama. Mudar
    ``_fetch_metas_produto_consultor`` (formato do pivot, colunas novas)
    nao invalida nada — a sessao aberta segue servindo o DataFrame do
    formato antigo ate o TTL vencer. Mesmo padrao de ``_consolidar_*``.
    Bump obrigatorio a cada mudanca de formato do fetch.
    """
    return _fetch_metas_produto_consultor(mes, ano)


@st.cache_data(ttl=86400)
def _metas_produto_consultor_historico(
    mes: int,
    ano: int,
    cache_version: int = 1,  # bump v1: colunas de nivel (META_PRATA...)
) -> pd.DataFrame:
    """Metas por produto (CONSULTOR) — historico. TTL 24h.

    Ver ``_metas_produto_consultor_atual`` para o porque do
    ``cache_version`` (TTL de 24h aqui torna a versao ainda mais
    critica: sem bump, o formato antigo sobrevive um dia inteiro).
    """
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
        resultado = _consolidar_atual(mes, ano, cache_version=4)
    else:
        resultado = _consolidar_historico(mes, ano, cache_version=4)

    df, df_metas, df_supervisores, diag = resultado

    # Side-effect: diagnostico no session_state
    if diag:
        st.session_state["_diag_pontuacao"] = diag

    return df, df_metas, df_supervisores


@st.cache_data(ttl=1800)
def _consolidar_atual(
    mes: int,
    ano: int,
    cache_version: int = 4,  # bump v4: VALOR = valor_consolidado
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Optional[dict]]:
    """Consolidacao — mes corrente. TTL 30min."""
    return _executar_consolidacao(mes, ano)


@st.cache_data(ttl=86400)
def _consolidar_historico(
    mes: int,
    ano: int,
    cache_version: int = 4,  # bump v4: VALOR = valor_consolidado
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Optional[dict]]:
    """Consolidacao — historico. TTL 24h."""
    return _executar_consolidacao(mes, ano)


def _executar_consolidacao(
    mes: int,
    ano: int,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Optional[dict]]:
    """Consolidacao cacheada — pura, sem side-effects.

    **Carga aqui, regra em ``kpis/consolidacao.py``** (Etapa 2 da
    revisao de 09/2026). Esta funcao junta os quatro loaders do periodo
    e delega a transformacao; a pontuacao, o fallback de categoria, o
    diagnostico, as regras de exclusao e as classificacoes de produto
    mudaram de arquivo sem mudar de comportamento.

    O early-return de ``df`` vazio fica do lado da carga de proposito:
    sem contrato pago nao ha o que consolidar, e ``consolidar_pontuacao``
    pressupoe frame nao vazio.
    """
    df = carregar_contratos_pagos(mes, ano)
    df_pontos = carregar_pontuacao_efetiva(mes, ano)
    df_metas = carregar_metas(mes, ano)
    df_supervisores = carregar_supervisores(mes, ano)

    if df.empty:
        return df, df_metas, df_supervisores, None

    df, diag = consolidar_pontuacao(df, df_pontos, carregar_categorias)
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
