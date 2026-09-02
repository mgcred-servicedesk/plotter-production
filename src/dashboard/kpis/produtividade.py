"""
Produtividade individual por dia elegivel.

Responde a pergunta que nenhuma superficie do dashboard respondia:
**quanto cada colaborador produz por dia de vinculo**, e nao apenas
quanto produziu no mes. Sem esse denominador, quem entrou no dia 20
aparece como mau vendedor ao lado de quem ficou o mes inteiro, e a
unica leitura possivel era o valor absoluto.

    produtividade = producao paga / dias uteis elegiveis no vinculo

A BASE E DE VINCULO, NAO DE PRESENCA
------------------------------------
``DIAS_ELEGIVEIS`` (``carregar_vinculos_consultores``) conta dias uteis
em que a pessoa tinha vinculo com a loja. **Ferias, faltas e
afastamentos nao sao descontados** — o ledger ``consultor_afastamento``
tem cobertura parcial e nao e consultado aqui. Toda linha carrega
``BASE_DIAS = ELIGIBLE_LINK_DAYS`` e ``COBERTURA_AFASTAMENTO = NONE``
justamente para que ninguem leia o numero como presenca real.

Consequencia pratica, e o motivo do aviso permanente na aba: quem
tirou ferias aparece com produtividade baixa sem ter trabalhado menos
por dia. E leitura exploratoria e de conversa com o time — nao e
insumo de decisao de RH.

POPULACAO
---------
A mesma dos dois lados da divisao, que e a regra que a migration 096 e
o progress de 2026-08-31 firmaram: fora supervisor (pela ancora da
competencia) e fora backoffice/VAI E VEM. O numerador daqui e o
analogo por pessoa do ``producao_consultores`` de ``kpis/gerais.py`` e
do ``paidByConsultants`` do Caderno.

BENCHMARK POR RAZAO DAS SOMAS
-----------------------------
Loja, regiao e carteira usam ``sum(producao) / sum(dias)``, nunca a
media simples das produtividades individuais. Media de medias daria o
mesmo peso a quem teve 2 dias e a quem teve 23.

PRODUCAO SEM VINCULO
--------------------
Contrato pago de quem o ledger nao conhece na competencia (desligado
antigo, cadastro sem janela) fica com ``DIAS_ELEGIVEIS = 0``. Nesse
caso a produtividade e **ausente**, nunca zero e nunca dividida por
outro denominador — ``linhas_sem_vinculo`` isola essas pessoas para a
UI mostrar o diagnostico em vez de esconder o furo.
"""
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from src.dashboard.kpis.gerais import (
    excluir_lojas_backoffice,
    excluir_supervisores,
)
from src.dashboard.kpis.rankings import _norm_nome

# ── Colunas da tabela de produtividade ───────────────
COL_CONSULTOR = "Consultor"
COL_LOJA = "Loja"
COL_REGIAO = "Regiao"
COL_PRODUCAO = "Producao paga"
COL_DIAS = "Dias elegiveis"
COL_PROD_DIA = "R$/dia elegivel"
COL_IDX_LOJA = "% da loja"
COL_IDX_REGIAO = "% da regiao"

COLUNAS_PRODUTIVIDADE = [
    COL_CONSULTOR,
    COL_LOJA,
    COL_REGIAO,
    COL_PRODUCAO,
    COL_DIAS,
    COL_PROD_DIA,
    COL_IDX_LOJA,
    COL_IDX_REGIAO,
]

# ── Colunas da serie temporal ────────────────────────
COL_ANO = "Ano"
COL_MES = "Mes"
COL_COMPETENCIA = "Competencia"

COLUNAS_SERIE = [
    COL_ANO,
    COL_MES,
    COL_COMPETENCIA,
    COL_CONSULTOR,
    COL_LOJA,
    COL_PRODUCAO,
    COL_DIAS,
    COL_PROD_DIA,
]


