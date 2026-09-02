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


def formatar_decimal(valor, casas: int = 1):
    """Formata numero com separador de milhares e casas decimais.

    Existe para o headcount ponderado, que e fracionario por construcao
    (``gente-mes``: 112,5 pessoas nao e erro de arredondamento, e alguem
    que trabalhou meio mes).
    """
    txt = f"{valor:,.{casas}f}"
    return txt.replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_percentual(valor):
    """Formata percentual."""
    return f"{valor:.1f}%"


def formatar_moeda_compacta(valor: float) -> str:
    """
    Formata valor como moeda brasileira de forma compacta.
    Usa sufixos M (milhão) e K (mil) para valores grandes.
    """
    if valor == 0:
        return "R$ 0"
    if valor >= 1_000_000:
        return f"R$ {valor / 1_000_000:.1f}M".replace(".", ",")
    if valor >= 1_000:
        return f"R$ {valor / 1_000:.1f}K".replace(".", ",")
    return f"R$ {valor:.0f}"
