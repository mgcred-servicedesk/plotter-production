"""
Consolidacao: as regras de negocio aplicadas sobre os contratos pagos.

Recebe frames JA CARREGADOS e devolve frames — **nao** toca o Supabase.
E a metade "transformacao" do que era `loaders._executar_consolidacao`:
a carga (quatro loaders) ficou em `loaders.py`, que continua sendo a
fachada publica; as regras vieram para ca.

O que mora aqui, na ordem em que roda:

1. **Fallback de categoria** — o ETL sobrescreve `produtos` a cada
   import e grava `categoria_id = NULL` quando a planilha renomeia um
   tipo; sem o fallback a linha some de tudo que agrupa por produto.
2. **Pontuacao** — `pontos = VALOR x PONTOS da categoria`, com
   Portabilidade herdando os pontos do CONSIG do banco de origem
   (granularidade de BANCO, maior que a de categoria — por isso vive em
   codigo e nao na tabela `pontuacao`).
3. **Diagnostico de mapeamento** — o que o expander de admin exibe.
4. **Regras de exclusao** — `conta_valor` / `conta_pontuacao` falsos
   zeram VALOR e pontos.
5. **Classificacoes** — Super Conta, emissao de cartao e os dois
   seguros, que contam so quantidade.

## Por que `carregar_categorias` chega como parametro

`preencher_categoria_fallback` precisa da tabela de categorias, que so
`loaders.py` sabe buscar. Importa-la daqui criaria ciclo
(`loaders` -> `consolidacao` -> `loaders`), entao o **callable** e
injetado pela fachada. Callable, e nao o frame ja carregado, de
proposito: a busca continua acontecendo so quando ha o que preencher —
carregar sempre acrescentaria uma consulta por consolidacao mesmo no
caso comum, em que nenhuma linha esta sem categoria.

Extraido na Etapa 2 da revisao de 09/2026. Corpos movidos sem
alteracao (prova de move byte-identico no commit).
"""

import pandas as pd

from src.config.settings import NOMES_DISPLAY_PRODUTO, PRODUTOS_EMISSAO


def eh_emissao(df: pd.DataFrame) -> pd.Series:
    """Emissao de cartao: ``TIPO_PRODUTO`` em ``PRODUTOS_EMISSAO``.

    **O unico criterio de Emissao do dashboard.** Consolidacao (zeragem
    de valor/pontos e flag ``is_emissao_cartao``), ``aplicar_conta_valor``
    (analise/cancelados), ``mascaras_aceleradores``, cards de quantidade
    e abas Produtos/Em Analise chamam esta funcao — o Caderno (SQL) usa
    o mesmo produto.

    Ate 09/2026 metade das superficies usava ``TIPO OPER. in {CARTAO
    BENEFICIO, Venda Pre-Adesao}``. Na base inteira os dois concordavam,
    exceto em 3 propostas de operacao de cartao com produto de SAQUE —
    que sao producao com valor. Decisao do usuario: vale o produto.
    Ver ``tests/test_criterio_emissao.py``.

    ``astype(str)`` antes de ``.str``: coluna toda nula chega como float.
    Sem a coluna, nada e emissao.
    """
    if "TIPO_PRODUTO" not in df.columns:
        return pd.Series(False, index=df.index)
    return (
        df["TIPO_PRODUTO"].astype(str).str.strip().str.upper()
        .isin({p.upper() for p in PRODUTOS_EMISSAO})
    )


