"""
Componente de tabelas do dashboard com suporte a AG Grid.

Utiliza st-aggrid para tabelas interativas com ordenação,
filtros e formatação automática. Fallback para st.dataframe
nativo quando AG Grid não está disponível.
"""
import math
import re
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

try:
    from st_aggrid import AgGrid, GridOptionsBuilder, JsCode
    _TEM_AGGRID = True
except ImportError:
    _TEM_AGGRID = False


# Altura mínima e máxima para tabelas (em pixels)
_ALTURA_MINIMA = 200
_ALTURA_MAXIMA = 600
_ALTURA_POR_LINHA = 35
_ALTURA_HEADER = 50


def _calcular_altura(num_linhas: int) -> int:
    """Calcula altura dinâmica baseada no número de linhas."""
    altura = _ALTURA_HEADER + (num_linhas * _ALTURA_POR_LINHA)
    return max(_ALTURA_MINIMA, min(altura, _ALTURA_MAXIMA))


# ── Detecção automática de tipos de coluna ──────────

_MOEDA_KEYWORDS = [
    "Valor", "Meta", "Ticket", "Projeção", "Média DU",
    "Meta Diária", "Valor Médio", "Mediano", "Mínimo",
    "Máximo",
]
_PERC_KEYWORDS = ["% Ating", "% Proj", "Atingimento %"]
# Meta Prata/Ouro são metas em pontos, não valores monetários
_PONTOS_KEYWORDS = [
    "Pontos", "pontos", "Meta Prata", "Meta Ouro",
]
_NUMERO_KEYWORDS = [
    "Qtd", "Posição", "Nº Lojas",
    "Nº Consultores", "Num Consultores", "TOTAL",
]


def _classificar_coluna(
    col: str,
    colunas_moeda: Optional[List[str]],
    colunas_percentual: Optional[List[str]],
    colunas_numero: Optional[List[str]],
    colunas_pontos: Optional[List[str]] = None,
) -> Optional[str]:
    """Retorna o tipo da coluna: 'moeda', 'perc', 'pontos',
    'numero' ou None."""
    if colunas_moeda and col in colunas_moeda:
        return "moeda"
    if colunas_percentual and col in colunas_percentual:
        return "perc"
    if colunas_pontos and col in colunas_pontos:
        return "pontos"
    if colunas_numero and col in colunas_numero:
        return "numero"
    if any(kw in col for kw in _PERC_KEYWORDS):
        return "perc"
    # Verificar pontos antes de número e moeda para que
    # "Total Pontos" ("TOTAL") e "Meta Prata"/"Meta Ouro"
    # ("Meta") sejam classificados como pontos
    if any(kw in col for kw in _PONTOS_KEYWORDS):
        return "pontos"
    if any(kw in col for kw in _NUMERO_KEYWORDS):
        return "numero"
    if any(kw in col for kw in _MOEDA_KEYWORDS):
        return "moeda"
    return None


# ── AG Grid ─────────────────────────────────────────

# Formatadores JS para AG Grid
_JS_MOEDA = JsCode("""
function(params) {
    if (params.value == null) return '';
    return 'R$ ' + params.value.toLocaleString('pt-BR', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}
""") if _TEM_AGGRID else None

_JS_PERC = JsCode("""
function(params) {
    if (params.value == null) return '';
    return params.value.toFixed(1) + '%';
}
""") if _TEM_AGGRID else None

_JS_NUMERO = JsCode("""
function(params) {
    if (params.value == null) return '';
    return Math.round(params.value).toLocaleString('pt-BR');
}
""") if _TEM_AGGRID else None

_JS_PONTOS = JsCode("""
function(params) {
    if (params.value == null) return '';
    return params.value.toLocaleString('pt-BR', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}
""") if _TEM_AGGRID else None

# Estilo condicional para percentuais de atingimento
_JS_CELL_STYLE_ATING = JsCode("""
function(params) {
    if (params.value == null) return {};
    if (params.value >= 100) {
        return {
            'color': 'var(--mg-success, #0f8a4f)',
            'fontWeight': '700'
        };
    } else if (params.value >= 80) {
        return {
            'color': 'var(--mg-warning, #c77c14)',
            'fontWeight': '600'
        };
    } else {
        return {
            'color': 'var(--mg-danger, #c0392b)',
            'fontWeight': '600'
        };
    }
}
""") if _TEM_AGGRID else None


