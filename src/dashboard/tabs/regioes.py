"""
Aba Regioes: KPIs regionais por regiao.
"""

import streamlit as st
import streamlit_antd_components as sac

from src.dashboard.components.tables import exibir_tabela
from src.dashboard.kpis.regioes import calcular_kpis_por_regiao
from src.dashboard.ui.charts import criar_grafico_regional
from src.dashboard.ui.header import chart_card_close, chart_card_open


def render_tab_regioes(
    df,
    df_metas,
    ano,
    mes,
    dia_atual,
    df_sup,
    df_metas_produto=None,
    categorias=None,
    df_full=None,
    df_metas_produto_full=None,
):
    """Renderiza aba de Regioes."""
    sac.divider(
        label="Analise por Regiao",
        icon="map-fill",
        align="left",
        color="blue",
    )

    df_reg = calcular_kpis_por_regiao(
        df,
        df_metas,
        ano,
        mes,
        dia_atual,
        df_sup,
    )

    if not df_reg.empty:
        fig = criar_grafico_regional(df_reg)
        chart_card_open(
            "Performance Regional",
            icon="📍",
            subtitle="Valor realizado, meta e atingimento por regiao",
        )
        st.plotly_chart(fig, width="stretch")
        chart_card_close()

        sac.divider(
            label="KPIs por Regiao",
            icon="table",
            align="left",
            color="gray",
        )
        exibir_tabela(df_reg)
    else:
        st.warning("Dados regionais nao disponiveis")

