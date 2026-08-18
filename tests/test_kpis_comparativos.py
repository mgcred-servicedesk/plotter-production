"""
Testes da comparação de período por entidade
(``src/dashboard/kpis/comparativos.py``).

``calcular_evolucao_por_entidade`` é função pura: agrega VALOR/DU por
LOJA ou CONSULTOR nos dois períodos e classifica cada entidade em
normal / nova / descontinuada. Usada pela tool ``comparar_entidades``
do chat de IA ("quais lojas cresceram", "quais consultores caíram").

Regras de negócio cobertas aqui:
- eixo consultor exclui supervisores e lojas de backoffice (Vai e Vem)
  nos DOIS períodos (``docs/agents/business-rules.md`` — "Exclusão de
  supervisores" e "Lojas de backoffice");
- cada período usa a lista de supervisores VIGENTE nele
  (``df_supervisores_ant``): quem foi promovido no intervalo continua
  contando no período em que ainda era consultor;
- eixo loja NÃO aplica essa exclusão (a loja segue no ranking de lojas;
  produção de supervisor soma no total da loja — "o eixo decide");
- sem base de comparação, ``% Evolução`` é nulo, nunca ``0``.
"""
import pandas as pd
import pytest

from src.dashboard.kpis.comparativos import calcular_evolucao_por_entidade


@pytest.fixture
def df_evo_atual():
    """Período atual (du_dec = 10).

    Por loja: A=200 (João 150 + Chefe 50), B=100, VAI E VEM=80, D=30.
    Por consultor (sem Chefe/Vai e Vem): João=150, Maria=100, Bruno=30.
    """
    return pd.DataFrame({
        "LOJA":      ["A", "A", "B", "VAI E VEM", "D"],
        "REGIAO":    ["R1", "R1", "R2", "ALEXANDRE", "R2"],
        "CONSULTOR": ["João", "Chefe", "Maria", "Amos", "Bruno"],
        "VALOR":     [1500.0, 500.0, 1000.0, 800.0, 300.0],
    })


@pytest.fixture
def df_evo_ant():
    """Período de comparação (du_dec = 10).

    Por loja: A=120 (João 100 + Chefe 20), B=200, VAI E VEM=40, C=50.
    Por consultor (sem Chefe/Vai e Vem): João=100, Maria=200, Ana=50.
    """
    return pd.DataFrame({
        "LOJA":      ["A", "A", "B", "VAI E VEM", "C"],
        "REGIAO":    ["R1", "R1", "R2", "ALEXANDRE", "R3"],
        "CONSULTOR": ["João", "Chefe", "Maria", "Amos", "Ana"],
        "VALOR":     [1000.0, 200.0, 2000.0, 400.0, 500.0],
    })


def _por_nome(res: pd.DataFrame, label: str) -> dict:
    return {r[label]: r for _, r in res.iterrows()}


