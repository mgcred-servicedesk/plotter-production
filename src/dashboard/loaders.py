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
from typing import List, Optional, Tuple

import pandas as pd
import streamlit as st

from src.config.supabase_client import get_supabase_client


_PAGE_SIZE = 1000


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

    all_data: List[dict] = []
    offset = 0
    while True:
        resp = (
            _sb()
            .from_("v_contratos_dashboard")
            .select("*")
            .eq("periodo_id", periodo["id"])
            .order("id")
            .limit(_PAGE_SIZE)
            .offset(offset)
            .execute()
        )
        batch = resp.data or []
        all_data.extend(batch)
        if len(batch) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    if not all_data:
        return pd.DataFrame()

    rows = []
    for c in all_data:
        rows.append(
            {
                "CONTRATO_ID": c.get("contrato_id"),
                "DATA": c.get("data_status_pagamento"),
                "DATA_CADASTRO": c.get("data_cadastro"),
                "LOJA": c.get("loja", ""),
                "REGIAO": c.get("regiao", ""),
                "CONSULTOR": c.get("consultor", ""),
                "PRODUTO": c.get("produto", ""),
                "TIPO_PRODUTO": c.get("tipo_produto", ""),
                "SUBTIPO": c.get("subtipo", ""),
                "TIPO OPER.": c.get("tipo_operacao", ""),
                "VALOR": float(c.get("valor", 0)),
                "BANCO": c.get("banco", ""),
                "CONVENIO": c.get("convenio", ""),
                "categoria_codigo": c.get("categoria_codigo", ""),
                "grupo_dashboard": c.get("grupo_dashboard"),
                "grupo_meta": c.get("grupo_meta"),
                "conta_valor": c.get("conta_valor", True),
                "conta_pontuacao": c.get("conta_pontuacao", True),
            }
        )

    df = pd.DataFrame(rows)

    if "DATA" in df.columns:
        df["DATA"] = pd.to_datetime(df["DATA"], errors="coerce")

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
    """Executa a RPC de contratos em analise sem cache."""
    all_data: List[dict] = []
    offset = 0
    while True:
        resp = (
            _sb()
            .rpc(
                "obter_contratos_em_analise",
                {"p_mes": mes, "p_ano": ano},
            )
            .range(offset, offset + _PAGE_SIZE - 1)
            .execute()
        )
        batch = resp.data or []
        all_data.extend(batch)
        if len(batch) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    if not all_data:
        return pd.DataFrame()

    rows = []
    for c in all_data:
        rows.append(
            {
                "CONTRATO_ID": c.get("contrato_id"),
                "DATA_CADASTRO": c.get("data_cadastro"),
                "LOJA": c.get("loja", ""),
                "REGIAO": c.get("regiao", ""),
                "CONSULTOR": c.get("consultor", ""),
                "PRODUTO": c.get("produto", ""),
                "TIPO_PRODUTO": c.get("tipo_produto", ""),
                "SUBTIPO": c.get("subtipo", ""),
                "TIPO OPER.": c.get("tipo_operacao", ""),
                "VALOR": float(c.get("valor", 0)),
                "BANCO": c.get("banco", ""),
                "STATUS_BANCO": c.get("status_banco", ""),
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

    return df


@st.cache_data(ttl=900)
def _contratos_em_analise_atual(mes: int, ano: int) -> pd.DataFrame:
    """Contratos em analise — mes corrente. TTL 15min."""
    return _fetch_contratos_em_analise(mes, ano)


@st.cache_data(ttl=21600)
def _contratos_em_analise_historico(mes: int, ano: int) -> pd.DataFrame:
    """Contratos em analise — historico. TTL 6h."""
    return _fetch_contratos_em_analise(mes, ano)


# ══════════════════════════════════════════════════════
# Contratos cancelados
# ══════════════════════════════════════════════════════


def carregar_contratos_cancelados(
    mes: int,
    ano: int,
) -> pd.DataFrame:
    """Carrega contratos cancelados via RPC obter_contratos_cancelados.

    TTL real: 15min para mes corrente, 6h para historico.
    """
    if _eh_mes_atual(mes, ano):
        return _contratos_cancelados_atual(mes, ano)
    return _contratos_cancelados_historico(mes, ano)


def _fetch_contratos_cancelados(mes: int, ano: int) -> pd.DataFrame:
    """Executa a RPC de contratos cancelados sem cache."""
    all_data: List[dict] = []
    offset = 0
    while True:
        resp = (
            _sb()
            .rpc(
                "obter_contratos_cancelados",
                {"p_mes": mes, "p_ano": ano},
            )
            .range(offset, offset + _PAGE_SIZE - 1)
            .execute()
        )
        batch = resp.data or []
        all_data.extend(batch)
        if len(batch) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    if not all_data:
        return pd.DataFrame()

    rows = []
    for c in all_data:
        rows.append(
            {
                "CONTRATO_ID": c.get("contrato_id"),
                "DATA_CADASTRO": c.get("data_cadastro"),
                "LOJA": c.get("loja", ""),
                "REGIAO": c.get("regiao", ""),
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

    return df


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


def _fetch_metas(mes: int, ano: int) -> pd.DataFrame:
    """Executa a query de metas GERAL/LOJA sem cache."""
    periodo = carregar_periodo(mes, ano)
    if not periodo:
        return pd.DataFrame()

    resp = (
        _sb()
        .table("metas")
        .select(
            "id, produto, escopo, nivel, valor, "
            "lojas(nome)"
        )
        .eq("periodo_id", periodo["id"])
        .eq("produto", "GERAL")
        .eq("escopo", "LOJA")
        .execute()
    )

    if not resp.data:
        return pd.DataFrame(
            columns=["LOJA", "META_PRATA", "META_OURO"]
        )

    rows = []
    for m in resp.data:
        loja = m.get("lojas") or {}
        rows.append(
            {
                "LOJA": loja.get("nome", ""),
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

        return df_pivot

    return pd.DataFrame(columns=["LOJA", "META_PRATA", "META_OURO"])


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

    resp = (
        _sb()
        .table("metas")
        .select("produto, escopo, nivel, valor, lojas(nome)")
        .eq("periodo_id", periodo["id"])
        .eq("escopo", "LOJA")
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
        return df_pivot

    return pd.DataFrame(columns=["LOJA"])


@st.cache_data(ttl=21600)
def _metas_produto_atual(mes: int, ano: int) -> pd.DataFrame:
    """Metas por produto — mes corrente. TTL 6h."""
    return _fetch_metas_produto(mes, ano)


@st.cache_data(ttl=86400)
def _metas_produto_historico(mes: int, ano: int) -> pd.DataFrame:
    """Metas por produto — historico. TTL 24h."""
    return _fetch_metas_produto(mes, ano)


# ══════════════════════════════════════════════════════
# Lojas, regioes e consultores de cadastro
# ══════════════════════════════════════════════════════


@st.cache_data(ttl=21600)
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


@st.cache_data(ttl=86400)
def carregar_consultores_cadastro() -> list[str]:
    """
    Retorna lista ordenada de nomes de consultores
    cadastrados em ``consultores`` (ativos).

    Usado em selects de configuracao (cadastro de
    usuario e 'Visualizar Como'). TTL 24h.
    """
    resp = (
        _sb()
        .table("consultores")
        .select("nome, status")
        .order("nome")
        .execute()
    )
    nomes: list[str] = []
    for row in resp.data or []:
        status = (row.get("status") or "").lower()
        if status and "ativo" not in status:
            continue
        nome = row.get("nome", "")
        if nome:
            nomes.append(nome)
    return sorted(set(nomes))


# ══════════════════════════════════════════════════════
# Supervisores
# ══════════════════════════════════════════════════════


@st.cache_data(ttl=21600)
def carregar_supervisores() -> pd.DataFrame:
    """Carrega supervisores com suas lojas e regioes. TTL 6h."""
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
    if _eh_mes_atual(mes, ano):
        resultado = _consolidar_atual(mes, ano)
    else:
        resultado = _consolidar_historico(mes, ano)

    df, df_metas, df_supervisores, diag = resultado

    # Side-effect: diagnostico no session_state
    if diag:
        st.session_state["_diag_pontuacao"] = diag

    return df, df_metas, df_supervisores


@st.cache_data(ttl=1800)
def _consolidar_atual(
    mes: int,
    ano: int,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Optional[dict]]:
    """Consolidacao — mes corrente. TTL 30min."""
    return _executar_consolidacao(mes, ano)


@st.cache_data(ttl=86400)
def _consolidar_historico(
    mes: int,
    ano: int,
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

    # Fallback: preencher categoria_codigo via TIPO_PRODUTO
    # quando produtos.categoria_id esta NULL no banco
    _TIPO_PARA_CATEGORIA = {
        "CNC": "CNC",
        "CNC 13º": "CNC_13",
        "CNC 13": "CNC_13",
        "CNC ANT": "ANT_BENEF",
        "SAQUE": "SAQUE",
        "SAQUE BENEFICIO": "SAQUE_BENEFICIO",
        "CONSIG": "CONSIG_BMG",
        "CONSIG BMG": "CONSIG_BMG",
        "CONSIG PRIV": "CONSIG_PRIV",
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

    mask_sem_cat = df["categoria_codigo"] == ""
    if mask_sem_cat.any() and "TIPO_PRODUTO" in df.columns:
        df.loc[mask_sem_cat, "categoria_codigo"] = (
            df.loc[mask_sem_cat, "TIPO_PRODUTO"]
            .map(_TIPO_PARA_CATEGORIA)
            .fillna("")
        )

        # Preencher grupo_dashboard, grupo_meta, conta_valor,
        # conta_pontuacao a partir das categorias do banco
        categorias = carregar_categorias()
        if not categorias.empty:
            cat_map = categorias.set_index("codigo")
            preenchidos = mask_sem_cat & (df["categoria_codigo"] != "")

            for campo in [
                "grupo_dashboard",
                "grupo_meta",
                "conta_valor",
                "conta_pontuacao",
            ]:
                if campo in cat_map.columns:
                    df.loc[preenchidos, campo] = (
                        df.loc[preenchidos, "categoria_codigo"]
                        .map(cat_map[campo])
                    )

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
    df["is_super_conta"] = df["SUBTIPO"] == "SUPER CONTA"

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
