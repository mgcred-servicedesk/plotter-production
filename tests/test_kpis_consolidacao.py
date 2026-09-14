"""
Regras da consolidação (``kpis/consolidacao.py``).

Testes de **caracterização**: fixam o comportamento que já rodava
dentro de `loaders._executar_consolidacao` antes da Etapa 2 da revisão
de 09/2026. Enquanto a transformação estava colada na carga, nada disso
era exercitado — `consolidar_pontuacao` saiu da extração com **0% de
cobertura**, e é a função que decide quanto cada contrato pontua.

A ordem das regras importa e está fixada aqui: `conta_valor` zera o
VALOR **antes** de `pontos = VALOR x PONTOS`, então uma linha sem valor
já nasce sem pontos; emissão de cartão zera os dois **depois**, por cima
de qualquer categoria.
"""
import pandas as pd
import pytest

from src.dashboard.kpis.consolidacao import (
    consolidar_pontuacao,
    preencher_categoria_fallback,
)


def _sem_categorias():
    """Loader de categorias que devolve vazio (não há fallback a
    aplicar nos cenários que já trazem `categoria_codigo`)."""
    return pd.DataFrame()


def _contratos(**overrides):
    """Uma linha de contrato pago com o schema mínimo da consolidação."""
    base = {
        "categoria_codigo": ["CNC"],
        "TIPO_PRODUTO": ["CNC"],
        "VALOR": [1000.0],
        "conta_valor": [True],
        "conta_pontuacao": [True],
        "SUBTIPO": ["NOVO"],
        "TIPO OPER.": ["CONTRATO NOVO"],
        "BANCO": ["BMG"],
    }
    base.update({k: v for k, v in overrides.items()})
    return pd.DataFrame(base)


def _pontos(mapa=None):
    mapa = mapa or {"CNC": 0.1}
    return pd.DataFrame({
        "categoria_codigo": list(mapa),
        "pontos": [float(v) for v in mapa.values()],
    })


@pytest.mark.unit
class TestPontuacaoBase:
    def test_pontos_sao_valor_vezes_a_taxa_da_categoria(self):
        df, _ = consolidar_pontuacao(
            _contratos(), _pontos({"CNC": 0.1}), _sem_categorias,
        )
        assert df["PONTOS"].tolist() == [0.1]
        assert df["pontos"].tolist() == [100.0]

    def test_categoria_fora_da_tabela_de_pontuacao_pontua_zero(self):
        df, _ = consolidar_pontuacao(
            _contratos(), _pontos({"SAQUE": 0.5}), _sem_categorias,
        )
        assert df["PONTOS"].tolist() == [0.0]
        assert df["pontos"].tolist() == [0.0]

    def test_tabela_de_pontuacao_vazia_zera_tudo(self):
        df, diag = consolidar_pontuacao(
            _contratos(), pd.DataFrame(), _sem_categorias,
        )
        assert df["PONTOS"].tolist() == [0]
        assert df["pontos"].tolist() == [0.0]
        assert diag["mapa_pontos"] == {}


