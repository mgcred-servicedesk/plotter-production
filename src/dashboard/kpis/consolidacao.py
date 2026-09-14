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

from src.config.settings import NOMES_DISPLAY_PRODUTO


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

    # Classificacoes por TIPO OPER. (mesma logica do dashboard original)
    col_tipo_oper = "TIPO OPER."

    # Emissao de cartao: contam apenas quantidade
    df["is_emissao_cartao"] = (
        df[col_tipo_oper].isin(["CARTÃO BENEFICIO", "Venda Pré-Adesão"])
        if col_tipo_oper in df.columns
        else False
    )

    # Zerar valor/pontos de emissoes nao cobertas por conta_valor=false
    # (ex: Venda Pre-Adesao com produto CONSIG tem categoria CONSIG_BMG
    # que possui conta_valor=true, mas o TIPO OPER. indica emissao)
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
