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


# ─────────────────────────────────────────────────────────
# Design tokens — Fase 1 do redesign
#
# Paleta baseada em OKLCH (perceptually uniform) com
# fallback hex. Light = warm neutrals, dark = warm black
# (inspirado em Linear, Vercel, Stripe).
# ─────────────────────────────────────────────────────────

# Paleta estendida para graficos Plotly (CSS nao alcanca)
_CHART_THEME = {
    "light": {
        "text": "#1F2937",
        "text_secondary": "rgba(31,41,55,0.62)",
        "bg": "rgba(0,0,0,0)",
        "grid": "rgba(31,41,55,0.06)",
        "grid_zero": "rgba(31,41,55,0.12)",
        "tooltip_bg": "rgba(20,20,22,0.94)",
        "tooltip_text": "#FAFAF9",
        "border": "rgba(31,41,55,0.08)",
    },
    "dark": {
        "text": "#F5F4F2",
        "text_secondary": "rgba(245,244,242,0.58)",
        "bg": "rgba(0,0,0,0)",
        "grid": "rgba(245,244,242,0.05)",
        "grid_zero": "rgba(245,244,242,0.10)",
        "tooltip_bg": "rgba(10,10,11,0.96)",
        "tooltip_text": "#F5F4F2",
        "border": "rgba(245,244,242,0.08)",
    },
}

# Cores do tema nativo Streamlit (sincronizado com o toggle)
_NATIVE_THEME = {
    "light": {
        "base": "light",
        "primaryColor": "#3366E6",
        "backgroundColor": "#FAFAF9",
        "secondaryBackgroundColor": "#FFFFFF",
        "textColor": "#1F2937",
    },
    "dark": {
        "base": "dark",
        "primaryColor": "#5C8FF7",
        "backgroundColor": "#0A0A0B",
        "secondaryBackgroundColor": "#141416",
        "textColor": "#F5F4F2",
    },
}

# Variaveis CSS por tema (--mg-*)
# - bg: app background
# - surface: card/surface background (antes: secondary-bg)
# - surface-elevated: popovers, dropdowns, tooltips
# - border: separadores sutis
# - border-strong: bordas de inputs, cards com peso
# - text / text-muted / text-subtle: hierarquia tipografica
# - shadow-{xs,sm,md,lg}: elevation system em camadas
_CSS_VARS = {
    "light": """
        --mg-primary: #3366E6;
        --mg-primary-hover: #2952C7;
        --mg-primary-soft: rgba(51,102,230,0.10);
        --mg-primary-ring: rgba(51,102,230,0.22);

        --mg-bg: #FAFAF9;
        --mg-surface: #FFFFFF;
        --mg-surface-elevated: #FFFFFF;
        --mg-sidebar-bg: #FFFFFF;
        --mg-secondary-bg: #FFFFFF;

        --mg-text: #1F2937;
        --mg-text-muted: #6B7280;
        --mg-text-subtle: #9CA3AF;
        --mg-text-secondary: #6B7280;

        --mg-border: #EBEAE8;
        --mg-border-strong: #D9D8D4;
        --mg-card-border: #EBEAE8;

        --mg-hover-bg: rgba(51,102,230,0.05);
        --mg-scrollbar: rgba(31,41,55,0.18);

        --mg-success: #10A37F;
        --mg-success-soft: rgba(16,163,127,0.10);
        --mg-warning: #D97706;
        --mg-warning-soft: rgba(217,119,6,0.10);
        --mg-danger: #DC2626;
        --mg-danger-soft: rgba(220,38,38,0.10);

        --mg-shadow-xs: 0 1px 2px rgba(17,24,39,0.04);
        --mg-shadow-sm: 0 2px 4px rgba(17,24,39,0.05),
                        0 1px 2px rgba(17,24,39,0.04);
        --mg-shadow-md: 0 4px 8px rgba(17,24,39,0.06),
                        0 2px 4px rgba(17,24,39,0.04);
        --mg-shadow-lg: 0 12px 24px rgba(17,24,39,0.08),
                        0 4px 8px rgba(17,24,39,0.05);

        --mg-shadow: var(--mg-shadow-xs);
        --mg-shadow-hover: var(--mg-shadow-md);

        --mg-gradient-1: linear-gradient(180deg, #3366E6, #5C8FF7);
        --mg-gradient-2: linear-gradient(180deg, #10A37F, #34D399);
        --mg-gradient-3: linear-gradient(180deg, #D97706, #FBBF24);
        --mg-gradient-4: linear-gradient(180deg, #10A37F, #5EEAD4);
    """,
    "dark": """
        --mg-primary: #5C8FF7;
        --mg-primary-hover: #7AA5F9;
        --mg-primary-soft: rgba(92,143,247,0.14);
        --mg-primary-ring: rgba(92,143,247,0.32);

        --mg-bg: #0A0A0B;
        --mg-surface: #141416;
        --mg-surface-elevated: #1C1C1F;
        --mg-sidebar-bg: #101012;
        --mg-secondary-bg: #141416;

        --mg-text: #F5F4F2;
        --mg-text-muted: #9A9A9F;
        --mg-text-subtle: #6B6B70;
        --mg-text-secondary: #9A9A9F;

        --mg-border: #1F1F22;
        --mg-border-strong: #2A2A2E;
        --mg-card-border: #1F1F22;

        --mg-hover-bg: rgba(92,143,247,0.08);
        --mg-scrollbar: rgba(245,244,242,0.14);

        --mg-success: #34D399;
        --mg-success-soft: rgba(52,211,153,0.14);
        --mg-warning: #FBBF24;
        --mg-warning-soft: rgba(251,191,36,0.14);
        --mg-danger: #F87171;
        --mg-danger-soft: rgba(248,113,113,0.14);

        --mg-shadow-xs: 0 1px 2px rgba(0,0,0,0.30);
        --mg-shadow-sm: 0 2px 4px rgba(0,0,0,0.35),
                        0 1px 2px rgba(0,0,0,0.30),
                        inset 0 1px 0 rgba(255,255,255,0.03);
        --mg-shadow-md: 0 4px 12px rgba(0,0,0,0.45),
                        0 2px 4px rgba(0,0,0,0.35),
                        inset 0 1px 0 rgba(255,255,255,0.04);
        --mg-shadow-lg: 0 16px 32px rgba(0,0,0,0.55),
                        0 6px 12px rgba(0,0,0,0.40),
                        inset 0 1px 0 rgba(255,255,255,0.05);

        --mg-shadow: var(--mg-shadow-xs);
        --mg-shadow-hover: var(--mg-shadow-md);

        --mg-gradient-1: linear-gradient(180deg, #5C8FF7, #93B5FA);
        --mg-gradient-2: linear-gradient(180deg, #34D399, #6EE7B7);
        --mg-gradient-3: linear-gradient(180deg, #FBBF24, #FDE047);
        --mg-gradient-4: linear-gradient(180deg, #34D399, #5EEAD4);
    """,
}