def _competencia(ano: int, mes: int) -> str:
    """Rotulo ordenavel da competencia (``2026-07``)."""
    return f"{int(ano):04d}-{int(mes):02d}"


def _sem_supervisores(
    df: pd.DataFrame,
    df_supervisores: Optional[pd.DataFrame],
) -> pd.DataFrame:
    """``excluir_supervisores`` mais o casamento por nome NORMALIZADO.

    ``excluir_supervisores`` (``kpis/gerais.py``) compara as grafias
    exatas (``isin``). Medido no banco em 2026-08-31: ha supervisora
    gravada em ``supervisor_vigencia`` como "DJANE MARIA PEREIRA DOS
    SANTOS" cuja producao chega como "Djane Maria Pereira dos Santos" —
    o ``isin`` nao casa e ela atravessa o corte.

    Aqui isso nao pode passar: o denominador (``consultor_vigencia``)
    exclui supervisor pela chave normalizada, entao um supervisor que
    escapasse do numerador viraria producao sem vinculo — um furo de
    ledger inventado por uma diferenca de caixa.

    O corte compartilhado continua sendo chamado (fonte da regra); a
    normalizacao e uma rede sobre ele. Se ``excluir_supervisores`` for
    corrigido na origem, esta rede vira no-op — nunca divergencia.
    """
    base = excluir_supervisores(df, df_supervisores)
    if (
        df_supervisores is None
        or df_supervisores.empty
        or "SUPERVISOR" not in df_supervisores.columns
        or base.empty
        or "CONSULTOR" not in base.columns
    ):
        return base
    chaves = {_norm_nome(n) for n in df_supervisores["SUPERVISOR"].fillna("")}
    return base[~base["CONSULTOR"].map(_norm_nome).isin(chaves)].copy()


def _producao_por_consultor(
    df: pd.DataFrame,
    df_supervisores: Optional[pd.DataFrame],
) -> pd.Series:
    """Producao paga por chave normalizada de consultor.

    Aplica os MESMOS dois cortes de ``producao_consultores``
    (``kpis/gerais.py``): fora supervisor da competencia, fora
    backoffice. E o numerador que casa com o denominador de vinculos —
    dividir populacoes diferentes foi exatamente o defeito que a 096
    corrigiu no Caderno e o progress de 2026-08-31 corrigiu aqui.
    """
    if df is None or df.empty:
        return pd.Series(dtype=float)
    if not {"CONSULTOR", "VALOR"}.issubset(df.columns):
        return pd.Series(dtype=float)

    df_cons = excluir_lojas_backoffice(
        _sem_supervisores(df, df_supervisores)
    )
    if df_cons.empty:
        return pd.Series(dtype=float)

    chaves = df_cons["CONSULTOR"].map(_norm_nome)
    valores = pd.to_numeric(df_cons["VALOR"], errors="coerce").fillna(0.0)
    return valores.groupby(chaves).sum()


