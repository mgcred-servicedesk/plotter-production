"""
Testes dos rankings de lojas e consultores
(``src/dashboard/kpis/rankings.py``).

Funções puras: agregam ``df`` (com VALOR > 0) por loja/consultor e
ordenam por atingimento, pontos, ticket médio, média DU ou acelerador.
"""
import pandas as pd
import pytest

from src.config.settings import PACK_LABEL_AGREGADO
from src.dashboard.kpis.rankings import (
    calcular_ranking_consultores,
    calcular_ranking_lojas,
    calcular_ranking_media_du,
    calcular_ranking_pontos,
    calcular_ranking_por_acelerador,
    calcular_ranking_por_produto,
    calcular_ranking_ticket_medio,
    listar_sem_producao,
    meta_individual_por_loja,
)


@pytest.fixture
def df_metas_consultor():
    """Meta Prata individual por loja (escopo CONSULTOR, chaveado por
    loja — cada linha e o alvo INDIVIDUAL de cada consultor daquela
    loja). Valores deliberadamente diferentes do rateio antigo
    (``META_PRATA`` da loja / nº de consultores) para que qualquer
    resquicio de rateio quebre os testes."""
    return pd.DataFrame({"LOJA": ["A", "B"], "META_PRATA": [500.0, 1500.0]})


@pytest.fixture
def univ_lojas():
    """Universo de lojas ativas: A e B produzem (df_rank); C é zerada."""
    return pd.DataFrame({
        "LOJA": ["A", "B", "C"],
        "REGIAO": ["R1", "R2", "R3"],
    })


