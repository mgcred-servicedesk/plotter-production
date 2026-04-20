"""
Aba Produtos: KPIs, meta diaria e grafico por produto.
"""

from typing import Optional

import pandas as pd
import streamlit as st
import streamlit_antd_components as sac

from src.dashboard.components.tables import exibir_tabela
from src.dashboard.formatters import formatar_moeda
from src.dashboard.kpis.produtos import calcular_kpis_por_produto
from src.dashboard.kpis.regioes import (
    calcular_evolucao_media_du,
    calcular_heatmap_regiao_produto,
)
from src.dashboard.ui.charts import (
    criar_grafico_produtos,
    criar_heatmap_regiao_produto,
)
from src.dashboard.ui.header import chart_card_close, chart_card_open

# Regiões excluídas do heatmap comparativo
_REGIOES_EXCLUIR_HM: frozenset = frozenset({"ALEXANDRE"})

# ── Configuracao dos 4 produtos de quantidade ────────

_PRODS_QTD = [
    {
        "label": "Emissão",
        "subtabs": [
            {
                "nome_col": "Cartão Benefício",
                "tipo_oper": ["CARTÃO BENEFICIO"],
            },
            {
                "nome_col": "Venda Pré-Adesão",
                "tipo_oper": ["Venda Pré-Adesão"],
            },
        ],
        "col_dig_tipo": [
            "CARTÃO BENEFICIO",
            "Venda Pré-Adesão",
        ],
    },
    {
        "label": "Super Conta",
        "subtabs": [
            {
                "nome_col": "Super Conta",
                "subtipo": "SUPER CONTA",
            },
        ],
        "col_dig_subtipo": "SUPER CONTA",
    },
    {
        "label": "BMG Med",
        "subtabs": [
            {
                "nome_col": "BMG Med",
                "tipo_oper": ["BMG MED"],
            },
        ],
        "col_dig_tipo": ["BMG MED"],
    },
    {
        "label": "Vida Familiar",
        "subtabs": [
            {
                "nome_col": "Vida Familiar",
                "tipo_oper": ["Seguro"],
            },
        ],
        "col_dig_tipo": ["Seguro"],
    },
]


def _html_tabela_evolucao(df: pd.DataFrame) -> str:
    """Gera tabela HTML estilizada de evolução de Média DU."""
    cabecalhos = ["Região", "Mês Anterior", "Mês Atual", "% Evolução"]
    header_cells = "".join(
        f'<th class="mg-rt-th">{c}</th>' for c in cabecalhos
    )
    rows_html = ""
    total_idx = len(df) - 1
    for i, row in df.iterrows():
        is_total = i == total_idx
        tr_cls = "mg-rt-tr--total" if is_total else (
            "mg-rt-tr--odd" if i % 2 else ""
        )
        perc = row["% Evolução"]
        if perc > 0.5:
            perc_cls = "mg-evol-pos"
            sinal = "+"
        elif perc < -0.5:
            perc_cls = "mg-evol-neg"
            sinal = ""
        else:
            perc_cls = "mg-evol-neu"
            sinal = ""

        def _fmt(v: float) -> str:
            return formatar_moeda(v).replace("$", "&#36;")

        cells = (
            f'<td class="mg-rt-td mg-rt-td--loja">'
            f'{row["Região"]}</td>'
            f'<td class="mg-rt-td mg-rt-td--num">'
            f'{_fmt(row["Mês Anterior"])}</td>'
            f'<td class="mg-rt-td mg-rt-td--num">'
            f'{_fmt(row["Mês Atual"])}</td>'
            f'<td class="mg-rt-td mg-rt-td--num {perc_cls}">'
            f'{sinal}{perc:.2f}%</td>'
        )
        rows_html += (
            f'<tr class="mg-rt-tr {tr_cls}">{cells}</tr>'
        )
    return (
        '<div class="mg-rt-wrap">'
        '<div class="mg-rt-header">Evolução Média DU por Região</div>'
        '<table class="mg-rt-table">'
        f'<thead><tr>{header_cells}</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        '</table></div>'
    )


def _html_tabela_regional(
    regiao: str,
    df: pd.DataFrame,
    cols_num: list,
) -> str:
    """Gera tabela HTML estilizada para análise regional."""
    header_cells = "".join(
        f'<th class="mg-rt-th">{c}</th>'
        for c in ["Loja"] + cols_num
    )
    rows_html = ""
    total_idx = len(df) - 1
    for i, row in df.iterrows():
        is_total = i == total_idx
        tr_cls = "mg-rt-tr--total" if is_total else (
            "mg-rt-tr--odd" if i % 2 else ""
        )
        loja_val = str(row["Loja"])
        cells = f'<td class="mg-rt-td mg-rt-td--loja">{loja_val}</td>'
        for c in cols_num:
            num = int(row[c]) if pd.notna(row[c]) else 0
            analise_cls = (
                " mg-rt-td--analise" if c == "Análise" else ""
            )
            cells += (
                f'<td class="mg-rt-td mg-rt-td--num'
                f'{analise_cls}">{num}</td>'
            )
        rows_html += (
            f'<tr class="mg-rt-tr {tr_cls}">{cells}</tr>'
        )
    return (
        f'<div class="mg-rt-wrap">'
        f'<div class="mg-rt-header">{regiao}</div>'
        f'<table class="mg-rt-table">'
        f'<thead><tr>{header_cells}</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table></div>'
    )


