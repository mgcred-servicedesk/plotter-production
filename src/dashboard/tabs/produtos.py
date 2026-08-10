"""
Aba Produtos: KPIs, meta diaria e grafico por produto.

Alem do render, este modulo e o dono do carregamento **lazy** dos dois
meses de comparacao que so esta aba consome (mes anterior e mesmo mes do
ano anterior). Ver ``_carregar_mes_comparativo``.
"""

import logging
from typing import Optional

import pandas as pd
import streamlit as st
import streamlit_antd_components as sac

from src.dashboard.formatters import formatar_moeda, formatar_numero
from src.dashboard.kpis.produtos import calcular_kpis_por_produto
from src.dashboard.kpis.regioes import (
    calcular_evolucao_media_du,
    calcular_heatmap_regiao_produto,
)
from src.dashboard.loaders import (
    aplicar_nomes_display_produto,
    consolidar_dados,
)
from src.dashboard.ui.charts import (
    criar_grafico_produtos,
    criar_heatmap_regiao_produto,
)
from src.dashboard.ui.header import chart_card_close, chart_card_open
from src.dashboard.ui.sidebar import aplicar_filtros_ui
from src.dashboard.rls import _obter_perfil_efetivo, aplicar_rls
from src.shared.dias_uteis import calcular_dias_uteis, carregar_feriados

logger = logging.getLogger(__name__)

# Regiões excluídas do heatmap comparativo
_REGIOES_EXCLUIR_HM: frozenset = frozenset({"ALEXANDRE"})

# Prefixos das chaves de session_state dos meses de comparação. Ficam
# aqui, e não soltos nos call sites, para que carregar e limpar leiam da
# MESMA lista: o YoY já ficou de fora do "Atualizar Dados" uma vez por
# ter sido acrescentado só no carregamento (ver
# ``limpar_cache_comparativos``).
_PREFIXO_MES_ANT = "_df_ant"
_PREFIXO_ANO_ANT = "_df_ano_ant"
_PREFIXOS_COMPARATIVO = (_PREFIXO_MES_ANT, _PREFIXO_ANO_ANT)

# Bancos aceitos pela flag "Somente BMG/Help". Sao valores JA
# normalizados (strip + upper) — a comparacao passa por ``_norm``. As
# variantes com prefixo "BANCO " existem porque a base nao e uniforme;
# hoje "HELP" nao ocorre como BANCO em CLT/Consignado, mas o filtro fica
# preparado (ver progress/2026-08-06-plano-clt-consignado-*.md).
_BANCOS_BMG_HELP = ("BMG", "BANCO BMG", "HELP", "BANCO HELP")

# ── Configuracao dos produtos de quantidade ──────────
#
# Cada item vira uma aba de "Emissão e Seguros — Análise Regional".
# Chaves reconhecidas:
#
# - ``label``: rotulo da aba.
# - ``subtabs``: lista de colunas de efetivados. Cada uma declara
#   ``nome_col`` + os criterios de filtro lidos por ``_mask_subtab``
#   (``tipo_oper``, ``subtipo``, ``categoria``, ``subtipos``,
#   ``excluir_tipo_oper``).
# - ``col_dig_tipo`` / ``col_dig_subtipo``: criterio da coluna
#   "Análise" (digitados). Ausentes = aba sem coluna de análise.
# - ``total_label`` / ``total_help``: KPI de total no topo da aba.
# - ``toggle_banco``: flag opcional que restringe o total **e** as
#   tabelas por regiao/loja/consultor da aba a uma lista de bancos.

_PRODS_QTD = [
    {
        "label": "Emissão",
        "subtabs": [
            {
                "nome_col": "Cartão Benefício",
                "tipo_oper": ["CARTÃO BENEFICIO"],
            },
            {
                "nome_col": "Venda Pré-Adesão",
                "tipo_oper": ["Venda Pré-Adesão"],
            },
        ],
        "col_dig_tipo": [
            "CARTÃO BENEFICIO",
            "Venda Pré-Adesão",
        ],
        "total_label": "Propostas pagas",
        "total_help": (
            "Contratos pagos de Emissão (Cartão Benefício + "
            "Venda Pré-Adesão)."
        ),
    },
    {
        "label": "Super Conta",
        "subtabs": [
            {
                "nome_col": "Super Conta",
                "subtipo": "SUPER CONTA",
            },
        ],
        "col_dig_subtipo": "SUPER CONTA",
        "total_label": "Propostas pagas",
        "total_help": "Contratos pagos de Super Conta (subtipo SUPER CONTA).",
    },
    {
        "label": "BMG Med",
        "subtabs": [
            {
                "nome_col": "BMG Med",
                "tipo_oper": ["BMG MED"],
            },
        ],
        "col_dig_tipo": ["BMG MED"],
        "total_label": "Propostas pagas",
        "total_help": (
            "Contratos pagos de BMG Med (tipo operação BMG MED)."
        ),
    },
    {
        "label": "Vida Familiar",
        "subtabs": [
            {
                "nome_col": "Vida Familiar",
                "tipo_oper": ["Seguro"],
            },
        ],
        "col_dig_tipo": ["Seguro"],
        "total_label": "Propostas pagas",
        "total_help": (
            "Contratos pagos de Vida Familiar (tipo operação Seguro)."
        ),
    },
    {
        "label": "CLT",
        "subtabs": [
            {
                "nome_col": "CLT",
                "categoria": ["CONSIG_PRIV"],
                "excluir_tipo_oper": ["SEGURO PRESTAMISTA"],
            },
        ],
        "total_label": "Propostas pagas",
        "total_help": (
            "Contratos pagos de CLT (categoria CONSIG_PRIV). "
            "Seguro Prestamista fica de fora da contagem."
        ),
        "toggle_banco": {
            "label": "Somente BMG/Help",
            "key": "prod_qtd_clt_bmg_help",
            "bancos": _BANCOS_BMG_HELP,
            "help": (
                "Restringe o total acima e as tabelas desta aba aos "
                "bancos BMG e Help."
            ),
        },
    },
    {
        "label": "Consignado (Novo/Refin)",
        "subtabs": [
            {
                "nome_col": "Consignado",
                "categoria": ["CONSIG_BMG", "CONSIG_ITAU", "CONSIG_C6"],
                "subtipos": ["NOVO", "REFIN"],
            },
        ],
        "total_label": "Propostas pagas",
        "total_help": (
            "Consignado pago com subtipo Novo ou Refin. Portabilidade "
            "e Refin da Portabilidade ficam fora — mantêm "
            "categoria PORTABILIDADE."
        ),
        "toggle_banco": {
            "label": "Somente BMG/Help",
            "key": "prod_qtd_consig_bmg_help",
            "bancos": _BANCOS_BMG_HELP,
            "help": (
                "Restringe o total acima e as tabelas desta aba aos "
                "bancos BMG e Help."
            ),
        },
    },
]