@pytest.fixture
def univ_consultores():
    """Universo de consultores ativos: Ana e Carlos sem produção."""
    return pd.DataFrame({
        "CONSULTOR": ["João", "Maria", "Pedro", "Ana", "Carlos"],
        "LOJA": ["A", "B", "B", "C", "C"],
        "REGIAO": ["R1", "R2", "R2", "R3", "R3"],
    })


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
    def test_meta_individual_escopo_consultor(
        self, df_rank, df_metas_lojas, df_metas_consultor
    ):
        """Meta do consultor = META_PRATA de escopo CONSULTOR da loja
        dele — nunca mais o rateio da meta de loja pelo nº de
        consultores que produziram (regra removida sem fallback)."""
        rk = calcular_ranking_consultores(
            df_rank, df_metas_lojas, df_metas_consultor=df_metas_consultor,
        )
        by = {r["Consultor"]: r for _, r in rk.iterrows()}
        # João (loja A): 400 pontos / meta individual 500 = 80%
        assert by["João"]["Atingimento %"] == pytest.approx(80.0)
        # Pedro (loja B): 60 / meta individual 1500 = 4%
        assert by["Pedro"]["Atingimento %"] == pytest.approx(4.0)
        # Maria (loja B): 400 / 1500 = 26,67% — MESMA meta de Pedro (é
        # da loja, não rateada por quem produziu nela)
        assert by["Maria"]["Atingimento %"] == pytest.approx(400 / 1500 * 100)

    def test_meta_de_loja_nao_influencia_atingimento_do_consultor(
        self, df_rank, df_metas_consultor
    ):
        """``df_metas`` (escopo LOJA) fica na assinatura só pelos call
        sites — não participa mais do cálculo do consultor. Prova
        forte: metas de loja absurdas não mudam nada."""
        df_metas_absurdas = pd.DataFrame(
            {"LOJA": ["A", "B"], "META_PRATA": [1.0, 999_999.0]}
        )
        rk_absurda = calcular_ranking_consultores(
            df_rank, df_metas_absurdas, df_metas_consultor=df_metas_consultor,
        )
        rk_sem_metas_loja = calcular_ranking_consultores(
            df_rank, pd.DataFrame(), df_metas_consultor=df_metas_consultor,
        )
        by_absurda = {
            r["Consultor"]: r["Atingimento %"] for _, r in rk_absurda.iterrows()
        }
        by_sem = {
            r["Consultor"]: r["Atingimento %"]
            for _, r in rk_sem_metas_loja.iterrows()
        }
        assert by_absurda == by_sem

    def test_sem_metas_consultor_atingimento_zero(self, df_rank, df_metas_lojas):
        """Sem ``df_metas_consultor`` (parâmetro ausente) — sem
        fallback para o rateio antigo, tudo fica 0%."""
        rk = calcular_ranking_consultores(df_rank, df_metas_lojas)
        assert (rk["Atingimento %"] == 0).all()

    def test_loja_ausente_da_meta_individual_zera_so_ela(self, df_rank):
        """Loja fora do frame de metas individuais ⇒ meta 0 ⇒
        atingimento 0% só para quem está nela — sem fallback
        silencioso para a meta de loja."""
        metas_incompletas = pd.DataFrame(
            {"LOJA": ["A"], "META_PRATA": [500.0]}
        )  # loja B ausente
        rk = calcular_ranking_consultores(
            df_rank, pd.DataFrame(), df_metas_consultor=metas_incompletas,
        )
        by = {r["Consultor"]: r for _, r in rk.iterrows()}
        assert by["João"]["Atingimento %"] == pytest.approx(80.0)
        assert by["Maria"]["Atingimento %"] == 0.0
        assert by["Pedro"]["Atingimento %"] == 0.0

    def test_universo_zerado_recebe_meta_real_da_loja_de_cadastro(
        self, df_rank, univ_consultores, df_metas_consultor
    ):
        """Consultor do universo sem produção entra zerado, mas com a
        loja de cadastro (usada para buscar a meta individual dela —
        nunca a loja 0/ausente)."""
        metas = pd.concat(
            [df_metas_consultor, pd.DataFrame({"LOJA": ["C"], "META_PRATA": [800.0]})],
            ignore_index=True,
        )
        rk = calcular_ranking_consultores(
            df_rank, pd.DataFrame(), df_universo=univ_consultores,
            df_metas_consultor=metas,
        )
        by = {r["Consultor"]: r for _, r in rk.iterrows()}
        assert by["Ana"]["Pontos"] == 0
        assert by["Ana"]["Loja"] == "C"  # loja de cadastro, não vazia
        # meta_individual_por_loja confirma que "C" mapeia para a meta
        # real (800), não para 0 por ausência de loja:
        assert meta_individual_por_loja(
            pd.Series(["C"]), metas
        ).iloc[0] == pytest.approx(800.0)
        assert by["Ana"]["Atingimento %"] == 0.0  # 0 pontos / 800 = 0%

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

    def test_pack_desmembrado_em_tres_produtos(self):
        # Ranking e por Pontos (sem meta) → o PACK vira FGTS,
        # ANT. DE BENEF. e CNC 13º, cada um com o seu ranking.
        df = pd.DataFrame({
            "LOJA": ["A", "B", "A", "B", "A"],
            "CONSULTOR": ["João", "Maria", "João", "Maria", "João"],
            "grupo_dashboard": ["PACK"] * 4 + ["CNC"],
            "categoria_codigo": [
                "FGTS", "FGTS", "ANT_BENEF", "CNC_13", "CNC",
            ],
            "VALOR": [100.0, 200.0, 300.0, 400.0, 500.0],
            "pontos": [1.0, 2.0, 3.0, 4.0, 5.0],
        })
        rks = calcular_ranking_por_produto(df, tipo="loja")
        assert set(rks) == {"FGTS", "ANT. DE BENEF.", "CNC 13º", "CNC"}
        # FGTS: B (200) na frente de A (100)
        assert rks["FGTS"].iloc[0]["Loja"] == "B"
        assert len(rks["ANT. DE BENEF."]) == 1
        assert rks["ANT. DE BENEF."].iloc[0]["Loja"] == "A"

    def test_sem_categoria_mantem_grupo(self):
        # Digitacao/dados legados sem categoria_codigo: cai no label
        # amigavel do grupo, sem quebrar o dict.
        df = pd.DataFrame({
            "LOJA": ["A"],
            "CONSULTOR": ["João"],
            "grupo_dashboard": ["PACK"],
            "VALOR": [100.0],
            "pontos": [1.0],
        })
        rks = calcular_ranking_por_produto(df, tipo="loja")
        assert set(rks) == {PACK_LABEL_AGREGADO}


