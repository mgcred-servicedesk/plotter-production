"""
Testes dos KPIs gerais e helpers compartilhados
(``src/dashboard/kpis/gerais.py``).

Inclui os helpers ``excluir_supervisores`` / ``contar_consultores``,
reusados pelos demais módulos KPI. ``calcular_kpis_gerais`` depende de
``calcular_dias_uteis`` → usa a fixture ``sem_feriados``.

``TestObterKpisPeriodo`` cobre a composição + cache manual de
``obter_kpis_periodo`` (miss/hit/invalidação por escopo — a fronteira de
RLS entre perfis); a correção interna de cada ``calcular_*`` já está
coberta pelas classes acima, não é reexercitada ali.
"""
from datetime import datetime, timedelta

import pandas as pd
import pytest

from src.dashboard.kpis import gerais as kpis_gerais_module
from src.dashboard.kpis.gerais import (
    JANELA_PIPELINE_DIAS,
    KpisPeriodo,
    _chave_kpis,
    calcular_assertividade_consultores,
    calcular_kpis_analise,
    calcular_kpis_cancelados,
    calcular_kpis_gerais,
    calcular_kpis_qtd_produtos,
    calcular_medias_du_por_nivel,
    calcular_medias_organizacao,
    calcular_metas_produto_diarias,
    calcular_oportunidades_perdidas,
    contar_consultores,
    excluir_supervisores,
    filtrar_janela_recente,
    limpar_cache_kpis,
    obter_kpis_periodo,
    separar_cancelados_liquidos,
)
from src.shared.dias_uteis import calcular_dias_uteis


@pytest.mark.unit
class TestHelpers:
    def test_excluir_supervisores_remove_listados(self, sample_pagos_produto_df):
        sup = pd.DataFrame({"SUPERVISOR": ["João"]})
        out = excluir_supervisores(sample_pagos_produto_df, sup)
        assert "João" not in out["CONSULTOR"].values
        assert len(out) == 3

    def test_excluir_supervisores_sem_df_sup_retorna_copia(
        self, sample_pagos_produto_df
    ):
        out = excluir_supervisores(sample_pagos_produto_df, None)
        assert len(out) == len(sample_pagos_produto_df)
        assert out is not sample_pagos_produto_df  # cópia

    def test_contar_consultores(self, sample_pagos_produto_df):
        assert contar_consultores(sample_pagos_produto_df, None) == 4

    def test_contar_consultores_exclui_supervisores(self, sample_pagos_produto_df):
        sup = pd.DataFrame({"SUPERVISOR": ["João", "Maria"]})
        assert contar_consultores(sample_pagos_produto_df, sup) == 2

    def test_contar_consultores_sem_coluna(self):
        assert contar_consultores(pd.DataFrame({"VALOR": [1]}), None) == 0


@pytest.mark.unit
class TestFiltrarJanelaRecente:
    """``DATA_CADASTRO`` chega ja como datetime do loader (``pd.to_datetime``
    com ``errors='coerce'``) — a funcao NAO reconverte, entao os testes usam
    objetos ``datetime`` reais na coluna (nao strings)."""

    _REF = datetime(2026, 6, 30, 12, 0, 0)

    def test_mantem_linhas_dentro_da_janela(self):
        df = pd.DataFrame({
            "DATA_CADASTRO": [self._REF, self._REF - timedelta(days=15)],
            "VALOR": [100.0, 200.0],
        })
        out = filtrar_janela_recente(df, referencia=self._REF)
        assert len(out) == 2

    def test_borda_referencia_menos_30_dias_e_inclusiva(self):
        borda = self._REF - timedelta(days=JANELA_PIPELINE_DIAS)
        df = pd.DataFrame({
            "DATA_CADASTRO": [borda],
            "VALOR": [100.0],
        })
        out = filtrar_janela_recente(df, referencia=self._REF)
        # corte = referencia - dias, comparacao >= : a borda exata fica
        assert len(out) == 1

    def test_exclui_fora_da_janela(self):
        fora = self._REF - timedelta(days=JANELA_PIPELINE_DIAS + 1)
        df = pd.DataFrame({
            "DATA_CADASTRO": [fora],
            "VALOR": [100.0],
        })
        out = filtrar_janela_recente(df, referencia=self._REF)
        assert out.empty

    def test_data_nula_e_excluida(self):
        df = pd.DataFrame({
            "DATA_CADASTRO": [pd.NaT, self._REF],
            "VALOR": [100.0, 200.0],
        })
        out = filtrar_janela_recente(df, referencia=self._REF)
        # NaT >= corte e sempre False -> linha nula nunca entra na janela
        assert len(out) == 1
        assert out["VALOR"].tolist() == [200.0]

    def test_parametro_dias_customizado_sobrepoe_default(self):
        df = pd.DataFrame({
            "DATA_CADASTRO": [self._REF - timedelta(days=10)],
            "VALOR": [100.0],
        })
        out = filtrar_janela_recente(df, dias=7, referencia=self._REF)
        assert out.empty

    def test_sem_referencia_usa_now(self):
        df = pd.DataFrame({
            "DATA_CADASTRO": [datetime.now()],
            "VALOR": [100.0],
        })
        out = filtrar_janela_recente(df)  # referencia default -> now()
        assert len(out) == 1

    def test_df_vazio_devolve_copia(self):
        df = pd.DataFrame(columns=["DATA_CADASTRO", "VALOR"])
        out = filtrar_janela_recente(df, referencia=self._REF)
        assert out.empty
        assert out is not df

    def test_sem_coluna_data_cadastro_devolve_copia(self):
        df = pd.DataFrame({"VALOR": [100.0]})
        out = filtrar_janela_recente(df, referencia=self._REF)
        assert out["VALOR"].tolist() == [100.0]
        assert out is not df


