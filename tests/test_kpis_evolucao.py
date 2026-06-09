"""
Testes da evolução diária de vendas e pontos
(``src/dashboard/kpis/evolucao.py``).
"""
import pandas as pd
import pytest

from src.dashboard.kpis.evolucao import calcular_evolucao_diaria


@pytest.mark.unit
class TestCalcularEvolucaoDiaria:
    def test_sem_coluna_data_retorna_vazio(self):
        df = pd.DataFrame({"VALOR": [100.0], "pontos": [10.0]})
        assert calcular_evolucao_diaria(df, 2026, 3).empty

    def test_agrega_por_dia_e_acumula(self):
        df = pd.DataFrame({
            "DATA": ["2026-03-02", "2026-03-01", "2026-03-01"],
            "VALOR": [500.0, 1000.0, 200.0],
            "pontos": [50.0, 100.0, 20.0],
        })
        ev = calcular_evolucao_diaria(df, 2026, 3)

        # Um registro por dia, ordenado cronologicamente
        assert len(ev) == 2
        assert list(ev["DATA"].dt.day) == [1, 2]

        # Dia 01 agrega as duas linhas: VALOR 1200, pontos 120
        dia1 = ev.iloc[0]
        assert dia1["VALOR"] == pytest.approx(1200.0)
        assert dia1["pontos"] == pytest.approx(120.0)

        # Acumulados
        assert list(ev["Valor Acumulado"]) == pytest.approx([1200.0, 1700.0])
        assert list(ev["Pontos Acumulados"]) == pytest.approx([120.0, 170.0])
