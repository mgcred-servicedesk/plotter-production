"""
Testes da produtividade individual por dia elegivel
(``src/dashboard/kpis/produtividade.py``).

Cobre a matriz minima do plano de 2026-08-31: consultor elegivel sem
pagamento, pagamento sem vinculo, transferencia no meio do mes,
supervisor na ancora, VAI E VEM, benchmark por razao das somas,
lacuna de competencia e base declarada em toda linha.
"""
import numpy as np
import pandas as pd
import pytest

from src.dashboard.kpis.produtividade import (
    COL_COMPETENCIA,
    COL_CONSULTOR,
    COL_DIAS,
    COL_IDX_CARTEIRA,
    COL_LOJA,
    COL_POS_LOJA,
    COL_PROD_DIA,
    COL_PRODUCAO,
    COL_REGIAO,
    COL_SHARE_LOJA,
    COL_SHARE_REGIAO,
    COL_SITUACAO,
    SIT_AUSENTE_ANTERIOR,
    SIT_CAIU,
    SIT_SAIU_DE_ZERO,
    SIT_SEM_DENOMINADOR,
    SIT_SUBIU,
    SIT_ZERADO_NOS_DOIS,
    benchmark_por,
    linhas_sem_vinculo,
    produtividade_carteira,
    produtividade_por_consultor,
    serie_por_consultor,
    variacao_ultima_competencia,
)


def _vinculos(linhas):
    """Frame no formato de ``carregar_vinculos_consultores``."""
    return pd.DataFrame(
        [
            {
                "CONSULTOR": c,
                "LOJA": lj,
                "REGIAO": rg,
                "REGIAO_ATUAL": rg,
                "DIAS_ELEGIVEIS": d,
                "DU_COMPETENCIA": 20,
                "BASE_DIAS": "ELIGIBLE_LINK_DAYS",
                "COBERTURA_AFASTAMENTO": "NONE",
            }
            for c, lj, rg, d in linhas
        ]
    )


def _producao(linhas):
    """Contratos pagos minimos: consultor, loja, regiao, valor."""
    return pd.DataFrame(
        [
            {"CONSULTOR": c, "LOJA": lj, "REGIAO": rg, "VALOR": v}
            for c, lj, rg, v in linhas
        ]
    )


