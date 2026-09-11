"""
Testes de ``src/dashboard/ui/prioridades_pontuacao.py``.

Mesmo incidente documentado em ``tests/test_ui_kpi_cards_pontuacao.py``:
um gap zerado por FALTA de meta cadastrada (loja DIGITAL, ou qualquer
loja/competência sem cadastro) não pode ser lido como "meta atingida".
Aqui a distinção é feita por ``_html_card_produto_pts`` (badge/label do
card e ``txt_prata``/``txt_ouro``) e propagada por ``_render_lista`` e
``render_prioridades_pontuacao`` até o bloco "💡 Ação Recomendada" — os
três ganharam os kwargs opcionais ``meta_prata``/``meta_ouro``
(default ``0.0``, retrocompatíveis).

``_html_card_produto_pts`` devolve string pura (sem Streamlit) — testada
direto, como ``_card_contexto`` em ``test_ui_cards.py``.
``render_prioridades_pontuacao`` escreve via ``st.markdown``; roda via
``AppTest.from_function`` (mesma técnica de ``test_tabs_produtos.py``),
com ``df``/``df_metas_produto`` vazios para que
``render_prioridades_aceleradores`` retorne cedo (``df.empty``) sem
tocar RLS/``session_state`` — irrelevante para o que este teste cobre.
``_render_lista`` não ganha um teste próprio: ela só repassa
``meta_prata``/``meta_ouro`` para ``_html_card_produto_pts`` dentro do
mesmo fluxo de markdown que ``render_prioridades_pontuacao`` já
exercita de ponta a ponta — um teste isolado duplicaria o que os dois
abaixo já provam.

Asserts ancorados em texto VISÍVEL ("Sem meta definida"/"Sem meta Prata
definida", "já atingida", o travessão), nunca em classe CSS.
"""
import pytest
from streamlit.testing.v1 import AppTest

from src.dashboard.formatters import formatar_percentual
from src.dashboard.ui.prioridades_pontuacao import _html_card_produto_pts


def _prio(**overrides) -> dict:
    base = {
        "produto": "CNC",
        "pontos_pagos": 1000.0,
        "pontos_analise": 500.0,
        "qtd_analise": 3,
        "peso_atual": 25.0,
        "fecha_prata_pct": 40.0,
        "fecha_ouro_pct": 20.0,
        "gap_prata": 1250.0,
        "gap_ouro": 2500.0,
    }
    base.update(overrides)
    return base


@pytest.mark.unit
class TestHtmlCardProdutoPts:
    def test_meta_prata_com_gap_mostra_percentual_real(self):
        html = _html_card_produto_pts(
            1, _prio(), meta_prata=360000.0, meta_ouro=500000.0,
        )
        assert "Sem meta" not in html
        assert f"fecha {formatar_percentual(40.0)} da Prata" in html

    def test_meta_prata_batida_mostra_ja_atingida(self):
        html = _html_card_produto_pts(
            1, _prio(gap_prata=0.0), meta_prata=360000.0, meta_ouro=500000.0,
        )
        assert "Prata já atingida" in html
        assert "Sem meta" not in html

    def test_sem_meta_prata_mostra_sem_meta_nunca_atingida(self):
        """``gap_prata=0`` aqui é FALTA de meta, não meta batida — é o
        mesmo bug do incidente: o guard de ``meta_prata <= 0`` precisa
        vencer antes de qualquer leitura de ``gap_prata``."""
        html = _html_card_produto_pts(
            1, _prio(gap_prata=0.0), meta_prata=0.0, meta_ouro=500000.0,
        )
        assert "Sem meta" in html  # badge do topo do card
        assert "sem meta definida" in html  # txt_prata
        assert "Prata já atingida" not in html
        assert "Atingida" not in html

    def test_meta_ouro_zero_com_prata_positiva_trata_independente(self):
        html = _html_card_produto_pts(
            1, _prio(), meta_prata=360000.0, meta_ouro=0.0,
        )
        partes = html.split("Para a Meta Ouro:")
        assert len(partes) == 2
        assert f"fecha {formatar_percentual(40.0)} da Prata" in partes[0]
        assert "sem meta definida" in partes[1]


def _script_render_prioridades_pontuacao(prioridades, meta_prata, meta_ouro):
    import pandas as pd

    from src.dashboard.ui.prioridades_pontuacao import render_prioridades_pontuacao

    render_prioridades_pontuacao(
        prioridades,
        pd.DataFrame(),  # df vazio -> aceleradores retornam cedo
        pd.DataFrame(),
        meta_prata=meta_prata,
        meta_ouro=meta_ouro,
    )


def _run_prioridades(prioridades: list, meta_prata=0.0, meta_ouro=0.0) -> AppTest:
    at = AppTest.from_function(
        _script_render_prioridades_pontuacao,
        kwargs=dict(
            prioridades=prioridades, meta_prata=meta_prata, meta_ouro=meta_ouro,
        ),
    )
    at.run()
    return at


@pytest.mark.unit
class TestRenderPrioridadesPontuacaoAcaoRecomendada:
    """Bloco "💡 Ação Recomendada" — mesma distinção, ponta a ponta."""

    def test_com_meta_e_gap_mostra_percentual_do_gap(self):
        at = _run_prioridades(
            [_prio()], meta_prata=360000.0, meta_ouro=500000.0,
        )
        assert not at.exception
        html = "".join(m.value for m in at.markdown)

        assert "💡 Ação Recomendada" in html
        assert (
            f"fecharia <strong>{formatar_percentual(40.0)}</strong> "
            "do gap da Prata" in html
        )
        assert "Sem meta Prata definida" not in html
        # kwargs propagaram até o card do produto tambem (_render_lista)
        assert f"fecha {formatar_percentual(40.0)} da Prata" in html

    def test_meta_batida_foca_em_ouro(self):
        at = _run_prioridades(
            [_prio(gap_prata=0.0)], meta_prata=360000.0, meta_ouro=500000.0,
        )
        html = "".join(m.value for m in at.markdown)

        assert "Prata já atingida. Focar em" in html
        assert "Sem meta Prata definida" not in html

    def test_sem_meta_prata_nunca_diz_atingida(self):
        """``gap_prata=0`` de propósito: sem o guard de
        ``meta_prata <= 0`` primeiro, isso cairia no ramo "já
        atingida" — o texto teria que ser "sem meta", não "atingida"."""
        at = _run_prioridades(
            [_prio(gap_prata=0.0)], meta_prata=0.0, meta_ouro=0.0,
        )
        html = "".join(m.value for m in at.markdown)

        assert "Sem meta Prata definida para este escopo" in html
        assert "atingida" not in html.lower()
