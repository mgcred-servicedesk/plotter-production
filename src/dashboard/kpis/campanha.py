"""Regras de campanha — registro e apuracao.

Regras **de campanha**, nao de producao. Moram separadas de
``kpis/gerais.py`` de proposito: recorte de produtos, meta e criterio de
desempate valem para a campanha que os declarou e para mais nada. Mudar
qualquer coisa aqui nao pode mexer no numero do dashboard de vendas.

O modulo e generico e o registro :data:`CAMPANHAS` e a fonte unica: uma
campanha nova e uma entrada nova, sem tocar em funcao nenhuma. Toda
funcao de apuracao recebe a :class:`Campanha` como parametro — nao ha
constante de campanha solta no modulo, justamente para que a segunda
campanha nao precise reabrir a primeira.

Duas decisoes do usuario que o codigo nao teria como inferir, tomadas
para a Semestral 2026-H2 e registradas na propria entrada dela:

1. **Super Conta conta como CNC** — na producao e no desempate. O
   projeto ja trata Super Conta como subtipo de CNC
   (``business-rules.md``), e a campanha seguiu a mesma leitura.
2. **A apuracao sempre reflete a base atual.** Contrato pago em julho e
   cancelado depois some da base no proximo import e sai da campanha
   sozinho — por isso nao existe aqui nenhuma regra de exclusao de
   cancelado. O efeito colateral aceito e que ranking ja divulgado pode
   mudar; nao ha snapshot congelado.
"""

from dataclasses import dataclass
from datetime import date
from typing import Mapping, Optional

import pandas as pd

from src.shared.texto import normalizar_nome


# ══════════════════════════════════════════════════════
# Definicao de campanha
# ══════════════════════════════════════════════════════


@dataclass(frozen=True)
class Condicao:
    """Um degrau de premiacao.

    Os degraus sao **cumulativos e ordenados**: o enesimo so vale se
    todos os anteriores tambem foram atingidos. Bater o CLT sem bater o
    CNC nao promove ninguem — e a regra que o usuario definiu em
    09/2026, e o motivo de :func:`contemplacao` parar no primeiro degrau
    que falha em vez de contar os atingidos.

    Campos:
        rotulo: nome exibido do degrau.
        familia: familia de ``Campanha.familias`` cuja producao e
            medida. ``None`` mede a producao **total** da campanha
            (a meta global).
        meta: alvo em R$ de producao (``VALOR``).
        consultores: quantos consultores passam a ser contemplados
            quando este degrau (e os anteriores) sao atingidos.
        lojas: idem, para o ranking de lojas/supervisores.
    """

    rotulo: str
    familia: Optional[str]
    meta: float
    consultores: int
    lojas: int


