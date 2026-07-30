"""
KPIs para a aba de Gestao: apuracao por produto MIX com filtro
multi-criterio, em qualquer nivel do organograma.

A dimensao de produto deriva do MIX definido em ``PRODUTOS_DASHBOARD``
(src/dashboard/kpis/gerais.py), que mapeia cada produto para os
``categoria_codigo`` correspondentes. "Consignado", por exemplo, agrega
CONSIG_BMG/ITAU/C6; o pack (FGTS_ANT_BEN_CNC13) aparece desmembrado nas
suas tres categorias — ver ``PRODUTOS_GESTAO``.

Tres eixos independentes montam a tabela (``construir_tabela``):

- **nivel**: consultor, loja, supervisor ou regiao. A apuracao sempre
  nasce por consultor e e agregada para cima, entao os quatro niveis
  contam a mesma historia — nao ha dois caminhos de calculo.
- **metrica**: valor pago, quantidade de contratos, ticket medio ou
  share do produto no mix da entidade.
- **produtos_total**: quais produtos a coluna ``Total`` soma. Por
  padrao, so os produtos escolhidos como criterio — "Total" responde
  "quanto essa pessoa fez NO QUE ESTOU OLHANDO", nao no MIX inteiro.

Universo: quando ``df_universo`` e informado (cadastro de consultores
ATIVOS do RH), consultor sem nenhum pagamento no periodo entra na tabela
com zero em todos os produtos. Sem esse universo, a visao so enxerga
quem produziu — e um filtro do tipo "vendeu menos de X" perderia
justamente quem vendeu nada.
"""
from typing import Dict, List, Optional, Tuple, Union

import pandas as pd

from src.config.settings import PACK_SPLIT_LABELS
from src.dashboard.kpis.gerais import (
    ACELERADORES,
    PRODUTOS_DASHBOARD,
    PRODUTOS_DASHBOARD_COL_META,
    excluir_lojas_backoffice,
    excluir_supervisores,
    mascaras_aceleradores,
)
# Mesma normalizacao de nome usada no casamento cadastro x producao dos
# rankings (trim + upper). Importado — e nao reescrito — para que as
# duas superficies nunca divirjam no que consideram "o mesmo consultor".
from src.dashboard.kpis.rankings import _norm_nome

# Limiar de um criterio: escalar (base absoluta) ou uma serie com um
# limiar por linha (bases relativas — media, percentil, meta).
_Limiar = Union[float, pd.Series]

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

COL_TOTAL = "Total"

# Aceleradores entram na aba como colunas de CRITERIO, sempre em
# quantidade de contratos — qualquer que seja a metrica escolhida para
# os produtos. Nao somam no ``Total`` (unidade diferente) e nao tem
# meta individual. Os rotulos vem de kpis/gerais.py.
ROTULOS_ACELERADORES: List[str] = list(ACELERADORES)

# Super Conta e o unico acelerador que TAMBEM e produto: o valor dela
# entra em CNC (PRODUTOS_GESTAO['CNC'] inclui SUPER_CONTA) e a coluna
# de acelerador so acrescenta a contagem. Nao ha dupla contagem de
# dinheiro — a coluna de acelerador nunca entra no Total.
ACEL_SUPER_CONTA = "Super Conta"

# ── Metricas ─────────────────────────────────────────
METRICA_VALOR = "valor"
METRICA_QTD = "qtd"
METRICA_TICKET = "ticket"
METRICA_SHARE = "share"

# ── Niveis de agregacao ──────────────────────────────
NIVEL_CONSULTOR = "Consultor"
NIVEL_LOJA = "Loja"
NIVEL_SUPERVISOR = "Supervisor"
NIVEL_REGIAO = "Regiao"

SEM_SUPERVISOR = "(sem supervisor)"