@pytest.mark.unit
class TestEvolucaoPorLoja:
    def test_crescimento_e_queda(self, df_evo_atual, df_evo_ant):
        res = calcular_evolucao_por_entidade(
            df_evo_atual, 10, df_evo_ant, 10, entidade="LOJA",
        )
        by = _por_nome(res, "Loja")
        # A: 120 → 200 (média DU) = +66,67%
        assert by["A"]["Mês Anterior"] == pytest.approx(120.0)
        assert by["A"]["Mês Atual"] == pytest.approx(200.0)
        assert by["A"]["Variação Abs."] == pytest.approx(80.0)
        assert by["A"]["% Evolução"] == pytest.approx(80 / 120 * 100)
        assert by["A"]["Status"] == "normal"
        # B: 200 → 100 = -50%
        assert by["B"]["% Evolução"] == pytest.approx(-50.0)
        assert by["B"]["Variação Abs."] == pytest.approx(-100.0)

    def test_uniao_dos_dois_periodos(self, df_evo_atual, df_evo_ant):
        """Resultado usa a UNIÃO — C (só no anterior) e D (só no atual)."""
        res = calcular_evolucao_por_entidade(
            df_evo_atual, 10, df_evo_ant, 10, entidade="LOJA",
        )
        assert set(res["Loja"]) == {"A", "B", "C", "D", "VAI E VEM"}

    def test_nova_sem_percentual(self, df_evo_atual, df_evo_ant):
        res = calcular_evolucao_por_entidade(
            df_evo_atual, 10, df_evo_ant, 10, entidade="LOJA",
        )
        nova = _por_nome(res, "Loja")["D"]
        assert nova["Status"] == "nova"
        assert nova["Mês Anterior"] == pytest.approx(0.0)
        assert nova["Mês Atual"] == pytest.approx(30.0)
        # Nunca 0: "sem variação" e "sem base de comparação" são
        # respostas diferentes para o chat.
        assert pd.isna(nova["% Evolução"])

    def test_descontinuada_zera_mes_atual(self, df_evo_atual, df_evo_ant):
        res = calcular_evolucao_por_entidade(
            df_evo_atual, 10, df_evo_ant, 10, entidade="LOJA",
        )
        fora = _por_nome(res, "Loja")["C"]
        assert fora["Status"] == "descontinuada"
        assert fora["Mês Anterior"] == pytest.approx(50.0)
        assert fora["Mês Atual"] == pytest.approx(0.0)
        assert fora["Variação Abs."] == pytest.approx(-50.0)
        assert pd.isna(fora["% Evolução"])

    def test_backoffice_permanece_no_eixo_loja(self, df_evo_atual, df_evo_ant):
        """Vai e Vem é excluído só do eixo consultor (business-rules.md).

        Paridade com ``calcular_ranking_lojas``
        (``test_kpis_rankings.py::test_loja_backoffice_segue_no_ranking_de_lojas``).
        """
        res = calcular_evolucao_por_entidade(
            df_evo_atual, 10, df_evo_ant, 10, entidade="LOJA",
        )
        vv = _por_nome(res, "Loja")["VAI E VEM"]
        assert vv["Mês Anterior"] == pytest.approx(40.0)
        assert vv["Mês Atual"] == pytest.approx(80.0)
        assert vv["% Evolução"] == pytest.approx(100.0)

    def test_supervisor_soma_no_total_da_loja(
        self, df_evo_atual, df_evo_ant, sample_supervisores_df,
    ):
        """Eixo loja não exclui supervisor — passar df_supervisores não muda nada.

        "O eixo decide": agregou por loja, a produção do supervisor
        (Chefe) entra somada, igual ao card Aceleradores.
        """
        sem_sup = calcular_evolucao_por_entidade(
            df_evo_atual, 10, df_evo_ant, 10, entidade="LOJA",
        )
        com_sup = calcular_evolucao_por_entidade(
            df_evo_atual, 10, df_evo_ant, 10, entidade="LOJA",
            df_supervisores=sample_supervisores_df,
        )
        # A = João (1500) + Chefe (500) = 2000 / 10 du
        assert _por_nome(sem_sup, "Loja")["A"]["Mês Atual"] == pytest.approx(200.0)
        pd.testing.assert_frame_equal(sem_sup, com_sup)

    def test_entidades_excluir(self, df_evo_atual, df_evo_ant):
        res = calcular_evolucao_por_entidade(
            df_evo_atual, 10, df_evo_ant, 10, entidade="LOJA",
            entidades_excluir={"vai e vem ", "B"},
        )
        lojas = set(res["Loja"])
        assert "VAI E VEM" not in lojas  # match normalizado (strip+upper)
        assert "B" not in lojas
        assert "A" in lojas

    def test_valor_zerado_conta_como_descontinuada(self, df_evo_ant):
        """Loja que só emitiu (VALOR zerado na consolidação) some do atual.

        Mesmo critério VALOR > 0 dos rankings — sem zona cega entre
        "caiu a zero" e "só produziu emissão".
        """
        df_atual = pd.DataFrame({
            "LOJA": ["A", "C"],
            "CONSULTOR": ["João", "Ana"],
            "VALOR": [1000.0, 0.0],
        })
        res = calcular_evolucao_por_entidade(
            df_atual, 10, df_evo_ant, 10, entidade="LOJA",
        )
        assert _por_nome(res, "Loja")["C"]["Status"] == "descontinuada"


