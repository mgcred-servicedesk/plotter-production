"""
Placeholder shimmer exibido enquanto os dados carregam.

Usa as classes CSS ``mg-skeleton*`` do design system em
``assets/dashboard_style.css``.
"""

import streamlit as st


def render_skeleton() -> None:
    """Renderiza placeholder shimmer enquanto dados carregam."""
    cards = ""
    for _ in range(4):
        cards += (
            '<div class="mg-skeleton-card">'
            '<div class="mg-skeleton-line lg"></div>'
            '<div class="mg-skeleton-line sm"></div>'
            '<div class="mg-skeleton-line xs"></div>'
            "</div>"
        )
    st.markdown(
        f'<div class="mg-skeleton">'
        f'<div class="mg-skeleton-row">{cards}</div>'
        f'<div class="mg-skeleton-chart">'
        f'<div class="mg-skeleton-chart-inner"></div>'
        f"</div></div>",
        unsafe_allow_html=True,
    )