@pytest.mark.unit
class TestProdutividadePorConsultor:
    def test_divide_producao_pelos_dias_de_vinculo(self):
        vin = _vinculos([("ANA", "LOJA A", "R1", 20)])
        df = _producao([("ANA", "LOJA A", "R1", 10000.0)])

        prod = produtividade_por_consultor(df, vin)

        linha = prod.iloc[0]
        assert linha[COL_DIAS] == 20
        assert linha[COL_PRODUCAO] == pytest.approx(10000.0)
        assert linha[COL_PROD_DIA] == pytest.approx(500.0)

    def test_meio_mes_nao_e_lido_como_metade_da_performance(self):
        """O ponto da metrica: quem teve 10 dias nao e pior por isso."""
        vin = _vinculos(
            [("ANA", "LOJA A", "R1", 20), ("BIA", "LOJA A", "R1", 10)]
        )
        df = _producao(
            [("ANA", "LOJA A", "R1", 10000.0),
             ("BIA", "LOJA A", "R1", 5000.0)]
        )

        prod = produtividade_por_consultor(df, vin).set_index(COL_CONSULTOR)

        # Metade da producao, metade dos dias: MESMA produtividade.
        assert prod.loc["ANA", COL_PROD_DIA] == pytest.approx(500.0)
        assert prod.loc["BIA", COL_PROD_DIA] == pytest.approx(500.0)
        # E, por isso, a MESMA fatia — apesar de BIA ter tido metade
        # dos dias. E o motivo de a fatia ser da taxa, nao do dinheiro:
        # pelo dinheiro BIA ficaria com 33,3% contra 66,7% de ANA.
        assert prod.loc["ANA", COL_SHARE_LOJA] == pytest.approx(50.0)
        assert prod.loc["BIA", COL_SHARE_LOJA] == pytest.approx(50.0)

    def test_elegivel_sem_pagamento_fica_na_tabela_com_zero(self):
        vin = _vinculos(
            [("ANA", "LOJA A", "R1", 20), ("BIA", "LOJA A", "R1", 20)]
        )
        df = _producao([("ANA", "LOJA A", "R1", 10000.0)])

        prod = produtividade_por_consultor(df, vin).set_index(COL_CONSULTOR)

        assert "BIA" in prod.index
        assert prod.loc["BIA", COL_PRODUCAO] == 0.0
        assert prod.loc["BIA", COL_PROD_DIA] == 0.0

    def test_esqueleto_nasce_do_vinculo_e_nao_da_producao(self):
        """Sem isso, a media da loja SOBE quando mais gente para de vender."""
        vin = _vinculos(
            [("ANA", "LOJA A", "R1", 20), ("BIA", "LOJA A", "R1", 20)]
        )
        df = _producao([("ANA", "LOJA A", "R1", 10000.0)])

        bench = benchmark_por(produtividade_por_consultor(df, vin), COL_LOJA)

        # 10.000 / 40 dias = 250, nao 500 (que seria ignorar a BIA).
        assert bench["LOJA A"] == pytest.approx(250.0)

    def test_pagamento_sem_vinculo_fica_ausente_nunca_zero(self):
        vin = _vinculos([("ANA", "LOJA A", "R1", 20)])
        df = _producao(
            [("ANA", "LOJA A", "R1", 10000.0),
             ("FANTASMA", "LOJA A", "R1", 3000.0)]
        )

        prod = produtividade_por_consultor(df, vin).set_index(COL_CONSULTOR)

        assert prod.loc["FANTASMA", COL_DIAS] == 0
        assert np.isnan(prod.loc["FANTASMA", COL_PROD_DIA])
        assert prod.loc["FANTASMA", COL_PRODUCAO] == pytest.approx(3000.0)

    def test_producao_sem_vinculo_nao_infla_benchmark_da_loja(self):
        vin = _vinculos([("ANA", "LOJA A", "R1", 20)])
        df = _producao(
            [("ANA", "LOJA A", "R1", 10000.0),
             ("FANTASMA", "LOJA A", "R1", 90000.0)]
        )

        prod = produtividade_por_consultor(df, vin)

        # A loja continua valendo 500/dia: producao sem denominador
        # sai dos DOIS lados da razao.
        assert benchmark_por(prod, COL_LOJA)["LOJA A"] == pytest.approx(500.0)
        assert list(linhas_sem_vinculo(prod)[COL_CONSULTOR]) == ["FANTASMA"]

    def test_transferencia_soma_dias_sem_duplicar(self):
        vin = _vinculos(
            [("ANA", "LOJA A", "R1", 8), ("ANA", "LOJA B", "R1", 12)]
        )
        df = _producao(
            [("ANA", "LOJA A", "R1", 4000.0),
             ("ANA", "LOJA B", "R1", 6000.0)]
        )

        prod = produtividade_por_consultor(df, vin)

        # Uma linha so, com o mes inteiro da pessoa.
        assert len(prod) == 1
        assert prod.iloc[0][COL_DIAS] == 20
        assert prod.iloc[0][COL_PRODUCAO] == pytest.approx(10000.0)
        # Identificada na loja de MAIOR permanencia.
        assert prod.iloc[0][COL_LOJA] == "LOJA B"

    def test_supervisor_sai_dos_dois_lados(self):
        vin = _vinculos([("ANA", "LOJA A", "R1", 20)])
        df = _producao(
            [("ANA", "LOJA A", "R1", 10000.0),
             ("CHEFE", "LOJA A", "R1", 50000.0)]
        )
        df_sup = pd.DataFrame(
            {"SUPERVISOR": ["CHEFE"], "LOJA": ["LOJA A"], "REGIAO": ["R1"]}
        )

        prod = produtividade_por_consultor(df, vin, df_sup)

        assert list(prod[COL_CONSULTOR]) == ["ANA"]
        assert prod.iloc[0][COL_PROD_DIA] == pytest.approx(500.0)

    def test_vai_e_vem_fora_do_numerador(self):
        vin = _vinculos([("ANA", "LOJA A", "R1", 20)])
        df = _producao(
            [("ANA", "LOJA A", "R1", 10000.0),
             ("ANA", "VAI E VEM", "R1", 7000.0)]
        )

        prod = produtividade_por_consultor(df, vin)

        assert prod.iloc[0][COL_PRODUCAO] == pytest.approx(10000.0)

    def test_nome_casa_por_normalizacao(self):
        vin = _vinculos([("ana  maria", "LOJA A", "R1", 20)])
        df = _producao([(" ANA MARIA ", "LOJA A", "R1", 10000.0)])

        prod = produtividade_por_consultor(df, vin)

        assert len(prod) == 1
        assert prod.iloc[0][COL_PROD_DIA] == pytest.approx(500.0)

    def test_sem_vinculos_tudo_vira_diagnostico(self):
        """Ledger vazio nao inventa denominador: vira furo declarado."""
        df = _producao([("ANA", "LOJA A", "R1", 10000.0)])

        prod = produtividade_por_consultor(df, pd.DataFrame())

        assert np.isnan(prod.iloc[0][COL_PROD_DIA])
        assert list(linhas_sem_vinculo(prod)[COL_CONSULTOR]) == ["ANA"]

    def test_sem_producao_mantem_o_time_zerado(self):
        vin = _vinculos([("ANA", "LOJA A", "R1", 20)])

        prod = produtividade_por_consultor(pd.DataFrame(), vin)

        assert len(prod) == 1
        assert prod.iloc[0][COL_PROD_DIA] == 0.0