# Colunas de identificacao exibidas em cada nivel, da mais externa para
# a mais interna. Toda agregacao rola a partir da matriz por consultor.
COLUNAS_ID: Dict[str, List[str]] = {
    NIVEL_CONSULTOR: ["Regiao", "Loja", "Consultor"],
    NIVEL_LOJA: ["Regiao", "Loja"],
    NIVEL_SUPERVISOR: ["Regiao", "Supervisor"],
    NIVEL_REGIAO: ["Regiao"],
}

# ── Combinacao de criterios ──────────────────────────
COMB_E = "E"
COMB_OU = "OU"
COMB_MINIMO = "minimo"

# ── Bases de comparacao de um criterio ───────────────
# Absoluta compara com R$/qtd digitados; as demais convertem um
# percentual em limiar por linha (ver _resolver_limiar).
BASE_ABSOLUTA = "absoluto"
BASE_MEDIA_GRUPO = "media_grupo"
BASE_MEDIA_REGIAO = "media_regiao"
BASE_PERCENTIL = "percentil"
BASE_META = "meta"

BASES_RELATIVAS = frozenset(
    {BASE_MEDIA_GRUPO, BASE_MEDIA_REGIAO, BASE_PERCENTIL, BASE_META}
)


def _base_universo(
    df_universo: Optional[pd.DataFrame],
    df_supervisores: Optional[pd.DataFrame],
) -> pd.DataFrame:
    """Consultores ativos do cadastro, com ``Loja``/``Regiao`` do RH.

    Espelha o universo consultor de ``listar_sem_producao``: fora
    supervisores e consultores de lojas de backoffice (Vai e Vem), cuja
    producao e creditada ao consultor de loja. ``Regiao`` vem de
    ``REGIAO_ATUAL`` (organograma de hoje) — decisao de exibicao desta
    aba, que lista pessoas, nao contratos.

    Retorna ``[Consultor, Loja, Regiao, _key]`` (vazio se sem universo).
    """
    cols = ["Consultor", "Loja", "Regiao", "_key"]
    if (
        df_universo is None
        or df_universo.empty
        or "CONSULTOR" not in df_universo.columns
    ):
        return pd.DataFrame(columns=cols)

    univ = excluir_lojas_backoffice(
        excluir_supervisores(df_universo, df_supervisores)
    )
    if univ.empty:
        return pd.DataFrame(columns=cols)

    col_regiao = (
        "REGIAO_ATUAL" if "REGIAO_ATUAL" in univ.columns else "REGIAO"
    )
    base = pd.DataFrame({"Consultor": univ["CONSULTOR"].to_numpy()})
    base["Loja"] = (
        univ["LOJA"].fillna("").to_numpy()
        if "LOJA" in univ.columns
        else ""
    )
    base["Regiao"] = (
        univ[col_regiao].fillna("").to_numpy()
        if col_regiao in univ.columns
        else ""
    )
    base["_key"] = base["Consultor"].map(_norm_nome)
    return base.drop_duplicates(subset=["_key"]).reset_index(drop=True)


