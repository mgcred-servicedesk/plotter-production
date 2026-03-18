"""
Testes para validação de dados e integridade.
"""
import pytest
import pandas as pd

from src.data_processing.column_mapper import (
    mapear_digitacao,
    aplicar_regras_exclusao_valor_pontos,
    identificar_tipo_produto_real
)


class TestMapeamentoDigitacao:
    """Testes para mapeamento de dados de digitação."""

    def test_colunas_obrigatorias_presentes(self):
        """Verifica que colunas obrigatórias são criadas."""
        df_input = pd.DataFrame({
            'DATA': ['2026-03-01'],
            'LOJA': ['LOJA A'],
            'CONSULTOR': ['João'],
            'PRODUTO': ['CNC'],
            'VALOR': [1000.0]
        })

        df_result = mapear_digitacao(df_input)

        colunas_obrigatorias = ['DATA', 'LOJA', 'CONSULTOR', 'PRODUTO', 'VALOR']
        for col in colunas_obrigatorias:
            assert col in df_result.columns, f"Coluna {col} deve existir"


class TestRegraExclusao:
    """Testes para regras de exclusão de valor/pontos."""

    def test_funcao_adiciona_coluna_is_emissao(self):
        """Verifica que a função adiciona coluna is_emissao_cartao."""
        df_test = pd.DataFrame({
            'PRODUTO': ['CNC NORMAL', 'SAQUE'],
            'VALOR': [1000.0, 500.0],
            'pontos': [5000.0, 1250.0]
        })

        df_result = aplicar_regras_exclusao_valor_pontos(df_test)

        assert 'is_emissao_cartao' in df_result.columns, \
            "Deve criar coluna is_emissao_cartao"
        assert df_result['is_emissao_cartao'].dtype == bool, \
            "Coluna is_emissao_cartao deve ser booleana"


class TestIntegridadeDados:
    """Testes de integridade de dados."""

    def test_sem_valores_nulos_criticos(self, sample_vendas_df):
        """Verifica que colunas críticas não têm valores nulos."""
        colunas_criticas = ['DATA', 'LOJA', 'CONSULTOR', 'VALOR']

        for col in colunas_criticas:
            if col in sample_vendas_df.columns:
                assert not sample_vendas_df[col].isnull().any(), \
                    f"Coluna {col} não deve ter valores nulos"

    def test_valores_numericos_validos(self, sample_vendas_df):
        """Verifica que valores numéricos são válidos."""
        assert (sample_vendas_df['VALOR'] >= 0).all(), \
            "VALOR não deve ter valores negativos"
        assert sample_vendas_df['VALOR'].dtype in ['float64', 'int64'], \
            "VALOR deve ser numérico"