@pytest.mark.unit
class TestEvolucaoPorConsultor:
    def test_crescimento_e_queda(
        self, df_evo_atual, df_evo_ant, sample_supervisores_df,
    ):
        res = calcular_evolucao_por_entidade(
            df_evo_atual, 10, df_evo_ant, 10, entidade="CONSULTOR",
            df_supervisores=sample_supervisores_df,
        )
        by = _por_nome(res, "Consultor")
        # João: 100 → 150 = +50%
        assert by["João"]["% Evolução"] == pytest.approx(50.0)
        # Maria: 200 → 100 = -50%
        assert by["Maria"]["% Evolução"] == pytest.approx(-50.0)

    def test_exclui_supervisor_e_backoffice(
        self, df_evo_atual, df_evo_ant, sample_supervisores_df,
    ):
        res = calcular_evolucao_por_entidade(
            df_evo_atual, 10, df_evo_ant, 10, entidade="CONSULTOR",
            df_supervisores=sample_supervisores_df,
        )
        consultores = set(res["Consultor"])
        assert "Chefe" not in consultores  # supervisor
        assert "Amos" not in consultores   # loja de backoffice (Vai e Vem)
        assert consultores == {"João", "Maria", "Ana", "Bruno"}

    def test_exclusao_vale_para_o_periodo_anterior(
        self, df_evo_ant, sample_supervisores_df,
    ):
        """Excluídos não podem virar falsa "queda".

        Supervisor/Vai e Vem presentes só no período anterior sairiam
        como ``descontinuada`` se a exclusão fosse aplicada apenas ao
        período atual.
        """
        df_atual = pd.DataFrame({
            "LOJA": ["A"], "CONSULTOR": ["João"], "VALOR": [1500.0],
        })
        res = calcular_evolucao_por_entidade(
            df_atual, 10, df_evo_ant, 10, entidade="CONSULTOR",
            df_supervisores=sample_supervisores_df,
        )
        assert "Chefe" not in set(res["Consultor"])
        assert "Amos" not in set(res["Consultor"])
        assert set(res["Consultor"]) == {"João", "Maria", "Ana"}

    def test_nova_e_descontinuada(
        self, df_evo_atual, df_evo_ant, sample_supervisores_df,
    ):
        res = calcular_evolucao_por_entidade(
            df_evo_atual, 10, df_evo_ant, 10, entidade="CONSULTOR",
            df_supervisores=sample_supervisores_df,
        )
        by = _por_nome(res, "Consultor")
        assert by["Bruno"]["Status"] == "nova"
        assert by["Bruno"]["Mês Atual"] == pytest.approx(30.0)
        assert pd.isna(by["Bruno"]["% Evolução"])
        assert by["Ana"]["Status"] == "descontinuada"
        assert by["Ana"]["Mês Atual"] == pytest.approx(0.0)
        assert pd.isna(by["Ana"]["% Evolução"])

    def test_sem_df_supervisores_ninguem_e_excluido(
        self, df_evo_atual, df_evo_ant,
    ):
        """Sem cadastro de supervisores só o Vai e Vem é filtrado.

        ``excluir_supervisores`` devolve o frame intacto quando
        ``df_sup`` é None — o Chefe volta a ser um consultor comum.
        """
        res = calcular_evolucao_por_entidade(
            df_evo_atual, 10, df_evo_ant, 10, entidade="CONSULTOR",
        )
        consultores = set(res["Consultor"])
        assert "Chefe" in consultores
        assert "Amos" not in consultores


    def test_promovido_conta_no_periodo_em_que_era_consultor(
        self, df_evo_atual, df_evo_ant,
    ):
        """Promoção no intervalo não apaga o passado de consultor.

        João virou supervisor entre os dois períodos. Com a lista
        vigente de cada período, a produção dele no período anterior
        continua contando — ele sai como ``descontinuada``, não some.
        """
        res = calcular_evolucao_por_entidade(
            df_evo_atual, 10, df_evo_ant, 10, entidade="CONSULTOR",
            df_supervisores=pd.DataFrame({"SUPERVISOR": ["Chefe", "João"]}),
            df_supervisores_ant=pd.DataFrame({"SUPERVISOR": ["Chefe"]}),
        )
        by = _por_nome(res, "Consultor")
        assert "João" in by
        assert by["João"]["Status"] == "descontinuada"
        assert by["João"]["Mês Anterior"] == pytest.approx(100.0)
        assert by["João"]["Mês Atual"] == pytest.approx(0.0)

    def test_sem_lista_do_periodo_anterior_usa_a_atual(
        self, df_evo_atual, df_evo_ant,
    ):
        """Fallback: omitir ``df_supervisores_ant`` mantém o antigo.

        A lista atual vale para os dois períodos — o promovido some dos
        dois lados, apagando a produção que ele fez como consultor.
        Documenta o comportamento anterior a 2026-08-18, preservado para
        chamador que não tenha o cadastro do período de comparação.
        """
        res = calcular_evolucao_por_entidade(
            df_evo_atual, 10, df_evo_ant, 10, entidade="CONSULTOR",
            df_supervisores=pd.DataFrame({"SUPERVISOR": ["Chefe", "João"]}),
        )
        assert "João" not in set(res["Consultor"])

    def test_saida_da_supervisao_nao_devolve_o_passado(
        self, df_evo_atual, df_evo_ant,
    ):
        """Direção oposta: quem deixou a supervisão entra só no atual.

        O Chefe deixou de ser supervisor entre os dois períodos. Os
        meses em que ele supervisionava seguem excluídos (lista do
        período anterior), e a produção nova conta — ``nova``, não uma
        falsa alta contra base inflada.
        """
        res = calcular_evolucao_por_entidade(
            df_evo_atual, 10, df_evo_ant, 10, entidade="CONSULTOR",
            df_supervisores=pd.DataFrame({"SUPERVISOR": []}, dtype=object),
            df_supervisores_ant=pd.DataFrame({"SUPERVISOR": ["Chefe"]}),
        )
        by = _por_nome(res, "Consultor")
        assert by["Chefe"]["Status"] == "nova"
        assert by["Chefe"]["Mês Anterior"] == pytest.approx(0.0)
        assert by["Chefe"]["Mês Atual"] == pytest.approx(50.0)


