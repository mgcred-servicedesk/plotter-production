"""
KPIs do Dashboard de Pontuacao.

Diferente do dashboard de vendas (em R$), este modulo opera em
pontos: ``pontos = VALOR x PTS`` (ver docs/agents/business-rules.md).

A coluna ``pontos`` ja existe em ``df`` (pagos) apos
``consolidar_dados``. Em ``df_analise`` e ``df_cancelados`` ela nao
existe, entao calculamos aqui usando o mesmo ``mapa_pontos`` que vem
de ``carregar_pontuacao_efetiva``.

Aceleradores (Emissao, Super Conta, BMG Med, Vida Familiar) tem
``conta_pontuacao=False`` por categoria e ja entram com ``pontos=0``
no df pagos. Para analise/cancelados aplicamos a mesma regra via
``conta_pontuacao``.
"""

from typing import Dict, List, Optional

import pandas as pd

from src.dashboard.kpis.gerais import (
    PRODUTOS_DASHBOARD,
    excluir_lojas_backoffice,
    excluir_supervisores,
    separar_cancelados_liquidos,
)


def _aplicar_pontos(
    frame: pd.DataFrame,
    mapa_pontos: Dict[str, float],
) -> pd.Series:
    """Calcula a serie de pontos para um df sem coluna ``pontos``.

    Regra: ``pontos = VALOR x PTS_categoria``, zerado quando
    ``conta_pontuacao == False`` (cartao, seguros).
    """
    if frame.empty:
        return pd.Series(dtype=float)

    if "categoria_codigo" in frame.columns:
        pts = frame["categoria_codigo"].map(mapa_pontos).fillna(0).astype(float)
    else:
        pts = pd.Series(0.0, index=frame.index)

    valor = pd.to_numeric(
        frame.get("VALOR", pd.Series(0, index=frame.index)),
        errors="coerce",
    ).fillna(0)

    pontos = valor * pts

    if "conta_pontuacao" in frame.columns:
        pontos = pontos.where(frame["conta_pontuacao"] != False, 0)  # noqa: E712

    return pontos


def calcular_pontos_em_analise(
    df_analise: pd.DataFrame,
    mapa_pontos: Dict[str, float],
    du_decorridos: int,
) -> Dict:
    """KPIs de pontos para contratos em analise.

    Aceleradores nao entram em pontos (zerados pela regra de
    ``conta_pontuacao=False`` na categoria).
    """
    if df_analise.empty:
        return {
            "pontos_analise": 0.0,
            "qtd_analise": 0,
            "media_diaria_pontos_analise": 0.0,
        }

    pontos = _aplicar_pontos(df_analise, mapa_pontos)
    total = float(pontos.sum())
    qtd = int((pontos > 0).sum())
    media_du = total / du_decorridos if du_decorridos > 0 else 0.0

    return {
        "pontos_analise": total,
        "qtd_analise": qtd,
        "media_diaria_pontos_analise": media_du,
    }


def calcular_pontos_cancelados(
    df_cancelados: pd.DataFrame,
    df: pd.DataFrame,
    df_analise: pd.DataFrame,
    mapa_pontos: Dict[str, float],
) -> Dict:
    """KPIs de pontos para cancelados.

    Conforme acordado: na pagina de pontuacao exibimos apenas
    ``perc_perda`` (mesma logica do dashboard de vendas: quantidade
    de cancelados vs total de propostas). Mantemos o total em pontos
    no dict caso seja util no futuro, mas nao e usado na UI.
    """
    if df_cancelados.empty:
        return {
            "pontos_cancelados": 0.0,
            "qtd_cancelados": 0,
            "indice_perda": 0.0,
        }

    # Apenas cancelados liquidos contam (redigitadas/recuperadas
    # saem da contagem) — mesma regra do dashboard de vendas.
    df_liquidos, _, _ = separar_cancelados_liquidos(df_cancelados)

    pontos = _aplicar_pontos(df_liquidos, mapa_pontos)
    total = float(pontos.sum())
    qtd_cancelados = len(df_liquidos)

    qtd_pagos = len(df)
    qtd_analise = len(df_analise) if not df_analise.empty else 0
    total_propostas = qtd_pagos + qtd_cancelados + qtd_analise
    indice_perda = (
        (qtd_cancelados / total_propostas * 100)
        if total_propostas > 0
        else 0.0
    )

    return {
        "pontos_cancelados": total,
        "qtd_cancelados": qtd_cancelados,
        "indice_perda": indice_perda,
    }


