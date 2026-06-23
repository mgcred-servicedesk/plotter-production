"""
Rankings de lojas e consultores — atingimento, ticket
medio, pontos, media por DU, rankings por produto e aceleradores.
"""

from typing import Dict, Optional

import pandas as pd

from src.config.settings import PRODUTOS_EMISSAO
from src.dashboard.kpis.gerais import excluir_supervisores


# ── Helpers compartilhados ───────────────────────────

def _preparar(
    df: pd.DataFrame,
    tipo: str,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Filtra VALOR > 0; exclui supervisores no escopo consultor."""
    df_v = df[df["VALOR"] > 0].copy()
    if tipo == "consultor":
        df_v = excluir_supervisores(df_v, df_supervisores)
    return df_v


def _agrupar(df_v: pd.DataFrame, tipo: str) -> pd.DataFrame:
    """Agrega Qtd/Valor/Pontos por loja/consultor.

    No escopo consultor inclui a coluna ``Loja`` (primeira ocorrencia).
    """
    coluna = "LOJA" if tipo == "loja" else "CONSULTOR"
    label = "Loja" if tipo == "loja" else "Consultor"
    agg_dict = {
        "Qtd": ("VALOR", "count"),
        "Valor": ("VALOR", "sum"),
        "Pontos": ("pontos", "sum"),
    }
    if tipo == "consultor":
        agg_dict["Loja"] = ("LOJA", "first")
    return (
        df_v.groupby(coluna)
        .agg(**agg_dict)
        .reset_index()
        .rename(columns={coluna: label})
    )


def _anexar_regiao(rk: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    """Anexa REGIAO ao ranking pela chave 'Loja' (origem: contratos)."""
    df_reg = df[["LOJA", "REGIAO"]].drop_duplicates()
    return rk.merge(
        df_reg, left_on="Loja", right_on="LOJA", how="left",
    ).drop("LOJA", axis=1)


def _ticket(rk: pd.DataFrame) -> pd.Series:
    """Ticket medio vetorizado: Valor / Qtd (0 quando Qtd == 0)."""
    return (rk["Valor"] / rk["Qtd"].where(rk["Qtd"] > 0)).fillna(0)


def _atingimento(pontos: pd.Series, meta: pd.Series) -> pd.Series:
    """% atingimento vetorizado: pontos / meta * 100 (0 quando meta <= 0)."""
    return (pontos / meta.where(meta > 0) * 100).fillna(0)


def _rankear(rk: pd.DataFrame, sort_col: str, top_n: int) -> pd.DataFrame:
    """Ordena desc por sort_col, corta top_n e insere 'Posição' (1..n)."""
    rk = rk.sort_values(sort_col, ascending=False).head(top_n)
    rk.insert(0, "Posição", range(1, len(rk) + 1))
    return rk


# ── Rankings ─────────────────────────────────────────

def calcular_ranking_lojas(
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    top_n: int = 10,
) -> pd.DataFrame:
    """Ranking de lojas por atingimento de meta prata."""
    df_v = _preparar(df, "loja")
    if "LOJA" not in df_v.columns:
        return pd.DataFrame()

    ranking = _agrupar(df_v, "loja")

    if "REGIAO" in df.columns:
        ranking = _anexar_regiao(ranking, df)

    if "LOJA" in df_metas.columns and "META_PRATA" in df_metas.columns:
        ranking = ranking.merge(
            df_metas[["LOJA", "META_PRATA"]],
            left_on="Loja",
            right_on="LOJA",
            how="left",
        )
        ranking["Meta Prata"] = ranking["META_PRATA"].fillna(0)
        ranking = ranking.drop(["LOJA", "META_PRATA"], axis=1)
    else:
        ranking["Meta Prata"] = 0

    ranking["Atingimento %"] = _atingimento(
        ranking["Pontos"], ranking["Meta Prata"]
    )
    ranking["Ticket Médio"] = _ticket(ranking)

    ranking = _rankear(ranking, "Atingimento %", top_n)
    return ranking.drop(columns=["Qtd", "Meta Prata"], errors="ignore")


def calcular_ranking_consultores(
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    top_n: int = 10,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Ranking de consultores por atingimento."""
    df_v = _preparar(df, "consultor", df_supervisores)
    if "CONSULTOR" not in df_v.columns:
        return pd.DataFrame()

    ranking = _agrupar(df_v, "consultor")

    if "LOJA" in df_metas.columns and "META_PRATA" in df_metas.columns:
        metas_loja = df_metas.set_index("LOJA")["META_PRATA"]
        num_cons_loja = df_v.groupby("LOJA")["CONSULTOR"].nunique()

        ranking["Meta Prata"] = ranking["Loja"].map(
            lambda x: (
                metas_loja.get(x, 0) / num_cons_loja.get(x, 1)
                if x in num_cons_loja.index
                else 0
            )
        )
    else:
        ranking["Meta Prata"] = 0

    ranking["Atingimento %"] = _atingimento(
        ranking["Pontos"], ranking["Meta Prata"]
    )
    ranking["Ticket Médio"] = _ticket(ranking)

    ranking = _rankear(ranking, "Atingimento %", top_n)
    return ranking.drop(columns=["Qtd", "Meta Prata"], errors="ignore")


def calcular_ranking_ticket_medio(
    df: pd.DataFrame,
    tipo: str = "loja",
    top_n: int = 10,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Ranking por ticket medio (lojas ou consultores)."""
    df_v = _preparar(df, tipo, df_supervisores)
    coluna = "LOJA" if tipo == "loja" else "CONSULTOR"
    if coluna not in df_v.columns:
        return pd.DataFrame()

    ranking = _agrupar(df_v, tipo)
    if "REGIAO" in df.columns and tipo == "loja":
        ranking = _anexar_regiao(ranking, df)

    ranking["Ticket Médio"] = _ticket(ranking)
    return _rankear(ranking, "Ticket Médio", top_n)


def calcular_ranking_por_produto(
    df: pd.DataFrame,
    tipo: str = "loja",
    top_n: int = 10,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> Dict[str, pd.DataFrame]:
    """Rankings por grupo_dashboard (lojas ou consultores)."""
    df_v = _preparar(df, tipo, df_supervisores)
    grupos = df_v[df_v["grupo_dashboard"].notna()]["grupo_dashboard"].unique()

    rankings = {}
    for grupo in sorted(grupos):
        df_g = df_v[df_v["grupo_dashboard"] == grupo]
        if df_g.empty:
            rankings[grupo] = pd.DataFrame()
            continue

        ranking = _agrupar(df_g, tipo)
        ranking["Ticket Médio"] = _ticket(ranking)
        rankings[grupo] = _rankear(ranking, "Pontos", top_n)

    return rankings


def calcular_ranking_pontos(
    df: pd.DataFrame,
    tipo: str = "loja",
    top_n: int = 10,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Ranking por pontos (lojas ou consultores)."""
    df_v = _preparar(df, tipo, df_supervisores)
    coluna = "LOJA" if tipo == "loja" else "CONSULTOR"
    if coluna not in df_v.columns:
        return pd.DataFrame()

    ranking = _agrupar(df_v, tipo)
    if "REGIAO" in df.columns and tipo == "loja":
        ranking = _anexar_regiao(ranking, df)

    ranking["Ticket Médio"] = _ticket(ranking)
    ranking = _rankear(ranking, "Pontos", top_n)
    return ranking.drop(columns=["Qtd"], errors="ignore")


def calcular_ranking_media_du(
    df: pd.DataFrame,
    tipo: str = "loja",
    top_n: int = 10,
    du_decorridos: int = 1,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Ranking por media DU (lojas ou consultores)."""
    df_v = _preparar(df, tipo, df_supervisores)
    coluna = "LOJA" if tipo == "loja" else "CONSULTOR"
    if coluna not in df_v.columns:
        return pd.DataFrame()

    ranking = _agrupar(df_v, tipo)
    if "REGIAO" in df.columns and tipo == "loja":
        ranking = _anexar_regiao(ranking, df)

    du = max(du_decorridos, 1)
    ranking["Média DU"] = ranking["Valor"] / du
    ranking["Ticket Médio"] = _ticket(ranking)
    return _rankear(ranking, "Média DU", top_n)


def calcular_ranking_por_acelerador(
    df: pd.DataFrame,
    tipo: str = "loja",
    top_n: int = 10,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> Dict[str, pd.DataFrame]:
    """Rankings por acelerador (BMG Med, Vida Familiar, Emissao, Super Conta).

    Ordena por quantidade de contratos — aceleradores nao tem valor monetario
    significativo para ranking.
    """
    df_base = (
        excluir_supervisores(df, df_supervisores)
        if tipo == "consultor"
        else df.copy()
    )

    coluna = "LOJA" if tipo == "loja" else "CONSULTOR"
    label = "Loja" if tipo == "loja" else "Consultor"

    if coluna not in df_base.columns:
        return {}

    def _flag(col: str) -> pd.Series:
        return (
            df_base.get(col, pd.Series(False, index=df_base.index))
            .fillna(False)
            .astype(bool)
        )

    aceleradores = {
        "BMG Med": _flag("is_bmg_med"),
        "Vida Familiar": _flag("is_seguro_vida"),
        "Emissao": (
            df_base["TIPO_PRODUTO"].str.upper().isin(
                {p.upper() for p in PRODUTOS_EMISSAO}
            )
            if "TIPO_PRODUTO" in df_base.columns
            else pd.Series(False, index=df_base.index)
        ),
        "Super Conta": (
            df_base["SUBTIPO"].str.strip().str.upper() == "SUPER CONTA"
            if "SUBTIPO" in df_base.columns
            else pd.Series(False, index=df_base.index)
        ),
    }

    rankings: Dict[str, pd.DataFrame] = {}
    for nome, mask in aceleradores.items():
        df_acel = df_base[mask]
        if df_acel.empty:
            continue

        rk = (
            df_acel.groupby(coluna)
            .size()
            .reset_index(name="Qtd")
            .rename(columns={coluna: label})
        )

        if tipo == "consultor" and "LOJA" in df_acel.columns:
            loja_map = df_acel.groupby(coluna)["LOJA"].first()
            rk["Loja"] = rk[label].map(loja_map)

        if tipo == "loja" and "REGIAO" in df_base.columns:
            rk = _anexar_regiao(rk, df_base)

        rk = _rankear(rk, "Qtd", top_n)
        rankings[nome] = rk

    return rankings
