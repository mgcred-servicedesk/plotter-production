"""
KPI Cards Reformulados — Prioridade 2 da Reforma UX/UI.

Novo layout: 3 KPIs principais dominantes + KPIs de contexto.
- Realizado (fonte grande, destaque)
- % Meta (com indicador visual de status)
- Falta (faltante para meta)

Cores semânticas: Verde (>100%), Amarelo (60-99%), Vermelho (<60%)
"""

import math
from typing import Dict, List, Optional, Sequence

import streamlit as st

from src.dashboard.formatters import (
    formatar_moeda,
    formatar_moeda_compacta,
    formatar_percentual,
)
from src.dashboard.ui.colors import (
    get_status_color,
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
        | REALIZADO | % META | FALTA |

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

    # Linha dos 3 KPIs principais
    meta_mix = kpis.get("meta_mix", 0)
    du_restantes = kpis.get("du_restantes", 1)
    projecao = kpis.get("projecao", 0)
    # perc_proj em VALOR (projecao R$ / meta_mix), coerente com perc_ating_valor.
    # kpis["perc_proj"] global é projecao_pts/meta_prata — base diferente.
    perc_proj = (projecao / meta_mix * 100) if meta_mix > 0 else 0

    pagos_fmt = _formatar_valor_moeda(total_vendas)
    pagos_total = _formatar_valor_moeda_total(total_vendas)
    proj_fmt = _formatar_valor_moeda(projecao)
    meta_mix_fmt = _formatar_valor_moeda_total(meta_mix)

    card_pagos = f"""
        <div class="mg-kpi-hero" style="flex: 1.2;">
            <div class="mg-kpi-label">💰 Pagos</div>
            <div class="mg-kpi-valor">{pagos_fmt}</div>
            <div class="mg-kpi-sub" style="font-size: 16px; font-weight: 500;">
                {pagos_total}
                <span style="color: var(--mg-text-muted); font-size: 14px;">
                    → Proj: {proj_fmt}
                </span>
            </div>
        </div>"""

    if meta_mix > 0:
        card_meta = f"""
            <div class="mg-kpi-hero" style="flex: 1;">
                <div class="mg-kpi-label">📊 % Meta Atingida</div>
                <div class="mg-kpi-valor" style="color: {cor_status};">
                    {formatar_percentual(perc_ating)}
                </div>
                <div class="mg-kpi-sub" style="font-size: 14px;">
                    Projeção: {formatar_percentual(perc_proj)} |
                    MIX: {meta_mix_fmt}
                </div>
            </div>"""
    else:
        card_meta = """
            <div class="mg-kpi-hero" style="flex: 1;">
                <div class="mg-kpi-label">📊 % Meta Atingida</div>
                <div class="mg-kpi-valor" style="color: var(--mg-text-muted);">—</div>
                <div class="mg-kpi-sub" style="font-size: 14px;">
                    Sem meta definida
                </div>
            </div>"""

    if meta_mix <= 0:
        card_gap = """
            <div class="mg-kpi-hero" style="flex: 1;">
                <div class="mg-kpi-label">🎯 Falta para Meta</div>
                <div class="mg-kpi-valor" style="color: var(--mg-text-muted);">—</div>
                <div class="mg-kpi-sub" style="font-size: 14px;">
                    Sem meta definida
                </div>
            </div>"""
    elif gap > 0:
        gap_fmt = _formatar_valor_moeda(gap)
        gap_por_dia = gap / du_restantes if du_restantes > 1 else gap
        gap_por_dia_fmt = _formatar_valor_moeda(gap_por_dia)
        card_gap = f"""
            <div class="mg-kpi-hero" style="flex: 1;">
                <div class="mg-kpi-label">🎯 Falta para Meta</div>
                <div class="mg-kpi-valor mg-kpi-gap">-{gap_fmt}</div>
                <div class="mg-kpi-sub" style="font-size: 14px;">
                    Falta: {_formatar_valor_moeda_total(gap)}<br>
                    <strong>{gap_por_dia_fmt}/dia</strong>
                </div>
            </div>"""
    else:
        card_gap = f"""
            <div class="mg-kpi-hero" style="flex: 1;">
                <div class="mg-kpi-label">🎯 Falta para Meta</div>
                <div class="mg-kpi-valor" style="color: #10A37F;">✓ Meta Atingida</div>
                <div class="mg-kpi-sub" style="font-size: 14px;">
                    +{_formatar_valor_moeda_total(abs(gap))} acima
                </div>
            </div>"""

    st.markdown(
        f'<div style="display:flex; gap:clamp(10px,1.2vw,20px); align-items:stretch;">'
        f"{card_pagos}{card_meta}{card_gap}"
        f"</div>",
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

    # Linha de contexto — flex container único para altura uniforme
    cor_churn, emoji_churn, nivel_churn = get_churn_status(indice_perda)

    card_analise = f"""
        <div class="mg-kpi-context" style="flex: 1;">
            <div class="mg-kpi-ctx-label">⏳ Em Análise</div>
            <div class="mg-kpi-ctx-valor">{_formatar_valor_moeda(valor_analise)}</div>
            <div class="mg-kpi-ctx-sub">
                <span style="font-size:12px;">{formatar_moeda(valor_analise)}</span><br>
                {qtd_analise:,} propostas<br>
                💡 Se converter 35%: <strong>+{_formatar_valor_moeda(potencial)}</strong>
            </div>
        </div>"""

    card_cancel = f"""
        <div class="mg-kpi-context" style="flex: 1;">
            <div class="mg-kpi-ctx-label">⚠️ Cancelados</div>
            <div class="mg-kpi-ctx-valor">{_formatar_valor_moeda(valor_cancel)}</div>
            <div class="mg-kpi-ctx-sub">
                <span style="font-size:12px;">{formatar_moeda(valor_cancel)}</span><br>
                % Cancelamento:
                <strong style="color: {cor_churn};">{formatar_percentual(indice_perda)}</strong>
                {emoji_churn}<br>
                📉 Nível: <strong>{nivel_churn}</strong>
                | Impacto: <strong>-{impacto_cancel:.1f}% da meta</strong>
            </div>
        </div>"""

    card_consultor = f"""
        <div class="mg-kpi-context" style="flex: 1;">
            <div class="mg-kpi-ctx-label">👤 Média por Consultor</div>
            <div class="mg-kpi-ctx-valor">{_formatar_valor_moeda(media_consultor)}</div>
            <div class="mg-kpi-ctx-sub">
                <span style="font-size:12px;">{formatar_moeda(media_consultor)}</span><br>
                Acumulado entre {num_consultores:,} consultores<br>
                Média DU/consultor: <strong>{_formatar_valor_moeda(media_du_consultor)}</strong>
            </div>
        </div>"""

    card_loja = f"""
        <div class="mg-kpi-context" style="flex: 1;">
            <div class="mg-kpi-ctx-label">🏪 Média por Loja</div>
            <div class="mg-kpi-ctx-valor">{_formatar_valor_moeda(media_loja)}</div>
            <div class="mg-kpi-ctx-sub">
                <span style="font-size:12px;">{formatar_moeda(media_loja)}</span><br>
                Acumulado entre {num_lojas:,} lojas<br>
                Média DU/loja: <strong>{_formatar_valor_moeda(media_du_loja)}</strong>
            </div>
        </div>"""

    st.markdown(
        f'<div style="display:flex; gap:clamp(10px,1.2vw,20px); align-items:stretch;">'
        f"{card_analise}{card_cancel}{card_consultor}{card_loja}"
        f"</div>",
        unsafe_allow_html=True,
    )


def render_bloco_media_projecao(kpis: Dict) -> None:
    """
    Renderiza o bloco de Média vs Meta e Projeção.
    Design compacto unificado: Média → Necessário → Projeção
    """
    from src.dashboard.ui.colors import get_status_color

    projecao = kpis.get("projecao", 0)
    meta_mix = kpis.get("meta_mix", 1)
    media_du = kpis.get("media_du", 0)
    total_vendas = kpis.get("total_vendas", 0)
    du_restantes = kpis.get("du_restantes", 1)
    du_total = kpis.get("du_total", 1)
    du_decorridos = kpis.get("du_decorridos", 1)

    # perc_proj precisa estar na mesma base do resto do card (valor vs meta MIX).
    # O kpis["perc_proj"] global é projecao_pts/meta_prata (pontos vs Prata),
    # o que geraria incoerência com média/necessário/projeção em R$ vs MIX.
    perc_proj = (projecao / meta_mix * 100) if meta_mix > 0 else 0

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
    cor_proj = (
        get_status_color(perc_proj) if meta_mix > 0 else "var(--mg-text)"
    )
    projecao_fmt = (
        f"{formatar_moeda_compacta(projecao)} ({formatar_percentual(perc_proj)})"
        if meta_mix > 0
        else formatar_moeda_compacta(projecao)
    )

    # Progresso temporal: percentual de dias úteis decorridos
    perc_tempo = (
        (du_decorridos / du_total * 100) if du_total > 0 else 0
    )

    # Mensagem contextual
    meta_atingida = meta_mix > 0 and total_vendas >= meta_mix
    periodo_encerrado = du_restantes <= 0
    if meta_mix <= 0:
        msg_desvio = "Sem meta definida"
    elif meta_atingida:
        msg_desvio = "Meta atingida"
    elif periodo_encerrado:
        msg_desvio = "Período encerrado — meta não atingida"
    else:
        msg_desvio = (
            f"{abs(desvio):.0f}% "
            f"{'acima' if desvio > 0 else 'abaixo'} do necessário"
        )
    if meta_mix <= 0:
        msg_fechamento = ""
    else:
        verbo = "Fechamos" if periodo_encerrado else "Fecharemos"
        direcao = "acima" if perc_proj >= 100 else "abaixo"
        msg_fechamento = (
            f"{verbo} {abs(100 - perc_proj):.0f}% {direcao} da meta"
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
                    <div style="font-size: 13px; color: var(--mg-text-muted);
                                text-transform: uppercase;
                                letter-spacing: 0.5px; margin-bottom: 4px;">
                        Média Atual
                    </div>
                    <div style="font-size: 24px; font-weight: 700; color: {cor_media};">
                        {formatar_moeda_compacta(media_du)}/dia
                    </div>
                </div>
                <div style="font-size: 24px; color: var(--mg-text-subtle); margin: 0 12px;">→</div>
                <div style="text-align: center; flex: 1;">
                    <div style="font-size: 13px; color: var(--mg-text-muted);
                                text-transform: uppercase;
                                letter-spacing: 0.5px; margin-bottom: 4px;">
                        Necessário
                    </div>
                    <div style="font-size: 24px; font-weight: 700; color: var(--mg-text);">
                        {formatar_moeda_compacta(media_necessaria)}/dia
                    </div>
                </div>
                <div style="font-size: 24px; color: var(--mg-text-subtle); margin: 0 12px;">→</div>
                <div style="text-align: center; flex: 1;">
                    <div style="font-size: 13px; color: var(--mg-text-muted);
                                text-transform: uppercase;
                                letter-spacing: 0.5px; margin-bottom: 4px;">
                        Projeção Fim
                    </div>
                    <div style="font-size: 24px; font-weight: 700; color: {cor_proj};">
                        {projecao_fmt}
                    </div>
                </div>
            </div>
            <!-- Barra de progresso temporal -->
            <div style="margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between;
                            font-size: 13px; color: var(--mg-text-muted); margin-bottom: 6px;">
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
                        font-size: 14px; color: var(--mg-text-muted);">
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


def _calcular_indicador_media(
    valor_atual: float, media_org: float
) -> tuple[str, str, str, str]:
    """
    Calcula indicador visual de comparação com média da organização.

    Compara a Média DU do perfil contra a Média DU empresa (mesma
    granularidade conceitual: ritmo diário). Faróis:
      - Acima (>= +10%): verde
      - Na média (-10% a +10%): amarelo
      - Abaixo (<= -10%): vermelho

    Retorna: (emoji, cor, label, descricao)
    """
    if media_org <= 0:
        return "➡️", "#6B7280", "—", "Sem dados"

    razao = valor_atual / media_org
    perc_diff = (razao - 1) * 100

    if razao >= 1.10:
        return (
            "🟢",
            "#10A37F",
            f"+{perc_diff:.0f}%",
            "Acima da média",
        )
    elif razao <= 0.90:
        return (
            "🔴",
            "#EF4444",
            f"{perc_diff:.0f}%",
            "Abaixo da média",
        )
    else:
        return (
            "🟡",
            "#F59E0B",
            f"{perc_diff:+.0f}%",
            "Na média",
        )


def render_cards_produto_mix(
    metas_produto: List[Dict],
    medias_organizacao: Optional[Dict[str, float]] = None,
    perfil: Optional[str] = None,
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

    # Perfis que devem ver o comparativo com média da organização.
    # A granularidade da "média empresa" é definida em
    # ``calcular_medias_organizacao`` (gerais.py):
    #   - gerente_comercial: média DU entre regiões (sem ALEXANDRE)
    #   - supervisor: média DU entre lojas
    #   - consultor: média DU entre consultores (sem supervisores)
    perfis_comparativo = {"gerente_comercial", "supervisor", "consultor"}
    mostrar_comparativo = perfil in perfis_comparativo

    st.markdown("---")

    # Cards MIX — carrossel horizontal estilo Netflix
    cards_html = []
    for prod in produtos_mix:
        nome = _display_name_produto(prod.get("produto", ""))
        valor = float(prod.get("valor_atual", 0) or 0)
        meta_total = float(prod.get("meta_total", 0) or 0)
        meta_dia = float(prod.get("meta_diaria", 0) or 0)
        media_du = float(prod.get("ritmo_diario", 0) or 0)
        projecao = float(prod.get("projecao", 0) or 0)
        perc_proj = float(prod.get("perc_projecao", 0) or 0)

        # Indicador de comparação com média da organização.
        # IMPORTANTE: comparamos a Média DU do perfil (`media_du`)
        # com a Média DU empresa (`media_org`) — ambas no mesmo
        # ritmo diário, calculadas em ``calcular_medias_organizacao``.
        if mostrar_comparativo and medias_organizacao:
            media_org = float(
                medias_organizacao.get(prod.get("produto", ""), 0) or 0
            )
            emoji, cor_ind, label_ind, descricao = (
                _calcular_indicador_media(media_du, media_org)
            )
            linha_comparativo = (
                f'<div style="margin-top: 6px; padding-top: 6px; '
                f'border-top: 1px solid var(--mg-border);">'
                f'<span style="font-size: 13px; color: var(--mg-text-muted);">'
                f'Média empresa: </span>'
                f'<strong style="color: {cor_ind};">{formatar_moeda(media_org)}</strong> '
                f'<span style="color: {cor_ind}; font-size: 13px;">'
                f'{emoji} {descricao} ({label_ind})</span></div>'
            )
        else:
            if meta_total <= 0:
                linha_comparativo = (
                    "<span style='color: var(--mg-text-muted);'>"
                    "Sem meta neste período</span>"
                )
            else:
                perc = float(prod.get("perc_atingido", 0) or 0)
                cor = (
                    "#10A37F" if perc >= 100
                    else "#F59E0B" if perc >= 70
                    else "#EF4444"
                )
                linha_comparativo = (
                    f"Atingimento: <span style='color: {cor}; font-weight: 600;'>"
                    f"{perc:.1f}%</span>"
                )

        cor_proj = (
            "#10A37F" if perc_proj >= 100
            else "#F59E0B" if perc_proj >= 70
            else "#EF4444"
        )
        cards_html.append(
            f'<div class="mg-kpi-context" style="'
            f'min-width:clamp(180px, 20%, 260px); flex-shrink:0; scroll-snap-align:start;">'
            f'<div class="mg-kpi-ctx-label">{nome}</div>'
            f'<div class="mg-kpi-ctx-valor">{formatar_moeda(valor)}</div>'
            f'<div class="mg-kpi-ctx-sub">'
            f'Meta: <strong>{formatar_moeda(meta_total)}</strong><br>'
            f'Meta/dia: <strong>{formatar_moeda(meta_dia)}</strong><br>'
            f'Média DU: <strong>{formatar_moeda(media_du)}</strong><br>'
            f'Projeção: <strong>{formatar_moeda(projecao)}</strong>'
            f'<span style="font-size:12px; color:{cor_proj};">({perc_proj:.1f}%)</span><br>'
            f'{linha_comparativo}'
            f'</div></div>'
        )

    btn_style = (
        "background:var(--mg-surface); border:1px solid var(--mg-border); "
        "border-radius:8px; width:32px; height:32px; cursor:pointer; "
        "font-size:18px; line-height:1; display:flex; align-items:center; "
        "justify-content:center; box-shadow:var(--mg-shadow-sm); "
        "color:var(--mg-text); flex-shrink:0;"
    )
    # Botões sem onclick — JS anexado via st.iframe (same-origin)
    # porque React descarta atributos onclick ao renderizar via dangerouslySetInnerHTML
    st.markdown(
        f'<div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:12px;">'
        f'<span style="font-size:1.25rem; font-weight:700;">🏷️ Produtos MIX</span>'
        f'<div style="display:flex; gap:8px;">'
        f'<button id="mg-mix-prev" style="{btn_style}">&#8249;</button>'
        f'<button id="mg-mix-next" style="{btn_style}">&#8250;</button>'
        f'</div></div>'
        f'<div id="mg-mix-scroll" style="display:flex; gap:clamp(10px,1.2vw,20px); align-items:stretch; '
        f'overflow-x:auto; scroll-snap-type:x mandatory; -webkit-overflow-scrolling:touch; '
        f'padding-bottom:4px;">'
        + "".join(cards_html)
        + "</div>",
        unsafe_allow_html=True,
    )
    st.iframe(
        """
        <script>
        (function () {
            function attach() {
                var p = window.parent.document;
                var scroll = p.getElementById('mg-mix-scroll');
                var prev   = p.getElementById('mg-mix-prev');
                var next   = p.getElementById('mg-mix-next');
                if (!scroll || !prev || !next) { setTimeout(attach, 100); return; }
                prev.onclick = function () { scroll.scrollBy({ left: -216, behavior: 'smooth' }); };
                next.onclick = function () { scroll.scrollBy({ left:  216, behavior: 'smooth' }); };
            }
            attach();
        })();
        </script>
        """,
        height=1,
    )


def render_cards_aceleradores(
    kpis_qtd: List[Dict],
    perfil: str = "",
) -> None:
    """Renderiza cards para Aceleradores (contados por quantidade)."""
    if not kpis_qtd:
        return

    st.markdown("---")
    st.markdown("### 🚀 Aceleradores")

    _usa_ref = perfil in ("supervisor", "consultor")
    _label_ref = (
        "Média p/ Loja" if perfil == "supervisor"
        else "Média p/ Consultor" if perfil == "consultor"
        else "Média DU"
    )

    # Cards Aceleradores — flex container único para altura uniforme
    cards_html = []
    for prod in kpis_qtd:
        nome = prod.get("nome", prod.get("produto", ""))
        qtd = int(prod.get("qtd_paga", 0) or 0)
        proj = int(prod.get("projecao", 0) or 0)
        qtd_analise = int(prod.get("qtd_analise", 0) or 0)
        if _usa_ref and prod.get("media_ref") is not None:
            val_comp = int(round(float(prod["media_ref"])))
        else:
            val_comp = int(round(float(prod.get("ritmo_diario", 0) or 0)))
        cards_html.append(
            f'<div class="mg-kpi-context" style="flex: 1;">'
            f'<div class="mg-kpi-ctx-label">{nome}</div>'
            f'<div class="mg-kpi-ctx-valor">{qtd:,}</div>'
            f'<div class="mg-kpi-ctx-sub">'
            f'Projeção: <strong>{proj:,}</strong><br>'
            f'{_label_ref}: <strong>{val_comp:,}</strong><br>'
            f'Análise: <strong>{qtd_analise:,}</strong>'
            f'</div></div>'
        )

    st.markdown(
        '<div style="display:flex; gap:clamp(10px,1.2vw,20px); align-items:stretch;">'
        + "".join(cards_html)
        + "</div>",
        unsafe_allow_html=True,
    )


_MESES_RECONQ = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
}


def render_cards_reconquista(
    dados: Optional[Dict],
    mes: int,
    ano: int,
) -> None:
    """Bloco resumido de KPIs do Reconquista MG CRED (v2).

    Renderiza 4 cards minimalistas (Clientes do mês, Efetivadas,
    Promessas, Sem reconquista) no estilo `mg-kpi-context`. A
    apuracao é mensal por dt_fim_relacionamento com defasagem de
    1 mes (ja resolvida no loader). No-op se `dados` for vazio.
    """
    if not dados:
        return

    totais = dados.get("totais") or {}
    total = int(totais.get("total", 0))

    ref_mes = dados.get("ref_mes")
    ref_ano = dados.get("ref_ano")
    ref_label = (
        f"{_MESES_RECONQ.get(ref_mes, '?')}/{ref_ano}" if ref_mes else "—"
    )

    st.markdown("---")
    st.markdown("### 🎯 Reconquista")
    st.caption(
        f"Apuração {_MESES_RECONQ.get(mes, '?')}/{ano} · fim de "
        f"relacionamento em **{ref_label}**"
    )

    if total == 0:
        st.info(
            f"Sem contratos com fim de relacionamento em {ref_label}."
        )
        return

    efet = int(totais.get("efetivadas", 0))
    prom = int(totais.get("promessas", 0))
    sem = int(totais.get("sem_reconquista", 0))
    taxa = float(totais.get("taxa", 0.0))
    meta = float(totais.get("meta", 0.0))

    pct_efet = efet / total * 100 if total else 0.0
    pct_prom = prom / total * 100 if total else 0.0
    pct_sem = sem / total * 100 if total else 0.0

    cor_taxa = get_status_color(taxa / meta * 100 if meta > 0 else 0)
    delta_pp = taxa - meta
    sinal_pp = "+" if delta_pp >= 0 else ""

    # Quantas efetivações ainda faltam para atingir a meta no mês.
    alvo_meta = math.ceil(total * meta / 100) if meta > 0 else 0
    gap_meta = max(0, alvo_meta - efet)
    gap_txt = (
        f"Faltam <strong>{gap_meta}</strong> p/ meta"
        if gap_meta > 0
        else "✓ meta atingida"
    )

    # Taxa que a base alcançaria se todas as promessas virassem efetivadas.
    taxa_potencial = (efet + prom) / total * 100 if total else 0.0

    # Quantos clientes "sem reconquista" precisam virar promessa para que
    # a projeção (efetivadas + promessas) alcance a meta.
    estimular = max(0, alvo_meta - efet - prom)
    if estimular > 0:
        _cli = "cliente" if estimular == 1 else "clientes"
        estim_txt = f"Estimule <strong>{estimular}</strong> {_cli} a dar o aceite"
    else:
        estim_txt = "✓ aceites suficientes p/ meta"

    # Variação das promessas vs o período de apuração anterior.
    prom_ant = int(totais.get("promessas_anterior", 0))
    if prom_ant > 0:
        var_prom = (prom - prom_ant) / prom_ant * 100
        if var_prom > 0:
            seta_prom, cor_prom = "▲", "#10A37F"
        elif var_prom < 0:
            seta_prom, cor_prom = "▼", "#E5484D"
        else:
            seta_prom, cor_prom = "→", "var(--mg-text-muted)"
        var_prom_html = (
            f'<span style="color: {cor_prom};">'
            f'{seta_prom} {abs(var_prom):.1f}%</span> vs período ant.'
        )
    elif prom > 0:
        var_prom_html = '<span style="opacity: 0.8;">novo vs período ant.</span>'
    else:
        var_prom_html = '<span style="opacity: 0.8;">— vs período ant.</span>'

    card_total = (
        f'<div class="mg-kpi-context" style="flex: 1;">'
        f'<div class="mg-kpi-ctx-label">📋 Clientes do mês</div>'
        f'<div class="mg-kpi-ctx-valor">{total:,}</div>'
        f'<div class="mg-kpi-ctx-sub">Fim de relacionamento {ref_label}</div>'
        f'</div>'
    ).replace(",", ".")

    card_efet = (
        f'<div class="mg-kpi-context" style="flex: 1;">'
        f'<div class="mg-kpi-ctx-label">✅ Efetivadas</div>'
        f'<div class="mg-kpi-ctx-valor" style="color: {cor_taxa};">{efet:,}</div>'
        f'<div class="mg-kpi-ctx-sub">'
        f'{pct_efet:.1f}% · meta <strong>{meta:.0f}%</strong> '
        f'(<strong style="color: {cor_taxa};">{sinal_pp}{delta_pp:.1f} pp</strong>)'
        f'<br><span style="opacity: 0.8;">{gap_txt}</span>'
        f'</div>'
        f'</div>'
    ).replace(",", ".")

    card_prom = (
        f'<div class="mg-kpi-context" style="flex: 1;">'
        f'<div class="mg-kpi-ctx-label">⏳ Promessas</div>'
        f'<div class="mg-kpi-ctx-valor">{prom:,}</div>'
        f'<div class="mg-kpi-ctx-sub">'
        f'{pct_prom:.1f}% · {var_prom_html}'
        f'<br><span style="opacity: 0.8;">Se efetivadas: '
        f'<strong>{taxa_potencial:.1f}%</strong> da base</span>'
        f'</div>'
        f'</div>'
    ).replace(",", ".")

    card_sem = (
        f'<div class="mg-kpi-context" style="flex: 1;">'
        f'<div class="mg-kpi-ctx-label">🎯 Sem reconquista</div>'
        f'<div class="mg-kpi-ctx-valor">{sem:,}</div>'
        f'<div class="mg-kpi-ctx-sub">'
        f'{pct_sem:.1f}% · a trabalhar'
        f'<br><span style="opacity: 0.8;">{estim_txt}</span>'
        f'</div>'
        f'</div>'
    ).replace(",", ".")

    st.markdown(
        '<div style="display:flex; gap:clamp(10px,1.2vw,20px); align-items:stretch;">'
        + card_total + card_efet + card_prom + card_sem
        + '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div style="margin-top: 12px; padding: 10px 16px; '
        'background: var(--mg-surface); border: 1px solid var(--mg-border); '
        'border-left: 3px solid var(--mg-primary); '
        'border-radius: var(--mg-radius-md); '
        'font-size: clamp(12px, 0.85vw, 13px); color: var(--mg-text-muted); '
        'line-height: 1.45;">'
        'ℹ️&nbsp; O resultado definitivo, com o percentual alcançado por cada '
        'loja, será divulgado após a virada da maciça.'
        '</div>',
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
    medias_organizacao: Optional[Dict[str, float]] = None,
    perfil: Optional[str] = None,
    reconquista: Optional[Dict] = None,
    mes: Optional[int] = None,
    ano: Optional[int] = None,
) -> None:
    """
    Renderiza o novo bloco de KPIs reformulado.

    Ordem:
    1. 3 KPIs principais (dominantes)
    2. KPIs de contexto
    3. Cards por produto MIX
    4. Cards Aceleradores (qtd)
    5. Cards Reconquista (resumo da maciça ativa)
    6. Ritmo + Projeção
    """
    # 1. KPIs Principais
    render_kpis_principais(kpis, kpis_analise, kpis_cancel, daily_pago)

    # Espaçamento
    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)

    # 2. KPIs de Contexto
    render_kpis_contexto(kpis, kpis_analise, kpis_cancel, medias)

    # 3. Cards por produto MIX
    render_cards_produto_mix(
        metas_produto,
        medias_organizacao=medias_organizacao,
        perfil=perfil,
    )

    # 4. Cards Aceleradores (por quantidade)
    render_cards_aceleradores(kpis_qtd, perfil=perfil or "")

    # 5. Cards Reconquista
    if reconquista is not None and mes is not None and ano is not None:
        render_cards_reconquista(reconquista, mes, ano)

    # 6. Média e Projeção
    render_bloco_media_projecao(kpis)
