"""
Testes dos helpers puros de ``src/dashboard/tabs/analiticos.py``.

``_opcoes_coluna`` alimenta os selectbox de Produto/Subproduto do
detalhamento: precisa ignorar NaN (pagos) e "" (em analise/cancelados,
onde o join de produto nao resolveu) sem quebrar o ``sorted``.

O Detalhamento de Reconquista tem, alem disso, um render testado via
``AppTest``: o escopo (mes selecionado x todos os meses) e um widget, e
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
# verdade. A funcao precisa ser top-level e autocontida (imports no
# corpo).

def _script_render_detalhamento(clientes):
    import streamlit as st  # noqa: F401  (necessario no script isolado)

    from src.dashboard.tabs.analiticos import (
        _render_reconquista_detalhamento,
    )

    _render_reconquista_detalhamento(clientes, "08/2026")


def _clientes_reconquista() -> pd.DataFrame:
    """Um lead por mes de referencia, ja marcado como o loader marca.

    Mes selecionado 08/2026. Pelo eixo da CAMPANHA (defasado), ref 07 e
    a apuracao vigente e ref 08 e a proxima; pelo eixo do ANALITICO (fim
    de relacionamento), o recorte padrao e ref 08 — os dois se cruzam de
    proposito, para o teste distinguir um do outro.
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


def _rodar() -> AppTest:
    at = AppTest.from_function(
        _script_render_detalhamento,
        kwargs=dict(clientes=_clientes_reconquista()),
    )
    at.run()
    assert not at.exception
    return at


@pytest.mark.unit
class TestRenderReconquistaDetalhamento:
    """Desde 10/2026 o Detalhamento e so "Todos os meses": o export virou
    analitico (a apuracao e a liga), sem escopo do mes selecionado e sem
    as colunas Apuracao/Vigencia da campanha defasada.
    """

    def test_lista_todos_os_meses_do_mais_recente_ao_mais_antigo(self):
        df = _tabela(_rodar())
        assert df["Cod ADE"].tolist() == [4, 3, 2, 1]
        assert df["Mês Fim Relac."].tolist() == [
            "08/2026", "07/2026", "06/2026", "05/2026",
        ]

    def test_sem_colunas_da_apuracao_defasada(self):
        cols = set(_tabela(_rodar()).columns)
        assert "Mês Fim Relac." in cols
        assert not {"Apuração", "Vigência"} & cols

    def test_sem_pill_de_escopo(self):
        at = _rodar()
        assert "rec_det_escopo" not in at.session_state
        assert len(at.button_group) == 0

    def test_filtro_de_fim_de_relacionamento_sempre_presente(self):
        # Loja + Fim de Relacionamento.
        assert len(_rodar().multiselect) == 2

    def test_caption_fala_de_todos_os_meses_sem_defasagem(self):
        caption = _rodar().caption[0].value
        assert "todos os meses" in caption
        assert "05/2026 a 08/2026" in caption
        assert "defasagem" not in caption


# ── Sub-aba Reconquista: qual quebra por loja chega na tela ──────────
#
# A tela mostra o eixo do ANALITICO (`por_loja_mes`, fim de
# relacionamento no mes selecionado), nao o da apuracao defasada
# (`por_loja`). Os dois vem no mesmo dict do loader, entao o unico jeito
# de provar qual foi lido e povoar as duas chaves com lojas diferentes.

def _script_render_reconquista(reconquista):
    import streamlit as st  # noqa: F401  (necessario no script isolado)

    from src.dashboard.tabs.analiticos import _render_reconquista

    _render_reconquista(reconquista)


def _quebra_por_loja(loja: str) -> pd.DataFrame:
    return pd.DataFrame([{
        "loja": loja,
        "regiao": "R1",
        "total_clientes": 2,
        "efetivadas": 1,
        "promessas": 1,
        "sem_reconquista": 0,
        "saldo_medio": 100.0,
        "dias_atraso_medio": 3.0,
        "conversao_pct": 50.0,
        "faixa": "+20% sobre prêmio CNC",
    }])


def _dict_reconquista() -> dict:
    """Mes selecionado 09/2026; apuracao vigente le fim relac. 08/2026."""
    return {
        "ref_mes": 8, "ref_ano": 2026,
        "apuracao_mes": 9, "apuracao_ano": 2026,
        "totais": {
            "total": 2, "efetivadas": 1, "promessas": 1,
            "sem_reconquista": 0, "conversao": 50.0,
            "faixa": {"rotulo": "+20% sobre prêmio CNC"},
        },
        "por_loja": _quebra_por_loja("LOJA DA APURACAO"),
        "por_loja_mes": _quebra_por_loja("LOJA DO MES"),
        "clientes": _clientes_reconquista(),
        "clientes_todos": _clientes_reconquista(),
    }


