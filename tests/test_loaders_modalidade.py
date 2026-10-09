"""Modalidade (NORMAL/FLEX) da tabela nas propostas dos Analiticos.

A modalidade e resolvida no banco (migration 135: versao mensal da
tabela pelo mes de cadastro, com fallback) e so trafega pelos loaders.
O que exige teste aqui e o transporte: a coluna precisa sair no
``select`` da view de pagos e nas chaves das RPCs *_json de em analise
e cancelados — e nao pode ser confundida com TIPO OPER. (Contrato
Novo/Refin...), que e outro dado.

Nenhuma conexao e aberta: ``_sb``, ``carregar_periodo`` e
``_paginar_keyset`` sao substituidos por fakes em memoria.
"""
import pytest

from src.dashboard import loaders


class _Resposta:
    def __init__(self, data):
        self.data = data


@pytest.fixture
def pagos(monkeypatch):
    """Roda _fetch_contratos_pagos sobre linhas fixas, guardando o select."""
    capturado = {}

    def paginar(montar, _cursor):
        montar(10)  # executa o builder para capturar o select
        return capturado["linhas"]

    class _Builder:
        def from_(self, _t):
            return self

        def select(self, colunas):
            capturado["select"] = colunas
            return self

        def eq(self, *_a):
            return self

        def order(self, *_a):
            return self

        def limit(self, *_a):
            return self

    monkeypatch.setattr(loaders, "_sb", lambda: _Builder())
    monkeypatch.setattr(
        loaders, "carregar_periodo", lambda _m, _a: {"id": "per-10-2026"}
    )
    monkeypatch.setattr(loaders, "_paginar_keyset", paginar)

    def rodar(linhas):
        capturado["linhas"] = linhas
        df = loaders._fetch_contratos_pagos(10, 2026)
        return df, capturado["select"]

    return rodar


@pytest.fixture
def rpc(monkeypatch):
    class _Rpc:
        def __init__(self, dados):
            self.dados = dados

        def rpc(self, _nome, _params):
            return self

        def execute(self):
            return _Resposta(self.dados)

    def instalar(dados):
        monkeypatch.setattr(loaders, "_sb", lambda: _Rpc(dados))

    return instalar


class TestPagos:
    def test_select_da_view_pede_modalidade(self, pagos):
        _, select = pagos([])

        colunas = select.split(",")
        assert "modalidade" in colunas
        assert "modalidade_fallback" in colunas

    def test_modalidade_vira_coluna_propria_sem_tocar_tipo_oper(self, pagos):
        df, _ = pagos(
            [
                {
                    "contrato_id": 1,
                    "tipo_operacao": "Contrato Novo",
                    "modalidade": "FLEX",
                    "modalidade_fallback": False,
                    "valor_consolidado": 100,
                    "valor": 100,
                },
                {
                    "contrato_id": 2,
                    "tipo_operacao": "Refinanciamento",
                    "modalidade": "SEM TABELA",
                    "modalidade_fallback": True,
                    "valor_consolidado": 50,
                    "valor": 50,
                },
            ]
        )

        assert list(df["MODALIDADE"]) == ["FLEX", "SEM TABELA"]
        assert list(df["TIPO OPER."]) == ["Contrato Novo", "Refinanciamento"]
        assert list(df["MODALIDADE_FALLBACK"]) == [False, True]


class TestRpcsJson:
    _LINHA = {
        "contrato_id": 7,
        "valor": 100,
        "tipo_operacao": "Portabilidade",
        "modalidade": "NORMAL",
        "modalidade_fallback": True,
        "categoria_codigo": "CNC",
        "classificacao": "liquido",
    }

    def test_em_analise_carrega_modalidade(self, rpc):
        rpc([dict(self._LINHA)])

        df = loaders._fetch_contratos_em_analise(10, 2026)

        assert list(df["MODALIDADE"]) == ["NORMAL"]
        assert list(df["MODALIDADE_FALLBACK"]) == [True]
        assert list(df["TIPO OPER."]) == ["Portabilidade"]

    def test_cancelados_carrega_modalidade(self, rpc):
        rpc([dict(self._LINHA)])

        df = loaders._fetch_contratos_cancelados(10, 2026)

        assert list(df["MODALIDADE"]) == ["NORMAL"]
        assert list(df["MODALIDADE_FALLBACK"]) == [True]

    def test_rpc_sem_a_chave_fica_vazio_e_nao_vira_normal(self, rpc):
        """RPC antiga (antes da 135) nao pode produzir NORMAL de mentira."""
        linha = dict(self._LINHA)
        del linha["modalidade"]
        del linha["modalidade_fallback"]
        rpc([linha])

        df = loaders._fetch_contratos_em_analise(10, 2026)

        assert df["MODALIDADE"].isna().all()
