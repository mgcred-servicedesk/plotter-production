"""
Prioridades de Ação — Prioridade 3 da Reforma UX/UI.

Identifica automaticamente onde a equipe deve focar:
- Produtos com maior gap
- Regiões com pior desempenho
- Lojas com pior desempenho
- Consultores abaixo do esperado
"""

from typing import Dict, List

import pandas as pd
import streamlit as st

from src.dashboard.formatters import formatar_moeda, formatar_percentual
from src.dashboard.ui.colors import (
    get_status_color,
    get_status_bg_color,
    get_status_label,
)


# Colunas de meta em `df_metas_produto` que NÃO estão em R$
# (são quantidades de produtos contados por unidade). Devem ficar
# fora do somatório quando a meta a calcular é em valor.
# Fonte: src/dashboard/kpis/gerais.py::_PRODUTOS_QTD
_META_PRODUTO_QTD_COLS = {
    "EMISSAO",
    "SUPER_CONTA",
    "BMG_MED",
    "VIDA_FAMILIAR",
}


def calcular_prioridades_produto(
    metas_produto: List[Dict],
    top_n: int = 3,
) -> List[Dict]:
    """
    Identifica os produtos com maior prioridade de ação.

    Critérios:
    1. Menor % de atingimento
    2. Maior gap financeiro absoluto

    Returns:
        Lista de dicts com: produto, perc_ating, gap_valor, prioridade
    """
    prioridades = []

    for prod in metas_produto:
        if prod.get("is_mix", False):
            continue

        perc = float(prod.get("perc_atingido", 0) or 0)
        valor_atual = float(prod.get("valor_atual", 0) or 0)
        meta_total = float(prod.get("meta_total", 0) or 0)
        gap_valor = max(0.0, meta_total - valor_atual)

        # Score de prioridade: quanto menor o %, maior a prioridade
        # Peso: 70% % atingimento, 30% gap financeiro (em milhões)
        score = (100 - perc) * 0.7 + (gap_valor / 1_000_000) * 0.3

        # Só inclui produtos com meta cadastrada e abaixo dela
        if meta_total > 0 and perc < 100:
            prioridades.append(
                {
                    "produto": prod.get("produto", ""),
                    "perc_ating": perc,
                    "gap_valor": gap_valor,
                    "score": score,
                }
            )

    # Ordenar por prioridade (maior score primeiro)
    prioridades.sort(key=lambda x: x["score"], reverse=True)
    return prioridades[:top_n]


def calcular_prioridades_loja(
    df: pd.DataFrame,
    df_metas_produto: pd.DataFrame,
    top_n: int = 4,
) -> List[Dict]:
    """
    Identifica as lojas com maior prioridade de ação.

    Mesmo raciocínio de calcular_prioridades_regiao, mas agregado
    ao nível de loja individual.

    Returns:
        Lista de dicts com: loja, regiao, perc_ating, valor, meta, score
    """
    if df.empty or "LOJA" not in df.columns:
        return []

    # Meta por loja em valor: usa apenas a coluna MIX (meta em R$).
    meta_por_loja: Dict[str, float] = {}
    if not df_metas_produto.empty and "LOJA" in df_metas_produto.columns:
        if "MIX" in df_metas_produto.columns:
            meta_por_loja = dict(
                zip(
                    df_metas_produto["LOJA"],
                    pd.to_numeric(df_metas_produto["MIX"], errors="coerce")
                    .fillna(0)
                    .astype(float),
                )
            )

    # Mapeamento LOJA → REGIAO para exibição
    loja_regiao = {}
    if "REGIAO" in df.columns:
        loja_regiao = (
            df[["LOJA", "REGIAO"]]
            .drop_duplicates()
            .set_index("LOJA")["REGIAO"]
            .to_dict()
        )

    prioridades = []
    for loja in df["LOJA"].dropna().unique():
        df_loja = df[df["LOJA"] == loja]
        valor_realizado = (
            float(df_loja["VALOR"].sum()) if "VALOR" in df_loja.columns else 0.0
        )

        meta_loja = float(meta_por_loja.get(loja, 0.0))
        perc = (valor_realizado / meta_loja * 100) if meta_loja > 0 else 0

        if meta_loja > 0 and perc < 100:
            prioridades.append(
                {
                    "loja": loja,
                    "regiao": loja_regiao.get(loja, ""),
                    "perc_ating": perc,
                    "valor": valor_realizado,
                    "meta": meta_loja,
                    "score": 100 - perc,
                }
            )

    prioridades.sort(key=lambda x: x["score"], reverse=True)
    return prioridades[:top_n]


