"""
Testes dos KPIs gerais e helpers compartilhados
(``src/dashboard/kpis/gerais.py``).

Inclui os helpers ``excluir_supervisores`` / ``contar_consultores``,
reusados pelos demais módulos KPI. ``calcular_kpis_gerais`` depende de
``calcular_dias_uteis`` → usa a fixture ``sem_feriados``.
"""
import pandas as pd
import pytest

from src.dashboard.kpis.gerais import (
    calcular_kpis_analise,
    calcular_kpis_cancelados,
    calcular_kpis_gerais,
    calcular_kpis_qtd_produtos,
    calcular_medias_du_por_nivel,
    calcular_medias_organizacao,
    calcular_metas_produto_diarias,
    contar_consultores,
    excluir_supervisores,
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
class TestCalcularKpisCancelados:
    def test_vazio(self):
        r = calcular_kpis_cancelados(pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
        assert r == {"valor_cancelados": 0, "qtd_cancelados": 0, "indice_perda": 0}

    def test_indice_perda(self):
        df_canc = pd.DataFrame({"VALOR": [500.0]})
        df = pd.DataFrame({"VALOR": [100.0, 200.0]})  # 2 pagos
        df_analise = pd.DataFrame({"VALOR": [300.0]})  # 1 análise
        r = calcular_kpis_cancelados(df_canc, df, df_analise)
        assert r["valor_cancelados"] == pytest.approx(500.0)
        assert r["qtd_cancelados"] == 1
        # 1 / (2 + 1 + 1) = 25%
        assert r["indice_perda"] == pytest.approx(25.0)


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