@pytest.mark.unit
class TestCalcularRankingPontos:
    def test_ordenado_por_pontos(self, df_rank):
        rk = calcular_ranking_pontos(df_rank, tipo="loja")
        # B 460 > A 400
        assert rk.iloc[0]["Loja"] == "B"
        assert rk.iloc[0]["Pontos"] == pytest.approx(460.0)


@pytest.mark.unit
class TestAgruparLojaDoConsultor:
    """A coluna ``Loja`` (escopo consultor) virou a CHAVE da meta
    individual — precisa ser a de MAIOR pontuação no período, com
    desempate alfabético, e não mais a primeira linha na ordem de
    chegada. Exercitada via ``calcular_ranking_pontos`` (expõe a
    coluna ``Loja`` sem precisar de metas)."""

    def test_loja_e_a_de_maior_pontuacao_independente_da_ordem(self):
        # Loja Z vem PRIMEIRO nas linhas e tem MENOS pontos isolada,
        # mas a soma dela (10 + 40 = 50) supera a loja A (5) — as
        # linhas estão em ordem "errada" de propósito.
        df = pd.DataFrame({
            "LOJA":      ["Z", "A", "Z"],
            "CONSULTOR": ["Ana", "Ana", "Ana"],
            "VALOR":     [100.0, 50.0, 200.0],
            "pontos":    [10.0, 5.0, 40.0],
        })
        rk = calcular_ranking_pontos(df, tipo="consultor")
        assert rk.iloc[0]["Loja"] == "Z"

    def test_empate_exato_resolve_por_ordem_alfabetica(self):
        df = pd.DataFrame({
            "LOJA":      ["Z", "A"],
            "CONSULTOR": ["Ana", "Ana"],
            "VALOR":     [100.0, 100.0],
            "pontos":    [30.0, 30.0],
        })
        rk = calcular_ranking_pontos(df, tipo="consultor")
        assert rk.iloc[0]["Loja"] == "A"

    def test_ordem_das_linhas_trocada_nao_muda_o_resultado(self):
        # Mesmos dados do teste acima, linhas em ordem inversa.
        df = pd.DataFrame({
            "LOJA":      ["A", "Z"],
            "CONSULTOR": ["Ana", "Ana"],
            "VALOR":     [100.0, 100.0],
            "pontos":    [30.0, 30.0],
        })
        rk = calcular_ranking_pontos(df, tipo="consultor")
        assert rk.iloc[0]["Loja"] == "A"


