"""
`carregar_prestamista_cnc` (migration 134) — orquestracao e RLS.

As cargas (`_prestamista_periodo`, `_meta_prestamista`) sao substituidas
por frames fixos; o recorte por perfil e o REAL (`rls.decidir_rls`), so
o perfil logado e injetado — o teste falha se um perfil enxergar linha
de outro escopo.
"""
import pandas as pd
import pytest

from src.dashboard import loaders
from src.dashboard import rls as rls_mod
from src.dashboard.kpis.prestamista import (
    PRESTAMISTA_ERRO,
    PRESTAMISTA_NAO_IMPORTADO,
    PRESTAMISTA_OK,
)

META = {"meta_ipv": 0.8, "faixa_alerta": 0.6, "is_fallback": False}


def _base():
    return pd.DataFrame({
        "co_adesao": [1, 2, 3, 4],
        "qtd_elegivel": [1, 1, 1, 1],
        "qtd_seguro": [1, 0, 1, 1],
        "status_apolice": ["Aprovado", None, "Aprovado", "Aprovado"],
        "regiao": ["R1", "R1", "R2", "R2"],
        "loja": ["L1", "L1", "L2", "L3"],
        "consultor": ["ANA", "BIA", "CAU", "DUDA"],
    })


@pytest.fixture
def ambiente(monkeypatch):
    estado = {"base": _base(), "meta": META, "perfil": {"perfil": "admin"}}

    def _periodo(mes, ano):
        if isinstance(estado["base"], Exception):
            raise estado["base"]
        return estado["base"]

    def _meta(mes, ano):
        if isinstance(estado["meta"], Exception):
            raise estado["meta"]
        return estado["meta"]

    monkeypatch.setattr(loaders, "_prestamista_periodo", _periodo)
    monkeypatch.setattr(loaders, "_meta_prestamista", _meta)
    monkeypatch.setattr(
        rls_mod, "_obter_perfil_efetivo", lambda: estado["perfil"]
    )
    return estado


@pytest.mark.unit
class TestRecortePorPerfil:
    @pytest.mark.parametrize("role", ["admin", "gestor"])
    def test_global_ve_tudo(self, ambiente, role):
        ambiente["perfil"] = {"perfil": role, "escopo": []}
        d = loaders.carregar_prestamista_cnc(10, 2026)
        assert d["status"] == PRESTAMISTA_OK
        assert d["totais"]["elegiveis"] == 4
        assert d["totais"]["ipv"] == pytest.approx(0.75)

    @pytest.mark.parametrize("perfil,esperado", [
        ({"perfil": "gerente_comercial", "escopo": ["R2"]}, {"CAU", "DUDA"}),
        ({"perfil": "supervisor", "escopo": ["L1"]}, {"ANA", "BIA"}),
        ({"perfil": "consultor", "escopo": ["BIA"]}, {"BIA"}),
    ])
    def test_escopo_recorta_propostas_e_totais(self, ambiente, perfil, esperado):
        ambiente["perfil"] = perfil
        d = loaders.carregar_prestamista_cnc(10, 2026)
        assert set(d["propostas"]["consultor"]) == esperado
        assert d["totais"]["elegiveis"] == len(esperado)

    @pytest.mark.parametrize("perfil", [
        None,
        {"perfil": "supervisor", "escopo": []},
        {"perfil": "desconhecido", "escopo": ["L1"]},
    ])
    def test_sem_informacao_nega(self, ambiente, perfil):
        ambiente["perfil"] = perfil
        d = loaders.carregar_prestamista_cnc(10, 2026)
        assert d["propostas"].empty
        assert d["totais"]["ipv"] is None


@pytest.mark.unit
class TestEstados:
    def test_periodo_sem_linhas_e_nao_importado(self, ambiente):
        ambiente["base"] = pd.DataFrame()
        d = loaders.carregar_prestamista_cnc(10, 2026)
        assert d["status"] == PRESTAMISTA_NAO_IMPORTADO

    def test_falha_de_leitura_vira_erro_nao_zero(self, ambiente):
        ambiente["base"] = RuntimeError("timeout")
        d = loaders.carregar_prestamista_cnc(10, 2026)
        assert d["status"] == PRESTAMISTA_ERRO
        assert d["totais"]["ipv"] is None

    def test_escopo_vazio_em_periodo_importado_e_ok(self, ambiente):
        ambiente["perfil"] = {"perfil": "supervisor", "escopo": ["L9"]}
        d = loaders.carregar_prestamista_cnc(10, 2026)
        assert d["status"] == PRESTAMISTA_OK
        assert d["totais"]["propostas"] == 0

    def test_falha_na_meta_nao_derruba_o_ipv(self, ambiente):
        ambiente["meta"] = RuntimeError("rpc")
        d = loaders.carregar_prestamista_cnc(10, 2026)
        assert d["meta"] is None and d["meta_erro"] is True
        assert d["totais"]["ipv"] == pytest.approx(0.75)