def _contar_por_regiao(
    df: pd.DataFrame,
    filtro: pd.Series,
    nome: str,
) -> pd.DataFrame:
    """Agrupa df filtrado por REGIAO/LOJA e retorna contagem."""
    if (
        filtro is None
        or not filtro.any()
        or "REGIAO" not in df.columns
        or "LOJA" not in df.columns
    ):
        return pd.DataFrame(columns=["REGIAO", "LOJA", nome])
    return (
        df[filtro]
        .groupby(["REGIAO", "LOJA"])
        .size()
        .reset_index(name=nome)
    )


def _render_produto_regional(
    df: pd.DataFrame,
    df_analise: pd.DataFrame,
    cfg: dict,
    du_total: int,
    du_dec: int,
    df_sup: pd.DataFrame,
) -> None:
    """Renderiza a tabela regional de um produto de quantidade."""
    supervisores: set = set()
    if (
        df_sup is not None
        and not df_sup.empty
        and "CONSULTOR" in df_sup.columns
    ):
        supervisores = set(df_sup["CONSULTOR"].unique())

    def _excluir_sup(frame: pd.DataFrame) -> pd.DataFrame:
        if supervisores and "CONSULTOR" in frame.columns:
            return frame[~frame["CONSULTOR"].isin(supervisores)]
        return frame

    df_p = _excluir_sup(df)
    df_a = _excluir_sup(
        df_analise if df_analise is not None else pd.DataFrame()
    )

    # ── Colunas de efetivados (pode ter mais de 1 para Emissão) ──
    dfs_ef = []
    for sub in cfg["subtabs"]:
        if "tipo_oper" in sub:
            mask = (
                df_p["TIPO OPER."].isin(sub["tipo_oper"])
                if "TIPO OPER." in df_p.columns
                else pd.Series(False, index=df_p.index)
            )
        else:
            subtipo = sub.get("subtipo", "")
            mask = (
                df_p["SUBTIPO"].astype(str)
                .str.strip()
                .str.upper()
                == subtipo.upper()
                if "SUBTIPO" in df_p.columns
                else pd.Series(False, index=df_p.index)
            )
        dfs_ef.append(_contar_por_regiao(df_p, mask, sub["nome_col"]))

    df_merged = dfs_ef[0]
    for extra in dfs_ef[1:]:
        df_merged = pd.merge(
            df_merged, extra, on=["REGIAO", "LOJA"], how="outer"
        )

    # ── Digitados (em análise) ────────────────────────
    if not df_a.empty:
        if "col_dig_subtipo" in cfg:
            mask_dig = (
                df_a["SUBTIPO"].astype(str)
                .str.strip()
                .str.upper()
                == cfg["col_dig_subtipo"].upper()
                if "SUBTIPO" in df_a.columns
                else pd.Series(False, index=df_a.index)
            )
        else:
            tipos = cfg.get("col_dig_tipo", [])
            mask_dig = (
                df_a["TIPO OPER."].isin(tipos)
                if "TIPO OPER." in df_a.columns
                else pd.Series(False, index=df_a.index)
            )
        df_dig = _contar_por_regiao(df_a, mask_dig, "Análise")
    else:
        df_dig = pd.DataFrame(columns=["REGIAO", "LOJA", "Análise"])

    df_final = pd.merge(
        df_dig, df_merged, on=["REGIAO", "LOJA"], how="outer"
    ).fillna(0)

    # ── Colunas numéricas como int ────────────────────
    cols_num = [
        c for c in df_final.columns if c not in ("REGIAO", "LOJA")
    ]
    for c in cols_num:
        df_final[c] = df_final[c].astype(int)

    # ── Coluna Total (se houver mais de 1 col de efetivados) ──
    ef_cols = [s["nome_col"] for s in cfg["subtabs"]]
    if len(ef_cols) > 1:
        df_final["Total"] = df_final[ef_cols].sum(axis=1)
        ef_cols.append("Total")

    # ── Projeção ──────────────────────────────────────
    ef_base = ef_cols[0] if len(ef_cols) == 1 else "Total"
    if du_dec > 0:
        df_final["Proj"] = (
            df_final[ef_base] / du_dec * du_total
        ).round(0).astype(int)
    else:
        df_final["Proj"] = 0

    if df_final.empty or "REGIAO" not in df_final.columns:
        st.info("Sem dados para este produto no período.")
        return

    df_final = df_final.sort_values(["REGIAO", "LOJA"])
    regioes = sorted(df_final["REGIAO"].dropna().unique())
    if not regioes:
        st.info("Sem dados regionais disponíveis.")
        return

    col_exib = ["Análise"] + ef_cols + ["Proj"]
    col_exib = [c for c in col_exib if c in df_final.columns]

    # ── Layout 2 colunas de regiões ──────────────────
    metade = (len(regioes) + 1) // 2
    grp_esq, grp_dir = regioes[:metade], regioes[metade:]

    col_esq, col_dir = st.columns(2)
    for col_st, grupo in [(col_esq, grp_esq), (col_dir, grp_dir)]:
        with col_st:
            for reg in grupo:
                df_reg = (
                    df_final[df_final["REGIAO"] == reg]
                    [["LOJA"] + col_exib]
                    .copy()
                    .rename(columns={"LOJA": "Loja"})
                )
                total_row = {"Loja": "Total"}
                for c in col_exib:
                    total_row[c] = int(df_reg[c].sum())
                df_reg = pd.concat(
                    [df_reg, pd.DataFrame([total_row])],
                    ignore_index=True,
                )
                st.markdown(
                    _html_tabela_regional(reg, df_reg, col_exib),
                    unsafe_allow_html=True,
                )


