"""Testes das funcoes de detalhamento dos cards de KPI
(``src/dashboard/kpis/detalhes_cards.py``).

Funcoes puras (sem Supabase/Streamlit), entao os testes passam
``du_decorridos`` / ``du_totais`` diretamente e nao precisam da fixture
``sem_feriados``. Convencoes de coluna seguem o loader (MAIUSCULAS +
``grupo_dashboard`` / ``categoria_codigo`` / ``conta_valor``), exceto a
digitacao diaria, que usa as minusculas do RPC.
"""
import pandas as pd
import pytest

from src.config.settings import PACK_LABEL_AGREGADO
from src.dashboard.kpis.detalhes_cards import (
    COL_PRODUTO_DETALHADO,
    _aplicar_conta_valor,
    _projetar,
    adicionar_produto_detalhado,
    detalhe_analise_pivot,
    detalhe_analise_por_produto,
    detalhe_analise_por_regiao,
    detalhe_cancelados_pivot,
    detalhe_cancelados_por_produto,
    detalhe_cancelados_por_regiao,
    detalhe_digitacao_diaria,
    detalhe_medias_por_produto,
    detalhe_medias_por_regiao,
    detalhe_reaproveitamento,
    filtrar_ultimo_dia,
    ocultar_colunas_zeradas,
)


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestProjetar:
    def test_projecao_linear(self):
        # 1000 acumulado em 10 DU, projetado para 20 DU → 2000
        assert _projetar(1000.0, 10, 20) == pytest.approx(2000.0)

    def test_du_decorridos_zero_retorna_zero(self):
        assert _projetar(1000.0, 0, 20) == 0.0

    def test_du_decorridos_negativo_retorna_zero(self):
        assert _projetar(1000.0, -3, 20) == 0.0


@pytest.mark.unit
class TestAplicarContaValor:
    def test_zera_valor_sem_alterar_contagem(self):
        df = pd.DataFrame(
            {
                "VALOR": [100.0, 200.0, 300.0],
                "conta_valor": [True, False, True],
            }
        )
        out = _aplicar_conta_valor(df)
        assert len(out) == 3  # contagem preservada
        assert out["VALOR"].tolist() == [100.0, 0.0, 300.0]
        # nao muta o original
        assert df["VALOR"].tolist() == [100.0, 200.0, 300.0]

    def test_sem_coluna_conta_valor_inalterado(self):
        df = pd.DataFrame({"VALOR": [100.0, 200.0]})
        out = _aplicar_conta_valor(df)
        assert out["VALOR"].tolist() == [100.0, 200.0]

    def test_conta_valor_nulo_trata_como_true(self):
        df = pd.DataFrame({"VALOR": [100.0], "conta_valor": [None]})
        out = _aplicar_conta_valor(df)
        assert out["VALOR"].tolist() == [100.0]


# ──────────────────────────────────────────────────────────────────
# Quadro 1 — Analise
# ──────────────────────────────────────────────────────────────────


@pytest.fixture
def df_analise_detalhe():
    return pd.DataFrame(
        {
            "grupo_dashboard": ["CNC", "CNC", "SAQUE", "SAQUE"],
            "REGIAO": ["R1", "R1", "R2", "R2"],
            "VALOR": [1000.0, 500.0, 800.0, 0.0],
            "conta_valor": [True, True, True, True],
        }
    )


@pytest.fixture
def df_analise_loja():
    return pd.DataFrame(
        {
            "grupo_dashboard": ["CNC", "CNC", "SAQUE", "SAQUE"],
            "REGIAO": ["R1", "R1", "R2", "R2"],
            "LOJA": ["L1", "L1", "L2", "L2"],
            "VALOR": [1000.0, 500.0, 800.0, 0.0],
            "conta_valor": [True, True, True, True],
        }
    )


