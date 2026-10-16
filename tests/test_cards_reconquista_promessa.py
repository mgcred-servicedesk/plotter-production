"""
Card Promessas da Reconquista (`render_cards_reconquista`) na V3
(Promessa Diaria, >= 09/2026).

Valor = elegiveis do mes, SEM variacao vs mes anterior, insights do
proprio arquivo. Nao importada/erro => "—" + aviso, nunca 0. Antes de
09/2026 o card segue o legado do export (regressao).
"""
import re

import pytest
from streamlit.testing.v1 import AppTest


def _script_cards(dados, mes, ano):
    import streamlit as st  # noqa: F401  (necessario no script isolado)

    from src.dashboard.ui.kpi_cards_reforma import render_cards_reconquista

    render_cards_reconquista(dados, mes, ano)


def _dados(promessa_status="ok", **totais_extra):
    totais = {
        "total": 10, "total_geral": 10,
        "efetivadas": 7, "promessas": 3,
        "sem_reconquista": 0, "conversao": 70.0,
        "faixa": {"rotulo": "+20% sobre prêmio CNC", "cor": "#10A37F"},
        "cobranca_consignavel": 2,
        "acelerador_perfil": "gestor",
        "faixa_agregada": None,
        "liga_status": "ok",
        "liga_nao_contabilizadas": 4,
        "promessas_anterior": 99,   # legado; a V3 nao deve usar
    }
    if promessa_status is not None:
        totais["promessa_status"] = promessa_status
    if promessa_status == "ok":
        totais.update(
            promessas=42, nao_elegiveis=5, retorno_aceito=21,
            retorno_pendente=12, retorno_nao_aceito=9, retorno_outros=0,
            pct_retorno_aceito=50.0, fdr_e_promessa=10, so_promessa=32,
            promessas_efetivadas=6,
        )
    elif promessa_status in ("nao_importada", "erro"):
        totais.update(
            promessas=None, nao_elegiveis=None, retorno_aceito=None,
            retorno_pendente=None, retorno_nao_aceito=None,
            retorno_outros=None, pct_retorno_aceito=None,
            fdr_e_promessa=None, so_promessa=None,
            promessas_efetivadas=None,
        )
    totais.update(totais_extra)
    return {
        "ref_mes": 8, "ref_ano": 2026,
        "totais": totais, "por_consultor": None, "prox": None,
    }


def _rodar(dados, mes=9, ano=2026):
    at = AppTest.from_function(
        _script_cards, kwargs=dict(dados=dados, mes=mes, ano=ano),
    )
    at.run()
    assert not at.exception
    return at


def _card_promessas(at) -> str:
    """HTML so do card Promessas: a linha de cards chega num unico
    markdown, entao recorta do titulo dele ate o card seguinte."""
    linhas = [m.value for m in at.markdown if "⏳ Promessas" in m.value]
    assert len(linhas) == 1, linhas
    depois = linhas[0].split("⏳ Promessas", 1)[1]
    return depois.split("💰", 1)[0]