def _build_aggrid_options(
    df: pd.DataFrame,
    colunas_moeda: Optional[List[str]],
    colunas_percentual: Optional[List[str]],
    colunas_numero: Optional[List[str]],
    altura: int,
    colunas_pontos: Optional[List[str]] = None,
):
    """Constrói opções do AG Grid com formatação automática."""
    gb = GridOptionsBuilder.from_dataframe(df)

    gb.configure_default_column(
        resizable=True,
        sortable=True,
        filter=True,
        wrapHeaderText=True,
        autoHeaderHeight=True,
        minWidth=100,
    )

    num_cols = len(df.columns)

    for col in df.columns:
        tipo = _classificar_coluna(
            col, colunas_moeda, colunas_percentual, colunas_numero,
            colunas_pontos,
        )

        # Largura mínima por tipo de dado
        if tipo == "moeda":
            gb.configure_column(
                col,
                type=["numericColumn"],
                valueFormatter=_JS_MOEDA,
                minWidth=150,
            )
        elif tipo == "perc":
            is_ating = any(
                kw in col for kw in ["Ating", "Proj"]
            )
            gb.configure_column(
                col,
                type=["numericColumn"],
                valueFormatter=_JS_PERC,
                cellStyle=(
                    _JS_CELL_STYLE_ATING if is_ating else None
                ),
                minWidth=120,
            )
        elif tipo == "pontos":
            gb.configure_column(
                col,
                type=["numericColumn"],
                valueFormatter=_JS_PONTOS,
                minWidth=120,
            )
        elif tipo == "numero":
            gb.configure_column(
                col,
                type=["numericColumn"],
                valueFormatter=_JS_NUMERO,
                minWidth=120,
            )
        else:
            # Colunas de texto: largura proporcional ao
            # comprimento máximo do conteúdo
            max_len = (
                df[col].astype(str).str.len().max()
                if not df[col].empty else 10
            )
            header_len = len(str(col))
            char_width = max(max_len, header_len)
            min_w = max(100, min(char_width * 10, 300))
            gb.configure_column(col, minWidth=min_w)

    # Se poucas colunas, permitir que ocupem todo o espaço
    _should_fit = num_cols <= 5

    gb.configure_grid_options(
        domLayout="normal",
        headerHeight=42,
        rowHeight=36,
        suppressMenuHide=True,
        enableRangeSelection=False,
    )

    gb.configure_selection(selection_mode="disabled")

    options = gb.build()
    options["_should_fit"] = _should_fit
    return options


def _exibir_aggrid(
    df: pd.DataFrame,
    altura: int,
    colunas_moeda: Optional[List[str]],
    colunas_percentual: Optional[List[str]],
    colunas_numero: Optional[List[str]],
    colunas_pontos: Optional[List[str]] = None,
) -> None:
    """Exibe tabela usando AG Grid."""
    grid_options = _build_aggrid_options(
        df, colunas_moeda, colunas_percentual, colunas_numero, altura,
        colunas_pontos,
    )

    should_fit = grid_options.pop("_should_fit", False)

    AgGrid(
        df,
        gridOptions=grid_options,
        height=altura,
        theme="streamlit",
        fit_columns_on_grid_load=should_fit,
        allow_unsafe_jscode=True,
        custom_css={
            "#gridToolBar": {"display": "none"},
        },
    )


# ── st.dataframe (fallback) ─────────────────────────

def _formatar_moeda_br(valor):
    """Formata valor como moeda brasileira (R$ X.XXX,XX)."""
    if pd.isna(valor):
        return ""
    return (
        f"R$ {valor:,.2f}"
        .replace(",", "X").replace(".", ",").replace("X", ".")
    )


def _formatar_numero_br(valor):
    """Formata número inteiro no padrão brasileiro (X.XXX)."""
    if pd.isna(valor):
        return ""
    return f"{valor:,.0f}".replace(",", ".")


def _formatar_pontos_br(valor):
    """Formata pontos no padrão contábil brasileiro (X.XXX,XX)."""
    if pd.isna(valor):
        return ""
    return (
        f"{valor:,.2f}"
        .replace(",", "X").replace(".", ",").replace("X", ".")
    )


# Datas que chegam como texto ISO (yyyy-mm-dd, com hora/UTC opcional)
# nao tem dtype datetime64 e escapariam da formatacao. Detectamos por
# VALOR (nao por nome de coluna) para nao confundir com codigos.
_ISO_DATA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}|$)")


def _coluna_texto_e_data(serie: pd.Series) -> bool:
    """True se uma coluna textual contiver apenas datas ISO validas.

    Nao restringe por dtype (strings podem vir como ``object`` ou ``str``
    conforme a versao do pandas); o ``isinstance(v, str)`` abaixo filtra
    colunas numericas/booleanas. Dois filtros evitam falso-positivo:
    (1) todos os valores casam o padrao textual ISO; (2) todos convertem
    para data valida (descarta codigos como '1234-56-78', que casam o
    padrao mas nao sao data).
    """
    naonulos = serie.dropna()
    if naonulos.empty:
        return False
    amostra = naonulos.head(200)
    if not all(
        isinstance(v, str) and _ISO_DATA_RE.match(v) is not None
        for v in amostra
    ):
        return False
    convertido = pd.to_datetime(amostra, errors="coerce")
    return bool(convertido.notna().all())