def calcular_medias_pontos_por_nivel(
    df: pd.DataFrame,
    du_decorridos: int,
    df_supervisores: Optional[pd.DataFrame] = None,
    peso_headcount: Optional[float] = None,
) -> Dict:
    """Medias DU em pontos por loja e por consultor.

    Mesma logica de ``calcular_medias_du_por_nivel`` (em valor),
    mas operando sobre a coluna ``pontos``. Exclui supervisores e
    lojas de backoffice (``LOJAS_BACKOFFICE``).

    ``peso_headcount`` segue a mesma regra da versao em valor: e o
    gente-mes da competencia (091) somado no escopo, e ``None`` cai no
    denominador antigo (quem produziu). Manter as duas paginas com o
    mesmo denominador importa — valor e pontos sao a mesma producao
    vista por duas reguas, e nao podem discordar sobre quantas pessoas a
    produziram.
    """
    df_sem_sup = excluir_lojas_backoffice(
        excluir_supervisores(df, df_supervisores)
    )

    num_lojas = 0
    media_du_loja = 0.0
    if (
        "LOJA" in df_sem_sup.columns
        and "pontos" in df_sem_sup.columns
        and not df_sem_sup.empty
    ):
        pontos_por_loja = df_sem_sup.groupby("LOJA")["pontos"].sum()
        num_lojas = len(pontos_por_loja)
        media_du_loja = (
            float(pontos_por_loja.mean()) / du_decorridos
            if du_decorridos > 0
            else 0.0
        )

    # Denominador PONDERADO — ver a justificativa longa em
    # `calcular_medias_du_por_nivel` (gerais.py).
    num_consultores = 0
    total_consultores = 0.0
    if (
        "CONSULTOR" in df_sem_sup.columns
        and "pontos" in df_sem_sup.columns
        and not df_sem_sup.empty
    ):
        pontos_por_consultor = df_sem_sup.groupby("CONSULTOR")["pontos"].sum()
        num_consultores = len(pontos_por_consultor)
        total_consultores = float(pontos_por_consultor.sum())

    if peso_headcount is not None and peso_headcount > 0:
        denominador = float(peso_headcount)
        origem = "peso"
    else:
        denominador = float(num_consultores)
        origem = "produtores"

    media_du_consultor = (
        total_consultores / denominador / du_decorridos
        if du_decorridos > 0 and denominador > 0
        else 0.0
    )

    return {
        "media_du_loja_pontos": media_du_loja,
        "media_du_consultor_pontos": media_du_consultor,
        "num_lojas": num_lojas,
        "num_consultores": num_consultores,
        # Pontos da populacao CONSULTOR — mesmo papel que
        # `producao_consultores` cumpre em valor. Ver a justificativa
        # em `calcular_medias_du_por_nivel` (gerais.py).
        "pontos_consultores": total_consultores,
        "peso_consultores": (
            float(peso_headcount) if peso_headcount is not None else 0.0
        ),
        "denominador_consultores": origem,
    }