def _html_tabela_evolucao(df: pd.DataFrame) -> str:
    """Gera tabela HTML estilizada de evolução de Média DU."""

    def _fmt(v: float) -> str:
        return formatar_moeda(v).replace("$", "&#36;")

    # Separar total (última linha) das linhas de dados
    df_dados = df.iloc[:-1].copy()
    df_total = df.iloc[[-1]].copy()

    # Ordenar do melhor para o pior
    df_dados = df_dados.sort_values("% Evolução", ascending=False)

    cabecalhos = ["Região", "Mês Anterior", "Mês Atual", "% Evolução"]
    header_cells = "".join(
        f'<th class="mg-rt-th">{c}</th>' for c in cabecalhos
    )

    rows_html = ""
    for pos, (_, row) in enumerate(
        list(df_dados.iterrows()) + list(df_total.iterrows())
    ):
        is_total = _ == df_total.index[0]
        tr_cls = "mg-rt-tr--total" if is_total else (
            "mg-rt-tr--odd" if pos % 2 else ""
        )
        perc = row["% Evolução"]
        if perc > 0.5:
            perc_cls = "mg-evol-pos"
            sinal = "+"
        elif perc < -0.5:
            perc_cls = "mg-evol-neg"
            sinal = ""
        else:
            perc_cls = "mg-evol-neu"
            sinal = ""
        cells = (
            f'<td class="mg-rt-td mg-rt-td--loja">'
            f'{row["Região"]}</td>'
            f'<td class="mg-rt-td mg-rt-td--num">'
            f'{_fmt(row["Mês Anterior"])}</td>'
            f'<td class="mg-rt-td mg-rt-td--num">'
            f'{_fmt(row["Mês Atual"])}</td>'
            f'<td class="mg-rt-td mg-rt-td--num {perc_cls}">'
            f'{sinal}{perc:.2f}%</td>'
        )
        rows_html += f'<tr class="mg-rt-tr {tr_cls}">{cells}</tr>'

    return (
        '<div class="mg-rt-wrap">'
        '<div class="mg-rt-header">Evolução Média DU por Região</div>'
        '<table class="mg-rt-table">'
        f'<thead><tr>{header_cells}</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        '</table></div>'
    )


def _html_tabela_regional(
    regiao: str,
    df: pd.DataFrame,
    cols_num: list,
) -> str:
    """Gera tabela HTML estilizada para análise regional."""
    header_cells = "".join(
        f'<th class="mg-rt-th">{c}</th>'
        for c in ["Loja"] + cols_num
    )
    rows_html = ""
    total_idx = len(df) - 1
    for i, row in df.iterrows():
        is_total = i == total_idx
        tr_cls = "mg-rt-tr--total" if is_total else (
            "mg-rt-tr--odd" if i % 2 else ""
        )
        loja_val = str(row["Loja"])
        cells = f'<td class="mg-rt-td mg-rt-td--loja">{loja_val}</td>'
        for c in cols_num:
            num = int(row[c]) if pd.notna(row[c]) else 0
            analise_cls = (
                " mg-rt-td--analise" if c == "Análise" else ""
            )
            cells += (
                f'<td class="mg-rt-td mg-rt-td--num'
                f'{analise_cls}">{num}</td>'
            )
        rows_html += (
            f'<tr class="mg-rt-tr {tr_cls}">{cells}</tr>'
        )
    return (
        f'<div class="mg-rt-wrap">'
        f'<div class="mg-rt-header">{regiao}</div>'
        f'<table class="mg-rt-table">'
        f'<thead><tr>{header_cells}</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table></div>'
    )


def _norm(serie: pd.Series) -> pd.Series:
    """Normaliza texto para comparacao: str + strip + upper."""
    return serie.astype(str).str.strip().str.upper()


def _mask_falsa(df: pd.DataFrame) -> pd.Series:
    """Mascara que nao seleciona nada, alinhada ao indice de ``df``."""
    return pd.Series(False, index=df.index)