@pytest.mark.unit
class TestRenderReconquistaPorLoja:
    def test_por_loja_usa_o_mes_selecionado_nao_a_apuracao(self):
        at = AppTest.from_function(
            _script_render_reconquista,
            kwargs=dict(reconquista=_dict_reconquista()),
        )
        at.session_state["nav_reconquista"] = "Por Loja"
        at.run()
        assert not at.exception
        lojas = _tabela(at)["Loja"].tolist()
        assert lojas == ["LOJA DO MES"]

    def test_caption_avisa_que_a_faixa_e_previa(self):
        at = AppTest.from_function(
            _script_render_reconquista,
            kwargs=dict(reconquista=_dict_reconquista()),
        )
        at.session_state["nav_reconquista"] = "Por Loja"
        at.run()
        captions = " ".join(c.value for c in at.caption)
        # O mes do recorte, a apuracao que vale pro premio e o aviso.
        assert "09/2026" in captions
        assert "08/2026" in captions
        assert "prévia" in captions

    def test_sem_coluna_faixa_premio(self):
        """Faixa Premio saiu em 10/2026: o export nao decide premio."""
        at = AppTest.from_function(
            _script_render_reconquista,
            kwargs=dict(reconquista=_dict_reconquista()),
        )
        at.session_state["nav_reconquista"] = "Por Loja"
        at.run()
        assert not at.exception
        assert "Faixa Prêmio" not in _tabela(at).columns


# ── Sub-aba Liga ─────────────────────────────────────────────────────


def _liga() -> pd.DataFrame:
    return pd.DataFrame([
        {"co_adesao": 10, "qtde": 1, "loja": "LOJA A", "regiao": "R1",
         "consultor": "ANA", "data_reconquista": "2026-09-16"},
        {"co_adesao": 11, "qtde": 1, "loja": "LOJA B", "regiao": "R1",
         "consultor": "BRUNO", "data_reconquista": "2026-09-16"},
        {"co_adesao": 12, "qtde": 0, "loja": "LOJA A", "regiao": "R1",
         "consultor": "ANA", "data_reconquista": "2026-09-16"},
    ])


def _dict_liga(status: str = "ok") -> dict:
    d = _dict_reconquista()
    d["totais"] = {
        **d["totais"], "efetivadas": 2, "liga_status": status,
        "liga_listadas": 3, "liga_nao_contabilizadas": 1,
    }
    d["liga"] = _liga() if status == "ok" else pd.DataFrame()
    return d


def _rodar_liga(status: str = "ok", contab: str | None = None) -> AppTest:
    at = AppTest.from_function(
        _script_render_reconquista,
        kwargs=dict(reconquista=_dict_liga(status)),
    )
    if contab is not None:
        at.session_state["rec_liga_contab"] = contab
    at.run()
    assert not at.exception
    return at


@pytest.mark.unit
class TestRenderReconquistaLiga:
    def test_abre_na_liga_quando_a_apuracao_e_da_liga(self):
        df = _tabela(_rodar_liga())
        assert "Contabilizada" in df.columns

    def test_filtro_padrao_mostra_so_contabilizadas(self):
        df = _tabela(_rodar_liga())
        assert df["Cod ADE"].tolist() == [10, 11]
        assert set(df["Contabilizada"]) == {"Sim"}

    def test_nao_contabilizadas_a_um_filtro(self):
        df = _tabela(_rodar_liga(contab="Não contabilizadas"))
        assert df["Cod ADE"].tolist() == [12]

    def test_todas_lista_as_duas(self):
        assert len(_tabela(_rodar_liga(contab="Todas"))) == 3

    def test_caption_do_topo_usa_a_contagem_da_liga_sem_conversao(self):
        captions = " ".join(c.value for c in _rodar_liga().caption)
        assert "2 contabilizadas pela liga" in captions
        assert "Conversão" not in captions

    def test_liga_nao_importada_avisa_em_vez_de_zerar(self):
        at = _rodar_liga(status="nao_importada")
        avisos = " ".join(w.value for w in at.warning)
        assert "ainda não importada" in avisos
        assert len(at.dataframe) == 0
        captions = " ".join(c.value for c in at.caption)
        assert "contabilizadas pela liga" not in captions

    def test_antes_da_liga_abre_no_por_loja(self):
        at = AppTest.from_function(
            _script_render_reconquista,
            kwargs=dict(reconquista=_dict_reconquista()),
        )
        at.run()
        assert not at.exception
        assert _tabela(at)["Loja"].tolist() == ["LOJA DO MES"]


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


