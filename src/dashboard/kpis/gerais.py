"""
KPIs gerais do dashboard + helpers compartilhados entre
os modulos de KPI.

Este modulo hospeda ``excluir_supervisores``,
``contar_consultores`` e ``mascaras_aceleradores``, que sao
reusados por ``produtos.py``, ``regioes.py``,
``rankings.py``, ``gestao.py`` e ``evolucao.py``.
"""

from typing import Dict, List, Optional

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


def excluir_lojas_backoffice(df: pd.DataFrame) -> pd.DataFrame:
    """Remove linhas de lojas de backoffice (match por LOJA normalizada)."""
    if df.empty or "LOJA" not in df.columns:
        return df.copy()
    lojas_norm = (
        df["LOJA"].fillna("").astype(str).str.strip().str.upper()
    )
    return df[~lojas_norm.isin(LOJAS_BACKOFFICE)].copy()


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

    # Valor total digitado no mes (pagos + em analise base)
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
) -> Dict:
    """Calcula medias DU por loja e por consultor.

    Exclui supervisores e lojas de backoffice (``LOJAS_BACKOFFICE``) —
    ambos distorceriam as médias por nível.
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

    # Media DU por consultor
    num_consultores = 0
    if "CONSULTOR" in df_sem_sup.columns and not df_sem_sup.empty:
        vendas_por_consultor = df_sem_sup.groupby("CONSULTOR")["VALOR"].sum()
        num_consultores = len(vendas_por_consultor)
        media_du_consultor = (
            vendas_por_consultor.mean() / du_decorridos
            if du_decorridos > 0 and num_consultores > 0
            else 0
        )
    else:
        media_du_consultor = 0

    return {
        "media_du_loja": media_du_loja,
        "media_du_consultor": media_du_consultor,
        "num_lojas": num_lojas,
        "num_consultores": num_consultores,
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