# Fallback TIPO_PRODUTO → categoria, usado quando
# produtos.categoria_id esta NULL no banco (ver
# _preencher_categoria_fallback e migration 061).
_TIPO_PARA_CATEGORIA = {
    "CNC": "CNC",
    "CNC 13º": "CNC_13",
    "CNC 13": "CNC_13",
    "CNC ANT": "ANT_BENEF",
    "ANT. DE BENEF.": "ANT_BENEF",
    "SAQUE": "SAQUE",
    "SAQUE BENEFICIO": "SAQUE_BENEFICIO",
    "CONSIG": "CONSIG_BMG",
    "CONSIG BMG": "CONSIG_BMG",
    "CONSIG PRIV": "CONSIG_PRIV",
    "CLT": "CONSIG_PRIV",
    "CONSIG ITAU": "CONSIG_ITAU",
    "CONSIG Itau": "CONSIG_ITAU",
    "CONSIG C6": "CONSIG_C6",
    "FGTS": "FGTS",
    "EMISSAO": "CARTAO",
    "EMISSAO CB": "CARTAO",
    "EMISSAO CC": "CARTAO",
    "Portabilidade": "PORTABILIDADE",
    "PORTABILIDADE": "PORTABILIDADE",
}


# Portabilidade herda os pontos do CONSIG do banco origem.
# Chaves normalizadas (strip + upper). CONSIG_PRIV nao entra:
# Privado nao se aplica a portabilidade.
_PORTAB_BANCO_TO_CONSIG = {
    "BMG": "CONSIG_BMG",
    "BANCO BMG": "CONSIG_BMG",
    "C6 BANK": "CONSIG_C6",
    "C6": "CONSIG_C6",
    "BANCO C6": "CONSIG_C6",
    "ITAU": "CONSIG_ITAU",
    "ITAÚ": "CONSIG_ITAU",
    "BANCO ITAU": "CONSIG_ITAU",
    "BANCO ITAÚ": "CONSIG_ITAU",
}


# ── Saque no cartao Gov: taxa propria, nao a do cartao comum ──
#
# SAQUE e SAQUE_BENEFICIO nao pontuam pelo proprio codigo: aliasam
# para CARTAO (`categoria_pts_id`, migration 013), hoje 2,5. O saque
# feito no cartao Gov pontua 1 real = 1 ponto, e a migration 122 criou
# CARTAO_GOV para carregar essa taxa. Faltava quem consumisse o alias.
#
# POR QUE EM CODIGO E NAO VIA `categoria_pts_id`
# -----------------------------------------------
# Pelo mesmo motivo da Portabilidade acima: o diferencial nao cabe na
# categoria. `produtos.categoria_id` e resolvido por `tipo`/`subtipo`
# da planilha de produtos (angry-man, `import-produtos.ts`), e Gov e
# INSS compartilham tipo E nome de tabela — medido em 2026-09-25:
#
#   SAQUE COMPLEMENTAR - Digital Token - Não | INSS          | 4286
#   SAQUE COMPLEMENTAR - Digital Token - Não | GOVERNO DO RJ |    9
#
# Apontar esse produto para uma categoria Gov levaria 4.286 saques
# INSS junto. O unico campo que separa os dois e o CONVENIO, que vive
# no contrato — granularidade maior que categoria, igual ao BANCO da
# Portabilidade.
#
# VIGENCIA
# --------
# Decisao do usuario em 2026-09-25: a taxa nova vale de 09/2026 em
# diante; mes fechado continua como foi apurado e comunicado. O corte
# e por DATA (data_status_pagamento), que e de onde `periodo_id` e
# derivado — logo "DATA >= 01/09/2026" e exatamente "competencia >=
# 09/2026", e vale tambem na consolidacao por intervalo, que atravessa
# meses. Medido: 0 de 17.304 linhas de saque tem DATA nula, entao o
# corte nao deixa contrato de fora por dado ausente.
#
# PREMISSA A VALIDAR: SAQUE_BENEFICIO entra junto com SAQUE. Os dois
# aliasam para CARTAO hoje, e os produtos Gov aparecem nos dois
# (MFACIL CONSIG GOV RJ em SAQUE, CREDCESTA GOV RJ em
# SAQUE_BENEFICIO) — "saque no cartao Gov" cobre ambos. Em 09/2026 nao
# muda nada: nao ha SAQUE_BENEFICIO Gov pago no mes.
_SAQUE_GOV_CATEGORIAS = frozenset({"SAQUE", "SAQUE_BENEFICIO"})
_SAQUE_GOV_CONVENIOS = frozenset({"GOVERNO DO RJ"})
_SAQUE_GOV_CATEGORIA_PTS = "CARTAO_GOV"
_SAQUE_GOV_VIGENCIA = pd.Timestamp("2026-09-01")


