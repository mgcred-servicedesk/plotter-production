"""
Testes das tools do chat de IA (``src/dashboard/chat_ia/tools.py``).

As tools nunca calculam KPI sozinhas: cada uma reusa uma função já
testada de ``kpis/rankings.py`` ou ``kpis/comparativos.py`` sobre um
``ChatContext`` sintético. Aqui validamos o *reshape* (dict de saída),
a validação de entrada (entidade/critério inválidos) e o isolamento de
Supabase via monkeypatch no namespace de ``chat_ia.tools`` — nunca no
módulo de origem (``loaders``/``rls``/``ui.sidebar``), pois é lá que o
``tools.py`` resolve os nomes em tempo de chamada.
"""
import pandas as pd
import pytest

import src.dashboard.chat_ia.tools as tools_mod
from src.dashboard.chat_ia.tools import (
    TOOLS_SCHEMA,
    ChatContext,
    construir_dispatch,
    tool_comparar_entidades,
    tool_listar_sem_producao,
    tool_ranking_periodo,
    tool_resumo_kpis_periodo,
)
from src.dashboard.kpis.comparativos import calcular_evolucao_por_entidade
from src.shared.dias_uteis import calcular_dias_uteis


def _contexto(**overrides) -> ChatContext:
    """``ChatContext`` sintético com defaults inertes; sobrescreva só o
    necessário via ``_replace`` (NamedTuple)."""
    base = ChatContext(
        df=pd.DataFrame(),
        df_metas=pd.DataFrame(),
        df_sup=pd.DataFrame(),
        df_analise=pd.DataFrame(),
        df_cancelados=pd.DataFrame(),
        kpis={},
        kpis_qtd={},
        kpis_analise={},
        kpis_cancel={},
        medias={},
        mes=3,
        ano=2026,
        dia_atual=15,
        du_decorridos=10,
        role="gerente",
    )
    return base._replace(**overrides)


def _mockar_periodo_comparacao(
    monkeypatch, df_cmp, df_metas_cmp=None, df_sup_cmp=None,
):
    """Substitui as dependências externas de ``_carregar_periodo_comparacao``
    no namespace de ``chat_ia.tools``.

    ``calcular_dias_uteis`` NÃO é mockado — roda de verdade (é cálculo
    de calendário puro); a fixture ``sem_feriados`` do teste chamador
    neutraliza o único ponto que tocaria o Supabase (feriados).
    """
    df_metas_cmp = pd.DataFrame() if df_metas_cmp is None else df_metas_cmp
    df_sup_cmp = pd.DataFrame() if df_sup_cmp is None else df_sup_cmp
    monkeypatch.setattr(
        tools_mod,
        "consolidar_dados",
        lambda mes, ano: (df_cmp, df_metas_cmp, df_sup_cmp),
    )
    monkeypatch.setattr(tools_mod, "aplicar_rls", lambda df: df)
    monkeypatch.setattr(tools_mod, "aplicar_filtros_ui", lambda df: df)
    monkeypatch.setattr(
        tools_mod, "aplicar_rls_supervisores", lambda df_sup, df_dados: df_sup,
    )


