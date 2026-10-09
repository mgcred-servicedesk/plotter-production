"""
Sub-aba Prestamista e coluna "Prestamista" em Propostas Pagas (AppTest).

O cruzamento ADE do dashboard (texto, `NUM_PROPOSTA`) x Adesao do
arquivo (inteiro) e o ponto fragil: se ele falhar em silencio, a coluna
sai em branco e ninguem percebe. Os testes leem a tabela renderizada.
"""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.dashboard.kpis.prestamista import (
    PRESTAMISTA_NAO_IMPORTADO,
    PRESTAMISTA_OK,
    SITUACAO_COM_SEGURO,
    SITUACAO_SEM_SEGURO,
    totais_prestamista,
)


def _propostas():
    return pd.DataFrame({
        "co_adesao": [101, 102, 103, 104],
        "qtd_contrato": [1, 1, 1, 0],
        "qtd_elegivel": [1, 1, 0, 0],
        "qtd_seguro": [1, 0, 0, 0],
        "status_apolice": ["Aprovado", None, None, None],
        "regiao": ["R1"] * 4,
        "loja": ["L1", "L1", "L2", "L2"],
        "consultor": ["ANA", "BIA", "CAU", "CAU"],
    })


def _prestamista(status=PRESTAMISTA_OK):
    prop = _propostas()
    return {
        "status": status,
        "meta": {"meta_ipv": 0.8, "faixa_alerta": 0.6, "is_fallback": False},
        "meta_erro": False,
        "totais": totais_prestamista(prop),
        "propostas": prop,
    }


def _pagos():
    return pd.DataFrame({
        "CONTRATO_ID": [1, 2, 3],
        "NUM_PROPOSTA": ["101", "102", "555"],
        "DATA": pd.to_datetime(["2026-10-01", "2026-10-02", "2026-10-03"]),
        "LOJA": ["L1", "L1", "L2"],
        "CONSULTOR": ["ANA", "BIA", "CAU"],
        "REGIAO": ["R1"] * 3,
        "TIPO_PRODUTO": ["CNC"] * 3,
        "SUBTIPO": ["REFIN", "SUPER CONTA", "REFIN"],
        "PRODUTO": ["CNC"] * 3,
        "CATEGORIA_CODIGO": ["CNC", "SUPER_CONTA", "CNC"],
        "GRUPO_DASHBOARD": ["CNC"] * 3,
        "TIPO OPER.": ["REFIN"] * 3,
        "VALOR": [1000.0, 2000.0, 3000.0],
        "BANCO": ["BMG"] * 3,
    })


def _script_sub_aba(prestamista, pagos, perfil):
    import streamlit as st  # noqa: F401

    from src.dashboard.tabs.analiticos import _render_prestamista

    _render_prestamista(prestamista, pagos, perfil)


def _script_pagos(pagos, prestamista):
    import pandas as pd
    import streamlit as st  # noqa: F401

    from src.dashboard.tabs.analiticos import _render_detalhamento_pagos

    _render_detalhamento_pagos(pagos, pd.DataFrame(), prestamista)


def _tabela(at: AppTest, i: int = 0) -> pd.DataFrame:
    valor = at.dataframe[i].value
    return valor.data if hasattr(valor, "data") else valor


def _rodar(fn, **kwargs) -> AppTest:
    at = AppTest.from_function(fn, kwargs=kwargs)
    at.run()
    assert not at.exception, at.exception
    return at


@pytest.mark.unit
class TestSubAbaPrestamista:
    def test_pendencias_trazem_dados_do_contrato_pago(self):
        at = _rodar(
            _script_sub_aba, prestamista=_prestamista(), pagos=_pagos(),
            perfil="consultor",
        )
        pend = _tabela(at, 0)
        assert pend["Nº ADE"].tolist() == ["102"]
        assert pend["Situação"].tolist() == [SITUACAO_SEM_SEGURO]
        assert pend["Valor"].tolist() == [2000.0]
        assert pend["Subproduto"].tolist() == ["SUPER CONTA"]

    def test_metricas(self):
        at = _rodar(
            _script_sub_aba, prestamista=_prestamista(), pagos=_pagos(),
            perfil="consultor",
        )
        valores = {m.label: m.value for m in at.metric}
        assert valores["IPV"] == "50.0%"
        assert valores["Elegíveis sem seguro"] == "1"

    def test_consultor_nao_ve_quebras(self):
        at = _rodar(
            _script_sub_aba, prestamista=_prestamista(), pagos=_pagos(),
            perfil="consultor",
        )
        assert len(at.tabs) == 0

    def test_supervisor_ve_quebra_por_consultor(self):
        at = _rodar(
            _script_sub_aba, prestamista=_prestamista(), pagos=_pagos(),
            perfil="supervisor",
        )
        assert [t.label for t in at.tabs] == ["Por consultor"]

    def test_nao_importado_avisa(self):
        at = _rodar(
            _script_sub_aba,
            prestamista=_prestamista(PRESTAMISTA_NAO_IMPORTADO),
            pagos=_pagos(), perfil="admin",
        )
        assert "não importado" in at.info[0].value
        assert len(at.dataframe) == 0


@pytest.mark.unit
class TestColunaPropostasPagas:
    def test_coluna_marca_por_ade(self):
        at = _rodar(_script_pagos, pagos=_pagos(), prestamista=_prestamista())
        df = _tabela(at).set_index("Nº ADE")
        assert df.loc["101", "Prestamista"] == SITUACAO_COM_SEGURO
        assert df.loc["102", "Prestamista"] == SITUACAO_SEM_SEGURO
        assert df.loc["555", "Prestamista"] == ""

    def test_filtro_so_pendencias(self):
        at = AppTest.from_function(
            _script_pagos, kwargs=dict(pagos=_pagos(), prestamista=_prestamista())
        )
        at.run()
        cb = at.checkbox(key="det_pago_prest_pend")
        assert "(1)" in cb.label
        cb.check().run()
        assert _tabela(at)["Nº ADE"].tolist() == ["102"]

    def test_sem_arquivo_sem_coluna(self):
        at = _rodar(_script_pagos, pagos=_pagos(), prestamista=None)
        assert "Prestamista" not in _tabela(at).columns