def _mask_subtab(df: pd.DataFrame, sub: dict) -> pd.Series:
    """Monta a mascara de contagem de uma coluna de efetivados.

    Criterios suportados (combinados por AND; ausentes sao ignorados):

    - ``tipo_oper``: ``TIPO OPER.`` dentro de uma lista. Comparacao
      **crua**, sem normalizar — os rotulos de ``_PRODS_QTD`` batem
      1:1 com o dado ("CARTÃO BENEFICIO", "Venda Pré-Adesão", "Seguro").
    - ``subtipo``: ``SUBTIPO`` igual a um valor (normalizado).
    - ``categoria``: ``categoria_codigo`` dentro de uma lista.
    - ``subtipos``: ``SUBTIPO`` dentro de uma lista (normalizado).
    - ``excluir_tipo_oper``: ``TIPO OPER.`` **fora** de uma lista
      (normalizado).

    Criterio declarado cuja coluna nao existe no frame zera a contagem
    — o mesmo comportamento defensivo de antes desta extensao. Vale
    tambem para ``excluir_tipo_oper``: sem a coluna nao da para provar
    a exclusao, e um total silenciosamente inflado e pior que zero.
    """
    partes: list = []

    if "tipo_oper" in sub:
        partes.append(
            df["TIPO OPER."].isin(sub["tipo_oper"])
            if "TIPO OPER." in df.columns
            else _mask_falsa(df)
        )
    if "subtipo" in sub:
        partes.append(
            _norm(df["SUBTIPO"]) == str(sub["subtipo"]).upper()
            if "SUBTIPO" in df.columns
            else _mask_falsa(df)
        )
    if "categoria" in sub:
        partes.append(
            df["categoria_codigo"].isin(sub["categoria"])
            if "categoria_codigo" in df.columns
            else _mask_falsa(df)
        )
    if "subtipos" in sub:
        partes.append(
            _norm(df["SUBTIPO"]).isin(sub["subtipos"])
            if "SUBTIPO" in df.columns
            else _mask_falsa(df)
        )
    if "excluir_tipo_oper" in sub:
        partes.append(
            ~_norm(df["TIPO OPER."]).isin(sub["excluir_tipo_oper"])
            if "TIPO OPER." in df.columns
            else _mask_falsa(df)
        )

    if not partes:
        return _mask_falsa(df)

    mask = partes[0]
    for parte in partes[1:]:
        mask = mask & parte
    return mask


def _mask_banco(df: pd.DataFrame, bancos) -> pd.Series:
    """Mascara de ``BANCO`` normalizado dentro de ``bancos``."""
    if "BANCO" not in df.columns:
        return _mask_falsa(df)
    return _norm(df["BANCO"]).isin(list(bancos))


def _mask_supervisor(df: pd.DataFrame, supervisores_norm: set) -> pd.Series:
    """Mascara de linhas cujo ``CONSULTOR`` e um supervisor conhecido.

    ``supervisores_norm`` ja vem normalizado (strip + upper) por quem
    monta a lista a partir de ``df_sup`` — ver ``_render_produto_regional``.
    """
    if not supervisores_norm or "CONSULTOR" not in df.columns:
        return _mask_falsa(df)
    return _norm(df["CONSULTOR"]).isin(supervisores_norm)


def _render_total_produto(
    df: pd.DataFrame,
    cfg: dict,
    mask_supervisor: Optional[pd.Series] = None,
) -> Optional[pd.Series]:
    """KPI de total da aba + flag opcional de banco.

    Retorna a mascara de banco **ja aplicada a este total**, alinhada
    ao indice de ``df``, ou ``None`` quando nao ha filtro ativo (flag
    desligada ou aba sem ``toggle_banco``). O chamador repropaga essa
    mesma mascara para as tabelas por regiao/loja/consultor, para que
    a flag filtre a aba inteira — por isso o retorno so vale sobre o
    **mesmo frame** passado aqui.

    O total conta sobre o **mesmo frame** das tabelas (``df`` completo,
    COM producao de supervisor — ver ``_render_produto_regional``), e
    nao depende de REGIAO/LOJA preenchidos — linha sem regiao entra
    aqui e nao entra no ``groupby`` das tabelas.

    ``mask_supervisor``, quando informada, so serve para a legenda: se
    houver producao de supervisor dentro do total, mostra quanto —
    nunca subtrai nem exclui nada da conta principal.
    """
    mask = _mask_falsa(df)
    for sub in cfg["subtabs"]:
        mask = mask | _mask_subtab(df, sub)

    cfg_banco = cfg.get("toggle_banco")
    col_total, col_flag = st.columns([1, 2])

    somente_banco = False
    if cfg_banco:
        # Widget primeiro: o valor da flag entra na conta do total,
        # que so e desenhado depois (a coluna e um container, a ordem
        # de execucao nao muda o layout).
        with col_flag:
            somente_banco = st.toggle(
                cfg_banco["label"],
                key=cfg_banco["key"],
                help=cfg_banco.get("help"),
            )

    mask_banco: Optional[pd.Series] = None
    if somente_banco and cfg_banco:
        mask_banco = _mask_banco(df, cfg_banco["bancos"])
        mask = mask & mask_banco

    with col_total:
        st.metric(
            cfg["total_label"],
            formatar_numero(int(mask.sum())),
            help=cfg.get("total_help"),
        )
        if mask_supervisor is not None:
            qtd_sup = int((mask & mask_supervisor).sum())
            if qtd_sup > 0:
                st.caption(
                    f"Inclui {formatar_numero(qtd_sup)} de produção de "
                    "supervisor (fora de rankings e médias por consultor)."
                )

    return mask_banco


def _contar_por_regiao(
    df: pd.DataFrame,
    filtro: pd.Series,
    nome: str,
) -> pd.DataFrame:
    """Agrupa df filtrado por REGIAO/LOJA e retorna contagem."""
    if (
        filtro is None
        or not filtro.any()
        or "REGIAO" not in df.columns
        or "LOJA" not in df.columns
    ):
        return pd.DataFrame(columns=["REGIAO", "LOJA", nome])
    return (
        df[filtro]
        .groupby(["REGIAO", "LOJA"])
        .size()
        .reset_index(name=nome)
    )


