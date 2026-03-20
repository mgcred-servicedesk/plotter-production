"""
Testes para cálculos de KPIs por produto.
Valida cálculos de média por consultor para cada produto.
"""
import pytest
import pandas as pd
from src.dashboard.kpi_dashboard import calcular_kpis_por_produto


@pytest.fixture
def df_vendas_produtos_mock():
    """Cria DataFrame de vendas por produto para testes."""
    return pd.DataFrame({
        'CONSULTOR': [
            'Consultor A', 'Consultor B', 'Consultor C',
            'Supervisor X', 'Consultor A', 'Consultor B',
            'Consultor C', 'Consultor D', 'Supervisor Y'
        ],
        'TIPO_PRODUTO': [
            'CNC', 'CNC', 'CONSIG PRIV',
            'FGTS', 'CNC 13º', 'SAQUE',
            'CONSIG', 'CNC', 'FGTS'
        ],
        'VALOR': [
            5000, 3000, 2000,
            1500, 800, 1200,
            2500, 4000, 1000
        ],
        'pontos': [
            50, 30, 20,
            15, 8, 12,
            25, 40, 10
        ],
        'LOJA': ['L1', 'L2', 'L1', 'L3', 'L1', 'L2', 'L3', 'L1', 'L2'],
        'REGIAO': [
            'Sul', 'Norte', 'Sul', 'Centro', 'Sul',
            'Norte', 'Centro', 'Sul', 'Norte'
        ]
    })


@pytest.fixture
def df_metas_produtos_mock():
    """Cria DataFrame de metas por produto para testes."""
    return pd.DataFrame({
        'LOJA': ['L1', 'L2', 'L3'],
        'CNC LOJA': [10000, 8000, 6000],
        'SAQUE LOJA': [5000, 4000, 3000],
        'CLT': [3000, 2500, 2000],
        'CONSIGNADO': [4000, 3500, 3000],
        'META  LOJA FGTS & ANT. BEN.13º': [2000, 1500, 1000]
    })


@pytest.fixture
def df_supervisores_produtos_mock():
    """Cria DataFrame de supervisores para testes."""
    return pd.DataFrame({
        'SUPERVISOR': ['Supervisor X', 'Supervisor Y'],
        'REGIAO': ['Centro', 'Norte']
    })