@pytest.fixture
def df_pagos_gerais():
    return pd.DataFrame({
        "LOJA": ["A", "A", "B"],
        "REGIAO": ["R1", "R1", "R2"],
        "CONSULTOR": ["João", "Maria", "Pedro"],
        "VALOR": [1000.0, 500.0, 0.0],
        "pontos": [100.0, 50.0, 0.0],
    })


@pytest.mark.unit
class TestCalcularKpisGerais:
    def test_totais_metas_e_contagens(self, df_pagos_gerais, sem_feriados):
        df_metas = pd.DataFrame({"META_PRATA": [10000.0], "META_OURO": [20000.0]})
        df_metas_produto = pd.DataFrame({"MIX": [5000.0]})
        r = calcular_kpis_gerais(
            df_pagos_gerais, df_metas, df_metas_produto,
            ano=2026, mes=3, dia_atual=16,
        )
        assert r["total_vendas"] == pytest.approx(1500.0)
        assert r["total_pontos"] == pytest.approx(150.0)
        assert r["total_transacoes"] == 2  # VALOR > 0
        assert r["meta_prata"] == pytest.approx(10000.0)
        assert r["meta_ouro"] == pytest.approx(20000.0)
        assert r["meta_mix"] == pytest.approx(5000.0)
        assert r["perc_ating_prata"] == pytest.approx(1.5)
        assert r["ticket_medio"] == pytest.approx(750.0)
        assert r["num_lojas"] == 2
        assert r["num_consultores"] == 3
        assert r["num_regioes"] == 2

    def test_meta_mix_soma_componentes_sem_coluna_mix(
        self, df_pagos_gerais, sem_feriados
    ):
        df_metas = pd.DataFrame({"META_PRATA": [0.0]})
        # Sem coluna "MIX" → soma os componentes canônicos
        df_metas_produto = pd.DataFrame({
            "CNC": [100.0], "CLT": [200.0], "SAQUE": [300.0],
            "CONSIGNADO": [400.0], "FGTS_ANT_BENEF_13": [500.0],
        })
        r = calcular_kpis_gerais(
            df_pagos_gerais, df_metas, df_metas_produto,
            ano=2026, mes=3, dia_atual=16,
        )
        assert r["meta_mix"] == pytest.approx(1500.0)

    def test_derivados_de_dias_uteis(self, df_pagos_gerais, sem_feriados):
        du_total, du_dec, _ = calcular_dias_uteis(2026, 3, 16)
        df_metas = pd.DataFrame({"META_PRATA": [10000.0]})
        r = calcular_kpis_gerais(
            df_pagos_gerais, df_metas, pd.DataFrame(),
            ano=2026, mes=3, dia_atual=16,
        )
        assert r["media_du"] == pytest.approx(1500 / du_dec)
        assert r["media_du_pontos"] == pytest.approx(150 / du_dec)
        assert r["meta_diaria_pts"] == pytest.approx(10000 / du_total)
        assert r["meta_diaria"] == r["meta_diaria_pts"]  # alias

    def test_metas_ausentes_nao_quebram(self, df_pagos_gerais, sem_feriados):
        r = calcular_kpis_gerais(
            df_pagos_gerais, pd.DataFrame(), pd.DataFrame(),
            ano=2026, mes=3, dia_atual=16,
        )
        assert r["meta_prata"] == 0
        assert r["perc_ating_prata"] == 0
        assert r["meta_mix"] == 0

    def test_exclui_supervisores_na_contagem(self, df_pagos_gerais, sem_feriados):
        sup = pd.DataFrame({"SUPERVISOR": ["João"]})
        r = calcular_kpis_gerais(
            df_pagos_gerais, pd.DataFrame(), pd.DataFrame(),
            ano=2026, mes=3, dia_atual=16, df_supervisores=sup,
        )
        assert r["num_consultores"] == 2  # João removido


