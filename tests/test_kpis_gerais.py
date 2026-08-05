"""
Testes dos KPIs gerais e helpers compartilhados
(``src/dashboard/kpis/gerais.py``).

Inclui os helpers ``excluir_supervisores`` / ``contar_consultores``,
reusados pelos demais módulos KPI. ``calcular_kpis_gerais`` depende de
``calcular_dias_uteis`` → usa a fixture ``sem_feriados``.

As seis classes ``TestObter*Periodo`` cobrem a composição + cache manual
de cada uma das ``obter_*_periodo`` (``obter_kpis_gerais_periodo``,
``obter_kpis_pipeline_periodo``, ``obter_medias_periodo``,
``obter_medias_organizacao_periodo``, ``obter_metas_prod_diarias_periodo``,
``obter_kpis_qtd_periodo`` — sucessoras da antiga ``obter_kpis_periodo``,
decomposta por ISP): miss/hit/invalidação por escopo (a fronteira de RLS
entre perfis, ver docstring de ``_chave_kpis``) e a forma do valor
cacheado. A correção interna de cada ``calcular_*`` já está coberta
pelas classes acima, não é reexercitada ali. ``TestLimparCacheKpis``
cobre ``limpar_cache_kpis`` esquecendo os 6 pares de uma vez.
"""
from datetime import datetime, timedelta

import pandas as pd
import pytest

