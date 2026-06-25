"""
Resumo Executivo Automático — Prioridade 1 da Reforma UX/UI.

Gera narrativa visual estruturada baseada nos KPIs do dashboard.
Usa st.html() para CSS e st.markdown() para conteúdo (Streamlit 1.56+)
"""

from typing import Dict, List, Optional

import streamlit as st

from src.dashboard.formatters import formatar_moeda_compacta


CSS_RESUMO = """
<style>
.mg-resumo-card {
    background: var(--mg-surface);
    border-radius: 16px;
    border: 1px solid var(--mg-border);
    overflow: hidden;
    margin-bottom: 24px;
    box-shadow: var(--mg-shadow-md);
}
.mg-resumo-header {
    background: var(--mg-primary);
    color: white;
    padding: 12px 20px;
    font-size: 14px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.mg-resumo-body {
    padding: 20px;
}
.mg-status-box {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 16px;
    border-radius: 12px;
    margin-bottom: 16px;
}
.mg-status-success {
    background: var(--mg-success-soft);
    border-left: 4px solid var(--mg-success);
}
.mg-status-warning {
    background: var(--mg-warning-soft);
    border-left: 4px solid var(--mg-warning);
}
.mg-status-danger {
    background: var(--mg-danger-soft);
    border-left: 4px solid var(--mg-danger);
}
.mg-status-icon { font-size: 24px; }
.mg-status-text { font-size: 18px; font-weight: 700; color: var(--mg-text); }
.mg-info-row {
    display: flex;
    gap: 24px;
    padding: 12px 16px;
    background: var(--mg-hover-bg);
    border-radius: 8px;
    margin-bottom: 16px;
}
.mg-info-item { font-size: 15px; color: var(--mg-text-muted); }
.mg-info-item strong { color: var(--mg-text); }
.mg-text-success { color: var(--mg-success); font-weight: 600; }
.mg-text-warning { color: var(--mg-warning); font-weight: 600; }
.mg-text-danger  { color: var(--mg-danger);  font-weight: 600; }
.mg-divider { border-top: 1px dashed var(--mg-border-strong); margin: 16px 0; }
.mg-section-title {
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    color: var(--mg-text-muted);
    letter-spacing: 0.5px;
    margin-bottom: 10px;
}
.mg-tags { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
.mg-tag {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 6px 12px;
    border-radius: 20px;
    font-size: 13px;
    font-weight: 500;
}
.mg-tag-up   { background: var(--mg-success-soft); color: var(--mg-success); }
.mg-tag-down { background: var(--mg-danger-soft);  color: var(--mg-danger);  }
.mg-pills { display: flex; gap: 8px; flex-wrap: wrap; }
.mg-pill {
    display: inline-flex;
    align-items: center;
    padding: 6px 12px;
    border-radius: 16px;
    font-size: 12px;
    font-weight: 500;
}
.mg-pill-red {
    background: var(--mg-danger-soft);
    color: var(--mg-danger);
    border: 1px solid var(--mg-danger);
}
.mg-pill-yellow {
    background: var(--mg-warning-soft);
    color: var(--mg-warning);
    border: 1px solid var(--mg-warning);
}
.mg-pill-blue {
    background: var(--mg-primary-soft);
    color: var(--mg-primary);
    border: 1px solid var(--mg-primary);
}
.mg-pill-green {
    background: var(--mg-success-soft);
    color: var(--mg-success);
    border: 1px solid var(--mg-success);
}
.mg-status-sub {
    font-size: 13px;
    color: var(--mg-text-muted);
    margin-top: 3px;
}
.mg-metric-grid {
    display: grid;
    gap: 10px;
    margin-bottom: 16px;
}
.mg-metric-grid-3 { grid-template-columns: repeat(3, 1fr); }
.mg-metric-grid-2 { grid-template-columns: repeat(2, 1fr); }
.mg-metric-item {
    background: var(--mg-hover-bg);
    border-radius: 10px;
    padding: 12px 14px;
    border: 1px solid var(--mg-border);
}
.mg-metric-label {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    color: var(--mg-text-muted);
    letter-spacing: 0.5px;
    margin-bottom: 4px;
}
.mg-metric-value {
    font-size: 20px;
    font-weight: 700;
    color: var(--mg-text);
    line-height: 1.2;
}
.mg-metric-sub {
    font-size: 12px;
    color: var(--mg-text-muted);
    margin-top: 3px;
    line-height: 1.4;
}
</style>
"""


