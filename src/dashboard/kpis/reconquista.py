"""
Regras da Reconquista MG CRED e do acelerador combinado.

Recebe frames JA CARREGADOS e devolve frames/dicts — **nao** toca o
Supabase. E a metade "regra" do que era a secao de Reconquista de
`loaders.py`; a carga (view `v_reconquista`, cobranca consignavel,
faixas do acelerador), o cache e a orquestracao ficaram la, que segue
sendo a fachada publica (`carregar_reconquista`).

## O vocabulario

A apuracao e **mensal pelo mes de `dt_fim_relacionamento`**, com
defasagem de 1 mes: a apuracao do mes M exibe os contratos cujo dt_fim
caiu em M-1 (os de M so entram na esteira no mes seguinte). Cada lead
recebe um rotulo de `vigencia` (`VIGENCIA_*`) frente ao mes
selecionado, e um `status` (EFETIVADA / PROMESSA / SEM RECONQUISTA)
que ja vem da view.

Conversao = EFETIVADA / elegiveis. **So ELEGIVEL entra no
denominador** (NULL ou sem flag conta como elegivel); os NAO ELEGIVEL
seguem visiveis nos analiticos, apenas fora da conta.

## O que NAO veio para ca

`_faixas_acelerador_por_qtd`, `_faixa_agregada_acelerador` e
`_por_consultor_acelerador` chamam loaders (faixas, cobranca
consignavel, consultores ativos, supervisores): sao **orquestracao**,
nao regra pura, e ficaram em `loaders.py`. Traze-las exigiria injetar
cinco loaders — mudanca de assinatura que nao cabe numa etapa cujo
criterio e "mesmos resultados e interfaces publicas preservadas".
Fica como candidato para uma proxima passagem.

`_acelerador_no_escopo` tambem ficou: depende do perfil logado
(`_obter_perfil_efetivo`), e e gate de produto, nao calculo.

Extraido na Etapa 2 da revisao de 09/2026. Corpos movidos sem
alteracao (prova de move byte-identico no commit). Ver
docs/agents/business-rules.md.
"""


from typing import Dict, Optional, Tuple

import pandas as pd

from src.dashboard.kpis.gerais import excluir_supervisores
from src.shared.texto import normalizar_nome


# ══════════════════════════════════════════════════════
# Reconquista MG CRED (v2)
#
# Export unico, 1 linha por cliente (co_adesao), ja
# classificado em `status` (EFETIVADA/PROMESSA/SEM
# RECONQUISTA). Fonte: view `v_reconquista`. A apuracao e
# MENSAL pelo mes de dt_fim_relacionamento (ref_ano/ref_mes),
# com DEFASAGEM de 1 mes: a apuracao do mes M exibe os
# contratos cujo dt_fim caiu em M-1 (os de M so entram na
# esteira no mes seguinte).
#
# KPIs (3 estados + taxa) e a quebra por loja sao derivados
# em pandas a partir da view detalhada. Ver
# docs/agents/business-rules.md.
# ══════════════════════════════════════════════════════

# Rotulos de vigencia de cada lead frente ao mes selecionado
# (`_marcar_vigencia_reconquista`). Publicos: a UI compara contra eles
# para destacar/filtrar sem reescrever a regra.
VIGENCIA_VIGENTE = "Vigente"
VIGENCIA_PROXIMA = "Próxima"
VIGENCIA_HISTORICO = "Histórico"
VIGENCIA_FUTURA = "Futura"
VIGENCIA_SEM_REF = "Sem referência"


# Primeira apuracao (ano, mes) em que a regra vale.
_ACELERADOR_INICIO = (2026, 8)


def _faixa_premio_conversao(pct: float) -> Dict:
    """Mapeia % de conversao -> faixa de premio/deflator sobre premio CNC.

    Substitui a meta fixa: o percentual alcancado sobre a base ELEGIVEL
    define o ajuste (indicador — nao calcula R$). Faixas (tabela de
    negocio, limite superior inclusivo nas negativas):
        0 a 10%      -> -20%
        10,1 a 20%   -> -10%
        20,1 a 29,99 ->   0
        30 a 39,99   -> +10%
        >= 40        -> +20%
    Retorna {ajuste_pct, rotulo, cor}.
    """
    if pct <= 10:
        ajuste = -20
    elif pct <= 20:
        ajuste = -10
    elif pct < 30:
        ajuste = 0
    elif pct < 40:
        ajuste = 10
    else:
        ajuste = 20

    if ajuste < 0:
        cor = "#E5484D" if ajuste <= -20 else "#E5844D"
        rotulo = f"{ajuste}% sobre prêmio CNC"
    elif ajuste == 0:
        cor = "var(--mg-text-muted)"
        rotulo = "0 (neutro)"
    else:
        cor = "#10A37F" if ajuste >= 20 else "#3E9B4F"
        rotulo = f"+{ajuste}% sobre prêmio CNC"
    return {"ajuste_pct": ajuste, "rotulo": rotulo, "cor": cor}