@dataclass(frozen=True)
class Campanha:
    """Uma campanha e o conjunto fechado das suas regras.

    ``frozen`` porque campanha em curso nao muda de regra no meio: se
    mudar, e outra campanha (ou uma correcao deliberada no registro,
    versionada pelo git).

    Campos:
        slug: identificador estavel. E a chave de ``session_state`` e o
            nome da pasta de assets — mudar quebra as duas coisas.
        rotulo: nome exibido.
        inicio, fim: janela de PAGAMENTO, limites inclusivos.
        meta_valor: meta em R$ de producao (``VALOR``), nao em pontos.
        familias: rotulo da familia -> codigos de ``categorias_produto``.
            A ordem e a de exibicao. E o unico lugar que decide
            elegibilidade.
        familia_desempate: qual familia desempata o ranking. Precisa
            existir em ``familias``.
        excluidas_notaveis: codigos que alguem esperaria ver e nao
            estao — exibidos no rodape para quem audita. Documentacao,
            nao regra: a regra e ``familias``.
        condicoes: degraus de premiacao, **em ordem**. Ver
            :class:`Condicao` e :func:`contemplacao`.
    """

    slug: str
    rotulo: str
    inicio: date
    fim: date
    meta_valor: float
    familias: Mapping[str, tuple[str, ...]]
    familia_desempate: str
    excluidas_notaveis: tuple[str, ...] = ()
    descricao: str = ""
    condicoes: tuple[Condicao, ...] = ()

    def __post_init__(self) -> None:
        # Desempate apontando para familia inexistente daria ranking
        # sem criterio de desempate e ninguem perceberia — so empates
        # ficariam com a ordem arbitraria do sort.
        if self.familia_desempate not in self.familias:
            raise ValueError(
                f"Campanha {self.slug!r}: familia_desempate "
                f"{self.familia_desempate!r} nao esta em familias "
                f"({list(self.familias)})."
            )
        if self.fim < self.inicio:
            raise ValueError(
                f"Campanha {self.slug!r}: fim anterior ao inicio."
            )
        for cond in self.condicoes:
            # Condicao apontando para familia inexistente mediria
            # producao zero e nunca seria atingida — falharia calada.
            if cond.familia is not None and cond.familia not in self.familias:
                raise ValueError(
                    f"Campanha {self.slug!r}: condicao {cond.rotulo!r} "
                    f"referencia familia {cond.familia!r}, que nao esta "
                    f"em familias ({list(self.familias)})."
                )
        # Os degraus sao cumulativos: um degrau que contemplasse MENOS
        # que o anterior nao teria como ser alcancado (a cascata so
        # avanca) e indicaria erro de cadastro.
        for antes, depois in zip(self.condicoes, self.condicoes[1:]):
            if (
                depois.consultores < antes.consultores
                or depois.lojas < antes.lojas
            ):
                raise ValueError(
                    f"Campanha {self.slug!r}: condicao {depois.rotulo!r} "
                    f"contempla menos que {antes.rotulo!r}. Os degraus "
                    "sao cumulativos."
                )

    @property
    def categorias_elegiveis(self) -> frozenset:
        return frozenset(
            codigo
            for codigos in self.familias.values()
            for codigo in codigos
        )

    @property
    def categorias_desempate(self) -> frozenset:
        return frozenset(self.familias[self.familia_desempate])

    def vigente_em(self, quando: date) -> bool:
        return self.inicio <= quando <= self.fim


# ══════════════════════════════════════════════════════
# Registro
# ══════════════════════════════════════════════════════

