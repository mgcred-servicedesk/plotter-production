"""
Chaves de comparação de texto (``shared/texto.py``).

Duas funções porque são duas responsabilidades, e a diferença entre
elas é o que este arquivo trava:

- ``normalizar_nome`` compara PESSOAS entre fontes do banco → acento é
  ruído, tem de sumir;
- ``normalizar_rotulo`` compara rótulo de dado contra constante escrita
  no código (``"CARTÃO BENEFICIO"``, ``"Venda Pré-Adesão"``) → dobrar
  acento só de um lado faria a comparação falhar em silêncio.

Antes de 09/2026 existia uma implementação só (``strip + upper``),
copiada em cinco lugares. Servia aos dois usos ao mesmo tempo, então a
diferença nunca precisou de nome — e a falta do nome escondeu o bug de
`JOÃO DA SILVA` ≠ `JOAO DA SILVA` no merge de produção.
"""
import pandas as pd
import pytest

from src.shared.texto import normalizar_nome, normalizar_rotulo


@pytest.mark.unit
class TestNormalizarRotulo:
    def test_strip_e_upper(self):
        assert normalizar_rotulo(
            pd.Series(["  cartão beneficio  "])
        ).tolist() == ["CARTÃO BENEFICIO"]

    @pytest.mark.parametrize("literal", [
        "CARTÃO BENEFICIO", "Venda Pré-Adesão",
    ])
    def test_preserva_acento_dos_literais_da_config(self, literal):
        """Estes dois estão em `_PRODUTOS_QTD` (tabs/produtos.py). Se
        esta função passasse a dobrar acento, a série viraria `CARTAO`
        e o literal continuaria `CARTÃO`: a linha sumiria da contagem
        sem erro nenhum."""
        assert normalizar_rotulo(
            pd.Series([literal])
        ).tolist() == [literal.upper()]

    def test_numero_vira_texto(self):
        assert normalizar_rotulo(pd.Series([1, 2])).tolist() == ["1", "2"]


@pytest.mark.unit
class TestNormalizarNome:
    @pytest.mark.parametrize("variante", [
        "JOÃO DA SILVA", "joao da silva", "  João Da Silva  ",
        "JOAO DA SILVA", "joão da silva",
    ])
    def test_todas_as_grafias_dao_a_mesma_chave(self, variante):
        assert normalizar_nome(
            pd.Series([variante])
        ).tolist() == ["JOAO DA SILVA"]

    @pytest.mark.parametrize("acentuado,simples", [
        ("Conceição", "CONCEICAO"),
        ("ÂNGELA", "ANGELA"),
        ("Müller", "MULLER"),
        ("Antônio", "ANTONIO"),
        ("Inês", "INES"),
        ("José", "JOSE"),
    ])
    def test_dobra_os_diacriticos_do_português(self, acentuado, simples):
        assert normalizar_nome(pd.Series([acentuado])).tolist() == [simples]

    def test_nulo_permanece_nulo(self):
        """Não vira "" nem "NONE": nome ausente de um lado nunca pode
        casar com nome ausente do outro num merge."""
        assert normalizar_nome(pd.Series(["Ana", None])).isna().tolist() == [
            False, True,
        ]

    def test_serie_toda_nula_nao_levanta(self):
        """Regressão da implementação: o ida-e-volta por ASCII
        (`encode`/`decode`) quebrava aqui — coluna toda nula chega como
        float e o acessor `.str` levanta AttributeError."""
        assert normalizar_nome(pd.Series([None, None])).isna().all()

    def test_serie_vazia_nao_levanta(self):
        assert normalizar_nome(pd.Series([], dtype=object)).empty

    def test_funciona_com_dtype_string_do_arrow(self):
        """As colunas vindas do Supabase são Arrow-backed, e o regex vai
        para o RE2 do pyarrow — que não aceita escape `\\u`."""
        assert normalizar_nome(
            pd.Series(["João"], dtype="string")
        ).tolist() == ["JOAO"]

    def test_preserva_o_indice(self):
        s = pd.Series(["João", "Ana"], index=[7, 9])
        assert normalizar_nome(s).index.tolist() == [7, 9]


@pytest.mark.unit
class TestAsDuasFuncoesDivergem:
    """O ponto do módulo: elas NÃO são intercambiáveis."""

    def test_divergem_exatamente_no_acento(self):
        s = pd.Series(["João"])
        assert normalizar_rotulo(s).tolist() == ["JOÃO"]
        assert normalizar_nome(s).tolist() == ["JOAO"]

    def test_coincidem_quando_nao_ha_acento(self):
        s = pd.Series(["  ana maria  "])
        assert normalizar_rotulo(s).tolist() == normalizar_nome(s).tolist()
