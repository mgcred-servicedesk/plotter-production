"""
Testes do helper puro ``_card_contexto`` de
``src/dashboard/ui/kpi_cards_reforma.py``.

Streamlit importa em modo bare (sem servidor); o helper é uma função
pura de string e não chama ``st.*``.
"""
import pytest

from src.dashboard.ui.kpi_cards_reforma import _card_contexto


@pytest.mark.unit
class TestCardContexto:
    def test_estrutura_basica(self):
        html = _card_contexto("Lbl", "42", "sub")
        assert 'class="mg-kpi-context"' in html
        assert '<div class="mg-kpi-ctx-label">Lbl</div>' in html
        assert '<div class="mg-kpi-ctx-valor">42</div>' in html
        assert '<div class="mg-kpi-ctx-sub">sub</div>' in html

    def test_valor_style_injetado(self):
        html = _card_contexto(
            "L", "1", "s", valor_style=' style="color: #fff;"'
        )
        assert (
            '<div class="mg-kpi-ctx-valor" style="color: #fff;">1</div>'
            in html
        )

    def test_separador_milhar_br(self):
        # "1,234" (US) -> "1.234" (BR), aplicado ao card inteiro
        html = _card_contexto("L", "1,234", "s")
        assert "1.234" in html
        assert "1,234" not in html