def calcular_mix_pontos(
    df: pd.DataFrame,
    meta_prata: float,
    du_total: int,
) -> List[Dict]:
    """Cards MIX em pontos para os 5 produtos do MIX.

    Para cada produto:
    - ``pontos_atual``: soma de pontos pagos no produto
    - ``peso``: ``pontos_atual / total_pontos_mix``
    - ``meta_diaria_produto``: ``peso x (Meta_Prata / DU_total)``
      (meta diaria da Prata particionada pelo peso realizado)
    - ``meta_prata_fatia``: ``Meta_Prata x peso``
    - ``perc_atingido``: ``pontos_atual / meta_prata_fatia x 100``

    O peso usa o realizado no proprio mes (cada periodo apura
    pesos diferentes), conforme regra de negocio do projeto.
    Quando o produto ainda nao pontuou, peso=0 e meta diaria=0.
    """
    if df.empty or "pontos" not in df.columns:
        return []

    pontos_por_produto: Dict[str, float] = {}
    for produto_display, categorias in PRODUTOS_DASHBOARD.items():
        mask = df["categoria_codigo"].isin(categorias)
        pontos_por_produto[produto_display] = float(
            df.loc[mask, "pontos"].sum()
        )

    total_mix = sum(pontos_por_produto.values())
    meta_dia_prata = (
        float(meta_prata) / du_total if du_total > 0 else 0.0
    )

    resultados: List[Dict] = []
    for produto_display, pontos_atual in pontos_por_produto.items():
        peso = (pontos_atual / total_mix) if total_mix > 0 else 0.0
        meta_diaria_produto = peso * meta_dia_prata
        meta_prata_fatia = float(meta_prata) * peso
        perc_atingido = (
            (pontos_atual / meta_prata_fatia * 100)
            if meta_prata_fatia > 0
            else 0.0
        )

        resultados.append(
            {
                "produto": produto_display,
                "pontos_atual": pontos_atual,
                "peso": peso * 100,  # ja em %
                "meta_diaria_produto": meta_diaria_produto,
                "meta_prata_fatia": meta_prata_fatia,
                "perc_atingido": perc_atingido,
            }
        )

    return resultados


def calcular_prioridades_pontuacao(
    df: pd.DataFrame,
    df_analise: pd.DataFrame,
    mapa_pontos: Dict[str, float],
    meta_prata: float,
    meta_ouro: float,
) -> List[Dict]:
    """Insights por produto MIX: peso atual vs pontos em analise.

    Para cada produto MIX, devolve um dict com:
    - ``produto``: codigo display
    - ``pontos_pagos``: pontos ja pagos do produto
    - ``qtd_pagos``: numero de contratos que geraram pontos
    - ``pontos_analise``: pontos potenciais no pipeline (valor x PTS)
    - ``qtd_analise``: numero de contratos em analise do produto
    - ``peso_atual``: % do produto na producao paga em pontos
    - ``fecha_prata_pct``: o quanto ``pontos_analise`` fecharia da
      Meta Prata (gap restante de Prata) se 100% converter
    - ``fecha_ouro_pct``: idem para Meta Ouro
    - ``meta_prata``, ``meta_ouro``: contexto

    A lista vem ordenada por ``pontos_analise`` decrescente, para a
    UI destacar os produtos com maior potencial de conversao.
    """
    if df.empty and df_analise.empty:
        return []

    total_pagos_mix = 0.0
    pontos_pagos: Dict[str, float] = {}
    qtd_pagos: Dict[str, int] = {}
    if not df.empty and "pontos" in df.columns:
        for produto_display, categorias in PRODUTOS_DASHBOARD.items():
            mask = df["categoria_codigo"].isin(categorias)
            pontos_pagos[produto_display] = float(
                df.loc[mask, "pontos"].sum()
            )
            qtd_pagos[produto_display] = int((df.loc[mask, "pontos"] > 0).sum())
            total_pagos_mix += pontos_pagos[produto_display]

    pontos_analise_map: Dict[str, float] = {}
    qtd_analise_map: Dict[str, int] = {}
    if not df_analise.empty:
        pontos_serie = _aplicar_pontos(df_analise, mapa_pontos)
        df_an = df_analise.assign(_pts=pontos_serie)
        for produto_display, categorias in PRODUTOS_DASHBOARD.items():
            mask = df_an["categoria_codigo"].isin(categorias)
            pontos_analise_map[produto_display] = float(
                df_an.loc[mask, "_pts"].sum()
            )
            qtd_analise_map[produto_display] = int(
                (df_an.loc[mask, "_pts"] > 0).sum()
            )

    total_pagos = float(df["pontos"].sum()) if "pontos" in df.columns else 0.0
    gap_prata = max(0.0, float(meta_prata) - total_pagos)
    gap_ouro = max(0.0, float(meta_ouro) - total_pagos)

    resultados: List[Dict] = []
    for produto_display in PRODUTOS_DASHBOARD.keys():
        pagos = pontos_pagos.get(produto_display, 0.0)
        analise = pontos_analise_map.get(produto_display, 0.0)
        peso = (pagos / total_pagos_mix * 100) if total_pagos_mix > 0 else 0.0
        fecha_prata = (analise / gap_prata * 100) if gap_prata > 0 else 0.0
        fecha_ouro = (analise / gap_ouro * 100) if gap_ouro > 0 else 0.0

        resultados.append(
            {
                "produto": produto_display,
                "pontos_pagos": pagos,
                "qtd_pagos": qtd_pagos.get(produto_display, 0),
                "pontos_analise": analise,
                "qtd_analise": qtd_analise_map.get(produto_display, 0),
                "peso_atual": peso,
                "gap_prata": gap_prata,
                "gap_ouro": gap_ouro,
                "fecha_prata_pct": fecha_prata,
                "fecha_ouro_pct": fecha_ouro,
            }
        )

    resultados.sort(key=lambda r: r["pontos_analise"], reverse=True)
    return resultados