@pytest.mark.unit
class TestToolResumoKpisPeriodo:
    def test_shape_com_kpis_preenchidos(self):
        contexto = _contexto(
            mes=3,
            ano=2026,
            kpis={
                "total_vendas": 100000.0,
                "total_pontos": 50000.0,
                "meta_prata": 80000.0,
                "perc_ating_prata": 62.5,
                "perc_ating_ouro": 41.6,
                "projecao": 120000.0,
                "perc_proj": 150.0,
                "ticket_medio": 850.5,
                "num_lojas": 12,
                "num_consultores": 45,
                "du_total": 21,
                "du_decorridos": 10,
            },
            kpis_analise={"valor_analise": 5000.0, "qtd_analise": 3},
            kpis_cancel={
                "valor_cancelados": 2000.0,
                "qtd_cancelados": 2,
                "indice_perda": 4.0,
            },
        )

        resultado = tool_resumo_kpis_periodo(contexto, {})

        assert set(resultado) == {
            "mes", "ano", "total_vendas", "total_pontos", "meta_prata",
            "perc_atingimento_prata", "perc_atingimento_ouro",
            "projecao_fechamento", "perc_projecao", "ticket_medio",
            "num_lojas", "num_consultores", "du_total", "du_decorridos",
            "valor_em_analise", "qtd_em_analise", "valor_cancelado",
            "qtd_cancelada", "indice_perda_pct",
        }
        assert resultado["mes"] == 3
        assert resultado["ano"] == 2026
        assert resultado["total_vendas"] == pytest.approx(100000.0)
        assert resultado["perc_atingimento_prata"] == pytest.approx(62.5)
        assert resultado["perc_atingimento_ouro"] == pytest.approx(41.6)
        assert resultado["ticket_medio"] == pytest.approx(850.5)
        assert resultado["num_lojas"] == 12
        assert resultado["valor_em_analise"] == pytest.approx(5000.0)
        assert resultado["qtd_em_analise"] == 3
        assert resultado["valor_cancelado"] == pytest.approx(2000.0)
        assert resultado["indice_perda_pct"] == pytest.approx(4.0)

    def test_dicts_vazios_nao_lanca_keyerror(self):
        # kpis / kpis_analise / kpis_cancel todos {} — nenhum .get()
        # pode explodir; tudo cai no default declarado na tool.
        contexto = _contexto()

        resultado = tool_resumo_kpis_periodo(contexto, {})

        assert resultado["total_vendas"] == 0.0
        assert resultado["perc_atingimento_prata"] == 0.0
        assert resultado["num_lojas"] == 0
        assert resultado["valor_em_analise"] == 0.0
        assert resultado["qtd_em_analise"] == 0
        assert resultado["valor_cancelado"] == 0.0
        assert resultado["qtd_cancelada"] == 0
        assert resultado["indice_perda_pct"] == 0.0


@pytest.mark.unit
class TestToolRankingPeriodo:
    """Usa os fixtures compartilhados ``df_rank``/``df_metas_lojas``
    (mesmos valores já verificados em ``test_kpis_rankings.py``)."""

    def test_loja_atingimento(self, df_rank, df_metas_lojas):
        contexto = _contexto(df=df_rank, df_metas=df_metas_lojas)

        resultado = tool_ranking_periodo(
            contexto, {"entidade": "loja", "criterio": "atingimento"},
        )

        assert resultado["entidade"] == "loja"
        assert resultado["criterio"] == "atingimento"
        primeiro = resultado["resultados"][0]
        assert primeiro["posicao"] == 1
        assert primeiro["nome"] == "A"
        assert primeiro["atingimento_pct"] == pytest.approx(40.0)
        assert primeiro["ticket_medio"] == pytest.approx(750.0)

    def test_consultor_atingimento(self, df_rank, df_metas_lojas):
        contexto = _contexto(df=df_rank, df_metas=df_metas_lojas)

        resultado = tool_ranking_periodo(
            contexto, {"entidade": "consultor", "criterio": "atingimento"},
        )

        por_nome = {linha["nome"]: linha for linha in resultado["resultados"]}
        # B tem 2 consultores → meta rateada 1000 cada (mesmos valores
        # de TestCalcularRankingConsultores.test_meta_rateada_...)
        assert por_nome["Pedro"]["atingimento_pct"] == pytest.approx(6.0)
        assert por_nome["João"]["atingimento_pct"] == pytest.approx(40.0)

    def test_loja_pontos(self, df_rank):
        contexto = _contexto(df=df_rank)

        resultado = tool_ranking_periodo(
            contexto, {"entidade": "loja", "criterio": "pontos"},
        )

        primeiro = resultado["resultados"][0]
        assert primeiro["nome"] == "B"
        assert primeiro["pontos"] == pytest.approx(460.0)

    def test_consultor_pontos(self, df_rank):
        contexto = _contexto(df=df_rank)

        resultado = tool_ranking_periodo(
            contexto, {"entidade": "consultor", "criterio": "pontos"},
        )

        ultimo = resultado["resultados"][-1]
        assert ultimo["nome"] == "Pedro"
        assert ultimo["pontos"] == pytest.approx(60.0)

    def test_criterio_invalido_retorna_erro_sem_lancar(
        self, df_rank, df_metas_lojas,
    ):
        contexto = _contexto(df=df_rank, df_metas=df_metas_lojas)

        resultado = tool_ranking_periodo(
            contexto, {"entidade": "loja", "criterio": "bogus"},
        )

        assert "erro" in resultado

    def test_entidade_invalida_retorna_erro_sem_lancar(
        self, df_rank, df_metas_lojas,
    ):
        contexto = _contexto(df=df_rank, df_metas=df_metas_lojas)

        resultado = tool_ranking_periodo(
            contexto, {"entidade": "regiao", "criterio": "atingimento"},
        )

        assert "erro" in resultado

    def test_dataframe_vazio_nao_lanca(self):
        df_vazio = pd.DataFrame({
            "VALOR": pd.Series(dtype=float),
            "pontos": pd.Series(dtype=float),
        })
        contexto = _contexto(df=df_vazio)

        resultado = tool_ranking_periodo(
            contexto, {"entidade": "loja", "criterio": "atingimento"},
        )

        assert resultado == {
            "entidade": "loja", "criterio": "atingimento", "resultados": [],
        }