def _contar_por_loja_consultor(
    df: pd.DataFrame,
    filtro: pd.Series,
    nome: str,
) -> pd.DataFrame:
    """Agrupa df filtrado por LOJA/CONSULTOR e retorna contagem."""
    if (
        filtro is None
        or not filtro.any()
        or "LOJA" not in df.columns
        or "CONSULTOR" not in df.columns
    ):
        return pd.DataFrame(columns=["LOJA", "CONSULTOR", nome])
    return (
        df[filtro]
        .groupby(["LOJA", "CONSULTOR"])
        .size()
        .reset_index(name=nome)
    )


def _html_tabela_loja(
    loja: str,
    df: pd.DataFrame,
    cols_num: list,
) -> str:
    """Gera tabela HTML estilizada para análise por loja (consultores)."""
    header_cells = "".join(
        f'<th class="mg-rt-th">{c}</th>'
        for c in ["Consultor"] + cols_num
    )
    rows_html = ""
    total_idx = len(df) - 1
    for i, row in df.iterrows():
        is_total = i == total_idx
        tr_cls = "mg-rt-tr--total" if is_total else (
            "mg-rt-tr--odd" if i % 2 else ""
        )
        consultor_val = str(row["Consultor"])
        cells = f'<td class="mg-rt-td mg-rt-td--loja">{consultor_val}</td>'
        for c in cols_num:
            num = int(row[c]) if pd.notna(row[c]) else 0
            analise_cls = (
                " mg-rt-td--analise" if c == "Análise" else ""
            )
            cells += (
                f'<td class="mg-rt-td mg-rt-td--num'
                f'{analise_cls}">{num}</td>'
            )
        rows_html += (
            f'<tr class="mg-rt-tr {tr_cls}">{cells}</tr>'
        )
    return (
        f'<div class="mg-rt-wrap">'
        f'<div class="mg-rt-header">{loja}</div>'
        f'<table class="mg-rt-table">'
        f'<thead><tr>{header_cells}</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table></div>'
    )


