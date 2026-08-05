"""
Testes do helper puro ``_opcoes_consultor`` de
``src/dashboard/ui/sidebar.py``.

Streamlit importa em modo bare (sem servidor); o helper é uma função
pura sobre DataFrames e não chama ``st.*``.
"""
import pandas as pd
import pytest

from src.dashboard.ui.sidebar import _opcoes_consultor


@pytest.mark.unit
class TestOpcoesConsultor:
    def test_uniao_com_universo_traz_consultor_sem_producao_no_periodo(self):
        """Caso do bug: consultor ativo na loja mas sem venda no período
        não pode sumir do filtro só porque `df_source` (vendas do
        período) não tem nenhuma linha dele."""
        df_source = pd.DataFrame({"CONSULTOR": ["Camilly"]})
        df_universo = pd.DataFrame(
            {"CONSULTOR": ["Camilly", "João", "Maria"]}
        )
        df_sup = pd.DataFrame(columns=["SUPERVISOR"])

        resultado = _opcoes_consultor(df_source, df_sup, df_universo)

        assert resultado == ["Camilly", "João", "Maria"]

    def test_sem_universo_usa_so_df_source(self):
        df_source = pd.DataFrame({"CONSULTOR": ["Bela", "Ana"]})
        df_sup = pd.DataFrame(columns=["SUPERVISOR"])

        resultado = _opcoes_consultor(df_source, df_sup, df_universo=None)

        assert resultado == ["Ana", "Bela"]

    def test_exclui_supervisores_de_ambas_as_fontes(self):
        df_source = pd.DataFrame({"CONSULTOR": ["Camilly", "Chefe"]})
        df_universo = pd.DataFrame({"CONSULTOR": ["Camilly", "Chefe", "Zeca"]})
        df_sup = pd.DataFrame({"SUPERVISOR": ["Chefe"]})

        resultado = _opcoes_consultor(df_source, df_sup, df_universo)

        assert resultado == ["Camilly", "Zeca"]

    def test_universo_vazio_nao_quebra(self):
        df_source = pd.DataFrame({"CONSULTOR": ["Ana"]})
        df_sup = pd.DataFrame(columns=["SUPERVISOR"])

        resultado = _opcoes_consultor(df_source, df_sup, pd.DataFrame())

        assert resultado == ["Ana"]

    def test_sem_coluna_consultor_em_nenhuma_fonte_devolve_vazio(self):
        df_source = pd.DataFrame({"OUTRA": [1]})
        df_sup = pd.DataFrame(columns=["SUPERVISOR"])

        resultado = _opcoes_consultor(df_source, df_sup, pd.DataFrame({"OUTRA": [1]}))

        assert resultado == []

    def test_duplicatas_entre_source_e_universo_nao_repetem(self):
        df_source = pd.DataFrame({"CONSULTOR": ["Ana", "Ana"]})
        df_universo = pd.DataFrame({"CONSULTOR": ["Ana"]})
        df_sup = pd.DataFrame(columns=["SUPERVISOR"])

        resultado = _opcoes_consultor(df_source, df_sup, df_universo)

        assert resultado == ["Ana"]
