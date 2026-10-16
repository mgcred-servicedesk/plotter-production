"""
Sub-aba "Promessa Diária" de Reconquista (`tabs/analiticos.py`, V3).

`AppTest.from_function`: o filtro e a sub-nav sao widgets, so existem em
um run real. A tabela do detalhe e a primeira `st.dataframe` (as
quebras vem depois, em tabs).
"""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

# Colunas que o frame JAMAIS pode expor (LGPD / decisao V3): o teste
# poe todas no frame de entrada para provar que a tabela as filtra.
_PROIBIDAS = [
    "nu_matricula", "no_franqueado", "no_gerente_executivo",
    "no_gerente_regional", "no_gerente_canal_proprio",
    "no_gerente_loja", "no_coordenador_loja",
]


def _script_render_reconquista(reconquista):
    import streamlit as st  # noqa: F401  (necessario no script isolado)

    from src.dashboard.tabs.analiticos import _render_reconquista

    _render_reconquista(reconquista)


def _promessas(badge: str = "ok") -> pd.DataFrame:
    """3 elegiveis (ANA efetivada em 10/2026, ANA nao efetivada, SUP) +
    1 nao elegivel. `badge`: ok | indisponivel."""
    df = pd.DataFrame({
        "co_adesao": [1, 2, 3, 4],
        "dt_promessa": ["2026-09-10", "2026-09-11", "2026-09-12",
                        "2026-09-13"],
        "dt_retorno": [None, None, None, None],
        "retorno_inss": ["REGISTRO ACEITO", "NÃO ACEITO", None, None],
        "flag_elegibilidade": ["ELEGÍVEL", "ELEGÍVEL", "ELEGÍVEL",
                               "NÃO ELEGÍVEL"],
        "elegivel": [True, True, True, False],
        "status_mes_anterior": ["X"] * 4,
        "status_cliente_atual": ["PROMESSA"] * 4,
        "loja": ["L1", "L1", "L1", "L2"],
        "regiao": ["R1", "R1", "R1", "R2"],
        "consultor": ["ANA", "ANA", "SUP", "BRUNO"],
        "supervisor": ["SUP"] * 4,
        "efetivada": pd.array([True, False, False, False], dtype="boolean"),
        "efetivada_ref": ["10/2026", None, None, None],
    })
    if badge == "indisponivel":
        df["efetivada"] = pd.array([pd.NA] * 4, dtype="boolean")
        df["efetivada_ref"] = None
    for col in _PROIBIDAS:
        df[col] = "SEGREDO"
    return df


def _quebra_loja() -> pd.DataFrame:
    return pd.DataFrame({
        "loja": ["L1"], "regiao": ["R1"], "promessas": [3],
        "retorno_aceito": [1], "retorno_pendente": [1],
        "retorno_nao_aceito": [1], "fdr_e_promessa": [0],
        "so_promessa": [3],
        "efetivadas": pd.array([1], dtype="Int64"),
    })


def _quebra_consultor() -> pd.DataFrame:
    return pd.DataFrame({
        "consultor": ["ANA"], "promessas": [2],
        "retorno_aceito": [1], "retorno_pendente": [0],
        "retorno_nao_aceito": [1], "fdr_e_promessa": [0],
        "so_promessa": [2],
        "efetivadas": pd.array([1], dtype="Int64"),
    })


def _dict(status="ok", badge="ok") -> dict:
    ok = status == "ok"
    return {
        "ref_mes": 8, "ref_ano": 2026,
        "apuracao_mes": 9, "apuracao_ano": 2026,
        "totais": {
            "total": 0, "efetivadas": 2, "promessas": 3 if ok else None,
            "sem_reconquista": 0, "conversao": 0.0,
            "faixa": {"rotulo": "x"},
            "liga_status": "ok", "liga_listadas": 0,
            "liga_nao_contabilizadas": 0,
            "promessa_status": status,
            "nao_elegiveis": 1 if ok else None,
            "retorno_aceito": 1 if ok else None,
            "retorno_pendente": 1 if ok else None,
            "retorno_nao_aceito": 1 if ok else None,
            "retorno_outros": 0 if ok else None,
            "pct_retorno_aceito": 33.3 if ok else None,
            "promessas_efetivadas": (
                (1 if badge == "ok" else None) if ok else None
            ),
        },
        "por_loja": pd.DataFrame(),
        "por_loja_mes": pd.DataFrame(),
        "clientes": pd.DataFrame(),
        "clientes_todos": pd.DataFrame(),
        "liga": pd.DataFrame(),
        "promessas": _promessas(badge) if ok else pd.DataFrame(),
        "promessas_por_loja": _quebra_loja() if ok else pd.DataFrame(),
        "promessas_por_consultor": (
            _quebra_consultor() if ok else pd.DataFrame()
        ),
    }


def _rodar(dados: dict, nav: str | None = "Promessa Diária") -> AppTest:
    at = AppTest.from_function(
        _script_render_reconquista, kwargs=dict(reconquista=dados),
    )
    if nav is not None:
        at.session_state["nav_reconquista"] = nav
    at.run()
    assert not at.exception
    return at


