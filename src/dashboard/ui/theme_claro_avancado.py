"""
Tema Claro Avançado — camada complementar Aurora Glass.

DEVE ser chamado APÓS ``aplicar_tema()``. Não substitui o design
system: sobrescreve tokens ``--mg-*`` para um off-white quente,
adiciona camadas decorativas (aurora orbs, noise, wave) e injeta
glassmorphism nas classes ``.mg-*`` que o dashboard já renderiza.

Estilização opera direto nas classes existentes (``.mg-kpi-hero``,
``.mg-resumo-card``, ``.mg-prioridade-card``, etc.) — não cria
componentes paralelos. Para aplicar gradient flow no header, basta
adicionar ``class="mg-gradient-text"`` no ``<h1>`` desejado.
"""

import hashlib

import streamlit as st


def aplicar_tema_claro_avancado() -> None:
    """Camada complementar — chamar SEMPRE depois de ``aplicar_tema()``.

    Estratégia:
    - Sobrescreve ``--mg-bg`` (off-white quente).
    - 3 orbes aurora + noise SVG no fundo (camada ::before).
    - Wave pattern sutil no rodapé (camada ::after).
    - Glassmorphism nas classes ``.mg-kpi-hero``, ``.mg-resumo-card``,
      ``.mg-prioridade-card``, ``.mg-kpi-context``, ``.mg-chart-card``.
    - Hover lift reforçado nos cards principais.
    - Toast estilizado via ``[data-testid="stToast"]``.

    Usa ``st.markdown(unsafe_allow_html=True)`` (não ``st.html``) para
    garantir que mudanças no CSS sejam refletidas no hot-reload — mesmo
    padrão do ``aplicar_tema()`` em ``theme.py``. Hash do CSS no comentário
    inicial força o navegador a tratar como recurso novo a cada edição.
    """
    css_hash = hashlib.md5(_CSS.encode()).hexdigest()[:8]
    st.markdown(
        f"<!-- tca-v{css_hash} -->\n{_CSS}",
        unsafe_allow_html=True,
    )


