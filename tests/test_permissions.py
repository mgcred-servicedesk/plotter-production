"""Testes da matriz de permissoes de UI.

`src/dashboard/permissions.py` centraliza quem ve o que no dashboard.
"""
import pandas as pd
import pytest

from src.dashboard.pages.detalhes_cards import (
    _agregar_digitacao_diaria,
    _dimensao_por_perfil,
)
from src.dashboard.permissions import pode_ver


@pytest.mark.unit
class TestCardsMediasConsultorLoja:
    def test_admin_gestor_e_gerente_veem(self):
        for perfil in ("admin", "gestor", "gerente_comercial"):
            assert pode_ver("cards_medias_consultor_loja", perfil) is True

    def test_supervisor_e_consultor_nao_veem(self):
        for perfil in ("supervisor", "consultor"):
            assert pode_ver("cards_medias_consultor_loja", perfil) is False

    def test_perfil_nulo_nao_ve(self):
        assert pode_ver("cards_medias_consultor_loja", None) is False

    def test_elemento_inexistente_fail_closed(self):
        assert pode_ver("elemento_que_nao_existe", "admin") is False


@pytest.mark.unit
class TestDimensaoPorPerfil:
    def test_admin_e_gestor_usam_regiao(self):
        for perfil in ("admin", "gestor"):
            assert _dimensao_por_perfil(perfil) == "REGIAO"

    def test_gerente_comercial_usa_loja(self):
        assert _dimensao_por_perfil("gerente_comercial") == "LOJA"

    def test_perfil_desconhecido_default_regiao(self):
        assert _dimensao_por_perfil("supervisor") == "REGIAO"
        assert _dimensao_por_perfil(None) == "REGIAO"


@pytest.mark.unit
class TestAgregarDigitacaoDiaria:
    def test_agrega_por_data(self):
        df = pd.DataFrame(
            {
                "DATA_CADASTRO": pd.to_datetime(
                    ["2026-06-01", "2026-06-01", "2026-06-02"]
                ),
                "LOJA": ["L1", "L1", "L2"],
                "grupo_dashboard": ["CNC", "SAQUE", "CNC"],
                "VALOR": [1000.0, 500.0, 800.0],
                "qtd_digitada": [10, 5, 8],
            }
        )
        res = _agregar_digitacao_diaria(df)
        assert list(res.columns) == [
            "data_cadastro", "qtd_digitada", "valor_digitado",
        ]
        assert len(res) == 2
        dia1 = res[res["data_cadastro"] == "2026-06-01"].iloc[0]
        assert dia1["qtd_digitada"] == 15
        assert dia1["valor_digitado"] == pytest.approx(1500.0)

    def test_df_vazio(self):
        res = _agregar_digitacao_diaria(pd.DataFrame())
        assert res.empty
        assert list(res.columns) == [
            "data_cadastro", "qtd_digitada", "valor_digitado",
        ]

    def test_serie_reflete_apenas_o_escopo_recebido(self):
        # Regressao do vazamento: a serie "Ultimos 7 Dias" deriva do
        # detalhe JA recortado por RLS. Se alimentada com o subconjunto de
        # uma regiao, os totais diarios refletem SO essa regiao — nunca o
        # agregado global.
        detalhe_global = pd.DataFrame(
            {
                "DATA_CADASTRO": pd.to_datetime(
                    ["2026-06-01", "2026-06-01"]
                ),
                "REGIAO": ["R1", "R2"],
                "LOJA": ["L1", "L2"],
                "grupo_dashboard": ["CNC", "CNC"],
                "VALOR": [1000.0, 4000.0],
                "qtd_digitada": [10, 40],
            }
        )
        escopo_r1 = detalhe_global[detalhe_global["REGIAO"] == "R1"]
        res = _agregar_digitacao_diaria(escopo_r1)
        dia = res.iloc[0]
        # So R1 (1000 / 10) — NAO o global (5000 / 50).
        assert dia["valor_digitado"] == pytest.approx(1000.0)
        assert dia["qtd_digitada"] == 10
