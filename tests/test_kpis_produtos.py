"""
Testes dos KPIs por grupo de produto (``src/dashboard/kpis/produtos.py``).

``calcular_kpis_por_produto`` depende de ``calcular_dias_uteis``, que
busca feriados no Supabase quando ``feriados=None``. A fixture
``sem_feriados`` neutraliza esse acesso (conjunto vazio), deixando o DU
determinístico para asserções exatas.
"""
import pandas as pd
import pytest

from src.dashboard.kpis.produtos import (
    calcular_distribuicao_produtos,
    calcular_kpis_por_produto,
)
from src.shared.dias_uteis import calcular_dias_uteis

_COLS_ESPERADAS = {
    "Produto", "Valor", "Meta", "Meta Diária", "Meta Diária Restante",
    "% Atingimento", "Quantidade", "Ticket Médio", "Valor Médio/Consultor",
    "Média DU", "Projeção", "% Projeção",
}


@pytest.mark.unit
class TestCalcularKpisPorProduto:
    def test_estrutura_e_grupos_ordenados(
        self, sample_pagos_produto_df, sample_metas_produto_df,
        sample_categorias_df, sem_feriados,
    ):
        res = calcular_kpis_por_produto(
            sample_pagos_produto_df, sample_metas_produto_df,
            sample_categorias_df, ano=2026, mes=3, dia_atual=16,
        )
        assert list(res["Produto"]) == ["CNC", "SAQUE"]  # sorted(grupos)
        assert _COLS_ESPERADAS.issubset(set(res.columns))

    def test_valores_agregados(
        self, sample_pagos_produto_df, sample_metas_produto_df,
        sample_categorias_df, sem_feriados,
    ):
        res = calcular_kpis_por_produto(
            sample_pagos_produto_df, sample_metas_produto_df,
            sample_categorias_df, ano=2026, mes=3, dia_atual=16,
        )
        cnc = res[res["Produto"] == "CNC"].iloc[0]
        # CNC: 1000 + 500 = 1500; quantidade conta só VALOR > 0
        assert cnc["Valor"] == pytest.approx(1500.0)
        assert cnc["Quantidade"] == 2
        assert cnc["Meta"] == pytest.approx(3000.0)
        assert cnc["% Atingimento"] == pytest.approx(50.0)
        assert cnc["Ticket Médio"] == pytest.approx(1500 / 2)
        # 4 consultores únicos (incluindo Ana, com VALOR 0)
        assert cnc["Valor Médio/Consultor"] == pytest.approx(1500 / 4)

        saque = res[res["Produto"] == "SAQUE"].iloc[0]
        assert saque["Valor"] == pytest.approx(800.0)
        assert saque["Quantidade"] == 1  # Ana (VALOR 0) não conta

    def test_metas_diarias_usam_dias_uteis(
        self, sample_pagos_produto_df, sample_metas_produto_df,
        sample_categorias_df, sem_feriados,
    ):
        du_total, du_dec, _ = calcular_dias_uteis(2026, 3, 16)
        res = calcular_kpis_por_produto(
            sample_pagos_produto_df, sample_metas_produto_df,
            sample_categorias_df, ano=2026, mes=3, dia_atual=16,
        )
        cnc = res[res["Produto"] == "CNC"].iloc[0]
        assert cnc["Meta Diária"] == pytest.approx(3000 / du_total)
        assert cnc["Média DU"] == pytest.approx(1500 / du_dec)
        assert cnc["Projeção"] == pytest.approx((1500 / du_dec) * du_total)

    def test_meta_ausente_nao_quebra(
        self, sample_pagos_produto_df, sample_categorias_df, sem_feriados,
    ):
        # df_metas_produto vazio → meta 0, sem ZeroDivisionError
        res = calcular_kpis_por_produto(
            sample_pagos_produto_df, pd.DataFrame(),
            sample_categorias_df, ano=2026, mes=3, dia_atual=16,
        )
        assert (res["% Atingimento"] == 0).all()
        assert (res["% Projeção"] == 0).all()


@pytest.mark.unit
class TestCalcularDistribuicaoProdutos:
    def test_sem_coluna_consultor_retorna_vazio(self):
        distrib, moeda, numero = calcular_distribuicao_produtos(
            pd.DataFrame({"VALOR": [100.0]})
        )
        assert distrib.empty
        assert moeda == []
        assert numero == []

    def test_distribuicao_valor_total_e_ordenacao(self):
        df = pd.DataFrame({
            "CONSULTOR": ["João", "Maria"],
            "grupo_dashboard": ["CNC", "SAQUE"],
            "VALOR": [1000.0, 500.0],
            "TIPO_PRODUTO": ["CNC", "SAQUE"],
        })
        distrib, moeda, numero = calcular_distribuicao_produtos(df)
        assert "TOTAL" in distrib.columns
        # ordenado por TOTAL desc → João (1000) primeiro
        assert distrib.iloc[0]["CONSULTOR"] == "João"
        assert distrib["TOTAL"].tolist() == [1000.0, 500.0]
        assert set(moeda) >= {"CNC", "SAQUE", "TOTAL"}
        assert numero == []

    def test_aceleradores_contados_por_quantidade(self):
        df = pd.DataFrame({
            "CONSULTOR": ["João", "João", "Maria"],
            "grupo_dashboard": ["CNC", None, "CNC"],
            "VALOR": [1000.0, 0.0, 500.0],
            "TIPO_PRODUTO": ["CNC", "BMG MED", "CNC"],
            "is_bmg_med": [False, True, False],
        })
        distrib, _, numero = calcular_distribuicao_produtos(df)
        assert "BMG Med" in numero
        joao = distrib[distrib["CONSULTOR"] == "João"].iloc[0]
        assert joao["BMG Med"] == 1