def _esqueleto_vinculos(df_vinculos: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por pessoa: dias somados e loja de MAIOR permanencia.

    A pessoa transferida no meio do mes tem dois segmentos no ledger.
    Os dias somam (janelas nao se sobrepoem — 087, check 4) e a
    identificacao vai para a loja onde ela passou mais dias uteis, com
    o nome da loja como desempate para nao depender da ordem das
    linhas.

    A mesma pessoa continua com UM denominador: a leitura por loja
    soma dias e producao pela loja de identificacao, e numerador e
    denominador ficam atribuidos pela mesma regra. Atribuir dias por
    segmento e dinheiro por loja de identificacao criaria uma loja com
    dias de uma pessoa e producao de outra.
    """
    cols = ["_key", COL_CONSULTOR, COL_LOJA, COL_REGIAO, COL_DIAS]
    if df_vinculos is None or df_vinculos.empty:
        return pd.DataFrame(columns=cols)
    if not {"CONSULTOR", "LOJA", "DIAS_ELEGIVEIS"}.issubset(
        df_vinculos.columns
    ):
        return pd.DataFrame(columns=cols)

    vin = df_vinculos.copy()
    vin["_key"] = vin["CONSULTOR"].map(_norm_nome)
    vin[COL_DIAS] = pd.to_numeric(
        vin["DIAS_ELEGIVEIS"], errors="coerce"
    ).fillna(0).astype(int)
    if "REGIAO" not in vin.columns:
        vin["REGIAO"] = ""

    dias = vin.groupby("_key")[COL_DIAS].sum()
    principal = (
        vin.sort_values([COL_DIAS, "LOJA"], ascending=[False, True])
        .drop_duplicates(subset=["_key"])
        .set_index("_key")
    )

    base = pd.DataFrame(
        {
            "_key": dias.index,
            COL_CONSULTOR: principal.loc[dias.index, "CONSULTOR"].to_numpy(),
            COL_LOJA: principal.loc[dias.index, "LOJA"].to_numpy(),
            COL_REGIAO: (
                principal.loc[dias.index, "REGIAO"].fillna("").to_numpy()
            ),
            COL_DIAS: dias.to_numpy(),
        }
    )
    return base.reset_index(drop=True)


def _identificacao_da_producao(
    df: pd.DataFrame,
    df_supervisores: Optional[pd.DataFrame],
    chaves: set,
) -> pd.DataFrame:
    """Loja/regiao de quem produziu e o ledger nao conhece.

    Entra com ``DIAS_ELEGIVEIS = 0`` — nunca com um denominador
    emprestado. Identificacao pela loja de MAIOR producao, como em
    ``kpis/gestao.py``.
    """
    cols = ["_key", COL_CONSULTOR, COL_LOJA, COL_REGIAO, COL_DIAS]
    if df is None or df.empty or "CONSULTOR" not in df.columns:
        return pd.DataFrame(columns=cols)

    df_cons = excluir_lojas_backoffice(
        _sem_supervisores(df, df_supervisores)
    )
    if df_cons.empty:
        return pd.DataFrame(columns=cols)

    d = df_cons.copy()
    d["_key"] = d["CONSULTOR"].map(_norm_nome)
    d = d[~d["_key"].isin(chaves)]
    if d.empty:
        return pd.DataFrame(columns=cols)

    d["_valor"] = pd.to_numeric(d.get("VALOR"), errors="coerce").fillna(0.0)
    d["_loja"] = d["LOJA"].fillna("") if "LOJA" in d.columns else ""
    d["_regiao"] = d["REGIAO"].fillna("") if "REGIAO" in d.columns else ""

    por_loja = (
        d.groupby(["_key", "_loja", "_regiao"], as_index=False)["_valor"]
        .sum()
        .sort_values("_valor", ascending=False)
        .drop_duplicates(subset=["_key"])
    )
    nomes = d.drop_duplicates(subset=["_key"]).set_index("_key")["CONSULTOR"]

    return pd.DataFrame(
        {
            "_key": por_loja["_key"].to_numpy(),
            COL_CONSULTOR: (
                nomes.loc[por_loja["_key"]].to_numpy()
            ),
            COL_LOJA: por_loja["_loja"].to_numpy(),
            COL_REGIAO: por_loja["_regiao"].to_numpy(),
            COL_DIAS: 0,
        }
    ).reset_index(drop=True)


def benchmark_por(
    df_prod: pd.DataFrame,
    coluna: str,
) -> pd.Series:
    """Produtividade de cada grupo pela RAZAO DAS SOMAS.

    ``sum(producao) / sum(dias)`` do grupo — nunca a media das
    produtividades individuais, que daria o mesmo peso a quem teve 2
    dias e a quem teve 23.

    Linhas sem vinculo (``dias = 0``) ficam fora dos DOIS lados da
    razao: entrariam com producao e sem denominador, inflando o
    benchmark do grupo contra o qual as pessoas sao comparadas.
    """
    if df_prod.empty or coluna not in df_prod.columns:
        return pd.Series(dtype=float)

    com_dias = df_prod[df_prod[COL_DIAS] > 0]
    if com_dias.empty:
        return pd.Series(dtype=float)

    somas = com_dias.groupby(coluna)[[COL_PRODUCAO, COL_DIAS]].sum()
    return somas[COL_PRODUCAO] / somas[COL_DIAS].where(somas[COL_DIAS] > 0)


def produtividade_carteira(df_prod: pd.DataFrame) -> Dict[str, float]:
    """Totais da carteira no escopo ja recortado.

    ``produtividade`` e a razao das somas do escopo inteiro — o mesmo
    criterio dos benchmarks, para o card do topo e a tabela contarem a
    mesma historia.
    """
    if df_prod.empty:
        return {
            "producao": 0.0,
            "dias": 0,
            "produtividade": 0.0,
            "colaboradores": 0,
            "sem_vinculo": 0,
            "sem_producao": 0,
        }

    com_dias = df_prod[df_prod[COL_DIAS] > 0]
    producao = float(com_dias[COL_PRODUCAO].sum())
    dias = int(com_dias[COL_DIAS].sum())
    return {
        "producao": producao,
        "dias": dias,
        "produtividade": producao / dias if dias > 0 else 0.0,
        "colaboradores": int(len(com_dias)),
        "sem_vinculo": int((df_prod[COL_DIAS] == 0).sum()),
        "sem_producao": int(
            ((df_prod[COL_DIAS] > 0) & (df_prod[COL_PRODUCAO] <= 0)).sum()
        ),
    }


def produtividade_por_consultor(
    df: pd.DataFrame,
    df_vinculos: pd.DataFrame,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Produtividade por dia elegivel, uma linha por colaborador.

    Args:
        df: contratos pagos do periodo, JA recortados por RLS e pelos
            filtros da sidebar (feito em ``app.py``).
        df_vinculos: saida de ``carregar_vinculos_consultores``, pelo
            MESMO recorte de RLS — o escopo sai do filtro, nunca da
            producao.
        df_supervisores: supervisores vigentes na competencia, para o
            corte de populacao do numerador.

    Returns:
        ``COLUNAS_PRODUTIVIDADE``. O esqueleto nasce dos vinculos:
        colaborador elegivel que nao vendeu nada permanece na tabela
        com producao 0 e produtividade 0 — some-lo faria a media da
        loja subir justamente quando mais gente deixou de vender.
        Produtividade e ``NaN`` (nunca 0) para quem produziu sem
        vinculo no ledger.
    """
    esqueleto = _esqueleto_vinculos(df_vinculos)
    producao = _producao_por_consultor(df, df_supervisores)
    orfas = _identificacao_da_producao(
        df, df_supervisores, set(esqueleto["_key"])
    )

    base = pd.concat([esqueleto, orfas], ignore_index=True)
    if base.empty:
        return pd.DataFrame(columns=COLUNAS_PRODUTIVIDADE)

    base[COL_PRODUCAO] = (
        base["_key"].map(producao).fillna(0.0).astype(float)
    )
    base[COL_DIAS] = base[COL_DIAS].astype(int)

    # Sem vinculo, sem produtividade: NaN preserva a pergunta em
    # aberto. Zero diria "produz nada por dia", que e uma afirmacao
    # sobre a pessoa, quando o furo esta no ledger.
    base[COL_PROD_DIA] = np.where(
        base[COL_DIAS] > 0,
        base[COL_PRODUCAO] / base[COL_DIAS].where(base[COL_DIAS] > 0),
        np.nan,
    )

    bench_loja = benchmark_por(base, COL_LOJA)
    bench_regiao = benchmark_por(base, COL_REGIAO)
    base[COL_IDX_LOJA] = (
        base[COL_PROD_DIA]
        / base[COL_LOJA].map(bench_loja).replace(0, np.nan)
        * 100.0
    )
    base[COL_IDX_REGIAO] = (
        base[COL_PROD_DIA]
        / base[COL_REGIAO].map(bench_regiao).replace(0, np.nan)
        * 100.0
    )

    saida = base[COLUNAS_PRODUTIVIDADE].sort_values(
        [COL_PROD_DIA, COL_PRODUCAO], ascending=[False, False]
    )
    return saida.reset_index(drop=True)


def linhas_sem_vinculo(df_prod: pd.DataFrame) -> pd.DataFrame:
    """Quem produziu e o ledger nao conhece na competencia.

    Diagnostico para a UI: sao contratos pagos sem janela de vinculo
    correspondente. Nao entram em nenhum benchmark e nao recebem
    denominador emprestado — aparecem em separado, com o valor pago,
    para alguem corrigir o ledger.
    """
    if df_prod.empty:
        return df_prod
    fora = df_prod[
        (df_prod[COL_DIAS] == 0) & (df_prod[COL_PRODUCAO] > 0)
    ]
    return fora.reset_index(drop=True)


def serie_por_consultor(
    frames: Dict[Tuple[int, int], pd.DataFrame],
) -> pd.DataFrame:
    """Empilha produtividades de varias competencias numa serie longa.

    Args:
        frames: ``{(ano, mes): produtividade_por_consultor(...)}``.

    Returns:
        ``COLUNAS_SERIE``, ordenada por consultor e competencia.
        Competencia ausente e LACUNA: nao vira linha zerada, para a
        variacao saber que nao ha comparacao possivel.
    """
    partes = []
    for (ano, mes), frame in sorted(frames.items()):
        if frame is None or frame.empty:
            continue
        parte = frame[
            [COL_CONSULTOR, COL_LOJA, COL_PRODUCAO, COL_DIAS, COL_PROD_DIA]
        ].copy()
        parte[COL_ANO] = int(ano)
        parte[COL_MES] = int(mes)
        parte[COL_COMPETENCIA] = _competencia(ano, mes)
        partes.append(parte)

    if not partes:
        return pd.DataFrame(columns=COLUNAS_SERIE)

    serie = pd.concat(partes, ignore_index=True)[COLUNAS_SERIE]
    return serie.sort_values(
        [COL_CONSULTOR, COL_COMPETENCIA]
    ).reset_index(drop=True)


def variacao_ultima_competencia(serie: pd.DataFrame) -> pd.DataFrame:
    """Variacao da produtividade entre as duas ultimas competencias.

    Returns:
        ``[Consultor, R$/dia elegivel, Anterior, Variacao %]``. So
        compara competencias CONSECUTIVAS: se a pessoa nao aparece no
        mes anterior (entrou depois, saiu e voltou, ou o mes nao foi
        carregado), a variacao e ``NaN`` — lacuna nao e queda de 100%.
    """
    cols = [COL_CONSULTOR, COL_PROD_DIA, "Anterior", "Variacao %"]
    if serie.empty or COL_COMPETENCIA not in serie.columns:
        return pd.DataFrame(columns=cols)

    competencias = sorted(serie[COL_COMPETENCIA].unique())
    if len(competencias) < 2:
        return pd.DataFrame(columns=cols)

    atual = serie[serie[COL_COMPETENCIA] == competencias[-1]]
    anterior = serie[serie[COL_COMPETENCIA] == competencias[-2]].set_index(
        COL_CONSULTOR
    )[COL_PROD_DIA]

    saida = atual[[COL_CONSULTOR, COL_PROD_DIA]].copy()
    saida["Anterior"] = saida[COL_CONSULTOR].map(anterior)
    saida["Variacao %"] = (
        (saida[COL_PROD_DIA] / saida["Anterior"].replace(0, np.nan) - 1.0)
        * 100.0
    )
    return saida.reset_index(drop=True)
