"""
Cabecalho, barra de status e containers de card de
grafico do dashboard.

Todos os componentes usam o CSS design system
(``mg-*``) injetado em
``assets/dashboard_style.css``.
"""

import streamlit as st


def render_header() -> None:
    """Renderiza cabecalho estilizado."""
    st.markdown(
        """
        <div class="dashboard-header">
            <h1>Dashboard de Vendas</h1>
            <p>Analise completa de performance
            e KPIs - MGCred</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_status_bar(
    num_registros: int,
    ultima_data,
    filtro_regiao: str,
    num_em_analise: int = 0,
) -> None:
    """Renderiza barra de status com totais e filtros."""
    regiao_txt = (
        f" &middot; Regiao: {filtro_regiao}"
        if filtro_regiao != "Todas"
        else ""
    )
    data_str = (
        ultima_data.strftime("%d/%m/%Y")
        if hasattr(ultima_data, "strftime")
        else str(ultima_data)
    )
    analise_txt = (
        f" &middot; <strong>{num_em_analise:,}</strong> em analise"
        if num_em_analise > 0
        else ""
    )
    st.markdown(
        '<div class="status-bar fade-in">'
        '<span class="status-dot"></span>'
        f"<span><strong>{num_registros:,}</strong>"
        f" pagos{analise_txt}"
        f" &middot; Atualizado em"
        f" <strong>{data_str}</strong>"
        f"{regiao_txt}</span></div>",
        unsafe_allow_html=True,
    )


def chart_card_open(
    title: str,
    icon: str = "",
    subtitle: str = "",
) -> None:
    """Abre container HTML de card de grafico com header."""
    icon_html = (
        f'<div class="mg-chart-icon">{icon}</div>'
        if icon
        else ""
    )
    sub_html = (
        f'<div class="mg-chart-subtitle">{subtitle}</div>'
        if subtitle
        else ""
    )
    st.markdown(
        f'<div class="mg-chart-card">'
        f'<div class="mg-chart-header">'
        f'{icon_html}'
        f'<div><div class="mg-chart-title">{title}</div>'
        f'{sub_html}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def chart_card_close() -> None:
    """Fecha container HTML de card de grafico."""
    st.markdown("</div>", unsafe_allow_html=True)
