"""
Cards compostos de KPIs do dashboard.

Agrupa os grandes blocos de indicadores principais e do
pipeline em analise. Cada card usa ``st.metric`` combinado
com ``progress_bar``/``status_badge`` de ``ui.cards``.
"""

import streamlit as st
import streamlit_antd_components as sac

from src.dashboard.formatters import (
    formatar_moeda,
    formatar_numero,
    formatar_percentual,
)
from src.dashboard.ui.cards import progress_bar, status_badge


def criar_cards_kpis_principais(kpis):
    """Cria cards de KPIs principais."""
    sac.divider(
        label="Indicadores Principais",
        icon="bar-chart-line",
        align="left",
        color="blue",
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        dc = (
            "normal"
            if kpis["perc_ating_prata"] >= 100
            else "off"
            if kpis["perc_ating_prata"] >= 80
            else "inverse"
        )
        st.metric(
            "Total de Vendas",
            formatar_moeda(kpis["total_vendas"]),
            f"{formatar_percentual(kpis['perc_ating_prata'])} da meta prata",
            delta_color=dc,
        )
        progress_bar(kpis["perc_ating_prata"])
        status_badge(kpis["perc_ating_prata"])

    with col2:
        dc = (
            "normal"
            if kpis["perc_ating_prata"] >= 100
            else "off"
            if kpis["perc_ating_prata"] >= 80
            else "inverse"
        )
        st.metric(
            "Total de Pontos",
            formatar_numero(kpis["total_pontos"]),
            f"{formatar_percentual(kpis['perc_ating_prata'])} da meta prata",
            delta_color=dc,
        )
        progress_bar(kpis["perc_ating_prata"])
        status_badge(kpis["perc_ating_prata"])

    with col3:
        dc = (
            "normal"
            if kpis["perc_proj"] >= 100
            else "off"
            if kpis["perc_proj"] >= 90
            else "inverse"
        )
        st.metric(
            "Projecao (Pontos)",
            formatar_numero(kpis["projecao_pontos"]),
            f"{formatar_percentual(kpis['perc_proj'])} da meta prata",
            delta_color=dc,
        )
        progress_bar(kpis["perc_proj"])

    with col4:
        st.metric(
            "Meta Prata",
            formatar_numero(kpis["meta_prata"]),
            f"{kpis['du_restantes']} DU restantes",
        )

    sac.divider(
        label="Indicadores Operacionais",
        icon="clipboard-data",
        align="left",
        color="blue",
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        dc = (
            "normal"
            if kpis["perc_ating_ouro"] >= 100
            else "off"
            if kpis["perc_ating_ouro"] >= 80
            else "inverse"
        )
        st.metric(
            "Meta Ouro",
            formatar_numero(kpis["meta_ouro"]),
            f"{formatar_percentual(kpis['perc_ating_ouro'])} atingido",
            delta_color=dc,
        )
        progress_bar(kpis["perc_ating_ouro"])

    with col2:
        mdr = kpis["meta_diaria_restante"]
        if mdr == 0 and kpis["perc_ating_prata"] >= 100:
            st.metric(
                "Meta Diaria (Pontos)",
                "Meta atingida",
                f"Ritmo: {formatar_numero(kpis['media_du_pontos'])} pts/DU",
                delta_color="normal",
            )
        else:
            dif_pts = kpis["media_du_pontos"] - mdr
            dc = "normal" if dif_pts >= 0 else "inverse"
            st.metric(
                "Meta Diaria Restante",
                f"{formatar_numero(mdr)} pts/DU",
                f"Ritmo atual: {formatar_numero(kpis['media_du_pontos'])} pts/DU",
                delta_color=dc,
            )

    with col3:
        st.metric(
            "Ticket Medio",
            formatar_moeda(kpis["ticket_medio"]),
            f"{formatar_numero(kpis['total_transacoes'])} transacoes",
        )

    with col4:
        prod = (
            kpis["total_transacoes"] / kpis["num_consultores"]
            if kpis["num_consultores"] > 0
            else 0
        )
        st.metric(
            "Produtividade",
            f"{prod:.1f}",
            f"{formatar_numero(kpis['num_consultores'])} consultores",
        )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        pm = (
            kpis["total_pontos"] / kpis["num_consultores"]
            if kpis["num_consultores"] > 0
            else 0
        )
        st.metric(
            "Producao Media/Consultor",
            formatar_numero(pm),
            "pontos por consultor",
        )

    with col2:
        st.metric(
            "Lojas Ativas",
            formatar_numero(kpis["num_lojas"]),
            f"{formatar_numero(kpis['num_regioes'])} regioes",
        )

    with col3:
        st.metric(
            "Consultores Ativos",
            formatar_numero(kpis["num_consultores"]),
            f"Media: {pm:.0f} pts",
        )

    with col4:
        vmc = (
            kpis["total_vendas"] / kpis["num_consultores"]
            if kpis["num_consultores"] > 0
            else 0
        )
        st.metric(
            "Media/Consultor",
            formatar_moeda(vmc),
            "valor por consultor",
        )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Super Contas",
            formatar_numero(kpis.get("qtd_super_conta", 0)),
            "CNCs com subtipo Super Conta",
        )

    with col2:
        st.metric(
            "Emissao de Cartao",
            formatar_numero(kpis.get("qtd_emissao_cartao", 0)),
            "quantidade produzida",
        )

    with col3:
        st.metric(
            "BMG Med",
            formatar_numero(kpis.get("qtd_bmg_med", 0)),
            "quantidade produzida",
        )

    with col4:
        st.metric(
            "Seguro Vida Familiar",
            formatar_numero(kpis.get("qtd_seguro_vida", 0)),
            "quantidade produzida",
        )


def criar_cards_pipeline(df_analise, kpis_pagos):
    """Cria cards de KPIs do pipeline em analise."""
    sac.divider(
        label="Pipeline em Analise (ultimos 30 dias)",
        icon="hourglass-split",
        align="left",
        color="orange",
    )

    if df_analise.empty:
        st.info("Nenhum contrato em analise no periodo.")
        return

    valor_analise = df_analise["VALOR"].sum()
    qtd_analise = len(df_analise)
    ticket_analise = valor_analise / qtd_analise if qtd_analise > 0 else 0
    valor_pagos = kpis_pagos["total_vendas"]
    razao = (
        (valor_analise / valor_pagos * 100)
        if valor_pagos > 0
        else 0
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Valor em Analise",
            formatar_moeda(valor_analise),
            f"{qtd_analise} propostas",
        )
    with col2:
        st.metric(
            "Ticket Medio (Analise)",
            formatar_moeda(ticket_analise),
        )
    with col3:
        num_lojas = (
            df_analise["LOJA"].nunique()
            if "LOJA" in df_analise.columns
            else 0
        )
        st.metric(
            "Lojas com Pipeline",
            formatar_numero(num_lojas),
        )
    with col4:
        st.metric(
            "Pipeline / Produzido",
            formatar_percentual(razao),
            "do valor pago no periodo",
            delta_color="off",
        )