@pytest.mark.unit
class TestGuardasEEdgeCases:
    def test_entidade_invalida_levanta_valueerror(
        self, df_evo_atual, df_evo_ant,
    ):
        with pytest.raises(ValueError):
            calcular_evolucao_por_entidade(
                df_evo_atual, 10, df_evo_ant, 10, entidade="REGIAO",
            )

    def test_entidade_none_levanta_valueerror(self, df_evo_atual):
        with pytest.raises(ValueError):
            calcular_evolucao_por_entidade(
                df_evo_atual, 10, None, 10, entidade=None,
            )

    def test_entidade_aceita_caixa_baixa(self, df_evo_atual, df_evo_ant):
        res = calcular_evolucao_por_entidade(
            df_evo_atual, 10, df_evo_ant, 10, entidade=" loja ",
        )
        assert "Loja" in res.columns

    def test_df_atual_vazio_e_ant_none(self):
        res = calcular_evolucao_por_entidade(
            pd.DataFrame(), 10, None, 10, entidade="LOJA",
        )
        assert res.empty

    def test_df_ant_none_mantem_periodo_atual(self, df_evo_atual):
        res = calcular_evolucao_por_entidade(
            df_evo_atual, 10, None, 10, entidade="LOJA",
        )
        assert set(res["Status"]) == {"nova"}
        assert res["% Evolução"].isna().all()

    def test_frame_sem_coluna_da_entidade(self, df_evo_ant):
        df = pd.DataFrame({"CONSULTOR": ["João"], "VALOR": [100.0]})
        # entidade=LOJA, mas o frame atual não tem LOJA → só o anterior
        # contribui; sem período anterior, resultado vazio.
        assert calcular_evolucao_por_entidade(
            df, 10, None, 10, entidade="LOJA",
        ).empty

    def test_frame_sem_coluna_valor(self):
        df = pd.DataFrame({"LOJA": ["A"], "CONSULTOR": ["João"]})
        assert calcular_evolucao_por_entidade(
            df, 10, df, 10, entidade="LOJA",
        ).empty

    def test_du_zero_nao_quebra(self, df_evo_atual, df_evo_ant):
        """du = 0 cai no ``max(du, 1)`` — valores viram total bruto."""
        res = calcular_evolucao_por_entidade(
            df_evo_atual, 0, df_evo_ant, 0, entidade="LOJA",
        )
        by = _por_nome(res, "Loja")
        assert by["A"]["Mês Atual"] == pytest.approx(2000.0)
        assert by["A"]["Mês Anterior"] == pytest.approx(1200.0)

    def test_du_zero_so_no_atual(self, df_evo_atual, df_evo_ant):
        res = calcular_evolucao_por_entidade(
            df_evo_atual, 0, df_evo_ant, 10, entidade="LOJA",
        )
        assert _por_nome(res, "Loja")["A"]["Mês Atual"] == pytest.approx(2000.0)

    def test_sem_producao_nos_dois_periodos(self):
        """Frames com só VALOR = 0 → nenhuma entidade comparável."""
        df = pd.DataFrame({"LOJA": ["A"], "VALOR": [0.0]})
        assert calcular_evolucao_por_entidade(
            df, 10, df, 10, entidade="LOJA",
        ).empty

    def test_excluir_todas_as_entidades(self, df_evo_atual, df_evo_ant):
        res = calcular_evolucao_por_entidade(
            df_evo_atual, 10, df_evo_ant, 10, entidade="LOJA",
            entidades_excluir={"A", "B", "C", "D", "VAI E VEM"},
        )
        assert res.empty

    def test_colunas_do_retorno(self, df_evo_atual, df_evo_ant):
        res = calcular_evolucao_por_entidade(
            df_evo_atual, 10, df_evo_ant, 10, entidade="LOJA",
        )
        assert list(res.columns) == [
            "Loja", "Mês Anterior", "Mês Atual",
            "Variação Abs.", "% Evolução", "Status",
        ]
        # Sem linha TOTAL (diferente de calcular_evolucao_media_du) e
        # sem universo de zerados (diferente de calcular_ranking_*).
        assert "TOTAL" not in set(res["Loja"])
