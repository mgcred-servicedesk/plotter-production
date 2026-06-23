"""
Testes dos rankings de lojas e consultores
(``src/dashboard/kpis/rankings.py``).

Funções puras: agregam ``df`` (com VALOR > 0) por loja/consultor e
ordenam por atingimento, pontos, ticket médio, média DU ou acelerador.
"""
import pandas as pd
import pytest

from src.dashboard.kpis.rankings import (
    calcular_ranking_consultores,
    calcular_ranking_lojas,
    calcular_ranking_media_du,
    calcular_ranking_pontos,
    calcular_ranking_por_acelerador,
    calcular_ranking_por_produto,
    calcular_ranking_ticket_medio,
)


@pytest.mark.unit
class TestCalcularRankingLojas:
    def test_atingimento_e_ordenacao(self, df_rank, df_metas_lojas):
        rk = calcular_ranking_lojas(df_rank, df_metas_lojas)
        assert list(rk["Posição"]) == [1, 2]
        # A: pontos 400 / meta 1000 = 40%; B: 460 / 2000 = 23%
        primeiro = rk.iloc[0]
        assert primeiro["Loja"] == "A"
        assert primeiro["Atingimento %"] == pytest.approx(40.0)
        assert primeiro["Ticket Médio"] == pytest.approx(1500 / 2)
        # Qtd e Meta Prata são colunas internas, removidas do retorno
        assert "Qtd" not in rk.columns
        assert "Meta Prata" not in rk.columns

    def test_sem_coluna_loja_retorna_vazio(self):
        df = pd.DataFrame({"VALOR": [100.0], "pontos": [10.0]})
        assert calcular_ranking_lojas(df, pd.DataFrame()).empty

    def test_sem_metas_atingimento_zero(self, df_rank):
        rk = calcular_ranking_lojas(df_rank, pd.DataFrame())
        assert (rk["Atingimento %"] == 0).all()


@pytest.mark.unit
class TestCalcularRankingConsultores:
    def test_meta_rateada_por_consultores_da_loja(self, df_rank, df_metas_lojas):
        rk = calcular_ranking_consultores(df_rank, df_metas_lojas)
        by = {r["Consultor"]: r for _, r in rk.iterrows()}
        # B tem 2 consultores → meta rateada = 2000/2 = 1000 cada
        # Pedro: pontos 60 / 1000 = 6%
        assert by["Pedro"]["Atingimento %"] == pytest.approx(6.0)
        # João (loja A, 1 consultor): 400 / 1000 = 40%
        assert by["João"]["Atingimento %"] == pytest.approx(40.0)

    def test_exclui_supervisores(self, df_rank):
        sup = pd.DataFrame({"SUPERVISOR": ["Pedro"]})
        rk = calcular_ranking_consultores(df_rank, pd.DataFrame(), df_supervisores=sup)
        assert "Pedro" not in rk["Consultor"].values


@pytest.mark.unit
class TestCalcularRankingTicketMedio:
    def test_por_loja(self, df_rank):
        rk = calcular_ranking_ticket_medio(df_rank, tipo="loja")
        # B: 2300/2 = 1150 > A: 1500/2 = 750
        assert rk.iloc[0]["Loja"] == "B"
        assert rk.iloc[0]["Ticket Médio"] == pytest.approx(1150.0)

    def test_por_consultor(self, df_rank):
        rk = calcular_ranking_ticket_medio(df_rank, tipo="consultor")
        # Maria: 2000/1 = 2000 é o maior
        assert rk.iloc[0]["Consultor"] == "Maria"


@pytest.mark.unit
class TestCalcularRankingPorProduto:
    def test_dict_por_grupo_ordenado_por_pontos(self, df_rank):
        rks = calcular_ranking_por_produto(df_rank, tipo="loja")
        assert set(rks) == {"CNC", "SAQUE"}
        # CNC: B pontos 460 > A pontos 300
        assert rks["CNC"].iloc[0]["Loja"] == "B"


@pytest.mark.unit
class TestCalcularRankingPontos:
    def test_ordenado_por_pontos(self, df_rank):
        rk = calcular_ranking_pontos(df_rank, tipo="loja")
        # B 460 > A 400
        assert rk.iloc[0]["Loja"] == "B"
        assert rk.iloc[0]["Pontos"] == pytest.approx(460.0)


