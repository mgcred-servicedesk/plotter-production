"""
Testes de render de ``src/dashboard/ui/kpi_cards_pontuacao.py``.

Incidente (09/2026): com ``meta_prata = 0`` (loja/competência sem meta
cadastrada — caso real: loja DIGITAL), ``gap_pontos = max(0, 0 -
total_pontos)`` dava 0 e caía no ramo que renderiza "✓ Prata Atingida"
em verde — o dashboard afirmava meta batida onde não existe meta
nenhuma. A correção separa os dois "gap zero" por VALOR (``meta_prata
<= 0``), nunca por nome de loja: aqui travamos os três estados
(gap positivo real, meta batida de verdade, sem meta) e — o mais
importante — que "sem meta" nunca reintroduz o texto de meta batida.

``render_kpis_principais_pts``/``render_bloco_media_projecao_pts``
escrevem via ``st.markdown(html, unsafe_allow_html=True)``; como não
dependem de widget algum (sem ``st.toggle``/``session_state``), dá pra
rodar via ``AppTest.from_function`` só para capturar o HTML emitido —
mesma técnica de ``tests/test_tabs_produtos.py`` (ver
``_contagens_na_linha``/``at.markdown[i].value``).

Os asserts ancoram em texto VISÍVEL ao usuário ("Sem meta definida",
"✓ Prata Atingida", o travessão "—"), nunca em classe CSS/ordem de
atributo — layout muda, essas strings são o contrato com quem lê a
tela.
"""
import pytest
from streamlit.testing.v1 import AppTest

from src.dashboard.ui.kpi_cards_pontuacao import _fmt_pts, _fmt_pts_total


def _script_render_kpis_principais_pts(kpis):
    from src.dashboard.ui.kpi_cards_pontuacao import render_kpis_principais_pts

    render_kpis_principais_pts(kpis)


def _run_kpis_principais(kpis: dict) -> AppTest:
    at = AppTest.from_function(
        _script_render_kpis_principais_pts, kwargs=dict(kpis=kpis),
    )
    at.run()
    return at


def _script_render_bloco_media_projecao_pts(kpis):
    from src.dashboard.ui.kpi_cards_pontuacao import render_bloco_media_projecao_pts

    render_bloco_media_projecao_pts(kpis)


def _run_bloco_media_projecao(kpis: dict) -> AppTest:
    at = AppTest.from_function(
        _script_render_bloco_media_projecao_pts, kwargs=dict(kpis=kpis),
    )
    at.run()
    return at


@pytest.mark.unit
class TestRenderKpisPrincipaisPts:
    """Cards "📊 % Meta Prata" e "🎯 Falta para Prata"."""

    def test_meta_existente_com_gap_mostra_percentual_e_falta_real(self):
        # Caso real do incidente: HELP PENHA, PAULA VIRGINIA — 205.761
        # pontos contra meta individual de 360.000 (57,2%).
        total_pontos = 205761.0
        meta_prata = 360000.0
        perc_prata = total_pontos / meta_prata * 100
        gap = meta_prata - total_pontos
        kpis = {
            "total_pontos": total_pontos,
            "meta_prata": meta_prata,
            "meta_ouro": 500000.0,
            "perc_ating_prata": perc_prata,
            "perc_ating_ouro": 40.0,
            "perc_proj": 60.0,
            "projecao_pontos": 250000.0,
            "du_restantes": 10,
        }

        at = _run_kpis_principais(kpis)

        assert not at.exception
        assert len(at.markdown) == 1
        html = at.markdown[0].value

        assert f"{perc_prata:.1f}%" in html  # "57.2%"
        assert f"-{_fmt_pts(gap)}" in html  # número principal do gap
        assert _fmt_pts_total(gap) in html  # "Falta: 154.239 pts"
        assert "Sem meta definida" not in html
        assert "Prata Atingida" not in html

    def test_meta_batida_mostra_check_verde(self):
        """A regressão mais perigosa: alguém "simplificando" os ramos
        pode matar o ✓ verde junto com o travessão de "sem meta"."""
        kpis = {
            "total_pontos": 400000.0,
            "meta_prata": 360000.0,
            "meta_ouro": 500000.0,
            "perc_ating_prata": 111.1,
            "perc_ating_ouro": 80.0,
            "perc_proj": 120.0,
            "projecao_pontos": 450000.0,
            "du_restantes": 5,
        }

        at = _run_kpis_principais(kpis)
        html = at.markdown[0].value

        assert "✓ Prata Atingida" in html
        assert "Sem meta definida" not in html

    def test_sem_meta_mostra_travessao_nos_dois_cards_nunca_atingida(self):
        """O coração do teste — é literalmente o bug que o usuário viu:
        meta zerada (DIGITAL, ou qualquer loja/competência sem
        cadastro) não pode, em NENHUM lugar da linha, ler "atingida"."""
        kpis = {
            "total_pontos": 205761.0,
            "meta_prata": 0.0,
            "meta_ouro": 0.0,
            "perc_ating_prata": 0.0,
            "perc_ating_ouro": 0.0,
            "perc_proj": 0.0,
            "projecao_pontos": 0.0,
            "du_restantes": 10,
        }

        at = _run_kpis_principais(kpis)
        html = at.markdown[0].value

        assert html.count("Sem meta definida") == 2  # % Meta Prata + Falta
        assert html.count(">—<") == 2
        assert "Prata Atingida" not in html
        assert "Atingida" not in html


