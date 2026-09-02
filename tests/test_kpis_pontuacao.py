"""
Testes dos KPIs de pontuação (``src/dashboard/kpis/pontuacao.py``).

Módulo de funções puras: operam sobre a coluna ``pontos`` (já
consolidada em ``df``) e sobre ``pontos = VALOR x PTS`` calculado para
análise/cancelados, zerando aceleradores via ``conta_pontuacao=False``.
"""
import pandas as pd
import pytest

from src.dashboard.kpis.pontuacao import (
    calcular_medias_pontos_por_nivel,
    calcular_mix_pontos,
    calcular_pontos_cancelados,
    calcular_pontos_em_analise,
    calcular_prioridades_pontuacao,
)


@pytest.mark.unit
class TestCalcularPontosEmAnalise:
    def test_df_vazio(self, mapa_pontos):
        r = calcular_pontos_em_analise(pd.DataFrame(), mapa_pontos, 10)
        assert r == {
            "pontos_analise": 0.0,
            "qtd_analise": 0,
            "media_diaria_pontos_analise": 0.0,
        }

    def test_calculo_zera_aceleradores(self, sample_analise_df, mapa_pontos):
        # CNC 1000*1 + SAQUE 500*2 = 2000; EMISSAO zerado (conta_pontuacao=False)
        r = calcular_pontos_em_analise(sample_analise_df, mapa_pontos, 10)
        assert r["pontos_analise"] == pytest.approx(2000.0)
        assert r["qtd_analise"] == 2
        assert r["media_diaria_pontos_analise"] == pytest.approx(200.0)

    def test_du_zero_nao_divide(self, sample_analise_df, mapa_pontos):
        r = calcular_pontos_em_analise(sample_analise_df, mapa_pontos, 0)
        assert r["media_diaria_pontos_analise"] == 0.0


@pytest.mark.unit
class TestCalcularPontosCancelados:
    def test_df_vazio(self, mapa_pontos):
        r = calcular_pontos_cancelados(
            pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), mapa_pontos
        )
        assert r["qtd_cancelados"] == 0
        assert r["indice_perda"] == 0.0

    def test_indice_perda_sobre_total_propostas(self, mapa_pontos):
        df_canc = pd.DataFrame({
            "categoria_codigo": ["CNC"],
            "VALOR": [1000.0],
            "conta_pontuacao": [True],
        })
        df_pagos = pd.DataFrame({"categoria_codigo": ["CNC", "SAQUE"]})
        df_analise = pd.DataFrame({"categoria_codigo": ["CNC"]})
        r = calcular_pontos_cancelados(df_canc, df_pagos, df_analise, mapa_pontos)
        # total_propostas = 2 pagos + 1 cancelado + 1 analise = 4 → 1/4 = 25%
        assert r["qtd_cancelados"] == 1
        assert r["indice_perda"] == pytest.approx(25.0)
        assert r["pontos_cancelados"] == pytest.approx(1000.0)

    def test_apenas_liquido_conta_pontos(self, mapa_pontos):
        # Redigitada e recuperada saem do total de pontos/qtd.
        df_canc = pd.DataFrame({
            "categoria_codigo": ["CNC", "CNC", "CNC"],
            "VALOR": [1000.0, 500.0, 300.0],
            "conta_pontuacao": [True, True, True],
            "CLASSIFICACAO": ["liquido", "redigitada", "recuperada"],
        })
        df_pagos = pd.DataFrame({"categoria_codigo": ["CNC", "SAQUE"]})
        df_analise = pd.DataFrame({"categoria_codigo": ["CNC"]})
        r = calcular_pontos_cancelados(df_canc, df_pagos, df_analise, mapa_pontos)
        # Só o liquido (1000) gera pontos; qtd = 1.
        assert r["qtd_cancelados"] == 1
        assert r["pontos_cancelados"] == pytest.approx(1000.0)
        # churn = 1 / (2 + 1 + 1) = 25%
        assert r["indice_perda"] == pytest.approx(25.0)