@pytest.mark.unit
class TestDetalheAnalise:
    _COLS = [
        "Produto", "Valor", "Quantidade", "Ticket Médio",
        "Média DU", "Projeção",
    ]

    def test_por_produto_agrega_projeta(self, df_analise_detalhe):
        res = detalhe_analise_por_produto(
            df_analise_detalhe, du_decorridos=10, du_totais=20
        )
        assert list(res.columns) == self._COLS
        cnc = res[res["Produto"] == "CNC"].iloc[0]
        assert cnc["Valor"] == pytest.approx(1500.0)
        assert cnc["Quantidade"] == 2
        assert cnc["Ticket Médio"] == pytest.approx(750.0)
        assert cnc["Média DU"] == pytest.approx(150.0)
        assert cnc["Projeção"] == pytest.approx(3000.0)

    def test_quantidade_ignora_valor_zero(self, df_analise_detalhe):
        res = detalhe_analise_por_produto(
            df_analise_detalhe, du_decorridos=10, du_totais=20
        )
        saque = res[res["Produto"] == "SAQUE"].iloc[0]
        assert saque["Valor"] == pytest.approx(800.0)
        # a linha com VALOR 0 nao conta na quantidade
        assert saque["Quantidade"] == 1

    def test_por_regiao(self, df_analise_detalhe):
        res = detalhe_analise_por_regiao(
            df_analise_detalhe, du_decorridos=10, du_totais=20
        )
        assert list(res["REGIAO"]) == ["R1", "R2"]
        assert res[res["REGIAO"] == "R1"].iloc[0]["Valor"] == pytest.approx(1500.0)

    def test_por_loja(self, df_analise_loja):
        res = detalhe_analise_por_regiao(
            df_analise_loja, du_decorridos=10, du_totais=20,
            dimensao="LOJA",
        )
        assert list(res["LOJA"]) == ["L1", "L2"]
        l1 = res[res["LOJA"] == "L1"].iloc[0]
        assert l1["Valor"] == pytest.approx(1500.0)

    def test_df_vazio_retorna_colunas(self):
        res = detalhe_analise_por_produto(
            pd.DataFrame(), du_decorridos=10, du_totais=20
        )
        assert res.empty
        assert list(res.columns) == self._COLS

    def test_por_produto_desmembra_o_pack(self):
        # Quadro sem meta → PACK vira 3 linhas com os rotulos da planilha.
        df = pd.DataFrame(
            {
                "grupo_dashboard": ["PACK", "PACK", "PACK", "CNC"],
                "categoria_codigo": ["FGTS", "ANT_BENEF", "CNC_13", "CNC"],
                "VALOR": [100.0, 200.0, 300.0, 400.0],
                "conta_valor": [True, True, True, True],
            }
        )
        res = detalhe_analise_por_produto(df, du_decorridos=5, du_totais=10)
        assert set(res["Produto"]) == {
            "FGTS", "ANT. DE BENEF.", "CNC 13º", "CNC",
        }
        ant = res[res["Produto"] == "ANT. DE BENEF."].iloc[0]
        assert ant["Valor"] == pytest.approx(200.0)
        assert ant["Quantidade"] == 1

    def test_conta_valor_false_zera_valor_mantem_qtd(self):
        df = pd.DataFrame(
            {
                "grupo_dashboard": ["EMISSAO", "EMISSAO"],
                "VALOR": [300.0, 200.0],
                "conta_valor": [False, False],
            }
        )
        res = detalhe_analise_por_produto(df, du_decorridos=5, du_totais=10)
        em = res.iloc[0]
        assert em["Valor"] == pytest.approx(0.0)
        # VALOR zerado → nenhuma linha com VALOR > 0
        assert em["Quantidade"] == 0


# ──────────────────────────────────────────────────────────────────
# Quadro 2 — Digitacao diaria
# ──────────────────────────────────────────────────────────────────


@pytest.fixture
def df_digitacao():
    """df cru do RPC obter_digitacao_diaria (colunas minusculas)."""
    return pd.DataFrame(
        {
            "data_cadastro": ["2026-06-01", "2026-06-02", "2026-06-03"],
            "qtd_digitada": [10, 15, 12],
            "valor_digitado": [1000.0, 1500.0, 1200.0],
        }
    )


@pytest.mark.unit
class TestDetalheDigitacaoDiaria:
    _COLS = [
        "data_cadastro", "qtd_digitada", "Var. Qtd", "Var. %", "valor_digitado",
    ]

    def test_variacao_qtd_absoluta_e_percentual(self, df_digitacao):
        res = detalhe_digitacao_diaria(df_digitacao, du_decorridos=3, du_totais=20)
        assert list(res.columns) == self._COLS
        # 1ª linha: sem anterior → 0/0
        assert res.iloc[0]["Var. Qtd"] == 0
        assert res.iloc[0]["Var. %"] == pytest.approx(0.0)
        # 2ª linha: 15 - 10 = +5 ; +50%
        assert res.iloc[1]["Var. Qtd"] == 5
        assert res.iloc[1]["Var. %"] == pytest.approx(50.0)
        # 3ª linha: 12 - 15 = -3 ; -20%
        assert res.iloc[2]["Var. Qtd"] == -3
        assert res.iloc[2]["Var. %"] == pytest.approx(-20.0)

    def test_linha_projecao_acumulado(self, df_digitacao):
        res = detalhe_digitacao_diaria(df_digitacao, du_decorridos=3, du_totais=20)
        proj = res.iloc[-1]
        assert proj["data_cadastro"] == "Projeção do mês"
        # qtd acum = 37 ; 37/3*20 = 246.67 → round = 247
        assert proj["qtd_digitada"] == 247
        # valor acum = 3700 ; 3700/3*20
        assert proj["valor_digitado"] == pytest.approx(3700 / 3 * 20)

    def test_divisao_por_zero_anterior(self):
        df = pd.DataFrame(
            {
                "data_cadastro": ["2026-06-01", "2026-06-02"],
                "qtd_digitada": [0, 5],
                "valor_digitado": [0.0, 500.0],
            }
        )
        res = detalhe_digitacao_diaria(df, du_decorridos=2, du_totais=10)
        # anterior == 0 → Var. % = 0 (sem inf)
        assert res.iloc[1]["Var. %"] == pytest.approx(0.0)
        assert res.iloc[1]["Var. Qtd"] == 5

    def test_df_vazio_retorna_colunas(self):
        res = detalhe_digitacao_diaria(
            pd.DataFrame(), du_decorridos=3, du_totais=20
        )
        assert res.empty
        assert list(res.columns) == self._COLS

    def test_ordena_por_data(self):
        df = pd.DataFrame(
            {
                "data_cadastro": ["2026-06-03", "2026-06-01", "2026-06-02"],
                "qtd_digitada": [12, 10, 15],
                "valor_digitado": [1200.0, 1000.0, 1500.0],
            }
        )
        res = detalhe_digitacao_diaria(df, du_decorridos=3, du_totais=20)
        # exclui a linha de projecao para checar ordenacao
        serie = res[res["data_cadastro"] != "Projeção do mês"]
        assert list(serie["data_cadastro"]) == [
            "01/06/2026", "02/06/2026", "03/06/2026",
        ]


