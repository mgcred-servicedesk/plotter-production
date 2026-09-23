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
    _LIMITE_MAXIMO,
    _LIMITE_PADRAO,
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

    def test_consultor_atingimento(self, monkeypatch, df_rank, df_metas_lojas):
        # Meta do consultor = META_PRATA de escopo CONSULTOR da loja
        # dele (mesmos valores de
        # TestCalcularRankingConsultores.test_meta_individual_escopo_consultor
        # em test_kpis_rankings.py). carregar_metas_produto_consultor
        # é isolada da rede via monkeypatch no módulo consumidor.
        metas_consultor = pd.DataFrame(
            {"LOJA": ["A", "B"], "META_PRATA": [500.0, 1500.0]}
        )
        monkeypatch.setattr(
            tools_mod,
            "carregar_metas_produto_consultor",
            lambda mes, ano: metas_consultor,
        )
        # `aplicar_rls_metas` e fail-closed: sem usuario logado no
        # `session_state` ela devolve frame VAZIO (e o ranking voltaria
        # 0% para todo mundo). Este teste mede o reshape do ranking, nao
        # o RLS — que tem cobertura propria em `test_rls_cancelados.py`.
        # Neutralizado no namespace de `tools`, como manda o docstring
        # do modulo (nunca no modulo de origem).
        monkeypatch.setattr(
            tools_mod, "aplicar_rls_metas", lambda df, df_dados: df
        )
        contexto = _contexto(df=df_rank, df_metas=df_metas_lojas)

        resultado = tool_ranking_periodo(
            contexto, {"entidade": "consultor", "criterio": "atingimento"},
        )

        por_nome = {linha["nome"]: linha for linha in resultado["resultados"]}
        # João (loja A): 400 / 500 = 80%; Pedro (loja B): 60 / 1500 = 4%
        assert por_nome["João"]["atingimento_pct"] == pytest.approx(80.0)
        assert por_nome["Pedro"]["atingimento_pct"] == pytest.approx(4.0)

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

    def test_dataframe_vazio_nao_lanca(self, df_metas_lojas):
        """Sem produção no período, MAS com metas: nada a ranquear, e
        nenhuma exceção. (Sem metas é outro caso — ver
        ``TestRankingAtingimentoSemMetas``.)"""
        df_vazio = pd.DataFrame({
            "VALOR": pd.Series(dtype=float),
            "pontos": pd.Series(dtype=float),
        })
        contexto = _contexto(df=df_vazio, df_metas=df_metas_lojas)

        resultado = tool_ranking_periodo(
            contexto, {"entidade": "loja", "criterio": "atingimento"},
        )

        assert resultado == {
            "entidade": "loja", "criterio": "atingimento",
            "total_disponivel": 0, "truncado": False, "resultados": [],
        }


