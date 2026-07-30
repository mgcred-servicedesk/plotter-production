"""
Testes dos helpers puros de ``src/dashboard/loaders.py``
(``_mes_apuracao_seguinte``, ``_reanexar_regiao``,
``carregar_universo_lojas`` com fontes monkeypatched).

O cliente Supabase (``_sb()``) é lazy — instanciado só dentro das
funções de fetch — então o módulo importa sem nenhuma conexão.
"""
import pandas as pd
import pytest

from src.dashboard import loaders
from src.dashboard.loaders import (
    _colapsar_cadastro_recente,
    _mes_apuracao_seguinte,
    _preencher_categoria_fallback,
    _reanexar_regiao,
    _status_consultor_ativo,
    carregar_universo_lojas,
)


@pytest.mark.unit
class TestStatusConsultorAtivo:
    def test_ativo_passa(self):
        assert _status_consultor_ativo("Ativo (a)")
        assert _status_consultor_ativo("  ativo (a) ")

    def test_inativo_nao_passa(self):
        # Substring "ativo" pegaria "Inativo (a)" — o match é por prefixo.
        assert not _status_consultor_ativo("Inativo (a)")

    def test_desligado_e_licencas_nao_passam(self):
        assert not _status_consultor_ativo("Desligado (a)")
        assert not _status_consultor_ativo("Licenciado (a)")
        assert not _status_consultor_ativo("Licença Maternidade")

    def test_vazio_conta_como_ativo(self):
        # Linhas legadas sem status não somem do universo.
        assert _status_consultor_ativo("")
        assert _status_consultor_ativo(None)


@pytest.mark.unit
class TestColapsarCadastroRecente:
    def test_registro_mais_recente_vence(self):
        # Desligamento registrado em linha nova vence o 'Ativo (a)'
        # antigo (match de nome normalizado: caixa/espaços).
        rows = [
            {"nome": "Ana Silva", "status": "Ativo (a)",
             "updated_at": "2026-03-25T18:42:17+00:00"},
            {"nome": " ANA  SILVA ", "status": "Desligado (a)",
             "updated_at": "2026-07-08T15:17:33+00:00"},
        ]
        out = _colapsar_cadastro_recente(rows)
        assert len(out) == 1
        assert out[0]["status"] == "Desligado (a)"

    def test_sem_updated_at_mantem_primeiro(self):
        rows = [
            {"nome": "Ana", "status": "Ativo (a)"},
            {"nome": "Ana", "status": "Desligado (a)"},
        ]
        out = _colapsar_cadastro_recente(rows)
        assert len(out) == 1
        assert out[0]["status"] == "Ativo (a)"

    def test_nomes_distintos_preservados_em_ordem(self):
        rows = [
            {"nome": "Bia", "status": "Ativo (a)", "updated_at": "2026-01-01"},
            {"nome": "Ana", "status": "Ativo (a)", "updated_at": "2026-01-01"},
        ]
        out = _colapsar_cadastro_recente(rows)
        assert [r["nome"] for r in out] == ["Ana", "Bia"]

    def test_nome_vazio_ignorado(self):
        rows = [{"nome": "", "status": "Ativo (a)"}, {"nome": None}]
        assert _colapsar_cadastro_recente(rows) == []


@pytest.mark.unit
class TestMesApuracaoSeguinte:
    def test_mes_normal(self):
        assert _mes_apuracao_seguinte(6, 2026) == (7, 2026)
        assert _mes_apuracao_seguinte(11, 2025) == (12, 2025)

    def test_rollover_dezembro(self):
        assert _mes_apuracao_seguinte(12, 2025) == (1, 2026)


@pytest.mark.unit
class TestReanexarRegiao:
    def test_anexa_regiao_por_loja(self):
        pivot = pd.DataFrame({"LOJA": ["A", "B"], "META_PRATA": [10, 20]})
        fonte = pd.DataFrame({"LOJA": ["A", "B"], "REGIAO": ["R1", "R2"]})
        out = _reanexar_regiao(pivot, fonte)
        assert list(out.columns) == ["LOJA", "META_PRATA", "REGIAO"]
        assert dict(zip(out["LOJA"], out["REGIAO"])) == {"A": "R1", "B": "R2"}

    def test_loja_sem_regiao_fica_nan(self):
        pivot = pd.DataFrame({"LOJA": ["A", "C"], "META_PRATA": [10, 30]})
        fonte = pd.DataFrame({"LOJA": ["A"], "REGIAO": ["R1"]})
        out = _reanexar_regiao(pivot, fonte)
        assert out.loc[out["LOJA"] == "A", "REGIAO"].iloc[0] == "R1"
        assert pd.isna(out.loc[out["LOJA"] == "C", "REGIAO"].iloc[0])

    def test_dedup_mantem_primeira_regiao(self):
        pivot = pd.DataFrame({"LOJA": ["A"], "META_PRATA": [10]})
        fonte = pd.DataFrame({"LOJA": ["A", "A"], "REGIAO": ["R1", "R2"]})
        out = _reanexar_regiao(pivot, fonte)
        assert len(out) == 1
        assert out["REGIAO"].iloc[0] == "R1"


