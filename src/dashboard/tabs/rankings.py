"""
Aba Rankings: lojas, consultores, regioes e por produto.
"""

import streamlit as st
import streamlit_antd_components as sac

from src.dashboard.components.tables import exibir_tabela
from src.dashboard.kpis.rankings import (
    calcular_ranking_consultores,
    calcular_ranking_lojas,
    calcular_ranking_media_du,
    calcular_ranking_pontos,
    calcular_ranking_por_produto,
    calcular_ranking_ticket_medio,
)
from src.dashboard.kpis.regioes import calcular_ranking_regioes


def render_tab_rankings(df, df_metas, df_sup, du_decorridos):
    """Renderiza aba de Rankings."""
    sac.divider(
        label="Rankings de Performance",
        icon="trophy-fill",
        align="left",
        color="blue",
    )

    menu = sac.tabs(
        items=[
            sac.TabsItem(label="Lojas", icon="shop"),
            sac.TabsItem(label="Consultores", icon="people"),
            sac.TabsItem(label="Regioes", icon="geo-alt"),
            sac.TabsItem(label="Por Produto", icon="box-seam"),
        ],
        align="start",
        variant="outline",
    )

    if menu == "Lojas":
        col1, col2 = st.columns(2)
        with col1:
            sac.divider(
                label="Top 10 por Atingimento",
                icon="graph-up-arrow",
                align="left",
                color="green",
            )
            rl = calcular_ranking_lojas(df, df_metas, top_n=10)
            if not rl.empty:
                exibir_tabela(rl)
            else:
                st.warning("Dados nao disponiveis")

        with col2:
            sac.divider(
                label="Top 10 por Pontos",
                icon="star-fill",
                align="left",
                color="blue",
            )
            rp = calcular_ranking_pontos(
                df, tipo="loja", top_n=10,
            )
            if not rp.empty:
                exibir_tabela(rp)
            else:
                st.warning("Dados nao disponiveis")

        col3, col4 = st.columns(2)
        with col3:
            sac.divider(
                label="Top 10 por Ticket Medio",
                icon="cash-coin",
                align="left",
                color="orange",
            )
            rt = calcular_ranking_ticket_medio(
                df, tipo="loja", top_n=10,
            )
            if not rt.empty:
                exibir_tabela(rt)
            else:
                st.warning("Dados nao disponiveis")

        with col4:
            sac.divider(
                label="Top 10 por Media DU",
                icon="calendar-check",
                align="left",
                color="violet",
            )
            rm = calcular_ranking_media_du(
                df, tipo="loja", top_n=10,
                du_decorridos=du_decorridos,
            )
            if not rm.empty:
                exibir_tabela(rm)
            else:
                st.warning("Dados nao disponiveis")

    elif menu == "Consultores":
        col1, col2 = st.columns(2)
        with col1:
            sac.divider(
                label="Top 10 por Atingimento",
                icon="graph-up-arrow",
                align="left",
                color="green",
            )
            rc = calcular_ranking_consultores(
                df,
                df_metas,
                top_n=10,
                df_supervisores=df_sup,
            )
            if not rc.empty:
                exibir_tabela(rc)
            else:
                st.warning("Dados nao disponiveis")

        with col2:
            sac.divider(
                label="Top 10 por Pontos",
                icon="star-fill",
                align="left",
                color="blue",
            )
            rp = calcular_ranking_pontos(
                df, tipo="consultor", top_n=10,
                df_supervisores=df_sup,
            )
            if not rp.empty:
                exibir_tabela(rp)
            else:
                st.warning("Dados nao disponiveis")

        col3, col4 = st.columns(2)
        with col3:
            sac.divider(
                label="Top 10 por Ticket Medio",
                icon="cash-coin",
                align="left",
                color="orange",
            )
            rt = calcular_ranking_ticket_medio(
                df,
                tipo="consultor",
                top_n=10,
                df_supervisores=df_sup,
            )
            if not rt.empty:
                exibir_tabela(rt)
            else:
                st.warning("Dados nao disponiveis")

        with col4:
            sac.divider(
                label="Top 10 por Media DU",
                icon="calendar-check",
                align="left",
                color="violet",
            )
            rm = calcular_ranking_media_du(
                df, tipo="consultor", top_n=10,
                du_decorridos=du_decorridos,
                df_supervisores=df_sup,
            )
            if not rm.empty:
                exibir_tabela(rm)
            else:
                st.warning("Dados nao disponiveis")

    elif menu == "Regioes":
        rk_regioes = calcular_ranking_regioes(
            df, df_metas, du_decorridos=du_decorridos,
        )
        if not rk_regioes:
            st.warning("Dados nao disponiveis")
        else:
            col1, col2 = st.columns(2)
            with col1:
                sac.divider(
                    label="Por Atingimento Meta",
                    icon="graph-up-arrow",
                    align="left",
                    color="green",
                )
                exibir_tabela(rk_regioes["atingimento"])

            with col2:
                sac.divider(
                    label="Por Pontos",
                    icon="star-fill",
                    align="left",
                    color="blue",
                )
                exibir_tabela(rk_regioes["pontos"])

            col3, col4 = st.columns(2)
            with col3:
                sac.divider(
                    label="Por Ticket Medio",
                    icon="cash-coin",
                    align="left",
                    color="orange",
                )
                exibir_tabela(rk_regioes["ticket"])

            with col4:
                sac.divider(
                    label="Por Media DU",
                    icon="calendar-check",
                    align="left",
                    color="violet",
                )
                exibir_tabela(rk_regioes["media_du"])

            # Por Produto
            rk_prod = rk_regioes.get("por_produto", {})
            if rk_prod:
                sac.divider(
                    label="Regioes por Produto",
                    icon="tags-fill",
                    align="left",
                    color="gray",
                )
                for prod, rk in rk_prod.items():
                    if not rk.empty:
                        with st.expander(prod, expanded=False):
                            exibir_tabela(rk)

    elif menu == "Por Produto":
        tipo_sel = sac.segmented(
            items=[
                sac.SegmentedItem(label="Lojas", icon="shop"),
                sac.SegmentedItem(
                    label="Consultores", icon="people",
                ),
            ],
            align="start",
            use_container_width=False,
        )
        tipo = "loja" if tipo_sel == "Lojas" else "consultor"
        rankings = calcular_ranking_por_produto(
            df,
            tipo=tipo,
            top_n=10,
            df_supervisores=df_sup,
        )
        if rankings:
            for prod, rk in rankings.items():
                if not rk.empty:
                    with st.expander(prod, expanded=False):
                        exibir_tabela(rk)
        else:
            st.warning("Dados nao disponiveis")