# ──────────────────────────────────────────────────────────────────
# Quadro 3 — Cancelados
# ──────────────────────────────────────────────────────────────────


@pytest.fixture
def df_cancelados_detalhe():
    return pd.DataFrame(
        {
            "grupo_dashboard": ["CNC", "CNC", "SAQUE"],
            "REGIAO": ["R1", "R1", "R2"],
            "VALOR": [1000.0, 500.0, 800.0],
            "CLASSIFICACAO": ["liquido", "redigitada", "liquido"],
            "conta_valor": [True, True, True],
        }
    )


@pytest.fixture
def df_cancelados_loja():
    return pd.DataFrame(
        {
            "grupo_dashboard": ["CNC", "CNC", "SAQUE"],
            "REGIAO": ["R1", "R1", "R2"],
            "LOJA": ["L1", "L1", "L2"],
            "VALOR": [1000.0, 500.0, 800.0],
            "CLASSIFICACAO": ["liquido", "redigitada", "liquido"],
            "conta_valor": [True, True, True],
        }
    )


@pytest.mark.unit
class TestDetalheCancelados:
    def test_por_produto_so_liquidos(self, df_cancelados_detalhe):
        res = detalhe_cancelados_por_produto(
            df_cancelados_detalhe, du_decorridos=10, du_totais=20
        )
        cnc = res[res["Produto"] == "CNC"].iloc[0]
        # apenas a linha 'liquido' do CNC conta (a 'redigitada' sai)
        assert cnc["Valor"] == pytest.approx(1000.0)
        assert cnc["Quantidade"] == 1

    def test_por_regiao_so_liquidos(self, df_cancelados_detalhe):
        res = detalhe_cancelados_por_regiao(
            df_cancelados_detalhe, du_decorridos=10, du_totais=20
        )
        r1 = res[res["REGIAO"] == "R1"].iloc[0]
        assert r1["Valor"] == pytest.approx(1000.0)
        assert r1["Quantidade"] == 1

    def test_por_loja_so_liquidos(self, df_cancelados_loja):
        res = detalhe_cancelados_por_regiao(
            df_cancelados_loja, du_decorridos=10, du_totais=20,
            dimensao="LOJA",
        )
        l1 = res[res["LOJA"] == "L1"].iloc[0]
        assert l1["Valor"] == pytest.approx(1000.0)
        assert l1["Quantidade"] == 1

    def test_df_vazio(self):
        res = detalhe_cancelados_por_produto(
            pd.DataFrame(), du_decorridos=10, du_totais=20
        )
        assert res.empty


# ──────────────────────────────────────────────────────────────────
# Reaproveitamento
# ──────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestDetalheReaproveitamento:
    _COLS = ["Categoria", "Quantidade", "Valor"]

    def test_composicao_completa(self):
        df = pd.DataFrame(
            {
                "VALOR": [1000.0, 500.0, 800.0, 300.0],
                "CLASSIFICACAO": [
                    "redigitada", "recuperada", "liquido", "liquido",
                ],
                "RECUPERADA_OUTRO": [False, False, True, False],
                "RECUPERADA_OUTRA_LOJA": [False, False, False, True],
                "RECUPERADA_OUTRA_REGIAO": [False, False, False, False],
                "conta_valor": [True, True, True, True],
            }
        )
        res = detalhe_reaproveitamento(df)
        assert list(res.columns) == self._COLS
        salvos = res[res["Categoria"] == "Redigitada/Recuperada"].iloc[0]
        assert salvos["Quantidade"] == 2  # redigitada + recuperada
        assert salvos["Valor"] == pytest.approx(1500.0)

        cons = res[
            res["Categoria"] == "Oportunidade Perdida (Consultor)"
        ].iloc[0]
        assert cons["Quantidade"] == 1
        assert cons["Valor"] == pytest.approx(800.0)

        loja = res[res["Categoria"] == "Oportunidade Perdida (Loja)"].iloc[0]
        assert loja["Quantidade"] == 1
        assert loja["Valor"] == pytest.approx(300.0)

        regiao = res[
            res["Categoria"] == "Oportunidade Perdida (Região)"
        ].iloc[0]
        assert regiao["Quantidade"] == 0

    def test_sem_projecao_apenas_composicao(self):
        # nao deve haver coluna de projecao
        df = pd.DataFrame(
            {
                "VALOR": [1000.0],
                "CLASSIFICACAO": ["redigitada"],
                "RECUPERADA_OUTRO": [False],
            }
        )
        res = detalhe_reaproveitamento(df)
        assert "Projeção" not in res.columns

    def test_conta_valor_false_zera_valor(self):
        df = pd.DataFrame(
            {
                "VALOR": [1000.0],
                "CLASSIFICACAO": ["redigitada"],
                "conta_valor": [False],
            }
        )
        res = detalhe_reaproveitamento(df)
        salvos = res[res["Categoria"] == "Redigitada/Recuperada"].iloc[0]
        assert salvos["Quantidade"] == 1  # contagem preservada
        assert salvos["Valor"] == pytest.approx(0.0)  # valor zerado

    def test_df_vazio(self):
        res = detalhe_reaproveitamento(pd.DataFrame())
        assert res.empty
        assert list(res.columns) == self._COLS


