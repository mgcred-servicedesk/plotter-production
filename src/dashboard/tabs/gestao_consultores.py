"""
Aba Gestao: consultores por faixa de valor pago por produto MIX.

Filtro multi-criterio (combinado por E) sobre o VALOR pago em cada
produto MIX, organizado por regiao, com exportacao CSV. Visivel apenas
para admin/gestor/gerente_comercial (gating em permissions.py). O ``df``
recebido ja passou por RLS em ``app.py``, entao o gerente_comercial ve
somente as suas regioes.
"""
from typing import Dict, Optional

import pandas as pd
import streamlit as st
import streamlit_antd_components as sac

from src.dashboard.components.tables import exibir_tabela
from src.dashboard.kpis.gestao import (
    PRODUTOS_GESTAO,
    filtrar_por_criterios,
    vendas_mix_por_consultor,
)

_PRODUTO_LABELS = list(PRODUTOS_GESTAO)
_PRODUTOS_DEFAULT = ["CLT", "CNC", "Consignado"]

_Criterios = Dict[str, Dict[str, float | str]]


def _coletar_criterios(produtos: list[str]) -> _Criterios:
    """Renderiza os controles por produto e devolve os criterios ativos."""
    criterios: _Criterios = {}
    for rotulo in produtos:
        st.markdown(f"**{rotulo}**")
        col_modo, col_a, col_b = st.columns([1, 1, 1])
        with col_modo:
            modo = st.selectbox(
                "Modo",
                ["Menor que", "Entre"],
                key=f"gestao_modo_{rotulo}",
            )
        if modo == "Menor que":
            with col_a:
                maximo = st.number_input(
                    "Valor maximo (R$)",
                    min_value=0.0,
                    value=15000.0,
                    step=1000.0,
                    key=f"gestao_menor_{rotulo}",
                )
            criterios[rotulo] = {"modo": "menor", "max": maximo}
        else:
            with col_a:
                minimo = st.number_input(
                    "Minimo (R$)",
                    min_value=0.0,
                    value=0.0,
                    step=1000.0,
                    key=f"gestao_min_{rotulo}",
                )
            with col_b:
                maximo = st.number_input(
                    "Maximo (R$)",
                    min_value=0.0,
                    value=15000.0,
                    step=1000.0,
                    key=f"gestao_max_{rotulo}",
                )
            criterios[rotulo] = {"modo": "entre", "min": minimo, "max": maximo}
    return criterios


def render_tab_gestao(
    df: pd.DataFrame,
    df_sup: Optional[pd.DataFrame] = None,
) -> None:
    """Renderiza a aba de gestao de consultores por faixa de valor."""
    sac.divider(
        label="Gestao de Consultores",
        icon="funnel-fill",
        align="left",
        color="blue",
    )
    st.markdown(
        "Liste consultores pelo **valor pago** em cada produto. Os "
        "criterios combinam por **E** (todos precisam ser atendidos)."
    )

    tabela = vendas_mix_por_consultor(df, df_sup)
    if tabela.empty:
        st.warning("Nenhum consultor com vendas no periodo.")
        return

    produtos_sel = st.multiselect(
        "Produtos do criterio",
        _PRODUTO_LABELS,
        default=_PRODUTOS_DEFAULT,
        key="gestao_produtos",
    )

    criterios = _coletar_criterios(produtos_sel) if produtos_sel else {}
    resultado = filtrar_por_criterios(tabela, criterios)

    sac.divider(label="Consultores", icon="people", align="left", color="gray")

    total = f"{len(resultado):,}".replace(",", ".")
    if criterios:
        st.markdown(f"**{total} consultores** atendem aos criterios.")
    else:
        st.info("Selecione ao menos um produto para filtrar.")

    # Foco por produto: exibe apenas as colunas dos produtos selecionados
    # (mais identificacao), ocultando os demais produtos e o Total. Sem
    # selecao, mostra a visao geral com todos os produtos + Total.
    if produtos_sel:
        cols_id = [
            c for c in ("Regiao", "Loja", "Consultor")
            if c in resultado.columns
        ]
        cols_prod = [c for c in _PRODUTO_LABELS if c in produtos_sel]
        resultado = resultado[cols_id + cols_prod]

    colunas_moeda = [
        c for c in (*_PRODUTO_LABELS, "Total") if c in resultado.columns
    ]
    exibir_tabela(resultado, colunas_moeda=colunas_moeda)

    if not resultado.empty:
        csv = resultado.to_csv(index=False, sep=";", decimal=",")
        st.download_button(
            label="Exportar CSV",
            data=csv,
            file_name="consultores_gestao.csv",
            mime="text/csv",
            key="gestao_export",
            icon=":material/download:",
        )
