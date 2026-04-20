"""
Aba Analiticos: detalhamento de contratos (pagos/em analise/
cancelados), consultores por produto, producao por regiao e
distribuicao de produtos.
"""

import pandas as pd
import streamlit as st
import streamlit_antd_components as sac

from src.dashboard.components.tables import exibir_tabela
from src.dashboard.formatters import formatar_moeda, formatar_numero
from src.dashboard.kpis.evolucao import calcular_analitico_consultores
from src.dashboard.kpis.produtos import calcular_distribuicao_produtos
from src.dashboard.kpis.regioes import calcular_media_producao_regiao
from src.dashboard.ui.charts import criar_grafico_media_regiao
from src.dashboard.ui.header import chart_card_close, chart_card_open


def _exportar_csv(df: pd.DataFrame, nome: str, key: str):
    """Botao de download CSV para uma tabela."""
    csv = df.to_csv(index=False, sep=";", decimal=",")
    st.download_button(
        label=f"Exportar {nome}",
        data=csv,
        file_name=f"{nome}.csv",
        mime="text/csv",
        key=key,
        icon=":material/download:",
    )


def _render_detalhamento_pagos(df, df_sup):
    """Sub-aba: detalhamento de contratos pagos."""
    if df.empty:
        st.warning("Nenhum contrato pago no periodo.")
        return

    st.markdown(f"**{len(df):,} contratos pagos**".replace(",", "."))

    # Filtros
    col1, col2, col3 = st.columns(3)
    with col1:
        lojas = ["Todas"] + sorted(df["LOJA"].unique().tolist())
        filt_loja = st.selectbox("Loja", lojas, key="det_pago_loja")
    with col2:
        consultores = ["Todos"] + sorted(
            df["CONSULTOR"].unique().tolist()
        )
        filt_cons = st.selectbox(
            "Consultor", consultores, key="det_pago_cons"
        )
    with col3:
        produtos = ["Todos"]
        if "grupo_dashboard" in df.columns:
            produtos += sorted(
                [
                    str(x) for x in df["grupo_dashboard"].unique()
                    if pd.notna(x)
                ]
            )
        filt_prod = st.selectbox(
            "Produto", produtos, key="det_pago_prod"
        )

    df_d = df.copy()
    if filt_loja != "Todas":
        df_d = df_d[df_d["LOJA"] == filt_loja]
    if filt_cons != "Todos":
        df_d = df_d[df_d["CONSULTOR"] == filt_cons]
    if filt_prod != "Todos" and "grupo_dashboard" in df_d.columns:
        df_d = df_d[df_d["grupo_dashboard"] == filt_prod]

    # KPIs
    total_valor = df_d["VALOR"].sum()
    total_pts = df_d["pontos"].sum() if "pontos" in df_d.columns else 0
    total_trans = len(df_d[df_d["VALOR"] > 0])
    tk = total_valor / total_trans if total_trans > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total de Valor", formatar_moeda(total_valor))
    with col2:
        st.metric("Total de Pontos", formatar_numero(total_pts))
    with col3:
        st.metric("Ticket Medio", formatar_moeda(tk))
    with col4:
        st.metric("Quantidade", formatar_numero(len(df_d)))

    # Tabela detalhada
    cols = ["CONTRATO_ID", "DATA", "LOJA", "CONSULTOR"]
    if "REGIAO" in df_d.columns:
        cols.append("REGIAO")
    cols += ["TIPO_PRODUTO", "TIPO OPER.", "VALOR"]
    if "pontos" in df_d.columns:
        cols.append("pontos")
    cols.append("BANCO")

    cols_disp = [c for c in cols if c in df_d.columns]
    df_tabela = (
        df_d[cols_disp]
        .sort_values("DATA", ascending=False)
        .rename(columns={
            "CONTRATO_ID": "Nº Proposta",
            "DATA": "Data Pagamento",
            "TIPO_PRODUTO": "Produto",
            "TIPO OPER.": "Tipo Operacao",
            "VALOR": "Valor",
            "pontos": "Pontos",
            "BANCO": "Banco",
            "LOJA": "Loja",
            "CONSULTOR": "Consultor",
            "REGIAO": "Regiao",
        })
    )
    exibir_tabela(
        df_tabela,
        colunas_moeda=["Valor"],
        colunas_numero=["Pontos"],
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

    # Filtros
    col1, col2, col3 = st.columns(3)
    with col1:
        lojas = ["Todas"] + sorted(
            df_analise["LOJA"].unique().tolist()
        )
        filt_loja = st.selectbox(
            "Loja", lojas, key="det_analise_loja"
        )
    with col2:
        consultores = ["Todos"] + sorted(
            df_analise["CONSULTOR"].unique().tolist()
        )
        filt_cons = st.selectbox(
            "Consultor", consultores, key="det_analise_cons"
        )
    with col3:
        produtos = ["Todos"]
        if "grupo_dashboard" in df_analise.columns:
            produtos += sorted(
                [
                    str(x)
                    for x in df_analise["grupo_dashboard"].unique()
                    if pd.notna(x)
                ]
            )
        filt_prod = st.selectbox(
            "Produto", produtos, key="det_analise_prod"
        )

    df_d = df_analise.copy()
    if filt_loja != "Todas":
        df_d = df_d[df_d["LOJA"] == filt_loja]
    if filt_cons != "Todos":
        df_d = df_d[df_d["CONSULTOR"] == filt_cons]
    if filt_prod != "Todos" and "grupo_dashboard" in df_d.columns:
        df_d = df_d[df_d["grupo_dashboard"] == filt_prod]

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
    cols = ["CONTRATO_ID", "DATA_CADASTRO", "LOJA", "CONSULTOR"]
    if "REGIAO" in df_d.columns:
        cols.append("REGIAO")
    cols += [
        "TIPO_PRODUTO", "TIPO OPER.", "VALOR",
        "STATUS_BANCO", "BANCO",
    ]

    cols_disp = [c for c in cols if c in df_d.columns]
    df_tabela = (
        df_d[cols_disp]
        .sort_values("DATA_CADASTRO", ascending=False)
        .rename(columns={
            "CONTRATO_ID": "Nº Proposta",
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
    exibir_tabela(df_tabela, colunas_moeda=["Valor"])
    _exportar_csv(
        df_tabela, "contratos_em_analise", "exp_analise"
    )


def _render_detalhamento_cancelados(df_cancel):
    """Sub-aba: detalhamento de contratos cancelados."""
    if df_cancel.empty:
        st.warning("Nenhum contrato cancelado no periodo.")
        return

    st.markdown(
        f"**{len(df_cancel):,} contratos cancelados**"
        .replace(",", ".")
    )

    # Filtros
    col1, col2, col3 = st.columns(3)
    with col1:
        lojas = ["Todas"] + sorted(
            df_cancel["LOJA"].unique().tolist()
        )
        filt_loja = st.selectbox(
            "Loja", lojas, key="det_cancel_loja"
        )
    with col2:
        consultores = ["Todos"] + sorted(
            df_cancel["CONSULTOR"].unique().tolist()
        )
        filt_cons = st.selectbox(
            "Consultor", consultores, key="det_cancel_cons"
        )
    with col3:
        produtos = ["Todos"]
        if "grupo_dashboard" in df_cancel.columns:
            produtos += sorted(
                [
                    str(x)
                    for x in df_cancel["grupo_dashboard"].unique()
                    if pd.notna(x)
                ]
            )
        filt_prod = st.selectbox(
            "Produto", produtos, key="det_cancel_prod"
        )

    df_d = df_cancel.copy()
    if filt_loja != "Todas":
        df_d = df_d[df_d["LOJA"] == filt_loja]
    if filt_cons != "Todos":
        df_d = df_d[df_d["CONSULTOR"] == filt_cons]
    if filt_prod != "Todos" and "grupo_dashboard" in df_d.columns:
        df_d = df_d[df_d["grupo_dashboard"] == filt_prod]

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
    cols = ["CONTRATO_ID", "DATA_CADASTRO", "LOJA", "CONSULTOR"]
    if "REGIAO" in df_d.columns:
        cols.append("REGIAO")
    cols += [
        "TIPO_PRODUTO", "TIPO OPER.", "VALOR",
        "SUB_STATUS", "STATUS_PAG", "BANCO",
    ]

    cols_disp = [c for c in cols if c in df_d.columns]
    df_tabela = (
        df_d[cols_disp]
        .sort_values("DATA_CADASTRO", ascending=False)
        .rename(columns={
            "CONTRATO_ID": "Nº Proposta",
            "DATA_CADASTRO": "Data Cadastro",
            "TIPO_PRODUTO": "Produto",
            "TIPO OPER.": "Tipo Operacao",
            "VALOR": "Valor",
            "SUB_STATUS": "Sub-Status",
            "STATUS_PAG": "Status Pagamento",
            "BANCO": "Banco",
            "LOJA": "Loja",
            "CONSULTOR": "Consultor",
            "REGIAO": "Regiao",
        })
    )
    exibir_tabela(df_tabela, colunas_moeda=["Valor"])
    _exportar_csv(
        df_tabela, "contratos_cancelados", "exp_cancel"
    )


def render_tab_analiticos(
    df, df_sup, df_analise, df_cancelados,
):
    """Renderiza aba de Analiticos."""
    sac.divider(
        label="Analiticos Detalhados",
        icon="bar-chart-fill",
        align="left",
        color="blue",
    )

    menu = sac.tabs(
        items=[
            sac.TabsItem(
                label="Propostas Pagas",
                icon="check-circle",
            ),
            sac.TabsItem(
                label="Em Analise",
                icon="hourglass-split",
            ),
            sac.TabsItem(
                label="Cancelados",
                icon="x-circle",
            ),
            sac.TabsItem(
                label="Consultores por Produto",
                icon="people",
            ),
            sac.TabsItem(
                label="Producao por Regiao",
                icon="geo-alt",
            ),
            sac.TabsItem(
                label="Distribuicao de Produtos",
                icon="pie-chart",
            ),
        ],
        align="start",
        variant="outline",
    )

    if menu == "Propostas Pagas":
        _render_detalhamento_pagos(df, df_sup)

    elif menu == "Em Analise":
        _render_detalhamento_em_analise(df_analise)

    elif menu == "Cancelados":
        _render_detalhamento_cancelados(df_cancelados)

    elif menu == "Consultores por Produto":
        df_a = calcular_analitico_consultores(df, df_sup)
        if not df_a.empty:
            st.info(f"Total de {df_a['Consultor'].nunique()} consultores analisados")

            col1, col2 = st.columns(2)
            with col1:
                opts_c = ["Todos"] + sorted(df_a["Consultor"].unique().tolist())
                filt_c = st.selectbox("Filtrar por Consultor", opts_c)
            with col2:
                opts_p = ["Todos"] + sorted(df_a["Produto"].unique().tolist())
                filt_p = st.selectbox("Filtrar por Produto", opts_p)

            df_af = df_a.copy()
            if filt_c != "Todos":
                df_af = df_af[df_af["Consultor"] == filt_c]
            if filt_p != "Todos":
                df_af = df_af[df_af["Produto"] == filt_p]

            exibir_tabela(df_af)
            _exportar_csv(
                df_af, "consultores_por_produto",
                "exp_cons_prod",
            )

            # Cards resumo: usar df original (mesma base dos KPIs
            # principais) para manter consistencia, aplicando apenas
            # os filtros de consultor/produto selecionados pelo usuario
            mask_cards = df["VALOR"] > 0
            if "is_bmg_med" in df.columns:
                mask_cards = mask_cards | df["is_bmg_med"]
            if "is_seguro_vida" in df.columns:
                mask_cards = mask_cards | df["is_seguro_vida"]
            df_cards = df[mask_cards].copy()
            df_cards["PRODUTO_MIX"] = df_cards[
                "grupo_dashboard"
            ].fillna("OUTROS")
            if "is_bmg_med" in df_cards.columns:
                df_cards.loc[
                    df_cards["is_bmg_med"], "PRODUTO_MIX"
                ] = "BMG Med"
            if "is_seguro_vida" in df_cards.columns:
                df_cards.loc[
                    df_cards["is_seguro_vida"], "PRODUTO_MIX"
                ] = "Vida Familiar"
            if filt_c != "Todos":
                df_cards = df_cards[df_cards["CONSULTOR"] == filt_c]
            if filt_p != "Todos":
                df_cards = df_cards[df_cards["PRODUTO_MIX"] == filt_p]

            total_valor = df_cards["VALOR"].sum()
            total_pts = df_cards["pontos"].sum()
            total_trans = len(df_cards[df_cards["VALOR"] > 0])
            tk_medio = (
                total_valor / total_trans if total_trans > 0 else 0
            )

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(
                    "Total de Pontos",
                    formatar_numero(total_pts),
                )
            with col2:
                st.metric(
                    "Total de Valor",
                    formatar_moeda(total_valor),
                )
            with col3:
                st.metric(
                    "Ticket Medio Geral",
                    formatar_moeda(tk_medio),
                )
        else:
            st.warning("Dados nao disponiveis")

    elif menu == "Producao por Regiao":
        df_mr = calcular_media_producao_regiao(df, df_sup)
        if not df_mr.empty:
            chart_card_open(
                "Produtividade Media por Regiao",
                icon="📊",
                subtitle="Comparativo de produtividade media entre regioes",
            )
            fig = criar_grafico_media_regiao(df_mr)
            st.plotly_chart(fig, width="stretch")
            chart_card_close()
            sac.divider(
                label="Estatisticas Detalhadas",
                icon="table",
                align="left",
                color="gray",
            )
            df_d = df_mr.drop(
                ["Valor Desvio", "Pontos Desvio"],
                axis=1,
            )
            exibir_tabela(df_d)
            _exportar_csv(
                df_d, "producao_por_regiao", "exp_prod_reg"
            )
        else:
            st.warning("Dados nao disponiveis")

    elif menu == "Distribuicao de Produtos":
        df_dist = calcular_distribuicao_produtos(df, df_sup)
        if not df_dist.empty:
            st.info("Visualizacao da distribuicao de produtos por consultor")
            top_n = st.slider(
                "Exibir top N consultores",
                min_value=5,
                max_value=50,
                value=20,
                step=5,
            )
            exibir_tabela(df_dist.head(top_n))
            _exportar_csv(
                df_dist, "distribuicao_produtos",
                "exp_dist_prod",
            )
        else:
            st.warning("Dados nao disponiveis")
