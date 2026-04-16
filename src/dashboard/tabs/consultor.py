"""
Aba "Meu Dashboard" para o perfil consultor.

Exibe:
  - 4 cards principais: Pontos, Pagos (valor),
    Em Analise (qtd), Cancelados (qtd).
    Com badges de atingimento, projecao, meta e barra.
  - Breakdown por produto (cards).
  - Ranking regional + global (lado a lado) com
    destaque para a posicao do consultor logado.
  - Media/DU em valor e em pontos.
"""

from typing import Optional

import pandas as pd
import streamlit as st
import streamlit_antd_components as sac

from src.dashboard.kpis.consultor import (
    calcular_breakdown_produtos_consultor,
    calcular_kpis_consultor,
    ranking_global,
    ranking_regional,
    top_com_voce,
)
from src.dashboard.ui.cards import (
    card_kpi_principal,
    progress_bar,
)
from src.reports.formatters import (
    formatar_moeda,
    formatar_numero,
    formatar_percentual,
)


# ══════════════════════════════════════════════════════
# Helpers internos
# ══════════════════════════════════════════════════════


def _obter_contexto_consultor(
    df_meu: pd.DataFrame,
    df_full: pd.DataFrame,
    consultor_nome: str,
) -> tuple[Optional[str], Optional[str]]:
    """
    Descobre loja e regiao do consultor. Tenta primeiro
    nos dados do proprio consultor; se vazio, busca no
    df_full (pre-RLS).
    """
    for origem in (df_meu, df_full):
        if origem is None or origem.empty:
            continue
        if "CONSULTOR" not in origem.columns:
            continue
        linhas = origem[origem["CONSULTOR"] == consultor_nome]
        if linhas.empty:
            continue
        loja = (
            linhas["LOJA"].iloc[0]
            if "LOJA" in linhas.columns and not linhas["LOJA"].isna().all()
            else None
        )
        regiao = (
            linhas["REGIAO"].iloc[0]
            if "REGIAO" in linhas.columns
            and not linhas["REGIAO"].isna().all()
            else None
        )
        return loja, regiao
    return None, None


# ══════════════════════════════════════════════════════
# Secoes
# ══════════════════════════════════════════════════════


