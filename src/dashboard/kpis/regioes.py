"""
KPIs e rankings por regiao: visao por regiao, heatmap
regiao x produto, media de producao por regiao e
conjunto de rankings regionais.
"""

from typing import Dict, Optional, Set, Tuple

import pandas as pd

from src.dashboard.kpis.gerais import (
    contar_consultores,
)
from src.shared.dias_uteis import calcular_dias_uteis


def _metas_da_regiao(
    df_metas: pd.DataFrame,
    regiao: str,
    lojas_regiao,
) -> pd.DataFrame:
    """Recorta as metas pertencentes a uma regiao.

    Usa a coluna ``REGIAO`` das proprias metas (desacoplado da
    presenca de contratos): uma loja com meta mas sem contrato no
    periodo conta na regiao, mantendo o total regional consistente
    com o total global. Cai para o proxy por lojas-com-contrato
    apenas quando o DataFrame de metas nao traz ``REGIAO``.
    """
    if df_metas.empty:
        return df_metas
    if "REGIAO" in df_metas.columns:
        return df_metas[df_metas["REGIAO"] == regiao]
    if "LOJA" in df_metas.columns:
        return df_metas[df_metas["LOJA"].isin(lojas_regiao)]
    return df_metas


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
            meta_prata = (
                _metas_da_regiao(df_metas, regiao, lojas_r)["META_PRATA"]
                .sum()
            )

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

    # Calcular % atingimento e volume bruto por regiao x produto
    dados_ating = []
    dados_valor = []
    for regiao in regioes:
        df_r = df[df["REGIAO"] == regiao]
        lojas_r = df_r["LOJA"].unique()
        metas_prod_r = _metas_da_regiao(df_metas_produto, regiao, lojas_r)
        row_ating = {"Região": regiao}
        row_valor = {"Região": regiao}

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
                        metas_prod_r[meta_key],
                        errors="coerce",
                    )
                    .fillna(0)
                    .sum()
                )

            perc = (valor / meta * 100) if meta > 0 else 0
            row_ating[grupo] = perc
            row_valor[grupo] = valor

        dados_ating.append(row_ating)
        dados_valor.append(row_valor)

    df_ating = pd.DataFrame(dados_ating).set_index("Região")
    df_valor = pd.DataFrame(dados_valor).set_index("Região")

    # Ranking por % atingimento; produtos com meta zerada para todas
    # as regioes usam volume de producao como criterio de desempate
    # (maior volume = melhor posicao).
    df_ranking = df_ating.rank(ascending=False, method="min").astype(int)
    for col in df_ating.columns:
        if df_ating[col].sum() == 0:
            df_ranking[col] = (
                df_valor[col]
                .rank(ascending=False, method="min")
                .astype(int)
            )

    return df_ranking, df_ating