@pytest.mark.unit
class TestCalcularKpisAnalise:
    def test_vazio(self):
        df = pd.DataFrame({"VALOR": [100.0]})
        r = calcular_kpis_analise(pd.DataFrame(), df, 10)
        assert r == {
            "valor_analise": 0, "qtd_analise": 0, "ticket_medio_analise": 0,
            "media_diaria_analise": 0, "variacao_analise": 0,
        }

    def test_calculo(self):
        df_analise = pd.DataFrame({"VALOR": [1000.0, 500.0]})
        df = pd.DataFrame({"VALOR": [2000.0]})
        r = calcular_kpis_analise(df_analise, df, du_decorridos=10)
        assert r["valor_analise"] == pytest.approx(1500.0)
        assert r["qtd_analise"] == 2
        assert r["ticket_medio_analise"] == pytest.approx(750.0)
        assert r["media_diaria_analise"] == pytest.approx(150.0)
        # total digitado = 2000 + 1500 = 3500 → média 350; 150/350 = 42.857%
        assert r["variacao_analise"] == pytest.approx(150 / 350 * 100)


@pytest.mark.unit
class TestSepararCanceladosLiquidos:
    def test_sem_coluna_classificacao(self):
        # Retrocompat: sem CLASSIFICACAO, tudo é liquido.
        df = pd.DataFrame({"VALOR": [1.0, 2.0]})
        liq, n_redig, n_recup = separar_cancelados_liquidos(df)
        assert len(liq) == 2
        assert n_redig == 0
        assert n_recup == 0

    def test_com_classificacao(self):
        df = pd.DataFrame({
            "VALOR": [1.0, 2.0, 3.0, 4.0],
            "CLASSIFICACAO": [
                "liquido", "redigitada", "recuperada", "liquido",
            ],
        })
        liq, n_redig, n_recup = separar_cancelados_liquidos(df)
        assert len(liq) == 2
        assert n_redig == 1
        assert n_recup == 1


