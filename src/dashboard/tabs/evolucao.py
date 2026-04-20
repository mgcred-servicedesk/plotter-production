"""
Aba Evolucao: evolucao diaria de vendas e pontos.
"""

import streamlit as st
import streamlit_antd_components as sac

from src.dashboard.formatters import formatar_moeda
from src.dashboard.kpis.evolucao import calcular_evolucao_diaria
from src.dashboard.ui.charts import criar_grafico_evolucao
from src.dashboard.ui.header import chart_card_close, chart_card_open


def render_tab_evolucao(df, ano, mes, kpis):
    """Renderiza aba de Evolucao."""
    sac.divider(
        label="Evolucao Temporal",
        icon="graph-up-arrow",
        align="left",
        color="blue",
    )

    df_ev = calcular_evolucao_diaria(df, ano, mes)

    if not df_ev.empty:
        fig = criar_grafico_evolucao(df_ev, kpis)
        chart_card_open(
            "Evolucao Diaria de Vendas",
            icon="📈",
            subtitle="Acompanhamento diario e acumulado vs meta",
        )
        st.plotly_chart(fig, width="stretch")
        chart_card_close()

        col1, col2, col3 = st.columns(3)
        with col1:
            best = df_ev.loc[df_ev["VALOR"].idxmax()]
            st.metric(
                "Melhor Dia",
                best["DATA"].strftime("%d/%m"),
                formatar_moeda(best["VALOR"]),
            )
        with col2:
            media = df_ev["VALOR"].mean()
            st.metric(
                "Media Diaria",
                formatar_moeda(media),
                f"{len(df_ev)} dias com vendas",
            )
        with col3:
            acima = (df_ev["VALOR"] >= kpis["meta_diaria"]).sum()
            perc = acima / len(df_ev) * 100 if len(df_ev) > 0 else 0
            st.metric(
                "Dias Acima da Meta",
                f"{acima}",
                f"{perc:.1f}% dos dias",
            )
    else:
        st.warning("Dados de evolucao nao disponiveis")
