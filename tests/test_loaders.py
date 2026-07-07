"""
Testes dos helpers puros de ``src/dashboard/loaders.py``
(``_mes_apuracao_seguinte``, ``_reanexar_regiao``,
``carregar_universo_lojas`` com fontes monkeypatched).

O cliente Supabase (``_sb()``) é lazy — instanciado só dentro das
funções de fetch — então o módulo importa sem nenhuma conexão.
"""
import pandas as pd
import pytest

from src.dashboard import loaders
from src.dashboard.loaders import (
    _mes_apuracao_seguinte,
    _reanexar_regiao,
    carregar_universo_lojas,
)


@pytest.mark.unit
class TestMesApuracaoSeguinte:
    def test_mes_normal(self):
        assert _mes_apuracao_seguinte(6, 2026) == (7, 2026)
        assert _mes_apuracao_seguinte(11, 2025) == (12, 2025)

    def test_rollover_dezembro(self):
        assert _mes_apuracao_seguinte(12, 2025) == (1, 2026)


@pytest.mark.unit
class TestReanexarRegiao:
    def test_anexa_regiao_por_loja(self):
        pivot = pd.DataFrame({"LOJA": ["A", "B"], "META_PRATA": [10, 20]})
        fonte = pd.DataFrame({"LOJA": ["A", "B"], "REGIAO": ["R1", "R2"]})
        out = _reanexar_regiao(pivot, fonte)
        assert list(out.columns) == ["LOJA", "META_PRATA", "REGIAO"]
        assert dict(zip(out["LOJA"], out["REGIAO"])) == {"A": "R1", "B": "R2"}

    def test_loja_sem_regiao_fica_nan(self):
        pivot = pd.DataFrame({"LOJA": ["A", "C"], "META_PRATA": [10, 30]})
        fonte = pd.DataFrame({"LOJA": ["A"], "REGIAO": ["R1"]})
        out = _reanexar_regiao(pivot, fonte)
        assert out.loc[out["LOJA"] == "A", "REGIAO"].iloc[0] == "R1"
        assert pd.isna(out.loc[out["LOJA"] == "C", "REGIAO"].iloc[0])

    def test_dedup_mantem_primeira_regiao(self):
        pivot = pd.DataFrame({"LOJA": ["A"], "META_PRATA": [10]})
        fonte = pd.DataFrame({"LOJA": ["A", "A"], "REGIAO": ["R1", "R2"]})
        out = _reanexar_regiao(pivot, fonte)
        assert len(out) == 1
        assert out["REGIAO"].iloc[0] == "R1"


@pytest.mark.unit
class TestCarregarUniversoLojas:
    """Composição pura: mês corrente → lojas ativas; histórico → metas."""

    COLS = ["LOJA", "REGIAO", "REGIAO_ATUAL"]

    def test_mes_corrente_usa_lojas_ativas(self, monkeypatch):
        monkeypatch.setattr(loaders, "_eh_mes_atual", lambda m, a: True)
        monkeypatch.setattr(
            loaders, "carregar_lojas_ativas",
            lambda: pd.DataFrame({
                "LOJA": ["A", "C"], "REGIAO_ATUAL": ["R1", "R3"],
            }),
        )
        out = carregar_universo_lojas(7, 2026)
        assert list(out.columns) == self.COLS
        # REGIAO := REGIAO_ATUAL (organograma vigente = competência)
        assert list(out["REGIAO"]) == ["R1", "R3"]

    def test_historico_usa_metas_do_periodo(self, monkeypatch):
        monkeypatch.setattr(loaders, "_eh_mes_atual", lambda m, a: False)
        monkeypatch.setattr(
            loaders, "carregar_metas",
            lambda m, a: pd.DataFrame({
                "LOJA": ["A", "A", "B"],
                "REGIAO": ["R1", "R1", "R2"],
                "REGIAO_ATUAL": ["R9", "R9", "R2"],
                "META_PRATA": [1.0, 1.0, 2.0],
            }),
        )
        out = carregar_universo_lojas(1, 2026)
        assert list(out.columns) == self.COLS
        # Dedup por LOJA; REGIAO point-in-time preservada
        assert list(out["LOJA"]) == ["A", "B"]
        assert list(out["REGIAO"]) == ["R1", "R2"]

    def test_fontes_vazias_retornam_colunas_esperadas(self, monkeypatch):
        monkeypatch.setattr(loaders, "_eh_mes_atual", lambda m, a: True)
        monkeypatch.setattr(
            loaders, "carregar_lojas_ativas", lambda: pd.DataFrame(),
        )
        out = carregar_universo_lojas(7, 2026)
        assert out.empty
        assert list(out.columns) == self.COLS
