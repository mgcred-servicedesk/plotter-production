"""
Regras do Seguro Prestamista CNC (IPV).

Recebe frames JA CARREGADOS (view `v_prestamista_cnc`, pos-RLS) e
devolve frames/dicts — **nao** toca o Supabase. A carga, o cache e o
recorte por perfil ficam em `loaders.carregar_prestamista_cnc`.

## A conta

IPV = SUM(qtd_seguro) / SUM(qtd_elegivel), em qualquer nivel (total,
regiao, loja, consultor). E a mesma conta do BI do banco: o rodape do
arquivo de 10/2026 traz 93 / 231 = 40,26%. Sem elegivel no recorte, o
IPV e indefinido (None) — nunca 0%, que pareceria resultado ruim.

## Escopo: CNC + Super Conta

O filtro "Prst CNC" do BI inclui as propostas de Super Conta (que no
banco e produto CNC — Debito em Conta Portabilidade BMG); na nossa
base elas estao em `categoria_codigo = SUPER_CONTA`. Entram no IPV,
como no BI (decisao do usuario, 08/10/2026). No arquivo de 10/2026:
632 CNC + 80 Super Conta casam com `contratos.num_proposta`.

## Semaforo

Meta e alerta vem de `prestamista_cnc_meta` (migration 134), por
periodo: verde >= meta, amarelo >= alerta, vermelho abaixo. Sem meta
cadastrada nao ha cor (o card mostra o IPV e avisa).

Ver docs/agents/business-rules.md § "Seguro Prestamista CNC".
"""

from typing import Dict, Optional

import pandas as pd


PRESTAMISTA_OK = "ok"                        # periodo importado
PRESTAMISTA_NAO_IMPORTADO = "nao_importado"  # periodo sem linhas
PRESTAMISTA_ERRO = "erro"                    # falha ao ler a view

SEMAFORO_VERDE = "verde"
SEMAFORO_AMARELO = "amarelo"
SEMAFORO_VERMELHO = "vermelho"

COLS_QUEBRA = ["elegiveis", "seguros", "ipv"]


def _somas(df: pd.DataFrame) -> pd.DataFrame:
    """`qtd_elegivel`/`qtd_seguro` como inteiros (NaN -> 0)."""
    out = df.copy()
    for col in ("qtd_elegivel", "qtd_seguro"):
        out[col] = (
            pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)
        )
    return out


def _ipv(seguros: int, elegiveis: int) -> Optional[float]:
    return seguros / elegiveis if elegiveis > 0 else None


def totais_prestamista(df: Optional[pd.DataFrame]) -> Dict:
    """`{elegiveis, seguros, propostas, ipv}` do recorte (frame pos-RLS)."""
    if df is None or df.empty:
        return {"elegiveis": 0, "seguros": 0, "propostas": 0, "ipv": None}
    base = _somas(df)
    eleg = int(base["qtd_elegivel"].sum())
    seg = int(base["qtd_seguro"].sum())
    return {
        "elegiveis": eleg,
        "seguros": seg,
        "propostas": len(base),
        "ipv": _ipv(seg, eleg),
    }


def projetar_prestamista(
    totais: Dict,
    du_decorridos: int,
    du_total: int,
) -> Optional[Dict]:
    """IPV projetado para o fim do mes no ritmo dos DU decorridos.

    Seguros e elegiveis sao projetados pelo mesmo fator (`du_total /
    du_decorridos`, a conta de `media_du * du_total` das vendas), entao a
    razao projetada e o IPV de hoje: no ritmo atual, o mes fecha nele.
    Exibir as contagens projetadas confundia (970 elegiveis projetados x
    231 reais) — so o IPV sai. `None` sem DU decorrido ou sem elegivel.
    """
    if du_decorridos <= 0 or du_total <= 0:
        return None
    eleg = int(totais.get("elegiveis", 0))
    if eleg <= 0:
        return None
    fator = du_total / du_decorridos
    return {"ipv": (int(totais.get("seguros", 0)) * fator) / (eleg * fator)}