@pytest.mark.unit
class TestRankingAtingimentoSemMetas:
    """Sem metas, ``calcular_ranking_*`` não levanta: devolve **0% de
    atingimento para todo mundo**, e o modelo reportaria isso ao admin
    como se a operação estivesse zerada.

    O chat é Beta e só admin o usa (``tabs/chat_ia.py`` barra os demais
    perfis), então a decisão é falhar alto enquanto o PO ainda desenha
    a feature: melhor "não consegui" do que número errado com cara de
    certo. A chave ``erro`` faz ``agent.py`` marcar o bloco com
    ``is_error=True``.

    Duas causas chegam aqui com a mesma resposta: não há metas
    cadastradas no período, ou o RLS fail-closed esvaziou o frame.
    """

    def test_lojas_sem_metas_devolve_erro(self, df_rank):
        resultado = tool_ranking_periodo(
            _contexto(df=df_rank, df_metas=pd.DataFrame()),
            {"entidade": "loja", "criterio": "atingimento"},
        )
        assert "erro" in resultado
        assert "resultados" not in resultado

    def test_consultores_sem_metas_devolve_erro(
        self, monkeypatch, df_rank, df_metas_lojas
    ):
        """Inclui o caminho do RLS fail-closed: ``aplicar_rls_metas``
        devolvendo vazio (perfil sem escopo) chega aqui igual a "não há
        metas cadastradas"."""
        monkeypatch.setattr(
            tools_mod,
            "carregar_metas_produto_consultor",
            lambda mes, ano: pd.DataFrame(
                {"LOJA": ["A"], "META_PRATA": [500.0]}
            ),
        )
        monkeypatch.setattr(
            tools_mod,
            "aplicar_rls_metas",
            lambda df, df_dados: df.iloc[0:0],
        )
        resultado = tool_ranking_periodo(
            _contexto(df=df_rank, df_metas=df_metas_lojas),
            {"entidade": "consultor", "criterio": "atingimento"},
        )
        assert "erro" in resultado
        assert "resultados" not in resultado

    @pytest.mark.parametrize(
        "criterio", ["pontos", "ticket_medio", "media_du"]
    )
    def test_outros_criterios_seguem_sem_metas(self, df_rank, criterio):
        """A trava é só do atingimento — os outros critérios não
        dependem de meta e continuam respondendo."""
        resultado = tool_ranking_periodo(
            _contexto(df=df_rank, df_metas=pd.DataFrame()),
            {"entidade": "loja", "criterio": criterio},
        )
        assert "erro" not in resultado
        assert resultado["resultados"]


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

        assert resultado == {
            "entidade": "loja", "total": 1, "truncado": False, "nomes": ["C"],
        }

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
        n = _LIMITE_MAXIMO + 5
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
        assert len(resultado["resultados"]) == _LIMITE_MAXIMO
        assert resultado["truncado"] is True

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


@pytest.mark.unit
class TestRankingInformaCoberturaAoTruncar:
    """Um top N sem o total é indistinguível de "só existem estes N".

    Bug observado em 23/09: sem ``total_disponivel``, o modelo somou
    quatro rankings e inferiu por conta própria "~19 lojas de fora" —
    número que nenhuma tool produziu.
    """

    def _df_lojas(self, n: int) -> pd.DataFrame:
        """Uma venda por loja, pontuação decrescente (ranking estável)."""
        return pd.DataFrame({
            "LOJA":             [f"LOJA {i:03d}" for i in range(n)],
            "REGIAO":           ["R1"] * n,
            "CONSULTOR":        [f"CONS {i:03d}" for i in range(n)],
            "grupo_dashboard":  ["CNC"] * n,
            "categoria_codigo": ["CNC"] * n,
            "VALOR":            [1000.0 + i for i in range(n)],
            "pontos":           [float(n - i) for i in range(n)],
            "TIPO_PRODUTO":     ["CNC"] * n,
            "SUBTIPO":          [""] * n,
            "is_bmg_med":       [False] * n,
            "is_seguro_vida":   [False] * n,
        })

    def test_ranking_truncado_informa_o_total_real(self):
        n = _LIMITE_MAXIMO + 12
        contexto = _contexto(df=self._df_lojas(n))

        resultado = tool_ranking_periodo(
            contexto, {"entidade": "loja", "criterio": "pontos"},
        )

        # Sem `limite` na entrada vale o padrão, não o teto.
        assert resultado["total_disponivel"] == n
        assert resultado["truncado"] is True
        assert len(resultado["resultados"]) == _LIMITE_PADRAO

    def test_posicoes_seguem_contiguas_apos_o_corte(self):
        """O corte é feito aqui, depois de ``_rankear`` numerar: as
        posições precisam continuar 1..limite, sem buraco."""
        contexto = _contexto(df=self._df_lojas(_LIMITE_MAXIMO + 12))

        resultado = tool_ranking_periodo(
            contexto,
            {
                "entidade": "loja",
                "criterio": "pontos",
                "limite": _LIMITE_MAXIMO,
            },
        )

        posicoes = [linha["posicao"] for linha in resultado["resultados"]]
        assert posicoes == list(range(1, _LIMITE_MAXIMO + 1))

    def test_sem_truncamento_a_flag_fica_falsa(self):
        n = 5
        contexto = _contexto(df=self._df_lojas(n))

        resultado = tool_ranking_periodo(
            contexto, {"entidade": "loja", "criterio": "pontos", "limite": n},
        )

        assert resultado["truncado"] is False
        assert resultado["total_disponivel"] == n
        assert len(resultado["resultados"]) == n

    def test_limite_acima_do_maximo_e_truncado_no_teto(self):
        n = _LIMITE_MAXIMO + 12
        contexto = _contexto(df=self._df_lojas(n))

        resultado = tool_ranking_periodo(
            contexto,
            {"entidade": "loja", "criterio": "pontos", "limite": 500},
        )

        assert len(resultado["resultados"]) == _LIMITE_MAXIMO
        assert resultado["total_disponivel"] == n
        assert resultado["truncado"] is True


