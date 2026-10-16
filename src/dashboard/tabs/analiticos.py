"""
Aba Analiticos: detalhamento de contratos (pagos/em analise/
cancelados), consultores por produto, producao por regiao e
distribuicao de produtos.
"""

import logging

import pandas as pd
import streamlit as st
import streamlit_antd_components as sac

from src.dashboard.components.tables import (
    botao_exportar_csv,
    exibir_tabela,
)
from src.dashboard.formatters import (
    formatar_moeda,
    formatar_numero,
    formatar_percentual,
)
from src.dashboard.kpis.gerais import (
    calcular_assertividade_consultores,
    calcular_oportunidades_perdidas,
    mascaras_aceleradores,
    separar_cancelados_liquidos,
)
from src.dashboard.kpis.seguros import (
    _classificar_status_seguro,
    _pool_seguros,
)
from src.dashboard.kpis.produtos import (
    BANCOS_BMG_HELP,
    COL_PRODUTO_DETALHADO,
    adicionar_produto_detalhado,
    calcular_distribuicao_produtos,
    calcular_distribuicao_produtos_por_loja,
    opcoes_banco,
)
from src.dashboard.kpis.reconquista import (
    CARTEIRA_ERRO,
    CARTEIRA_FORA,
    CARTEIRA_NAO_IMPORTADA,
    carteira_elegivel_vigente,
    LIGA_ERRO,
    LIGA_FORA,
    LIGA_NAO_IMPORTADA,
    PROMESSA_ERRO,
    PROMESSA_FORA,
    PROMESSA_NAO_IMPORTADA,
    _anotar_contadores_promessa,
)
from src.dashboard.kpis.prestamista import (
    PRESTAMISTA_ERRO,
    PRESTAMISTA_NAO_IMPORTADO,
    PRESTAMISTA_OK,
    SITUACAO_COM_SEGURO,
    SITUACAO_ELEGIVEL,
    SITUACAO_NAO_ELEGIVEL,
    SITUACAO_SEM_SEGURO,
    com_situacao,
    marcar_situacao_por_ade,
    totais_prestamista,
)
from src.dashboard.loaders import carregar_carteira_elegivel
from src.dashboard.ui.kpi_cards_reforma import render_quebras_prestamista

logger = logging.getLogger(__name__)


# Compat: alias local mantido — implementação canônica em
# components/tables.py (CSV sob demanda via callable).
_exportar_csv = botao_exportar_csv


# Colunas de produto exibidas nas tabelas de detalhamento, na ordem
# da hierarquia do banco: grupo (PRODUTO_DETALHADO — grupo_dashboard com
# o PACK desmembrado em FGTS / ANT. DE BENEF. / CNC 13º) →
# TIPO_PRODUTO (produtos.tipo) → SUBTIPO (produtos.subtipo).
_COLS_PRODUTO = [COL_PRODUTO_DETALHADO, "TIPO_PRODUTO", "SUBTIPO"]


# Icones das sub-navegacoes. Sao Material Symbols (`:material/<nome>:`),
# nao Bootstrap: o st.pills renderiza markdown no rotulo. Nomes validos
# em `streamlit.material_icon_names.ALL_MATERIAL_ICONS`.
# `rocket_launch` em Aceleradores (e nao `bolt`, a traducao literal do
# antigo `lightning-charge`) porque `bolt` ja e o icone da aba principal
# Pagamentos Online.
_ICONES_ANALITICOS = {
    "Propostas Pagas": "check_circle",
    "Em Analise": "schedule",
    "Cancelados": "cancel",
    "Aceleradores": "rocket_launch",
    "Reconquista": "autorenew",
    "Cobranca Consignavel": "payments",
    "Prestamista": "shield",
    "Distribuicao de Produtos": "pie_chart",
}

# Ordem = ordem da sub-nav. "Promessa Diária" so entra nas options
# com a Promessa V3 vigente (>= 09/2026); "Carteira Elegível" (>= 10/2026)
# SUBSTITUI "Por Loja" e "Detalhamento", que leem o export antigo (nao
# mais importado) — ver `_render_reconquista`.
_ICONES_RECONQUISTA = {
    "Liga": "verified",
    "Promessa Diária": "handshake",
    "Carteira Elegível": "assignment",
    "Por Loja": "storefront",
    "Detalhamento": "table_chart",
}
_SUB_EXPORT = ("Por Loja", "Detalhamento")


def _opcoes_coluna(df: pd.DataFrame, coluna: str) -> list:
    """Valores distintos de `coluna` para selectbox (sem nulo/vazio).

    Em analise/cancelados chegam com "" onde o join de produto nao
    resolveu; pagos chegam com NaN. Ambos ficam fora das opcoes.
    """
    if coluna not in df.columns:
        return []
    return sorted(
        {
            str(x).strip()
            for x in df[coluna].unique()
            if pd.notna(x) and str(x).strip()
        }
    )


def _filtrar_detalhamento(df: pd.DataFrame, key_prefix: str) -> pd.DataFrame:
    """Filtros de Loja, Consultor, Produto, Banco e Subproduto.

    Produto filtra por ``PRODUTO_DETALHADO`` — a taxonomia do dashboard
    com o PACK desmembrado, para que FGTS, ANT. DE BENEF. e CNC 13º
    sejam buscaveis separadamente. Banco filtra por ``BANCO`` (valores
    crus, sem normalizacao — mesma logica de ``_opcoes_coluna`` ja usada
    em Produto). Subproduto filtra por ``SUBTIPO`` (NOVO, REFIN, MARGEM
    COMPLEMENTAR, SUPER CONTA...) e e em cascata: suas opcoes saem do
    recorte ja filtrado (incluindo Banco), evitando combinacoes sem
    linhas.
    """
    df = adicionar_produto_detalhado(df)
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        lojas = ["Todas"] + sorted(df["LOJA"].unique().tolist())
        filt_loja = st.selectbox("Loja", lojas, key=f"{key_prefix}_loja")
    with col2:
        consultores = ["Todos"] + sorted(
            df["CONSULTOR"].unique().tolist()
        )
        filt_cons = st.selectbox(
            "Consultor", consultores, key=f"{key_prefix}_cons"
        )
    with col3:
        produtos = ["Todos"] + _opcoes_coluna(df, COL_PRODUTO_DETALHADO)
        filt_prod = st.selectbox(
            "Produto", produtos, key=f"{key_prefix}_prod"
        )
    with col4:
        bancos = ["Todos"] + _opcoes_coluna(df, "BANCO")
        filt_banco = st.selectbox(
            "Banco", bancos, key=f"{key_prefix}_banco"
        )

    df_d = df.copy()
    if filt_loja != "Todas":
        df_d = df_d[df_d["LOJA"] == filt_loja]
    if filt_cons != "Todos":
        df_d = df_d[df_d["CONSULTOR"] == filt_cons]
    if filt_prod != "Todos" and COL_PRODUTO_DETALHADO in df_d.columns:
        df_d = df_d[df_d[COL_PRODUTO_DETALHADO] == filt_prod]
    if filt_banco != "Todos" and "BANCO" in df_d.columns:
        df_d = df_d[df_d["BANCO"].astype(str).str.strip() == filt_banco]

    subprodutos = ["Todos"] + _opcoes_coluna(df_d, "SUBTIPO")
    # Cascata: ao trocar Produto/Banco, o Subproduto selecionado pode nao
    # existir mais nas opcoes. Reseta antes de instanciar o widget
    # (depois disso o session_state e imutavel no mesmo rerun).
    key_sub = f"{key_prefix}_sub"
    if st.session_state.get(key_sub) not in subprodutos:
        st.session_state[key_sub] = "Todos"
    with col5:
        filt_sub = st.selectbox("Subproduto", subprodutos, key=key_sub)

    if filt_sub != "Todos" and "SUBTIPO" in df_d.columns:
        df_d = df_d[df_d["SUBTIPO"].astype(str).str.strip() == filt_sub]

    return df_d


def _prestamista_propostas(prestamista: dict | None) -> pd.DataFrame | None:
    """Propostas do Prestamista (pos-RLS) se o periodo foi importado."""
    if not prestamista or prestamista.get("status") != PRESTAMISTA_OK:
        return None
    return prestamista.get("propostas")


def _render_detalhamento_pagos(df, df_sup, prestamista: dict | None = None):
    """Sub-aba: detalhamento de contratos pagos.

    Com o Prestamista CNC importado no periodo, ganha a coluna
    "Prestamista" (situacao da ADE no arquivo do banco) e o filtro das
    elegiveis sem seguro. ADE fora do arquivo fica em branco.
    """
    if df.empty:
        st.warning("Nenhum contrato pago no periodo.")
        return

    st.markdown(f"**{len(df):,} contratos pagos**".replace(",", "."))

    df_d = _filtrar_detalhamento(df, "det_pago")

    propostas_prest = _prestamista_propostas(prestamista)
    if propostas_prest is not None:
        df_d = df_d.copy()
        df_d["PRESTAMISTA"] = marcar_situacao_por_ade(
            _nr_ade(df_d), propostas_prest
        )
        n_pend = int((df_d["PRESTAMISTA"] == SITUACAO_SEM_SEGURO).sum())
        if st.checkbox(
            f"Só Prestamista elegível sem seguro ({n_pend})",
            key="det_pago_prest_pend",
        ):
            df_d = df_d[df_d["PRESTAMISTA"] == SITUACAO_SEM_SEGURO]

    # KPIs
    total_valor = df_d["VALOR"].sum()
    total_trans = len(df_d[df_d["VALOR"] > 0])
    tk = total_valor / total_trans if total_trans > 0 else 0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total de Valor", formatar_moeda(total_valor))
    with col2:
        st.metric("Ticket Medio", formatar_moeda(tk))
    with col3:
        st.metric("Quantidade", formatar_numero(len(df_d)))

    # Tabela detalhada
    # NUM_PROPOSTA preferido; fallback para CONTRATO_ID em registros
    # importados antes da correção do campo Nº PROP/ADE.
    df_d = df_d.copy()
    df_d["NR_ADE"] = _nr_ade(df_d)

    cols = ["NR_ADE", "DATA", "LOJA", "CONSULTOR"]
    if "REGIAO" in df_d.columns:
        cols.append("REGIAO")
    cols += _COLS_PRODUTO + [
        "TIPO OPER.", "MODALIDADE", "VALOR", "BANCO", "PRESTAMISTA",
    ]

    cols_disp = [c for c in cols if c in df_d.columns]
    df_tabela = (
        df_d[cols_disp]
        .sort_values("DATA", ascending=False)
        .rename(columns={
            "PRESTAMISTA": "Prestamista",
            "NR_ADE": "Nº ADE",
            "DATA": "Data Pagamento",
            COL_PRODUTO_DETALHADO: "Grupo",
            "TIPO_PRODUTO": "Produto",
            "SUBTIPO": "Subproduto",
            "TIPO OPER.": "Tipo Operacao",
            "MODALIDADE": "Modalidade",
            "VALOR": "Valor",
            "BANCO": "Banco",
            "LOJA": "Loja",
            "CONSULTOR": "Consultor",
            "REGIAO": "Regiao",
        })
    )
    exibir_tabela(
        df_tabela,
        colunas_moeda=["Valor"],
        paginacao=100,
        key="tab_det_pagos",
    )
    _exportar_csv(df_tabela, "contratos_pagos", "exp_pagos")


def _render_detalhamento_em_analise(df_analise):
    """Sub-aba: detalhamento de contratos em analise."""
    if df_analise.empty:
        st.warning("Nenhum contrato em analise no periodo.")
        return

    st.markdown(
        f"**{len(df_analise):,} contratos em analise**"
        .replace(",", ".")
    )

    df_d = _filtrar_detalhamento(df_analise, "det_analise")

    # KPIs
    total_valor = df_d["VALOR"].sum()
    total_trans = len(df_d)
    tk = total_valor / total_trans if total_trans > 0 else 0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Valor Total", formatar_moeda(total_valor))
    with col2:
        st.metric("Ticket Medio", formatar_moeda(tk))
    with col3:
        st.metric("Quantidade", formatar_numero(total_trans))

    # Tabela detalhada
    df_d = df_d.copy()
    df_d["NR_ADE"] = _nr_ade(df_d)

    cols = ["NR_ADE", "DATA_CADASTRO", "LOJA", "CONSULTOR"]
    if "REGIAO" in df_d.columns:
        cols.append("REGIAO")
    cols += _COLS_PRODUTO + [
        "TIPO OPER.", "MODALIDADE", "VALOR",
        "STATUS_BANCO", "BANCO",
    ]

    cols_disp = [c for c in cols if c in df_d.columns]
    df_tabela = (
        df_d[cols_disp]
        .sort_values("DATA_CADASTRO", ascending=False)
        .rename(columns={
            "NR_ADE": "Nº ADE",
            "DATA_CADASTRO": "Data Cadastro",
            COL_PRODUTO_DETALHADO: "Grupo",
            "TIPO_PRODUTO": "Produto",
            "SUBTIPO": "Subproduto",
            "TIPO OPER.": "Tipo Operacao",
            "MODALIDADE": "Modalidade",
            "VALOR": "Valor",
            "STATUS_BANCO": "Status Banco",
            "BANCO": "Banco",
            "LOJA": "Loja",
            "CONSULTOR": "Consultor",
            "REGIAO": "Regiao",
        })
    )
    exibir_tabela(
        df_tabela,
        colunas_moeda=["Valor"],
        paginacao=100,
        key="tab_det_analise",
    )
    _exportar_csv(
        df_tabela, "contratos_em_analise", "exp_analise"
    )


