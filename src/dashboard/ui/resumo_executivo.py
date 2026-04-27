"""
Resumo Executivo Automático — Prioridade 1 da Reforma UX/UI.

Gera narrativa visual estruturada baseada nos KPIs do dashboard.
Usa st.html() para CSS e st.markdown() para conteúdo (Streamlit 1.56+)
"""

from typing import Dict, List, Optional

import streamlit as st


CSS_RESUMO = """
<style>
.mg-resumo-card {
    background: var(--background-color, #fafafa);
    border-radius: 16px;
    border: 1px solid var(--border-color, #e5e7eb);
    overflow: hidden;
    margin-bottom: 24px;
    box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
}
.mg-resumo-header {
    background: linear-gradient(135deg, var(--primary-color, #3b82f6) 0%, var(--primary-color, #3b82f6) 100%);
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
.mg-status-success { background: #dcfce7; border-left: 4px solid #22c55e; }
.mg-status-warning { background: #fef3c7; border-left: 4px solid #f59e0b; }
.mg-status-danger { background: #fee2e2; border-left: 4px solid #ef4444; }
.mg-status-icon { font-size: 24px; }
.mg-status-text { font-size: 18px; font-weight: 700; color: #1f2937; }
.mg-info-row {
    display: flex;
    gap: 24px;
    padding: 12px 16px;
    background: #f3f4f6;
    border-radius: 8px;
    margin-bottom: 16px;
}
.mg-info-item { font-size: 15px; color: #374151; }
.mg-info-item strong { color: #111827; }
.mg-text-success { color: #22c55e; font-weight: 600; }
.mg-text-warning { color: #f59e0b; font-weight: 600; }
.mg-text-danger { color: #ef4444; font-weight: 600; }
.mg-divider { border-top: 1px dashed #d1d5db; margin: 16px 0; }
.mg-section-title {
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    color: #6b7280;
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
.mg-tag-up { background: #dcfce7; color: #166534; }
.mg-tag-down { background: #fee2e2; color: #991b1b; }
.mg-pills { display: flex; gap: 8px; flex-wrap: wrap; }
.mg-pill {
    display: inline-flex;
    align-items: center;
    padding: 6px 12px;
    border-radius: 16px;
    font-size: 12px;
    font-weight: 500;
}
.mg-pill-red { background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
.mg-pill-yellow { background: #fef3c7; color: #92400e; border: 1px solid #fde68a; }
.mg-pill-blue { background: #dbeafe; color: #1e40af; border: 1px solid #bfdbfe; }
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

    # Extrair valores. % e gap aqui são em VALOR (R$), usando a meta-mix
    # global (soma das metas por produto). `perc_ating_prata` é em pontos.
    perc_ating = kpis.get("perc_ating_valor", 0)
    perc_proj = kpis.get("perc_proj", 0)
    gap = kpis.get("gap_valor", 0)
    du_restantes = kpis.get("du_restantes", 1)
    ritmo_atual = kpis.get("media_du", 1)

    ritmo_necessario = gap / du_restantes if gap > 0 and du_restantes > 0 else 0
    desvio_ritmo = (
        ((ritmo_atual - ritmo_necessario) / ritmo_necessario * 100)
        if ritmo_necessario > 0
        else 0
    )
    indice_perda = kpis_cancel.get("indice_perda", 0)

    # Produtos
    produtos_acima = []
    produtos_abaixo = []
    for prod in metas_produto:
        if prod.get("is_mix", False):
            continue
        perc = prod.get("perc_atingimento", 0)
        nome = prod.get("produto_display", prod.get("produto", ""))
        if perc >= 100:
            produtos_acima.append(nome)
        elif perc < 60:
            produtos_abaixo.append(nome)

    # Status
    if perc_ating >= 100:
        status_class = "mg-status-success"
        status_icon = "✅"
        status_text = f"Atingimos {perc_ating:.1f}% da meta"
    elif perc_ating >= 80:
        status_class = "mg-status-warning"
        status_icon = "⚠️"
        status_text = f"Estamos com {perc_ating:.1f}% da meta atingida"
    else:
        status_class = "mg-status-danger"
        status_icon = "🚨"
        status_text = f"Estamos com {perc_ating:.1f}% da meta, abaixo do esperado"

    # Cores de projeção
    if perc_proj >= 100:
        proj_class = "mg-text-success"
    elif perc_proj >= 80:
        proj_class = "mg-text-warning"
    else:
        proj_class = "mg-text-danger"

    gap_fmt = f"R$ {gap / 1e6:.2f}M".replace(".", ",") if gap > 0 else "R$ 0,00"

    # Tags de produtos
    tags_html = ""
    for nome in produtos_abaixo[:2]:
        tags_html += f'<span class="mg-tag mg-tag-down">📉 {nome}</span>'
    for nome in produtos_acima[:1]:
        tags_html += f'<span class="mg-tag mg-tag-up">📈 {nome}</span>'

    # Pills de prioridades
    pills_html = ""
    if desvio_ritmo < -20:
        pills_html += f'<span class="mg-pill mg-pill-red">🔥 Ritmo {abs(desvio_ritmo):.0f}% abaixo</span>'
    if indice_perda > 20:
        pills_html += (
            f'<span class="mg-pill mg-pill-yellow">⚠️ Churn {indice_perda:.1f}%</span>'
        )
    if produtos_abaixo:
        pills_html += (
            f'<span class="mg-pill mg-pill-blue">🎯 Foco: {produtos_abaixo[0]}</span>'
        )
    if regioes_criticas and regioes_criticas[0].get("regiao"):
        pills_html += f'<span class="mg-pill mg-pill-blue">📍 {regioes_criticas[0]["regiao"]}</span>'

    produtos_block = (
        f'<div class="mg-section-title">Produtos em Destaque</div>'
        f'<div class="mg-tags">{tags_html}</div>'
        if tags_html
        else ""
    )
    pills_block = (
        pills_html
        if pills_html
        else '<span class="mg-pill mg-pill-blue">✅ Tudo sob controle</span>'
    )

    html_card = (
        f'{CSS_RESUMO}'
        f'<div class="mg-resumo-card">'
        f'<div class="mg-resumo-header">📋 RESUMO EXECUTIVO</div>'
        f'<div class="mg-resumo-body">'
        f'<div class="mg-status-box {status_class}">'
        f'<span class="mg-status-icon">{status_icon}</span>'
        f'<span class="mg-status-text">{status_text}</span>'
        f'</div>'
        f'<div class="mg-info-row">'
        f'<span class="mg-info-item">📈 <strong>Projeção:</strong> '
        f'<span class="{proj_class}">{perc_proj:.1f}%</span></span>'
        f'<span class="mg-info-item">🎯 <strong>Gap:</strong> '
        f'<span class="mg-text-danger">{gap_fmt}</span> faltantes</span>'
        f'</div>'
        f'{produtos_block}'
        f'<div class="mg-divider"></div>'
        f'<div class="mg-section-title">Ações Prioritárias</div>'
        f'<div class="mg-pills">{pills_block}</div>'
        f'</div>'
        f'</div>'
    )

    st.html(html_card)
