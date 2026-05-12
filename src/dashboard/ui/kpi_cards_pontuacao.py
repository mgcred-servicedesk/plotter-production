"""
KPI Cards do Dashboard de Pontuacao.

Espelha o esqueleto de ``kpi_cards_reforma.py`` (dashboard de vendas)
trocando R$ por pontos:

1. Cards principais: Pagos / % Meta Prata / Falta para Prata
2. Cards de contexto: Em Analise (pts) / % Perda / Media/Consultor /
   Media/Loja
3. Cards MIX por produto (pts com peso e fatia da Prata)
4. Bloco "Para Onde Estamos Indo" com referencias para Prata e Ouro

Aceleradores ficam fora deste modulo: continuam aparecendo na pagina
mas sao renderizados via ``prioridades_pontuacao`` sem entrar no
calculo de pontos.
"""

from typing import Dict, List, Optional

import streamlit as st

from src.dashboard.formatters import formatar_numero, formatar_percentual
from src.dashboard.ui.colors import (
    get_churn_status,
    get_ritmo_status,
    get_status_color,
    get_status_full,
)


def _fmt_pts(valor: float) -> str:
    """Formato compacto para pontos: 1.2M / 12,3K / 1.234."""
    if valor is None:
        return "0"
    valor = float(valor)
    if abs(valor) >= 1_000_000:
        return f"{valor / 1_000_000:.2f}M".replace(".", ",")
    if abs(valor) >= 1_000:
        return f"{valor / 1_000:.1f}K".replace(".", ",")
    return formatar_numero(valor)


def _fmt_pts_total(valor: float) -> str:
    """Formato completo (com separador de milhar)."""
    return f"{formatar_numero(valor or 0)} pts"


def render_kpis_principais_pts(kpis: Dict) -> None:
    """Linha dominante: Pagos / % Meta Prata / Falta para Prata."""
    total_pontos = float(kpis.get("total_pontos", 0) or 0)
    meta_prata = float(kpis.get("meta_prata", 0) or 0)
    meta_ouro = float(kpis.get("meta_ouro", 0) or 0)
    perc_prata = float(kpis.get("perc_ating_prata", 0) or 0)
    perc_ouro = float(kpis.get("perc_ating_ouro", 0) or 0)
    perc_proj = float(kpis.get("perc_proj", 0) or 0)
    projecao_pts = float(kpis.get("projecao_pontos", 0) or 0)
    du_restantes = max(int(kpis.get("du_restantes", 1) or 1), 1)

    gap_pontos = max(0.0, meta_prata - total_pontos)
    cor_status, _bg, _emoji, _label = get_status_full(perc_prata)

    pagos_fmt = _fmt_pts(total_pontos)
    pagos_total = _fmt_pts_total(total_pontos)
    proj_fmt = _fmt_pts(projecao_pts)
    prata_fmt = _fmt_pts(meta_prata)
    ouro_fmt = _fmt_pts(meta_ouro)

    card_pagos = f"""
        <div class="mg-kpi-hero" style="flex: 1.2;">
            <div class="mg-kpi-label">🏅 Pontos Pagos</div>
            <div class="mg-kpi-valor">{pagos_fmt}</div>
            <div class="mg-kpi-sub" style="font-size: 16px; font-weight: 500;">
                {pagos_total}
                <span style="color: var(--mg-text-muted); font-size: 14px;">
                    → Proj: {proj_fmt} pts
                </span>
            </div>
        </div>"""

    card_meta = f"""
        <div class="mg-kpi-hero" style="flex: 1;">
            <div class="mg-kpi-label">📊 % Meta Prata</div>
            <div class="mg-kpi-valor" style="color: {cor_status};">
                {formatar_percentual(perc_prata)}
            </div>
            <div class="mg-kpi-sub" style="font-size: 14px;">
                Projeção: {formatar_percentual(perc_proj)} ·
                Prata: {prata_fmt} pts<br>
                Ouro: {ouro_fmt} pts ({formatar_percentual(perc_ouro)})
            </div>
        </div>"""

    if gap_pontos > 0:
        gap_dia = gap_pontos / du_restantes
        card_gap = f"""
            <div class="mg-kpi-hero" style="flex: 1;">
                <div class="mg-kpi-label">🎯 Falta para Prata</div>
                <div class="mg-kpi-valor mg-kpi-gap">-{_fmt_pts(gap_pontos)}</div>
                <div class="mg-kpi-sub" style="font-size: 14px;">
                    Falta: {_fmt_pts_total(gap_pontos)}<br>
                    <strong>{_fmt_pts(gap_dia)} pts/dia</strong>
                </div>
            </div>"""
    else:
        card_gap = f"""
            <div class="mg-kpi-hero" style="flex: 1;">
                <div class="mg-kpi-label">🎯 Falta para Prata</div>
                <div class="mg-kpi-valor" style="color: #10A37F;">✓ Prata Atingida</div>
                <div class="mg-kpi-sub" style="font-size: 14px;">
                    +{_fmt_pts_total(abs(gap_pontos))} acima
                </div>
            </div>"""

    st.markdown(
        f'<div style="display:flex; gap:clamp(10px,1.2vw,20px); align-items:stretch;">'
        f"{card_pagos}{card_meta}{card_gap}"
        f"</div>",
        unsafe_allow_html=True,
    )