def _render_detalhamento_cancelados(df_cancel):
    """Sub-aba: detalhamento de contratos cancelados."""
    if df_cancel.empty:
        st.warning("Nenhum contrato cancelado no periodo.")
        return

    df_liq, n_redig, n_recup = separar_cancelados_liquidos(df_cancel)
    n_bruto = len(df_cancel)
    n_liq = len(df_liq)

    st.markdown(
        f"**{n_liq:,} cancelados liquidos** "
        f"(de {n_bruto:,} no bruto)".replace(",", ".")
    )
    if n_redig or n_recup:
        st.caption(
            f"Fora da conta: {n_redig} redigitada(s) "
            f"(superada por redigitacao em 7 dias) e "
            f"{n_recup} recuperada(s) (paga em 7 dias)."
        )

    df_d = _filtrar_detalhamento(df_cancel, "det_cancel")

    # KPIs — cancelados liquidos (exclui redigitadas e recuperadas),
    # no layout das sub-abas adjacentes (Valor Total / Ticket Medio /
    # Quantidade). O total geral (bruto) aparece como info secundaria.
    df_d_liq, _, _ = separar_cancelados_liquidos(df_d)
    n_liq_d = len(df_d_liq)
    n_bruto_d = len(df_d)
    valor_liq_d = df_d_liq["VALOR"].sum()
    tk = valor_liq_d / n_liq_d if n_liq_d > 0 else 0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Valor Total", formatar_moeda(valor_liq_d))
    with col2:
        st.metric("Ticket Medio", formatar_moeda(tk))
    with col3:
        st.metric("Quantidade", formatar_numero(n_liq_d))
    st.caption(
        f"Total geral: {formatar_numero(n_bruto_d)} no bruto"
    )

    # Tabela detalhada
    df_d = df_d.copy()
    df_d["NR_ADE"] = _nr_ade(df_d)

    cols = ["NR_ADE", "DATA_CADASTRO", "LOJA", "CONSULTOR"]
    if "REGIAO" in df_d.columns:
        cols.append("REGIAO")
    cols += _COLS_PRODUTO + [
        "TIPO OPER.", "MODALIDADE", "VALOR",
        "SUB_STATUS", "STATUS_PAG", "BANCO", "CLASSIFICACAO",
    ]

    cols_disp = [c for c in cols if c in df_d.columns]
    df_tabela = (
        df_d[cols_disp]
        .sort_values("DATA_CADASTRO", ascending=False)
        .rename(columns={
            "NR_ADE": "Nº ADE",
            "DATA_CADASTRO": "Data Cadastro",
            COL_PRODUTO_DETALHADO: "Grupo",
            "TIPO_PRODUTO": "Produto",
            "SUBTIPO": "Subproduto",
            "TIPO OPER.": "Tipo Operacao",
            "MODALIDADE": "Modalidade",
            "VALOR": "Valor",
            "SUB_STATUS": "Sub-Status",
            "STATUS_PAG": "Status Pagamento",
            "BANCO": "Banco",
            "LOJA": "Loja",
            "CONSULTOR": "Consultor",
            "REGIAO": "Regiao",
            "CLASSIFICACAO": "Classificacao",
        })
    )
    exibir_tabela(
        df_tabela,
        colunas_moeda=["Valor"],
        paginacao=100,
        key="tab_det_cancel",
    )
    _exportar_csv(
        df_tabela, "contratos_cancelados", "exp_cancel"
    )


# Por perfil: (coluna flag, rotulo "capturada por X", frase "fechou ... X")
_OPORTUNIDADE_POR_PERFIL = {
    "consultor": (
        "RECUPERADA_OUTRO", "outro consultor", "com outro consultor",
    ),
    "supervisor": (
        "RECUPERADA_OUTRA_LOJA", "outra loja", "em outra loja",
    ),
    "gerente_comercial": (
        "RECUPERADA_OUTRA_REGIAO", "outra regiao", "em outra regiao",
    ),
}


def _render_oportunidades_perdidas(df_cancelados, perfil):
    """Secao: vendas do cliente capturadas FORA do proprio nivel.

    Exibida para consultor (outro consultor), supervisor (outra loja)
    e gerente (outra regiao). Identidade de quem capturou nao e
    exibida (so qtd e valor perdido).
    """
    cfg = _OPORTUNIDADE_POR_PERFIL.get(perfil)
    if cfg is None:
        return
    coluna_flag, rotulo, frase = cfg

    res = calcular_oportunidades_perdidas(df_cancelados, coluna_flag)
    if res["qtd_perdidas"] == 0:
        return

    sac.divider(
        label="Oportunidades perdidas",
        icon="exclamation-triangle",
        align="left",
        color="gray",
    )
    col1, col2 = st.columns(2)
    with col1:
        st.metric(
            f"Vendas capturadas por {rotulo}",
            formatar_numero(res["qtd_perdidas"]),
        )
    with col2:
        st.metric(
            "Valor perdido",
            formatar_moeda(res["valor_perdido"]),
        )
    st.caption(
        f"Cancelados do seu escopo cujo cliente fechou o mesmo "
        f"produto {frase} em ate 7 dias. A identidade de quem "
        f"capturou a venda nao e exibida."
    )


def _render_assertividade_consultores(
    df, df_analise, df_cancelados, df_sup
):
    """Assertividade dos consultores no cenario de redigitacao."""
    res = calcular_assertividade_consultores(
        df_cancelados, df, df_analise, df_sup
    )
    por_consultor = res["por_consultor"]
    if por_consultor.empty:
        return

    sac.divider(
        label="Assertividade dos Consultores",
        icon="person-check",
        align="left",
        color="gray",
    )

    col1, col2 = st.columns(2)
    with col1:
        st.metric(
            "Assertividade geral",
            formatar_percentual(res["assertividade_org"]),
        )
    with col2:
        st.metric(
            "Redigitacoes no periodo",
            formatar_numero(res["total_redigitadas"]),
        )

    st.caption(
        "Assertividade = 1 - redigitadas / (pagas + em analise + "
        "canceladas) por consultor. Quanto menor, mais retrabalho "
        "operacional (redigitacao de proposta)."
    )

    df_tab = por_consultor.rename(
        columns={
            "CONSULTOR": "Consultor",
            "total_propostas": "Propostas",
            "redigitadas": "Redigitadas",
            "assertividade": "Assertividade (%)",
        }
    )
    exibir_tabela(
        df_tab,
        colunas_numero=["Propostas", "Redigitadas"],
        colunas_percentual=["Assertividade (%)"],
    )


def _nr_ade(frame: pd.DataFrame) -> pd.Series:
    """Deriva coluna NR_ADE: NUM_PROPOSTA com fallback para CONTRATO_ID."""
    return (
        frame.get("NUM_PROPOSTA", pd.Series("", index=frame.index))
        .replace("", pd.NA)
        .fillna(frame["CONTRATO_ID"].astype(str))
    )


def _render_busca_ade(df, df_analise, df_cancelados):
    """Busca unificada por Nº ADE em todos os status."""
    fontes = [
        (df, "Pago", "DATA"),
        (df_analise, "Em Analise", "DATA_CADASTRO"),
        (df_cancelados, "Cancelado", "DATA_CADASTRO"),
    ]
    resultados = []
    for src, status, col_data in fontes:
        if src.empty:
            continue
        src2 = src.copy()
        src2["NR_ADE"] = _nr_ade(src2)
        src2["Status"] = status
        src2["_DATA"] = src2.get(col_data, pd.Series(dtype="object"))
        resultados.append(src2)

    if not resultados:
        return

    df_all = adicionar_produto_detalhado(
        pd.concat(resultados, ignore_index=True)
    )

    busca = st.text_input(
        "Buscar por Nº ADE",
        placeholder="Digite o número ADE e pressione Enter...",
        key="ade_search_input",
    )

    if not busca.strip():
        return

    mask = df_all["NR_ADE"].astype(str).str.contains(
        busca.strip(), case=False, na=False
    )
    encontrados = df_all[mask]

    if encontrados.empty:
        st.warning(f"Nenhum resultado para '{busca.strip()}'.")
        return

    st.success(f"{len(encontrados)} resultado(s) encontrado(s).")

    cols_base = ["NR_ADE", "Status", "_DATA", "LOJA", "CONSULTOR"]
    if "REGIAO" in encontrados.columns:
        cols_base.append("REGIAO")
    cols_base += _COLS_PRODUTO + ["TIPO OPER.", "MODALIDADE", "VALOR", "BANCO"]

    df_res = (
        encontrados[[c for c in cols_base if c in encontrados.columns]]
        .sort_values("_DATA", ascending=False)
        .rename(columns={
            "NR_ADE": "Nº ADE",
            "_DATA": "Data",
            COL_PRODUTO_DETALHADO: "Grupo",
            "TIPO_PRODUTO": "Produto",
            "SUBTIPO": "Subproduto",
            "TIPO OPER.": "Tipo Operacao",
            "MODALIDADE": "Modalidade",
            "VALOR": "Valor",
            "BANCO": "Banco",
            "LOJA": "Loja",
            "CONSULTOR": "Consultor",
            "REGIAO": "Regiao",
        })
    )
    exibir_tabela(df_res, colunas_moeda=["Valor"])
    _exportar_csv(df_res, "busca_ade", "exp_busca_ade")


def _filtrar_loja_consultor(df: pd.DataFrame, key_prefix: str) -> pd.DataFrame:
    """Filtros de Loja e Consultor compartilhados pelos expanders."""
    if df.empty:
        return df
    col1, col2 = st.columns(2)
    with col1:
        lojas = ["Todas"] + sorted(df["LOJA"].dropna().unique().tolist())
        filt_loja = st.selectbox("Loja", lojas, key=f"{key_prefix}_loja")
    with col2:
        cons = ["Todos"] + sorted(df["CONSULTOR"].dropna().unique().tolist())
        filt_cons = st.selectbox(
            "Consultor", cons, key=f"{key_prefix}_cons",
        )
    out = df.copy()
    if filt_loja != "Todas":
        out = out[out["LOJA"] == filt_loja]
    if filt_cons != "Todos":
        out = out[out["CONSULTOR"] == filt_cons]
    return out


def _render_expander_seguro(
    nome: str,
    tipo_oper: str,
    df: pd.DataFrame,
    df_analise: pd.DataFrame,
    df_cancelados: pd.DataFrame,
    status_sel: str,
):
    """Renderiza expander para BMG Med ou Vida Familiar.

    Estes nao tem `status_banco` no fluxo normal; classificam por
    `SUB_STATUS` (Liquidada/Cancelada/demais).
    """
    pool = _pool_seguros(df, df_analise, df_cancelados, tipo_oper)
    if pool.empty:
        with st.expander(nome, expanded=False):
            st.warning(f"Nenhum contrato {nome} no periodo.")
        return

    pool["_STATUS"] = _classificar_status_seguro(pool["SUB_STATUS"])
    df_st = pool[pool["_STATUS"] == status_sel]
    qtd_total = len(df_st)

    titulo = f"{nome} — {qtd_total} contratos"
    with st.expander(titulo, expanded=False):
        if df_st.empty:
            st.info(f"Nenhum contrato {nome} em '{status_sel}'.")
            return

        df_f = _filtrar_loja_consultor(df_st, f"acel_{tipo_oper}")
        st.metric("Quantidade", formatar_numero(len(df_f)))

        df_f = df_f.copy()
        df_f["NR_ADE"] = _nr_ade(df_f)
        col_data = "DATA" if status_sel == "Pagas" else "DATA_CADASTRO"
        cols = ["NR_ADE", col_data, "LOJA", "CONSULTOR"]
        if "REGIAO" in df_f.columns:
            cols.append("REGIAO")
        cols += ["TIPO_PRODUTO", "SUB_STATUS", "BANCO"]
        cols_disp = [c for c in cols if c in df_f.columns]

        df_tab = (
            df_f[cols_disp]
            .sort_values(col_data, ascending=False)
            .rename(columns={
                "NR_ADE": "Nº ADE",
                "DATA": "Data Pagamento",
                "DATA_CADASTRO": "Data Cadastro",
                "TIPO_PRODUTO": "Produto",
                "SUB_STATUS": "Sub-Status",
                "BANCO": "Banco",
                "LOJA": "Loja",
                "CONSULTOR": "Consultor",
                "REGIAO": "Regiao",
            })
        )
        exibir_tabela(df_tab)
        _exportar_csv(
            df_tab, f"acel_{nome.lower().replace(' ', '_')}_{status_sel.lower().replace(' ', '_')}",
            f"exp_acel_{tipo_oper}_{status_sel}",
        )