# ──────────────────────────────────────────────────────────────────
# Quadro 4 — Medias
# ──────────────────────────────────────────────────────────────────


@pytest.fixture
def df_medias():
    return pd.DataFrame(
        {
            "grupo_dashboard": ["CNC", "CNC", "CNC", "SAQUE"],
            "REGIAO": ["R1", "R1", "R2", "R1"],
            "LOJA": ["A", "A", "B", "A"],
            "CONSULTOR": ["João", "Maria", "Pedro", "João"],
            "VALOR": [1000.0, 500.0, 600.0, 400.0],
            "conta_valor": [True, True, True, True],
        }
    )


@pytest.mark.unit
class TestDetalheMedias:
    _COLS = [
        "Produto", "Valor", "Qtd Base", "Média", "Média DU",
        "Projeção",
    ]

    def test_media_por_produto_base_consultor(self, df_medias):
        res = detalhe_medias_por_produto(
            df_medias, base="consultor", du_decorridos=10, du_totais=20
        )
        assert list(res.columns) == self._COLS
        cnc = res[res["Produto"] == "CNC"].iloc[0]
        # CNC: 2100 entre 3 consultores distintos (João, Maria, Pedro)
        assert cnc["Valor"] == pytest.approx(2100.0)
        assert cnc["Qtd Base"] == 3
        assert cnc["Média"] == pytest.approx(700.0)
        assert cnc["Média DU"] == pytest.approx(70.0)
        assert cnc["Projeção"] == pytest.approx(1400.0)

    def test_media_por_produto_base_loja(self, df_medias):
        res = detalhe_medias_por_produto(
            df_medias, base="loja", du_decorridos=10, du_totais=20
        )
        cnc = res[res["Produto"] == "CNC"].iloc[0]
        # CNC: 2100 entre 2 lojas distintas (A, B)
        assert cnc["Qtd Base"] == 2
        assert cnc["Média"] == pytest.approx(1050.0)
        assert cnc["Média DU"] == pytest.approx(105.0)
        assert cnc["Projeção"] == pytest.approx(2100.0)

    def test_base_consultor_exclui_supervisores(self, df_medias):
        df_sup = pd.DataFrame({"SUPERVISOR": ["Maria"]})
        res = detalhe_medias_por_produto(
            df_medias, base="consultor", du_decorridos=10, du_totais=20,
            df_supervisores=df_sup,
        )
        cnc = res[res["Produto"] == "CNC"].iloc[0]
        # Maria (supervisora) sai: valor 2100-500=1600, base 2 (João, Pedro)
        assert cnc["Valor"] == pytest.approx(1600.0)
        assert cnc["Qtd Base"] == 2
        assert cnc["Média"] == pytest.approx(800.0)
        assert cnc["Projeção"] == pytest.approx(1600.0)

    def test_media_por_regiao(self, df_medias):
        res = detalhe_medias_por_regiao(
            df_medias, base="consultor", du_decorridos=10, du_totais=20
        )
        assert list(res.columns) == [
            "REGIAO", "Valor", "Qtd Base", "Média", "Média DU", "Projeção",
        ]
        r1 = res[res["REGIAO"] == "R1"].iloc[0]
        # R1: João (1000+400) + Maria (500) = 1900, base distinta = 2
        assert r1["Valor"] == pytest.approx(1900.0)
        assert r1["Qtd Base"] == 2
        assert r1["Média"] == pytest.approx(950.0)
        assert r1["Média DU"] == pytest.approx(95.0)
        assert r1["Projeção"] == pytest.approx(1900.0)

    def test_media_por_loja(self, df_medias):
        res = detalhe_medias_por_regiao(
            df_medias, base="consultor", du_decorridos=10, du_totais=20,
            dimensao="LOJA",
        )
        assert list(res.columns) == [
            "LOJA", "Valor", "Qtd Base", "Média", "Média DU", "Projeção",
        ]
        a = res[res["LOJA"] == "A"].iloc[0]
        # A: João (1000+400) + Maria (500) = 1900, base distinta = 2
        assert a["Valor"] == pytest.approx(1900.0)
        assert a["Qtd Base"] == 2
        assert a["Média"] == pytest.approx(950.0)
        assert a["Média DU"] == pytest.approx(95.0)
        assert a["Projeção"] == pytest.approx(1900.0)

    def test_media_por_produto_desmembra_o_pack(self):
        # Paginas "Média por Consultor/Loja": quadro sem meta, PACK
        # desmembrado nos rotulos da planilha.
        df = pd.DataFrame(
            {
                "grupo_dashboard": ["PACK", "PACK", "PACK"],
                "categoria_codigo": ["FGTS", "ANT_BENEF", "CNC_13"],
                "CONSULTOR": ["João", "Maria", "João"],
                "LOJA": ["A", "A", "A"],
                "VALOR": [1000.0, 500.0, 300.0],
                "conta_valor": [True, True, True],
            }
        )
        res = detalhe_medias_por_produto(
            df, base="consultor", du_decorridos=10, du_totais=20
        )
        assert set(res["Produto"]) == {"FGTS", "ANT. DE BENEF.", "CNC 13º"}
        fgts = res[res["Produto"] == "FGTS"].iloc[0]
        assert fgts["Valor"] == pytest.approx(1000.0)
        assert fgts["Qtd Base"] == 1
        assert fgts["Média"] == pytest.approx(1000.0)

    def test_du_zero_media_du_zero(self, df_medias):
        res = detalhe_medias_por_produto(
            df_medias, base="loja", du_decorridos=0, du_totais=20
        )
        assert (res["Média DU"] == 0.0).all()
        assert (res["Projeção"] == 0.0).all()
        # Média (principal) ainda calcula
        assert (res["Média"] > 0).any()

    def test_df_vazio(self):
        res = detalhe_medias_por_produto(
            pd.DataFrame(), base="consultor", du_decorridos=10, du_totais=20
        )
        assert res.empty
        assert list(res.columns) == self._COLS


