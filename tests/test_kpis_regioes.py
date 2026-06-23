"""
Testes dos KPIs e rankings por região
(``src/dashboard/kpis/regioes.py``).

``calcular_kpis_por_regiao`` e ``calcular_kpis_por_produto_regiao``
dependem de ``calcular_dias_uteis`` → usam a fixture ``sem_feriados``.
"""
import pandas as pd
import pytest

from src.dashboard.kpis.regioes import (
    _metas_da_regiao,
    calcular_evolucao_media_du,
    calcular_heatmap_regiao_produto,
    calcular_kpis_por_produto_regiao,
    calcular_kpis_por_regiao,
)


@pytest.mark.unit
class TestMetasDaRegiao:
    def test_usa_regiao_propria(self):
        metas = pd.DataFrame({
            "LOJA": ["A", "B", "C"],
            "REGIAO": ["R1", "R2", "R1"],
            "META_PRATA": [10, 20, 5],
        })
        # Filtra pela coluna REGIAO das metas, ignorando lojas_regiao.
        out = _metas_da_regiao(metas, "R1", lojas_regiao=["A"])
        assert set(out["LOJA"]) == {"A", "C"}

    def test_fallback_por_loja_quando_sem_regiao(self):
        metas = pd.DataFrame({"LOJA": ["A", "B"], "META_PRATA": [10, 20]})
        out = _metas_da_regiao(metas, "R1", lojas_regiao=["A"])
        assert set(out["LOJA"]) == {"A"}

    def test_sem_regiao_nem_loja_retorna_tudo(self):
        metas = pd.DataFrame({"META_PRATA": [10, 20]})
        out = _metas_da_regiao(metas, "R1", lojas_regiao=["A"])
        assert len(out) == 2

    def test_metas_vazio_retorna_vazio(self):
        out = _metas_da_regiao(pd.DataFrame(), "R1", lojas_regiao=["A"])
        assert out.empty


@pytest.mark.unit
class TestCalcularKpisPorRegiao:
    def test_agregados_por_regiao(self, df_rank, df_metas_lojas, sem_feriados):
        res = calcular_kpis_por_regiao(
            df_rank, df_metas_lojas, ano=2026, mes=3, dia_atual=16,
        )
        by = {r["Região"]: r for _, r in res.iterrows()}
        r1 = by["R1"]
        assert r1["Valor"] == pytest.approx(1500.0)
        assert r1["Pontos"] == pytest.approx(400.0)
        assert r1["Nº Lojas"] == 1
        assert r1["Nº Consultores"] == 1  # só João
        assert r1["% Atingimento"] == pytest.approx(40.0)  # 400 / 1000
        assert r1["Valor Médio/Consultor"] == pytest.approx(1500.0)

        r2 = by["R2"]
        assert r2["Nº Consultores"] == 2  # Maria e Pedro
        assert r2["Valor Médio/Consultor"] == pytest.approx(2300 / 2)

    def test_sem_regiao_retorna_vazio(self, sem_feriados):
        df = pd.DataFrame({"VALOR": [1.0], "pontos": [1.0], "LOJA": ["A"]})
        assert calcular_kpis_por_regiao(
            df, pd.DataFrame(), 2026, 3, dia_atual=16
        ).empty

    def test_meta_inclui_loja_sem_contrato_via_regiao(
        self, df_rank, sem_feriados
    ):
        """Metas com REGIAO propria contam lojas sem contrato no periodo.

        Loja C tem meta em R1 mas nenhum contrato (ausente de df_rank);
        o total de meta da regiao deve inclui-la, igual ao total global.
        """
        df_metas = pd.DataFrame({
            "LOJA": ["A", "B", "C"],
            "REGIAO": ["R1", "R2", "R1"],
            "META_PRATA": [1000.0, 2000.0, 500.0],
        })
        res = calcular_kpis_por_regiao(
            df_rank, df_metas, ano=2026, mes=3, dia_atual=16,
        )
        by = {r["Região"]: r for _, r in res.iterrows()}
        # R1 soma A (1000) + C (500), apesar de C nao ter contrato.
        assert by["R1"]["Meta Prata"] == pytest.approx(1500.0)
        # % Atingimento usa o denominador maior: 400 / 1500.
        assert by["R1"]["% Atingimento"] == pytest.approx(400 / 1500 * 100)


