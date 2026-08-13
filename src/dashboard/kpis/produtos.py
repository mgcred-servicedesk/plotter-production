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

# Bancos aceitos pela flag "Somente BMG/Help". Valores JA normalizados
# (strip + upper) — a comparacao normaliza a coluna antes do ``isin``.
#
# Duplicado de ``src/dashboard/tabs/produtos.py`` (``_BANCOS_BMG_HELP``,
# origem da lista) **de proposito**: importar de la criaria import
# cruzado UI -> KPI, invertendo a direcao de dependencia entre as
# camadas. Se a lista mudar, mudar nos dois lugares. Ver
# ``docs/agents/business-rules.md`` § 'Flag "Somente BMG/Help"'.
_BANCOS_BMG_HELP = ("BMG", "BANCO BMG", "HELP", "BANCO HELP")


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


def _mask_banco_bmg_help(df: pd.DataFrame) -> pd.Series:
    """Mascara de ``BANCO`` normalizado dentro de :data:`_BANCOS_BMG_HELP`.

    ``BANCO`` ausente do frame vira mascara toda-False — com a flag
    ligada isso **zera a tabela inteira**, coerente com "criterio sem
    coluna zera a contagem" (nunca devolve dado nao filtrado como se
    filtrado fosse).
    """
    if "BANCO" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["BANCO"].astype(str).str.strip().str.upper().isin(_BANCOS_BMG_HELP)


