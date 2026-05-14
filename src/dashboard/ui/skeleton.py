"""
Placeholder shimmer exibido enquanto os dados carregam.

Usa as classes CSS ``mg-skeleton*`` do design system em
``assets/dashboard_style.css``.
"""

import streamlit as st


def render_skeleton() -> None:
    """Renderiza placeholder shimmer enquanto dados carregam.

    Estrutura espelha o layout real do dashboard:
      status bar → 3 hero KPIs → 4 contexto → 5 produtos → chart → tabs
    """
    # Status bar
    status = '<div class="mg-skeleton-status"></div>'

    # Hero: 3 cards grandes (Realizado | % Meta | Falta)
    hero_cards = "".join(
        '<div class="mg-skeleton-card hero">'
        '<div class="mg-skeleton-line xs"></div>'
        '<div class="mg-skeleton-line xl"></div>'
        '<div class="mg-skeleton-line sm"></div>'
        "</div>"
        for _ in range(3)
    )

    # Contexto: 4 cards médios
    context_cards = "".join(
        '<div class="mg-skeleton-card">'
        '<div class="mg-skeleton-line lg"></div>'
        '<div class="mg-skeleton-line sm"></div>'
        '<div class="mg-skeleton-line xs"></div>'
        "</div>"
        for _ in range(4)
    )

    # Produtos/MIX: 5 cards compactos
    product_cards = "".join(
        '<div class="mg-skeleton-card compact">'
        '<div class="mg-skeleton-line sm"></div>'
        '<div class="mg-skeleton-line xs"></div>'
        "</div>"
        for _ in range(5)
    )

    # Barra de tabs
    tabs_bar = '<div class="mg-skeleton-tabs"></div>'

    st.markdown(
        f'<div class="mg-skeleton">'
        f"{status}"
        f'<div class="mg-skeleton-row">{hero_cards}</div>'
        f'<div class="mg-skeleton-row">{context_cards}</div>'
        f'<div class="mg-skeleton-row">{product_cards}</div>'
        f'<div class="mg-skeleton-chart">'
        f'<div class="mg-skeleton-chart-inner"></div>'
        f"</div>"
        f"{tabs_bar}"
        f"</div>",
        unsafe_allow_html=True,
    )
