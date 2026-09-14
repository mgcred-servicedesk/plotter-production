"""
Critérios de produto: uma definição, duas superfícies (item 4 da
revisão de 09/2026, fechado na Etapa 3).

"O que é um BMG Med / Vida Familiar / Emissão / Super Conta" estava
escrito **duas vezes**, com o mesmo texto, em `kpis/gerais.py` e
`kpis/produtos.py`. As superfícies concordavam por coincidência: uma
mudança de regra num lado deixaria a outra para trás, e aí rankings e
distribuição passariam a discordar sobre o mesmo consultor.

Agora `kpis/produtos.py` delega os quatro a `mascaras_aceleradores`.
Estes testes travam a concordância — se alguém reimplementar um deles,
falham aqui antes de chegar na tela.

CLT e Consignado continuam só em `kpis/produtos.py`: são critérios de
quantidade acrescentados por cima do pivot de valor, não aceleradores,
e nenhuma outra superfície os usa.
"""
import pandas as pd
import pytest

from src.dashboard.kpis.gerais import mascaras_aceleradores
from src.dashboard.kpis.produtos import _mascaras_aceleradores


def _df(**overrides):
    base = {
        "is_bmg_med": [True, False, False, False],
        "is_seguro_vida": [False, True, False, False],
        "is_super_conta": [False, False, True, False],
        "TIPO_PRODUTO": ["CNC", "CNC", "CNC", "EMISSAO CB"],
        "SUBTIPO": ["NOVO", "NOVO", "SUPER CONTA", "NOVO"],
        "categoria_codigo": ["CNC", "CNC", "CNC", "CARTAO"],
        "TIPO OPER.": ["CONTRATO NOVO"] * 4,
    }
    base.update(overrides)
    return pd.DataFrame(base)


@pytest.mark.unit
class TestAsDuasSuperficiesConcordam:
    @pytest.mark.parametrize("rotulo,posicao", [
        ("BMG Med", 0),
        ("Vida Familiar", 1),
        ("Emissao", 2),
        ("Super Conta", 3),
    ])
    def test_mesma_mascara_nos_dois_modulos(self, rotulo, posicao):
        df = _df()
        do_gerais = mascaras_aceleradores(df)[rotulo]
        do_produtos = _mascaras_aceleradores(df)[posicao]
        pd.testing.assert_series_equal(
            do_gerais, do_produtos, check_names=False,
        )

    def test_concordam_em_frame_parcial(self):
        """Frame sem as colunas de flag é caso normal em teste e em
        período sem consolidação — os dois têm de degradar igual."""
        df = pd.DataFrame({"VALOR": [1.0, 2.0]})
        do_gerais = mascaras_aceleradores(df)
        do_produtos = _mascaras_aceleradores(df)
        for posicao, rotulo in enumerate(
            ["BMG Med", "Vida Familiar", "Emissao", "Super Conta"]
        ):
            assert not do_gerais[rotulo].any(), rotulo
            assert not do_produtos[posicao].any(), rotulo


@pytest.mark.unit
class TestSuperContaPreferaFlagCanonica:
    """A única divergência real que a junção eliminou.

    `kpis/produtos.py` derivava Super Conta **só** do SUBTIPO. Dava o
    mesmo resultado porque a derivação em `kpis/consolidacao.py` é
    idêntica — mas deixaria de dar no dia em que a regra mudasse lá.
    """

    def test_usa_a_flag_quando_o_frame_a_traz(self):
        """Flag e SUBTIPO em desacordo: vence a flag canônica, nas
        duas superfícies."""
        df = _df(
            is_super_conta=[False, False, False, True],
            SUBTIPO=["SUPER CONTA", "NOVO", "NOVO", "NOVO"],
        )
        assert mascaras_aceleradores(df)["Super Conta"].tolist() == [
            False, False, False, True,
        ]
        assert _mascaras_aceleradores(df)[3].tolist() == [
            False, False, False, True,
        ]

    def test_cai_para_o_subtipo_sem_a_flag(self):
        df = _df().drop(columns=["is_super_conta"])
        assert _mascaras_aceleradores(df)[3].tolist() == [
            False, False, True, False,
        ]

    def test_subtipo_robusto_a_caixa_e_espacos(self):
        df = _df().drop(columns=["is_super_conta"])
        df["SUBTIPO"] = ["  super conta  ", "NOVO", "NOVO", "NOVO"]
        assert _mascaras_aceleradores(df)[3].tolist() == [
            True, False, False, False,
        ]


@pytest.mark.unit
class TestCriteriosExclusivosDeProdutos:
    """CLT e Consignado ficam só aqui — ver docstring do módulo."""

    def test_clt_exclui_seguro_prestamista(self):
        """`SEGURO PRESTAMISTA` é seguro, não crédito."""
        df = _df(
            categoria_codigo=["CONSIG_PRIV"] * 4,
            **{"TIPO OPER.": [
                "CONTRATO NOVO", "SEGURO PRESTAMISTA",
                "CONTRATO NOVO", "CONTRATO NOVO",
            ]},
        )
        assert _mascaras_aceleradores(df)[4].tolist() == [
            True, False, True, True,
        ]

    def test_consignado_so_novo_e_refin(self):
        """Portabilidade se exclui sozinha (mantém
        `categoria_codigo = PORTABILIDADE`); MARGEM COMPLEMENTAR fica
        de fora por não ser Novo nem Refin."""
        df = _df(
            categoria_codigo=[
                "CONSIG_BMG", "CONSIG_ITAU", "CONSIG_C6", "CONSIG_BMG",
            ],
            SUBTIPO=["NOVO", "REFIN", "MARGEM COMPLEMENTAR", "novo"],
        )
        assert _mascaras_aceleradores(df)[5].tolist() == [
            True, True, False, True,
        ]

    @pytest.mark.parametrize("posicao", [4, 5])
    def test_coluna_ausente_nao_infla_contagem(self, posicao):
        df = pd.DataFrame({"VALOR": [1.0]})
        assert not _mascaras_aceleradores(df)[posicao].any()