def _mascara_saque_gov(df: pd.DataFrame) -> pd.Series:
    """Saques no cartao Gov sujeitos a taxa propria (``CARTAO_GOV``).

    Combinados por AND: categoria de saque, ``CONVENIO`` na lista Gov
    (normalizado, que a base nao e uniformemente maiuscula) e ``DATA``
    a partir da vigencia. Coluna ausente -> nenhuma linha, pelo mesmo
    criterio de ``eh_emissao``: criterio sem coluna nao classifica
    ninguem.
    """
    if "CONVENIO" not in df.columns or "DATA" not in df.columns:
        return pd.Series(False, index=df.index)
    return (
        df["categoria_codigo"].isin(_SAQUE_GOV_CATEGORIAS)
        & (
            df["CONVENIO"].astype(str).str.strip().str.upper()
            .isin(_SAQUE_GOV_CONVENIOS)
        )
        & (
            pd.to_datetime(df["DATA"], errors="coerce")
            >= _SAQUE_GOV_VIGENCIA
        )
    )


def aplicar_nomes_display_produto(frame: pd.DataFrame) -> pd.DataFrame:
    """Troca as chaves internas de ``grupo_dashboard`` pelo rotulo de UI.

    ``NOMES_DISPLAY_PRODUTO`` mapeia a chave de dados (ex: ``PACK``) para
    o nome amigavel exibido na interface, sem alterar nada no banco. A
    troca acontece na fronteira de carga — antes de qualquer calculo ou
    renderizacao — para que todos os agrupamentos e joins por produto
    usem um vocabulario unico.

    Aplicavel a qualquer frame que exponha ``grupo_dashboard``: contratos
    pagos, em analise, cancelados e a propria tabela de ``categorias``.
    Nao muta o frame recebido — devolve copia (via ``assign``) quando ha
    o que renomear e o proprio objeto quando nao ha (vazio ou sem a
    coluna).
    """
    if frame.empty or "grupo_dashboard" not in frame.columns:
        return frame
    return frame.assign(
        grupo_dashboard=frame["grupo_dashboard"].replace(NOMES_DISPLAY_PRODUTO)
    )


def preencher_categoria_fallback(
    df: pd.DataFrame,
    carregar_categorias,
) -> pd.DataFrame:
    """Preenche categoria (e derivados) quando o banco veio sem ela.

    O ETL sobrescreve ``produtos`` a cada import e, quando a planilha de
    origem renomeia um tipo (ex: ``CONSIG PRIV`` -> ``CLT``,
    ``CNC ANT`` -> ``ANT. DE BENEF.``), grava ``categoria_id = NULL``
    (ver ``database/migrations/061``). Sem este fallback as linhas ficam
    com ``categoria_codigo``/``grupo_dashboard`` vazios e desaparecem de
    tudo que agrupa por produto — inclusive dos filtros da aba
    Analiticos. Corrigir na origem (ETL) segue sendo o definitivo.

    Muta e devolve ``df``. So preenche colunas que ja existem no frame
    (em analise/cancelados nao trazem ``grupo_meta`` nem
    ``conta_pontuacao``).
    """
    if df.empty or "categoria_codigo" not in df.columns:
        return df

    # Normaliza NaN → "" antes da máscara: contratos com categoria_id NULL
    # no banco chegam como NaN (float) e quebram diagnósticos posteriores
    # (sorted misturando float/str). Ex.: Maio/2025 tinha 13 linhas
    # PAPCARD/CONTA SIMPLES sem categoria.
    df["categoria_codigo"] = df["categoria_codigo"].fillna("")
    mask_sem_cat = df["categoria_codigo"] == ""
    if not mask_sem_cat.any() or "TIPO_PRODUTO" not in df.columns:
        return df

    df.loc[mask_sem_cat, "categoria_codigo"] = (
        df.loc[mask_sem_cat, "TIPO_PRODUTO"]
        .map(_TIPO_PARA_CATEGORIA)
        .fillna("")
    )

    # Preencher grupo_dashboard, grupo_meta, conta_valor,
    # conta_pontuacao a partir das categorias do banco
    categorias = carregar_categorias()
    if categorias.empty:
        return df

    cat_map = categorias.set_index("codigo")
    preenchidos = mask_sem_cat & (df["categoria_codigo"] != "")

    for campo in [
        "grupo_dashboard",
        "grupo_meta",
        "conta_valor",
        "conta_pontuacao",
    ]:
        if campo in cat_map.columns and campo in df.columns:
            df.loc[preenchidos, campo] = (
                df.loc[preenchidos, "categoria_codigo"]
                .map(cat_map[campo])
            )

    return df