# ──────────────────────────────────────────────────────────────────
# Ultimo dia apurado (filtro)
# ──────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestFiltrarUltimoDia:
    def test_filtra_ultimo_dia_e_rotulo(self):
        df = pd.DataFrame(
            {
                "DATA_CADASTRO": [
                    "2026-06-20", "2026-06-25", "2026-06-25", "2026-06-24",
                ],
                "VALOR": [100.0, 200.0, 300.0, 400.0],
            }
        )
        out, rotulo = filtrar_ultimo_dia(df)
        assert rotulo == "25/06/2026"
        assert len(out) == 2
        assert sorted(out["VALOR"].tolist()) == [200.0, 300.0]

    def test_ignora_a_hora(self):
        df = pd.DataFrame(
            {
                "DATA_CADASTRO": ["2026-06-25 08:00", "2026-06-25 17:30"],
                "VALOR": [100.0, 200.0],
            }
        )
        out, rotulo = filtrar_ultimo_dia(df)
        assert rotulo == "25/06/2026"
        assert len(out) == 2

    def test_df_vazio(self):
        out, rotulo = filtrar_ultimo_dia(pd.DataFrame())
        assert out.empty
        assert rotulo == ""

    def test_sem_coluna_data_devolve_inalterado(self):
        df = pd.DataFrame({"VALOR": [100.0]})
        out, rotulo = filtrar_ultimo_dia(df)
        assert rotulo == ""
        assert len(out) == 1

    def test_todas_as_datas_nulas(self):
        df = pd.DataFrame(
            {"DATA_CADASTRO": [None, None], "VALOR": [1.0, 2.0]}
        )
        out, rotulo = filtrar_ultimo_dia(df)
        assert rotulo == ""
        assert out.empty


# ──────────────────────────────────────────────────────────────────
# Pivot de analise (Regiao × Produto/Banco com Totais)
# ──────────────────────────────────────────────────────────────────


@pytest.fixture
def df_pivot():
    return pd.DataFrame(
        {
            "REGIAO": ["NORTE", "NORTE", "SUL", "SUL"],
            "grupo_dashboard": ["CNC", "SAQUE", "CNC", "CNC"],
            "BANCO": ["BMG", "C6", "BMG", "HELP"],
            "VALOR": [1000.0, 500.0, 800.0, 200.0],
            "conta_valor": [True, True, True, True],
        }
    )


@pytest.fixture
def df_pivot_loja():
    return pd.DataFrame(
        {
            "REGIAO": ["NORTE", "NORTE", "SUL", "SUL"],
            "LOJA": ["L1", "L1", "L2", "L2"],
            "grupo_dashboard": ["CNC", "SAQUE", "CNC", "CNC"],
            "BANCO": ["BMG", "C6", "BMG", "HELP"],
            "VALOR": [1000.0, 500.0, 800.0, 200.0],
            "conta_valor": [True, True, True, True],
        }
    )


