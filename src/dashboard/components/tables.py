"""
Componente de tabelas do dashboard usando st.dataframe nativo.

Utiliza column_config do Streamlit para formatação visual
mantendo os dados numéricos para ordenação e filtros corretos.
"""
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st


# Altura mínima e máxima para tabelas (em pixels)
_ALTURA_MINIMA = 150
_ALTURA_MAXIMA = 600
_ALTURA_POR_LINHA = 35
_ALTURA_HEADER = 50


def _calcular_altura(num_linhas: int) -> int:
    """Calcula altura dinâmica baseada no número de linhas."""
    altura = _ALTURA_HEADER + (num_linhas * _ALTURA_POR_LINHA)
    return max(_ALTURA_MINIMA, min(altura, _ALTURA_MAXIMA))


def _detectar_column_config(
    df: pd.DataFrame,
    colunas_moeda: Optional[List[str]] = None,
    colunas_percentual: Optional[List[str]] = None,
    colunas_numero: Optional[List[str]] = None,
) -> Dict:
    """
    Gera column_config automático baseado nos nomes
    das colunas do DataFrame.

    Prioriza listas explícitas; caso não fornecidas,
    detecta pelo nome da coluna.
    """
    config = {}

    moeda_keywords = [
        "Valor", "Meta", "Ticket", "Projeção", "Média DU",
        "Meta Diária", "Valor Médio", "Mediano", "Mínimo",
        "Máximo",
    ]
    perc_keywords = ["% Ating", "% Proj", "Atingimento %"]
    numero_keywords = [
        "Pontos", "Qtd", "Posição", "Nº Lojas",
        "Nº Consultores", "Num Consultores", "TOTAL",
    ]

    for col in df.columns:
        if colunas_moeda and col in colunas_moeda:
            config[col] = st.column_config.NumberColumn(
                col, format="R$ %.2f"
            )
        elif colunas_percentual and col in colunas_percentual:
            config[col] = st.column_config.NumberColumn(
                col, format="%.1f%%"
            )
        elif colunas_numero and col in colunas_numero:
            config[col] = st.column_config.NumberColumn(
                col, format="%.0f"
            )
        elif any(kw in col for kw in perc_keywords):
            config[col] = st.column_config.NumberColumn(
                col, format="%.1f%%"
            )
        elif any(kw in col for kw in moeda_keywords):
            config[col] = st.column_config.NumberColumn(
                col, format="R$ %.2f"
            )
        elif any(kw in col for kw in numero_keywords):
            config[col] = st.column_config.NumberColumn(
                col, format="%.0f"
            )

    return config


def exibir_tabela(
    df: pd.DataFrame,
    altura: Optional[int] = None,
    colunas_moeda: Optional[List[str]] = None,
    colunas_percentual: Optional[List[str]] = None,
    colunas_numero: Optional[List[str]] = None,
    column_config: Optional[Dict] = None,
) -> None:
    """
    Exibe tabela usando st.dataframe nativo com formatação
    automática via column_config.

    O tema (claro/escuro) é herdado automaticamente do
    Streamlit via config.toml.

    Args:
        df: DataFrame a ser exibido (dados numéricos
            originais).
        altura: Altura fixa em pixels. Se None, calcula
            dinamicamente.
        colunas_moeda: Lista de colunas para formatar como
            moeda (R$).
        colunas_percentual: Lista de colunas para formatar
            como percentual.
        colunas_numero: Lista de colunas para formatar como
            número inteiro.
        column_config: Configuração manual de colunas.
            Sobrescreve a detecção automática.
    """
    if df.empty:
        st.info("Nenhum dado disponível para exibição.")
        return

    if column_config is None:
        config = _detectar_column_config(
            df, colunas_moeda, colunas_percentual, colunas_numero
        )
    else:
        config = column_config

    h = altura if altura else _calcular_altura(len(df))

    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        height=h,
        column_config=config,
    )