def _formatar_percentual_br(valor):
    """Formata percentual no padrão brasileiro (X,X%)."""
    if pd.isna(valor):
        return ""
    return f"{valor:.1f}%".replace(".", ",")


def _preparar_exibicao_br(
    df: pd.DataFrame,
    colunas_moeda: Optional[List[str]],
    colunas_percentual: Optional[List[str]],
    colunas_numero: Optional[List[str]],
    colunas_pontos: Optional[List[str]] = None,
):
    """
    Prepara o DataFrame para exibição no padrão brasileiro sem
    perder os tipos originais (a ordenação do st.dataframe usa o
    valor bruto; a formatação fica no Styler/column_config).

    Retorna ``(df_conv, formatos, config_datas)`` onde ``df_conv``
    tem colunas de data ISO-texto convertidas para datetime,
    ``formatos`` é o mapa coluna→formatter para ``Styler.format`` e
    ``config_datas`` é o column_config das colunas de data
    (dd/mm/aaaa).
    """
    df_conv = df.copy()
    formatos: Dict[str, object] = {}
    config_datas: Dict[str, object] = {}
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            config_datas[col] = st.column_config.DatetimeColumn(
                format="DD/MM/YYYY"
            )
            continue
        if _coluna_texto_e_data(df[col]):
            df_conv[col] = pd.to_datetime(df[col], errors="coerce")
            config_datas[col] = st.column_config.DatetimeColumn(
                format="DD/MM/YYYY"
            )
            continue
        tipo = _classificar_coluna(
            col, colunas_moeda, colunas_percentual, colunas_numero,
            colunas_pontos,
        )
        if tipo == "moeda":
            formatos[col] = _formatar_moeda_br
        elif tipo == "perc":
            formatos[col] = _formatar_percentual_br
        elif tipo == "pontos":
            formatos[col] = _formatar_pontos_br
        elif tipo == "numero":
            formatos[col] = _formatar_numero_br
    return df_conv, formatos, config_datas


_HIGHLIGHT_BG = "#fffbeb"   # amber-50 — linha destacada
_HIGHLIGHT_STYLE = f"background-color: {_HIGHLIGHT_BG}; font-weight: 600;"


def _exibir_dataframe(
    df: pd.DataFrame,
    altura: int,
    colunas_moeda: Optional[List[str]],
    colunas_percentual: Optional[List[str]],
    colunas_numero: Optional[List[str]],
    column_config: Optional[Dict],
    highlight_mask: Optional["pd.Series"] = None,
    colunas_pontos: Optional[List[str]] = None,
) -> None:
    """Exibe tabela usando st.dataframe nativo (fallback)."""
    df_conv, formatos, config_datas = _preparar_exibicao_br(
        df, colunas_moeda, colunas_percentual, colunas_numero,
        colunas_pontos,
    )

    data = df_conv
    if formatos:
        data = data.style.format(formatos)

    if highlight_mask is not None and highlight_mask.any():
        mask = highlight_mask.reindex(df_conv.index, fill_value=False)

        def _hl(row: "pd.Series") -> list:
            if mask.get(row.name, False):
                return [_HIGHLIGHT_STYLE] * len(row)
            return [""] * len(row)

        if not isinstance(data, pd.io.formats.style.Styler):
            data = data.style
        data = data.apply(_hl, axis=1)

    # column_config explícito do chamador tem precedência sobre o
    # config automático de datas.
    config_final = {**config_datas, **(column_config or {})} or None

    st.dataframe(
        data,
        width="stretch",
        hide_index=True,
        height=altura,
        column_config=config_final,
    )


# ── API Pública ──────────────────────────────────────