def _linhas_acelerador(fonte: pd.DataFrame, nome: str) -> pd.DataFrame:
    """Linhas de ``fonte`` que sao o acelerador ``nome``.

    Delega a ``mascaras_aceleradores`` (kpis/gerais.py), a definicao
    unica de Emissao e Super Conta. Ate 09/2026 os expanders escreviam a
    mascara inline — uma quarta superficie que concordava com a canonica
    por coincidencia.
    """
    return fonte[mascaras_aceleradores(fonte)[nome]]


def _render_expander_emissao(
    df: pd.DataFrame,
    df_analise: pd.DataFrame,
    df_cancelados: pd.DataFrame,
    status_sel: str,
):
    """Emissao segue o ciclo normal (status_banco) — usa as 3 fontes
    nativas. Conta apenas como quantidade (VALOR zerado por design)."""
    fonte = {"Pagas": df, "Em Analise": df_analise, "Cancelados": df_cancelados}[status_sel]
    if fonte is None or fonte.empty or "TIPO_PRODUTO" not in fonte.columns:
        with st.expander("Emissao", expanded=False):
            st.warning("Nenhum contrato de emissao no periodo.")
        return

    df_e = _linhas_acelerador(fonte, "Emissao")

    titulo = f"Emissao — {len(df_e)} contratos"
    with st.expander(titulo, expanded=False):
        if df_e.empty:
            st.info(f"Nenhuma emissao em '{status_sel}'.")
            return

        df_f = _filtrar_loja_consultor(df_e, "acel_emissao")
        st.metric("Quantidade", formatar_numero(len(df_f)))

        df_f = df_f.copy()
        df_f["NR_ADE"] = _nr_ade(df_f)
        col_data = "DATA" if status_sel == "Pagas" else "DATA_CADASTRO"
        cols = ["NR_ADE", col_data, "LOJA", "CONSULTOR"]
        if "REGIAO" in df_f.columns:
            cols.append("REGIAO")
        cols += ["TIPO_PRODUTO", "TIPO OPER.", "BANCO"]
        if status_sel != "Pagas" and "STATUS_BANCO" in df_f.columns:
            cols.append("STATUS_BANCO")
        cols_disp = [c for c in cols if c in df_f.columns]

        df_tab = (
            df_f[cols_disp]
            .sort_values(col_data, ascending=False)
            .rename(columns={
                "NR_ADE": "Nº ADE",
                "DATA": "Data Pagamento",
                "DATA_CADASTRO": "Data Cadastro",
                "TIPO_PRODUTO": "Produto",
                "TIPO OPER.": "Tipo Operacao",
                "STATUS_BANCO": "Status Banco",
                "BANCO": "Banco",
                "LOJA": "Loja",
                "CONSULTOR": "Consultor",
                "REGIAO": "Regiao",
            })
        )
        exibir_tabela(df_tab)
        _exportar_csv(
            df_tab, f"acel_emissao_{status_sel.lower().replace(' ', '_')}",
            f"exp_acel_emissao_{status_sel}",
        )


def _render_expander_super_conta(
    df: pd.DataFrame,
    df_analise: pd.DataFrame,
    df_cancelados: pd.DataFrame,
    status_sel: str,
):
    """Super Conta segue o ciclo normal (status_banco). Conta valor e
    quantidade (e o mesmo valor ja esta computado em CNC por regra de
    negocio — exibido aqui apenas para auditoria)."""
    fonte = {"Pagas": df, "Em Analise": df_analise, "Cancelados": df_cancelados}[status_sel]
    if fonte is None or fonte.empty or "SUBTIPO" not in fonte.columns:
        with st.expander("Super Conta", expanded=False):
            st.warning("Nenhum contrato Super Conta no periodo.")
        return

    df_s = _linhas_acelerador(fonte, "Super Conta")

    titulo = f"Super Conta — {len(df_s)} contratos"
    with st.expander(titulo, expanded=False):
        st.caption(
            "Valores tambem computados em CNC (regra de contagem dupla); "
            "isolados aqui para auditoria."
        )
        if df_s.empty:
            st.info(f"Nenhuma Super Conta em '{status_sel}'.")
            return

        df_f = _filtrar_loja_consultor(df_s, "acel_super_conta")
        total_valor = float(df_f["VALOR"].sum()) if "VALOR" in df_f.columns else 0.0
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Quantidade", formatar_numero(len(df_f)))
        with col2:
            st.metric("Valor Total", formatar_moeda(total_valor))

        df_f = df_f.copy()
        df_f["NR_ADE"] = _nr_ade(df_f)
        col_data = "DATA" if status_sel == "Pagas" else "DATA_CADASTRO"
        cols = ["NR_ADE", col_data, "LOJA", "CONSULTOR"]
        if "REGIAO" in df_f.columns:
            cols.append("REGIAO")
        cols += ["TIPO_PRODUTO", "TIPO OPER.", "VALOR", "BANCO"]
        if status_sel != "Pagas" and "STATUS_BANCO" in df_f.columns:
            cols.append("STATUS_BANCO")
        cols_disp = [c for c in cols if c in df_f.columns]

        df_tab = (
            df_f[cols_disp]
            .sort_values(col_data, ascending=False)
            .rename(columns={
                "NR_ADE": "Nº ADE",
                "DATA": "Data Pagamento",
                "DATA_CADASTRO": "Data Cadastro",
                "TIPO_PRODUTO": "Produto",
                "TIPO OPER.": "Tipo Operacao",
                "VALOR": "Valor",
                "STATUS_BANCO": "Status Banco",
                "BANCO": "Banco",
                "LOJA": "Loja",
                "CONSULTOR": "Consultor",
                "REGIAO": "Regiao",
            })
        )
        exibir_tabela(df_tab, colunas_moeda=["Valor"])
        _exportar_csv(
            df_tab, f"acel_super_conta_{status_sel.lower().replace(' ', '_')}",
            f"exp_acel_super_conta_{status_sel}",
        )


def _render_aceleradores(
    df: pd.DataFrame,
    df_analise: pd.DataFrame,
    df_cancelados: pd.DataFrame,
):
    """Sub-aba Aceleradores: BMG Med, Vida Familiar, Emissao, Super Conta."""
    status_sel = sac.segmented(
        items=[
            sac.SegmentedItem(label="Pagas", icon="check-circle"),
            sac.SegmentedItem(label="Em Analise", icon="hourglass-split"),
            sac.SegmentedItem(label="Cancelados", icon="x-circle"),
        ],
        align="start",
        use_container_width=False,
        key="acel_status",
    )

    _render_expander_seguro(
        "BMG Med", "BMG MED", df, df_analise, df_cancelados, status_sel,
    )
    _render_expander_seguro(
        "Vida Familiar", "Seguro", df, df_analise, df_cancelados, status_sel,
    )
    _render_expander_emissao(df, df_analise, df_cancelados, status_sel)
    _render_expander_super_conta(df, df_analise, df_cancelados, status_sel)


def _render_reconquista_por_loja(
    por_loja: pd.DataFrame,
    mes_label: str,
    ref_apuracao_label: str,
) -> None:
    """Quebra por loja no eixo do analitico: fim de relacionamento no
    mes selecionado (`por_loja_mes`), a partir do export do banco.

    Analitico apenas: a conversao daqui e PREVIA da esteira, nao o
    premio (no mes corrente a macica ainda nao virou e EFETIVADA tende
    a 0). A coluna Faixa Premio saiu em 10/2026 — sugeria um premio que
    o export nao decide mais (business-rules.md § "Liga").
    """
    if por_loja.empty:
        st.warning(
            f"Sem leads com fim de relacionamento em {mes_label} no "
            f"escopo atual."
        )
        return

    st.caption(
        f"Fim de relacionamento em **{mes_label}** · clientes indicados "
        f"pelo banco. Conversão aqui é **prévia da esteira**, não a "
        f"apuração."
    )
    cols = [
        "loja", "regiao", "total_clientes", "efetivadas", "promessas",
        "sem_reconquista", "conversao_pct",
        "saldo_medio", "dias_atraso_medio",
    ]
    df_view = por_loja[[c for c in cols if c in por_loja.columns]].rename(
        columns={
            "loja": "Loja",
            "regiao": "Regiao",
            "total_clientes": "Elegíveis",
            "efetivadas": "Efetivadas",
            "promessas": "Promessas",
            "sem_reconquista": "Sem Reconquista",
            "conversao_pct": "Conversão %",
            "saldo_medio": "Saldo Medio",
            "dias_atraso_medio": "Dias Atraso Medio",
        }
    ).sort_values("Efetivadas", ascending=False)
    exibir_tabela(
        df_view,
        colunas_moeda=["Saldo Medio"],
        # "Conversão %" nao casa nenhuma keyword de `_classificar_coluna`
        # (sao "% Ating"/"% Proj"/"Atingimento %"), entao sem a lista
        # explicita a coluna saia crua: 58.800000 em vez de 58,8%.
        colunas_percentual=["Conversão %"],
        colunas_numero=[
            "Elegíveis", "Efetivadas", "Promessas",
            "Sem Reconquista", "Dias Atraso Medio",
        ],
    )
    _exportar_csv(df_view, "reconquista_por_loja", "exp_rec_loja")