def _matriz_por_consultor(
    df: pd.DataFrame,
    df_supervisores: Optional[pd.DataFrame] = None,
    df_universo: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Matriz bruta por consultor: valor E quantidade por produto.

    Colunas de identificacao (``Regiao``/``Loja``/``Consultor``) mais um
    par ``_val_<rotulo>`` / ``_qtd_<rotulo>`` por produto. As metricas
    derivadas (ticket medio, share) e a agregacao para niveis acima
    saem daqui — um unico caminho de calculo para todas as leituras.
    """
    obrigatorias = {"CONSULTOR", "VALOR", "categoria_codigo"}
    tem_producao = not df.empty and obrigatorias.issubset(df.columns)

    df_v = pd.DataFrame()
    # df_todos guarda as linhas SEM o corte de VALOR > 0: os
    # aceleradores chegam da consolidacao com VALOR zerado (emissao e
    # seguros), entao conta-los sobre df_v devolveria zero sempre.
    df_todos = pd.DataFrame()
    if tem_producao:
        df_todos = excluir_supervisores(df, df_supervisores)
        df_v = df_todos[df_todos["VALOR"] > 0].copy()

    universo = _base_universo(df_universo, df_supervisores)
    if df_v.empty and universo.empty:
        return pd.DataFrame()

    # Base de quem teve QUALQUER contrato no periodo — inclusive quem
    # so vendeu acelerador, que chega com VALOR = 0 e sumiria se a
    # identificacao saisse de df_v. Regiao/Loja pela loja de MAIOR
    # volume (nao pela primeira linha do groupby, que dependia da
    # ordem das linhas e era arbitraria para quem trocou de loja).
    if not df_todos.empty:
        produziu = _identificacao_por_producao(df_todos)
    else:
        produziu = pd.DataFrame(columns=["Consultor", "_key"])

    if universo.empty:
        base = produziu
    else:
        # Universo manda na identificacao (organograma de hoje); quem
        # produziu mas nao esta no cadastro entra pelos dados do contrato.
        extras = produziu[~produziu["_key"].isin(set(universo["_key"]))]
        base = pd.concat([universo, extras], ignore_index=True)
        for col in ("Loja", "Regiao"):
            if col in base.columns:
                base[col] = base[col].fillna("")

    if not df_v.empty:
        df_v["_key"] = df_v["CONSULTOR"].map(_norm_nome)

    for rotulo, cats in PRODUTOS_GESTAO.items():
        if df_v.empty:
            base[_col_val(rotulo)] = 0.0
            base[_col_qtd(rotulo)] = 0.0
            continue
        recorte = df_v.loc[df_v["categoria_codigo"].isin(cats)]
        agrupado = recorte.groupby("_key")["VALOR"].agg(["sum", "size"])
        base[_col_val(rotulo)] = (
            base["_key"].map(agrupado["sum"]).fillna(0.0)
        )
        base[_col_qtd(rotulo)] = (
            base["_key"].map(agrupado["size"]).fillna(0.0)
        )

    _anexar_aceleradores(base, df_todos)
    return base


def _anexar_aceleradores(
    base: pd.DataFrame,
    df_todos: pd.DataFrame,
) -> None:
    """Adiciona ``_acel_<rotulo>`` com a contagem de cada acelerador.

    Conta sobre ``df_todos`` (sem o corte de ``VALOR > 0``) porque
    emissoes e seguros chegam com valor zerado da consolidacao. Muta
    ``base`` no lugar, como o laco de produtos acima.
    """
    if df_todos.empty:
        for rotulo in ROTULOS_ACELERADORES:
            base[_col_acel(rotulo)] = 0.0
        return

    chaves = df_todos["CONSULTOR"].map(_norm_nome)
    for rotulo, mask in mascaras_aceleradores(df_todos).items():
        contagem = chaves[mask].value_counts()
        base[_col_acel(rotulo)] = (
            base["_key"].map(contagem).fillna(0.0).astype(float)
        )


def _col_val(rotulo: str) -> str:
    return f"_val_{rotulo}"


def _col_qtd(rotulo: str) -> str:
    return f"_qtd_{rotulo}"


def _col_acel(rotulo: str) -> str:
    return f"_acel_{rotulo}"


def _mapa_supervisor(
    df_supervisores: Optional[pd.DataFrame],
) -> Dict[str, str]:
    """Loja normalizada -> nome do supervisor, a partir do cadastro."""
    if (
        df_supervisores is None
        or df_supervisores.empty
        or "SUPERVISOR" not in df_supervisores.columns
        or "LOJA" not in df_supervisores.columns
    ):
        return {}
    mapa: Dict[str, str] = {}
    for _, linha in df_supervisores.iterrows():
        loja = _norm_nome(linha.get("LOJA") or "")
        sup = str(linha.get("SUPERVISOR") or "").strip()
        if loja and sup:
            mapa.setdefault(loja, sup)
    return mapa


def _agregar_nivel(
    matriz: pd.DataFrame,
    nivel: str,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Rola a matriz por consultor para o nivel pedido.

    Valor e quantidade sao somas; ticket e share sao recalculados
    depois, sobre os totais agregados (media de medias mentiria).
    """
    if nivel == NIVEL_CONSULTOR:
        return matriz

    if nivel == NIVEL_SUPERVISOR:
        mapa = _mapa_supervisor(df_supervisores)
        origem = (
            matriz["Loja"].map(lambda lj: mapa.get(_norm_nome(lj), ""))
            if "Loja" in matriz.columns
            else pd.Series("", index=matriz.index)
        )
        matriz = matriz.assign(
            Supervisor=origem.replace("", SEM_SUPERVISOR)
        )

    chaves = [c for c in COLUNAS_ID[nivel] if c in matriz.columns]
    if not chaves:
        return matriz

    metricas = [
        c for c in matriz.columns
        if c.startswith(("_val_", "_qtd_", "_acel_"))
    ]
    agregada = (
        matriz.groupby(chaves, dropna=False)[metricas].sum().reset_index()
    )
    agregada["_key"] = agregada[chaves[-1]].map(_norm_nome)
    return agregada


def _aplicar_metrica(
    matriz: pd.DataFrame,
    metrica: str,
    produtos_total: List[str],
) -> pd.DataFrame:
    """Converte a matriz bruta na tabela exibida, na metrica pedida.

    ``Total`` cobre exatamente ``produtos_total``: em valor e
    quantidade e a soma; em ticket medio e o valor total dividido pela
    quantidade total (nao a media dos tickets); em share e sempre 100%,
    por construcao — as fatias exibidas somam o proprio Total.
    """
    saida = matriz.drop(
        columns=[
            c for c in matriz.columns
            if c.startswith(("_val_", "_qtd_", "_acel_")) or c == "_key"
        ]
    )
    rotulos = list(PRODUTOS_GESTAO)
    val_total = sum(
        (matriz[_col_val(r)] for r in produtos_total),
        pd.Series(0.0, index=matriz.index),
    )
    qtd_total = sum(
        (matriz[_col_qtd(r)] for r in produtos_total),
        pd.Series(0.0, index=matriz.index),
    )

    for rotulo in rotulos:
        val = matriz[_col_val(rotulo)]
        qtd = matriz[_col_qtd(rotulo)]
        if metrica == METRICA_QTD:
            saida[rotulo] = qtd
        elif metrica == METRICA_TICKET:
            saida[rotulo] = (val / qtd.where(qtd > 0)).fillna(0.0)
        elif metrica == METRICA_SHARE:
            saida[rotulo] = (
                val / val_total.where(val_total > 0) * 100.0
            ).fillna(0.0)
        else:
            saida[rotulo] = val

    if metrica == METRICA_QTD:
        saida[COL_TOTAL] = qtd_total
    elif metrica == METRICA_TICKET:
        saida[COL_TOTAL] = (
            val_total / qtd_total.where(qtd_total > 0)
        ).fillna(0.0)
    elif metrica == METRICA_SHARE:
        saida[COL_TOTAL] = (val_total > 0).astype(float) * 100.0
    else:
        saida[COL_TOTAL] = val_total

    # Aceleradores sempre em quantidade, depois do Total: sao outra
    # unidade e por isso ficam FORA da soma — misturar contratos de
    # seguro com reais de CLT nao produz numero que signifique nada.
    for rotulo in ROTULOS_ACELERADORES:
        col = _col_acel(rotulo)
        if col in matriz.columns:
            saida[rotulo] = matriz[col]
    return saida


def construir_tabela(
    df: pd.DataFrame,
    df_supervisores: Optional[pd.DataFrame] = None,
    df_universo: Optional[pd.DataFrame] = None,
    nivel: str = NIVEL_CONSULTOR,
    metrica: str = METRICA_VALOR,
    produtos_total: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Tabela da aba de Gestao no nivel, metrica e escopo pedidos.

    Colunas: identificacao do nivel (ver ``COLUNAS_ID``), uma coluna por
    produto de ``PRODUTOS_GESTAO`` e ``Total``.

    Args:
        df: contratos pagos do periodo, ja filtrados por RLS e pelos
            filtros da sidebar (feito em ``app.py``).
        df_supervisores: cadastro de supervisores. Usado para excluir
            supervisores da apuracao de consultor e, no nivel
            ``Supervisor``, para mapear loja -> supervisor.
        df_universo: consultores ATIVOS do RH
            (``carregar_consultores_ativos``, ja recortado pelo mesmo
            RLS/filtros de ``df``). Quando informado, quem nao produziu
            no periodo entra zerado — sem isso, um criterio "ate X"
            perde exatamente quem vendeu nada. ``Loja``/``Regiao`` saem
            do cadastro; consultor com producao fora do universo (ex.:
            desligado no mes) e mantido com os dados do contrato.
        nivel: ``Consultor`` (padrao), ``Loja``, ``Supervisor`` ou
            ``Regiao``.
        metrica: ``valor`` (padrao), ``qtd``, ``ticket`` ou ``share``.
        produtos_total: produtos somados na coluna ``Total``. ``None``
            soma o MIX inteiro; na aba, recebe os produtos do criterio.

    Espera ``df`` ja filtrado por RLS; nao aplica RLS nem queries aqui.
    """
    matriz = _matriz_por_consultor(df, df_supervisores, df_universo)
    if matriz.empty:
        return pd.DataFrame()

    matriz = _agregar_nivel(matriz, nivel, df_supervisores)
    rotulos = list(PRODUTOS_GESTAO)
    escopo = [r for r in (produtos_total or rotulos) if r in rotulos]
    if not escopo:
        escopo = rotulos

    tabela = _aplicar_metrica(matriz, metrica, escopo)

    cols_id = [c for c in COLUNAS_ID[nivel] if c in tabela.columns]
    cols_acel = [
        r for r in ROTULOS_ACELERADORES if r in tabela.columns
    ]
    tabela = tabela[[*cols_id, *rotulos, COL_TOTAL, *cols_acel]]
    return tabela.sort_values(cols_id).reset_index(drop=True)


def vendas_mix_por_consultor(
    df: pd.DataFrame,
    df_supervisores: Optional[pd.DataFrame] = None,
    df_universo: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Valor pago por consultor em cada produto, com ``Total`` do MIX.

    Atalho de :func:`construir_tabela` no nivel consultor e metrica de
    valor — a leitura padrao da aba antes dos eixos de nivel/metrica.
    """
    return construir_tabela(
        df,
        df_supervisores,
        df_universo,
        nivel=NIVEL_CONSULTOR,
        metrica=METRICA_VALOR,
    )


def _identificacao_por_producao(df_v: pd.DataFrame) -> pd.DataFrame:
    """Consultor -> Loja/Regiao da loja com MAIOR valor no periodo.

    Desempate deterministico por nome da loja, para que a tabela nao
    mude entre execucoes quando o volume empata. Colunas ``Loja`` e
    ``Regiao`` so aparecem quando existem na origem — df sem essas
    dimensoes continua produzindo uma tabela sem elas.
    """
    saida = pd.DataFrame(
        {"Consultor": df_v["CONSULTOR"].dropna().unique()}
    )
    saida["_key"] = saida["Consultor"].map(_norm_nome)

    if "LOJA" not in df_v.columns:
        if "REGIAO" in df_v.columns:
            regiao = (
                df_v.assign(_key=df_v["CONSULTOR"].map(_norm_nome))
                .groupby("_key")["REGIAO"]
                .first()
            )
            saida["Regiao"] = saida["_key"].map(regiao).fillna("")
        return saida

    dims = ["CONSULTOR", "LOJA"]
    if "REGIAO" in df_v.columns:
        dims.append("REGIAO")
    volume = (
        df_v.groupby(dims, dropna=False)["VALOR"]
        .sum()
        .reset_index()
        .sort_values(
            ["CONSULTOR", "VALOR", "LOJA"], ascending=[True, False, True]
        )
        .drop_duplicates(subset=["CONSULTOR"])
    )
    volume["_key"] = volume["CONSULTOR"].map(_norm_nome)
    volume = volume.set_index("_key")
    saida["Loja"] = saida["_key"].map(volume["LOJA"]).fillna("")
    if "REGIAO" in volume.columns:
        saida["Regiao"] = saida["_key"].map(volume["REGIAO"]).fillna("")
    return saida


# Modos de criterio. Todos os limiares sao INCLUSIVOS — "ate 15.000"
# e "a partir de 15.000" ambos contem quem tem exatamente 15.000, e o
# mesmo numero digitado em modos diferentes nunca produz uma zona cega
# entre as duas listas. ``menor`` e alias historico de ``ate``.
MODO_ATE = "ate"
MODO_ENTRE = "entre"
MODO_ACIMA = "acima"
MODO_ZERO = "zero"
MODO_POSITIVO = "positivo"

# Modos com teto numerico: sustentam o calculo de lacuna (quanto falta
# para o consultor sair da faixa de baixa producao). ``zero`` fica de
# fora — "sair de sem venda" nao tem alvo em R$, qualquer valor serve.
_MODOS_COM_TETO = frozenset({MODO_ATE, MODO_ENTRE, "menor"})


def matriz_metas(
    tabela: pd.DataFrame,
    df_metas: Optional[pd.DataFrame],
) -> pd.DataFrame:
    """Meta por linha da tabela e por rotulo, para a base ``meta``.

    ``df_metas`` e o pivot de ``carregar_metas_produto_consultor``
    (``LOJA`` + uma coluna por produto de meta): o alvo individual de
    cada consultor daquela loja. O casamento e por ``Loja``, entao so
    faz sentido no nivel consultor.

    Os tres rotulos do pack (FGTS, ANT. DE BENEF., CNC 13º) ficam de
    fora: a meta ``FGTS_ANT_BENEF_13`` e CONJUNTA, nao existe alvo por
    categoria — dividi-la em tres seria inventar numero. Rotulos sem
    meta saem como ``NaN`` e o criterio correspondente e ignorado
    (ver :func:`diagnosticar_criterios`).
    """
    vazia = pd.DataFrame(index=tabela.index)
    if (
        tabela.empty
        or df_metas is None
        or df_metas.empty
        or "LOJA" not in df_metas.columns
        or "Loja" not in tabela.columns
    ):
        return vazia

    metas = df_metas.copy()
    metas["_key"] = metas["LOJA"].map(_norm_nome)
    metas = metas.drop_duplicates(subset=["_key"]).set_index("_key")
    chave_loja = tabela["Loja"].map(_norm_nome)

    saida = pd.DataFrame(index=tabela.index)
    for rotulo in PRODUTOS_GESTAO:
        col_meta = PRODUTOS_DASHBOARD_COL_META.get(_chave_mix(rotulo))
        if col_meta and col_meta in metas.columns:
            saida[rotulo] = chave_loja.map(metas[col_meta]).astype(float)
    if not saida.empty:
        # Total = soma das metas dos produtos com alvo individual.
        saida[COL_TOTAL] = saida.sum(axis=1, min_count=1)
    return saida


def _chave_mix(rotulo: str) -> str:
    """Rotulo da aba -> chave do MIX global (para achar a coluna de meta)."""
    equivalencia = {
        "CNC": "CNC",
        "CLT": "CLT",
        "Saque": "SAQUE",
        "Consignado": "CONSIGNADO",
    }
    return equivalencia.get(rotulo, "")


def _resolver_limiar(
    tabela: pd.DataFrame,
    rotulo: str,
    crit: Dict,
    chave: str,
    metas: Optional[pd.DataFrame] = None,
) -> Optional[_Limiar]:
    """Limiar de um criterio: escalar (absoluto) ou uma serie por linha.

    Nas bases relativas o numero digitado e um PERCENTUAL: 50% da media
    do grupo, 80% da meta, percentil 20. Isso deixa o criterio vivo mes
    a mes — um teto fixo em R$ envelhece, "metade da media" nao.

    Devolve ``None`` quando a base nao pode ser resolvida (ex.: meta
    inexistente para o rotulo), sinalizando que o criterio deve ser
    ignorado em vez de silenciosamente zerar a lista.
    """
    base = crit.get("base", BASE_ABSOLUTA)
    numero = float(crit.get(chave, 0.0))
    coluna = tabela[rotulo]

    if base == BASE_ABSOLUTA:
        return numero
    if base == BASE_MEDIA_GRUPO:
        return float(coluna.mean()) * numero / 100.0
    if base == BASE_MEDIA_REGIAO:
        if "Regiao" not in tabela.columns:
            return float(coluna.mean()) * numero / 100.0
        media = tabela.groupby("Regiao")[rotulo].transform("mean")
        return media * numero / 100.0
    if base == BASE_PERCENTIL:
        return float(coluna.quantile(min(max(numero, 0.0), 100.0) / 100.0))
    if base == BASE_META:
        if metas is None or rotulo not in metas.columns:
            return None
        alvo = metas[rotulo]
        if alvo.isna().all():
            return None
        return alvo * numero / 100.0
    return numero


def _mascara_criterio(
    tabela: pd.DataFrame,
    rotulo: str,
    crit: Dict,
    metas: Optional[pd.DataFrame] = None,
) -> Optional[pd.Series]:
    """Mascara booleana de um unico criterio; ``None`` se irresoluvel."""
    coluna = tabela[rotulo]
    modo = crit.get("modo", MODO_ATE)

    if modo == MODO_ZERO:
        return coluna <= 0
    if modo == MODO_POSITIVO:
        return coluna > 0

    if modo == MODO_ENTRE:
        minimo = _resolver_limiar(tabela, rotulo, crit, "min", metas)
        maximo = _resolver_limiar(tabela, rotulo, crit, "max", metas)
        if minimo is None or maximo is None:
            return None
        return (coluna >= minimo) & (coluna <= maximo)
    if modo == MODO_ACIMA:
        minimo = _resolver_limiar(tabela, rotulo, crit, "min", metas)
        return None if minimo is None else coluna >= minimo
    # MODO_ATE e o alias "menor"
    maximo = _resolver_limiar(tabela, rotulo, crit, "max", metas)
    return None if maximo is None else coluna <= maximo


def _mascaras(
    tabela: pd.DataFrame,
    criterios: Dict[str, Dict],
    metas: Optional[pd.DataFrame] = None,
) -> Tuple[List[pd.Series], List[str]]:
    """Mascaras aplicaveis e rotulos ignorados (coluna ou base ausente)."""
    aplicaveis: List[pd.Series] = []
    ignorados: List[str] = []
    for rotulo, crit in criterios.items():
        if rotulo not in tabela.columns:
            ignorados.append(rotulo)
            continue
        mask = _mascara_criterio(tabela, rotulo, crit, metas)
        if mask is None:
            ignorados.append(rotulo)
        else:
            aplicaveis.append(mask)
    return aplicaveis, ignorados


def diagnosticar_criterios(
    tabela: pd.DataFrame,
    criterios: Dict[str, Dict],
    metas: Optional[pd.DataFrame] = None,
) -> List[str]:
    """Rotulos cujo criterio nao pode ser aplicado (para avisar na UI).

    Um criterio irresoluvel e IGNORADO, nunca tratado como "ninguem
    atende" — do contrario a lista viria vazia sem explicacao.
    """
    if tabela.empty or not criterios:
        return []
    return _mascaras(tabela, criterios, metas)[1]


def filtrar_por_criterios(
    tabela: pd.DataFrame,
    criterios: Dict[str, Dict[str, float | str]],
    combinacao: str = COMB_E,
    minimo: int = 1,
    metas: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Aplica os criterios por produto, na combinacao pedida.

    Args:
        tabela: saida de :func:`construir_tabela`.
        criterios: ``{rotulo: {"modo": ..., "base": ..., "min": float,
            "max": float}}``, onde ``rotulo`` e um produto de
            ``PRODUTOS_GESTAO`` ou ``"Total"``. Modos:

            - ``ate`` (alias ``menor``): ``valor <= max``
            - ``entre``: ``min <= valor <= max``
            - ``acima``: ``valor >= min``
            - ``zero``: ``valor <= 0`` (sem venda no produto)
            - ``positivo``: ``valor > 0`` (com venda no produto)

            Todos inclusivos. Bases: ``absoluto`` (padrao), ou
            ``media_grupo`` / ``media_regiao`` / ``percentil`` /
            ``meta``, em que ``min``/``max`` sao percentuais.
        combinacao: ``E`` (padrao, todos), ``OU`` (qualquer um) ou
            ``minimo`` (pelo menos ``minimo`` criterios atendidos).
        minimo: quantos criterios bastam quando ``combinacao="minimo"``.
        metas: saida de :func:`matriz_metas`, exigida pela base ``meta``.

    Returns:
        As entidades que satisfazem a combinacao. Sem criterios (ou com
        todos irresoluveis), retorna a tabela inalterada.
    """
    if tabela.empty or not criterios:
        return tabela

    aplicaveis, _ = _mascaras(tabela, criterios, metas)
    if not aplicaveis:
        return tabela

    if combinacao == COMB_OU:
        mask = pd.Series(False, index=tabela.index)
        for m in aplicaveis:
            mask |= m
    elif combinacao == COMB_MINIMO:
        atendidos = sum(m.astype(int) for m in aplicaveis)
        alvo = max(1, min(int(minimo), len(aplicaveis)))
        mask = atendidos >= alvo
    else:  # COMB_E
        mask = pd.Series(True, index=tabela.index)
        for m in aplicaveis:
            mask &= m

    return tabela[mask].reset_index(drop=True)


def calcular_lacuna(
    tabela: pd.DataFrame,
    criterios: Dict[str, Dict[str, float | str]],
    metas: Optional[pd.DataFrame] = None,
    apenas: Optional[List[str]] = None,
) -> pd.Series:
    """Quanto falta para cada entidade sair dos criterios de teto.

    Para cada criterio com teto (``ate``/``entre``), soma
    ``max(0, teto - valor)``. E o numero acionavel da lista: "esta
    pessoa precisa de mais X para deixar de ser um caso de
    acompanhamento". Criterios sem teto (``acima``, ``positivo``,
    ``zero``) nao contribuem, nem os irresoluveis.

    Args:
        apenas: restringe a soma a estes rotulos. **Necessario quando
            ha criterios de unidades diferentes na mesma consulta** —
            produto segue a metrica (R$, contratos, ticket, p.p.) e
            acelerador e sempre contratos. Somar as duas coisas numa
            coluna so produziria um numero sem significado, entao a
            aba calcula uma lacuna por unidade.
    """
    lacuna = pd.Series(0.0, index=tabela.index)
    if tabela.empty or not criterios:
        return lacuna

    permitidos = set(apenas) if apenas is not None else None
    for rotulo, crit in criterios.items():
        if rotulo not in tabela.columns:
            continue
        if permitidos is not None and rotulo not in permitidos:
            continue
        if crit.get("modo", MODO_ATE) not in _MODOS_COM_TETO:
            continue
        teto = _resolver_limiar(tabela, rotulo, crit, "max", metas)
        if teto is None:
            continue
        lacuna += (teto - tabela[rotulo]).clip(lower=0.0)

    return lacuna
