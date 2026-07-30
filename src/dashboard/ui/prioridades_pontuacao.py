"""
Prioridades de Acao do Dashboard de Pontuacao.

Foco: peso de cada produto MIX em pontos vs pontos em analise, com
insights para Meta Prata e Meta Ouro.

Os Aceleradores continuam visiveis (reuso de
``render_prioridades_aceleradores`` de ``prioridades_acao``), mas
apenas como referencia visual em quantidade — eles nao entram no
calculo de pontos da pagina.
"""

from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

from src.config.settings import PACK_LABEL_AGREGADO
from src.dashboard.formatters import formatar_numero, formatar_percentual
from src.dashboard.ui.colors import (
    get_status_bg_color,
    get_status_color,
    get_status_label,
)
from src.dashboard.ui.prioridades_acao import render_prioridades_aceleradores


_NOMES_MIX = {
    "CNC": "CNC",
    "CLT": "CLT",
    "SAQUE": "Saque",
    "CONSIGNADO": "Consignado",
    "FGTS_ANT_BEN_CNC13": PACK_LABEL_AGREGADO,
}


def _fmt_pts(valor: float) -> str:
    valor = float(valor or 0)
    if abs(valor) >= 1_000_000:
        return f"{valor / 1_000_000:.2f}M".replace(".", ",")
    if abs(valor) >= 1_000:
        return f"{valor / 1_000:.1f}K".replace(".", ",")
    return formatar_numero(valor)


def _html_card_produto_pts(i: int, prio: Dict) -> str:
    """Card por produto: peso, pontos pagos, pontos em analise,
    e quanto fecharia da Meta Prata e Ouro se converter."""
    nome = _NOMES_MIX.get(prio["produto"], prio["produto"])
    pontos_pagos = float(prio.get("pontos_pagos", 0) or 0)
    pontos_analise = float(prio.get("pontos_analise", 0) or 0)
    qtd_analise = int(prio.get("qtd_analise", 0) or 0)
    peso = float(prio.get("peso_atual", 0) or 0)
    fecha_prata = float(prio.get("fecha_prata_pct", 0) or 0)
    fecha_ouro = float(prio.get("fecha_ouro_pct", 0) or 0)
    gap_prata = float(prio.get("gap_prata", 0) or 0)
    gap_ouro = float(prio.get("gap_ouro", 0) or 0)

    # Cor do card vem do impacto na Prata (gap mais imediato)
    cor = get_status_color(fecha_prata)
    bg_cor = get_status_bg_color(fecha_prata)
    label = get_status_label(fecha_prata) if gap_prata > 0 else "Atingida"

    badge_topo = (
        f'<span class="mg-prioridade-badge" '
        f'style="background: {bg_cor}; color: {cor};">'
        f"Peso {formatar_percentual(peso)}</span>"
    )

    linha_pagos = (
        f'<div class="mg-prioridade-detalhe">'
        f"💰 <strong>{_fmt_pts(pontos_pagos)} pts pagos</strong> · "
        f"peso {formatar_percentual(peso)} na produção MIX</div>"
    )

    if pontos_analise > 0:
        cor_prata = get_status_color(fecha_prata) if gap_prata > 0 else "#10A37F"
        cor_ouro = get_status_color(fecha_ouro) if gap_ouro > 0 else "#10A37F"

        if gap_prata <= 0:
            txt_prata = "Prata já atingida"
        elif fecha_prata >= 100:
            txt_prata = (
                f"<span style='color:{cor_prata};font-weight:600;'>"
                f"fecha 100% da Prata</span> "
                f"<em>(sobra +{_fmt_pts(pontos_analise - gap_prata)} pts)</em>"
            )
        else:
            txt_prata = (
                f"<span style='color:{cor_prata};font-weight:600;'>"
                f"fecha {formatar_percentual(fecha_prata)} da Prata</span> "
                f"<em>(faltariam {_fmt_pts(gap_prata - pontos_analise)} pts)</em>"
            )

        if gap_ouro <= 0:
            txt_ouro = "Ouro já atingida"
        elif fecha_ouro >= 100:
            txt_ouro = (
                f"<span style='color:{cor_ouro};font-weight:600;'>"
                f"fecha 100% da Ouro</span>"
            )
        else:
            txt_ouro = (
                f"<span style='color:{cor_ouro};font-weight:600;'>"
                f"fecha {formatar_percentual(fecha_ouro)} da Ouro</span>"
            )

        linha_analise = (
            f'<div class="mg-prioridade-detalhe" style="margin-top:4px;">'
            f"📋 <strong>{qtd_analise} em análise</strong> · "
            f"{_fmt_pts(pontos_analise)} pts potenciais → {txt_prata}"
            f"</div>"
            f'<div class="mg-prioridade-detalhe" style="margin-top:4px;">'
            f"🥇 Para a Meta Ouro: {txt_ouro}</div>"
        )
    else:
        linha_analise = (
            '<div class="mg-prioridade-detalhe" style="margin-top:4px;">'
            "📋 Sem contratos em análise para este produto.</div>"
        )

    return (
        f'<div class="mg-prioridade-card" style="border-left-color: {cor};">'
        f'<div style="display: flex; align-items: center;">'
        f'<span class="mg-prioridade-numero" style="background: {cor};">{i}</span>'
        f'<span class="mg-prioridade-titulo">{nome} {badge_topo}'
        f'<span class="mg-prioridade-badge" style="background: {bg_cor}; color: {cor}; '
        f'margin-left:6px;">{label}</span></span></div>'
        f"{linha_pagos}{linha_analise}"
        f"</div>"
    )


