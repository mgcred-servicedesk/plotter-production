"""
Aba Em Analise: detalhamento do pipeline de contratos em analise.
"""

import pandas as pd
import streamlit as st
import streamlit_antd_components as sac

from src.dashboard.components.tables import exibir_tabela
from src.dashboard.formatters import formatar_moeda, formatar_numero


def render_tab_em_analise(df_analise, df_sup):
    """Renderiza aba de contratos Em Analise."""
    sac.divider(
        label="Contratos em Analise",
        icon="clock-history",
        align="left",
        color="orange",
    )

    if df_analise.empty:
        st.warning("Nenhum contrato em analise no periodo.")
        return

    df_a = df_analise.copy()
    if df_sup is not None and "SUPERVISOR" in df_sup.columns:
        supervisores = df_sup["SUPERVISOR"].unique()
    else:
        supervisores = []

    # ── Filtros ────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        lojas = ["Todas"] + sorted(df_a["LOJA"].unique().tolist())
        filt_loja = st.selectbox("Loja", lojas, key="analise_loja")
    with col2:
        if "REGIAO" in df_a.columns:
            regioes = ["Todas"] + sorted(df_a["REGIAO"].unique().tolist())
            filt_reg = st.selectbox(
                "Regiao", regioes, key="analise_regiao"
            )
        else:
            filt_reg = "Todas"
    with col3:
        status_opts = ["Todos"] + sorted(
            [str(x) for x in df_a["STATUS_BANCO"].unique() if pd.notna(x)]
        )
        filt_status = st.selectbox(
            "Status Banco", status_opts, key="analise_status"
        )

    if filt_loja != "Todas":
        df_a = df_a[df_a["LOJA"] == filt_loja]
    if filt_reg != "Todas" and "REGIAO" in df_a.columns:
        df_a = df_a[df_a["REGIAO"] == filt_reg]
    if filt_status != "Todos":
        df_a = df_a[df_a["STATUS_BANCO"] == filt_status]

    qtd_emissao_analise = (
        (df_a["TIPO OPER."].isin(["CARTÃO BENEFICIO", "Venda Pré-Adesão"])).sum()
        if "TIPO OPER." in df_a.columns
        else 0
    )
    qtd_sem_emissao = len(df_a) - qtd_emissao_analise

    st.markdown(f"**{len(df_a):,} propostas em analise**")

    # ── KPIs resumo ───────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Valor Total", formatar_moeda(df_a["VALOR"].sum()))
    with col2:
        st.metric(
            "Quantidade",
            formatar_numero(len(df_a)),
            f"{formatar_numero(qtd_sem_emissao)} operacoes"
            f" + {formatar_numero(qtd_emissao_analise)} emissoes",
        )
    with col3:
        tk = df_a["VALOR"].sum() / len(df_a) if len(df_a) > 0 else 0
        st.metric("Ticket Medio", formatar_moeda(tk))
    with col4:
        cons = df_a["CONSULTOR"].unique()
        cons_sem_sup = [c for c in cons if c not in supervisores]
        st.metric("Consultores", formatar_numero(len(cons_sem_sup)))

    # ── Breakdown por produto ─────────────────────
    sac.divider(
        label="Por Produto",
        icon="tags-fill",
        align="left",
        color="gray",
    )

    if "grupo_dashboard" in df_a.columns:
        df_prod = (
            df_a[df_a["grupo_dashboard"].notna()]
            .groupby("grupo_dashboard")
            .agg(
                Qtd=("VALOR", "count"),
                Valor=("VALOR", "sum"),
            )
            .reset_index()
            .rename(columns={"grupo_dashboard": "Produto"})
            .sort_values("Valor", ascending=False)
        )
        df_prod["Ticket Medio"] = df_prod.apply(
            lambda r: r["Valor"] / r["Qtd"] if r["Qtd"] > 0 else 0,
            axis=1,
        )
        exibir_tabela(df_prod, colunas_moeda=["Valor", "Ticket Medio"])

    # ── Breakdown BMG Med e Vida Familiar ───────
    sac.divider(
        label="BMG Med e Vida Familiar (Em Análise)",
        icon="heart-pulse",
        align="left",
        color="gray",
    )

    if "TIPO OPER." in df_a.columns:
        # Contar BMG MED e Seguro em análise
        mask_bmg_med = df_a["TIPO OPER."] == "BMG MED"
        mask_seguro = df_a["TIPO OPER."] == "Seguro"

        # Breakdown por status para BMG MED
        if mask_bmg_med.any():
            st.markdown("**BMG Med - Status:**")
            df_bmg_status = (
                df_a[mask_bmg_med]
                .groupby("STATUS_BANCO")
                .size()
                .reset_index(name="Quantidade")
            )
            st.dataframe(df_bmg_status, width="stretch", hide_index=True)

        # Breakdown por sub-status para Seguro
        if mask_seguro.any():
            st.markdown("**Vida Familiar (Seguro) - Status:**")
            df_seg_status = (
                df_a[mask_seguro]
                .groupby("STATUS_BANCO")
                .size()
                .reset_index(name="Quantidade")
            )
            st.dataframe(df_seg_status, width="stretch", hide_index=True)

        # Resumo geral
        total_bmg = int(mask_bmg_med.sum())
        total_seguro = int(mask_seguro.sum())

        if total_bmg > 0 or total_seguro > 0:
            st.info(
                f"📌 **Resumo:** {total_bmg} BMG Med + {total_seguro} "
                f"Vida Familiar em análise. "
                f"Estes contratos aparecerão nos 'Contratos Pagos' "
                f"quando o Sub-Status mudar para 'Liquidada'. "
                f"Valor não é contabilizado (apenas quantidade)."
            )

    # ── Breakdown por loja ────────────────────────
    sac.divider(
        label="Por Loja",
        icon="shop",
        align="left",
        color="gray",
    )

    df_loja = (
        df_a.groupby("LOJA")
        .agg(
            Qtd=("VALOR", "count"),
            Valor=("VALOR", "sum"),
        )
        .reset_index()
        .rename(columns={"LOJA": "Loja"})
        .sort_values("Valor", ascending=False)
    )
    df_loja["Ticket Medio"] = df_loja.apply(
        lambda r: r["Valor"] / r["Qtd"] if r["Qtd"] > 0 else 0,
        axis=1,
    )
    exibir_tabela(df_loja, colunas_moeda=["Valor", "Ticket Medio"])

    # ── Tabela detalhada ──────────────────────────
    sac.divider(
        label="Detalhamento",
        icon="table",
        align="left",
        color="gray",
    )

    cols = [
        "DATA_CADASTRO",
        "LOJA",
        "CONSULTOR",
        "TIPO_PRODUTO",
        "VALOR",
        "STATUS_BANCO",
        "BANCO",
    ]
    if "REGIAO" in df_a.columns:
        cols.insert(2, "REGIAO")

    exibir_tabela(
        df_a[cols].sort_values("DATA_CADASTRO", ascending=False),
        colunas_moeda=["VALOR"],
    )
