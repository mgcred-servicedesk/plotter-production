"""
Testes dos helpers puros de ``src/dashboard/tabs/analiticos.py``.

``_opcoes_coluna`` alimenta os selectbox de Produto/Subproduto do
detalhamento: precisa ignorar NaN (pagos) e "" (em analise/cancelados,
onde o join de produto nao resolveu) sem quebrar o ``sorted``.

O Detalhamento de Reconquista tem, alem disso, um render testado via
``AppTest``: o escopo (vigente x todas as apuracoes) e um widget, e
widget fora de um script run real devolve sempre o valor padrao.
"""
import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.dashboard.kpis.produtos import COL_PRODUTO_DETALHADO
from src.dashboard.loaders import _marcar_vigencia_reconquista
from src.dashboard.tabs.analiticos import _COLS_PRODUTO, _opcoes_coluna


@pytest.mark.unit
class TestOpcoesColuna:
    def test_ignora_nan_e_vazio(self):
        df = pd.DataFrame({
            "SUBTIPO": ["REFIN", "", None, np.nan, "  ", "NOVO"],
        })
        assert _opcoes_coluna(df, "SUBTIPO") == ["NOVO", "REFIN"]

    def test_dedup_e_ordenacao_com_strip(self):
        df = pd.DataFrame({"SUBTIPO": [" REFIN", "REFIN ", "MARGEM"]})
        assert _opcoes_coluna(df, "SUBTIPO") == ["MARGEM", "REFIN"]

    def test_coluna_ausente_retorna_vazio(self):
        assert _opcoes_coluna(pd.DataFrame({"X": [1]}), "SUBTIPO") == []

    def test_df_vazio_retorna_vazio(self):
        df = pd.DataFrame(columns=["SUBTIPO"])
        assert _opcoes_coluna(df, "SUBTIPO") == []


@pytest.mark.unit
class TestColsProduto:
    def test_hierarquia_grupo_tipo_subtipo(self):
        # Ordem importa: e a hierarquia exibida nas tabelas analiticas.
        # O grupo e a dimensao desmembrada (PACK -> FGTS / ANT. DE
        # BENEF. / CNC 13º), nao o grupo_dashboard cru.
        assert _COLS_PRODUTO == [
            COL_PRODUTO_DETALHADO, "TIPO_PRODUTO", "SUBTIPO",
        ]


# ── Detalhamento de Reconquista (AppTest) ────────────────────────────
#
# ``AppTest.from_function`` roda o corpo da funcao abaixo como script de
# verdade — unica forma de pre-setar o pill de escopo em
# ``session_state`` antes do primeiro ``run()``. A funcao precisa ser
# top-level e autocontida (imports no corpo).

def _script_render_detalhamento(clientes):
    import streamlit as st  # noqa: F401  (necessario no script isolado)

    from src.dashboard.tabs.analiticos import (
        _render_reconquista_detalhamento,
    )

    _render_reconquista_detalhamento(clientes, "08/2026", "07/2026")


def _clientes_reconquista() -> pd.DataFrame:
    """Um lead por mes de referencia, ja marcado como o loader marca.

    Selecionando a apuracao 08/2026: ref 07 e a vigente, ref 08 e a
    proxima, ref 05 e 06 sao historico.
    """
    df = pd.DataFrame([
        {
            "co_adesao": i,
            "ref_ano": 2026,
            "ref_mes": mes,
            "status": "SEM RECONQUISTA",
            "flag_elegibilidade": "ELEGIVEL",
            "loja": f"LOJA {mes}",
            "regiao": "R1",
            "consultor": "CONSULTOR 1",
            "dt_fim_relacionamento": f"2026-0{mes}-10",
            "saldo_contabil": 100.0,
            "dias_atraso": 5,
        }
        for i, mes in enumerate([5, 6, 7, 8], start=1)
    ])
    return _marcar_vigencia_reconquista(df, 8, 2026)


def _tabela(at: AppTest) -> pd.DataFrame:
    """DataFrame renderizado (o valor vem embrulhado em Styler)."""
    valor = at.dataframe[0].value
    return valor.data if hasattr(valor, "data") else valor


def _rodar(escopo: str) -> AppTest:
    at = AppTest.from_function(
        _script_render_detalhamento,
        kwargs=dict(clientes=_clientes_reconquista()),
    )
    at.session_state["rec_det_escopo"] = escopo
    at.run()
    assert not at.exception
    return at