@pytest.mark.unit
class TestCalcularKpisCancelados:
    def test_vazio(self):
        r = calcular_kpis_cancelados(pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
        assert r == {
            "valor_cancelados": 0,
            "qtd_cancelados": 0,
            "indice_perda": 0,
            "qtd_bruto": 0,
            "qtd_redigitadas": 0,
            "qtd_recuperadas": 0,
        }

    def test_indice_perda(self):
        df_canc = pd.DataFrame({"VALOR": [500.0]})
        df = pd.DataFrame({"VALOR": [100.0, 200.0]})  # 2 pagos
        df_analise = pd.DataFrame({"VALOR": [300.0]})  # 1 análise
        r = calcular_kpis_cancelados(df_canc, df, df_analise)
        assert r["valor_cancelados"] == pytest.approx(500.0)
        assert r["qtd_cancelados"] == 1
        # 1 / (2 + 1 + 1) = 25%
        assert r["indice_perda"] == pytest.approx(25.0)
        # Sem CLASSIFICACAO: bruto = liquido, sem contexto.
        assert r["qtd_bruto"] == 1
        assert r["qtd_redigitadas"] == 0
        assert r["qtd_recuperadas"] == 0

    def test_liquido_exclui_redigitada_e_recuperada(self):
        df_canc = pd.DataFrame({
            "VALOR": [500.0, 300.0, 200.0, 100.0],
            "CLASSIFICACAO": [
                "liquido", "redigitada", "recuperada", "liquido",
            ],
        })
        df = pd.DataFrame({"VALOR": [100.0, 200.0]})  # 2 pagos
        df_analise = pd.DataFrame({"VALOR": [300.0]})  # 1 análise
        r = calcular_kpis_cancelados(df_canc, df, df_analise)
        # Só os 2 liquidos contam (500 + 100).
        assert r["valor_cancelados"] == pytest.approx(600.0)
        assert r["qtd_cancelados"] == 2
        assert r["qtd_bruto"] == 4
        assert r["qtd_redigitadas"] == 1
        assert r["qtd_recuperadas"] == 1
        # churn = 2 / (2 + 2 + 1) = 40%
        assert r["indice_perda"] == pytest.approx(40.0)


@pytest.mark.unit
class TestCalcularAssertividadeConsultores:
    def test_vazio(self):
        r = calcular_assertividade_consultores(
            pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        )
        assert r["assertividade_org"] == 100.0
        assert r["total_redigitadas"] == 0
        assert r["por_consultor"].empty

    def test_por_consultor(self):
        # Pagas: A=2, B=1
        df = pd.DataFrame({
            "CONSULTOR": ["A", "A", "B"],
            "VALOR": [1.0, 1.0, 1.0],
        })
        # Em análise: A=1
        df_analise = pd.DataFrame({"CONSULTOR": ["A"], "VALOR": [1.0]})
        # Canceladas (bruto): A=2 (1 redigitada), B=1
        df_canc = pd.DataFrame({
            "CONSULTOR": ["A", "A", "B"],
            "VALOR": [1.0, 1.0, 1.0],
            "CLASSIFICACAO": ["redigitada", "liquido", "liquido"],
        })
        r = calcular_assertividade_consultores(df_canc, df, df_analise)
        por = r["por_consultor"].set_index("CONSULTOR")
        # A: total = 2 + 1 + 2 = 5; redig = 1 → 80%
        assert por.loc["A", "total_propostas"] == 5
        assert por.loc["A", "redigitadas"] == 1
        assert por.loc["A", "assertividade"] == pytest.approx(80.0)
        # B: total = 1 + 0 + 1 = 2; redig = 0 → 100%
        assert por.loc["B", "total_propostas"] == 2
        assert por.loc["B", "assertividade"] == pytest.approx(100.0)
        # Org: total = 7, redig = 1
        assert r["total_propostas"] == 7
        assert r["total_redigitadas"] == 1
        assert r["assertividade_org"] == pytest.approx((1 - 1 / 7) * 100)


@pytest.mark.unit
class TestCalcularOportunidadesPerdidas:
    def test_vazio(self):
        r = calcular_oportunidades_perdidas(pd.DataFrame())
        assert r == {"qtd_perdidas": 0, "valor_perdido": 0.0}

    def test_sem_coluna_retorna_zero(self):
        df = pd.DataFrame({"VALOR": [1000.0]})
        r = calcular_oportunidades_perdidas(df)
        assert r == {"qtd_perdidas": 0, "valor_perdido": 0.0}

    def test_conta_apenas_recuperada_outro(self):
        df = pd.DataFrame({
            "VALOR": [1000.0, 500.0, 300.0],
            "RECUPERADA_OUTRO": [True, False, True],
        })
        r = calcular_oportunidades_perdidas(df)
        assert r["qtd_perdidas"] == 2
        assert r["valor_perdido"] == pytest.approx(1300.0)

    def test_coluna_flag_por_nivel(self):
        # Supervisor/gerente usam colunas de loja/regiao.
        df = pd.DataFrame({
            "VALOR": [100.0, 200.0, 400.0],
            "RECUPERADA_OUTRA_LOJA": [True, False, True],
        })
        r = calcular_oportunidades_perdidas(df, "RECUPERADA_OUTRA_LOJA")
        assert r["qtd_perdidas"] == 2
        assert r["valor_perdido"] == pytest.approx(500.0)


@pytest.mark.unit
class TestCalcularMediasDuPorNivel:
    def test_medias(self):
        df = pd.DataFrame({
            "LOJA": ["A", "A", "B"],
            "CONSULTOR": ["João", "Maria", "Pedro"],
            "VALOR": [1000.0, 500.0, 600.0],
        })
        r = calcular_medias_du_por_nivel(df, du_decorridos=10)
        # lojas: A=1500, B=600 → média 1050 → /10 = 105
        assert r["num_lojas"] == 2
        assert r["media_du_loja"] == pytest.approx(105.0)
        # consultores: 1000,500,600 → média 700 → /10 = 70
        assert r["num_consultores"] == 3
        assert r["media_du_consultor"] == pytest.approx(70.0)

    def test_exclui_supervisores(self):
        df = pd.DataFrame({
            "LOJA": ["A", "A"],
            "CONSULTOR": ["João", "Maria"],
            "VALOR": [1000.0, 500.0],
        })
        sup = pd.DataFrame({"SUPERVISOR": ["João"]})
        r = calcular_medias_du_por_nivel(df, 10, df_supervisores=sup)
        assert r["num_consultores"] == 1

    def test_exclui_loja_backoffice(self):
        # Vai e Vem (backoffice) não entra na média por loja nem na
        # média por consultor.
        df = pd.DataFrame({
            "LOJA": ["A", "VAI E VEM"],
            "CONSULTOR": ["João", "Amos"],
            "VALOR": [1000.0, 500.0],
        })
        r = calcular_medias_du_por_nivel(df, du_decorridos=10)
        assert r["num_lojas"] == 1
        assert r["media_du_loja"] == pytest.approx(100.0)
        assert r["num_consultores"] == 1
        assert r["media_du_consultor"] == pytest.approx(100.0)


@pytest.mark.unit
class TestCalcularMediasOrganizacao:
    def _df(self):
        return pd.DataFrame({
            "REGIAO": ["R1", "R2", "ALEXANDRE"],
            "LOJA": ["A", "B", "C"],
            "CONSULTOR": ["João", "Maria", "Pedro"],
            "categoria_codigo": ["CNC", "CNC", "CNC"],
            "VALOR": [1000.0, 2000.0, 9999.0],
        })

    def test_perfil_none_retorna_vazio(self):
        assert calcular_medias_organizacao(self._df(), 1, perfil=None) == {}

    def test_perfil_desconhecido_retorna_vazio(self):
        assert calcular_medias_organizacao(self._df(), 1, perfil="diretor") == {}

    def test_du_zero_retorna_vazio(self):
        assert calcular_medias_organizacao(
            self._df(), 0, perfil="gerente_comercial"
        ) == {}

    def test_gerente_exclui_regiao_alexandre(self):
        medias = calcular_medias_organizacao(
            self._df(), du_decorridos=1, perfil="gerente_comercial"
        )
        # R1=1000, R2=2000 (ALEXANDRE fora) → média 1500
        assert medias["CNC"] == pytest.approx(1500.0)

    def test_consultor_exclui_supervisores(self):
        sup = pd.DataFrame({"SUPERVISOR": ["Pedro"]})
        medias = calcular_medias_organizacao(
            self._df(), du_decorridos=1, perfil="consultor", df_sup=sup,
        )
        # João=1000, Maria=2000 (Pedro removido) → média 1500
        assert medias["CNC"] == pytest.approx(1500.0)

    def test_supervisor_agrupa_por_loja(self):
        # Sem exclusão de região → A=1000, B=2000, C=9999 → média 4333
        medias = calcular_medias_organizacao(
            self._df(), du_decorridos=1, perfil="supervisor",
        )
        assert medias["CNC"] == pytest.approx((1000 + 2000 + 9999) / 3)


@pytest.mark.unit
class TestCalcularMetasProdutoDiarias:
    def test_valores_e_metas_por_produto(self):
        df = pd.DataFrame({
            "LOJA": ["A", "A"],
            "categoria_codigo": ["CNC", "SAQUE"],
            "VALOR": [1000.0, 500.0],
        })
        df_metas_produto = pd.DataFrame({
            "LOJA": ["A"], "CNC": [3000.0], "SAQUE": [2000.0],
        })
        res = calcular_metas_produto_diarias(
            df, df_metas_produto, du_total=20, du_decorridos=10,
        )
        by = {r["produto"]: r for r in res}
        cnc = by["CNC"]
        assert cnc["valor_atual"] == pytest.approx(1000.0)
        assert cnc["meta_total"] == pytest.approx(3000.0)
        assert cnc["ritmo_diario"] == pytest.approx(100.0)
        assert cnc["meta_diaria"] == pytest.approx(150.0)
        assert cnc["perc_atingido"] == pytest.approx(1000 / 3000 * 100)
        assert cnc["projecao"] == pytest.approx(2000.0)


@pytest.mark.unit
class TestCalcularKpisQtdProdutos:
    def test_quantidades_analise_e_meta(self):
        df = pd.DataFrame({
            "LOJA": ["A", "A"],
            "is_emissao_cartao": [True, True],
            "is_super_conta": [False, True],
            "is_bmg_med": [False, False],
            "is_seguro_vida": [False, False],
        })
        df_analise = pd.DataFrame({
            "SUBTIPO": ["SUPER CONTA", None],
            "TIPO OPER.": ["CARTÃO BENEFICIO", "BMG MED"],
        })
        df_metas_produto = pd.DataFrame({
            "LOJA": ["A"], "EMISSAO": [5.0], "SUPER_CONTA": [3.0],
            "BMG_MED": [2.0], "VIDA_FAMILIAR": [1.0],
        })
        res = calcular_kpis_qtd_produtos(
            df, df_analise, df_metas_produto, du_total=20, du_decorridos=10,
        )
        by = {r["produto"]: r for r in res}
        assert set(by) == {"EMISSAO", "SUPER_CONTA", "BMG_MED", "VIDA_FAMILIAR"}

        emissao = by["EMISSAO"]
        assert emissao["qtd_paga"] == 2
        assert emissao["qtd_analise"] == 1  # CARTÃO BENEFICIO
        assert emissao["meta"] == pytest.approx(5.0)
        assert emissao["perc_atingido"] == pytest.approx(40.0)

        assert by["SUPER_CONTA"]["qtd_paga"] == 1
        assert by["SUPER_CONTA"]["qtd_analise"] == 1  # SUBTIPO == SUPER CONTA
        assert by["BMG_MED"]["qtd_analise"] == 1  # TIPO OPER. BMG MED

    def test_media_ref_a_partir_de_df_org(self):
        df = pd.DataFrame({"LOJA": ["A"], "is_emissao_cartao": [True]})
        df_org = pd.DataFrame({"is_emissao_cartao": [True, True, True]})
        res = calcular_kpis_qtd_produtos(
            df, pd.DataFrame(), pd.DataFrame(),
            du_total=20, du_decorridos=10, df_org=df_org, org_norm=3,
        )
        emissao = next(r for r in res if r["produto"] == "EMISSAO")
        # qtd_org = 3, normalizado por 3 → media_ref = 1.0
        assert emissao["media_ref"] == pytest.approx(1.0)


@pytest.mark.unit
class TestObterKpisPeriodo:
    """``obter_kpis_periodo`` compõe os sete cálculos do período e memoiza
    o resultado em ``session_state['_kpis_cache']`` sob a chave de
    ``_chave_kpis`` — a fronteira de RLS entre perfis (ver docstring de
    ``_chave_kpis``). Cobre miss/hit/invalidação por escopo e a forma do
    valor retornado; os ``calcular_*`` internos já têm suas próprias
    classes de teste acima.
    """

    _MES, _ANO, _DIA_ATUAL, _DU_DECORRIDOS = 6, 2026, 16, 10

    # df_metas_produto fixo (só LOJA "A"): a soma de componentes do MIX em
    # calcular_kpis_gerais NÃO é filtrada por LOJA, então o valor é o mesmo
    # em qualquer cenário — as funções que SÃO filtradas por LOJA
    # (metas_prod_diarias/kpis_qtd) simplesmente zeram para lojas ausentes
    # aqui, sem erro.
    def _df_metas_produto(self):
        return pd.DataFrame({
            "LOJA": ["A"],
            "CNC": [3000.0],
            "CLT": [0.0],
            "SAQUE": [2000.0],
            "CONSIGNADO": [0.0],
            "FGTS_ANT_BENEF_13": [0.0],
            "EMISSAO": [5.0],
            "SUPER_CONTA": [3.0],
            "BMG_MED": [2.0],
            "VIDA_FAMILIAR": [1.0],
        })

    def _df_a(self):
        """Escopo A: lojas A/B, regiões R1/R2. total_vendas = 1800."""
        return pd.DataFrame({
            "LOJA": ["A", "A", "B"],
            "REGIAO": ["R1", "R1", "R2"],
            "CONSULTOR": ["João", "Maria", "Pedro"],
            "categoria_codigo": ["CNC", "SAQUE", "CNC"],
            "VALOR": [1000.0, 500.0, 300.0],
            "pontos": [100.0, 50.0, 30.0],
            "is_super_conta": [False, False, False],
            "is_emissao_cartao": [False, False, False],
            "is_bmg_med": [False, False, False],
            "is_seguro_vida": [False, False, False],
            "DATA": pd.to_datetime(
                ["2026-06-01", "2026-06-01", "2026-06-02"]
            ),
        })

    def _df_b(self):
        """Escopo B: loja C, região R3. total_vendas = 9999 (não colide
        com o total de A)."""
        return pd.DataFrame({
            "LOJA": ["C"],
            "REGIAO": ["R3"],
            "CONSULTOR": ["Ana"],
            "categoria_codigo": ["SAQUE"],
            "VALOR": [9999.0],
            "pontos": [999.0],
            "is_super_conta": [False],
            "is_emissao_cartao": [False],
            "is_bmg_med": [False],
            "is_seguro_vida": [False],
            "DATA": pd.to_datetime(["2026-06-03"]),
        })

    def _kwargs(self, session_state, df, perfil_efetivo, df_full=None):
        """Monta os kwargs completos de ``obter_kpis_periodo``.

        ``df_full`` default é o escopo A: representa a base PRE-RLS da
        organização inteira, que não muda conforme o escopo do chamador
        (só ``df`` — o recorte já filtrado por RLS — muda entre perfis).
        """
        return dict(
            session_state=session_state,
            mes=self._MES,
            ano=self._ANO,
            role="gerente_comercial",
            perfil_efetivo=perfil_efetivo,
            df=df,
            df_metas=pd.DataFrame(
                {"META_PRATA": [10000.0], "META_OURO": [20000.0]}
            ),
            df_metas_produto=self._df_metas_produto(),
            df_analise=pd.DataFrame({
                "VALOR": [200.0],
                "SUBTIPO": ["OUTRO"],
                "TIPO OPER.": ["OUTRO"],
            }),
            df_cancelados=pd.DataFrame(
                {"VALOR": [100.0], "CLASSIFICACAO": ["liquido"]}
            ),
            df_sup=pd.DataFrame(columns=["SUPERVISOR"]),
            df_full=self._df_a() if df_full is None else df_full,
            df_sup_full=pd.DataFrame(columns=["SUPERVISOR"]),
            dia_atual=self._DIA_ATUAL,
            du_decorridos=self._DU_DECORRIDOS,
        )

    def test_cache_miss_dispara_calculo_e_grava_estado(self, sem_feriados):
        ss = {}
        perfil = {"perfil": "gerente_comercial", "escopo": ["R1", "R2"]}
        resultado = obter_kpis_periodo(**self._kwargs(ss, self._df_a(), perfil))

        chave_esperada = _chave_kpis(
            self._MES, self._ANO, "gerente_comercial", perfil, ss
        )
        assert ss.get("_kpis_chave") == chave_esperada
        assert resultado.kpis["total_vendas"] == pytest.approx(1800.0)
        assert ss["_kpis_cache"]["kpis"]["total_vendas"] == pytest.approx(1800.0)

    def test_cache_hit_nao_recalcula(self, monkeypatch, sem_feriados):
        """Segunda chamada com a MESMA chave não deve re-executar os
        cálculos pesados nem substituir o dict de cache."""
        original = kpis_gerais_module.calcular_kpis_gerais
        chamadas = []

        def _espiao(*args, **kwargs):
            chamadas.append(1)
            return original(*args, **kwargs)

        monkeypatch.setattr(kpis_gerais_module, "calcular_kpis_gerais", _espiao)

        ss = {}
        perfil = {"perfil": "gerente_comercial", "escopo": ["R1", "R2"]}
        kwargs = self._kwargs(ss, self._df_a(), perfil)

        resultado_1 = obter_kpis_periodo(**kwargs)
        assert len(chamadas) == 1
        cache_id_apos_miss = id(ss["_kpis_cache"])

        resultado_2 = obter_kpis_periodo(**kwargs)
        assert len(chamadas) == 1  # não recalculou na segunda chamada
        assert id(ss["_kpis_cache"]) == cache_id_apos_miss  # mesmo dict
        assert resultado_1 == resultado_2

    def test_mudanca_escopo_invalida_e_recalcula(self, sem_feriados):
        """Dois gerentes com o MESMO role, escopos diferentes — o caso
        mais próximo de um vazamento de RLS entre perfis (ver docstring
        de ``_chave_kpis``: role sozinho não separa dois gerentes)."""
        ss = {}
        perfil_a = {"perfil": "gerente_comercial", "escopo": ["R1", "R2"]}
        perfil_b = {"perfil": "gerente_comercial", "escopo": ["R3"]}

        resultado_a = obter_kpis_periodo(**self._kwargs(ss, self._df_a(), perfil_a))
        assert resultado_a.kpis["total_vendas"] == pytest.approx(1800.0)
        chave_apos_a = ss["_kpis_chave"]

        resultado_b = obter_kpis_periodo(**self._kwargs(ss, self._df_b(), perfil_b))
        assert ss["_kpis_chave"] != chave_apos_a

        # B não pode herdar o total cacheado de A.
        assert resultado_b.kpis["total_vendas"] == pytest.approx(9999.0)
        assert resultado_b.kpis["total_vendas"] != resultado_a.kpis["total_vendas"]
        # E o resultado já retornado para A permanece intacto (NamedTuple
        # imutável — não é uma view do dict de cache que B sobrescreveu).
        assert resultado_a.kpis["total_vendas"] == pytest.approx(1800.0)

    def test_campos_do_kpis_periodo(self, sem_feriados):
        ss = {}
        perfil = {"perfil": "gerente_comercial", "escopo": ["R1", "R2"]}
        resultado = obter_kpis_periodo(**self._kwargs(ss, self._df_a(), perfil))

        assert resultado._fields == (
            "kpis", "kpis_analise", "kpis_cancel", "medias",
            "metas_prod_diarias", "medias_organizacao", "kpis_qtd",
            "daily_pago",
        )
        assert isinstance(resultado.kpis, dict)
        assert isinstance(resultado.kpis_analise, dict)
        assert isinstance(resultado.kpis_cancel, dict)
        assert isinstance(resultado.medias, dict)
        assert isinstance(resultado.metas_prod_diarias, list)
        assert isinstance(resultado.medias_organizacao, dict)
        assert isinstance(resultado.kpis_qtd, list)
        # _df_a tem 2 dias distintos de DATA → serie com >= 2 pontos
        assert isinstance(resultado.daily_pago, list)
        assert resultado.daily_pago == pytest.approx([1500.0, 300.0])

        # meta_global_valor/perc_ating_valor/gap_valor são adicionados por
        # obter_kpis_periodo (não por calcular_kpis_gerais isolado) — meta
        # em VALOR (R$), via meta_mix, distinta de meta_prata (PONTOS).
        assert resultado.kpis["meta_global_valor"] == pytest.approx(5000.0)
        assert resultado.kpis["perc_ating_valor"] == pytest.approx(1800 / 5000 * 100)
        assert resultado.kpis["gap_valor"] == pytest.approx(5000 - 1800)

    def test_meta_global_valor_zero_nao_gera_erro_de_divisao(self, sem_feriados):
        """``meta_mix = 0`` (sem metas de produto) não pode gerar
        ZeroDivisionError em ``perc_ating_valor`` — guard explícito na
        composição (linhas 1104-1112 de ``gerais.py``)."""
        ss = {}
        perfil = {"perfil": "gerente_comercial", "escopo": ["R1", "R2"]}
        kwargs = self._kwargs(ss, self._df_a(), perfil)
        kwargs["df_metas_produto"] = pd.DataFrame()

        resultado = obter_kpis_periodo(**kwargs)
        assert resultado.kpis["meta_global_valor"] == 0
        assert resultado.kpis["perc_ating_valor"] == 0
        assert resultado.kpis["gap_valor"] == 0

    def test_cache_mantem_dict_com_as_8_chaves_do_kpis_periodo(self, sem_feriados):
        """O botão "Atualizar Dados" faz ``pop`` de ``_kpis_cache`` — o
        formato dict (não o NamedTuple) precisa continuar valendo."""
        ss = {}
        perfil = {"perfil": "gerente_comercial", "escopo": ["R1", "R2"]}
        obter_kpis_periodo(**self._kwargs(ss, self._df_a(), perfil))

        cache = ss["_kpis_cache"]
        assert isinstance(cache, dict)
        assert set(cache.keys()) == set(KpisPeriodo._fields)
        assert len(cache) == 8

    def test_limpar_cache_kpis_forca_recalculo(self, sem_feriados):
        """``limpar_cache_kpis`` é o que o botão "Atualizar Dados" chama:
        some com as duas chaves e faz a chamada seguinte recalcular (o
        chamador não conhece os nomes ``_kpis_cache``/``_kpis_chave``)."""
        ss = {}
        perfil = {"perfil": "gerente_comercial", "escopo": ["R1", "R2"]}
        kwargs = self._kwargs(ss, self._df_a(), perfil)
        obter_kpis_periodo(**kwargs)
        cache_antes = id(ss["_kpis_cache"])

        limpar_cache_kpis(ss)
        assert "_kpis_cache" not in ss
        assert "_kpis_chave" not in ss

        # Mesma chave de novo, mas sem cache: recalcula (dict novo).
        obter_kpis_periodo(**kwargs)
        assert id(ss["_kpis_cache"]) != cache_antes

    def test_limpar_cache_kpis_e_idempotente(self):
        """Chamada com o cache já ausente não pode levantar KeyError —
        o botão pode ser clicado antes de qualquer cálculo."""
        ss = {}
        limpar_cache_kpis(ss)
        assert ss == {}
