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
from src.config.settings import PACK_LABEL_AGREGADO
from src.dashboard.loaders import (
    VIGENCIA_FUTURA,
    VIGENCIA_HISTORICO,
    VIGENCIA_PROXIMA,
    VIGENCIA_SEM_REF,
    VIGENCIA_VIGENTE,
    _ACELERADORES_META_CONSULTOR,
    _COLUNAS_NIVEL_META_CONSULTOR,
    _colapsar_cadastro_recente,
    _coluna_meta_consultor,
    _fatiar_ref,
    _marcar_vigencia_reconquista,
    _mes_apuracao_seguinte,
    _preencher_categoria_fallback,
    _reanexar_regiao,
    _status_consultor_ativo,
    aplicar_nomes_display_produto,
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
class TestColunaMetaConsultor:
    """O par (produto, nivel) inteiro define a coluna do pivot de
    ``carregar_metas_produto_consultor`` — nunca só o produto. Sem
    isso, BRONZE/PRATA/OURO do mesmo produto colapsariam numa única
    coluna e seriam SOMADOS pelo pivot."""

    def test_nivel_null_devolve_o_proprio_produto(self):
        assert _coluna_meta_consultor("CNC", None) == "CNC"

    def test_geral_prata_devolve_meta_prata(self):
        assert _coluna_meta_consultor("GERAL", "PRATA") == "META_PRATA"

    def test_geral_ouro_devolve_meta_ouro(self):
        assert _coluna_meta_consultor("GERAL", "OURO") == "META_OURO"

    def test_acelerador_prata_devolve_nome_nu(self):
        assert _coluna_meta_consultor("BMG_MED", "PRATA") == "BMG_MED"

    def test_acelerador_ouro_devolve_sufixo_ouro(self):
        assert _coluna_meta_consultor("BMG_MED", "OURO") == "BMG_MED_OURO"

    def test_bronze_devolve_none_em_qualquer_produto(self):
        assert _coluna_meta_consultor("GERAL", "BRONZE") is None
        assert _coluna_meta_consultor("BMG_MED", "BRONZE") is None

    def test_bug_que_a_coluna_previne_colisao_de_niveis_no_pivot(self):
        """Sem o par (produto, nivel), BRONZE + PRATA + OURO do mesmo
        acelerador colapsariam na mesma coluna e um pivot os SOMARIA
        (0 + 6 + 12 = 18 contratos) — bug silencioso que nenhum
        consumidor teria como detectar."""
        linhas = pd.DataFrame({
            "produto": ["BMG_MED", "BMG_MED", "BMG_MED"],
            "nivel": ["BRONZE", "PRATA", "OURO"],
            "valor": [0, 6, 12],
        })
        linhas["coluna"] = [
            _coluna_meta_consultor(p, n)
            for p, n in zip(linhas["produto"], linhas["nivel"])
        ]
        # BRONZE é descartado (coluna None); PRATA e OURO vão para
        # colunas DIFERENTES — nenhum pivot soma os dois.
        por_nivel = linhas.set_index("nivel")["coluna"]
        assert pd.isna(por_nivel["BRONZE"])
        assert por_nivel["PRATA"] == "BMG_MED"
        assert por_nivel["OURO"] == "BMG_MED_OURO"


@pytest.fixture
def periodo_stub(monkeypatch):
    """Período resolvido sem tocar o banco (mesmo padrão de
    ``test_loaders_cobranca_consignavel.py``)."""
    monkeypatch.setattr(loaders, "carregar_periodo", lambda m, a: {"id": "p1"})


def _linha_meta_consultor(produto, nivel=None, valor=0.0, loja="HELP PENHA"):
    """Linha crua da query de metas (escopo CONSULTOR), como o Supabase
    devolveria: ``lojas(nome)`` é o embed do FK."""
    return {
        "produto": produto,
        "nivel": nivel,
        "valor": valor,
        "lojas": {"nome": loja},
    }


class _FakeQueryMetasConsultor:
    """Query fluente que só REGISTRA os filtros montados, sem executar
    nada — usada para travar que a query de metas (CONSULTOR) nunca
    filtre por ``nivel`` no servidor. Mesmo padrão de ``_FakeQuery`` em
    ``test_loaders_cobranca_consignavel.py``."""

    def __init__(self, registro: dict):
        self._registro = registro

    def table(self, nome):
        self._registro["tabela"] = nome
        return self

    def select(self, colunas):
        self._registro["colunas"] = colunas
        return self

    def eq(self, coluna, valor):
        self._registro.setdefault("eq", {})[coluna] = valor
        return self

    def is_(self, coluna, valor):
        self._registro.setdefault("is_", {})[coluna] = valor
        return self

    def gt(self, coluna, valor):  # usado pelo keyset a partir da 2a pagina
        self._registro.setdefault("gt", {})[coluna] = valor
        return self

    def order(self, coluna):
        self._registro["order"] = coluna
        return self

    def limit(self, n):
        self._registro["limit"] = n
        return self


@pytest.mark.unit
class TestFetchMetasProdutoConsultorPivot:
    """Contrato da montagem do pivot em ``_fetch_metas_produto_consultor``
    — nada além de ``TestColunaMetaConsultor`` cobria essa função antes
    do incidente de 09/2026 (ranking de consultores 0% para todo mundo:
    ver ``tests/test_loaders_cache_version.py`` para a causa raiz de
    CACHE; aqui é o contrato do FORMATO que o cache serve). Trava
    especificamente a regressão "alguém recoloca o filtro
    ``nivel IS NULL``" — o bug original que apagou as metas de ponto e
    de acelerador do pivot inteiro, silenciosamente."""

    def test_tres_familias_de_colunas_aparecem_no_pivot(
        self, monkeypatch, periodo_stub
    ):
        linhas = [
            _linha_meta_consultor("CNC", None, 20000.0),        # monetario
            _linha_meta_consultor("GERAL", "PRATA", 360000.0),  # ponto PRATA
            _linha_meta_consultor("GERAL", "OURO", 500000.0),   # ponto OURO
            _linha_meta_consultor("BMG_MED", "PRATA", 6.0),     # acelerador PRATA
            _linha_meta_consultor("BMG_MED", "OURO", 12.0),     # acelerador OURO
        ]
        monkeypatch.setattr(loaders, "_paginar_keyset", lambda q, c: linhas)

        df = loaders._fetch_metas_produto_consultor(9, 2026)

        linha = df.set_index("LOJA").loc["HELP PENHA"]
        assert linha["CNC"] == pytest.approx(20000.0)
        assert linha["META_PRATA"] == pytest.approx(360000.0)
        assert linha["META_OURO"] == pytest.approx(500000.0)
        assert linha["BMG_MED"] == pytest.approx(6.0)
        assert linha["BMG_MED_OURO"] == pytest.approx(12.0)

    def test_bronze_e_descartado_do_pivot(self, monkeypatch, periodo_stub):
        monkeypatch.setattr(
            loaders, "_paginar_keyset",
            lambda q, c: [
                _linha_meta_consultor("CNC", None, 1000.0),
                _linha_meta_consultor("BMG_MED", "BRONZE", 999.0),
            ],
        )

        df = loaders._fetch_metas_produto_consultor(9, 2026)

        assert "BRONZE" not in df.columns
        # BMG_MED é coluna garantida, mas BRONZE nunca a populou —
        # fica no default (0.0), não no valor (999) da linha BRONZE.
        assert df.set_index("LOJA").loc["HELP PENHA", "BMG_MED"] == 0.0

    def test_niveis_do_mesmo_produto_nao_sao_somados(
        self, monkeypatch, periodo_stub
    ):
        """O bug que ``_coluna_meta_consultor`` existe para prevenir,
        agora na montagem real do pivot: sem o par (produto, nivel) na
        chave, BRONZE + PRATA + OURO colapsariam e o aggfunc somaria
        (0 + 6 + 12 = 18 contratos)."""
        monkeypatch.setattr(
            loaders, "_paginar_keyset",
            lambda q, c: [
                _linha_meta_consultor("BMG_MED", "BRONZE", 0.0),
                _linha_meta_consultor("BMG_MED", "PRATA", 6.0),
                _linha_meta_consultor("BMG_MED", "OURO", 12.0),
            ],
        )

        df = loaders._fetch_metas_produto_consultor(9, 2026)

        linha = df.set_index("LOJA").loc["HELP PENHA"]
        assert linha["BMG_MED"] == pytest.approx(6.0)       # não 18
        assert linha["BMG_MED_OURO"] == pytest.approx(12.0)

    def test_colunas_de_nivel_sempre_presentes_com_zero_quando_ausentes(
        self, monkeypatch, periodo_stub
    ):
        """Sem NENHUMA linha de ponto/acelerador no período (só
        monetário) — as colunas de nível não podem sumir do pivot: o
        consumidor lê ``df[col]`` sem checar existência primeiro."""
        monkeypatch.setattr(
            loaders, "_paginar_keyset",
            lambda q, c: [_linha_meta_consultor("CNC", None, 1000.0)],
        )

        df = loaders._fetch_metas_produto_consultor(9, 2026)

        linha = df.set_index("LOJA").loc["HELP PENHA"]
        for col in _COLUNAS_NIVEL_META_CONSULTOR:
            assert linha[col] == 0.0, col
        # As 4 famílias de acelerador da fonte única (kpis/gerais.py,
        # via loaders) estão todas cobertas pela constante acima.
        assert len(_ACELERADORES_META_CONSULTOR) == 4

    def test_periodo_ausente_devolve_vazio_sem_chamar_paginacao(
        self, monkeypatch
    ):
        monkeypatch.setattr(loaders, "carregar_periodo", lambda m, a: None)
        chamou = []
        monkeypatch.setattr(
            loaders, "_paginar_keyset",
            lambda q, c: chamou.append(1) or [],
        )

        df = loaders._fetch_metas_produto_consultor(9, 2026)

        assert df.empty
        assert chamou == []

    def test_query_nao_filtra_por_nivel_no_servidor(
        self, monkeypatch, periodo_stub
    ):
        """O bug original (pré-incidente de 09/2026): um filtro
        ``nivel IS NULL`` no servidor escondia do dashboard INTEIRO as
        metas de ponto (``GERAL``) e de acelerador — a query hoje traz
        TODOS os níveis, e só ``BRONZE`` é descartado depois, no
        client (``_coluna_meta_consultor``). Os testes acima do
        pivot/coluna não pegariam esse filtro voltar, porque mockam
        ``_paginar_keyset`` inteiro (a query nunca chega a ser
        inspecionada); este aqui inspeciona a query MONTADA."""
        registro: dict = {}

        def _capturar(montar_query, coluna_chave):
            montar_query(loaders._PAGE_SIZE)
            return []

        monkeypatch.setattr(
            loaders, "_sb", lambda: _FakeQueryMetasConsultor(registro)
        )
        monkeypatch.setattr(loaders, "_paginar_keyset", _capturar)

        loaders._fetch_metas_produto_consultor(9, 2026)

        assert "nivel" not in registro.get("eq", {})
        assert "nivel" not in registro.get("is_", {})
        assert registro.get("eq", {}).get("escopo") == "CONSULTOR"
        assert registro.get("tabela") == "metas"


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
class TestAplicarNomesDisplayProduto:
    """Chave interna de grupo_dashboard -> rotulo de UI.

    Mesmo helper para contratos (pagos/analise/cancelados) e para a
    tabela de categorias, que tambem expoe grupo_dashboard.
    """

    def test_renomeia_chave_mapeada(self):
        df = pd.DataFrame({"grupo_dashboard": ["PACK", "CNC", "PACK"]})
        out = aplicar_nomes_display_produto(df)
        assert list(out["grupo_dashboard"]) == [
            PACK_LABEL_AGREGADO, "CNC", PACK_LABEL_AGREGADO,
        ]

    def test_nao_muta_o_original(self):
        df = pd.DataFrame({"grupo_dashboard": ["PACK"]})
        aplicar_nomes_display_produto(df)
        assert df["grupo_dashboard"].iloc[0] == "PACK"

    def test_preserva_demais_colunas_e_indice(self):
        df = pd.DataFrame(
            {"grupo_dashboard": ["PACK"], "VALOR": [100.0]}, index=[7],
        )
        out = aplicar_nomes_display_produto(df)
        assert list(out.columns) == ["grupo_dashboard", "VALOR"]
        assert list(out.index) == [7]
        assert out["VALOR"].iloc[0] == 100.0

    def test_df_vazio_ou_sem_coluna_passa_direto(self):
        assert aplicar_nomes_display_produto(pd.DataFrame()).empty
        df = pd.DataFrame({"VALOR": [100.0]})
        assert list(aplicar_nomes_display_produto(df).columns) == ["VALOR"]

    def test_categorias_tratadas_como_qualquer_frame(self):
        # carregar_categorias() traz grupo_dashboard na mesma chave
        # interna dos contratos — precisa do mesmo vocabulario.
        categorias = pd.DataFrame({
            "codigo": ["ANT_BENEF", "CNC"],
            "grupo_dashboard": ["PACK", "CNC"],
            "conta_valor": [True, True],
        })
        out = aplicar_nomes_display_produto(categorias)
        assert list(out["grupo_dashboard"]) == [PACK_LABEL_AGREGADO, "CNC"]
        assert list(out["codigo"]) == ["ANT_BENEF", "CNC"]


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


def _base_reconquista() -> pd.DataFrame:
    """Base minima de Reconquista: uma linha por mes de referencia."""
    return pd.DataFrame(
        [
            {"co_adesao": 1, "ref_ano": 2025, "ref_mes": 12},
            {"co_adesao": 2, "ref_ano": 2026, "ref_mes": 6},
            {"co_adesao": 3, "ref_ano": 2026, "ref_mes": 7},
            {"co_adesao": 4, "ref_ano": 2026, "ref_mes": 8},
        ]
    )


@pytest.mark.unit
class TestFatiarRef:
    def test_recorta_o_mes_de_referencia(self):
        df = _fatiar_ref(_base_reconquista(), 2026, 7)
        assert df["co_adesao"].tolist() == [3]

    def test_mes_sem_linhas_devolve_vazio(self):
        assert _fatiar_ref(_base_reconquista(), 2026, 2).empty

    def test_base_vazia_devolve_vazio(self):
        assert _fatiar_ref(pd.DataFrame(), 2026, 7).empty

    def test_nao_muta_a_base(self):
        base = _base_reconquista()
        _fatiar_ref(base, 2026, 7)
        assert len(base) == 4


@pytest.mark.unit
class TestMarcarVigenciaReconquista:
    # Apuracao = ref + 1 (defasagem de 1 mes da campanha); os rotulos
    # sao posicionais frente ao (mes, ano) selecionado.
    def test_apuracao_e_o_mes_seguinte_ao_ref(self):
        df = _marcar_vigencia_reconquista(_base_reconquista(), 8, 2026)
        rotulos = dict(zip(df["co_adesao"], df["apuracao_ref"]))
        assert rotulos == {
            1: "01/2026",   # ref 12/2025 — vira o ano
            2: "07/2026",
            3: "08/2026",
            4: "09/2026",
        }

    def test_rotulos_por_posicao_frente_ao_mes_selecionado(self):
        df = _marcar_vigencia_reconquista(_base_reconquista(), 8, 2026)
        vigencia = dict(zip(df["co_adesao"], df["vigencia"]))
        assert vigencia == {
            1: VIGENCIA_HISTORICO,   # apuracao 01/2026
            2: VIGENCIA_HISTORICO,   # apuracao 07/2026
            3: VIGENCIA_VIGENTE,     # apuracao 08/2026 = selecionada
            4: VIGENCIA_PROXIMA,     # apuracao 09/2026 = esteira
        }

    def test_apuracao_alem_da_proxima_e_futura(self):
        # Selecionando 06/2026: nenhuma linha da base cai na vigente
        # (seria ref 05/2026) — o que exercita justamente Proxima/Futura.
        df = _marcar_vigencia_reconquista(_base_reconquista(), 6, 2026)
        vigencia = dict(zip(df["co_adesao"], df["vigencia"]))
        assert vigencia[1] == VIGENCIA_HISTORICO  # apuracao 01/2026
        assert vigencia[2] == VIGENCIA_PROXIMA    # apuracao 07/2026
        assert vigencia[3] == VIGENCIA_FUTURA     # apuracao 08/2026
        assert vigencia[4] == VIGENCIA_FUTURA     # apuracao 09/2026
        assert VIGENCIA_VIGENTE not in vigencia.values()

    def test_chave_ordena_cronologicamente(self):
        df = _marcar_vigencia_reconquista(_base_reconquista(), 8, 2026)
        chaves = df.sort_values("apuracao_key")["co_adesao"].tolist()
        assert chaves == [1, 2, 3, 4]

    def test_sem_data_de_referencia_nao_entra_em_nenhuma_apuracao(self):
        base = pd.DataFrame(
            [{"co_adesao": 9, "ref_ano": None, "ref_mes": None}]
        )
        df = _marcar_vigencia_reconquista(base, 8, 2026)
        assert df.loc[0, "vigencia"] == VIGENCIA_SEM_REF
        assert df.loc[0, "apuracao_ref"] == "—"

    def test_base_vazia_nao_quebra(self):
        assert _marcar_vigencia_reconquista(pd.DataFrame(), 8, 2026).empty

    def test_nao_muta_o_frame_de_entrada(self):
        base = _base_reconquista()
        _marcar_vigencia_reconquista(base, 8, 2026)
        assert "vigencia" not in base.columns