def _render_lista(prios: List[Dict], top_n: int) -> None:
    if not prios:
        st.success("Sem prioridades em pontos — ótimo cenário!")
        return

    visiveis = prios[:top_n]
    restantes = prios[top_n:]

    html = "".join(
        _html_card_produto_pts(i + 1, p) for i, p in enumerate(visiveis)
    )
    st.markdown(html, unsafe_allow_html=True)

    if restantes:
        with st.expander(f"Ver mais {len(restantes)} produtos"):
            html_rest = "".join(
                _html_card_produto_pts(top_n + i + 1, p)
                for i, p in enumerate(restantes)
            )
            st.markdown(html_rest, unsafe_allow_html=True)


def render_prioridades_pontuacao(
    prioridades: List[Dict],
    df: pd.DataFrame,
    df_metas_produto: pd.DataFrame,
    df_sup: Optional[pd.DataFrame] = None,
    perfil: str = "",
) -> None:
    """Renderiza o bloco 'Onde Agir Agora' focado em pontos.

    Args:
        prioridades: saida de ``calcular_prioridades_pontuacao``.
        df: contratos pagos (pos-RLS+filtros) — usado pelos
            aceleradores em quantidade.
        df_metas_produto: metas por produto pos-RLS.
        df_sup: supervisores pos-RLS (opcional, usado em aceleradores).
        perfil: role efetivo, para a logica dos aceleradores.
    """
    if df_sup is None:
        df_sup = pd.DataFrame()

    st.markdown("---")
    st.markdown("### 🎯 Onde Agir Agora (Prioridades em Pontos)")
    st.caption(
        "Peso de cada produto na produção paga em pontos e quanto o "
        "pipeline em análise fecharia das Metas Prata e Ouro."
    )

    # CSS — mesmo padrao visual de prioridades_acao
    st.markdown(
        """
        <style>
        .mg-prioridade-card {
            background: var(--mg-surface);
            border-radius: 12px;
            padding: 16px 20px;
            margin-bottom: 12px;
            border-left: 4px solid var(--mg-primary);
            transition: all 0.2s ease;
        }
        .mg-prioridade-card:hover {
            transform: translateX(4px);
            box-shadow: var(--mg-shadow-sm);
        }
        .mg-prioridade-numero {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 28px;
            height: 28px;
            background: var(--mg-primary);
            color: white;
            font-size: 14px;
            font-weight: 700;
            border-radius: 50%;
            margin-right: 12px;
        }
        .mg-prioridade-titulo {
            font-size: 16px;
            font-weight: 600;
            color: var(--mg-text);
        }
        .mg-prioridade-detalhe {
            font-size: 14px;
            color: var(--mg-text-muted);
            margin-left: 40px;
            margin-top: 4px;
        }
        .mg-prioridade-badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 13px;
            font-weight: 600;
            margin-left: 8px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    _render_lista(prioridades, top_n=5)

    # Aceleradores em quantidade — exibidos como referencia,
    # nao entram em pontos.
    render_prioridades_aceleradores(df, df_metas_produto, df_sup, perfil)

    # Acao recomendada: produto com maior potencial em pontos no pipeline
    if prioridades:
        top = prioridades[0]
        nome_top = _NOMES_MIX.get(top["produto"], top["produto"])
        pontos_an = float(top.get("pontos_analise", 0) or 0)
        if pontos_an > 0:
            fecha = float(top.get("fecha_prata_pct", 0) or 0)
            if top.get("gap_prata", 0) <= 0:
                acao_txt = (
                    f"Prata já atingida. Focar em <strong>{nome_top}</strong> "
                    f"para alavancar Ouro: {_fmt_pts(pontos_an)} pts em análise."
                )
            else:
                acao_txt = (
                    f"Converter os <strong>{int(top.get('qtd_analise', 0))} contratos</strong> "
                    f"de <strong>{nome_top}</strong> em análise "
                    f"({_fmt_pts(pontos_an)} pts) fecharia "
                    f"<strong>{formatar_percentual(fecha)}</strong> do gap da Prata."
                )
            st.markdown(
                f"""
                <div style="background: var(--mg-primary-soft);
                            border: 1px solid var(--mg-primary-ring);
                            padding: 16px 20px; border-radius: 12px;
                            margin-top: 16px;">
                    <div style="font-size: 14px; font-weight: 600;
                                color: var(--mg-primary);
                                margin-bottom: 4px;">
                        💡 Ação Recomendada
                    </div>
                    <div style="color: var(--mg-primary); font-size: 14px;">
                        {acao_txt}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