def _render_produto_regional(
    df: pd.DataFrame,
    df_analise: pd.DataFrame,
    cfg: dict,
    du_total: int,
    du_dec: int,
    df_sup: pd.DataFrame,
) -> None:
    """Renderiza a tabela regional de um produto de quantidade.

    Visão por Região (Admin/Gestor): tabelas por região, linhas = lojas
    Visão por Loja (Gerente Comercial): tabelas por loja, linhas = consultores
    """
    # Detectar perfil para decidir a visão
    perfil = _obter_perfil_efetivo()
    perfil_role = perfil["perfil"] if perfil else None
    visao_por_loja = perfil_role == "gerente_comercial"

    # ── Normalizar nomes de supervisores para comparação robusta ──
    # df_sup vem de carregar_supervisores(): a coluna de nomes é
    # SUPERVISOR (nao CONSULTOR).
    supervisores_raw: set = set()
    if (
        df_sup is not None
        and not df_sup.empty
        and "SUPERVISOR" in df_sup.columns
    ):
        supervisores_raw = set(df_sup["SUPERVISOR"].dropna().unique())

    supervisores_norm = {
        str(n).strip().upper() for n in supervisores_raw
    } if supervisores_raw else set()

    def _excluir_sup(frame: pd.DataFrame) -> pd.DataFrame:
        if supervisores_norm and "CONSULTOR" in frame.columns:
            mask_nao_sup = (
                frame["CONSULTOR"]
                .astype(str)
                .str.strip()
                .str.upper()
                .isin(supervisores_norm)
            )
            return frame[~mask_nao_sup]
        return frame

    df_p = _excluir_sup(df)
    df_a = _excluir_sup(
        df_analise if df_analise is not None else pd.DataFrame()
    )
    mask_sup_total = _mask_supervisor(df, supervisores_norm)

    # ── Total da aba (+ flag de banco, quando configurada) ───────
    # A flag do total repropaga para as tabelas abaixo: o mesmo
    # recorte de banco entra por AND no mask de cada subtab, valendo
    # para as duas visoes (regiao/loja e loja/consultor). Aba sem
    # ``total_label`` nem ``toggle_banco`` (as 4 antigas) fica com
    # ``mask_banco = None`` — nenhum filtro extra.
    #
    # O total e as tabelas contam sobre ``df`` **completo** (com
    # producao de supervisor) — decisao de 2026-08-10: supervisor
    # conta pra loja, igual ja vale pro resto do dashboard (ver
    # docs/agents/rls.md "Nota de design" e business-rules.md
    # "Exclusao de supervisores"). O que muda por perfil e SO como
    # essa producao aparece nas tabelas (ver mais abaixo): agregada e
    # anonima na visao por regiao/loja, destacada como linha propria
    # na visao por consultor — nunca misturada ao ranking/media de
    # consultor.
    mask_banco: Optional[pd.Series] = None
    if cfg.get("total_label"):
        mask_banco = _render_total_produto(
            df, cfg, mask_supervisor=mask_sup_total,
        )

    # ── Colunas de efetivados (pode ter mais de 1 para Emissão) ──
    dfs_ef = []
    for sub in cfg["subtabs"]:
        mask = _mask_subtab(df, sub)
        if mask_banco is not None:
            mask = mask & mask_banco
        if visao_por_loja:
            dfs_ef.append(
                _contar_por_loja_consultor(df, mask, sub["nome_col"])
            )
        else:
            dfs_ef.append(_contar_por_regiao(df, mask, sub["nome_col"]))

    # Merge conforme a visão
    if visao_por_loja:
        merge_cols = ["LOJA", "CONSULTOR"]
        df_merged = dfs_ef[0]
        for extra in dfs_ef[1:]:
            df_merged = pd.merge(
                df_merged, extra, on=merge_cols, how="outer"
            )
    else:
        merge_cols = ["REGIAO", "LOJA"]
        df_merged = dfs_ef[0]
        for extra in dfs_ef[1:]:
            df_merged = pd.merge(
                df_merged, extra, on=merge_cols, how="outer"
            )

    # ── Separar producao de supervisor (visao por consultor) ──────
    # So a visao por consultor precisa disso: e onde "consultor" vira
    # uma pessoa fisica na tabela, e supervisor nao pode entrar como
    # se fosse um consultor (nem no esqueleto de zerados, nem no
    # ranking por ``ef_base``). Sai ANTES do merge de digitados/
    # esqueleto — os dois so operam sobre consultores de verdade — e
    # volta depois, so na hora de renderizar, como linha propria por
    # loja (ver bloco de render mais abaixo).
    ef_cols_prod = [s["nome_col"] for s in cfg["subtabs"]]
    df_merged_sup = pd.DataFrame(columns=merge_cols)
    if visao_por_loja and supervisores_norm and not df_merged.empty:
        mask_sup_merged = _mask_supervisor(df_merged, supervisores_norm)
        if mask_sup_merged.any():
            df_merged_sup = df_merged[mask_sup_merged].copy()
            df_merged = df_merged[~mask_sup_merged].copy()

    # ── Digitados (em análise) ────────────────────────
    # Aba sem criterio de digitados (CLT, Consignado) nao ganha coluna
    # "Análise": o frame vazio so com as chaves de merge some no
    # ``col_exib``, que filtra por coluna existente.
    tem_analise = "col_dig_subtipo" in cfg or "col_dig_tipo" in cfg
    if not tem_analise:
        df_dig = pd.DataFrame(columns=merge_cols)
    elif not df_a.empty:
        if "col_dig_subtipo" in cfg:
            mask_dig = (
                df_a["SUBTIPO"].astype(str)
                .str.strip()
                .str.upper()
                == cfg["col_dig_subtipo"].upper()
                if "SUBTIPO" in df_a.columns
                else pd.Series(False, index=df_a.index)
            )
        else:
            tipos = cfg.get("col_dig_tipo", [])
            mask_dig = (
                df_a["TIPO OPER."].isin(tipos)
                if "TIPO OPER." in df_a.columns
                else pd.Series(False, index=df_a.index)
            )
        if visao_por_loja:
            df_dig = _contar_por_loja_consultor(df_a, mask_dig, "Análise")
        else:
            df_dig = _contar_por_regiao(df_a, mask_dig, "Análise")
    else:
        if visao_por_loja:
            df_dig = pd.DataFrame(columns=["LOJA", "CONSULTOR", "Análise"])
        else:
            df_dig = pd.DataFrame(columns=["REGIAO", "LOJA", "Análise"])

    # ── Incluir todos os consultores (mesmo zerados) na visão por loja ──
    # Supervisores não entram aqui: não recebem linha zerada quando não
    # produzem, e quando produzem aparecem à parte (bloco de supervisor
    # montado logo abaixo, renderizado como linha própria por loja).
    if visao_por_loja:
        if "LOJA" in df_p.columns and "CONSULTOR" in df_p.columns:
            esqueleto = (
                df_p[["LOJA", "CONSULTOR"]]
                .drop_duplicates()
                .sort_values(["LOJA", "CONSULTOR"])
            )
            # Garantir que nenhum supervisor entre no esqueleto
            if supervisores_norm:
                esq_norm = (
                    esqueleto["CONSULTOR"]
                    .astype(str)
                    .str.strip()
                    .str.upper()
                )
                esqueleto = esqueleto[~esq_norm.isin(supervisores_norm)]
            df_merged = pd.merge(
                esqueleto, df_merged, on=merge_cols, how="left"
            )
            if not df_dig.empty:
                df_dig = pd.merge(
                    esqueleto, df_dig, on=merge_cols, how="left"
                )

    df_final = pd.merge(
        df_dig, df_merged, on=merge_cols, how="outer"
    ).fillna(0)

    # ── Colunas numéricas como int ────────────────────
    cols_num = [
        c for c in df_final.columns if c not in ("REGIAO", "LOJA", "CONSULTOR")
    ]
    for c in cols_num:
        df_final[c] = df_final[c].astype(int)

    # ── Coluna Total (se houver mais de 1 col de efetivados) ──
    ef_cols = [s["nome_col"] for s in cfg["subtabs"]]
    if len(ef_cols) > 1:
        df_final["Total"] = df_final[ef_cols].sum(axis=1)
        ef_cols.append("Total")

    # ── Projeção ──────────────────────────────────────
    ef_base = ef_cols[0] if len(ef_cols) == 1 else "Total"
    if du_dec > 0:
        df_final["Proj"] = (
            df_final[ef_base] / du_dec * du_total
        ).round(0).astype(int)
    else:
        df_final["Proj"] = 0

    if df_final.empty:
        st.info("Sem dados para este produto no período.")
        return

    col_exib = ["Análise"] + ef_cols + ["Proj"]
    col_exib = [c for c in col_exib if c in df_final.columns]

    # ── Bloco de producao de supervisor (visao por consultor) ─────
    # Mesmas colunas numericas de ``df_final`` (fillna 0 + int, Total
    # se houver mais de uma subtab, Proj pela mesma formula), MENOS
    # "Análise": digitados de supervisor nao sao computados aqui (o
    # frame ``df_a`` ja exclui supervisor antes disso, sem mudar) —
    # a coluna existe zerada so pra caber no mesmo ``col_exib`` da
    # tabela. Nao entra no esqueleto nem no ranking por ``ef_base``;
    # o render mais abaixo acrescenta como linha propria, por ultimo,
    # dentro da loja onde houve producao.
    df_final_sup = df_merged_sup.copy()
    if not df_final_sup.empty:
        for c in ef_cols_prod:
            df_final_sup[c] = (
                df_final_sup[c].fillna(0).astype(int)
                if c in df_final_sup.columns
                else 0
            )
        if len(ef_cols_prod) > 1:
            df_final_sup["Total"] = df_final_sup[ef_cols_prod].sum(axis=1)
        df_final_sup["Análise"] = 0
        if du_dec > 0:
            df_final_sup["Proj"] = (
                df_final_sup[ef_base] / du_dec * du_total
            ).round(0).astype(int)
        else:
            df_final_sup["Proj"] = 0

    # ── Lojas com producao de supervisor (visao por regiao) ───────
    # Na visao Admin/Gestor nao ha linha por pessoa — a producao do
    # supervisor entra somada e anonima no total da loja (mesma regra
    # "supervisor conta pra loja"). Aqui so identificamos QUAIS lojas
    # tem esse componente, pra marcar o rotulo na tabela.
    lojas_com_supervisor: set = set()
    if not visao_por_loja and mask_sup_total.any() and "LOJA" in df.columns:
        mask_prod_sup = _mask_falsa(df)
        for sub in cfg["subtabs"]:
            m = _mask_subtab(df, sub)
            if mask_banco is not None:
                m = m & mask_banco
            mask_prod_sup = mask_prod_sup | (m & mask_sup_total)
        if mask_prod_sup.any():
            lojas_com_supervisor = set(
                df.loc[mask_prod_sup, "LOJA"].unique()
            )

    # ── Renderização conforme a visão ────────────────
    if visao_por_loja:
        # Visão Gerente Comercial: tabelas por LOJA, linhas = CONSULTORES
        if "LOJA" not in df_final.columns:
            st.info("Sem dados de loja disponíveis.")
            return

        df_final = df_final.sort_values(["LOJA", "CONSULTOR"])
        lojas = sorted(df_final["LOJA"].dropna().unique())
        if not lojas:
            st.info("Sem dados de lojas disponíveis.")
            return

        # Layout 2 colunas de lojas
        metade = (len(lojas) + 1) // 2
        grp_esq, grp_dir = lojas[:metade], lojas[metade:]

        col_esq, col_dir = st.columns(2)
        for col_st, grupo in [(col_esq, grp_esq), (col_dir, grp_dir)]:
            with col_st:
                for loja in grupo:
                    df_loja = (
                        df_final[df_final["LOJA"] == loja]
                        [["CONSULTOR"] + col_exib]
                        .copy()
                        .rename(columns={"CONSULTOR": "Consultor"})
                        .sort_values(ef_base, ascending=False)
                        .reset_index(drop=True)
                    )
                    # Producao de supervisor desta loja: linha propria,
                    # sempre depois do ranking de consultores (nunca
                    # entra no sort acima) e antes do Total — visivel,
                    # mas fora do ranking/media por consultor.
                    if not df_final_sup.empty:
                        bloco_sup = df_final_sup[
                            df_final_sup["LOJA"] == loja
                        ][["CONSULTOR"] + col_exib].copy()
                        if not bloco_sup.empty:
                            bloco_sup = bloco_sup.rename(
                                columns={"CONSULTOR": "Consultor"}
                            )
                            bloco_sup["Consultor"] = (
                                bloco_sup["Consultor"] + " (Supervisor)"
                            )
                            df_loja = pd.concat(
                                [df_loja, bloco_sup], ignore_index=True,
                            )
                    total_row = {"Consultor": "Total"}
                    for c in col_exib:
                        total_row[c] = int(df_loja[c].sum())
                    df_loja = pd.concat(
                        [df_loja, pd.DataFrame([total_row])],
                        ignore_index=True,
                    )
                    st.markdown(
                        _html_tabela_loja(loja, df_loja, col_exib),
                        unsafe_allow_html=True,
                    )
    else:
        # Visão Admin/Gestor: tabelas por REGIÃO, linhas = LOJAS
        if "REGIAO" not in df_final.columns:
            st.info("Sem dados regionais disponíveis.")
            return

        df_final = df_final.sort_values(["REGIAO", "LOJA"])
        regioes = sorted(df_final["REGIAO"].dropna().unique())
        if not regioes:
            st.info("Sem dados regionais disponíveis.")
            return

        col_exib = ["Análise"] + ef_cols + ["Proj"]
        col_exib = [c for c in col_exib if c in df_final.columns]

        # Layout 2 colunas de regiões
        metade = (len(regioes) + 1) // 2
        grp_esq, grp_dir = regioes[:metade], regioes[metade:]

        col_esq, col_dir = st.columns(2)
        for col_st, grupo in [(col_esq, grp_esq), (col_dir, grp_dir)]:
            with col_st:
                for reg in grupo:
                    df_reg = (
                        df_final[df_final["REGIAO"] == reg]
                        [["LOJA"] + col_exib]
                        .copy()
                        .rename(columns={"LOJA": "Loja"})
                        .sort_values(ef_base, ascending=False)
                        .reset_index(drop=True)
                    )
                    if lojas_com_supervisor:
                        df_reg["Loja"] = df_reg["Loja"].apply(
                            lambda v: (
                                f"{v} *"
                                if v in lojas_com_supervisor
                                else v
                            )
                        )
                    total_row = {"Loja": "Total"}
                    for c in col_exib:
                        total_row[c] = int(df_reg[c].sum())
                    df_reg = pd.concat(
                        [df_reg, pd.DataFrame([total_row])],
                        ignore_index=True,
                    )
                    st.markdown(
                        _html_tabela_regional(reg, df_reg, col_exib),
                        unsafe_allow_html=True,
                    )

        if lojas_com_supervisor:
            st.caption(
                "* Loja com produção de supervisor incluída no total "
                "(fora de rankings e médias por consultor)."
            )