def _mask_elegivel(clientes: pd.DataFrame) -> pd.Series:
    """Mascara ELEGIVEL. Sem coluna ou valor ausente/NULL => ELEGIVEL
    (decisao: interim conta como elegivel). NAO ELEGIVEL (com/sem
    acento) sai da apuracao."""
    if clientes is None or clientes.empty:
        return pd.Series([], dtype=bool)
    if "flag_elegibilidade" not in clientes.columns:
        return pd.Series(True, index=clientes.index)
    norm = (
        clientes["flag_elegibilidade"].fillna("").astype(str)
        .str.upper().str.strip()
    )
    return ~norm.str.startswith(("NAO", "NÃO"))


def _mes_apuracao_anterior(mes: int, ano: int) -> Tuple[int, int]:
    """Defasagem de 1 mes: apuracao de (mes, ano) -> mes anterior."""
    ref_mes = mes - 1
    ref_ano = ano
    if ref_mes == 0:
        ref_mes = 12
        ref_ano = ano - 1
    return ref_mes, ref_ano


def _mes_apuracao_seguinte(mes: int, ano: int) -> Tuple[int, int]:
    """Apuracao seguinte de (mes, ano) -> mes posterior (rollover dez->jan)."""
    prox_mes = mes + 1
    prox_ano = ano
    if prox_mes == 13:
        prox_mes = 1
        prox_ano = ano + 1
    return prox_mes, prox_ano


def _chave_apuracao(ano: int, mes: int) -> int:
    """Mes como inteiro monotonico (ano*12 + mes) — compara e ordena."""
    return int(ano) * 12 + int(mes)


def _rotulo_mes(chave: pd.Series) -> pd.Series:
    """`ano*12+mes` -> rotulo ``MM/AAAA`` (vetorizado)."""
    mes = ((chave - 1) % 12) + 1
    ano = (chave - mes) // 12
    return mes.astype(str).str.zfill(2) + "/" + ano.astype(str)


def _marcar_vigencia_reconquista(
    clientes: pd.DataFrame, mes: int, ano: int
) -> pd.DataFrame:
    """Anota cada lead com a apuracao a que pertence e a vigencia dela.

    A separacao ja existe no dado — a view deriva `ref_ano`/`ref_mes` de
    dt_fim_relacionamento e a campanha tem defasagem de 1 mes
    (business-rules.md), entao ``apuracao = ref + 1``. Aqui isso so vira
    rotulo, por linha:

      * ``ref_key``      — ano*12+mes do fim de relacionamento;
      * ``ref_label``    — rotulo ``MM/AAAA`` do fim de relacionamento;
      * ``apuracao_key`` — ano*12+mes da apuracao (ordenacao);
      * ``apuracao_ref`` — rotulo ``MM/AAAA`` da apuracao;
      * ``vigencia``     — posicao frente ao (mes, ano) selecionado:
        VIGENTE (a que os KPIs apuram), PROXIMA (esteira ja acumulando,
        a mesma da previa), HISTORICO, FUTURA.

    Os dois eixos convivem de proposito: a campanha apura por
    ``apuracao_*`` (defasada), o analitico lista por ``ref_*`` (a data
    do lead — Setembro lista quem encerrou em Setembro). Ver
    ``_render_reconquista_detalhamento``.

    Colunas derivadas, nao existem na view. Nenhum KPI le daqui.
    """
    if clientes is None or clientes.empty:
        return pd.DataFrame() if clientes is None else clientes.copy()

    df = clientes.copy()
    if "ref_ano" not in df.columns or "ref_mes" not in df.columns:
        df["ref_key"] = -1
        df["ref_label"] = "—"
        df["apuracao_key"] = -1
        df["apuracao_ref"] = "—"
        df["vigencia"] = VIGENCIA_SEM_REF
        return df

    ref = (
        pd.to_numeric(df["ref_ano"], errors="coerce") * 12
        + pd.to_numeric(df["ref_mes"], errors="coerce")
    )
    valido = ref.notna()
    apuracao = ref + 1  # defasagem: dt_fim em M -> apuracao em M+1

    df["ref_key"] = ref.fillna(-1).astype(int)
    df["apuracao_key"] = apuracao.fillna(-1).astype(int)
    df["ref_label"] = _rotulo_mes(df["ref_key"]).where(valido, "—")
    df["apuracao_ref"] = _rotulo_mes(df["apuracao_key"]).where(valido, "—")

    selecionada = _chave_apuracao(ano, mes)
    vigencia = pd.Series(VIGENCIA_FUTURA, index=df.index)
    vigencia[df["apuracao_key"] < selecionada] = VIGENCIA_HISTORICO
    vigencia[df["apuracao_key"] == selecionada + 1] = VIGENCIA_PROXIMA
    vigencia[df["apuracao_key"] == selecionada] = VIGENCIA_VIGENTE
    vigencia[~valido] = VIGENCIA_SEM_REF
    df["vigencia"] = vigencia
    return df


