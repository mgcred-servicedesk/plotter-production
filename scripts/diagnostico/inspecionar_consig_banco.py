"""Mostra que valores de BANCO aparecem para cada CONSIG_*."""
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
    consigs = df[
        df["categoria_codigo"].fillna("").str.startswith("CONSIG")
    ].copy()
    print(f"{MES:02d}/{ANO} CONSIG_* qtd: {len(consigs):,}\n")

    bd = (
        consigs.groupby(["categoria_codigo", "BANCO"], dropna=False)
        .size().rename("qtd").reset_index()
        .sort_values(["categoria_codigo", "qtd"], ascending=[True, False])
    )
    with pd.option_context("display.max_rows", None,
                           "display.width", 200):
        print(bd.to_string(index=False))


if __name__ == "__main__":
    main()