@pytest.mark.unit
class TestCalcularRankingMediaDu:
    def test_media_du_por_loja(self, df_rank):
        rk = calcular_ranking_media_du(df_rank, tipo="loja", du_decorridos=10)
        # B: 2300/10 = 230 > A: 1500/10 = 150
        assert rk.iloc[0]["Loja"] == "B"
        assert rk.iloc[0]["Média DU"] == pytest.approx(230.0)

    def test_du_zero_usa_minimo_1(self, df_rank):
        rk = calcular_ranking_media_du(df_rank, tipo="loja", du_decorridos=0)
        # du = max(0, 1) = 1 → Média DU == Valor
        b = rk[rk["Loja"] == "B"].iloc[0]
        assert b["Média DU"] == pytest.approx(2300.0)


@pytest.mark.unit
class TestCalcularRankingPorAcelerador:
    def test_conta_apenas_aceleradores_presentes(self, df_rank):
        rks = calcular_ranking_por_acelerador(df_rank, tipo="loja")
        # Só há BMG Med (linha do Pedro); demais aceleradores ausentes
        assert set(rks) == {"BMG Med"}
        bmg = rks["BMG Med"]
        assert bmg.iloc[0]["Loja"] == "B"
        assert bmg.iloc[0]["Qtd"] == 1

    def test_sem_coluna_chave_retorna_vazio(self):
        df = pd.DataFrame({"VALOR": [1.0], "is_bmg_med": [True]})
        assert calcular_ranking_por_acelerador(df, tipo="loja") == {}


@pytest.mark.unit
class TestVariantesConsultor:
    """Cobre os branches simétricos ``tipo='consultor'`` (Loja=first)."""

    def test_pontos_por_consultor(self, df_rank):
        rk = calcular_ranking_pontos(df_rank, tipo="consultor")
        assert "Loja" in rk.columns
        # João e Maria empatam em 400; Pedro 60 fica por último
        assert rk.iloc[-1]["Consultor"] == "Pedro"

    def test_media_du_por_consultor(self, df_rank):
        rk = calcular_ranking_media_du(df_rank, tipo="consultor", du_decorridos=10)
        # Maria 2000/10 = 200 é a maior
        assert rk.iloc[0]["Consultor"] == "Maria"
        assert rk.iloc[0]["Média DU"] == pytest.approx(200.0)

    def test_por_produto_por_consultor(self, df_rank):
        rks = calcular_ranking_por_produto(df_rank, tipo="consultor")
        # CNC: Maria 400 > João 300 > Pedro 60
        assert rks["CNC"].iloc[0]["Consultor"] == "Maria"
        assert "Loja" in rks["CNC"].columns

    def test_acelerador_por_consultor(self, df_rank):
        rks = calcular_ranking_por_acelerador(df_rank, tipo="consultor")
        bmg = rks["BMG Med"]
        assert bmg.iloc[0]["Consultor"] == "Pedro"
        assert bmg.iloc[0]["Loja"] == "B"

    def test_ticket_consultor_sem_coluna_retorna_vazio(self):
        df = pd.DataFrame({"VALOR": [100.0], "pontos": [1.0], "LOJA": ["A"]})
        # tipo consultor, mas sem coluna CONSULTOR → vazio
        assert calcular_ranking_ticket_medio(df, tipo="consultor").empty

    def test_consultores_sem_coluna_retorna_vazio(self):
        df = pd.DataFrame({"VALOR": [100.0], "pontos": [1.0]})
        assert calcular_ranking_consultores(df, pd.DataFrame()).empty


@pytest.mark.unit
class TestRankingGuards:
    """Guardas de coluna ausente (pontos / média DU) → DataFrame vazio."""

    def test_pontos_sem_coluna_retorna_vazio(self):
        df = pd.DataFrame({"VALOR": [100.0], "pontos": [10.0]})
        assert calcular_ranking_pontos(df, tipo="loja").empty

    def test_media_du_sem_coluna_retorna_vazio(self):
        df = pd.DataFrame({"VALOR": [100.0], "pontos": [10.0]})
        assert calcular_ranking_media_du(df, tipo="loja").empty