def _fatiar_ref(
    todos: pd.DataFrame, ref_ano: int, ref_mes: int
) -> pd.DataFrame:
    """Recorte de um mes de referencia (dt_fim_relacionamento) da base."""
    if todos is None or todos.empty:
        return pd.DataFrame()
    if "ref_ano" not in todos.columns or "ref_mes" not in todos.columns:
        return pd.DataFrame()
    return todos[
        (todos["ref_ano"] == ref_ano) & (todos["ref_mes"] == ref_mes)
    ].copy()


def _totais_reconquista(clientes: pd.DataFrame) -> Dict:
    """KPIs do mes sobre a base ELEGIVEL: contagem por estado +
    conversao (= EFETIVADA / elegiveis) + faixa de premio/deflator.

    Somente ELEGIVEL contam na conversao (NULL/sem flag => ELEGIVEL);
    os NAO ELEGIVEL seguem visiveis nos analiticos, so fora da conta.
    """
    # As 4 chaves do acelerador entram aqui so para o dict ter schema
    # estavel (a previa tambem usa estes totais); quem preenche de fato
    # e `carregar_reconquista`, sob o gate.
    vazio = {
        "total": 0, "total_geral": 0, "nao_elegivel": 0,
        "efetivadas": 0, "promessas": 0, "sem_reconquista": 0,
        "conversao": 0.0, "faixa": _faixa_premio_conversao(0.0),
        "cobranca_consignavel": 0, "acelerador_no_escopo": False,
        "acelerador_perfil": None, "faixa_agregada": None,
    }
    if clientes is None or clientes.empty or "status" not in clientes.columns:
        return vazio

    total_geral = len(clientes)
    eleg = clientes[_mask_elegivel(clientes)]
    total = len(eleg)
    if total == 0:
        return {**vazio, "total_geral": total_geral, "nao_elegivel": total_geral}

    vc = eleg["status"].value_counts()
    efetivadas = int(vc.get("EFETIVADA", 0))
    conversao = efetivadas / total * 100
    return {
        "total": total,                    # base elegivel (denominador)
        "total_geral": total_geral,        # todos (contexto)
        "nao_elegivel": total_geral - total,
        "efetivadas": efetivadas,
        "promessas": int(vc.get("PROMESSA", 0)),
        "sem_reconquista": int(vc.get("SEM RECONQUISTA", 0)),
        "conversao": conversao,
        "faixa": _faixa_premio_conversao(conversao),
        "cobranca_consignavel": 0,      # ver comentario em `vazio`
        "acelerador_no_escopo": False,  # idem
        "acelerador_perfil": None,      # idem
        "faixa_agregada": None,         # idem
    }


def _coagir_numerico(df: pd.DataFrame, colunas) -> None:
    """Coage colunas a numerico in-place (NaN no lugar de None).

    Coluna inteira nula chega do export como `object`, e `mean()` de
    object devolve `None` — a tabela imprimia "None" onde devia ficar
    vazio. Nao muda media nenhuma: so troca o tipo do vazio.
    """
    for col in colunas:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")