def exibir_tabela(
    df: pd.DataFrame,
    altura: Optional[int] = None,
    colunas_moeda: Optional[List[str]] = None,
    colunas_percentual: Optional[List[str]] = None,
    colunas_numero: Optional[List[str]] = None,
    column_config: Optional[Dict] = None,
    usar_aggrid: Optional[bool] = None,
    highlight_mask: Optional["pd.Series"] = None,
    paginacao: Optional[int] = None,
    key: Optional[str] = None,
    colunas_pontos: Optional[List[str]] = None,
) -> None:
    """
    Exibe tabela com formatação automática.

    Usa AG Grid por padrão quando disponível; fallback
    para st.dataframe nativo caso contrário.

    Args:
        df: DataFrame a ser exibido.
        altura: Altura fixa em pixels. Se None, calcula
            dinamicamente.
        colunas_moeda: Lista de colunas para formatar como
            moeda pt-BR (R$ X.XXX,XX).
        colunas_percentual: Lista de colunas para formatar
            como percentual.
        colunas_numero: Lista de colunas para formatar como
            número inteiro (X.XXX).
        colunas_pontos: Lista de colunas de pontos, formato
            contábil pt-BR (X.XXX,XX).
        column_config: Configuração manual de colunas
            (apenas st.dataframe).
        usar_aggrid: Forçar AG Grid (True), st.dataframe
            (False), ou automático (None).
        highlight_mask: Série booleana (mesmo índice do df)
            indicando quais linhas destacar.
        paginacao: Linhas por página. Se definido e o df
            exceder esse tamanho, exibe st.pagination abaixo
            da tabela (requer ``key``).
        key: Chave única — obrigatória quando ``paginacao``
            está ativo (identifica o widget de paginação).
    """
    if df.empty:
        st.info("Nenhum dado disponível para exibição.")
        return

    total = len(df)
    if paginacao and total > paginacao:
        if not key:
            raise ValueError(
                "exibir_tabela: 'key' é obrigatório quando "
                "'paginacao' está ativo."
            )
        num_pages = math.ceil(total / paginacao)
        corpo = st.container()
        rodape = st.container()
        with rodape:
            col_info, col_pag = st.columns([1, 2])
            with col_pag:
                pagina = st.pagination(
                    num_pages, key=f"{key}_pag"
                )
            ini = (pagina - 1) * paginacao
            fim = min(ini + paginacao, total)
            if highlight_mask is not None:
                highlight_mask = highlight_mask.iloc[ini:fim]
            df = df.iloc[ini:fim]
            with col_info:
                st.caption(
                    f"Exibindo {ini + 1:,}–{fim:,} de "
                    f"{total:,} registros".replace(",", ".")
                )
    else:
        corpo = st.container()

    with corpo:
        _exibir_tabela_corpo(
            df, altura, colunas_moeda, colunas_percentual,
            colunas_numero, column_config, usar_aggrid,
            highlight_mask, colunas_pontos,
        )


def _exibir_tabela_corpo(
    df: pd.DataFrame,
    altura: Optional[int],
    colunas_moeda: Optional[List[str]],
    colunas_percentual: Optional[List[str]],
    colunas_numero: Optional[List[str]],
    column_config: Optional[Dict],
    usar_aggrid: Optional[bool],
    highlight_mask: Optional["pd.Series"],
    colunas_pontos: Optional[List[str]] = None,
) -> None:
    """Renderiza a tabela em si (página atual, se paginada)."""
    h = altura if altura else _calcular_altura(len(df))

    use_grid = (
        usar_aggrid
        if usar_aggrid is not None
        else False
    )

    # AG Grid nao renderiza highlight_mask; havendo destaque a exibir,
    # usa st.dataframe para nao perde-lo silenciosamente.
    tem_highlight = highlight_mask is not None and highlight_mask.any()

    if use_grid and _TEM_AGGRID and not tem_highlight:
        _exibir_aggrid(
            df, h, colunas_moeda, colunas_percentual,
            colunas_numero, colunas_pontos,
        )
    else:
        _exibir_dataframe(
            df, h, colunas_moeda, colunas_percentual,
            colunas_numero, column_config, highlight_mask,
            colunas_pontos,
        )


def botao_exportar_csv(
    df: pd.DataFrame,
    nome: str,
    key: str,
) -> None:
    """Botão de download CSV para uma tabela.

    O CSV é gerado sob demanda (callable) apenas quando o
    usuário clica — sem custo de serialização a cada rerun.
    Codificação: UTF-8 com BOM (utf-8-sig) — sem o BOM o Excel
    pt-BR assume cp1252 e corrompe os acentos.

    Contrato de segurança (RLS): o chamador DEVE passar um
    DataFrame já filtrado pelo RLS do perfil ativo (princípio
    "RLS antes de render" — docs/agents/rls.md). Este helper
    exporta exatamente o que recebe, sem refazer filtros.
    """
    def _gerar_csv() -> bytes:
        csv = df.to_csv(index=False, sep=";", decimal=",")
        return csv.encode("utf-8-sig")

    st.download_button(
        label=f"Exportar {nome}",
        data=_gerar_csv,
        file_name=f"{nome}.csv",
        mime="text/csv",
        key=key,
        icon=":material/download:",
    )
