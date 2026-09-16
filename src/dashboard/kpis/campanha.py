"""Regras da Campanha Semestral 2026-H2.

Regras **da campanha**, nao de producao. Moram separadas de
``kpis/gerais.py`` de proposito: o recorte de produtos, a meta e o
criterio de desempate valem para esta campanha e para mais nada. Mudar
qualquer coisa aqui nao pode mexer no numero do dashboard de vendas.

Contrato apurado (definido pelo usuario em 09/2026):

- Meta de **R$ 75 milhoes em VALOR** — nao em pontos.
- Produtos elegiveis: CNC, CLT, Consignado (inclui portabilidade),
  Antecipacao de Beneficio e FGTS. **SAQUE de cartao fica de fora.**
- Valem propostas **pagas** entre 01/07/2026 e 31/12/2026.
- Ranking de consultores e de lojas por **pontos**; desempate pela
  **producao de CNC**.

Duas decisoes do usuario que o codigo nao teria como inferir:

1. **Super Conta conta como CNC** — tanto na producao quanto no
   desempate. O projeto ja trata Super Conta como subtipo de CNC
   (``business-rules.md``), e a campanha seguiu a mesma leitura.
2. **A apuracao sempre reflete a base atual.** Contrato pago em julho e
   cancelado depois some da base no proximo import e sai da campanha
   sozinho — por isso nao existe aqui nenhuma regra de exclusao de
   cancelado. O efeito colateral aceito e que ranking ja divulgado pode
   mudar; nao ha snapshot congelado.
"""

from datetime import date
from typing import Optional

import pandas as pd

# ══════════════════════════════════════════════════════
# Parametros da campanha
# ══════════════════════════════════════════════════════

CAMPANHA_INICIO = date(2026, 7, 1)
CAMPANHA_FIM = date(2026, 12, 31)
META_VALOR = 75_000_000.0

CAMPANHA_ROTULO = "Campanha Semestral 2026 · 2º semestre"

# Categorias elegiveis, por familia declarada pelo usuario.
#
# Os codigos saem de `categorias_produto` (database/schema.sql). O
# mapa TIPO_PRODUTO -> categoria_codigo vive em
# `kpis/consolidacao.py::_TIPO_PARA_CATEGORIA` e ja foi aplicado pelo
# loader antes de chegar aqui — sem ele, ANT. DE BENEF. e CLT chegam
# SEM categoria (o ETL zera `categoria_id` quando a planilha renomeia o
# tipo; ver migration 061). Em 16/09/2026 isso era 27% dos contratos da
# janela e R$ 4,19 mi da apuracao.
CATEGORIAS_POR_FAMILIA: dict[str, tuple[str, ...]] = {
    # Super Conta e subtipo de CNC — decisao do usuario, 09/2026.
    "CNC": ("CNC", "SUPER_CONTA"),
    "CLT": ("CONSIG_PRIV",),
    "Consignado": ("CONSIG_BMG", "CONSIG_ITAU", "CONSIG_C6", "PORTABILIDADE"),
    "Ant. de Benef.": ("ANT_BENEF",),
    "FGTS": ("FGTS",),
}

CATEGORIAS_ELEGIVEIS = frozenset(
    codigo
    for codigos in CATEGORIAS_POR_FAMILIA.values()
    for codigo in codigos
)

# Desempate: producao de CNC. Segue a mesma leitura da familia CNC —
# Super Conta incluida.
CATEGORIAS_DESEMPATE = frozenset(CATEGORIAS_POR_FAMILIA["CNC"])

# Fora da campanha, explicito para quem for auditar: SAQUE e
# SAQUE_BENEFICIO (o "saque do cartao" que o usuario excluiu), alem de
# CARTAO/BMG_MED/SEGURO_VIDA, que nao contam valor em lugar nenhum.
#
# CNC_13 ("CNC 13º") NAO esta elegivel: o usuario nomeou cinco familias
# e CNC_13 e categoria propria, com `grupo_meta = FGTS_ANT_BENEF_13`.
# Em 16/09/2026 nao havia nenhum contrato CNC_13 na janela, mas 13º e
# produto de nov/dez — DENTRO da campanha. Confirmar antes de novembro;
# incluir e acrescentar "CNC_13" a familia CNC acima.
CATEGORIAS_EXCLUIDAS_NOTAVEIS = ("SAQUE", "SAQUE_BENEFICIO", "CNC_13")


# ══════════════════════════════════════════════════════
# Recorte
# ══════════════════════════════════════════════════════


def filtrar_janela(
    df: pd.DataFrame,
    inicio: date = CAMPANHA_INICIO,
    fim: date = CAMPANHA_FIM,
) -> pd.DataFrame:
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
    limite = pd.Timestamp(fim) + pd.Timedelta(days=1)
    dentro = (
        datas.notna()
        & (datas >= pd.Timestamp(inicio))
        & (datas < limite)
    )
    return df[dentro].copy()


def filtrar_elegiveis(df: pd.DataFrame) -> pd.DataFrame:
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

    return df[df["categoria_codigo"].isin(CATEGORIAS_ELEGIVEIS)].copy()


def preparar(
    df: pd.DataFrame,
    inicio: date = CAMPANHA_INICIO,
    fim: date = CAMPANHA_FIM,
) -> pd.DataFrame:
    """Janela + elegibilidade, na ordem. Entrada de tudo mais aqui."""
    return filtrar_elegiveis(filtrar_janela(df, inicio, fim))


