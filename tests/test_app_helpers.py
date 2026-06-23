"""
Testes dos helpers puros de ``app.py`` (``_ritmo_organizacao``,
``_serie_diaria_pago``).

``app.py`` importa Streamlit em modo bare; ambos os helpers são puros
(não chamam ``st.*``).
"""
import pandas as pd
import pytest

from app import _ritmo_organizacao, _serie_diaria_pago


@pytest.mark.unit
class TestRitmoOrganizacao:
    def test_perfil_sem_referencia(self):
        df = pd.DataFrame({"REGIAO": ["R1"], "LOJA": ["A"], "VALOR": [1.0]})
        assert _ritmo_organizacao(
            "gerente_comercial", df, df, pd.DataFrame()
        ) == (None, 1)
        assert _ritmo_organizacao("admin", df, df, pd.DataFrame()) == (None, 1)

    def test_supervisor_normaliza_por_lojas(self):
        df_f = pd.DataFrame({"REGIAO": ["R1"], "LOJA": ["A"]})
        df_full = pd.DataFrame({
            "REGIAO": ["R1", "R1", "R2"],
            "LOJA": ["A", "B", "C"],
        })
        df_reg, norm = _ritmo_organizacao(
            "supervisor", df_f, df_full, pd.DataFrame()
        )
        assert norm == 2  # lojas A, B em R1
        assert set(df_reg["LOJA"]) == {"A", "B"}

    def test_consultor_exclui_supervisores(self):
        df_f = pd.DataFrame({"REGIAO": ["R1"], "CONSULTOR": ["X"]})
        df_full = pd.DataFrame({
            "REGIAO": ["R1", "R1", "R1"],
            "CONSULTOR": ["X", "Y", "S"],
        })
        df_sup = pd.DataFrame({"SUPERVISOR": ["S"]})
        _df_reg, norm = _ritmo_organizacao("consultor", df_f, df_full, df_sup)
        assert norm == 2  # X, Y (S é supervisor, excluído)

    def test_df_vazio(self):
        empty = pd.DataFrame()
        assert _ritmo_organizacao("supervisor", empty, empty, empty) == (
            None, 1
        )


@pytest.mark.unit
class TestSerieDiariaPago:
    def test_serie_com_dois_ou_mais_dias(self):
        df = pd.DataFrame({
            "DATA": pd.to_datetime(
                ["2026-06-01", "2026-06-01", "2026-06-02"]
            ),
            "VALOR": [100.0, 50.0, 200.0],
        })
        assert _serie_diaria_pago(df) == [150.0, 200.0]

    def test_um_dia_retorna_none(self):
        df = pd.DataFrame({
            "DATA": pd.to_datetime(["2026-06-01"]),
            "VALOR": [100.0],
        })
        assert _serie_diaria_pago(df) is None

    def test_sem_data_ou_vazio(self):
        assert _serie_diaria_pago(pd.DataFrame({"VALOR": [1.0]})) is None
        assert _serie_diaria_pago(pd.DataFrame()) is None
