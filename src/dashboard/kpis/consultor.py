"""
Calculos de KPIs, breakdown e rankings para a visao
individual do consultor.

Todas as funcoes sao puras (apenas pandas / numpy).
A carga de dados e o render ficam em outros modulos.
"""

from typing import Optional

import pandas as pd

from src.shared.dias_uteis import calcular_dias_uteis


# ══════════════════════════════════════════════════════
# KPIs principais
# ══════════════════════════════════════════════════════


def calcular_kpis_consultor(
    df_meu: pd.DataFrame,
    df_analise_meu: pd.DataFrame,
    df_cancelados_meu: pd.DataFrame,
    meta_prata: float,
    meta_ouro: float,
    ano: int,
    mes: int,
    dia_atual: Optional[int] = None,
) -> dict:
    """
    Calcula os 4 KPIs principais e derivados do consultor.

    Args:
        df_meu: Contratos pagos do consultor.
        df_analise_meu: Propostas em analise do consultor.
        df_cancelados_meu: Contratos cancelados do consultor.
        meta_prata: Meta Prata individual (pontos).
        meta_ouro: Meta Ouro individual (pontos).
        ano: Ano de referencia.
        mes: Mes de referencia (1-12).
        dia_atual: Dia atual (para DU decorridos). None = fim.

    Returns:
        Dict com os KPIs. Chaves relevantes:
            pagos_qtd, pagos_valor,
            analise_qtd, analise_valor,
            cancelados_qtd, cancelados_pct,
            pontos_total,
            meta_prata, meta_ouro,
            perc_ating_prata, perc_ating_ouro,
            projecao_pontos, perc_proj,
            media_du_valor, media_du_pontos,
            meta_diaria_restante,
            du_total, du_decorridos, du_restantes.
    """
    du_total, du_dec, du_rest = calcular_dias_uteis(
        ano, mes, dia_atual,
    )

    # ── Pagos ────────────────────────────────
    if df_meu.empty:
        pagos_valor = 0.0
        pagos_qtd = 0
        pontos_total = 0.0
    else:
        pagos_valor = float(df_meu["VALOR"].sum())
        pagos_qtd = int((df_meu["VALOR"] > 0).sum())
        pontos_total = (
            float(df_meu["pontos"].sum())
            if "pontos" in df_meu.columns
            else 0.0
        )

    # ── Em analise ───────────────────────────
    if df_analise_meu.empty:
        analise_qtd = 0
        analise_valor = 0.0
    else:
        analise_qtd = len(df_analise_meu)
        analise_valor = (
            float(df_analise_meu["VALOR"].sum())
            if "VALOR" in df_analise_meu.columns
            else 0.0
        )

    # ── Cancelados ───────────────────────────
    if df_cancelados_meu.empty:
        cancelados_qtd = 0
    else:
        cancelados_qtd = len(df_cancelados_meu)
    total_contratos = pagos_qtd + cancelados_qtd
    cancelados_pct = (
        cancelados_qtd / total_contratos * 100
        if total_contratos > 0
        else 0.0
    )

    # ── Percentuais e projecoes ──────────────
    perc_ating_prata = (
        pontos_total / meta_prata * 100
        if meta_prata > 0
        else 0.0
    )
    perc_ating_ouro = (
        pontos_total / meta_ouro * 100
        if meta_ouro > 0
        else 0.0
    )

    media_du_valor = pagos_valor / du_dec if du_dec > 0 else 0.0
    media_du_pontos = pontos_total / du_dec if du_dec > 0 else 0.0
    projecao_pontos = media_du_pontos * du_total
    projecao_valor = media_du_valor * du_total
    perc_proj = (
        projecao_pontos / meta_prata * 100
        if meta_prata > 0
        else 0.0
    )

    gap_pontos = max(0.0, meta_prata - pontos_total)
    meta_diaria_restante = (
        gap_pontos / du_rest if du_rest > 0 else 0.0
    )

    return {
        "pagos_qtd": pagos_qtd,
        "pagos_valor": pagos_valor,
        "analise_qtd": analise_qtd,
        "analise_valor": analise_valor,
        "cancelados_qtd": cancelados_qtd,
        "cancelados_pct": cancelados_pct,
        "pontos_total": pontos_total,
        "meta_prata": meta_prata,
        "meta_ouro": meta_ouro,
        "perc_ating_prata": perc_ating_prata,
        "perc_ating_ouro": perc_ating_ouro,
        "projecao_pontos": projecao_pontos,
        "projecao_valor": projecao_valor,
        "perc_proj": perc_proj,
        "media_du_valor": media_du_valor,
        "media_du_pontos": media_du_pontos,
        "meta_diaria_restante": meta_diaria_restante,
        "du_total": du_total,
        "du_decorridos": du_dec,
        "du_restantes": du_rest,
    }


# ══════════════════════════════════════════════════════
# Breakdown por produto
# ══════════════════════════════════════════════════════


