"""Campanha Semestral 2026-H2 — regras de elegibilidade, ranking e ritmo.

## O que esta suite protege

A campanha tem meta propria (R$ 75 mi em VALOR), recorte proprio de
produtos e criterio proprio de desempate. Nada disso existe no
dashboard de vendas, entao nao ha outra suite que pegue uma regressao
aqui.

Os dois pontos onde o numero cala em vez de gritar:

1. **Elegibilidade.** SAQUE fora, Super Conta dentro (como CNC). Um
   erro aqui move a apuracao em milhoes sem nenhum erro na tela.
2. **Dependencia do fallback de categoria.** ANT. DE BENEF. e CLT
   chegam da view SEM `categoria_codigo` (o ETL zera `categoria_id`
   quando a planilha renomeia o tipo — migration 061). Em 16/09/2026
   eram 27% dos contratos da janela e R$ 4,19 mi. Se o fallback deixar
   de rodar antes da campanha, duas das cinco familias somem.
   `TestDependenciaDoFallback` e a catraca disso.

## O frame desta suite

Uma linha por familia elegivel, mais as exclusoes:

| cat             | familia        | elegivel? |
|-----------------|----------------|-----------|
| CNC             | CNC            | sim       |
| SUPER_CONTA     | CNC            | sim       |
| CONSIG_PRIV     | CLT            | sim       |
| CONSIG_BMG      | Consignado     | sim       |
| PORTABILIDADE   | Consignado     | sim       |
| ANT_BENEF       | Ant. de Benef. | sim       |
| FGTS            | FGTS           | sim       |
| SAQUE           | —              | **nao**   |
| CNC_13          | —              | **nao**   |
"""

from datetime import date, timedelta

import pandas as pd
import pytest

from src.dashboard.kpis.campanha import (
    CAMPANHA_FIM,
    CAMPANHA_INICIO,
    CATEGORIAS_DESEMPATE,
    CATEGORIAS_ELEGIVEIS,
    META_VALOR,
    apurar,
    apurar_por_familia,
    filtrar_elegiveis,
    filtrar_janela,
    preparar,
    ranking,
    ritmo,
)

_CATS = [
    "CNC",
    "SUPER_CONTA",
    "CONSIG_PRIV",
    "CONSIG_BMG",
    "PORTABILIDADE",
    "ANT_BENEF",
    "FGTS",
    "SAQUE",
    "CNC_13",
]


def _frame(**extra) -> pd.DataFrame:
    n = len(_CATS)
    base = {
        "categoria_codigo": list(_CATS),
        "VALOR": [100.0] * n,
        "pontos": [10.0] * n,
        "CONSULTOR": [f"C{i}" for i in range(n)],
        "LOJA": ["L1"] * n,
        "DATA": [pd.Timestamp("2026-08-15")] * n,
    }
    base.update(extra)
    return pd.DataFrame(base)


# ══════════════════════════════════════════════════════
# Elegibilidade
# ══════════════════════════════════════════════════════


class TestElegibilidade:
    def test_saque_fica_de_fora(self):
        """SAQUE de cartao foi excluido explicitamente pelo usuario."""
        assert "SAQUE" not in CATEGORIAS_ELEGIVEIS
        assert "SAQUE_BENEFICIO" not in CATEGORIAS_ELEGIVEIS
        out = filtrar_elegiveis(_frame())
        assert "SAQUE" not in set(out["categoria_codigo"])

    def test_super_conta_conta_como_cnc(self):
        """Decisao do usuario (09/2026): R$ 3,73 mi dependiam disso."""
        assert "SUPER_CONTA" in CATEGORIAS_ELEGIVEIS
        assert "SUPER_CONTA" in CATEGORIAS_DESEMPATE

    def test_cnc_13_nao_entra_sem_decisao(self):
        """CNC_13 e categoria propria — nao foi nomeada na campanha.

        13º e produto de nov/dez, DENTRO da janela. Este teste falha de
        proposito no dia em que alguem incluir CNC_13 sem registrar a
        decisao, forcando a conversa em vez do commit silencioso.
        """
        assert "CNC_13" not in CATEGORIAS_ELEGIVEIS

    def test_as_cinco_familias_entram(self):
        out = filtrar_elegiveis(_frame())
        assert set(out["categoria_codigo"]) == {
            "CNC",
            "SUPER_CONTA",
            "CONSIG_PRIV",
            "CONSIG_BMG",
            "PORTABILIDADE",
            "ANT_BENEF",
            "FGTS",
        }

    def test_frame_vazio_nao_quebra(self):
        assert filtrar_elegiveis(pd.DataFrame()).empty

    def test_sem_coluna_categoria_devolve_vazio(self):
        """Sem `categoria_codigo` nao da para afirmar elegibilidade."""
        df = pd.DataFrame({"VALOR": [1.0]})
        assert filtrar_elegiveis(df).empty