def _chave_mes_comparativo(mes: int, ano: int) -> tuple:
    """Chave de invalidacao do cache de um mes de comparacao.

    **Fronteira de seguranca entre perfis**, pelo mesmo motivo de
    ``_chave_kpis`` (kpis/gerais.py): o frame comparativo fica em
    ``session_state`` e nao e recarregado enquanto esta chave nao muda,
    entao todo componente que altera o RECORTE dos dados precisa estar
    aqui. Sao os mesmos seis, na mesma ordem: periodo (``mes``/``ano``),
    ``perfil`` efetivo (ja considera "Visualizar como"), ``escopo`` do
    perfil efetivo, filtro granular de lojas (ordenado, para que a mesma
    selecao em ordem diferente nao invalide o cache a toa) e filtro
    granular de consultor.

    Alterar esta funcao muda quem ve o que — nao e ajuste cosmetico.
    """
    perfil = _obter_perfil_efetivo()
    return (
        mes,
        ano,
        perfil["perfil"] if perfil else None,
        tuple(perfil.get("escopo", []) if perfil else []),
        tuple(sorted(st.session_state.get("ui_filtro_lojas") or [])),
        st.session_state.get("ui_filtro_consultor") or "",
    )


def _carregar_mes_comparativo(
    mes: int,
    ano: int,
    *,
    prefixo: str,
    rotulo: str,
) -> pd.DataFrame:
    """Carrega (ou recupera do cache) um mes de comparacao da aba.

    Lazy de proposito: a chamada mora dentro do render desta aba, entao
    quem fica em outra aba nao paga a query no Supabase nem a
    consolidacao. O resultado pos-RLS+filtros e memoizado em
    ``session_state`` sob ``<prefixo>_cache`` / ``<prefixo>_chave``, o
    que evita repetir a cadeia inteira a cada rerun da aba (hover,
    clique em outro widget).

    O frame recebe o **mesmo** escopo de perfil e os mesmos filtros de UI
    do mes atual, para que a curva comparativa no grafico acumulado
    represente a mesma granularidade (regiao / loja / consultor) que
    esta sendo visualizada.

    Tambem cacheia, em paralelo, um snapshot **pre-RLS** sob
    ``<prefixo>_cache_full`` — mesmo papel do ``df_full`` do mes atual
    (ver ``app.py``): base para comparativos agregados por regiao que
    nao devem ficar reduzidos ao escopo do perfil (ex.: "Mes Anterior"
    do quadro de Evolucao Media DU por Regiao, consumido via
    ``_mes_comparativo_full``). Nao paga query extra, so guarda a
    referencia anterior ao ``aplicar_rls``.

    Falha de carga nao derruba a aba: e logada, virada em ``st.warning``
    visivel e o comparativo cai para um frame vazio (o grafico apenas
    perde a curva).

    Args:
        mes / ano: periodo a carregar.
        prefixo: raiz das chaves de ``session_state``
            (``_df_ant`` para o mes anterior, ``_df_ano_ant`` para o
            mesmo mes do ano anterior).
        rotulo: nome do comparativo nas mensagens de log e de aviso.
    """
    chave = _chave_mes_comparativo(mes, ano)
    if st.session_state.get(f"{prefixo}_chave") != chave:
        try:
            frame, _, _ = consolidar_dados(mes, ano)
            frame = aplicar_nomes_display_produto(frame)
            frame_full = frame
            frame = aplicar_rls(frame)
            if (
                st.session_state.get("ui_filtro_lojas")
                or st.session_state.get("ui_filtro_consultor")
            ):
                frame = aplicar_filtros_ui(frame)
        except Exception as exc:
            logger.exception(
                "Falha ao carregar %s (%s/%s)", rotulo, mes, ano,
            )
            st.warning(
                f"Não foi possível carregar o {rotulo} "
                f"({mes:02d}/{ano}): {exc}"
            )
            frame = pd.DataFrame()
            frame_full = pd.DataFrame()
        st.session_state[f"{prefixo}_cache"] = frame
        st.session_state[f"{prefixo}_cache_full"] = frame_full
        st.session_state[f"{prefixo}_chave"] = chave
    return st.session_state[f"{prefixo}_cache"]


