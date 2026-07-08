"""
Testes dos calculadores puros de ``src/dashboard/ui/prioridades_acao.py``
(``calcular_aceleradores_consultor``).

Streamlit importa em modo bare (sem servidor); as funções de cálculo são
puras e não chamam ``st.*``.
"""
import pandas as pd
import pytest

from src.dashboard.ui.prioridades_acao import calcular_aceleradores_consultor


@pytest.fixture
def df_aceleradores():
    """João vendeu BMG Med; Maria zerada no acelerador; Amos é Vai e Vem."""
    return pd.DataFrame({
        "LOJA": ["A", "B", "VAI E VEM"],
        "CONSULTOR": ["João", "Maria", "Amos"],
        "VALOR": [1000.0, 500.0, 800.0],
        "is_bmg_med": [True, False, False],
    })


@pytest.mark.unit
class TestCalcularAceleradoresConsultor:
    def test_zerados_priorizados(self, df_aceleradores):
        r = calcular_aceleradores_consultor(df_aceleradores, pd.DataFrame())
        bmg = next(a for a in r if a["produto"] == "BMG_MED")
        assert bmg["tem_zeros"]
        zerados = [c["consultor"] for c in bmg["todos_zeros"]]
        assert "Maria" in zerados

    def test_exclui_supervisores(self, df_aceleradores):
        sup = pd.DataFrame({"SUPERVISOR": ["Maria"]})
        r = calcular_aceleradores_consultor(df_aceleradores, sup)
        bmg = next(a for a in r if a["produto"] == "BMG_MED")
        nomes = [c["consultor"] for c in bmg["consultores"]]
        assert "Maria" not in nomes

    def test_exclui_loja_backoffice(self, df_aceleradores):
        # Amos (Vai e Vem) não aparece zerado nem entra na média da
        # organização: média BMG Med = 1/2 consultores (não 1/3).
        r = calcular_aceleradores_consultor(df_aceleradores, pd.DataFrame())
        bmg = next(a for a in r if a["produto"] == "BMG_MED")
        todos = [c["consultor"] for c in bmg["todos_zeros"] + bmg["consultores"]]
        assert "Amos" not in todos
        assert bmg["consultores"][0]["media_org"] == pytest.approx(0.5)

    def test_df_vazio(self):
        assert calcular_aceleradores_consultor(pd.DataFrame(), None) == []