def _texto(card: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", card)).strip()


@pytest.mark.unit
class TestCardPromessaV3Ok:
    def test_valor_e_a_contagem_do_arquivo(self):
        txt = _texto(_card_promessas(_rodar(_dados("ok"))))
        assert "42" in txt

    def test_sem_variacao_vs_periodo_anterior(self):
        at = _rodar(_dados("ok"))
        card = _card_promessas(at)
        for proibido in ("▲", "▼", "vs período ant."):
            assert proibido not in card
            assert proibido not in " ".join(m.value for m in at.markdown
                                            if "⏳" in m.value)

    def test_insights_do_proprio_arquivo(self):
        txt = _texto(_card_promessas(_rodar(_dados("ok"))))
        assert "Retorno INSS: 50.0% aceito" in txt
        assert "12 pendentes" in txt
        assert "9 não aceitos" in txt
        assert "6 já efetivadas (liga)" in txt
        assert "+5 não elegíveis fora da conta" in txt

    def test_sem_nao_elegiveis_omite_a_linha(self):
        txt = _texto(_card_promessas(_rodar(_dados("ok", nao_elegiveis=0))))
        assert "fora da conta" not in txt

    def test_retorno_outros_aparece_quando_existe(self):
        txt = _texto(_card_promessas(_rodar(_dados("ok", retorno_outros=3))))
        assert "3 outros" in txt

    def test_efetivacao_indisponivel_quando_badge_none(self):
        txt = _texto(_card_promessas(
            _rodar(_dados("ok", promessas_efetivadas=None))
        ))
        assert "Efetivação indisponível" in txt
        assert "já efetivadas" not in txt

    def test_zero_efetivadas_e_zero_legitimo_nao_indisponivel(self):
        txt = _texto(_card_promessas(
            _rodar(_dados("ok", promessas_efetivadas=0))
        ))
        assert "0 já efetivadas (liga)" in txt
        assert "indisponível" not in txt

    def test_caption_fala_da_promessa_diaria(self):
        at = _rodar(_dados("ok"))
        captions = " ".join(c.value for c in at.caption)
        assert "Promessa Diária" in captions

    def test_export_vazio_nao_esconde_o_bloco(self):
        dados = _dados("ok", total=0, total_geral=0)
        txt = _texto(_card_promessas(_rodar(dados)))
        assert "42" in txt

    def test_export_vazio_sem_liga_tambem_nao_esconde_a_promessa(self):
        dados = _dados("ok", total=0, total_geral=0, liga_status="fora")
        at = _rodar(dados, mes=9)
        assert "42" in _texto(_card_promessas(at))


@pytest.mark.unit
class TestCardPromessaV3SemDado:
    def test_nao_importada_mostra_traco_e_avisa(self):
        at = _rodar(_dados("nao_importada"))
        txt = _texto(_card_promessas(at))
        assert "—" in txt
        assert "não importada" in txt
        avisos = " ".join(w.value for w in at.warning)
        assert "Promessa Diária de 09/2026 ainda não importada" in avisos

    def test_erro_mostra_traco_e_erro(self):
        at = _rodar(_dados("erro"))
        txt = _texto(_card_promessas(at))
        assert "—" in txt
        erros = " ".join(e.value for e in at.error)
        assert "Não foi possível carregar a Promessa Diária" in erros

    @pytest.mark.parametrize("status", ["nao_importada", "erro"])
    def test_nunca_mostra_zero_nem_o_numero_do_export(self, status):
        """`totais["promessas"]` do export (3) e o 0 de fallback nao
        podem aparecer como valor do card."""
        at = _rodar(_dados(status, promessas_anterior=99))
        card = _card_promessas(at)
        # O valor do card e o "—": nenhum numero fora do rotulo do mes.
        txt = _texto(card).replace("09/2026", "").replace("Set/2026", "")
        txt = re.sub(r"[A-Za-zçãéíóú]+/2026", "", txt)
        assert not re.search(r"\d", txt), txt
        assert "▲" not in card and "▼" not in card

    @pytest.mark.parametrize("status", ["nao_importada", "erro"])
    def test_sem_insights_de_retorno(self, status):
        txt = _texto(_card_promessas(_rodar(_dados(status))))
        assert "Retorno INSS" not in txt
        assert "já efetivadas" not in txt

    def test_export_vazio_nao_esconde_o_bloco_sem_dado(self):
        dados = _dados("nao_importada", total=0, total_geral=0)
        at = _rodar(dados)
        assert "—" in _texto(_card_promessas(at))


@pytest.mark.unit
class TestCardPromessaForaDaV3:
    def test_agosto_mantem_a_variacao_do_legado(self):
        at = _rodar(
            _dados("fora", promessas=3, promessas_anterior=1),
            mes=8, ano=2026,
        )
        card = _card_promessas(at)
        assert "▲" in card
        assert "vs período ant." in card
        assert "Retorno INSS" not in card

    def test_chave_promessa_status_ausente_e_legado(self):
        dados = _dados(None, promessas=3, promessas_anterior=1)
        card = _card_promessas(_rodar(dados, mes=8, ano=2026))
        assert "▲" in card

    def test_caption_legado_fala_de_fim_de_relacionamento(self):
        at = _rodar(_dados("fora", liga_status="fora"), mes=8, ano=2026)
        captions = " ".join(c.value for c in at.caption)
        assert "Promessa Diária" not in captions