# Os codigos saem de `categorias_produto` (database/schema.sql). O mapa
# TIPO_PRODUTO -> categoria_codigo vive em
# `kpis/consolidacao.py::_TIPO_PARA_CATEGORIA` e ja foi aplicado pelo
# loader antes de chegar aqui — sem ele, ANT. DE BENEF. e CLT chegam SEM
# categoria (o ETL zera `categoria_id` quando a planilha renomeia o
# tipo; ver migration 061). Em 16/09/2026 isso era 27% dos contratos da
# janela e R$ 4,19 mi da apuracao.
SEMESTRAL_2026H2 = Campanha(
    slug="semestral-2026h2",
    rotulo="Campanha Semestral 2026 · 2º semestre",
    inicio=date(2026, 7, 1),
    fim=date(2026, 12, 31),
    meta_valor=75_000_000.0,
    familias={
        # Super Conta e subtipo de CNC — decisao do usuario, 09/2026.
        "CNC": ("CNC", "SUPER_CONTA"),
        "CLT": ("CONSIG_PRIV",),
        "Consignado": (
            "CONSIG_BMG",
            "CONSIG_ITAU",
            "CONSIG_C6",
            "PORTABILIDADE",
        ),
        "Ant. de Benef.": ("ANT_BENEF",),
        "FGTS": ("FGTS",),
    },
    familia_desempate="CNC",
    # Explicito para quem for auditar: SAQUE e SAQUE_BENEFICIO (o "saque
    # do cartao" que o usuario excluiu), alem de CARTAO/BMG_MED/
    # SEGURO_VIDA, que nao contam valor em lugar nenhum.
    #
    # CNC_13 ("CNC 13º") NAO esta elegivel: o usuario nomeou cinco
    # familias e CNC_13 e categoria propria, com
    # `grupo_meta = FGTS_ANT_BENEF_13`. Em 16/09/2026 nao havia nenhum
    # contrato CNC_13 na janela, mas 13º e produto de nov/dez — DENTRO
    # da campanha. Confirmar antes de novembro; incluir e acrescentar
    # "CNC_13" a familia CNC acima.
    excluidas_notaveis=("SAQUE", "SAQUE_BENEFICIO", "CNC_13"),
    descricao=(
        "Meta de R$ 75 milhoes em producao (valor, nao pontos) entre "
        "01/07/2026 e 31/12/2026. Ranking de consultores e de lojas "
        "por pontos; desempate pela producao de CNC."
    ),
    # Degraus de premiacao definidos pelo usuario em 09/2026.
    # CUMULATIVOS: o CLT so promove se o CNC tambem tiver sido batido,
    # e nenhum deles vale sem a meta global. Sem a global, ninguem e
    # contemplado — mesmo com CNC e CLT atingidos.
    #
    # Os valores de CNC e CLT vem da arte oficial da campanha
    # (assets/campanhas/semestral-2026h2/rodape-2.png), que quebra os
    # R$ 75 mi em 44,5 + 23 + 7,5. Confirmados pelo usuario em
    # 16/09/2026.
    #
    # O bloco de R$ 44,5 mi (Consignado + Antecipacao + FGTS) fica
    # **fora dos degraus por ora** — decisao do usuario na mesma data,
    # e "no momento" foi a palavra dele: o bloco existe na arte e pode
    # virar uma quarta condicao. Se vier, e uma linha na tupla abaixo,
    # e as tres familias precisam ser agrupadas numa so (hoje sao
    # "Consignado", "Ant. de Benef." e "FGTS" separadas, porque
    # `Condicao.familia` aponta para UMA familia de `familias`).
    condicoes=(
        Condicao("Meta global", None, 75_000_000.0, 8, 4),
        Condicao("Meta de CNC", "CNC", 23_000_000.0, 12, 6),
        Condicao("Meta de CLT", "CLT", 7_500_000.0, 16, 8),
    ),
)

# Ordem = ordem de exibicao. Campanha nova entra aqui e aparece sozinha
# no seletor da pagina; nenhuma funcao precisa mudar.
CAMPANHAS: tuple[Campanha, ...] = (SEMESTRAL_2026H2,)


def campanha_por_slug(slug: str) -> Optional[Campanha]:
    """Campanha do registro, ou ``None``. Nunca levanta."""
    for camp in CAMPANHAS:
        if camp.slug == slug:
            return camp
    return None


def campanha_padrao(hoje: Optional[date] = None) -> Optional[Campanha]:
    """A campanha a abrir por default: a vigente hoje, senao a ultima.

    "Vigente" ganha da ordem do registro para que, com duas campanhas
    cadastradas, a pagina abra na que esta rodando — nao na que terminou.
    """
    if not CAMPANHAS:
        return None
    hoje = hoje or date.today()
    for camp in CAMPANHAS:
        if camp.vigente_em(hoje):
            return camp
    return max(CAMPANHAS, key=lambda c: c.fim)


# ══════════════════════════════════════════════════════
# Recorte
# ══════════════════════════════════════════════════════


