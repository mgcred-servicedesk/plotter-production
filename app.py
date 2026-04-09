"""
Dashboard interativo de vendas — MGCred.

Entrypoint principal para deploy no Streamlit Cloud.
Consome dados diretamente do banco Supabase (PostgreSQL),
usando categorias_produto, v_pontuacao_efetiva e views.
Autocontido: nao depende dos modulos de KPI antigos
(kpi_dashboard.py, kpi_analiticos.py) nem dos loaders
de planilha (column_mapper.py, pontuacao_loader.py).

Frontend: streamlit-antd-components para navegacao,
tabelas via st.dataframe, CSS design system customizado.
"""

import sys
import warnings
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit_antd_components as sac
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).parent))

from src.config.supabase_client import get_supabase_client
from src.dashboard.auth import (
    PERFIS,
    fazer_logout,
    tela_login,
    usuario_logado,
)
from src.dashboard.components.tables import exibir_tabela
from src.dashboard.rls import (
    aplicar_rls,
    aplicar_rls_metas,
    aplicar_rls_supervisores,
    obter_regioes_permitidas,
)
from src.dashboard.user_mgmt import render_pagina_usuarios

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*ScriptRunContext.*")

st.set_page_config(
    page_title="Dashboard de Vendas - MGCred",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ══════════════════════════════════════════════════════
# SISTEMA DE TEMAS (LIGHT / DARK)
# ══════════════════════════════════════════════════════

# Paleta estendida para graficos Plotly (CSS nao alcanca)
_CHART_THEME = {
    "light": {
        "text": "#1a1a2e",
        "text_secondary": "rgba(26,26,46,0.65)",
        "bg": "rgba(0,0,0,0)",
        "grid": "rgba(128,128,128,0.10)",
        "grid_zero": "rgba(128,128,128,0.15)",
        "tooltip_bg": "rgba(30,30,46,0.92)",
        "tooltip_text": "#ffffff",
        "border": "rgba(26,26,46,0.10)",
    },
    "dark": {
        "text": "#e2e4ea",
        "text_secondary": "rgba(226,228,234,0.55)",
        "bg": "rgba(0,0,0,0)",
        "grid": "rgba(226,228,234,0.06)",
        "grid_zero": "rgba(226,228,234,0.10)",
        "tooltip_bg": "rgba(15,17,23,0.95)",
        "tooltip_text": "#e2e4ea",
        "border": "rgba(226,228,234,0.08)",
    },
}

# Cores do tema nativo Streamlit (sincronizado com o toggle)
_NATIVE_THEME = {
    "light": {
        "base": "light",
        "primaryColor": "#2563eb",
        "backgroundColor": "#f8f9fb",
        "secondaryBackgroundColor": "#ffffff",
        "textColor": "#1a1a2e",
    },
    "dark": {
        "base": "dark",
        "primaryColor": "#3b82f6",
        "backgroundColor": "#0f1117",
        "secondaryBackgroundColor": "#1a1c25",
        "textColor": "#e2e4ea",
    },
}

# Variaveis CSS por tema (--mg-*)
_CSS_VARS = {
    "light": """
        --mg-primary: #2563eb;
        --mg-bg: #f8f9fb;
        --mg-secondary-bg: #ffffff;
        --mg-sidebar-bg: #ffffff;
        --mg-text: #1a1a2e;
        --mg-text-secondary: rgba(26,26,46,0.65);
        --mg-border: rgba(26,26,46,0.10);
        --mg-shadow: rgba(26,26,46,0.06);
        --mg-shadow-hover: rgba(26,26,46,0.10);
        --mg-card-border: rgba(26,26,46,0.08);
        --mg-hover-bg: rgba(37,99,235,0.04);
        --mg-scrollbar: rgba(26,26,46,0.18);
    """,
    "dark": """
        --mg-primary: #3b82f6;
        --mg-bg: #0f1117;
        --mg-secondary-bg: #1a1c25;
        --mg-sidebar-bg: #161820;
        --mg-text: #e2e4ea;
        --mg-text-secondary: rgba(226,228,234,0.55);
        --mg-border: rgba(226,228,234,0.08);
        --mg-shadow: rgba(0,0,0,0.20);
        --mg-shadow-hover: rgba(0,0,0,0.35);
        --mg-card-border: rgba(226,228,234,0.06);
        --mg-hover-bg: rgba(59,130,246,0.08);
        --mg-scrollbar: rgba(226,228,234,0.15);
    """,
}


def _get_theme() -> str:
    """Retorna tema ativo.

    Na primeira visita, detecta preferencia do sistema
    via localStorage (setado pelo JS de deteccao).
    """
    if "theme" not in st.session_state:
        # Tenta ler do query param _theme (setado pelo JS)
        detected = st.query_params.get("_theme")
        if detected in ("light", "dark"):
            st.session_state["theme"] = detected
            # Limpar o param para nao poluir a URL
            del st.query_params["_theme"]
        else:
            # Fallback: sera corrigido pelo JS de deteccao
            # no primeiro render (redireciona com ?_theme)
            st.session_state["theme"] = "light"
    return st.session_state["theme"]


def _chart_theme() -> dict:
    """Retorna paleta de cores para graficos Plotly."""
    return _CHART_THEME[_get_theme()]


def _aplicar_tema():
    """Sincroniza tema nativo Streamlit + CSS custom properties."""
    from streamlit.config import set_option

    theme = _get_theme()
    vars_css = _CSS_VARS[theme]
    native = _NATIVE_THEME[theme]

    # Sincronizar tema nativo (widgets, st.dataframe, st.metric)
    set_option("theme.base", native["base"])
    set_option("theme.primaryColor", native["primaryColor"])
    set_option(
        "theme.backgroundColor", native["backgroundColor"]
    )
    set_option(
        "theme.secondaryBackgroundColor",
        native["secondaryBackgroundColor"],
    )
    set_option("theme.textColor", native["textColor"])

    # CSS custom properties — o CSS file usa var(--mg-*)
    # Esconde o seletor nativo de tema para evitar conflito
    st.markdown(
        f"""<style>
        :root {{ {vars_css}
            --primary-color: var(--mg-primary) !important;
            --background-color: var(--mg-bg) !important;
            --secondary-background-color: var(--mg-secondary-bg) !important;
            --text-color: var(--mg-text) !important;
        }}
        html, body, .stApp,
        [data-testid="stAppViewContainer"],
        .main, .main .block-container {{
            background-color: var(--mg-bg) !important;
            color: var(--mg-text) !important;
        }}
        [data-testid="stHeader"], header {{
            background-color: var(--mg-bg) !important;
        }}
        [data-testid="stBottomBlockContainer"] {{
            background-color: var(--mg-bg) !important;
        }}
        section[data-testid="stSidebar"],
        section[data-testid="stSidebar"] > div {{
            background-color: var(--mg-sidebar-bg) !important;
        }}
        /* Esconder seletor de tema nativo para evitar
           dessincronizacao com o toggle customizado */
        [data-testid="stMainMenu"] ul li:has(
            [data-testid="stMainMenuPopoverThemeItem"]
        ) {{
            display: none !important;
        }}
        </style>""",
        unsafe_allow_html=True,
    )

    # JS: detectar preferencia do sistema na primeira
    # visita + persistir tema + tematizar iframes
    import streamlit.components.v1 as components

    is_dark = "true" if theme == "dark" else "false"
    components.html(
        f"""<script>
        (function() {{
            const p = window.parent;
            const isDark = {is_dark};

            // Detectar preferencia do sistema na 1a visita
            const stored = localStorage.getItem('mgcred_theme');
            if (!stored) {{
                const prefersDark = window.matchMedia
                    && window.matchMedia('(prefers-color-scheme: dark)').matches;
                const detected = prefersDark ? 'dark' : 'light';
                localStorage.setItem('mgcred_theme', detected);
                if (detected !== (isDark ? 'dark' : 'light')) {{
                    const url = new URL(p.location);
                    url.searchParams.set('_theme', detected);
                    p.location.replace(url.toString());
                    return;
                }}
            }}
            const tc = isDark ? '#e2e4ea' : '#1a1a2e';
            const pc = isDark ? '#3b82f6' : '#2563eb';
            const sb = isDark ? '#1a1c25' : '#ffffff';
            const bg = isDark ? '#0f1117' : '#f8f9fb';

            localStorage.setItem('mgcred_theme', isDark ? 'dark' : 'light');

            const VARS = {{
                '--primary-color': pc,
                '--background-color': bg,
                '--secondary-background-color': sb,
                '--text-color': tc,
            }};

            function inject(iframe) {{
                try {{
                    const doc = iframe.contentDocument
                             || iframe.contentWindow.document;
                    if (!doc || !doc.documentElement) return;
                    const root = doc.documentElement;
                    for (const [k, v] of Object.entries(VARS))
                        root.style.setProperty(k, v);
                    let s = doc.getElementById('mgcred-theme');
                    if (!s) {{
                        s = doc.createElement('style');
                        s.id = 'mgcred-theme';
                        doc.head.appendChild(s);
                    }}
                    s.textContent = `
                        :root, body {{ background:transparent!important; color:${{tc}}!important }}
                        .ant-divider {{ border-color:${{tc}}20!important }}
                        .ant-divider-inner-text {{ background:transparent!important; color:${{tc}}!important }}
                        .ant-tabs-tab-btn {{ color:${{tc}}90!important }}
                        .ant-tabs-tab-active .ant-tabs-tab-btn {{ color:${{pc}}!important }}
                        .ant-tabs-ink-bar {{ background:${{pc}}!important }}
                        .ant-tabs-nav::before {{ border-color:${{tc}}15!important }}
                        .ant-tabs-card .ant-tabs-tab {{ background:transparent!important; border-color:${{tc}}15!important }}
                        .ant-tabs-card .ant-tabs-tab-active {{ background:${{sb}}!important; border-color:${{pc}}!important }}
                        .ant-segmented {{ background:${{tc}}10!important }}
                        .ant-segmented-item-label {{ color:${{tc}}80!important }}
                        .ant-segmented-item-selected .ant-segmented-item-label {{ color:${{pc}}!important }}
                        .ant-segmented-thumb {{ background:${{sb}}!important }}
                    `;
                }} catch(e) {{}}
            }}

            function run() {{
                p.document.querySelectorAll('iframe').forEach(f => {{
                    if (f.contentDocument) inject(f);
                    else f.addEventListener('load', () => inject(f));
                }});
            }}

            run();
            const obs = new MutationObserver(muts => {{
                for (const m of muts)
                    for (const n of m.addedNodes)
                        if (n.tagName === 'IFRAME' || (n.querySelectorAll && n.querySelectorAll('iframe').length))
                            {{ setTimeout(run, 100); return; }}
            }});
            obs.observe(p.document.body, {{ childList:true, subtree:true }});
            setTimeout(run, 500);
            setTimeout(run, 1500);
        }})();
        </script>""",
        height=0,
    )


# ══════════════════════════════════════════════════════
# PALETA DE CORES PARA GRAFICOS
# ══════════════════════════════════════════════════════

CHART_COLORS = {
    "primary": "#2563eb",
    "primary_dark": "#1e40af",
    "secondary": "#0d9488",
    "success": "#059669",
    "danger": "#dc2626",
    "warning": "#d97706",
    "neutral": "#64748b",
    "purple": "#7c3aed",
    "rose": "#e11d48",
    "seq": [
        "#2563eb",
        "#0d9488",
        "#7c3aed",
        "#d97706",
        "#059669",
        "#e11d48",
        "#64748b",
        "#0284c7",
    ],
}


# ══════════════════════════════════════════════════════
# CAMADA DE DADOS — SUPABASE
# ══════════════════════════════════════════════════════


def _sb():
    """Atalho para obter o cliente Supabase."""
    return get_supabase_client()


def _ttl_periodo(
    mes: int,
    ano: int,
    ttl_atual: int,
    ttl_historico: int,
) -> int:
    """Retorna TTL curto para periodo vigente, longo para historico.

    Periodos fechados (meses passados) raramente mudam,
    entao podem ter cache longo. O mes corrente usa TTL
    mais curto para refletir atualizacoes diarias.
    """
    hoje = datetime.now()
    if mes == hoje.month and ano == hoje.year:
        return ttl_atual
    return ttl_historico


@st.cache_data(ttl=86400)
def carregar_categorias() -> pd.DataFrame:
    """Carrega categorias_produto do banco. TTL 24h — raramente muda."""
    resp = (
        _sb()
        .table("categorias_produto")
        .select("*")
        .eq("ativo", True)
        .order("ordem")
        .execute()
    )
    return pd.DataFrame(resp.data or [])


@st.cache_data(ttl=86400)
def carregar_periodo(mes: int, ano: int) -> Optional[dict]:
    """Busca o periodo correspondente a mes/ano. TTL 24h — imutavel."""
    resp = (
        _sb()
        .table("periodos")
        .select("id, mes, ano, referencia")
        .eq("mes", mes)
        .eq("ano", ano)
        .limit(1)
        .execute()
    )
    return resp.data[0] if resp.data else None


_PAGE_SIZE = 1000


def carregar_contratos_pagos(
    mes: int,
    ano: int,
) -> pd.DataFrame:
    """Carrega contratos pagos via view v_contratos_dashboard.

    TTL dinamico: 30min para mes corrente, 24h para historico.
    A view resolve todos os joins no banco — sem paginacao manual.
    """
    ttl = _ttl_periodo(mes, ano, 1800, 86400)
    return _carregar_contratos_pagos_cached(mes, ano, ttl)


@st.cache_data(ttl=1800)
def _carregar_contratos_pagos_cached(
    mes: int,
    ano: int,
    _ttl: int,
) -> pd.DataFrame:
    """Cache interno com TTL variavel via parametro _ttl."""
    periodo = carregar_periodo(mes, ano)
    if not periodo:
        return pd.DataFrame()

    all_data: List[dict] = []
    offset = 0
    while True:
        resp = (
            _sb()
            .from_("v_contratos_dashboard")
            .select("*")
            .eq("periodo_id", periodo["id"])
            .order("id")
            .limit(_PAGE_SIZE)
            .offset(offset)
            .execute()
        )
        batch = resp.data or []
        all_data.extend(batch)
        if len(batch) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    if not all_data:
        return pd.DataFrame()

    rows = []
    for c in all_data:
        rows.append(
            {
                "CONTRATO_ID": c.get("contrato_id"),
                "DATA": c.get("data_status_pagamento"),
                "DATA_CADASTRO": c.get("data_cadastro"),
                "LOJA": c.get("loja", ""),
                "REGIAO": c.get("regiao", ""),
                "CONSULTOR": c.get("consultor", ""),
                "PRODUTO": c.get("produto", ""),
                "TIPO_PRODUTO": c.get("tipo_produto", ""),
                "SUBTIPO": c.get("subtipo", ""),
                "TIPO OPER.": c.get("tipo_operacao", ""),
                "VALOR": float(c.get("valor", 0)),
                "BANCO": c.get("banco", ""),
                "CONVENIO": c.get("convenio", ""),
                "categoria_codigo": c.get("categoria_codigo", ""),
                "grupo_dashboard": c.get("grupo_dashboard"),
                "grupo_meta": c.get("grupo_meta"),
                "conta_valor": c.get("conta_valor", True),
                "conta_pontuacao": c.get("conta_pontuacao", True),
            }
        )

    df = pd.DataFrame(rows)

    if "DATA" in df.columns:
        df["DATA"] = pd.to_datetime(df["DATA"], errors="coerce")

    return df


def carregar_contratos_em_analise(
    mes: int,
    ano: int,
) -> pd.DataFrame:
    """Carrega contratos em analise via RPC obter_contratos_em_analise.

    TTL dinamico: 15min para mes corrente, 6h para historico.
    A RPC encapsula a logica de datas (ultimos 30 dias) no banco.
    """
    ttl = _ttl_periodo(mes, ano, 900, 21600)
    return _carregar_contratos_em_analise_cached(mes, ano, ttl)


@st.cache_data(ttl=900)
def _carregar_contratos_em_analise_cached(
    mes: int,
    ano: int,
    _ttl: int,
) -> pd.DataFrame:
    """Cache interno com TTL variavel via parametro _ttl."""
    resp = (
        _sb()
        .rpc(
            "obter_contratos_em_analise",
            {"p_mes": mes, "p_ano": ano},
        )
        .execute()
    )

    all_data = resp.data or []
    if not all_data:
        return pd.DataFrame()

    rows = []
    for c in all_data:
        rows.append(
            {
                "CONTRATO_ID": c.get("contrato_id"),
                "DATA_CADASTRO": c.get("data_cadastro"),
                "LOJA": c.get("loja", ""),
                "REGIAO": c.get("regiao", ""),
                "CONSULTOR": c.get("consultor", ""),
                "PRODUTO": c.get("produto", ""),
                "TIPO_PRODUTO": c.get("tipo_produto", ""),
                "SUBTIPO": c.get("subtipo", ""),
                "TIPO OPER.": c.get("tipo_operacao", ""),
                "VALOR": float(c.get("valor", 0)),
                "BANCO": c.get("banco", ""),
                "STATUS_BANCO": c.get("status_banco", ""),
                "categoria_codigo": c.get("categoria_codigo", ""),
                "grupo_dashboard": c.get("grupo_dashboard"),
                "conta_valor": c.get("conta_valor", True),
            }
        )

    df = pd.DataFrame(rows)

    if "DATA_CADASTRO" in df.columns:
        df["DATA_CADASTRO"] = pd.to_datetime(
            df["DATA_CADASTRO"], errors="coerce"
        )

    return df


def carregar_contratos_cancelados(
    mes: int,
    ano: int,
) -> pd.DataFrame:
    """Carrega contratos cancelados via RPC obter_contratos_cancelados.

    TTL dinamico: 15min para mes corrente, 6h para historico.
    """
    ttl = _ttl_periodo(mes, ano, 900, 21600)
    return _carregar_contratos_cancelados_cached(mes, ano, ttl)


@st.cache_data(ttl=900)
def _carregar_contratos_cancelados_cached(
    mes: int,
    ano: int,
    _ttl: int,
) -> pd.DataFrame:
    """Cache interno com TTL variavel via parametro _ttl."""
    resp = (
        _sb()
        .rpc(
            "obter_contratos_cancelados",
            {"p_mes": mes, "p_ano": ano},
        )
        .execute()
    )

    all_data = resp.data or []
    if not all_data:
        return pd.DataFrame()

    rows = []
    for c in all_data:
        rows.append(
            {
                "CONTRATO_ID": c.get("contrato_id"),
                "DATA_CADASTRO": c.get("data_cadastro"),
                "LOJA": c.get("loja", ""),
                "REGIAO": c.get("regiao", ""),
                "CONSULTOR": c.get("consultor", ""),
                "PRODUTO": c.get("produto", ""),
                "TIPO_PRODUTO": c.get("tipo_produto", ""),
                "SUBTIPO": c.get("subtipo", ""),
                "TIPO OPER.": c.get("tipo_operacao", ""),
                "VALOR": float(c.get("valor", 0)),
                "BANCO": c.get("banco", ""),
                "STATUS_BANCO": c.get("status_banco", ""),
                "SUB_STATUS": c.get("sub_status_banco", ""),
                "STATUS_PAG": c.get(
                    "status_pagamento_cliente", ""
                ),
                "categoria_codigo": c.get(
                    "categoria_codigo", ""
                ),
                "grupo_dashboard": c.get("grupo_dashboard"),
                "conta_valor": c.get("conta_valor", True),
            }
        )

    df = pd.DataFrame(rows)

    if "DATA_CADASTRO" in df.columns:
        df["DATA_CADASTRO"] = pd.to_datetime(
            df["DATA_CADASTRO"], errors="coerce"
        )

    return df


def carregar_pontuacao_efetiva(
    mes: int,
    ano: int,
) -> pd.DataFrame:
    """Carrega pontuacao efetiva via funcao SQL.

    TTL dinamico: 6h para mes corrente, 24h para historico.
    Pontuacao muda raramente dentro do mes.
    """
    ttl = _ttl_periodo(mes, ano, 21600, 86400)
    return _carregar_pontuacao_cached(mes, ano, ttl)


@st.cache_data(ttl=21600)
def _carregar_pontuacao_cached(
    mes: int,
    ano: int,
    _ttl: int,
) -> pd.DataFrame:
    """Cache interno com TTL variavel."""
    resp = (
        _sb()
        .rpc(
            "obter_pontuacao_periodo",
            {"p_mes": mes, "p_ano": ano},
        )
        .execute()
    )
    return pd.DataFrame(resp.data or [])


def carregar_metas(mes: int, ano: int) -> pd.DataFrame:
    """Carrega metas GERAL/LOJA do periodo.

    TTL dinamico: 6h para mes corrente, 24h para historico.
    Metas sao definidas mensalmente e raramente mudam intraday.
    """
    ttl = _ttl_periodo(mes, ano, 21600, 86400)
    return _carregar_metas_cached(mes, ano, ttl)


@st.cache_data(ttl=21600)
def _carregar_metas_cached(
    mes: int, ano: int, _ttl: int,
) -> pd.DataFrame:
    """Cache interno com TTL variavel."""
    periodo = carregar_periodo(mes, ano)
    if not periodo:
        return pd.DataFrame()

    resp = (
        _sb()
        .table("metas")
        .select(
            "id, produto, escopo, nivel, valor, "
            "lojas(nome)"
        )
        .eq("periodo_id", periodo["id"])
        .eq("produto", "GERAL")
        .eq("escopo", "LOJA")
        .execute()
    )

    if not resp.data:
        return pd.DataFrame(
            columns=["LOJA", "META_PRATA", "META_OURO"]
        )

    rows = []
    for m in resp.data:
        loja = m.get("lojas") or {}
        rows.append(
            {
                "LOJA": loja.get("nome", ""),
                "nivel": m.get("nivel"),
                "valor": float(m.get("valor", 0)),
            }
        )

    df_geral_loja = pd.DataFrame(rows)

    if not df_geral_loja.empty:
        df_pivot = df_geral_loja.pivot_table(
            index="LOJA",
            columns="nivel",
            values="valor",
            aggfunc="sum",
        ).reset_index()

        rename_map = {}
        if "PRATA" in df_pivot.columns:
            rename_map["PRATA"] = "META_PRATA"
        if "OURO" in df_pivot.columns:
            rename_map["OURO"] = "META_OURO"
        if "BRONZE" in df_pivot.columns:
            rename_map["BRONZE"] = "META_BRONZE"
        df_pivot = df_pivot.rename(columns=rename_map)

        for col in ["META_PRATA", "META_OURO"]:
            if col not in df_pivot.columns:
                df_pivot[col] = 0

        return df_pivot

    return pd.DataFrame(columns=["LOJA", "META_PRATA", "META_OURO"])


def carregar_metas_produto(
    mes: int,
    ano: int,
) -> pd.DataFrame:
    """Carrega metas por produto do periodo.

    TTL dinamico: 6h para mes corrente, 24h para historico.
    """
    ttl = _ttl_periodo(mes, ano, 21600, 86400)
    return _carregar_metas_produto_cached(mes, ano, ttl)


@st.cache_data(ttl=21600)
def _carregar_metas_produto_cached(
    mes: int, ano: int, _ttl: int,
) -> pd.DataFrame:
    """Cache interno com TTL variavel."""
    periodo = carregar_periodo(mes, ano)
    if not periodo:
        return pd.DataFrame()

    resp = (
        _sb()
        .table("metas")
        .select("produto, escopo, nivel, valor, lojas(nome)")
        .eq("periodo_id", periodo["id"])
        .eq("escopo", "LOJA")
        .is_("nivel", "null")
        .execute()
    )

    if not resp.data:
        return pd.DataFrame()

    rows = []
    for m in resp.data:
        loja = m.get("lojas") or {}
        rows.append(
            {
                "LOJA": loja.get("nome", ""),
                "produto_meta": m["produto"],
                "valor": float(m.get("valor", 0)),
            }
        )

    df = pd.DataFrame(rows)

    # Deduplicar por (LOJA, produto_meta) — constraint
    # UNIQUE com nivel NULL nao impede duplicatas no PG
    df = df.drop_duplicates(
        subset=["LOJA", "produto_meta"], keep="first"
    )

    # Pivotar para ter uma coluna por produto_meta
    if not df.empty:
        df_pivot = df.pivot_table(
            index="LOJA",
            columns="produto_meta",
            values="valor",
            aggfunc="sum",
            fill_value=0,
        ).reset_index()
        return df_pivot

    return pd.DataFrame(columns=["LOJA"])


@st.cache_data(ttl=21600)
def carregar_supervisores() -> pd.DataFrame:
    """Carrega supervisores com suas lojas e regioes. TTL 6h."""
    resp = (
        _sb().table("supervisores").select("nome, lojas(nome), regioes(nome)").execute()
    )

    if not resp.data:
        return pd.DataFrame(columns=["SUPERVISOR", "LOJA", "REGIAO"])

    rows = []
    for s in resp.data:
        loja = s.get("lojas") or {}
        regiao = s.get("regioes") or {}
        rows.append(
            {
                "SUPERVISOR": s.get("nome", ""),
                "LOJA": loja.get("nome", ""),
                "REGIAO": regiao.get("nome", ""),
            }
        )

    return pd.DataFrame(rows)


def consolidar_dados(
    mes: int,
    ano: int,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Carrega, consolida e aplica pontuacao/regras.

    Delega o processamento pesado para _consolidar_cached()
    e popula o diagnostico no session_state (side-effect
    que nao pode viver dentro de cache_data).

    Returns:
        (df_consolidado, df_metas, df_supervisores)
    """
    ttl = _ttl_periodo(mes, ano, 1800, 86400)
    resultado = _consolidar_cached(mes, ano, ttl)
    df, df_metas, df_supervisores, diag = resultado

    # Side-effect: diagnostico no session_state
    if diag:
        st.session_state["_diag_pontuacao"] = diag

    return df, df_metas, df_supervisores


@st.cache_data(ttl=1800)
def _consolidar_cached(
    mes: int,
    ano: int,
    _ttl: int,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Optional[dict]]:
    """Consolidacao cacheada — pura, sem side-effects."""
    df = carregar_contratos_pagos(mes, ano)
    df_pontos = carregar_pontuacao_efetiva(mes, ano)
    df_metas = carregar_metas(mes, ano)
    df_supervisores = carregar_supervisores()

    if df.empty:
        return df, df_metas, df_supervisores, None

    # Fallback: preencher categoria_codigo via TIPO_PRODUTO
    # quando produtos.categoria_id esta NULL no banco
    _TIPO_PARA_CATEGORIA = {
        "CNC": "CNC",
        "CNC 13º": "CNC_13",
        "CNC 13": "CNC_13",
        "CNC ANT": "ANT_BENEF",
        "SAQUE": "SAQUE",
        "SAQUE BENEFICIO": "SAQUE_BENEFICIO",
        "CONSIG": "CONSIG_BMG",
        "CONSIG BMG": "CONSIG_BMG",
        "CONSIG PRIV": "CONSIG_PRIV",
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

    mask_sem_cat = df["categoria_codigo"] == ""
    if mask_sem_cat.any() and "TIPO_PRODUTO" in df.columns:
        df.loc[mask_sem_cat, "categoria_codigo"] = (
            df.loc[mask_sem_cat, "TIPO_PRODUTO"]
            .map(_TIPO_PARA_CATEGORIA)
            .fillna("")
        )

        # Preencher grupo_dashboard, grupo_meta, conta_valor,
        # conta_pontuacao a partir das categorias do banco
        categorias = carregar_categorias()
        if not categorias.empty:
            cat_map = categorias.set_index("codigo")
            preenchidos = mask_sem_cat & (df["categoria_codigo"] != "")

            for campo in [
                "grupo_dashboard",
                "grupo_meta",
                "conta_valor",
                "conta_pontuacao",
            ]:
                if campo in cat_map.columns:
                    df.loc[preenchidos, campo] = (
                        df.loc[preenchidos, "categoria_codigo"]
                        .map(cat_map[campo])
                    )

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
    df["is_super_conta"] = df["SUBTIPO"] == "SUPER CONTA"

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

    return df, df_metas, df_supervisores, diag


# ══════════════════════════════════════════════════════
# CALCULO DE DIAS UTEIS
# ══════════════════════════════════════════════════════


def calcular_dias_uteis(
    ano: int,
    mes: int,
    dia_atual: Optional[int] = None,
) -> Tuple[int, int, int]:
    """Calcula total de DU, DU decorridos e restantes."""
    if dia_atual is None:
        data_ref = datetime.now()
    else:
        data_ref = datetime(ano, mes, int(dia_atual))

    primeiro_dia = datetime(ano, mes, 1)
    if mes == 12:
        ultimo_dia = datetime(ano + 1, 1, 1) - pd.Timedelta(days=1)
    else:
        ultimo_dia = datetime(ano, mes + 1, 1) - pd.Timedelta(days=1)

    total_du = len(pd.bdate_range(primeiro_dia, ultimo_dia))

    if data_ref < primeiro_dia:
        return total_du, 0, total_du
    if data_ref > ultimo_dia:
        return total_du, total_du, 0

    du_decorridos = len(pd.bdate_range(primeiro_dia, data_ref))
    du_restantes = total_du - du_decorridos

    return total_du, du_decorridos, du_restantes


# ══════════════════════════════════════════════════════
# CALCULO DE KPIs
# ══════════════════════════════════════════════════════


def calcular_kpis_gerais(
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    ano: int,
    mes: int,
    dia_atual: Optional[int] = None,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> Dict:
    """Calcula KPIs gerais do dashboard."""
    du_total, du_dec, du_rest = calcular_dias_uteis(ano, mes, dia_atual)

    total_vendas = df["VALOR"].sum()
    total_pontos = df["pontos"].sum()
    total_transacoes = len(df[df["VALOR"] > 0])

    meta_prata = 0
    meta_ouro = 0
    if "META_PRATA" in df_metas.columns:
        meta_prata = (
            pd.to_numeric(df_metas["META_PRATA"], errors="coerce").fillna(0).sum()
        )
    if "META_OURO" in df_metas.columns:
        meta_ouro = (
            pd.to_numeric(df_metas["META_OURO"], errors="coerce").fillna(0).sum()
        )

    perc_prata = (total_pontos / meta_prata * 100) if meta_prata > 0 else 0
    perc_ouro = (total_pontos / meta_ouro * 100) if meta_ouro > 0 else 0

    media_du = total_vendas / du_dec if du_dec > 0 else 0
    media_du_pts = total_pontos / du_dec if du_dec > 0 else 0
    meta_diaria = meta_prata / du_total if du_total > 0 else 0
    gap_pontos = max(0, meta_prata - total_pontos)
    meta_diaria_restante = gap_pontos / du_rest if du_rest > 0 else 0
    projecao = media_du * du_total
    projecao_pts = media_du_pts * du_total
    perc_proj = (projecao_pts / meta_prata * 100) if meta_prata > 0 else 0
    ticket_medio = total_vendas / total_transacoes if total_transacoes > 0 else 0

    num_consultores = 0
    if "CONSULTOR" in df.columns:
        consultores_unicos = df["CONSULTOR"].unique()
        if df_supervisores is not None and "SUPERVISOR" in df_supervisores.columns:
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
        "meta_diaria": meta_diaria,
        "meta_diaria_restante": meta_diaria_restante,
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


def _excluir_supervisores(
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


def _contar_consultores(
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


def calcular_kpis_por_produto(
    df: pd.DataFrame,
    df_metas_produto: pd.DataFrame,
    categorias: pd.DataFrame,
    ano: int,
    mes: int,
    dia_atual: Optional[int] = None,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Calcula KPIs por grupo de produto do dashboard."""
    du_total, du_dec, du_rest = calcular_dias_uteis(ano, mes, dia_atual)

    num_consultores = _contar_consultores(df, df_supervisores)

    # Grupos do dashboard vindos do banco
    grupos = (
        categorias[categorias["grupo_dashboard"].notna()]["grupo_dashboard"]
        .unique()
        .tolist()
    )

    # Mapeamento grupo_dashboard → grupo_meta
    grupo_meta_map = (
        categorias[categorias["grupo_dashboard"].notna()]
        .groupby("grupo_dashboard")["grupo_meta"]
        .first()
        .to_dict()
    )

    dados = []
    for grupo in sorted(grupos):
        df_grupo = df[df["grupo_dashboard"] == grupo].copy()

        valor = df_grupo["VALOR"].sum()
        quantidade = len(df_grupo[df_grupo["VALOR"] > 0])

        # Buscar meta por grupo_meta
        meta_key = grupo_meta_map.get(grupo, grupo)
        meta_total = 0
        if not df_metas_produto.empty and meta_key in df_metas_produto.columns:
            meta_total = (
                pd.to_numeric(
                    df_metas_produto[meta_key],
                    errors="coerce",
                )
                .fillna(0)
                .sum()
            )

        perc_ating = (valor / meta_total * 100) if meta_total > 0 else 0
        media_du = valor / du_dec if du_dec > 0 else 0
        meta_diaria = meta_total / du_total if du_total > 0 else 0
        gap = max(0, meta_total - valor)
        meta_diaria_rest = gap / du_rest if du_rest > 0 else 0
        ticket = valor / quantidade if quantidade > 0 else 0
        projecao = media_du * du_total
        perc_proj = (projecao / meta_total * 100) if meta_total > 0 else 0
        valor_medio_cons = valor / num_consultores if num_consultores > 0 else 0

        dados.append(
            {
                "Produto": grupo,
                "Valor": valor,
                "Meta": meta_total,
                "Meta Diária": meta_diaria,
                "Meta Diária Restante": meta_diaria_rest,
                "% Atingimento": perc_ating,
                "Quantidade": quantidade,
                "Ticket Médio": ticket,
                "Valor Médio/Consultor": valor_medio_cons,
                "Média DU": media_du,
                "Projeção": projecao,
                "% Projeção": perc_proj,
            }
        )

    return pd.DataFrame(dados)


def calcular_kpis_por_regiao(
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    ano: int,
    mes: int,
    dia_atual: Optional[int] = None,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Calcula KPIs por regiao."""
    if "REGIAO" not in df.columns:
        return pd.DataFrame()

    du_total, du_dec, _ = calcular_dias_uteis(ano, mes, dia_atual)

    dados = []
    for regiao in sorted(df["REGIAO"].unique()):
        df_r = df[df["REGIAO"] == regiao]

        valor = df_r["VALOR"].sum()
        pontos = df_r["pontos"].sum()
        num_lojas = df_r["LOJA"].nunique()
        num_cons = _contar_consultores(df_r, df_supervisores)

        meta_prata = 0
        if "META_PRATA" in df_metas.columns:
            lojas_r = df_r["LOJA"].unique()
            meta_prata = df_metas[df_metas["LOJA"].isin(lojas_r)]["META_PRATA"].sum()

        perc = (pontos / meta_prata * 100) if meta_prata > 0 else 0
        media_du = valor / du_dec if du_dec > 0 else 0
        projecao = media_du * du_total
        valor_medio_cons = valor / num_cons if num_cons > 0 else 0

        dados.append(
            {
                "Região": regiao,
                "Valor": valor,
                "Pontos": pontos,
                "Meta Prata": meta_prata,
                "% Atingimento": perc,
                "Nº Lojas": num_lojas,
                "Nº Consultores": num_cons,
                "Valor Médio/Consultor": valor_medio_cons,
                "Média DU": media_du,
                "Projeção": projecao,
            }
        )

    return pd.DataFrame(dados)


def calcular_ranking_lojas(
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    top_n: int = 10,
) -> pd.DataFrame:
    """Ranking de lojas por atingimento de meta prata."""
    df_v = df[df["VALOR"] > 0].copy()
    if "LOJA" not in df_v.columns:
        return pd.DataFrame()

    ranking = (
        df_v.groupby("LOJA")
        .agg(
            Qtd=("VALOR", "count"),
            Valor=("VALOR", "sum"),
            Pontos=("pontos", "sum"),
        )
        .reset_index()
        .rename(columns={"LOJA": "Loja"})
    )

    if "REGIAO" in df.columns:
        df_reg = df[["LOJA", "REGIAO"]].drop_duplicates()
        ranking = ranking.merge(
            df_reg,
            left_on="Loja",
            right_on="LOJA",
            how="left",
        ).drop("LOJA", axis=1)

    if "LOJA" in df_metas.columns and "META_PRATA" in df_metas.columns:
        ranking = ranking.merge(
            df_metas[["LOJA", "META_PRATA"]],
            left_on="Loja",
            right_on="LOJA",
            how="left",
        )
        ranking["Meta Prata"] = ranking["META_PRATA"].fillna(0)
        ranking = ranking.drop(["LOJA", "META_PRATA"], axis=1)
    else:
        ranking["Meta Prata"] = 0

    ranking["Atingimento %"] = ranking.apply(
        lambda r: r["Pontos"] / r["Meta Prata"] * 100 if r["Meta Prata"] > 0 else 0,
        axis=1,
    )
    ranking["Ticket Médio"] = ranking.apply(
        lambda r: r["Valor"] / r["Qtd"] if r["Qtd"] > 0 else 0,
        axis=1,
    )

    ranking = ranking.sort_values("Atingimento %", ascending=False).head(top_n)
    ranking.insert(0, "Posição", range(1, len(ranking) + 1))
    return ranking


def calcular_ranking_consultores(
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    top_n: int = 10,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Ranking de consultores por atingimento."""
    df_v = _excluir_supervisores(df[df["VALOR"] > 0], df_supervisores)
    if "CONSULTOR" not in df_v.columns:
        return pd.DataFrame()

    ranking = (
        df_v.groupby("CONSULTOR")
        .agg(
            Qtd=("VALOR", "count"),
            Valor=("VALOR", "sum"),
            Pontos=("pontos", "sum"),
            Loja=("LOJA", "first"),
        )
        .reset_index()
        .rename(columns={"CONSULTOR": "Consultor"})
    )

    if "LOJA" in df_metas.columns and "META_PRATA" in df_metas.columns:
        metas_loja = df_metas.set_index("LOJA")["META_PRATA"]
        num_cons_loja = df_v.groupby("LOJA")["CONSULTOR"].nunique()

        ranking["Meta Prata"] = ranking["Loja"].map(
            lambda x: (
                metas_loja.get(x, 0) / num_cons_loja.get(x, 1)
                if x in num_cons_loja.index
                else 0
            )
        )
    else:
        ranking["Meta Prata"] = 0

    ranking["Atingimento %"] = ranking.apply(
        lambda r: r["Pontos"] / r["Meta Prata"] * 100 if r["Meta Prata"] > 0 else 0,
        axis=1,
    )
    ranking["Ticket Médio"] = ranking.apply(
        lambda r: r["Valor"] / r["Qtd"] if r["Qtd"] > 0 else 0,
        axis=1,
    )

    ranking = ranking.sort_values("Atingimento %", ascending=False).head(top_n)
    ranking.insert(0, "Posição", range(1, len(ranking) + 1))
    return ranking


def calcular_ranking_ticket_medio(
    df: pd.DataFrame,
    tipo: str = "loja",
    top_n: int = 10,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Ranking por ticket medio (lojas ou consultores)."""
    df_v = df[df["VALOR"] > 0].copy()

    if tipo == "consultor":
        df_v = _excluir_supervisores(df_v, df_supervisores)

    coluna = "LOJA" if tipo == "loja" else "CONSULTOR"
    label = "Loja" if tipo == "loja" else "Consultor"

    if coluna not in df_v.columns:
        return pd.DataFrame()

    agg_dict = {
        "Qtd": ("VALOR", "count"),
        "Valor": ("VALOR", "sum"),
        "Pontos": ("pontos", "sum"),
    }
    if tipo == "consultor":
        agg_dict["Loja"] = ("LOJA", "first")

    ranking = (
        df_v.groupby(coluna)
        .agg(**agg_dict)
        .reset_index()
        .rename(columns={coluna: label})
    )

    if "REGIAO" in df.columns and tipo == "loja":
        df_reg = df[["LOJA", "REGIAO"]].drop_duplicates()
        ranking = ranking.merge(
            df_reg,
            left_on="Loja",
            right_on="LOJA",
            how="left",
        ).drop("LOJA", axis=1)

    ranking["Ticket Médio"] = ranking.apply(
        lambda r: r["Valor"] / r["Qtd"] if r["Qtd"] > 0 else 0,
        axis=1,
    )

    ranking = ranking.sort_values("Ticket Médio", ascending=False).head(top_n)
    ranking.insert(0, "Posição", range(1, len(ranking) + 1))
    return ranking


def calcular_ranking_por_produto(
    df: pd.DataFrame,
    tipo: str = "loja",
    top_n: int = 10,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> Dict[str, pd.DataFrame]:
    """Rankings por grupo_dashboard (lojas ou consultores)."""
    df_v = df[df["VALOR"] > 0].copy()
    if tipo == "consultor":
        df_v = _excluir_supervisores(df_v, df_supervisores)

    grupos = df_v[df_v["grupo_dashboard"].notna()]["grupo_dashboard"].unique()

    coluna = "LOJA" if tipo == "loja" else "CONSULTOR"
    label = "Loja" if tipo == "loja" else "Consultor"

    rankings = {}
    for grupo in sorted(grupos):
        df_g = df_v[df_v["grupo_dashboard"] == grupo]
        if df_g.empty:
            rankings[grupo] = pd.DataFrame()
            continue

        agg_dict = {
            "Qtd": ("VALOR", "count"),
            "Valor": ("VALOR", "sum"),
            "Pontos": ("pontos", "sum"),
        }
        if tipo == "consultor":
            agg_dict["Loja"] = ("LOJA", "first")

        ranking = (
            df_g.groupby(coluna)
            .agg(**agg_dict)
            .reset_index()
            .rename(columns={coluna: label})
        )
        ranking["Ticket Médio"] = ranking.apply(
            lambda r: r["Valor"] / r["Qtd"] if r["Qtd"] > 0 else 0,
            axis=1,
        )
        ranking = ranking.sort_values("Pontos", ascending=False).head(top_n)
        ranking.insert(0, "Posição", range(1, len(ranking) + 1))
        rankings[grupo] = ranking

    return rankings


def calcular_ranking_pontos(
    df: pd.DataFrame,
    tipo: str = "loja",
    top_n: int = 10,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Ranking por pontos (lojas ou consultores)."""
    df_v = df[df["VALOR"] > 0].copy()

    if tipo == "consultor":
        df_v = _excluir_supervisores(df_v, df_supervisores)

    coluna = "LOJA" if tipo == "loja" else "CONSULTOR"
    label = "Loja" if tipo == "loja" else "Consultor"

    if coluna not in df_v.columns:
        return pd.DataFrame()

    agg_dict = {
        "Qtd": ("VALOR", "count"),
        "Valor": ("VALOR", "sum"),
        "Pontos": ("pontos", "sum"),
    }
    if tipo == "consultor":
        agg_dict["Loja"] = ("LOJA", "first")

    ranking = (
        df_v.groupby(coluna)
        .agg(**agg_dict)
        .reset_index()
        .rename(columns={coluna: label})
    )

    if "REGIAO" in df.columns and tipo == "loja":
        df_reg = df[["LOJA", "REGIAO"]].drop_duplicates()
        ranking = ranking.merge(
            df_reg,
            left_on="Loja",
            right_on="LOJA",
            how="left",
        ).drop("LOJA", axis=1)

    ranking["Ticket Médio"] = ranking.apply(
        lambda r: r["Valor"] / r["Qtd"] if r["Qtd"] > 0 else 0,
        axis=1,
    )

    ranking = ranking.sort_values(
        "Pontos", ascending=False,
    ).head(top_n)
    ranking.insert(0, "Posição", range(1, len(ranking) + 1))
    return ranking


def calcular_ranking_media_du(
    df: pd.DataFrame,
    tipo: str = "loja",
    top_n: int = 10,
    du_decorridos: int = 1,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Ranking por media DU (lojas ou consultores)."""
    df_v = df[df["VALOR"] > 0].copy()

    if tipo == "consultor":
        df_v = _excluir_supervisores(df_v, df_supervisores)

    coluna = "LOJA" if tipo == "loja" else "CONSULTOR"
    label = "Loja" if tipo == "loja" else "Consultor"

    if coluna not in df_v.columns:
        return pd.DataFrame()

    agg_dict = {
        "Qtd": ("VALOR", "count"),
        "Valor": ("VALOR", "sum"),
        "Pontos": ("pontos", "sum"),
    }
    if tipo == "consultor":
        agg_dict["Loja"] = ("LOJA", "first")

    ranking = (
        df_v.groupby(coluna)
        .agg(**agg_dict)
        .reset_index()
        .rename(columns={coluna: label})
    )

    if "REGIAO" in df.columns and tipo == "loja":
        df_reg = df[["LOJA", "REGIAO"]].drop_duplicates()
        ranking = ranking.merge(
            df_reg,
            left_on="Loja",
            right_on="LOJA",
            how="left",
        ).drop("LOJA", axis=1)

    du = max(du_decorridos, 1)
    ranking["Média DU"] = ranking["Valor"] / du
    ranking["Ticket Médio"] = ranking.apply(
        lambda r: r["Valor"] / r["Qtd"] if r["Qtd"] > 0 else 0,
        axis=1,
    )

    ranking = ranking.sort_values(
        "Média DU", ascending=False,
    ).head(top_n)
    ranking.insert(0, "Posição", range(1, len(ranking) + 1))
    return ranking


def calcular_ranking_regioes(
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    du_decorridos: int = 1,
) -> Dict[str, pd.DataFrame]:
    """Todos os rankings de regioes."""
    df_v = df[df["VALOR"] > 0].copy()
    if "REGIAO" not in df_v.columns:
        return {}

    base = (
        df_v.groupby("REGIAO")
        .agg(
            Qtd=("VALOR", "count"),
            Valor=("VALOR", "sum"),
            Pontos=("pontos", "sum"),
        )
        .reset_index()
        .rename(columns={"REGIAO": "Região"})
    )

    du = max(du_decorridos, 1)
    base["Ticket Médio"] = base.apply(
        lambda r: r["Valor"] / r["Qtd"] if r["Qtd"] > 0 else 0,
        axis=1,
    )
    base["Média DU"] = base["Valor"] / du

    # Atingimento meta: somar metas das lojas por regiao
    if (
        "LOJA" in df_metas.columns
        and "META_PRATA" in df_metas.columns
        and "REGIAO" in df.columns
    ):
        loja_reg = df[["LOJA", "REGIAO"]].drop_duplicates()
        metas_reg = (
            df_metas[["LOJA", "META_PRATA"]]
            .merge(loja_reg, on="LOJA", how="left")
            .groupby("REGIAO")["META_PRATA"]
            .sum()
        )
        base["Meta Prata"] = base["Região"].map(metas_reg).fillna(0)
    else:
        base["Meta Prata"] = 0

    base["Atingimento %"] = base.apply(
        lambda r: (
            r["Pontos"] / r["Meta Prata"] * 100
            if r["Meta Prata"] > 0
            else 0
        ),
        axis=1,
    )

    def _add_pos(r):
        r = r.copy()
        r.insert(0, "Posição", range(1, len(r) + 1))
        return r

    # Por Pontos
    rk_pontos = _add_pos(
        base[["Região", "Qtd", "Valor", "Pontos", "Ticket Médio"]]
        .sort_values("Pontos", ascending=False)
    )

    # Por Ticket Médio
    rk_ticket = _add_pos(
        base[["Região", "Qtd", "Valor", "Pontos", "Ticket Médio"]]
        .sort_values("Ticket Médio", ascending=False)
    )

    # Por Média DU
    rk_media = _add_pos(
        base[
            ["Região", "Qtd", "Valor", "Pontos",
             "Ticket Médio", "Média DU"]
        ]
        .sort_values("Média DU", ascending=False)
    )

    # Por Atingimento
    rk_ating = _add_pos(
        base[
            ["Região", "Qtd", "Valor", "Pontos",
             "Meta Prata", "Atingimento %", "Ticket Médio"]
        ]
        .sort_values("Atingimento %", ascending=False)
    )

    # Por Produto
    rk_produto = {}
    grupos = df_v[
        df_v["grupo_dashboard"].notna()
    ]["grupo_dashboard"].unique()
    for grupo in sorted(grupos):
        df_g = df_v[df_v["grupo_dashboard"] == grupo]
        if df_g.empty:
            continue
        rk = (
            df_g.groupby("REGIAO")
            .agg(
                Qtd=("VALOR", "count"),
                Valor=("VALOR", "sum"),
                Pontos=("pontos", "sum"),
            )
            .reset_index()
            .rename(columns={"REGIAO": "Região"})
        )
        rk["Ticket Médio"] = rk.apply(
            lambda r: r["Valor"] / r["Qtd"] if r["Qtd"] > 0 else 0,
            axis=1,
        )
        rk["Média DU"] = rk["Valor"] / du
        rk = rk.sort_values("Pontos", ascending=False)
        rk.insert(0, "Posição", range(1, len(rk) + 1))
        rk_produto[grupo] = rk

    return {
        "pontos": rk_pontos,
        "ticket": rk_ticket,
        "media_du": rk_media,
        "atingimento": rk_ating,
        "por_produto": rk_produto,
    }


def calcular_analitico_consultores(
    df: pd.DataFrame,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Analitico de consultores por produto e loja."""
    if "CONSULTOR" not in df.columns:
        return pd.DataFrame()

    # Incluir seguros (VALOR=0) que contam apenas quantidade
    mask_producao = df["VALOR"] > 0
    if "is_bmg_med" in df.columns:
        mask_producao = mask_producao | df["is_bmg_med"]
    if "is_seguro_vida" in df.columns:
        mask_producao = mask_producao | df["is_seguro_vida"]

    df_v = _excluir_supervisores(df[mask_producao], df_supervisores)

    df_v["PRODUTO_MIX"] = df_v["grupo_dashboard"].fillna("OUTROS")
    if "is_bmg_med" in df_v.columns:
        df_v.loc[df_v["is_bmg_med"], "PRODUTO_MIX"] = "BMG Med"
    if "is_seguro_vida" in df_v.columns:
        df_v.loc[df_v["is_seguro_vida"], "PRODUTO_MIX"] = "Vida Familiar"

    analitico = (
        df_v.groupby(["CONSULTOR", "LOJA", "REGIAO", "PRODUTO_MIX"])
        .agg(
            Qtd=("VALOR", "count"),
            Valor=("VALOR", "sum"),
            Pontos=("pontos", "sum"),
        )
        .reset_index()
    )

    analitico.columns = [
        "Consultor",
        "Loja",
        "Região",
        "Produto",
        "Qtd",
        "Valor",
        "Pontos",
    ]
    analitico["Ticket Médio"] = analitico.apply(
        lambda r: r["Valor"] / r["Qtd"] if r["Qtd"] > 0 else 0,
        axis=1,
    )
    return analitico.sort_values(
        ["Consultor", "Pontos"],
        ascending=[True, False],
    )


def calcular_media_producao_regiao(
    df: pd.DataFrame,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Media de producao por consultor por regiao."""
    if "CONSULTOR" not in df.columns or "REGIAO" not in df.columns:
        return pd.DataFrame()

    df_v = _excluir_supervisores(df[df["VALOR"] > 0], df_supervisores)

    por_cons = (
        df_v.groupby(["REGIAO", "CONSULTOR"])
        .agg(
            VALOR=("VALOR", "sum"),
            pontos=("pontos", "sum"),
        )
        .reset_index()
    )

    stats = (
        por_cons.groupby("REGIAO")
        .agg(
            **{
                "Valor Médio": ("VALOR", "mean"),
                "Valor Mediano": ("VALOR", "median"),
                "Valor Desvio": ("VALOR", "std"),
                "Valor Mínimo": ("VALOR", "min"),
                "Valor Máximo": ("VALOR", "max"),
                "Pontos Médio": ("pontos", "mean"),
                "Pontos Mediano": ("pontos", "median"),
                "Pontos Desvio": ("pontos", "std"),
                "Pontos Mínimo": ("pontos", "min"),
                "Pontos Máximo": ("pontos", "max"),
                "Num Consultores": ("CONSULTOR", "count"),
            }
        )
        .reset_index()
        .rename(columns={"REGIAO": "Região"})
    )

    return stats.sort_values("Pontos Médio", ascending=False)


def calcular_distribuicao_produtos(
    df: pd.DataFrame,
    df_supervisores: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Distribuicao de produtos por consultor."""
    if "CONSULTOR" not in df.columns:
        return pd.DataFrame()

    # Incluir seguros (VALOR=0) que contam apenas quantidade
    mask_producao = df["VALOR"] > 0
    if "is_bmg_med" in df.columns:
        mask_producao = mask_producao | df["is_bmg_med"]
    if "is_seguro_vida" in df.columns:
        mask_producao = mask_producao | df["is_seguro_vida"]

    df_v = _excluir_supervisores(df[mask_producao], df_supervisores)

    df_v["PRODUTO_MIX"] = df_v["grupo_dashboard"].fillna("OUTROS")
    if "is_bmg_med" in df_v.columns:
        df_v.loc[df_v["is_bmg_med"], "PRODUTO_MIX"] = "BMG Med"
    if "is_seguro_vida" in df_v.columns:
        df_v.loc[df_v["is_seguro_vida"], "PRODUTO_MIX"] = "Vida Familiar"

    grupos = sorted(
        df_v[df_v["PRODUTO_MIX"] != "OUTROS"]["PRODUTO_MIX"].unique().tolist()
    )

    distrib = df_v.pivot_table(
        index="CONSULTOR",
        columns="PRODUTO_MIX",
        values="pontos",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()

    cols_existentes = [g for g in grupos if g in distrib.columns]
    distrib["TOTAL"] = distrib[cols_existentes].sum(axis=1)

    if "LOJA" in df.columns:
        df_info = df[["CONSULTOR", "LOJA"]].drop_duplicates()
        distrib = distrib.merge(df_info, on="CONSULTOR", how="left")

    if "REGIAO" in df.columns:
        df_reg = df[["LOJA", "REGIAO"]].drop_duplicates()
        distrib = distrib.merge(df_reg, on="LOJA", how="left")

    return distrib.sort_values("TOTAL", ascending=False)


def calcular_evolucao_diaria(
    df: pd.DataFrame,
    ano: int,
    mes: int,
) -> pd.DataFrame:
    """Evolucao diaria de vendas e pontos."""
    if "DATA" not in df.columns:
        return pd.DataFrame()

    df_t = df.copy()
    df_t["DATA_DIA"] = pd.to_datetime(df_t["DATA"]).dt.date

    evolucao = (
        df_t.groupby("DATA_DIA")
        .agg(
            VALOR=("VALOR", "sum"),
            pontos=("pontos", "sum"),
        )
        .reset_index()
        .rename(columns={"DATA_DIA": "DATA"})
    )

    evolucao["DATA"] = pd.to_datetime(evolucao["DATA"])
    evolucao = evolucao.sort_values("DATA")
    evolucao["Valor Acumulado"] = evolucao["VALOR"].cumsum()
    evolucao["Pontos Acumulados"] = evolucao["pontos"].cumsum()

    return evolucao


# ══════════════════════════════════════════════════════
# FORMATADORES
# ══════════════════════════════════════════════════════


def formatar_moeda(valor):
    """Formata valor como moeda brasileira."""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_numero(valor):
    """Formata numero com separador de milhares."""
    return f"{valor:,.0f}".replace(",", ".")


def formatar_percentual(valor):
    """Formata percentual."""
    return f"{valor:.1f}%"


# ══════════════════════════════════════════════════════
# ESTILOS
# ══════════════════════════════════════════════════════


def carregar_estilos_customizados():
    """Carrega CSS customizado do dashboard."""
    try:
        with open("assets/dashboard_style.css") as f:
            st.markdown(
                f"<style>{f.read()}</style>",
                unsafe_allow_html=True,
            )
    except FileNotFoundError:
        pass


# ══════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════


def _render_header():
    """Renderiza cabecalho estilizado."""
    st.markdown(
        """
        <div class="dashboard-header">
            <h1>Dashboard de Vendas</h1>
            <p>Analise completa de performance
            e KPIs - MGCred</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_status_bar(
    num_registros,
    ultima_data,
    filtro_regiao,
    num_em_analise=0,
):
    """Renderiza barra de status."""
    regiao_txt = (
        f" &middot; Regiao: {filtro_regiao}" if filtro_regiao != "Todas" else ""
    )
    data_str = (
        ultima_data.strftime("%d/%m/%Y")
        if hasattr(ultima_data, "strftime")
        else str(ultima_data)
    )
    analise_txt = (
        f" &middot; <strong>{num_em_analise:,}</strong> em analise"
        if num_em_analise > 0
        else ""
    )
    st.markdown(
        '<div class="status-bar fade-in">'
        '<span class="status-dot"></span>'
        f"<span><strong>{num_registros:,}</strong>"
        f" pagos{analise_txt}"
        f" &middot; Atualizado em"
        f" <strong>{data_str}</strong>"
        f"{regiao_txt}</span></div>",
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════
# KPI CARDS
# ══════════════════════════════════════════════════════


def criar_cards_kpis_principais(kpis):
    """Cria cards de KPIs principais."""
    sac.divider(
        label="Indicadores Principais",
        icon="bar-chart-line",
        align="left",
        color="blue",
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        dc = (
            "normal"
            if kpis["perc_ating_prata"] >= 100
            else "off"
            if kpis["perc_ating_prata"] >= 80
            else "inverse"
        )
        st.metric(
            "Total de Vendas",
            formatar_moeda(kpis["total_vendas"]),
            f"{formatar_percentual(kpis['perc_ating_prata'])} da meta prata",
            delta_color=dc,
        )

    with col2:
        dc = (
            "normal"
            if kpis["perc_ating_prata"] >= 100
            else "off"
            if kpis["perc_ating_prata"] >= 80
            else "inverse"
        )
        st.metric(
            "Total de Pontos",
            formatar_numero(kpis["total_pontos"]),
            f"{formatar_percentual(kpis['perc_ating_prata'])} da meta prata",
            delta_color=dc,
        )

    with col3:
        dc = (
            "normal"
            if kpis["perc_proj"] >= 100
            else "off"
            if kpis["perc_proj"] >= 90
            else "inverse"
        )
        st.metric(
            "Projecao (Pontos)",
            formatar_numero(kpis["projecao_pontos"]),
            f"{formatar_percentual(kpis['perc_proj'])} da meta prata",
            delta_color=dc,
        )

    with col4:
        st.metric(
            "Meta Prata",
            formatar_numero(kpis["meta_prata"]),
            f"{kpis['du_restantes']} DU restantes",
        )

    sac.divider(
        label="Indicadores Operacionais",
        icon="clipboard-data",
        align="left",
        color="blue",
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        dc = (
            "normal"
            if kpis["perc_ating_ouro"] >= 100
            else "off"
            if kpis["perc_ating_ouro"] >= 80
            else "inverse"
        )
        st.metric(
            "Meta Ouro",
            formatar_numero(kpis["meta_ouro"]),
            f"{formatar_percentual(kpis['perc_ating_ouro'])} atingido",
            delta_color=dc,
        )

    with col2:
        mdr = kpis["meta_diaria_restante"]
        if mdr == 0 and kpis["perc_ating_prata"] >= 100:
            st.metric(
                "Meta Diaria (Pontos)",
                "Meta atingida",
                f"Ritmo: {formatar_numero(kpis['media_du_pontos'])} pts/DU",
                delta_color="normal",
            )
        else:
            dif_pts = kpis["media_du_pontos"] - mdr
            dc = "normal" if dif_pts >= 0 else "inverse"
            st.metric(
                "Meta Diaria Restante",
                f"{formatar_numero(mdr)} pts/DU",
                f"Ritmo atual: {formatar_numero(kpis['media_du_pontos'])} pts/DU",
                delta_color=dc,
            )

    with col3:
        st.metric(
            "Ticket Medio",
            formatar_moeda(kpis["ticket_medio"]),
            f"{formatar_numero(kpis['total_transacoes'])} transacoes",
        )

    with col4:
        prod = (
            kpis["total_transacoes"] / kpis["num_consultores"]
            if kpis["num_consultores"] > 0
            else 0
        )
        st.metric(
            "Produtividade",
            f"{prod:.1f}",
            f"{formatar_numero(kpis['num_consultores'])} consultores",
        )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        pm = (
            kpis["total_pontos"] / kpis["num_consultores"]
            if kpis["num_consultores"] > 0
            else 0
        )
        st.metric(
            "Producao Media/Consultor",
            formatar_numero(pm),
            "pontos por consultor",
        )

    with col2:
        st.metric(
            "Lojas Ativas",
            formatar_numero(kpis["num_lojas"]),
            f"{formatar_numero(kpis['num_regioes'])} regioes",
        )

    with col3:
        st.metric(
            "Consultores Ativos",
            formatar_numero(kpis["num_consultores"]),
            f"Media: {pm:.0f} pts",
        )

    with col4:
        vmc = (
            kpis["total_vendas"] / kpis["num_consultores"]
            if kpis["num_consultores"] > 0
            else 0
        )
        st.metric(
            "Media/Consultor",
            formatar_moeda(vmc),
            "valor por consultor",
        )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Super Contas",
            formatar_numero(kpis.get("qtd_super_conta", 0)),
            "CNCs com subtipo Super Conta",
        )

    with col2:
        st.metric(
            "Emissao de Cartao",
            formatar_numero(kpis.get("qtd_emissao_cartao", 0)),
            "quantidade produzida",
        )

    with col3:
        st.metric(
            "BMG Med",
            formatar_numero(kpis.get("qtd_bmg_med", 0)),
            "quantidade produzida",
        )

    with col4:
        st.metric(
            "Seguro Vida Familiar",
            formatar_numero(kpis.get("qtd_seguro_vida", 0)),
            "quantidade produzida",
        )


def criar_cards_pipeline(df_analise, kpis_pagos):
    """Cria cards de KPIs do pipeline em analise."""
    sac.divider(
        label="Pipeline em Analise (ultimos 30 dias)",
        icon="hourglass-split",
        align="left",
        color="orange",
    )

    if df_analise.empty:
        st.info("Nenhum contrato em analise no periodo.")
        return

    valor_analise = df_analise["VALOR"].sum()
    qtd_analise = len(df_analise)
    ticket_analise = valor_analise / qtd_analise if qtd_analise > 0 else 0
    valor_pagos = kpis_pagos["total_vendas"]
    razao = (
        (valor_analise / valor_pagos * 100)
        if valor_pagos > 0
        else 0
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Valor em Analise",
            formatar_moeda(valor_analise),
            f"{qtd_analise} propostas",
        )
    with col2:
        st.metric(
            "Ticket Medio (Analise)",
            formatar_moeda(ticket_analise),
        )
    with col3:
        num_lojas = (
            df_analise["LOJA"].nunique()
            if "LOJA" in df_analise.columns
            else 0
        )
        st.metric(
            "Lojas com Pipeline",
            formatar_numero(num_lojas),
        )
    with col4:
        st.metric(
            "Pipeline / Produzido",
            formatar_percentual(razao),
            "do valor pago no periodo",
            delta_color="off",
        )


# ══════════════════════════════════════════════════════
# GRAFICOS
# ══════════════════════════════════════════════════════


def _template():
    """Configuracao base para graficos Plotly."""
    ct = _chart_theme()
    return {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": dict(
            family=(
                "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
            ),
            size=12,
            color=ct["text"],
        ),
        "title_font": dict(size=16, weight=700),
        "legend": dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=11, color=ct["text"]),
            bgcolor="rgba(0,0,0,0)",
        ),
        "margin": dict(l=60, r=30, t=60, b=50),
        "hoverlabel": dict(
            bgcolor=ct["tooltip_bg"],
            font_color=ct["tooltip_text"],
            font_size=12,
            bordercolor=ct["border"],
        ),
    }


def _aplicar(fig, t):
    """Aplica template a um grafico."""
    ct = _chart_theme()
    text_color = ct["text"]
    fig.update_layout(
        paper_bgcolor=t["paper_bgcolor"],
        plot_bgcolor=t["plot_bgcolor"],
        font=t["font"],
        legend=t["legend"],
        hoverlabel=t["hoverlabel"],
        title_font_color=text_color,
    )
    # subplot_titles criam annotations — forcar cor do texto
    for ann in fig.layout.annotations:
        ann.font.color = text_color
    fig.update_xaxes(
        gridcolor=ct["grid"],
        zerolinecolor=ct["grid_zero"],
        tickfont_color=text_color,
        title_font_color=text_color,
    )
    fig.update_yaxes(
        gridcolor=ct["grid"],
        zerolinecolor=ct["grid_zero"],
        tickfont_color=text_color,
        title_font_color=text_color,
    )
    return fig


def criar_grafico_produtos(df_produtos):
    """Grafico completo de produtos."""
    t = _template()

    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=(
            "Realizado vs Meta",
            "% Atingimento por Produto",
            "Projecao vs Meta",
            "Ticket Medio por Produto",
        ),
        specs=[
            [{"type": "bar"}, {"type": "bar"}],
            [{"type": "scatter"}, {"type": "bar"}],
        ],
        vertical_spacing=0.14,
        horizontal_spacing=0.10,
    )

    fig.add_trace(
        go.Bar(
            name="Realizado",
            x=df_produtos["Produto"],
            y=df_produtos["Valor"],
            marker_color=CHART_COLORS["primary"],
            marker_line=dict(width=0),
            text=df_produtos["Valor"].apply(formatar_moeda),
            textposition="outside",
            textfont=dict(size=10),
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Bar(
            name="Meta",
            x=df_produtos["Produto"],
            y=df_produtos["Meta"],
            marker_color=CHART_COLORS["primary_dark"],
            marker_line=dict(width=0),
            text=df_produtos["Meta"].apply(formatar_moeda),
            textposition="outside",
            textfont=dict(size=10),
        ),
        row=1,
        col=1,
    )

    cores = df_produtos["% Atingimento"].apply(
        lambda x: CHART_COLORS["success"] if x >= 100 else CHART_COLORS["danger"]
    )
    fig.add_trace(
        go.Bar(
            name="% Atingimento",
            x=df_produtos["Produto"],
            y=df_produtos["% Atingimento"],
            marker_color=cores,
            marker_line=dict(width=0),
            text=df_produtos["% Atingimento"].apply(lambda x: f"{x:.1f}%"),
            textposition="outside",
            textfont=dict(size=10),
            showlegend=False,
        ),
        row=1,
        col=2,
    )

    fig.add_hline(
        y=100,
        line_dash="dash",
        line_color=CHART_COLORS["neutral"],
        line_width=1,
        opacity=0.5,
        row=1,
        col=2,
    )

    fig.add_trace(
        go.Scatter(
            name="Projecao",
            x=df_produtos["Produto"],
            y=df_produtos["Projeção"],
            mode="lines+markers",
            marker=dict(
                size=10,
                color=CHART_COLORS["rose"],
                line=dict(width=2, color=_chart_theme()["bg"]),
            ),
            line=dict(width=3, color=CHART_COLORS["rose"]),
        ),
        row=2,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            name="Meta",
            x=df_produtos["Produto"],
            y=df_produtos["Meta"],
            mode="lines+markers",
            marker=dict(size=8, color=CHART_COLORS["primary_dark"]),
            line=dict(
                width=2,
                color=CHART_COLORS["primary_dark"],
                dash="dash",
            ),
            showlegend=False,
        ),
        row=2,
        col=1,
    )

    fig.add_trace(
        go.Bar(
            name="Ticket Medio",
            x=df_produtos["Produto"],
            y=df_produtos["Ticket Médio"],
            marker_color=CHART_COLORS["secondary"],
            marker_line=dict(width=0),
            text=df_produtos["Ticket Médio"].apply(formatar_moeda),
            textposition="outside",
            textfont=dict(size=10),
            showlegend=False,
        ),
        row=2,
        col=2,
    )

    fig.update_layout(
        height=640,
        showlegend=True,
        title_text="Analise Completa de Produtos",
        bargap=0.2,
        autosize=True,
    )
    return _aplicar(fig, t)


def criar_grafico_evolucao(df_evolucao, kpis):
    """Grafico de evolucao diaria."""
    t = _template()
    fig = make_subplots(
        rows=2,
        cols=1,
        subplot_titles=(
            "Evolucao Diaria de Vendas",
            "Evolucao Acumulada vs Meta",
        ),
        vertical_spacing=0.15,
    )

    fig.add_trace(
        go.Bar(
            name="Valor Diario",
            x=df_evolucao["DATA"],
            y=df_evolucao["VALOR"],
            marker_color=CHART_COLORS["primary"],
            marker_line=dict(width=0),
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            name="Valor Acumulado",
            x=df_evolucao["DATA"],
            y=df_evolucao["Valor Acumulado"],
            mode="lines+markers",
            marker=dict(
                size=5,
                color=CHART_COLORS["primary_dark"],
                line=dict(width=1, color=_chart_theme()["bg"]),
            ),
            line=dict(width=3, color=CHART_COLORS["primary_dark"]),
            fill="tozeroy",
            fillcolor="rgba(37, 99, 235, 0.08)",
        ),
        row=2,
        col=1,
    )

    fig.add_hline(
        y=kpis["meta_prata"],
        line_dash="dash",
        line_color=CHART_COLORS["success"],
        line_width=2,
        annotation_text="Meta Prata",
        annotation_font=dict(size=11, color=CHART_COLORS["success"]),
        row=2,
        col=1,
    )
    fig.add_hline(
        y=kpis["projecao"],
        line_dash="dot",
        line_color=CHART_COLORS["warning"],
        line_width=2,
        annotation_text="Projecao",
        annotation_font=dict(size=11, color=CHART_COLORS["warning"]),
        row=2,
        col=1,
    )

    fig.update_layout(
        height=640,
        showlegend=True,
        hovermode="x unified",
        autosize=True,
    )
    return _aplicar(fig, t)


def criar_grafico_regional(df_regioes):
    """Grafico de analise regional."""
    t = _template()
    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=(
            "Valor por Regiao",
            "% Atingimento por Regiao",
        ),
        specs=[[{"type": "bar"}, {"type": "bar"}]],
    )

    df_s = df_regioes.sort_values("Valor", ascending=False)

    fig.add_trace(
        go.Bar(
            x=df_s["Região"],
            y=df_s["Valor"],
            name="Valor",
            marker_color=CHART_COLORS["primary"],
            marker_line=dict(width=0),
            text=df_s["Valor"].apply(formatar_moeda),
            textposition="outside",
            textfont=dict(size=10),
        ),
        row=1,
        col=1,
    )

    cores = df_s["% Atingimento"].apply(
        lambda x: CHART_COLORS["success"] if x >= 100 else CHART_COLORS["danger"]
    )
    fig.add_trace(
        go.Bar(
            x=df_s["Região"],
            y=df_s["% Atingimento"],
            name="% Atingimento",
            marker_color=cores,
            marker_line=dict(width=0),
            text=df_s["% Atingimento"].apply(lambda x: f"{x:.1f}%"),
            textposition="outside",
            textfont=dict(size=10),
        ),
        row=1,
        col=2,
    )

    fig.update_layout(
        height=460,
        showlegend=False,
        title_text="Analise por Regiao",
        bargap=0.25,
        autosize=True,
    )
    return _aplicar(fig, t)


def criar_grafico_media_regiao(df_media):
    """Grafico de media de pontos por regiao."""
    t = _template()
    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=df_media["Região"],
            y=df_media["Pontos Médio"],
            name="Pontos Medio",
            marker_color=CHART_COLORS["secondary"],
            marker_line=dict(width=0),
            text=df_media["Pontos Médio"].apply(formatar_numero),
            textposition="outside",
            textfont=dict(size=11),
        )
    )

    fig.update_layout(
        title="Media de Pontos por Consultor por Regiao",
        xaxis_title="Regiao",
        yaxis_title="Pontos Medio",
        height=400,
        bargap=0.3,
        autosize=True,
    )
    return _aplicar(fig, t)


# ══════════════════════════════════════════════════════
# TAB RENDERERS
# ══════════════════════════════════════════════════════


def _render_tab_produtos(
    df,
    df_metas_produto,
    categorias,
    ano,
    mes,
    dia_atual,
    df_sup,
):
    """Renderiza aba de Produtos."""
    sac.divider(
        label="Analise de Produtos",
        icon="box",
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

    # ── Cards de meta diaria por produto ────────
    if not df_prod.empty and "Meta Diária Restante" in df_prod.columns:
        sac.divider(
            label="Meta Diaria Restante por Produto",
            icon="calendar-check",
            align="left",
            color="gray",
        )

        prods = df_prod[df_prod["Meta"] > 0]
        if not prods.empty:
            cols = st.columns(len(prods))
            for col, (_, row) in zip(cols, prods.iterrows()):
                with col:
                    mdr = row["Meta Diária Restante"]
                    atingiu = (
                        mdr == 0 and row["% Atingimento"] >= 100
                    )
                    if atingiu:
                        st.metric(
                            row["Produto"],
                            "Meta atingida",
                            f"Ritmo: {formatar_moeda(row['Média DU'])}/DU",
                            delta_color="normal",
                        )
                    else:
                        dif = row["Média DU"] - mdr
                        dc = "normal" if dif >= 0 else "inverse"
                        st.metric(
                            row["Produto"],
                            formatar_moeda(mdr) + "/DU",
                            f"Ritmo: {formatar_moeda(row['Média DU'])}/DU",
                            delta_color=dc,
                        )

            # Resumo geral de produtos
            mdr_total = prods["Meta Diária Restante"].sum()
            media_du_total = prods["Média DU"].sum()
            todas_atingidas = (
                mdr_total == 0
                and (prods["% Atingimento"] >= 100).all()
            )

            col_geral, col_gap, col_ritmo = st.columns([2, 1, 2])
            with col_geral:
                if todas_atingidas:
                    st.metric(
                        "Meta Diaria Geral (Produtos)",
                        "Todas atingidas",
                        f"Ritmo: {formatar_moeda(media_du_total)}/DU",
                        delta_color="normal",
                    )
                else:
                    dif_total = media_du_total - mdr_total
                    dc_total = (
                        "normal" if dif_total >= 0 else "inverse"
                    )
                    st.metric(
                        "Meta Diaria Restante (Geral)",
                        formatar_moeda(mdr_total) + "/DU",
                        f"Ritmo: {formatar_moeda(media_du_total)}/DU",
                        delta_color=dc_total,
                    )
            with col_ritmo:
                if todas_atingidas:
                    st.metric(
                        "Folga Diaria",
                        formatar_moeda(media_du_total),
                        "meta ja atingida",
                        delta_color="normal",
                    )
                else:
                    gap = mdr_total - media_du_total
                    if gap > 0:
                        st.metric(
                            "Gap Diario",
                            formatar_moeda(gap),
                            "abaixo do necessario",
                            delta_color="inverse",
                        )
                    else:
                        st.metric(
                            "Folga Diaria",
                            formatar_moeda(abs(gap)),
                            "acima do necessario",
                            delta_color="normal",
                        )

    fig = criar_grafico_produtos(df_prod)
    st.plotly_chart(fig, width="stretch")

    sac.divider(
        label="KPIs por Produto",
        icon="table",
        align="left",
        color="gray",
    )
    exibir_tabela(df_prod)
    st.info("PACK = FGTS + ANT. BEN. + CNC 13o")


def _render_tab_regioes(
    df,
    df_metas,
    ano,
    mes,
    dia_atual,
    df_sup,
):
    """Renderiza aba de Regioes."""
    sac.divider(
        label="Analise por Regiao",
        icon="geo-alt",
        align="left",
        color="blue",
    )

    df_reg = calcular_kpis_por_regiao(
        df,
        df_metas,
        ano,
        mes,
        dia_atual,
        df_sup,
    )

    if not df_reg.empty:
        fig = criar_grafico_regional(df_reg)
        st.plotly_chart(fig, width="stretch")

        sac.divider(
            label="KPIs por Regiao",
            icon="table",
            align="left",
            color="gray",
        )
        exibir_tabela(df_reg)
    else:
        st.warning("Dados regionais nao disponiveis")


def _render_tab_rankings(df, df_metas, df_sup, du_decorridos):
    """Renderiza aba de Rankings."""
    sac.divider(
        label="Rankings de Performance",
        icon="trophy",
        align="left",
        color="blue",
    )

    menu = sac.tabs(
        items=[
            sac.TabsItem(label="Lojas", icon="shop"),
            sac.TabsItem(label="Consultores", icon="people"),
            sac.TabsItem(label="Regioes", icon="geo-alt"),
            sac.TabsItem(label="Por Produto", icon="box-seam"),
        ],
        align="start",
        variant="outline",
    )

    if menu == "Lojas":
        col1, col2 = st.columns(2)
        with col1:
            sac.divider(
                label="Top 10 por Atingimento",
                icon="graph-up-arrow",
                align="left",
                color="green",
            )
            rl = calcular_ranking_lojas(df, df_metas, top_n=10)
            if not rl.empty:
                exibir_tabela(rl)
            else:
                st.warning("Dados nao disponiveis")

        with col2:
            sac.divider(
                label="Top 10 por Pontos",
                icon="star",
                align="left",
                color="blue",
            )
            rp = calcular_ranking_pontos(
                df, tipo="loja", top_n=10,
            )
            if not rp.empty:
                exibir_tabela(rp)
            else:
                st.warning("Dados nao disponiveis")

        col3, col4 = st.columns(2)
        with col3:
            sac.divider(
                label="Top 10 por Ticket Medio",
                icon="cash-coin",
                align="left",
                color="orange",
            )
            rt = calcular_ranking_ticket_medio(
                df, tipo="loja", top_n=10,
            )
            if not rt.empty:
                exibir_tabela(rt)
            else:
                st.warning("Dados nao disponiveis")

        with col4:
            sac.divider(
                label="Top 10 por Media DU",
                icon="calendar-check",
                align="left",
                color="violet",
            )
            rm = calcular_ranking_media_du(
                df, tipo="loja", top_n=10,
                du_decorridos=du_decorridos,
            )
            if not rm.empty:
                exibir_tabela(rm)
            else:
                st.warning("Dados nao disponiveis")

    elif menu == "Consultores":
        col1, col2 = st.columns(2)
        with col1:
            sac.divider(
                label="Top 10 por Atingimento",
                icon="graph-up-arrow",
                align="left",
                color="green",
            )
            rc = calcular_ranking_consultores(
                df,
                df_metas,
                top_n=10,
                df_supervisores=df_sup,
            )
            if not rc.empty:
                exibir_tabela(rc)
            else:
                st.warning("Dados nao disponiveis")

        with col2:
            sac.divider(
                label="Top 10 por Pontos",
                icon="star",
                align="left",
                color="blue",
            )
            rp = calcular_ranking_pontos(
                df, tipo="consultor", top_n=10,
                df_supervisores=df_sup,
            )
            if not rp.empty:
                exibir_tabela(rp)
            else:
                st.warning("Dados nao disponiveis")

        col3, col4 = st.columns(2)
        with col3:
            sac.divider(
                label="Top 10 por Ticket Medio",
                icon="cash-coin",
                align="left",
                color="orange",
            )
            rt = calcular_ranking_ticket_medio(
                df,
                tipo="consultor",
                top_n=10,
                df_supervisores=df_sup,
            )
            if not rt.empty:
                exibir_tabela(rt)
            else:
                st.warning("Dados nao disponiveis")

        with col4:
            sac.divider(
                label="Top 10 por Media DU",
                icon="calendar-check",
                align="left",
                color="violet",
            )
            rm = calcular_ranking_media_du(
                df, tipo="consultor", top_n=10,
                du_decorridos=du_decorridos,
                df_supervisores=df_sup,
            )
            if not rm.empty:
                exibir_tabela(rm)
            else:
                st.warning("Dados nao disponiveis")

    elif menu == "Regioes":
        rk_regioes = calcular_ranking_regioes(
            df, df_metas, du_decorridos=du_decorridos,
        )
        if not rk_regioes:
            st.warning("Dados nao disponiveis")
        else:
            col1, col2 = st.columns(2)
            with col1:
                sac.divider(
                    label="Por Atingimento Meta",
                    icon="graph-up-arrow",
                    align="left",
                    color="green",
                )
                exibir_tabela(rk_regioes["atingimento"])

            with col2:
                sac.divider(
                    label="Por Pontos",
                    icon="star",
                    align="left",
                    color="blue",
                )
                exibir_tabela(rk_regioes["pontos"])

            col3, col4 = st.columns(2)
            with col3:
                sac.divider(
                    label="Por Ticket Medio",
                    icon="cash-coin",
                    align="left",
                    color="orange",
                )
                exibir_tabela(rk_regioes["ticket"])

            with col4:
                sac.divider(
                    label="Por Media DU",
                    icon="calendar-check",
                    align="left",
                    color="violet",
                )
                exibir_tabela(rk_regioes["media_du"])

            # Por Produto
            rk_prod = rk_regioes.get("por_produto", {})
            if rk_prod:
                sac.divider(
                    label="Regioes por Produto",
                    icon="box-seam",
                    align="left",
                    color="gray",
                )
                for prod, rk in rk_prod.items():
                    if not rk.empty:
                        with st.expander(prod, expanded=False):
                            exibir_tabela(rk)

    elif menu == "Por Produto":
        tipo_sel = sac.segmented(
            items=[
                sac.SegmentedItem(label="Lojas", icon="shop"),
                sac.SegmentedItem(
                    label="Consultores", icon="people",
                ),
            ],
            align="start",
            use_container_width=False,
        )
        tipo = "loja" if tipo_sel == "Lojas" else "consultor"
        rankings = calcular_ranking_por_produto(
            df,
            tipo=tipo,
            top_n=10,
            df_supervisores=df_sup,
        )
        if rankings:
            for prod, rk in rankings.items():
                if not rk.empty:
                    with st.expander(prod, expanded=False):
                        exibir_tabela(rk)
        else:
            st.warning("Dados nao disponiveis")


def _exportar_csv(df: pd.DataFrame, nome: str, key: str):
    """Botao de download CSV para uma tabela."""
    csv = df.to_csv(index=False, sep=";", decimal=",")
    st.download_button(
        label=f"Exportar {nome}",
        data=csv,
        file_name=f"{nome}.csv",
        mime="text/csv",
        key=key,
        icon=":material/download:",
    )


def _render_detalhamento_pagos(df, df_sup):
    """Sub-aba: detalhamento de contratos pagos."""
    if df.empty:
        st.warning("Nenhum contrato pago no periodo.")
        return

    st.markdown(f"**{len(df):,} contratos pagos**".replace(",", "."))

    # Filtros
    col1, col2, col3 = st.columns(3)
    with col1:
        lojas = ["Todas"] + sorted(df["LOJA"].unique().tolist())
        filt_loja = st.selectbox("Loja", lojas, key="det_pago_loja")
    with col2:
        consultores = ["Todos"] + sorted(
            df["CONSULTOR"].unique().tolist()
        )
        filt_cons = st.selectbox(
            "Consultor", consultores, key="det_pago_cons"
        )
    with col3:
        produtos = ["Todos"]
        if "grupo_dashboard" in df.columns:
            produtos += sorted(
                [
                    str(x) for x in df["grupo_dashboard"].unique()
                    if pd.notna(x)
                ]
            )
        filt_prod = st.selectbox(
            "Produto", produtos, key="det_pago_prod"
        )

    df_d = df.copy()
    if filt_loja != "Todas":
        df_d = df_d[df_d["LOJA"] == filt_loja]
    if filt_cons != "Todos":
        df_d = df_d[df_d["CONSULTOR"] == filt_cons]
    if filt_prod != "Todos" and "grupo_dashboard" in df_d.columns:
        df_d = df_d[df_d["grupo_dashboard"] == filt_prod]

    # KPIs
    total_valor = df_d["VALOR"].sum()
    total_pts = df_d["pontos"].sum() if "pontos" in df_d.columns else 0
    total_trans = len(df_d[df_d["VALOR"] > 0])
    tk = total_valor / total_trans if total_trans > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total de Valor", formatar_moeda(total_valor))
    with col2:
        st.metric("Total de Pontos", formatar_numero(total_pts))
    with col3:
        st.metric("Ticket Medio", formatar_moeda(tk))
    with col4:
        st.metric("Quantidade", formatar_numero(len(df_d)))

    # Tabela detalhada
    cols = ["CONTRATO_ID", "DATA", "LOJA", "CONSULTOR"]
    if "REGIAO" in df_d.columns:
        cols.append("REGIAO")
    cols += ["TIPO_PRODUTO", "TIPO OPER.", "VALOR"]
    if "pontos" in df_d.columns:
        cols.append("pontos")
    cols.append("BANCO")

    cols_disp = [c for c in cols if c in df_d.columns]
    df_tabela = (
        df_d[cols_disp]
        .sort_values("DATA", ascending=False)
        .rename(columns={
            "CONTRATO_ID": "Nº Proposta",
            "DATA": "Data Pagamento",
            "TIPO_PRODUTO": "Produto",
            "TIPO OPER.": "Tipo Operacao",
            "VALOR": "Valor",
            "pontos": "Pontos",
            "BANCO": "Banco",
            "LOJA": "Loja",
            "CONSULTOR": "Consultor",
            "REGIAO": "Regiao",
        })
    )
    exibir_tabela(
        df_tabela,
        colunas_moeda=["Valor"],
        colunas_numero=["Pontos"],
    )
    _exportar_csv(df_tabela, "contratos_pagos", "exp_pagos")


def _render_detalhamento_em_analise(df_analise):
    """Sub-aba: detalhamento de contratos em analise."""
    if df_analise.empty:
        st.warning("Nenhum contrato em analise no periodo.")
        return

    st.markdown(
        f"**{len(df_analise):,} contratos em analise**"
        .replace(",", ".")
    )

    # Filtros
    col1, col2, col3 = st.columns(3)
    with col1:
        lojas = ["Todas"] + sorted(
            df_analise["LOJA"].unique().tolist()
        )
        filt_loja = st.selectbox(
            "Loja", lojas, key="det_analise_loja"
        )
    with col2:
        consultores = ["Todos"] + sorted(
            df_analise["CONSULTOR"].unique().tolist()
        )
        filt_cons = st.selectbox(
            "Consultor", consultores, key="det_analise_cons"
        )
    with col3:
        produtos = ["Todos"]
        if "grupo_dashboard" in df_analise.columns:
            produtos += sorted(
                [
                    str(x)
                    for x in df_analise["grupo_dashboard"].unique()
                    if pd.notna(x)
                ]
            )
        filt_prod = st.selectbox(
            "Produto", produtos, key="det_analise_prod"
        )

    df_d = df_analise.copy()
    if filt_loja != "Todas":
        df_d = df_d[df_d["LOJA"] == filt_loja]
    if filt_cons != "Todos":
        df_d = df_d[df_d["CONSULTOR"] == filt_cons]
    if filt_prod != "Todos" and "grupo_dashboard" in df_d.columns:
        df_d = df_d[df_d["grupo_dashboard"] == filt_prod]

    # KPIs
    total_valor = df_d["VALOR"].sum()
    total_trans = len(df_d)
    tk = total_valor / total_trans if total_trans > 0 else 0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Valor Total", formatar_moeda(total_valor))
    with col2:
        st.metric("Ticket Medio", formatar_moeda(tk))
    with col3:
        st.metric("Quantidade", formatar_numero(total_trans))

    # Tabela detalhada
    cols = ["CONTRATO_ID", "DATA_CADASTRO", "LOJA", "CONSULTOR"]
    if "REGIAO" in df_d.columns:
        cols.append("REGIAO")
    cols += [
        "TIPO_PRODUTO", "TIPO OPER.", "VALOR",
        "STATUS_BANCO", "BANCO",
    ]

    cols_disp = [c for c in cols if c in df_d.columns]
    df_tabela = (
        df_d[cols_disp]
        .sort_values("DATA_CADASTRO", ascending=False)
        .rename(columns={
            "CONTRATO_ID": "Nº Proposta",
            "DATA_CADASTRO": "Data Cadastro",
            "TIPO_PRODUTO": "Produto",
            "TIPO OPER.": "Tipo Operacao",
            "VALOR": "Valor",
            "STATUS_BANCO": "Status Banco",
            "BANCO": "Banco",
            "LOJA": "Loja",
            "CONSULTOR": "Consultor",
            "REGIAO": "Regiao",
        })
    )
    exibir_tabela(df_tabela, colunas_moeda=["Valor"])
    _exportar_csv(
        df_tabela, "contratos_em_analise", "exp_analise"
    )


def _render_detalhamento_cancelados(df_cancel):
    """Sub-aba: detalhamento de contratos cancelados."""
    if df_cancel.empty:
        st.warning("Nenhum contrato cancelado no periodo.")
        return

    st.markdown(
        f"**{len(df_cancel):,} contratos cancelados**"
        .replace(",", ".")
    )

    # Filtros
    col1, col2, col3 = st.columns(3)
    with col1:
        lojas = ["Todas"] + sorted(
            df_cancel["LOJA"].unique().tolist()
        )
        filt_loja = st.selectbox(
            "Loja", lojas, key="det_cancel_loja"
        )
    with col2:
        consultores = ["Todos"] + sorted(
            df_cancel["CONSULTOR"].unique().tolist()
        )
        filt_cons = st.selectbox(
            "Consultor", consultores, key="det_cancel_cons"
        )
    with col3:
        produtos = ["Todos"]
        if "grupo_dashboard" in df_cancel.columns:
            produtos += sorted(
                [
                    str(x)
                    for x in df_cancel["grupo_dashboard"].unique()
                    if pd.notna(x)
                ]
            )
        filt_prod = st.selectbox(
            "Produto", produtos, key="det_cancel_prod"
        )

    df_d = df_cancel.copy()
    if filt_loja != "Todas":
        df_d = df_d[df_d["LOJA"] == filt_loja]
    if filt_cons != "Todos":
        df_d = df_d[df_d["CONSULTOR"] == filt_cons]
    if filt_prod != "Todos" and "grupo_dashboard" in df_d.columns:
        df_d = df_d[df_d["grupo_dashboard"] == filt_prod]

    # KPIs
    total_valor = df_d["VALOR"].sum()
    total_trans = len(df_d)
    tk = total_valor / total_trans if total_trans > 0 else 0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Valor Total", formatar_moeda(total_valor))
    with col2:
        st.metric("Ticket Medio", formatar_moeda(tk))
    with col3:
        st.metric("Quantidade", formatar_numero(total_trans))

    # Tabela detalhada
    cols = ["CONTRATO_ID", "DATA_CADASTRO", "LOJA", "CONSULTOR"]
    if "REGIAO" in df_d.columns:
        cols.append("REGIAO")
    cols += [
        "TIPO_PRODUTO", "TIPO OPER.", "VALOR",
        "SUB_STATUS", "STATUS_PAG", "BANCO",
    ]

    cols_disp = [c for c in cols if c in df_d.columns]
    df_tabela = (
        df_d[cols_disp]
        .sort_values("DATA_CADASTRO", ascending=False)
        .rename(columns={
            "CONTRATO_ID": "Nº Proposta",
            "DATA_CADASTRO": "Data Cadastro",
            "TIPO_PRODUTO": "Produto",
            "TIPO OPER.": "Tipo Operacao",
            "VALOR": "Valor",
            "SUB_STATUS": "Sub-Status",
            "STATUS_PAG": "Status Pagamento",
            "BANCO": "Banco",
            "LOJA": "Loja",
            "CONSULTOR": "Consultor",
            "REGIAO": "Regiao",
        })
    )
    exibir_tabela(df_tabela, colunas_moeda=["Valor"])
    _exportar_csv(
        df_tabela, "contratos_cancelados", "exp_cancel"
    )


def _render_tab_analiticos(
    df, df_sup, df_analise, df_cancelados,
):
    """Renderiza aba de Analiticos."""
    sac.divider(
        label="Analiticos Detalhados",
        icon="graph-up",
        align="left",
        color="blue",
    )

    menu = sac.tabs(
        items=[
            sac.TabsItem(
                label="Propostas Pagas",
                icon="check-circle",
            ),
            sac.TabsItem(
                label="Em Analise",
                icon="hourglass-split",
            ),
            sac.TabsItem(
                label="Cancelados",
                icon="x-circle",
            ),
            sac.TabsItem(
                label="Consultores por Produto",
                icon="people",
            ),
            sac.TabsItem(
                label="Producao por Regiao",
                icon="geo-alt",
            ),
            sac.TabsItem(
                label="Distribuicao de Produtos",
                icon="pie-chart",
            ),
        ],
        align="start",
        variant="outline",
    )

    if menu == "Propostas Pagas":
        _render_detalhamento_pagos(df, df_sup)

    elif menu == "Em Analise":
        _render_detalhamento_em_analise(df_analise)

    elif menu == "Cancelados":
        _render_detalhamento_cancelados(df_cancelados)

    elif menu == "Consultores por Produto":
        df_a = calcular_analitico_consultores(df, df_sup)
        if not df_a.empty:
            st.info(f"Total de {df_a['Consultor'].nunique()} consultores analisados")

            col1, col2 = st.columns(2)
            with col1:
                opts_c = ["Todos"] + sorted(df_a["Consultor"].unique().tolist())
                filt_c = st.selectbox("Filtrar por Consultor", opts_c)
            with col2:
                opts_p = ["Todos"] + sorted(df_a["Produto"].unique().tolist())
                filt_p = st.selectbox("Filtrar por Produto", opts_p)

            df_af = df_a.copy()
            if filt_c != "Todos":
                df_af = df_af[df_af["Consultor"] == filt_c]
            if filt_p != "Todos":
                df_af = df_af[df_af["Produto"] == filt_p]

            exibir_tabela(df_af)
            _exportar_csv(
                df_af, "consultores_por_produto",
                "exp_cons_prod",
            )

            # Cards resumo: usar df original (mesma base dos KPIs
            # principais) para manter consistencia, aplicando apenas
            # os filtros de consultor/produto selecionados pelo usuario
            mask_cards = df["VALOR"] > 0
            if "is_bmg_med" in df.columns:
                mask_cards = mask_cards | df["is_bmg_med"]
            if "is_seguro_vida" in df.columns:
                mask_cards = mask_cards | df["is_seguro_vida"]
            df_cards = df[mask_cards].copy()
            df_cards["PRODUTO_MIX"] = df_cards[
                "grupo_dashboard"
            ].fillna("OUTROS")
            if "is_bmg_med" in df_cards.columns:
                df_cards.loc[
                    df_cards["is_bmg_med"], "PRODUTO_MIX"
                ] = "BMG Med"
            if "is_seguro_vida" in df_cards.columns:
                df_cards.loc[
                    df_cards["is_seguro_vida"], "PRODUTO_MIX"
                ] = "Vida Familiar"
            if filt_c != "Todos":
                df_cards = df_cards[df_cards["CONSULTOR"] == filt_c]
            if filt_p != "Todos":
                df_cards = df_cards[df_cards["PRODUTO_MIX"] == filt_p]

            total_valor = df_cards["VALOR"].sum()
            total_pts = df_cards["pontos"].sum()
            total_trans = len(df_cards[df_cards["VALOR"] > 0])
            tk_medio = (
                total_valor / total_trans if total_trans > 0 else 0
            )

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(
                    "Total de Pontos",
                    formatar_numero(total_pts),
                )
            with col2:
                st.metric(
                    "Total de Valor",
                    formatar_moeda(total_valor),
                )
            with col3:
                st.metric(
                    "Ticket Medio Geral",
                    formatar_moeda(tk_medio),
                )
        else:
            st.warning("Dados nao disponiveis")

    elif menu == "Producao por Regiao":
        df_mr = calcular_media_producao_regiao(df, df_sup)
        if not df_mr.empty:
            st.info("Comparativo de produtividade media entre regioes")
            fig = criar_grafico_media_regiao(df_mr)
            st.plotly_chart(fig, width="stretch")
            sac.divider(
                label="Estatisticas Detalhadas",
                icon="table",
                align="left",
                color="gray",
            )
            df_d = df_mr.drop(
                ["Valor Desvio", "Pontos Desvio"],
                axis=1,
            )
            exibir_tabela(df_d)
            _exportar_csv(
                df_d, "producao_por_regiao", "exp_prod_reg"
            )
        else:
            st.warning("Dados nao disponiveis")

    elif menu == "Distribuicao de Produtos":
        df_dist = calcular_distribuicao_produtos(df, df_sup)
        if not df_dist.empty:
            st.info("Visualizacao da distribuicao de produtos por consultor")
            top_n = st.slider(
                "Exibir top N consultores",
                min_value=5,
                max_value=50,
                value=20,
                step=5,
            )
            exibir_tabela(df_dist.head(top_n))
            _exportar_csv(
                df_dist, "distribuicao_produtos",
                "exp_dist_prod",
            )
        else:
            st.warning("Dados nao disponiveis")


def _render_tab_evolucao(df, ano, mes, kpis):
    """Renderiza aba de Evolucao."""
    sac.divider(
        label="Evolucao Temporal",
        icon="graph-down",
        align="left",
        color="blue",
    )

    df_ev = calcular_evolucao_diaria(df, ano, mes)

    if not df_ev.empty:
        fig = criar_grafico_evolucao(df_ev, kpis)
        st.plotly_chart(fig, width="stretch")

        col1, col2, col3 = st.columns(3)
        with col1:
            best = df_ev.loc[df_ev["VALOR"].idxmax()]
            st.metric(
                "Melhor Dia",
                best["DATA"].strftime("%d/%m"),
                formatar_moeda(best["VALOR"]),
            )
        with col2:
            media = df_ev["VALOR"].mean()
            st.metric(
                "Media Diaria",
                formatar_moeda(media),
                f"{len(df_ev)} dias com vendas",
            )
        with col3:
            acima = (df_ev["VALOR"] >= kpis["meta_diaria"]).sum()
            perc = acima / len(df_ev) * 100 if len(df_ev) > 0 else 0
            st.metric(
                "Dias Acima da Meta",
                f"{acima}",
                f"{perc:.1f}% dos dias",
            )
    else:
        st.warning("Dados de evolucao nao disponiveis")


def _render_tab_em_analise(df_analise, df_sup):
    """Renderiza aba de contratos Em Analise."""
    sac.divider(
        label="Contratos em Analise",
        icon="hourglass-split",
        align="left",
        color="orange",
    )

    if df_analise.empty:
        st.warning("Nenhum contrato em analise no periodo.")
        return

    df_a = df_analise.copy()
    if df_sup is not None and "SUPERVISOR" in df_sup.columns:
        supervisores = df_sup["SUPERVISOR"].unique()
    else:
        supervisores = []

    # ── Filtros ────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        lojas = ["Todas"] + sorted(df_a["LOJA"].unique().tolist())
        filt_loja = st.selectbox("Loja", lojas, key="analise_loja")
    with col2:
        if "REGIAO" in df_a.columns:
            regioes = ["Todas"] + sorted(df_a["REGIAO"].unique().tolist())
            filt_reg = st.selectbox(
                "Regiao", regioes, key="analise_regiao"
            )
        else:
            filt_reg = "Todas"
    with col3:
        status_opts = ["Todos"] + sorted(
            [str(x) for x in df_a["STATUS_BANCO"].unique() if pd.notna(x)]
        )
        filt_status = st.selectbox(
            "Status Banco", status_opts, key="analise_status"
        )

    if filt_loja != "Todas":
        df_a = df_a[df_a["LOJA"] == filt_loja]
    if filt_reg != "Todas" and "REGIAO" in df_a.columns:
        df_a = df_a[df_a["REGIAO"] == filt_reg]
    if filt_status != "Todos":
        df_a = df_a[df_a["STATUS_BANCO"] == filt_status]

    qtd_emissao_analise = (
        (df_a["TIPO OPER."].isin(["CARTÃO BENEFICIO", "Venda Pré-Adesão"])).sum()
        if "TIPO OPER." in df_a.columns
        else 0
    )
    qtd_sem_emissao = len(df_a) - qtd_emissao_analise

    st.markdown(f"**{len(df_a):,} propostas em analise**")

    # ── KPIs resumo ───────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Valor Total", formatar_moeda(df_a["VALOR"].sum()))
    with col2:
        st.metric(
            "Quantidade",
            formatar_numero(len(df_a)),
            f"{formatar_numero(qtd_sem_emissao)} operacoes"
            f" + {formatar_numero(qtd_emissao_analise)} emissoes",
        )
    with col3:
        tk = df_a["VALOR"].sum() / len(df_a) if len(df_a) > 0 else 0
        st.metric("Ticket Medio", formatar_moeda(tk))
    with col4:
        cons = df_a["CONSULTOR"].unique()
        cons_sem_sup = [c for c in cons if c not in supervisores]
        st.metric("Consultores", formatar_numero(len(cons_sem_sup)))

    # ── Breakdown por produto ─────────────────────
    sac.divider(
        label="Por Produto",
        icon="box-seam",
        align="left",
        color="gray",
    )

    if "grupo_dashboard" in df_a.columns:
        df_prod = (
            df_a[df_a["grupo_dashboard"].notna()]
            .groupby("grupo_dashboard")
            .agg(
                Qtd=("VALOR", "count"),
                Valor=("VALOR", "sum"),
            )
            .reset_index()
            .rename(columns={"grupo_dashboard": "Produto"})
            .sort_values("Valor", ascending=False)
        )
        df_prod["Ticket Medio"] = df_prod.apply(
            lambda r: r["Valor"] / r["Qtd"] if r["Qtd"] > 0 else 0,
            axis=1,
        )
        exibir_tabela(df_prod, colunas_moeda=["Valor", "Ticket Medio"])

    # ── Breakdown por loja ────────────────────────
    sac.divider(
        label="Por Loja",
        icon="shop",
        align="left",
        color="gray",
    )

    df_loja = (
        df_a.groupby("LOJA")
        .agg(
            Qtd=("VALOR", "count"),
            Valor=("VALOR", "sum"),
        )
        .reset_index()
        .rename(columns={"LOJA": "Loja"})
        .sort_values("Valor", ascending=False)
    )
    df_loja["Ticket Medio"] = df_loja.apply(
        lambda r: r["Valor"] / r["Qtd"] if r["Qtd"] > 0 else 0,
        axis=1,
    )
    exibir_tabela(df_loja, colunas_moeda=["Valor", "Ticket Medio"])

    # ── Tabela detalhada ──────────────────────────
    sac.divider(
        label="Detalhamento",
        icon="table",
        align="left",
        color="gray",
    )

    cols = [
        "DATA_CADASTRO",
        "LOJA",
        "CONSULTOR",
        "TIPO_PRODUTO",
        "VALOR",
        "STATUS_BANCO",
        "BANCO",
    ]
    if "REGIAO" in df_a.columns:
        cols.insert(2, "REGIAO")

    exibir_tabela(
        df_a[cols].sort_values("DATA_CADASTRO", ascending=False),
        colunas_moeda=["VALOR"],
    )


def _render_tab_detalhes(df):
    """Renderiza aba de Detalhes."""
    sac.divider(
        label="Dados Detalhados",
        icon="clipboard-data",
        align="left",
        color="blue",
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        lojas = ["Todas"] + sorted(df["LOJA"].unique().tolist())
        filt_loja = st.selectbox("Loja", lojas)

    with col2:
        if "REGIAO" in df.columns:
            regioes = ["Todas"] + sorted(df["REGIAO"].unique().tolist())
            filt_reg = st.selectbox("Regiao (detalhe)", regioes)
        else:
            filt_reg = "Todas"

    with col3:
        prods = ["Todos"] + sorted(
            [str(x) for x in df["TIPO_PRODUTO"].unique() if pd.notna(x)]
        )
        filt_prod = st.selectbox("Produto", prods)

    df_d = df.copy()
    if filt_loja != "Todas":
        df_d = df_d[df_d["LOJA"] == filt_loja]
    if filt_reg != "Todas" and "REGIAO" in df.columns:
        df_d = df_d[df_d["REGIAO"] == filt_reg]
    if filt_prod != "Todos":
        df_d = df_d[df_d["TIPO_PRODUTO"] == filt_prod]

    st.markdown(f"**{len(df_d):,} registros encontrados**")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            "Total Valor",
            formatar_moeda(df_d["VALOR"].sum()),
        )
    with col2:
        st.metric(
            "Total Pontos",
            formatar_numero(df_d["pontos"].sum()),
        )
    with col3:
        tk = df_d["VALOR"].sum() / len(df_d) if len(df_d) > 0 else 0
        st.metric("Ticket Medio", formatar_moeda(tk))

    cols = [
        "DATA",
        "LOJA",
        "CONSULTOR",
        "TIPO_PRODUTO",
        "VALOR",
        "pontos",
    ]
    if "REGIAO" in df_d.columns:
        cols.insert(2, "REGIAO")

    exibir_tabela(
        df_d[cols],
        colunas_moeda=["VALOR"],
        colunas_numero=["pontos"],
    )


# ══════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════


def _render_sidebar_usuario():
    """Informacoes do usuario e logout."""
    user = usuario_logado()
    if not user:
        return

    sac.divider(
        label="Usuario",
        icon="person-circle",
        align="center",
        color="gray",
    )

    perfil_label = PERFIS.get(user["perfil"], user["perfil"])
    st.markdown(
        f"**{user['nome']}**  \n<small style='opacity:0.6'>{perfil_label}</small>",
        unsafe_allow_html=True,
    )

    if user["perfil"] not in ("admin", "gestor") and user.get("escopo"):
        st.caption(f"Escopo: {', '.join(user['escopo'])}")

    col_cfg, col_sair = st.columns(2)

    with col_cfg:
        icon = "⚙️"
        label = "Config"
        if user["perfil"] == "admin":
            icon = "👥"
            label = "Usuarios"
        if st.button(
            f"{icon} {label}",
            width="stretch",
        ):
            st.session_state["mostrar_config"] = not st.session_state.get(
                "mostrar_config", False
            )
            st.rerun()

    with col_sair:
        if st.button("Sair", width="stretch"):
            fazer_logout()
            st.rerun()


def _render_sidebar_visualizar_como(df):
    """Seletor 'Visualizar como' para admin."""
    user = usuario_logado()
    if not user or user["perfil"] != "admin":
        return

    sac.divider(
        label="Visualizar Como",
        icon="eye",
        align="center",
        color="gray",
    )

    opcoes = [
        "Admin (padrao)",
        "Gerente Comercial",
        "Supervisor",
    ]
    sel = st.selectbox(
        "Simular perfil",
        opcoes,
        key="sel_visualizar_perfil",
    )

    if sel == "Admin (padrao)":
        st.session_state.pop("visualizar_como", None)
    elif sel == "Gerente Comercial":
        regioes = (
            sorted(df["REGIAO"].unique().tolist()) if "REGIAO" in df.columns else []
        )
        escopo = st.multiselect(
            "Regioes",
            regioes,
            key="sel_visualizar_regioes",
        )
        if escopo:
            st.session_state["visualizar_como"] = {
                "perfil": "gerente_comercial",
                "escopo": escopo,
            }
        else:
            st.session_state.pop("visualizar_como", None)
    elif sel == "Supervisor":
        lojas = sorted(df["LOJA"].unique().tolist()) if "LOJA" in df.columns else []
        escopo = st.multiselect(
            "Lojas",
            lojas,
            key="sel_visualizar_lojas",
        )
        if escopo:
            st.session_state["visualizar_como"] = {
                "perfil": "supervisor",
                "escopo": escopo,
            }
        else:
            st.session_state.pop("visualizar_como", None)


# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════


def main():
    """Funcao principal do dashboard."""
    carregar_estilos_customizados()
    _aplicar_tema()

    # ── Autenticacao ──────────────────────────────
    if not tela_login():
        return

    _render_header()

    with st.sidebar:
        # ── Logo + toggle de tema ──
        col_logo, col_theme = st.columns([4, 1])
        with col_logo:
            logo = (
                "assets/logo-grayscale.png"
                if _get_theme() == "dark"
                else "assets/logotipo-mg-cred.png"
            )
            st.image(logo, width="stretch")
        with col_theme:
            is_dark = _get_theme() == "dark"
            icon = ":material/light_mode:" if is_dark else ":material/dark_mode:"
            if st.button(
                icon,
                key="theme_toggle",
                help="Alternar tema claro/escuro",
                width="stretch",
            ):
                new_theme = "light" if is_dark else "dark"
                st.session_state["theme"] = new_theme
                st.rerun()

        _render_sidebar_usuario()

        sac.divider(
            label="Periodo",
            icon="calendar3",
            align="center",
            color="gray",
        )

        ano = st.selectbox("Ano", [2024, 2025, 2026], index=2)
        mes = st.selectbox(
            "Mes",
            list(range(1, 13)),
            index=2,
            format_func=lambda x: {
                1: "Janeiro",
                2: "Fevereiro",
                3: "Marco",
                4: "Abril",
                5: "Maio",
                6: "Junho",
                7: "Julho",
                8: "Agosto",
                9: "Setembro",
                10: "Outubro",
                11: "Novembro",
                12: "Dezembro",
            }[x],
        )

        sac.divider(
            label="Legenda",
            icon="book",
            align="center",
            color="gray",
        )
        st.caption("**DU**: Dias Uteis")
        st.caption("**Meta Prata**: Meta principal")
        st.caption("**Meta Ouro**: Meta desafio")
        st.caption("**PACK**: FGTS + ANT. BEN. + CNC 13o")

        # ── Botao para forcar atualizacao do cache ──
        if st.button(
            ":material/refresh: Atualizar Dados",
            help=(
                "Limpa o cache e recarrega todos os dados "
                "do banco. Use quando souber que os dados "
                "foram atualizados recentemente."
            ),
            key="btn_refresh_cache",
            width="stretch",
        ):
            st.cache_data.clear()
            st.rerun()

    try:
        with st.status(
            "Carregando dados...", expanded=False
        ) as _status:
            _status.update(label="Carregando contratos pagos...")
            df, df_metas, df_sup = consolidar_dados(mes, ano)

            _status.update(label="Carregando categorias e metas...")
            categorias = carregar_categorias()
            df_metas_produto = carregar_metas_produto(mes, ano)

            _status.update(label="Carregando pipeline em analise...")
            df_analise = carregar_contratos_em_analise(mes, ano)

            # Zerar VALOR de produtos que nao contam
            # valor (emissoes de cartao, seguros)
            if (
                not df_analise.empty
                and "conta_valor" in df_analise.columns
            ):
                df_analise.loc[
                    df_analise["conta_valor"] == False,  # noqa
                    "VALOR",
                ] = 0
            # Zerar emissoes por TIPO OPER. (Venda Pre-Adesao
            # com produto CONSIG nao tem conta_valor=false)
            if (
                not df_analise.empty
                and "TIPO OPER." in df_analise.columns
            ):
                df_analise.loc[
                    df_analise["TIPO OPER."].isin(
                        ["CARTÃO BENEFICIO", "Venda Pré-Adesão"]
                    ),
                    "VALOR",
                ] = 0

            _status.update(label="Carregando cancelados...")
            df_cancelados = carregar_contratos_cancelados(
                mes, ano
            )
            if (
                not df_cancelados.empty
                and "conta_valor" in df_cancelados.columns
            ):
                df_cancelados.loc[
                    df_cancelados["conta_valor"] == False,  # noqa
                    "VALOR",
                ] = 0
            if (
                not df_cancelados.empty
                and "TIPO OPER." in df_cancelados.columns
            ):
                df_cancelados.loc[
                    df_cancelados["TIPO OPER."].isin(
                        ["CARTÃO BENEFICIO", "Venda Pré-Adesão"]
                    ),
                    "VALOR",
                ] = 0
            n_pagos = len(df)
            n_analise = len(df_analise)
            n_cancel = len(df_cancelados)
            _status.update(
                label=(
                    f"Dados carregados — "
                    f"{n_pagos:,} pagos · "
                    f"{n_analise:,} em analise · "
                    f"{n_cancel:,} cancelados"
                ).replace(",", "."),
                state="complete",
            )

        # ── Diagnostico de pontuacao ─────────────
        diag = st.session_state.get("_diag_pontuacao")
        if diag:
            with st.expander(
                f"Diagnostico de pontuacao — "
                f"{diag['com_pontos_mapeados']}/{diag['total_contratos']} "
                f"contratos com pontos",
                expanded=False,
            ):
                c1, c2, c3 = st.columns(3)
                c1.metric("Total contratos", diag["total_contratos"])
                c2.metric("Sem categoria", diag["sem_categoria"])
                c3.metric("Com pontos", diag["com_pontos_mapeados"])

                st.markdown("**Categorias nos contratos:**")
                st.code(
                    ", ".join(
                        c for c in diag["categorias_no_contrato"] if c
                    )
                    or "(vazio)",
                )

                st.markdown("**Categorias na pontuacao (RPC):**")
                st.code(
                    ", ".join(diag["categorias_na_pontuacao"]) or "(vazio)",
                )

                st.markdown("**Mapa de pontos:**")
                st.json(diag["mapa_pontos"])

                # Tipos sem categoria (não mapeados pelo fallback)
                tipos_sem_cat = diag.get("tipos_sem_categoria", [])
                if tipos_sem_cat:
                    st.warning(
                        f"**{diag['sem_categoria']} contratos sem categoria** "
                        f"— TIPO_PRODUTO nao mapeado:"
                    )
                    st.dataframe(
                        pd.DataFrame(tipos_sem_cat),
                        width="stretch",
                        hide_index=True,
                    )

                # Categorias sem match
                cats_contrato = {
                    c for c in diag["categorias_no_contrato"] if c
                }
                cats_pontuacao = set(diag["categorias_na_pontuacao"])
                sem_match = sorted(cats_contrato - cats_pontuacao)
                if sem_match:
                    st.warning(
                        f"**{len(sem_match)} categorias sem pontuacao:** "
                        + ", ".join(sem_match)
                    )

        # ── Configuracoes (toggle via sidebar) ────
        if st.session_state.get("mostrar_config"):
            if st.button("← Voltar ao Dashboard"):
                st.session_state["mostrar_config"] = False
                st.rerun()

            user = usuario_logado()
            if user and user["perfil"] == "admin":
                sac.divider(
                    label="Gerenciamento de Usuarios",
                    icon="people",
                    align="left",
                    color="blue",
                )
                regioes_cfg = (
                    sorted(df["REGIAO"].unique().tolist())
                    if not df.empty and "REGIAO" in df.columns
                    else []
                )
                lojas_cfg = (
                    sorted(df["LOJA"].unique().tolist())
                    if not df.empty and "LOJA" in df.columns
                    else []
                )
                render_pagina_usuarios(
                    regioes=regioes_cfg,
                    lojas=lojas_cfg,
                )
            else:
                sac.divider(
                    label="Minha Conta",
                    icon="person-gear",
                    align="left",
                    color="blue",
                )
                render_pagina_usuarios()
            return

        if df.empty and df_analise.empty and df_cancelados.empty:
            st.warning("Nenhum dado encontrado para o periodo selecionado.")
            return

        if df.empty:
            st.info(
                "Nenhum contrato pago no periodo. "
                "Exibindo apenas propostas em analise."
            )
            df_analise = aplicar_rls(df_analise)
            criar_cards_pipeline(df_analise, {
                "total_vendas": 0,
            })
            _render_tab_em_analise(df_analise, df_sup)
            return

        # ── RLS: filtrar dados por perfil ─────────
        df = aplicar_rls(df)
        df_metas = aplicar_rls_metas(df_metas, df)
        df_metas_produto = aplicar_rls_metas(df_metas_produto, df)
        df_sup = aplicar_rls_supervisores(df_sup, df)
        if not df_analise.empty:
            df_analise = aplicar_rls(df_analise)
        if not df_cancelados.empty:
            df_cancelados = aplicar_rls(df_cancelados)

        ultima_data = df["DATA"].max()
        dia_atual = ultima_data.day if hasattr(ultima_data, "day") else None
        _, du_decorridos, _ = calcular_dias_uteis(
            ano, mes, dia_atual,
        )

        # ── Regioes permitidas pelo RLS ───────────
        regioes_todas = ["Todas"]
        if "REGIAO" in df.columns:
            regioes_todas += sorted(df["REGIAO"].unique().tolist())
        regioes_disp = obter_regioes_permitidas(
            regioes_todas,
        )

        with st.sidebar:
            _render_sidebar_visualizar_como(df)

            if regioes_disp:
                sac.divider(
                    label="Filtros Globais",
                    icon="funnel",
                    align="center",
                    color="gray",
                )
                filtro_regiao = st.selectbox(
                    "Regiao",
                    regioes_disp,
                    help="Filtrar dados por regiao",
                )
            else:
                filtro_regiao = "Todas"

        df_f = df.copy()
        df_metas_f = df_metas.copy()
        df_metas_prod_f = df_metas_produto.copy()
        df_sup_f = df_sup.copy()
        df_analise_f = df_analise.copy()
        df_cancelados_f = df_cancelados.copy()

        if filtro_regiao != "Todas" and "REGIAO" in df.columns:
            df_f = df_f[df_f["REGIAO"] == filtro_regiao]
            lojas_r = df_f["LOJA"].unique()
            df_metas_f = df_metas_f[df_metas_f["LOJA"].isin(lojas_r)]
            if not df_metas_prod_f.empty:
                df_metas_prod_f = df_metas_prod_f[df_metas_prod_f["LOJA"].isin(lojas_r)]
            if "REGIAO" in df_sup.columns:
                df_sup_f = df_sup_f[df_sup_f["REGIAO"] == filtro_regiao]
            if not df_analise_f.empty and "REGIAO" in df_analise_f.columns:
                df_analise_f = df_analise_f[df_analise_f["REGIAO"] == filtro_regiao]
            if not df_cancelados_f.empty and "REGIAO" in df_cancelados_f.columns:
                df_cancelados_f = df_cancelados_f[df_cancelados_f["REGIAO"] == filtro_regiao]

        _render_status_bar(
            len(df_f),
            ultima_data,
            filtro_regiao,
            num_em_analise=len(df_analise_f),
        )

        # ── Aviso de pontuacao com fallback ───────
        df_pontos = carregar_pontuacao_efetiva(mes, ano)
        if not df_pontos.empty:
            fallbacks = df_pontos[
                df_pontos["is_fallback"] == True  # noqa
            ]
            if not fallbacks.empty:
                with st.expander(
                    "Info: Pontuacao usando dados de periodo anterior (fallback)",
                    expanded=False,
                ):
                    st.info(
                        "Algumas categorias estao "
                        "usando pontuacao de um "
                        "periodo anterior pois o "
                        "periodo atual nao tem dados."
                    )
                    exibir_tabela(
                        fallbacks[
                            [
                                "categoria_codigo",
                                "pontos",
                                "periodo_origem",
                            ]
                        ].rename(
                            columns={
                                "categoria_codigo": "Categoria",
                                "pontos": "Pontos",
                                "periodo_origem": "Origem",
                            }
                        )
                    )

        kpis = calcular_kpis_gerais(
            df_f,
            df_metas_f,
            ano,
            mes,
            dia_atual,
            df_sup_f,
        )
        criar_cards_kpis_principais(kpis)
        criar_cards_pipeline(df_analise_f, kpis)

        # ── Navegacao principal ───────────────────
        user = usuario_logado()
        tab_items = [
            sac.TabsItem(label="Produtos", icon="box"),
            sac.TabsItem(label="Regioes", icon="geo-alt"),
            sac.TabsItem(label="Rankings", icon="trophy"),
            sac.TabsItem(label="Analiticos", icon="graph-up"),
            sac.TabsItem(
                label="Evolucao",
                icon="calendar-range",
            ),
            sac.TabsItem(
                label="Em Analise",
                icon="hourglass-split",
            ),
            sac.TabsItem(
                label="Detalhes",
                icon="clipboard-data",
            ),
        ]

        tab = sac.tabs(
            items=tab_items,
            align="center",
            variant="outline",
        )

        if tab == "Produtos":
            _render_tab_produtos(
                df_f,
                df_metas_prod_f,
                categorias,
                ano,
                mes,
                dia_atual,
                df_sup_f,
            )
        elif tab == "Regioes":
            _render_tab_regioes(
                df_f,
                df_metas_f,
                ano,
                mes,
                dia_atual,
                df_sup_f,
            )
        elif tab == "Rankings":
            _render_tab_rankings(
                df_f,
                df_metas_f,
                df_sup_f,
                du_decorridos,
            )
        elif tab == "Analiticos":
            _render_tab_analiticos(
                df_f, df_sup_f, df_analise_f,
                df_cancelados_f,
            )
        elif tab == "Evolucao":
            _render_tab_evolucao(
                df_f,
                ano,
                mes,
                kpis,
            )
        elif tab == "Em Analise":
            _render_tab_em_analise(df_analise_f, df_sup_f)
        elif tab == "Detalhes":
            _render_tab_detalhes(df_f)

    except Exception as e:
        st.error(f"Erro inesperado: {e}")
        st.exception(e)


if __name__ == "__main__":
    main()
