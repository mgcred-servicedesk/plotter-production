"""
Testes para o módulo de KPIs do dashboard.
Valida cálculos de KPIs gerais, incluindo exclusão de supervisores.
"""
import pytest
import pandas as pd
from src.dashboard.kpi_dashboard import calcular_kpis_gerais


@pytest.fixture
def df_vendas_mock():
    """Cria DataFrame de vendas fictício para testes."""
    return pd.DataFrame({
        'CONSULTOR': [
            'Consultor A', 'Consultor B', 'Consultor C',
            'Supervisor X', 'Consultor A', 'Supervisor Y',
            'Consultor B', 'Consultor C', 'Consultor D'
        ],
        'VALOR': [
            1000, 1500, 2000, 3000, 1200, 2500, 1800, 2200, 1600
        ],
        'pontos': [10, 15, 20, 30, 12, 25, 18, 22, 16],
        'LOJA': ['L1', 'L2', 'L1', 'L3', 'L1', 'L2', 'L2', 'L3', 'L1'],
        'REGIAO': ['Sul', 'Norte', 'Sul', 'Centro', 'Sul', 'Norte',
                   'Norte', 'Centro', 'Sul']
    })


@pytest.fixture
def df_metas_mock():
    """Cria DataFrame de metas fictício para testes."""
    return pd.DataFrame({
        'LOJA': ['L1', 'L2', 'L3'],
        'META_PRATA': [5000, 4000, 3000],
        'META_OURO': [7000, 6000, 5000]
    })


@pytest.fixture
def df_supervisores_mock():
    """Cria DataFrame de supervisores fictício para testes."""
    return pd.DataFrame({
        'SUPERVISOR': ['Supervisor X', 'Supervisor Y'],
        'REGIAO': ['Centro', 'Norte']
    })