def render_kpis_contexto_pts(
    kpis: Dict,
    kpis_analise_pts: Dict,
    kpis_cancel_pts: Dict,
    medias_pts: Dict,
) -> None:
    """Linha secundaria: Em Analise / Cancelados (% perda) / Medias."""
    pontos_analise = float(kpis_analise_pts.get("pontos_analise", 0) or 0)
    qtd_analise = int(kpis_analise_pts.get("qtd_analise", 0) or 0)
    indice_perda = float(kpis_cancel_pts.get("indice_perda", 0) or 0)
    qtd_cancelados = int(kpis_cancel_pts.get("qtd_cancelados", 0) or 0)

    total_pontos = float(kpis.get("total_pontos", 0) or 0)
    num_consultores = int(
        medias_pts.get("num_consultores", 0)
        or kpis.get("num_consultores", 0)
        or 0
    )
    num_lojas = int(
        medias_pts.get("num_lojas", 0) or kpis.get("num_lojas", 0) or 0
    )
    media_consultor = (
        total_pontos / num_consultores if num_consultores > 0 else 0.0
    )
    media_loja = total_pontos / num_lojas if num_lojas > 0 else 0.0
    media_du_consultor = float(medias_pts.get("media_du_consultor_pontos", 0) or 0)
    media_du_loja = float(medias_pts.get("media_du_loja_pontos", 0) or 0)

    # Potencial: pipeline em pontos com taxa de conversao 35%
    # (mesma premissa do dashboard de vendas)
    taxa_conv = 0.35
    potencial = pontos_analise * taxa_conv

    cor_churn, emoji_churn, nivel_churn = get_churn_status(indice_perda)

    card_analise = f"""
        <div class="mg-kpi-context" style="flex: 1;">
            <div class="mg-kpi-ctx-label">⏳ Em Análise</div>
            <div class="mg-kpi-ctx-valor">{_fmt_pts(pontos_analise)}</div>
            <div class="mg-kpi-ctx-sub">
                <span style="font-size:12px;">{_fmt_pts_total(pontos_analise)}</span><br>
                {qtd_analise:,} propostas<br>
                💡 Se converter 35%: <strong>+{_fmt_pts(potencial)} pts</strong>
            </div>
        </div>"""

    card_cancel = f"""
        <div class="mg-kpi-context" style="flex: 1;">
            <div class="mg-kpi-ctx-label">⚠️ Cancelados</div>
            <div class="mg-kpi-ctx-valor" style="color: {cor_churn};">
                {formatar_percentual(indice_perda)}
            </div>
            <div class="mg-kpi-ctx-sub">
                {qtd_cancelados:,} cancelamentos {emoji_churn}<br>
                📉 Nível: <strong>{nivel_churn}</strong>
            </div>
        </div>"""

    card_consultor = f"""
        <div class="mg-kpi-context" style="flex: 1;">
            <div class="mg-kpi-ctx-label">👤 Média por Consultor</div>
            <div class="mg-kpi-ctx-valor">{_fmt_pts(media_consultor)}</div>
            <div class="mg-kpi-ctx-sub">
                <span style="font-size:12px;">{_fmt_pts_total(media_consultor)}</span><br>
                Acumulado entre {num_consultores:,} consultores<br>
                Média DU/consultor: <strong>{_fmt_pts(media_du_consultor)} pts</strong>
            </div>
        </div>"""

    card_loja = f"""
        <div class="mg-kpi-context" style="flex: 1;">
            <div class="mg-kpi-ctx-label">🏪 Média por Loja</div>
            <div class="mg-kpi-ctx-valor">{_fmt_pts(media_loja)}</div>
            <div class="mg-kpi-ctx-sub">
                <span style="font-size:12px;">{_fmt_pts_total(media_loja)}</span><br>
                Acumulado entre {num_lojas:,} lojas<br>
                Média DU/loja: <strong>{_fmt_pts(media_du_loja)} pts</strong>
            </div>
        </div>"""

    st.markdown(
        f'<div style="display:flex; gap:clamp(10px,1.2vw,20px); align-items:stretch;">'
        f"{card_analise}{card_cancel}{card_consultor}{card_loja}"
        f"</div>",
        unsafe_allow_html=True,
    )


