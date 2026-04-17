"""
KPIs gerais do dashboard + helpers compartilhados entre
os modulos de KPI.

Este modulo hospeda ``excluir_supervisores`` e
``contar_consultores``, que sao reusados por
``produtos.py``, ``regioes.py``, ``rankings.py`` e
``evolucao.py``.
"""

from typing import Dict, List, Optional

import pandas as pd

from src.shared.dias_uteis import calcular_dias_uteis


# Mapeamento de produtos do dashboard para categoria_codigo
# Baseado em MAPEAMENTO_PRODUTOS de settings.py
PRODUTOS_DASHBOARD = {
    "CNC": ["CNC", "SUPER_CONTA"],  # CNC inclui Super Conta
    "CLT": ["CONSIG_PRIV"],  # CLT = CONSIG PRIVADO
    "SAQUE": ["SAQUE", "SAQUE_BENEFICIO"],
    "CONSIGNADO": ["CONSIG_BMG", "CONSIG_ITAU", "CONSIG_C6"],
    "FGTS_ANT_BEN_CNC13": ["FGTS", "ANT_BENEF", "CNC_13"],
}


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
    df_metas_produto: pd.DataFrame,
    ano: int,
    mes: int,
    dia_atual: Optional[int] = None,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> Dict:
    """Calcula KPIs gerais do dashboard."""
    du_total, du_dec, du_rest = calcular_dias_uteis(ano, mes, dia_atual)

    total_vendas = df["VALOR"].sum()
    total_pontos = df["pontos"].sum()
    total_transacoes = len(
        df[df["VALOR"] > 0]
    )

    meta_prata = 0
    meta_ouro = 0
    if "META_PRATA" in df_metas.columns:
        meta_prata = (
            pd.to_numeric(
                df_metas["META_PRATA"], errors="coerce"
            ).fillna(0).sum()
        )
    if "META_OURO" in df_metas.columns:
        meta_ouro = (
            pd.to_numeric(
                df_metas["META_OURO"], errors="coerce"
            ).fillna(0).sum()
        )

    perc_prata = (
        (total_pontos / meta_prata * 100)
        if meta_prata > 0 else 0
    )
    perc_ouro = (
        (total_pontos / meta_ouro * 100)
        if meta_ouro > 0 else 0
    )

    media_du = total_vendas / du_dec if du_dec > 0 else 0
    media_du_pts = total_pontos / du_dec if du_dec > 0 else 0
    meta_diaria_pts = meta_prata / du_total if du_total > 0 else 0
    gap_pontos = max(0, meta_prata - total_pontos)
    meta_diaria_restante_pts = gap_pontos / du_rest if du_rest > 0 else 0
    projecao = media_du * du_total
    projecao_pts = media_du_pts * du_total
    perc_proj = (projecao_pts / meta_prata * 100) if meta_prata > 0 else 0
    ticket_medio = total_vendas / total_transacoes if total_transacoes > 0 else 0

    num_consultores = 0
    if "CONSULTOR" in df.columns:
        consultores_unicos = df["CONSULTOR"].unique()
        if df_supervisores is not None and \
                "SUPERVISOR" in df_supervisores.columns:
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
        "meta_diaria_pts": meta_diaria_pts,
        "meta_diaria_restante_pts": meta_diaria_restante_pts,
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


def calcular_kpis_analise(
    df_analise: pd.DataFrame,
    df: pd.DataFrame,
    du_decorridos: int,
) -> Dict:
    """Calcula KPIs relacionados a contratos em analise."""
    if df_analise.empty:
        return {
            "valor_analise": 0,
            "qtd_analise": 0,
            "ticket_medio_analise": 0,
            "media_diaria_analise": 0,
            "variacao_analise": 0,
        }

    valor_analise = df_analise["VALOR"].sum()
    qtd_analise = len(df_analise)
    ticket_medio_analise = (
        valor_analise / qtd_analise if qtd_analise > 0 else 0
    )

    # Media diaria de contratos em analise
    media_diaria_analise = (
        valor_analise / du_decorridos if du_decorridos > 0 else 0
    )

    # Valor total digitado no mes (pagos + em analise base)
    valor_total_digitado = df["VALOR"].sum() + valor_analise

    # Variacao = % do valor em analise vs media do total digitado
    media_diaria_total = (
        valor_total_digitado / du_decorridos
        if du_decorridos > 0
        else 0
    )
    variacao_analise = (
        (media_diaria_analise / media_diaria_total * 100)
        if media_diaria_total > 0
        else 0
    )

    return {
        "valor_analise": valor_analise,
        "qtd_analise": qtd_analise,
        "ticket_medio_analise": ticket_medio_analise,
        "media_diaria_analise": media_diaria_analise,
        "variacao_analise": variacao_analise,
    }


