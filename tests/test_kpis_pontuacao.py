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
    calcular_resumo_lojas_pontuacao,
    calcular_resumo_lojas_pontuacao_por_regiao,
    ROTULO_SEM_REGIAO,
    ROTULO_TOTAL_RESUMO_LOJAS,
)
from src.dashboard.kpis.gerais import calcular_kpis_gerais
from src.shared.dias_uteis import calcular_dias_uteis


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


@pytest.mark.unit
class TestCalcularResumoLojasPontuacao:
    """Resumo por loja: mesmas fórmulas dos cards, meta de escopo LOJA."""

    @staticmethod
    def _df(linhas):
        return pd.DataFrame(linhas, columns=["LOJA", "pontos"])

    @staticmethod
    def _metas(linhas):
        return pd.DataFrame(linhas, columns=["LOJA", "META_PRATA", "META_OURO"])

    def _resumo(self, df, metas, du_total=20, du_dec=10, du_rest=10):
        return calcular_resumo_lojas_pontuacao(
            df, metas, du_total=du_total, du_decorridos=du_dec,
            du_restantes=du_rest,
        )

    def test_vazio_devolve_frame_com_colunas(self):
        res = self._resumo(pd.DataFrame(), pd.DataFrame())
        assert res.empty
        assert "Meta Diária Ouro" in res.columns

    def test_formulas_por_loja(self):
        res = self._resumo(
            self._df([("A", 3000.0), ("A", 2000.0)]),
            self._metas([("A", 10000.0, 20000.0)]),
        )
        a = res.set_index("Loja").loc["A"]
        assert a["Pontos"] == pytest.approx(5000.0)
        assert a["Projeção"] == pytest.approx(5000 / 10 * 20)
        assert a["Ating. Prata %"] == pytest.approx(50.0)
        assert a["Ating. Ouro %"] == pytest.approx(25.0)
        # (meta - pontos) / DU restantes
        assert a["Meta Diária Prata"] == pytest.approx(500.0)
        assert a["Meta Diária Ouro"] == pytest.approx(1500.0)

    def test_loja_com_meta_sem_pontos_aparece_zerada(self):
        res = self._resumo(
            self._df([("A", 1000.0)]),
            self._metas([("A", 2000.0, 4000.0), ("B", 3000.0, 6000.0)]),
        )
        b = res.set_index("Loja").loc["B"]
        assert b["Pontos"] == 0.0
        assert b["Ating. Prata %"] == 0.0
        assert b["Meta Diária Prata"] == pytest.approx(300.0)

    def test_loja_sem_meta_fica_nan_e_nunca_atingida(self):
        res = self._resumo(self._df([("DIGITAL", 5000.0)]), pd.DataFrame())
        d = res.set_index("Loja").loc["DIGITAL"]
        assert pd.isna(d["Ating. Prata %"])
        assert pd.isna(d["Meta Diária Prata"])
        assert pd.isna(d["Ating. Ouro %"])
        assert d["Projeção"] == pytest.approx(10000.0)

    def test_meta_batida_zera_meta_diaria(self):
        res = self._resumo(
            self._df([("A", 15000.0)]),
            self._metas([("A", 10000.0, 20000.0)]),
        )
        a = res.set_index("Loja").loc["A"]
        assert a["Meta Diária Prata"] == 0.0
        assert a["Meta Diária Ouro"] == pytest.approx(500.0)

    def test_periodo_encerrado_nao_divide_por_zero(self):
        res = self._resumo(
            self._df([("A", 5000.0)]),
            self._metas([("A", 10000.0, 20000.0)]),
            du_dec=20, du_rest=0,
        )
        a = res.set_index("Loja").loc["A"]
        assert pd.isna(a["Meta Diária Prata"])
        assert a["Projeção"] == pytest.approx(5000.0)

    def test_ordena_por_prata_sem_meta_no_fim_e_total_por_ultimo(self):
        res = self._resumo(
            self._df([("A", 1000.0), ("B", 9000.0), ("C", 99999.0)]),
            self._metas([("A", 10000.0, 0.0), ("B", 10000.0, 0.0)]),
        )
        assert res["Loja"].tolist() == [
            "B", "A", "C", ROTULO_TOTAL_RESUMO_LOJAS,
        ]

    def test_total_bate_com_cards_do_topo(self, sem_feriados):
        # Mesmo recorte em calcular_kpis_gerais: o TOTAL do resumo tem de
        # reproduzir pontos, projeção, % e meta diária restante dos cards.
        df = pd.DataFrame({
            "LOJA": ["A", "A", "B"],
            "pontos": [12000.0, 1000.0, 2000.0],
            "VALOR": [100.0, 100.0, 100.0],
            "CONSULTOR": ["x", "y", "z"],
        })
        metas = self._metas([("A", 10000.0, 20000.0), ("B", 8000.0, 9000.0)])
        du_total, du_dec, du_rest = calcular_dias_uteis(2026, 3, 16)
        kpis = calcular_kpis_gerais(df, metas, pd.DataFrame(), 2026, 3, 16)

        total = (
            self._resumo(df, metas, du_total, du_dec, du_rest)
            .set_index("Loja")
            .loc[ROTULO_TOTAL_RESUMO_LOJAS]
        )
        assert total["Pontos"] == pytest.approx(kpis["total_pontos"])
        assert total["Projeção"] == pytest.approx(kpis["projecao_pontos"])
        assert total["Ating. Prata %"] == pytest.approx(kpis["perc_ating_prata"])
        assert total["Ating. Ouro %"] == pytest.approx(kpis["perc_ating_ouro"])
        # Gap do agregado (A acima da meta compensa B), como nos cards.
        assert total["Meta Diária Prata"] == pytest.approx(
            kpis["meta_diaria_restante_pts"]
        )


