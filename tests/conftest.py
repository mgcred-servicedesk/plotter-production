"""
Configuração de fixtures para testes pytest.
"""
import sys
from pathlib import Path

import pytest
import pandas as pd

# Adicionar diretório raiz ao path
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


@pytest.fixture
def sample_vendas_df():
    """DataFrame de vendas de exemplo para testes."""
    return pd.DataFrame({
        'DATA': ['2026-03-01', '2026-03-01', '2026-03-02'],
        'LOJA': ['LOJA A', 'LOJA A', 'LOJA B'],
        'CONSULTOR': ['João', 'Maria', 'Pedro'],
        'TIPO_PRODUTO': ['CNC', 'EMISSAO', 'CNC 13º'],
        'PRODUTO': ['CNC NORMAL', 'CARTÃO BMG', 'CNC 13 SALARIO'],
        'VALOR': [1000.0, 500.0, 800.0]
    })


@pytest.fixture
def sample_metas_df():
    """DataFrame de metas de exemplo para testes."""
    return pd.DataFrame({
        'LOJA': ['LOJA A', 'LOJA B'],
        'META_PRATA': [50000, 40000],
        'META_OURO': [80000, 60000]
    })


@pytest.fixture
def mes_teste():
    """Mês padrão para testes."""
    return 3


@pytest.fixture
def ano_teste():
    """Ano padrão para testes."""
    return 2026
