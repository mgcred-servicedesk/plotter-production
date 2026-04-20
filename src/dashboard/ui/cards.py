"""
Primitivas de cards e indicadores visuais.

Reutilizam as classes CSS ja definidas em ``app.py``
(``mg-progress*``, ``mg-status*``), mantendo a mesma
linguagem visual do dashboard existente.

Componentes:
    progress_bar        Barra de progresso colorida.
    status_badge        Badge textual (meta atingida /
                        em progresso / abaixo da meta).
    card_kpi_principal  Card completo: metric + badge de
                        atingimento + projecao + barra.
"""

from typing import Optional

import streamlit as st

from src.reports.formatters import (
    formatar_numero,
    formatar_percentual,
)


# ── Primitivas ───────────────────────────────────────


def progress_bar(percent: float, label: str = "") -> None:
    """
    Renderiza barra de progresso horizontal.

    Cor muda conforme a faixa:
        >=100% → sucesso
        >= 80% → aviso
        < 80% → alerta

    Args:
        percent: Percentual absoluto (0-100+).
        label: Rotulo opcional abaixo da barra.
    """
    clamped = max(0, min(percent, 100))
    if percent >= 100:
        css_class = "mg-success"
    elif percent >= 80:
        css_class = "mg-warning"
    else:
        css_class = "mg-danger"
    lbl = (
        f'<div class="mg-progress-label">{label}</div>'
        if label
        else ""
    )
    st.markdown(
        f'<div class="mg-progress">'
        f'<div class="mg-progress-fill {css_class}" '
        f'style="width:{clamped:.1f}%"></div>'
        f"</div>{lbl}",
        unsafe_allow_html=True,
    )


def status_badge(percent: float) -> None:
    """
    Renderiza badge textual de status da meta.

    Args:
        percent: Percentual de atingimento.
    """
    if percent >= 100:
        cls = "mg-status-success"
        txt = "Meta atingida"
    elif percent >= 80:
        cls = "mg-status-warning"
        txt = "Em progresso"
    else:
        cls = "mg-status-danger"
        txt = "Abaixo da meta"
    st.markdown(
        f'<div class="mg-status {cls}">'
        f'<span class="mg-status-dot"></span>'
        f"{txt}</div>",
        unsafe_allow_html=True,
    )


def _delta_color(percent: float, limiar_warning: float = 80) -> str:
    """Cor do delta conforme percentual (API st.metric)."""
    if percent >= 100:
        return "normal"
    if percent >= limiar_warning:
        return "off"
    return "inverse"


# ── Cards compostos ──────────────────────────────────


def card_kpi_principal(
    label: str,
    valor: str,
    meta: Optional[float] = None,
    atingimento_pct: Optional[float] = None,
    projecao: Optional[float] = None,
    projecao_label: str = "projecao",
    legenda: Optional[str] = None,
    mostrar_badge: bool = True,
) -> None:
    """
    Card completo para um indicador principal do consultor.

    Exibe ``st.metric`` com delta de atingimento, barra de
    progresso e badge de status. Se ``projecao`` for
    informada, acrescenta legenda auxiliar abaixo do card.

    Args:
        label: Nome do indicador (ex: 'Total de Pontos').
        valor: Valor ja formatado (ex: '1.234' ou 'R$ 1.234,56').
        meta: Valor da meta. Mostrado como referencia fixa.
        atingimento_pct: Percentual atingido (0-100+). Se
            None, nao renderiza barra nem badge.
        projecao: Valor projetado para fim do periodo.
        projecao_label: Descricao da projecao (ex: 'pontos'
            ou 'reais').
        legenda: Texto auxiliar abaixo do card (sobrescreve
            a legenda default gerada por projecao/meta).
        mostrar_badge: Se False, suprime o badge textual.
    """
    if atingimento_pct is not None:
        delta_txt = (
            f"{formatar_percentual(atingimento_pct)} da meta"
        )
        st.metric(
            label,
            valor,
            delta_txt,
            delta_color=_delta_color(atingimento_pct),
        )
        progress_bar(atingimento_pct)
        if mostrar_badge:
            status_badge(atingimento_pct)
    else:
        st.metric(label, valor)

    linhas: list[str] = []
    if meta is not None:
        linhas.append(
            f"Meta: <strong>{formatar_numero(meta)}</strong>"
        )
    if projecao is not None:
        linhas.append(
            f"Projecao: <strong>"
            f"{formatar_numero(projecao)}</strong> "
            f"{projecao_label}"
        )
    if legenda:
        linhas.append(legenda)

    if linhas:
        st.markdown(
            '<div class="mg-card-legend">'
            + " &middot; ".join(linhas)
            + "</div>",
            unsafe_allow_html=True,
        )