@pytest.mark.unit
class TestBenchmark:
    def test_razao_das_somas_e_nao_media_das_medias(self):
        # 10.000/20 = 500 e 100/1 = 100. Media simples daria 300;
        # razao das somas da 10.100/21 = 480,95.
        vin = _vinculos(
            [("ANA", "LOJA A", "R1", 20), ("BIA", "LOJA A", "R1", 1)]
        )
        df = _producao(
            [("ANA", "LOJA A", "R1", 10000.0),
             ("BIA", "LOJA A", "R1", 100.0)]
        )

        bench = benchmark_por(produtividade_por_consultor(df, vin), COL_LOJA)

        assert bench["LOJA A"] == pytest.approx(10100.0 / 21.0)

    def test_fatia_da_loja_e_a_parte_da_taxa_somada(self):
        vin = _vinculos(
            [("ANA", "LOJA A", "R1", 10), ("BIA", "LOJA A", "R1", 10)]
        )
        df = _producao(
            [("ANA", "LOJA A", "R1", 6000.0),
             ("BIA", "LOJA A", "R1", 2000.0)]
        )

        prod = produtividade_por_consultor(df, vin).set_index(COL_CONSULTOR)

        # ANA 600/dia, BIA 200/dia: soma 800. Fatias 75% e 25%, que
        # somam 100%. Fatia justa numa loja de dois = 50%.
        assert prod.loc["ANA", COL_SHARE_LOJA] == pytest.approx(75.0)
        assert prod.loc["BIA", COL_SHARE_LOJA] == pytest.approx(25.0)

    def test_carteira_usa_razao_das_somas(self):
        vin = _vinculos(
            [("ANA", "LOJA A", "R1", 20), ("BIA", "LOJA B", "R1", 10)]
        )
        df = _producao(
            [("ANA", "LOJA A", "R1", 10000.0),
             ("BIA", "LOJA B", "R1", 2000.0)]
        )

        resumo = produtividade_carteira(produtividade_por_consultor(df, vin))

        assert resumo["dias"] == 30
        assert resumo["produtividade"] == pytest.approx(12000.0 / 30.0)
        assert resumo["colaboradores"] == 2
        assert resumo["sem_vinculo"] == 0

    def test_media_de_dias_por_colaborador(self):
        """O card do topo le a MEDIA, nao a soma de dias-colaborador."""
        vin = _vinculos(
            [("ANA", "LOJA A", "R1", 20), ("BIA", "LOJA B", "R1", 10)]
        )
        df = _producao([("ANA", "LOJA A", "R1", 10000.0)])

        resumo = produtividade_carteira(produtividade_por_consultor(df, vin))

        # 30 dias-colaborador / 2 pessoas — quem entrou no meio do mes
        # puxa a media para baixo do DU da competencia.
        assert resumo["dias_por_colaborador"] == pytest.approx(15.0)

    def test_media_de_dias_sem_ninguem_no_escopo(self):
        """Escopo vazio nao divide por zero."""
        resumo = produtividade_carteira(pd.DataFrame())

        assert resumo["dias_por_colaborador"] == 0.0

    def test_carteira_conta_quem_nao_vendeu(self):
        vin = _vinculos(
            [("ANA", "LOJA A", "R1", 20), ("BIA", "LOJA A", "R1", 20)]
        )
        df = _producao([("ANA", "LOJA A", "R1", 10000.0)])

        resumo = produtividade_carteira(produtividade_por_consultor(df, vin))

        assert resumo["sem_producao"] == 1
        assert resumo["colaboradores"] == 2