def _tabela(at: AppTest, i: int = 0) -> pd.DataFrame:
    valor = at.dataframe[i].value
    return valor.data if hasattr(valor, "data") else valor


def _opcoes_nav(at: AppTest) -> list:
    """Rotulos da sub-nav (st.pills) lidos do proto do widget."""
    return [o.content for o in at.get("button_group")[0].proto.options]


@pytest.mark.unit
class TestSubNavPromessa:
    @pytest.mark.parametrize("status", ["ok", "nao_importada", "erro"])
    def test_aba_presente_quando_status_nao_e_fora(self, status):
        at = _rodar(_dict(status), nav=None)
        opcoes = _opcoes_nav(at)
        assert any("Promessa Diária" in o for o in opcoes)

    def test_aba_ausente_quando_fora(self):
        at = _rodar(_dict("fora"), nav=None)
        assert not any("Promessa Diária" in o for o in _opcoes_nav(at))

    def test_ordem_liga_promessa_por_loja_detalhamento(self):
        opcoes = _opcoes_nav(_rodar(_dict("ok"), nav=None))
        nomes = [o.split(":")[-1].split("·")[0].strip() for o in opcoes]
        assert nomes == ["Liga", "Promessa Diária", "Por Loja",
                         "Detalhamento"]


@pytest.mark.unit
class TestTabelaPromessa:
    def test_colunas_proibidas_ausentes_da_tabela(self):
        at = _rodar(_dict("ok"))
        for i in range(len(at.dataframe)):
            colunas = set(_tabela(at, i).columns)
            assert not colunas & set(_PROIBIDAS), (i, colunas)

    def test_nada_proibido_vaza_em_nenhum_texto_renderizado(self):
        at = _rodar(_dict("ok"))
        for i in range(len(at.dataframe)):
            assert "SEGREDO" not in _tabela(at, i).to_csv()

    def test_abre_so_nas_elegiveis(self):
        df = _tabela(_rodar(_dict("ok")))
        # Mais recente primeiro; a ADE 4 (nao elegivel) fica de fora.
        assert df["ADE"].tolist() == [3, 2, 1]

    def test_promessa_em_nome_do_supervisor_e_listada(self):
        df = _tabela(_rodar(_dict("ok")))
        assert "SUP" in df["Consultor"].tolist()

    def test_badge_efetivada_com_referencia_e_traco(self):
        df = _tabela(_rodar(_dict("ok"))).set_index("ADE")
        assert df.loc[1, "Efetivada"] == "✅ 10/2026"
        assert df.loc[2, "Efetivada"] == "—"

    def test_badge_indisponivel_nunca_vira_traco(self):
        df = _tabela(_rodar(_dict("ok", badge="indisponivel")))
        assert set(df["Efetivada"]) == {"indisponível"}

    def test_card_de_metricas_mostra_indisponivel_sem_badge(self):
        at = _rodar(_dict("ok", badge="indisponivel"))
        valores = {m.label: m.value for m in at.metric}
        assert valores["Já efetivadas"] == "indisponível"

    def test_metricas_batem_com_os_totais(self):
        at = _rodar(_dict("ok"))
        valores = {m.label: m.value for m in at.metric}
        assert valores["Promessas elegíveis"] == "3"
        assert valores["Não elegíveis"] == "1"
        assert valores["Pendentes"] == "1"


@pytest.mark.unit
class TestEstadosSemTabela:
    def test_nao_importada_avisa_e_nao_lista(self):
        at = _rodar(_dict("nao_importada"))
        assert "ainda não importada" in " ".join(
            w.value for w in at.warning)
        assert len(at.dataframe) == 0

    def test_erro_avisa_e_nao_lista(self):
        at = _rodar(_dict("erro"))
        assert "Não foi possível carregar a Promessa Diária" in " ".join(
            e.value for e in at.error)
        assert len(at.dataframe) == 0

    def test_promessas_por_consultor_none_mostra_aviso_e_mantem_o_resto(
        self
    ):
        d = _dict("ok")
        d["promessas_por_consultor"] = None
        at = _rodar(d)
        assert "Quebra por consultor indisponível" in " ".join(
            w.value for w in at.warning)
        # detalhe + quebra por loja seguem renderizados
        assert len(at.dataframe) == 2


@pytest.mark.unit
class TestCaptionTopo:
    def _caption(self, dados):
        return " ".join(c.value for c in _rodar(dados, nav=None).caption)

    def test_ok_fala_da_promessa_diaria(self):
        cap = self._caption(_dict("ok"))
        assert "Promessas: 3 elegíveis (Promessa Diária do mês)" in cap

    @pytest.mark.parametrize("status,trecho", [
        ("nao_importada", "Promessas: — (Promessa Diária não importada)"),
        ("erro", "Promessas: — (Promessa Diária indisponível)"),
    ])
    def test_sem_dado_vira_traco_nunca_zero(self, status, trecho):
        cap = self._caption(_dict(status))
        assert trecho in cap
        assert "Promessas: 0" not in cap

    def test_fora_mantem_o_texto_do_export(self):
        d = _dict("fora")
        d["totais"]["promessas"] = 7
        cap = self._caption(d)
        assert "Promessas: 7 (fim de relacionamento em 08/2026)" in cap