def _mes_comparativo_full(prefixo: str) -> pd.DataFrame:
    """Snapshot pre-RLS do mes de comparacao cacheado por
    ``_carregar_mes_comparativo`` (chamar so depois dele, mesmo
    ``prefixo``). Deste frame so devem sair agregados por regiao para
    a tela — nunca linha crua (mesma regra do ``df_full``)."""
    return st.session_state.get(f"{prefixo}_cache_full", pd.DataFrame())


def limpar_cache_comparativos() -> None:
    """Invalida o cache dos meses de comparacao desta aba.

    As quatro chaves (``<prefixo>_cache`` / ``<prefixo>_chave`` dos dois
    prefixos) sao privadas DESTE modulo — quem dispara um refresh global
    (o botao "Atualizar Dados", na sidebar) nao deve conhece-las pelo
    nome. Enquanto conhecia, esqueceu: o par ``_df_ano_ant_*`` nasceu na
    extracao do lazy-load e so entrou no refresh depois, por bugfix
    (commit ``40a0999``). Derivando as chaves de
    ``_PREFIXOS_COMPARATIVO``, um comparativo novo passa a ser limpo de
    graca.

    Nao recarrega nada: a proxima renderizacao da aba encontra a chave
    ausente e refaz a cadeia (query + RLS + filtros de UI).
    """
    for prefixo in _PREFIXOS_COMPARATIVO:
        st.session_state.pop(f"{prefixo}_cache", None)
        st.session_state.pop(f"{prefixo}_cache_full", None)
        st.session_state.pop(f"{prefixo}_chave", None)