def calcular_breakdown_produtos_consultor(
    df_meu: pd.DataFrame,
) -> pd.DataFrame:
    """
    Agrega a producao do consultor por grupo de produto.

    Produtos com ``grupo_dashboard`` preenchido (CNC, SAQUE,
    CLT, CONSIGNADO, PACK) contam para valor e pontos.
    Emissoes (BMG Med, Vida Familiar, Cartao) entram numa
    linha separada com apenas quantidade.

    Returns:
        DataFrame ordenado por pontos desc. Colunas:
            produto, qtd, valor, pontos, ticket_medio,
            eh_emissao (bool).
    """
    if df_meu.empty:
        return pd.DataFrame(
            columns=[
                "produto", "qtd", "valor", "pontos",
                "ticket_medio", "eh_emissao",
            ]
        )

    df = df_meu.copy()

    # ── Produtos regulares (grupo_dashboard valido) ──
    df_reg = df[df["grupo_dashboard"].notna()].copy()
    if not df_reg.empty:
        reg = (
            df_reg.groupby("grupo_dashboard")
            .agg(
                qtd=("VALOR", "size"),
                valor=("VALOR", "sum"),
                pontos=("pontos", "sum"),
            )
            .reset_index()
            .rename(columns={"grupo_dashboard": "produto"})
        )
        reg["eh_emissao"] = False
    else:
        reg = pd.DataFrame(
            columns=[
                "produto", "qtd", "valor", "pontos",
                "eh_emissao",
            ]
        )

    # ── Emissoes: contam so quantidade ─────────────
    emissoes = []
    if "is_emissao_cartao" in df.columns:
        q = int(df["is_emissao_cartao"].sum())
        if q > 0:
            emissoes.append(
                {"produto": "Cartao",
                 "qtd": q, "valor": 0.0, "pontos": 0.0,
                 "eh_emissao": True}
            )
    if "is_bmg_med" in df.columns:
        q = int(df["is_bmg_med"].sum())
        if q > 0:
            emissoes.append(
                {"produto": "BMG Med",
                 "qtd": q, "valor": 0.0, "pontos": 0.0,
                 "eh_emissao": True}
            )
    if "is_seguro_vida" in df.columns:
        q = int(df["is_seguro_vida"].sum())
        if q > 0:
            emissoes.append(
                {"produto": "Vida Familiar",
                 "qtd": q, "valor": 0.0, "pontos": 0.0,
                 "eh_emissao": True}
            )

    df_emi = pd.DataFrame(emissoes) if emissoes else pd.DataFrame()

    breakdown = pd.concat([reg, df_emi], ignore_index=True)

    # Ticket medio (só faz sentido p/ produtos regulares)
    breakdown["ticket_medio"] = (
        breakdown["valor"] / breakdown["qtd"].replace(0, pd.NA)
    ).fillna(0.0)

    # Ordem: regulares por pontos desc, emissoes no fim
    breakdown = breakdown.sort_values(
        by=["eh_emissao", "pontos"],
        ascending=[True, False],
    ).reset_index(drop=True)

    return breakdown


# ══════════════════════════════════════════════════════
# Rankings (regional e global)
# ══════════════════════════════════════════════════════


def _ranking_por_pontos(
    df: pd.DataFrame,
    consultor_nome: str,
    categoria_codigo: Optional[str] = None,
) -> pd.DataFrame:
    """
    Calcula ranking de consultores por pontos no df
    informado. Se ``categoria_codigo`` for passado, filtra
    apenas contratos daquela categoria.
    """
    if df.empty or "CONSULTOR" not in df.columns:
        return pd.DataFrame(
            columns=["posicao", "CONSULTOR", "pontos",
                     "valor", "qtd", "eh_voce"]
        )

    df_v = df.copy()
    if categoria_codigo:
        df_v = df_v[
            df_v.get("categoria_codigo") == categoria_codigo
        ]
        if df_v.empty:
            return pd.DataFrame(
                columns=["posicao", "CONSULTOR", "pontos",
                         "valor", "qtd", "eh_voce"]
            )

    ranking = (
        df_v.groupby("CONSULTOR")
        .agg(
            pontos=("pontos", "sum"),
            valor=("VALOR", "sum"),
            qtd=("VALOR", "size"),
        )
        .reset_index()
        .sort_values("pontos", ascending=False, kind="stable")
        .reset_index(drop=True)
    )
    ranking["posicao"] = ranking.index + 1
    ranking["eh_voce"] = ranking["CONSULTOR"] == consultor_nome

    return ranking[
        ["posicao", "CONSULTOR", "pontos",
         "valor", "qtd", "eh_voce"]
    ]


def ranking_global(
    df_full: pd.DataFrame,
    consultor_nome: str,
    categoria_codigo: Optional[str] = None,
) -> pd.DataFrame:
    """Ranking global (todas as regioes) por pontos."""
    return _ranking_por_pontos(
        df_full, consultor_nome, categoria_codigo,
    )


def ranking_regional(
    df_full: pd.DataFrame,
    consultor_nome: str,
    regiao: str,
    categoria_codigo: Optional[str] = None,
) -> pd.DataFrame:
    """Ranking dentro da regiao do consultor."""
    if df_full.empty or "REGIAO" not in df_full.columns:
        return pd.DataFrame(
            columns=["posicao", "CONSULTOR", "pontos",
                     "valor", "qtd", "eh_voce"]
        )
    df_r = df_full[df_full["REGIAO"] == regiao]
    return _ranking_por_pontos(
        df_r, consultor_nome, categoria_codigo,
    )


def top_com_voce(
    ranking: pd.DataFrame,
    top_n: int = 10,
) -> pd.DataFrame:
    """
    Retorna o top N do ranking; se o consultor logado
    nao estiver no top, anexa a linha dele ao final.

    Permite renderizar "top 10 + sua posicao" em uma
    unica tabela.
    """
    if ranking.empty:
        return ranking

    top = ranking.head(top_n).copy()
    voce = ranking[ranking["eh_voce"]]
    if voce.empty:
        return top
    if voce.iloc[0]["posicao"] <= top_n:
        return top
    return pd.concat([top, voce], ignore_index=True)