@pytest.mark.unit
class TestRenderReconquistaDetalhamento:
    """O analitico deixou de ficar preso a apuracao vigente: o mesmo
    frame (todas as apuracoes) serve os dois escopos, e a referencia
    de cada lead fica na linha em ambos.
    """

    def test_escopo_vigente_lista_so_a_apuracao_do_mes(self):
        df = _tabela(_rodar("Vigente"))
        assert df["Cod ADE"].tolist() == [3]
        assert df["Apuração"].tolist() == ["08/2026"]

    def test_escopo_todas_lista_o_historico_inteiro(self):
        df = _tabela(_rodar("Todas"))
        assert len(df) == 4
        # Apuracao mais recente primeiro.
        assert df["Apuração"].tolist() == [
            "09/2026", "08/2026", "07/2026", "06/2026",
        ]
        assert df["Vigência"].tolist() == [
            "Próxima", "Vigente", "Histórico", "Histórico",
        ]

    def test_referencia_aparece_nos_dois_escopos(self):
        for escopo in ("Vigente", "Todas"):
            df = _tabela(_rodar(escopo))
            assert {"Apuração", "Vigência"} <= set(df.columns)

    def test_filtro_de_apuracao_so_no_escopo_completo(self):
        # 4 filtros no vigente (a apuracao seria inerte) e 5 em todas.
        assert len(_rodar("Vigente").multiselect) == 1   # so Loja
        assert len(_rodar("Todas").multiselect) == 2     # Loja + Apuracao

    def test_caption_evidencia_a_vigencia(self):
        for escopo in ("Vigente", "Todas"):
            caption = _rodar(escopo).caption[0].value
            assert "08/2026" in caption   # apuracao vigente
            assert "07/2026" in caption   # fim de relacionamento



# ── Seletor de banco da Distribuicao de Produtos (AppTest) ───────────
#
# ``_selecionar_banco`` so existe dentro de um script run real: a lista
# de opcoes depende do ``df`` e o guard de cascata escreve em
# ``session_state`` ANTES de instanciar o widget. Fora de um run,
# widget devolve sempre o padrao e o guard nunca roda.

def _script_selecionar_banco(df):
    import streamlit as st

    from src.dashboard.tabs.analiticos import _selecionar_banco

    # Expoe o retorno para a asserção — o widget em si nao carrega a
    # tupla resultante (so o rotulo selecionado).
    st.session_state["_saida"] = _selecionar_banco(df)


def _df_bancos() -> pd.DataFrame:
    return pd.DataFrame({
        "BANCO": ["BMG", "BANCO BMG", "C6 BANK", "MASTER", None],
    })


def _rodar_seletor(df=None, selecionado=None) -> AppTest:
    at = AppTest.from_function(
        _script_selecionar_banco, kwargs=dict(df=_df_bancos() if df is None else df),
    )
    if selecionado is not None:
        at.session_state["dist_prod_banco"] = selecionado
    at.run()
    assert not at.exception
    return at


@pytest.mark.unit
class TestSelecionarBanco:
    def test_opcoes_sao_todos_preset_e_bancos_canonicos(self):
        at = _rodar_seletor()
        # "BMG" e "BANCO BMG" colapsam numa opcao so; nulo fica de fora.
        assert at.selectbox[0].options == [
            "Todos", "BMG/Help", "BMG", "C6", "MASTER",
        ]

    def test_todos_e_o_padrao_e_nao_recorta(self):
        at = _rodar_seletor()
        assert at.selectbox[0].value == "Todos"
        assert at.session_state["_saida"] is None

    def test_preset_devolve_o_par_bmg_help(self):
        at = _rodar_seletor(selecionado="BMG/Help")
        assert at.session_state["_saida"] == ("BMG", "HELP")

    def test_banco_unico_devolve_tupla_de_um(self):
        at = _rodar_seletor(selecionado="C6")
        assert at.session_state["_saida"] == ("C6",)

    def test_banco_que_sumiu_da_base_reseta_para_todos(self):
        # Guard de cascata: trocar o mes na sidebar pode tirar da base o
        # banco selecionado. Sem o reset, o widget subiria com um valor
        # fora das opcoes.
        at = _rodar_seletor(selecionado="VCTEX")
        assert at.selectbox[0].value == "Todos"
        assert at.session_state["_saida"] is None

    def test_sem_coluna_banco_sobra_todos_e_o_preset(self):
        at = _rodar_seletor(df=pd.DataFrame({"X": [1]}))
        assert at.selectbox[0].options == ["Todos", "BMG/Help"]
        assert at.session_state["_saida"] is None