@pytest.mark.unit
class TestMetaIndividualPorLoja:
    """``meta_individual_por_loja`` — lookup puro, sem fallback."""

    def test_lookup_simples(self):
        lojas = pd.Series(["A", "B", "A"])
        metas = pd.DataFrame({"LOJA": ["A", "B"], "META_PRATA": [500.0, 1500.0]})
        out = meta_individual_por_loja(lojas, metas)
        assert out.tolist() == [500.0, 1500.0, 500.0]

    def test_lojas_none_devolve_series_vazia(self):
        metas = pd.DataFrame({"LOJA": ["A"], "META_PRATA": [1.0]})
        out = meta_individual_por_loja(None, metas)
        assert out.empty

    def test_frame_de_metas_none_devolve_zeros(self):
        out = meta_individual_por_loja(pd.Series(["A", "B"]), None)
        assert out.tolist() == [0.0, 0.0]

    def test_frame_de_metas_vazio_devolve_zeros(self):
        out = meta_individual_por_loja(pd.Series(["A"]), pd.DataFrame())
        assert out.tolist() == [0.0]

    def test_coluna_loja_ausente_devolve_zeros(self):
        metas = pd.DataFrame({"META_PRATA": [500.0]})
        out = meta_individual_por_loja(pd.Series(["A"]), metas)
        assert out.tolist() == [0.0]

    def test_coluna_meta_prata_ausente_devolve_zeros(self):
        metas = pd.DataFrame({"LOJA": ["A"]})
        out = meta_individual_por_loja(pd.Series(["A"]), metas)
        assert out.tolist() == [0.0]

    def test_loja_ausente_do_frame_devolve_zero_so_para_ela(self):
        metas = pd.DataFrame({"LOJA": ["A"], "META_PRATA": [500.0]})
        out = meta_individual_por_loja(pd.Series(["A", "X"]), metas)
        assert out.tolist() == [500.0, 0.0]

    def test_meta_nula_vira_zero(self):
        metas = pd.DataFrame({"LOJA": ["A"], "META_PRATA": [None]})
        out = meta_individual_por_loja(pd.Series(["A"]), metas)
        assert out.tolist() == [0.0]

    def test_meta_zero_permanece_zero(self):
        metas = pd.DataFrame({"LOJA": ["A"], "META_PRATA": [0.0]})
        out = meta_individual_por_loja(pd.Series(["A"]), metas)
        assert out.tolist() == [0.0]


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
class TestUniversoSemProducao:
    """df_universo: entidades ativas sem produção entram zeradas no fim."""

    def test_loja_zerada_entra_no_fim_com_zeros(
        self, df_rank, df_metas_lojas, univ_lojas,
    ):
        rk = calcular_ranking_lojas(
            df_rank, df_metas_lojas, df_universo=univ_lojas,
        )
        assert len(rk) == 3
        ultimo = rk.iloc[-1]
        assert ultimo["Loja"] == "C"
        assert ultimo["Posição"] == 3
        assert ultimo["Pontos"] == pytest.approx(0.0)
        assert ultimo["Atingimento %"] == pytest.approx(0.0)
        assert ultimo["Ticket Médio"] == pytest.approx(0.0)
        assert ultimo["REGIAO"] == "R3"

    def test_match_normalizado_nao_duplica(self, df_rank, df_metas_lojas):
        # Universo com caixa/espaços divergentes → não duplica A e B.
        univ = pd.DataFrame({
            "LOJA": ["  a ", "b"], "REGIAO": ["R1", "R2"],
        })
        rk = calcular_ranking_lojas(df_rank, df_metas_lojas, df_universo=univ)
        assert len(rk) == 2

    def test_universo_none_preserva_comportamento(
        self, df_rank, df_metas_lojas,
    ):
        rk = calcular_ranking_lojas(df_rank, df_metas_lojas)
        assert len(rk) == 2

    def test_top_n_corta_zeradas(self, df_rank, df_metas_lojas, univ_lojas):
        # Zeradas ficam no fim → o corte do Top N as esconde (por isso
        # a UI usa bloco "Sem produção" separado nas visões globais).
        rk = calcular_ranking_lojas(
            df_rank, df_metas_lojas, top_n=2, df_universo=univ_lojas,
        )
        assert "C" not in rk["Loja"].values

    def test_consultor_zerado_e_supervisor_excluido(
        self, df_rank, df_metas_lojas, univ_consultores,
    ):
        sup = pd.DataFrame({"SUPERVISOR": ["Carlos"]})
        rk = calcular_ranking_consultores(
            df_rank, df_metas_lojas,
            df_supervisores=sup, df_universo=univ_consultores,
        )
        assert "Ana" in rk["Consultor"].values
        assert "Carlos" not in rk["Consultor"].values
        ana = rk[rk["Consultor"] == "Ana"].iloc[0]
        assert ana["Loja"] == "C"
        assert ana["Pontos"] == pytest.approx(0.0)
        assert ana["Atingimento %"] == pytest.approx(0.0)

    def test_pontos_com_universo_loja(self, df_rank, univ_lojas):
        rk = calcular_ranking_pontos(
            df_rank, tipo="loja", df_universo=univ_lojas,
        )
        assert rk.iloc[-1]["Loja"] == "C"
        assert rk.iloc[-1]["Pontos"] == pytest.approx(0.0)

    def test_regiao_toda_zerada(self, df_metas_lojas, univ_lojas):
        # Nenhum produtor (ex.: recorte de região sem produção) →
        # ranking vira só o universo zerado.
        df_vazio = pd.DataFrame({
            "LOJA": pd.Series(dtype=str),
            "REGIAO": pd.Series(dtype=str),
            "VALOR": pd.Series(dtype=float),
            "pontos": pd.Series(dtype=float),
        })
        rk = calcular_ranking_lojas(
            df_vazio, df_metas_lojas, df_universo=univ_lojas,
        )
        assert list(rk["Loja"]) == ["A", "B", "C"]
        assert (rk["Pontos"] == 0).all()