# Rotulo da linha agregada do resumo por loja. Exportado para a UI
# destacar a linha sem depender da posicao.
ROTULO_TOTAL_RESUMO_LOJAS = "TOTAL"


def _metas_por_loja(df_metas: pd.DataFrame, coluna: str) -> pd.Series:
    """Soma ``coluna`` por LOJA; meta nula/negativa vira 0 (sem meta)."""
    if df_metas.empty or "LOJA" not in df_metas.columns:
        return pd.Series(dtype=float)
    if coluna not in df_metas.columns:
        return pd.Series(0.0, index=df_metas["LOJA"].dropna().unique())
    valores = pd.to_numeric(df_metas[coluna], errors="coerce").fillna(0)
    return (
        valores.groupby(df_metas["LOJA"]).sum().clip(lower=0.0).astype(float)
    )


def _linha_resumo_loja(
    loja: str,
    pontos: float,
    meta_prata: float,
    meta_ouro: float,
    du_total: int,
    du_decorridos: int,
    du_restantes: int,
) -> Dict:
    """Uma linha do resumo — mesmas formulas de ``calcular_kpis_gerais``.

    ``NaN`` significa "nao se aplica", nunca zero:
    - meta ``<= 0`` (nao cadastrada) ⇒ atingimento e meta diaria NaN,
      para a UI nao mostrar 0% nem "0 pts/dia" como se fosse alvo;
    - meta nao batida e ``du_restantes == 0`` (periodo encerrado) ⇒
      meta diaria NaN — nao ha dia para dividir o gap.
    """
    nan = float("nan")
    projecao = pontos / du_decorridos * du_total if du_decorridos > 0 else 0.0

    def _perc(meta: float) -> float:
        return pontos / meta * 100 if meta > 0 else nan

    def _meta_diaria(meta: float) -> float:
        if meta <= 0:
            return nan
        gap = max(0.0, meta - pontos)
        if gap == 0:
            return 0.0
        return gap / du_restantes if du_restantes > 0 else nan

    return {
        "Loja": loja,
        "Pontos": pontos,
        "Projeção": projecao,
        "Meta Prata": meta_prata,
        "Ating. Prata %": _perc(meta_prata),
        "Meta Ouro": meta_ouro,
        "Ating. Ouro %": _perc(meta_ouro),
        "Meta Diária Prata": _meta_diaria(meta_prata),
        "Meta Diária Ouro": _meta_diaria(meta_ouro),
    }


