"""
Sub-aba "Carteira Elegível" de Reconquista e a saida das sub-abas do
export (`tabs/analiticos.py`) + o bloco "Clientes na esteira" do card.

A partir de 10/2026 o export antigo nao e mais importado: Por Loja e
Detalhamento saem da sub-nav e a Carteira Elegivel entra; antes disso,
o inverso (legado intocado). A carteira e carregada SO pela sub-aba —
o script stuba `carregar_carteira_elegivel` dentro do run.
"""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

_PROIBIDAS = [
    "nu_matricula", "no_franqueado", "no_gerente_executivo",
    "no_gerente_regional", "no_gerente_canal_proprio",
    "no_gerente_loja", "no_coordenador_loja",
]


def _script(reconquista, carteira):
    import streamlit as st  # noqa: F401  (necessario no script isolado)

    from src.dashboard.tabs import analiticos

    chamadas = st.session_state.setdefault("_chamadas_carteira", [])

    def _stub(mes, ano):
        chamadas.append((mes, ano))
        if isinstance(carteira, Exception):
            raise carteira
        return carteira

    analiticos.carregar_carteira_elegivel = _stub
    analiticos._render_reconquista(reconquista)


def _reconquista(mes=10, ano=2026) -> dict:
    return {
        "ref_mes": mes - 1, "ref_ano": ano,
        "apuracao_mes": mes, "apuracao_ano": ano,
        "totais": {
            "total": 0, "efetivadas": 0, "sem_reconquista": 0,
            "conversao": 0.0, "faixa": {"rotulo": "x"},
            "liga_status": "ok", "promessa_status": "ok", "promessas": 0,
        },
        "por_loja_mes": pd.DataFrame(),
        "clientes_todos": pd.DataFrame(),
        "liga": pd.DataFrame(),
        "promessas": pd.DataFrame(),
    }


def _carteira_df(badge="ok") -> pd.DataFrame:
    """Ja na ordem do loader: 1 prioridade, 2 baixa prioridade."""
    df = pd.DataFrame({
        "co_adesao": [1, 2],
        "baixa_prioridade": [False, True],
        "motivo_impedido_operar": [None, "AÇÃO CONTRA"],
        "loja": ["L1", "L1"],
        "regiao": ["R1", "R1"],
        "supervisor": ["SUP", "SUP"],
        "consultor": ["ANA", "ANA"],
        "saldo_carteira": [10.0, 900.0],
        "banco_origem": ["BMG", "BMG"],
        "banco_destino": [None, None],
        "regra_pagamento": ["1° dia Útil Normal"] * 2,
        "status_cliente_anterior": ["SEM RECONQUISTA", "FDR"],
        "link_reconquista": [
            "https://dnabmg.help.com.br/public.html#/x",
            "javascript:alert(1)",
        ],
        "prometido": pd.array([True, False], dtype="boolean"),
        "prometido_ref": ["10/2026", None],
        "efetivado": pd.array([False, False], dtype="boolean"),
        "efetivado_ref": [None, None],
    })
    if badge == "indisponivel":
        df["prometido"] = pd.array([pd.NA] * 2, dtype="boolean")
    for col in _PROIBIDAS:
        df[col] = "SEGREDO"
    return df


def _dados(status="ok", badge="ok") -> dict:
    ok = status == "ok"
    vazio = pd.DataFrame()
    return {
        "status": status,
        "carteira": _carteira_df(badge) if ok else vazio,
        "totais": {
            "elegiveis": 2, "prioridade": 1, "baixa_prioridade": 1,
            "nao_elegiveis": 0, "fdr_anterior": 1, "saldo_total": 910.0,
            "saldo_prioridade": 10.0, "saldo_zero": 0, "sem_consultor": 0,
            "prometidos": 1 if badge == "ok" else None, "efetivados": 0,
        } if ok else None,
        # Quebras COM a coluna `saldo` (como o loader entrega): a tela
        # tem que omiti-la.
        "por_loja": pd.DataFrame({
            "loja": ["L1"], "regiao": ["R1"], "elegiveis": [2],
            "prioridade": [1], "baixa_prioridade": [1], "fdr_anterior": [1],
            "saldo": [910.0],
            "prometidos": pd.array([1], dtype="Int64"),
            "efetivados": pd.array([0], dtype="Int64"),
        }) if ok else vazio,
        "por_consultor": vazio,
        "por_banco": pd.DataFrame({
            "banco_origem": ["BMG"], "clientes": [2], "saldo": [910.0],
        }) if ok else vazio,
        "por_regra": vazio, "por_motivo": vazio,
    }


def _rodar(reconquista, carteira=None, nav="Carteira Elegível"):
    at = AppTest.from_function(
        _script, kwargs=dict(
            reconquista=reconquista,
            carteira=_dados() if carteira is None else carteira,
        ),
    )
    if nav is not None:
        at.session_state["nav_reconquista"] = nav
    at.run()
    assert not at.exception
    return at


def _nomes_nav(at) -> list:
    opcoes = [o.content for o in at.get("button_group")[0].proto.options]
    return [o.split(":")[-1].split("·")[0].strip() for o in opcoes]


def _tabela(at, i=0) -> pd.DataFrame:
    valor = at.dataframe[i].value
    return valor.data if hasattr(valor, "data") else valor


