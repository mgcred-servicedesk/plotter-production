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

**A partir de 09/2026 (liga)** as Efetivadas deixam de vir daqui: sao a
contagem `qtde = 1` do arquivo da liga do banco no proprio mes, sem
defasagem (`liga_vigente`, `totais_liga`,
`efetivadas_por_consultor_liga`). O export segue como analitico.

**A partir de 09/2026 (Promessa Diaria, V3)** as Promessas do card vem
do arquivo do banco (view `v_reconquista_promessa`, migration 137), pelo
mes de `dt_promessa`, sem defasagem: `promessa_v3_vigente`,
`totais_promessa`, `marcar_efetivada` (badge pela liga),
`promessas_por_loja` e `promessas_por_consultor`.

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

# Primeira apuracao (ano, mes) contada pela LIGA (arquivo do banco,
# tabela `reconquista_liga`, migration 127). Antes dela, efetivadas
# saem do export (status EFETIVADA, defasagem de 1 mes).
_LIGA_INICIO = (2026, 9)

# Estados da liga no dict de `carregar_reconquista` (`liga_status`).
# Publicos: a UI decide a mensagem por eles, sem reescrever a regra.
LIGA_FORA = "fora"                    # apuracao < 09/2026: regra antiga
LIGA_OK = "ok"                        # liga do periodo importada
LIGA_NAO_IMPORTADA = "nao_importada"  # periodo sem linhas na liga
LIGA_ERRO = "erro"                    # falha ao ler a liga

# Primeira apuracao (ano, mes) com Promessas V3 (arquivo Promessa
# Diaria, tabela `reconquista_promessa`, migration 137). Constante
# propria de proposito: coincide hoje com `_LIGA_INICIO`, mas e outra
# regra. Antes dela, Promessas seguem do export (legado intocado).
_PROMESSA_V3_INICIO = (2026, 9)

# Estados da Promessa Diaria, analogos aos LIGA_*. NAO_IMPORTADA/ERRO
# => card "—" + aviso; nunca 0 nem o numero do export.
PROMESSA_FORA = "fora"                    # apuracao < 09/2026: export
PROMESSA_OK = "ok"                        # periodo importado
PROMESSA_NAO_IMPORTADA = "nao_importada"  # periodo sem linhas (pre-RLS)
PROMESSA_ERRO = "erro"                    # falha ao ler a promessa


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


def liga_vigente(mes: int, ano: int) -> bool:
    """A apuracao (mes, ano) e contada pela liga? So a data importa.

    Corte simples, como `_acelerador_vigente`: a partir de 09/2026 o
    indicador e a contagem do banco no proprio mes, sem defasagem.
    """
    return (ano, mes) >= _LIGA_INICIO


def _mask_contabilizada(liga: pd.DataFrame) -> pd.Series:
    """`qtde == 1` — o que o banco contabilizou. Qtde 0 fica so no
    analitico; valor ausente/ilegivel NAO conta."""
    if liga is None:
        return pd.Series([], dtype=bool)
    if "qtde" not in liga.columns:
        return pd.Series(False, index=liga.index, dtype=bool)
    return pd.to_numeric(liga["qtde"], errors="coerce").eq(1)


def totais_liga(liga: pd.DataFrame) -> Dict:
    """Contagem da liga do periodo (frame ja pos-RLS).

    `efetivadas` e o indicador; `liga_listadas`/`liga_nao_contabilizadas`
    sao contexto do card. Sem base total na liga, nao ha conversao.
    """
    if liga is None or liga.empty:
        return {
            "efetivadas": 0, "liga_listadas": 0,
            "liga_nao_contabilizadas": 0,
        }
    efet = int(_mask_contabilizada(liga).sum())
    return {
        "efetivadas": efet,
        "liga_listadas": len(liga),
        "liga_nao_contabilizadas": len(liga) - efet,
    }


def efetivadas_por_consultor_liga(liga: pd.DataFrame) -> pd.DataFrame:
    """`(consultor, efetivadas)` da liga — so `qtde == 1`.

    Mesmo formato que `montar_acelerador_por_consultor` extrai de
    `_por_consultor_reconquista`, para entrar no acelerador no lugar da
    contagem do export.
    """
    cols = ["consultor", "efetivadas"]
    if liga is None or liga.empty or "consultor" not in liga.columns:
        return pd.DataFrame(columns=cols)
    contab = liga[_mask_contabilizada(liga)]
    if contab.empty:
        return pd.DataFrame(columns=cols)
    return (
        contab.groupby("consultor", dropna=False)
        .size()
        .reset_index(name="efetivadas")
    )


