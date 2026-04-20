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
    """Card: Total Pago com projecao e ritmo vs meta diaria."""
    total_pago = kpis.get("total_vendas", 0)
    projecao = kpis.get("projecao", 0)
    meta_dr_pts = kpis.get("meta_diaria_restante_pts", 0)
    media_du = kpis.get("media_du", 0)
    media_du_pts = kpis.get("media_du_pontos", 1)
    du_restantes = kpis.get("du_restantes", 0)

    def fmt(v: float) -> str:
        return formatar_moeda(v).replace("$", "&#36;")

    track_html = ""
    card_mod = "mg-prod-card--accent-teal"

    if meta_dr_pts > 0 and media_du_pts > 0:
        fator = media_du / media_du_pts
        meta_dr_val = meta_dr_pts * fator
        perc, status, _ = _termometro_status(media_du, meta_dr_val)
        clamped = max(0.0, min(perc, 100.0))
        if perc >= 100:
            card_mod = "mg-prod-card--success"
            bar_mod = "mg-success"
            meta_cls = "mg-prod-footer-ok"
        elif perc >= 80:
            card_mod = "mg-prod-card--warning"
            bar_mod = "mg-warning"
            meta_cls = "mg-prod-footer-meta"
        else:
            card_mod = "mg-prod-card--danger"
            bar_mod = "mg-danger"
            meta_cls = "mg-prod-footer-gap"
        track_html = (
            f'<div class="mg-prod-track">'
            f'<div class="mg-prod-fill {bar_mod}" '
            f'style="width:{clamped:.1f}%"></div>'
            f"</div>"
        )
        footer_meta = (
            f'<span class="mg-prod-footer-meta {meta_cls}">'
            f"Meta Di&#225;ria: {fmt(meta_dr_val)}/DU"
            f" &#183; {status}"
            f" &#183; {du_restantes} DU rest</span>"
        )
    else:
        footer_meta = (
            f'<span class="mg-prod-footer-meta">'
            f"{du_restantes} DU restantes</span>"
        )

    footer_proj = (
        f'<span class="mg-prod-footer-ritmo">'
        f"&#8599; Proj: {fmt(projecao)}</span>"
    )
    html = (
        f'<div class="mg-prod-card {card_mod}">'
        f'<div class="mg-prod-header">'
        f'<span class="mg-prod-name">Total Pago</span>'
        f"</div>"
        f'<div class="mg-prod-value">{fmt(total_pago)}</div>'
        f"{track_html}"
        f'<div class="mg-prod-footer">'
        f"{footer_meta}{footer_proj}"
        f"</div>"
        f"</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def _card_em_analise(kpis_analise: Dict) -> None:
    """Card: Em Analise com qtd propostas e representatividade."""
    valor = kpis_analise.get("valor_analise", 0)
    qtd = kpis_analise.get("qtd_analise", 0)
    variacao = kpis_analise.get("variacao_analise", 0)
    media_diaria = kpis_analise.get("media_diaria_analise", 0)

    def fmt(v: float) -> str:
        return formatar_moeda(v).replace("$", "&#36;")

    qtd_fmt = f"{qtd:,}".replace(",", ".")
    footer_qtd = (
        f'<span class="mg-prod-footer-meta">'
        f"&#128203; {qtd_fmt} propostas</span>"
    )
    footer_ctx = ""
    if variacao > 0:
        footer_ctx = (
            f'<span class="mg-prod-footer-ritmo">'
            f"{formatar_percentual(variacao)} do dia"
            f" &#183; M&#233;dia: {fmt(media_diaria)}/DU"
            f"</span>"
        )
    html = (
        f'<div class="mg-prod-card mg-prod-card--accent-teal">'
        f'<div class="mg-prod-header">'
        f'<span class="mg-prod-name">Em An&#225;lise</span>'
        f"</div>"
        f'<div class="mg-prod-value">{fmt(valor)}</div>'
        f'<div class="mg-prod-footer">'
        f"{footer_qtd}{footer_ctx}"
        f"</div>"
        f"</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def _card_cancelados(kpis_cancel: Dict) -> None:
    """Card: Cancelados com qtd e churn rate."""
    valor = kpis_cancel.get("valor_cancelados", 0)
    qtd = kpis_cancel.get("qtd_cancelados", 0)
    indice = kpis_cancel.get("indice_perda", 0)

    def fmt(v: float) -> str:
        return formatar_moeda(v).replace("$", "&#36;")

    if indice < 15:
        card_mod = "mg-prod-card--success"
        cor_churn = "#28a745"
        nivel = "Baixo"
    elif indice < 25:
        card_mod = "mg-prod-card--warning"
        cor_churn = "#d97706"
        nivel = "Moderado"
    else:
        card_mod = "mg-prod-card--danger"
        cor_churn = "#dc3545"
        nivel = "Alto"

    qtd_fmt = f"{qtd:,}".replace(",", ".")
    footer_qtd = (
        f'<span class="mg-prod-footer-meta">'
        f"&#9888;&#65039; {qtd_fmt} propostas canceladas</span>"
    )
    footer_churn = (
        f'<span class="mg-prod-footer-ritmo">Churn: '
        f'<span style="color:{cor_churn};font-weight:700;">'
        f"{formatar_percentual(indice)}</span>"
        f" &#183; {nivel}</span>"
    )
    html = (
        f'<div class="mg-prod-card {card_mod}">'
        f'<div class="mg-prod-header">'
        f'<span class="mg-prod-name">Cancelados</span>'
        f"</div>"
        f'<div class="mg-prod-value">{fmt(valor)}</div>'
        f'<div class="mg-prod-footer">'
        f"{footer_qtd}{footer_churn}"
        f"</div>"
        f"</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def _card_media_du_loja(medias: Dict) -> None:
    """Card: Media DU Loja."""
    media_du_loja = medias.get("media_du_loja", 0)
    num_lojas = medias.get("num_lojas", 0)

    def fmt(v: float) -> str:
        return formatar_moeda(v).replace("$", "&#36;")

    html = (
        f'<div class="mg-prod-card mg-prod-card--accent-teal">'
        f'<div class="mg-prod-header">'
        f'<span class="mg-prod-name">M&#233;dia DU Loja</span>'
        f"</div>"
        f'<div class="mg-prod-value">{fmt(media_du_loja)}</div>'
        f'<div class="mg-prod-footer">'
        f'<span class="mg-prod-footer-meta">'
        f"&#127978; {num_lojas} lojas</span>"
        f'<span class="mg-prod-footer-ritmo">'
        f"Ritmo m&#233;dio por loja</span>"
        f"</div>"
        f"</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def _card_media_du_consultor(medias: Dict) -> None:
    """Card: Media DU Consultor."""
    media_du_consultor = medias.get("media_du_consultor", 0)
    num_consultores = medias.get("num_consultores", 0)

    def fmt(v: float) -> str:
        return formatar_moeda(v).replace("$", "&#36;")

    html = (
        f'<div class="mg-prod-card mg-prod-card--accent-indigo">'
        f'<div class="mg-prod-header">'
        f'<span class="mg-prod-name">M&#233;dia DU Consultor</span>'
        f"</div>"
        f'<div class="mg-prod-value">'
        f"{fmt(media_du_consultor)}</div>"
        f'<div class="mg-prod-footer">'
        f'<span class="mg-prod-footer-meta">'
        f"&#128100; {num_consultores} consultores</span>"
        f'<span class="mg-prod-footer-ritmo">'
        f"Ritmo m&#233;dio por consultor</span>"
        f"</div>"
        f"</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def _card_pontos_efetivos(kpis: Dict) -> None:
    """Card: Pontos Efetivos com % meta Prata e gap diario."""
    total_pontos = kpis.get("total_pontos", 0)
    perc_ating = kpis.get("perc_ating_prata", 0)
    perc_proj = kpis.get("perc_proj", 0)
    meta_prata = kpis.get("meta_prata", 0)
    du_restantes = kpis.get("du_restantes", 0)

    clamped = max(0.0, min(perc_ating, 100.0))
    if perc_ating >= 100:
        card_mod = "mg-prod-card--success"
        badge_mod = "mg-prod-badge--success"
        bar_mod = "mg-success"
    elif perc_ating >= 80:
        card_mod = "mg-prod-card--warning"
        badge_mod = "mg-prod-badge--warning"
        bar_mod = "mg-warning"
    else:
        card_mod = "mg-prod-card--danger"
        badge_mod = "mg-prod-badge--danger"
        bar_mod = "mg-danger"

    if perc_ating < 100 and du_restantes > 0:
        gap = meta_prata - total_pontos
        nec = gap / du_restantes
        nec_cls = (
            "mg-prod-footer-meta mg-prod-footer-gap"
            if perc_ating < 80
            else "mg-prod-footer-meta"
        )
        footer_meta = (
            f'<span class="{nec_cls}">'
            f"Meta Di&#225;ria: {formatar_numero(nec)}/DU</span>"
        )
        footer_sec = (
            f'<span class="mg-prod-footer-ritmo">'
            f"Faltam {formatar_numero(gap)} pts</span>"
        )
    else:
        footer_meta = (
            '<span class="mg-prod-footer-meta mg-prod-footer-ok">'
            "&#10003; Meta atingida</span>"
        )
        footer_sec = (
            f'<span class="mg-prod-footer-ritmo">'
            f"Proj: {formatar_percentual(perc_proj)} da meta</span>"
        )

    html = (
        f'<div class="mg-prod-card {card_mod}">'
        f'<div class="mg-prod-header">'
        f'<span class="mg-prod-name">Pontos Efetivos</span>'
        f'<span class="mg-prod-badge {badge_mod}">'
        f"{formatar_percentual(perc_ating)}</span>"
        f"</div>"
        f'<div class="mg-prod-value">'
        f"{formatar_numero(total_pontos)}</div>"
        f'<div class="mg-prod-track">'
        f'<div class="mg-prod-fill {bar_mod}" '
        f'style="width:{clamped:.1f}%"></div>'
        f"</div>"
        f'<div class="mg-prod-footer">'
        f"{footer_meta}{footer_sec}"
        f"</div>"
        f"</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════
# Metas por Produto (cards 2x3)
# ═══════════════════════════════════════════════════════

_ORDEM_ROW1 = ["CNC", "CLT"]
_ORDEM_ROW2 = ["SAQUE", "CONSIGNADO", "FGTS_ANT_BEN_CNC13"]

_NOMES_PRODUTO = {
    "MIX": "Mix Geral",
    "CNC": "CNC",
    "CLT": "CLT",
    "SAQUE": "Saque",
    "CONSIGNADO": "Consignado",
    "FGTS_ANT_BEN_CNC13": "FGTS/Ant.Ben./13o",
}


def _nome_produto_display(produto_key: str) -> str:
    """Converte chave interna para nome de exibicao."""
    return _NOMES_PRODUTO.get(produto_key, produto_key)


def _calcular_mix(produtos: List[Dict]) -> Dict:
    """Agrega todos os produtos em um card MIX."""
    valor = sum(p.get("valor_atual", 0) for p in produtos)
    meta = sum(p.get("meta_total", 0) for p in produtos)
    ritmo = sum(p.get("ritmo_diario", 0) for p in produtos)
    meta_dr = sum(
        p.get("meta_diaria_restante", 0) for p in produtos
    )
    perc = (valor / meta * 100) if meta > 0 else 0
    return {
        "produto": "MIX",
        "valor_atual": valor,
        "meta_total": meta,
        "ritmo_diario": ritmo,
        "meta_diaria_restante": meta_dr,
        "perc_atingido": perc,
    }


def _card_meta_produto(
    produto: Dict, is_mix: bool = False
) -> None:
    """Card individual para meta de um produto."""
    nome = _nome_produto_display(produto.get("produto", ""))
    valor = produto.get("valor_atual", 0)
    meta = produto.get("meta_total", 0)
    ritmo = produto.get("ritmo_diario", 0)
    meta_dr = produto.get("meta_diaria_restante", 0)
    perc = produto.get("perc_atingido", 0)

    if meta_dr > 0:
        perc_ritmo = (ritmo / meta_dr) * 100
    else:
        perc_ritmo = 100.0 if perc >= 100 else 0.0

    clamped = max(0.0, min(perc_ritmo, 100.0))

    if is_mix:
        card_mod = "mg-prod-card--mix"
        badge_mod = "mg-prod-badge--mix"
        bar_mod = "mg-primary"
    elif perc >= 100:
        card_mod = "mg-prod-card--success"
        badge_mod = "mg-prod-badge--success"
        bar_mod = "mg-success"
    elif perc >= 80:
        card_mod = "mg-prod-card--warning"
        badge_mod = "mg-prod-badge--warning"
        bar_mod = "mg-warning"
    else:
        card_mod = "mg-prod-card--danger"
        badge_mod = "mg-prod-badge--danger"
        bar_mod = "mg-danger"

    def fmt(v: float) -> str:
        return formatar_moeda(v).replace("$", "&#36;")

    if meta == 0:
        footer = (
            f'<span class="mg-prod-footer-ritmo">'
            f"Ritmo: {fmt(ritmo)}/DU</span>"
        )
    elif perc >= 100 or meta_dr <= 0:
        footer = (
            f'<span class="mg-prod-footer-meta'
            f' mg-prod-footer-ok">'
            f"&#10003; Meta atingida</span>"
            f'<span class="mg-prod-footer-ritmo">'
            f"Ritmo: {fmt(ritmo)}/DU</span>"
        )
    elif ritmo >= meta_dr:
        folga = ritmo - meta_dr
        footer = (
            f'<span class="mg-prod-footer-meta'
            f' mg-prod-footer-ok">'
            f"&#8593; Meta Di&#225;ria: {fmt(meta_dr)}/DU"
            f" <small>(+{fmt(folga)})</small></span>"
            f'<span class="mg-prod-footer-ritmo">'
            f"Ritmo: {fmt(ritmo)}/DU</span>"
        )
    else:
        gap = meta_dr - ritmo
        footer = (
            f'<span class="mg-prod-footer-meta'
            f' mg-prod-footer-gap">'
            f"&#8595; Meta Di&#225;ria: {fmt(meta_dr)}/DU"
            f" <small>(-{fmt(gap)})</small></span>"
            f'<span class="mg-prod-footer-ritmo">'
            f"Ritmo: {fmt(ritmo)}/DU</span>"
        )

    badge_txt = (
        formatar_percentual(perc) if meta > 0 else "Sem meta"
    )

    html = (
        f'<div class="mg-prod-card {card_mod}">'
        f'<div class="mg-prod-header">'
        f'<span class="mg-prod-name">{nome}</span>'
        f'<span class="mg-prod-badge {badge_mod}">'
        f"{badge_txt}</span>"
        f"</div>"
        f'<div class="mg-prod-value">{fmt(valor)}</div>'
        f'<div class="mg-prod-track">'
        f'<div class="mg-prod-fill {bar_mod}" '
        f'style="width:{clamped:.1f}%"></div>'
        f"</div>"
        f'<div class="mg-prod-footer">{footer}</div>'
        f"</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════
# Cards de Quantidade (Emissão, Super Conta, BMG Med,
# Vida Familiar)
# ═══════════════════════════════════════════════════════

_ACENTO_QTD = {
    "EMISSAO": "mg-prod-card--accent-indigo",
    "SUPER_CONTA": "mg-prod-card--accent-teal",
    "BMG_MED": "mg-prod-card--accent-teal",
    "VIDA_FAMILIAR": "mg-prod-card--accent-teal",
}


def _card_qtd_produto(prod: Dict) -> None:
    """Card de quantidade para produtos sem valor monetário."""
    chave = prod.get("produto", "")
    nome = prod.get("nome", chave)
    qtd_paga = prod.get("qtd_paga", 0)
    qtd_analise = prod.get("qtd_analise", 0)
    meta = prod.get("meta", 0)
    perc = prod.get("perc_atingido", 0)
    ritmo = prod.get("ritmo_diario", 0.0)
    projecao = prod.get("projecao", 0.0)
    meta_dr = prod.get("meta_diaria_restante", 0.0)

    clamped = max(0.0, min(perc, 100.0))

    if meta > 0:
        if perc >= 100:
            card_mod = "mg-prod-card--success"
            badge_mod = "mg-prod-badge--success"
            bar_mod = "mg-success"
        elif perc >= 80:
            card_mod = "mg-prod-card--warning"
            badge_mod = "mg-prod-badge--warning"
            bar_mod = "mg-warning"
        else:
            card_mod = "mg-prod-card--danger"
            badge_mod = "mg-prod-badge--danger"
            bar_mod = "mg-danger"
        badge_txt = formatar_percentual(perc)
    else:
        card_mod = _ACENTO_QTD.get(chave, "mg-prod-card--accent-teal")
        badge_mod = ""
        bar_mod = "mg-primary"
        badge_txt = ""

    def fmtq(v: float) -> str:
        return formatar_numero(int(round(v)))

    # Barra de progresso (só quando há meta)
    track_html = ""
    if meta > 0:
        track_html = (
            f'<div class="mg-prod-track">'
            f'<div class="mg-prod-fill {bar_mod}" '
            f'style="width:{clamped:.1f}%"></div>'
            f"</div>"
        )

    # Footer L1: Meta Diária em destaque
    if meta <= 0:
        footer_meta = (
            f'<span class="mg-prod-footer-meta">'
            f"Proj: {fmtq(projecao)}</span>"
        )
    elif perc >= 100 or meta_dr <= 0:
        footer_meta = (
            '<span class="mg-prod-footer-meta'
            ' mg-prod-footer-ok">'
            "&#10003; Meta atingida</span>"
        )
    elif ritmo >= meta_dr:
        folga = ritmo - meta_dr
        footer_meta = (
            f'<span class="mg-prod-footer-meta'
            f' mg-prod-footer-ok">'
            f"&#8593; Meta Di&#225;ria: {fmtq(meta_dr)}/DU"
            f" <small>(+{fmtq(folga)})</small></span>"
        )
    else:
        gap = meta_dr - ritmo
        footer_meta = (
            f'<span class="mg-prod-footer-meta'
            f' mg-prod-footer-gap">'
            f"&#8595; Meta Di&#225;ria: {fmtq(meta_dr)}/DU"
            f" <small>(-{fmtq(gap)})</small></span>"
        )

    # Footer L2: Ritmo · Em análise · Projeção
    analise_txt = (
        f" &#183; An&#225;lise: {fmtq(qtd_analise)}"
        if qtd_analise > 0
        else ""
    )
    footer_sec = (
        f'<span class="mg-prod-footer-ritmo">'
        f"Ritmo: {fmtq(ritmo)}/DU"
        f" &#183; Proj: {fmtq(projecao)}"
        f"{analise_txt}</span>"
    )

    badge_html = (
        f'<span class="mg-prod-badge {badge_mod}">'
        f"{badge_txt}</span>"
        if badge_txt
        else ""
    )

    html = (
        f'<div class="mg-prod-card {card_mod}">'
        f'<div class="mg-prod-header">'
        f'<span class="mg-prod-name">{nome}</span>'
        f"{badge_html}"
        f"</div>"
        f'<div class="mg-prod-value">{fmtq(qtd_paga)}</div>'
        f"{track_html}"
        f'<div class="mg-prod-footer">'
        f"{footer_meta}{footer_sec}"
        f"</div>"
        f"</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


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
    Renderiza os cards de metas por produto em layout 2x3.

    Linha 1: Mix Geral | CNC | CLT
    Linha 2: Saque | Consignado | FGTS/Ant.Ben./13o

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

    idx = {p["produto"]: p for p in produtos}
    mix = _calcular_mix(produtos)

    # Linha 1: Mix | CNC | CLT
    col_mix, col_cnc, col_clt = st.columns(3)
    with col_mix:
        _card_meta_produto(mix, is_mix=True)
    with col_cnc:
        if "CNC" in idx:
            _card_meta_produto(idx["CNC"])
    with col_clt:
        if "CLT" in idx:
            _card_meta_produto(idx["CLT"])

    st.markdown(
        "<div style='height:10px;'></div>",
        unsafe_allow_html=True,
    )

    # Linha 2: Saque | Consignado | FGTS/Ant.Ben./13o
    col_saq, col_cons, col_fgts = st.columns(3)
    with col_saq:
        if "SAQUE" in idx:
            _card_meta_produto(idx["SAQUE"])
    with col_cons:
        if "CONSIGNADO" in idx:
            _card_meta_produto(idx["CONSIGNADO"])
    with col_fgts:
        if "FGTS_ANT_BEN_CNC13" in idx:
            _card_meta_produto(idx["FGTS_ANT_BEN_CNC13"])


def criar_cards_qtd_produto(produtos: List[Dict]) -> None:
    """
    Renderiza os 4 cards de quantidade em uma linha:
    Emissão | Super Conta | BMG Med | Vida Familiar

    Args:
        produtos: saida de calcular_kpis_qtd_produtos()
    """
    if not produtos:
        return

    sac.divider(
        label="Emissão e Seguros",
        icon="heart-pulse",
        align="left",
        color="blue",
    )

    cols = st.columns(4)
    for col, prod in zip(cols, produtos):
        with col:
            _card_qtd_produto(prod)


def criar_cards_pipeline(df_analise, kpis_pagos):
    """
    Mantido para compatibilidade — sera removido em refactor posterior.
    Agora os dados de pipeline estao integrados no card Em Analise.
    """
    pass