@pytest.mark.unit
class TestRenderBlocoMediaProjecaoPts:
    """Bloco "📈 Para Onde Estamos Indo" — ``msg_desvio``, "Necessário
    p/ Prata" e as cores derivadas de ``sem_meta_prata``/``sem_meta_ouro``."""

    def test_gap_positivo_mostra_necessario_e_desvio_reais(self):
        kpis = {
            "total_pontos": 205761.0,
            "meta_prata": 360000.0,
            "meta_ouro": 500000.0,
            "projecao_pontos": 250000.0,
            "media_du_pontos": 15000.0,
            "du_total": 20,
            "du_decorridos": 10,
            "du_restantes": 10,
        }

        at = _run_bloco_media_projecao(kpis)
        html = at.markdown[-1].value

        necess_prata = (360000.0 - 205761.0) / 10
        assert f"{_fmt_pts(necess_prata)} pts/dia" in html
        assert "Sem meta definida" not in html
        assert "Prata atingida" not in html

    def test_meta_batida_mostra_prata_atingida_no_desvio(self):
        kpis = {
            "total_pontos": 400000.0,
            "meta_prata": 360000.0,
            "meta_ouro": 500000.0,
            "projecao_pontos": 450000.0,
            "media_du_pontos": 30000.0,
            "du_total": 20,
            "du_decorridos": 15,
            "du_restantes": 5,
        }

        at = _run_bloco_media_projecao(kpis)
        html = at.markdown[-1].value

        assert "Prata atingida" in html
        assert "Sem meta definida" not in html

    def test_sem_meta_prata_e_ouro_mostra_travessao_e_nunca_atingida(self):
        kpis = {
            "total_pontos": 205761.0,
            "meta_prata": 0.0,
            "meta_ouro": 0.0,
            "projecao_pontos": 0.0,
            "media_du_pontos": 15000.0,
            "du_total": 20,
            "du_decorridos": 10,
            "du_restantes": 10,
        }

        at = _run_bloco_media_projecao(kpis)
        html = at.markdown[-1].value

        assert html.count("Sem meta definida") == 2  # desvio + projeção
        assert "Ouro: —" in html
        assert "Prata atingida" not in html
        assert "atingida" not in html.lower().replace("sem meta definida", "")

    def test_meta_ouro_zero_com_prata_positiva_trata_independente(self):
        """Metas mistas: DIGITAL pode não ter Prata nem Ouro, mas uma
        loja normal pode ter Prata cadastrada e Ouro não (ou
        vice-versa) — as duas colunas precisam decidir cada uma por
        si, sem uma "contaminar" a outra."""
        kpis = {
            "total_pontos": 205761.0,
            "meta_prata": 360000.0,
            "meta_ouro": 0.0,
            "projecao_pontos": 250000.0,
            "media_du_pontos": 15000.0,
            "du_total": 20,
            "du_decorridos": 10,
            "du_restantes": 10,
        }

        at = _run_bloco_media_projecao(kpis)
        html = at.markdown[-1].value

        assert "Ouro: —" in html
        assert "Sem meta definida" not in html  # Prata continua com número
        assert "da Prata" in html
        assert "da Ouro" not in html  # msg_ouro vazio quando meta_ouro <= 0