# ── Expanders de Aceleradores: critério canônico ─────────────────────
#
# Os expanders de Emissão e Super Conta reimplementavam a máscara
# inline — uma quarta superfície para "o que é Emissão / Super Conta",
# além de `mascaras_aceleradores` (kpis/gerais.py), `kpis/produtos.py`
# e `tabs/produtos.py::_PRODS_QTD`. Passaram a usar a canônica.
#
# `_criterio_inline_*` abaixo é o código ANTIGO, copiado verbatim como
# referência: a troca só é válida se as duas marcam as mesmas linhas
# em cada fonte (pagos COM a flag `is_super_conta`; em análise e
# cancelados SEM ela) e nos casos de borda de texto.

def _criterio_inline_emissao(fonte):
    from src.config.settings import PRODUTOS_EMISSAO

    return fonte["TIPO_PRODUTO"].astype(str).str.upper().isin(
        {p.upper() for p in PRODUTOS_EMISSAO}
    )


def _criterio_inline_super_conta(fonte):
    return (
        fonte["SUBTIPO"].fillna("").astype(str).str.strip().str.upper()
        == "SUPER CONTA"
    )


_TIPOS = ["EMISSAO", "emissao cc", "EMISSAO CB", "CNC", "", None, np.nan]
_SUBTIPOS = [" super conta ", "SUPER CONTA", "NOVO", "", None, np.nan, "SUPERCONTA"]


def _fontes_adversariais():
    n = len(_TIPOS) * len(_SUBTIPOS)
    tipos = [t for t in _TIPOS for _ in _SUBTIPOS]
    subtipos = [s for _ in _TIPOS for s in _SUBTIPOS]
    base = pd.DataFrame({
        "TIPO_PRODUTO": tipos, "SUBTIPO": subtipos, "VALOR": [1.0] * n,
    })
    pagos = base.copy()
    # A flag como a consolidação a deriva (kpis/consolidacao.py).
    pagos["is_super_conta"] = (
        pagos["SUBTIPO"].astype(str).str.strip().str.upper() == "SUPER CONTA"
    )
    return {
        "pagos (com flag)": pagos,
        "em análise (sem flag)": base.copy(),
        "tipo todo NaN float": pd.DataFrame({
            "TIPO_PRODUTO": [np.nan] * 3, "SUBTIPO": [np.nan] * 3,
        }),
        "tipo todo None": pd.DataFrame(
            [{"TIPO_PRODUTO": None, "SUBTIPO": None}] * 3
        ),
    }


@pytest.mark.unit
class TestLinhasAceleradorIgualAoCriterioAntigo:
    @pytest.mark.parametrize("nome_fonte", list(_fontes_adversariais()))
    def test_emissao(self, nome_fonte):
        from src.dashboard.tabs.analiticos import _linhas_acelerador

        fonte = _fontes_adversariais()[nome_fonte]
        esperado = fonte[_criterio_inline_emissao(fonte)]
        pd.testing.assert_frame_equal(
            _linhas_acelerador(fonte, "Emissao"), esperado
        )

    @pytest.mark.parametrize("nome_fonte", list(_fontes_adversariais()))
    def test_super_conta(self, nome_fonte):
        from src.dashboard.tabs.analiticos import _linhas_acelerador

        fonte = _fontes_adversariais()[nome_fonte]
        esperado = fonte[_criterio_inline_super_conta(fonte)]
        pd.testing.assert_frame_equal(
            _linhas_acelerador(fonte, "Super Conta"), esperado
        )

    def test_segue_a_definicao_canonica(self, monkeypatch):
        """O mecanismo, não a aparência: se a regra canônica mudar, o
        expander muda junto — é o motivo da troca."""
        import src.dashboard.tabs.analiticos as mod

        fonte = pd.DataFrame({"TIPO_PRODUTO": ["X", "Y"], "SUBTIPO": ["", ""]})
        monkeypatch.setattr(
            mod, "mascaras_aceleradores",
            lambda df: {"Emissao": pd.Series([False, True], index=df.index)},
        )
        assert _linhas_acelerador_de(mod, fonte)["TIPO_PRODUTO"].tolist() == ["Y"]


def _linhas_acelerador_de(mod, fonte):
    return mod._linhas_acelerador(fonte, "Emissao")


@pytest.mark.unit
class TestNrAde:
    def test_prefere_num_proposta_e_cai_para_contrato_id(self):
        from src.dashboard.tabs.analiticos import _nr_ade

        df = pd.DataFrame({
            "NUM_PROPOSTA": ["123", "", None],
            "CONTRATO_ID": [1, 2, 3],
        })
        assert _nr_ade(df).tolist() == ["123", "2", "3"]

    def test_sem_num_proposta_usa_contrato_id(self):
        from src.dashboard.tabs.analiticos import _nr_ade

        df = pd.DataFrame({"CONTRATO_ID": [7, 8]})
        assert _nr_ade(df).tolist() == ["7", "8"]