@pytest.mark.unit
class TestDetalheAnalisePivot:
    def test_pivot_regiao_produto_com_totais(self, df_pivot):
        res = detalhe_analise_pivot(df_pivot, "REGIAO", "grupo_dashboard")
        assert list(res.columns) == ["REGIAO", "CNC", "SAQUE", "Total"]
        assert list(res["REGIAO"]) == ["NORTE", "SUL", "Total"]

        norte = res[res["REGIAO"] == "NORTE"].iloc[0]
        assert norte["CNC"] == pytest.approx(1000.0)
        assert norte["SAQUE"] == pytest.approx(500.0)
        assert norte["Total"] == pytest.approx(1500.0)

        sul = res[res["REGIAO"] == "SUL"].iloc[0]
        assert sul["CNC"] == pytest.approx(1000.0)  # 800 + 200
        assert sul["SAQUE"] == pytest.approx(0.0)
        assert sul["Total"] == pytest.approx(1000.0)

        total = res[res["REGIAO"] == "Total"].iloc[0]
        assert total["CNC"] == pytest.approx(2000.0)
        assert total["SAQUE"] == pytest.approx(500.0)
        assert total["Total"] == pytest.approx(2500.0)

    def test_pivot_por_banco(self, df_pivot):
        res = detalhe_analise_pivot(df_pivot, "REGIAO", "BANCO")
        assert list(res.columns) == ["REGIAO", "BMG", "C6", "HELP", "Total"]
        total = res[res["REGIAO"] == "Total"].iloc[0]
        assert total["BMG"] == pytest.approx(1800.0)  # 1000 + 800
        assert total["C6"] == pytest.approx(500.0)
        assert total["HELP"] == pytest.approx(200.0)
        assert total["Total"] == pytest.approx(2500.0)

    def test_pivot_loja_produto_com_totais(self, df_pivot_loja):
        res = detalhe_analise_pivot(df_pivot_loja, "LOJA", "grupo_dashboard")
        assert list(res.columns) == ["LOJA", "CNC", "SAQUE", "Total"]
        assert list(res["LOJA"]) == ["L1", "L2", "Total"]

        l1 = res[res["LOJA"] == "L1"].iloc[0]
        assert l1["CNC"] == pytest.approx(1000.0)
        assert l1["SAQUE"] == pytest.approx(500.0)
        assert l1["Total"] == pytest.approx(1500.0)

    def test_conta_valor_false_zera_celula(self):
        df = pd.DataFrame(
            {
                "REGIAO": ["NORTE", "NORTE"],
                "grupo_dashboard": ["CNC", "EMISSAO"],
                "VALOR": [1000.0, 300.0],
                "conta_valor": [True, False],
            }
        )
        res = detalhe_analise_pivot(df, "REGIAO", "grupo_dashboard")
        norte = res[res["REGIAO"] == "NORTE"].iloc[0]
        assert norte["CNC"] == pytest.approx(1000.0)
        assert norte["EMISSAO"] == pytest.approx(0.0)
        assert norte["Total"] == pytest.approx(1000.0)

    def test_nulos_viram_outros(self):
        df = pd.DataFrame(
            {
                "REGIAO": ["NORTE", None],
                "grupo_dashboard": [None, "CNC"],
                "VALOR": [100.0, 200.0],
            }
        )
        res = detalhe_analise_pivot(df, "REGIAO", "grupo_dashboard")
        assert "OUTROS" in list(res["REGIAO"])
        assert "OUTROS" in list(res.columns)

    def test_df_vazio(self):
        res = detalhe_analise_pivot(
            pd.DataFrame(), "REGIAO", "grupo_dashboard"
        )
        assert res.empty
        assert list(res.columns) == ["REGIAO"]

    def test_coluna_ausente(self):
        df = pd.DataFrame({"REGIAO": ["NORTE"], "VALOR": [100.0]})
        res = detalhe_analise_pivot(df, "REGIAO", "BANCO")
        assert res.empty
        assert list(res.columns) == ["REGIAO"]


# ──────────────────────────────────────────────────────────────────
# Digitacao diaria — limite de ultimos N dias
# ──────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestDigitacaoUltimosDias:
    def test_limita_linhas_mas_projeta_mes_inteiro(self):
        df = pd.DataFrame(
            {
                "data_cadastro": [f"2026-06-{d:02d}" for d in range(1, 11)],
                "qtd_digitada": [10] * 10,
                "valor_digitado": [100.0] * 10,
            }
        )
        res = detalhe_digitacao_diaria(
            df, du_decorridos=10, du_totais=20, ultimos_dias=7
        )
        diarias = res[res["data_cadastro"] != "Projeção do mês"]
        # so as 7 ultimas linhas diarias permanecem
        assert len(diarias) == 7
        assert list(diarias["data_cadastro"])[0] == "04/06/2026"
        assert list(diarias["data_cadastro"])[-1] == "10/06/2026"
        # projecao usa o acumulado do MES INTEIRO (100), nao so os 7 dias
        proj = res.iloc[-1]
        assert proj["data_cadastro"] == "Projeção do mês"
        assert proj["qtd_digitada"] == 200  # 100 / 10 * 20
        assert proj["valor_digitado"] == pytest.approx(2000.0)

    def test_sem_param_mantem_todas_as_linhas(self, df_digitacao):
        res = detalhe_digitacao_diaria(
            df_digitacao, du_decorridos=3, du_totais=20
        )
        diarias = res[res["data_cadastro"] != "Projeção do mês"]
        assert len(diarias) == 3

    def test_base_variacao_valor(self, df_digitacao):
        # valores: 1000, 1500, 1200 → Var.% do VALOR: 0, +50%, -20%
        res = detalhe_digitacao_diaria(
            df_digitacao, du_decorridos=3, du_totais=20,
            base_variacao="valor",
        )
        diarias = res[res["data_cadastro"] != "Projeção do mês"]
        assert diarias.iloc[0]["Var. %"] == pytest.approx(0.0)
        assert diarias.iloc[1]["Var. %"] == pytest.approx(50.0)
        assert diarias.iloc[2]["Var. %"] == pytest.approx(-20.0)

    def test_sem_projecao_devolve_so_os_dias(self, df_digitacao):
        res = detalhe_digitacao_diaria(
            df_digitacao,
            du_decorridos=3,
            du_totais=20,
            incluir_projecao=False,
        )
        # nenhuma linha de projecao — so os 3 dias
        assert "Projeção do mês" not in list(res["data_cadastro"])
        assert len(res) == 3

    def test_sem_projecao_com_ultimos_dias(self):
        df = pd.DataFrame(
            {
                "data_cadastro": [f"2026-06-{d:02d}" for d in range(1, 11)],
                "qtd_digitada": [10] * 10,
                "valor_digitado": [100.0] * 10,
            }
        )
        res = detalhe_digitacao_diaria(
            df,
            du_decorridos=10,
            du_totais=20,
            ultimos_dias=7,
            incluir_projecao=False,
        )
        assert "Projeção do mês" not in list(res["data_cadastro"])
        assert len(res) == 7
        assert list(res["data_cadastro"])[0] == "04/06/2026"