def _por_loja_reconquista(clientes: pd.DataFrame) -> pd.DataFrame:
    """Quebra por loja/regiao sobre a base ELEGIVEL: 3 estados +
    conversao (EFETIVADA / elegiveis da loja) + faixa."""
    if clientes is None or clientes.empty or "loja" not in clientes.columns:
        return pd.DataFrame()

    df = clientes[_mask_elegivel(clientes)].copy()  # so elegiveis na apuracao
    if df.empty:
        return pd.DataFrame()
    _coagir_numerico(df, ("saldo_contabil", "dias_atraso"))
    df["_efet"] = (df["status"] == "EFETIVADA").astype(int)
    df["_prom"] = (df["status"] == "PROMESSA").astype(int)
    df["_sem"] = (df["status"] == "SEM RECONQUISTA").astype(int)

    g = (
        df.groupby(["loja", "regiao"], dropna=False)
        .agg(
            total_clientes=("co_adesao", "count"),
            efetivadas=("_efet", "sum"),
            promessas=("_prom", "sum"),
            sem_reconquista=("_sem", "sum"),
            saldo_medio=("saldo_contabil", "mean"),
            dias_atraso_medio=("dias_atraso", "mean"),
        )
        .reset_index()
    )
    g["conversao_pct"] = (
        g["efetivadas"] * 100.0
        / g["total_clientes"].where(g["total_clientes"] > 0)
    ).round(1)
    g["faixa"] = g["conversao_pct"].fillna(0.0).map(
        lambda p: _faixa_premio_conversao(p)["rotulo"]
    )
    return g.sort_values("efetivadas", ascending=False)


def _por_consultor_reconquista(clientes: pd.DataFrame) -> pd.DataFrame:
    """Espelha `_por_loja_reconquista` agrupando por consultor.

    Consultor e agregado por NOME (soma a producao da pessoa mesmo
    transferida de loja — ver docs/agents/rls.md, nota nome x id).
    """
    if clientes is None or clientes.empty or "consultor" not in clientes.columns:
        return pd.DataFrame()

    df = clientes[_mask_elegivel(clientes)].copy()  # so elegiveis na apuracao
    if df.empty:
        return pd.DataFrame()
    _coagir_numerico(df, ("saldo_contabil", "dias_atraso"))
    df["_efet"] = (df["status"] == "EFETIVADA").astype(int)
    df["_prom"] = (df["status"] == "PROMESSA").astype(int)
    df["_sem"] = (df["status"] == "SEM RECONQUISTA").astype(int)

    g = (
        df.groupby("consultor", dropna=False)
        .agg(
            total_clientes=("co_adesao", "count"),
            efetivadas=("_efet", "sum"),
            promessas=("_prom", "sum"),
            sem_reconquista=("_sem", "sum"),
            saldo_medio=("saldo_contabil", "mean"),
            dias_atraso_medio=("dias_atraso", "mean"),
        )
        .reset_index()
    )
    g["conversao_pct"] = (
        g["efetivadas"] * 100.0
        / g["total_clientes"].where(g["total_clientes"] > 0)
    ).round(1)
    g["faixa"] = g["conversao_pct"].fillna(0.0).map(
        lambda p: _faixa_premio_conversao(p)["rotulo"]
    )
    return g.sort_values("efetivadas", ascending=False)


def _norm_texto(serie: pd.Series) -> pd.Series:
    """Chave de comparacao de NOME DE PESSOA — ver `shared/texto.py`.

    Alias mantido porque e o nome que `loaders.py` ja importava. A
    implementacao saiu daqui em 09/2026: era `strip + upper` replicado
    do `_norm` de `tabs/produtos.py`, e NAO dobrava acento — entao o
    merge de producao nao casava `JOÃO DA SILVA` com `JOAO DA SILVA` e
    a pessoa aparecia zerada no acelerador.
    """
    return normalizar_nome(serie)


def _acelerador_vigente(mes: int, ano: int) -> bool:
    """Gate de VIGENCIA (sem perfil): so a data importa.

    Usado pela contagem agregada de Cobranca Consignavel (card), que
    e visivel a qualquer perfil a partir de 08/2026 — RLS normal de
    cada um (admin/gestor veem tudo, gerente_comercial a regiao,
    supervisor a loja, consultor so ele) ja escopa o numero.
    """
    return (ano, mes) >= _ACELERADOR_INICIO