class TestCalcularKpisGerais:
    """Testes para a função calcular_kpis_gerais."""

    def test_calculo_kpis_sem_supervisores(
        self, df_vendas_mock, df_metas_mock
    ):
        """
        Testa cálculo de KPIs sem passar df_supervisores.
        Deve contar todos os consultores únicos.
        """
        kpis = calcular_kpis_gerais(
            df_vendas_mock,
            df_metas_mock,
            ano=2026,
            mes=3,
            dia_atual=15
        )

        assert kpis['total_vendas'] == 16800
        assert kpis['total_pontos'] == 168
        assert kpis['total_transacoes'] == 9
        assert kpis['num_consultores'] == 6
        assert kpis['meta_prata'] == 12000
        assert kpis['meta_ouro'] == 18000

    def test_calculo_kpis_com_supervisores(
        self, df_vendas_mock, df_metas_mock, df_supervisores_mock
    ):
        """
        Testa cálculo de KPIs passando df_supervisores.
        Deve excluir supervisores da contagem de consultores.
        """
        kpis = calcular_kpis_gerais(
            df_vendas_mock,
            df_metas_mock,
            ano=2026,
            mes=3,
            dia_atual=15,
            df_supervisores=df_supervisores_mock
        )

        assert kpis['total_vendas'] == 16800
        assert kpis['total_pontos'] == 168
        assert kpis['total_transacoes'] == 9
        assert kpis['num_consultores'] == 4
        assert kpis['meta_prata'] == 12000
        assert kpis['meta_ouro'] == 18000

    def test_produtividade_sem_supervisores(
        self, df_vendas_mock, df_metas_mock
    ):
        """
        Testa cálculo de produtividade sem excluir supervisores.
        Produtividade = transações / consultores
        """
        kpis = calcular_kpis_gerais(
            df_vendas_mock,
            df_metas_mock,
            ano=2026,
            mes=3,
            dia_atual=15
        )

        produtividade = (
            kpis['total_transacoes'] / kpis['num_consultores']
        )
        assert produtividade == pytest.approx(1.5, rel=0.01)

    def test_produtividade_com_supervisores(
        self, df_vendas_mock, df_metas_mock, df_supervisores_mock
    ):
        """
        Testa cálculo de produtividade excluindo supervisores.
        Deve resultar em produtividade maior (menos consultores).
        """
        kpis = calcular_kpis_gerais(
            df_vendas_mock,
            df_metas_mock,
            ano=2026,
            mes=3,
            dia_atual=15,
            df_supervisores=df_supervisores_mock
        )

        produtividade = (
            kpis['total_transacoes'] / kpis['num_consultores']
        )
        assert produtividade == pytest.approx(2.25, rel=0.01)

    def test_percentual_atingimento(
        self, df_vendas_mock, df_metas_mock, df_supervisores_mock
    ):
        """Testa cálculo de percentuais de atingimento."""
        kpis = calcular_kpis_gerais(
            df_vendas_mock,
            df_metas_mock,
            ano=2026,
            mes=3,
            dia_atual=15,
            df_supervisores=df_supervisores_mock
        )

        perc_prata_esperado = (168 / 12000) * 100
        perc_ouro_esperado = (168 / 18000) * 100

        assert kpis['perc_ating_prata'] == pytest.approx(
            perc_prata_esperado, rel=0.01
        )
        assert kpis['perc_ating_ouro'] == pytest.approx(
            perc_ouro_esperado, rel=0.01
        )

    def test_ticket_medio(
        self, df_vendas_mock, df_metas_mock, df_supervisores_mock
    ):
        """Testa cálculo de ticket médio."""
        kpis = calcular_kpis_gerais(
            df_vendas_mock,
            df_metas_mock,
            ano=2026,
            mes=3,
            dia_atual=15,
            df_supervisores=df_supervisores_mock
        )

        ticket_medio_esperado = 16800 / 9
        assert kpis['ticket_medio'] == pytest.approx(
            ticket_medio_esperado, rel=0.01
        )

    def test_num_lojas_e_regioes(
        self, df_vendas_mock, df_metas_mock, df_supervisores_mock
    ):
        """Testa contagem de lojas e regiões únicas."""
        kpis = calcular_kpis_gerais(
            df_vendas_mock,
            df_metas_mock,
            ano=2026,
            mes=3,
            dia_atual=15,
            df_supervisores=df_supervisores_mock
        )

        assert kpis['num_lojas'] == 3
        assert kpis['num_regioes'] == 3

    def test_df_supervisores_vazio(
        self, df_vendas_mock, df_metas_mock
    ):
        """
        Testa comportamento com df_supervisores vazio.
        Deve contar todos os consultores.
        """
        df_supervisores_vazio = pd.DataFrame({
            'SUPERVISOR': [],
            'REGIAO': []
        })

        kpis = calcular_kpis_gerais(
            df_vendas_mock,
            df_metas_mock,
            ano=2026,
            mes=3,
            dia_atual=15,
            df_supervisores=df_supervisores_vazio
        )

        assert kpis['num_consultores'] == 6

    def test_df_supervisores_none(
        self, df_vendas_mock, df_metas_mock
    ):
        """
        Testa comportamento com df_supervisores=None.
        Deve contar todos os consultores.
        """
        kpis = calcular_kpis_gerais(
            df_vendas_mock,
            df_metas_mock,
            ano=2026,
            mes=3,
            dia_atual=15,
            df_supervisores=None
        )

        assert kpis['num_consultores'] == 6

    def test_filtro_regiao_com_supervisores(
        self, df_vendas_mock, df_metas_mock, df_supervisores_mock
    ):
        """
        Testa filtro de região: deve excluir apenas supervisores
        da região filtrada, não de todas as regiões.
        """
        df_regiao_sul = df_vendas_mock[
            df_vendas_mock['REGIAO'] == 'Sul'
        ]
        df_supervisores_sul = df_supervisores_mock[
            df_supervisores_mock['REGIAO'] == 'Sul'
        ]

        kpis = calcular_kpis_gerais(
            df_regiao_sul,
            df_metas_mock,
            ano=2026,
            mes=3,
            dia_atual=15,
            df_supervisores=df_supervisores_sul
        )

        assert kpis['num_consultores'] == 3
