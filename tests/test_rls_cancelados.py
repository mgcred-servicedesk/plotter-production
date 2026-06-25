"""
RLS dos cancelados + features de contenção (oportunidades perdidas
e assertividade).

Garante que, após ``aplicar_rls``, cada perfil só enxerga as próprias
linhas — incluindo as colunas novas ``CLASSIFICACAO`` e
``RECUPERADA_OUTRO`` — e que as funções derivadas não vazam dados de
outros usuários. O matching cross-consultor é global no SQL, mas o
RESULTADO exibido tem de respeitar o escopo do perfil.
"""
import pandas as pd
import pytest

import src.dashboard.rls as rls_mod
from src.dashboard.kpis.gerais import (
    calcular_assertividade_consultores,
    calcular_oportunidades_perdidas,
)
from src.dashboard.rls import aplicar_rls


@pytest.fixture
def df_cancelados_2_consultores():
    """Cancelados de A (loja L1/reg R1) e B (loja L2/reg R2).

    Cada consultor tem 1 oportunidade perdida (recuperada_outro).
    """
    return pd.DataFrame({
        "CONSULTOR": ["A", "A", "B", "B"],
        "LOJA": ["L1", "L1", "L2", "L2"],
        "REGIAO": ["R1", "R1", "R2", "R2"],
        "VALOR": [1000.0, 500.0, 800.0, 300.0],
        "CLASSIFICACAO": [
            "liquido", "recuperada", "liquido", "recuperada",
        ],
        "RECUPERADA_OUTRO": [False, True, False, True],
        "RECUPERADA_OUTRA_LOJA": [False, True, False, False],
        "RECUPERADA_OUTRA_REGIAO": [False, False, False, True],
    })


def _set_perfil(monkeypatch, perfil, escopo):
    monkeypatch.setattr(
        rls_mod,
        "_obter_perfil_efetivo",
        lambda: {"perfil": perfil, "escopo": escopo},
    )