def filtrar_janela(df: pd.DataFrame, camp: Campanha) -> pd.DataFrame:
    """Recorta pela data de PAGAMENTO, limites inclusivos.

    A coluna ``DATA`` e a data de pagamento (``data_status_pagamento``)
    — a mesma que ``loaders.CAMPO_PAGAMENTO`` nomeia. A campanha e
    apurada por pagamento por decisao do usuario, e e o criterio que
    torna o conjunto de meses exato: ``contratos.periodo_id`` deriva da
    data de pagamento, entao nenhum contrato pago na janela mora fora
    dos meses dela.

    Linha sem data sai — nao da para afirmar que foi paga na janela.
    Coluna ``DATA`` ausente **nega tudo**, em vez de deixar passar: sem
    a data nao ha como afirmar elegibilidade, e a campanha e apurada
    fail-closed como o resto do projeto.

    Compara em ``Timestamp``, nao em ``.dt.date``. Dois motivos, os
    dois com sintoma real: (a) numa coluna **toda NaT** o ``.dt.date``
    devolve ``datetime64`` em vez de ``object``, e comparar com ``date``
    levanta ``TypeError`` — a aba quebrava em vez de dizer "sem dados";
    (b) o limite superior vira ``< fim + 1 dia``, entao contrato pago em
    31/12 com hora (23:00) continua dentro, que ``<= Timestamp(fim)``
    (meia-noite) descartaria.
    """
    if df.empty or "DATA" not in df.columns:
        return df.iloc[0:0].copy()

    datas = pd.to_datetime(df["DATA"], errors="coerce")
    limite = pd.Timestamp(camp.fim) + pd.Timedelta(days=1)
    dentro = (
        datas.notna()
        & (datas >= pd.Timestamp(camp.inicio))
        & (datas < limite)
    )
    return df[dentro].copy()


def filtrar_elegiveis(df: pd.DataFrame, camp: Campanha) -> pd.DataFrame:
    """Mantem so os produtos que pontuam na campanha.

    Pressupoe ``categoria_codigo`` ja reidratada pelo fallback do
    projeto. Sem isso, ANT. DE BENEF. e CLT — duas das cinco familias —
    chegam vazias e a campanha aparece ~19% menor, sem erro na tela.

    Coluna ausente **nega tudo** (fail-closed). Devolver o frame
    inteiro seria somar SAQUE e emissao na campanha — inflar a
    apuracao, que e o pior erro possivel aqui.
    """
    if df.empty or "categoria_codigo" not in df.columns:
        return df.iloc[0:0].copy()

    return df[
        df["categoria_codigo"].isin(camp.categorias_elegiveis)
    ].copy()


def preparar(df: pd.DataFrame, camp: Campanha) -> pd.DataFrame:
    """Janela + elegibilidade, na ordem. Entrada de tudo mais aqui."""
    return filtrar_elegiveis(filtrar_janela(df, camp), camp)


# ══════════════════════════════════════════════════════
# Apuracao
# ══════════════════════════════════════════════════════


def _soma(df: pd.DataFrame, coluna: str) -> float:
    if df.empty or coluna not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[coluna], errors="coerce").fillna(0).sum())


def apurar(df: pd.DataFrame, camp: Campanha) -> dict:
    """Numeros de topo da campanha.

    ``df`` deve vir de :func:`preparar`. ``valor`` e a producao
    consolidada (``VALOR``, ja com os zeramentos de ``conta_valor`` e
    emissao aplicados na consolidacao) — e o que conta para os R$ 75 mi.

    Returns:
        dict com ``valor``, ``meta``, ``atingimento`` (0-1+), ``falta``,
        ``pontos``, ``qtd``, ``valor_cnc``.
    """
    valor = _soma(df, "VALOR")
    meta = float(camp.meta_valor)
    cnc = (
        df[df["categoria_codigo"].isin(camp.categorias_desempate)]
        if not df.empty and "categoria_codigo" in df.columns
        else df
    )
    return {
        "valor": valor,
        "meta": meta,
        "atingimento": (valor / meta) if meta else 0.0,
        "falta": max(meta - valor, 0.0),
        "pontos": _soma(df, "pontos"),
        "qtd": int(len(df)),
        "valor_cnc": _soma(cnc, "VALOR"),
    }


