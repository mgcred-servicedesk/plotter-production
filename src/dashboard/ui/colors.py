"""
Sistema de Cores Semânticas — Prioridade 5 da Reforma UX/UI.

Padronização:
- Verde → acima da meta (>= 100%)
- Amarelo → atenção (60-99%)
- Vermelho → crítico (< 60%)
- Azul → neutro/informativo
"""

from typing import Tuple


# ═══════════════════════════════════════════════════════
# Paleta Semântica
# ═══════════════════════════════════════════════════════

class StatusColors:
    """Cores hexadecimais por status semântico."""
    
    # Verde: Sucesso/Meta Atingida
    SUCCESS = "#10b981"      # emerald-500
    SUCCESS_LIGHT = "#d1fae5"  # emerald-100
    SUCCESS_DARK = "#065f46"   # emerald-800
    
    # Amarelo: Atenção/Proximidade
    WARNING = "#f59e0b"      # amber-500
    WARNING_LIGHT = "#fef3c7"  # amber-100
    WARNING_DARK = "#92400e"   # amber-800
    
    # Vermelho: Crítico/Abaixo
    DANGER = "#ef4444"       # red-500
    DANGER_LIGHT = "#fee2e2"     # red-100
    DANGER_DARK = "#991b1b"      # red-800
    
    # Azul: Neutro/Informativo
    INFO = "#3b82f6"         # blue-500
    INFO_LIGHT = "#dbeafe"       # blue-100
    INFO_DARK = "#1e40af"        # blue-800
    
    # Cinza: Contexto/Secundário
    NEUTRAL = "#6b7280"      # gray-500
    NEUTRAL_LIGHT = "#f3f4f6"    # gray-100
    NEUTRAL_DARK = "#1f2937"     # gray-800


# ═══════════════════════════════════════════════════════
# Funções de Resolução de Cor
# ═══════════════════════════════════════════════════════

def get_status_color(perc_atingimento: float) -> str:
    """
    Retorna cor hexadecimal baseada no percentual de atingimento.
    
    Args:
        perc_atingimento: Percentual de atingimento (0-100+)
    
    Returns:
        Cor hexadecimal correspondente ao status
    """
    if perc_atingimento >= 100:
        return StatusColors.SUCCESS
    elif perc_atingimento >= 60:
        return StatusColors.WARNING
    else:
        return StatusColors.DANGER


def get_status_bg_color(perc_atingimento: float) -> str:
    """Retorna cor de background (light) para o status."""
    if perc_atingimento >= 100:
        return StatusColors.SUCCESS_LIGHT
    elif perc_atingimento >= 60:
        return StatusColors.WARNING_LIGHT
    else:
        return StatusColors.DANGER_LIGHT


def get_status_text_color(perc_atingimento: float) -> str:
    """Retorna cor de texto (dark) para o status."""
    if perc_atingimento >= 100:
        return StatusColors.SUCCESS_DARK
    elif perc_atingimento >= 60:
        return StatusColors.WARNING_DARK
    else:
        return StatusColors.DANGER_DARK


def get_status_emoji(perc_atingimento: float) -> str:
    """Retorna emoji indicador do status."""
    if perc_atingimento >= 100:
        return "🟢"
    elif perc_atingimento >= 60:
        return "🟡"
    else:
        return "🔴"


def get_status_label(perc_atingimento: float) -> str:
    """Retorna label textual do status."""
    if perc_atingimento >= 100:
        return "Saudável"
    elif perc_atingimento >= 80:
        return "Atenção"
    elif perc_atingimento >= 60:
        return "Alerta"
    else:
        return "Crítico"


def get_status_full(perc_atingimento: float) -> Tuple[str, str, str, str]:
    """
    Retorna tupla completa: (cor, bg, emoji, label)
    
    Args:
        perc_atingimento: Percentual de atingimento
    
    Returns:
        Tuple: (cor_principal, cor_bg, emoji, label)
    """
    return (
        get_status_color(perc_atingimento),
        get_status_bg_color(perc_atingimento),
        get_status_emoji(perc_atingimento),
        get_status_label(perc_atingimento),
    )


# ═══════════════════════════════════════════════════════
# Cores para Churn/Índice de Perda
# ═══════════════════════════════════════════════════════

def get_churn_status(indice_perda: float) -> Tuple[str, str, str]:
    """
    Retorna status para índice de churn/perda.
    
    Args:
        indice_perda: Percentual de perda (0-100)
    
    Returns:
        Tuple: (cor, emoji, nivel_texto)
    """
    if indice_perda < 15:
        return (StatusColors.SUCCESS, "🟢", "Baixo")
    elif indice_perda < 25:
        return (StatusColors.WARNING, "🟡", "Moderado")
    else:
        return (StatusColors.DANGER, "🔴", "Alto")


# ═══════════════════════════════════════════════════════
# Cores para Ritmo vs Meta
# ═══════════════════════════════════════════════════════

def get_ritmo_status(desvio_percentual: float) -> Tuple[str, str, str]:
    """
    Retorna status para desvio de ritmo.
    
    Args:
        desvio_percentual: Desvio do ritmo necessário (ex: -36 para 36% abaixo)
    
    Returns:
        Tuple: (cor, emoji, status_texto)
    """
    if desvio_percentual >= 0:
        return (StatusColors.SUCCESS, "✓", "No ritmo")
    elif desvio_percentual >= -20:
        return (StatusColors.WARNING, "⚠", "Atenção")
    else:
        return (StatusColors.DANGER, "🔴", "Abaixo do ritmo")


# ═══════════════════════════════════════════════════════
# Gradientes CSS
# ═══════════════════════════════════════════════════════

def get_gradient_bar_css(perc_atingimento: float) -> str:
    """Retorna CSS de gradiente para barras de progresso."""
    cor = get_status_color(perc_atingimento)
    return f"linear-gradient(90deg, {cor} 0%, {cor}dd 100%)"


# ═══════════════════════════════════════════════════════
# Classes CSS Prontas
# ═══════════════════════════════════════════════════════

def get_status_badge_css(perc_atingimento: float) -> str:
    """Retorna CSS inline para badge de status."""
    cor = get_status_color(perc_atingimento)
    bg = get_status_bg_color(perc_atingimento)
    return f"""
        background-color: {bg};
        color: {cor};
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 600;
        display: inline-block;
    """


def get_semantic_css_variables() -> str:
    """Retorna CSS com variáveis semânticas para uso global."""
    return """
    <style>
    :root {
        /* Status: Sucesso */
        --mg-status-success: #10b981;
        --mg-status-success-light: #d1fae5;
        --mg-status-success-dark: #065f46;
        
        /* Status: Atenção */
        --mg-status-warning: #f59e0b;
        --mg-status-warning-light: #fef3c7;
        --mg-status-warning-dark: #92400e;
        
        /* Status: Crítico */
        --mg-status-danger: #ef4444;
        --mg-status-danger-light: #fee2e2;
        --mg-status-danger-dark: #991b1b;
        
        /* Status: Info/Neutro */
        --mg-status-info: #3b82f6;
        --mg-status-info-light: #dbeafe;
        --mg-status-info-dark: #1e40af;
    }
    </style>
    """
