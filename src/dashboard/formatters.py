"""
Formatadores especificos do dashboard interativo.

Diferem dos formatadores em ``src/reports/formatters.py``
no tratamento de NaN e no formato de percentuais (usam
ponto decimal e 1 casa, vs virgula e 2 casas nos PDFs).
"""


def formatar_moeda(valor):
    """Formata valor como moeda brasileira."""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_numero(valor):
    """Formata numero com separador de milhares."""
    return f"{valor:,.0f}".replace(",", ".")


def formatar_percentual(valor):
    """Formata percentual."""
    return f"{valor:.1f}%"