@pytest.mark.unit
class TestFatiaEComparacao:
    """As colunas percentuais respondem a duas perguntas distintas.

    FATIA (loja, regiao): soma 100% no grupo, neutro em ``100 / n``.
    COMPARACAO (carteira): neutro em 100%.
    """

    def test_fatias_somam_cem_por_cento_no_grupo(self):
        vin = _vinculos(
            [("ANA", "DOIS", "R1", 10), ("BIA", "DOIS", "R1", 20)]
            + [
                (nome, "QUATRO", "R1", 15)
                for nome in ("CLARA", "DUDA", "ELIS", "FLOR")
            ]
        )
        df = _producao(
            [("ANA", "DOIS", "R1", 4000.0),
             ("BIA", "DOIS", "R1", 3000.0),
             ("CLARA", "QUATRO", "R1", 9000.0),
             ("DUDA", "QUATRO", "R1", 1500.0)]
        )

        prod = produtividade_por_consultor(df, vin)

        por_loja = prod.groupby(COL_LOJA)[COL_SHARE_LOJA].sum()
        assert por_loja["DOIS"] == pytest.approx(100.0)
        assert por_loja["QUATRO"] == pytest.approx(100.0)
        assert (
            prod.groupby(COL_REGIAO)[COL_SHARE_REGIAO].sum()["R1"]
            == pytest.approx(100.0)
        )

    def test_fatia_nao_tem_teto_ligado_ao_tamanho_do_time(self):
        # Mesma situacao nas duas lojas: uma pessoa produz, as outras
        # nao. Quem produz leva a fatia INTEIRA nos dois casos — o
        # indice antigo travava em 200% numa loja e 400% na outra.
        vin = _vinculos(
            [("ANA", "DOIS", "R1", 10), ("BIA", "DOIS", "R1", 10)]
            + [
                (nome, "QUATRO", "R1", 10)
                for nome in ("CLARA", "DUDA", "ELIS", "FLOR")
            ]
        )
        df = _producao(
            [("ANA", "DOIS", "R1", 4000.0),
             ("CLARA", "QUATRO", "R1", 4000.0)]
        )

        prod = produtividade_por_consultor(df, vin).set_index(COL_CONSULTOR)

        assert prod.loc["ANA", COL_SHARE_LOJA] == pytest.approx(100.0)
        assert prod.loc["CLARA", COL_SHARE_LOJA] == pytest.approx(100.0)
        # E a comparacao com a carteira tambem nao muda com o tamanho.
        assert (
            prod.loc["ANA", COL_IDX_CARTEIRA]
            == pytest.approx(prod.loc["CLARA", COL_IDX_CARTEIRA])
        )

    def test_sozinho_na_loja_leva_a_fatia_inteira_e_isso_e_verdade(self):
        vin = _vinculos(
            [("ANA", "LOJA A", "R1", 10), ("BIA", "LOJA B", "R1", 10)]
        )
        df = _producao(
            [("ANA", "LOJA A", "R1", 100.0),
             ("BIA", "LOJA B", "R1", 90000.0)]
        )

        prod = produtividade_por_consultor(df, vin).set_index(COL_CONSULTOR)

        # 100% da propria loja e literalmente verdade para quem esta
        # sozinho — diferente do indice antigo, onde 100% significava
        # "na media de si mesmo" e nao dizia nada.
        assert prod.loc["ANA", COL_SHARE_LOJA] == pytest.approx(100.0)
        assert prod.loc["BIA", COL_SHARE_LOJA] == pytest.approx(100.0)
        # A comparacao com a carteira separa as duas.
        assert prod.loc["ANA", COL_IDX_CARTEIRA] < 1.0
        assert prod.loc["BIA", COL_IDX_CARTEIRA] > 190.0

    def test_fatia_e_da_taxa_nunca_do_dinheiro(self):
        """O caso ILUARA: mes parcial nao pode virar fatia pequena.

        Medido em 08/2026 na HELP CASCADURA — 5 dias uteis de 21 e o
        melhor R$/dia da loja. Pela fatia do dinheiro ela cairia para
        atras de quem ficou o mes inteiro.
        """
        vin = _vinculos(
            [("PARCIAL", "LOJA A", "R1", 5), ("INTEIRO", "LOJA A", "R1", 20)]
        )
        df = _producao(
            [("PARCIAL", "LOJA A", "R1", 10000.0),   # 2.000/dia
             ("INTEIRO", "LOJA A", "R1", 20000.0)]   # 1.000/dia
        )

        prod = produtividade_por_consultor(df, vin).set_index(COL_CONSULTOR)

        # Pela taxa: 2.000 de 3.000 somados = 66,7%.
        assert prod.loc["PARCIAL", COL_SHARE_LOJA] == pytest.approx(
            2000.0 / 3000.0 * 100.0
        )
        # Pelo dinheiro seria 10.000/30.000 = 33,3% — e ela apareceria
        # como a pior da loja tendo o melhor R$/dia.
        assert prod.loc["PARCIAL", COL_SHARE_LOJA] > 50.0
        assert prod.loc["PARCIAL", COL_POS_LOJA] == "1 de 2"

    def test_indice_da_carteira_usa_a_razao_das_somas_do_escopo(self):
        vin = _vinculos(
            [("ANA", "LOJA A", "R1", 20), ("BIA", "LOJA B", "R1", 10)]
        )
        df = _producao(
            [("ANA", "LOJA A", "R1", 10000.0),
             ("BIA", "LOJA B", "R1", 2000.0)]
        )

        prod = produtividade_por_consultor(df, vin).set_index(COL_CONSULTOR)

        # Carteira = 12.000/30 = 400/dia. ANA 500 (125%), BIA 200 (50%).
        assert prod.loc["ANA", COL_IDX_CARTEIRA] == pytest.approx(125.0)
        assert prod.loc["BIA", COL_IDX_CARTEIRA] == pytest.approx(50.0)

    def test_carteira_sem_venda_nenhuma_deixa_indice_ausente(self):
        vin = _vinculos(
            [("ANA", "LOJA A", "R1", 10), ("BIA", "LOJA A", "R1", 10)]
        )
        prod = produtividade_por_consultor(_producao([]), vin)

        # Sem denominador de rede o indice e ausente — nunca 0%, que
        # afirmaria posicao relativa que nao foi medida.
        assert prod[COL_IDX_CARTEIRA].isna().all()
        assert prod[COL_SHARE_LOJA].isna().all()

    def test_posicao_na_loja_nao_depende_do_tamanho(self):
        vin = _vinculos(
            [("ANA", "LOJA A", "R1", 10), ("BIA", "LOJA A", "R1", 10),
             ("CLARA", "LOJA A", "R1", 10)]
        )
        df = _producao(
            [("ANA", "LOJA A", "R1", 9000.0),
             ("BIA", "LOJA A", "R1", 5000.0),
             ("CLARA", "LOJA A", "R1", 1000.0)]
        )

        prod = produtividade_por_consultor(df, vin).set_index(COL_CONSULTOR)

        assert prod.loc["ANA", COL_POS_LOJA] == "1 de 3"
        assert prod.loc["BIA", COL_POS_LOJA] == "2 de 3"
        assert prod.loc["CLARA", COL_POS_LOJA] == "3 de 3"

    def test_empate_divide_a_posicao(self):
        vin = _vinculos(
            [("ANA", "LOJA A", "R1", 10), ("BIA", "LOJA A", "R1", 10),
             ("CLARA", "LOJA A", "R1", 10)]
        )
        df = _producao(
            [("ANA", "LOJA A", "R1", 5000.0),
             ("BIA", "LOJA A", "R1", 5000.0),
             ("CLARA", "LOJA A", "R1", 1000.0)]
        )

        prod = produtividade_por_consultor(df, vin).set_index(COL_CONSULTOR)

        assert prod.loc["ANA", COL_POS_LOJA] == "1 de 3"
        assert prod.loc["BIA", COL_POS_LOJA] == "1 de 3"
        assert prod.loc["CLARA", COL_POS_LOJA] == "3 de 3"

    def test_sem_dia_elegivel_nao_recebe_posicao(self):
        vin = _vinculos([("ANA", "LOJA A", "R1", 10)])
        df = _producao(
            [("ANA", "LOJA A", "R1", 5000.0),
             ("ZE", "LOJA A", "R1", 8000.0)]
        )

        prod = produtividade_por_consultor(df, vin).set_index(COL_CONSULTOR)

        # ZE produziu sem janela no ledger: sem denominador nao ha
        # produtividade, e portanto nao ha posicao a atribuir.
        assert prod.loc["ANA", COL_POS_LOJA] == "1 de 1"
        assert prod.loc["ZE", COL_POS_LOJA] == ""