_CSS = """
<style>
/* ============================================
   1. OFF-WHITE QUENTE — overrides dos tokens
   ============================================ */
:root {
    --mg-bg: #F2EFE9;
    --mg-surface: #FCFBF8;
    --mg-surface-elevated: #FFFFFF;
    --mg-sidebar-bg: #EAE6DF;
    --mg-secondary-bg: #FCFBF8;

    --mg-border: #E5E1D7;
    --mg-border-strong: #D4CFC2;
    --mg-card-border: #E5E1D7;

    --mg-shadow-xs: 0 1px 2px rgba(80,60,30,0.05);
    --mg-shadow-sm: 0 2px 6px rgba(80,60,30,0.06),
                    0 1px 2px rgba(80,60,30,0.04);
    --mg-shadow-md: 0 6px 16px rgba(80,60,30,0.07),
                    0 2px 4px rgba(80,60,30,0.04);
    --mg-shadow-lg: 0 14px 28px rgba(80,60,30,0.09),
                    0 4px 8px rgba(80,60,30,0.05);

    /* Tokens novos só do tema avançado — usados pelos overrides */
    /* Glass clearly warm-tinted: cream cards sobre warm-bg eliminam
       o branco puro. Opacidade reduzida deixa orbs aurora aparecerem. */
    --tca-glass-bg: rgba(247, 238, 218, 0.62);
    --tca-glass-bg-strong: rgba(250, 244, 230, 0.82);
    --tca-glass-border: rgba(196, 178, 140, 0.35);
    --tca-glow-warm: rgba(180, 140, 90, 0.16);
}

/* ============================================
   2. AURORA AMBIENT — orbes + noise no fundo
   ============================================ */
[data-testid="stAppViewContainer"]::before {
    content: '';
    position: fixed;
    inset: 0;
    z-index: 0;
    pointer-events: none;
    background:
        /* Noise SVG sutil — textura orgânica */
        url("data:image/svg+xml,%3Csvg viewBox='0 0 400 400' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.018'/%3E%3C/svg%3E"),
        /* Spotlight focal acima dos KPIs principais */
        radial-gradient(1100px 450px at 50% 0%,
            rgba(196,176,224,0.26) 0%, transparent 65%),
        /* Aurora orbs — cantos */
        radial-gradient(900px 600px at 90% 10%,
            rgba(196,176,224,0.22) 0%, transparent 60%),
        radial-gradient(700px 500px at -5% 25%,
            rgba(176,210,232,0.20) 0%, transparent 60%),
        radial-gradient(800px 600px at 50% 110%,
            rgba(232,200,168,0.20) 0%, transparent 60%);
}

/* Wave pattern decorativo no rodapé */
[data-testid="stAppViewContainer"]::after {
    content: '';
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    height: 240px;
    z-index: 0;
    pointer-events: none;
    opacity: 0.55;
    background:
        url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1440 320'%3E%3Cpath fill='%23c4b0e0' fill-opacity='0.18' d='M0,160L60,176C120,192,240,224,360,224C480,224,600,192,720,165.3C840,139,960,117,1080,128C1200,139,1320,181,1380,197.3L1440,213L1440,320L1380,320C1320,320,1200,320,1080,320C960,320,840,320,720,320C600,320,480,320,360,320C240,320,120,320,60,320L0,320Z'%3E%3C/path%3E%3C/svg%3E")
        no-repeat bottom / cover;
}

/* Conteúdo flutua acima das camadas decorativas */
[data-testid="stAppViewContainer"] > * {
    position: relative;
    z-index: 1;
}

/* ============================================
   3. GLASSMORPHISM — cards reais do dashboard
   ============================================ */

/* KPIs hero (PAGOS / % META / GAP) */
.mg-kpi-hero {
    background: var(--tca-glass-bg) !important;
    backdrop-filter: blur(18px) saturate(170%);
    -webkit-backdrop-filter: blur(18px) saturate(170%);
    border: 1px solid var(--tca-glass-border) !important;
    box-shadow:
        0 4px 20px rgba(80,60,30,0.06),
        inset 0 1px 0 rgba(255,255,255,0.85) !important;
    transition: transform 0.25s cubic-bezier(0.4,0,0.2,1),
                box-shadow 0.25s cubic-bezier(0.4,0,0.2,1),
                background 0.25s ease !important;
    position: relative;
    overflow: hidden;
}

.mg-kpi-hero::before {
    content: '';
    position: absolute;
    top: 0;
    left: -120%;
    width: 100%;
    height: 100%;
    background: linear-gradient(110deg,
        transparent 40%,
        rgba(255,255,255,0.45) 50%,
        transparent 60%);
    transition: left 0.7s ease;
    pointer-events: none;
}

.mg-kpi-hero:hover {
    background: var(--tca-glass-bg-strong) !important;
    transform: translateY(-3px) !important;
    box-shadow:
        0 12px 32px rgba(80,60,30,0.10),
        0 0 0 1px rgba(255,255,255,0.7),
        0 0 36px var(--tca-glow-warm),
        inset 0 1px 0 rgba(255,255,255,0.95) !important;
}

.mg-kpi-hero:hover::before {
    left: 120%;
}

/* KPIs de contexto (em análise, cancelados, médias) */
.mg-kpi-context {
    background: var(--tca-glass-bg) !important;
    backdrop-filter: blur(14px) saturate(160%);
    -webkit-backdrop-filter: blur(14px) saturate(160%);
    border: 1px solid var(--tca-glass-border) !important;
    box-shadow:
        0 2px 12px rgba(80,60,30,0.04),
        inset 0 1px 0 rgba(255,255,255,0.75) !important;
    transition: transform 0.2s ease, box-shadow 0.2s ease,
                background 0.2s ease !important;
}

.mg-kpi-context:hover {
    background: var(--tca-glass-bg-strong) !important;
    transform: translateY(-2px) !important;
    box-shadow:
        0 6px 20px rgba(80,60,30,0.07),
        inset 0 1px 0 rgba(255,255,255,0.9) !important;
}

/* Resumo executivo */
.mg-resumo-card {
    background: var(--tca-glass-bg-strong) !important;
    backdrop-filter: blur(18px) saturate(170%);
    -webkit-backdrop-filter: blur(18px) saturate(170%);
    border: 1px solid var(--tca-glass-border) !important;
    box-shadow:
        0 6px 24px rgba(80,60,30,0.07),
        inset 0 1px 0 rgba(255,255,255,0.9) !important;
}

/* Prioridades de ação */
.mg-prioridade-card {
    background: var(--tca-glass-bg) !important;
    backdrop-filter: blur(14px) saturate(160%);
    -webkit-backdrop-filter: blur(14px) saturate(160%);
    border: 1px solid var(--tca-glass-border) !important;
    border-left: 4px solid var(--mg-primary) !important;
    box-shadow: 0 2px 10px rgba(80,60,30,0.04) !important;
    transition: transform 0.2s ease, box-shadow 0.2s ease !important;
}

.mg-prioridade-card:hover {
    transform: translateX(4px) !important;
    box-shadow:
        0 6px 18px rgba(80,60,30,0.08),
        inset 0 1px 0 rgba(255,255,255,0.85) !important;
    background: var(--tca-glass-bg-strong) !important;
}

/* Cards de chart wrapper */
.mg-chart-card {
    background: var(--tca-glass-bg) !important;
    backdrop-filter: blur(14px) saturate(160%);
    -webkit-backdrop-filter: blur(14px) saturate(160%);
    border: 1px solid var(--tca-glass-border) !important;
    box-shadow:
        0 4px 16px rgba(80,60,30,0.05),
        inset 0 1px 0 rgba(255,255,255,0.8) !important;
}

/* ============================================
   4. TOAST GLASS — st.toast() nativo
   ============================================ */
[data-testid="stToast"] {
    background: var(--tca-glass-bg-strong) !important;
    backdrop-filter: blur(20px) saturate(180%) !important;
    -webkit-backdrop-filter: blur(20px) saturate(180%) !important;
    border: 1px solid var(--tca-glass-border) !important;
    border-radius: 14px !important;
    box-shadow: 0 8px 28px rgba(80,60,30,0.12) !important;
}

/* ============================================
   5. UTILITY — gradient text para headers
       Uso opcional: <h1 class="mg-gradient-text">...
   ============================================ */
.mg-gradient-text {
    background: linear-gradient(90deg,
        #5b6ee0 0%, #7d5da8 30%, #c084d6 60%,
        #d97c64 90%, #5b6ee0 100%);
    background-size: 220% auto;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    animation: tcaGradientFlow 6s linear infinite;
}

@keyframes tcaGradientFlow {
    0%   { background-position:   0% center; }
    100% { background-position: 220% center; }
}
</style>
"""