@pytest.mark.unit
class TestRlsCanceladosIsolamento:
    def test_consultor_so_ve_proprias_linhas(
        self, monkeypatch, df_cancelados_2_consultores
    ):
        _set_perfil(monkeypatch, "consultor", ["A"])
        post = aplicar_rls(df_cancelados_2_consultores)
        assert set(post["CONSULTOR"].unique()) == {"A"}
        # Nenhuma linha de B vaza (nome nem valor).
        assert "B" not in post["CONSULTOR"].values
        assert 800.0 not in post["VALOR"].values
        assert 300.0 not in post["VALOR"].values

    def test_oportunidade_perdida_so_do_proprio_consultor(
        self, monkeypatch, df_cancelados_2_consultores
    ):
        _set_perfil(monkeypatch, "consultor", ["A"])
        post = aplicar_rls(df_cancelados_2_consultores)
        r = calcular_oportunidades_perdidas(post)
        # A tem 1 perdida no valor da PROPRIA proposta (500), nunca 300 (de B).
        assert r["qtd_perdidas"] == 1
        assert r["valor_perdido"] == pytest.approx(500.0)

    def test_consultor_b_isolado_simetricamente(
        self, monkeypatch, df_cancelados_2_consultores
    ):
        _set_perfil(monkeypatch, "consultor", ["B"])
        post = aplicar_rls(df_cancelados_2_consultores)
        r = calcular_oportunidades_perdidas(post)
        assert set(post["CONSULTOR"].unique()) == {"B"}
        assert r["qtd_perdidas"] == 1
        assert r["valor_perdido"] == pytest.approx(300.0)

    def test_supervisor_filtra_por_loja(
        self, monkeypatch, df_cancelados_2_consultores
    ):
        _set_perfil(monkeypatch, "supervisor", ["L1"])
        post = aplicar_rls(df_cancelados_2_consultores)
        assert set(post["LOJA"].unique()) == {"L1"}
        assert "B" not in post["CONSULTOR"].values

    def test_supervisor_oportunidade_por_loja(
        self, monkeypatch, df_cancelados_2_consultores
    ):
        # Supervisor usa o flag de OUTRA loja, restrito a sua loja.
        _set_perfil(monkeypatch, "supervisor", ["L1"])
        post = aplicar_rls(df_cancelados_2_consultores)
        r = calcular_oportunidades_perdidas(
            post, "RECUPERADA_OUTRA_LOJA"
        )
        # So a linha de L1 capturada por outra loja (500) conta.
        assert r["qtd_perdidas"] == 1
        assert r["valor_perdido"] == pytest.approx(500.0)
        # Nao vaza a oportunidade de B (regiao), que e de L2.
        assert 300.0 not in post["VALOR"].values

    def test_gerente_filtra_por_regiao(
        self, monkeypatch, df_cancelados_2_consultores
    ):
        _set_perfil(monkeypatch, "gerente_comercial", ["R1"])
        post = aplicar_rls(df_cancelados_2_consultores)
        assert set(post["REGIAO"].unique()) == {"R1"}

    def test_admin_ve_tudo(
        self, monkeypatch, df_cancelados_2_consultores
    ):
        _set_perfil(monkeypatch, "admin", [])
        post = aplicar_rls(df_cancelados_2_consultores)
        assert len(post) == 4

    def test_assertividade_nao_vaza_outro_consultor(
        self, monkeypatch, df_cancelados_2_consultores
    ):
        # Pagos/análise de ambos; após RLS p/ A, só A deve aparecer.
        df_pagos = pd.DataFrame({
            "CONSULTOR": ["A", "B"],
            "LOJA": ["L1", "L2"],
            "REGIAO": ["R1", "R2"],
            "VALOR": [1.0, 1.0],
        })
        df_analise = df_pagos.copy()
        _set_perfil(monkeypatch, "consultor", ["A"])
        canc = aplicar_rls(df_cancelados_2_consultores)
        pagos = aplicar_rls(df_pagos)
        analise = aplicar_rls(df_analise)
        res = calcular_assertividade_consultores(canc, pagos, analise)
        consultores = set(res["por_consultor"]["CONSULTOR"].unique())
        assert consultores == {"A"}
        assert "B" not in consultores


@pytest.mark.unit
class TestRlsFailClosed:
    def test_consultor_sem_escopo_nao_ve_nada(
        self, monkeypatch, df_cancelados_2_consultores
    ):
        # Escopo vazio em perfil nao-admin => DataFrame vazio (nunca a base).
        _set_perfil(monkeypatch, "consultor", [])
        post = aplicar_rls(df_cancelados_2_consultores)
        assert post.empty

    def test_supervisor_sem_escopo_nao_ve_nada(
        self, monkeypatch, df_cancelados_2_consultores
    ):
        _set_perfil(monkeypatch, "supervisor", [])
        post = aplicar_rls(df_cancelados_2_consultores)
        assert post.empty

    def test_perfil_desconhecido_nao_ve_nada(
        self, monkeypatch, df_cancelados_2_consultores
    ):
        _set_perfil(monkeypatch, "qualquer_coisa", ["A"])
        post = aplicar_rls(df_cancelados_2_consultores)
        assert post.empty

    def test_coluna_escopo_ausente_nao_ve_nada(self, monkeypatch):
        # Consultor com escopo, mas df sem a coluna CONSULTOR => vazio.
        df = pd.DataFrame({"VALOR": [1.0, 2.0]})
        _set_perfil(monkeypatch, "consultor", ["A"])
        post = aplicar_rls(df)
        assert post.empty

    def test_admin_sem_escopo_ve_tudo(
        self, monkeypatch, df_cancelados_2_consultores
    ):
        # Admin/gestao mantem visao global mesmo sem escopo.
        _set_perfil(monkeypatch, "admin", [])
        post = aplicar_rls(df_cancelados_2_consultores)
        assert len(post) == 4