@pytest.mark.unit
class TestListarSemProducao:
    """Lista de controle: universo ativo sem contrato VALOR > 0."""

    def test_lojas_zeradas(self, df_rank, univ_lojas):
        tab = listar_sem_producao(df_rank, univ_lojas, tipo="loja")
        assert list(tab["Loja"]) == ["C"]
        assert list(tab["REGIAO"]) == ["R3"]

    def test_valor_zero_conta_como_sem_producao(self, df_rank, univ_lojas):
        # Loja C só tem contrato de emissão (VALOR zerado) → segue
        # listada, espelhando o critério VALOR > 0 dos rankings.
        linha_c = pd.DataFrame({
            "LOJA": ["C"], "REGIAO": ["R3"], "CONSULTOR": ["Ana"],
            "grupo_dashboard": ["CNC"], "categoria_codigo": ["CNC"],
            "VALOR": [0.0], "pontos": [0.0],
            "TIPO_PRODUTO": ["CNC"], "SUBTIPO": [""],
            "is_bmg_med": [False], "is_seguro_vida": [False],
        })
        df = pd.concat([df_rank, linha_c], ignore_index=True)
        tab = listar_sem_producao(df, univ_lojas, tipo="loja")
        assert "C" in tab["Loja"].values

    def test_consultores_exclui_supervisores(
        self, df_rank, univ_consultores,
    ):
        sup = pd.DataFrame({"SUPERVISOR": ["Carlos"]})
        tab = listar_sem_producao(
            df_rank, univ_consultores, tipo="consultor",
            df_supervisores=sup,
        )
        assert list(tab["Consultor"]) == ["Ana"]
        assert list(tab["Loja"]) == ["C"]
        assert list(tab["REGIAO"]) == ["R3"]

    def test_match_normalizado(self, univ_lojas):
        # Produção com caixa/espaços divergentes ainda casa com o
        # cadastro → loja não aparece como zerada.
        df = pd.DataFrame({"LOJA": ["  a  ", "B "], "VALOR": [10.0, 5.0]})
        tab = listar_sem_producao(df, univ_lojas, tipo="loja")
        assert list(tab["Loja"]) == ["C"]

    def test_universo_none_ou_vazio(self, df_rank):
        assert listar_sem_producao(df_rank, None, tipo="loja").empty
        assert listar_sem_producao(
            df_rank, pd.DataFrame(), tipo="loja",
        ).empty

    def test_df_sem_colunas_lista_universo_inteiro(self, univ_lojas):
        tab = listar_sem_producao(pd.DataFrame(), univ_lojas, tipo="loja")
        assert list(tab["Loja"]) == ["A", "B", "C"]

    def test_recorte_por_produto(self, df_rank, univ_lojas):
        # Sub-aba Por Produto: df recortado pelo grupo → quem não
        # vendeu AQUELE produto aparece zerado (SAQUE: só A vendeu).
        df_saque = df_rank[df_rank["grupo_dashboard"] == "SAQUE"]
        tab = listar_sem_producao(df_saque, univ_lojas, tipo="loja")
        assert list(tab["Loja"]) == ["B", "C"]

    def test_recorte_por_produto_consultores(
        self, df_rank, univ_consultores,
    ):
        # CNC: João, Maria e Pedro venderam → só Ana e Carlos zerados;
        # com Carlos supervisor, resta Ana.
        sup = pd.DataFrame({"SUPERVISOR": ["Carlos"]})
        df_cnc = df_rank[df_rank["grupo_dashboard"] == "CNC"]
        tab = listar_sem_producao(
            df_cnc, univ_consultores, tipo="consultor", df_supervisores=sup,
        )
        assert list(tab["Consultor"]) == ["Ana"]


