"""
Aba Regioes: KPIs regionais e mapa de calor regiao x produto.
"""

import streamlit as st
import streamlit_antd_components as sac

from src.dashboard.components.tables import exibir_tabela
from src.dashboard.kpis.regioes import (
    calcular_heatmap_regiao_produto,
    calcular_kpis_por_regiao,
)
from src.dashboard.ui.charts import (
    criar_grafico_regional,
    criar_heatmap_regiao_produto,
)
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

    # ── Mapa de calor: ranking regiao x produto ───
    # Visivel para admin, gestor e gerente_comercial
    # Gerente comercial ve TODAS as regioes (dados pre-RLS)
    # com destaque na(s) sua(s) regiao(oes)
    from src.dashboard.rls import _obter_perfil_efetivo

    perfil = _obter_perfil_efetivo()
    perfil_role = perfil["perfil"] if perfil else None
    pode_ver_heatmap = perfil_role in (
        "admin", "gestor", "gerente_comercial",
    )

    if (
        pode_ver_heatmap
        and df_metas_produto is not None
        and categorias is not None
        and not df_metas_produto.empty
    ):
        # Usar dados completos (pre-RLS) para o heatmap
        # comparativo, quando disponiveis
        df_hm = (
            df_full
            if df_full is not None and not df_full.empty
            else df
        )
        df_mp_hm = (
            df_metas_produto_full
            if df_metas_produto_full is not None
            and not df_metas_produto_full.empty
            else df_metas_produto
        )

        # Regioes do usuario (para destaque)
        regioes_usuario = None
        if perfil_role == "gerente_comercial":
            regioes_usuario = perfil.get("escopo", [])

        df_ranking, df_ating = calcular_heatmap_regiao_produto(
            df_hm, df_mp_hm, categorias,
        )

        if not df_ranking.empty:
            sac.divider(
                label="Ranking por Produto x Regiao",
                icon="grid-3x3-gap-fill",
                align="left",
                color="blue",
            )
            fig_hm = criar_heatmap_regiao_produto(
                df_ranking, df_ating,
                regioes_destaque=regioes_usuario,
            )
            chart_card_open(
                "Ranking Regiao x Produto",
                icon="🗺️",
                subtitle="Mapa de calor comparativo de atingimento",
            )
            st.plotly_chart(fig_hm, width="stretch")
            chart_card_close()