@pytest.mark.unit
class TestSubNav:
    def test_a_partir_de_10_2026_carteira_substitui_o_export(self):
        nomes = _nomes_nav(_rodar(_reconquista(10, 2026), nav=None))
        assert nomes == ["Liga", "Promessa Diária", "Carteira Elegível"]

    def test_09_2026_mantem_as_sub_abas_do_export(self):
        nomes = _nomes_nav(_rodar(_reconquista(9, 2026), nav=None))
        assert nomes == ["Liga", "Promessa Diária", "Por Loja",
                         "Detalhamento"]

    def test_carteira_so_e_lida_quando_a_sub_aba_abre(self):
        at = _rodar(_reconquista(10, 2026), nav="Liga")
        assert at.session_state["_chamadas_carteira"] == []
        at = _rodar(_reconquista(10, 2026))
        assert at.session_state["_chamadas_carteira"] == [(10, 2026)]


@pytest.mark.unit
class TestTabela:
    def test_baixa_prioridade_fica_abaixo_mesmo_com_saldo_maior(self):
        df = _tabela(_rodar(_reconquista()))
        assert df["ADE"].tolist() == [1, 2]
        assert df["Atuação"].tolist() == ["Prioridade", "Baixa prioridade"]

    def test_so_https_vira_link(self):
        df = _tabela(_rodar(_reconquista())).set_index("ADE")
        assert df.loc[1, "Jornada"].startswith("https://")
        assert df.loc[2, "Jornada"] is None or pd.isna(df.loc[2, "Jornada"])

    def test_colunas_proibidas_nao_vazam(self):
        at = _rodar(_reconquista())
        for i in range(len(at.dataframe)):
            tab = _tabela(at, i)
            assert not set(tab.columns) & set(_PROIBIDAS)
            assert "SEGREDO" not in tab.to_csv()

    def test_badge_prometido(self):
        df = _tabela(_rodar(_reconquista())).set_index("ADE")
        assert df.loc[1, "Trabalhado"] == "🤝 Prometido 10/2026"
        assert df.loc[2, "Trabalhado"] == "—"

    def test_badge_indisponivel_nunca_vira_traco(self):
        df = _tabela(_rodar(_reconquista(), _dados(badge="indisponivel")))
        assert set(df["Trabalhado"]) == {"indisponível"}

    def test_saldo_omitido_em_metricas_detalhe_e_quebras(self):
        """Decisao do usuario (16/10/2026): saldo da carteira nao aparece
        no dashboard — nem card, nem coluna, nem valor."""
        at = _rodar(_reconquista())
        assert not any("aldo" in m.label for m in at.metric)
        assert len(at.dataframe) >= 3   # detalhe + Por Loja + Banco
        for i in range(len(at.dataframe)):
            tab = _tabela(at, i)
            assert not any("aldo" in str(c) for c in tab.columns), (
                i, list(tab.columns))
            csv = tab.to_csv()
            for valor in ("910", "900", "10.5"):
                assert valor not in csv, (i, valor)

    def test_metricas(self):
        valores = {m.label: m.value for m in _rodar(_reconquista()).metric}
        assert valores["Elegíveis"] == "2"
        assert valores["Baixa prioridade"] == "1"


@pytest.mark.unit
class TestEstados:
    @pytest.mark.parametrize("status, tipo, trecho", [
        ("nao_importada", "warning", "ainda não importada"),
        ("erro", "error", "Não foi possível carregar"),
    ])
    def test_avisa_e_nao_lista(self, status, tipo, trecho):
        at = _rodar(_reconquista(), _dados(status))
        assert any(trecho in e.value for e in getattr(at, tipo))
        assert len(at.dataframe) == 0
        assert len(at.metric) == 0

    def test_excecao_inesperada_vira_erro_e_nao_quebra(self):
        at = _rodar(_reconquista(), RuntimeError("boom"))
        assert any("Não foi possível carregar" in e.value for e in at.error)


# ── Bloco "Clientes na esteira" do card ──

def _script_card(dados, mes, ano):
    import streamlit as st  # noqa: F401

    from src.dashboard.ui.kpi_cards_reforma import render_cards_reconquista

    render_cards_reconquista(dados, mes, ano)


def _dados_card():
    return {
        "ref_mes": 9, "ref_ano": 2026,
        "totais": {
            "total": 10, "total_geral": 10, "efetivadas": 1,
            "promessas": 2, "sem_reconquista": 0, "conversao": 10.0,
            "faixa": {"rotulo": "x", "cor": "#000"},
            "cobranca_consignavel": 0, "acelerador_perfil": "gestor",
            "faixa_agregada": None, "liga_status": "ok",
            "liga_nao_contabilizadas": 0, "promessa_status": "ok",
            "nao_elegiveis": 0, "retorno_aceito": 0, "retorno_pendente": 0,
            "retorno_nao_aceito": 0, "retorno_outros": 0,
            "pct_retorno_aceito": 0.0, "promessas_efetivadas": 0,
        },
        "por_consultor": None,
        "prox": {
            "apuracao_mes": 11, "apuracao_ano": 2026,
            "ref_mes": 10, "ref_ano": 2026,
            "totais": {"total": 50, "efetivadas": 0, "promessas": 5,
                       "sem_reconquista": 45},
        },
    }


def _tem_esteira(mes, ano) -> bool:
    at = AppTest.from_function(
        _script_card, kwargs=dict(dados=_dados_card(), mes=mes, ano=ano),
    )
    at.run()
    assert not at.exception
    return any("Clientes na esteira" in m.value for m in at.markdown)


@pytest.mark.unit
class TestClientesNaEsteira:
    def test_some_com_a_carteira_vigente(self):
        assert not _tem_esteira(10, 2026)

    def test_continua_antes_da_carteira(self):
        assert _tem_esteira(9, 2026)