@pytest.mark.unit
class TestCalcularHeatmapRegiaoProduto:
    def test_atingimento_e_ranking(
        self, df_rank, df_metas_produto_lojas, categorias_regioes
    ):
        df_rk, df_ating = calcular_heatmap_regiao_produto(
            df_rank, df_metas_produto_lojas, categorias_regioes,
        )
        assert list(df_ating.columns) == ["CNC", "SAQUE"]
        # CNC R2: valor 2300 / meta 1000 = 230%
        assert df_ating.loc["R2", "CNC"] == pytest.approx(230.0)
        # CNC R1: valor 1000 / meta 1000 = 100%
        assert df_ating.loc["R1", "CNC"] == pytest.approx(100.0)
        # Ranking CNC: R2 (230%) à frente de R1 (100%)
        assert df_rk.loc["R2", "CNC"] == 1
        assert df_rk.loc["R1", "CNC"] == 2

    def test_sem_colunas_retorna_vazio(self, categorias_regioes):
        df = pd.DataFrame({"VALOR": [1.0]})
        rk, at = calcular_heatmap_regiao_produto(
            df, pd.DataFrame(), categorias_regioes
        )
        assert rk.empty and at.empty


@pytest.mark.unit
class TestCalcularKpisPorProdutoRegiao:
    def test_dict_por_grupo_com_conta_valor(
        self, df_rank, df_metas_produto_lojas, categorias_regioes, sem_feriados
    ):
        res = calcular_kpis_por_produto_regiao(
            df_rank, df_metas_produto_lojas, categorias_regioes,
            ano=2026, mes=3, dia_atual=16,
        )
        assert set(res) == {"CNC", "SAQUE"}
        cnc = res["CNC"]
        # Ordenado por % Atingimento → R2 (230%) primeiro
        assert cnc.iloc[0]["Região"] == "R2"
        assert cnc.iloc[0]["Pos."] == 1
        assert cnc.iloc[0]["Valor"] == pytest.approx(2300.0)
        assert cnc.iloc[0]["% Atingimento"] == pytest.approx(230.0)

    def test_sem_colunas_retorna_vazio(self, categorias_regioes, sem_feriados):
        df = pd.DataFrame({"VALOR": [1.0]})
        assert calcular_kpis_por_produto_regiao(
            df, pd.DataFrame(), categorias_regioes, 2026, 3, dia_atual=16
        ) == {}


@pytest.mark.unit
class TestCalcularEvolucaoMediaDu:
    def _df_ant(self):
        return pd.DataFrame({
            "REGIAO": ["R1", "R2"],
            "VALOR": [1000.0, 1000.0],
        })

    def test_evolucao_e_total(self, df_rank):
        res = calcular_evolucao_media_du(
            df_rank, du_dec_atual=10, df_ant=self._df_ant(), du_dec_ant=10,
        )
        by = {r["Região"]: r for _, r in res.iterrows()}
        # R1 atual 150 vs anterior 100 → +50%
        assert by["R1"]["Mês Atual"] == pytest.approx(150.0)
        assert by["R1"]["% Evolução"] == pytest.approx(50.0)
        # Linha de TOTAL presente
        assert "TOTAL" in by
        assert by["TOTAL"]["Mês Atual"] == pytest.approx(150 + 230)

    def test_exclui_regioes(self, df_rank):
        res = calcular_evolucao_media_du(
            df_rank, 10, self._df_ant(), 10, regioes_excluir={"R2"},
        )
        regioes = set(res["Região"])
        assert "R2" not in regioes
        assert "R1" in regioes

    def test_sem_regiao_retorna_vazio(self):
        df = pd.DataFrame({"VALOR": [1.0]})
        assert calcular_evolucao_media_du(df, 10, None, 10).empty
