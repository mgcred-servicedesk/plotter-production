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
    COL_IDX_LOJA,
    COL_LOJA,
    COL_PROD_DIA,
    COL_PRODUCAO,
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
        assert prod.loc["BIA", COL_IDX_LOJA] == pytest.approx(100.0)

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

    def test_indice_compara_com_a_propria_loja(self):
        vin = _vinculos(
            [("ANA", "LOJA A", "R1", 10), ("BIA", "LOJA A", "R1", 10)]
        )
        df = _producao(
            [("ANA", "LOJA A", "R1", 6000.0),
             ("BIA", "LOJA A", "R1", 2000.0)]
        )

        prod = produtividade_por_consultor(df, vin).set_index(COL_CONSULTOR)

        # Loja = 8.000/20 = 400/dia. ANA 600 (150%), BIA 200 (50%).
        assert prod.loc["ANA", COL_IDX_LOJA] == pytest.approx(150.0)
        assert prod.loc["BIA", COL_IDX_LOJA] == pytest.approx(50.0)

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