def _por_consultor_cobranca_consignavel(
    contratos: pd.DataFrame,
) -> pd.DataFrame:
    """Contagem de Cobranca Consignavel por consultor (frame ja pos-RLS)."""
    cols = ["consultor", "cobranca_consignavel"]
    if (
        contratos is None
        or contratos.empty
        or "CONSULTOR" not in contratos.columns
    ):
        return pd.DataFrame(columns=cols)
    return (
        contratos.groupby("CONSULTOR", dropna=False)
        .size()
        .reset_index(name="cobranca_consignavel")
        .rename(columns={"CONSULTOR": "consultor"})
    )


def _juntar_producao(
    nomes: pd.DataFrame, rec: pd.DataFrame, cobr: pd.DataFrame
) -> pd.DataFrame:
    """Junta `efetivadas`/`cobranca_consignavel` a um conjunto de nomes.

    Devolve exatamente as linhas de `nomes` (dedupe por nome
    normalizado) — quem nao tem correspondencia em `rec`/`cobr` entra
    com 0, nunca adiciona linha nova. Merge por `_norm_texto`: as
    fontes podem vir com grafia levemente diferente do cadastro.
    """
    base = nomes[["consultor"]].copy()
    base["_key"] = _norm_texto(base["consultor"])
    base = base.drop_duplicates(subset="_key", keep="first")
    for frame, coluna in ((rec, "efetivadas"), (cobr, "cobranca_consignavel")):
        if frame.empty:
            base[coluna] = 0
            continue
        aux = frame[["consultor", coluna]].copy()
        aux["_key"] = _norm_texto(aux["consultor"])
        aux = (
            aux.drop(columns=["consultor"])
            .groupby("_key", as_index=False)
            .sum()
        )
        base = base.merge(aux, on="_key", how="left")

    base["efetivadas"] = base["efetivadas"].fillna(0).astype(int)
    base["cobranca_consignavel"] = (
        base["cobranca_consignavel"].fillna(0).astype(int)
    )
    return base.drop(columns=["_key"]).reset_index(drop=True)


COLS_ACELERADOR = [
    "consultor",
    "efetivadas",
    "cobranca_consignavel",
    "total_acelerador",
    "faixa_rotulo",
]


def faixas_acelerador_por_qtd(
    qtds,
    mes: int,
    ano: int,
    carregar_faixa_acelerador,
) -> Dict[int, str]:
    """Resolve o rotulo de cada contagem DISTINTA (1 RPC por valor unico).

    Uma chamada por consultor seria O(n) RPCs para pouquissimos valores
    distintos; o dedupe + cache mantem o custo em ~1 chamada por faixa.
    """
    unicos = sorted({int(q) for q in qtds})
    return {q: carregar_faixa_acelerador(q, mes, ano)["rotulo"] for q in unicos}


def faixa_agregada_acelerador(
    totais: Dict,
    mes: int,
    ano: int,
    carregar_faixa_acelerador,
) -> Optional[Dict]:
    """Faixa do total AGREGADO do escopo: `{rotulo, is_deflator}` ou None.

    Alimenta a barra-resumo, que so faz sentido para o perfil `consultor`
    — o premio do supervisor e por consultor individual, entao a soma da
    equipe enganaria. Quem decide exibir e a UI, por
    `totais["acelerador_perfil"]`. None = sem faixa resolvida (fora do
    gate ou periodo sem faixas): nao inventar faixa default.
    """
    if not totais.get("acelerador_no_escopo"):
        return None
    total = int(totais.get("efetivadas", 0) or 0) + int(
        totais.get("cobranca_consignavel", 0) or 0
    )
    faixa = carregar_faixa_acelerador(total, mes, ano)
    if not faixa.get("rotulo"):
        return None
    return {
        "rotulo": faixa["rotulo"],
        "is_deflator": bool(faixa.get("is_deflator")),
    }


