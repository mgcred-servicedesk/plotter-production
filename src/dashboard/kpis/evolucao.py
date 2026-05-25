"""
Evolucao diaria de vendas e pontos.
"""

import pandas as pd


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
