"""
KPI Cards Reformulados — Prioridade 2 da Reforma UX/UI.

Novo layout: 3 KPIs principais dominantes + KPIs de contexto.
- Realizado (fonte grande, destaque)
- % Meta (com indicador visual de status)
- Gap (faltante para meta)

Cores semânticas: Verde (>100%), Amarelo (60-99%), Vermelho (<60%)
"""

from typing import Dict, List, Optional, Sequence

import streamlit as st

from src.dashboard.formatters import (
    formatar_moeda,
    formatar_moeda_compacta,
    formatar_percentual,
)
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


def _formatar_valor_moeda_total(valor: float) -> str:
    """Formata valor completo com separadores de milhar."""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


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
    # % e gap aqui são em VALOR (R$), comparando vendas com a meta-mix.
    # Meta MIX (produto) = R$ 15.7M; Meta PRATA/OURO = pontos (página à parte).
    perc_ating = kpis.get("perc_ating_valor", 0)
    gap = kpis.get("gap_valor", 0)

    cor_status, bg_status, emoji_status, label_status = get_status_full(perc_ating)

    # CSS para os cards reformulados
    css_cards = """
    <style>
    .mg-kpi-hero {
        background: var(--mg-surface);
        border-radius: 16px;
        padding: 28px 32px;
        text-align: center;
        box-shadow: var(--mg-shadow-md);
        border: 1px solid var(--mg-border);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .mg-kpi-hero:hover {
        transform: translateY(-2px);
        box-shadow: var(--mg-shadow-lg);
    }
    .mg-kpi-label {
        font-size: 13px;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        color: var(--mg-text-muted);
        margin-bottom: 12px;
    }
    .mg-kpi-valor {
        font-size: 42px;
        font-weight: 700;
        color: var(--mg-text);
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
        background: var(--mg-hover-bg);
    }
    .mg-kpi-gap {
        font-size: 24px;
        color: var(--mg-danger);
    }
    .mg-kpi-sub {
        font-size: 13px;
        color: var(--mg-text-muted);
        margin-top: 8px;
    }
    </style>
    """
    st.markdown(css_cards, unsafe_allow_html=True)

    # Linha dos 3 KPIs principais
    # Obter dados adicionais necessários
    meta_mix = kpis.get("meta_mix", 0)
    perc_proj = kpis.get("perc_proj", 0)
    du_restantes = kpis.get("du_restantes", 1)

    col1, col2, col3 = st.columns([1.2, 1, 1])

    with col1:
        # Card: Pagos (antes Realizado)
        pagos_fmt = _formatar_valor_moeda(total_vendas)
        pagos_total = _formatar_valor_moeda_total(total_vendas)
        projecao = kpis.get("projecao", 0)
        proj_fmt = _formatar_valor_moeda(projecao)
        st.markdown(
            f"""
            <div class="mg-kpi-hero">
                <div class="mg-kpi-label">💰 Pagos</div>
                <div class="mg-kpi-valor">{pagos_fmt}</div>
                <div class="mg-kpi-sub" style="font-size: 15px; font-weight: 500;">
                    {pagos_total} <span style="color: var(--mg-text-muted); font-size: 13px;">
                    → Proj: {proj_fmt}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        # Card: % Meta (com projeção e valor da meta)
        meta_mix_fmt = _formatar_valor_moeda_total(meta_mix)
        st.markdown(
            f"""
            <div class="mg-kpi-hero">
                <div class="mg-kpi-label">📊 % Meta Atingida</div>
                <div class="mg-kpi-valor" style="color: {cor_status};">
                    {formatar_percentual(perc_ating)}
                </div>
                <div class="mg-kpi-sub" style="font-size: 13px;">
                    Projeção: {formatar_percentual(perc_proj)} |
                    MIX: {meta_mix_fmt}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        # Card: Gap (com falta e valor por dia)
        if gap > 0:
            gap_fmt = _formatar_valor_moeda(gap)
            gap_por_dia = gap / du_restantes if du_restantes > 1 else gap
            gap_por_dia_fmt = _formatar_valor_moeda(gap_por_dia)
            st.markdown(
                f"""
                <div class="mg-kpi-hero">
                    <div class="mg-kpi-label">🎯 Gap para Meta</div>
                    <div class="mg-kpi-valor mg-kpi-gap">-{gap_fmt}</div>
                    <div class="mg-kpi-sub" style="font-size: 13px;">
                        Falta: {_formatar_valor_moeda_total(gap)}<br>
                        <strong>{gap_por_dia_fmt}/dia</strong>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
                <div class="mg-kpi-hero">
                    <div class="mg-kpi-label">🎯 Gap para Meta</div>
                    <div class="mg-kpi-valor" style="color: #10A37F;">
                    ✓ Meta Atingida
                </div>
                    <div class="mg-kpi-sub" style="font-size: 13px;">
                        +{_formatar_valor_moeda_total(abs(gap))} acima
                    </div>
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

    # Médias por loja (em valor)
    num_lojas = kpis.get("num_lojas", 1)
    media_loja = total_vendas / num_lojas if num_lojas > 0 else 0
    du_dec = kpis.get("du_decorridos", 1)
    if num_lojas > 0 and du_dec > 0:
        media_du_loja = total_vendas / num_lojas / du_dec
    else:
        media_du_loja = media_loja

    # Calcular potencial e impacto
    taxa_conv = 0.35
    potencial = valor_analise * taxa_conv
    meta_mix_ctx = kpis.get("meta_mix", 1)
    impacto_cancel = (valor_cancel / meta_mix_ctx * 100) if meta_mix_ctx > 0 else 0

    css_contexto = """
    <style>
    .mg-kpi-context {
        background: var(--mg-surface);
        border-radius: 12px;
        padding: 18px 20px;
        border: 1px solid var(--mg-border);
        box-shadow: var(--mg-shadow-sm);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .mg-kpi-context:hover {
        transform: translateY(-2px);
        box-shadow: var(--mg-shadow-md);
    }
    .mg-kpi-ctx-label {
        font-size: 12px;
        font-weight: 500;
        text-transform: uppercase;
        color: var(--mg-text-muted);
        margin-bottom: 8px;
    }
    .mg-kpi-ctx-valor {
        font-size: 24px;
        font-weight: 600;
        color: var(--mg-text);
    }
    .mg-kpi-ctx-sub {
        font-size: 12px;
        color: var(--mg-text-muted);
        margin-top: 6px;
        line-height: 1.4;
    }
    </style>
    """
    st.markdown(css_contexto, unsafe_allow_html=True)

    # Linha de contexto
    col1, col2, col3, col4 = st.columns(4)

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

    with col4:
        st.markdown(
            f"""
            <div class="mg-kpi-context">
                <div class="mg-kpi-ctx-label">
                    🏪 Média por Loja
                </div>
                <div class="mg-kpi-ctx-valor">
                    {formatar_moeda(media_loja)}
                </div>
                <div class="mg-kpi-ctx-sub">
                    Acumulado entre {num_lojas:,} lojas<br>
                    Média DU/loja:
                    <strong>{formatar_moeda(media_du_loja)}</strong>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_bloco_media_projecao(kpis: Dict) -> None:
    """
    Renderiza o bloco de Média vs Meta e Projeção.
    Design compacto unificado: Média → Necessário → Projeção
    """
    from src.dashboard.ui.colors import get_status_color

    perc_proj = kpis.get("perc_proj", 0)
    projecao = kpis.get("projecao", 0)
    meta_mix = kpis.get("meta_mix", 1)
    media_du = kpis.get("media_du", 0)
    total_vendas = kpis.get("total_vendas", 0)
    du_restantes = kpis.get("du_restantes", 1)
    du_total = kpis.get("du_total", 1)
    du_decorridos = kpis.get("du_decorridos", 1)

    # Calcular média necessária e projeção
    gap = max(0, meta_mix - total_vendas)
    media_necessaria = (
        gap / du_restantes if du_restantes > 0 else 0
    )
    desvio = (
        ((media_du - media_necessaria) / media_necessaria * 100)
        if media_necessaria > 0
        else 0
    )

    # Cores por status
    cor_media, emoji_media, status_texto = get_ritmo_status(desvio)
    cor_proj = get_status_color(perc_proj)

    # Progresso temporal: percentual de dias úteis decorridos
    perc_tempo = (
        (du_decorridos / du_total * 100) if du_total > 0 else 0
    )

    # Mensagem contextual
    msg_desvio = (
        f"{abs(desvio):.0f}% {'acima' if desvio > 0 else 'abaixo'} do necessário"
        if media_necessaria > 0
        else "Meta atingida"
    )
    msg_fechamento = (
        f"Fecharemos {abs(100 - perc_proj):.0f}% "
        f"{'acima' if perc_proj >= 100 else 'abaixo'} da meta"
        if meta_mix > 0
        else ""
    )

    st.markdown("---")
    st.markdown("### 📈 Para Onde Estamos Indo")

    # Card único compacto
    st.markdown(
        f"""
        <div style="background: var(--mg-surface); border-radius: 12px;
                    padding: 20px; border: 1px solid var(--mg-border);">
            <!-- Linha de métricas principais -->
            <div style="display: flex; justify-content: space-between; align-items: center;
                        margin-bottom: 16px;">
                <div style="text-align: center; flex: 1;">
                    <div style="font-size: 11px; color: var(--mg-text-muted);
                                text-transform: uppercase;
                                letter-spacing: 0.5px; margin-bottom: 4px;">
                        Média Atual
                    </div>
                    <div style="font-size: 22px; font-weight: 700; color: {cor_media};">
                        {formatar_moeda_compacta(media_du)}/dia
                    </div>
                </div>
                <div style="font-size: 24px; color: var(--mg-text-subtle); margin: 0 12px;">→</div>
                <div style="text-align: center; flex: 1;">
                    <div style="font-size: 11px; color: var(--mg-text-muted);
                                text-transform: uppercase;
                                letter-spacing: 0.5px; margin-bottom: 4px;">
                        Necessário
                    </div>
                    <div style="font-size: 22px; font-weight: 700; color: var(--mg-text);">
                        {formatar_moeda_compacta(media_necessaria)}/dia
                    </div>
                </div>
                <div style="font-size: 24px; color: var(--mg-text-subtle); margin: 0 12px;">→</div>
                <div style="text-align: center; flex: 1;">
                    <div style="font-size: 11px; color: var(--mg-text-muted);
                                text-transform: uppercase;
                                letter-spacing: 0.5px; margin-bottom: 4px;">
                        Projeção Fim
                    </div>
                    <div style="font-size: 22px; font-weight: 700; color: {cor_proj};">
                        {formatar_moeda_compacta(projecao)} ({formatar_percentual(perc_proj)})
                    </div>
                </div>
            </div>
            <!-- Barra de progresso temporal -->
            <div style="margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between;
                            font-size: 11px; color: var(--mg-text-muted); margin-bottom: 6px;">
                    <span>Início do mês</span>
                    <span>{du_decorridos} de {du_total} dias úteis ({perc_tempo:.0f}%)</span>
                    <span>Fechamento</span>
                </div>
                <div style="background: var(--mg-border); height: 8px;
                            border-radius: 4px; overflow: hidden;">
                    <div style="background: var(--mg-gradient-1);
                                width: {perc_tempo:.0f}%; height: 100%; border-radius: 4px;
                                transition: width 0.5s ease;"></div>
                </div>
            </div>
            <!-- Mensagem contextual -->
            <div style="display: flex; justify-content: center; gap: 24px;
                        font-size: 13px; color: var(--mg-text-muted);">
                <span><strong style="color: {cor_media};">{msg_desvio}</strong></span>
                <span>·</span>
                <span><strong style="color: {cor_proj};">{msg_fechamento}</strong></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _display_name_produto(produto: str) -> str:
    """Retorna nome amigável para produto do MIX."""
    nomes = {
        "CNC": "CNC",
        "CLT": "CLT",
        "SAQUE": "Saque",
        "CONSIGNADO": "Consignado",
        "FGTS_ANT_BEN_CNC13": "FGTS/Ant.Ben./13º",
    }
    return nomes.get(produto, produto)


def render_cards_produto_mix(
    metas_produto: List[Dict],
) -> None:
    """Renderiza cards compactos para cada produto do MIX."""
    if not metas_produto:
        return

    # Filtra apenas os 5 produtos principais do MIX
    produtos_mix = [
        p for p in metas_produto
        if p.get("produto", "") in {
            "CNC", "CLT", "SAQUE", "CONSIGNADO", "FGTS_ANT_BEN_CNC13"
        }
    ]
    if not produtos_mix:
        return

    st.markdown("---")
    st.markdown("### 🏷️ Produtos MIX")

    # 5 colunas para os 5 produtos
    cols = st.columns(len(produtos_mix))
    for col, prod in zip(cols, produtos_mix):
        nome = _display_name_produto(prod.get("produto", ""))
        valor = float(prod.get("valor_atual", 0) or 0)
        meta_total = float(prod.get("meta_total", 0) or 0)
        meta_dia = float(prod.get("meta_diaria", 0) or 0)
        media_du = float(prod.get("ritmo_diario", 0) or 0)
        perc = float(prod.get("perc_atingido", 0) or 0)

        cor = "#10A37F" if perc >= 100 else "#F59E0B" if perc >= 70 else "#EF4444"

        with col:
            st.markdown(
                f"""
                <div class="mg-kpi-context" style="padding: 14px 16px;">
                    <div class="mg-kpi-ctx-label" style="font-size: 12px;">
                        {nome}
                    </div>
                    <div class="mg-kpi-ctx-valor" style="font-size: 20px;">
                        {formatar_moeda(valor)}
                    </div>
                    <div class="mg-kpi-ctx-sub" style="font-size: 13px; line-height: 1.5;">
                        Meta: <strong>{formatar_moeda(meta_total)}</strong><br>
                        Meta/dia: <strong>{formatar_moeda(meta_dia)}</strong><br>
                        Média DU: <strong>{formatar_moeda(media_du)}</strong><br>
                        <span style="color: {cor}; font-weight: 600;">
                            {perc:.1f}%
                        </span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_cards_aceleradores(
    kpis_qtd: List[Dict],
) -> None:
    """Renderiza cards para Aceleradores (contados por quantidade)."""
    if not kpis_qtd:
        return

    st.markdown("---")
    st.markdown("### 🚀 Aceleradores")

    # 4 colunas para os 4 aceleradores
    cols = st.columns(len(kpis_qtd))
    for col, prod in zip(cols, kpis_qtd):
        nome = prod.get("nome", prod.get("produto", ""))
        qtd = int(prod.get("qtd_paga", 0) or 0)
        proj = int(prod.get("projecao", 0) or 0)
        media_du = float(prod.get("ritmo_diario", 0) or 0)
        qtd_analise = int(prod.get("qtd_analise", 0) or 0)

        with col:
            st.markdown(
                f"""
                <div class="mg-kpi-context" style="padding: 16px 18px;">
                    <div class="mg-kpi-ctx-label" style="font-size: 13px;">
                        {nome}
                    </div>
                    <div class="mg-kpi-ctx-valor" style="font-size: 24px;">
                        {qtd:,}
                    </div>
                    <div class="mg-kpi-ctx-sub" style="font-size: 14px; line-height: 1.6;">
                        Projeção: <strong>{proj:,}</strong><br>
                        Média DU: <strong>{media_du:.1f}</strong><br>
                        Análise: <strong>{qtd_analise:,}</strong>
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
    metas_produto: Optional[List[Dict]] = None,
    kpis_qtd: Optional[List[Dict]] = None,
    daily_pago: Optional[Sequence[float]] = None,
) -> None:
    """
    Renderiza o novo bloco de KPIs reformulado.

    Ordem:
    1. 3 KPIs principais (dominantes)
    2. KPIs de contexto
    3. Cards por produto MIX
    4. Cards Aceleradores (qtd)
    5. Ritmo + Projeção
    """
    # 1. KPIs Principais
    render_kpis_principais(kpis, kpis_analise, kpis_cancel, daily_pago)

    # Espaçamento
    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)

    # 2. KPIs de Contexto
    render_kpis_contexto(kpis, kpis_analise, kpis_cancel, medias)

    # 3. Cards por produto MIX
    render_cards_produto_mix(metas_produto)

    # 4. Cards Aceleradores (por quantidade)
    render_cards_aceleradores(kpis_qtd)

    # 5. Média e Projeção
    render_bloco_media_projecao(kpis)
