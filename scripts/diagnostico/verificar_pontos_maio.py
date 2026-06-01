"""Diagnostica pontuacao total de Maio.

Carrega contratos via mesma logica do dashboard, agrega
pontos por categoria, sinaliza exclusoes e mostra
contratos sem pontuacao mapeada. Objetivo: explicar
delta entre soma manual e dashboard.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from src.dashboard.loaders import (  # noqa: E402
    _executar_consolidacao,
    carregar_contratos_pagos,
    carregar_pontuacao_efetiva,
)

MES = int(sys.argv[1]) if len(sys.argv) > 1 else 5
ANO = int(sys.argv[2]) if len(sys.argv) > 2 else 2026


def main() -> None:
    print(f"=== Diagnostico pontuacao {MES:02d}/{ANO} ===\n")

    df_raw = carregar_contratos_pagos(MES, ANO)
    print(f"contratos brutos (view): {len(df_raw):,}")

    df_pts = carregar_pontuacao_efetiva(MES, ANO)
    print("\nTabela pontuacao efetiva (categoria -> pontos):")
    print(df_pts.to_string(index=False))

    df, _metas, _supers, diag = _executar_consolidacao(MES, ANO)
    print(f"\ncontratos pos consolidacao: {len(df):,}")

    if diag:
        print(f"sem categoria mapeada: {diag['sem_categoria']}")
        print(f"com categoria mapeada: {diag['com_categoria']}")
        print(f"com pontos>0:          {diag['com_pontos_mapeados']}")
        print(f"sem pontos (0):        {diag['sem_pontos_mapeados']}")
        if diag.get("tipos_sem_categoria"):
            print(
                f"tipos sem categoria: {diag['tipos_sem_categoria']}"
            )

    total = float(df["pontos"].sum())
    print(f"\n>>> TOTAL PONTOS DASHBOARD: {total:,.0f}")
    print(">>> Esperado pelo usuario:   25.076.375")
    print(f">>> Diff:                   {total - 25_076_375:,.0f}")

    print("\n--- Breakdown por categoria_codigo ---")
    bd = (
        df.groupby("categoria_codigo", dropna=False)
        .agg(
            qtd=("VALOR", "size"),
            valor=("VALOR", "sum"),
            pts_unit=("PONTOS", "first"),
            pts_total=("pontos", "sum"),
            conta_valor=("conta_valor", "first"),
            conta_pts=("conta_pontuacao", "first"),
        )
        .sort_values("pts_total", ascending=False)
    )
    with pd.option_context("display.max_rows", None,
                           "display.width", 200,
                           "display.float_format", "{:,.2f}".format):
        print(bd)

    print("\n--- Contratos com VALOR>0 mas pontos=0 ---")
    mask_perdidos = (df["VALOR"] > 0) & (df["pontos"] == 0)
    perdidos = df.loc[mask_perdidos]
    print(f"qtd: {len(perdidos):,}")
    if not perdidos.empty:
        agg = (
            perdidos.groupby(
                ["categoria_codigo", "TIPO_PRODUTO", "TIPO OPER.",
                 "conta_valor", "conta_pontuacao"],
                dropna=False,
            )
            .agg(qtd=("VALOR", "size"), valor=("VALOR", "sum"))
            .sort_values("valor", ascending=False)
        )
        with pd.option_context("display.max_rows", 30,
                               "display.width", 200):
            print(agg.head(30))

    print("\n--- Contratos sem categoria_codigo ---")
    sem = df[df["categoria_codigo"].fillna("") == ""]
    print(f"qtd: {len(sem):,}")
    if not sem.empty and "TIPO_PRODUTO" in sem.columns:
        print(sem["TIPO_PRODUTO"].value_counts().head(20))


if __name__ == "__main__":
    main()
