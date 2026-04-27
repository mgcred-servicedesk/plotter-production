"""
KPI Cards Reformulados — Prioridade 2 da Reforma UX/UI.

Novo layout: 3 KPIs principais dominantes + KPIs de contexto.
- Realizado (fonte grande, destaque)
- % Meta (com indicador visual de status)
- Gap (faltante para meta)

Cores semânticas: Verde (>100%), Amarelo (60-99%), Vermelho (<60%)
"""

from typing import Dict, Optional, Sequence

import streamlit as st

from src.dashboard.formatters import formatar_moeda, formatar_percentual
from src.dashboard.ui.colors import (
    get_status_full,
    get_churn_status,
    get_ritmo_status,
)


def _formatar_valor_moeda(valor: float) -> str:
    """Formata valor em milhões com 2 casas decimais."""
    if valor >= 1_000_000:
        return f"R$ {valor / 1e6:.2f}M"
    elif valor >= 1_000:
        return f"R$ {valor / 1e3:.1f}K"
    else:
        return f"R$ {valor:,.0f}"


def render_kpis_principais(
    kpis: Dict,
    kpis_analise: Dict,
    kpis_cancel: Dict,
    daily_pago: Optional[Sequence[float]] = None,
) -> None:
    """
    Renderiza os 3 KPIs principais em linha dominante.

    Layout:
        | REALIZADO | % META | GAP |

    Args:
        kpis: KPIs gerais (total_vendas, perc_ating, meta, etc)
        kpis_analise: KPIs de contratos em análise
        kpis_cancel: KPIs de cancelados
        daily_pago: Série diária de valores pagos (para sparkline)
    """
    total_vendas = kpis.get("total_vendas", 0)
    # % e gap aqui são em VALOR (R$), comparando vendas com a meta-mix
    # global (soma das metas por produto). `perc_ating_prata` é em pontos.
    perc_ating = kpis.get("perc_ating_valor", 0)
    gap = kpis.get("gap_valor", 0)

    cor_status, bg_status, emoji_status, label_status = get_status_full(perc_ating)

    # CSS para os cards reformulados
    css_cards = """
    <style>
    .mg-kpi-hero {
        background: var(--bg-secondary);
        border-radius: 16px;
        padding: 28px 32px;
        text-align: center;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        border: 1px solid var(--border-color);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .mg-kpi-hero:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 24px rgba(0,0,0,0.12);
    }
    .mg-kpi-label {
        font-size: 13px;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        color: var(--text-muted);
        margin-bottom: 12px;
    }
    .mg-kpi-valor {
        font-size: 42px;
        font-weight: 700;
        color: var(--text-color);
        line-height: 1.1;
        margin-bottom: 8px;
    }
    .mg-kpi-status {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-size: 16px;
        font-weight: 600;
        padding: 6px 14px;
        border-radius: 20px;
        background: rgba(0,0,0,0.05);
    }
    .mg-kpi-gap {
        font-size: 24px;
        color: #ef4444;
    }
    .mg-kpi-sub {
        font-size: 13px;
        color: var(--text-muted);
        margin-top: 8px;
    }
    </style>
    """
    st.markdown(css_cards, unsafe_allow_html=True)

    # Linha dos 3 KPIs principais
    col1, col2, col3 = st.columns([1.2, 1, 1])

    with col1:
        # Card: Realizado
        realizado_fmt = _formatar_valor_moeda(total_vendas)
        st.markdown(
            f"""
            <div class="mg-kpi-hero">
                <div class="mg-kpi-label">💰 Realizado</div>
                <div class="mg-kpi-valor">{realizado_fmt}</div>
                <div class="mg-kpi-sub">Total acumulado no período</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        # Card: % Meta
        st.markdown(
            f"""
            <div class="mg-kpi-hero">
                <div class="mg-kpi-label">📊 % Meta Atingida</div>
                <div class="mg-kpi-valor" style="color: {cor_status};">
                    {formatar_percentual(perc_ating)}
                </div>
                <div class="mg-kpi-status" style="color: {cor_status}; background: {bg_status};">
                    {emoji_status} {label_status}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        # Card: Gap
        if gap > 0:
            gap_fmt = _formatar_valor_moeda(gap)
            gap_texto = f"-{gap_fmt}"
            gap_sub = "Faltam para meta"
        else:
            gap_texto = "✓ Meta Atingida"
            gap_sub = f"+{_formatar_valor_moeda(abs(gap))} acima"

        st.markdown(
            f"""
            <div class="mg-kpi-hero">
                <div class="mg-kpi-label">🎯 Gap para Meta</div>
                <div class="mg-kpi-valor mg-kpi-gap">{gap_texto}</div>
                <div class="mg-kpi-sub">{gap_sub}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_kpis_contexto(
    kpis: Dict,
    kpis_analise: Dict,
    kpis_cancel: Dict,
    medias: Dict,
) -> None:
    """
    Renderiza KPIs de contexto em linha secundária.

    Layout:
        | Em Análise | Cancelados | Ticket Médio |

    Args:
        kpis: KPIs gerais
        kpis_analise: KPIs de contratos em análise
        kpis_cancel: KPIs de cancelados
        medias: Médias DU
    """
    valor_analise = kpis_analise.get("valor_analise", 0)
    qtd_analise = kpis_analise.get("qtd_analise", 0)
    valor_cancel = kpis_cancel.get("valor_cancelados", 0)
    indice_perda = kpis_cancel.get("indice_perda", 0)

    # Médias por consultor (em valor)
    total_vendas = kpis.get("total_vendas", 0)
    num_consultores = medias.get("num_consultores", 0) or kpis.get(
        "num_consultores", 0
    )
    media_consultor = (
        total_vendas / num_consultores if num_consultores > 0 else 0
    )
    media_du_consultor = medias.get("media_du_consultor", 0)

    # Calcular potencial e impacto
    taxa_conv = 0.35
    potencial = valor_analise * taxa_conv
    meta_prata = kpis.get("meta_prata", 1)
    impacto_cancel = (valor_cancel / meta_prata * 100) if meta_prata > 0 else 0

    css_contexto = """
    <style>
    .mg-kpi-context {
        background: var(--bg-secondary);
        border-radius: 12px;
        padding: 18px 20px;
        border: 1px solid var(--border-color);
    }
    .mg-kpi-ctx-label {
        font-size: 12px;
        font-weight: 500;
        text-transform: uppercase;
        color: var(--text-muted);
        margin-bottom: 8px;
    }
    .mg-kpi-ctx-valor {
        font-size: 24px;
        font-weight: 600;
        color: var(--text-color);
    }
    .mg-kpi-ctx-sub {
        font-size: 12px;
        color: var(--text-muted);
        margin-top: 6px;
        line-height: 1.4;
    }
    </style>
    """
    st.markdown(css_contexto, unsafe_allow_html=True)

    # Linha de contexto
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            f"""
            <div class="mg-kpi-context">
                <div class="mg-kpi-ctx-label">⏳ Em Análise</div>
                <div class="mg-kpi-ctx-valor">{formatar_moeda(valor_analise)}</div>
                <div class="mg-kpi-ctx-sub">
                    {qtd_analise:,} propostas<br>
                    💡 Se converter 35%: <strong>+{formatar_moeda(potencial)}</strong>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        cor_churn, emoji_churn, nivel_churn = get_churn_status(indice_perda)
        st.markdown(
            f"""
            <div class="mg-kpi-context">
                <div class="mg-kpi-ctx-label">⚠️ Cancelados</div>
                <div class="mg-kpi-ctx-valor">{formatar_moeda(valor_cancel)}</div>
                <div class="mg-kpi-ctx-sub">
                    Churn: <strong style="color: {cor_churn};">{formatar_percentual(indice_perda)}</strong> {emoji_churn}<br>
                    📉 Nível: <strong>{nivel_churn}</strong> | Impacto: <strong>-{impacto_cancel:.1f}% da meta</strong>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            f"""
            <div class="mg-kpi-context">
                <div class="mg-kpi-ctx-label">👤 Média por Consultor</div>
                <div class="mg-kpi-ctx-valor">{formatar_moeda(media_consultor)}</div>
                <div class="mg-kpi-ctx-sub">
                    Acumulado entre {num_consultores:,} consultores<br>
                    Média DU/consultor: <strong>{formatar_moeda(media_du_consultor)}</strong>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_bloco_ritmo_projecao(kpis: Dict) -> None:
    """
    Renderiza o bloco de Ritmo vs Meta e Projeção.

    Layout visual com barras de comparação.
    """
    perc_proj = kpis.get("perc_proj", 0)
    projecao = kpis.get("projecao", 0)
    meta_prata = kpis.get("meta_prata", 0)
    media_du = kpis.get("media_du", 0)
    media_du_pts = kpis.get("media_du_pontos", 1)

    # Calcular ritmos
    fator = media_du / media_du_pts if media_du_pts > 0 else 1
    meta_diaria_restante = kpis.get("meta_diaria_restante_pts", 0) * fator
    ritmo_necessario = meta_diaria_restante if meta_diaria_restante > 0 else 0
    desvio = (
        ((media_du - ritmo_necessario) / ritmo_necessario * 100)
        if ritmo_necessario > 0
        else 0
    )

    # Cores por status (usando sistema semântico)
    cor_ritmo, emoji_ritmo, status_texto = get_ritmo_status(desvio)

    st.markdown("---")
    st.markdown("### 📈 Para Onde Estamos Indo")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Ritmo de Vendas**")

        # Barra de comparação
        perc_ritmo = min(
            100,
            max(
                0, (media_du / ritmo_necessario * 100) if ritmo_necessario > 0 else 100
            ),
        )
        st.markdown(
            f"""
            <div style="margin: 16px 0;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                    <span style="font-size: 14px; color: var(--text-muted);">Ritmo Atual</span>
                    <span style="font-size: 14px; font-weight: 600;">{formatar_moeda(media_du)}/DIA</span>
                </div>
                <div style="background: var(--bg-primary); height: 24px; border-radius: 12px; overflow: hidden;">
                    <div style="background: linear-gradient(90deg, {cor_ritmo} 0%, {cor_ritmo}80 100%); 
                                height: 100%; width: {perc_ritmo:.0f}%; border-radius: 12px;
                                transition: width 0.5s ease;"></div>
                </div>
                <div style="display: flex; justify-content: space-between; margin-top: 8px;">
                    <span style="font-size: 12px; color: var(--text-muted);">Necessário: {formatar_moeda(ritmo_necessario)}/DIA</span>
                    <span style="font-size: 13px; color: {cor_ritmo}; font-weight: 600;">{status_texto} ({desvio:+.0f}%)</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown("**Projeção de Fechamento**")

        from src.dashboard.ui.colors import get_status_color

        perc_proj_vis = min(100, perc_proj)
        cor_proj = get_status_color(perc_proj)

        st.markdown(
            f"""
            <div style="margin: 16px 0;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                    <span style="font-size: 14px;">Meta: {formatar_moeda(meta_prata)}</span>
                </div>
                <div style="background: var(--bg-primary); height: 24px; border-radius: 12px; overflow: hidden;">
                    <div style="background: linear-gradient(90deg, {cor_proj} 0%, {cor_proj}80 100%); 
                                height: 100%; width: {perc_proj_vis:.0f}%; border-radius: 12px;"></div>
                </div>
                <div style="display: flex; justify-content: space-between; margin-top: 8px; align-items: center;">
                    <span style="font-size: 14px; font-weight: 600; color: {cor_proj};">
                        Projeção: {formatar_moeda(projecao)} ({formatar_percentual(perc_proj)})
                    </span>
                </div>
                <div style="font-size: 12px; color: var(--text-muted); margin-top: 8px; padding: 8px; background: var(--bg-primary); border-radius: 6px;">
                    → Mantido o ritmo, fecharemos <strong style="color: {cor_proj};">{abs(100 - perc_proj):.0f}% {"acima" if perc_proj >= 100 else "abaixo"}</strong> da meta
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_kpis_reforma(
    kpis: Dict,
    kpis_analise: Dict,
    kpis_cancel: Dict,
    medias: Dict,
    daily_pago: Optional[Sequence[float]] = None,
) -> None:
    """
    Renderiza o novo bloco de KPIs reformulado.

    Ordem:
    1. 3 KPIs principais (dominantes)
    2. KPIs de contexto
    3. Ritmo + Projeção
    """
    # 1. KPIs Principais
    render_kpis_principais(kpis, kpis_analise, kpis_cancel, daily_pago)

    # Espaçamento
    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)

    # 2. KPIs de Contexto
    render_kpis_contexto(kpis, kpis_analise, kpis_cancel, medias)

    # 3. Ritmo e Projeção
    render_bloco_ritmo_projecao(kpis)