def calcular_resumo_lojas_pontuacao(
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    du_total: int,
    du_decorridos: int,
    du_restantes: int,
) -> pd.DataFrame:
    """Resumo por loja: pontos, projecao, atingimento e meta diaria.

    Aplica por loja as MESMAS formulas dos cards do topo
    (``calcular_kpis_gerais``):

    - ``Projeção = pontos / DU_decorridos x DU_total``;
    - ``Ating. X % = pontos / Meta X x 100``;
    - ``Meta Diária X = max(0, Meta X - pontos) / DU_restantes``
      (regra "Meta diaria restante" de business-rules).

    A meta e a de escopo **LOJA** (``df_metas`` pos-RLS/filtros) — a
    mesma do ranking de lojas. Nunca chamar com o frame de escopo
    CONSULTOR: o resumo compara a producao da loja inteira.

    Universo: lojas com producao em ``df`` UNIAO lojas com meta > 0 em
    ``df_metas`` (loja com meta e sem ponto aparece zerada — sinal util).
    ``pontos`` soma todas as linhas da loja, como ``total_pontos``.

    Ordenado por ``Ating. Prata %`` desc (lojas sem meta no fim, por
    pontos), com a linha ``ROTULO_TOTAL_RESUMO_LOJAS`` por ultimo. O
    total usa a meta e os pontos SOMADOS do recorte — bate com os cards
    do topo, inclusive na meta diaria (gap do agregado, e nao soma dos
    gaps por loja: loja acima da meta compensa loja abaixo, como nos
    cards).
    """
    colunas = list(
        _linha_resumo_loja("", 0.0, 0.0, 0.0, 0, 0, 0).keys()
    )

    pontos_loja = pd.Series(dtype=float)
    if not df.empty and "LOJA" in df.columns and "pontos" in df.columns:
        pontos_loja = (
            pd.to_numeric(df["pontos"], errors="coerce")
            .fillna(0)
            .groupby(df["LOJA"])
            .sum()
            .astype(float)
        )

    prata_loja = _metas_por_loja(df_metas, "META_PRATA")
    ouro_loja = _metas_por_loja(df_metas, "META_OURO")

    com_meta = set(prata_loja[prata_loja > 0].index) | set(
        ouro_loja[ouro_loja > 0].index
    )
    lojas = sorted(set(pontos_loja.index) | com_meta)
    if not lojas:
        return pd.DataFrame(columns=colunas)

    linhas = [
        _linha_resumo_loja(
            loja,
            float(pontos_loja.get(loja, 0.0)),
            float(prata_loja.get(loja, 0.0)),
            float(ouro_loja.get(loja, 0.0)),
            du_total,
            du_decorridos,
            du_restantes,
        )
        for loja in lojas
    ]
    resumo = pd.DataFrame(linhas, columns=colunas)
    resumo = resumo.sort_values(
        ["Ating. Prata %", "Pontos", "Loja"],
        ascending=[False, False, True],
        na_position="last",
        kind="stable",
    )

    total = _linha_resumo_loja(
        ROTULO_TOTAL_RESUMO_LOJAS,
        float(resumo["Pontos"].sum()),
        float(resumo["Meta Prata"].sum()),
        float(resumo["Meta Ouro"].sum()),
        du_total,
        du_decorridos,
        du_restantes,
    )
    resumo = pd.concat(
        [resumo, pd.DataFrame([total], columns=colunas)],
        ignore_index=True,
    )
    return resumo


# Grupo das lojas sem regiao resolvida — sempre o ultimo bloco.
ROTULO_SEM_REGIAO = "Sem região"