@pytest.mark.unit
class TestPreencherCategoriaFallback:
    """Contratos com produtos.categoria_id NULL no banco (migration 061).

    Vale para pagos, em analise e cancelados — os dois ultimos nao
    trazem grupo_meta/conta_pontuacao e nao devem ganhar colunas novas.
    """

    CATEGORIAS = pd.DataFrame({
        "codigo": ["CONSIG_PRIV", "ANT_BENEF"],
        "grupo_dashboard": ["CLT", "PACK"],
        "grupo_meta": ["CLT", "FGTS_ANT_BENEF_13"],
        "conta_valor": [True, True],
        "conta_pontuacao": [True, True],
    })

    @pytest.fixture(autouse=True)
    def _stub_categorias(self, monkeypatch):
        monkeypatch.setattr(
            loaders, "carregar_categorias", lambda: self.CATEGORIAS,
        )

    def test_preenche_categoria_e_grupo_por_tipo_produto(self):
        df = pd.DataFrame({
            "TIPO_PRODUTO": ["CLT", "ANT. DE BENEF.", "CNC"],
            "categoria_codigo": ["", None, "CNC"],
            "grupo_dashboard": [None, None, "CNC"],
            "conta_valor": [None, None, True],
        })
        out = _preencher_categoria_fallback(df)
        assert list(out["categoria_codigo"]) == [
            "CONSIG_PRIV", "ANT_BENEF", "CNC",
        ]
        assert list(out["grupo_dashboard"]) == ["CLT", "PACK", "CNC"]
        assert list(out["conta_valor"]) == [True, True, True]

    def test_tipo_desconhecido_fica_vazio(self):
        df = pd.DataFrame({
            "TIPO_PRODUTO": ["CONTA SIMPLES"],
            "categoria_codigo": [None],
            "grupo_dashboard": [None],
        })
        out = _preencher_categoria_fallback(df)
        assert out["categoria_codigo"].iloc[0] == ""
        assert pd.isna(out["grupo_dashboard"].iloc[0])

    def test_nao_cria_colunas_ausentes(self):
        # Em analise/cancelados nao expoem grupo_meta/conta_pontuacao.
        df = pd.DataFrame({
            "TIPO_PRODUTO": ["CLT"],
            "categoria_codigo": [""],
            "grupo_dashboard": [None],
        })
        out = _preencher_categoria_fallback(df)
        assert "grupo_meta" not in out.columns
        assert "conta_pontuacao" not in out.columns

    def test_df_vazio_ou_sem_coluna_passa_direto(self):
        assert _preencher_categoria_fallback(pd.DataFrame()).empty
        df = pd.DataFrame({"TIPO_PRODUTO": ["CLT"]})
        assert list(_preencher_categoria_fallback(df).columns) == [
            "TIPO_PRODUTO"
        ]


@pytest.mark.unit
class TestCarregarUniversoLojas:
    """Composição pura: mês corrente → lojas ativas; histórico → metas."""

    COLS = ["LOJA", "REGIAO", "REGIAO_ATUAL"]

    def test_mes_corrente_usa_lojas_ativas(self, monkeypatch):
        monkeypatch.setattr(loaders, "_eh_mes_atual", lambda m, a: True)
        monkeypatch.setattr(
            loaders, "carregar_lojas_ativas",
            lambda: pd.DataFrame({
                "LOJA": ["A", "C"], "REGIAO_ATUAL": ["R1", "R3"],
            }),
        )
        out = carregar_universo_lojas(7, 2026)
        assert list(out.columns) == self.COLS
        # REGIAO := REGIAO_ATUAL (organograma vigente = competência)
        assert list(out["REGIAO"]) == ["R1", "R3"]

    def test_historico_usa_metas_do_periodo(self, monkeypatch):
        monkeypatch.setattr(loaders, "_eh_mes_atual", lambda m, a: False)
        monkeypatch.setattr(
            loaders, "carregar_metas",
            lambda m, a: pd.DataFrame({
                "LOJA": ["A", "A", "B"],
                "REGIAO": ["R1", "R1", "R2"],
                "REGIAO_ATUAL": ["R9", "R9", "R2"],
                "META_PRATA": [1.0, 1.0, 2.0],
            }),
        )
        out = carregar_universo_lojas(1, 2026)
        assert list(out.columns) == self.COLS
        # Dedup por LOJA; REGIAO point-in-time preservada
        assert list(out["LOJA"]) == ["A", "B"]
        assert list(out["REGIAO"]) == ["R1", "R2"]

    def test_fontes_vazias_retornam_colunas_esperadas(self, monkeypatch):
        monkeypatch.setattr(loaders, "_eh_mes_atual", lambda m, a: True)
        monkeypatch.setattr(
            loaders, "carregar_lojas_ativas", lambda: pd.DataFrame(),
        )
        out = carregar_universo_lojas(7, 2026)
        assert out.empty
        assert list(out.columns) == self.COLS