def consolidar_pontuacao(
    df: pd.DataFrame,
    df_pontos: pd.DataFrame,
    carregar_categorias,
) -> tuple:
    """Aplica pontuacao, regras de exclusao e classificacoes.

    Args:
        df: contratos pagos do periodo (nao vazio).
        df_pontos: tabela de pontuacao efetiva (categoria -> pontos).
        carregar_categorias: callable que devolve a tabela de
            categorias — ver o porque no topo do modulo.

    Returns:
        ``(df_consolidado, diagnostico)``. O diagnostico alimenta o
        expander de admin e e ``None`` quando nao ha o que diagnosticar.
    """
    df = preencher_categoria_fallback(df, carregar_categorias)

    # Mapear pontos por categoria_codigo
    if not df_pontos.empty:
        mapa_pontos = dict(
            zip(
                df_pontos["categoria_codigo"],
                df_pontos["pontos"].astype(float),
            )
        )
        df["PONTOS"] = df["categoria_codigo"].map(mapa_pontos).fillna(0)
    else:
        mapa_pontos = {}
        df["PONTOS"] = 0

    # PORTABILIDADE herda a pontuacao do CONSIG do banco origem.
    # Regra: Portabilidade BMG -> CONSIG_BMG, C6 -> CONSIG_C6,
    # Itau -> CONSIG_ITAU. CONSIG_PRIV nao se aplica a portabilidade
    # (produto distinto). Bancos sem mapeamento permanecem com 0.
    # Resolvido em codigo (nao via tabela pontuacao) porque o
    # diferencial e o BANCO do contrato, granularidade maior que
    # categoria.
    if "BANCO" in df.columns:
        mask_portab = df["categoria_codigo"] == "PORTABILIDADE"
        if mask_portab.any():
            banco_norm = (
                df.loc[mask_portab, "BANCO"]
                .astype(str).str.strip().str.upper()
            )
            consig_alvo = banco_norm.map(_PORTAB_BANCO_TO_CONSIG)
            pts_alias = consig_alvo.map(mapa_pontos)
            df.loc[mask_portab, "PONTOS"] = pts_alias.fillna(0).astype(
                float
            )

    # Saque no cartao Gov usa CARTAO_GOV, nao o alias CARTAO da
    # categoria. Ver o bloco de comentario de `_SAQUE_GOV_CATEGORIAS`
    # para o porque de morar aqui e nao em `categoria_pts_id`.
    #
    # Sem linha de CARTAO_GOV na pontuacao do periodo (planilha do mes
    # nao atualizada), a taxa antiga PERMANECE e a contagem vai para o
    # diagnostico. Cair para 0 apagaria producao paga em silencio, que
    # e o pior dos dois erros; manter 2,5 preserva o numero anterior e
    # o aviso diz que ele esta desatualizado.
    mask_saque_gov = _mascara_saque_gov(df)
    qtd_saque_gov = int(mask_saque_gov.sum())
    pts_saque_gov = mapa_pontos.get(_SAQUE_GOV_CATEGORIA_PTS)
    saque_gov_sem_taxa = 0
    if qtd_saque_gov:
        if pts_saque_gov is None:
            saque_gov_sem_taxa = qtd_saque_gov
        else:
            df.loc[mask_saque_gov, "PONTOS"] = float(pts_saque_gov)

    # ── Diagnostico de mapeamento ──────────────────
    total = len(df)
    sem_cat = (df["categoria_codigo"] == "").sum()
    com_cat = total - sem_cat
    com_pontos = (df["PONTOS"] > 0).sum()
    sem_pontos = com_cat - com_pontos

    tipos_sem_cat: list = []
    if sem_cat > 0 and "TIPO_PRODUTO" in df.columns:
        tipos_sem_cat = (
            df.loc[df["categoria_codigo"] == "", "TIPO_PRODUTO"]
            .value_counts()
            .reset_index()
            .rename(columns={"TIPO_PRODUTO": "tipo", "count": "qtd"})
            .to_dict(orient="records")
        )

    diag = {
        "total_contratos": total,
        "sem_categoria": int(sem_cat),
        "com_categoria": int(com_cat),
        "com_pontos_mapeados": int(com_pontos),
        "sem_pontos_mapeados": int(sem_pontos),
        "categorias_no_contrato": (
            sorted(df["categoria_codigo"].unique().tolist())
        ),
        "categorias_na_pontuacao": sorted(mapa_pontos.keys()),
        "mapa_pontos": mapa_pontos,
        "tipos_sem_categoria": tipos_sem_cat,
        # Saque no cartao Gov: quantos foram reclassificados para a
        # taxa de CARTAO_GOV e quantos ficaram com a taxa antiga por
        # falta da linha na pontuacao do periodo.
        "saque_gov_reclassificado": qtd_saque_gov - saque_gov_sem_taxa,
        "saque_gov_sem_pontuacao": saque_gov_sem_taxa,
    }
    # ───────────────────────────────────────────────

    # Aplicar regras de exclusao:
    # Produtos com conta_valor=false → VALOR = 0
    # Produtos com conta_pontuacao=false → pontos = 0
    mask_sem_valor = df["conta_valor"] == False  # noqa
    mask_sem_pontos = df["conta_pontuacao"] == False  # noqa

    df.loc[mask_sem_valor, "VALOR"] = 0
    df["pontos"] = df["VALOR"] * df["PONTOS"]
    df.loc[mask_sem_pontos, "pontos"] = 0

    # Super Conta: CNC com subtipo especifico — conta valor/pontos
    # como CNC e tambem e contado como producao Super Conta
    # Usar strip() e upper() para ser robusto contra espacos
    df["is_super_conta"] = (
        df["SUBTIPO"]
        .astype(str)
        .str.strip()
        .str.upper() == "SUPER CONTA"
    )

    # Classificacoes por TIPO OPER. (seguros)
    col_tipo_oper = "TIPO OPER."

    # Emissao de cartao: contam apenas quantidade. Criterio unico por
    # produto — ver `eh_emissao`.
    df["is_emissao_cartao"] = eh_emissao(df)

    # Zerar valor/pontos de emissoes mesmo quando a categoria nao traz
    # conta_valor=false (defesa contra cadastro de categoria incompleto).
    mask_emissao = df["is_emissao_cartao"]
    if mask_emissao.any():
        df.loc[mask_emissao, "VALOR"] = 0
        df.loc[mask_emissao, "pontos"] = 0

    # Seguros: contam apenas quantidade (valor/pontos ja zerados acima)
    # Fallback para categoria_codigo caso tipo_operacao nao esteja preenchido
    df["is_bmg_med"] = (
        (df[col_tipo_oper] == "BMG MED")
        if col_tipo_oper in df.columns
        else (df["categoria_codigo"] == "BMG_MED")
    )
    df["is_seguro_vida"] = (
        (df[col_tipo_oper] == "Seguro")
        if col_tipo_oper in df.columns
        else (df["categoria_codigo"] == "SEGURO_VIDA")
    )

    return df, diag