def _regiao_por_loja(df: pd.DataFrame, df_metas: pd.DataFrame) -> pd.Series:
    """LOJA -> REGIAO do periodo.

    Metas primeiro: e o eixo da meta que o resumo compara (os pagos
    resolvem a REGIAO pela mesma competencia, entao normalmente
    coincidem). Loja so com producao cai no ``df``; se ali aparecer em
    mais de uma regiao, vence a de mais pontos, desempate alfabetico —
    mesmo criterio de ``resolver_loja_principal``.
    """
    regioes = pd.Series(dtype=object)

    if (
        not df.empty
        and {"LOJA", "REGIAO", "pontos"} <= set(df.columns)
    ):
        base = df[["LOJA", "REGIAO"]].assign(
            pontos=pd.to_numeric(df["pontos"], errors="coerce").fillna(0)
        )
        base = base[base["REGIAO"].fillna("").astype(str).str.strip() != ""]
        if not base.empty:
            somas = (
                base.groupby(["LOJA", "REGIAO"])["pontos"].sum().reset_index()
            )
            somas = somas.sort_values(
                ["LOJA", "pontos", "REGIAO"],
                ascending=[True, False, True],
                kind="stable",
            ).drop_duplicates("LOJA", keep="first")
            regioes = somas.set_index("LOJA")["REGIAO"]

    if not df_metas.empty and {"LOJA", "REGIAO"} <= set(df_metas.columns):
        metas = df_metas[["LOJA", "REGIAO"]].dropna()
        metas = metas[metas["REGIAO"].astype(str).str.strip() != ""]
        metas = metas.drop_duplicates("LOJA", keep="first")
        regioes = metas.set_index("LOJA")["REGIAO"].combine_first(regioes)

    return regioes


def calcular_resumo_lojas_pontuacao_por_regiao(
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    du_total: int,
    du_decorridos: int,
    du_restantes: int,
) -> Dict:
    """Resumo por loja separado por REGIAO do periodo.

    Cada regiao e um ``calcular_resumo_lojas_pontuacao`` sobre as lojas
    dela (com o proprio ``TOTAL``), entao as regras de universo,
    ordenacao e "nao se aplica" sao exatamente as da tabela unica.

    Returns:
        ``{"regioes": [(regiao, resumo_df), ...], "total": total_df}``.
        Regioes em ordem alfabetica, ``ROTULO_SEM_REGIAO`` por ultimo.
        ``total`` e a linha ``TOTAL`` do resumo sem separacao (uma
        linha) — igual aos cards do topo; vazio quando nao ha loja.
    """
    geral = calcular_resumo_lojas_pontuacao(
        df, df_metas, du_total, du_decorridos, du_restantes
    )
    if geral.empty:
        return {"regioes": [], "total": geral}

    regiao_loja = _regiao_por_loja(df, df_metas)
    lojas = geral.loc[geral["Loja"] != ROTULO_TOTAL_RESUMO_LOJAS, "Loja"]
    grupo = lojas.map(regiao_loja).fillna(ROTULO_SEM_REGIAO)

    nomes = sorted(set(grupo) - {ROTULO_SEM_REGIAO})
    if ROTULO_SEM_REGIAO in set(grupo):
        nomes.append(ROTULO_SEM_REGIAO)

    blocos = []
    for nome in nomes:
        lojas_regiao = set(lojas[grupo == nome])
        df_r = (
            df[df["LOJA"].isin(lojas_regiao)]
            if "LOJA" in df.columns
            else df
        )
        metas_r = (
            df_metas[df_metas["LOJA"].isin(lojas_regiao)]
            if "LOJA" in df_metas.columns
            else df_metas
        )
        blocos.append(
            (
                nome,
                calcular_resumo_lojas_pontuacao(
                    df_r, metas_r, du_total, du_decorridos, du_restantes
                ),
            )
        )

    return {"regioes": blocos, "total": geral.tail(1).reset_index(drop=True)}