def _render_reconquista_detalhamento(
    clientes: pd.DataFrame,
    mes_label: str,
) -> None:
    """Listagem analitica — 1 linha por cliente (co_adesao) + link.

    Recebe a base INTEIRA do export (`clientes_todos`, ja marcada pelo
    loader com `ref_key`/`ref_label` do fim de relacionamento) e lista
    todos os meses, do fim de relacionamento mais recente ao mais
    antigo. O mes selecionado fica destacado e o multiselect "Fim de
    Relacionamento" recorta.

    Ate 09/2026 havia um escopo "mes selecionado" e as colunas
    Apuracao/Vigencia (posicao do lead frente a apuracao defasada). Com
    a liga como apuracao (business-rules.md § "Liga"), o export virou so
    analitico: nao ha mais apuracao a que o lead pertenca, e as duas
    sairam (decisao do usuario, 02/10/2026).

    Filtrar e pandas sobre o frame que ja veio — nao ha fetch novo.
    """
    if clientes is None or clientes.empty:
        st.warning("Sem clientes no escopo atual.")
        return

    # Cobertura da base (mais antiga → mais recente), pelo mes de FIM DE
    # RELACIONAMENTO. O rotulo precisa dizer o que "todos" significa
    # nesta carga, ja que a tabela e truncada e realimentada a cada
    # import.
    rotulos_ref = (
        clientes[["ref_key", "ref_label"]]
        .drop_duplicates()
        .sort_values("ref_key", ascending=False)["ref_label"]
        .tolist()
    )
    cobertura = (
        f"{rotulos_ref[-1]} a {rotulos_ref[0]}"
        if len(rotulos_ref) > 1
        else (rotulos_ref[0] if rotulos_ref else "—")
    )
    base = clientes

    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        status_opts = ["Todos"] + (
            sorted(base["status"].dropna().unique().tolist())
            if "status" in base.columns else []
        )
        filt_status = st.selectbox("Status", status_opts, key="rec_det_status")

    with c2:
        lojas_opts = (
            sorted(base["loja"].dropna().unique().tolist())
            if "loja" in base.columns else []
        )
        filt_lojas = st.multiselect(
            "Loja", lojas_opts, key="rec_det_lojas",
            placeholder="Todas",
        )

    with c3:
        cons_opts = ["Todos"] + (
            sorted(base["consultor"].dropna().unique().tolist())
            if "consultor" in base.columns else []
        )
        filt_cons = st.selectbox("Consultor", cons_opts, key="rec_det_cons")

    with c4:
        eleg_opts = ["Todos"] + (
            sorted(base["flag_elegibilidade"].dropna().unique().tolist())
            if "flag_elegibilidade" in base.columns else []
        )
        filt_eleg = st.selectbox(
            "Elegibilidade", eleg_opts, key="rec_det_eleg"
        )

    with c5:
        filt_ref = st.multiselect(
            "Fim de Relacionamento", rotulos_ref, key="rec_det_ref_mes",
            placeholder="Todos",
        )

    df_f = base.copy()
    if filt_status != "Todos" and "status" in df_f.columns:
        df_f = df_f[df_f["status"] == filt_status]
    if filt_lojas and "loja" in df_f.columns:
        df_f = df_f[df_f["loja"].isin(filt_lojas)]
    if filt_cons != "Todos" and "consultor" in df_f.columns:
        df_f = df_f[df_f["consultor"] == filt_cons]
    if filt_eleg != "Todos" and "flag_elegibilidade" in df_f.columns:
        df_f = df_f[df_f["flag_elegibilidade"] == filt_eleg]
    if filt_ref:
        df_f = df_f[df_f["ref_label"].isin(filt_ref)]
    # Fim de relacionamento mais recente primeiro; dentro do mes a ordem
    # do fetch (co_adesao), para a lista nao "dancar" entre reruns.
    df_f = df_f.sort_values(
        ["ref_key", "co_adesao"], ascending=[False, True]
    )

    st.caption(
        f"{formatar_numero(len(df_f))} de {formatar_numero(len(base))} "
        f"leads (após filtros) · todos os meses de fim de "
        f"relacionamento ({cobertura}) · clientes indicados pelo banco, "
        f"elegíveis ou não. Linhas de {mes_label} destacadas."
    )

    cols = [
        "co_adesao", "ref_label", "status",
        "flag_elegibilidade", "loja", "regiao",
        "consultor", "subproduto",
        "dt_fim_relacionamento", "dt_macica", "dt_dna",
        "banco_origem", "banco_destino", "saldo_contabil", "dias_atraso",
        "faixa_atraso", "tipo_pagamento", "link_aceite",
    ]
    df_view = df_f[[c for c in cols if c in df_f.columns]].rename(
        columns={
            "co_adesao": "Cod ADE",
            "ref_label": "Mês Fim Relac.",
            "status": "Status",
            "flag_elegibilidade": "Elegível",
            "loja": "Loja",
            "regiao": "Regiao",
            "consultor": "Consultor",
            "subproduto": "Subproduto",
            "dt_fim_relacionamento": "Dt Fim Relac.",
            "dt_macica": "Dt Maciça",
            "dt_dna": "Dt DNA",
            "banco_origem": "Banco Origem",
            "banco_destino": "Banco Destino",
            "saldo_contabil": "Saldo",
            "dias_atraso": "Dias Atraso",
            "faixa_atraso": "Faixa Atraso",
            "tipo_pagamento": "Tipo Pgto",
            "link_aceite": "Link Aceite",
        }
    )

    exibir_tabela(
        df_view,
        colunas_moeda=["Saldo"],
        colunas_numero=["Dias Atraso"],
        highlight_mask=(df_f["ref_label"] == mes_label),
        paginacao=100,
        key="rec_det_tabela",
    )
    _exportar_csv(
        df_view,
        "reconquista_clientes_todos_os_meses",
        "exp_rec_clientes",
    )


_LIGA_CONTAB_OPCOES = ["Contabilizadas", "Não contabilizadas", "Todas"]


def _render_reconquista_liga(
    liga: pd.DataFrame,
    liga_status: str,
    mes_label: str,
) -> None:
    """Analitico da liga — a apuracao oficial do banco no mes selecionado.

    Lista as propostas do arquivo da liga com `qtde` 1 (contabilizada,
    entra nos KPIs) e 0 (listada, fora da conta); o filtro abre em
    "Contabilizadas" — decisao do usuario, 02/10/2026: as nao
    contabilizadas ficam a um clique para quem confere com o banco.
    """
    if liga_status == LIGA_FORA:
        st.info(
            "A liga é a apuração da Reconquista a partir de 09/2026. "
            f"Para {mes_label} vale a regra anterior (export do banco, "
            "com defasagem de 1 mês)."
        )
        return
    if liga_status == LIGA_NAO_IMPORTADA:
        st.warning(f"Liga de {mes_label} ainda não importada.")
        return
    if liga_status == LIGA_ERRO:
        st.error(f"Não foi possível carregar a liga de {mes_label}.")
        return
    if liga is None or liga.empty:
        st.warning(f"Sem propostas da liga de {mes_label} no escopo atual.")
        return

    df = liga.copy()
    df["_contab"] = pd.to_numeric(df["qtde"], errors="coerce").eq(1)
    df["contabilizada"] = df["_contab"].map({True: "Sim", False: "Não"})

    c1, c2, c3 = st.columns(3)
    with c1:
        filt_contab = st.selectbox(
            "Contabilizada", _LIGA_CONTAB_OPCOES, key="rec_liga_contab",
        )
    with c2:
        lojas_opts = _opcoes_coluna(df, "loja")
        filt_lojas = st.multiselect(
            "Loja", lojas_opts, key="rec_liga_lojas", placeholder="Todas",
        )
    with c3:
        cons_opts = ["Todos"] + _opcoes_coluna(df, "consultor")
        filt_cons = st.selectbox(
            "Consultor", cons_opts, key="rec_liga_cons",
        )

    df_f = df
    if filt_contab == "Contabilizadas":
        df_f = df_f[df_f["_contab"]]
    elif filt_contab == "Não contabilizadas":
        df_f = df_f[~df_f["_contab"]]
    if filt_lojas:
        df_f = df_f[df_f["loja"].isin(filt_lojas)]
    if filt_cons != "Todos":
        df_f = df_f[df_f["consultor"] == filt_cons]

    n_contab = int(df["_contab"].sum())
    st.caption(
        f"{formatar_numero(len(df_f))} de {formatar_numero(len(df))} "
        f"propostas da liga de **{mes_label}** (após filtros) · "
        f"{formatar_numero(n_contab)} contabilizadas pelo banco — é o "
        f"número das Efetivadas nos KPIs."
    )

    cols = [
        "co_adesao", "contabilizada", "loja", "regiao", "consultor",
        "data_reconquista",
    ]
    df_view = (
        df_f.sort_values(["loja", "consultor", "co_adesao"])
        [[c for c in cols if c in df_f.columns]]
        .rename(columns={
            "co_adesao": "Cod ADE",
            "contabilizada": "Contabilizada",
            "loja": "Loja",
            "regiao": "Regiao",
            "consultor": "Consultor",
            "data_reconquista": "Data Reconquista",
        })
    )
    exibir_tabela(df_view, paginacao=100, key="rec_liga_tabela")
    _exportar_csv(
        df_view,
        f"reconquista_liga_{mes_label.replace('/', '-')}",
        "exp_rec_liga",
    )


# ── Promessa Diaria (V3, >= 09/2026, migration 137) ─────────────────

_PROM_RETORNO_ACEITO = "Aceito"
_PROM_RETORNO_PENDENTE = "Pendente"
_PROM_RETORNO_NAO_ACEITO = "Não aceito"
_PROM_RETORNO_OUTRO = "Outro"
_PROM_ELEG_OPCOES = ["Elegíveis", "Não elegíveis", "Todas"]
_PROM_EFET_OPCOES = ["Todas", "Sim", "Não"]

# Rotulos das quebras (loader: `promessas_por_loja` /
# `promessas_por_consultor`).
_PROM_COLS_QUEBRA = {
    "loja": "Loja",
    "regiao": "Regiao",
    "consultor": "Consultor",
    "promessas": "Promessas",
    "retorno_aceito": "Retorno Aceito",
    "retorno_pendente": "Retorno Pendente",
    "retorno_nao_aceito": "Retorno Não Aceito",
    "fdr_e_promessa": "FDR e Promessa",
    "so_promessa": "Só Promessa",
    "efetivadas": "Já Efetivadas",
}


def _fmt_contagem(valor) -> str:
    """Contagem do `totais` -> texto; None (indisponivel) -> "—"."""
    return "—" if valor is None else formatar_numero(valor)


def _badge_efetivada(efetivada, ref, csv: bool = False) -> str:
    """Badge da coluna Efetivada (fonte unica = liga, `marcar_efetivada`).

    NA = liga nao pode ser lida: "indisponivel", nunca "nao efetivada".
    No CSV o icone vira texto (mesmo criterio do semaforo do
    Prestamista).
    """
    if pd.isna(efetivada):
        return "indisponível"
    if bool(efetivada):
        ref_txt = ref if isinstance(ref, str) and ref else "—"
        return f"Sim ({ref_txt})" if csv else f"✅ {ref_txt}"
    return "Não" if csv else "—"


def _classificar_retorno_promessa(df: pd.DataFrame) -> pd.Series:
    """Retorno INSS em 4 classes, pelo MESMO criterio do card.

    Reusa `_anotar_contadores_promessa` (kpis/reconquista.py) para que o
    filtro bata com os numeros de Aceito/Pendente/Nao aceito: rotulo
    fora dos dois conhecidos vira "Outro" (nao some em silencio).
    """
    anot = _anotar_contadores_promessa(df)
    classe = pd.Series(_PROM_RETORNO_OUTRO, index=df.index, dtype=object)
    classe[anot["_aceito"].eq(1)] = _PROM_RETORNO_ACEITO
    classe[anot["_pendente"].eq(1)] = _PROM_RETORNO_PENDENTE
    classe[anot["_nao_aceito"].eq(1)] = _PROM_RETORNO_NAO_ACEITO
    return classe