def montar_acelerador_por_consultor(
    clientes: pd.DataFrame,
    contratos_consignavel: pd.DataFrame,
    df_sup: pd.DataFrame,
    universo_ativos: pd.DataFrame,
    resolver_faixas,
) -> pd.DataFrame:
    """Quebra do acelerador por consultor — a regra, sem a carga.

    Recebe tudo pronto e ja pos-RLS. Ate 09/2026 esta funcao carregava
    sozinha a cobranca consignavel, os supervisores e os consultores
    ativos, e aplicava RLS — responsabilidades que o chamador
    (`loaders.carregar_reconquista`) JA tinha. O resultado era
    `aplicar_rls(carregar_cobranca_consignavel(...))` acontecendo duas
    vezes por render, uma aqui e uma la. Puxar a carga para o
    orquestrador nao acrescentou responsabilidade a ele: consolidou uma
    que ja era dele e havia vazado para baixo.

    O GATE tambem saiu: quem decide se o acelerador detalhado se aplica
    ao perfil/periodo e `_acelerador_no_escopo`, que depende do usuario
    logado. O chamador so nao chama esta funcao quando esta fora do
    gate.

    Args:
        clientes: leads da Reconquista do mes (pos-RLS).
        contratos_consignavel: contratos de Cobranca Consignavel do mes
            (pos-RLS).
        df_sup: supervisores vigentes na competencia.
        universo_ativos: consultores ativos do escopo (pos-RLS), ainda
            COM supervisores — a exclusao acontece aqui.
        resolver_faixas: callable que recebe as contagens e devolve
            ``{qtd: rotulo}``; e o unico ponto que ainda toca o banco,
            e por isso chega injetado.

    Universo = SO consultores ativos, sem supervisor. Supervisor com
    producao propria vira linha separada, marcada "(Supervisor)" e
    sempre depois dos consultores reais.
    """
    vazio = pd.DataFrame(columns=COLS_ACELERADOR)
    cobr = _por_consultor_cobranca_consignavel(contratos_consignavel)

    rec = _por_consultor_reconquista(clientes)
    rec = (
        rec[["consultor", "efetivadas"]]
        if not rec.empty
        else pd.DataFrame(columns=["consultor", "efetivadas"])
    )

    sup_keys = (
        set(_norm_texto(df_sup["SUPERVISOR"]))
        if "SUPERVISOR" in df_sup.columns
        else set()
    )

    universo = excluir_supervisores(universo_ativos, df_sup)
    universo = (
        universo[["CONSULTOR"]].rename(columns={"CONSULTOR": "consultor"})
        if "CONSULTOR" in universo.columns
        else pd.DataFrame(columns=["consultor"])
    )

    # Universo = SO consultores ativos, sem supervisor. `rec`/`cobr` so
    # enriquecem contagem de quem ja esta no universo — nunca adicionam
    # linha nova aqui (o bloco de producao de supervisor e tratado a
    # parte, abaixo). Sem essa restricao, um consultor desligado com
    # cliente elegivel de reconquista no periodo (mesmo sem EFETIVADA,
    # so aparecer no frame ja basta) ou contrato de cobranca
    # consignavel pago no mes voltava a aparecer na tabela.
    cols_prod = ["consultor", "efetivadas", "cobranca_consignavel"]
    base = (
        _juntar_producao(universo, rec, cobr)
        if not universo.empty
        else pd.DataFrame(columns=cols_prod)
    )

    # Producao do proprio supervisor: so vira linha (marcada) se rec/cobr
    # tiver alguma contagem em nome dele; sem producao, fica de fora.
    bloco_sup = pd.DataFrame(columns=cols_prod)
    if sup_keys:
        candidatos = set()
        for frame in (rec, cobr):
            if not frame.empty:
                candidatos |= set(_norm_texto(frame["consultor"])) & sup_keys
        if candidatos:
            nomes_sup = (
                df_sup[["SUPERVISOR"]]
                .rename(columns={"SUPERVISOR": "consultor"})
                .drop_duplicates()
            )
            nomes_sup = nomes_sup[
                _norm_texto(nomes_sup["consultor"]).isin(candidatos)
            ]
            bloco_sup = _juntar_producao(nomes_sup, rec, cobr)
            bloco_sup = bloco_sup[
                (bloco_sup["efetivadas"] + bloco_sup["cobranca_consignavel"])
                > 0
            ].copy()

    if base.empty and bloco_sup.empty:
        return vazio

    for frame in (base, bloco_sup):
        frame["total_acelerador"] = (
            frame["efetivadas"] + frame["cobranca_consignavel"]
        )

    faixas = resolver_faixas(
        pd.concat([base["total_acelerador"], bloco_sup["total_acelerador"]])
    )
    base["faixa_rotulo"] = base["total_acelerador"].map(faixas).fillna("")
    bloco_sup["faixa_rotulo"] = (
        bloco_sup["total_acelerador"].map(faixas).fillna("")
    )
    bloco_sup["consultor"] = bloco_sup["consultor"] + " (Supervisor)"

    base = base.sort_values(
        ["total_acelerador", "consultor"], ascending=[False, True]
    )
    return (
        pd.concat([base, bloco_sup], ignore_index=True)[COLS_ACELERADOR]
        .reset_index(drop=True)
    )