@pytest.mark.unit
class TestMarcaDeBackoffice:
    """No eixo LOJA o Vai e Vem aparece **por regra** (a exclusão de
    backoffice vale no eixo consultor — business-rules.md "Lojas de
    backoffice"). Sem marca, o modelo lê a linha como loja de venda com
    desempenho fraco; foi o que fez em 23/09.
    """

    def _df(self, lojas: list[str]) -> pd.DataFrame:
        n = len(lojas)
        return pd.DataFrame({
            "LOJA":             lojas,
            "REGIAO":           ["R1"] * n,
            "CONSULTOR":        [f"CONS {i}" for i in range(n)],
            "grupo_dashboard":  ["CNC"] * n,
            "categoria_codigo": ["CNC"] * n,
            "VALOR":            [1000.0 + i for i in range(n)],
            "pontos":           [float(n - i) for i in range(n)],
            "TIPO_PRODUTO":     ["CNC"] * n,
            "SUBTIPO":          [""] * n,
            "is_bmg_med":       [False] * n,
            "is_seguro_vida":   [False] * n,
        })

    def test_ranking_de_lojas_marca_a_linha_e_anexa_a_nota(self):
        contexto = _contexto(df=self._df(["LOJA A", "VAI E VEM", "LOJA B"]))

        resultado = tool_ranking_periodo(
            contexto, {"entidade": "loja", "criterio": "pontos"},
        )

        por_nome = {r["nome"]: r for r in resultado["resultados"]}
        assert por_nome["VAI E VEM"]["natureza"] == "backoffice"
        # Lojas de venda não carregam o campo — a marca só custa token
        # onde ela muda a leitura.
        assert "natureza" not in por_nome["LOJA A"]
        assert resultado["nota_backoffice"]["entidades"] == ["VAI E VEM"]
        assert "backoffice" in resultado["nota_backoffice"]["observacao"]

    def test_sem_backoffice_no_resultado_nao_ha_nota(self):
        contexto = _contexto(df=self._df(["LOJA A", "LOJA B"]))

        resultado = tool_ranking_periodo(
            contexto, {"entidade": "loja", "criterio": "pontos"},
        )

        assert "nota_backoffice" not in resultado
        assert all("natureza" not in r for r in resultado["resultados"])

    def test_match_normaliza_espacos_e_caixa(self):
        """Mesma normalização de ``excluir_lojas_backoffice``: um
        cadastro com espaço ou caixa diferente não pode escapar da
        marca."""
        contexto = _contexto(df=self._df(["LOJA A", "  vai e vem "]))

        resultado = tool_ranking_periodo(
            contexto, {"entidade": "loja", "criterio": "pontos"},
        )

        marcadas = [
            r for r in resultado["resultados"]
            if r.get("natureza") == "backoffice"
        ]
        assert len(marcadas) == 1
        assert resultado["nota_backoffice"]["entidades"] == ["VAI E VEM"]

    def test_listar_sem_producao_anexa_a_nota(self, monkeypatch):
        universo = pd.DataFrame({
            "LOJA": ["LOJA A", "VAI E VEM"], "REGIAO": ["R1", "R1"],
        })
        monkeypatch.setattr(
            tools_mod, "carregar_universo_lojas", lambda mes, ano: universo,
        )
        monkeypatch.setattr(tools_mod, "aplicar_rls", lambda df: df)
        monkeypatch.setattr(tools_mod, "aplicar_filtros_ui", lambda df: df)

        contexto = _contexto(df=self._df(["LOJA A"]))
        resultado = tool_listar_sem_producao(contexto, {"entidade": "loja"})

        assert "VAI E VEM" in resultado["nomes"]
        assert resultado["nota_backoffice"]["entidades"] == ["VAI E VEM"]
