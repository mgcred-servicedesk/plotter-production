"""Inspeciona contratos PORTABILIDADE para mapear banco origem."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from src.dashboard.loaders import carregar_contratos_pagos  # noqa: E402

MES = int(sys.argv[1]) if len(sys.argv) > 1 else 5
ANO = int(sys.argv[2]) if len(sys.argv) > 2 else 2026


def main() -> None:
    df = carregar_contratos_pagos(MES, ANO)
    mask = (
        df["categoria_codigo"].fillna("").str.upper() == "PORTABILIDADE"
    ) | (
        df["TIPO_PRODUTO"].astype(str).str.upper().str.contains(
            "PORTAB", na=False
        )
    )
    pp = df.loc[mask].copy()
    print(f"PORTABILIDADE: {len(pp)} contratos em {MES:02d}/{ANO}\n")
    if pp.empty:
        return

    print("Colunas disponiveis:")
    print(list(pp.columns))
    print()

    candidatas = [c for c in pp.columns if any(
        k in c.lower() for k in ["banco", "tipo", "oper", "subtipo",
                                  "produto", "categoria"]
    )]
    print("Colunas candidatas:", candidatas, "\n")

    with pd.option_context("display.max_columns", None,
                           "display.width", 220):
        print(pp[candidatas].to_string(index=False))

    print("\nValores unicos por candidata:")
    for c in candidatas:
        u = pp[c].dropna().unique()
        print(f"  {c}: {list(u)}")


if __name__ == "__main__":
    main()
