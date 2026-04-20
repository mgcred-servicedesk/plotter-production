"""
Aba Detalhes: dados detalhados com filtros de loja, regiao e produto.
"""

import pandas as pd
import streamlit as st
import streamlit_antd_components as sac

from src.dashboard.components.tables import exibir_tabela
from src.dashboard.formatters import formatar_moeda, formatar_numero


def render_tab_detalhes(df):
    """Renderiza aba de Detalhes."""
    sac.divider(
        label="Dados Detalhados",
        icon="table",
        align="left",
        color="blue",
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        lojas = ["Todas"] + sorted(df["LOJA"].unique().tolist())
        filt_loja = st.selectbox("Loja", lojas)

    with col2:
        if "REGIAO" in df.columns:
            regioes = ["Todas"] + sorted(df["REGIAO"].unique().tolist())
            filt_reg = st.selectbox("Regiao (detalhe)", regioes)
        else:
            filt_reg = "Todas"

    with col3:
        prods = ["Todos"] + sorted(
            [str(x) for x in df["TIPO_PRODUTO"].unique() if pd.notna(x)]
        )
        filt_prod = st.selectbox("Produto", prods)

    df_d = df.copy()
    if filt_loja != "Todas":
        df_d = df_d[df_d["LOJA"] == filt_loja]
    if filt_reg != "Todas" and "REGIAO" in df.columns:
        df_d = df_d[df_d["REGIAO"] == filt_reg]
    if filt_prod != "Todos":
        df_d = df_d[df_d["TIPO_PRODUTO"] == filt_prod]

    st.markdown(f"**{len(df_d):,} registros encontrados**")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            "Total Valor",
            formatar_moeda(df_d["VALOR"].sum()),
        )
    with col2:
        st.metric(
            "Total Pontos",
            formatar_numero(df_d["pontos"].sum()),
        )
    with col3:
        tk = df_d["VALOR"].sum() / len(df_d) if len(df_d) > 0 else 0
        st.metric("Ticket Medio", formatar_moeda(tk))

    cols = [
        "DATA",
        "LOJA",
        "CONSULTOR",
        "TIPO_PRODUTO",
        "VALOR",
        "pontos",
    ]
    if "REGIAO" in df_d.columns:
        cols.insert(2, "REGIAO")

    exibir_tabela(
        df_d[cols],
        colunas_moeda=["VALOR"],
        colunas_numero=["pontos"],
    )
