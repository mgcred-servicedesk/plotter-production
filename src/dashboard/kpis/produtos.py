"""
KPIs e distribuicoes por grupo de produto.
"""

from typing import Optional

import pandas as pd

from src.dashboard.kpis.gerais import (
    contar_consultores,
    excluir_supervisores,
)
from src.shared.dias_uteis import calcular_dias_uteis


def calcular_kpis_por_produto(
    df: pd.DataFrame,
    df_metas_produto: pd.DataFrame,
    categorias: pd.DataFrame,
    ano: int,
    mes: int,
    dia_atual: Optional[int] = None,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Calcula KPIs por grupo de produto do dashboard."""
    du_total, du_dec, du_rest = calcular_dias_uteis(ano, mes, dia_atual)

    num_consultores = contar_consultores(df, df_supervisores)

    # Grupos do dashboard vindos do banco
    grupos = (
        categorias[categorias["grupo_dashboard"].notna()]["grupo_dashboard"]
        .unique()
        .tolist()
    )

    # Mapeamento grupo_dashboard → grupo_meta
    grupo_meta_map = (
        categorias[categorias["grupo_dashboard"].notna()]
        .groupby("grupo_dashboard")["grupo_meta"]
        .first()
        .to_dict()
    )

    dados = []
    for grupo in sorted(grupos):
        df_grupo = df[df["grupo_dashboard"] == grupo].copy()

        valor = df_grupo["VALOR"].sum()
        quantidade = len(df_grupo[df_grupo["VALOR"] > 0])

        # Buscar meta por grupo_meta
        meta_key = grupo_meta_map.get(grupo, grupo)
        meta_total = 0
        if not df_metas_produto.empty and meta_key in df_metas_produto.columns:
            meta_total = (
                pd.to_numeric(
                    df_metas_produto[meta_key],
                    errors="coerce",
                )
                .fillna(0)
                .sum()
            )

        perc_ating = (valor / meta_total * 100) if meta_total > 0 else 0
        media_du = valor / du_dec if du_dec > 0 else 0
        meta_diaria = meta_total / du_total if du_total > 0 else 0
        gap = max(0, meta_total - valor)
        meta_diaria_rest = gap / du_rest if du_rest > 0 else 0
        ticket = valor / quantidade if quantidade > 0 else 0
        projecao = media_du * du_total
        perc_proj = (projecao / meta_total * 100) if meta_total > 0 else 0
        valor_medio_cons = valor / num_consultores if num_consultores > 0 else 0

        dados.append(
            {
                "Produto": grupo,
                "Valor": valor,
                "Meta": meta_total,
                "Meta Diária": meta_diaria,
                "Meta Diária Restante": meta_diaria_rest,
                "% Atingimento": perc_ating,
                "Quantidade": quantidade,
                "Ticket Médio": ticket,
                "Valor Médio/Consultor": valor_medio_cons,
                "Média DU": media_du,
                "Projeção": projecao,
                "% Projeção": perc_proj,
            }
        )

    return pd.DataFrame(dados)


def calcular_distribuicao_produtos(
    df: pd.DataFrame,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Distribuicao de produtos por consultor."""
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

    grupos = sorted(
        df_v[df_v["PRODUTO_MIX"] != "OUTROS"]["PRODUTO_MIX"].unique().tolist()
    )

    distrib = df_v.pivot_table(
        index="CONSULTOR",
        columns="PRODUTO_MIX",
        values="pontos",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()

    cols_existentes = [g for g in grupos if g in distrib.columns]
    distrib["TOTAL"] = distrib[cols_existentes].sum(axis=1)

    if "LOJA" in df.columns:
        df_info = df[["CONSULTOR", "LOJA"]].drop_duplicates()
        distrib = distrib.merge(df_info, on="CONSULTOR", how="left")

    if "REGIAO" in df.columns:
        df_reg = df[["LOJA", "REGIAO"]].drop_duplicates()
        distrib = distrib.merge(df_reg, on="LOJA", how="left")

    return distrib.sort_values("TOTAL", ascending=False)