def render_resumo_executivo(
    kpis: Dict,
    kpis_analise: Dict,
    kpis_cancel: Dict,
    metas_produto: List[Dict],
    produtos_criticos: Optional[List[Dict]] = None,
    regioes_criticas: Optional[List[Dict]] = None,
) -> None:
    """Renderiza o bloco de Resumo Executivo estruturado."""

    # ── KPIs de valor MIX (base R$) ──────────────────────────────────────
    total_vendas = kpis.get("total_vendas", 0)
    meta_mix = kpis.get("meta_mix", 0)
    perc_ating = kpis.get("perc_ating_valor", 0)
    gap = kpis.get("gap_valor", 0)
    du_restantes = kpis.get("du_restantes", 1)
    ritmo_atual = kpis.get("media_du", 0)

    # Proj. MIX em valor (R$/meta_mix) — mesma base que perc_ating e gap_valor
    projecao = kpis.get("projecao", 0)
    perc_proj_mix = (projecao / meta_mix * 100) if meta_mix > 0 else 0

    # Proj. Prata em pontos — base diferente (meta_prata); mantida para contexto
    perc_proj_prata = kpis.get("perc_proj", 0)

    # Velocidade
    ritmo_necessario = gap / du_restantes if gap > 0 and du_restantes > 0 else 0
    desvio_ritmo = (
        ((ritmo_atual - ritmo_necessario) / ritmo_necessario * 100)
        if ritmo_necessario > 0
        else 0
    )

    # Pipeline e cancelamentos
    valor_analise = kpis_analise.get("valor_analise", 0)
    potencial_pipeline = valor_analise * 0.35
    impacto_pipeline = (potencial_pipeline / meta_mix * 100) if meta_mix > 0 else 0

    valor_cancelados = kpis_cancel.get("valor_cancelados", 0)
    indice_perda = kpis_cancel.get("indice_perda", 0)
    impacto_cancel = (valor_cancelados / meta_mix * 100) if meta_mix > 0 else 0

    # Contencao de redigitacao: contratos cancelados redigitados
    # (fora da conta de cancelados) e os recuperados (pagos em 7 dias).
    qtd_redigitadas = kpis_cancel.get("qtd_redigitadas", 0)
    qtd_recuperadas = kpis_cancel.get("qtd_recuperadas", 0)

    # Produtos (FIX: chave correta é "perc_atingido" de calcular_metas_produto_diarias)
    produtos_acima = []
    produtos_abaixo = []
    for prod in metas_produto:
        if prod.get("is_mix", False):
            continue
        if not float(prod.get("meta_total", 0) or 0) > 0:
            continue
        perc = float(prod.get("perc_atingido", 0) or 0)
        nome = prod.get("produto_display", prod.get("produto", ""))
        gap_prod = max(
            0.0,
            float(prod.get("meta_total", 0)) - float(prod.get("valor_atual", 0)),
        )
        if perc >= 100:
            produtos_acima.append({"nome": nome, "perc": perc})
        elif perc < 60:
            produtos_abaixo.append({"nome": nome, "perc": perc, "gap": gap_prod})
    produtos_abaixo.sort(key=lambda x: x["perc"])

    # ── Status headline ───────────────────────────────────────────────────
    if meta_mix <= 0:
        status_class = "mg-status-warning"
        status_icon = "ℹ️"
        status_text = "Sem meta definida para o período"
    elif perc_ating >= 100:
        status_class = "mg-status-success"
        status_icon = "✅"
        status_text = f"Meta MIX atingida — {perc_ating:.1f}% em valor (R$)"
    elif perc_ating >= 80:
        status_class = "mg-status-warning"
        status_icon = "⚠️"
        status_text = f"{perc_ating:.1f}% da meta MIX atingida (R$)"
    else:
        status_class = "mg-status-danger"
        status_icon = "🚨"
        status_text = f"Apenas {perc_ating:.1f}% da meta MIX atingida (R$)"

    if meta_mix <= 0:
        status_sub = (
            f"Realizado: {formatar_moeda_compacta(total_vendas)} · Sem meta definida"
        )
    else:
        status_sub = (
            f"Realizado: {formatar_moeda_compacta(total_vendas)} de "
            f"{formatar_moeda_compacta(meta_mix)} · "
            f"Faltam: {formatar_moeda_compacta(gap)}"
        )

    # ── Cores por faixa de atingimento ───────────────────────────────────
    proj_mix_class = (
        "mg-text-success" if perc_proj_mix >= 100
        else ("mg-text-warning" if perc_proj_mix >= 80 else "mg-text-danger")
    )
    proj_prata_class = (
        "mg-text-success" if perc_proj_prata >= 100
        else ("mg-text-warning" if perc_proj_prata >= 80 else "mg-text-danger")
    )

    # ── Velocidade: formato do ritmo necessário (usado nas pills) ──────────────
    ritmo_nec_fmt = (
        formatar_moeda_compacta(ritmo_necessario) if ritmo_necessario > 0 else "—"
    )

    # ── Tags de produtos ──────────────────────────────────────────────────
    tags_html = ""
    for p in produtos_abaixo[:2]:
        tags_html += (
            f'<span class="mg-tag mg-tag-down">'
            f'📉 {p["nome"]} · {p["perc"]:.0f}% · falta {formatar_moeda_compacta(p["gap"])}'
            f'</span>'
        )
    for p in produtos_acima[:1]:
        tags_html += (
            f'<span class="mg-tag mg-tag-up">'
            f'📈 {p["nome"]} · {p["perc"]:.0f}%'
            f'</span>'
        )

    # ── Pills de prioridades ──────────────────────────────────────────────
    pills_html = ""
    if desvio_ritmo < -20 and ritmo_necessario > 0:
        pills_html += (
            f'<span class="mg-pill mg-pill-red">'
            f'🔥 Ritmo {abs(desvio_ritmo):.0f}% abaixo — meta {ritmo_nec_fmt}/dia'
            f'</span>'
        )
    if indice_perda > 20:
        pills_html += (
            f'<span class="mg-pill mg-pill-yellow">'
            f'⚠️ Cancelamento {indice_perda:.1f}% · -{impacto_cancel:.1f}% da meta MIX'
            f'</span>'
        )
    if qtd_redigitadas > 0:
        extra_recup = (
            f' · {qtd_recuperadas} recuperadas' if qtd_recuperadas else ''
        )
        pills_html += (
            f'<span class="mg-pill mg-pill-yellow">'
            f'🔁 {qtd_redigitadas} contratos redigitados (fora dos cancelados)'
            f'{extra_recup}'
            f'</span>'
        )
    if produtos_abaixo:
        top = produtos_abaixo[0]
        pills_html += (
            f'<span class="mg-pill mg-pill-blue">'
            f'🎯 Foco: {top["nome"]} ({top["perc"]:.0f}%)'
            f'</span>'
        )
    if impacto_pipeline > 5 and valor_analise > 0:
        pills_html += (
            f'<span class="mg-pill mg-pill-green">'
            f'💡 Pipeline: +{impacto_pipeline:.1f}% potencial'
            f'</span>'
        )
    if regioes_criticas and regioes_criticas[0].get("regiao"):
        pills_html += (
            f'<span class="mg-pill mg-pill-blue">'
            f'📍 {regioes_criticas[0]["regiao"]}'
            f'</span>'
        )
    if not pills_html:
        pills_html = '<span class="mg-pill mg-pill-blue">✅ Tudo sob controle</span>'

    # ── Bloco condicional de produtos ─────────────────────────────────────
    produtos_block = (
        f'<div class="mg-section-title">Produtos em Destaque</div>'
        f'<div class="mg-tags">{tags_html}</div>'
        if tags_html
        else ""
    )

    # ── Montagem do card ──────────────────────────────────────────────────
    html_card = (
        f'{CSS_RESUMO}'
        f'<div class="mg-resumo-card">'
        f'<div class="mg-resumo-header">📋 RESUMO EXECUTIVO</div>'
        f'<div class="mg-resumo-body">'
        f'<div class="mg-status-box {status_class}">'
        f'<span class="mg-status-icon">{status_icon}</span>'
        f'<div>'
        f'<div class="mg-status-text">{status_text}</div>'
        f'<div class="mg-status-sub">{status_sub}</div>'
        f'</div>'
        f'</div>'
        f'<div class="mg-section-title">📈 Projeções do Período</div>'
        f'<div class="mg-metric-grid mg-metric-grid-3">'
        f'<div class="mg-metric-item">'
        f'<div class="mg-metric-label">Proj. MIX</div>'
        f'<div class="mg-metric-value {proj_mix_class}">{perc_proj_mix:.1f}%</div>'
        f'<div class="mg-metric-sub">Projeção em valor financeiro</div>'
        f'</div>'
        f'<div class="mg-metric-item">'
        f'<div class="mg-metric-label">Proj. Geral</div>'
        f'<div class="mg-metric-value {proj_prata_class}">{perc_proj_prata:.1f}%</div>'
        f'<div class="mg-metric-sub">Projeção Prata</div>'
        f'</div>'
        f'<div class="mg-metric-item">'
        f'<div class="mg-metric-label">Dias Úteis Restantes</div>'
        f'<div class="mg-metric-value">{du_restantes}</div>'
        f'<div class="mg-metric-sub">'
        f'{"Sem meta definida" if meta_mix <= 0 else f"Gap: {formatar_moeda_compacta(gap)}"}'
        f'</div>'
        f'</div>'
        f'</div>'
        f'{produtos_block}'
        f'<div class="mg-divider"></div>'
        f'<div class="mg-section-title">Ações Prioritárias</div>'
        f'<div class="mg-pills">{pills_html}</div>'
        f'</div>'
        f'</div>'
    )

    st.html(html_card)