# ──────────────────────────────────────────────────────────────────
# Pivot de cancelados (so liquidos)
# ──────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestDetalheCanceladosPivot:
    def test_pivot_so_liquidos(self):
        df = pd.DataFrame(
            {
                "REGIAO": ["NORTE", "NORTE", "SUL"],
                "grupo_dashboard": ["CNC", "SAQUE", "CNC"],
                "VALOR": [1000.0, 500.0, 800.0],
                "CLASSIFICACAO": ["liquido", "redigitada", "liquido"],
                "conta_valor": [True, True, True],
            }
        )
        res = detalhe_cancelados_pivot(df, "REGIAO", "grupo_dashboard")
        # a linha 'redigitada' (NORTE/SAQUE) sai → so a coluna CNC sobra
        assert list(res.columns) == ["REGIAO", "CNC", "Total"]
        norte = res[res["REGIAO"] == "NORTE"].iloc[0]
        assert norte["CNC"] == pytest.approx(1000.0)
        assert norte["Total"] == pytest.approx(1000.0)
        total = res[res["REGIAO"] == "Total"].iloc[0]
        assert total["CNC"] == pytest.approx(1800.0)

    def test_pivot_por_banco(self):
        df = pd.DataFrame(
            {
                "REGIAO": ["NORTE", "SUL"],
                "BANCO": ["BMG", "C6"],
                "VALOR": [1000.0, 800.0],
                "CLASSIFICACAO": ["liquido", "liquido"],
                "conta_valor": [True, True],
            }
        )
        res = detalhe_cancelados_pivot(df, "REGIAO", "BANCO")
        assert list(res.columns) == ["REGIAO", "BMG", "C6", "Total"]
        total = res[res["REGIAO"] == "Total"].iloc[0]
        assert total["Total"] == pytest.approx(1800.0)

    def test_df_vazio(self):
        res = detalhe_cancelados_pivot(
            pd.DataFrame(), "REGIAO", "grupo_dashboard"
        )
        assert res.empty

    def test_pivot_loja_so_liquidos(self):
        df = pd.DataFrame(
            {
                "LOJA": ["L1", "L1", "L2"],
                "grupo_dashboard": ["CNC", "SAQUE", "CNC"],
                "VALOR": [1000.0, 500.0, 800.0],
                "CLASSIFICACAO": ["liquido", "redigitada", "liquido"],
                "conta_valor": [True, True, True],
            }
        )
        res = detalhe_cancelados_pivot(df, "LOJA", "grupo_dashboard")
        assert list(res.columns) == ["LOJA", "CNC", "Total"]
        l1 = res[res["LOJA"] == "L1"].iloc[0]
        assert l1["CNC"] == pytest.approx(1000.0)
        assert l1["Total"] == pytest.approx(1000.0)