# ══════════════════════════════════════════════════════
# Reconquista V3 — Promessa Diaria (a partir de 09/2026)
#
# Arquivo do banco, 1 linha por ADE (co_adesao) por periodo. Fonte:
# view `v_reconquista_promessa`. Periodo = mes de dt_promessa, SEM
# defasagem. Promessas = linhas `elegivel = true` (fluxo: inclui as
# que depois efetivaram); `retorno_inss` nao filtra a contagem. O
# badge "Efetivada" vem SO da liga. Ver docs/agents/business-rules.md.
# ══════════════════════════════════════════════════════

# Rotulos do arquivo, comparados SEM acento dos dois lados: o dado
# passa por `_rotulo_sem_acento` e as constantes ja sao escritas sem.
_RETORNO_ACEITO = "REGISTRO ACEITO"
_RETORNO_NAO_ACEITO = "NAO ACEITO"
_STATUS_FDR_E_PROMESSA = "FDR E PROMESSA"
_STATUS_SO_PROMESSA = "PROMESSA"


def promessa_v3_vigente(mes: int, ano: int) -> bool:
    """A apuracao (mes, ano) conta Promessas pela Promessa Diaria?

    Corte por data, como `liga_vigente`. Abaixo de 09/2026 vale o
    export (legado).
    """
    return (ano, mes) >= _PROMESSA_V3_INICIO


def _rotulo_sem_acento(serie: pd.Series) -> pd.Series:
    """Rotulo do arquivo -> chave sem acento (vazio/NaN -> "").

    `fillna` antes: `normalizar_rotulo` faz `astype(str)` e NaN de
    coluna object viraria o literal "NAN".
    """
    return normalizar_nome(serie.fillna("").astype(str))


def _mask_elegivel_promessa(df: pd.DataFrame) -> pd.Series:
    """`elegivel == True` (derivado na RPC). Nulo nao conta."""
    return df["elegivel"].eq(True)


def _badge_disponivel(df: pd.DataFrame) -> bool:
    """O badge (`marcar_efetivada`) esta no frame e sem NA?"""
    return "efetivada" in df.columns and not df["efetivada"].isna().any()


def _anotar_contadores_promessa(df: pd.DataFrame) -> pd.DataFrame:
    """Colunas 0/1 de retorno INSS e status — base das quebras."""
    out = df.copy()
    retorno = _rotulo_sem_acento(out["retorno_inss"])
    status = _rotulo_sem_acento(out["status_cliente_atual"])
    out["_aceito"] = retorno.eq(_RETORNO_ACEITO).astype(int)
    out["_pendente"] = retorno.eq("").astype(int)
    out["_nao_aceito"] = retorno.eq(_RETORNO_NAO_ACEITO).astype(int)
    out["_fdr"] = status.eq(_STATUS_FDR_E_PROMESSA).astype(int)
    out["_so_prom"] = status.eq(_STATUS_SO_PROMESSA).astype(int)
    return out


def totais_promessa(df: pd.DataFrame) -> Dict:
    """Card Promessas V3 do periodo (frame ja pos-RLS).

    `promessas` = elegiveis; o resto e contexto sobre elegiveis.
    Retorno INSS: pendente = vazio; valor fora dos dois rotulos
    conhecidos cai em `retorno_outros` (nao some em silencio).
    `efetivadas` = None quando o badge da liga nao esta disponivel —
    nunca 0 nesse caso. Sem variacao vs mes anterior (decisao V3).
    """
    vazio = {
        "promessas": 0, "nao_elegiveis": 0,
        "retorno_aceito": 0, "retorno_pendente": 0,
        "retorno_nao_aceito": 0, "retorno_outros": 0,
        "pct_retorno_aceito": 0.0,
        "fdr_e_promessa": 0, "so_promessa": 0,
        "efetivadas": 0,
    }
    if df is None or df.empty:
        return vazio

    mask = _mask_elegivel_promessa(df)
    eleg = _anotar_contadores_promessa(df[mask])
    promessas = len(eleg)
    aceito = int(eleg["_aceito"].sum())
    pendente = int(eleg["_pendente"].sum())
    nao_aceito = int(eleg["_nao_aceito"].sum())
    efetivadas = (
        int(eleg["efetivada"].astype(bool).sum())
        if _badge_disponivel(eleg)
        else None
    )
    return {
        "promessas": promessas,
        "nao_elegiveis": int(df["elegivel"].eq(False).sum()),
        "retorno_aceito": aceito,
        "retorno_pendente": pendente,
        "retorno_nao_aceito": nao_aceito,
        "retorno_outros": promessas - aceito - pendente - nao_aceito,
        "pct_retorno_aceito": (
            aceito / promessas * 100 if promessas else 0.0
        ),
        "fdr_e_promessa": int(eleg["_fdr"].sum()),
        "so_promessa": int(eleg["_so_prom"].sum()),
        "efetivadas": efetivadas,
    }