@pytest.mark.unit
class TestRankingGuards:
    """Guardas de coluna ausente (pontos / média DU) → DataFrame vazio."""

    def test_pontos_sem_coluna_retorna_vazio(self):
        df = pd.DataFrame({"VALOR": [100.0], "pontos": [10.0]})
        assert calcular_ranking_pontos(df, tipo="loja").empty

    def test_media_du_sem_coluna_retorna_vazio(self):
        df = pd.DataFrame({"VALOR": [100.0], "pontos": [10.0]})
        assert calcular_ranking_media_du(df, tipo="loja").empty


@pytest.mark.unit
class TestExclusaoBackoffice:
    """Consultores de lojas de backoffice (Vai e Vem) não são ranqueados
    nem listados como zerados — a produção paga deles é repassada ao
    consultor de loja que iniciou a negociação. A exclusão vale só para
    o eixo consultor; a loja em si segue no ranking de lojas."""

    @pytest.fixture
    def df_com_backoffice(self, df_rank):
        linha = pd.DataFrame({
            "LOJA": ["VAI E VEM"], "REGIAO": ["ALEXANDRE"],
            "CONSULTOR": ["Amos"], "grupo_dashboard": ["CNC"],
            "categoria_codigo": ["CNC"], "VALOR": [800.0],
            "pontos": [200.0], "TIPO_PRODUTO": ["CNC"], "SUBTIPO": [""],
            "is_bmg_med": [False], "is_seguro_vida": [False],
        })
        return pd.concat([df_rank, linha], ignore_index=True)

    @pytest.fixture
    def univ_com_backoffice(self, univ_consultores):
        extra = pd.DataFrame({
            "CONSULTOR": ["Carla"], "LOJA": ["VAI E VEM"],
            "REGIAO": ["ALEXANDRE"],
        })
        return pd.concat([univ_consultores, extra], ignore_index=True)

    def test_ranking_consultores_sem_backoffice(
        self, df_com_backoffice, df_metas_lojas, univ_com_backoffice,
    ):
        rk = calcular_ranking_consultores(
            df_com_backoffice, df_metas_lojas,
            df_universo=univ_com_backoffice,
        )
        assert "Amos" not in rk["Consultor"].values   # produção paga
        assert "Carla" not in rk["Consultor"].values  # universo zerado

    def test_ranking_pontos_consultor_sem_backoffice(
        self, df_com_backoffice, univ_com_backoffice,
    ):
        rk = calcular_ranking_pontos(
            df_com_backoffice, tipo="consultor",
            df_universo=univ_com_backoffice,
        )
        assert "Amos" not in rk["Consultor"].values
        assert "Carla" not in rk["Consultor"].values

    def test_zerados_sem_backoffice(
        self, df_com_backoffice, univ_com_backoffice,
    ):
        tab = listar_sem_producao(
            df_com_backoffice, univ_com_backoffice, tipo="consultor",
        )
        assert "Carla" not in tab["Consultor"].values
        # consultores de loja seguem listados normalmente
        assert "Ana" in tab["Consultor"].values

    def test_match_loja_normalizado(self):
        # Caixa/espaços divergentes ainda casam com LOJAS_BACKOFFICE.
        univ = pd.DataFrame({
            "CONSULTOR": ["Carla"], "LOJA": ["  vai e vem "],
            "REGIAO": ["ALEXANDRE"],
        })
        df = pd.DataFrame(columns=["CONSULTOR", "LOJA", "VALOR"])
        tab = listar_sem_producao(df, univ, tipo="consultor")
        assert tab.empty

    def test_loja_backoffice_segue_no_ranking_de_lojas(
        self, df_com_backoffice, df_metas_lojas,
    ):
        # Escopo aprovado: exclusão apenas no eixo consultor.
        rk = calcular_ranking_lojas(df_com_backoffice, df_metas_lojas)
        assert "VAI E VEM" in rk["Loja"].values