def calcular_kpis_por_produto_regiao(
    df: pd.DataFrame,
    df_metas_produto: pd.DataFrame,
    categorias: pd.DataFrame,
    ano: int,
    mes: int,
    dia_atual: Optional[int] = None,
) -> Dict[str, pd.DataFrame]:
    """KPIs por produto para cada regiao.

    Retorna dict {grupo_dashboard → DataFrame} com colunas:
    Pos., Região, Qtd, Valor, Meta, % Atingimento, Ticket Médio,
    Projeção, % Projeção. Apenas grupos com conta_valor=True.
    Ordenado por % Atingimento; quando meta zerada para todas as
    regiões, ordena por Valor (maior = 1º).
    """
    if "REGIAO" not in df.columns or "grupo_dashboard" not in df.columns:
        return {}

    du_total, du_dec, _ = calcular_dias_uteis(ano, mes, dia_atual)

    grupo_meta_map = (
        categorias[categorias["grupo_dashboard"].notna()]
        .groupby("grupo_dashboard")["grupo_meta"]
        .first()
        .to_dict()
    )

    grupos = sorted(
        categorias[
            categorias["grupo_dashboard"].notna()
            & categorias["conta_valor"].fillna(False).astype(bool)
        ]["grupo_dashboard"]
        .unique()
        .tolist()
    )

    regioes = sorted(df["REGIAO"].unique())
    resultado: Dict[str, pd.DataFrame] = {}

    for grupo in grupos:
        df_g = df[df["grupo_dashboard"] == grupo]
        rows = []

        for regiao in regioes:
            df_r = df_g[df_g["REGIAO"] == regiao]
            lojas_r = df[df["REGIAO"] == regiao]["LOJA"].unique()
            metas_prod_r = _metas_da_regiao(
                df_metas_produto, regiao, lojas_r
            )

            valor = df_r["VALOR"].sum()
            qtd = int((df_r["VALOR"] > 0).sum())
            ticket_medio = valor / qtd if qtd > 0 else 0.0

            meta_key = grupo_meta_map.get(grupo, grupo)
            meta = 0.0
            if (
                not df_metas_produto.empty
                and meta_key in df_metas_produto.columns
            ):
                meta = (
                    pd.to_numeric(
                        metas_prod_r[meta_key],
                        errors="coerce",
                    )
                    .fillna(0)
                    .sum()
                )

            perc = (valor / meta * 100) if meta > 0 else 0.0
            projecao = (valor / du_dec * du_total) if du_dec > 0 else 0.0
            perc_proj = (projecao / meta * 100) if meta > 0 else 0.0

            rows.append(
                {
                    "Região": regiao,
                    "Qtd": qtd,
                    "Valor": valor,
                    "Meta": meta,
                    "% Atingimento": perc,
                    "Ticket Médio": ticket_medio,
                    "Projeção": projecao,
                    "% Projeção": perc_proj,
                }
            )

        if not rows:
            continue

        df_rk = pd.DataFrame(rows)
        sort_col = "% Atingimento" if df_rk["Meta"].sum() > 0 else "Valor"
        df_rk = df_rk.sort_values(sort_col, ascending=False).reset_index(
            drop=True
        )
        df_rk.insert(0, "Pos.", range(1, len(df_rk) + 1))
        resultado[grupo] = df_rk

    return resultado


def calcular_evolucao_media_du(
    df_atual: pd.DataFrame,
    du_dec_atual: int,
    df_ant: Optional[pd.DataFrame],
    du_dec_ant: int,
    regioes_excluir: Optional[Set[str]] = None,
) -> pd.DataFrame:
    """Evolução da Média DU por região entre mês anterior e atual.

    Retorna DataFrame com: Região, Mês Anterior, Mês Atual,
    % Evolução, incluindo linha de TOTAL.
    """
    if "REGIAO" not in df_atual.columns:
        return pd.DataFrame()

    excluir = {r.upper() for r in (regioes_excluir or set())}

    def _serie(df: pd.DataFrame, du: int) -> pd.Series:
        if df is None or df.empty or "REGIAO" not in df.columns:
            return pd.Series(dtype=float)
        du_safe = max(du, 1)
        return (
            df[df["VALOR"] > 0]
            .groupby("REGIAO")["VALOR"]
            .sum()
            / du_safe
        )

    serie_atual = _serie(df_atual, du_dec_atual)
    serie_ant = _serie(df_ant, du_dec_ant)

    regioes = sorted(
        r for r in df_atual["REGIAO"].dropna().unique()
        if r.upper() not in excluir
    )

    rows = []
    for reg in regioes:
        atual = float(serie_atual.get(reg, 0))
        ant = float(
            serie_ant.get(reg, 0) if not serie_ant.empty else 0
        )
        perc = ((atual - ant) / ant * 100) if ant > 0 else 0
        rows.append({
            "Região": reg,
            "Mês Anterior": ant,
            "Mês Atual": atual,
            "% Evolução": perc,
        })

    if rows:
        tot_ant = sum(r["Mês Anterior"] for r in rows)
        tot_atual = sum(r["Mês Atual"] for r in rows)
        tot_perc = (
            (tot_atual - tot_ant) / tot_ant * 100
            if tot_ant > 0
            else 0
        )
        rows.append({
            "Região": "TOTAL",
            "Mês Anterior": tot_ant,
            "Mês Atual": tot_atual,
            "% Evolução": tot_perc,
        })

    return pd.DataFrame(rows)
