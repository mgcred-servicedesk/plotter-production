"""
Sistema de tema (light/dark) e paletas de cores para
graficos Plotly.

Exporta:
  - ``CHART_COLORS`` — paleta de cores fixa para plots.
  - ``get_theme()`` — retorna o tema ativo ('light'/'dark').
  - ``chart_theme()`` — retorna paleta do tema ativo para
    uso em graficos Plotly.
  - ``aplicar_tema()`` — sincroniza tema nativo Streamlit
    + CSS custom properties + deteccao de preferencia.
  - ``carregar_estilos_customizados()`` — injeta o CSS
    design system de ``assets/dashboard_style.css``.
"""

import streamlit as st


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


# Paleta de cores para graficos (tokens semanticos)
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


def get_theme() -> str:
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


def chart_theme() -> dict:
    """Retorna paleta de cores para graficos Plotly."""
    return _CHART_THEME[get_theme()]


def aplicar_tema() -> None:
    """Sincroniza tema nativo Streamlit + CSS custom properties."""
    from streamlit.config import set_option

    theme = get_theme()
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


def carregar_estilos_customizados() -> None:
    """Carrega CSS customizado do dashboard."""
    try:
        with open("assets/dashboard_style.css") as f:
            st.markdown(
                f"<style>{f.read()}</style>",
                unsafe_allow_html=True,
            )
    except FileNotFoundError:
        pass