def apurar_por_familia(
    df: pd.DataFrame,
    camp: Campanha,
    du_decorridos: int = 0,
) -> pd.DataFrame:
    """Quebra da producao pelas familias declaradas na campanha.

    Agrupa por FAMILIA (o rotulo que o usuario usou), nao por
    ``categoria_codigo`` — e como a rede le a campanha. Familia sem
    contrato aparece zerada em vez de sumir: ausencia de linha e
    ambigua entre "nao vendeu" e "regra nao pegou".
    """
    linhas = []
    for familia, codigos in camp.familias.items():
        parte = (
            df[df["categoria_codigo"].isin(codigos)]
            if not df.empty and "categoria_codigo" in df.columns
            else df.iloc[0:0]
        )
        linhas.append(
            {
                "Família": familia,
                "Valor": _soma(parte, "VALOR"),
                "Pontos": _soma(parte, "pontos"),
            }
        )

    out = pd.DataFrame(linhas)
    total = out["Valor"].sum()
    out["% do Total"] = (out["Valor"] / total * 100) if total else 0.0
    out[COLUNA_MEDIA_DU] = _media_du(out["Valor"], du_decorridos)
    return out.sort_values("Valor", ascending=False).reset_index(drop=True)


# ══════════════════════════════════════════════════════
# Condicoes de premiacao
# ══════════════════════════════════════════════════════


def valor_da_familia(df: pd.DataFrame, familia: Optional[str],
                     camp: Campanha) -> float:
    """Producao de uma familia, ou a total quando ``familia`` e ``None``."""
    if familia is None:
        return _soma(df, "VALOR")
    if df.empty or "categoria_codigo" not in df.columns:
        return 0.0
    codigos = camp.familias.get(familia, ())
    return _soma(df[df["categoria_codigo"].isin(codigos)], "VALOR")


def avaliar_condicoes(df: pd.DataFrame, camp: Campanha) -> list[dict]:
    """Estado de cada degrau, na ordem do cadastro.

    ``atingida`` olha so a meta do proprio degrau. ``liberada`` aplica a
    cascata: so e ``True`` se este degrau **e todos os anteriores**
    foram atingidos. Sao coisas diferentes e a UI precisa das duas —
    bater o CLT sem o CNC deixa ``atingida=True`` e ``liberada=False``,
    e e exatamente esse caso que a rede precisa enxergar.
    """
    linhas: list[dict] = []
    cascata_viva = True
    for cond in camp.condicoes:
        realizado = valor_da_familia(df, cond.familia, camp)
        atingida = realizado >= cond.meta
        cascata_viva = cascata_viva and atingida
        linhas.append(
            {
                "condicao": cond,
                "realizado": realizado,
                "atingida": atingida,
                "liberada": cascata_viva,
                "falta": max(cond.meta - realizado, 0.0),
                "atingimento": (
                    realizado / cond.meta if cond.meta else 0.0
                ),
            }
        )
    return linhas


COLUNA_PREMIADO = "Premiado"


def marcar_contemplados(rk: pd.DataFrame, quantos: int) -> pd.DataFrame:
    """Acrescenta ao ranking a coluna de quem seria premiado hoje.

    Corta pela POSICAO (``#``), nao pela linha: a posicao e densa, entao
    um empate exato — mesmos pontos **e** mesma producao de desempate —
    na fronteira contempla os dois. Cortar por linha escolheria um
    vencedor pela ordem que o sort deixou por acaso, que e o que a
    posicao densa existe para evitar.

    Coluna em vez de destaque visual de proposito: ela viaja no CSV
    exportado, e a lista de premiados e justamente o que sai da tela
    para virar pagamento.
    """
    out = rk.copy()
    if out.empty:
        out[COLUNA_PREMIADO] = []
        return out
    if quantos <= 0 or "#" not in out.columns:
        out[COLUNA_PREMIADO] = "—"
        return out
    out[COLUNA_PREMIADO] = out["#"].le(quantos).map({True: "Sim", False: "—"})
    return out


def contemplacao(df: pd.DataFrame, camp: Campanha) -> dict:
    """Quantos consultores e lojas seriam premiados com o dado de hoje.

    Vale o **ultimo degrau liberado** — o mais alto cuja cascata inteira
    fechou. Nenhum degrau liberado significa zero contemplados, nao o
    primeiro degrau: sem a meta global nao ha premiacao.

    Returns:
        dict com ``consultores``, ``lojas``, ``degraus`` (a avaliacao
        completa) e ``atual`` (a ``Condicao`` vigente, ou ``None``).
    """
    degraus = avaliar_condicoes(df, camp)
    liberados = [linha for linha in degraus if linha["liberada"]]
    atual = liberados[-1]["condicao"] if liberados else None
    return {
        "consultores": atual.consultores if atual else 0,
        "lojas": atual.lojas if atual else 0,
        "degraus": degraus,
        "atual": atual,
    }


