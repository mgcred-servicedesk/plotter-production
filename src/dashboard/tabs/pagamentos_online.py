"""
Aba Pagamentos Online: estimativa horaria a partir do extrator DNA.

Fonte: view `v_pagamentos_online_efetivo`. A view ja aplica o filtro
`Agrupamento='Paga'`, calcula `valor_producao` e exclui ADEs ja
consolidadas em `contratos`.

Esta aba so e exibida para admin e gestor (ver `permissions.py`).
"""

from datetime import datetime, timezone

import pandas as pd
import streamlit as st
import streamlit_antd_components as sac

from src.dashboard.formatters import formatar_moeda, formatar_numero


# Mapa grupo_produto (no banco) -> (label longo, label curto) para exibicao.
# A coluna `grupo_produto` em pagamentos_online vem do extrator DNA com nomes
# que diferem do vocabulario interno do dashboard; aqui traduzimos. O label
# curto e o nome do tipo como no resto do dashboard (= planilha de origem).
GRUPO_DISPLAY: dict[str, tuple[str, str]] = {
    "Antecipação em Conta": ("Antecipação de Benefício", "ANT. DE BENEF."),
    "Crédito na Conta": ("Crédito na Conta", "CNC"),
}


CSS_CARDS = """
<style>
.mg-pago-card {
    background: var(--mg-surface);
    border-radius: 12px;
    border: 1px solid var(--mg-border);
    padding: 18px 22px;
    margin-bottom: 14px;
    box-shadow: var(--mg-shadow-sm);
    display: grid;
    grid-template-columns: 1fr auto;
    align-items: center;
    gap: 16px;
}
.mg-pago-title {
    font-size: 18px;
    font-weight: 700;
    color: var(--mg-text);
    display: flex;
    align-items: baseline;
    gap: 10px;
}
.mg-pago-alias {
    font-size: 12px;
    font-weight: 600;
    color: var(--mg-text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.mg-pago-sub {
    font-size: 11px;
    color: var(--mg-text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-top: 4px;
}
.mg-pago-meta {
    font-size: 13px;
    color: var(--mg-text-muted);
    margin-top: 6px;
}
.mg-pago-valor {
    font-size: 28px;
    font-weight: 700;
    color: var(--mg-text);
    text-align: right;
    line-height: 1.1;
}
.mg-pago-ticket {
    font-size: 12px;
    color: var(--mg-text-muted);
    text-align: right;
    margin-top: 4px;
}
</style>
"""


def _formatar_atualizacao(imported_at: pd.Timestamp) -> str:
    """Retorna 'ha X min' / 'ha X h' a partir do imported_at mais recente."""
    if pd.isna(imported_at):
        return "sem dados"
    agora = datetime.now(timezone.utc)
    delta = agora - imported_at.to_pydatetime()
    segundos = int(delta.total_seconds())
    if segundos < 60:
        return f"ha {segundos}s"
    if segundos < 3600:
        return f"ha {segundos // 60} min"
    if segundos < 86400:
        return f"ha {segundos // 3600} h"
    return f"ha {segundos // 86400} d"


def _formatar_timestamp_local(imported_at: pd.Timestamp) -> str:
    """Formata o imported_at no padrao dd/mm/aaaa HH:MM:SS (timezone local)."""
    if pd.isna(imported_at):
        return "—"
    # imported_at chega em UTC; converte para fuso local de Sao Paulo (-03:00)
    ts = imported_at.tz_convert("America/Sao_Paulo")
    return ts.strftime("%d/%m/%Y %H:%M:%S")


def _render_card(
    grupo_db: str,
    valor: float,
    qtd: int,
    ticket: float,
    ultima_posicao: str,
) -> str:
    """Monta o HTML de um card de grupo de produto."""
    label_longo, label_curto = GRUPO_DISPLAY.get(
        grupo_db, (grupo_db, grupo_db)
    )
    return (
        '<div class="mg-pago-card">'
        '<div>'
        f'<div class="mg-pago-title">{label_longo}'
        f'<span class="mg-pago-alias">{label_curto}</span>'
        '</div>'
        f'<div class="mg-pago-sub">ÚLTIMA POSIÇÃO: {ultima_posicao}</div>'
        f'<div class="mg-pago-meta">'
        f'{formatar_numero(qtd)} propostas'
        '</div>'
        '</div>'
        '<div>'
        f'<div class="mg-pago-valor">{formatar_moeda(valor)}</div>'
        f'<div class="mg-pago-ticket">Ticket {formatar_moeda(ticket)}</div>'
        '</div>'
        '</div>'
    )


def render_tab_pagamentos_online(df: pd.DataFrame):
    """Renderiza a aba de Pagamentos Online em formato de cards.

    Args:
        df: DataFrame retornado por `carregar_pagamentos_online`. Espera
            ao menos as colunas GRUPO_PRODUTO, VALOR e IMPORTED_AT.
    """
    sac.divider(
        label="Pagamentos Online (estimativa do dia)",
        icon="lightning-charge-fill",
        align="left",
        color="orange",
    )

    st.info(
        "Estimativa nao consolidada. Os numeros oficiais entram no "
        "dashboard apenas D-1, apos o processamento do consolidado."
    )

    if df is None or df.empty:
        st.warning(
            "Nenhuma proposta paga online no momento. Verifique se "
            "o ciclo de ingestao do extrator DNA esta rodando."
        )
        return

    ultima_atualizacao = df["IMPORTED_AT"].max()
    st.caption(
        f"Atualizado {_formatar_atualizacao(ultima_atualizacao)} "
        f"({len(df):,} propostas)"
    )

    ultima_posicao = _formatar_timestamp_local(ultima_atualizacao)

    # Cards por grupo_produto. Ordem fixa: primeiro os mapeados em
    # GRUPO_DISPLAY (na ordem de declaracao), depois quaisquer outros
    # grupos novos que aparecerem no extrator.
    grupos_presentes = df["GRUPO_PRODUTO"].unique().tolist()
    ordem = [g for g in GRUPO_DISPLAY if g in grupos_presentes] + [
        g for g in grupos_presentes if g not in GRUPO_DISPLAY
    ]

    cards_html = [CSS_CARDS]
    for grupo in ordem:
        df_g = df[df["GRUPO_PRODUTO"] == grupo]
        qtd = len(df_g)
        valor = float(df_g["VALOR"].sum())
        ticket = valor / qtd if qtd > 0 else 0.0
        cards_html.append(
            _render_card(grupo, valor, qtd, ticket, ultima_posicao)
        )

    st.html("".join(cards_html))
