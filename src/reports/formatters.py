"""
Funções centralizadas de formatação para relatórios PDF e Excel.

Formato padrão brasileiro: moeda (R$), separador de milhares (.),
separador decimal (,) e percentual com vírgula.
"""
import pandas as pd


def formatar_moeda(valor: float) -> str:
    """
    Formata valor como moeda brasileira (R$ X.XXX,XX).

    Args:
        valor: Valor numérico a ser formatado.

    Returns:
        String formatada como moeda brasileira.
    """
    if pd.isna(valor):
        return "R$ 0,00"
    return (
        f"R$ {valor:,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def formatar_moeda_compacta(valor: float) -> str:
    """
    Formata valor como moeda brasileira de forma compacta.

    Usa sufixos M (milhão) e K (mil) para valores grandes.

    Args:
        valor: Valor numérico a ser formatado.

    Returns:
        String formatada de forma compacta.
    """
    if pd.isna(valor) or valor == 0:
        return "R$ 0"
    if valor >= 1_000_000:
        return f"R$ {valor / 1_000_000:.1f}M".replace(".", ",")
    if valor >= 1_000:
        return f"R$ {valor / 1_000:.1f}K".replace(".", ",")
    return f"R$ {valor:.0f}"


def formatar_numero(valor: float) -> str:
    """
    Formata número inteiro com separador de milhares (ponto).

    Args:
        valor: Valor numérico a ser formatado.

    Returns:
        String formatada com separador de milhares.
    """
    if pd.isna(valor):
        return "0"
    return f"{valor:,.0f}".replace(",", ".")


def formatar_percentual(valor: float, casas: int = 2) -> str:
    """
    Formata valor como percentual com vírgula decimal.

    Args:
        valor: Valor numérico (ex: 85.5 para 85,50%).
        casas: Número de casas decimais (padrão: 2).

    Returns:
        String formatada como percentual.
    """
    if pd.isna(valor):
        return "0,00%"
    return f"{valor:.{casas}f}%".replace(".", ",")