# ══════════════════════════════════════════════════════
# Rankings
# ══════════════════════════════════════════════════════


def rotulo_desempate(camp: Campanha) -> str:
    """Nome da coluna de desempate — segue a familia da campanha.

    Diz "pts" porque o desempate e em PONTOS, nao em valor: o ranking
    inteiro e em pontos, e um desempate noutra unidade seria uma
    segunda moeda escondida na mesma tabela.
    """
    return f"{camp.familia_desempate} (pts, desempate)"


COLUNA_LOJA_CONSULTOR = "Loja"
# Sufixo de quem produziu em mais de uma loja na janela (`_loja_do_consultor`).
MARCA_MULTIPLAS_LOJAS = " *"
COLUNA_MEDIA_DU = "Média/DU"


def _media_du(valores, du_decorridos: int):
    """Producao por dia util decorrido.

    O denominador e o **mesmo para todas as linhas**: os DU decorridos
    da campanha. E o que torna as linhas comparaveis entre si e com o
    card de Media/DU do topo.

    Consequencia aceita: quem foi admitido no meio da janela aparece
    diluido, porque nao trabalhou os 55 DU. O projeto tem a maquinaria
    de vigencia para ponderar isso (`consultor_vigencia`,
    `fn_headcount_ponderado`), mas ela nao entra aqui — a coluna e
    leitura de contexto, e o ranking e ordenado por PONTOS, nao por
    media/DU, entao a diluicao nao muda posicao nem premiacao.

    ``du_decorridos = 0`` (campanha nao comecou) devolve zero — nao ha
    media sem dia util decorrido, e nesse momento a producao tambem e
    zero.
    """
    if not du_decorridos:
        return valores * 0.0
    return valores / du_decorridos


def _loja_do_consultor(df: pd.DataFrame, coluna: str) -> dict:
    """Loja de cada consultor: a do contrato pago MAIS RECENTE.

    Numa janela de seis meses a pessoa pode ter sido transferida — o
    projeto agrega consultor por NOME justamente para nao fragmentar a
    producao de quem mudou de loja (ver `rls.md`). A coluna e contexto
    de leitura ("de onde e essa pessoa"), entao vale a loja atual, que e
    a do ultimo pagamento.

    Quem produziu em mais de uma loja na janela sai marcado com ``*`` —
    sem isso a coluna afirmaria uma lotacao unica que nao existiu, e o
    supervisor da loja anterior nao entenderia por que a producao dele
    aparece sob outra loja. A producao em si nunca se move: o ranking de
    LOJA usa `contratos.loja_id`, que e por contrato.
    """
    if "LOJA" not in df.columns or "DATA" not in df.columns:
        return {}

    base = df[[coluna, "LOJA", "DATA"]].dropna(subset=[coluna, "LOJA"]).copy()
    if base.empty:
        return {}
    base["DATA"] = pd.to_datetime(base["DATA"], errors="coerce")

    # Ultima loja por data de pagamento; NaT vai para o fim do sort.
    recentes = (
        base.sort_values("DATA", na_position="first")
        .groupby(coluna)["LOJA"]
        .last()
    )
    multiplas = base.groupby(coluna)["LOJA"].nunique()
    return {
        nome: (
            f"{loja}{MARCA_MULTIPLAS_LOJAS}"
            if multiplas.get(nome, 1) > 1
            else loja
        )
        for nome, loja in recentes.items()
    }


