"""
Testes para o sistema de pontuação mensal.
"""
import pytest
import pandas as pd

from src.data_processing.pontuacao_loader import (
    carregar_pontuacao_mensal,
    calcular_pontos_com_tabela_mensal,
    verificar_produtos_sem_pontuacao,
    criar_mapeamento_tipo_produto
)


class TestCarregarPontuacaoMensal:
    """Testes para carregamento de tabelas de pontuação."""
    
    def test_carregar_pontuacao_marco_2026(self):
        """Testa carregamento da tabela de março 2026."""
        df = carregar_pontuacao_mensal(3, 2026)
        
        assert not df.empty, "Tabela de pontuação não deve estar vazia"
        assert 'PRODUTO' in df.columns, "Deve ter coluna PRODUTO"
        assert 'PONTOS' in df.columns, "Deve ter coluna PONTOS"
        assert len(df) > 0, "Deve ter pelo menos um produto"
        
    def test_pontuacao_sem_duplicatas(self):
        """Verifica que não há produtos duplicados."""
        df = carregar_pontuacao_mensal(3, 2026)
        
        duplicatas = df['PRODUTO'].duplicated().sum()
        assert duplicatas == 0, "Não deve haver produtos duplicados"
        
    def test_pontos_sao_numericos(self):
        """Verifica que pontos são valores numéricos válidos."""
        df = carregar_pontuacao_mensal(3, 2026)
        
        assert df['PONTOS'].dtype in ['float64', 'int64'], \
            "PONTOS deve ser numérico"
        assert (df['PONTOS'] >= 0).all(), \
            "PONTOS não deve ter valores negativos"


class TestCalcularPontos:
    """Testes para cálculo de pontos."""
    
    def test_calculo_basico(self, sample_vendas_df, mes_teste, ano_teste):
        """Testa cálculo básico de pontos."""
        df_result = calcular_pontos_com_tabela_mensal(
            sample_vendas_df, mes_teste, ano_teste, mostrar_avisos=False
        )
        
        assert 'pontos' in df_result.columns, \
            "Deve criar coluna 'pontos'"
        assert 'PONTOS' in df_result.columns, \
            "Deve ter coluna 'PONTOS' da tabela mensal"
        
    def test_calculo_correto(self, sample_vendas_df, mes_teste, ano_teste):
        """Verifica se cálculo pontos = VALOR × PONTOS está correto."""
        df_result = calcular_pontos_com_tabela_mensal(
            sample_vendas_df, mes_teste, ano_teste, mostrar_avisos=False
        )
        
        for idx, row in df_result.iterrows():
            esperado = row['VALOR'] * row['PONTOS']
            calculado = row['pontos']
            assert abs(esperado - calculado) < 0.01, \
                f"Cálculo incorreto para {row.get('PRODUTO', 'N/A')}"
    
    def test_sem_valores_negativos(self, sample_vendas_df, mes_teste, ano_teste):
        """Verifica que não há pontos negativos."""
        df_result = calcular_pontos_com_tabela_mensal(
            sample_vendas_df, mes_teste, ano_teste, mostrar_avisos=False
        )
        
        assert (df_result['pontos'] >= 0).all(), \
            "Não deve haver pontos negativos"


class TestMapeamentoProdutos:
    """Testes para mapeamento de produtos."""
    
    def test_mapeamento_existe(self):
        """Verifica que o mapeamento foi criado."""
        mapeamento = criar_mapeamento_tipo_produto()
        
        assert isinstance(mapeamento, dict), \
            "Mapeamento deve ser um dicionário"
        assert len(mapeamento) > 0, \
            "Mapeamento não deve estar vazio"
        
    def test_produtos_principais_mapeados(self):
        """Verifica que produtos principais estão mapeados."""
        mapeamento = criar_mapeamento_tipo_produto()
        
        produtos_essenciais = ['CNC', 'SAQUE', 'CONSIG', 'FGTS', 'EMISSAO']
        for produto in produtos_essenciais:
            assert produto in mapeamento, \
                f"Produto {produto} deve estar no mapeamento"


class TestVerificacaoProdutosSemPontuacao:
    """Testes para verificação de produtos sem pontuação."""
    
    def test_detecta_produtos_sem_pontuacao(self):
        """Testa detecção de produtos sem pontuação."""
        df_test = pd.DataFrame({
            'PRODUTO': ['PRODUTO A', 'PRODUTO B', 'PRODUTO C'],
            'VALOR': [100, 200, 300],
            'PONTOS': [1.0, 0.0, 1.5],
            'TIPO_PRODUTO': ['CNC', 'SAQUE', 'CONSIG']
        })
        
        info = verificar_produtos_sem_pontuacao(df_test)
        
        assert info['tem_problemas'] is True, \
            "Deve detectar produtos com PONTOS = 0"
        assert info['total_registros'] == 1, \
            "Deve contar 1 registro sem pontuação"
        
    def test_sem_problemas_quando_todos_tem_pontuacao(self):
        """Testa quando todos os produtos têm pontuação."""
        df_test = pd.DataFrame({
            'PRODUTO': ['PRODUTO A', 'PRODUTO B'],
            'VALOR': [100, 200],
            'PONTOS': [1.0, 1.5]
        })
        
        info = verificar_produtos_sem_pontuacao(df_test)
        
        assert info['tem_problemas'] is False, \
            "Não deve reportar problemas"
        assert info['total_registros'] == 0, \
            "Deve contar 0 registros sem pontuação"