def calcular_prioridades_regiao(
    df: pd.DataFrame,
    df_metas_produto: pd.DataFrame,
    top_n: int = 3,
) -> List[Dict]:
    """
    Identifica as regiões com maior prioridade de ação.

    Meta regional em VALOR (R$) = soma da coluna MIX do df_metas_produto
    (coluna MIX = meta em valor de todos os produtos da loja), agregada por
    região via mapping LOJA → REGIAO presente em ``df``.

    Returns:
        Lista de dicts com: regiao, perc_ating, valor, meta, score
    """
    if df.empty or "REGIAO" not in df.columns or "LOJA" not in df.columns:
        return []

    # Meta por loja em valor: usa apenas a coluna MIX (meta em R$).
    # A coluna MIX representa o mix total de produtos em valor monetário.
    # Não somar outras colunas (CNC, FGTS, etc) pois já estão no MIX.
    meta_por_loja: Dict[str, float] = {}
    if not df_metas_produto.empty and "LOJA" in df_metas_produto.columns:
        if "MIX" in df_metas_produto.columns:
            meta_por_loja = dict(
                zip(
                    df_metas_produto["LOJA"],
                    pd.to_numeric(df_metas_produto["MIX"], errors="coerce")
                    .fillna(0)
                    .astype(float),
                )
            )

    # Mapping LOJA → REGIAO (a partir de df, fonte canônica)
    loja_regiao = df[["LOJA", "REGIAO"]].drop_duplicates().set_index("LOJA")["REGIAO"]

    prioridades = []
    for regiao in df["REGIAO"].dropna().unique():
        df_reg = df[df["REGIAO"] == regiao]
        valor_realizado = (
            float(df_reg["VALOR"].sum()) if "VALOR" in df_reg.columns else 0.0
        )

        lojas_regiao = [loja for loja, reg in loja_regiao.items() if reg == regiao]
        meta_regiao = float(sum(meta_por_loja.get(loja, 0.0) for loja in lojas_regiao))

        perc = (valor_realizado / meta_regiao * 100) if meta_regiao > 0 else 0

        if meta_regiao > 0 and perc < 100:
            prioridades.append(
                {
                    "regiao": regiao,
                    "perc_ating": perc,
                    "valor": valor_realizado,
                    "meta": meta_regiao,
                    "score": 100 - perc,
                }
            )

    prioridades.sort(key=lambda x: x["score"], reverse=True)
    return prioridades[:top_n]