def _mascaras_aceleradores(
    df: pd.DataFrame,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """Devolve as 6 mascaras de acelerador.

    Ordem: bmg, seguro, emissao, super conta, CLT, consignado
    (Novo/Refin).

    Criterio declarado cuja coluna nao existe no frame vira mascara
    toda-False (nunca infla contagem). Usado pelas distribuicoes por
    consultor e por loja — e recalculado apos qualquer filtro/reset_index,
    porque a mascara so vale para o indice em que foi construida.

    CLT e Consignado reusam o criterio canonico de
    ``docs/agents/business-rules.md`` § "CLT e Consignado (Novo/Refin)
    pagos": CLT e ``CONSIG_PRIV`` menos ``SEGURO PRESTAMISTA`` (que e
    seguro, nao credito); Consignado e ``CONSIG_{BMG,ITAU,C6}``
    restrito a ``SUBTIPO ∈ {NOVO, REFIN}`` (Portabilidade e Refin da
    Portabilidade se excluem sozinhos, porque mantem
    ``categoria_codigo = PORTABILIDADE``; ``MARGEM COMPLEMENTAR`` fica
    de fora por nao ser Novo nem Refin).
    """

    def _flag(col: str) -> pd.Series:
        return df.get(col, pd.Series(False, index=df.index)).fillna(False).astype(bool)

    def _norm(col: str) -> pd.Series:
        return df[col].astype(str).str.strip().str.upper()

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
    mask_clt = (
        (df["categoria_codigo"] == "CONSIG_PRIV")
        & (_norm("TIPO OPER.") != "SEGURO PRESTAMISTA")
        if {"categoria_codigo", "TIPO OPER."}.issubset(df.columns)
        else pd.Series(False, index=df.index)
    )
    mask_consig = (
        df["categoria_codigo"].isin({"CONSIG_BMG", "CONSIG_ITAU", "CONSIG_C6"})
        & _norm("SUBTIPO").isin({"NOVO", "REFIN"})
        if {"categoria_codigo", "SUBTIPO"}.issubset(df.columns)
        else pd.Series(False, index=df.index)
    )
    return mask_bmg, mask_seg, mask_em, mask_sc, mask_clt, mask_consig


def calcular_distribuicao_produtos(
    df: pd.DataFrame,
    df_supervisores: Optional[pd.DataFrame] = None,
    somente_bmg_help: bool = False,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Distribuicao de valor e quantidade por consultor.

    Produtos de valor (CNC, SAQUE, etc.): agrega por VALOR (R$).
    Aceleradores (BMG Med, Vida Familiar, Emissao, Super Conta, CLT,
    Consignado (Novo/Refin)): agrega por quantidade de contratos.

    CLT e Consignado sao colunas de **quantidade acrescentadas por
    cima**: o valor em R$ desses produtos ja aparece nas colunas de
    valor do pivot (via ``grupo_dashboard`` 'CLT'/'CONSIGNADO'), e por
    isso eles **nao** sao excluidos de ``mask_cred`` — mesmo tratamento
    que Super Conta ja recebe (conta duas vezes, em valor e em
    quantidade). Criterio em ``docs/agents/business-rules.md``
    § "CLT e Consignado (Novo/Refin) pagos".

    ``somente_bmg_help`` restringe a **tabela inteira** (todas as
    colunas: valor, quantidade e TOTAL) a ``BANCO ∈``
    :data:`_BANCOS_BMG_HELP` — o recorte entra no topo, antes de
    qualquer mascara, entao todo o pipeline ja o herda. Escopo
    **diferente** do toggle homonimo de "Emissao e Seguros — Analise
    Regional" (``src/dashboard/tabs/produtos.py``), que so existe dentro
    das abas CLT/Consignado e so afeta a aba onde esta ligado.

    Visao consultor-level → aplica ``excluir_supervisores``
    (``docs/agents/business-rules.md`` § "Exclusao de supervisores").

    Returns (df, colunas_moeda, colunas_numero).
    """
    if "CONSULTOR" not in df.columns:
        return pd.DataFrame(), [], []

    if somente_bmg_help:
        # Recorte no topo: pivot de valor, 6 mascaras, TOTAL e os merges
        # de LOJA/REGIAO abaixo passam a ler o frame ja filtrado, sem
        # branch por coluna. Sem ``BANCO``, zera a tabela inteira.
        df = df[_mask_banco_bmg_help(df)].copy()

    mask_bmg, mask_seg, mask_em, mask_sc, mask_clt, mask_consig = _mascaras_aceleradores(df)

    mask_all = (
        (df["VALOR"] > 0) | mask_bmg | mask_seg | mask_em | mask_sc | mask_clt | mask_consig
    )
    df_v = excluir_supervisores(df[mask_all].copy().reset_index(drop=True), df_supervisores)

    # Recompute flags on filtered df
    bmg_v, seg_v, em_v, sc_v, clt_v, consig_v = _mascaras_aceleradores(df_v)

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
        # "CLT (Qtd)", e nao "CLT": ``CONSIG_PRIV`` tem
        # ``grupo_dashboard = 'CLT'`` (database/schema.sql), entao o pivot
        # de VALOR ja emite uma coluna chamada "CLT". Nomes iguais fazem o
        # merge virar "CLT_x"/"CLT_y", e ai os filtros ``c in
        # distrib.columns`` derrubam AS DUAS — o R$ de CLT sumiria do
        # TOTAL silenciosamente. "CONSIGNADO" (valor) x "Consignado
        # (Novo/Refin)" (qtd) nao colidem, por isso so CLT precisa do
        # sufixo.
        ("CLT (Qtd)", clt_v),
        ("Consignado (Novo/Refin)", consig_v),
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


def calcular_distribuicao_produtos_por_loja(
    df: pd.DataFrame,
    somente_bmg_help: bool = False,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Distribuicao de valor e quantidade por LOJA.

    Mesmas mascaras e mesmos pivots de
    :func:`calcular_distribuicao_produtos` — incluindo as colunas de
    quantidade CLT e Consignado (Novo/Refin) e o parametro
    ``somente_bmg_help``, que aqui tambem recorta a **tabela inteira**
    (valor + quantidade + TOTAL) a ``BANCO ∈`` :data:`_BANCOS_BMG_HELP`,
    e nao apenas as duas colunas novas. Com duas diferencas centrais:

    1. **Eixo de agregacao**: ``LOJA`` no lugar de ``CONSULTOR``.
    2. **Nao exclui supervisor**: a producao do proprio supervisor entra
       somada (e anonima) no total da loja — nao ha ``excluir_supervisores``
       aqui, e por isso a funcao nao recebe ``df_supervisores``.

    O item 2 segue o precedente ja documentado em
    ``docs/agents/business-rules.md`` §§ "Producao de supervisor — conta
    pro total, marcada, fora do ranking" e "Exclusao de supervisores":
    total por loja/regiao soma supervisor; so visao consultor-level o
    exclui (``calcular_distribuicao_produtos`` continua excluindo).

    Returns (df, colunas_moeda, colunas_numero).
    """
    if "LOJA" not in df.columns:
        return pd.DataFrame(), [], []

    if somente_bmg_help:
        # Recorte no topo: pivot de valor, 6 mascaras, TOTAL e o merge
        # de REGIAO abaixo passam a ler o frame ja filtrado, sem branch
        # por coluna. Sem ``BANCO``, zera a tabela inteira.
        df = df[_mask_banco_bmg_help(df)].copy()

    mask_bmg, mask_seg, mask_em, mask_sc, mask_clt, mask_consig = _mascaras_aceleradores(df)

    mask_all = (
        (df["VALOR"] > 0) | mask_bmg | mask_seg | mask_em | mask_sc | mask_clt | mask_consig
    )
    # Sem excluir_supervisores: producao de supervisor conta pra loja.
    df_v = df[mask_all].copy().reset_index(drop=True)

    # Recompute flags on filtered df
    bmg_v, seg_v, em_v, sc_v, clt_v, consig_v = _mascaras_aceleradores(df_v)

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
            index="LOJA",
            columns="PRODUTO_MIX",
            values="VALOR",
            aggfunc="sum",
            fill_value=0,
        ).reset_index()
        cols_valor = [c for c in pv_val.columns if c != "LOJA"]
    else:
        pv_val = pd.DataFrame(columns=["LOJA"])
        cols_valor = []

    # ── Pivot de Qtd (aceleradores) ─────────────────────────────────────────
    _ACEL = [
        ("BMG Med", bmg_v),
        ("Vida Familiar", seg_v),
        ("Emissao", em_v),
        ("Super Conta", sc_v),
        # "CLT (Qtd)", e nao "CLT": ``CONSIG_PRIV`` tem
        # ``grupo_dashboard = 'CLT'`` (database/schema.sql), entao o pivot
        # de VALOR ja emite uma coluna chamada "CLT". Nomes iguais fazem o
        # merge virar "CLT_x"/"CLT_y", e ai os filtros ``c in
        # distrib.columns`` derrubam AS DUAS — o R$ de CLT sumiria do
        # TOTAL silenciosamente. "CONSIGNADO" (valor) x "Consignado
        # (Novo/Refin)" (qtd) nao colidem, por isso so CLT precisa do
        # sufixo.
        ("CLT (Qtd)", clt_v),
        ("Consignado (Novo/Refin)", consig_v),
    ]
    pv_qtd = pd.DataFrame({"LOJA": df_v["LOJA"].unique()})
    cols_qtd: list[str] = []
    for nome, mask in _ACEL:
        if mask.any():
            qtd = df_v[mask].groupby("LOJA").size().rename(nome)
            pv_qtd = pv_qtd.merge(qtd.reset_index(), on="LOJA", how="left")
            pv_qtd[nome] = pv_qtd[nome].fillna(0).astype(int)
            cols_qtd.append(nome)

    # ── Merge e TOTAL ────────────────────────────────────────────────────────
    distrib = pv_val.merge(pv_qtd, on="LOJA", how="outer").fillna(0)
    cv_exist = [c for c in cols_valor if c in distrib.columns]
    distrib["TOTAL"] = distrib[cv_exist].sum(axis=1)

    if "REGIAO" in df.columns:
        # drop_duplicates("LOJA") — e nao o par (LOJA, REGIAO): loja que
        # trocou de regiao no meio do periodo (vigencia temporal) traria
        # duas linhas e duplicaria a loja inteira no resultado.
        distrib = distrib.merge(
            df[["LOJA", "REGIAO"]].drop_duplicates("LOJA"),
            on="LOJA", how="left",
        )

    # Ordem: info | produtos valor | TOTAL | aceleradores
    col_order = ["LOJA"]
    if "REGIAO" in distrib.columns:
        col_order.append("REGIAO")
    col_order += sorted(cv_exist) + ["TOTAL"] + [c for c in cols_qtd if c in distrib.columns]

    distrib = distrib[[c for c in col_order if c in distrib.columns]]
    distrib = distrib.sort_values("TOTAL", ascending=False).reset_index(drop=True)

    colunas_moeda = [c for c in sorted(cv_exist) + ["TOTAL"] if c in distrib.columns]
    colunas_numero = [c for c in cols_qtd if c in distrib.columns]
    return distrib, colunas_moeda, colunas_numero