_NOMES_MIX = {
    "CNC": "CNC",
    "CLT": "CLT",
    "SAQUE": "Saque",
    "CONSIGNADO": "Consignado",
    "FGTS_ANT_BEN_CNC13": "FGTS/Ant.Ben./13º",
}


def render_cards_mix_pts(mix_pontos: List[Dict]) -> None:
    """Cards horizontais para cada produto MIX em pontos."""
    if not mix_pontos:
        return

    st.markdown("---")

    cards_html = []
    for prod in mix_pontos:
        nome = _NOMES_MIX.get(prod.get("produto", ""), prod.get("produto", ""))
        pontos = float(prod.get("pontos_atual", 0) or 0)
        peso = float(prod.get("peso", 0) or 0)
        meta_dia = float(prod.get("meta_diaria_produto", 0) or 0)
        meta_fatia = float(prod.get("meta_prata_fatia", 0) or 0)
        perc = float(prod.get("perc_atingido", 0) or 0)

        cor = get_status_color(perc) if meta_fatia > 0 else "var(--mg-text-muted)"
        perc_txt = (
            f"<span style='color:{cor}; font-weight:600;'>"
            f"{formatar_percentual(perc)}</span>"
            if meta_fatia > 0
            else "<span style='color:var(--mg-text-muted);'>—</span>"
        )

        cards_html.append(
            f'<div class="mg-kpi-context" style="'
            f'min-width:clamp(180px, 20%, 260px); flex-shrink:0; '
            f'scroll-snap-align:start;">'
            f'<div class="mg-kpi-ctx-label">{nome}</div>'
            f'<div class="mg-kpi-ctx-valor">{_fmt_pts(pontos)}</div>'
            f'<div class="mg-kpi-ctx-sub">'
            f"Peso na produção: <strong>{formatar_percentual(peso)}</strong><br>"
            f"Meta/dia (Prata): <strong>{_fmt_pts(meta_dia)} pts</strong><br>"
            f"Fatia da Prata: <strong>{_fmt_pts(meta_fatia)} pts</strong><br>"
            f"Atingimento: {perc_txt}"
            f"</div></div>"
        )

    btn_style = (
        "background:var(--mg-surface); border:1px solid var(--mg-border); "
        "border-radius:8px; width:32px; height:32px; cursor:pointer; "
        "font-size:18px; line-height:1; display:flex; align-items:center; "
        "justify-content:center; box-shadow:var(--mg-shadow-sm); "
        "color:var(--mg-text); flex-shrink:0;"
    )
    st.markdown(
        f'<div style="display:flex; align-items:center; '
        f'justify-content:space-between; margin-bottom:12px;">'
        f'<span style="font-size:1.25rem; font-weight:700;">'
        f"🏷️ Produtos MIX (Pontuação)</span>"
        f'<div style="display:flex; gap:8px;">'
        f'<button id="mg-mix-pts-prev" style="{btn_style}">&#8249;</button>'
        f'<button id="mg-mix-pts-next" style="{btn_style}">&#8250;</button>'
        f"</div></div>"
        f'<div id="mg-mix-pts-scroll" style="display:flex; '
        f"gap:clamp(10px,1.2vw,20px); align-items:stretch; "
        f"overflow-x:auto; scroll-snap-type:x mandatory; "
        f'-webkit-overflow-scrolling:touch; padding-bottom:4px;">'
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
                var scroll = p.getElementById('mg-mix-pts-scroll');
                var prev   = p.getElementById('mg-mix-pts-prev');
                var next   = p.getElementById('mg-mix-pts-next');
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


def render_bloco_media_projecao_pts(kpis: Dict) -> None:
    """Bloco 'Para Onde Estamos Indo' em pontos com refs Prata e Ouro."""
    total_pontos = float(kpis.get("total_pontos", 0) or 0)
    meta_prata = float(kpis.get("meta_prata", 0) or 0)
    meta_ouro = float(kpis.get("meta_ouro", 0) or 0)
    projecao_pts = float(kpis.get("projecao_pontos", 0) or 0)
    media_du_pts = float(kpis.get("media_du_pontos", 0) or 0)
    du_total = max(int(kpis.get("du_total", 1) or 1), 1)
    du_dec = int(kpis.get("du_decorridos", 0) or 0)
    du_rest = max(int(kpis.get("du_restantes", 0) or 0), 0)

    gap_prata = max(0.0, meta_prata - total_pontos)
    gap_ouro = max(0.0, meta_ouro - total_pontos)
    necess_prata = gap_prata / du_rest if du_rest > 0 else 0.0
    necess_ouro = gap_ouro / du_rest if du_rest > 0 else 0.0

    perc_proj_prata = (
        (projecao_pts / meta_prata * 100) if meta_prata > 0 else 0.0
    )
    perc_proj_ouro = (
        (projecao_pts / meta_ouro * 100) if meta_ouro > 0 else 0.0
    )

    # Desvio do ritmo vs necessario p/ Prata (referencia primaria)
    desvio = (
        ((media_du_pts - necess_prata) / necess_prata * 100)
        if necess_prata > 0
        else 0.0
    )
    cor_media, _emoji_m, _status = get_ritmo_status(desvio)
    cor_proj_prata = get_status_color(perc_proj_prata)
    cor_proj_ouro = get_status_color(perc_proj_ouro)

    perc_tempo = (du_dec / du_total * 100) if du_total > 0 else 0.0

    msg_desvio = (
        f"{abs(desvio):.0f}% {'acima' if desvio > 0 else 'abaixo'} "
        f"do necessário p/ Prata"
        if necess_prata > 0
        else "Prata atingida"
    )
    msg_prata = (
        f"Projeção fecha {formatar_percentual(perc_proj_prata)} da Prata"
        if meta_prata > 0
        else ""
    )
    msg_ouro = (
        f"e {formatar_percentual(perc_proj_ouro)} da Ouro"
        if meta_ouro > 0
        else ""
    )

    st.markdown("---")
    st.markdown("### 📈 Para Onde Estamos Indo")

    st.markdown(
        f"""
        <div style="background: var(--mg-surface); border-radius: 12px;
                    padding: 20px; border: 1px solid var(--mg-border);">
            <div style="display: flex; justify-content: space-between;
                        align-items: center; margin-bottom: 16px;">
                <div style="text-align: center; flex: 1;">
                    <div style="font-size: 13px; color: var(--mg-text-muted);
                                text-transform: uppercase;
                                letter-spacing: 0.5px; margin-bottom: 4px;">
                        Média Atual
                    </div>
                    <div style="font-size: 24px; font-weight: 700; color: {cor_media};">
                        {_fmt_pts(media_du_pts)} pts/dia
                    </div>
                </div>
                <div style="font-size: 24px; color: var(--mg-text-subtle); margin: 0 12px;">→</div>
                <div style="text-align: center; flex: 1;">
                    <div style="font-size: 13px; color: var(--mg-text-muted);
                                text-transform: uppercase;
                                letter-spacing: 0.5px; margin-bottom: 4px;">
                        Necessário p/ Prata
                    </div>
                    <div style="font-size: 24px; font-weight: 700; color: var(--mg-text);">
                        {_fmt_pts(necess_prata)} pts/dia
                    </div>
                    <div style="font-size: 12px; color: var(--mg-text-muted);">
                        Ouro: {_fmt_pts(necess_ouro)} pts/dia
                    </div>
                </div>
                <div style="font-size: 24px; color: var(--mg-text-subtle); margin: 0 12px;">→</div>
                <div style="text-align: center; flex: 1;">
                    <div style="font-size: 13px; color: var(--mg-text-muted);
                                text-transform: uppercase;
                                letter-spacing: 0.5px; margin-bottom: 4px;">
                        Projeção Fim
                    </div>
                    <div style="font-size: 24px; font-weight: 700; color: {cor_proj_prata};">
                        {_fmt_pts(projecao_pts)} pts
                    </div>
                    <div style="font-size: 12px; color: var(--mg-text-muted);">
                        <span style="color:{cor_proj_prata};">
                            {formatar_percentual(perc_proj_prata)} Prata
                        </span>
                        ·
                        <span style="color:{cor_proj_ouro};">
                            {formatar_percentual(perc_proj_ouro)} Ouro
                        </span>
                    </div>
                </div>
            </div>
            <div style="margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between;
                            font-size: 13px; color: var(--mg-text-muted); margin-bottom: 6px;">
                    <span>Início do mês</span>
                    <span>{du_dec} de {du_total} dias úteis ({perc_tempo:.0f}%)</span>
                    <span>Fechamento</span>
                </div>
                <div style="background: var(--mg-border); height: 8px;
                            border-radius: 4px; overflow: hidden;">
                    <div style="background: var(--mg-gradient-1);
                                width: {perc_tempo:.0f}%; height: 100%; border-radius: 4px;
                                transition: width 0.5s ease;"></div>
                </div>
            </div>
            <div style="display: flex; justify-content: center; gap: 24px;
                        font-size: 14px; color: var(--mg-text-muted);">
                <span><strong style="color: {cor_media};">{msg_desvio}</strong></span>
                <span>·</span>
                <span><strong style="color: {cor_proj_prata};">{msg_prata}</strong>
                {msg_ouro}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_kpis_pontuacao(
    kpis: Dict,
    kpis_analise_pts: Dict,
    kpis_cancel_pts: Dict,
    medias_pts: Dict,
    mix_pontos: Optional[List[Dict]] = None,
) -> None:
    """Orquestra os blocos principais da pagina de pontuacao."""
    render_kpis_principais_pts(kpis)
    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
    render_kpis_contexto_pts(kpis, kpis_analise_pts, kpis_cancel_pts, medias_pts)
    render_cards_mix_pts(mix_pontos or [])
    render_bloco_media_projecao_pts(kpis)