@pytest.mark.unit
class TestToolListarSemProducao:
    @staticmethod
    def _df_producao():
        return pd.DataFrame({
            "LOJA": ["A", "A", "B"],
            "CONSULTOR": ["João", "Maria", "Pedro"],
            "VALOR": [1000.0, 500.0, 800.0],
        })

    def test_lojas_sem_producao(self, monkeypatch):
        universo = pd.DataFrame({
            "LOJA": ["A", "B", "C"], "REGIAO": ["R1", "R2", "R3"],
        })
        monkeypatch.setattr(
            tools_mod, "carregar_universo_lojas", lambda mes, ano: universo,
        )
        monkeypatch.setattr(tools_mod, "aplicar_rls", lambda df: df)
        monkeypatch.setattr(tools_mod, "aplicar_filtros_ui", lambda df: df)

        contexto = _contexto(df=self._df_producao())
        resultado = tool_listar_sem_producao(contexto, {"entidade": "loja"})

        assert resultado == {"entidade": "loja", "total": 1, "nomes": ["C"]}

    def test_consultores_sem_producao(self, monkeypatch):
        universo = pd.DataFrame({
            "CONSULTOR": ["João", "Maria", "Pedro", "Ana", "Carlos"],
            "LOJA": ["A", "B", "B", "C", "C"],
            "REGIAO": ["R1", "R2", "R2", "R3", "R3"],
        })
        monkeypatch.setattr(
            tools_mod, "carregar_consultores_ativos", lambda: universo,
        )
        monkeypatch.setattr(tools_mod, "aplicar_rls", lambda df: df)
        monkeypatch.setattr(tools_mod, "aplicar_filtros_ui", lambda df: df)

        contexto = _contexto(df=self._df_producao())
        resultado = tool_listar_sem_producao(
            contexto, {"entidade": "consultor"},
        )

        assert resultado["entidade"] == "consultor"
        assert resultado["total"] == 2
        assert resultado["nomes"] == ["Ana", "Carlos"]

    def test_falha_ao_carregar_universo_retorna_erro(self, monkeypatch):
        def _boom(mes, ano):
            raise RuntimeError("supabase indisponível")

        monkeypatch.setattr(tools_mod, "carregar_universo_lojas", _boom)
        monkeypatch.setattr(tools_mod, "aplicar_rls", lambda df: df)
        monkeypatch.setattr(tools_mod, "aplicar_filtros_ui", lambda df: df)

        contexto = _contexto(df=self._df_producao())
        resultado = tool_listar_sem_producao(contexto, {"entidade": "loja"})

        assert "erro" in resultado