def excluir_desligados(
    df: pd.DataFrame, desligados
) -> tuple[pd.DataFrame, int]:
    """Tira do frame os contratos de consultores desligados.

    Para o ranking de CONSULTORES: aplicado ANTES do `ranking`, as
    posicoes sao recalculadas e desligado nao ocupa vaga de premiacao.
    O ranking de LOJAS nao passa por aqui — a producao foi feita na
    loja e continua dela.

    Match por ``normalizar_nome`` (cadastro e contratos divergem na
    grafia). Devolve tambem QUANTAS pessoas sairam, para a tela dizer
    — filtro que some com gente sem avisar parece bug.
    """
    if df.empty or "CONSULTOR" not in df.columns or not len(desligados):
        return df.copy(), 0
    chaves = set(normalizar_nome(pd.Series(list(desligados), dtype=object)))
    nomes = normalizar_nome(df["CONSULTOR"])
    fora = nomes.isin(chaves)
    return df[~fora].copy(), int(nomes[fora].nunique())


def ranking(
    df: pd.DataFrame,
    coluna: str,
    camp: Campanha,
    top: Optional[int] = None,
    com_loja: bool = False,
    du_decorridos: int = 0,
) -> pd.DataFrame:
    """Ranking por PONTOS, desempate pela familia declarada da campanha.

    ``coluna`` e ``CONSULTOR`` ou ``LOJA``. O desempate entra como
    segunda chave de ordenacao — e o criterio declarado da campanha, e
    fica materializado numa coluna visivel (ex.: "CNC (pts, desempate)")
    para que quem contesta a posicao veja o numero que a decidiu.
    Desempate em **pontos**, mesma unidade do ranking.

    A posicao e ``1..n`` densa: empate real nos DOIS criterios divide a
    mesma posicao, em vez de escolher um vencedor pela ordem alfabetica
    que o sort deixou por acaso.

    ``com_loja`` acrescenta a loja do consultor. Ver
    :func:`_loja_do_consultor` para o criterio — numa janela de seis
    meses a pessoa pode ter mudado de loja.

    ``du_decorridos`` alimenta a coluna Media/DU, que substituiu a
    contagem de contratos: quantidade nao diz nada numa campanha
    apurada em VALOR. Ver :func:`_media_du`.
    """
    col_desempate = rotulo_desempate(camp)
    colunas_vazias = [
        coluna, "Pontos", "Valor", col_desempate, COLUNA_MEDIA_DU
    ]
    if com_loja:
        colunas_vazias.insert(1, COLUNA_LOJA_CONSULTOR)
    vazio = pd.DataFrame(columns=colunas_vazias)
    if df.empty or coluna not in df.columns:
        return vazio

    base = df.copy()
    # Desempate em PONTOS da familia (nao em valor): o ranking e em
    # pontos, e misturar unidades na mesma tabela esconderia o criterio.
    base["_desempate"] = base["pontos"].where(
        base["categoria_codigo"].isin(camp.categorias_desempate), 0.0
    )

    out = (
        base.groupby(coluna, dropna=False)
        .agg(
            Pontos=("pontos", "sum"),
            Valor=("VALOR", "sum"),
            **{col_desempate: ("_desempate", "sum")},
        )
        .reset_index()
    )
    if out.empty:
        return vazio

    out[COLUNA_MEDIA_DU] = _media_du(out["Valor"], du_decorridos)

    if com_loja:
        lojas = _loja_do_consultor(base, coluna)
        out.insert(
            1, COLUNA_LOJA_CONSULTOR, out[coluna].map(lojas).fillna("—")
        )

    out = out.sort_values(
        ["Pontos", col_desempate], ascending=[False, False]
    ).reset_index(drop=True)

    # Posicao densa sobre o PAR (pontos, cnc): so quem empata nos dois
    # criterios divide posicao.
    chave = list(zip(out["Pontos"], out[col_desempate]))
    posicoes, anterior, pos = [], None, 0
    for i, atual in enumerate(chave, start=1):
        if atual != anterior:
            pos, anterior = i, atual
        posicoes.append(pos)
    out.insert(0, "#", posicoes)

    return out.head(top) if top else out