def marcar_efetivada(
    promessas: pd.DataFrame, liga: Optional[pd.DataFrame]
) -> pd.DataFrame:
    """Badge "Efetivada MM/AAAA": cruza a promessa com a liga por ADE.

    Efetivada = ADE na liga com `qtde = 1` num periodo (ano, mes) >=
    o da promessa; `efetivada_ref` e o primeiro desses periodos. A liga
    precisa cobrir os periodos posteriores, nao so o selecionado.

    `liga=None` (falha de leitura) => `efetivada` = NA ("indisponivel"),
    nunca False. Liga lida e vazia => False (sem cruzamento).
    """
    if promessas is None:
        return pd.DataFrame()
    df = promessas.copy()

    if liga is None:
        df["efetivada"] = pd.Series(pd.NA, index=df.index, dtype="boolean")
        df["efetivada_ref"] = pd.Series(None, index=df.index, dtype=object)
        return df

    df["efetivada"] = pd.Series(False, index=df.index, dtype="boolean")
    df["efetivada_ref"] = pd.Series(None, index=df.index, dtype=object)
    if df.empty or liga.empty:
        return df

    contab = liga[_mask_contabilizada(liga)]
    if contab.empty:
        return df
    lado_liga = pd.DataFrame({
        "_ade": pd.to_numeric(contab["co_adesao"], errors="coerce"),
        "_chave_liga": (
            pd.to_numeric(contab["ano"], errors="coerce") * 12
            + pd.to_numeric(contab["mes"], errors="coerce")
        ),
    }).dropna()
    lado_prom = pd.DataFrame({
        "_linha": range(len(df)),
        "_ade": pd.to_numeric(df["co_adesao"], errors="coerce").to_numpy(),
        "_chave_prom": (
            pd.to_numeric(df["ano"], errors="coerce") * 12
            + pd.to_numeric(df["mes"], errors="coerce")
        ).to_numpy(),
    }).dropna()

    cruz = lado_prom.merge(lado_liga, on="_ade", how="inner")
    cruz = cruz[cruz["_chave_liga"] >= cruz["_chave_prom"]]
    if cruz.empty:
        return df
    primeira = cruz.groupby("_linha")["_chave_liga"].min().astype(int)

    posicoes = primeira.index.to_numpy()
    col_efet = df.columns.get_loc("efetivada")
    col_ref = df.columns.get_loc("efetivada_ref")
    df.iloc[posicoes, col_efet] = True
    df.iloc[posicoes, col_ref] = _rotulo_mes(primeira).to_numpy()
    return df


def _quebra_promessa(df: pd.DataFrame, chaves) -> pd.DataFrame:
    """Agrega elegiveis por `chaves`: promessas, retorno INSS, status e
    efetivadas (NA na coluna quando o badge nao esta disponivel)."""
    eleg = _anotar_contadores_promessa(df[_mask_elegivel_promessa(df)])
    if eleg.empty:
        return pd.DataFrame()
    badge = _badge_disponivel(eleg)
    eleg["_efet"] = eleg["efetivada"].astype(bool).astype(int) if badge else 0
    g = (
        eleg.groupby(chaves, dropna=False)
        .agg(
            promessas=("co_adesao", "count"),
            retorno_aceito=("_aceito", "sum"),
            retorno_pendente=("_pendente", "sum"),
            retorno_nao_aceito=("_nao_aceito", "sum"),
            fdr_e_promessa=("_fdr", "sum"),
            so_promessa=("_so_prom", "sum"),
            efetivadas=("_efet", "sum"),
        )
        .reset_index()
    )
    g["efetivadas"] = (
        g["efetivadas"].astype("Int64")
        if badge
        else pd.array([pd.NA] * len(g), dtype="Int64")
    )
    return g.sort_values(
        ["promessas", *chaves], ascending=[False, *([True] * len(chaves))]
    ).reset_index(drop=True)


