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

DUAS PERGUNTAS DIFERENTES: FATIA E COMPARACAO
---------------------------------------------
As colunas percentuais NAO respondem a mesma coisa, e a distincao e
deliberada — cada leitura vale onde o grupo tem o tamanho certo para
ela.

**FATIA (share) — ``% da loja`` e ``% da regiao``.** Quanto da
produtividade somada do grupo e daquela pessoa::

    share_i = (R$/dia da pessoa) / (soma dos R$/dia do grupo) x 100

Somam exatamente 100% dentro do grupo, ficam no universo de 0 a 100 e
respondem "que destaque essa pessoa tem no time dela". O ponto neutro
NAO e 100%: e a fatia justa, ``100 / n_pessoas`` — 50% numa loja de
dois, 33,3% numa de tres, 25% numa de quatro; de 3,0% a 25,0% nas
regioes. A UI publica a fatia justa ao lado, porque sem ela o numero
nao se interpreta sozinho.

A fatia e da TAXA, nunca do dinheiro. Medido em 08/2026, e a diferenca
que carrega o proposito deste modulo: ILUARA BORGES CABRAL, 5 dias uteis
de 21 na HELP CASCADURA, produziu R$ 2.844/dia — a MELHOR da loja por
dia. Na fatia da taxa ela aparece com 63,2%; na fatia do dinheiro,
29,0%, atras de quem ficou o mes inteiro. As duas fatias somam 100% e
concordam quase sempre (1 loja de 48 muda de ordem interna, diferenca
mediana de 0,0 p.p.), mas divergem ate 34,2 p.p. exatamente sobre quem
teve mes parcial — que e quem esta metrica existe para nao punir.

**COMPARACAO (indice) — ``vs. media da carteira``.** Quantas vezes a
media do escopo em tela a pessoa produz por dia, em percentual. Aqui
100% E o ponto neutro, e o denominador e o MESMO do card "R$ por dia
elegivel". Cabe no nivel da carteira (122 pessoas) porque a pessoa pesa
menos de 1% do proprio benchmark; nao caberia na loja, onde ela pesa
metade dele.

POR QUE NAO INDICE NA LOJA, E POR QUE NAO FATIA NA REDE
--------------------------------------------------------
- **Indice na loja** tinha teto mecanico ``n_pessoas x 100%``: medido em
  09/2026, exatamente 100 / 200 / 300 / 400% nas lojas de 1 / 2 / 3 / 4
  pessoas. Com 48 lojas de ate 4 pessoas e 84% do time em loja de ate
  3, o mesmo desempenho virava numero diferente conforme o tamanho da
  equipe, e quem estava sozinho marcava 100% para sempre — dizendo nada.
  Na fatia, quem esta sozinho marca 100% e isso e LITERALMENTE verdade:
  ele e toda a produtividade da loja dele.
- **Fatia na rede** foi medida e descartada: com 122 pessoas, a fatia
  justa e 0,82% e o maximo observado foi 2,76%. Verdadeiro, mas nao e
  leitura de destaque — e ruido visual.
- **Leave-one-out por loja** tambem foi medido e descartado: com o
  colega no denominador o indice explode (maximo de 30.690% e
  desvio-padrao de 4.459 nas lojas de dois em 08/2026), porque um unico
  colega que quase nao vendeu vira o divisor de todo mundo.

``COL_POS_LOJA`` ("2 de 3") acompanha a fatia da loja: da a fatia justa
de graca (``100 / n``) e ordena sem depender de escala nenhuma.

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
COL_POS_LOJA = "Na loja"
# FATIA: soma 100% no grupo, ponto neutro em `100 / n`.
COL_SHARE_LOJA = "% da loja"
COL_SHARE_REGIAO = "% da regiao"
# COMPARACAO: ponto neutro em 100%. O "vs." separa as duas leituras no
# cabecalho — tres colunas em "%" com dois significados era exatamente
# a confusao que esta sub-visao veio desfazer.
COL_IDX_CARTEIRA = "vs. media da carteira"