class TestCalcularKpisPorProduto:
    """Testes para a função calcular_kpis_por_produto."""

    def test_calculo_basico_sem_supervisores(
        self,
        df_vendas_produtos_mock,
        df_metas_produtos_mock
    ):
        """Testa cálculo básico de KPIs por produto sem exclusão."""
        resultado = calcular_kpis_por_produto(
            df_vendas_produtos_mock,
            df_metas_produtos_mock,
            ano=2026,
            mes=3,
            dia_atual=15
        )

        assert not resultado.empty
        assert 'Produto' in resultado.columns
        assert 'Valor' in resultado.columns
        assert 'Pontos' in resultado.columns
        assert 'Pontos Médio/Consultor' in resultado.columns
        assert 'Valor Médio/Consultor' in resultado.columns

        # Verificar que todos os produtos estão presentes
        produtos = resultado['Produto'].tolist()
        assert 'CNC' in produtos
        assert 'SAQUE' in produtos
        assert 'CLT' in produtos
        assert 'CONSIGNADO' in produtos
        assert 'PACK' in produtos

    def test_calculo_com_exclusao_supervisores(
        self,
        df_vendas_produtos_mock,
        df_metas_produtos_mock,
        df_supervisores_produtos_mock
    ):
        """Testa cálculo com exclusão de supervisores."""
        resultado = calcular_kpis_por_produto(
            df_vendas_produtos_mock,
            df_metas_produtos_mock,
            ano=2026,
            mes=3,
            dia_atual=15,
            df_supervisores=df_supervisores_produtos_mock
        )

        assert not resultado.empty

        # Total de consultores deve ser 4 (excluindo 2 supervisores)
        # Verificar produto CNC
        cnc = resultado[resultado['Produto'] == 'CNC'].iloc[0]

        # CNC: Consultor A (5000), Consultor B (3000), Consultor D (4000)
        # Total: 12000
        assert cnc['Valor'] == 12000

        # Pontos CNC: 50 + 30 + 40 = 120
        assert cnc['Pontos'] == 120

        # Média por consultor (4 consultores no total)
        # Pontos médio: 120 / 4 = 30
        assert cnc['Pontos Médio/Consultor'] == 30.0

        # Valor médio: 12000 / 4 = 3000
        assert cnc['Valor Médio/Consultor'] == 3000.0

    def test_media_por_consultor_pack(
        self,
        df_vendas_produtos_mock,
        df_metas_produtos_mock,
        df_supervisores_produtos_mock
    ):
        """Testa cálculo de média por consultor para PACK."""
        resultado = calcular_kpis_por_produto(
            df_vendas_produtos_mock,
            df_metas_produtos_mock,
            ano=2026,
            mes=3,
            dia_atual=15,
            df_supervisores=df_supervisores_produtos_mock
        )

        # PACK = FGTS + CNC 13º
        # FGTS: Supervisor X (1500), Supervisor Y (1000) = 2500
        # CNC 13º: Consultor A (800) = 800
        # Total PACK: 3300 (mas supervisores vendem)
        pack = resultado[resultado['Produto'] == 'PACK'].iloc[0]

        # Valor total PACK
        assert pack['Valor'] == 3300

        # Pontos PACK: 15 + 8 + 10 = 33
        assert pack['Pontos'] == 33

        # Média por consultor (4 consultores)
        # Pontos médio: 33 / 4 = 8.25
        assert pack['Pontos Médio/Consultor'] == 8.25

        # Valor médio: 3300 / 4 = 825
        assert pack['Valor Médio/Consultor'] == 825.0

    def test_media_por_consultor_clt(
        self,
        df_vendas_produtos_mock,
        df_metas_produtos_mock,
        df_supervisores_produtos_mock
    ):
        """Testa cálculo de média por consultor para CLT."""
        resultado = calcular_kpis_por_produto(
            df_vendas_produtos_mock,
            df_metas_produtos_mock,
            ano=2026,
            mes=3,
            dia_atual=15,
            df_supervisores=df_supervisores_produtos_mock
        )

        # CLT = CONSIG PRIV
        # Consultor C: 2000
        clt = resultado[resultado['Produto'] == 'CLT'].iloc[0]

        assert clt['Valor'] == 2000
        assert clt['Pontos'] == 20

        # Média por consultor (4 consultores)
        # Pontos médio: 20 / 4 = 5
        assert clt['Pontos Médio/Consultor'] == 5.0

        # Valor médio: 2000 / 4 = 500
        assert clt['Valor Médio/Consultor'] == 500.0

    def test_sem_consultores(
        self,
        df_metas_produtos_mock
    ):
        """Testa comportamento quando não há consultores."""
        df_vazio = pd.DataFrame({
            'CONSULTOR': [],
            'TIPO_PRODUTO': [],
            'VALOR': [],
            'pontos': []
        })

        resultado = calcular_kpis_por_produto(
            df_vazio,
            df_metas_produtos_mock,
            ano=2026,
            mes=3,
            dia_atual=15
        )

        assert not resultado.empty

        # Todos os produtos devem ter média 0
        for _, row in resultado.iterrows():
            assert row['Pontos Médio/Consultor'] == 0
            assert row['Valor Médio/Consultor'] == 0

    def test_consistencia_total_pontos(
        self,
        df_vendas_produtos_mock,
        df_metas_produtos_mock,
        df_supervisores_produtos_mock
    ):
        """Testa consistência entre pontos totais e soma das médias."""
        resultado = calcular_kpis_por_produto(
            df_vendas_produtos_mock,
            df_metas_produtos_mock,
            ano=2026,
            mes=3,
            dia_atual=15,
            df_supervisores=df_supervisores_produtos_mock
        )

        # Soma total de pontos de todos os produtos
        total_pontos = resultado['Pontos'].sum()

        # Total de pontos no DataFrame original
        pontos_esperados = df_vendas_produtos_mock['pontos'].sum()

        assert total_pontos == pontos_esperados

    def test_valores_nao_negativos(
        self,
        df_vendas_produtos_mock,
        df_metas_produtos_mock,
        df_supervisores_produtos_mock
    ):
        """Testa que não há valores negativos nos cálculos."""
        resultado = calcular_kpis_por_produto(
            df_vendas_produtos_mock,
            df_metas_produtos_mock,
            ano=2026,
            mes=3,
            dia_atual=15,
            df_supervisores=df_supervisores_produtos_mock
        )

        # Verificar que todas as médias são >= 0
        assert (resultado['Pontos Médio/Consultor'] >= 0).all()
        assert (resultado['Valor Médio/Consultor'] >= 0).all()
        assert (resultado['Valor'] >= 0).all()
        assert (resultado['Pontos'] >= 0).all()
