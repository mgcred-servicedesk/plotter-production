"""
KPIs para a aba de Gestao: visao por consultor do VALOR pago por
produto MIX, com filtro multi-criterio por faixa de valor.

A dimensao de produto deriva do MIX definido em ``PRODUTOS_DASHBOARD``
(src/dashboard/kpis/gerais.py), que mapeia cada produto para os
``categoria_codigo`` correspondentes. "Consignado", por exemplo, agrega
CONSIG_BMG/ITAU/C6; o pack (FGTS_ANT_BEN_CNC13) aparece desmembrado nas
suas tres categorias — ver ``PRODUTOS_GESTAO``.
"""
from typing import Dict, Optional

import pandas as pd

from src.config.settings import PACK_SPLIT_LABELS
from src.dashboard.kpis.gerais import PRODUTOS_DASHBOARD, excluir_supervisores

# Mapeamento produto -> categoria_codigo para a aba de Gestao.
#
# Difere do MIX global (PRODUTOS_DASHBOARD) em um ponto: o grupo
# "FGTS_ANT_BEN_CNC13" e desmembrado nas suas tres categorias (a visao
# nao compara com meta, entao vale a leitura granular), com os rotulos
# canonicos de PACK_SPLIT_LABELS. Os demais produtos sao derivados de
# PRODUTOS_DASHBOARD para manter sincronia com a taxonomia global.
PRODUTOS_GESTAO: Dict[str, list[str]] = {
    "CNC": PRODUTOS_DASHBOARD["CNC"],
    "CLT": PRODUTOS_DASHBOARD["CLT"],
    "Saque": PRODUTOS_DASHBOARD["SAQUE"],
    "Consignado": PRODUTOS_DASHBOARD["CONSIGNADO"],
    **{
        PACK_SPLIT_LABELS[cat]: [cat]
        for cat in PRODUTOS_DASHBOARD["FGTS_ANT_BEN_CNC13"]
    },
}


def vendas_mix_por_consultor(
    df: pd.DataFrame,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Tabela por consultor com o VALOR pago em cada produto de Gestao.

    Colunas: ``Regiao`` e ``Loja`` (quando presentes em ``df``),
    ``Consultor``, uma coluna por produto de ``PRODUTOS_GESTAO`` (com o
    pack desmembrado em FGTS, ANT. DE BENEF. e CNC 13º) e ``Total``
    (soma dessas colunas). Considera apenas ``VALOR > 0`` e exclui
    supervisores, em linha com os rankings de consultor.

    Espera ``df`` ja filtrado por RLS (feito em ``app.py``); nao aplica
    RLS nem queries aqui.
    """
    obrigatorias = {"CONSULTOR", "VALOR", "categoria_codigo"}
    if df.empty or not obrigatorias.issubset(df.columns):
        return pd.DataFrame()

    df_v = df[df["VALOR"] > 0].copy()
    df_v = excluir_supervisores(df_v, df_supervisores)
    if df_v.empty:
        return pd.DataFrame()

    agg: Dict[str, tuple] = {}
    if "REGIAO" in df_v.columns:
        agg["Regiao"] = ("REGIAO", "first")
    if "LOJA" in df_v.columns:
        agg["Loja"] = ("LOJA", "first")

    if agg:
        base = df_v.groupby("CONSULTOR").agg(**agg).reset_index()
    else:
        base = (
            df_v[["CONSULTOR"]]
            .drop_duplicates()
            .reset_index(drop=True)
        )
    base = base.rename(columns={"CONSULTOR": "Consultor"})

    rotulos = list(PRODUTOS_GESTAO)
    for rotulo, cats in PRODUTOS_GESTAO.items():
        mask = df_v["categoria_codigo"].isin(cats)
        soma = df_v.loc[mask].groupby("CONSULTOR")["VALOR"].sum()
        base[rotulo] = base["Consultor"].map(soma).fillna(0.0)

    base["Total"] = base[rotulos].sum(axis=1)

    ordem = [c for c in ("Regiao", "Loja") if c in base.columns]
    ordem += ["Consultor", *rotulos, "Total"]
    base = base[ordem]

    sort_cols = [c for c in ("Regiao", "Consultor") if c in base.columns]
    return base.sort_values(sort_cols).reset_index(drop=True)


def filtrar_por_criterios(
    tabela: pd.DataFrame,
    criterios: Dict[str, Dict[str, float | str]],
) -> pd.DataFrame:
    """Aplica criterios de faixa de valor por produto, combinados por E.

    Args:
        tabela: saida de :func:`vendas_mix_por_consultor`.
        criterios: ``{rotulo_produto: {"modo": "menor"|"entre",
            "max": float, "min": float}}``. Para ``modo="menor"`` usa
            ``valor < max``; para ``modo="entre"`` usa ``min <= valor <=
            max`` (inclusivo). Produtos ausentes da tabela sao ignorados.

    Returns:
        Apenas os consultores que atendem a TODOS os criterios. Sem
        criterios, retorna a tabela inalterada.
    """
    if tabela.empty or not criterios:
        return tabela

    mask = pd.Series(True, index=tabela.index)
    for rotulo, crit in criterios.items():
        if rotulo not in tabela.columns:
            continue
        coluna = tabela[rotulo]
        if crit.get("modo") == "entre":
            minimo = float(crit.get("min", 0.0))
            maximo = float(crit.get("max", 0.0))
            mask &= coluna.between(minimo, maximo)
        else:  # "menor"
            maximo = float(crit.get("max", 0.0))
            mask &= coluna < maximo

    return tabela[mask].reset_index(drop=True)
