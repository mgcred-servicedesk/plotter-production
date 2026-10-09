"""Pill do Prestamista CNC no Resumo Executivo."""
import pandas as pd
import pytest

from src.dashboard.kpis.prestamista import (
    PRESTAMISTA_ERRO,
    PRESTAMISTA_NAO_IMPORTADO,
    PRESTAMISTA_OK,
    totais_prestamista,
)
from src.dashboard.ui.resumo_executivo import _pill_prestamista

META = {"meta_ipv": 0.8, "faixa_alerta": 0.6, "is_fallback": False}


def _dados(eleg, seg, meta=META):
    prop = pd.DataFrame({
        "co_adesao": range(len(eleg)),
        "qtd_elegivel": eleg,
        "qtd_seguro": seg,
    })
    return {
        "status": PRESTAMISTA_OK, "meta": meta,
        "totais": totais_prestamista(prop), "propostas": prop,
    }


@pytest.mark.unit
class TestPillPrestamista:
    def test_vermelho_com_pendencias(self):
        html = _pill_prestamista(_dados([1, 1, 1, 0], [1, 0, 0, 0]))
        assert "mg-pill-red" in html
        assert "33,3% (meta 80%)" in html
        assert "2 elegíveis sem seguro" in html

    def test_amarelo(self):
        html = _pill_prestamista(_dados([1] * 10, [1] * 7 + [0] * 3))
        assert "mg-pill-yellow" in html

    def test_verde_sem_pendencias_nao_cita_pendencia(self):
        html = _pill_prestamista(_dados([1, 1], [1, 1]))
        assert "mg-pill-green" in html and "sem seguro" not in html

    def test_sem_meta_fica_azul_sem_meta_no_texto(self):
        html = _pill_prestamista(_dados([1, 1], [1, 0], meta=None))
        assert "mg-pill-blue" in html and "meta" not in html

    @pytest.mark.parametrize("dados", [
        None,
        {"status": PRESTAMISTA_NAO_IMPORTADO},
        {"status": PRESTAMISTA_ERRO},
    ])
    def test_sem_dado_nao_gera_pill(self, dados):
        assert _pill_prestamista(dados) == ""

    def test_sem_elegivel_nao_gera_pill(self):
        assert _pill_prestamista(_dados([0, 0], [0, 0])) == ""