@pytest.mark.unit
class TestCalcularResumoLojasPontuacaoPorRegiao:
    """Separação por REGIAO do período — cada bloco é o resumo das suas lojas."""

    DU = dict(du_total=20, du_decorridos=10, du_restantes=10)

    def test_vazio(self):
        res = calcular_resumo_lojas_pontuacao_por_regiao(
            pd.DataFrame(), pd.DataFrame(), **self.DU
        )
        assert res["regioes"] == []
        assert res["total"].empty

    def test_blocos_por_regiao_com_total_proprio_e_geral(self):
        df = pd.DataFrame({
            "LOJA": ["A", "B", "C"],
            "REGIAO": ["SUL", "NORTE", "SUL"],
            "pontos": [5000.0, 2000.0, 1000.0],
        })
        metas = pd.DataFrame({
            "LOJA": ["A", "B", "C"],
            "REGIAO": ["SUL", "NORTE", "SUL"],
            "META_PRATA": [10000.0, 4000.0, 2000.0],
            "META_OURO": [20000.0, 8000.0, 4000.0],
        })
        res = calcular_resumo_lojas_pontuacao_por_regiao(df, metas, **self.DU)

        assert [nome for nome, _ in res["regioes"]] == ["NORTE", "SUL"]
        sul = dict(res["regioes"])["SUL"]
        assert sul["Loja"].tolist() == ["A", "C", ROTULO_TOTAL_RESUMO_LOJAS]
        total_sul = sul.iloc[-1]
        assert total_sul["Pontos"] == pytest.approx(6000.0)
        assert total_sul["Ating. Prata %"] == pytest.approx(50.0)

        geral = calcular_resumo_lojas_pontuacao(df, metas, **self.DU)
        pd.testing.assert_frame_equal(
            res["total"], geral.tail(1).reset_index(drop=True)
        )

    def test_regiao_vem_da_meta_antes_da_producao(self):
        # Meta e realizado apuram a região pela competência; se divergirem,
        # vale o eixo da meta que o resumo compara.
        df = pd.DataFrame(
            {"LOJA": ["A"], "REGIAO": ["ANTIGA"], "pontos": [100.0]}
        )
        metas = pd.DataFrame({
            "LOJA": ["A"], "REGIAO": ["NOVA"],
            "META_PRATA": [1000.0], "META_OURO": [2000.0],
        })
        res = calcular_resumo_lojas_pontuacao_por_regiao(df, metas, **self.DU)
        assert [nome for nome, _ in res["regioes"]] == ["NOVA"]

    def test_loja_so_com_producao_usa_regiao_de_mais_pontos(self):
        df = pd.DataFrame({
            "LOJA": ["X", "X", "X"],
            "REGIAO": ["R2", "R1", "R1"],
            "pontos": [300.0, 200.0, 200.0],
        })
        res = calcular_resumo_lojas_pontuacao_por_regiao(
            df, pd.DataFrame(), **self.DU
        )
        assert [nome for nome, _ in res["regioes"]] == ["R1"]

    def test_sem_regiao_vai_para_ultimo_bloco(self):
        df = pd.DataFrame({
            "LOJA": ["A", "DIGITAL"],
            "REGIAO": ["SUL", None],
            "pontos": [100.0, 50.0],
        })
        res = calcular_resumo_lojas_pontuacao_por_regiao(
            df, pd.DataFrame(), **self.DU
        )
        nomes = [nome for nome, _ in res["regioes"]]
        assert nomes == ["SUL", ROTULO_SEM_REGIAO]
        assert dict(res["regioes"])[ROTULO_SEM_REGIAO]["Loja"].tolist() == [
            "DIGITAL", ROTULO_TOTAL_RESUMO_LOJAS,
        ]