@pytest.mark.unit
class TestSerieEVariacao:
    def _frames(self):
        vin = _vinculos([("ANA", "LOJA A", "R1", 20)])
        return {
            (2026, 6): produtividade_por_consultor(
                _producao([("ANA", "LOJA A", "R1", 8000.0)]), vin
            ),
            (2026, 7): produtividade_por_consultor(
                _producao([("ANA", "LOJA A", "R1", 10000.0)]), vin
            ),
        }

    def test_empilha_em_ordem_de_competencia(self):
        serie = serie_por_consultor(self._frames())

        assert list(serie[COL_COMPETENCIA]) == ["2026-06", "2026-07"]
        assert list(serie[COL_PROD_DIA]) == pytest.approx([400.0, 500.0])

    def test_competencia_ausente_e_lacuna_nao_zero(self):
        frames = self._frames()
        frames[(2026, 5)] = pd.DataFrame()

        serie = serie_por_consultor(frames)

        assert "2026-05" not in set(serie[COL_COMPETENCIA])

    def test_variacao_entre_as_duas_ultimas(self):
        var = variacao_ultima_competencia(serie_por_consultor(self._frames()))

        assert var.iloc[0]["Variacao %"] == pytest.approx(25.0)

    def test_quem_nao_aparece_no_mes_anterior_fica_sem_variacao(self):
        vin = _vinculos(
            [("ANA", "LOJA A", "R1", 20), ("NOVA", "LOJA A", "R1", 20)]
        )
        frames = {
            (2026, 6): produtividade_por_consultor(
                _producao([("ANA", "LOJA A", "R1", 8000.0)]),
                _vinculos([("ANA", "LOJA A", "R1", 20)]),
            ),
            (2026, 7): produtividade_por_consultor(
                _producao(
                    [("ANA", "LOJA A", "R1", 10000.0),
                     ("NOVA", "LOJA A", "R1", 4000.0)]
                ),
                vin,
            ),
        }

        var = variacao_ultima_competencia(
            serie_por_consultor(frames)
        ).set_index(COL_CONSULTOR)

        # Lacuna nao e queda de 100%: fica ausente.
        assert np.isnan(var.loc["NOVA", "Variacao %"])
        assert var.loc["ANA", "Variacao %"] == pytest.approx(25.0)

    def test_uma_competencia_so_nao_produz_variacao(self):
        frames = {(2026, 7): self._frames()[(2026, 7)]}
        assert variacao_ultima_competencia(
            serie_por_consultor(frames)
        ).empty