def quebra_prestamista(
    df: Optional[pd.DataFrame],
    niveis: list[str],
) -> pd.DataFrame:
    """IPV agrupado por `niveis` (ex.: ["regiao"], ["loja", "consultor"]).

    Linhas sem elegivel ficam (IPV None): quem vendeu CNC sem proposta
    elegivel continua aparecendo, so sem percentual. Ordem: IPV
    decrescente (None no fim), depois elegiveis decrescente.
    """
    cols = [*niveis, *COLS_QUEBRA]
    if df is None or df.empty or any(n not in df.columns for n in niveis):
        return pd.DataFrame(columns=cols)

    base = _somas(df)
    for n in niveis:
        base[n] = base[n].fillna("(Não Identificado)")
    agg = (
        base.groupby(niveis, as_index=False)
        .agg(elegiveis=("qtd_elegivel", "sum"), seguros=("qtd_seguro", "sum"))
    )
    # Ordena pela razao numerica (NaN no fim) e so depois grava o IPV
    # como objeto: uma lista com None vira NaN numa coluna float, e NaN
    # nao e "sem IPV" para quem compara com a meta.
    eleg = agg["elegiveis"].astype(int)
    razao = agg["seguros"].astype(int) / eleg.where(eleg > 0)
    agg = (
        agg.assign(_razao=razao)
        .sort_values(
            ["_razao", "elegiveis"], ascending=[False, False],
            na_position="last",
        )
        .drop(columns="_razao")
    )
    agg["ipv"] = pd.Series(
        [
            _ipv(int(s), int(e))
            for s, e in zip(agg["seguros"], agg["elegiveis"])
        ],
        index=agg.index,
        dtype=object,
    )
    return agg[cols].reset_index(drop=True)


def classificar_ipv(
    ipv: Optional[float],
    meta: Optional[Dict],
) -> Optional[str]:
    """Cor do semaforo; None sem IPV (None/NaN) ou sem meta cadastrada."""
    if ipv is None or pd.isna(ipv) or not meta:
        return None
    if ipv >= float(meta["meta_ipv"]):
        return SEMAFORO_VERDE
    if ipv >= float(meta["faixa_alerta"]):
        return SEMAFORO_AMARELO
    return SEMAFORO_VERMELHO


# ── Situacao por proposta (analiticos) ─────────────────────────────────

SITUACAO_SEM_SEGURO = "⚠️ Elegível sem seguro"
SITUACAO_COM_SEGURO = "✅ Com seguro"
SITUACAO_NAO_ELEGIVEL = "Não elegível"

# Quebras por perfil, do nivel mais alto para o mais baixo — usadas no
# card do dashboard e na sub-aba de Analiticos. Perfil fora do mapa nao
# ve quebra (fail-closed); o consultor so ve o proprio numero.
QUEBRAS_POR_PERFIL: Dict[str, list] = {
    "admin": [("Por região", ["regiao"]), ("Por loja", ["regiao", "loja"])],
    "gestor": [("Por região", ["regiao"]), ("Por loja", ["regiao", "loja"])],
    "gerente_comercial": [
        ("Por loja", ["loja"]),
        ("Por consultor", ["loja", "consultor"]),
    ],
    "supervisor": [("Por consultor", ["consultor"])],
}


def situacao_prestamista(elegivel, seguro) -> str:
    """Rotulo da proposta: seguro tem precedencia (como no IPV do BI)."""
    if int(seguro or 0) == 1:
        return SITUACAO_COM_SEGURO
    if int(elegivel or 0) == 1:
        return SITUACAO_SEM_SEGURO
    return SITUACAO_NAO_ELEGIVEL


def com_situacao(df: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Copia de `propostas` com a coluna `situacao` e `ade` (texto)."""
    if df is None or df.empty:
        return pd.DataFrame(
            columns=[*(df.columns if df is not None else []), "ade", "situacao"]
        )
    out = _somas(df)
    out["ade"] = pd.to_numeric(out["co_adesao"], errors="coerce").astype(
        "Int64"
    ).astype(str)
    out["situacao"] = [
        situacao_prestamista(e, s)
        for e, s in zip(out["qtd_elegivel"], out["qtd_seguro"])
    ]
    return out


def pendencias_prestamista(df: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Propostas elegiveis sem seguro — a lista acionavel."""
    base = com_situacao(df)
    if base.empty:
        return base
    return base[base["situacao"] == SITUACAO_SEM_SEGURO].reset_index(drop=True)


def marcar_situacao_por_ade(
    ades: pd.Series,
    propostas: Optional[pd.DataFrame],
) -> pd.Series:
    """Situacao do Prestamista para cada Nº ADE de outro frame.

    Casa por texto (o Nº ADE do dashboard e `num_proposta`, texto; a
    Adesao do arquivo e inteiro). ADE fora do arquivo fica vazia — nao
    e "nao elegivel", e "sem informacao do banco".
    """
    base = com_situacao(propostas)
    if base.empty:
        return pd.Series("", index=ades.index, dtype=object)
    mapa = dict(zip(base["ade"], base["situacao"]))
    chave = ades.astype(str).str.strip()
    return chave.map(mapa).fillna("").astype(object)