class TestDependenciaDoFallback:
    """ANT. DE BENEF. e CLT so existem na campanha via fallback.

    Simula o que a view entrega crua: `categoria_codigo` nula nessas
    duas familias. Se alguem remover `_preencher_categoria_fallback` do
    caminho da campanha, a apuracao cai ~19% em silencio — este teste e
    o que grita.
    """

    def test_categoria_nula_nao_e_elegivel(self):
        df = pd.DataFrame(
            {
                "categoria_codigo": [None, None],
                "VALOR": [1000.0, 2000.0],
                "pontos": [1.0, 1.0],
                "DATA": [pd.Timestamp("2026-08-15")] * 2,
            }
        )
        assert filtrar_elegiveis(df).empty
        assert apurar(preparar(df))["valor"] == 0.0

    def test_com_fallback_aplicado_entram(self):
        df = pd.DataFrame(
            {
                "categoria_codigo": ["ANT_BENEF", "CONSIG_PRIV"],
                "VALOR": [1000.0, 2000.0],
                "pontos": [1.0, 1.0],
                "DATA": [pd.Timestamp("2026-08-15")] * 2,
            }
        )
        assert apurar(preparar(df))["valor"] == 3000.0


# ══════════════════════════════════════════════════════
# Janela
# ══════════════════════════════════════════════════════


class TestJanela:
    @pytest.mark.parametrize(
        "dia,dentro",
        [
            ("2026-06-30", False),
            ("2026-07-01", True),   # limite inferior inclusivo
            ("2026-09-15", True),
            ("2026-12-31", True),   # limite superior inclusivo
            ("2027-01-01", False),
        ],
    )
    def test_limites_inclusivos(self, dia, dentro):
        df = _frame(
            categoria_codigo=["CNC"],
            VALOR=[100.0],
            pontos=[1.0],
            CONSULTOR=["C1"],
            LOJA=["L1"],
            DATA=[pd.Timestamp(dia)],
        )
        assert (not filtrar_janela(df).empty) is dentro

    def test_data_nula_sai(self):
        """Sem data nao da para afirmar que foi paga na janela."""
        df = _frame(
            categoria_codigo=["CNC"],
            VALOR=[100.0],
            pontos=[1.0],
            CONSULTOR=["C1"],
            LOJA=["L1"],
            DATA=[pd.NaT],
        )
        assert filtrar_janela(df).empty


# ══════════════════════════════════════════════════════
# Apuracao
# ══════════════════════════════════════════════════════


class TestApuracao:
    def test_soma_so_elegiveis(self):
        """7 elegiveis x 100 = 700; SAQUE e CNC_13 ficam fora."""
        assert apurar(preparar(_frame()))["valor"] == 700.0

    def test_atingimento_e_falta(self):
        ap = apurar(preparar(_frame()), meta=1000.0)
        assert ap["valor"] == 700.0
        assert ap["atingimento"] == pytest.approx(0.7)
        assert ap["falta"] == pytest.approx(300.0)

    def test_falta_nunca_negativa(self):
        ap = apurar(preparar(_frame()), meta=100.0)
        assert ap["falta"] == 0.0

    def test_valor_cnc_soma_cnc_e_super_conta(self):
        assert apurar(preparar(_frame()))["valor_cnc"] == 200.0

    def test_meta_default_e_75_milhoes(self):
        assert META_VALOR == 75_000_000.0

    def test_por_familia_soma_o_total(self):
        df = preparar(_frame())
        fam = apurar_por_familia(df)
        assert fam["Valor"].sum() == apurar(df)["valor"]
        assert fam["% do Total"].sum() == pytest.approx(100.0)

    def test_por_familia_mostra_familia_zerada(self):
        """Familia sem venda aparece zerada, nao some."""
        df = preparar(_frame(categoria_codigo=["CNC"] + _CATS[1:]))
        fam = apurar_por_familia(df)
        assert len(fam) == 5
        assert "FGTS" in set(fam["Família"])


# ══════════════════════════════════════════════════════
# Ranking
# ══════════════════════════════════════════════════════