from src.dashboard.kpis import gerais as kpis_gerais_module
from src.dashboard.kpis.gerais import (
    JANELA_PIPELINE_DIAS,
    PRODUTOS_DASHBOARD,
    KpisPipeline,
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
    obter_kpis_gerais_periodo,
    obter_kpis_pipeline_periodo,
    obter_kpis_qtd_periodo,
    obter_medias_organizacao_periodo,
    obter_medias_periodo,
    obter_metas_prod_diarias_periodo,
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


# ══════════════════════════════════════════════════════════════════
# Fixtures/kwargs-builders compartilhados pelas 6 classes de
# obter_*_periodo e por TestLimparCacheKpis.
#
# O cenário de RLS é sempre o mesmo: dois "gerentes" com o MESMO role
# e escopos diferentes (perfil A: regiões R1/R2; perfil B: região R3)
# — o caso mais próximo de um vazamento de RLS entre perfis (ver
# docstring de ``_chave_kpis``: role sozinho não separa dois gerentes).
# ══════════════════════════════════════════════════════════════════

_MES, _ANO, _DIA_ATUAL, _DU_DECORRIDOS = 6, 2026, 16, 10

_PERFIL_A = {"perfil": "gerente_comercial", "escopo": ["R1", "R2"]}
_PERFIL_B = {"perfil": "gerente_comercial", "escopo": ["R3"]}


@pytest.fixture
def df_metas_produto_periodo():
    """Metas por produto fixas (só LOJA "A"): a soma de componentes do
    MIX em ``calcular_kpis_gerais`` não é filtrada por LOJA, então o
    valor é o mesmo em qualquer cenário — as funções que SÃO filtradas
    por LOJA (metas_prod_diarias/kpis_qtd) simplesmente zeram para
    lojas ausentes aqui, sem erro."""
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


@pytest.fixture
def df_escopo_a():
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


@pytest.fixture
def df_escopo_b():
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


def _df_metas():
    return pd.DataFrame({"META_PRATA": [10000.0], "META_OURO": [20000.0]})


def _df_analise_periodo():
    return pd.DataFrame({
        "VALOR": [200.0],
        "SUBTIPO": ["OUTRO"],
        "TIPO OPER.": ["OUTRO"],
    })


def _df_cancelados_periodo():
    return pd.DataFrame({"VALOR": [100.0], "CLASSIFICACAO": ["liquido"]})


def _df_sup_vazio():
    return pd.DataFrame(columns=["SUPERVISOR"])


def _kwargs_gerais(ss, df, perfil, df_metas_produto, role="gerente_comercial"):
    return dict(
        session_state=ss,
        mes=_MES,
        ano=_ANO,
        role=role,
        perfil_efetivo=perfil,
        df=df,
        df_metas=_df_metas(),
        df_metas_produto=df_metas_produto,
        dia_atual=_DIA_ATUAL,
        df_sup=_df_sup_vazio(),
    )


def _kwargs_pipeline(ss, df, perfil, role="gerente_comercial"):
    return dict(
        session_state=ss,
        mes=_MES,
        ano=_ANO,
        role=role,
        perfil_efetivo=perfil,
        df=df,
        df_analise=_df_analise_periodo(),
        df_cancelados=_df_cancelados_periodo(),
        du_decorridos=_DU_DECORRIDOS,
    )


def _kwargs_medias(ss, df, perfil, role="gerente_comercial"):
    return dict(
        session_state=ss,
        mes=_MES,
        ano=_ANO,
        role=role,
        perfil_efetivo=perfil,
        df=df,
        du_decorridos=_DU_DECORRIDOS,
        df_sup=_df_sup_vazio(),
    )


def _kwargs_medias_organizacao(ss, df_full, perfil, role="gerente_comercial"):
    return dict(
        session_state=ss,
        mes=_MES,
        ano=_ANO,
        role=role,
        perfil_efetivo=perfil,
        df_full=df_full,
        du_decorridos=_DU_DECORRIDOS,
        df_sup_full=_df_sup_vazio(),
    )


def _kwargs_metas_prod_diarias(
    ss, df, perfil, df_metas_produto, role="gerente_comercial"
):
    return dict(
        session_state=ss,
        mes=_MES,
        ano=_ANO,
        role=role,
        perfil_efetivo=perfil,
        df=df,
        df_metas=_df_metas(),
        df_metas_produto=df_metas_produto,
        df_sup=_df_sup_vazio(),
        dia_atual=_DIA_ATUAL,
        du_decorridos=_DU_DECORRIDOS,
    )


def _kwargs_kpis_qtd(
    ss, df, perfil, df_metas_produto, df_full, role="gerente_comercial"
):
    return dict(
        session_state=ss,
        mes=_MES,
        ano=_ANO,
        role=role,
        perfil_efetivo=perfil,
        df=df,
        df_metas=_df_metas(),
        df_metas_produto=df_metas_produto,
        df_sup=_df_sup_vazio(),
        df_analise=_df_analise_periodo(),
        df_full=df_full,
        df_sup_full=_df_sup_vazio(),
        dia_atual=_DIA_ATUAL,
        du_decorridos=_DU_DECORRIDOS,
    )


@pytest.mark.unit
class TestObterKpisGeraisPeriodo:
    """``obter_kpis_gerais_periodo`` — KPIs gerais do período + o trio
    de VALOR (meta_global_valor/perc_ating_valor/gap_valor), com cache
    em ``_kpis_gerais_cache``/``_kpis_gerais_chave``."""

    def test_cache_miss_dispara_calculo_e_grava_estado(
        self, df_escopo_a, df_metas_produto_periodo, sem_feriados
    ):
        ss = {}
        resultado = obter_kpis_gerais_periodo(
            **_kwargs_gerais(ss, df_escopo_a, _PERFIL_A, df_metas_produto_periodo)
        )

        chave_esperada = _chave_kpis(_MES, _ANO, "gerente_comercial", _PERFIL_A, ss)
        assert ss.get("_kpis_gerais_chave") == chave_esperada
        assert resultado["total_vendas"] == pytest.approx(1800.0)
        assert ss["_kpis_gerais_cache"]["total_vendas"] == pytest.approx(1800.0)
        # Cache é o PRÓPRIO dict de retorno, não um wrapper.
        assert ss["_kpis_gerais_cache"] is resultado

    def test_cache_hit_nao_recalcula(
        self, monkeypatch, df_escopo_a, df_metas_produto_periodo, sem_feriados
    ):
        original = kpis_gerais_module.calcular_kpis_gerais
        chamadas = []

        def _espiao(*args, **kwargs):
            chamadas.append(1)
            return original(*args, **kwargs)

        monkeypatch.setattr(kpis_gerais_module, "calcular_kpis_gerais", _espiao)

        ss = {}
        kwargs = _kwargs_gerais(ss, df_escopo_a, _PERFIL_A, df_metas_produto_periodo)

        resultado_1 = obter_kpis_gerais_periodo(**kwargs)
        assert len(chamadas) == 1
        cache_id_apos_miss = id(ss["_kpis_gerais_cache"])

        resultado_2 = obter_kpis_gerais_periodo(**kwargs)
        assert len(chamadas) == 1  # não recalculou na segunda chamada
        assert id(ss["_kpis_gerais_cache"]) == cache_id_apos_miss
        assert resultado_1 == resultado_2

    def test_mudanca_escopo_invalida_e_recalcula(
        self, df_escopo_a, df_escopo_b, df_metas_produto_periodo, sem_feriados
    ):
        """Dois gerentes com o MESMO role, escopos diferentes — o caso
        mais próximo de um vazamento de RLS entre perfis."""
        ss = {}
        resultado_a = obter_kpis_gerais_periodo(
            **_kwargs_gerais(ss, df_escopo_a, _PERFIL_A, df_metas_produto_periodo)
        )
        assert resultado_a["total_vendas"] == pytest.approx(1800.0)
        chave_apos_a = ss["_kpis_gerais_chave"]

        resultado_b = obter_kpis_gerais_periodo(
            **_kwargs_gerais(ss, df_escopo_b, _PERFIL_B, df_metas_produto_periodo)
        )
        assert ss["_kpis_gerais_chave"] != chave_apos_a

        # B não pode herdar o total cacheado de A.
        assert resultado_b["total_vendas"] == pytest.approx(9999.0)
        assert resultado_b["total_vendas"] != resultado_a["total_vendas"]
        # O resultado já retornado para A permanece intacto — cada
        # cálculo produz um dict NOVO, não é view do que B sobrescreveu.
        assert resultado_a["total_vendas"] == pytest.approx(1800.0)

    def test_meta_global_valor_deriva_de_meta_mix(
        self, df_escopo_a, df_metas_produto_periodo, sem_feriados
    ):
        ss = {}
        resultado = obter_kpis_gerais_periodo(
            **_kwargs_gerais(ss, df_escopo_a, _PERFIL_A, df_metas_produto_periodo)
        )
        # meta_mix (sem coluna MIX) = soma dos componentes: CNC 3000 + SAQUE
        # 2000 = 5000. Meta em VALOR (R$), distinta de meta_prata (PONTOS).
        assert resultado["meta_global_valor"] == pytest.approx(5000.0)
        assert resultado["perc_ating_valor"] == pytest.approx(1800 / 5000 * 100)
        assert resultado["gap_valor"] == pytest.approx(5000 - 1800)

    def test_meta_global_valor_zero_nao_gera_erro_de_divisao(
        self, df_escopo_a, sem_feriados
    ):
        """``meta_mix = 0`` (sem metas de produto) não pode gerar
        ZeroDivisionError em ``perc_ating_valor``."""
        ss = {}
        kwargs = _kwargs_gerais(ss, df_escopo_a, _PERFIL_A, pd.DataFrame())
        resultado = obter_kpis_gerais_periodo(**kwargs)
        assert resultado["meta_global_valor"] == 0
        assert resultado["perc_ating_valor"] == 0
        assert resultado["gap_valor"] == 0

    def test_cache_e_dict_com_chaves_do_calculo_mais_extras_de_valor(
        self, df_escopo_a, df_metas_produto_periodo, sem_feriados
    ):
        ss = {}
        obter_kpis_gerais_periodo(
            **_kwargs_gerais(ss, df_escopo_a, _PERFIL_A, df_metas_produto_periodo)
        )
        base = calcular_kpis_gerais(
            df_escopo_a, _df_metas(), df_metas_produto_periodo,
            _ANO, _MES, _DIA_ATUAL, _df_sup_vazio(),
        )
        cache = ss["_kpis_gerais_cache"]
        assert isinstance(cache, dict)
        assert set(cache.keys()) == set(base.keys()) | {
            "meta_global_valor", "perc_ating_valor", "gap_valor",
        }


@pytest.mark.unit
class TestObterKpisPipelinePeriodo:
    """``obter_kpis_pipeline_periodo`` — "Em Análise" + "Cancelados",
    retorna ``KpisPipeline``, com cache em
    ``_kpis_pipeline_cache``/``_kpis_pipeline_chave``."""

    def test_cache_miss_dispara_calculo_e_grava_estado(self, df_escopo_a):
        ss = {}
        resultado = obter_kpis_pipeline_periodo(
            **_kwargs_pipeline(ss, df_escopo_a, _PERFIL_A)
        )

        chave_esperada = _chave_kpis(_MES, _ANO, "gerente_comercial", _PERFIL_A, ss)
        assert ss.get("_kpis_pipeline_chave") == chave_esperada
        esperado_analise = calcular_kpis_analise(
            _df_analise_periodo(), df_escopo_a, _DU_DECORRIDOS
        )
        esperado_cancel = calcular_kpis_cancelados(
            _df_cancelados_periodo(), df_escopo_a, _df_analise_periodo()
        )
        assert resultado.kpis_analise == esperado_analise
        assert resultado.kpis_cancel == esperado_cancel
        assert ss["_kpis_pipeline_cache"] == {
            "kpis_analise": esperado_analise, "kpis_cancel": esperado_cancel,
        }

    def test_cache_hit_nao_recalcula(self, monkeypatch, df_escopo_a):
        original_analise = kpis_gerais_module.calcular_kpis_analise
        original_cancel = kpis_gerais_module.calcular_kpis_cancelados
        chamadas_analise, chamadas_cancel = [], []

        def _espiao_analise(*args, **kwargs):
            chamadas_analise.append(1)
            return original_analise(*args, **kwargs)

        def _espiao_cancel(*args, **kwargs):
            chamadas_cancel.append(1)
            return original_cancel(*args, **kwargs)

        monkeypatch.setattr(
            kpis_gerais_module, "calcular_kpis_analise", _espiao_analise
        )
        monkeypatch.setattr(
            kpis_gerais_module, "calcular_kpis_cancelados", _espiao_cancel
        )

        ss = {}
        kwargs = _kwargs_pipeline(ss, df_escopo_a, _PERFIL_A)

        resultado_1 = obter_kpis_pipeline_periodo(**kwargs)
        assert len(chamadas_analise) == 1
        assert len(chamadas_cancel) == 1
        cache_id_apos_miss = id(ss["_kpis_pipeline_cache"])

        resultado_2 = obter_kpis_pipeline_periodo(**kwargs)
        assert len(chamadas_analise) == 1
        assert len(chamadas_cancel) == 1
        assert id(ss["_kpis_pipeline_cache"]) == cache_id_apos_miss
        assert resultado_1 == resultado_2

    def test_mudanca_escopo_invalida_e_recalcula(self, df_escopo_a, df_escopo_b):
        ss = {}
        resultado_a = obter_kpis_pipeline_periodo(
            **_kwargs_pipeline(ss, df_escopo_a, _PERFIL_A)
        )
        esperado_a = calcular_kpis_cancelados(
            _df_cancelados_periodo(), df_escopo_a, _df_analise_periodo()
        )
        assert resultado_a.kpis_cancel == esperado_a
        chave_apos_a = ss["_kpis_pipeline_chave"]

        resultado_b = obter_kpis_pipeline_periodo(
            **_kwargs_pipeline(ss, df_escopo_b, _PERFIL_B)
        )
        assert ss["_kpis_pipeline_chave"] != chave_apos_a
        esperado_b = calcular_kpis_cancelados(
            _df_cancelados_periodo(), df_escopo_b, _df_analise_periodo()
        )
        # indice_perda depende de qtd_pagos (len(df)), que muda com o
        # escopo: A tem 3 linhas, B tem 1 → B não pode herdar o de A.
        assert resultado_b.kpis_cancel == esperado_b
        assert resultado_b.kpis_cancel != resultado_a.kpis_cancel
        assert resultado_a.kpis_cancel == esperado_a

    def test_retorno_e_namedtuple_com_2_campos(self, df_escopo_a):
        ss = {}
        resultado = obter_kpis_pipeline_periodo(
            **_kwargs_pipeline(ss, df_escopo_a, _PERFIL_A)
        )
        assert resultado._fields == ("kpis_analise", "kpis_cancel")
        assert isinstance(resultado, KpisPipeline)

    def test_cache_e_dict_com_as_2_chaves_do_kpis_pipeline(self, df_escopo_a):
        ss = {}
        obter_kpis_pipeline_periodo(**_kwargs_pipeline(ss, df_escopo_a, _PERFIL_A))
        cache = ss["_kpis_pipeline_cache"]
        assert isinstance(cache, dict)
        assert set(cache.keys()) == set(KpisPipeline._fields)
        assert len(cache) == 2


@pytest.mark.unit
class TestObterMediasPeriodo:
    """``obter_medias_periodo`` — médias DU por loja/consultor do
    escopo PÓS-RLS, com cache em ``_medias_cache``/``_medias_chave``."""

    def test_cache_miss_dispara_calculo_e_grava_estado(self, df_escopo_a):
        ss = {}
        resultado = obter_medias_periodo(**_kwargs_medias(ss, df_escopo_a, _PERFIL_A))

        chave_esperada = _chave_kpis(_MES, _ANO, "gerente_comercial", _PERFIL_A, ss)
        assert ss.get("_medias_chave") == chave_esperada
        esperado = calcular_medias_du_por_nivel(
            df_escopo_a, _DU_DECORRIDOS, _df_sup_vazio()
        )
        assert resultado == esperado
        assert ss["_medias_cache"] is resultado

    def test_cache_hit_nao_recalcula(self, monkeypatch, df_escopo_a):
        original = kpis_gerais_module.calcular_medias_du_por_nivel
        chamadas = []

        def _espiao(*args, **kwargs):
            chamadas.append(1)
            return original(*args, **kwargs)

        monkeypatch.setattr(
            kpis_gerais_module, "calcular_medias_du_por_nivel", _espiao
        )

        ss = {}
        kwargs = _kwargs_medias(ss, df_escopo_a, _PERFIL_A)

        resultado_1 = obter_medias_periodo(**kwargs)
        assert len(chamadas) == 1
        cache_id_apos_miss = id(ss["_medias_cache"])

        resultado_2 = obter_medias_periodo(**kwargs)
        assert len(chamadas) == 1
        assert id(ss["_medias_cache"]) == cache_id_apos_miss
        assert resultado_1 == resultado_2

    def test_mudanca_escopo_invalida_e_recalcula(self, df_escopo_a, df_escopo_b):
        ss = {}
        resultado_a = obter_medias_periodo(
            **_kwargs_medias(ss, df_escopo_a, _PERFIL_A)
        )
        esperado_a = calcular_medias_du_por_nivel(
            df_escopo_a, _DU_DECORRIDOS, _df_sup_vazio()
        )
        assert resultado_a == esperado_a
        chave_apos_a = ss["_medias_chave"]

        resultado_b = obter_medias_periodo(
            **_kwargs_medias(ss, df_escopo_b, _PERFIL_B)
        )
        assert ss["_medias_chave"] != chave_apos_a
        esperado_b = calcular_medias_du_por_nivel(
            df_escopo_b, _DU_DECORRIDOS, _df_sup_vazio()
        )
        assert resultado_b == esperado_b
        assert resultado_b != resultado_a
        assert resultado_a == esperado_a

    def test_cache_e_dict_com_as_4_chaves_de_medias_du_por_nivel(self, df_escopo_a):
        ss = {}
        obter_medias_periodo(**_kwargs_medias(ss, df_escopo_a, _PERFIL_A))
        cache = ss["_medias_cache"]
        assert isinstance(cache, dict)
        assert set(cache.keys()) == {
            "media_du_loja", "media_du_consultor", "num_lojas", "num_consultores",
        }


@pytest.mark.unit
class TestObterMediasOrganizacaoPeriodo:
    """``obter_medias_organizacao_periodo`` — médias da organização
    inteira (PRÉ-RLS, base de comparação), com granularidade que segue
    o filtro de UI, cache em
    ``_medias_organizacao_cache``/``_medias_organizacao_chave``."""

    def test_cache_miss_dispara_calculo_e_grava_estado(self, df_escopo_a):
        ss = {}
        resultado = obter_medias_organizacao_periodo(
            **_kwargs_medias_organizacao(ss, df_escopo_a, _PERFIL_A)
        )

        chave_esperada = _chave_kpis(_MES, _ANO, "gerente_comercial", _PERFIL_A, ss)
        assert ss.get("_medias_organizacao_chave") == chave_esperada
        esperado = calcular_medias_organizacao(
            df_escopo_a, du_decorridos=_DU_DECORRIDOS,
            perfil="gerente_comercial", df_sup=_df_sup_vazio(),
        )
        assert resultado == esperado
        assert ss["_medias_organizacao_cache"] is resultado

    def test_cache_hit_nao_recalcula(self, monkeypatch, df_escopo_a):
        original = kpis_gerais_module.calcular_medias_organizacao
        chamadas = []

        def _espiao(*args, **kwargs):
            chamadas.append(1)
            return original(*args, **kwargs)

        monkeypatch.setattr(
            kpis_gerais_module, "calcular_medias_organizacao", _espiao
        )

        ss = {}
        kwargs = _kwargs_medias_organizacao(ss, df_escopo_a, _PERFIL_A)

        resultado_1 = obter_medias_organizacao_periodo(**kwargs)
        assert len(chamadas) == 1
        cache_id_apos_miss = id(ss["_medias_organizacao_cache"])

        resultado_2 = obter_medias_organizacao_periodo(**kwargs)
        assert len(chamadas) == 1
        assert id(ss["_medias_organizacao_cache"]) == cache_id_apos_miss
        assert resultado_1 == resultado_2

    def test_mudanca_escopo_invalida_e_recalcula(self, df_escopo_a, df_escopo_b):
        ss = {}
        resultado_a = obter_medias_organizacao_periodo(
            **_kwargs_medias_organizacao(ss, df_escopo_a, _PERFIL_A)
        )
        esperado_a = calcular_medias_organizacao(
            df_escopo_a, du_decorridos=_DU_DECORRIDOS,
            perfil="gerente_comercial", df_sup=_df_sup_vazio(),
        )
        assert resultado_a == esperado_a
        chave_apos_a = ss["_medias_organizacao_chave"]

        resultado_b = obter_medias_organizacao_periodo(
            **_kwargs_medias_organizacao(ss, df_escopo_b, _PERFIL_B)
        )
        assert ss["_medias_organizacao_chave"] != chave_apos_a
        esperado_b = calcular_medias_organizacao(
            df_escopo_b, du_decorridos=_DU_DECORRIDOS,
            perfil="gerente_comercial", df_sup=_df_sup_vazio(),
        )
        assert resultado_b == esperado_b
        assert resultado_b != resultado_a
        assert resultado_a == esperado_a

    def test_granularidade_segue_filtro_ui_quando_gerente_afunila(self):
        """``ui_filtro_lojas``/``ui_filtro_consultor`` decidem
        ``_perfil_media`` — sem filtro, usa o role; com lojas, afunila
        para "supervisor"; com consultor, afunila para "consultor"
        (mais granular que qualquer filtro de loja).

        Usa um df dedicado (não ``df_escopo_a``): lá LOJA e REGIAO
        coincidem 1-para-1, então agrupar por uma ou por outra dá a
        MESMA média — não provaria que a granularidade mudou de fato.
        Aqui LOJA A concentra 2 consultores de R1, LOJA B é a outra
        loja de R1 e LOJA C é a única de R2: região, loja e consultor
        agrupam em partições diferentes entre si.
        """
        df_full = pd.DataFrame({
            "REGIAO": ["R1", "R1", "R1", "R2"],
            "LOJA": ["A", "A", "B", "C"],
            "CONSULTOR": ["X", "Y", "Z", "W"],
            "categoria_codigo": ["CNC", "CNC", "CNC", "CNC"],
            "VALOR": [1000.0, 2000.0, 300.0, 9000.0],
        })
        esperado_regiao = calcular_medias_organizacao(
            df_full, du_decorridos=_DU_DECORRIDOS,
            perfil="gerente_comercial", df_sup=_df_sup_vazio(),
        )
        esperado_loja = calcular_medias_organizacao(
            df_full, du_decorridos=_DU_DECORRIDOS,
            perfil="supervisor", df_sup=_df_sup_vazio(),
        )
        esperado_consultor = calcular_medias_organizacao(
            df_full, du_decorridos=_DU_DECORRIDOS,
            perfil="consultor", df_sup=_df_sup_vazio(),
        )
        # As 3 granularidades produzem médias diferentes (senão o teste
        # não provaria nada).
        assert esperado_regiao != esperado_loja
        assert esperado_loja != esperado_consultor

        r_sem_filtro = obter_medias_organizacao_periodo(
            **_kwargs_medias_organizacao({}, df_full, _PERFIL_A)
        )
        assert r_sem_filtro == esperado_regiao

        r_com_lojas = obter_medias_organizacao_periodo(
            **_kwargs_medias_organizacao(
                {"ui_filtro_lojas": ["A"]}, df_full, _PERFIL_A
            )
        )
        assert r_com_lojas == esperado_loja

        r_com_consultor = obter_medias_organizacao_periodo(
            **_kwargs_medias_organizacao(
                {"ui_filtro_consultor": "X"}, df_full, _PERFIL_A
            )
        )
        assert r_com_consultor == esperado_consultor

    def test_cache_e_dict_com_uma_chave_por_produto_dashboard(self, df_escopo_a):
        ss = {}
        obter_medias_organizacao_periodo(
            **_kwargs_medias_organizacao(ss, df_escopo_a, _PERFIL_A)
        )
        cache = ss["_medias_organizacao_cache"]
        assert isinstance(cache, dict)
        assert set(cache.keys()) == set(PRODUTOS_DASHBOARD.keys())


@pytest.mark.unit
class TestObterMetasProdDiariasPeriodo:
    """``obter_metas_prod_diarias_periodo`` — meta diária restante por
    produto; depende de ``du_total``, obtido via chamada INTERNA a
    ``obter_kpis_gerais_periodo``. Cache em
    ``_metas_prod_diarias_cache``/``_metas_prod_diarias_chave``."""

    def test_cache_miss_dispara_calculo_e_grava_estado(
        self, df_escopo_a, df_metas_produto_periodo, sem_feriados
    ):
        ss = {}
        resultado = obter_metas_prod_diarias_periodo(
            **_kwargs_metas_prod_diarias(
                ss, df_escopo_a, _PERFIL_A, df_metas_produto_periodo
            )
        )

        chave_esperada = _chave_kpis(_MES, _ANO, "gerente_comercial", _PERFIL_A, ss)
        assert ss.get("_metas_prod_diarias_chave") == chave_esperada
        kpis_gerais = calcular_kpis_gerais(
            df_escopo_a, _df_metas(), df_metas_produto_periodo,
            _ANO, _MES, _DIA_ATUAL, _df_sup_vazio(),
        )
        esperado = calcular_metas_produto_diarias(
            df_escopo_a, df_metas_produto_periodo,
            kpis_gerais["du_total"], _DU_DECORRIDOS,
        )
        assert resultado == esperado
        assert ss["_metas_prod_diarias_cache"] is resultado

    def test_cache_hit_nao_recalcula(
        self, monkeypatch, df_escopo_a, df_metas_produto_periodo, sem_feriados
    ):
        original = kpis_gerais_module.calcular_metas_produto_diarias
        chamadas = []

        def _espiao(*args, **kwargs):
            chamadas.append(1)
            return original(*args, **kwargs)

        monkeypatch.setattr(
            kpis_gerais_module, "calcular_metas_produto_diarias", _espiao
        )

        ss = {}
        kwargs = _kwargs_metas_prod_diarias(
            ss, df_escopo_a, _PERFIL_A, df_metas_produto_periodo
        )

        resultado_1 = obter_metas_prod_diarias_periodo(**kwargs)
        assert len(chamadas) == 1
        cache_id_apos_miss = id(ss["_metas_prod_diarias_cache"])

        resultado_2 = obter_metas_prod_diarias_periodo(**kwargs)
        assert len(chamadas) == 1
        assert id(ss["_metas_prod_diarias_cache"]) == cache_id_apos_miss
        assert resultado_1 == resultado_2

    def test_mudanca_escopo_invalida_e_recalcula(
        self, df_escopo_a, df_escopo_b, df_metas_produto_periodo, sem_feriados
    ):
        ss = {}
        resultado_a = obter_metas_prod_diarias_periodo(
            **_kwargs_metas_prod_diarias(
                ss, df_escopo_a, _PERFIL_A, df_metas_produto_periodo
            )
        )
        kpis_a = calcular_kpis_gerais(
            df_escopo_a, _df_metas(), df_metas_produto_periodo,
            _ANO, _MES, _DIA_ATUAL, _df_sup_vazio(),
        )
        esperado_a = calcular_metas_produto_diarias(
            df_escopo_a, df_metas_produto_periodo,
            kpis_a["du_total"], _DU_DECORRIDOS,
        )
        assert resultado_a == esperado_a
        chave_apos_a = ss["_metas_prod_diarias_chave"]

        resultado_b = obter_metas_prod_diarias_periodo(
            **_kwargs_metas_prod_diarias(
                ss, df_escopo_b, _PERFIL_B, df_metas_produto_periodo
            )
        )
        assert ss["_metas_prod_diarias_chave"] != chave_apos_a
        kpis_b = calcular_kpis_gerais(
            df_escopo_b, _df_metas(), df_metas_produto_periodo,
            _ANO, _MES, _DIA_ATUAL, _df_sup_vazio(),
        )
        esperado_b = calcular_metas_produto_diarias(
            df_escopo_b, df_metas_produto_periodo,
            kpis_b["du_total"], _DU_DECORRIDOS,
        )
        assert resultado_b == esperado_b
        assert resultado_b != resultado_a
        assert resultado_a == esperado_a

    def test_reaproveita_cache_de_kpis_gerais_sem_recalculo_redundante(
        self, monkeypatch, df_escopo_a, df_metas_produto_periodo, sem_feriados
    ):
        """``du_total`` vem de chamar ``obter_kpis_gerais_periodo``
        internamente — se ``app.py`` já o chamou neste rerun (mesma
        chave), essa chamada interna tem que ser cache HIT, não um
        segundo ``calcular_kpis_gerais``."""
        original = kpis_gerais_module.calcular_kpis_gerais
        chamadas = []

        def _espiao(*args, **kwargs):
            chamadas.append(1)
            return original(*args, **kwargs)

        monkeypatch.setattr(kpis_gerais_module, "calcular_kpis_gerais", _espiao)

        ss = {}
        obter_kpis_gerais_periodo(
            **_kwargs_gerais(ss, df_escopo_a, _PERFIL_A, df_metas_produto_periodo)
        )
        assert len(chamadas) == 1

        obter_metas_prod_diarias_periodo(
            **_kwargs_metas_prod_diarias(
                ss, df_escopo_a, _PERFIL_A, df_metas_produto_periodo
            )
        )
        assert len(chamadas) == 1  # cache hit interno: sem recálculo

    def test_cache_e_lista_com_um_item_por_produto_dashboard(
        self, df_escopo_a, df_metas_produto_periodo, sem_feriados
    ):
        ss = {}
        obter_metas_prod_diarias_periodo(
            **_kwargs_metas_prod_diarias(
                ss, df_escopo_a, _PERFIL_A, df_metas_produto_periodo
            )
        )
        cache = ss["_metas_prod_diarias_cache"]
        assert isinstance(cache, list)
        assert {item["produto"] for item in cache} == set(PRODUTOS_DASHBOARD.keys())
        assert len(cache) == len(PRODUTOS_DASHBOARD)


@pytest.mark.unit
class TestObterKpisQtdPeriodo:
    """``obter_kpis_qtd_periodo`` — KPIs de QUANTIDADE por produto,
    misturando frames PÓS-RLS (``df``/``df_analise``) e PRÉ-RLS
    (``df_full``/``df_sup_full``, alimentam ``_ritmo_organizacao`` para
    a Média DU de referência). Depende de ``du_total`` via chamada
    INTERNA a ``obter_kpis_gerais_periodo``. Cache em
    ``_kpis_qtd_cache``/``_kpis_qtd_chave``."""

    def test_cache_miss_dispara_calculo_e_grava_estado(
        self, df_escopo_a, df_metas_produto_periodo, sem_feriados
    ):
        ss = {}
        resultado = obter_kpis_qtd_periodo(
            **_kwargs_kpis_qtd(
                ss, df_escopo_a, _PERFIL_A, df_metas_produto_periodo, df_escopo_a
            )
        )

        chave_esperada = _chave_kpis(_MES, _ANO, "gerente_comercial", _PERFIL_A, ss)
        assert ss.get("_kpis_qtd_chave") == chave_esperada
        kpis_gerais = calcular_kpis_gerais(
            df_escopo_a, _df_metas(), df_metas_produto_periodo,
            _ANO, _MES, _DIA_ATUAL, _df_sup_vazio(),
        )
        # role="gerente_comercial" -> _ritmo_organizacao devolve (None, 1).
        esperado = calcular_kpis_qtd_produtos(
            df_escopo_a, _df_analise_periodo(), df_metas_produto_periodo,
            kpis_gerais["du_total"], _DU_DECORRIDOS, df_org=None, org_norm=1,
        )
        assert resultado == esperado
        assert ss["_kpis_qtd_cache"] is resultado

    def test_cache_hit_nao_recalcula(
        self, monkeypatch, df_escopo_a, df_metas_produto_periodo, sem_feriados
    ):
        original = kpis_gerais_module.calcular_kpis_qtd_produtos
        chamadas = []

        def _espiao(*args, **kwargs):
            chamadas.append(1)
            return original(*args, **kwargs)

        monkeypatch.setattr(
            kpis_gerais_module, "calcular_kpis_qtd_produtos", _espiao
        )

        ss = {}
        kwargs = _kwargs_kpis_qtd(
            ss, df_escopo_a, _PERFIL_A, df_metas_produto_periodo, df_escopo_a
        )

        resultado_1 = obter_kpis_qtd_periodo(**kwargs)
        assert len(chamadas) == 1
        cache_id_apos_miss = id(ss["_kpis_qtd_cache"])

        resultado_2 = obter_kpis_qtd_periodo(**kwargs)
        assert len(chamadas) == 1
        assert id(ss["_kpis_qtd_cache"]) == cache_id_apos_miss
        assert resultado_1 == resultado_2

    def test_mudanca_escopo_invalida_e_recalcula(
        self, df_escopo_a, df_escopo_b, df_metas_produto_periodo, sem_feriados
    ):
        ss = {}
        resultado_a = obter_kpis_qtd_periodo(
            **_kwargs_kpis_qtd(
                ss, df_escopo_a, _PERFIL_A, df_metas_produto_periodo, df_escopo_a
            )
        )
        kpis_a = calcular_kpis_gerais(
            df_escopo_a, _df_metas(), df_metas_produto_periodo,
            _ANO, _MES, _DIA_ATUAL, _df_sup_vazio(),
        )
        esperado_a = calcular_kpis_qtd_produtos(
            df_escopo_a, _df_analise_periodo(), df_metas_produto_periodo,
            kpis_a["du_total"], _DU_DECORRIDOS, df_org=None, org_norm=1,
        )
        assert resultado_a == esperado_a
        chave_apos_a = ss["_kpis_qtd_chave"]

        resultado_b = obter_kpis_qtd_periodo(
            **_kwargs_kpis_qtd(
                ss, df_escopo_b, _PERFIL_B, df_metas_produto_periodo, df_escopo_b
            )
        )
        assert ss["_kpis_qtd_chave"] != chave_apos_a
        kpis_b = calcular_kpis_gerais(
            df_escopo_b, _df_metas(), df_metas_produto_periodo,
            _ANO, _MES, _DIA_ATUAL, _df_sup_vazio(),
        )
        # LOJA de B (C) não bate com a meta cadastrada só p/ LOJA A ->
        # "meta" zera para B, diferente de A -> não pode herdar de A.
        esperado_b = calcular_kpis_qtd_produtos(
            df_escopo_b, _df_analise_periodo(), df_metas_produto_periodo,
            kpis_b["du_total"], _DU_DECORRIDOS, df_org=None, org_norm=1,
        )
        assert resultado_b == esperado_b
        assert resultado_b != resultado_a
        assert resultado_a == esperado_a

    def test_reaproveita_cache_de_kpis_gerais_sem_recalculo_redundante(
        self, monkeypatch, df_escopo_a, df_metas_produto_periodo, sem_feriados
    ):
        """Mesmo trade-off de ``obter_metas_prod_diarias_periodo``: a
        chamada interna a ``obter_kpis_gerais_periodo`` deve ser cache
        HIT quando a chave já foi populada neste rerun."""
        original = kpis_gerais_module.calcular_kpis_gerais
        chamadas = []

        def _espiao(*args, **kwargs):
            chamadas.append(1)
            return original(*args, **kwargs)

        monkeypatch.setattr(kpis_gerais_module, "calcular_kpis_gerais", _espiao)

        ss = {}
        obter_kpis_gerais_periodo(
            **_kwargs_gerais(ss, df_escopo_a, _PERFIL_A, df_metas_produto_periodo)
        )
        assert len(chamadas) == 1

        obter_kpis_qtd_periodo(
            **_kwargs_kpis_qtd(
                ss, df_escopo_a, _PERFIL_A, df_metas_produto_periodo, df_escopo_a
            )
        )
        assert len(chamadas) == 1  # cache hit interno: sem recálculo

    def test_role_supervisor_usa_ritmo_organizacao_para_media_ref(
        self, sem_feriados
    ):
        """``df_full``/``df_sup_full`` (PRÉ-RLS) alimentam
        ``_ritmo_organizacao`` para dar ao supervisor uma referência de
        quantidade por loja da própria região — o comportamento de
        ``_ritmo_organizacao`` em si já é coberto por
        ``TestRitmoOrganizacao`` (``test_app_helpers.py``); aqui só
        confirmamos que ``obter_kpis_qtd_periodo`` liga essa base ao
        resultado (``media_ref``)."""
        df = pd.DataFrame({
            "LOJA": ["A"],
            "REGIAO": ["R1"],
            "VALOR": [500.0],
            "pontos": [50.0],
            "is_emissao_cartao": [False],
        })
        df_full = pd.DataFrame({
            "LOJA": ["A", "B"],
            "REGIAO": ["R1", "R1"],
            "is_emissao_cartao": [True, True],
        })
        ss = {}
        perfil = {"perfil": "supervisor", "escopo": ["A"]}
        resultado = obter_kpis_qtd_periodo(
            session_state=ss,
            mes=_MES,
            ano=_ANO,
            role="supervisor",
            perfil_efetivo=perfil,
            df=df,
            df_metas=_df_metas(),
            df_metas_produto=pd.DataFrame(),
            df_sup=_df_sup_vazio(),
            df_analise=pd.DataFrame(),
            df_full=df_full,
            df_sup_full=_df_sup_vazio(),
            dia_atual=_DIA_ATUAL,
            du_decorridos=_DU_DECORRIDOS,
        )
        emissao = next(r for r in resultado if r["produto"] == "EMISSAO")
        # df_org = as 2 lojas de R1 (A, B), ambas com is_emissao_cartao=True:
        # qtd_org=2, org_norm=2 lojas -> media_ref = 2/2 = 1.0
        assert emissao["media_ref"] == pytest.approx(1.0)

    def test_cache_e_lista_com_um_item_por_produto_qtd(
        self, df_escopo_a, df_metas_produto_periodo, sem_feriados
    ):
        ss = {}
        obter_kpis_qtd_periodo(
            **_kwargs_kpis_qtd(
                ss, df_escopo_a, _PERFIL_A, df_metas_produto_periodo, df_escopo_a
            )
        )
        cache = ss["_kpis_qtd_cache"]
        assert isinstance(cache, list)
        assert {item["produto"] for item in cache} == {
            "EMISSAO", "SUPER_CONTA", "BMG_MED", "VIDA_FAMILIAR",
        }
        assert len(cache) == 4


@pytest.mark.unit
class TestLimparCacheKpis:
    """``limpar_cache_kpis`` esquece os 6 pares ``_*_cache``/``_*_chave``
    das ``obter_*_periodo`` de uma vez — o botão "Atualizar Dados" não
    conhece esses nomes."""

    _NOMES_CACHE = (
        "_kpis_gerais_cache", "_kpis_gerais_chave",
        "_kpis_pipeline_cache", "_kpis_pipeline_chave",
        "_medias_cache", "_medias_chave",
        "_medias_organizacao_cache", "_medias_organizacao_chave",
        "_metas_prod_diarias_cache", "_metas_prod_diarias_chave",
        "_kpis_qtd_cache", "_kpis_qtd_chave",
    )

    def _chamar_as_6(self, ss, df, perfil, df_metas_produto):
        obter_kpis_gerais_periodo(**_kwargs_gerais(ss, df, perfil, df_metas_produto))
        obter_kpis_pipeline_periodo(**_kwargs_pipeline(ss, df, perfil))
        obter_medias_periodo(**_kwargs_medias(ss, df, perfil))
        obter_medias_organizacao_periodo(
            **_kwargs_medias_organizacao(ss, df, perfil)
        )
        obter_metas_prod_diarias_periodo(
            **_kwargs_metas_prod_diarias(ss, df, perfil, df_metas_produto)
        )
        obter_kpis_qtd_periodo(
            **_kwargs_kpis_qtd(ss, df, perfil, df_metas_produto, df)
        )

    def test_limpar_cache_kpis_forca_recalculo(
        self, df_escopo_a, df_metas_produto_periodo, sem_feriados
    ):
        ss = {}
        self._chamar_as_6(ss, df_escopo_a, _PERFIL_A, df_metas_produto_periodo)
        assert all(nome in ss for nome in self._NOMES_CACHE)
        assert len(self._NOMES_CACHE) == 12

        ids_antes = {
            nome: id(ss[nome])
            for nome in self._NOMES_CACHE
            if nome.endswith("_cache")
        }

        limpar_cache_kpis(ss)
        assert not any(nome in ss for nome in self._NOMES_CACHE)

        # Mesma chave de escopo de novo, mas sem cache: as 6 recalculam.
        self._chamar_as_6(ss, df_escopo_a, _PERFIL_A, df_metas_produto_periodo)
        for nome, id_antes in ids_antes.items():
            assert id(ss[nome]) != id_antes, f"{nome} não foi recalculado"

    def test_limpar_cache_kpis_e_idempotente(self):
        """Chamada com o cache já ausente não pode levantar KeyError —
        o botão pode ser clicado antes de qualquer cálculo."""
        ss = {}
        limpar_cache_kpis(ss)
        assert ss == {}