def render_tab_produtos(
    df: pd.DataFrame,
    df_metas_produto: pd.DataFrame,
    categorias: pd.DataFrame,
    ano: int,
    mes: int,
    dia_atual: int,
    df_sup: pd.DataFrame,
    df_analise: Optional[pd.DataFrame] = None,
    du_total: int = 0,
    du_decorridos: int = 0,
    df_full: Optional[pd.DataFrame] = None,
    df_metas_produto_full: Optional[pd.DataFrame] = None,
    df_ant: Optional[pd.DataFrame] = None,
    du_dec_ant: int = 0,
) -> None:
    """Renderiza aba de Produtos."""
    sac.divider(
        label="Analise de Produtos",
        icon="tags-fill",
        align="left",
        color="blue",
    )

    df_prod = calcular_kpis_por_produto(
        df,
        df_metas_produto,
        categorias,
        ano,
        mes,
        dia_atual,
        df_sup,
    )

    # ── Heatmap regional + tabela de evolução ───────
    from src.dashboard.rls import _obter_perfil_efetivo
    perfil = _obter_perfil_efetivo()
    perfil_role = perfil["perfil"] if perfil else None
    pode_heatmap = perfil_role in (
        "admin", "gestor", "gerente_comercial",
    )

    if (
        pode_heatmap
        and df_full is not None
        and not df_full.empty
        and df_metas_produto_full is not None
        and categorias is not None
        and not df_metas_produto_full.empty
    ):
        sac.divider(
            label="Comparativo Regional",
            icon="grid-3x3-gap-fill",
            align="left",
            color="gray",
        )
        df_hm = df_full[
            ~df_full.get("REGIAO", pd.Series(dtype=str))
            .str.upper()
            .isin(_REGIOES_EXCLUIR_HM)
        ] if "REGIAO" in df_full.columns else df_full

        df_ranking, df_ating = calcular_heatmap_regiao_produto(
            df_hm, df_metas_produto_full, categorias,
        )

        df_evol = calcular_evolucao_media_du(
            df_full,
            max(du_decorridos, 1),
            df_ant,
            max(du_dec_ant, 1),
            regioes_excluir=_REGIOES_EXCLUIR_HM,
        )

        col_hm, col_ev = st.columns([2, 1])
        with col_hm:
            if not df_ranking.empty:
                fig_hm = criar_heatmap_regiao_produto(
                    df_ranking, df_ating,
                )
                chart_card_open(
                    "Ranking Região × Produto",
                    icon="🗺️",
                    subtitle="Posição de cada região por produto"
                    " (1º = melhor atingimento)",
                )
                st.plotly_chart(fig_hm, width="stretch")
                chart_card_close()
        with col_ev:
            if not df_evol.empty:
                st.markdown(
                    _html_tabela_evolucao(df_evol),
                    unsafe_allow_html=True,
                )

    fig = criar_grafico_produtos(df_prod)
    chart_card_open(
        "Analise Completa de Produtos",
        icon="📦",
        subtitle="Realizado vs Meta, Atingimento, Projecao e Ticket Medio",
    )
    st.plotly_chart(fig, width="stretch")
    chart_card_close()

    sac.divider(
        label="KPIs por Produto",
        icon="table",
        align="left",
        color="gray",
    )
    exibir_tabela(df_prod)
    st.info(
        "FGTS/Ant. Ben./CNC 13o: conjunto FGTS + "
        "Antecipação de Benefício + CNC 13º"
    )

    # ── Análise Regional: Emissão e Seguros ─────────
    if df_analise is not None:
        sac.divider(
            label="Emissão e Seguros — Análise Regional",
            icon="geo-alt-fill",
            align="left",
            color="gray",
        )

        tab_labels = [p["label"] for p in _PRODS_QTD]
        tabs = st.tabs(tab_labels)
        for tab, cfg in zip(tabs, _PRODS_QTD):
            with tab:
                _render_produto_regional(
                    df,
                    df_analise,
                    cfg,
                    du_total,
                    du_decorridos,
                    df_sup,
                )