@pytest.mark.unit
class TestPortabilidade:
    """Portabilidade herda os pontos do CONSIG do banco de origem.

    A regra vive em código, não na tabela `pontuacao`, porque o
    diferencial é o BANCO do contrato — granularidade maior que
    categoria.
    """

    @pytest.mark.parametrize("banco,categoria_herdada", [
        ("BMG", "CONSIG_BMG"),
        ("BANCO BMG", "CONSIG_BMG"),
        ("C6 BANK", "CONSIG_C6"),
        ("ITAU", "CONSIG_ITAU"),
        ("ITAÚ", "CONSIG_ITAU"),
    ])
    def test_herda_os_pontos_do_consig_do_banco(
        self, banco, categoria_herdada
    ):
        df, _ = consolidar_pontuacao(
            _contratos(categoria_codigo=["PORTABILIDADE"], BANCO=[banco]),
            _pontos({categoria_herdada: 0.3}),
            _sem_categorias,
        )
        assert df["PONTOS"].tolist() == [0.3]

    def test_normaliza_espacos_e_caixa_do_banco(self):
        df, _ = consolidar_pontuacao(
            _contratos(
                categoria_codigo=["PORTABILIDADE"], BANCO=["  c6 bank  "],
            ),
            _pontos({"CONSIG_C6": 0.3}),
            _sem_categorias,
        )
        assert df["PONTOS"].tolist() == [0.3]

    def test_banco_sem_mapeamento_fica_com_zero(self):
        df, _ = consolidar_pontuacao(
            _contratos(
                categoria_codigo=["PORTABILIDADE"], BANCO=["BANCO XPTO"],
            ),
            _pontos({"CONSIG_BMG": 0.3}),
            _sem_categorias,
        )
        assert df["PONTOS"].tolist() == [0.0]

    def test_consig_privado_nao_se_aplica_a_portabilidade(self):
        """`CONSIG_PRIV` está fora do mapa de propósito — Privado é
        produto distinto, não origem de portabilidade."""
        df, _ = consolidar_pontuacao(
            _contratos(
                categoria_codigo=["PORTABILIDADE"], BANCO=["CLT"],
            ),
            _pontos({"CONSIG_PRIV": 0.9}),
            _sem_categorias,
        )
        assert df["PONTOS"].tolist() == [0.0]

    def test_sem_coluna_banco_a_regra_nao_roda(self):
        contratos = _contratos(categoria_codigo=["PORTABILIDADE"])
        df, _ = consolidar_pontuacao(
            contratos.drop(columns=["BANCO"]),
            _pontos({"CONSIG_BMG": 0.3}),
            _sem_categorias,
        )
        assert df["PONTOS"].tolist() == [0.0]

    def test_nao_afeta_as_demais_linhas(self):
        contratos = _contratos(
            categoria_codigo=["PORTABILIDADE", "CNC"],
            TIPO_PRODUTO=["Portabilidade", "CNC"],
            VALOR=[1000.0, 1000.0],
            conta_valor=[True, True],
            conta_pontuacao=[True, True],
            SUBTIPO=["NOVO", "NOVO"],
            **{"TIPO OPER.": ["CONTRATO NOVO", "CONTRATO NOVO"]},
            BANCO=["BMG", "BMG"],
        )
        df, _ = consolidar_pontuacao(
            contratos, _pontos({"CONSIG_BMG": 0.3, "CNC": 0.1}),
            _sem_categorias,
        )
        assert df["PONTOS"].tolist() == [0.3, 0.1]


@pytest.mark.unit
class TestRegrasDeExclusao:
    def test_conta_valor_falso_zera_valor_e_por_consequencia_os_pontos(self):
        """A ordem importa: VALOR é zerado ANTES de `pontos = VALOR x
        PONTOS`, então não é preciso zerar pontos separadamente."""
        df, _ = consolidar_pontuacao(
            _contratos(conta_valor=[False]), _pontos(), _sem_categorias,
        )
        assert df["VALOR"].tolist() == [0]
        assert df["pontos"].tolist() == [0.0]

    def test_conta_pontuacao_falso_zera_so_os_pontos(self):
        df, _ = consolidar_pontuacao(
            _contratos(conta_pontuacao=[False]), _pontos(), _sem_categorias,
        )
        assert df["VALOR"].tolist() == [1000.0]
        assert df["pontos"].tolist() == [0]


@pytest.mark.unit
class TestClassificacoes:
    def test_super_conta_por_subtipo(self):
        df, _ = consolidar_pontuacao(
            _contratos(SUBTIPO=["SUPER CONTA"]), _pontos(), _sem_categorias,
        )
        assert df["is_super_conta"].tolist() == [True]

    @pytest.mark.parametrize("subtipo", ["super conta", "  Super Conta "])
    def test_super_conta_e_robusta_a_caixa_e_espacos(self, subtipo):
        df, _ = consolidar_pontuacao(
            _contratos(SUBTIPO=[subtipo]), _pontos(), _sem_categorias,
        )
        assert df["is_super_conta"].tolist() == [True]

    @pytest.mark.parametrize("tipo_oper", [
        "CARTÃO BENEFICIO", "Venda Pré-Adesão",
    ])
    def test_emissao_conta_so_quantidade(self, tipo_oper):
        """Zera valor e pontos POR CIMA da categoria: uma Venda
        Pré-Adesão de produto CONSIG tem `conta_valor=True`, mas o TIPO
        OPER. diz que é emissão."""
        df, _ = consolidar_pontuacao(
            _contratos(**{"TIPO OPER.": [tipo_oper]}),
            _pontos(), _sem_categorias,
        )
        assert df["is_emissao_cartao"].tolist() == [True]
        assert df["VALOR"].tolist() == [0]
        assert df["pontos"].tolist() == [0]

    def test_bmg_med_por_tipo_oper(self):
        df, _ = consolidar_pontuacao(
            _contratos(**{"TIPO OPER.": ["BMG MED"]}),
            _pontos(), _sem_categorias,
        )
        assert df["is_bmg_med"].tolist() == [True]
        assert df["is_seguro_vida"].tolist() == [False]

    def test_seguro_vida_por_tipo_oper(self):
        df, _ = consolidar_pontuacao(
            _contratos(**{"TIPO OPER.": ["Seguro"]}),
            _pontos(), _sem_categorias,
        )
        assert df["is_seguro_vida"].tolist() == [True]
        assert df["is_bmg_med"].tolist() == [False]

    def test_sem_tipo_oper_os_seguros_caem_na_categoria(self):
        contratos = _contratos(categoria_codigo=["BMG_MED"])
        df, _ = consolidar_pontuacao(
            contratos.drop(columns=["TIPO OPER."]),
            _pontos(), _sem_categorias,
        )
        assert df["is_bmg_med"].tolist() == [True]


