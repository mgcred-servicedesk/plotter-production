"""Foto mensal FDR: paginacao, isolamento de periodo, RLS e falhas."""
from unittest.mock import Mock

import pandas as pd
import pytest

from src.dashboard import loaders
from src.dashboard import rls
from tests.conftest import ClienteFakePaginado, QueryFakePaginada


class QueryPeriodo(QueryFakePaginada):
    """Acrescenta filtros reais ao duplo canonico de paginacao."""

    def eq(self, coluna, valor):
        self._linhas = [r for r in self._linhas if r[coluna] == valor]
        return self


class ClientePeriodo(ClienteFakePaginado):
    def __init__(self, linhas):
        super().__init__(linhas, chave="co_adesao")

    def from_(self, nome):
        assert nome == "v_fim_relacionamento_liga"
        self.paginas += 1
        return QueryPeriodo(self.linhas, self.chave)


def _linha(ade, **extra):
    return {
        "co_adesao": ade, "ano": 2026, "mes": 10, "qtde": ade % 2,
        "data_contrato": "2026-06-03",
        "data_fim_relacionamento": "2026-08-16",
        "loja": "L1", "regiao": "R1", "consultor": "ANA",
        **extra,
    }


@pytest.fixture(autouse=True)
def _cache_limpo(monkeypatch):
    loaders._fim_relacionamento_liga_atual.clear()
    loaders._fim_relacionamento_liga_historico.clear()
    monkeypatch.setattr(loaders, "_eh_mes_atual", lambda m, a: True)
    monkeypatch.setattr(
        rls, "_obter_perfil_efetivo",
        lambda: {"perfil": "admin", "escopo": []},
    )
    yield
    loaders._fim_relacionamento_liga_atual.clear()
    loaders._fim_relacionamento_liga_historico.clear()


def _cliente(monkeypatch, linhas):
    cliente = ClientePeriodo(linhas)
    monkeypatch.setattr(loaders, "_sb", lambda: cliente)
    return cliente


@pytest.mark.unit
class TestFotoFdr:
    def test_pagina_sem_perder_adesoes_e_isola_competencia(self, monkeypatch):
        total = loaders._PAGE_SIZE + 7
        linhas = [_linha(i) for i in range(1, total + 1)]
        # Mesma ADE em outra competencia nao pode poluir o keyset.
        linhas += [_linha(1, mes=9), _linha(2, ano=2025)]
        cliente = _cliente(monkeypatch, linhas)
        out = loaders.carregar_fim_relacionamento_liga(10, 2026)
        assert out["status"] == "ok"
        assert len(out["clientes"]) == total
        assert out["clientes"]["co_adesao"].nunique() == total
        assert cliente.paginas == 2
        # Data da saida em agosto permanece na foto de outubro.
        assert set(out["clientes"]["data_fim_relacionamento"]) == {
            "2026-08-16",
        }
        assert set(out["clientes"]["qtde"]) == {0, 1}

    def test_carga_pequena_usa_uma_pagina(self, monkeypatch):
        cliente = _cliente(monkeypatch, [_linha(1), _linha(2)])
        assert len(loaders.carregar_fim_relacionamento_liga(10, 2026)[
            "clientes"
        ]) == 2
        assert cliente.paginas == 1

    def test_sem_carga_e_nao_importada(self, monkeypatch):
        _cliente(monkeypatch, [])
        out = loaders.carregar_fim_relacionamento_liga(10, 2026)
        assert out["status"] == "nao_importada"
        assert out["clientes"].empty

    @pytest.mark.parametrize("perfil,escopo", [
        ("consultor", ["ANA"]),
        ("supervisor", ["L1"]),
        ("gerente_comercial", ["R1"]),
    ])
    def test_rls_recorta_antes_do_retorno(self, monkeypatch, perfil, escopo):
        _cliente(monkeypatch, [
            _linha(1),
            _linha(2, loja="L2", regiao="R2", consultor="BRUNO"),
        ])
        monkeypatch.setattr(
            rls, "_obter_perfil_efetivo",
            lambda: {"perfil": perfil, "escopo": escopo},
        )
        out = loaders.carregar_fim_relacionamento_liga(10, 2026)
        assert out["status"] == "ok"
        assert out["clientes"]["co_adesao"].tolist() == [1]

    @pytest.mark.parametrize("perfil", [
        None,
        {"perfil": "desconhecido", "escopo": ["L1"]},
        {"perfil": "supervisor", "escopo": []},
        {"perfil": "supervisor", "escopo": ["L3"]},
    ])
    def test_sem_acesso_nega_sem_confundir_com_sem_carga(
        self, monkeypatch, perfil,
    ):
        _cliente(monkeypatch, [_linha(1)])
        monkeypatch.setattr(rls, "_obter_perfil_efetivo", lambda: perfil)
        out = loaders.carregar_fim_relacionamento_liga(10, 2026)
        assert out["status"] == "ok"
        assert out["clientes"].empty
        assert "co_adesao" in out["clientes"].columns

    def test_perfil_reaplicado_ao_usar_mesmo_cache(self, monkeypatch):
        cliente = _cliente(monkeypatch, [
            _linha(1), _linha(2, consultor="BRUNO"),
        ])
        perfil = {"perfil": "consultor", "escopo": ["ANA"]}
        monkeypatch.setattr(rls, "_obter_perfil_efetivo", lambda: perfil)
        ana = loaders.carregar_fim_relacionamento_liga(10, 2026)
        perfil["escopo"] = ["BRUNO"]
        bruno = loaders.carregar_fim_relacionamento_liga(10, 2026)
        assert ana["clientes"]["co_adesao"].tolist() == [1]
        assert bruno["clientes"]["co_adesao"].tolist() == [2]
        assert cliente.paginas == 1

    def test_erro_nao_vira_vazio_cacheado(self, monkeypatch):
        fetch = Mock(side_effect=[RuntimeError("view indisponivel"),
                                  pd.DataFrame([_linha(1)])])
        monkeypatch.setattr(loaders, "_fetch_fim_relacionamento_liga", fetch)
        primeiro = loaders.carregar_fim_relacionamento_liga(10, 2026)
        segundo = loaders.carregar_fim_relacionamento_liga(10, 2026)
        assert primeiro["status"] == "erro"
        assert primeiro["clientes"].empty
        assert segundo["status"] == "ok"
        assert len(segundo["clientes"]) == 1
        assert fetch.call_count == 2

    @pytest.mark.parametrize("atual", [True, False])
    def test_escolhe_cache_da_competencia(self, monkeypatch, atual):
        monkeypatch.setattr(loaders, "_eh_mes_atual", lambda m, a: atual)
        corrente = Mock(return_value=pd.DataFrame([_linha(1)]))
        historico = Mock(return_value=pd.DataFrame([_linha(2)]))
        monkeypatch.setattr(loaders, "_fim_relacionamento_liga_atual", corrente)
        monkeypatch.setattr(
            loaders, "_fim_relacionamento_liga_historico", historico,
        )
        out = loaders.carregar_fim_relacionamento_liga(10, 2026)
        escolhido = corrente if atual else historico
        outro = historico if atual else corrente
        escolhido.assert_called_once_with(10, 2026)
        outro.assert_not_called()
        assert out["status"] == "ok"