# Paleta de cores para graficos (tokens semanticos).
# Sequencia pensada para categorias distintas em series
# comparadas — mantem ordem estavel entre temas.
CHART_COLORS = {
    "primary": "#3366E6",
    "primary_dark": "#2952C7",
    "secondary": "#10A37F",
    "success": "#10A37F",
    "danger": "#DC2626",
    "warning": "#D97706",
    "neutral": "#6B7280",
    "purple": "#7C3AED",
    "rose": "#E11D48",
    "seq": [
        "#3366E6",
        "#10A37F",
        "#D97706",
        "#7C3AED",
        "#0EA5E9",
        "#E11D48",
        "#14B8A6",
        "#6B7280",
    ],
}


def get_theme_mode() -> str:
    """Retorna o modo escolhido pelo usuario.

    Valores: ``'light'``, ``'dark'``, ``'system'``.
    Default: ``'system'`` (segue preferencia do SO).
    """
    return st.session_state.get("theme_mode", "system")


def set_theme_mode(mode: str) -> None:
    """Define o modo do tema e invalida o tema resolvido.

    Se ``mode`` for ``'light'`` ou ``'dark'``, o tema
    ativo fica fixo. Se for ``'system'``, remove o cache
    para que ``get_theme()`` re-resolva via JS de deteccao.
    """
    if mode not in ("light", "dark", "system"):
        return
    st.session_state["theme_mode"] = mode
    if mode in ("light", "dark"):
        st.session_state["theme"] = mode
    else:
        st.session_state.pop("theme", None)


def get_theme() -> str:
    """Retorna tema ativo ('light' ou 'dark') derivado do mode.

    - Se mode = ``'light'``/``'dark'``: retorna explicitamente.
    - Se mode = ``'system'``: lê do JS (query param ``_theme``)
      ou fallback ``'light'`` no primeiro render.
    """
    mode = get_theme_mode()
    if mode in ("light", "dark"):
        return mode

    # mode == "system" — detectar via JS / query param
    if "theme" not in st.session_state:
        detected = st.query_params.get("_theme")
        if detected in ("light", "dark"):
            st.session_state["theme"] = detected
            del st.query_params["_theme"]
        else:
            # Fallback: sera corrigido pelo JS no 1o render
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

    # JS para sincronizar tema no html[data-theme] para CSS
    is_dark = theme == "dark"
    st.markdown(
        f"""<script>
        (function() {{
            document.documentElement.setAttribute(
                'data-theme', '{theme}'
            );
        }})();
        </script>""",
        unsafe_allow_html=True,
    )

    # JS: detectar preferencia do sistema na primeira
    # visita + persistir tema + tematizar iframes.
    # Usa st.iframe (substitui components.v1.html deprecated
    # em Streamlit 1.56, removido em 2026-06-01).
    is_dark = "true" if theme == "dark" else "false"
    st.iframe(
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
            const tc = isDark ? '#F5F4F2' : '#1F2937';
            const pc = isDark ? '#5C8FF7' : '#3366E6';
            const sb = isDark ? '#141416' : '#FFFFFF';
            const bg = isDark ? '#0A0A0B' : '#FAFAF9';

            localStorage.setItem('mgcred_theme', isDark ? 'dark' : 'light');

            function inject(iframe) {{
                try {{
                    const doc = iframe.contentDocument
                             || iframe.contentWindow.document;
                    if (!doc || !doc.documentElement) return;
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
        height=1,
    )


def carregar_estilos_customizados() -> None:
    """Carrega CSS customizado do dashboard."""
    import os

    css_path = "assets/dashboard_style.css"
    try:
        # Cache busting: usa timestamp de modificação do arquivo
        mtime = os.path.getmtime(css_path)
        with open(css_path) as f:
            css_content = f.read()

        # Adiciona comment com timestamp para invalidar cache
        st.markdown(
            f"<style>/* CSS v{mtime} */\n{css_content}</style>",
            unsafe_allow_html=True,
        )
    except FileNotFoundError:
        pass