def _render_cards_principais(kpis: dict) -> None:
    """Renderiza os 4 cards principais do consultor."""
    sac.divider(
        label="Indicadores Principais",
        icon="bar-chart-line",
        align="left",
        color="blue",
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        card_kpi_principal(
            label="Pontos",
            valor=formatar_numero(kpis["pontos_total"]),
            meta=kpis["meta_prata"],
            atingimento_pct=kpis["perc_ating_prata"],
            projecao=kpis["projecao_pontos"],
            projecao_label="pontos",
        )

    with col2:
        # Pagos em valor: usa meta_prata como ref (mesma
        # conta proporcional). Se meta_prata = 0, nao
        # renderiza atingimento.
        card_kpi_principal(
            label="Vendas Pagas",
            valor=formatar_moeda(kpis["pagos_valor"]),
            projecao=kpis["projecao_valor"],
            projecao_label="reais",
            legenda=(
                f"{formatar_numero(kpis['pagos_qtd'])} "
                f"contratos"
            ),
            mostrar_badge=False,
            atingimento_pct=None,
        )

    with col3:
        card_kpi_principal(
            label="Em Analise",
            valor=formatar_numero(kpis["analise_qtd"]),
            legenda=(
                f"Valor potencial: "
                f"{formatar_moeda(kpis['analise_valor'])}"
            ),
            mostrar_badge=False,
            atingimento_pct=None,
        )

    with col4:
        card_kpi_principal(
            label="Cancelados",
            valor=formatar_numero(kpis["cancelados_qtd"]),
            legenda=(
                f"{formatar_percentual(kpis['cancelados_pct'])} "
                f"sobre total"
            ),
            mostrar_badge=False,
            atingimento_pct=None,
        )


def _render_ritmo_projecao(kpis: dict) -> None:
    """Cards auxiliares: ritmo diario, meta restante,
    projecao vs meta ouro."""
    sac.divider(
        label="Ritmo & Projecao",
        icon="speedometer2",
        align="left",
        color="blue",
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Media / DU (Valor)",
            formatar_moeda(kpis["media_du_valor"]),
            f"{formatar_numero(kpis['du_decorridos'])} "
            f"DU decorridos",
        )

    with col2:
        st.metric(
            "Media / DU (Pontos)",
            formatar_numero(kpis["media_du_pontos"]),
            f"{formatar_numero(kpis['du_restantes'])} "
            f"DU restantes",
        )

    with col3:
        mdr = kpis["meta_diaria_restante"]
        ritmo = kpis["media_du_pontos"]
        if mdr == 0 and kpis["perc_ating_prata"] >= 100:
            st.metric(
                "Meta Diaria",
                "Meta atingida",
                f"Ritmo: {formatar_numero(ritmo)} pts/DU",
                delta_color="normal",
            )
        else:
            dif = ritmo - mdr
            dc = "normal" if dif >= 0 else "inverse"
            st.metric(
                "Meta Diaria Restante",
                f"{formatar_numero(mdr)} pts/DU",
                f"Ritmo atual: {formatar_numero(ritmo)} pts/DU",
                delta_color=dc,
            )

    with col4:
        perc_ouro = kpis["perc_ating_ouro"]
        st.metric(
            "Meta Ouro",
            formatar_numero(kpis["meta_ouro"]),
            f"{formatar_percentual(perc_ouro)} atingido",
            delta_color=(
                "normal" if perc_ouro >= 100
                else "off" if perc_ouro >= 80
                else "inverse"
            ),
        )
        progress_bar(perc_ouro)


def _render_breakdown_produtos(
    breakdown: pd.DataFrame,
) -> None:
    """Grid de cards por produto + linha de emissoes."""
    sac.divider(
        label="Producao por Produto",
        icon="box-seam",
        align="left",
        color="blue",
    )

    if breakdown.empty:
        st.info("Sem producao registrada no periodo.")
        return

    regulares = breakdown[~breakdown["eh_emissao"]]
    emissoes = breakdown[breakdown["eh_emissao"]]

    if not regulares.empty:
        cols = st.columns(min(4, len(regulares)))
        for i, (_, row) in enumerate(regulares.iterrows()):
            with cols[i % len(cols)]:
                st.metric(
                    row["produto"],
                    formatar_numero(row["pontos"]) + " pts",
                    f"{formatar_moeda(row['valor'])}",
                )
                st.caption(
                    f"{formatar_numero(row['qtd'])} contratos · "
                    f"TM {formatar_moeda(row['ticket_medio'])}"
                )

    if not emissoes.empty:
        st.markdown(
            '<div class="mg-section-sub">Emissoes '
            "(quantidade apenas)</div>",
            unsafe_allow_html=True,
        )
        cols = st.columns(min(4, len(emissoes)))
        for i, (_, row) in enumerate(emissoes.iterrows()):
            with cols[i % len(cols)]:
                st.metric(
                    row["produto"],
                    formatar_numero(row["qtd"]),
                    "emissoes",
                )


def _render_ranking_tabela(
    ranking: pd.DataFrame,
    titulo: str,
    top_n: int = 10,
) -> None:
    """Tabela de ranking destacando a linha do consultor."""
    st.markdown(f"**{titulo}**")
    if ranking.empty:
        st.info("Sem dados para o ranking.")
        return

    exibir = top_com_voce(ranking, top_n=top_n).copy()
    exibir["pontos"] = exibir["pontos"].map(formatar_numero)
    exibir["valor"] = exibir["valor"].map(formatar_moeda)

    total = len(ranking)
    voce = ranking[ranking["eh_voce"]]
    if not voce.empty:
        pos = int(voce.iloc[0]["posicao"])
        st.caption(f"Sua posicao: **{pos}º de {total}**")

    tabela = exibir[
        ["posicao", "CONSULTOR", "pontos", "valor", "qtd",
         "eh_voce"]
    ].rename(
        columns={
            "posicao": "#",
            "CONSULTOR": "Consultor",
            "pontos": "Pontos",
            "valor": "Valor",
            "qtd": "Contratos",
            "eh_voce": "_voce",
        }
    )

    def _highlight_voce(row: pd.Series) -> list[str]:
        if row.get("_voce"):
            return [
                "background-color: rgba(37,99,235,0.12); "
                "font-weight: 600"
            ] * len(row)
        return [""] * len(row)

    styled = tabela.style.apply(_highlight_voce, axis=1)

    st.dataframe(
        styled,
        width="stretch",
        hide_index=True,
        column_config={
            "_voce": None,  # ocultar coluna de controle
        },
    )


def _render_rankings(
    df_full: pd.DataFrame,
    consultor_nome: str,
    regiao: Optional[str],
) -> None:
    """Rankings regional e global, lado a lado."""
    sac.divider(
        label="Rankings",
        icon="trophy",
        align="left",
        color="blue",
    )

    col_reg, col_glo = st.columns(2)

    with col_reg:
        if regiao:
            r_reg = ranking_regional(
                df_full, consultor_nome, regiao,
            )
            _render_ranking_tabela(
                r_reg, f"Regional — {regiao}",
            )
        else:
            st.info("Regiao nao identificada.")

    with col_glo:
        r_glo = ranking_global(df_full, consultor_nome)
        _render_ranking_tabela(r_glo, "Global")


# ══════════════════════════════════════════════════════
# Entrypoint
# ══════════════════════════════════════════════════════


def render_tab_consultor(
    df_meu: pd.DataFrame,
    df_analise_meu: pd.DataFrame,
    df_cancelados_meu: pd.DataFrame,
    df_full: pd.DataFrame,
    metas_consultor: dict,
    consultor_nome: str,
    ano: int,
    mes: int,
    dia_atual: Optional[int] = None,
) -> None:
    """
    Renderiza a aba "Meu Dashboard" do consultor.

    Args:
        df_meu: Contratos pagos do consultor (pos-RLS).
        df_analise_meu: Propostas em analise do consultor.
        df_cancelados_meu: Contratos cancelados do consultor.
        df_full: Dataset completo pre-RLS (para rankings).
        metas_consultor: Dict com ``meta_prata`` e
            ``meta_ouro`` individuais do consultor (pontos).
        consultor_nome: Nome do consultor logado.
        ano, mes, dia_atual: Periodo de referencia.
    """
    meta_prata = float(metas_consultor.get("meta_prata", 0))
    meta_ouro = float(metas_consultor.get("meta_ouro", 0))

    kpis = calcular_kpis_consultor(
        df_meu=df_meu,
        df_analise_meu=df_analise_meu,
        df_cancelados_meu=df_cancelados_meu,
        meta_prata=meta_prata,
        meta_ouro=meta_ouro,
        ano=ano,
        mes=mes,
        dia_atual=dia_atual,
    )

    _, regiao = _obter_contexto_consultor(
        df_meu, df_full, consultor_nome,
    )

    _render_cards_principais(kpis)
    _render_ritmo_projecao(kpis)

    breakdown = calcular_breakdown_produtos_consultor(df_meu)
    _render_breakdown_produtos(breakdown)

    _render_rankings(df_full, consultor_nome, regiao)
