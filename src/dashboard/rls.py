"""
Row-Level Security (RLS) para o dashboard.

Filtra DataFrames de acordo com o perfil e escopo do
usuário logado, garantindo que cada papel veja apenas
os dados autorizados.

Perfis:
    admin            → sem filtro (todos os dados)
    gestor           → sem filtro (visao global)
    gerente_comercial → filtra por REGIAO (escopo = regiões)
    supervisor       → filtra por LOJA (escopo = lojas)
"""

from typing import Optional

import pandas as pd
import streamlit as st


def _obter_perfil_efetivo() -> Optional[dict]:
    """
    Retorna o perfil efetivo (considera 'visualizar como'
    para admin).
    """
    usuario = st.session_state.get("usuario_logado")
    if not usuario:
        return None

    visualizar_como = st.session_state.get("visualizar_como")
    if visualizar_como and usuario["perfil"] == "admin":
        return visualizar_como

    return usuario


def aplicar_rls(
    df: pd.DataFrame,
    coluna_regiao: str = "REGIAO",
    coluna_loja: str = "LOJA",
) -> pd.DataFrame:
    """
    Aplica filtro de segurança por linha no DataFrame.

    Args:
        df: DataFrame a ser filtrado.
        coluna_regiao: Nome da coluna de região.
        coluna_loja: Nome da coluna de loja.

    Returns:
        DataFrame filtrado conforme o perfil do usuário.
    """
    perfil = _obter_perfil_efetivo()
    if not perfil:
        return df

    role = perfil["perfil"]
    escopo = perfil.get("escopo", [])

    if role in ("admin", "gestor"):
        return df

    if role == "gerente_comercial" and escopo:
        if coluna_regiao in df.columns:
            return df[df[coluna_regiao].isin(escopo)].copy()

    if role == "supervisor" and escopo:
        if coluna_loja in df.columns:
            return df[df[coluna_loja].isin(escopo)].copy()

    return df


def aplicar_rls_metas(
    df_metas: pd.DataFrame,
    df_dados: pd.DataFrame,
    coluna_loja: str = "LOJA",
) -> pd.DataFrame:
    """
    Filtra metas para conter apenas lojas presentes nos
    dados já filtrados por RLS.
    """
    if coluna_loja not in df_metas.columns:
        return df_metas
    if coluna_loja not in df_dados.columns:
        return df_metas

    lojas_permitidas = df_dados[coluna_loja].unique()
    return df_metas[df_metas[coluna_loja].isin(lojas_permitidas)].copy()


def aplicar_rls_supervisores(
    df_supervisores: pd.DataFrame,
    df_dados: pd.DataFrame,
    coluna_regiao: str = "REGIAO",
    coluna_loja: str = "LOJA",
) -> pd.DataFrame:
    """
    Filtra supervisores conforme o escopo RLS.
    """
    perfil = _obter_perfil_efetivo()
    if not perfil:
        return df_supervisores

    role = perfil["perfil"]
    escopo = perfil.get("escopo", [])

    if role in ("admin", "gestor"):
        return df_supervisores

    if role == "gerente_comercial" and escopo:
        if coluna_regiao in df_supervisores.columns:
            return df_supervisores[df_supervisores[coluna_regiao].isin(escopo)].copy()

    if role == "supervisor" and escopo:
        if coluna_loja in df_supervisores.columns:
            lojas_permitidas = df_dados[coluna_loja].unique()
            return df_supervisores[
                df_supervisores[coluna_loja].isin(lojas_permitidas)
            ].copy()

    return df_supervisores


def obter_regioes_permitidas(
    regioes_disponiveis: list[str],
) -> list[str]:
    """
    Retorna as regiões que o usuário pode ver no filtro
    da sidebar.

    Admin e gerente_comercial veem as regiões do escopo.
    Supervisor não filtra por região (já filtrado por loja).
    """
    perfil = _obter_perfil_efetivo()
    if not perfil:
        return regioes_disponiveis

    role = perfil["perfil"]
    escopo = perfil.get("escopo", [])

    if role in ("admin", "gestor"):
        return regioes_disponiveis

    if role == "gerente_comercial" and escopo:
        filtradas = [r for r in regioes_disponiveis if r in escopo]
        if len(filtradas) > 1:
            return ["Todas"] + filtradas
        return filtradas

    # Supervisor: não exibe filtro de região
    return []