COLUNAS_PRODUTIVIDADE = [
    COL_CONSULTOR,
    COL_LOJA,
    COL_REGIAO,
    COL_PRODUCAO,
    COL_DIAS,
    COL_PROD_DIA,
    COL_POS_LOJA,
    COL_SHARE_LOJA,
    COL_SHARE_REGIAO,
    COL_IDX_CARTEIRA,
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

# ── Situacao na variacao entre competencias ──────────
# A variacao percentual sozinha nao distingue os casos em que ela e
# AUSENTE: quem nao estava no mes anterior, quem estava com R$ 0/dia
# (percentual sobre zero nao existe) e quem esta sem denominador agora
# viravam todos o mesmo `NaN`, e a aba os relatava como "nao aparecem
# nas duas competencias". Medido em 07->08/2026: das 18 lacunas, 3
# eram gente PRESENTE nos dois meses — duas delas saindo de zero para
# R$ 918,78/dia e R$ 3.056,38/dia, as duas maiores viradas do mes,
# arquivadas como ausencia.
COL_SITUACAO = "Situacao"
SIT_SUBIU = "SUBIU"
SIT_CAIU = "CAIU"
SIT_ESTAVEL = "ESTAVEL"
SIT_SAIU_DE_ZERO = "SAIU DE ZERO"
SIT_ZERADO_NOS_DOIS = "ZERADO NOS DOIS"
SIT_AUSENTE_ANTERIOR = "AUSENTE NO ANTERIOR"
SIT_SEM_DENOMINADOR = "SEM DIA ELEGIVEL AGORA"


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


def _share_do_grupo(base: pd.DataFrame, coluna_grupo: str) -> pd.Series:
    """Fatia da pessoa na produtividade SOMADA do proprio grupo.

    ``R$/dia da pessoa / soma dos R$/dia do grupo x 100``. Soma
    exatamente 100% dentro do grupo (verificado contra o banco em
    08/2026, nas 48 lojas e nas 5 regioes) e vive no universo de 0 a
    100 — que e o pedido: um numero que se le como destaque, sem teto
    dependente do tamanho do time.

    **A fatia e da TAXA, nunca do dinheiro.** Fatia do dinheiro somaria
    100% igual, mas devolveria o viés que este modulo existe para
    remover: ILUARA BORGES CABRAL, 5 dias de 21 e a melhor da HELP
    CASCADURA por dia (R$ 2.844), sai de 63,2% para 29,0% e volta a
    parecer a terceira da loja.

    Quem nao tem dia elegivel entra com ``R$/dia`` ausente: nao soma no
    denominador (o ``sum`` ignora ``NaN``) e nao recebe fatia. Grupo com
    produtividade somada zero — loja inteira sem venda no periodo —
    devolve fatia ausente para todo mundo, nunca uma divisao por zero
    disfarcada de 0%.
    """
    taxa = base[COL_PROD_DIA]
    total = taxa.groupby(base[coluna_grupo]).transform("sum")
    return taxa / total.replace(0, np.nan) * 100.0


def _posicao_na_loja(base: pd.DataFrame) -> pd.Series:
    """Posicao por ``R$/dia`` DENTRO da propria loja, no formato "2 de 3".

    Existe porque ``% da loja`` nao e escala comparavel entre lojas: com
    a pessoa dentro do proprio benchmark, o teto do indice e
    ``n_pessoas x 100%`` — medido em 09/2026, exatamente 100 / 200 /
    300 / 400% nas lojas de 1 / 2 / 3 / 4 pessoas. Num parque de 48
    lojas de ate 4 pessoas, o mesmo desempenho relativo vira numero
    diferente conforme o tamanho da equipe, e ordenar a rede por esse
    percentual ordena parcialmente por tamanho de time.

    A posicao responde a MESMA pergunta ("como estou entre os meus")
    sem teto e sem depender do tamanho: "1 de 2" e "1 de 4" dizem a
    mesma coisa sobre o topo da propria loja.

    Empate divide a posicao (``method="min"``): dois primeiros de tres
    aparecem os dois como "1 de 3". Linha sem dia elegivel fica em
    BRANCO — sem denominador nao ha produtividade, e portanto nao ha
    posicao a atribuir.
    """
    posicao = pd.Series("", index=base.index, dtype=object)
    com_dias = base[COL_DIAS] > 0
    if not com_dias.any():
        return posicao

    elegiveis = base.loc[com_dias]
    grupo = elegiveis.groupby(COL_LOJA)[COL_PROD_DIA]
    ordem = grupo.rank(ascending=False, method="min").astype(int)
    total = grupo.transform("size").astype(int)
    posicao.loc[com_dias] = ordem.astype(str) + " de " + total.astype(str)
    return posicao


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


def _benchmark_carteira(df_prod: pd.DataFrame) -> float:
    """``sum(producao) / sum(dias)`` do escopo inteiro em tela.

    ``NaN`` quando o escopo nao tem dia elegivel ou nao vendeu nada: o
    indice devolve ausente em vez de dividir por zero. Mesma regra dos
    demais benchmarks — linha sem vinculo fica fora dos dois lados.
    """
    com_dias = df_prod[df_prod[COL_DIAS] > 0]
    dias = float(com_dias[COL_DIAS].sum())
    producao = float(com_dias[COL_PRODUCAO].sum())
    if dias <= 0 or producao <= 0:
        return np.nan
    return producao / dias


def produtividade_carteira(df_prod: pd.DataFrame) -> Dict[str, float]:
    """Totais da carteira no escopo ja recortado.

    ``produtividade`` e a razao das somas do escopo inteiro — o mesmo
    criterio dos benchmarks, para o card do topo e a tabela contarem a
    mesma historia.

    ``dias`` e a soma dos dias de vinculo de TODO o escopo: sao
    dias-colaborador (homem-dia), nao dias de calendario. Sozinho ele
    nao e leitura de KPI — 2.352 num mes de 21 dias uteis so confunde
    quem le. Quem responde "quanto de mes cada pessoa teve" e
    ``dias_por_colaborador`` (a media do escopo), que a UI mostra
    contra o DU da competencia; o total fica disponivel como base
    auditavel do ``produtividade``.
    """
    if df_prod.empty:
        return {
            "producao": 0.0,
            "dias": 0,
            "produtividade": 0.0,
            "dias_por_colaborador": 0.0,
            "colaboradores": 0,
            "sem_vinculo": 0,
            "sem_producao": 0,
        }

    com_dias = df_prod[df_prod[COL_DIAS] > 0]
    producao = float(com_dias[COL_PRODUCAO].sum())
    dias = int(com_dias[COL_DIAS].sum())
    colaboradores = int(len(com_dias))
    return {
        "producao": producao,
        "dias": dias,
        "produtividade": producao / dias if dias > 0 else 0.0,
        "dias_por_colaborador": (
            dias / colaboradores if colaboradores > 0 else 0.0
        ),
        "colaboradores": colaboradores,
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

        ``% da loja`` e ``% da regiao`` sao FATIAS (somam 100% no
        grupo, neutro em ``100 / n``); ``vs. media da carteira`` e
        COMPARACAO (neutro em 100%). Ver a secao "Duas perguntas
        diferentes" no topo do modulo.
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

    # FATIA nos grupos pequenos: soma 100% e o neutro e `100 / n`.
    base[COL_SHARE_LOJA] = _share_do_grupo(base, COL_LOJA)
    base[COL_SHARE_REGIAO] = _share_do_grupo(base, COL_REGIAO)
    # COMPARACAO no grupo grande: aqui o neutro E 100%, porque a pessoa
    # pesa menos de 1% do proprio benchmark. Mesmo denominador do card
    # "R$ por dia elegivel", de proposito — os dois numeros precisam
    # contar a mesma historia.
    base[COL_IDX_CARTEIRA] = (
        base[COL_PROD_DIA]
        / _benchmark_carteira(base)
        * 100.0
    )
    base[COL_POS_LOJA] = _posicao_na_loja(base)

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
        ``[Consultor, R$/dia elegivel, Anterior, Variacao %, Situacao]``.
        So compara competencias CONSECUTIVAS: se a pessoa nao aparece no
        mes anterior (entrou depois, saiu e voltou, ou o mes nao foi
        carregado), a variacao e ``NaN`` — lacuna nao e queda de 100%.

        ``Situacao`` existe porque ``Variacao %`` ausente tem QUATRO
        causas diferentes e quem le precisa saber qual: nao estava no
        mes anterior, estava com R$ 0/dia (nao ha percentual sobre
        zero), seguiu zerado nos dois, ou esta sem dia elegivel agora.
        Contar tudo como "nao aparece nas duas" transformava a maior
        virada do mes — sair de zero — em ausencia.
    """
    cols = [
        COL_CONSULTOR, COL_PROD_DIA, "Anterior", "Variacao %", COL_SITUACAO,
    ]
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
    # A ordem importa: os casos sem percentual sao testados ANTES de
    # olhar o sinal da variacao, que e `NaN` em todos eles.
    saida[COL_SITUACAO] = np.select(
        [
            saida[COL_PROD_DIA].isna(),
            saida["Anterior"].isna(),
            (saida["Anterior"] == 0) & (saida[COL_PROD_DIA] > 0),
            (saida["Anterior"] == 0) & (saida[COL_PROD_DIA] == 0),
            saida["Variacao %"] > 0,
            saida["Variacao %"] < 0,
        ],
        [
            SIT_SEM_DENOMINADOR,
            SIT_AUSENTE_ANTERIOR,
            SIT_SAIU_DE_ZERO,
            SIT_ZERADO_NOS_DOIS,
            SIT_SUBIU,
            SIT_CAIU,
        ],
        default=SIT_ESTAVEL,
    )
    return saida[cols].reset_index(drop=True)