@pytest.mark.unit
class TestSituacaoDaVariacao:
    """Cada causa de ``Variacao %`` ausente tem nome proprio.

    Antes, as quatro viravam o mesmo ``NaN`` e a aba relatava todas
    como "nao aparecem nas duas competencias" — inclusive quem saiu de
    zero, que e a maior virada possivel.
    """

    def _frames(self, anterior, atual, nomes=("ANA",)):
        vin = _vinculos([(n, "LOJA A", "R1", 20) for n in nomes])
        return {
            (2026, 6): produtividade_por_consultor(_producao(anterior), vin),
            (2026, 7): produtividade_por_consultor(_producao(atual), vin),
        }

    def _situacao(self, frames, nome="ANA"):
        var = variacao_ultima_competencia(
            serie_por_consultor(frames)
        ).set_index(COL_CONSULTOR)
        return var.loc[nome, COL_SITUACAO]

    def test_saiu_de_zero_nao_e_ausencia(self):
        frames = self._frames(
            anterior=[],
            atual=[("ANA", "LOJA A", "R1", 10000.0)],
        )

        assert self._situacao(frames) == SIT_SAIU_DE_ZERO

    def test_zerado_nos_dois_meses(self):
        assert self._situacao(self._frames([], [])) == SIT_ZERADO_NOS_DOIS

    def test_ausente_no_anterior_continua_ausente(self):
        frames = {
            (2026, 6): produtividade_por_consultor(
                _producao([("ANA", "LOJA A", "R1", 8000.0)]),
                _vinculos([("ANA", "LOJA A", "R1", 20)]),
            ),
            (2026, 7): produtividade_por_consultor(
                _producao(
                    [("ANA", "LOJA A", "R1", 8000.0),
                     ("NOVA", "LOJA A", "R1", 4000.0)]
                ),
                _vinculos(
                    [("ANA", "LOJA A", "R1", 20),
                     ("NOVA", "LOJA A", "R1", 20)]
                ),
            ),
        }

        assert self._situacao(frames, "NOVA") == SIT_AUSENTE_ANTERIOR

    def test_sem_dia_elegivel_agora_nao_vira_ausencia(self):
        frames = {
            (2026, 6): produtividade_por_consultor(
                _producao([("ANA", "LOJA A", "R1", 8000.0)]),
                _vinculos([("ANA", "LOJA A", "R1", 20)]),
            ),
            # Em 07 a pessoa produziu mas sumiu do ledger: o furo esta
            # no cadastro, nao no desempenho dela.
            (2026, 7): produtividade_por_consultor(
                _producao([("ANA", "LOJA A", "R1", 9000.0)]),
                _vinculos([("OUTRA", "LOJA A", "R1", 20)]),
            ),
        }

        assert self._situacao(frames) == SIT_SEM_DENOMINADOR

    def test_subiu_e_caiu_seguem_pelo_sinal(self):
        subiu = self._frames(
            [("ANA", "LOJA A", "R1", 8000.0)],
            [("ANA", "LOJA A", "R1", 10000.0)],
        )
        caiu = self._frames(
            [("ANA", "LOJA A", "R1", 10000.0)],
            [("ANA", "LOJA A", "R1", 8000.0)],
        )

        assert self._situacao(subiu) == SIT_SUBIU
        assert self._situacao(caiu) == SIT_CAIU

    def test_queda_a_zero_e_queda_de_cem_por_cento_nao_lacuna(self):
        frames = self._frames(
            [("ANA", "LOJA A", "R1", 8000.0)],
            [],
        )
        var = variacao_ultima_competencia(
            serie_por_consultor(frames)
        ).set_index(COL_CONSULTOR)

        assert var.loc["ANA", "Variacao %"] == pytest.approx(-100.0)
        assert var.loc["ANA", COL_SITUACAO] == SIT_CAIU
