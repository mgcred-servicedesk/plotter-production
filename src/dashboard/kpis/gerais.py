"""
KPIs gerais do dashboard + helpers compartilhados entre
os modulos de KPI.

Este modulo hospeda ``excluir_supervisores`` e
``contar_consultores``, que sao reusados por
``produtos.py``, ``regioes.py``, ``rankings.py`` e
``evolucao.py``.
"""

from typing import Dict, Optional

import pandas as pd

from src.shared.dias_uteis import calcular_dias_uteis


def excluir_supervisores(
    df: pd.DataFrame,
    df_sup: Optional[pd.DataFrame],
) -> pd.DataFrame:
    """Remove supervisores do DataFrame de vendas."""
    if (
        df_sup is not None
        and "SUPERVISOR" in df_sup.columns
        and "CONSULTOR" in df.columns
    ):
        supervisores = df_sup["SUPERVISOR"].unique()
        return df[~df["CONSULTOR"].isin(supervisores)].copy()
    return df.copy()


def contar_consultores(
    df: pd.DataFrame,
    df_sup: Optional[pd.DataFrame],
) -> int:
    """Conta consultores excluindo supervisores."""
    if "CONSULTOR" not in df.columns:
        return 0
    consultores = df["CONSULTOR"].unique()
    if df_sup is not None and "SUPERVISOR" in df_sup.columns:
        supervisores = df_sup["SUPERVISOR"].unique()
        consultores = [c for c in consultores if c not in supervisores]
    return len(consultores)


def calcular_kpis_gerais(
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    ano: int,
    mes: int,
    dia_atual: Optional[int] = None,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> Dict:
    """Calcula KPIs gerais do dashboard."""
    du_total, du_dec, du_rest = calcular_dias_uteis(ano, mes, dia_atual)

    total_vendas = df["VALOR"].sum()
    total_pontos = df["pontos"].sum()
    total_transacoes = len(df[df["VALOR"] > 0])

    meta_prata = 0
    meta_ouro = 0
    if "META_PRATA" in df_metas.columns:
        meta_prata = (
            pd.to_numeric(df_metas["META_PRATA"], errors="coerce").fillna(0).sum()
        )
    if "META_OURO" in df_metas.columns:
        meta_ouro = (
            pd.to_numeric(df_metas["META_OURO"], errors="coerce").fillna(0).sum()
        )

    perc_prata = (total_pontos / meta_prata * 100) if meta_prata > 0 else 0
    perc_ouro = (total_pontos / meta_ouro * 100) if meta_ouro > 0 else 0

    media_du = total_vendas / du_dec if du_dec > 0 else 0
    media_du_pts = total_pontos / du_dec if du_dec > 0 else 0
    meta_diaria = meta_prata / du_total if du_total > 0 else 0
    gap_pontos = max(0, meta_prata - total_pontos)
    meta_diaria_restante = gap_pontos / du_rest if du_rest > 0 else 0
    projecao = media_du * du_total
    projecao_pts = media_du_pts * du_total
    perc_proj = (projecao_pts / meta_prata * 100) if meta_prata > 0 else 0
    ticket_medio = total_vendas / total_transacoes if total_transacoes > 0 else 0

    num_consultores = 0
    if "CONSULTOR" in df.columns:
        consultores_unicos = df["CONSULTOR"].unique()
        if df_supervisores is not None and "SUPERVISOR" in df_supervisores.columns:
            supervisores = df_supervisores["SUPERVISOR"].unique()
            consultores_unicos = [
                c for c in consultores_unicos if c not in supervisores
            ]
        num_consultores = len(consultores_unicos)

    qtd_super_conta = (
        int(df["is_super_conta"].sum())
        if "is_super_conta" in df.columns
        else 0
    )
    qtd_emissao_cartao = (
        int(df["is_emissao_cartao"].sum())
        if "is_emissao_cartao" in df.columns
        else 0
    )
    qtd_bmg_med = (
        int(df["is_bmg_med"].sum())
        if "is_bmg_med" in df.columns
        else 0
    )
    qtd_seguro_vida = (
        int(df["is_seguro_vida"].sum())
        if "is_seguro_vida" in df.columns
        else 0
    )

    return {
        "total_vendas": total_vendas,
        "total_pontos": total_pontos,
        "total_transacoes": total_transacoes,
        "meta_prata": meta_prata,
        "meta_ouro": meta_ouro,
        "meta_diaria": meta_diaria,
        "meta_diaria_restante": meta_diaria_restante,
        "perc_ating_prata": perc_prata,
        "perc_ating_ouro": perc_ouro,
        "media_du": media_du,
        "media_du_pontos": media_du_pts,
        "projecao": projecao,
        "projecao_pontos": projecao_pts,
        "perc_proj": perc_proj,
        "ticket_medio": ticket_medio,
        "du_total": du_total,
        "du_decorridos": du_dec,
        "du_restantes": du_rest,
        "num_lojas": (df["LOJA"].nunique() if "LOJA" in df.columns else 0),
        "num_consultores": num_consultores,
        "num_regioes": (df["REGIAO"].nunique() if "REGIAO" in df.columns else 0),
        "qtd_super_conta": qtd_super_conta,
        "qtd_emissao_cartao": qtd_emissao_cartao,
        "qtd_bmg_med": qtd_bmg_med,
        "qtd_seguro_vida": qtd_seguro_vida,
    }
