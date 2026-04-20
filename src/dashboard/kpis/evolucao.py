"""
Analitico de consultores e evolucao diaria.
"""

from typing import Optional

import pandas as pd

from src.dashboard.kpis.gerais import excluir_supervisores


def calcular_analitico_consultores(
    df: pd.DataFrame,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Analitico de consultores por produto e loja."""
    if "CONSULTOR" not in df.columns:
        return pd.DataFrame()

    # Incluir seguros (VALOR=0) que contam apenas quantidade
    mask_producao = df["VALOR"] > 0
    if "is_bmg_med" in df.columns:
        mask_producao = mask_producao | df["is_bmg_med"]
    if "is_seguro_vida" in df.columns:
        mask_producao = mask_producao | df["is_seguro_vida"]

    df_v = excluir_supervisores(df[mask_producao], df_supervisores)

    df_v["PRODUTO_MIX"] = df_v["grupo_dashboard"].fillna("OUTROS")
    if "is_bmg_med" in df_v.columns:
        df_v.loc[df_v["is_bmg_med"], "PRODUTO_MIX"] = "BMG Med"
    if "is_seguro_vida" in df_v.columns:
        df_v.loc[df_v["is_seguro_vida"], "PRODUTO_MIX"] = "Vida Familiar"

    analitico = (
        df_v.groupby(["CONSULTOR", "LOJA", "REGIAO", "PRODUTO_MIX"])
        .agg(
            Qtd=("VALOR", "count"),
            Valor=("VALOR", "sum"),
            Pontos=("pontos", "sum"),
        )
        .reset_index()
    )

    analitico.columns = [
        "Consultor",
        "Loja",
        "Região",
        "Produto",
        "Qtd",
        "Valor",
        "Pontos",
    ]
    analitico["Ticket Médio"] = analitico.apply(
        lambda r: r["Valor"] / r["Qtd"] if r["Qtd"] > 0 else 0,
        axis=1,
    )
    return analitico.sort_values(
        ["Consultor", "Pontos"],
        ascending=[True, False],
    )


def calcular_evolucao_diaria(
    df: pd.DataFrame,
    ano: int,
    mes: int,
) -> pd.DataFrame:
    """Evolucao diaria de vendas e pontos."""
    if "DATA" not in df.columns:
        return pd.DataFrame()

    df_t = df.copy()
    df_t["DATA_DIA"] = pd.to_datetime(df_t["DATA"]).dt.date

    evolucao = (
        df_t.groupby("DATA_DIA")
        .agg(
            VALOR=("VALOR", "sum"),
            pontos=("pontos", "sum"),
        )
        .reset_index()
        .rename(columns={"DATA_DIA": "DATA"})
    )

    evolucao["DATA"] = pd.to_datetime(evolucao["DATA"])
    evolucao = evolucao.sort_values("DATA")
    evolucao["Valor Acumulado"] = evolucao["VALOR"].cumsum()
    evolucao["Pontos Acumulados"] = evolucao["pontos"].cumsum()

    return evolucao