@pytest.mark.unit
class TestToolCompararEntidades:
    def test_entidade_invalida_retorna_erro_sem_lancar(self):
        contexto = _contexto()

        resultado = tool_comparar_entidades(contexto, {"entidade": "regiao"})

        assert "erro" in resultado

    def test_resultado_basico_bate_com_calculo_direto(
        self, monkeypatch, sem_feriados,
    ):
        df_atual = pd.DataFrame({
            "LOJA": ["A", "B"], "CONSULTOR": ["João", "Maria"],
            "VALOR": [1000.0, 1500.0],
        })
        df_ant = pd.DataFrame({
            "LOJA": ["A", "C"], "CONSULTOR": ["João", "Zeca"],
            "VALOR": [500.0, 700.0],
        })
        _mockar_periodo_comparacao(monkeypatch, df_ant)
        contexto = _contexto(df=df_atual, mes=3, ano=2026, du_decorridos=10)

        resultado = tool_comparar_entidades(contexto, {"entidade": "loja"})

        du_total_cmp, _, _ = calcular_dias_uteis(2026, 2, 1)
        esperado = calcular_evolucao_por_entidade(
            df_atual=df_atual,
            du_dec_atual=10,
            df_ant=df_ant,
            du_dec_ant=du_total_cmp,
            entidade="LOJA",
            df_supervisores=pd.DataFrame(),
        )
        esperado = esperado.reindex(
            esperado["Variação Abs."].abs().sort_values(ascending=False).index
        )

        assert resultado["entidade"] == "loja"
        assert resultado["periodo_comparacao"] == "mes_anterior"
        assert resultado["total_comparadas"] == len(esperado)
        nomes_resultado = [linha["nome"] for linha in resultado["resultados"]]
        assert nomes_resultado == list(esperado["Loja"])

    def test_direcao_crescimento_inclui_status_nova(
        self, monkeypatch, sem_feriados,
    ):
        # A: cresceu (500->1000, normal); B: só no atual (nova); C: caiu
        # (1000->100) — não deve entrar no "crescimento".
        df_atual = pd.DataFrame({
            "LOJA": ["A", "B", "C"], "VALOR": [1000.0, 800.0, 100.0],
        })
        df_ant = pd.DataFrame({"LOJA": ["A", "C"], "VALOR": [500.0, 1000.0]})
        _mockar_periodo_comparacao(monkeypatch, df_ant)
        contexto = _contexto(df=df_atual, mes=3, ano=2026, du_decorridos=10)

        resultado = tool_comparar_entidades(
            contexto, {"entidade": "loja", "direcao": "crescimento"},
        )

        nomes = {linha["nome"] for linha in resultado["resultados"]}
        assert nomes == {"A", "B"}
        linha_b = next(
            item for item in resultado["resultados"] if item["nome"] == "B"
        )
        assert linha_b["status"] == "nova"
        assert linha_b["variacao_pct"] is None

    def test_direcao_queda_inclui_status_descontinuada(
        self, monkeypatch, sem_feriados,
    ):
        # A: cresceu (não é queda); B: só no anterior (descontinuada);
        # C: caiu (1000->100, normal negativo) — as duas últimas contam
        # como "queda".
        df_atual = pd.DataFrame({"LOJA": ["A", "C"], "VALOR": [1000.0, 100.0]})
        df_ant = pd.DataFrame({
            "LOJA": ["A", "B", "C"], "VALOR": [500.0, 900.0, 1000.0],
        })
        _mockar_periodo_comparacao(monkeypatch, df_ant)
        contexto = _contexto(df=df_atual, mes=3, ano=2026, du_decorridos=10)

        resultado = tool_comparar_entidades(
            contexto, {"entidade": "loja", "direcao": "queda"},
        )

        nomes = {linha["nome"] for linha in resultado["resultados"]}
        assert nomes == {"B", "C"}
        linha_b = next(
            item for item in resultado["resultados"] if item["nome"] == "B"
        )
        assert linha_b["status"] == "descontinuada"
        assert linha_b["variacao_pct"] is None

    def test_limite_nunca_excede_maximo(self, monkeypatch, sem_feriados):
        n = 30
        df_atual = pd.DataFrame({
            "LOJA": [f"LOJA {i:02d}" for i in range(n)],
            "VALOR": [1000.0 + i for i in range(n)],
        })
        df_ant = pd.DataFrame(columns=["LOJA", "VALOR"])
        _mockar_periodo_comparacao(monkeypatch, df_ant)
        contexto = _contexto(df=df_atual, mes=3, ano=2026, du_decorridos=10)

        resultado = tool_comparar_entidades(
            contexto, {"entidade": "loja", "limite": 1000},
        )

        assert resultado["total_comparadas"] == n
        assert len(resultado["resultados"]) == 25

    def test_excecao_ao_carregar_periodo_retorna_erro(self, monkeypatch):
        def _boom(mes, ano):
            raise RuntimeError("supabase indisponível")

        monkeypatch.setattr(tools_mod, "consolidar_dados", _boom)
        contexto = _contexto(
            df=pd.DataFrame({"LOJA": ["A"], "VALOR": [1.0]}), mes=3, ano=2026,
        )

        resultado = tool_comparar_entidades(contexto, {"entidade": "loja"})

        assert "erro" in resultado


@pytest.mark.unit
class TestToolsSchemaDispatchParidade:
    def test_toda_tool_declarada_tem_implementacao_e_vice_versa(self):
        contexto = _contexto()
        dispatch = construir_dispatch(contexto)

        nomes_schema = {tool["name"] for tool in TOOLS_SCHEMA}
        assert nomes_schema == set(dispatch)
