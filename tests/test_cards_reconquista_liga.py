"""
Card principal da Reconquista (`render_cards_reconquista`) com a liga.

A partir de 09/2026 Efetivadas e a contagem da liga, sem % de conversao
nem faixa sobre premio CNC (decisao de 02/10/2026); sem liga importada
o card mostra "—", nunca zero, e o consultor nao ve a barra antiga de
conversao.
"""
import pytest
from streamlit.testing.v1 import AppTest


def _script_cards(dados, mes, ano):
    import streamlit as st  # noqa: F401  (necessario no script isolado)

    from src.dashboard.ui.kpi_cards_reforma import render_cards_reconquista

    render_cards_reconquista(dados, mes, ano)


def _dados(liga_status, perfil="gestor", efetivadas=7):
    return {
        "ref_mes": 8, "ref_ano": 2026,
        "totais": {
            "total": 10, "total_geral": 10,
            "efetivadas": efetivadas, "promessas": 3,
            "sem_reconquista": 0, "conversao": 70.0,
            "faixa": {"rotulo": "+20% sobre prêmio CNC", "cor": "#10A37F"},
            "cobranca_consignavel": 2,
            "acelerador_perfil": perfil,
            "faixa_agregada": None,
            "liga_status": liga_status,
            "liga_nao_contabilizadas": 4,
        },
        "por_consultor": None,
        "prox": None,
    }


def _html(dados, mes=9, ano=2026) -> tuple[AppTest, str]:
    at = AppTest.from_function(
        _script_cards, kwargs=dict(dados=dados, mes=mes, ano=ano),
    )
    at.run()
    assert not at.exception
    return at, " ".join(m.value for m in at.markdown)


@pytest.mark.unit
class TestCardsReconquistaLiga:
    def test_liga_mostra_so_a_quantidade(self):
        _, html = _html(_dados("ok"))
        assert "Contabilizadas pela liga" in html
        assert "4 listadas não contabilizadas" in html
        assert "de conversão" not in html
        assert "Se efetivadas" not in html

    def test_liga_nao_importada_mostra_traco_e_avisa(self):
        at, html = _html(_dados("nao_importada", efetivadas=0))
        assert "Liga não importada" in html
        assert "ainda não importada" in " ".join(w.value for w in at.warning)
        # Acelerador combinado tambem sem numero.
        assert "<strong>—</strong> com Efetivadas" in html

    def test_consultor_sem_liga_nao_ve_a_barra_antiga(self):
        _, html = _html(_dados("nao_importada", perfil="consultor"))
        assert "Conversão (elegíveis)" not in html

    def test_antes_da_liga_segue_com_conversao(self):
        _, html = _html(_dados("fora"), mes=8, ano=2026)
        assert "de conversão" in html
        assert "Contabilizadas pela liga" not in html

    def test_export_vazio_nao_esconde_a_liga(self):
        dados = _dados("ok")
        dados["totais"]["total"] = 0
        dados["totais"]["total_geral"] = 0
        _, html = _html(dados)
        assert "Contabilizadas pela liga" in html
