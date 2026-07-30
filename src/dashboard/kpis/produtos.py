"""
KPIs e distribuicoes por grupo de produto.

Guarda tambem a dimensao derivada ``PRODUTO_DETALHADO``, que desmembra o
grupo ``PACK`` nas suas tres categorias. Superficies que comparam valor
x META continuam agrupando por ``grupo_dashboard`` (a meta
``FGTS_ANT_BENEF_13`` e conjunta — nao existe alvo por categoria).
"""

from typing import Optional

import pandas as pd

from src.config.settings import (  # noqa: F401  (PACK_SPLIT_LABELS reexportado)
    NOMES_DISPLAY_PRODUTO,
    PACK_SPLIT_LABELS,
    PRODUTOS_EMISSAO,
)
from src.dashboard.kpis.gerais import (
    contar_consultores,
    excluir_supervisores,
)
from src.shared.dias_uteis import calcular_dias_uteis

# Nome da coluna derivada que substitui ``grupo_dashboard`` nas visoes
# sem meta (listagens, rankings, distribuicao, detalhe dos cards).
COL_PRODUTO_DETALHADO = "PRODUTO_DETALHADO"


def adicionar_produto_detalhado(df: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta ``PRODUTO_DETALHADO`` desmembrando o grupo 'PACK'.

    Para cada linha: se ``categoria_codigo`` pertence ao PACK
    (``PACK_SPLIT_LABELS``), usa o rotulo granular (FGTS / ANT. DE
    BENEF. / CNC 13º); caso contrario mantem o ``grupo_dashboard``
    (aplicando ``NOMES_DISPLAY_PRODUTO`` como rede de seguranca para
    qualquer 'PACK' residual que nao tenha caido no split). Copia
    defensiva.

    Se faltar ``grupo_dashboard``, devolve o df inalterado (os
    consumidores fazem fallback para ``grupo_dashboard`` quando a coluna
    nao existe).
    """
    if df.empty or "grupo_dashboard" not in df.columns:
        return df
    out = df.copy()
    base = out["grupo_dashboard"].replace(NOMES_DISPLAY_PRODUTO)
    if "categoria_codigo" in out.columns:
        granular = out["categoria_codigo"].map(PACK_SPLIT_LABELS)
        out[COL_PRODUTO_DETALHADO] = granular.fillna(base)
    else:
        out[COL_PRODUTO_DETALHADO] = base
    return out


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
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Distribuicao de valor e quantidade por consultor.

    Produtos de valor (CNC, SAQUE, etc.): agrega por VALOR (R$).
    Aceleradores (BMG Med, Vida Familiar, Emissao, Super Conta):
    agrega por quantidade de contratos.

    Returns (df, colunas_moeda, colunas_numero).
    """
    if "CONSULTOR" not in df.columns:
        return pd.DataFrame(), [], []

    def _flag(col: str) -> pd.Series:
        return df.get(col, pd.Series(False, index=df.index)).fillna(False).astype(bool)

    mask_bmg = _flag("is_bmg_med")
    mask_seg = _flag("is_seguro_vida")
    mask_em = (
        df["TIPO_PRODUTO"].str.upper().isin({p.upper() for p in PRODUTOS_EMISSAO})
        if "TIPO_PRODUTO" in df.columns
        else pd.Series(False, index=df.index)
    )
    mask_sc = (
        df["SUBTIPO"].str.strip().str.upper() == "SUPER CONTA"
        if "SUBTIPO" in df.columns
        else pd.Series(False, index=df.index)
    )

    mask_all = (df["VALOR"] > 0) | mask_bmg | mask_seg | mask_em | mask_sc
    df_v = excluir_supervisores(df[mask_all].copy().reset_index(drop=True), df_supervisores)

    # Recompute flags on filtered df
    def _flag_v(col: str) -> pd.Series:
        return df_v.get(col, pd.Series(False, index=df_v.index)).fillna(False).astype(bool)

    bmg_v = _flag_v("is_bmg_med")
    seg_v = _flag_v("is_seguro_vida")
    em_v = (
        df_v["TIPO_PRODUTO"].str.upper().isin({p.upper() for p in PRODUTOS_EMISSAO})
        if "TIPO_PRODUTO" in df_v.columns
        else pd.Series(False, index=df_v.index)
    )
    sc_v = (
        df_v["SUBTIPO"].str.strip().str.upper() == "SUPER CONTA"
        if "SUBTIPO" in df_v.columns
        else pd.Series(False, index=df_v.index)
    )

    # ── Pivot de VALOR (produtos de crédito) ────────────────────────────────
    mask_cred = (df_v["VALOR"] > 0) & ~bmg_v & ~seg_v & ~em_v
    # PACK desmembrado: a distribuicao nao compara com meta, entao cada
    # categoria vira sua propria coluna (FGTS / ANT. DE BENEF. / CNC 13º).
    df_cred = adicionar_produto_detalhado(df_v[mask_cred].copy())
    df_cred["PRODUTO_MIX"] = (
        df_cred[COL_PRODUTO_DETALHADO].fillna("OUTROS")
        if COL_PRODUTO_DETALHADO in df_cred.columns
        else df_cred["grupo_dashboard"].fillna("OUTROS")
    )

    if not df_cred.empty:
        pv_val = df_cred.pivot_table(
            index="CONSULTOR",
            columns="PRODUTO_MIX",
            values="VALOR",
            aggfunc="sum",
            fill_value=0,
        ).reset_index()
        cols_valor = [c for c in pv_val.columns if c != "CONSULTOR"]
    else:
        pv_val = pd.DataFrame(columns=["CONSULTOR"])
        cols_valor = []

    # ── Pivot de Qtd (aceleradores) ─────────────────────────────────────────
    _ACEL = [
        ("BMG Med", bmg_v),
        ("Vida Familiar", seg_v),
        ("Emissao", em_v),
        ("Super Conta", sc_v),
    ]
    pv_qtd = pd.DataFrame({"CONSULTOR": df_v["CONSULTOR"].unique()})
    cols_qtd: list[str] = []
    for nome, mask in _ACEL:
        if mask.any():
            qtd = df_v[mask].groupby("CONSULTOR").size().rename(nome)
            pv_qtd = pv_qtd.merge(qtd.reset_index(), on="CONSULTOR", how="left")
            pv_qtd[nome] = pv_qtd[nome].fillna(0).astype(int)
            cols_qtd.append(nome)

    # ── Merge e TOTAL ────────────────────────────────────────────────────────
    distrib = pv_val.merge(pv_qtd, on="CONSULTOR", how="outer").fillna(0)
    cv_exist = [c for c in cols_valor if c in distrib.columns]
    distrib["TOTAL"] = distrib[cv_exist].sum(axis=1)

    if "LOJA" in df.columns:
        distrib = distrib.merge(
            df[["CONSULTOR", "LOJA"]].drop_duplicates("CONSULTOR"),
            on="CONSULTOR", how="left",
        )
    if "REGIAO" in df.columns:
        distrib = distrib.merge(
            df[["LOJA", "REGIAO"]].drop_duplicates(),
            on="LOJA", how="left",
        )

    # Ordem: info | produtos valor | TOTAL | aceleradores
    col_order = ["CONSULTOR"]
    if "LOJA" in distrib.columns:
        col_order.append("LOJA")
    if "REGIAO" in distrib.columns:
        col_order.append("REGIAO")
    col_order += sorted(cv_exist) + ["TOTAL"] + [c for c in cols_qtd if c in distrib.columns]

    distrib = distrib[[c for c in col_order if c in distrib.columns]]
    distrib = distrib.sort_values("TOTAL", ascending=False).reset_index(drop=True)

    colunas_moeda = [c for c in sorted(cv_exist) + ["TOTAL"] if c in distrib.columns]
    colunas_numero = [c for c in cols_qtd if c in distrib.columns]
    return distrib, colunas_moeda, colunas_numero
