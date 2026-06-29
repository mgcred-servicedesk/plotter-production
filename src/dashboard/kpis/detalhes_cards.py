"""Funcoes puras de detalhamento (drill-down) dos cards de KPI.

Cada funcao recebe DataFrames ja carregados e RLS-aplicados (client-side)
e devolve um ``pd.DataFrame`` pronto para a UI consumir. Sem Streamlit,
sem acesso a Supabase, sem efeitos colaterais.

Convencoes de coluna (verdade = loader / RPCs):

- Colunas de vendas/cancelados em MAIUSCULAS: ``PRODUTO``, ``REGIAO``,
  ``LOJA``, ``CONSULTOR``, ``VALOR``, ``DATA_CADASTRO``,
  ``CLASSIFICACAO``, ``RECUPERADA_OUTRO``, ``RECUPERADA_OUTRA_LOJA``,
  ``RECUPERADA_OUTRA_REGIAO``; mais as minusculas ``grupo_dashboard``,
  ``categoria_codigo``, ``conta_valor``.
- EXCECAO: o df de digitacao diaria vem do RPC ``obter_digitacao_diaria``
  com colunas MINUSCULAS ``data_cadastro`` (DATE), ``qtd_digitada`` (int)
  e ``valor_digitado`` (float). Consumidas apenas em
  ``detalhe_digitacao_diaria``.

Regras transversais:

- ``conta_valor=False``: zera o VALOR dessas linhas nos breakdowns de
  analise/cancelados/medias SEM alterar a contagem de registros. A
  digitacao diaria usa o valor bruto do RPC (nao aplica essa regra).
- Projecao linear por linha: ``valor / du_decorridos * du_totais``,
  com ``du_decorridos <= 0 -> 0.0``.
- Medias (quadro 4): ``media = total_do_grupo / qtd_distinta_no_grupo``
  (PRINCIPAL) e ``media DU = media / du_decorridos`` (SECUNDARIO), com a
  MESMA base. base distinta de CONSULTOR exclui supervisores via
  ``excluir_supervisores``.
"""

from typing import Optional

import pandas as pd

from src.config.settings import NOMES_DISPLAY_PRODUTO
from src.dashboard.kpis.gerais import (
    excluir_supervisores,
    separar_cancelados_liquidos,
)

# Desmembramento do grupo 'PACK' (grupo_dashboard) nas suas categorias
# granulares para os pivots de detalhe. A chave e o ``categoria_codigo``
# (verdade dos contratos / RPC); o valor e o rotulo exibido. Linhas fora
# deste mapa mantem o ``grupo_dashboard``. Espelha a composicao do PACK
# em ``PRODUTOS_DASHBOARD['FGTS_ANT_BEN_CNC13']`` (gerais.py).
PACK_SPLIT_LABELS = {
    "FGTS": "FGTS",
    "ANT_BENEF": "Antecipação",
    "CNC_13": "13o",
}

# Nome da coluna derivada que substitui ``grupo_dashboard`` nos pivots
# de detalhe quando o PACK e desmembrado.
COL_PRODUTO_DETALHADO = "PRODUTO_DETALHADO"