def promessas_por_loja(df: pd.DataFrame) -> pd.DataFrame:
    """Quebra por loja/regiao sobre as elegiveis (frame pos-RLS).

    Conta TODAS as elegiveis, inclusive as em nome de supervisor —
    a exclusao vale so para a visao por pessoa.
    """
    if df is None or df.empty or "loja" not in df.columns:
        return pd.DataFrame()
    return _quebra_promessa(df, ["loja", "regiao"])


SUFIXO_SEM_CONSULTOR = " · sem consultor identificado"
ROTULO_SEM_SUPERVISOR = "Sem supervisor vigente · {loja}"


def _responsavel_sem_consultor(
    nao_ident: pd.DataFrame, df_sup: Optional[pd.DataFrame]
) -> pd.Series:
    """Rotulo da linha que recebe o lead sem consultor identificado.

    Supervisor VIGENTE da loja da promessa no cadastro (`df_sup`, colunas
    SUPERVISOR/LOJA de `carregar_supervisores(mes, ano)`). Loja com mais
    de um supervisor vigente junta os nomes; loja sem nenhum cai num
    rotulo explicito por loja — o lead nunca some.
    """
    sup_por_loja: Dict[str, str] = {}
    if df_sup is not None and not df_sup.empty and {
        "SUPERVISOR", "LOJA"
    } <= set(df_sup.columns):
        vig = df_sup.dropna(subset=["SUPERVISOR", "LOJA"])
        chave = normalizar_nome(vig["LOJA"].astype(str))
        for loja_norm, nomes in vig.groupby(chave)["SUPERVISOR"]:
            sup_por_loja[loja_norm] = " / ".join(sorted(set(nomes)))

    lojas = nao_ident["loja"].fillna("").astype(str)
    return pd.Series(
        [
            sup_por_loja[norm] + SUFIXO_SEM_CONSULTOR
            if norm in sup_por_loja
            else ROTULO_SEM_SUPERVISOR.format(loja=loja)
            for loja, norm in zip(lojas, normalizar_nome(lojas))
        ],
        index=nao_ident.index,
        dtype=object,
    )


def promessas_por_consultor(
    df: pd.DataFrame, df_sup: Optional[pd.DataFrame]
) -> pd.DataFrame:
    """Quebra por consultor sobre as elegiveis, SEM supervisores.

    Criterio de supervisor = cadastro (`df_sup`, coluna SUPERVISOR, de
    `carregar_supervisores(mes, ano)`), nao a coluna `supervisor` do
    arquivo. Agrega por NOME, como `_por_consultor_reconquista`.

    Lead com consultor NAO identificado (`consultor_identificado` False,
    migration 138) vai para o supervisor vigente da loja atuar: linha
    "<SUPERVISOR> · sem consultor identificado", so com esses leads —
    unica excecao a exclusao de supervisor. A classificacao vem ANTES da
    exclusao: nome nao resolvido na loja da promessa (mesmo que seja de
    um supervisor de outra loja) e lead da loja, nao da pessoa. Sem a
    coluna levanta KeyError (falha explicita; o loader trata).
    """
    if df is None or df.empty or "consultor" not in df.columns:
        return pd.DataFrame()
    identificado = df["consultor_identificado"].eq(True)
    ident = df[identificado]
    nao_ident = df[~identificado].copy()

    # `excluir_supervisores` casa pela coluna CONSULTOR: renomeia so
    # para a chamada e devolve o nome do frame da view.
    sem_sup = excluir_supervisores(
        ident.rename(columns={"consultor": "CONSULTOR"}), df_sup
    ).rename(columns={"CONSULTOR": "consultor"})
    if not nao_ident.empty:
        nao_ident["consultor"] = _responsavel_sem_consultor(nao_ident, df_sup)

    base = pd.concat([sem_sup, nao_ident])
    if base.empty:
        return pd.DataFrame()
    return _quebra_promessa(base, ["consultor"])


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
    efetivadas_por_consultor: Optional[pd.DataFrame] = None,
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
        efetivadas_por_consultor: ``(consultor, efetivadas)`` ja
            contado — a partir de 09/2026 vem da liga
            (`efetivadas_por_consultor_liga`). Quando informado,
            substitui a contagem de EFETIVADA de `clientes`.

    Universo = SO consultores ativos, sem supervisor. Supervisor com
    producao propria vira linha separada, marcada "(Supervisor)" e
    sempre depois dos consultores reais.
    """
    vazio = pd.DataFrame(columns=COLS_ACELERADOR)
    cobr = _por_consultor_cobranca_consignavel(contratos_consignavel)

    rec = (
        efetivadas_por_consultor
        if efetivadas_por_consultor is not None
        else _por_consultor_reconquista(clientes)
    )
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
