"""
Regras dos seguros (BMG Med e Vida Familiar) sobre as tres fontes de
contrato: pagos, em analise e cancelados.

## Por que estes produtos tem modulo proprio

BMG Med e Vida Familiar nao seguem o ciclo de `status_banco` do resto
do dashboard. O estado real deles vive em `SUB_STATUS`
(`Liquidada` = paga, `Cancelada` = cancelada, o resto = em analise), e
a mesma adesao pode aparecer nas TRES fontes ao mesmo tempo — dai a
uniao com deduplicacao por `CONTRATO_ID`.

Extraido de `tabs/analiticos.py` na Etapa 2 da revisao de 09/2026: a
uniao, a deduplicacao e a classificacao sao **regra de negocio**, e
estavam dentro do renderer da aba. Os corpos foram movidos sem
alteracao (prova de move byte-identico no commit); o renderer
continua chamando as duas pelo mesmo nome.
"""

import pandas as pd


def _pool_seguros(
    df: pd.DataFrame,
    df_analise: pd.DataFrame,
    df_cancelados: pd.DataFrame,
    tipo_oper: str,
) -> pd.DataFrame:
    """Une seguros (BMG MED ou Seguro) das 3 fontes e dedupe por CONTRATO_ID.

    Para BMG Med / Vida Familiar o "status" real do contrato vive em
    SUB_STATUS (Liquidada=paga, Cancelada=cancelada, demais=em analise);
    `status_banco` nao reflete o ciclo desses produtos.

    Em caso de duplicidade entre fontes (mesmo CONTRATO_ID), preserva a
    linha de pagos > analise > cancelados.
    """
    pieces = []
    for src, origem in (
        (df, "pago"),
        (df_analise, "analise"),
        (df_cancelados, "cancelado"),
    ):
        if src is None or src.empty or "TIPO OPER." not in src.columns:
            continue
        sub = src[src["TIPO OPER."] == tipo_oper].copy()
        if sub.empty:
            continue
        sub["_origem"] = origem
        pieces.append(sub)

    if not pieces:
        return pd.DataFrame()

    pool = pd.concat(pieces, ignore_index=True, sort=False)
    if "SUB_STATUS" not in pool.columns:
        pool["SUB_STATUS"] = ""
    pool["SUB_STATUS"] = pool["SUB_STATUS"].fillna("").astype(str)

    if "CONTRATO_ID" in pool.columns:
        prio = {"pago": 0, "analise": 1, "cancelado": 2}
        pool["_prio"] = pool["_origem"].map(prio).fillna(99)
        pool = (
            pool.sort_values("_prio")
            .drop_duplicates(subset=["CONTRATO_ID"], keep="first")
            .drop(columns=["_prio"])
        )

    return pool


def _classificar_status_seguro(sub_status: pd.Series) -> pd.Series:
    """Mapeia SUB_STATUS de seguros para Pagas / Em Analise / Cancelados."""
    s = sub_status.fillna("").astype(str).str.strip()
    return pd.Series(
        ["Pagas" if v == "Liquidada"
         else "Cancelados" if v == "Cancelada"
         else "Em Analise"
         for v in s],
        index=sub_status.index,
    )
