"""
Componente de tabelas do dashboard com suporte a AG Grid.

Utiliza st-aggrid para tabelas interativas com ordenação,
filtros e formatação automática. Fallback para st.dataframe
nativo quando AG Grid não está disponível.
"""
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
_NUMERO_KEYWORDS = [
    "Meta Prata", "Meta Ouro",
    "Pontos", "Qtd", "Posição", "Nº Lojas",
    "Nº Consultores", "Num Consultores", "TOTAL",
]


def _classificar_coluna(
    col: str,
    colunas_moeda: Optional[List[str]],
    colunas_percentual: Optional[List[str]],
    colunas_numero: Optional[List[str]],
) -> Optional[str]:
    """Retorna o tipo da coluna: 'moeda', 'perc', 'numero' ou None."""
    if colunas_moeda and col in colunas_moeda:
        return "moeda"
    if colunas_percentual and col in colunas_percentual:
        return "perc"
    if colunas_numero and col in colunas_numero:
        return "numero"
    if any(kw in col for kw in _PERC_KEYWORDS):
        return "perc"
    # Verificar número antes de moeda para que "Meta Prata"
    # e "Meta Ouro" (pontos) tenham prioridade sobre "Meta"
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
            col, colunas_moeda, colunas_percentual, colunas_numero
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
) -> None:
    """Exibe tabela usando AG Grid."""
    grid_options = _build_aggrid_options(
        df, colunas_moeda, colunas_percentual, colunas_numero, altura
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


def _formatar_dataframe_br(
    df: pd.DataFrame,
    colunas_moeda: Optional[List[str]],
    colunas_percentual: Optional[List[str]],
    colunas_numero: Optional[List[str]],
) -> pd.DataFrame:
    """
    Retorna cópia do DataFrame com colunas monetárias,
    numéricas e de data formatadas no padrão brasileiro.
    Datas (datetime64 ou texto ISO/UTC) viram dd/mm/aaaa.
    """
    df_fmt = df.copy()
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df_fmt[col] = df[col].dt.strftime("%d/%m/%Y").where(
                df[col].notna(), other=""
            )
            continue
        if _coluna_texto_e_data(df[col]):
            convertido = pd.to_datetime(df[col], errors="coerce")
            df_fmt[col] = convertido.dt.strftime("%d/%m/%Y").where(
                convertido.notna(), other=""
            )
            continue
        tipo = _classificar_coluna(
            col, colunas_moeda, colunas_percentual, colunas_numero
        )
        if tipo == "moeda":
            df_fmt[col] = df[col].apply(_formatar_moeda_br)
        elif tipo == "perc":
            df_fmt[col] = df[col].apply(
                lambda v: "" if pd.isna(v)
                else f"{v:.1f}%".replace(".", ",")
            )
        elif tipo == "numero":
            df_fmt[col] = df[col].apply(_formatar_numero_br)
    return df_fmt


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
) -> None:
    """Exibe tabela usando st.dataframe nativo (fallback)."""
    df_fmt = _formatar_dataframe_br(
        df, colunas_moeda, colunas_percentual, colunas_numero
    )

    if highlight_mask is not None and highlight_mask.any():
        mask = highlight_mask.reindex(df_fmt.index, fill_value=False)

        def _hl(row: "pd.Series") -> list:
            if mask.get(row.name, False):
                return [_HIGHLIGHT_STYLE] * len(row)
            return [""] * len(row)

        data = df_fmt.style.apply(_hl, axis=1)
    else:
        data = df_fmt

    st.dataframe(
        data,
        width="stretch",
        hide_index=True,
        height=altura,
        column_config=column_config,
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
            moeda (R$).
        colunas_percentual: Lista de colunas para formatar
            como percentual.
        colunas_numero: Lista de colunas para formatar como
            número inteiro.
        column_config: Configuração manual de colunas
            (apenas st.dataframe).
        usar_aggrid: Forçar AG Grid (True), st.dataframe
            (False), ou automático (None).
        highlight_mask: Série booleana (mesmo índice do df)
            indicando quais linhas destacar.
    """
    if df.empty:
        st.info("Nenhum dado disponível para exibição.")
        return

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
            colunas_numero,
        )
    else:
        _exibir_dataframe(
            df, h, colunas_moeda, colunas_percentual,
            colunas_numero, column_config, highlight_mask,
        )