# ──────────────────────────────────────────────────────────────────
# Desmembramento do PACK (adicionar_produto_detalhado)
# ──────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestAdicionarProdutoDetalhado:
    def test_explode_pack_em_categorias_granulares(self):
        df = pd.DataFrame(
            {
                "grupo_dashboard": ["PACK", "PACK", "PACK", "CNC"],
                "categoria_codigo": ["FGTS", "ANT_BENEF", "CNC_13", "CNC"],
                "VALOR": [100.0, 200.0, 300.0, 400.0],
            }
        )
        out = adicionar_produto_detalhado(df)
        # Rotulos = nomes do tipo na planilha de origem (mesmos da coluna
        # "Produto"/TIPO_PRODUTO), padronizados em todo o app.
        assert out[COL_PRODUTO_DETALHADO].tolist() == [
            "FGTS", "ANT. DE BENEF.", "CNC 13º", "CNC",
        ]
        # nao muta a entrada
        assert "PRODUTO_DETALHADO" not in df.columns

    def test_nao_pack_mantem_grupo_dashboard(self):
        df = pd.DataFrame(
            {
                "grupo_dashboard": ["CNC", "SAQUE", "CONSIGNADO"],
                "categoria_codigo": ["CNC", "SAQUE", "CONSIG_BMG"],
                "VALOR": [1.0, 2.0, 3.0],
            }
        )
        out = adicionar_produto_detalhado(df)
        assert out[COL_PRODUTO_DETALHADO].tolist() == [
            "CNC", "SAQUE", "CONSIGNADO",
        ]

    def test_pack_ja_renomeado_sem_categoria_cai_no_label(self):
        # df_analise/df_cancelados passam por NOMES_DISPLAY_PRODUTO; se um
        # 'PACK' residual nao tiver categoria mapeada, mantem o label.
        df = pd.DataFrame(
            {
                "grupo_dashboard": [PACK_LABEL_AGREGADO, "CNC"],
                "categoria_codigo": ["", "CNC"],
                "VALOR": [10.0, 20.0],
            }
        )
        out = adicionar_produto_detalhado(df)
        assert out[COL_PRODUTO_DETALHADO].tolist() == [
            PACK_LABEL_AGREGADO, "CNC",
        ]

    def test_pack_cru_sem_categoria_usa_nomes_display(self):
        # Rede de seguranca: 'PACK' cru (digitacao detalhe pre-migration)
        # sem categoria_codigo cai no label amigavel via NOMES_DISPLAY.
        df = pd.DataFrame(
            {
                "grupo_dashboard": ["PACK"],
                "VALOR": [10.0],
            }
        )
        out = adicionar_produto_detalhado(df)
        assert out[COL_PRODUTO_DETALHADO].tolist() == [PACK_LABEL_AGREGADO]

    def test_sem_grupo_dashboard_inalterado(self):
        df = pd.DataFrame({"VALOR": [1.0]})
        out = adicionar_produto_detalhado(df)
        assert COL_PRODUTO_DETALHADO not in out.columns

    def test_df_vazio_inalterado(self):
        df = pd.DataFrame(columns=["grupo_dashboard", "categoria_codigo"])
        out = adicionar_produto_detalhado(df)
        assert out.empty

    def test_pivot_separa_colunas_do_pack(self):
        # Integracao: alimenta o pivot com a dimensao desmembrada.
        df = pd.DataFrame(
            {
                "REGIAO": ["R1", "R1", "R1", "R1"],
                "grupo_dashboard": ["PACK", "PACK", "PACK", "CNC"],
                "categoria_codigo": ["FGTS", "ANT_BENEF", "CNC_13", "CNC"],
                "VALOR": [100.0, 200.0, 300.0, 400.0],
                "conta_valor": [True, True, True, True],
            }
        )
        pivot = detalhe_analise_pivot(
            adicionar_produto_detalhado(df), "REGIAO", COL_PRODUTO_DETALHADO
        )
        # uma coluna por produto granular, sem 'PACK'
        assert "PACK" not in pivot.columns
        for col in ("FGTS", "ANT. DE BENEF.", "CNC 13º", "CNC"):
            assert col in pivot.columns
        r1 = pivot[pivot["REGIAO"] == "R1"].iloc[0]
        assert r1["FGTS"] == pytest.approx(100.0)
        assert r1["ANT. DE BENEF."] == pytest.approx(200.0)
        assert r1["CNC 13º"] == pytest.approx(300.0)
        assert r1["Total"] == pytest.approx(1000.0)


# ──────────────────────────────────────────────────────────────────
# Ocultar colunas de valor zeradas (ocultar_colunas_zeradas)
# ──────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestOcultarColunasZeradas:
    def test_remove_coluna_outros_zerada(self):
        pivot = pd.DataFrame(
            {
                "REGIAO": ["R1", "R2", "Total"],
                "CNC": [100.0, 200.0, 300.0],
                "OUTROS": [0.0, 0.0, 0.0],
                "Total": [100.0, 200.0, 300.0],
            }
        )
        out = ocultar_colunas_zeradas(pivot, "REGIAO")
        assert list(out.columns) == ["REGIAO", "CNC", "Total"]
        # totais por linha intactos
        assert out["Total"].tolist() == [100.0, 200.0, 300.0]

    def test_mantem_colunas_com_qualquer_valor(self):
        pivot = pd.DataFrame(
            {
                "REGIAO": ["R1", "Total"],
                "CNC": [0.0, 0.0],
                "SAQUE": [0.0, 0.0],
                "FGTS": [50.0, 50.0],
                "Total": [50.0, 50.0],
            }
        )
        out = ocultar_colunas_zeradas(pivot, "REGIAO")
        # CNC e SAQUE (todas-zero) saem; FGTS fica
        assert list(out.columns) == ["REGIAO", "FGTS", "Total"]

    def test_total_nunca_e_removido(self):
        # pivot degenerado: todas as colunas de valor zeradas
        pivot = pd.DataFrame(
            {
                "REGIAO": ["R1", "Total"],
                "OUTROS": [0.0, 0.0],
                "Total": [0.0, 0.0],
            }
        )
        out = ocultar_colunas_zeradas(pivot, "REGIAO")
        assert list(out.columns) == ["REGIAO", "Total"]

    def test_pivot_vazio_inalterado(self):
        pivot = pd.DataFrame(columns=["REGIAO"])
        out = ocultar_colunas_zeradas(pivot, "REGIAO")
        assert list(out.columns) == ["REGIAO"]

    def test_so_dimensao_inalterado(self):
        pivot = pd.DataFrame({"REGIAO": ["R1", "Total"]})
        out = ocultar_colunas_zeradas(pivot, "REGIAO")
        assert list(out.columns) == ["REGIAO"]