# ══════════════════════════════════════════════════════
# Dias uteis da janela
# ══════════════════════════════════════════════════════


def dias_uteis_campanha(
    camp: Campanha,
    hoje: Optional[date] = None,
) -> tuple[int, int]:
    """``(du_total, du_decorridos)`` na janela inteira da campanha.

    Soma mes a mes porque ``calcular_dias_uteis`` e mensal — e mensal
    porque o calendario de feriados e consultado por competencia. Para
    cada mes da janela: se ja passou, conta o mes inteiro; se e o
    corrente, conta ate hoje; se e futuro, conta zero decorridos.

    **Nao substitui o ritmo em dias corridos.** Sao perguntas
    diferentes: a campanha foi declarada por datas de calendario ("de
    01/07 a 31/12"), entao a projecao contra a meta usa dias corridos
    (:func:`ritmo`); a media/DU e produtividade — quanto sai por dia
    trabalhado — e ai feriado e fim de semana nao contam.

    Meses parciais nas pontas (se a campanha nao comecar no dia 1º ou
    nao terminar no ultimo dia) nao sao recortados: a Semestral 2026-H2
    casa com as bordas dos meses. Campanha com janela quebrada precisa
    rever isto — por isso o aviso fica aqui, e nao so no commit.
    """
    from src.shared.dias_uteis import calcular_dias_uteis

    hoje = hoje or date.today()
    total = decorridos = 0

    mes, ano = camp.inicio.month, camp.inicio.year
    while (ano, mes) <= (camp.fim.year, camp.fim.month):
        du_mes, _, _ = calcular_dias_uteis(ano, mes, dia_atual=None)
        total += du_mes

        if (ano, mes) < (hoje.year, hoje.month):
            decorridos += du_mes
        elif (ano, mes) == (hoje.year, hoje.month):
            _, du_dec, _ = calcular_dias_uteis(ano, mes, dia_atual=hoje.day)
            decorridos += du_dec
        # mes futuro: nada a somar em decorridos

        mes += 1
        if mes > 12:
            mes, ano = 1, ano + 1

    return total, decorridos


# ══════════════════════════════════════════════════════
# Ritmo
# ══════════════════════════════════════════════════════


def ritmo(
    apuracao: dict,
    camp: Campanha,
    hoje: Optional[date] = None,
) -> dict:
    """Pace da campanha em dias corridos.

    Dias CORRIDOS, nao uteis, de proposito: a campanha foi declarada por
    datas de calendario ("de 01/07 ate 31/12"), e a meta e um total do
    semestre, nao uma media diaria de producao. ``calcular_dias_uteis``
    continua sendo a regra para meta diaria do dashboard de vendas —
    outro numero, outra pergunta.

    ``projecao`` extrapola linearmente o ritmo ate aqui. E projecao, nao
    previsao: nao conhece sazonalidade (13º em nov/dez, por exemplo).
    """
    hoje = hoje or date.today()
    total_dias = (camp.fim - camp.inicio).days + 1

    if hoje < camp.inicio:
        decorridos = 0
    elif hoje > camp.fim:
        decorridos = total_dias
    else:
        decorridos = (hoje - camp.inicio).days + 1

    restantes = max(total_dias - decorridos, 0)
    valor = apuracao.get("valor", 0.0)
    meta = apuracao.get("meta", camp.meta_valor)

    ritmo_dia = (valor / decorridos) if decorridos else 0.0
    projecao = ritmo_dia * total_dias

    return {
        "dias_total": total_dias,
        "dias_decorridos": decorridos,
        "dias_restantes": restantes,
        "pct_tempo": (decorridos / total_dias) if total_dias else 0.0,
        "ritmo_dia": ritmo_dia,
        "projecao": projecao,
        "projecao_vs_meta": (projecao / meta) if meta else 0.0,
        # Quanto precisa por dia, daqui para frente, para fechar a meta.
        "necessario_dia": (
            (meta - valor) / restantes if restantes and meta > valor else 0.0
        ),
    }
