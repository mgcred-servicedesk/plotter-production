"""
`carregar_reconquista` com a liga (>= 09/2026, migration 127).

Exercita a ORQUESTRACAO — o que nenhum teste de regra pura alcanca:
qual fonte vira `totais["efetivadas"]`, o estado `liga_status`, o
recorte por perfil na liga e o corte do acelerador quando a liga nao
existe. Todas as cargas sao substituidas por frames fixos.
"""
import pandas as pd
import pytest

from src.dashboard import loaders
from src.dashboard.kpis.reconquista import (
    LIGA_ERRO,
    LIGA_FORA,
    LIGA_NAO_IMPORTADA,
    LIGA_OK,
)


def _export(ref_ano, ref_mes):
    """Export do banco: 2 EFETIVADA de ANA no ref pedido."""
    return pd.DataFrame({
        "co_adesao": [1, 2],
        "status": ["EFETIVADA", "EFETIVADA"],
        "flag_elegibilidade": ["ELEGIVEL", "ELEGIVEL"],
        "ref_ano": [ref_ano, ref_ano],
        "ref_mes": [ref_mes, ref_mes],
        "loja": ["L1", "L1"],
        "regiao": ["R1", "R1"],
        "consultor": ["ANA", "ANA"],
        "saldo_contabil": [1.0, 1.0],
        "dias_atraso": [0, 0],
    })


def _liga():
    return pd.DataFrame({
        "co_adesao": [10, 11, 12, 13, 14],
        "qtde": [1, 1, 1, 0, 1],
        "loja": ["L1", "L1", "L2", "L1", "L2"],
        "regiao": ["R1", "R1", "R2", "R1", "R2"],
        "consultor": ["ANA", "ANA", "BRUNO", "ANA", "BRUNO"],
        "ano": [2026] * 5,
        "mes": [9] * 5,
    })


@pytest.fixture
def ambiente(monkeypatch):
    """Substitui toda carga de `carregar_reconquista`.

    `estado["liga"]` controla `_liga_periodo`: um DataFrame, ou uma
    Exception (falha de leitura). `estado["perfil"]` e o perfil logado;
    `estado["filtro"]` o recorte de RLS (None = global).
    """
    estado = {
        "liga": _liga(),
        "perfil": {"perfil": "consultor"},
        "filtro": None,
    }

    def _cache(mes, ano):
        ref_mes, ref_ano = loaders._mes_apuracao_anterior(mes, ano)
        return {
            "ref_mes": ref_mes, "ref_ano": ref_ano,
            "clientes": _export(ref_ano, ref_mes),
            "clientes_ant": pd.DataFrame(),
            "clientes_prox": pd.DataFrame(),
        }

    def _liga_periodo(mes, ano):
        if isinstance(estado["liga"], Exception):
            raise estado["liga"]
        return estado["liga"]

    monkeypatch.setattr(loaders, "_reconquista_cache", _cache)
    monkeypatch.setattr(
        loaders, "_reconquista_todos", lambda: _export(2026, 8)
    )
    monkeypatch.setattr(loaders, "_liga_periodo", _liga_periodo)
    monkeypatch.setattr(
        loaders, "_filtro_rls_reconquista", lambda: estado["filtro"]
    )
    monkeypatch.setattr(
        loaders, "_filtrar_rls_reconquista", lambda dados: dados
    )
    monkeypatch.setattr(
        loaders, "_obter_perfil_efetivo", lambda: estado["perfil"]
    )
    monkeypatch.setattr(loaders, "aplicar_rls", lambda df: df)
    monkeypatch.setattr(
        loaders, "carregar_cobranca_consignavel",
        lambda mes, ano: pd.DataFrame({"CONSULTOR": ["ANA"]}),
    )
    monkeypatch.setattr(
        loaders, "carregar_supervisores",
        lambda mes, ano: pd.DataFrame(columns=["SUPERVISOR"]),
    )
    monkeypatch.setattr(
        loaders, "carregar_consultores_ativos",
        lambda: pd.DataFrame({"CONSULTOR": ["ANA", "BRUNO"]}),
    )
    monkeypatch.setattr(
        loaders, "carregar_faixa_acelerador",
        lambda qtd, mes, ano: {
            "rotulo": f"faixa-{qtd}", "is_fallback": False,
            "is_deflator": False,
        },
    )
    return estado


@pytest.mark.unit
class TestCarregarReconquistaLiga:
    def test_setembro_conta_pela_liga_sem_defasagem(self, ambiente):
        out = loaders.carregar_reconquista(9, 2026)
        t = out["totais"]
        assert t["liga_status"] == LIGA_OK
        # 4 com qtde 1 na liga — NAO as 2 EFETIVADA do export (ago).
        assert t["efetivadas"] == 4
        assert t["liga_nao_contabilizadas"] == 1
        assert len(out["liga"]) == 5

    def test_acelerador_por_consultor_usa_a_liga(self, ambiente):
        out = loaders.carregar_reconquista(9, 2026)
        pc = out["por_consultor"].set_index("consultor")
        assert pc.loc["ANA", "efetivadas"] == 2       # liga, nao export
        assert pc.loc["ANA", "cobranca_consignavel"] == 1
        assert pc.loc["BRUNO", "efetivadas"] == 2
        # faixa agregada = efetivadas da liga + consignavel
        assert out["totais"]["faixa_agregada"]["rotulo"] == "faixa-5"

    def test_agosto_segue_a_regra_antiga(self, ambiente):
        # Ler a liga em agosto viraria LIGA_ERRO e o teste acusaria.
        ambiente["liga"] = AssertionError("agosto nao deveria ler a liga")
        out = loaders.carregar_reconquista(8, 2026)
        t = out["totais"]
        assert t["liga_status"] == LIGA_FORA
        assert t["efetivadas"] == 2  # EFETIVADA do export
        assert out["liga"].empty

    def test_liga_nao_importada_nao_vira_zero_nem_faixa(self, ambiente):
        ambiente["liga"] = pd.DataFrame()
        out = loaders.carregar_reconquista(9, 2026)
        t = out["totais"]
        assert t["liga_status"] == LIGA_NAO_IMPORTADA
        # Sem faixa nem quebra: seria calculada com efetivadas = 0.
        assert t["faixa_agregada"] is None
        assert out["por_consultor"].empty

    def test_falha_de_leitura_vira_estado_de_erro(self, ambiente):
        ambiente["liga"] = RuntimeError("view ausente")
        out = loaders.carregar_reconquista(9, 2026)
        t = out["totais"]
        assert t["liga_status"] == LIGA_ERRO
        assert t["faixa_agregada"] is None
        assert out["por_consultor"].empty

    def test_rls_recorta_a_liga(self, ambiente):
        """Consultor so ve (e so conta) a propria liga."""
        ambiente["filtro"] = lambda df: df[df["consultor"] == "BRUNO"]
        out = loaders.carregar_reconquista(9, 2026)
        assert out["totais"]["efetivadas"] == 2
        assert set(out["liga"]["consultor"]) == {"BRUNO"}
        assert out["totais"]["liga_status"] == LIGA_OK

    def test_rls_que_esvazia_a_liga_e_zero_legitimo(self, ambiente):
        """Liga importada, mas nada no escopo: 0 de verdade, nao
        "nao importada"."""
        ambiente["filtro"] = lambda df: df.iloc[0:0]
        out = loaders.carregar_reconquista(9, 2026)
        assert out["totais"]["liga_status"] == LIGA_OK
        assert out["totais"]["efetivadas"] == 0