def adicionar_produto_detalhado(df: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta ``PRODUTO_DETALHADO`` desmembrando o grupo 'PACK'.

    Para cada linha: se ``categoria_codigo`` pertence ao PACK
    (``PACK_SPLIT_LABELS``), usa o rotulo granular (FGTS / Antecipação /
    13o); caso contrario mantem o ``grupo_dashboard`` (aplicando
    ``NOMES_DISPLAY_PRODUTO`` como rede de seguranca para qualquer 'PACK'
    residual que nao tenha caido no split). Copia defensiva.

    Se faltar ``grupo_dashboard``, devolve o df inalterado (os pivots
    fazem fallback para ``grupo_dashboard`` quando a coluna nao existe).
    """
    if df.empty or "grupo_dashboard" not in df.columns:
        return df
    out = df.copy()
    base = out["grupo_dashboard"].replace(NOMES_DISPLAY_PRODUTO)
    if "categoria_codigo" in out.columns:
        granular = out["categoria_codigo"].map(PACK_SPLIT_LABELS)
        out[COL_PRODUTO_DETALHADO] = granular.fillna(base)
    else:
        out[COL_PRODUTO_DETALHADO] = base
    return out


# ──────────────────────────────────────────────────────────────────
# Helpers internos
# ──────────────────────────────────────────────────────────────────


def _projetar(valor: float, du_decorridos: int, du_totais: int) -> float:
    """Projecao linear de um valor acumulado para o fim do periodo.

    ``valor / du_decorridos * du_totais``. ``du_decorridos <= 0``
    devolve ``0.0`` (sem dias decorridos nao ha ritmo a projetar).
    """
    if du_decorridos <= 0:
        return 0.0
    return float(valor) / du_decorridos * du_totais


def _aplicar_conta_valor(df: pd.DataFrame) -> pd.DataFrame:
    """Zera ``VALOR`` das linhas ``conta_valor=False`` (copia defensiva).

    Mantem todas as linhas (a contagem nao muda) — apenas neutraliza o
    VALOR das categorias que nao contam para o total monetario. Se a
    coluna ``conta_valor`` nao existir, devolve copia inalterada.
    """
    out = df.copy()
    if "conta_valor" in out.columns and "VALOR" in out.columns:
        nao_conta = ~out["conta_valor"].fillna(True).astype(bool)
        out.loc[nao_conta, "VALOR"] = 0.0
    return out


def _breakdown_por_dimensao(
    df: pd.DataFrame,
    dimensao: str,
    du_decorridos: int,
    du_totais: int,
) -> pd.DataFrame:
    """Agrega VALOR/Quantidade por ``dimensao`` e projeta o total.

    Quantidade conta apenas registros com ``VALOR > 0`` (apos a regra
    ``conta_valor``), espelhando a definicao de quantidade dos demais
    KPIs (ver ``calcular_kpis_por_produto``). df vazio ou sem a coluna
    devolve df vazio com as colunas de saida.
    """
    cols = [
        dimensao,
        "Valor",
        "Quantidade",
        "Ticket Médio",
        "Média DU",
        "Projeção",
    ]
    if df.empty or dimensao not in df.columns:
        return pd.DataFrame(columns=cols)

    base = _aplicar_conta_valor(df)
    linhas = []
    for chave in sorted(base[dimensao].fillna("OUTROS").unique()):
        grupo = base[base[dimensao].fillna("OUTROS") == chave]
        valor = float(grupo["VALOR"].sum())
        quantidade = int((grupo["VALOR"] > 0).sum())
        ticket = valor / quantidade if quantidade > 0 else 0.0
        media_du = valor / du_decorridos if du_decorridos > 0 else 0.0
        projecao = _projetar(valor, du_decorridos, du_totais)
        linhas.append(
            {
                dimensao: chave,
                "Valor": valor,
                "Quantidade": quantidade,
                "Ticket Médio": ticket,
                "Média DU": media_du,
                "Projeção": projecao,
            }
        )
    return pd.DataFrame(linhas, columns=cols)


def _medias_por_dimensao(
    df: pd.DataFrame,
    dimensao: str,
    base: str,
    du_decorridos: int,
    du_totais: int,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Media por grupo da ``dimensao`` com base ``consultor`` ou ``loja``.

    ``Média`` (PRINCIPAL) = total do grupo / nº distinto da base no
    grupo; ``Média DU`` (SECUNDARIO) = Média / du_decorridos — MESMA
    base nas duas. ``Projeção`` = Média DU × du_totais, projetando o
    ritmo atual até o fim do período. ``base='consultor'`` exclui
    supervisores via ``excluir_supervisores``. df vazio / sem colunas
    → df vazio com as colunas de saida.
    """
    coluna_base = "CONSULTOR" if base == "consultor" else "LOJA"
    cols = [dimensao, "Valor", "Qtd Base", "Média", "Média DU", "Projeção"]

    if df.empty or dimensao not in df.columns or coluna_base not in df.columns:
        return pd.DataFrame(columns=cols)

    trabalho = _aplicar_conta_valor(df)
    if base == "consultor":
        trabalho = excluir_supervisores(trabalho, df_supervisores)
    if trabalho.empty:
        return pd.DataFrame(columns=cols)

    linhas = []
    for chave in sorted(trabalho[dimensao].fillna("OUTROS").unique()):
        grupo = trabalho[trabalho[dimensao].fillna("OUTROS") == chave]
        valor = float(grupo["VALOR"].sum())
        qtd_base = int(grupo[coluna_base].nunique())
        media = valor / qtd_base if qtd_base > 0 else 0.0
        media_du = media / du_decorridos if du_decorridos > 0 else 0.0
        projecao = media_du * du_totais if du_totais > 0 else 0.0
        linhas.append(
            {
                dimensao: chave,
                "Valor": valor,
                "Qtd Base": qtd_base,
                "Média": media,
                "Média DU": media_du,
                "Projeção": projecao,
            }
        )
    return pd.DataFrame(linhas, columns=cols)


# ──────────────────────────────────────────────────────────────────
# Quadro 1 — Analise por produto / regiao
# ──────────────────────────────────────────────────────────────────


def detalhe_analise_por_produto(
    df_analise: pd.DataFrame,
    du_decorridos: int,
    du_totais: int,
) -> pd.DataFrame:
    """Detalhe dos contratos em ANALISE por grupo de produto.

    Saida: ``grupo_dashboard, Valor, Quantidade, Ticket Médio,
    Média DU, Projeção``.
    """
    return _breakdown_por_dimensao(
        df_analise, "grupo_dashboard", du_decorridos, du_totais
    )


def detalhe_analise_por_regiao(
    df_analise: pd.DataFrame,
    du_decorridos: int,
    du_totais: int,
    dimensao: str = "REGIAO",
) -> pd.DataFrame:
    """Detalhe dos contratos em ANALISE por ``dimensao``.

    Default ``REGIAO`` mantem o comportamento anterior. Para perfis
    gerenciais por loja, use ``dimensao='LOJA'``. Saida: ``<dimensao>,
    Valor, Quantidade, Ticket Médio, Média DU, Projeção``.
    """
    return _breakdown_por_dimensao(
        df_analise, dimensao, du_decorridos, du_totais
    )


def filtrar_ultimo_dia(df_analise: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Filtra ``df_analise`` para o ultimo dia apurado (max DATA_CADASTRO).

    Devolve ``(df_filtrado, rotulo)`` com ``rotulo`` no formato
    ``dd/mm/aaaa`` (``""`` se nao houver data valida). Compara apenas a
    parte de data (ignora a hora). df vazio / sem ``DATA_CADASTRO`` →
    ``(df, "")``. Linhas com data nula nunca entram no ultimo dia.
    """
    if df_analise.empty or "DATA_CADASTRO" not in df_analise.columns:
        return df_analise, ""
    datas = pd.to_datetime(df_analise["DATA_CADASTRO"], errors="coerce")
    if datas.notna().sum() == 0:
        return df_analise.iloc[0:0], ""
    dias = datas.dt.normalize()
    ultimo = dias.max()
    return df_analise[dias == ultimo], ultimo.strftime("%d/%m/%Y")


def detalhe_analise_pivot(
    df_analise: pd.DataFrame,
    linha: str,
    coluna: str,
) -> pd.DataFrame:
    """Pivot do VALOR em ANALISE: ``linha`` × ``coluna`` com Totais.

    Matriz no formato da imagem-referencia: ``linha`` (ex. ``REGIAO``)
    nas linhas, cada valor distinto de ``coluna`` (ex. ``grupo_dashboard``
    ou ``BANCO``) nas colunas, celula = soma de VALOR. Acrescenta uma
    coluna ``Total`` (soma da linha) e uma linha ``Total`` (soma de cada
    coluna).

    Aplica ``conta_valor`` (zera o VALOR das linhas que nao contam, sem
    remover registros). Nulos nas duas dimensoes viram bucket ``OUTROS``.
    Colunas e linhas ficam em ordem alfabetica, com ``Total`` por ultimo.
    df vazio / sem as colunas necessarias → df vazio com apenas a coluna
    ``linha``.
    """
    if (
        df_analise.empty
        or linha not in df_analise.columns
        or coluna not in df_analise.columns
        or "VALOR" not in df_analise.columns
    ):
        return pd.DataFrame(columns=[linha])

    base = _aplicar_conta_valor(df_analise)
    base[linha] = base[linha].fillna("OUTROS")
    base[coluna] = base[coluna].fillna("OUTROS")

    pivot = base.pivot_table(
        index=linha,
        columns=coluna,
        values="VALOR",
        aggfunc="sum",
        fill_value=0.0,
    )
    pivot = pivot.reindex(sorted(pivot.columns), axis=1).sort_index()

    pivot["Total"] = pivot.sum(axis=1)
    total_row = pivot.sum(axis=0)
    total_row.name = "Total"
    pivot = pd.concat([pivot, total_row.to_frame().T])

    pivot.index.name = linha
    return pivot.reset_index()


def ocultar_colunas_zeradas(pivot: pd.DataFrame, linha: str) -> pd.DataFrame:
    """Remove do pivot as colunas de valor inteiramente zeradas.

    Mantem sempre ``linha`` (dimensao) e ``Total``. Uma coluna de
    produto/banco cujo VALOR e zero em TODAS as linhas — caso tipico do
    bucket ``OUTROS`` (emissoes/seguros com ``conta_valor=False``) ou de
    produtos sem digitacao no dia — apenas ocupa espaco; e descartada.
    Como as colunas removidas sao todas-zero, os ``Total`` por linha NAO
    mudam. Pivot vazio / so com ``linha`` → inalterado.
    """
    if pivot.empty or pivot.shape[1] <= 1:
        return pivot
    manter = [
        col
        for col in pivot.columns
        if col in (linha, "Total")
        or (pd.to_numeric(pivot[col], errors="coerce").fillna(0.0) != 0).any()
    ]
    return pivot[manter]


# ──────────────────────────────────────────────────────────────────
# Quadro 2 — Digitacao diaria (RPC obter_digitacao_diaria)
# ──────────────────────────────────────────────────────────────────


def detalhe_digitacao_diaria(
    df_digitacao: pd.DataFrame,
    du_decorridos: int,
    du_totais: int,
    ultimos_dias: Optional[int] = None,
    incluir_projecao: bool = True,
    base_variacao: str = "qtd",
) -> pd.DataFrame:
    """Serie diaria de digitacao com variacao vs. o dia anterior.

    Consome o df cru do RPC ``obter_digitacao_diaria`` (colunas
    MINUSCULAS ``data_cadastro``, ``qtd_digitada``, ``valor_digitado``).
    Usa o valor bruto do RPC — NAO aplica ``conta_valor``.

    ``Var. Qtd`` (delta absoluto da quantidade) e ``Var. %`` (percentual;
    1ª linha e divisao por zero → 0). ``base_variacao`` define a coluna-
    base do ``Var. %``: ``"qtd"`` (default, variacao da QUANTIDADE) ou
    ``"valor"`` (variacao do VALOR digitado — para tabelas focadas em
    valor). A ultima linha e a projecao do acumulado do mes.

    ``ultimos_dias`` (opcional) limita as linhas DIARIAS exibidas as N
    mais recentes — a variacao continua calculada sobre a serie completa
    e a projecao usa o acumulado do mes INTEIRO (nao apenas os N dias).

    ``incluir_projecao=False`` devolve apenas as linhas diarias, sem a
    linha "Projeção do mês" no rodape.

    Saida: ``data_cadastro, qtd_digitada, Var. Qtd, Var. %,
    valor_digitado``.
    """
    cols = [
        "data_cadastro",
        "qtd_digitada",
        "Var. Qtd",
        "Var. %",
        "valor_digitado",
    ]
    if df_digitacao.empty or "qtd_digitada" not in df_digitacao.columns:
        return pd.DataFrame(columns=cols)

    out = df_digitacao.copy()
    out = out.sort_values("data_cadastro").reset_index(drop=True)
    # Uniformiza data_cadastro como string dd/mm/aaaa: a ultima linha
    # leva o rotulo "Projeção do mês", e uma coluna object com
    # Timestamp + str quebra o Arrow ao serializar (st.dataframe).
    out["data_cadastro"] = pd.to_datetime(
        out["data_cadastro"], errors="coerce"
    ).dt.strftime("%d/%m/%Y")
    out["qtd_digitada"] = (
        pd.to_numeric(out["qtd_digitada"], errors="coerce").fillna(0).astype(int)
    )
    out["valor_digitado"] = (
        pd.to_numeric(out["valor_digitado"], errors="coerce").fillna(0.0)
        if "valor_digitado" in out.columns
        else 0.0
    )

    qtd_anterior = out["qtd_digitada"].shift(1)
    out["Var. Qtd"] = (out["qtd_digitada"] - qtd_anterior).fillna(0).astype(int)
    # Coluna-base do Var. %: quantidade (default) ou valor digitado.
    col_var = "valor_digitado" if base_variacao == "valor" else "qtd_digitada"
    base_anterior = out[col_var].shift(1)
    var_pct = (out[col_var] - base_anterior) / base_anterior * 100
    # 1ª linha (sem anterior) e divisao por zero (anterior == 0) → 0
    out["Var. %"] = var_pct.replace([float("inf"), float("-inf")], 0.0).fillna(0.0)

    out = out[cols]

    # Projecao do acumulado do mes INTEIRO (antes de cortar para os
    # ultimos N dias, senao a projecao consideraria so a janela exibida).
    qtd_acum = int(out["qtd_digitada"].sum())
    valor_acum = float(out["valor_digitado"].sum())
    if ultimos_dias is not None and ultimos_dias > 0:
        out = out.tail(ultimos_dias).reset_index(drop=True)

    if not incluir_projecao:
        return out

    linha_proj = pd.DataFrame(
        [
            {
                "data_cadastro": "Projeção do mês",
                "qtd_digitada": int(
                    round(_projetar(qtd_acum, du_decorridos, du_totais))
                ),
                "Var. Qtd": 0,
                "Var. %": 0.0,
                "valor_digitado": _projetar(valor_acum, du_decorridos, du_totais),
            }
        ],
        columns=cols,
    )
    return pd.concat([out, linha_proj], ignore_index=True)


# ──────────────────────────────────────────────────────────────────
# Quadro 3 — Cancelados por produto / regiao
# ──────────────────────────────────────────────────────────────────


def detalhe_cancelados_por_produto(
    df_cancelados: pd.DataFrame,
    du_decorridos: int,
    du_totais: int,
) -> pd.DataFrame:
    """Detalhe dos cancelados LIQUIDOS por grupo de produto.

    Considera apenas ``CLASSIFICACAO=='liquido'`` (via
    ``separar_cancelados_liquidos``); redigitadas/recuperadas saem da
    contagem. Saida: ``grupo_dashboard, Valor, Quantidade, Ticket Médio,
    Média DU, Projeção``.
    """
    liquidos, _, _ = separar_cancelados_liquidos(df_cancelados)
    return _breakdown_por_dimensao(
        liquidos, "grupo_dashboard", du_decorridos, du_totais
    )


def detalhe_cancelados_por_regiao(
    df_cancelados: pd.DataFrame,
    du_decorridos: int,
    du_totais: int,
    dimensao: str = "REGIAO",
) -> pd.DataFrame:
    """Detalhe dos cancelados LIQUIDOS por ``dimensao``.

    Default ``REGIAO`` mantem o comportamento anterior. Para perfis
    gerenciais por loja, use ``dimensao='LOJA'``. Considera apenas
    ``CLASSIFICACAO=='liquido'``. Saida: ``<dimensao>, Valor,
    Quantidade, Ticket Médio, Média DU, Projeção``.
    """
    liquidos, _, _ = separar_cancelados_liquidos(df_cancelados)
    return _breakdown_por_dimensao(
        liquidos, dimensao, du_decorridos, du_totais
    )


def detalhe_cancelados_pivot(
    df_cancelados: pd.DataFrame,
    linha: str,
    coluna: str,
) -> pd.DataFrame:
    """Pivot de VALOR dos cancelados LIQUIDOS: ``linha`` × ``coluna``.

    Mesma matriz com Totais de ``detalhe_analise_pivot``, mas restrita
    aos cancelados ``CLASSIFICACAO=='liquido'`` (redigitadas/recuperadas
    saem). Reusa o pivot generico apos filtrar os liquidos.
    """
    liquidos, _, _ = separar_cancelados_liquidos(df_cancelados)
    return detalhe_analise_pivot(liquidos, linha, coluna)


# ──────────────────────────────────────────────────────────────────
# Quadro Reaproveitamento — composicao (sem projecao)
# ──────────────────────────────────────────────────────────────────


def detalhe_reaproveitamento(df_cancelados: pd.DataFrame) -> pd.DataFrame:
    """Composicao de reaproveitamento de cancelados (sem projecao).

    Compoe (semantica das migrations 032/033):

    - ``Redigitada/Recuperada``: cancelados ``CLASSIFICACAO`` em
      {``redigitada``, ``recuperada``} — venda salva no proprio nivel.
    - ``Oportunidade Perdida (Consultor)`` / ``(Loja)`` / ``(Região)``:
      cancelados cuja venda foi capturada em OUTRO nivel, via flags
      ``RECUPERADA_OUTRO`` / ``RECUPERADA_OUTRA_LOJA`` /
      ``RECUPERADA_OUTRA_REGIAO`` (so qtd e valor; quem capturou nao e
      exposto).

    Aplica ``conta_valor`` ao VALOR (sem mexer na contagem). df vazio →
    df vazio com as colunas de saida. Saida: ``Categoria, Quantidade,
    Valor``.
    """
    cols = ["Categoria", "Quantidade", "Valor"]
    if df_cancelados.empty:
        return pd.DataFrame(columns=cols)

    base = _aplicar_conta_valor(df_cancelados)

    linhas = []

    if "CLASSIFICACAO" in base.columns:
        salvos = base[
            base["CLASSIFICACAO"].isin(["redigitada", "recuperada"])
        ]
        linhas.append(
            {
                "Categoria": "Redigitada/Recuperada",
                "Quantidade": int(len(salvos)),
                "Valor": float(salvos["VALOR"].sum())
                if "VALOR" in salvos.columns
                else 0.0,
            }
        )

    flags = [
        ("RECUPERADA_OUTRO", "Oportunidade Perdida (Consultor)"),
        ("RECUPERADA_OUTRA_LOJA", "Oportunidade Perdida (Loja)"),
        ("RECUPERADA_OUTRA_REGIAO", "Oportunidade Perdida (Região)"),
    ]
    for coluna_flag, rotulo in flags:
        if coluna_flag not in base.columns:
            continue
        perdidas = base[base[coluna_flag].fillna(False).astype(bool)]
        linhas.append(
            {
                "Categoria": rotulo,
                "Quantidade": int(len(perdidas)),
                "Valor": float(perdidas["VALOR"].sum())
                if "VALOR" in perdidas.columns
                else 0.0,
            }
        )

    if not linhas:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(linhas, columns=cols)


# ──────────────────────────────────────────────────────────────────
# Quadro 4 — Medias por produto / regiao
# ──────────────────────────────────────────────────────────────────


def detalhe_medias_por_produto(
    df: pd.DataFrame,
    base: str,
    du_decorridos: int,
    du_totais: int,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Media por grupo de produto (base ``consultor`` ou ``loja``).

    ``Média`` = Valor / Qtd Base; ``Média DU`` = Média / du_decorridos,
    com a MESMA base. ``Projeção`` = Média DU × du_totais. ``base='consultor'``
    exclui supervisores. Saida: ``grupo_dashboard, Valor, Qtd Base, Média,
    Média DU, Projeção``.
    """
    return _medias_por_dimensao(
        df, "grupo_dashboard", base, du_decorridos, du_totais, df_supervisores
    )


def detalhe_medias_por_regiao(
    df: pd.DataFrame,
    base: str,
    du_decorridos: int,
    du_totais: int,
    df_supervisores: Optional[pd.DataFrame] = None,
    dimensao: str = "REGIAO",
) -> pd.DataFrame:
    """Media por ``dimensao`` (base ``consultor`` ou ``loja``).

    Default ``REGIAO`` mantem o comportamento anterior. Para perfis
    gerenciais por loja, use ``dimensao='LOJA'``. ``Média`` = Valor /
    Qtd Base; ``Média DU`` = Média / du_decorridos, com a MESMA base.
    ``Projeção`` = Média DU × du_totais. ``base='consultor'`` exclui
    supervisores. Saida: ``<dimensao>, Valor, Qtd Base, Média, Média DU,
    Projeção``.
    """
    return _medias_por_dimensao(
        df, dimensao, base, du_decorridos, du_totais, df_supervisores
    )