class TestRanking:
    def test_ordena_por_pontos(self):
        df = pd.DataFrame(
            {
                "categoria_codigo": ["CNC"] * 3,
                "VALOR": [10.0, 10.0, 10.0],
                "pontos": [5.0, 30.0, 20.0],
                "CONSULTOR": ["A", "B", "C"],
                "DATA": [pd.Timestamp("2026-08-01")] * 3,
            }
        )
        out = ranking(preparar(df), "CONSULTOR")
        assert out["CONSULTOR"].tolist() == ["B", "C", "A"]
        assert out["#"].tolist() == [1, 2, 3]

    def test_desempate_por_producao_cnc(self):
        """Pontos iguais: ganha quem produziu mais CNC.

        A tem mais VALOR total, mas B tem mais CNC. O criterio da
        campanha e CNC — B vence.
        """
        df = pd.DataFrame(
            {
                "categoria_codigo": ["FGTS", "CNC", "CNC", "FGTS"],
                "VALOR": [900.0, 100.0, 500.0, 500.0],
                "pontos": [10.0, 10.0, 10.0, 10.0],
                "CONSULTOR": ["A", "A", "B", "B"],
                "DATA": [pd.Timestamp("2026-08-01")] * 4,
            }
        )
        out = ranking(preparar(df), "CONSULTOR")
        assert out["CONSULTOR"].tolist() == ["B", "A"]
        assert out.loc[0, "CNC (desempate)"] == 500.0
        assert out.loc[1, "CNC (desempate)"] == 100.0

    def test_super_conta_vale_no_desempate(self):
        """B so ganha porque Super Conta conta como CNC."""
        df = pd.DataFrame(
            {
                "categoria_codigo": ["CNC", "SUPER_CONTA"],
                "VALOR": [100.0, 500.0],
                "pontos": [10.0, 10.0],
                "CONSULTOR": ["A", "B"],
                "DATA": [pd.Timestamp("2026-08-01")] * 2,
            }
        )
        out = ranking(preparar(df), "CONSULTOR")
        assert out["CONSULTOR"].tolist() == ["B", "A"]

    def test_empate_real_divide_posicao(self):
        """Empate nos DOIS criterios nao inventa vencedor."""
        df = pd.DataFrame(
            {
                "categoria_codigo": ["CNC", "CNC"],
                "VALOR": [100.0, 100.0],
                "pontos": [10.0, 10.0],
                "CONSULTOR": ["A", "B"],
                "DATA": [pd.Timestamp("2026-08-01")] * 2,
            }
        )
        assert ranking(preparar(df), "CONSULTOR")["#"].tolist() == [1, 1]

    def test_ranking_de_loja(self):
        df = pd.DataFrame(
            {
                "categoria_codigo": ["CNC", "CNC"],
                "VALOR": [100.0, 300.0],
                "pontos": [10.0, 30.0],
                "LOJA": ["L1", "L2"],
                "DATA": [pd.Timestamp("2026-08-01")] * 2,
            }
        )
        out = ranking(preparar(df), "LOJA")
        assert out["LOJA"].tolist() == ["L2", "L1"]

    def test_top_n(self):
        assert len(ranking(preparar(_frame()), "CONSULTOR", top=3)) == 3

    def test_vazio_preserva_schema(self):
        out = ranking(pd.DataFrame(), "CONSULTOR")
        assert out.empty
        assert "Pontos" in out.columns


# ══════════════════════════════════════════════════════
# Ritmo
# ══════════════════════════════════════════════════════


class TestRitmo:
    def test_janela_tem_184_dias(self):
        r = ritmo({"valor": 0.0, "meta": META_VALOR}, date(2026, 7, 1))
        assert r["dias_total"] == 184  # jul..dez/2026

    def test_primeiro_dia_conta_como_um(self):
        r = ritmo({"valor": 0.0, "meta": META_VALOR}, date(2026, 7, 1))
        assert r["dias_decorridos"] == 1
        assert r["dias_restantes"] == 183

    def test_antes_do_inicio_nao_tem_dia_decorrido(self):
        r = ritmo({"valor": 0.0, "meta": META_VALOR}, date(2026, 6, 1))
        assert r["dias_decorridos"] == 0
        assert r["ritmo_dia"] == 0.0

    def test_depois_do_fim_satura(self):
        r = ritmo({"valor": 0.0, "meta": META_VALOR}, date(2027, 3, 1))
        assert r["dias_decorridos"] == r["dias_total"]
        assert r["dias_restantes"] == 0

    def test_projecao_linear(self):
        """Metade do tempo com metade da meta projeta a meta cheia."""
        meio = CAMPANHA_INICIO + timedelta(days=91)
        r = ritmo({"valor": META_VALOR / 2, "meta": META_VALOR}, meio)
        assert r["projecao_vs_meta"] == pytest.approx(1.0, rel=0.02)

    def test_necessario_por_dia(self):
        r = ritmo(
            {"valor": 0.0, "meta": 184.0},
            date(2026, 7, 1),
            CAMPANHA_INICIO,
            CAMPANHA_FIM,
        )
        assert r["necessario_dia"] == pytest.approx(184.0 / 183)

    def test_meta_batida_nao_pede_mais_por_dia(self):
        r = ritmo(
            {"valor": META_VALOR * 2, "meta": META_VALOR},
            date(2026, 9, 1),
        )
        assert r["necessario_dia"] == 0.0