def calcular_kpis_cancelados(
    df_cancelados: pd.DataFrame,
    df: pd.DataFrame,
    df_analise: pd.DataFrame,
) -> Dict:
    """Calcula KPIs relacionados a contratos cancelados."""
    if df_cancelados.empty:
        return {
            "valor_cancelados": 0,
            "qtd_cancelados": 0,
            "indice_perda": 0,
        }

    valor_cancelados = df_cancelados["VALOR"].sum()
    qtd_cancelados = len(df_cancelados)

    # Indice de perda (churn) = Cancelados / (Pagos + Cancelados + Em Analise)
    qtd_pagos = len(df)
    qtd_analise = len(df_analise) if not df_analise.empty else 0
    total_propostas = qtd_pagos + qtd_cancelados + qtd_analise

    indice_perda = (
        (qtd_cancelados / total_propostas * 100)
        if total_propostas > 0
        else 0
    )

    return {
        "valor_cancelados": valor_cancelados,
        "qtd_cancelados": qtd_cancelados,
        "indice_perda": indice_perda,
    }


def calcular_medias_du_por_nivel(
    df: pd.DataFrame,
    du_decorridos: int,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> Dict:
    """Calcula medias DU por loja e por consultor (excluindo supervisores)."""
    df_sem_sup = excluir_supervisores(df, df_supervisores)

    # Media DU por loja
    num_lojas = 0
    if "LOJA" in df_sem_sup.columns and not df_sem_sup.empty:
        vendas_por_loja = df_sem_sup.groupby("LOJA")["VALOR"].sum()
        num_lojas = len(vendas_por_loja)
        media_du_loja = (
            vendas_por_loja.mean() / du_decorridos
            if du_decorridos > 0
            else 0
        )
    else:
        media_du_loja = 0

    # Media DU por consultor
    num_consultores = 0
    if "CONSULTOR" in df_sem_sup.columns and not df_sem_sup.empty:
        vendas_por_consultor = df_sem_sup.groupby("CONSULTOR")["VALOR"].sum()
        num_consultores = len(vendas_por_consultor)
        media_du_consultor = (
            vendas_por_consultor.mean() / du_decorridos
            if du_decorridos > 0 and num_consultores > 0
            else 0
        )
    else:
        media_du_consultor = 0

    return {
        "media_du_loja": media_du_loja,
        "media_du_consultor": media_du_consultor,
        "num_lojas": num_lojas,
        "num_consultores": num_consultores,
    }


def calcular_metas_produto_diarias(
    df: pd.DataFrame,
    df_metas_produto: pd.DataFrame,
    du_total: int,
    du_decorridos: int,
) -> List[Dict]:
    """Calcula metas diarias por produto para o dashboard."""
    resultados = []

    for produto_display, categorias in PRODUTOS_DASHBOARD.items():
        # Calcular valor atual do produto
        mask_produto = df["categoria_codigo"].isin(categorias)
        valor_atual = df.loc[mask_produto, "VALOR"].sum()

        # Calcular meta total do produto (soma das metas das lojas presentes no df)
        meta_total = 0
        if not df_metas_produto.empty and "LOJA" in df.columns:
            lojas_ativas = df["LOJA"].unique()
            colunas_meta = [c for c in df_metas_produto.columns if c != "LOJA"]

            for col in colunas_meta:
                if col.upper() in [c.upper() for c in categorias] or \
                   any(cat in col.upper() for cat in categorias):
                    meta_total += df_metas_produto.loc[
                        df_metas_produto["LOJA"].isin(lojas_ativas), col
                    ].sum()

        # Se nao encontrou meta especifica, tentar pelo nome do produto
        if meta_total == 0 and not df_metas_produto.empty:
            for col in df_metas_produto.columns:
                if col == "LOJA":
                    continue
                if produto_display.upper() in col.upper():
                    lojas_ativas = df["LOJA"].unique()
                    meta_total += df_metas_produto.loc[
                        df_metas_produto["LOJA"].isin(lojas_ativas), col
                    ].sum()

        # Calcular ritmo e metas diarias
        ritmo_diario = (
            valor_atual / du_decorridos if du_decorridos > 0 else 0
        )
        meta_diaria = meta_total / du_total if du_total > 0 else 0
        gap = max(0, meta_total - valor_atual)
        dias_restantes = du_total - du_decorridos
        meta_diaria_restante = (
            gap / dias_restantes if dias_restantes > 0 else 0
        )

        perc_atingido = (valor_atual / meta_total * 100) if meta_total > 0 else 0

        resultados.append({
            "produto": produto_display,
            "valor_atual": valor_atual,
            "meta_total": meta_total,
            "ritmo_diario": ritmo_diario,
            "meta_diaria": meta_diaria,
            "meta_diaria_restante": meta_diaria_restante,
            "perc_atingido": perc_atingido,
            "du_total": du_total,
            "du_decorridos": du_decorridos,
        })

    return resultados
