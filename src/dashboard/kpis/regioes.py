"""
KPIs e rankings por regiao: visao por regiao, heatmap
regiao x produto, media de producao por regiao e
conjunto de rankings regionais.
"""

from typing import Dict, Optional, Tuple

import pandas as pd

from src.dashboard.kpis.gerais import (
    contar_consultores,
    excluir_supervisores,
)
from src.shared.dias_uteis import calcular_dias_uteis


def calcular_kpis_por_regiao(
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    ano: int,
    mes: int,
    dia_atual: Optional[int] = None,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Calcula KPIs por regiao."""
    if "REGIAO" not in df.columns:
        return pd.DataFrame()

    du_total, du_dec, _ = calcular_dias_uteis(ano, mes, dia_atual)

    dados = []
    for regiao in sorted(df["REGIAO"].unique()):
        df_r = df[df["REGIAO"] == regiao]

        valor = df_r["VALOR"].sum()
        pontos = df_r["pontos"].sum()
        num_lojas = df_r["LOJA"].nunique()
        num_cons = contar_consultores(df_r, df_supervisores)

        meta_prata = 0
        if "META_PRATA" in df_metas.columns:
            lojas_r = df_r["LOJA"].unique()
            meta_prata = df_metas[df_metas["LOJA"].isin(lojas_r)]["META_PRATA"].sum()

        perc = (pontos / meta_prata * 100) if meta_prata > 0 else 0
        media_du = valor / du_dec if du_dec > 0 else 0
        projecao = media_du * du_total
        valor_medio_cons = valor / num_cons if num_cons > 0 else 0

        dados.append(
            {
                "Região": regiao,
                "Valor": valor,
                "Pontos": pontos,
                "Meta Prata": meta_prata,
                "% Atingimento": perc,
                "Nº Lojas": num_lojas,
                "Nº Consultores": num_cons,
                "Valor Médio/Consultor": valor_medio_cons,
                "Média DU": media_du,
                "Projeção": projecao,
            }
        )

    return pd.DataFrame(dados)


def calcular_heatmap_regiao_produto(
    df: pd.DataFrame,
    df_metas_produto: pd.DataFrame,
    categorias: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Calcula matriz de ranking por regiao x produto.

    Cada celula contem a posicao da regiao naquele produto,
    baseada no % de atingimento (valor realizado / meta).

    Returns:
        (df_ranking, df_atingimento): ranking e % atingimento.
    """
    if "REGIAO" not in df.columns or "grupo_dashboard" not in df.columns:
        return pd.DataFrame(), pd.DataFrame()

    # Mapeamento grupo_dashboard → grupo_meta
    grupo_meta_map = (
        categorias[categorias["grupo_dashboard"].notna()]
        .groupby("grupo_dashboard")["grupo_meta"]
        .first()
        .to_dict()
    )

    grupos = sorted(
        categorias[categorias["grupo_dashboard"].notna()][
            "grupo_dashboard"
        ]
        .unique()
        .tolist()
    )

    regioes = sorted(df["REGIAO"].unique())

    # Calcular % atingimento por regiao x produto
    dados_ating = []
    for regiao in regioes:
        df_r = df[df["REGIAO"] == regiao]
        lojas_r = df_r["LOJA"].unique()
        row = {"Região": regiao}

        for grupo in grupos:
            valor = df_r[df_r["grupo_dashboard"] == grupo][
                "VALOR"
            ].sum()

            meta_key = grupo_meta_map.get(grupo, grupo)
            meta = 0
            if (
                not df_metas_produto.empty
                and meta_key in df_metas_produto.columns
            ):
                meta = (
                    pd.to_numeric(
                        df_metas_produto[
                            df_metas_produto["LOJA"].isin(lojas_r)
                        ][meta_key],
                        errors="coerce",
                    )
                    .fillna(0)
                    .sum()
                )

            perc = (valor / meta * 100) if meta > 0 else 0
            row[grupo] = perc

        dados_ating.append(row)

    df_ating = pd.DataFrame(dados_ating).set_index("Região")

    # Gerar ranking (1 = melhor % atingimento)
    df_ranking = df_ating.rank(ascending=False, method="min").astype(
        int
    )

    return df_ranking, df_ating


def calcular_media_producao_regiao(
    df: pd.DataFrame,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Media de producao por consultor por regiao."""
    if "CONSULTOR" not in df.columns or "REGIAO" not in df.columns:
        return pd.DataFrame()

    df_v = excluir_supervisores(df[df["VALOR"] > 0], df_supervisores)

    por_cons = (
        df_v.groupby(["REGIAO", "CONSULTOR"])
        .agg(
            VALOR=("VALOR", "sum"),
            pontos=("pontos", "sum"),
        )
        .reset_index()
    )

    stats = (
        por_cons.groupby("REGIAO")
        .agg(
            **{
                "Valor Médio": ("VALOR", "mean"),
                "Valor Mediano": ("VALOR", "median"),
                "Valor Desvio": ("VALOR", "std"),
                "Valor Mínimo": ("VALOR", "min"),
                "Valor Máximo": ("VALOR", "max"),
                "Pontos Médio": ("pontos", "mean"),
                "Pontos Mediano": ("pontos", "median"),
                "Pontos Desvio": ("pontos", "std"),
                "Pontos Mínimo": ("pontos", "min"),
                "Pontos Máximo": ("pontos", "max"),
                "Num Consultores": ("CONSULTOR", "count"),
            }
        )
        .reset_index()
        .rename(columns={"REGIAO": "Região"})
    )

    return stats.sort_values("Pontos Médio", ascending=False)


def calcular_ranking_regioes(
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    du_decorridos: int = 1,
) -> Dict[str, pd.DataFrame]:
    """Todos os rankings de regioes."""
    df_v = df[df["VALOR"] > 0].copy()
    if "REGIAO" not in df_v.columns:
        return {}

    base = (
        df_v.groupby("REGIAO")
        .agg(
            Qtd=("VALOR", "count"),
            Valor=("VALOR", "sum"),
            Pontos=("pontos", "sum"),
        )
        .reset_index()
        .rename(columns={"REGIAO": "Região"})
    )

    du = max(du_decorridos, 1)
    base["Ticket Médio"] = base.apply(
        lambda r: r["Valor"] / r["Qtd"] if r["Qtd"] > 0 else 0,
        axis=1,
    )
    base["Média DU"] = base["Valor"] / du

    # Atingimento meta: somar metas das lojas por regiao
    if (
        "LOJA" in df_metas.columns
        and "META_PRATA" in df_metas.columns
        and "REGIAO" in df.columns
    ):
        loja_reg = df[["LOJA", "REGIAO"]].drop_duplicates()
        metas_reg = (
            df_metas[["LOJA", "META_PRATA"]]
            .merge(loja_reg, on="LOJA", how="left")
            .groupby("REGIAO")["META_PRATA"]
            .sum()
        )
        base["Meta Prata"] = base["Região"].map(metas_reg).fillna(0)
    else:
        base["Meta Prata"] = 0

    base["Atingimento %"] = base.apply(
        lambda r: (
            r["Pontos"] / r["Meta Prata"] * 100
            if r["Meta Prata"] > 0
            else 0
        ),
        axis=1,
    )

    def _add_pos(r):
        r = r.copy()
        r.insert(0, "Posição", range(1, len(r) + 1))
        return r

    # Por Pontos
    rk_pontos = _add_pos(
        base[["Região", "Qtd", "Valor", "Pontos", "Ticket Médio"]]
        .sort_values("Pontos", ascending=False)
    )

    # Por Ticket Médio
    rk_ticket = _add_pos(
        base[["Região", "Qtd", "Valor", "Pontos", "Ticket Médio"]]
        .sort_values("Ticket Médio", ascending=False)
    )

    # Por Média DU
    rk_media = _add_pos(
        base[
            ["Região", "Qtd", "Valor", "Pontos",
             "Ticket Médio", "Média DU"]
        ]
        .sort_values("Média DU", ascending=False)
    )

    # Por Atingimento
    rk_ating = _add_pos(
        base[
            ["Região", "Qtd", "Valor", "Pontos",
             "Meta Prata", "Atingimento %", "Ticket Médio"]
        ]
        .sort_values("Atingimento %", ascending=False)
    )

    # Por Produto
    rk_produto = {}
    grupos = df_v[
        df_v["grupo_dashboard"].notna()
    ]["grupo_dashboard"].unique()
    for grupo in sorted(grupos):
        df_g = df_v[df_v["grupo_dashboard"] == grupo]
        if df_g.empty:
            continue
        rk = (
            df_g.groupby("REGIAO")
            .agg(
                Qtd=("VALOR", "count"),
                Valor=("VALOR", "sum"),
                Pontos=("pontos", "sum"),
            )
            .reset_index()
            .rename(columns={"REGIAO": "Região"})
        )
        rk["Ticket Médio"] = rk.apply(
            lambda r: r["Valor"] / r["Qtd"] if r["Qtd"] > 0 else 0,
            axis=1,
        )
        rk["Média DU"] = rk["Valor"] / du
        rk = rk.sort_values("Pontos", ascending=False)
        rk.insert(0, "Posição", range(1, len(rk) + 1))
        rk_produto[grupo] = rk

    return {
        "pontos": rk_pontos,
        "ticket": rk_ticket,
        "media_du": rk_media,
        "atingimento": rk_ating,
        "por_produto": rk_produto,
    }
