"""
Aba Regioes: comparativo regional por produto e produtividade.
Visivel apenas para admin e gestor (gerente_comercial excluido).
"""

import pandas as pd
import streamlit as st
import streamlit_antd_components as sac

from src.config.settings import NOMES_DISPLAY_PRODUTO
from src.dashboard.components.tables import exibir_tabela
from src.dashboard.kpis.regioes import (
    calcular_kpis_por_produto_regiao,
    calcular_kpis_por_regiao,
)
from src.dashboard.ui.charts import criar_grafico_regional
from src.dashboard.ui.header import chart_card_close, chart_card_open

_REGIOES_EXCLUIR = frozenset({"ALEXANDRE"})


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

    # Excluir regioes de projeto especifico de todos os comparativos
    if "REGIAO" in df.columns:
        df = df[~df["REGIAO"].str.upper().isin(_REGIOES_EXCLUIR)]

    df_reg = calcular_kpis_por_regiao(
        df, df_metas, ano, mes, dia_atual, df_sup,
    )

    if df_reg.empty:
        st.warning("Dados regionais nao disponiveis")
        return

    # ── Grafico de performance ──────────────────────────
    fig = criar_grafico_regional(df_reg)
    chart_card_open(
        "Performance Regional",
        icon="📍",
        subtitle="Valor realizado e % atingimento por regiao",
    )
    st.plotly_chart(fig, width="stretch")
    chart_card_close()

    # ── Comparativo por produto ─────────────────────────
    if categorias is not None and df_metas_produto is not None and not df_metas_produto.empty:
        sac.divider(
            label="Comparativo por Produto",
            icon="box-seam",
            align="left",
            color="blue",
        )

        rankings = calcular_kpis_por_produto_regiao(
            df, df_metas_produto, categorias, ano, mes, dia_atual,
        )
        grupos = sorted(rankings.keys())

        if grupos:
            labels = [NOMES_DISPLAY_PRODUTO.get(g, g) for g in grupos]
            label_to_grupo = dict(zip(labels, grupos))

            sel = sac.segmented(
                items=[sac.SegmentedItem(label=lb) for lb in labels],
                align="start",
                use_container_width=False,
            )

            grupo_sel = label_to_grupo.get(sel, grupos[0])
            df_prod = rankings.get(grupo_sel, pd.DataFrame())

            if not df_prod.empty:
                exibir_tabela(
                    df_prod,
                    colunas_moeda=["Valor", "Meta", "Ticket Médio", "Projeção"],
                    colunas_percentual=["% Atingimento", "% Projeção"],
                )

    # ── Produtividade por regiao ────────────────────────
    sac.divider(
        label="Produtividade por Regiao",
        icon="graph-up-arrow",
        align="left",
        color="green",
    )

    df_prd = df_reg[
        ["Região", "Nº Consultores", "Valor Médio/Consultor", "Pontos", "Média DU"]
    ].copy()

    df_prd["Pontos/Consultor"] = df_prd.apply(
        lambda r: round(r["Pontos"] / r["Nº Consultores"])
        if r["Nº Consultores"] > 0
        else 0,
        axis=1,
    )

    moeda_cols = ["Valor Médio/Consultor"]
    num_cols = ["Nº Consultores", "Pontos/Consultor"]

    if "PRAZO" in df.columns and "VALOR_PARCELA" in df.columns:
        df_val = df[df["VALOR"] > 0]
        prazo_num = pd.to_numeric(df_val["PRAZO"], errors="coerce")
        prazo_med = prazo_num.groupby(df_val["REGIAO"]).mean().rename("Prazo Médio (meses)")
        parcela_med = df_val["VALOR_PARCELA"].groupby(df_val["REGIAO"]).mean().rename("Parcela Média")
        df_prd["Prazo Médio (meses)"] = df_prd["Região"].map(prazo_med)
        df_prd["Parcela Média"] = df_prd["Região"].map(parcela_med)
        moeda_cols.append("Parcela Média")

    cols = (
        ["Região", "Nº Consultores", "Valor Médio/Consultor",
         "Pontos/Consultor", "Média DU"]
        + (["Prazo Médio (meses)", "Parcela Média"] if "Prazo Médio (meses)" in df_prd.columns else [])
    )

    exibir_tabela(
        df_prd[cols].sort_values("Pontos/Consultor", ascending=False),
        colunas_moeda=moeda_cols,
        colunas_numero=num_cols,
    )
