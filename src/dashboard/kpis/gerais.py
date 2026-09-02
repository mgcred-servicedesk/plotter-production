"""
KPIs gerais do dashboard + helpers compartilhados entre
os modulos de KPI.

Este modulo hospeda ``excluir_supervisores``,
``contar_consultores`` e ``mascaras_aceleradores``, que sao
reusados por ``produtos.py``, ``regioes.py``,
``rankings.py``, ``gestao.py`` e ``evolucao.py``.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, MutableMapping, NamedTuple, Optional

import pandas as pd

from src.config.settings import PRODUTOS_EMISSAO
from src.shared.dias_uteis import calcular_dias_uteis


# Mapeamento de produtos do dashboard para categoria_codigo
# (taxonomia oriunda da tabela categorias_produto no Supabase).
PRODUTOS_DASHBOARD = {
    "CNC": ["CNC", "SUPER_CONTA"],  # CNC inclui Super Conta
    "CLT": ["CONSIG_PRIV"],  # CLT = CONSIG PRIVADO
    "SAQUE": ["SAQUE", "SAQUE_BENEFICIO"],
    "CONSIGNADO": ["CONSIG_BMG", "CONSIG_ITAU", "CONSIG_C6"],
    "FGTS_ANT_BEN_CNC13": ["FGTS", "ANT_BENEF", "CNC_13"],
}

# Mapeia produto_display do dashboard → nome da coluna na tabela `metas`.
# Usado para casamento determinístico (sem fuzzy match por substring), que
# antes confundia colunas com nomes parecidos (ex.: meta `FGTS` independente
# sendo somada na categoria FGTS_ANT_BEN_CNC13).
PRODUTOS_DASHBOARD_COL_META: Dict[str, str] = {
    "CNC": "CNC",
    "CLT": "CLT",
    "SAQUE": "SAQUE",
    "CONSIGNADO": "CONSIGNADO",
    "FGTS_ANT_BEN_CNC13": "FGTS_ANT_BENEF_13",
}


def excluir_supervisores(
    df: pd.DataFrame,
    df_sup: Optional[pd.DataFrame],
) -> pd.DataFrame:
    """Remove supervisores do DataFrame de vendas."""
    if (
        df_sup is not None
        and "SUPERVISOR" in df_sup.columns
        and "CONSULTOR" in df.columns
    ):
        supervisores = df_sup["SUPERVISOR"].unique()
        return df[~df["CONSULTOR"].isin(supervisores)].copy()
    return df.copy()


# Lojas de backoffice (digitação): a produção paga é repassada ao
# consultor de loja que iniciou a negociação, então esses consultores
# ficam fora de rankings, listagem de zerados e médias por
# consultor/loja. Contratos cancelados e em análise NÃO passam por este
# filtro (regra de negócio: nessas somas o Vai e Vem conta normalmente).
LOJAS_BACKOFFICE: frozenset = frozenset({"VAI E VEM"})


def peso_headcount_escopo(
    df_headcount: Optional[pd.DataFrame],
    consultor_selecionado: str = "",
) -> Optional[float]:
    """Soma o peso do headcount ponderado no escopo ja recortado.

    ``df_headcount`` vem de ``carregar_headcount_ponderado`` DEPOIS de
    ``aplicar_rls`` e dos filtros da sidebar. O escopo sai do FILTRO, nao
    da producao: loja dentro do escopo entra no denominador mesmo sem
    nenhum contrato no periodo. E o mesmo principio de
    ``aplicar_rls_metas`` — usar a presenca de contrato como proxy de
    escopo reintroduziria exatamente o vies que este denominador existe
    para corrigir (quem nao vendeu sumir da conta).

    Devolve ``None`` quando nao ha denominador ponderado confiavel, e o
    chamador cai no comportamento antigo:

    - frame vazio ou ausente (loader indisponivel, competencia sem
      ledger);
    - **um consultor selecionado na sidebar** — a 091 agrega por LOJA e
      nao existe peso por pessoa, entao restringir a uma pessoa deixaria
      o denominador da loja inteira contra a producao de um so. O card
      volta a dividir por quem produziu, que com um filtro de consultor
      e a propria pessoa.
    """
    if consultor_selecionado:
        return None
    if df_headcount is None or df_headcount.empty:
        return None
    if "PESO" not in df_headcount.columns:
        return None
    peso = float(
        pd.to_numeric(df_headcount["PESO"], errors="coerce").fillna(0.0).sum()
    )
    return peso if peso > 0 else None


def excluir_lojas_backoffice(df: pd.DataFrame) -> pd.DataFrame:
    """Remove linhas de lojas de backoffice (match por LOJA normalizada)."""
    if df.empty or "LOJA" not in df.columns:
        return df.copy()
    lojas_norm = (
        df["LOJA"].fillna("").astype(str).str.strip().str.upper()
    )
    return df[~lojas_norm.isin(LOJAS_BACKOFFICE)].copy()


# Janela do pipeline: "em analise" e "cancelados" so consideram o que
# foi cadastrado nos ultimos N dias CORRIDOS (nao uteis). Os dois
# conjuntos vem do sistema de origem sem expurgo, entao registros
# antigos e parados distorceriam o pipeline e o churn do periodo.
JANELA_PIPELINE_DIAS: int = 30


def filtrar_janela_recente(
    df: pd.DataFrame,
    dias: int = JANELA_PIPELINE_DIAS,
    referencia: Optional[datetime] = None,
) -> pd.DataFrame:
    """Mantem so as linhas com ``DATA_CADASTRO`` nos ultimos ``dias``.

    Corte = ``referencia - dias`` (``referencia`` default ``now()``),
    comparacao inclusiva (``>=``). ``referencia`` explicita serve para
    aplicar o MESMO instante a varios DataFrames e para tornar a funcao
    deterministica em teste.

    ``DATA_CADASTRO`` e datetime garantido pelo loader (``pd.to_datetime``
    com ``errors='coerce'``); linhas com data nula (``NaT``) nunca
    satisfazem a comparacao e portanto saem. df vazio ou sem a coluna
    devolve copia inalterada.
    """
    if df.empty or "DATA_CADASTRO" not in df.columns:
        return df.copy()
    agora = referencia if referencia is not None else datetime.now()
    corte = agora - timedelta(days=dias)
    return df[df["DATA_CADASTRO"] >= corte].copy()


# Aceleradores: recortes que contam por QUANTIDADE de contratos, nao
# por valor. BMG Med, Vida Familiar e Emissao chegam com VALOR = 0 da
# consolidacao (conta_valor=false / regra de emissao), entao qualquer
# leitura que filtre VALOR > 0 antes de conta-los devolve zero — quem
# consome estas mascaras precisa aplica-las no df COMPLETO.
#
# SUPER CONTA e a excecao e merece atencao: alem de acelerador, ela E
# CNC em valor (``PRODUTOS_DASHBOARD['CNC']`` inclui SUPER_CONTA, e a
# consolidacao registra "conta valor/pontos como CNC e tambem e
# contado como producao Super Conta"). Ou seja, contar Super Conta
# aqui NAO tira o dinheiro dela do CNC — a mascara e so contagem.
ACELERADORES: tuple = (
    "BMG Med", "Vida Familiar", "Emissao", "Super Conta",
)


def mascaras_aceleradores(df: pd.DataFrame) -> Dict[str, pd.Series]:
    """Mascara booleana de cada acelerador sobre as linhas de ``df``.

    Fonte unica da definicao, compartilhada por rankings e pela aba de
    Gestao: se as duas superficies divergirem sobre o que e um "BMG
    Med", passam a discordar sobre o mesmo consultor.

    Coluna ausente vira mascara toda falsa (nunca KeyError) — df
    parcial e caso normal em testes e em periodos sem consolidacao.
    """
    falso = pd.Series(False, index=df.index)

    def _flag(col: str) -> pd.Series:
        if col not in df.columns:
            return falso
        return df[col].fillna(False).astype(bool)

    if "TIPO_PRODUTO" in df.columns:
        emissao = df["TIPO_PRODUTO"].str.upper().isin(
            {p.upper() for p in PRODUTOS_EMISSAO}
        )
    else:
        emissao = falso

    # Prefere a flag canonica derivada na consolidacao; o fallback por
    # SUBTIPO cobre df parcial (testes, periodo sem consolidacao) e usa
    # exatamente a mesma normalizacao (strip + upper).
    if "is_super_conta" in df.columns:
        super_conta = _flag("is_super_conta")
    elif "SUBTIPO" in df.columns:
        super_conta = (
            df["SUBTIPO"].astype(str).str.strip().str.upper()
            == "SUPER CONTA"
        )
    else:
        super_conta = falso

    return {
        "BMG Med": _flag("is_bmg_med"),
        "Vida Familiar": _flag("is_seguro_vida"),
        "Emissao": emissao,
        "Super Conta": super_conta,
    }


def contar_consultores(
    df: pd.DataFrame,
    df_sup: Optional[pd.DataFrame],
) -> int:
    """Conta consultores excluindo supervisores."""
    if "CONSULTOR" not in df.columns:
        return 0
    consultores = df["CONSULTOR"].unique()
    if df_sup is not None and "SUPERVISOR" in df_sup.columns:
        supervisores = df_sup["SUPERVISOR"].unique()
        consultores = [c for c in consultores if c not in supervisores]
    return len(consultores)


def calcular_kpis_gerais(
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    df_metas_produto: pd.DataFrame,
    ano: int,
    mes: int,
    dia_atual: Optional[int] = None,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> Dict:
    """Calcula KPIs gerais do dashboard."""
    du_total, du_dec, du_rest = calcular_dias_uteis(ano, mes, dia_atual)

    total_vendas = df["VALOR"].sum()
    total_pontos = df["pontos"].sum()
    total_transacoes = len(
        df[df["VALOR"] > 0]
    )

    # Metas GERAL (escopo LOJA, produto GERAL)
    meta_prata = 0
    meta_ouro = 0
    if "META_PRATA" in df_metas.columns:
        meta_prata = (
            pd.to_numeric(
                df_metas["META_PRATA"], errors="coerce"
            ).fillna(0).sum()
        )
    if "META_OURO" in df_metas.columns:
        meta_ouro = (
            pd.to_numeric(
                df_metas["META_OURO"], errors="coerce"
            ).fillna(0).sum()
        )

    # Meta MIX: coluna "MIX" para escopo LOJA, ou soma dos produtos
    # componentes para escopo CONSULTOR (que não tem linha MIX no banco).
    # Os componentes vêm do mapeamento canônico produto_display → coluna do
    # banco, garantindo que `_MIX_COMPONENTES` fique sempre em sincronia.
    _MIX_COMPONENTES = list(PRODUTOS_DASHBOARD_COL_META.values())
    meta_mix = 0
    if not df_metas_produto.empty:
        if "MIX" in df_metas_produto.columns:
            meta_mix = (
                pd.to_numeric(df_metas_produto["MIX"], errors="coerce")
                .fillna(0)
                .sum()
            )
        else:
            for _col in _MIX_COMPONENTES:
                if _col in df_metas_produto.columns:
                    meta_mix += (
                        pd.to_numeric(df_metas_produto[_col], errors="coerce")
                        .fillna(0)
                        .sum()
                    )

    perc_prata = (
        (total_pontos / meta_prata * 100)
        if meta_prata > 0 else 0
    )
    perc_ouro = (
        (total_pontos / meta_ouro * 100)
        if meta_ouro > 0 else 0
    )

    media_du = total_vendas / du_dec if du_dec > 0 else 0
    media_du_pts = total_pontos / du_dec if du_dec > 0 else 0
    meta_diaria_pts = meta_prata / du_total if du_total > 0 else 0
    gap_pontos = max(0, meta_prata - total_pontos)
    meta_diaria_restante_pts = gap_pontos / du_rest if du_rest > 0 else 0
    projecao = media_du * du_total
    projecao_pts = media_du_pts * du_total
    perc_proj = (projecao_pts / meta_prata * 100) if meta_prata > 0 else 0
    ticket_medio = total_vendas / total_transacoes if total_transacoes > 0 else 0

    num_consultores = 0
    if "CONSULTOR" in df.columns:
        consultores_unicos = df["CONSULTOR"].unique()
        if df_supervisores is not None and \
                "SUPERVISOR" in df_supervisores.columns:
            supervisores = df_supervisores["SUPERVISOR"].unique()
            consultores_unicos = [
                c for c in consultores_unicos if c not in supervisores
            ]
        num_consultores = len(consultores_unicos)

    qtd_super_conta = (
        int(df["is_super_conta"].sum())
        if "is_super_conta" in df.columns
        else 0
    )
    qtd_emissao_cartao = (
        int(df["is_emissao_cartao"].sum())
        if "is_emissao_cartao" in df.columns
        else 0
    )
    qtd_bmg_med = (
        int(df["is_bmg_med"].sum())
        if "is_bmg_med" in df.columns
        else 0
    )
    qtd_seguro_vida = (
        int(df["is_seguro_vida"].sum())
        if "is_seguro_vida" in df.columns
        else 0
    )

    return {
        "total_vendas": total_vendas,
        "total_pontos": total_pontos,
        "total_transacoes": total_transacoes,
        "meta_prata": meta_prata,
        "meta_ouro": meta_ouro,
        "meta_mix": meta_mix,  # Nova meta MIX por produto
        "meta_diaria": meta_diaria_pts,  # Alias para evolucao.py
        "meta_diaria_pts": meta_diaria_pts,
        "meta_diaria_restante_pts": meta_diaria_restante_pts,
        "perc_ating_prata": perc_prata,
        "perc_ating_ouro": perc_ouro,
        "media_du": media_du,
        "media_du_pontos": media_du_pts,
        "projecao": projecao,
        "projecao_pontos": projecao_pts,
        "perc_proj": perc_proj,
        "ticket_medio": ticket_medio,
        "du_total": du_total,
        "du_decorridos": du_dec,
        "du_restantes": du_rest,
        "num_lojas": (df["LOJA"].nunique() if "LOJA" in df.columns else 0),
        "num_consultores": num_consultores,
        "num_regioes": (df["REGIAO"].nunique() if "REGIAO" in df.columns else 0),
        "qtd_super_conta": qtd_super_conta,
        "qtd_emissao_cartao": qtd_emissao_cartao,
        "qtd_bmg_med": qtd_bmg_med,
        "qtd_seguro_vida": qtd_seguro_vida,
    }


def calcular_kpis_analise(
    df_analise: pd.DataFrame,
    df: pd.DataFrame,
    du_decorridos: int,
) -> Dict:
    """Calcula KPIs relacionados a contratos em analise."""
    if df_analise.empty:
        return {
            "valor_analise": 0,
            "qtd_analise": 0,
            "ticket_medio_analise": 0,
            "media_diaria_analise": 0,
            "variacao_analise": 0,
        }

    valor_analise = df_analise["VALOR"].sum()
    qtd_analise = len(df_analise)
    ticket_medio_analise = (
        valor_analise / qtd_analise if qtd_analise > 0 else 0
    )

    # Media diaria de contratos em analise
    media_diaria_analise = (
        valor_analise / du_decorridos if du_decorridos > 0 else 0
    )

    # Valor total digitado no mes = pagos + pipeline em analise.
    # Denominador de `variacao_analise` apenas — nao e exibido como
    # producao. Soma DUAS definicoes de valor: `df` (pagos) vem
    # consolidado (VLR BRUTO na Cobranca Consignavel, migration 067) e
    # `df_analise` segue em VLR BASE, porque a regra vale so para pagos
    # (ver business-rules.md "Producao pelo VLR BRUTO"). O efeito e de
    # centesimo de ponto percentual e a direcao e conservadora — o
    # pipeline nunca infla a variacao.
    valor_total_digitado = df["VALOR"].sum() + valor_analise

    # Variacao = % do valor em analise vs media do total digitado
    media_diaria_total = (
        valor_total_digitado / du_decorridos
        if du_decorridos > 0
        else 0
    )
    variacao_analise = (
        (media_diaria_analise / media_diaria_total * 100)
        if media_diaria_total > 0
        else 0
    )

    return {
        "valor_analise": valor_analise,
        "qtd_analise": qtd_analise,
        "ticket_medio_analise": ticket_medio_analise,
        "media_diaria_analise": media_diaria_analise,
        "variacao_analise": variacao_analise,
    }


def separar_cancelados_liquidos(
    df_cancelados: pd.DataFrame,
) -> tuple:
    """Separa cancelados pela coluna ``CLASSIFICACAO``.

    Retorna ``(df_liquidos, qtd_redigitadas, qtd_recuperadas)``.
    Cancelados ``liquido`` sao os que contam de fato; ``redigitada``
    (superada por redigitacao em 7 dias) e ``recuperada`` (paga em
    7 dias) saem da contagem.

    Retrocompat: sem a coluna ``CLASSIFICACAO`` (RPC antiga), tudo
    e tratado como liquido.
    """
    if df_cancelados.empty or "CLASSIFICACAO" not in df_cancelados.columns:
        return df_cancelados, 0, 0

    classif = df_cancelados["CLASSIFICACAO"].fillna("liquido")
    df_liquidos = df_cancelados[classif == "liquido"]
    qtd_redigitadas = int((classif == "redigitada").sum())
    qtd_recuperadas = int((classif == "recuperada").sum())
    return df_liquidos, qtd_redigitadas, qtd_recuperadas


def calcular_kpis_cancelados(
    df_cancelados: pd.DataFrame,
    df: pd.DataFrame,
    df_analise: pd.DataFrame,
) -> Dict:
    """Calcula KPIs relacionados a contratos cancelados.

    Conta apenas os cancelados ``liquido`` (ver
    ``separar_cancelados_liquidos``); redigitadas e recuperadas
    saem do valor/qtd/churn e voltam como contexto no dict.
    """
    if df_cancelados.empty:
        return {
            "valor_cancelados": 0,
            "qtd_cancelados": 0,
            "indice_perda": 0,
            "qtd_bruto": 0,
            "qtd_redigitadas": 0,
            "qtd_recuperadas": 0,
        }

    qtd_bruto = len(df_cancelados)
    df_liquidos, qtd_redigitadas, qtd_recuperadas = (
        separar_cancelados_liquidos(df_cancelados)
    )

    valor_cancelados = df_liquidos["VALOR"].sum()
    qtd_cancelados = len(df_liquidos)

    # Indice de perda (churn) = Cancelados liquidos /
    # (Pagos + Cancelados liquidos + Em Analise)
    qtd_pagos = len(df)
    qtd_analise = len(df_analise) if not df_analise.empty else 0
    total_propostas = qtd_pagos + qtd_cancelados + qtd_analise

    indice_perda = (
        (qtd_cancelados / total_propostas * 100)
        if total_propostas > 0
        else 0
    )

    return {
        "valor_cancelados": valor_cancelados,
        "qtd_cancelados": qtd_cancelados,
        "indice_perda": indice_perda,
        "qtd_bruto": qtd_bruto,
        "qtd_redigitadas": qtd_redigitadas,
        "qtd_recuperadas": qtd_recuperadas,
    }


def calcular_assertividade_consultores(
    df_cancelados: pd.DataFrame,
    df: pd.DataFrame,
    df_analise: pd.DataFrame,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> Dict:
    """Assertividade dos consultores no cenario de redigitacao.

    ``assertividade = (1 - redigitadas / total_propostas) * 100``,
    onde ``redigitadas`` sao cancelados ``CLASSIFICACAO=='redigitada''``
    e ``total_propostas`` = pagas + em analise + canceladas (bruto)
    do consultor no periodo. Supervisores sao excluidos.

    Retorna metricas org-level + DataFrame por consultor (ordenado
    da menor assertividade para a maior, para evidenciar onde agir).

    Nota: as fontes (pagas/analise/cancelados) usam janelas de carga
    distintas, entao ``total_propostas`` e uma aproximacao do periodo.
    """
    def _qtd_por_consultor(frame: Optional[pd.DataFrame]) -> pd.Series:
        if (
            frame is None
            or frame.empty
            or "CONSULTOR" not in frame.columns
        ):
            return pd.Series(dtype="int64")
        limpo = excluir_supervisores(frame, df_supervisores)
        if limpo.empty:
            return pd.Series(dtype="int64")
        return limpo.groupby("CONSULTOR").size()

    pagos_c = _qtd_por_consultor(df)
    analise_c = _qtd_por_consultor(df_analise)
    cancel_c = _qtd_por_consultor(df_cancelados)

    # Redigitadas atribuidas ao consultor que as digitou.
    if (
        not df_cancelados.empty
        and "CONSULTOR" in df_cancelados.columns
        and "CLASSIFICACAO" in df_cancelados.columns
    ):
        df_redig = df_cancelados[
            df_cancelados["CLASSIFICACAO"] == "redigitada"
        ]
        redig_c = _qtd_por_consultor(df_redig)
    else:
        redig_c = pd.Series(dtype="int64")

    total_c = (
        pagos_c.add(analise_c, fill_value=0)
        .add(cancel_c, fill_value=0)
    )

    vazio = pd.DataFrame(
        columns=[
            "CONSULTOR",
            "total_propostas",
            "redigitadas",
            "assertividade",
        ]
    )
    if total_c.empty:
        return {
            "assertividade_org": 100.0,
            "total_redigitadas": 0,
            "total_propostas": 0,
            "por_consultor": vazio,
        }

    por_consultor = pd.DataFrame(
        {
            "CONSULTOR": total_c.index,
            "total_propostas": total_c.values.astype(int),
        }
    )
    por_consultor["redigitadas"] = (
        por_consultor["CONSULTOR"].map(redig_c).fillna(0).astype(int)
    )
    por_consultor["assertividade"] = (
        1 - por_consultor["redigitadas"] / por_consultor["total_propostas"]
    ) * 100
    por_consultor = por_consultor.sort_values(
        "assertividade"
    ).reset_index(drop=True)

    total_propostas = int(total_c.sum())
    total_redigitadas = int(redig_c.sum()) if not redig_c.empty else 0
    assertividade_org = (
        (1 - total_redigitadas / total_propostas) * 100
        if total_propostas > 0
        else 100.0
    )

    return {
        "assertividade_org": assertividade_org,
        "total_redigitadas": total_redigitadas,
        "total_propostas": total_propostas,
        "por_consultor": por_consultor,
    }


def calcular_oportunidades_perdidas(
    df_cancelados: pd.DataFrame,
    coluna_flag: str = "RECUPERADA_OUTRO",
) -> Dict:
    """Oportunidades perdidas (venda capturada em outro nivel).

    Cancelados cuja venda (mesmo cliente+categoria em 7 dias) foi
    capturada fora do proprio nivel — venda perdida do ponto de vista
    de quem cancelou. ``coluna_flag`` seleciona o nivel:
    ``RECUPERADA_OUTRO`` (outro consultor), ``RECUPERADA_OUTRA_LOJA``
    (outra loja) ou ``RECUPERADA_OUTRA_REGIAO`` (outra regiao). A
    identidade de quem capturou NAO e exposta: so qtd e valor.

    Deve ser chamada APOS o RLS client-side (``aplicar_rls``), para
    refletir o escopo do usuario.
    """
    if (
        df_cancelados.empty
        or coluna_flag not in df_cancelados.columns
    ):
        return {"qtd_perdidas": 0, "valor_perdido": 0.0}

    perdidas = df_cancelados[
        df_cancelados[coluna_flag] == True  # noqa: E712
    ]
    valor = (
        float(perdidas["VALOR"].sum())
        if "VALOR" in perdidas.columns
        else 0.0
    )
    return {
        "qtd_perdidas": int(len(perdidas)),
        "valor_perdido": valor,
    }


def calcular_medias_du_por_nivel(
    df: pd.DataFrame,
    du_decorridos: int,
    df_supervisores: Optional[pd.DataFrame] = None,
    peso_headcount: Optional[float] = None,
) -> Dict:
    """Calcula medias DU por loja e por consultor.

    Exclui supervisores e lojas de backoffice (``LOJAS_BACKOFFICE``) —
    ambos distorceriam as médias por nível.

    ``peso_headcount`` e o denominador PONDERADO da competencia
    (``fn_headcount_ponderado``, migration 091), somado no escopo pelo
    chamador via ``peso_headcount_escopo``. E a mesma fonte que o Caderno
    divide em ``weightedHeadcount``. ``None`` cai no denominador antigo
    (quem produziu), e ``denominador_consultores`` no retorno diz qual
    dos dois valeu.
    """
    df_sem_sup = excluir_lojas_backoffice(
        excluir_supervisores(df, df_supervisores)
    )

    # Media DU por loja
    num_lojas = 0
    if "LOJA" in df_sem_sup.columns and not df_sem_sup.empty:
        vendas_por_loja = df_sem_sup.groupby("LOJA")["VALOR"].sum()
        num_lojas = len(vendas_por_loja)
        media_du_loja = (
            vendas_por_loja.mean() / du_decorridos
            if du_decorridos > 0
            else 0
        )
    else:
        media_du_loja = 0

    # Media DU por consultor — DENOMINADOR PONDERADO.
    #
    # Ate 2026-08-25 o denominador era quem PRODUZIU no periodo, e essa
    # era a razao de dashboard e Caderno nunca fecharem. Nao pela
    # diferenca de tamanho (em 07/2026 eram ~110 produtores contra peso
    # 112,48), e sim pela DIRECAO: excluir quem nao vendeu faz a media
    # SUBIR justamente no mes em que mais gente nao vendeu, enquanto a do
    # Caderno DESCE. Os dois numeros andavam em sentidos opostos, entao
    # nenhuma reconciliacao era possivel.
    #
    # Agora divide pelo gente-mes da competencia — mesma fonte, mesmos
    # filtros e mesma aritmetica do `weightedHeadcount` do Caderno.
    #
    # `num_consultores` continua sendo a contagem de produtores, agora
    # como diagnostico: e o mesmo movimento que a 092 fez do outro lado,
    # onde a contagem de cadastro virou `countedInRegistry`. Ver a
    # diferenca entre os dois e o que expoe a patologia.
    num_consultores = 0
    total_consultores = 0.0
    if "CONSULTOR" in df_sem_sup.columns and not df_sem_sup.empty:
        vendas_por_consultor = df_sem_sup.groupby("CONSULTOR")["VALOR"].sum()
        num_consultores = len(vendas_por_consultor)
        total_consultores = float(vendas_por_consultor.sum())

    if peso_headcount is not None and peso_headcount > 0:
        denominador = float(peso_headcount)
        origem = "peso"
    else:
        # Fallback identico ao comportamento anterior: soma/len e a
        # media aritmetica que `.mean()` calculava.
        denominador = float(num_consultores)
        origem = "produtores"

    media_du_consultor = (
        total_consultores / denominador / du_decorridos
        if du_decorridos > 0 and denominador > 0
        else 0
    )

    return {
        "media_du_loja": media_du_loja,
        "media_du_consultor": media_du_consultor,
        "num_lojas": num_lojas,
        "num_consultores": num_consultores,
        # Producao da populacao CONSULTOR (sem supervisor, sem
        # backoffice) — o numerador que casa com o denominador acima.
        # E o analogo exato do `paidByConsultants` que a 096 criou no
        # Caderno, e existe pelo mesmo motivo: `total_vendas` inclui
        # supervisor e VAI E VEM (regra de 2026-08-10), o peso exclui os
        # dois, e dividir um pelo outro e media sobre duas populacoes.
        "producao_consultores": total_consultores,
        "peso_consultores": (
            float(peso_headcount) if peso_headcount is not None else 0.0
        ),
        "denominador_consultores": origem,
    }


# Regiões excluídas das médias da organização (projeto à parte)
_REGIOES_EXCLUIR_MEDIA: frozenset = frozenset({"ALEXANDRE"})


def calcular_medias_organizacao(
    df: pd.DataFrame,
    du_decorridos: int = 1,
    perfil: Optional[str] = None,
    df_sup: Optional[pd.DataFrame] = None,
) -> Dict[str, float]:
    """Calcula a Média DU empresa por produto, com granularidade por perfil.

    Usa ``df`` PRE-RLS para que o resultado represente toda a empresa,
    independente do perfil logado. A granularidade do agrupamento varia:

    - ``gerente_comercial``: média entre as Médias DU regionais,
      excluindo a região ``ALEXANDRE`` (projeto à parte).
    - ``supervisor``: média entre as Médias DU por loja.
    - ``consultor``: média entre as Médias DU por consultor (sem
      supervisores, via ``df_sup``).
    - Outros perfis: retorna dict vazio (sem comparativo).

    Retorna dict: produto_display -> Média DU empresa.
    """
    if df.empty or du_decorridos <= 0 or perfil not in {
        "gerente_comercial", "supervisor", "consultor"
    }:
        return {}

    # Define a coluna de agrupamento e o df base por perfil
    if perfil == "gerente_comercial":
        if "REGIAO" not in df.columns:
            return {}
        df_base = df[
            ~df["REGIAO"].fillna("").str.upper().isin(_REGIOES_EXCLUIR_MEDIA)
        ]
        coluna_grupo = "REGIAO"
    elif perfil == "supervisor":
        if "LOJA" not in df.columns:
            return {}
        df_base = excluir_lojas_backoffice(df)
        coluna_grupo = "LOJA"
    else:  # consultor
        if "CONSULTOR" not in df.columns:
            return {}
        df_base = excluir_lojas_backoffice(
            excluir_supervisores(df, df_sup)
        )
        coluna_grupo = "CONSULTOR"

    if df_base.empty:
        return {}

    medias: Dict[str, float] = {}
    for produto_display, categorias in PRODUTOS_DASHBOARD.items():
        mask = df_base["categoria_codigo"].isin(categorias)
        df_prod = df_base.loc[mask]
        if df_prod.empty:
            medias[produto_display] = 0.0
            continue
        soma_por_grupo = df_prod.groupby(coluna_grupo)["VALOR"].sum()
        if soma_por_grupo.empty:
            medias[produto_display] = 0.0
            continue
        # Média DU empresa = média aritmética das Médias DU por grupo
        medias[produto_display] = float(
            soma_por_grupo.mean() / du_decorridos
        )
    return medias


def calcular_metas_produto_diarias(
    df: pd.DataFrame,
    df_metas_produto: pd.DataFrame,
    du_total: int,
    du_decorridos: int,
) -> List[Dict]:
    """Calcula metas diarias por produto para o dashboard."""
    resultados = []

    for produto_display, categorias in PRODUTOS_DASHBOARD.items():
        # Calcular valor atual do produto
        mask_produto = df["categoria_codigo"].isin(categorias)
        valor_atual = df.loc[mask_produto, "VALOR"].sum()

        # Definir lojas ativas (usado para meta e média organizacional)
        lojas_ativas = (
            df["LOJA"].unique() if "LOJA" in df.columns else []
        )

        # Meta total do produto: casamento determinístico via
        # PRODUTOS_DASHBOARD_COL_META (produto_display → coluna do banco).
        meta_total = 0.0
        col_meta = PRODUTOS_DASHBOARD_COL_META.get(produto_display)
        if (
            col_meta
            and not df_metas_produto.empty
            and "LOJA" in df.columns
            and col_meta in df_metas_produto.columns
        ):
            meta_total = float(
                df_metas_produto.loc[
                    df_metas_produto["LOJA"].isin(lojas_ativas), col_meta
                ].sum()
            )

        # Calcular ritmo e metas diarias
        ritmo_diario = (
            valor_atual / du_decorridos if du_decorridos > 0 else 0
        )
        meta_diaria = meta_total / du_total if du_total > 0 else 0
        gap = max(0, meta_total - valor_atual)
        dias_restantes = du_total - du_decorridos
        meta_diaria_restante = (
            gap / dias_restantes if dias_restantes > 0 else 0
        )

        perc_atingido = (
            (valor_atual / meta_total * 100) if meta_total > 0 else 0
        )

        projecao = ritmo_diario * du_total
        perc_projecao = (projecao / meta_total * 100) if meta_total > 0 else 0

        resultados.append({
            "produto": produto_display,
            "valor_atual": valor_atual,
            "meta_total": meta_total,
            "ritmo_diario": ritmo_diario,
            "meta_diaria": meta_diaria,
            "meta_diaria_restante": meta_diaria_restante,
            "perc_atingido": perc_atingido,
            "projecao": projecao,
            "perc_projecao": perc_projecao,
            "du_total": du_total,
            "du_decorridos": du_decorridos,
        })

    return resultados


# Produtos contados apenas por quantidade (sem valor/pontos)
_PRODUTOS_QTD = [
    {
        "produto": "EMISSAO",
        "nome": "Emissão",
        "col_pago": "is_emissao_cartao",
        "col_meta": "EMISSAO",
        "tipo_oper_analise": [
            "CARTÃO BENEFICIO",
            "Venda Pré-Adesão",
        ],
    },
    {
        "produto": "SUPER_CONTA",
        "nome": "Super Conta",
        "col_pago": "is_super_conta",
        "col_meta": "SUPER_CONTA",
        "subtipo_analise": "SUPER CONTA",
    },
    {
        "produto": "BMG_MED",
        "nome": "BMG Med",
        "col_pago": "is_bmg_med",
        "col_meta": "BMG_MED",
        "tipo_oper_analise": ["BMG MED"],
    },
    {
        "produto": "VIDA_FAMILIAR",
        "nome": "Vida Familiar",
        "col_pago": "is_seguro_vida",
        "col_meta": "VIDA_FAMILIAR",
        "tipo_oper_analise": ["Seguro"],
    },
]


def calcular_kpis_qtd_produtos(
    df: pd.DataFrame,
    df_analise: pd.DataFrame,
    df_metas_produto: pd.DataFrame,
    du_total: int,
    du_decorridos: int,
    df_org: Optional[pd.DataFrame] = None,
    org_norm: int = 1,
) -> List[Dict]:
    """
    Calcula KPIs de quantidade para produtos contados apenas
    por quantidade: Emissão, Super Conta, BMG Med e
    Vida Familiar.
    """
    du_rest = max(0, du_total - du_decorridos)
    lojas_ativas = (
        df["LOJA"].unique()
        if "LOJA" in df.columns
        else []
    )
    resultados = []

    for prod in _PRODUTOS_QTD:
        # Quantidade paga/liquidada
        col = prod["col_pago"]
        qtd_paga = (
            int(df[col].sum()) if col in df.columns else 0
        )

        # Quantidade em análise no pipeline
        qtd_analise = 0
        if not df_analise.empty:
            if "subtipo_analise" in prod:
                if "SUBTIPO" in df_analise.columns:
                    qtd_analise = int(
                        (
                            df_analise["SUBTIPO"]
                            == prod["subtipo_analise"]
                        ).sum()
                    )
            elif "tipo_oper_analise" in prod:
                if "TIPO OPER." in df_analise.columns:
                    qtd_analise = int(
                        df_analise["TIPO OPER."]
                        .isin(prod["tipo_oper_analise"])
                        .sum()
                    )

        # Meta total (soma das lojas ativas)
        meta = 0
        col_meta = prod["col_meta"]
        if (
            not df_metas_produto.empty
            and col_meta in df_metas_produto.columns
            and "LOJA" in df_metas_produto.columns
            and len(lojas_ativas) > 0
        ):
            meta = float(
                df_metas_produto.loc[
                    df_metas_produto["LOJA"].isin(lojas_ativas),
                    col_meta,
                ].sum()
            )

        # Ritmo local (base de projeção e Média DU para perfis superiores)
        ritmo_local = qtd_paga / du_decorridos if du_decorridos > 0 else 0
        ritmo = ritmo_local
        projecao = ritmo_local * du_total
        # Referência regional por entidade (loja ou consultor) — sem divisão por DU
        media_ref: Optional[float] = None
        if df_org is not None and col in df_org.columns:
            qtd_org = int(df_org[col].sum())
            media_ref = qtd_org / max(org_norm, 1)
        gap = max(0, meta - qtd_paga)
        meta_dr = gap / du_rest if du_rest > 0 else 0
        perc = (qtd_paga / meta * 100) if meta > 0 else 0

        resultados.append({
            "produto": prod["produto"],
            "nome": prod["nome"],
            "qtd_paga": qtd_paga,
            "qtd_analise": qtd_analise,
            "meta": meta,
            "perc_atingido": perc,
            "ritmo_diario": ritmo,
            "media_ref": media_ref,
            "projecao": projecao,
            "meta_diaria_restante": meta_dr,
            "du_restantes": du_rest,
        })

    return resultados


# ══════════════════════════════════════════════════════
# Composicao dos KPIs do periodo (com cache manual)
# ══════════════════════════════════════════════════════


def _ritmo_organizacao(
    role: str | None,
    df_f: pd.DataFrame,
    df_full: pd.DataFrame,
    df_sup_full: pd.DataFrame,
) -> tuple[pd.DataFrame | None, int]:
    """Base e normalizador do ritmo da organizacao (media DU de referencia).

    Para supervisor/consultor, restringe df_full as regioes presentes em
    df_f e normaliza por nº de lojas (supervisor) ou consultores
    não-supervisor (consultor). Outros perfis: (None, 1).
    """
    if role not in ("supervisor", "consultor") or df_f.empty:
        return None, 1
    if "REGIAO" not in df_f.columns:
        return None, 1
    regioes = df_f["REGIAO"].dropna().unique()
    df_reg = df_full[df_full["REGIAO"].isin(regioes)]
    if df_reg.empty:
        return None, 1
    if role == "supervisor" and "LOJA" in df_reg.columns:
        return df_reg, max(int(df_reg["LOJA"].nunique()), 1)
    if role == "consultor" and "CONSULTOR" in df_reg.columns:
        sups = set(
            df_sup_full["SUPERVISOR"].dropna()
            if "SUPERVISOR" in df_sup_full.columns
            else []
        )
        n_cons = int(
            df_reg[~df_reg["CONSULTOR"].isin(sups)]["CONSULTOR"].nunique()
        )
        return df_reg, max(n_cons, 1)
    return df_reg, 1


def serie_diaria_pago(df_f: pd.DataFrame) -> list | None:
    """Serie diaria de VALOR pago (>= 2 pontos) p/ sparkline; senao None.

    Publica e SEM cache, ao contrario das ``obter_*_periodo``: e calculo
    puro e barato sobre um frame ja em memoria (um ``groupby`` por dia),
    nao justifica mais um par de chaves em ``session_state``.
    """
    if "DATA" not in df_f.columns or df_f.empty:
        return None
    df_com_data = df_f.dropna(subset=["DATA"])
    if df_com_data.empty:
        return None
    serie = (
        df_com_data.groupby(df_com_data["DATA"].dt.date)["VALOR"]
        .sum()
        .sort_index()
    )
    return serie.tolist() if len(serie) >= 2 else None


def _chave_kpis(
    mes: int,
    ano: int,
    role: Optional[str],
    perfil_efetivo: Optional[dict],
    session_state: MutableMapping[str, Any],
) -> tuple:
    """Chave de invalidacao do cache de KPIs.

    **Fronteira de seguranca entre perfis.** O cache de KPIs vive em
    ``session_state`` e nao e recalculado enquanto esta chave nao muda;
    logo, todo componente que altera o RECORTE dos dados precisa estar
    aqui. Perder ou trocar um componente faz um perfil enxergar numero
    calculado para o escopo de outro (ex.: gerente A vendo o KPI de B
    depois de um "Visualizar como").

    Os seis componentes, nesta ordem:

    1. ``mes`` / 2. ``ano`` — periodo selecionado;
    3. ``role`` — perfil EFETIVO (ja considera "Visualizar como");
    4. ``escopo`` do perfil efetivo — regioes/lojas/consultores que o
       ``aplicar_rls`` usa; e o que separa dois gerentes de mesmo role;
    5. filtro granular de lojas (``ui_filtro_lojas``), ordenado para que
       a mesma selecao em ordem diferente nao invalide o cache a toa;
    6. filtro granular de consultor (``ui_filtro_consultor``).

    Os dois filtros de UI sao lidos de ``session_state`` no momento da
    chamada: quem chama precisa ter renderizado a sidebar de filtros
    ANTES (em ``app.py``, ``render_sidebar_filtros_perfil``), que e o
    unico ponto do codebase que escreve nessas duas chaves.

    Alterar esta funcao muda quem ve o que — nao e ajuste cosmetico.
    """
    return (
        mes,
        ano,
        role,
        tuple(perfil_efetivo.get("escopo", []) if perfil_efetivo else []),
        tuple(sorted(session_state.get("ui_filtro_lojas") or [])),
        session_state.get("ui_filtro_consultor") or "",
    )


def obter_kpis_gerais_periodo(
    *,
    session_state: MutableMapping[str, Any],
    mes: int,
    ano: int,
    role: Optional[str],
    perfil_efetivo: Optional[dict],
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    df_metas_produto: pd.DataFrame,
    dia_atual: Optional[int],
    df_sup: pd.DataFrame,
) -> Dict:
    """KPIs gerais do periodo (valor, pontos, metas, DU) — com cache.

    Envolve ``calcular_kpis_gerais`` e acrescenta o trio de VALOR
    (``meta_global_valor`` / ``perc_ating_valor`` / ``gap_valor``), que
    nao existe no calculo puro: e derivacao de apresentacao, feita aqui
    desde a extracao de ``app.py``.

    **Escopo dos frames.** Todos chegam JA recortados pelo perfil
    (``aplicar_rls``) e pelos filtros da sidebar — esta funcao nao
    aplica RLS. Nenhum frame pre-RLS entra aqui.

    Cache em ``session_state`` sob ``_kpis_gerais_cache`` /
    ``_kpis_gerais_chave``, invalidado por ``_chave_kpis``.

    ``session_state`` e injetado em vez de importado: nenhum modulo de
    ``kpis/`` importa Streamlit no topo, e assim a funcao pode ser
    exercitada em teste com um ``dict`` comum — basta suportar
    ``.get`` / ``[]`` / ``[]=``.
    """
    chave = _chave_kpis(mes, ano, role, perfil_efetivo, session_state)

    if session_state.get("_kpis_gerais_chave") != chave:
        kpis = calcular_kpis_gerais(
            df,
            df_metas,
            df_metas_produto,
            ano,
            mes,
            dia_atual,
            df_sup,
        )

        # Meta global em VALOR (R$) = meta_mix do calcular_kpis_gerais.
        # Diferente de `meta_prata`, que está em PONTOS.
        meta_global_valor = float(kpis.get("meta_mix", 0) or 0)
        total_vendas_valor = float(kpis.get("total_vendas", 0) or 0)
        kpis["meta_global_valor"] = meta_global_valor
        kpis["perc_ating_valor"] = (
            (total_vendas_valor / meta_global_valor * 100)
            if meta_global_valor > 0
            else 0
        )
        kpis["gap_valor"] = max(0, meta_global_valor - total_vendas_valor)

        session_state["_kpis_gerais_cache"] = kpis
        session_state["_kpis_gerais_chave"] = chave

    return session_state["_kpis_gerais_cache"]


class KpisPipeline(NamedTuple):
    """Os dois blocos do pipeline de contratos: em analise e cancelados.

    NamedTuple pelo mesmo motivo de ``DadosPeriodo`` (loaders): sao dois
    ``Dict`` e posicao sozinha seria fragil. Desempacota como tupla e
    permite acesso por nome quando ajuda.

    Os campos espelham EXATAMENTE as chaves gravadas em
    ``session_state['_kpis_pipeline_cache']``.
    """

    kpis_analise: Dict
    kpis_cancel: Dict


def obter_kpis_pipeline_periodo(
    *,
    session_state: MutableMapping[str, Any],
    mes: int,
    ano: int,
    role: Optional[str],
    perfil_efetivo: Optional[dict],
    df: pd.DataFrame,
    df_analise: pd.DataFrame,
    df_cancelados: pd.DataFrame,
    du_decorridos: int,
) -> KpisPipeline:
    """KPIs do pipeline — "Em Analise" e "Cancelados" — com cache.

    Os dois andam juntos de proposito: nenhum consumidor pede so um
    deles, ``calcular_kpis_cancelados`` ja depende de ``df_analise``, e
    separa-los criaria dois pares de chaves de cache para dado sempre
    consumido em bloco — sem ganho real de ISP.

    **Escopo dos frames.** Todos chegam JA recortados pelo perfil
    (``aplicar_rls``) e pelos filtros da sidebar. Nenhum frame pre-RLS
    entra aqui.

    Cache em ``session_state`` sob ``_kpis_pipeline_cache`` /
    ``_kpis_pipeline_chave``, invalidado por ``_chave_kpis``.

    O cache e gravado como ``dict`` e o ``KpisPipeline`` construido na
    saida (precedente da ST-07): cache remanescente de sessao viva com
    formato antigo falha alto em vez de virar ``AttributeError`` mudo.
    """
    chave = _chave_kpis(mes, ano, role, perfil_efetivo, session_state)

    if session_state.get("_kpis_pipeline_chave") != chave:
        kpis_analise = calcular_kpis_analise(
            df_analise,
            df,
            du_decorridos,
        )

        kpis_cancel = calcular_kpis_cancelados(
            df_cancelados,
            df,
            df_analise,
        )

        session_state["_kpis_pipeline_cache"] = {
            "kpis_analise": kpis_analise,
            "kpis_cancel": kpis_cancel,
        }
        session_state["_kpis_pipeline_chave"] = chave

    return KpisPipeline(**session_state["_kpis_pipeline_cache"])


def obter_medias_periodo(
    *,
    session_state: MutableMapping[str, Any],
    mes: int,
    ano: int,
    role: Optional[str],
    perfil_efetivo: Optional[dict],
    df: pd.DataFrame,
    du_decorridos: int,
    df_sup: pd.DataFrame,
    peso_headcount: Optional[float] = None,
) -> Dict:
    """Medias por DU e por nivel (regiao/loja/consultor) — com cache.

    **Escopo dos frames — POS-RLS.** ``df`` e ``df_sup`` chegam ja
    recortados pelo perfil e pelos filtros da sidebar: sao as medias
    do que o usuario enxerga. A comparacao com a organizacao inteira
    e outra funcao (``obter_medias_organizacao_periodo``), separada
    justamente para que o call site deixe explicito qual das duas toca
    dado fora do escopo do perfil.

    Cache em ``session_state`` sob ``_medias_cache`` /
    ``_medias_chave``, invalidado por ``_chave_kpis``.
    """
    chave = _chave_kpis(mes, ano, role, perfil_efetivo, session_state)

    if session_state.get("_medias_chave") != chave:
        session_state["_medias_cache"] = calcular_medias_du_por_nivel(
            df,
            du_decorridos,
            df_sup,
            peso_headcount=peso_headcount,
        )
        session_state["_medias_chave"] = chave

    return session_state["_medias_cache"]


def obter_medias_organizacao_periodo(
    *,
    session_state: MutableMapping[str, Any],
    mes: int,
    ano: int,
    role: Optional[str],
    perfil_efetivo: Optional[dict],
    df_full: pd.DataFrame,
    du_decorridos: int,
    df_sup_full: pd.DataFrame,
) -> Dict[str, float]:
    """Medias da organizacao inteira (base de comparacao) — com cache.

    **Escopo dos frames — PRE-RLS, de proposito.** ``df_full`` e a base
    da organizacao (media da empresa) e ``df_sup_full`` e a lista global
    de supervisores usada so para EXCLUSAO (nunca exibida). Deles nao
    sai NENHUMA linha para a tela: somente medias e contagens agregadas.
    Esta funcao existe separada de ``obter_medias_periodo`` por isso —
    ter as duas no mesmo call site torna obvio, em auditoria, qual delas
    recebe dado fora do escopo do perfil.

    A granularidade da media acompanha o filtro de UI: se o usuario
    afunilou ate consultor → granularidade consultor; ate loja →
    supervisor; sem filtro extra → granularidade nativa do perfil.

    Cache em ``session_state`` sob ``_medias_organizacao_cache`` /
    ``_medias_organizacao_chave``, invalidado por ``_chave_kpis`` — que
    ja inclui os dois filtros de UI lidos aqui.
    """
    chave = _chave_kpis(mes, ano, role, perfil_efetivo, session_state)

    if session_state.get("_medias_organizacao_chave") != chave:
        if session_state.get("ui_filtro_consultor"):
            _perfil_media = "consultor"
        elif (
            (session_state.get("ui_filtro_lojas") or [])
            and role == "gerente_comercial"
        ):
            _perfil_media = "supervisor"
        else:
            _perfil_media = role

        session_state["_medias_organizacao_cache"] = (
            calcular_medias_organizacao(
                df_full,
                du_decorridos=du_decorridos,
                perfil=_perfil_media,
                df_sup=df_sup_full,
            )
        )
        session_state["_medias_organizacao_chave"] = chave

    return session_state["_medias_organizacao_cache"]


def obter_metas_prod_diarias_periodo(
    *,
    session_state: MutableMapping[str, Any],
    mes: int,
    ano: int,
    role: Optional[str],
    perfil_efetivo: Optional[dict],
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    df_metas_produto: pd.DataFrame,
    df_sup: pd.DataFrame,
    dia_atual: Optional[int],
    du_decorridos: int,
) -> List[Dict]:
    """Meta diaria restante por produto — com cache.

    **Sobre ``df_metas`` / ``df_sup`` / ``dia_atual``:** nao entram no
    calculo desta funcao. Existem na assinatura porque o ``du_total``
    de que ela depende so e produzido dentro do grupo "gerais", e a
    forma escolhida de obte-lo e chamar
    ``obter_kpis_gerais_periodo`` internamente (chamada barata: mesmo
    ``session_state`` e mesma ``_chave_kpis``, entao se ``app.py`` ja a
    chamou neste rerun e cache hit). A alternativa — receber
    ``du_total`` pronto por parametro — deixaria o call site com um
    contrato de ordem implicito ("chame gerais antes"), que e
    exatamente o acoplamento que a decomposicao quis remover. Trade-off
    consciente: parametros a mais aqui, autossuficiencia la.

    **Escopo dos frames.** Todos POS-RLS. Nenhum frame pre-RLS entra.

    Cache em ``session_state`` sob ``_metas_prod_diarias_cache`` /
    ``_metas_prod_diarias_chave``, invalidado por ``_chave_kpis``.
    """
    chave = _chave_kpis(mes, ano, role, perfil_efetivo, session_state)

    if session_state.get("_metas_prod_diarias_chave") != chave:
        kpis = obter_kpis_gerais_periodo(
            session_state=session_state,
            mes=mes,
            ano=ano,
            role=role,
            perfil_efetivo=perfil_efetivo,
            df=df,
            df_metas=df_metas,
            df_metas_produto=df_metas_produto,
            dia_atual=dia_atual,
            df_sup=df_sup,
        )

        session_state["_metas_prod_diarias_cache"] = (
            calcular_metas_produto_diarias(
                df,
                df_metas_produto,
                kpis.get("du_total", 0),
                du_decorridos,
            )
        )
        session_state["_metas_prod_diarias_chave"] = chave

    return session_state["_metas_prod_diarias_cache"]


def obter_kpis_qtd_periodo(
    *,
    session_state: MutableMapping[str, Any],
    mes: int,
    ano: int,
    role: Optional[str],
    perfil_efetivo: Optional[dict],
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    df_metas_produto: pd.DataFrame,
    df_sup: pd.DataFrame,
    df_analise: pd.DataFrame,
    df_full: pd.DataFrame,
    df_sup_full: pd.DataFrame,
    dia_atual: Optional[int],
    du_decorridos: int,
) -> List[Dict]:
    """KPIs de QUANTIDADE por produto (com ritmo de referencia) — cache.

    **Escopo dos frames — mistura POS e PRE-RLS, por regra de negocio.**
    ``df`` / ``df_analise`` / ``df_metas_produto`` chegam POS-RLS. Ja
    ``df_full`` e ``df_sup_full`` sao PRE-RLS de proposito: alimentam
    ``_ritmo_organizacao``, que produz a media DU de referencia da
    regiao (por loja para supervisor, por consultor para consultor).
    Isso nao e acoplamento acidental — e a mesma regra de negocio de
    sempre: o ritmo comparativo precisa da regiao inteira, nao so do
    escopo do usuario. Desses dois frames nao sai NENHUMA linha para a
    tela: apenas a base agregada e o normalizador (``org_norm``).

    **Sobre ``df_metas`` / ``df_sup`` / ``dia_atual``:** mesmo motivo de
    ``obter_metas_prod_diarias_periodo`` — sao repassados a
    ``obter_kpis_gerais_periodo`` para obter o ``du_total``, sem contrato
    de ordem implicito no call site.

    Cache em ``session_state`` sob ``_kpis_qtd_cache`` /
    ``_kpis_qtd_chave``, invalidado por ``_chave_kpis``.
    """
    chave = _chave_kpis(mes, ano, role, perfil_efetivo, session_state)

    if session_state.get("_kpis_qtd_chave") != chave:
        kpis = obter_kpis_gerais_periodo(
            session_state=session_state,
            mes=mes,
            ano=ano,
            role=role,
            perfil_efetivo=perfil_efetivo,
            df=df,
            df_metas=df_metas,
            df_metas_produto=df_metas_produto,
            dia_atual=dia_atual,
            df_sup=df_sup,
        )

        # Média DU de referência: média da região por loja (supervisor)
        # ou por consultor (consultor). Para outros perfis, sem referência.
        _df_org_ritmo, _org_norm = _ritmo_organizacao(
            role, df, df_full, df_sup_full
        )

        session_state["_kpis_qtd_cache"] = calcular_kpis_qtd_produtos(
            df,
            df_analise,
            df_metas_produto,
            kpis.get("du_total", 0),
            du_decorridos,
            df_org=_df_org_ritmo,
            org_norm=_org_norm,
        )
        session_state["_kpis_qtd_chave"] = chave

    return session_state["_kpis_qtd_cache"]


def limpar_cache_kpis(session_state: MutableMapping[str, Any]) -> None:
    """Invalida os caches de KPIs do periodo (``obter_*_periodo``).

    Os seis pares ``_*_cache`` / ``_*_chave`` sao chaves privadas DESTE
    modulo: quem dispara um refresh global (o botao "Atualizar Dados",
    na sidebar) precisa poder esquece-las sem conhece-las pelo nome. Sem
    este ponto unico, cada novo par de chaves de cache criado aqui
    precisaria ser lembrado no call site — foi assim que o cache YoY
    ficou de fora do refresh por uma versao (ver
    ``tabs/produtos.py::limpar_cache_comparativos``). Depois da
    decomposicao de ``obter_kpis_periodo`` em seis funcoes, o argumento
    vale seis vezes mais: **funcao ``obter_*_periodo`` nova entra aqui
    na mesma tarefa em que nasce.**

    Nao recalcula nada: a proxima chamada de cada ``obter_*_periodo``
    encontra a chave ausente e refaz o seu bloco.

    Os nomes sao escritos por extenso (e nao montados por prefixo) de
    proposito: auditar cache de KPI comeca por um ``grep`` do nome da
    chave, e nome montado em runtime some do grep.
    """
    session_state.pop("_kpis_gerais_cache", None)
    session_state.pop("_kpis_gerais_chave", None)
    session_state.pop("_kpis_pipeline_cache", None)
    session_state.pop("_kpis_pipeline_chave", None)
    session_state.pop("_medias_cache", None)
    session_state.pop("_medias_chave", None)
    session_state.pop("_medias_organizacao_cache", None)
    session_state.pop("_medias_organizacao_chave", None)
    session_state.pop("_metas_prod_diarias_cache", None)
    session_state.pop("_metas_prod_diarias_chave", None)
    session_state.pop("_kpis_qtd_cache", None)
    session_state.pop("_kpis_qtd_chave", None)