@pytest.mark.unit
class TestCalcularMediasPontosPorNivel:
    def test_medias_loja_e_consultor(self, sample_pontos_df):
        r = calcular_medias_pontos_por_nivel(sample_pontos_df, 10)
        # lojas: A=600+400=1000, B=0 → média 500 → /10 = 50
        assert r["num_lojas"] == 2
        assert r["media_du_loja_pontos"] == pytest.approx(50.0)
        # consultores: João600, Maria400, Pedro0 → média 1000/3 → /10
        assert r["num_consultores"] == 3
        assert r["media_du_consultor_pontos"] == pytest.approx(1000 / 3 / 10)

    def test_exclui_supervisores(self, sample_pontos_df):
        sup = pd.DataFrame({"SUPERVISOR": ["João"]})
        r = calcular_medias_pontos_por_nivel(sample_pontos_df, 10, df_supervisores=sup)
        assert r["num_consultores"] == 2  # João removido

    def test_exclui_loja_backoffice(self):
        # Vai e Vem (backoffice) fora das médias em pontos.
        df = pd.DataFrame({
            "LOJA": ["A", "VAI E VEM"],
            "CONSULTOR": ["João", "Amos"],
            "pontos": [600.0, 400.0],
        })
        r = calcular_medias_pontos_por_nivel(df, 10)
        assert r["num_lojas"] == 1
        assert r["media_du_loja_pontos"] == pytest.approx(60.0)
        assert r["num_consultores"] == 1
        assert r["media_du_consultor_pontos"] == pytest.approx(60.0)

    def test_pontos_consultores_e_o_numerador_da_populacao_limpa(self):
        """Numerador em pontos, sem supervisor e sem backoffice.

        Espelha ``producao_consultores`` em valor: o card de pontuacao
        dividia ``total_pontos`` (que soma os dois) pelo peso, que
        exclui os dois. Valor e pontos sao a mesma producao vista por
        duas reguas e nao podem discordar sobre a populacao.
        """
        df = pd.DataFrame({
            "LOJA": ["A", "A", "VAI E VEM"],
            "CONSULTOR": ["João", "Chefe", "Amos"],
            "pontos": [600.0, 150.0, 400.0],
        })
        sup = pd.DataFrame({"SUPERVISOR": ["Chefe"]})
        r = calcular_medias_pontos_por_nivel(
            df, 10, df_supervisores=sup, peso_headcount=2.0
        )
        assert r["pontos_consultores"] == pytest.approx(600.0)
        assert r["denominador_consultores"] == "peso"
        # Coerencia interna do card: (pontos/peso)/DU == media DU.
        media_card = r["pontos_consultores"] / r["peso_consultores"]
        assert media_card / 10 == pytest.approx(
            r["media_du_consultor_pontos"]
        )


@pytest.mark.unit
class TestCalcularMixPontos:
    def test_df_vazio(self):
        assert calcular_mix_pontos(pd.DataFrame(), 10000, 20) == []

    def test_pesos_e_metas_por_produto(self, sample_pontos_df):
        res = calcular_mix_pontos(sample_pontos_df, meta_prata=10000, du_total=20)
        by = {r["produto"]: r for r in res}
        # CNC pontos = 600+0 = 600; SAQUE = 400; total_mix = 1000
        cnc = by["CNC"]
        assert cnc["pontos_atual"] == pytest.approx(600.0)
        assert cnc["peso"] == pytest.approx(60.0)  # já em %
        assert cnc["meta_diaria_produto"] == pytest.approx(0.6 * (10000 / 20))
        assert cnc["meta_prata_fatia"] == pytest.approx(6000.0)
        assert cnc["perc_atingido"] == pytest.approx(600 / 6000 * 100)

    def test_du_zero_nao_divide(self, sample_pontos_df):
        res = calcular_mix_pontos(sample_pontos_df, meta_prata=10000, du_total=0)
        assert all(r["meta_diaria_produto"] == 0.0 for r in res)


@pytest.mark.unit
class TestCalcularPrioridadesPontuacao:
    def test_tudo_vazio(self, mapa_pontos):
        assert (
            calcular_prioridades_pontuacao(
                pd.DataFrame(), pd.DataFrame(), mapa_pontos, 10000, 20000
            )
            == []
        )

    def test_gap_peso_e_ordenacao(
        self, sample_pontos_df, sample_analise_df, mapa_pontos
    ):
        res = calcular_prioridades_pontuacao(
            sample_pontos_df, sample_analise_df, mapa_pontos,
            meta_prata=10000, meta_ouro=20000,
        )
        # ordenado por pontos_analise desc
        analises = [r["pontos_analise"] for r in res]
        assert analises == sorted(analises, reverse=True)

        by = {r["produto"]: r for r in res}
        # pagos: total = 600+400 = 1000 → gap_prata = 9000, gap_ouro = 19000
        assert by["CNC"]["gap_prata"] == pytest.approx(9000.0)
        assert by["CNC"]["gap_ouro"] == pytest.approx(19000.0)
        # análise: CNC 1000*1 = 1000; SAQUE 500*2 = 1000
        assert by["CNC"]["pontos_analise"] == pytest.approx(1000.0)
        assert by["SAQUE"]["pontos_analise"] == pytest.approx(1000.0)
        # peso pago CNC = 600/1000 = 60%
        assert by["CNC"]["peso_atual"] == pytest.approx(60.0)