def render_tab_produtos(
    df: pd.DataFrame,
    df_metas_produto: pd.DataFrame,
    categorias: pd.DataFrame,
    ano: int,
    mes: int,
    dia_atual: int,
    df_sup: pd.DataFrame,
    df_analise: Optional[pd.DataFrame] = None,
    du_total: int = 0,
    du_decorridos: int = 0,
    df_full: Optional[pd.DataFrame] = None,
    df_metas_produto_full: Optional[pd.DataFrame] = None,
) -> None:
    """Renderiza aba de Produtos.

    Os dois meses de comparacao (anterior e YoY) sao carregados **aqui**,
    nao em ``app.py``: so esta aba os consome, e o custo (query +
    consolidacao) nao deve ser pago por quem esta em outra aba. Ver
    ``_carregar_mes_comparativo``.
    """
    # ── Meses de comparacao (lazy, so nesta aba) ─────
    # Antes do primeiro render: um aviso de falha de carga deve aparecer
    # no topo da aba, como aparecia quando o bloco vivia em `main()`.
    mes_ant = mes - 1 if mes > 1 else 12
    ano_ant = ano if mes > 1 else ano - 1
    df_ant = _carregar_mes_comparativo(
        mes_ant,
        ano_ant,
        prefixo=_PREFIXO_MES_ANT,
        rotulo="mês anterior",
    )
    du_dec_ant = calcular_dias_uteis(ano_ant, mes_ant, 1)[0]
    df_ano_ant = _carregar_mes_comparativo(
        mes,
        ano - 1,
        prefixo=_PREFIXO_ANO_ANT,
        rotulo="comparativo YoY",
    )

    sac.divider(
        label="Analise de Produtos",
        icon="tags-fill",
        align="left",
        color="blue",
    )

    df_prod = calcular_kpis_por_produto(
        df,
        df_metas_produto,
        categorias,
        ano,
        mes,
        dia_atual,
        df_sup,
    )

    # ── Heatmap regional + tabela de evolução ───────
    perfil = _obter_perfil_efetivo()
    perfil_role = perfil["perfil"] if perfil else None
    pode_heatmap = perfil_role in (
        "admin", "gestor", "gerente_comercial",
    )

    if (
        pode_heatmap
        and df_full is not None
        and not df_full.empty
        and df_metas_produto_full is not None
        and categorias is not None
        and not df_metas_produto_full.empty
    ):
        sac.divider(
            label="Comparativo Regional",
            icon="grid-3x3-gap-fill",
            align="left",
            color="gray",
        )
        df_hm = df_full[
            ~df_full.get("REGIAO", pd.Series(dtype=str))
            .str.upper()
            .isin(_REGIOES_EXCLUIR_HM)
        ] if "REGIAO" in df_full.columns else df_full

        df_ranking, df_ating = calcular_heatmap_regiao_produto(
            df_hm, df_metas_produto_full, categorias,
        )

        # "Mes Anterior" tambem pre-RLS: espelha o df_full do mes
        # atual acima. Com df_ant (pos-RLS) aqui, todo perfil
        # gerente_comercial via regiao alheia zerada ("Mes Anterior"
        # = 0 / 0% de evolucao) — o comparativo entre regionais so
        # faz sentido com as duas pontas na mesma base organizacional.
        df_evol = calcular_evolucao_media_du(
            df_full,
            max(du_decorridos, 1),
            _mes_comparativo_full(_PREFIXO_MES_ANT),
            max(du_dec_ant, 1),
            regioes_excluir=_REGIOES_EXCLUIR_HM,
        )

        # Layout: banner acima, heatmap + tabela evolução lado a lado
        if not df_ranking.empty:
            chart_card_open(
                "Ranking Região × Produto",
                icon="🗺️",
                subtitle="Posição de cada região por produto"
                " (1º = melhor atingimento)",
            )

            col_hm, col_ev = st.columns([3, 2])

            with col_hm:
                fig_hm = criar_heatmap_regiao_produto(
                    df_ranking, df_ating,
                )
                st.plotly_chart(fig_hm, width="stretch")

            with col_ev:
                if not df_evol.empty:
                    st.markdown(
                        _html_tabela_evolucao(df_evol),
                        unsafe_allow_html=True,
                    )

            chart_card_close()

    _fer_atual = carregar_feriados(mes, ano)
    _fer_ant = carregar_feriados(mes_ant, ano_ant)
    _fer_ano_ant = carregar_feriados(mes, ano - 1)
    fig = criar_grafico_produtos(
        df_prod,
        df_atual=df,
        df_ant=df_ant,
        feriados_atual=_fer_atual,
        feriados_ant=_fer_ant,
        df_ano_ant=df_ano_ant,
        feriados_ano_ant=_fer_ano_ant,
    )
    chart_card_open(
        "Analise Completa de Produtos",
        icon="📦",
        subtitle="Realizado vs Meta, Projecao vs Meta e Acumulado Mensal",
    )
    st.plotly_chart(fig, width="stretch")
    chart_card_close()

    # ── Análise Regional: Emissão e Seguros ─────────
    # Consultor já visualiza seus aceleradores nos KPI cards e no painel
    # de Prioridades — a visão regional não agrega para quem tem escopo único.
    if df_analise is not None and perfil_role != "consultor":
        sac.divider(
            label="Emissão e Seguros — Análise Regional",
            icon="geo-alt-fill",
            align="left",
            color="gray",
        )

        tab_labels = [p["label"] for p in _PRODS_QTD]
        tabs = st.tabs(tab_labels)
        for tab, cfg in zip(tabs, _PRODS_QTD):
            with tab:
                _render_produto_regional(
                    df,
                    df_analise,
                    cfg,
                    du_total,
                    du_decorridos,
                    df_sup,
                )
