"""
Aba Produtos: KPIs, meta diaria e grafico por produto.
"""

import streamlit as st
import streamlit_antd_components as sac

from src.dashboard.components.tables import exibir_tabela
from src.dashboard.formatters import formatar_moeda
from src.dashboard.kpis.produtos import calcular_kpis_por_produto
from src.dashboard.ui.charts import criar_grafico_produtos
from src.dashboard.ui.header import chart_card_close, chart_card_open


def render_tab_produtos(
    df,
    df_metas_produto,
    categorias,
    ano,
    mes,
    dia_atual,
    df_sup,
):
    """Renderiza aba de Produtos."""
    sac.divider(
        label="Analise de Produtos",
        icon="tags-fill",
        align="left",
        color="blue",
    )

    df_prod = calcular_kpis_por_produto(
        df,
        df_metas_produto,
        categorias,
        ano,
        mes,
        dia_atual,
        df_sup,
    )

    # ── Cards de meta diaria por produto ────────
    if not df_prod.empty and "Meta Diária Restante" in df_prod.columns:
        sac.divider(
            label="Meta Diaria Restante por Produto",
            icon="bullseye",
            align="left",
            color="gray",
        )

        prods = df_prod[df_prod["Meta"] > 0]
        if not prods.empty:
            cols = st.columns(len(prods))
            for col, (_, row) in zip(cols, prods.iterrows()):
                with col:
                    mdr = row["Meta Diária Restante"]
                    atingiu = (
                        mdr == 0 and row["% Atingimento"] >= 100
                    )
                    if atingiu:
                        st.metric(
                            row["Produto"],
                            "Meta atingida",
                            f"Ritmo: {formatar_moeda(row['Média DU'])}/DU",
                            delta_color="normal",
                        )
                    else:
                        dif = row["Média DU"] - mdr
                        dc = "normal" if dif >= 0 else "inverse"
                        st.metric(
                            row["Produto"],
                            formatar_moeda(mdr) + "/DU",
                            f"Ritmo: {formatar_moeda(row['Média DU'])}/DU",
                            delta_color=dc,
                        )

            # Resumo geral de produtos
            mdr_total = prods["Meta Diária Restante"].sum()
            media_du_total = prods["Média DU"].sum()
            todas_atingidas = (
                mdr_total == 0
                and (prods["% Atingimento"] >= 100).all()
            )

            col_geral, col_gap, col_ritmo = st.columns([2, 1, 2])
            with col_geral:
                if todas_atingidas:
                    st.metric(
                        "Meta Diaria Geral (Produtos)",
                        "Todas atingidas",
                        f"Ritmo: {formatar_moeda(media_du_total)}/DU",
                        delta_color="normal",
                    )
                else:
                    dif_total = media_du_total - mdr_total
                    dc_total = (
                        "normal" if dif_total >= 0 else "inverse"
                    )
                    st.metric(
                        "Meta Diaria Restante (Geral)",
                        formatar_moeda(mdr_total) + "/DU",
                        f"Ritmo: {formatar_moeda(media_du_total)}/DU",
                        delta_color=dc_total,
                    )
            with col_ritmo:
                if todas_atingidas:
                    st.metric(
                        "Folga Diaria",
                        formatar_moeda(media_du_total),
                        "meta ja atingida",
                        delta_color="normal",
                    )
                else:
                    gap = mdr_total - media_du_total
                    if gap > 0:
                        st.metric(
                            "Gap Diario",
                            formatar_moeda(gap),
                            "abaixo do necessario",
                            delta_color="inverse",
                        )
                    else:
                        st.metric(
                            "Folga Diaria",
                            formatar_moeda(abs(gap)),
                            "acima do necessario",
                            delta_color="normal",
                        )

    fig = criar_grafico_produtos(df_prod)
    chart_card_open(
        "Analise Completa de Produtos",
        icon="📦",
        subtitle="Realizado vs Meta, Atingimento, Projecao e Ticket Medio",
    )
    st.plotly_chart(fig, width="stretch")
    chart_card_close()

    sac.divider(
        label="KPIs por Produto",
        icon="table",
        align="left",
        color="gray",
    )
    exibir_tabela(df_prod)
    st.info("FGTS/Ant. Ben./CNC 13o: conjunto FGTS + Antecipação de Benefício + CNC 13º")
