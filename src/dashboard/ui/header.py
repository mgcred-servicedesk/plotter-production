"""
Cabecalho, barra de status e containers de card de
grafico do dashboard.

Todos os componentes usam o CSS design system
(``mg-*``) injetado em
``assets/dashboard_style.css``.
"""

import streamlit as st

from src.config.settings import MESES_PT_TITULO


def render_header(
    mes: int | None = None,
    ano: int | None = None,
    titulo: str = "Dashboard de Vendas",
    subtitulo: str = "Analise completa de performance e KPIs - MGCred",
) -> None:
    """Renderiza cabecalho estilizado com micro-breadcrumb opcional.

    Args:
        mes: Mês ativo (1–12). Quando fornecido junto com ``ano``,
            exibe o período como terceiro item do breadcrumb.
        ano: Ano ativo (ex: 2026).
        titulo: Titulo principal exibido no header (h1). Default
            mantem o comportamento original.
        subtitulo: Texto secundario abaixo do titulo.
    """
    if mes and ano:
        periodo = f"{MESES_PT_TITULO.get(mes, mes)} {ano}"
        breadcrumb = (
            f'<nav class="mg-breadcrumb" aria-label="breadcrumb">'
            f"<span>MGCred</span>"
            f'<span class="mg-breadcrumb-sep">›</span>'
            f"<span>{titulo}</span>"
            f'<span class="mg-breadcrumb-sep">›</span>'
            f'<span class="mg-breadcrumb-active">{periodo}</span>'
            f"</nav>"
        )
    else:
        breadcrumb = (
            f'<nav class="mg-breadcrumb" aria-label="breadcrumb">'
            f"<span>MGCred</span>"
            f'<span class="mg-breadcrumb-sep">›</span>'
            f'<span class="mg-breadcrumb-active">{titulo}</span>'
            f"</nav>"
        )

    st.markdown(
        f'<div class="dashboard-header">'
        f"{breadcrumb}"
        f"<h1>{titulo}</h1>"
        f"<p>{subtitulo}</p>"
        f"</div>",
        unsafe_allow_html=True,
    )


def render_status_bar(
    num_registros: int,
    ultima_data,
    filtro_regiao: str,
    num_em_analise: int = 0,
    num_cancelados: int = 0,
    ultima_atualizacao=None,
) -> None:
    """Renderiza barra de status com totais e filtros.

    Args:
        ultima_data: data de competencia dos dados exibidos (rotulo
            "Dados em"). Normalmente o maior ``data_status_pagamento``.
        ultima_atualizacao: timestamp da ultima insercao de contrato
            no Supabase (rotulo "Atualizado em"). Pode ser ``None``
            quando nao houver dados.
    """
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
    # CREATED_AT chega em UTC; converte para America/Sao_Paulo para
    # evitar deslocamento de 1 dia em insercoes apos as 21h locais.
    if hasattr(ultima_atualizacao, "tz_convert"):
        atualizacao_str = ultima_atualizacao.tz_convert(
            "America/Sao_Paulo"
        ).strftime("%d/%m/%Y")
    elif hasattr(ultima_atualizacao, "strftime"):
        atualizacao_str = ultima_atualizacao.strftime("%d/%m/%Y")
    else:
        atualizacao_str = None
    atualizacao_txt = (
        f" &middot; Atualizado em <strong>{atualizacao_str}</strong>"
        if atualizacao_str
        else ""
    )
    analise_txt = (
        f" &middot; <strong>{num_em_analise:,}</strong> em analise"
        if num_em_analise > 0
        else ""
    )
    cancel_txt = (
        f" &middot; <strong>{num_cancelados:,}</strong> cancelados"
        if num_cancelados > 0
        else ""
    )
    st.markdown(
        '<div class="status-bar fade-in">'
        '<span class="status-dot"></span>'
        f"<span><strong>{num_registros:,}</strong>"
        f" pagos{analise_txt}{cancel_txt}"
        f" &middot; Dados em"
        f" <strong>{data_str}</strong>"
        f"{atualizacao_txt}"
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