# ══════════════════════════════════════════════════════
# Apuracao
# ══════════════════════════════════════════════════════


def _soma(df: pd.DataFrame, coluna: str) -> float:
    if df.empty or coluna not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[coluna], errors="coerce").fillna(0).sum())


def apurar(
    df: pd.DataFrame,
    meta: float = META_VALOR,
) -> dict:
    """Numeros de topo da campanha.

    ``df`` deve vir de :func:`preparar`. ``valor`` e a producao
    consolidada (``VALOR``, ja com os zeramentos de ``conta_valor`` e
    emissao aplicados na consolidacao) — e o que conta para os R$ 75 mi.

    Returns:
        dict com ``valor``, ``meta``, ``atingimento`` (0-1+), ``falta``,
        ``pontos``, ``qtd``, ``valor_cnc``.
    """
    valor = _soma(df, "VALOR")
    cnc = (
        df[df["categoria_codigo"].isin(CATEGORIAS_DESEMPATE)]
        if not df.empty and "categoria_codigo" in df.columns
        else df
    )
    return {
        "valor": valor,
        "meta": float(meta),
        "atingimento": (valor / meta) if meta else 0.0,
        "falta": max(float(meta) - valor, 0.0),
        "pontos": _soma(df, "pontos"),
        "qtd": int(len(df)),
        "valor_cnc": _soma(cnc, "VALOR"),
    }


def apurar_por_familia(df: pd.DataFrame) -> pd.DataFrame:
    """Quebra da producao pelas cinco familias declaradas na campanha.

    Agrupa por FAMILIA (o rotulo que o usuario usou), nao por
    ``categoria_codigo`` — e como a rede le a campanha. Familia sem
    contrato aparece zerada em vez de sumir: ausencia de linha e
    ambigua entre "nao vendeu" e "regra nao pegou".
    """
    linhas = []
    for familia, codigos in CATEGORIAS_POR_FAMILIA.items():
        parte = (
            df[df["categoria_codigo"].isin(codigos)]
            if not df.empty and "categoria_codigo" in df.columns
            else df.iloc[0:0]
        )
        linhas.append(
            {
                "Família": familia,
                "Contratos": int(len(parte)),
                "Valor": _soma(parte, "VALOR"),
                "Pontos": _soma(parte, "pontos"),
            }
        )

    out = pd.DataFrame(linhas)
    total = out["Valor"].sum()
    out["% do Total"] = (out["Valor"] / total * 100) if total else 0.0
    return out.sort_values("Valor", ascending=False).reset_index(drop=True)


# ══════════════════════════════════════════════════════
# Rankings
# ══════════════════════════════════════════════════════


def ranking(
    df: pd.DataFrame,
    coluna: str,
    top: Optional[int] = None,
) -> pd.DataFrame:
    """Ranking por PONTOS, desempate por producao de CNC.

    ``coluna`` e ``CONSULTOR`` ou ``LOJA``. O desempate entra como
    segunda chave de ordenacao — e o criterio declarado da campanha, e
    fica materializado numa coluna visivel ("CNC (desempate)") para que
    quem contesta a posicao veja o numero que a decidiu.

    A posicao e ``1..n`` densa: empate real nos DOIS criterios divide a
    mesma posicao, em vez de escolher um vencedor pela ordem alfabetica
    que o sort deixou por acaso.
    """
    vazio = pd.DataFrame(
        columns=[coluna, "Pontos", "Valor", "CNC (desempate)", "Contratos"]
    )
    if df.empty or coluna not in df.columns:
        return vazio

    base = df.copy()
    base["_cnc"] = base["VALOR"].where(
        base["categoria_codigo"].isin(CATEGORIAS_DESEMPATE), 0.0
    )

    out = (
        base.groupby(coluna, dropna=False)
        .agg(
            Pontos=("pontos", "sum"),
            Valor=("VALOR", "sum"),
            **{"CNC (desempate)": ("_cnc", "sum")},
            Contratos=(coluna, "size"),
        )
        .reset_index()
    )
    if out.empty:
        return vazio

    out = out.sort_values(
        ["Pontos", "CNC (desempate)"], ascending=[False, False]
    ).reset_index(drop=True)

    # Posicao densa sobre o PAR (pontos, cnc): so quem empata nos dois
    # criterios divide posicao.
    chave = list(zip(out["Pontos"], out["CNC (desempate)"]))
    posicoes, anterior, pos = [], None, 0
    for i, atual in enumerate(chave, start=1):
        if atual != anterior:
            pos, anterior = i, atual
        posicoes.append(pos)
    out.insert(0, "#", posicoes)

    return out.head(top) if top else out


# ══════════════════════════════════════════════════════
# Ritmo
# ══════════════════════════════════════════════════════


def ritmo(
    apuracao: dict,
    hoje: Optional[date] = None,
    inicio: date = CAMPANHA_INICIO,
    fim: date = CAMPANHA_FIM,
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
    total_dias = (fim - inicio).days + 1

    if hoje < inicio:
        decorridos = 0
    elif hoje > fim:
        decorridos = total_dias
    else:
        decorridos = (hoje - inicio).days + 1

    restantes = max(total_dias - decorridos, 0)
    valor = apuracao.get("valor", 0.0)
    meta = apuracao.get("meta", META_VALOR)

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