def _quebra_promessa_view(quebra: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    """Quebra do loader -> tabela rotulada.

    `efetivadas` vem Int64 com NA quando o badge esta indisponivel:
    nesse caso a coluna vira o texto "indisponivel" (nunca 0). Devolve
    tambem se a coluna ficou numerica (para `colunas_numero`).
    """
    view = quebra.copy()
    efet_numerica = True
    if "efetivadas" in view.columns and view["efetivadas"].isna().any():
        view["efetivadas"] = "indisponível"
        efet_numerica = False
    cols = [c for c in _PROM_COLS_QUEBRA if c in view.columns]
    return view[cols].rename(columns=_PROM_COLS_QUEBRA), efet_numerica


def _tabela_quebra_promessa(
    quebra: pd.DataFrame, nome: str, key: str
) -> None:
    view, efet_numerica = _quebra_promessa_view(quebra)
    cols_num = [
        "Promessas", "Retorno Aceito", "Retorno Pendente",
        "Retorno Não Aceito", "FDR e Promessa", "Só Promessa",
    ]
    if efet_numerica:
        cols_num.append("Já Efetivadas")
    exibir_tabela(
        view,
        colunas_numero=[c for c in cols_num if c in view.columns],
        paginacao=100,
        key=key,
    )
    _exportar_csv(view, nome, f"exp_{key}")


def _render_reconquista_promessa(reconquista: dict) -> None:
    """Sub-aba "Promessa Diaria" — arquivo do banco do mes selecionado.

    Fonte: `carregar_reconquista` (view `v_reconquista_promessa`, ja
    pos-RLS). Periodo = mes de `dt_promessa`, sem defasagem. As
    metricas e as quebras sao do escopo inteiro do perfil; os filtros
    recortam so o detalhe (que abre em "Elegiveis" — as que contam no
    card). Badge "Efetivada" vem so da liga; indisponivel nunca vira
    "nao efetivada". Promessa em nome de supervisor conta e e listada na
    loja, mas fica fora da quebra por consultor.
    """
    totais = reconquista.get("totais") or {}
    status = totais.get("promessa_status", PROMESSA_FORA)
    apur_mes = reconquista.get("apuracao_mes")
    apur_ano = reconquista.get("apuracao_ano")
    mes_label = f"{apur_mes:02d}/{apur_ano}" if apur_mes else "—"

    if status == PROMESSA_FORA:
        st.info(
            "A Promessa Diária é a fonte das Promessas a partir de "
            f"09/2026. Para {mes_label} vale o export do banco."
        )
        return
    if status == PROMESSA_NAO_IMPORTADA:
        st.warning(f"Promessa Diária de {mes_label} ainda não importada.")
        return
    if status == PROMESSA_ERRO:
        st.error(
            f"Não foi possível carregar a Promessa Diária de {mes_label}."
        )
        return

    promessas = reconquista.get("promessas")
    if promessas is None or promessas.empty:
        st.warning(
            f"Sem promessas da Promessa Diária de {mes_label} no escopo "
            "atual."
        )
        return

    # ── Metricas do escopo (mesmos numeros do card) ──
    efet = totais.get("promessas_efetivadas")
    pct = totais.get("pct_retorno_aceito")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric(
            "Promessas elegíveis", _fmt_contagem(totais.get("promessas")),
            help="Linhas elegíveis do arquivo no mês — o número do card.",
        )
    with c2:
        st.metric(
            "Retorno INSS aceito",
            "—" if pct is None else formatar_percentual(pct),
            help=(
                f"{_fmt_contagem(totais.get('retorno_aceito'))} aceitos "
                "sobre as elegíveis."
            ),
        )
    with c3:
        st.metric(
            "Pendentes", _fmt_contagem(totais.get("retorno_pendente")),
            help="Elegíveis com o retorno INSS ainda vazio.",
        )
    with c4:
        st.metric(
            "Já efetivadas",
            "indisponível" if efet is None else formatar_numero(efet),
            help="Elegíveis com a ADE contabilizada na liga.",
        )
    with c5:
        st.metric(
            "Não elegíveis", _fmt_contagem(totais.get("nao_elegiveis")),
            help="Linhas do arquivo fora da conta das Promessas.",
        )

    df = promessas.copy()
    df["_retorno"] = _classificar_retorno_promessa(df)
    df["_elegivel"] = df["elegivel"].eq(True)
    badge_disponivel = (
        "efetivada" in df.columns and not df["efetivada"].isna().any()
    )

    # ── Filtros do detalhe ──
    retorno_opts = [
        "Todos", _PROM_RETORNO_ACEITO, _PROM_RETORNO_PENDENTE,
        _PROM_RETORNO_NAO_ACEITO,
    ]
    if df["_retorno"].eq(_PROM_RETORNO_OUTRO).any():
        retorno_opts.append(_PROM_RETORNO_OUTRO)

    f1, f2, f3 = st.columns(3)
    with f1:
        filt_lojas = st.multiselect(
            "Loja", _opcoes_coluna(df, "loja"), key="rec_prom_lojas",
            placeholder="Todas",
        )
    with f2:
        filt_cons = st.selectbox(
            "Consultor", ["Todos"] + _opcoes_coluna(df, "consultor"),
            key="rec_prom_cons",
        )
    with f3:
        filt_sit = st.selectbox(
            "Situação",
            ["Todas"] + _opcoes_coluna(df, "status_cliente_atual"),
            key="rec_prom_sit",
        )
    f4, f5, f6 = st.columns(3)
    with f4:
        filt_ret = st.selectbox(
            "Retorno INSS", retorno_opts, key="rec_prom_retorno",
        )
    with f5:
        filt_eleg = st.selectbox(
            "Elegibilidade", _PROM_ELEG_OPCOES, key="rec_prom_eleg",
        )
    with f6:
        filt_efet = st.selectbox(
            "Efetivada", _PROM_EFET_OPCOES, key="rec_prom_efet",
            disabled=not badge_disponivel,
            help=(
                None if badge_disponivel else
                "Liga indisponível: não dá para saber quais efetivaram."
            ),
        )

    df_f = df
    if filt_lojas:
        df_f = df_f[df_f["loja"].isin(filt_lojas)]
    if filt_cons != "Todos":
        df_f = df_f[df_f["consultor"] == filt_cons]
    if filt_sit != "Todas":
        df_f = df_f[df_f["status_cliente_atual"] == filt_sit]
    if filt_ret != "Todos":
        df_f = df_f[df_f["_retorno"] == filt_ret]
    if filt_eleg == "Elegíveis":
        df_f = df_f[df_f["_elegivel"]]
    elif filt_eleg == "Não elegíveis":
        df_f = df_f[~df_f["_elegivel"]]
    # Desabilitado (badge indisponivel) o filtro nao recorta, mesmo que
    # o session_state guarde "Sim"/"Nao" de um rerun anterior.
    if badge_disponivel and filt_efet != "Todas":
        df_f = df_f[df_f["efetivada"].eq(filt_efet == "Sim")]

    _outros = totais.get("retorno_outros") or 0
    _outros_txt = (
        f" · retorno INSS fora de Aceito/Não aceito em "
        f"{formatar_numero(_outros)} elegível(is) (filtro \"Outro\")"
        if _outros else ""
    )
    st.caption(
        f"{formatar_numero(len(df_f))} de {formatar_numero(len(df))} "
        f"linhas da Promessa Diária de **{mes_label}** (após filtros) · "
        f"só as elegíveis contam no card{_outros_txt}."
    )

    # ── Detalhe ──
    df_f = df_f.sort_values(
        ["dt_promessa", "loja", "co_adesao"],
        ascending=[False, True, True],
    )
    retorno_txt = df_f["retorno_inss"].where(
        df_f["_retorno"] != _PROM_RETORNO_PENDENTE, _PROM_RETORNO_PENDENTE
    )
    if "efetivada" in df_f.columns:
        efet_col = df_f["efetivada"]
        ref_col = df_f.get(
            "efetivada_ref", pd.Series(None, index=df_f.index)
        )
    else:
        efet_col = pd.Series(pd.NA, index=df_f.index, dtype="boolean")
        ref_col = pd.Series(None, index=df_f.index)
    detalhe = pd.DataFrame({
        "ADE": df_f["co_adesao"],
        "Data Promessa": df_f["dt_promessa"],
        "Data Retorno": df_f["dt_retorno"],
        "Retorno INSS": retorno_txt,
        "Elegibilidade": df_f["flag_elegibilidade"],
        "Situação mês anterior": df_f["status_mes_anterior"],
        "Situação atual": df_f["status_cliente_atual"],
        "Loja": df_f["loja"],
        "Supervisor": df_f["supervisor"],
        "Consultor": df_f["consultor"],
    })
    view = detalhe.assign(Efetivada=[
        _badge_efetivada(e, r) for e, r in zip(efet_col, ref_col)
    ])
    exibir_tabela(view, paginacao=100, key="rec_prom_tabela")
    csv = detalhe.assign(Efetivada=[
        _badge_efetivada(e, r, csv=True) for e, r in zip(efet_col, ref_col)
    ])
    _exportar_csv(
        csv,
        f"reconquista_promessa_{mes_label.replace('/', '-')}",
        "exp_rec_prom",
    )

    # ── Quebras (escopo inteiro, sem os filtros do detalhe) ──
    st.markdown("#### Quebras das promessas elegíveis")
    st.caption(
        "Sobre todas as elegíveis do seu escopo, sem os filtros acima."
    )
    sufixo = mes_label.replace("/", "-")
    aba_loja, aba_cons = st.tabs(["Por Loja", "Por Consultor"])
    with aba_loja:
        por_loja = reconquista.get("promessas_por_loja")
        if por_loja is None or por_loja.empty:
            st.info("Sem promessas elegíveis por loja no seu escopo.")
        else:
            st.caption(
                "Inclui as promessas em nome de supervisor no total da "
                "loja."
            )
            _tabela_quebra_promessa(
                por_loja, f"reconquista_promessa_por_loja_{sufixo}",
                "rec_prom_loja",
            )
    with aba_cons:
        por_cons = reconquista.get("promessas_por_consultor")
        if por_cons is None:
            st.warning(
                "Quebra por consultor indisponível: não foi possível ler "
                "o cadastro de supervisores do período ou identificar os "
                "consultores das promessas."
            )
        elif por_cons.empty:
            st.info("Sem promessas elegíveis por consultor no seu escopo.")
        else:
            st.caption(
                "Promessas em nome de supervisor contam só na loja — "
                "ficam fora desta visão. Promessas sem consultor "
                "identificado no cadastro vão para o supervisor vigente "
                "da loja atuar (linha \"· sem consultor identificado\")."
            )
            _tabela_quebra_promessa(
                por_cons, f"reconquista_promessa_por_consultor_{sufixo}",
                "rec_prom_cons_tab",
            )


def _texto_promessas_caption(totais: dict, ref_label: str) -> str:
    """Trecho "Promessas: ..." do caption do topo de Reconquista.

    Fora da V3 (< 09/2026) e a contagem do export, com o fim de
    relacionamento em `ref_label`. Na V3 e a Promessa Diaria do proprio
    mes; nao importada/erro (ou valor None) vira "—" com o motivo —
    nunca 0 nem o numero do export.
    """
    status = totais.get("promessa_status", PROMESSA_FORA)
    if status == PROMESSA_FORA:
        return (
            f"Promessas: {totais.get('promessas', 0)} "
            f"(fim de relacionamento em {ref_label})"
        )
    if status == PROMESSA_NAO_IMPORTADA:
        return "Promessas: — (Promessa Diária não importada)"
    if status == PROMESSA_ERRO:
        return "Promessas: — (Promessa Diária indisponível)"
    return (
        f"Promessas: {_fmt_contagem(totais.get('promessas'))} elegíveis "
        "(Promessa Diária do mês)"
    )


_CART_PRIORIDADE = "Prioridade"
_CART_BAIXA = "Baixa prioridade"
_CART_TRAB_OPCOES = [
    "Todos", "Não trabalhados", "Prometidos", "Efetivados",
]


def _link_https(serie: pd.Series) -> pd.Series:
    """So `https://` vira link clicavel; o resto fica vazio (defesa contra
    `javascript:`/texto solto no arquivo do banco — migration 140)."""
    txt = serie.fillna("").astype(str).str.strip()
    return txt.where(txt.str.lower().str.startswith("https://"), None)


def _rotulo_prioridade(serie: pd.Series) -> pd.Series:
    return serie.map({False: _CART_PRIORIDADE, True: _CART_BAIXA})


def _badge_trabalhado(prometido, prom_ref, efetivado, efet_ref,
                      csv: bool = False) -> str:
    """Coluna "Trabalhado": efetivado vence prometido. Um "sim" de uma
    fonte vale mesmo com a outra ilegivel; o "nao" so com as duas lidas
    — fonte NA => "indisponível", nunca "não trabalhado"."""
    def _ref(r):
        return r if isinstance(r, str) and r else "—"

    if not pd.isna(efetivado) and bool(efetivado):
        return (f"Efetivado ({_ref(efet_ref)})" if csv
                else f"✅ Efetivado {_ref(efet_ref)}")
    if not pd.isna(prometido) and bool(prometido):
        return (f"Prometido ({_ref(prom_ref)})" if csv
                else f"🤝 Prometido {_ref(prom_ref)}")
    if pd.isna(efetivado) or pd.isna(prometido):
        return "indisponível"
    return "Não" if csv else "—"


def _tabela_quebra_carteira(
    quebra: pd.DataFrame, chave_label: dict, nome: str, key: str
) -> None:
    """Quebra por loja/consultor da Carteira Elegivel (+ CSV).

    Saldo da carteira omitido da tela e do CSV (decisao do usuario,
    16/10/2026) — o loader ainda o calcula, so nao e exibido.
    """
    view = quebra.drop(columns=["saldo"], errors="ignore").rename(columns={
        **chave_label,
        "elegiveis": "Elegíveis",
        "prioridade": "Prioridade",
        "baixa_prioridade": "Baixa Prioridade",
        "fdr_anterior": "FDR Anterior",
        "prometidos": "Já Prometidos",
        "efetivados": "Já Efetivados",
    })
    for col in ("Já Prometidos", "Já Efetivados"):
        if col in view.columns and view[col].isna().all():
            view[col] = "indisponível"
    cols_num = [
        c for c in (
            "Elegíveis", "Prioridade", "Baixa Prioridade", "FDR Anterior",
            "Já Prometidos", "Já Efetivados",
        )
        if c in view.columns and view[c].dtype != object
    ]
    exibir_tabela(
        view,
        colunas_numero=cols_num,
        paginacao=100,
        key=key,
    )
    _exportar_csv(view, nome, f"exp_{key}")


def _tabela_dimensao_carteira(
    dim: pd.DataFrame, coluna: str, rotulo: str, key: str, sufixo: str
) -> None:
    if dim is None or dim.empty:
        st.info("Sem dados no seu escopo.")
        return
    # Saldo omitido (ver `_tabela_quebra_carteira`).
    view = dim.drop(columns=["saldo"], errors="ignore").rename(columns={
        coluna: rotulo, "clientes": "Clientes",
    })
    exibir_tabela(view, colunas_numero=["Clientes"])
    _exportar_csv(view, f"reconquista_carteira_{key}_{sufixo}",
                  f"exp_rec_cart_{key}")


def _render_reconquista_carteira(mes: int, ano: int) -> None:
    """Sub-aba "Carteira Elegivel" — Extrator de Elegiveis do banco.

    Carregada SO aqui (`carregar_carteira_elegivel`, ja pos-RLS): o card
    nao usa a carteira. Foto do mes = lista de trabalho; metricas e
    quebras do escopo inteiro, filtros so no detalhe. Baixa prioridade
    conta como elegivel mas vem depois das prioritarias (decisao do
    usuario). Badges "Prometido"/"Efetivado" cruzam a ADE com a Promessa
    Diaria e a liga dos periodos >= o da carteira; indisponivel nunca
    vira "nao trabalhado". Ver business-rules.md § "Carteira Elegivel".
    """
    mes_label = f"{mes:02d}/{ano}"
    try:
        dados = carregar_carteira_elegivel(mes, ano)
    except Exception:
        # Falha fora dos estados previstos (ex.: RLS) — avisa, nao zera.
        logger.exception("Falha ao montar a Carteira Elegivel")
        dados = {"status": CARTEIRA_ERRO}
    status = dados.get("status", CARTEIRA_ERRO)

    if status == CARTEIRA_FORA:
        st.info(
            "A Carteira Elegível começa em 10/2026 (primeiro Extrator de "
            f"Elegíveis). Para {mes_label} valem Por Loja e Detalhamento "
            "do export."
        )
        return
    if status == CARTEIRA_NAO_IMPORTADA:
        st.warning(f"Carteira Elegível de {mes_label} ainda não importada.")
        return
    if status == CARTEIRA_ERRO:
        st.error(
            f"Não foi possível carregar a Carteira Elegível de {mes_label}."
        )
        return

    carteira = dados.get("carteira")
    if carteira is None or carteira.empty:
        st.warning(
            f"Sem clientes na Carteira Elegível de {mes_label} no escopo "
            "atual."
        )
        return

    t = dados.get("totais") or {}

    # ── Metricas do escopo ──
    # Sem card de saldo da carteira: informacao omitida no dashboard
    # (decisao do usuario, 16/10/2026).
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(
            "Elegíveis", _fmt_contagem(t.get("elegiveis")),
            help="Clientes elegíveis da foto do mês, inclusive os de "
                 "baixa prioridade.",
        )
    with c2:
        st.metric(
            "Prioridade", _fmt_contagem(t.get("prioridade")),
            help="Acionáveis: sem impedimento para operar.",
        )
    with c3:
        st.metric(
            "Baixa prioridade", _fmt_contagem(t.get("baixa_prioridade")),
            help="Elegíveis com impedimento para operar (ação judicial, "
                 "não me perturbe, restrição...). Contam como elegíveis, "
                 "mas ficam no fim da lista.",
        )
    with c4:
        st.metric(
            "FDR anterior", _fmt_contagem(t.get("fdr_anterior")),
            help="Clientes que já tiveram fim de relacionamento antes.",
        )
    prom = t.get("prometidos")
    efet = t.get("efetivados")
    st.caption(
        "Desde a foto: "
        f"**{'indisponível' if prom is None else formatar_numero(prom)}** "
        "já prometido(s) (Promessa Diária) · "
        f"**{'indisponível' if efet is None else formatar_numero(efet)}** "
        "já efetivado(s) (liga) · "
        f"{_fmt_contagem(t.get('sem_consultor'))} sem consultor "
        "identificado no cadastro."
    )

    df = carteira.copy()
    df["_prioridade"] = _rotulo_prioridade(df["baixa_prioridade"])
    badges_ok = all(
        c in df.columns and not df[c].isna().any()
        for c in ("prometido", "efetivado")
    )

    # ── Filtros do detalhe ──
    f1, f2, f3 = st.columns(3)
    with f1:
        filt_lojas = st.multiselect(
            "Loja", _opcoes_coluna(df, "loja"), key="rec_cart_lojas",
            placeholder="Todas",
        )
    with f2:
        filt_cons = st.selectbox(
            "Consultor", ["Todos"] + _opcoes_coluna(df, "consultor"),
            key="rec_cart_cons",
        )
    with f3:
        filt_prio = st.selectbox(
            "Atuação", ["Todas", _CART_PRIORIDADE, _CART_BAIXA],
            key="rec_cart_prio",
        )
    f4, f5, f6 = st.columns(3)
    with f4:
        filt_banco = st.selectbox(
            "Banco de origem",
            ["Todos"] + _opcoes_coluna(df, "banco_origem"),
            key="rec_cart_banco",
        )
    with f5:
        filt_status = st.selectbox(
            "Situação anterior",
            ["Todas"] + _opcoes_coluna(df, "status_cliente_anterior"),
            key="rec_cart_status",
        )
    with f6:
        filt_trab = st.selectbox(
            "Trabalhado", _CART_TRAB_OPCOES, key="rec_cart_trab",
            disabled=not badges_ok,
            help=(
                None if badges_ok else
                "Promessa Diária ou liga indisponível: não dá para saber "
                "quem já foi trabalhado."
            ),
        )

    df_f = df
    if filt_lojas:
        df_f = df_f[df_f["loja"].isin(filt_lojas)]
    if filt_cons != "Todos":
        df_f = df_f[df_f["consultor"] == filt_cons]
    if filt_prio != "Todas":
        df_f = df_f[df_f["_prioridade"] == filt_prio]
    if filt_banco != "Todos":
        df_f = df_f[df_f["banco_origem"] == filt_banco]
    if filt_status != "Todas":
        df_f = df_f[df_f["status_cliente_anterior"] == filt_status]
    # Desabilitado o filtro nao recorta (session_state pode guardar valor
    # de um rerun anterior).
    if badges_ok and filt_trab != "Todos":
        prometido = df_f["prometido"].astype(bool)
        efetivado = df_f["efetivado"].astype(bool)
        if filt_trab == "Não trabalhados":
            df_f = df_f[~prometido & ~efetivado]
        elif filt_trab == "Prometidos":
            df_f = df_f[prometido]
        else:
            df_f = df_f[efetivado]

    st.caption(
        f"{formatar_numero(len(df_f))} de {formatar_numero(len(df))} "
        f"clientes da Carteira Elegível de **{mes_label}** (após filtros) "
        "· prioritários primeiro; baixa prioridade no "
        "fim."
    )

    # ── Detalhe (ordem do loader: prioridade -> saldo, que segue so como
    # criterio de ordem — a coluna nao e exibida) ──
    def _col(nome):
        return df_f.get(nome, pd.Series(pd.NA, index=df_f.index))

    trab = [
        _badge_trabalhado(p, pr, e, er)
        for p, pr, e, er in zip(
            _col("prometido"), _col("prometido_ref"),
            _col("efetivado"), _col("efetivado_ref"),
        )
    ]
    trab_csv = [
        _badge_trabalhado(p, pr, e, er, csv=True)
        for p, pr, e, er in zip(
            _col("prometido"), _col("prometido_ref"),
            _col("efetivado"), _col("efetivado_ref"),
        )
    ]
    detalhe = pd.DataFrame({
        "ADE": df_f["co_adesao"],
        "Atuação": df_f["_prioridade"],
        "Motivo Impedimento": df_f["motivo_impedido_operar"],
        "Loja": df_f["loja"],
        "Supervisor (arquivo)": df_f["supervisor"],
        "Consultor": df_f["consultor"],
        "Banco Origem": df_f["banco_origem"],
        "Banco Destino": df_f["banco_destino"],
        "Regra Pagamento": df_f["regra_pagamento"],
        "Situação Anterior": df_f["status_cliente_anterior"],
    })
    link = _link_https(df_f["link_reconquista"])
    exibir_tabela(
        detalhe.assign(Trabalhado=trab, Jornada=link.to_numpy()),
        column_config={
            "Jornada": st.column_config.LinkColumn(
                "Jornada", display_text="Abrir",
                help="Link da jornada Reconquista Fácil do cliente.",
            ),
        },
        paginacao=100,
        key="rec_cart_tabela",
    )
    sufixo = mes_label.replace("/", "-")
    _exportar_csv(
        detalhe.assign(Trabalhado=trab_csv, Jornada=link.to_numpy()),
        f"reconquista_carteira_elegivel_{sufixo}",
        "exp_rec_cart",
    )

    # ── Quebras (escopo inteiro, sem os filtros do detalhe) ──
    st.markdown("#### Quebras da carteira elegível")
    st.caption("Sobre todos os elegíveis do seu escopo, sem os filtros "
               "acima.")
    aba_loja, aba_cons, aba_banco, aba_regra, aba_motivo = st.tabs([
        "Por Loja", "Por Consultor", "Banco de Origem",
        "Regra de Pagamento", "Motivo de Impedimento",
    ])
    with aba_loja:
        por_loja = dados.get("por_loja")
        if por_loja is None or por_loja.empty:
            st.info("Sem elegíveis por loja no seu escopo.")
        else:
            st.caption(
                "Inclui a carteira em nome de supervisor e a sem consultor "
                "identificado. A loja é a do arquivo, mesmo quando o "
                "consultor está cadastrado em outra loja."
            )
            _tabela_quebra_carteira(
                por_loja, {"loja": "Loja", "regiao": "Regiao"},
                f"reconquista_carteira_por_loja_{sufixo}", "rec_cart_loja",
            )
    with aba_cons:
        por_cons = dados.get("por_consultor")
        if por_cons is None:
            st.warning(
                "Quebra por consultor indisponível: não foi possível ler "
                "o cadastro de supervisores do período ou identificar os "
                "consultores da carteira."
            )
        elif por_cons.empty:
            st.info("Sem elegíveis por consultor no seu escopo.")
        else:
            st.caption(
                "Carteira sem consultor identificado no cadastro e "
                "carteira em nome de supervisor vão para o supervisor "
                "vigente da loja distribuir (linha \"· a distribuir\")."
            )
            _tabela_quebra_carteira(
                por_cons, {"consultor": "Consultor"},
                f"reconquista_carteira_por_consultor_{sufixo}",
                "rec_cart_cons_tab",
            )
    with aba_banco:
        _tabela_dimensao_carteira(
            dados.get("por_banco"), "banco_origem", "Banco de Origem",
            "banco", sufixo,
        )
    with aba_regra:
        _tabela_dimensao_carteira(
            dados.get("por_regra"), "regra_pagamento", "Regra de Pagamento",
            "regra", sufixo,
        )
    with aba_motivo:
        st.caption("Só os clientes de baixa prioridade.")
        _tabela_dimensao_carteira(
            dados.get("por_motivo"), "motivo_impedido_operar",
            "Motivo de Impedimento", "motivo", sufixo,
        )


def _render_reconquista(reconquista: dict | None):
    """Sub-aba Reconquista: liga (apuracao) + export (analitico).

    A partir de 09/2026 os KPIs de Efetivadas sao a LIGA do mes
    selecionado (contagem do banco, sem defasagem) — sub-aba "Liga".
    O export do banco segue como analitico apenas: Por Loja no fim de
    relacionamento do mes selecionado, Detalhamento com todos os meses.
    Antes de 09/2026 o caption do topo descreve a regra antiga
    (apuracao defasada em 1 mes sobre o export). Ver business-rules.md
    § "Liga".

    Promessa V3 (>= 09/2026, `promessa_status != PROMESSA_FORA`): a
    sub-aba "Promessa Diária" entra entre Liga e Por Loja, e o caption
    do topo conta as Promessas pela Promessa Diaria do mes.

    Carteira Elegivel (>= 10/2026, `carteira_elegivel_vigente`): a
    sub-aba "Carteira Elegível" SUBSTITUI Por Loja e Detalhamento — o
    export deixou de ser importado (decisao do usuario, 16/10/2026). Os
    meses anteriores seguem com as sub-abas do export.
    """
    if not reconquista:
        st.info("Sem dados de reconquista para este período.")
        return

    totais = reconquista.get("totais") or {}
    ref_mes = reconquista.get("ref_mes")
    ref_ano = reconquista.get("ref_ano")
    apur_mes = reconquista.get("apuracao_mes")
    apur_ano = reconquista.get("apuracao_ano")
    # Eixo do analitico: fim de relacionamento do mes selecionado. A
    # chave `por_loja` (apuracao defasada) continua no dict, mas nao e o
    # que esta tela mostra.
    por_loja = reconquista.get("por_loja_mes", pd.DataFrame())
    clientes_todos = reconquista.get("clientes_todos", pd.DataFrame())
    liga = reconquista.get("liga", pd.DataFrame())
    liga_status = totais.get("liga_status", LIGA_FORA)
    em_liga = liga_status != LIGA_FORA
    # Promessa V3 (>= 09/2026): sub-aba propria + caption do topo
    # passando a falar da Promessa Diaria. Ausente no dict = legado.
    promessa_status = totais.get("promessa_status", PROMESSA_FORA)
    em_promessa_v3 = promessa_status != PROMESSA_FORA
    # Carteira Elegivel (>= 10/2026): corte por data, sem ler a carteira
    # (ela so e carregada se a sub-aba for aberta).
    em_carteira = bool(apur_mes and apur_ano) and carteira_elegivel_vigente(
        apur_mes, apur_ano
    )

    ref_label = f"{ref_mes:02d}/{ref_ano}" if ref_mes else "—"
    apur_label = f"{apur_mes:02d}/{apur_ano}" if apur_mes else "—"
    if em_liga:
        if liga_status in (LIGA_NAO_IMPORTADA, LIGA_ERRO):
            efet_txt = "liga não disponível"
        else:
            efet_txt = (
                f"{totais.get('efetivadas', 0)} contabilizadas pela liga"
            )
        st.caption(
            f"**KPIs acima** — apuração {apur_label} · Efetivadas: "
            f"{efet_txt} · {_texto_promessas_caption(totais, ref_label)}"
        )
    else:
        _faixa = (totais.get("faixa") or {}).get("rotulo", "—")
        _nao_eleg = int(totais.get("nao_elegivel", 0))
        _nao_eleg_txt = f" ({_nao_eleg} não elegíveis)" if _nao_eleg else ""
        _prom_txt = (
            _texto_promessas_caption(totais, ref_label)
            if em_promessa_v3
            else f"Promessas: {totais.get('promessas', 0)}"
        )
        st.caption(
            f"**KPIs acima** — apuração {apur_label}, com defasagem de "
            f"1 mês: fim de relacionamento em **{ref_label}** · "
            f"{totais.get('total', 0)} elegíveis"
            f"{_nao_eleg_txt} · "
            f"Conversão: **{totais.get('conversao', 0.0):.1f}%** ({_faixa}) · "
            f"Efetivadas: {totais.get('efetivadas', 0)} · "
            f"{_prom_txt} · "
            f"Sem reconquista: {totais.get('sem_reconquista', 0)}"
        )

    # Nada a navegar so quando nao ha liga nem export no escopo do
    # perfil.
    if (
        (clientes_todos is None or clientes_todos.empty)
        and (liga is None or liga.empty)
        and not em_liga
        and not em_promessa_v3
        and not em_carteira
    ):
        return

    # st.pills pelo mesmo motivo do sub-nav de Analiticos (ver
    # render_tab_analiticos): sac.tabs esconde o que nao cabe. O rotulo
    # carrega o recorte de cada sub-aba.
    _periodo_sub = {
        "Liga": apur_label,
        "Promessa Diária": apur_label,
        "Carteira Elegível": apur_label,
        "Por Loja": apur_label,
        "Detalhamento": "todos os meses",
    }
    # "Promessa Diária" so com a V3 vigente. Com a Carteira Elegivel
    # vigente, ela entra e as duas sub-abas do export saem (o export nao e
    # mais importado: Por Loja viria vazia e Detalhamento congelado);
    # antes disso, o inverso. O st.pills descarta valor de session_state
    # fora das options.
    opcoes_sub = [
        r for r in _ICONES_RECONQUISTA
        if (r != "Promessa Diária" or em_promessa_v3)
        and (r != "Carteira Elegível" or em_carteira)
        and (r not in _SUB_EXPORT or not em_carteira)
    ]
    menu = st.pills(
        "Sub-navegacao de Reconquista",
        options=opcoes_sub,
        default=(
            "Liga" if em_liga
            else "Por Loja" if "Por Loja" in opcoes_sub
            else opcoes_sub[0]
        ),
        required=True,
        format_func=lambda r: (
            f":material/{_ICONES_RECONQUISTA[r]}: {r} · {_periodo_sub[r]}"
        ),
        label_visibility="collapsed",
        key="nav_reconquista",
    )

    if menu == "Liga":
        _render_reconquista_liga(liga, liga_status, apur_label)
    elif menu == "Promessa Diária":
        _render_reconquista_promessa(reconquista)
    elif menu == "Carteira Elegível":
        _render_reconquista_carteira(apur_mes, apur_ano)
    elif menu == "Por Loja":
        _render_reconquista_por_loja(por_loja, apur_label, ref_label)
    elif menu == "Detalhamento":
        _render_reconquista_detalhamento(clientes_todos, apur_label)


def _render_cobranca_consignavel(reconquista: dict | None) -> None:
    """Sub-aba: propostas que compõem a Cobrança Consignável do mês.

    Lista os contratos RLS'd já calculados em `carregar_reconquista`
    (mesmo dado usado para a contagem do card do acelerador combinado —
    ver business-rules.md "Cobrança Consignável — critério"), sem novo
    fetch. Vazio tanto fora da vigência (< 08/2026) quanto quando não há
    propostas no período — mesmo tratamento das abas irmãs.
    """
    contratos = (reconquista or {}).get(
        "cobranca_consignavel_contratos", pd.DataFrame()
    )
    if contratos is None or contratos.empty:
        st.info("Nenhuma proposta de Cobrança Consignável no período.")
        return

    df_f = _filtrar_loja_consultor(contratos, "cobr_consig")

    total_valor = (
        float(df_f["VALOR"].sum()) if "VALOR" in df_f.columns else 0.0
    )
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Quantidade", formatar_numero(len(df_f)))
    with col2:
        st.metric("Valor Considerado", formatar_moeda(total_valor))

    df_f = df_f.copy()
    df_f["NR_ADE"] = _nr_ade(df_f)
    cols = ["NR_ADE", "DATA", "LOJA", "CONSULTOR"]
    if "REGIAO" in df_f.columns:
        cols.append("REGIAO")
    # Base -> Bruto -> Considerado conta a historia da regra ("era X, a
    # venda cheia foi Y, entrou Y na producao") e deixa visivel o
    # GREATEST da migration 067 quando o bruto vem menor que a base
    # (Considerado = Base).
    # TIPO OPER. separa Contrato Novo de Refinanciamento: desde a
    # migration 130 as tabelas dedicadas do banco trazem REFIN, que
    # produz no VLR BASE (Considerado = Base mesmo com Bruto maior).
    cols += ["TIPO OPER.", "BANCO", "VALOR_BASE", "VALOR_BRUTO", "VALOR"]
    cols_disp = [c for c in cols if c in df_f.columns]

    df_tab = (
        df_f[cols_disp]
        .sort_values("DATA", ascending=False)
        .rename(columns={
            "NR_ADE": "Nº ADE",
            "DATA": "Data Pagamento",
            "LOJA": "Loja",
            "CONSULTOR": "Consultor",
            "REGIAO": "Regiao",
            "TIPO OPER.": "Tipo Operacao",
            "BANCO": "Banco",
            "VALOR_BASE": "Valor Base",
            "VALOR_BRUTO": "Valor Bruto",
            "VALOR": "Valor Considerado",
        })
    )
    exibir_tabela(
        df_tab,
        colunas_moeda=["Valor Base", "Valor Bruto", "Valor Considerado"],
        paginacao=100,
        key="tab_cobr_consignavel",
    )
    _exportar_csv(
        df_tab, "cobranca_consignavel", "exp_cobr_consignavel"
    )


# Seletor de banco da Distribuicao de Produtos.
#
# Chave NOVA de proposito: a antiga ``dist_prod_bmg_help`` guardava
# ``bool`` (era um ``st.toggle``). Reusar o mesmo nome num selectbox
# quebraria toda sessao ja aberta, que carrega o bool em session_state.
_KEY_BANCO_DIST = "dist_prod_banco"

# Preset composto — nao e um banco, e o par que a regra de
# comissionamento de CLT/Consignado trata junto (ver
# ``docs/agents/business-rules.md`` § 'Flag "Somente BMG/Help"'). Fica
# na lista ao lado dos bancos atomicos porque era o unico recorte
# disponivel ate aqui: tirar seria regressao para quem ja usa.
_OPCAO_BMG_HELP = "BMG/Help"


# ══════════════════════════════════════════════════════
# Prestamista CNC (IPV) — migration 134
# ══════════════════════════════════════════════════════

_COLS_PRESTAMISTA = {
    "ade": "Nº ADE",
    "situacao": "Situação",
    "status_apolice": "Status Apólice",
    "REGIAO": "Regiao",
    "LOJA": "Loja",
    "CONSULTOR": "Consultor",
    "TIPO_PRODUTO": "Produto",
    "SUBTIPO": "Subproduto",
    "DATA": "Data Pagamento",
    "VALOR": "Valor",
}


def _prestamista_com_contrato(
    propostas: pd.DataFrame, df_pagos: pd.DataFrame
) -> pd.DataFrame:
    """Propostas do arquivo + produto/valor/data do contrato pago.

    Loja/consultor/regiao vem do ARQUIVO (e a atribuicao do IPV); da
    nossa base so entram os dados do contrato. ADE sem contrato pago no
    periodo fica com essas colunas vazias.
    """
    base = com_situacao(propostas).rename(columns={
        "regiao": "REGIAO", "loja": "LOJA", "consultor": "CONSULTOR",
    })
    if df_pagos is None or df_pagos.empty:
        return base
    contrato = df_pagos.copy()
    contrato["ade"] = _nr_ade(contrato).astype(str).str.strip()
    cols = [c for c in ("TIPO_PRODUTO", "SUBTIPO", "DATA", "VALOR")
            if c in contrato.columns]
    contrato = contrato.drop_duplicates("ade")[["ade", *cols]]
    return base.merge(contrato, on="ade", how="left")


def _tabela_prestamista(df: pd.DataFrame, nome: str, key: str) -> None:
    cols = [c for c in _COLS_PRESTAMISTA if c in df.columns]
    view = df[cols].rename(columns=_COLS_PRESTAMISTA)
    exibir_tabela(view, colunas_moeda=["Valor"], paginacao=100, key=key)
    _exportar_csv(view, nome, f"exp_{key}")


def _filtros_prestamista(base: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Linha de filtros acima das abas: Loja, Consultor e Nº ADE.

    Vale para todas as abas — a contagem de cada uma acompanha o filtro,
    entao buscar uma ADE mostra em que situacao ela esta. A busca segue
    a semantica da busca geral (`_render_busca_ade`): trecho do numero.
    Devolve o frame filtrado e o texto buscado (vazio se nao houve busca).
    """
    col1, col2, col3 = st.columns(3)
    with col1:
        lojas = ["Todas"] + sorted(base["LOJA"].dropna().unique().tolist())
        filt_loja = st.selectbox("Loja", lojas, key="anl_prest_loja")
    with col2:
        cons = ["Todos"] + sorted(base["CONSULTOR"].dropna().unique().tolist())
        filt_cons = st.selectbox("Consultor", cons, key="anl_prest_cons")
    with col3:
        busca = st.text_input(
            "Nº ADE",
            placeholder="Digite o número ADE e pressione Enter...",
            key="anl_prest_busca_input",
        ).strip()
    out = base
    if filt_loja != "Todas":
        out = out[out["LOJA"] == filt_loja]
    if filt_cons != "Todos":
        out = out[out["CONSULTOR"] == filt_cons]
    if busca:
        out = out[out["ade"].astype(str).str.contains(busca, case=False, na=False)]
    return out, busca


# Abas da sub-aba Prestamista, na ordem de acao: (situacao, legenda,
# nome do CSV, key). A pendencia acionavel vem primeiro.
_ABAS_SITUACAO = [
    (
        SITUACAO_SEM_SEGURO,
        "Elegíveis ao Prestamista, sem seguro e sem apólice digitada — "
        "a pendência: cada uma conta contra o IPV.",
        "prestamista_elegiveis_sem_seguro",
        "anl_prest_pend",
    ),
    (
        SITUACAO_ELEGIVEL,
        "Elegíveis com o seguro já digitado (Status Apólice preenchido, "
        "ex.: Aguardando Envio de Arrecadação). Só entram no IPV quando "
        "o banco efetivar o seguro.",
        "prestamista_seguro_digitado",
        "anl_prest_digitado",
    ),
    (
        SITUACAO_COM_SEGURO,
        "Seguro efetivado — o numerador do IPV.",
        "prestamista_com_seguro",
        "anl_prest_com_seguro",
    ),
    (
        SITUACAO_NAO_ELEGIVEL,
        "Propostas que o banco não marcou como elegíveis — fora do IPV.",
        "prestamista_nao_elegiveis",
        "anl_prest_nao_elegivel",
    ),
]


def _render_prestamista(
    prestamista: dict | None, df_pagos: pd.DataFrame, perfil: str
) -> None:
    """Sub-aba Prestamista: propostas por situacao, quebras e o arquivo.

    Escopo do BI do banco: CNC + Super Conta (produto CNC no banco).
    Recorte por perfil ja aplicado no loader.
    """
    if not prestamista:
        st.info("Prestamista CNC indisponível.")
        return
    status = prestamista.get("status")
    if status == PRESTAMISTA_ERRO:
        st.error("Não foi possível carregar o Prestamista CNC do período.")
        return
    if status == PRESTAMISTA_NAO_IMPORTADO:
        st.info("Arquivo do Prestamista CNC do período ainda não importado.")
        return

    propostas = prestamista.get("propostas")
    if propostas is None or propostas.empty:
        st.info("Sem propostas de Prestamista CNC no seu escopo.")
        return

    st.caption(
        "Fonte: BI do banco (Prst CNC — inclui Super Conta). "
        "IPV = seguros ativos / propostas elegíveis."
    )
    tot = totais_prestamista(propostas)
    base = _prestamista_com_contrato(propostas, df_pagos)
    n_situacao = base["situacao"].value_counts()

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        ipv = tot["ipv"]
        st.metric("IPV", "—" if ipv is None else formatar_percentual(ipv * 100))
    with col2:
        st.metric("Elegíveis", formatar_numero(tot["elegiveis"]))
    with col3:
        st.metric("Com seguro", formatar_numero(tot["seguros"]))
    with col4:
        st.metric(
            "Seguro digitado",
            formatar_numero(int(n_situacao.get(SITUACAO_ELEGIVEL, 0))),
        )
    with col5:
        st.metric(
            "Elegíveis sem seguro",
            formatar_numero(int(n_situacao.get(SITUACAO_SEM_SEGURO, 0))),
        )

    st.markdown("#### 📋 Propostas por situação")
    filtrado, busca = _filtros_prestamista(base)
    if busca and filtrado.empty:
        st.warning(f"Nenhuma proposta do Prestamista com ADE '{busca}'.")
    filtros_ativos = len(filtrado) < len(base)
    por_situacao = {
        sit: filtrado[filtrado["situacao"] == sit]
        for sit, *_ in _ABAS_SITUACAO
    }
    abas = st.tabs([
        f"{sit} ({formatar_numero(len(por_situacao[sit]))})"
        for sit, *_ in _ABAS_SITUACAO
    ])
    for aba, (sit, legenda, nome, key) in zip(abas, _ABAS_SITUACAO):
        with aba:
            st.caption(legenda)
            df_sit = por_situacao[sit]
            if df_sit.empty:
                if filtros_ativos:
                    st.info("Nenhuma proposta nesta situação com esses filtros.")
                elif sit == SITUACAO_SEM_SEGURO:
                    st.success(
                        "Nenhuma proposta elegível sem seguro no seu escopo."
                    )
                else:
                    st.info("Nenhuma proposta nesta situação no seu escopo.")
                continue
            _tabela_prestamista(df_sit, nome, key)

    if perfil in ("admin", "gestor", "gerente_comercial", "supervisor"):
        st.markdown("#### 📊 IPV por nível")
        render_quebras_prestamista(
            propostas, prestamista.get("meta"), perfil,
            key_prefix="anl_prestamista", exportar=True,
        )

    with st.expander(f"Todas as propostas do arquivo ({len(base)})"):
        situacoes = [sit for sit, *_ in _ABAS_SITUACAO]
        sel = st.multiselect(
            "Situação", situacoes, default=situacoes,
            key="anl_prest_situacao",
        )
        todas = _filtrar_loja_consultor(
            base[base["situacao"].isin(sel)], "anl_prest_todas"
        )
        _tabela_prestamista(todas, "prestamista_cnc", "anl_prest_todas")


def _selecionar_banco(df) -> tuple[str, ...] | None:
    """Selectbox de banco da Distribuicao de Produtos.

    Devolve a tupla de bancos canonicos a recortar, ou ``None`` para
    "Todos" (sem recorte nenhum — nem precisa da coluna ``BANCO``).

    As opcoes saem do proprio ``df`` ja recortado por perfil/sidebar,
    entao cada perfil so enxerga os bancos do seu escopo. Sao valores
    **canonicos** (``opcoes_banco``): "BMG" e "BANCO BMG" viram uma
    opcao so, em vez de duas linhas partindo o mesmo banco ao meio.

    O escopo do recorte e local a esta sub-aba (chave propria) — nao
    afeta nenhuma outra aba do dashboard.
    """
    opcoes = ["Todos", _OPCAO_BMG_HELP] + opcoes_banco(df)
    # Cascata: trocar mes/loja na sidebar pode tirar da base o banco que
    # estava selecionado. Reseta antes de instanciar o widget (depois
    # disso o session_state e imutavel no mesmo rerun) — mesmo padrao do
    # Subproduto em ``_filtrar_detalhamento``.
    if st.session_state.get(_KEY_BANCO_DIST) not in opcoes:
        st.session_state[_KEY_BANCO_DIST] = "Todos"

    col_banco, _ = st.columns([1, 3])
    with col_banco:
        sel = st.selectbox(
            "Banco",
            opcoes,
            key=_KEY_BANCO_DIST,
            help=(
                "Recorta toda a tabela — valor e quantidade — ao banco "
                "escolhido. 'BMG/Help' mantem o par usado pela regra de "
                "CLT/Consignado."
            ),
        )

    if sel == "Todos":
        return None
    if sel == _OPCAO_BMG_HELP:
        return BANCOS_BMG_HELP
    return (sel,)


def _render_distribuicao_por_loja(
    df, bancos: tuple[str, ...] | None = None,
) -> None:
    """Distribuicao agregada por LOJA (inclui producao de supervisor)."""
    df_dist, cols_moeda, cols_num = calcular_distribuicao_produtos_por_loja(
        df, bancos=bancos,
    )
    if df_dist.empty:
        st.warning("Dados nao disponiveis")
        return

    st.info("Distribuicao de valor (R$) e aceleradores (Qtd) por loja")
    st.caption(
        "Inclui a producao do proprio supervisor no total da loja — "
        "a visao por consultor a exclui."
    )
    exibir_tabela(
        df_dist,
        colunas_moeda=cols_moeda,
        colunas_numero=cols_num,
        paginacao=100,
        key="tab_dist_prod_loja",
    )
    _exportar_csv(
        df_dist, "distribuicao_produtos_loja",
        "exp_dist_prod_loja",
    )


def _render_distribuicao_por_consultor(
    df, df_sup, key_tabela: str, com_busca: bool,
    bancos: tuple[str, ...] | None = None,
) -> None:
    """Distribuicao por CONSULTOR (supervisores excluidos).

    ``com_busca`` revela um selectbox de consultor **local** a esta
    sub-aba (key propria) — nao e o filtro global da sidebar, entao
    selecionar aqui nao afeta nenhuma outra aba. A busca so recorta o
    que aparece na tela: o CSV continua exportando o dataset completo.
    """
    df_dist, cols_moeda, cols_num = calcular_distribuicao_produtos(
        df, df_sup, bancos=bancos,
    )
    if df_dist.empty:
        st.warning("Dados nao disponiveis")
        return

    st.info("Distribuicao de valor (R$) e aceleradores (Qtd) por consultor")

    df_exib = df_dist
    if com_busca and "CONSULTOR" in df_dist.columns:
        consultores = ["Todos"] + sorted(
            df_dist["CONSULTOR"].unique().tolist()
        )
        filt_cons = st.selectbox(
            "Consultor", consultores, key="dist_prod_busca_cons",
        )
        if filt_cons != "Todos":
            df_exib = df_dist[df_dist["CONSULTOR"] == filt_cons]

    exibir_tabela(
        df_exib,
        colunas_moeda=cols_moeda,
        colunas_numero=cols_num,
        paginacao=100,
        key=key_tabela,
    )
    _exportar_csv(
        df_dist, "distribuicao_produtos",
        "exp_dist_prod",
    )


def _render_distribuicao_produtos(df, df_sup, perfil: str) -> None:
    """Sub-aba: distribuicao de produtos, com visao por perfil.

    Supervisor ve sempre a tabela por consultor — o escopo dele e uma
    loja so, entao a agregacao por loja renderia uma unica linha. Os
    demais perfis (admin/gestor/gerente_comercial) abrem na visao por
    loja e alternam para a de consultor pelo toggle.
    """
    bancos = _selecionar_banco(df)

    if perfil == "supervisor":
        _render_distribuicao_por_consultor(
            df, df_sup, "tab_dist_prod_sup_cons", com_busca=False,
            bancos=bancos,
        )
        return

    ver_consultor = st.toggle(
        "Ver por Consultor",
        key="dist_prod_ver_consultor",
        help=(
            "Desligado: distribuicao agregada por loja. Ligado: detalhe "
            "por consultor, com busca."
        ),
    )
    if ver_consultor:
        _render_distribuicao_por_consultor(
            df, df_sup, "tab_dist_prod_cons", com_busca=True,
            bancos=bancos,
        )
    else:
        _render_distribuicao_por_loja(df, bancos=bancos)


def render_tab_analiticos(
    df, df_sup, df_analise, df_cancelados, perfil: str = "",
    reconquista: dict | None = None,
    prestamista: dict | None = None,
):
    """Renderiza aba de Analiticos."""
    sac.divider(
        label="Analiticos Detalhados",
        icon="bar-chart-fill",
        align="left",
        color="blue",
    )

    _render_busca_ade(df, df_analise, df_cancelados)

    _is_consultor = perfil == "consultor"

    # Sub-navegacao em st.pills (nao sac.tabs) pelo mesmo motivo da nav
    # principal em app.py: o sac roda em iframe e o CSS empacotado na lib
    # tem `.ant-tabs-nav-more{display:none}`, entao as abas que nao cabem
    # na largura ficam INACESSIVEIS, nao apenas cortadas — e CSS do
    # documento pai nao atravessa o iframe. Com 7 itens de rotulo longo
    # (a partir de "Cobranca Consignavel") isso passou a acontecer em
    # telas menores, escondendo "Distribuicao de Produtos", o ultimo da
    # lista. O button group do st.pills tem flex-wrap: quebra em linhas.
    # `required=True` impede desselecionar e cair sem nenhuma sub-aba.
    opcoes = [
        "Propostas Pagas",
        "Em Analise",
        "Cancelados",
        "Aceleradores",
        "Reconquista",
        "Cobranca Consignavel",
        "Prestamista",
    ]
    if not _is_consultor:
        opcoes.append("Distribuicao de Produtos")

    menu = st.pills(
        "Sub-navegacao de Analiticos",
        options=opcoes,
        default=opcoes[0],
        required=True,
        format_func=lambda r: f":material/{_ICONES_ANALITICOS[r]}: {r}",
        label_visibility="collapsed",
        key="nav_analiticos",
    )

    if menu == "Propostas Pagas":
        _render_detalhamento_pagos(df, df_sup, prestamista)

    elif menu == "Em Analise":
        _render_detalhamento_em_analise(df_analise)

    elif menu == "Cancelados":
        _render_detalhamento_cancelados(df_cancelados)
        _render_oportunidades_perdidas(df_cancelados, perfil)
        _render_assertividade_consultores(
            df, df_analise, df_cancelados, df_sup
        )

    elif menu == "Aceleradores":
        _render_aceleradores(df, df_analise, df_cancelados)

    elif menu == "Reconquista":
        _render_reconquista(reconquista)

    elif menu == "Cobranca Consignavel":
        _render_cobranca_consignavel(reconquista)

    elif menu == "Prestamista":
        _render_prestamista(prestamista, df, perfil)

    elif menu == "Distribuicao de Produtos":
        _render_distribuicao_produtos(df, df_sup, perfil)