def render_prioridades_acao(
    metas_produto: List[Dict],
    df: pd.DataFrame,
    df_metas_produto: pd.DataFrame,
    kpis: Dict,
) -> None:
    """
    Renderiza o bloco de Prioridades de Ação.

    Layout:
    - Lista numerada de prioridades
    - Produtos críticos
    - Regiões críticas
    """
    st.markdown("---")
    st.markdown("### 🎯 Onde Agir Agora (Prioridades)")

    # Calcular prioridades
    prioridades_prod = calcular_prioridades_produto(metas_produto, top_n=3)
    prioridades_reg = calcular_prioridades_regiao(df, df_metas_produto, top_n=2)
    prioridades_loja = calcular_prioridades_loja(df, df_metas_produto, top_n=4)

    # Container principal
    css_prioridades = """
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
    """
    st.markdown(css_prioridades, unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**🔥 Produtos Prioritários**")

        if prioridades_prod:
            for i, prio in enumerate(prioridades_prod, 1):
                perc = prio["perc_ating"]
                cor = get_status_color(perc)
                bg_cor = get_status_bg_color(perc)
                label = get_status_label(perc)

                st.markdown(
                    f"""
                    <div class="mg-prioridade-card" style="border-left-color: {cor};">
                        <div style="display: flex; align-items: center;">
                            <span class="mg-prioridade-numero" style="background: {cor};">{i}</span>
                            <span class="mg-prioridade-titulo">
                                {prio["produto"]}
                                <span class="mg-prioridade-badge" style="background: {bg_cor}; color: {cor};">
                                    {formatar_percentual(perc)} · {label}
                                </span>
                            </span>
                        </div>
                        <div class="mg-prioridade-detalhe">
                            Falta: {formatar_moeda(prio["gap_valor"])}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.info("Todos os produtos atingiram a meta! 🎉")

    with col2:
        st.markdown("**📍 Regiões que Precisam de Atenção**")

        if prioridades_reg:
            for i, prio in enumerate(prioridades_reg, 1):
                perc = prio["perc_ating"]
                cor = get_status_color(perc)
                bg_cor = get_status_bg_color(perc)
                label = get_status_label(perc)

                st.markdown(
                    f"""
                    <div class="mg-prioridade-card" style="border-left-color: {cor};">
                        <div style="display: flex; align-items: center;">
                            <span class="mg-prioridade-numero" style="background: {cor};">{i}</span>
                            <span class="mg-prioridade-titulo">
                                {prio["regiao"]}
                                <span class="mg-prioridade-badge" style="background: {bg_cor}; color: {cor};">
                                    {formatar_percentual(perc)} · {label}
                                </span>
                            </span>
                        </div>
                        <div class="mg-prioridade-detalhe">
                            Realizado: {formatar_moeda(prio["valor"])} 
                            / Meta: {formatar_moeda(prio["meta"])}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.info("Todas as regiões estão acima da meta! 🎉")

    with col3:
        st.markdown("**🏪 Lojas que Precisam de Atenção**")

        if prioridades_loja:
            for i, prio in enumerate(prioridades_loja, 1):
                perc = prio["perc_ating"]
                cor = get_status_color(perc)
                bg_cor = get_status_bg_color(perc)
                label = get_status_label(perc)
                regiao_label = f" ({prio['regiao']})" if prio.get("regiao") else ""

                st.markdown(
                    f"""
                    <div class="mg-prioridade-card" style="border-left-color: {cor};">
                        <div style="display: flex; align-items: center;">
                            <span class="mg-prioridade-numero" style="background: {cor};">{i}</span>
                            <span class="mg-prioridade-titulo">
                                {prio["loja"]}{regiao_label}
                                <span class="mg-prioridade-badge" style="background: {bg_cor}; color: {cor};">
                                    {formatar_percentual(perc)} · {label}
                                </span>
                            </span>
                        </div>
                        <div class="mg-prioridade-detalhe">
                            Realizado: {formatar_moeda(prio["valor"])}
                            / Meta: {formatar_moeda(prio["meta"])}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.info("Todas as lojas estão acima da meta! 🎉")

    # Resumo de ação
    st.markdown("---")

    # Gerar mensagem de ação sugerida
    acoes = []
    if prioridades_prod:
        top_prod = prioridades_prod[0]
        acoes.append(
            f"Focar em **{top_prod['produto']}** (falta de {formatar_moeda(top_prod['gap_valor'])})"
        )
    if prioridades_reg:
        top_reg = prioridades_reg[0]
        acoes.append(
            f"Apoiar região **{top_reg['regiao']}** ({formatar_percentual(top_reg['perc_ating'])} da meta)"
        )
    if prioridades_loja:
        top_loja = prioridades_loja[0]
        acoes.append(
            f"Atuar na loja **{top_loja['loja']}** ({formatar_percentual(top_loja['perc_ating'])} da meta)"
        )

    if acoes:
        itens = "".join(f'<li style="margin-bottom: 4px;">{a}</li>' for a in acoes)
        st.markdown(
            f"""
            <div style="background: var(--mg-primary-soft);
                        border: 1px solid var(--mg-primary-ring);
                        padding: 16px 20px; border-radius: 12px;
                        margin-top: 16px;">
                <div style="font-size: 14px; font-weight: 600;
                            color: var(--mg-primary);
                            margin-bottom: 8px;">
                    💡 Ações Recomendadas para Hoje:
                </div>
                <ul style="margin: 0; padding-left: 20px;
                           color: var(--mg-primary);">
                    {itens}
                </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )
