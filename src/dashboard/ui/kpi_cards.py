"""
Cards compostos de KPIs do dashboard — Layout reformulado.

Nova organizacao dos cards:
1. Indicadores Principais (6 cards)
   - Total Pago, Em Analise, Cancelados
   - Media DU Loja, Media DU Consultor, Pontos Efetivos
2. Metas Diarias por Produto (5 cards)
   - CNC, CLT, Saque, Consignado, FGTS/Ant.Ben/CNC13
"""

from typing import Dict, List

import streamlit as st
import streamlit_antd_components as sac

from src.dashboard.formatters import (
    formatar_moeda,
    formatar_numero,
    formatar_percentual,
)
from src.dashboard.ui.cards import progress_bar


# ═══════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════


def _delta_color(percent: float, limiar: float = 80) -> str:
    """Cor do delta conforme percentual (API st.metric)."""
    if percent >= 100:
        return "normal"
    if percent >= limiar:
        return "off"
    return "inverse"


def _termometro_status(
    valor_atual: float, referencia: float
) -> tuple[float, str, str]:
    """
    Retorna (percentual, status_texto, delta_color) para termometro.
    """
    if referencia <= 0:
        return (100.0, "Sem referencia", "off")

    perc = (valor_atual / referencia) * 100

    if perc >= 100:
        return (perc, "Acima", "normal")
    elif perc >= 80:
        return (perc, "Em progresso", "off")
    else:
        return (perc, "Abaixo", "inverse")


# ═══════════════════════════════════════════════════════
# Cards Principais (6 cards)
# ═══════════════════════════════════════════════════════


def _card_total_pago(kpis: Dict) -> None:
    """Card: Total Pago com projecao e termometro de meta diaria."""
    total_pago = kpis.get("total_vendas", 0)
    projecao = kpis.get("projecao", 0)
    meta_diaria_pts = kpis.get("meta_diaria_pts", 0)
    media_du = kpis.get("media_du", 0)
    media_du_pts = kpis.get("media_du_pontos", 1)
    du_restantes = kpis.get("du_restantes", 0)

    with st.container():
        st.metric(
            "Total Pago",
            formatar_moeda(total_pago),
            f"↗ Proj: {formatar_moeda(projecao)}",
            delta_color="off",
        )

        # Termometro: ritmo vs meta diaria
        if meta_diaria_pts > 0 and media_du_pts > 0:
            fator = media_du / media_du_pts if media_du_pts > 0 else 0
            meta_diaria_valor = meta_diaria_pts * fator
            perc_meta, status, _ = _termometro_status(media_du, meta_diaria_valor)

            st.markdown(
                f"<small style='display:block;margin-top:4px;'>"
                f"Meta: {formatar_moeda(meta_diaria_valor)}/DU • "
                f"{status} • {du_restantes} DU rest</small>",
                unsafe_allow_html=True,
            )
            progress_bar(perc_meta)
        st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)


def _card_em_analise(kpis_analise: Dict) -> None:
    """Card: Em Analise com qtd propostas e representatividade."""
    valor = kpis_analise.get("valor_analise", 0)
    qtd = kpis_analise.get("qtd_analise", 0)
    variacao = kpis_analise.get("variacao_analise", 0)
    media_diaria = kpis_analise.get("media_diaria_analise", 0)

    with st.container():
        st.metric(
            "Em Analise",
            formatar_moeda(valor),
            f"📋 {qtd:,} propostas".replace(",", "."),
            delta_color="off",
        )

        # Representatividade do pipeline
        if variacao > 0:
            st.markdown(
                f"<small style='display:block;margin-top:4px;'>"
                f"Representa {formatar_percentual(variacao)} do dia • "
                f"Media: {formatar_moeda(media_diaria)}/DU</small>",
                unsafe_allow_html=True,
            )
        st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)


def _card_cancelados(kpis_cancel: Dict) -> None:
    """Card: Cancelados com qtd e churn rate."""
    valor = kpis_cancel.get("valor_cancelados", 0)
    qtd = kpis_cancel.get("qtd_cancelados", 0)
    indice = kpis_cancel.get("indice_perda", 0)

    with st.container():
        st.metric(
            "Cancelados",
            formatar_moeda(valor),
            f"⚠️ {qtd:,} propostas".replace(",", "."),
            delta_color="inverse",
        )

        # Churn rate com indicador visual
        cor = "#28a745" if indice < 15 else "#ffc107" if indice < 25 else "#dc3545"
        nivel = "Baixo" if indice < 15 else "Moderado" if indice < 25 else "Alto"
        st.markdown(
            f"<small style='display:block;margin-top:4px;'>Churn: "
            f"<span style='color:{cor};font-weight:600;'>"
            f"{formatar_percentual(indice)}</span> • {nivel}</small>",
            unsafe_allow_html=True,
        )
        st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)


def _card_media_du_loja(medias: Dict) -> None:
    """Card: Media DU Loja com contexto."""
    media_du_loja = medias.get("media_du_loja", 0)
    num_lojas = medias.get("num_lojas", 0)

    with st.container():
        st.metric(
            "Media DU Loja",
            formatar_moeda(media_du_loja),
            f"🏪 {num_lojas} lojas",
            delta_color="off",
        )
        st.markdown(
            "<small style='display:block;margin-top:4px;'>"
            "Ritmo medio por loja</small>",
            unsafe_allow_html=True,
        )
        st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)


def _card_media_du_consultor(medias: Dict) -> None:
    """Card: Media DU Consultor com contexto."""
    media_du_consultor = medias.get("media_du_consultor", 0)
    num_consultores = medias.get("num_consultores", 0)

    with st.container():
        st.metric(
            "Media DU Consultor",
            formatar_moeda(media_du_consultor),
            f"👤 {num_consultores} consultores",
            delta_color="off",
        )
        st.markdown(
            "<small style='display:block;margin-top:4px;'>"
            "Ritmo medio por consultor</small>",
            unsafe_allow_html=True,
        )
        st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)


def _card_pontos_efetivos(kpis: Dict) -> None:
    """Card: Pontos Efetivos com % meta Prata e projecao."""
    total_pontos = kpis.get("total_pontos", 0)
    perc_ating = kpis.get("perc_ating_prata", 0)
    perc_proj = kpis.get("perc_proj", 0)
    meta_prata = kpis.get("meta_prata", 0)
    du_restantes = kpis.get("du_restantes", 0)

    with st.container():
        dc = _delta_color(perc_ating)
        st.metric(
            "Pontos Efetivos",
            formatar_numero(total_pontos),
            f"{formatar_percentual(perc_ating)} da meta",
            delta_color=dc,
        )

        progress_bar(perc_ating)

        # Gap para meta com projeção
        if perc_ating < 100 and du_restantes > 0:
            gap = meta_prata - total_pontos
            nec_por_du = gap / du_restantes if du_restantes > 0 else 0
            st.markdown(
                f"<small style='display:block;margin-top:4px;'>"
                f"Faltam {formatar_numero(gap)} pts • "
                f"Nec: {formatar_numero(nec_por_du)}/DU</small>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<small style='display:block;margin-top:4px;'>"
                f"Proj: {formatar_percentual(perc_proj)} da meta</small>",
                unsafe_allow_html=True,
            )
        st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════
# Metas por Produto (5 cards)
# ═══════════════════════════════════════════════════════


def _nome_produto_display(produto_key: str) -> str:
    """Converte chave interna para nome de exibicao."""
    nomes = {
        "CNC": "CNC",
        "CLT": "CLT",
        "SAQUE": "Saque",
        "CONSIGNADO": "Consignado",
        "FGTS_ANT_BEN_CNC13": "FGTS/Ant.Ben./13o",
    }
    return nomes.get(produto_key, produto_key)


def _card_meta_produto(produto: Dict) -> None:
    """Card individual para meta de um produto."""
    nome = _nome_produto_display(produto.get("produto", ""))
    valor = produto.get("valor_atual", 0)
    meta = produto.get("meta_total", 0)
    ritmo = produto.get("ritmo_diario", 0)
    meta_diaria = produto.get("meta_diaria", 0)
    perc = produto.get("perc_atingido", 0)
    perc_ritmo = (ritmo / meta_diaria) * 100 if meta_diaria > 0 else 0

    # Status do atingimento
    dc = _delta_color(perc)
    if meta > 0:
        delta_txt = f"{formatar_percentual(perc)} da meta"
    else:
        delta_txt = "Sem meta definida"

    st.metric(nome, formatar_moeda(valor), delta_txt, delta_color=dc)

    if meta_diaria > 0:
        # Progress bar do ritmo vs meta diaria
        progress_bar(perc_ritmo)
        # Label com ritmo e gap
        if perc_ritmo >= 100:
            st.markdown(
                f"<small>✓ Ritmo: {formatar_moeda(ritmo)}/DU</small>",
                unsafe_allow_html=True,
            )
        else:
            gap = meta_diaria - ritmo
            st.markdown(
                f"<small>↓ Ritmo: {formatar_moeda(ritmo)}/DU "
                f"(-{formatar_moeda(gap)})</small>",
                unsafe_allow_html=True,
            )
    elif valor > 0:
        # Sem meta mas com vendas
        st.markdown(
            f"<small>Ritmo: {formatar_moeda(ritmo)}/DU</small>",
            unsafe_allow_html=True,
        )


# ═══════════════════════════════════════════════════════
# Funcoes Publicas
# ═══════════════════════════════════════════════════════


def criar_cards_indicadores_principais(
    kpis: Dict,
    kpis_analise: Dict,
    kpis_cancel: Dict,
    medias: Dict,
) -> None:
    """
    Renderiza os 6 cards de indicadores principais.

    Args:
        kpis: KPIs gerais do dashboard
        kpis_analise: KPIs de contratos em analise
        kpis_cancel: KPIs de contratos cancelados
        medias: Medias DU por loja e consultor
    """
    sac.divider(
        label="Indicadores Principais",
        icon="bar-chart-line",
        align="left",
        color="blue",
    )

    # Primeira linha: 3 cards
    col1, col2, col3 = st.columns(3)
    with col1:
        _card_total_pago(kpis)
    with col2:
        _card_em_analise(kpis_analise)
    with col3:
        _card_cancelados(kpis_cancel)

    # Espaçamento entre linhas
    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    # Segunda linha: 3 cards
    col1, col2, col3 = st.columns(3)
    with col1:
        _card_media_du_loja(medias)
    with col2:
        _card_media_du_consultor(medias)
    with col3:
        _card_pontos_efetivos(kpis)


def criar_cards_metas_produto(produtos: List[Dict]) -> None:
    """
    Renderiza os 5 cards de metas diarias por produto.

    Args:
        produtos: Lista de dicts com dados de cada produto
    """
    if not produtos:
        return

    sac.divider(
        label="Meta Diaria por Produto",
        icon="box",
        align="left",
        color="blue",
    )

    # 5 colunas para os 5 produtos
    cols = st.columns(5)
    for i, produto in enumerate(produtos[:5]):
        with cols[i]:
            _card_meta_produto(produto)


def criar_cards_pipeline(df_analise, kpis_pagos):
    """
    Mantido para compatibilidade — sera removido em refactor posterior.
    Agora os dados de pipeline estao integrados no card Em Analise.
    """
    pass