@pytest.mark.unit
class TestDiagnostico:
    def test_conta_categorias_e_pontos_mapeados(self):
        contratos = _contratos(
            categoria_codigo=["CNC", "SAQUE"],
            TIPO_PRODUTO=["CNC", "SAQUE"],
            VALOR=[1000.0, 500.0],
            conta_valor=[True, True],
            conta_pontuacao=[True, True],
            SUBTIPO=["NOVO", "NOVO"],
            **{"TIPO OPER.": ["CONTRATO NOVO", "CONTRATO NOVO"]},
            BANCO=["BMG", "BMG"],
        )
        _, diag = consolidar_pontuacao(
            contratos, _pontos({"CNC": 0.1}), _sem_categorias,
        )
        assert diag["total_contratos"] == 2
        assert diag["com_categoria"] == 2
        assert diag["sem_categoria"] == 0
        assert diag["com_pontos_mapeados"] == 1
        assert diag["sem_pontos_mapeados"] == 1
        assert diag["categorias_na_pontuacao"] == ["CNC"]

    def test_lista_os_tipos_que_ficaram_sem_categoria(self):
        """O expander de admin mostra isso para o suporte rastrear
        renomeação de produto na origem (ETL)."""
        contratos = _contratos(
            categoria_codigo=[""], TIPO_PRODUTO=["PRODUTO NOVO XPTO"],
        )
        _, diag = consolidar_pontuacao(
            contratos, _pontos(), _sem_categorias,
        )
        assert diag["sem_categoria"] == 1
        assert diag["tipos_sem_categoria"] == [
            {"tipo": "PRODUTO NOVO XPTO", "qtd": 1},
        ]


@pytest.mark.unit
class TestFallbackDeCategoria:
    def test_preenche_categoria_a_partir_do_tipo_produto(self):
        """O ETL grava `categoria_id = NULL` quando a planilha renomeia
        um tipo (migration 061); sem o fallback a linha sumiria de tudo
        que agrupa por produto."""
        df = preencher_categoria_fallback(
            pd.DataFrame({
                "categoria_codigo": [None],
                "TIPO_PRODUTO": ["CLT"],
            }),
            _sem_categorias,
        )
        assert df["categoria_codigo"].tolist() == ["CONSIG_PRIV"]

    def test_tipo_desconhecido_vira_string_vazia_nao_nan(self):
        """NaN misturado com str quebrava o `sorted` do diagnóstico."""
        df = preencher_categoria_fallback(
            pd.DataFrame({
                "categoria_codigo": [None],
                "TIPO_PRODUTO": ["NAO EXISTE"],
            }),
            _sem_categorias,
        )
        assert df["categoria_codigo"].tolist() == [""]

    def test_nao_busca_categorias_quando_nao_ha_o_que_preencher(self):
        """A busca é lazy de propósito — por isso o loader chega como
        callable e não como frame. Carregar sempre acrescentaria uma
        consulta por consolidação no caso comum."""
        def _explode():
            raise AssertionError(
                "carregar_categorias não deveria ser chamado"
            )

        df = preencher_categoria_fallback(
            pd.DataFrame({
                "categoria_codigo": ["CNC"], "TIPO_PRODUTO": ["CNC"],
            }),
            _explode,
        )
        assert df["categoria_codigo"].tolist() == ["CNC"]

    def test_consolidar_pontuacao_tambem_e_lazy(self):
        """A laziness precisa sobreviver à passagem pela consolidação —
        é ali que o callable é repassado."""
        def _explode():
            raise AssertionError(
                "carregar_categorias não deveria ser chamado"
            )

        df, _ = consolidar_pontuacao(_contratos(), _pontos(), _explode)
        assert df["pontos"].tolist() == [100.0]
