"""
Testes dos KPIs por grupo de produto (``src/dashboard/kpis/produtos.py``).

``calcular_kpis_por_produto`` depende de ``calcular_dias_uteis``, que
busca feriados no Supabase quando ``feriados=None``. A fixture
``sem_feriados`` neutraliza esse acesso (conjunto vazio), deixando o DU
determinístico para asserções exatas.
"""
import pandas as pd
import pytest

from src.dashboard.kpis.produtos import (
    BANCOS_BMG_HELP,
    calcular_distribuicao_produtos,
    calcular_distribuicao_produtos_por_loja,
    calcular_kpis_por_produto,
    canonizar_banco,
    opcoes_banco,
)
from src.shared.dias_uteis import calcular_dias_uteis

_COLS_ESPERADAS = {
    "Produto", "Valor", "Meta", "Meta Diária", "Meta Diária Restante",
    "% Atingimento", "Quantidade", "Ticket Médio", "Valor Médio/Consultor",
    "Média DU", "Projeção", "% Projeção",
}


@pytest.mark.unit
class TestCalcularKpisPorProduto:
    def test_estrutura_e_grupos_ordenados(
        self, sample_pagos_produto_df, sample_metas_produto_df,
        sample_categorias_df, sem_feriados,
    ):
        res = calcular_kpis_por_produto(
            sample_pagos_produto_df, sample_metas_produto_df,
            sample_categorias_df, ano=2026, mes=3, dia_atual=16,
        )
        assert list(res["Produto"]) == ["CNC", "SAQUE"]  # sorted(grupos)
        assert _COLS_ESPERADAS.issubset(set(res.columns))

    def test_valores_agregados(
        self, sample_pagos_produto_df, sample_metas_produto_df,
        sample_categorias_df, sem_feriados,
    ):
        res = calcular_kpis_por_produto(
            sample_pagos_produto_df, sample_metas_produto_df,
            sample_categorias_df, ano=2026, mes=3, dia_atual=16,
        )
        cnc = res[res["Produto"] == "CNC"].iloc[0]
        # CNC: 1000 + 500 = 1500; quantidade conta só VALOR > 0
        assert cnc["Valor"] == pytest.approx(1500.0)
        assert cnc["Quantidade"] == 2
        assert cnc["Meta"] == pytest.approx(3000.0)
        assert cnc["% Atingimento"] == pytest.approx(50.0)
        assert cnc["Ticket Médio"] == pytest.approx(1500 / 2)
        # 4 consultores únicos (incluindo Ana, com VALOR 0)
        assert cnc["Valor Médio/Consultor"] == pytest.approx(1500 / 4)

        saque = res[res["Produto"] == "SAQUE"].iloc[0]
        assert saque["Valor"] == pytest.approx(800.0)
        assert saque["Quantidade"] == 1  # Ana (VALOR 0) não conta

    def test_metas_diarias_usam_dias_uteis(
        self, sample_pagos_produto_df, sample_metas_produto_df,
        sample_categorias_df, sem_feriados,
    ):
        du_total, du_dec, _ = calcular_dias_uteis(2026, 3, 16)
        res = calcular_kpis_por_produto(
            sample_pagos_produto_df, sample_metas_produto_df,
            sample_categorias_df, ano=2026, mes=3, dia_atual=16,
        )
        cnc = res[res["Produto"] == "CNC"].iloc[0]
        assert cnc["Meta Diária"] == pytest.approx(3000 / du_total)
        assert cnc["Média DU"] == pytest.approx(1500 / du_dec)
        assert cnc["Projeção"] == pytest.approx((1500 / du_dec) * du_total)

    def test_meta_ausente_nao_quebra(
        self, sample_pagos_produto_df, sample_categorias_df, sem_feriados,
    ):
        # df_metas_produto vazio → meta 0, sem ZeroDivisionError
        res = calcular_kpis_por_produto(
            sample_pagos_produto_df, pd.DataFrame(),
            sample_categorias_df, ano=2026, mes=3, dia_atual=16,
        )
        assert (res["% Atingimento"] == 0).all()
        assert (res["% Projeção"] == 0).all()

    def test_pack_permanece_agregado(self, sem_feriados):
        # Superficie com meta: a meta FGTS_ANT_BENEF_13 e conjunta, entao
        # o pack NAO se desmembra aqui (ao contrario dos quadros sem meta).
        df = pd.DataFrame({
            "CONSULTOR": ["João", "Maria", "João"],
            "grupo_dashboard": ["PACK", "PACK", "PACK"],
            "categoria_codigo": ["FGTS", "ANT_BENEF", "CNC_13"],
            "VALOR": [100.0, 200.0, 300.0],
        })
        categorias = pd.DataFrame({
            "codigo": ["FGTS", "ANT_BENEF", "CNC_13"],
            "grupo_dashboard": ["PACK", "PACK", "PACK"],
            "grupo_meta": ["FGTS_ANT_BENEF_13"] * 3,
        })
        metas = pd.DataFrame({"FGTS_ANT_BENEF_13": [1200.0]})
        res = calcular_kpis_por_produto(
            df, metas, categorias, ano=2026, mes=3, dia_atual=16,
        )
        assert list(res["Produto"]) == ["PACK"]
        assert res.iloc[0]["Valor"] == pytest.approx(600.0)
        assert res.iloc[0]["Meta"] == pytest.approx(1200.0)
        assert res.iloc[0]["% Atingimento"] == pytest.approx(50.0)


@pytest.mark.unit
class TestCanonizarBanco:
    """Canonizacao de ``BANCO`` — base a rigor de variantes de grafia.

    Alimenta o seletor de banco da Distribuicao de Produtos: sem ela,
    "BMG" e "BANCO BMG" virariam duas opcoes partindo o mesmo banco.
    """

    def test_normaliza_strip_e_caixa(self):
        assert canonizar_banco("  bmg ") == "BMG"

    def test_funde_prefixo_banco(self):
        assert canonizar_banco("BANCO BMG") == "BMG"
        assert canonizar_banco("BANCO HELP") == "HELP"

    def test_funde_variantes_de_c6_e_itau(self):
        assert canonizar_banco("C6 BANK") == "C6"
        assert canonizar_banco("BANCO C6") == "C6"
        assert canonizar_banco("ITAÚ") == "ITAU"
        assert canonizar_banco("BANCO ITAÚ") == "ITAU"

    def test_itau_360_nao_funde_com_itau(self):
        # Canal proprio na base, nao alias — fundir seria decisao de
        # negocio, nao de normalizacao.
        assert canonizar_banco("ITAU-360") == "ITAU-360"

    def test_desconhecido_volta_so_normalizado(self):
        # Canonizar nunca descarta banco.
        assert canonizar_banco(" vctex ") == "VCTEX"

    def test_preset_bmg_help_e_canonico(self):
        assert BANCOS_BMG_HELP == ("BMG", "HELP")


@pytest.mark.unit
class TestOpcoesBanco:
    def test_dedup_canonico_e_ordenado(self):
        df = pd.DataFrame({
            "BANCO": ["BANCO BMG", "BMG", "C6 BANK", "C6", "MASTER"],
        })
        assert opcoes_banco(df) == ["BMG", "C6", "MASTER"]

    def test_ignora_nulo_e_vazio(self):
        df = pd.DataFrame({"BANCO": ["BMG", None, "", "   ", "HELP"]})
        assert opcoes_banco(df) == ["BMG", "HELP"]

    def test_coluna_ausente_retorna_vazio(self):
        assert opcoes_banco(pd.DataFrame({"X": [1]})) == []

    def test_df_vazio_retorna_vazio(self):
        assert opcoes_banco(pd.DataFrame(columns=["BANCO"])) == []


@pytest.mark.unit
class TestCalcularDistribuicaoProdutos:
    def test_sem_coluna_consultor_retorna_vazio(self):
        distrib, moeda, numero = calcular_distribuicao_produtos(
            pd.DataFrame({"VALOR": [100.0]})
        )
        assert distrib.empty
        assert moeda == []
        assert numero == []

    def test_distribuicao_valor_total_e_ordenacao(self):
        df = pd.DataFrame({
            "CONSULTOR": ["João", "Maria"],
            "grupo_dashboard": ["CNC", "SAQUE"],
            "VALOR": [1000.0, 500.0],
            "TIPO_PRODUTO": ["CNC", "SAQUE"],
        })
        distrib, moeda, numero = calcular_distribuicao_produtos(df)
        assert "TOTAL" in distrib.columns
        # ordenado por TOTAL desc → João (1000) primeiro
        assert distrib.iloc[0]["CONSULTOR"] == "João"
        assert distrib["TOTAL"].tolist() == [1000.0, 500.0]
        assert set(moeda) >= {"CNC", "SAQUE", "TOTAL"}
        assert numero == []

    def test_pack_vira_uma_coluna_por_categoria(self):
        # Distribuicao nao compara com meta → PACK desmembrado.
        df = pd.DataFrame({
            "CONSULTOR": ["João", "João", "Maria"],
            "grupo_dashboard": ["PACK", "PACK", "PACK"],
            "categoria_codigo": ["FGTS", "CNC_13", "ANT_BENEF"],
            "VALOR": [1000.0, 300.0, 500.0],
            "TIPO_PRODUTO": ["FGTS", "CNC 13º", "ANT. DE BENEF."],
        })
        distrib, moeda, _ = calcular_distribuicao_produtos(df)
        assert {"FGTS", "CNC 13º", "ANT. DE BENEF."}.issubset(set(moeda))
        joao = distrib[distrib["CONSULTOR"] == "João"].iloc[0]
        assert joao["FGTS"] == pytest.approx(1000.0)
        assert joao["CNC 13º"] == pytest.approx(300.0)
        assert joao["TOTAL"] == pytest.approx(1300.0)

    def test_aceleradores_contados_por_quantidade(self):
        df = pd.DataFrame({
            "CONSULTOR": ["João", "João", "Maria"],
            "grupo_dashboard": ["CNC", None, "CNC"],
            "VALOR": [1000.0, 0.0, 500.0],
            "TIPO_PRODUTO": ["CNC", "BMG MED", "CNC"],
            "is_bmg_med": [False, True, False],
        })
        distrib, _, numero = calcular_distribuicao_produtos(df)
        assert "BMG Med" in numero
        joao = distrib[distrib["CONSULTOR"] == "João"].iloc[0]
        assert joao["BMG Med"] == 1

    def test_clt_conta_consig_priv_exclui_seguro_prestamista(self):
        # João: 1 linha CONSIG_PRIV valida (Emprestimo) + 1 Seguro
        # Prestamista em minusculo (nao conta, prova normalizacao).
        # Maria: CONSIG_PRIV com "SEGURO PRESTAMISTA" ja maiusculo (nao
        # conta).
        df = pd.DataFrame({
            "CONSULTOR": ["João", "João", "Maria"],
            "grupo_dashboard": ["CLT", "CLT", "CLT"],
            "categoria_codigo": ["CONSIG_PRIV", "CONSIG_PRIV", "CONSIG_PRIV"],
            "TIPO OPER.": ["Emprestimo", "seguro prestamista", "SEGURO PRESTAMISTA"],
            "VALOR": [1000.0, 500.0, 300.0],
            "TIPO_PRODUTO": ["CLT", "CLT", "CLT"],
        })
        distrib, _, numero = calcular_distribuicao_produtos(df)
        assert "CLT (Qtd)" in numero
        joao = distrib[distrib["CONSULTOR"] == "João"].iloc[0]
        assert joao["CLT (Qtd)"] == 1
        maria = distrib[distrib["CONSULTOR"] == "Maria"].iloc[0]
        assert maria["CLT (Qtd)"] == 0

    def test_consignado_normaliza_subtipo_exclui_portabilidade_e_margem(self):
        # João: "novo " (CONSIG_BMG) e " Refin" (CONSIG_ITAU) contam,
        # espaco/capitalizacao variados provam a normalizacao;
        # PORTABILIDADE com SUBTIPO=REFIN NAO conta (categoria_codigo
        # continua PORTABILIDADE, nunca vira CONSIG_*).
        # Maria: SUBTIPO=MARGEM COMPLEMENTAR nao e Novo nem Refin, nao
        # conta.
        df = pd.DataFrame({
            "CONSULTOR": ["João", "João", "João", "Maria"],
            "grupo_dashboard": ["CONSIGNADO"] * 4,
            "categoria_codigo": [
                "CONSIG_BMG", "CONSIG_ITAU", "PORTABILIDADE", "CONSIG_C6",
            ],
            "SUBTIPO": ["novo ", " Refin", "REFIN", "MARGEM COMPLEMENTAR"],
            "VALOR": [1000.0, 1200.0, 900.0, 700.0],
            "TIPO_PRODUTO": ["CONSIGNADO"] * 4,
        })
        distrib, _, numero = calcular_distribuicao_produtos(df)
        assert "Consignado (Novo/Refin)" in numero
        joao = distrib[distrib["CONSULTOR"] == "João"].iloc[0]
        assert joao["Consignado (Novo/Refin)"] == 2
        maria = distrib[distrib["CONSULTOR"] == "Maria"].iloc[0]
        assert maria["Consignado (Novo/Refin)"] == 0

    def _df_tres_bancos(self):
        # João: BMG. Maria: C6. Ana: HELP. Cada um com uma linha de
        # valor (CNC) e uma de Consignado.
        return pd.DataFrame({
            "CONSULTOR": ["João", "João", "Maria", "Maria", "Ana", "Ana"],
            "grupo_dashboard": [
                "CNC", "CONSIGNADO", "CNC", "CONSIGNADO", "CNC", "CONSIGNADO",
            ],
            "categoria_codigo": [
                None, "CONSIG_BMG", None, "CONSIG_C6", None, "CONSIG_BMG",
            ],
            "SUBTIPO": [None, "NOVO", None, "NOVO", None, "NOVO"],
            "BANCO": ["BMG", "BMG", "C6 BANK", "C6 BANK", "HELP", "HELP"],
            "VALOR": [1000.0, 500.0, 800.0, 400.0, 600.0, 300.0],
            "TIPO_PRODUTO": [
                "CNC", "CONSIGNADO", "CNC", "CONSIGNADO", "CNC", "CONSIGNADO",
            ],
        })

    def test_bancos_none_nao_recorta(self):
        # Default (None) preserva o comportamento de "Todos": ninguém
        # some, nem precisa da coluna BANCO existir.
        distrib, _, _ = calcular_distribuicao_produtos(self._df_tres_bancos())
        assert set(distrib["CONSULTOR"]) == {"João", "Maria", "Ana"}
        assert distrib["TOTAL"].sum() == pytest.approx(3600.0)

    def test_banco_unico_restringe_tabela_inteira(self):
        # Um banco só: recorta valor E quantidade (e o TOTAL) juntos —
        # quem não é do banco some inteiro da tabela.
        distrib, _, numero = calcular_distribuicao_produtos(
            self._df_tres_bancos(), bancos=("BMG",)
        )
        assert set(distrib["CONSULTOR"]) == {"João"}
        joao = distrib.iloc[0]
        assert joao["TOTAL"] == pytest.approx(1500.0)
        assert joao["Consignado (Novo/Refin)"] == 1
        assert "Consignado (Novo/Refin)" in numero

    def test_preset_bmg_help_soma_os_dois_bancos(self):
        # O preset composto continua existindo e mantém o alcance de
        # antes: BMG + Help juntos, C6 fora.
        distrib, _, _ = calcular_distribuicao_produtos(
            self._df_tres_bancos(), bancos=BANCOS_BMG_HELP
        )
        assert set(distrib["CONSULTOR"]) == {"João", "Ana"}
        assert distrib["TOTAL"].sum() == pytest.approx(2400.0)

    def test_banco_canonizado_casa_variantes_da_base(self):
        # "C6 BANK" na base e "C6" no seletor são o mesmo banco; idem
        # "BANCO BMG" x "BMG". A canonização acontece nos dois lados.
        df = self._df_tres_bancos()
        distrib, _, _ = calcular_distribuicao_produtos(df, bancos=("C6",))
        assert set(distrib["CONSULTOR"]) == {"Maria"}

        df_prefixado = df.copy()
        df_prefixado["BANCO"] = df_prefixado["BANCO"].replace(
            {"BMG": "  banco bmg "}
        )
        distrib_pref, _, _ = calcular_distribuicao_produtos(
            df_prefixado, bancos=("BMG",)
        )
        assert set(distrib_pref["CONSULTOR"]) == {"João"}

    def test_banco_ausente_com_recorte_zera_tabela_inteira(self):
        # Sem coluna BANCO no frame, qualquer recorte de banco zera tudo
        # (mesma regra de "criterio sem coluna zera a contagem").
        df = pd.DataFrame({
            "CONSULTOR": ["João", "Maria"],
            "grupo_dashboard": ["CNC", "CNC"],
            "VALOR": [1000.0, 500.0],
            "TIPO_PRODUTO": ["CNC", "CNC"],
        })
        distrib, moeda, numero = calcular_distribuicao_produtos(
            df, bancos=BANCOS_BMG_HELP
        )
        assert distrib.empty
        # Comportamento observado: sobra so a coluna TOTAL (0 linhas),
        # sem colunas de valor nem de quantidade.
        assert list(distrib.columns) == ["CONSULTOR", "TOTAL"]
        assert moeda == ["TOTAL"]
        assert numero == []

    def test_colisao_nome_clt_valor_e_clt_qtd_nao_se_suprimem(self):
        # grupo_dashboard="CLT" produz a coluna de VALOR "CLT" (via
        # PRODUTO_MIX) e a linha tambem bate no criterio de CLT (Qtd).
        # Antes do sufixo " (Qtd)" as duas colunas homonimas colidiam no
        # merge (CLT_x/CLT_y) e AS DUAS desapareciam — TOTAL zerava
        # silenciosamente. Este teste falha se a colisão for
        # reintroduzida.
        df = pd.DataFrame({
            "CONSULTOR": ["João"],
            "grupo_dashboard": ["CLT"],
            "categoria_codigo": ["CONSIG_PRIV"],
            "TIPO OPER.": ["Emprestimo"],
            "VALOR": [1500.0],
            "TIPO_PRODUTO": ["CLT"],
        })
        distrib, moeda, numero = calcular_distribuicao_produtos(df)
        assert "CLT" in distrib.columns
        assert "CLT (Qtd)" in distrib.columns
        joao = distrib.iloc[0]
        assert joao["CLT"] == pytest.approx(1500.0)
        assert joao["CLT (Qtd)"] == 1
        assert joao["TOTAL"] == pytest.approx(1500.0)
        assert "CLT" in moeda
        assert "CLT (Qtd)" in numero


@pytest.mark.unit
class TestCalcularDistribuicaoProdutosPorLoja:
    def test_sem_coluna_loja_retorna_vazio(self):
        distrib, moeda, numero = calcular_distribuicao_produtos_por_loja(
            pd.DataFrame({"VALOR": [100.0]})
        )
        assert distrib.empty
        assert moeda == []
        assert numero == []

    def test_distribuicao_por_loja_agrega_e_ordena(self):
        # Loja A: João (CNC 1000) + Maria (SAQUE 500) = 1500
        # Loja B: Pedro (CNC 2000)
        df = pd.DataFrame({
            "LOJA": ["A", "A", "B"],
            "CONSULTOR": ["João", "Maria", "Pedro"],
            "grupo_dashboard": ["CNC", "SAQUE", "CNC"],
            "VALOR": [1000.0, 500.0, 2000.0],
            "TIPO_PRODUTO": ["CNC", "SAQUE", "CNC"],
        })
        distrib, moeda, numero = calcular_distribuicao_produtos_por_loja(df)
        assert "TOTAL" in distrib.columns
        assert "CONSULTOR" not in distrib.columns  # agregado por loja, não consultor
        # ordenado por TOTAL desc → Loja B (2000) primeiro
        assert distrib.iloc[0]["LOJA"] == "B"
        assert distrib["TOTAL"].tolist() == [2000.0, 1500.0]
        assert set(moeda) >= {"CNC", "SAQUE", "TOTAL"}
        assert numero == []

    def test_producao_supervisor_soma_no_total_da_loja(self, sample_supervisores_df):
        # João (CNC 1000) e Chefe/supervisor (SAQUE 500), ambos na Loja A.
        df = pd.DataFrame({
            "CONSULTOR": ["João", "Chefe"],
            "LOJA": ["A", "A"],
            "grupo_dashboard": ["CNC", "SAQUE"],
            "VALOR": [1000.0, 500.0],
            "TIPO_PRODUTO": ["CNC", "SAQUE"],
        })
        # Visão por consultor exclui o supervisor do total (excluir_supervisores).
        distrib_consultor, _, _ = calcular_distribuicao_produtos(
            df, df_supervisores=sample_supervisores_df
        )
        assert distrib_consultor["TOTAL"].sum() == pytest.approx(1000.0)
        assert "Chefe" not in distrib_consultor["CONSULTOR"].tolist()

        # Visão por loja NÃO exclui supervisor: produção soma no total da loja.
        distrib_loja, _, _ = calcular_distribuicao_produtos_por_loja(df)
        loja_a = distrib_loja[distrib_loja["LOJA"] == "A"].iloc[0]
        assert loja_a["TOTAL"] == pytest.approx(1500.0)

    def test_pack_vira_uma_coluna_por_categoria_por_loja(self):
        # Distribuicao nao compara com meta → PACK desmembrado, por loja.
        df = pd.DataFrame({
            "LOJA": ["A", "A", "B"],
            "CONSULTOR": ["João", "João", "Maria"],
            "grupo_dashboard": ["PACK", "PACK", "PACK"],
            "categoria_codigo": ["FGTS", "CNC_13", "ANT_BENEF"],
            "VALOR": [1000.0, 300.0, 500.0],
            "TIPO_PRODUTO": ["FGTS", "CNC 13º", "ANT. DE BENEF."],
        })
        distrib, moeda, _ = calcular_distribuicao_produtos_por_loja(df)
        assert {"FGTS", "CNC 13º", "ANT. DE BENEF."}.issubset(set(moeda))
        loja_a = distrib[distrib["LOJA"] == "A"].iloc[0]
        assert loja_a["FGTS"] == pytest.approx(1000.0)
        assert loja_a["CNC 13º"] == pytest.approx(300.0)
        assert loja_a["TOTAL"] == pytest.approx(1300.0)

    def test_aceleradores_contados_por_quantidade_por_loja(self):
        df = pd.DataFrame({
            "LOJA": ["A", "A", "B"],
            "CONSULTOR": ["João", "João", "Maria"],
            "grupo_dashboard": ["CNC", None, "CNC"],
            "VALOR": [1000.0, 0.0, 500.0],
            "TIPO_PRODUTO": ["CNC", "BMG MED", "CNC"],
            "is_bmg_med": [False, True, False],
        })
        distrib, _, numero = calcular_distribuicao_produtos_por_loja(df)
        assert "BMG Med" in numero
        loja_a = distrib[distrib["LOJA"] == "A"].iloc[0]
        assert loja_a["BMG Med"] == 1

    def test_loja_com_regiao_variavel_nao_duplica(self):
        # Mesma LOJA aparece com duas REGIAO diferentes (troca de região no
        # meio do período) — drop_duplicates("LOJA") deve manter 1 única
        # linha, ficando com a primeira região observada no frame (R1).
        df = pd.DataFrame({
            "LOJA": ["A", "A"],
            "REGIAO": ["R1", "R2"],
            "CONSULTOR": ["João", "Maria"],
            "grupo_dashboard": ["CNC", "SAQUE"],
            "VALOR": [1000.0, 500.0],
            "TIPO_PRODUTO": ["CNC", "SAQUE"],
        })
        distrib, _, _ = calcular_distribuicao_produtos_por_loja(df)
        assert len(distrib) == 1
        assert distrib.iloc[0]["LOJA"] == "A"
        assert distrib.iloc[0]["REGIAO"] == "R1"
        assert distrib.iloc[0]["TOTAL"] == pytest.approx(1500.0)

    def test_clt_e_consignado_contados_por_loja(self):
        # Loja A: CLT valido (Emprestimo) conta; CLT com Seguro
        # Prestamista (minusculo, prova normalizacao) nao conta.
        # Loja B: Consignado "novo " (CONSIG_BMG, espaco/caixa variados)
        # conta; PORTABILIDADE com SUBTIPO=REFIN nao conta.
        df = pd.DataFrame({
            "LOJA": ["A", "A", "B", "B"],
            "grupo_dashboard": ["CLT", "CLT", "CONSIGNADO", "CONSIGNADO"],
            "categoria_codigo": [
                "CONSIG_PRIV", "CONSIG_PRIV", "CONSIG_BMG", "PORTABILIDADE",
            ],
            "TIPO OPER.": ["Emprestimo", "seguro prestamista", "N/A", "N/A"],
            "SUBTIPO": [None, None, "novo ", "REFIN"],
            "VALOR": [1000.0, 500.0, 700.0, 900.0],
            "TIPO_PRODUTO": ["CLT", "CLT", "CONSIGNADO", "CONSIGNADO"],
        })
        distrib, _, numero = calcular_distribuicao_produtos_por_loja(df)
        assert {"CLT (Qtd)", "Consignado (Novo/Refin)"}.issubset(set(numero))
        loja_a = distrib[distrib["LOJA"] == "A"].iloc[0]
        assert loja_a["CLT (Qtd)"] == 1
        loja_b = distrib[distrib["LOJA"] == "B"].iloc[0]
        assert loja_b["Consignado (Novo/Refin)"] == 1

    def test_recorte_de_banco_restringe_tabela_inteira_por_loja(self):
        # Loja A: BMG. Loja B: ITAÚ (acentuado — canoniza para ITAU).
        df = pd.DataFrame({
            "LOJA": ["A", "A", "B", "B"],
            "grupo_dashboard": ["CNC", "CONSIGNADO", "CNC", "CONSIGNADO"],
            "categoria_codigo": [None, "CONSIG_BMG", None, "CONSIG_ITAU"],
            "SUBTIPO": [None, "NOVO", None, "REFIN"],
            "BANCO": ["BMG", "BMG", "BANCO ITAÚ", "BANCO ITAÚ"],
            "VALOR": [1000.0, 500.0, 800.0, 400.0],
            "TIPO_PRODUTO": ["CNC", "CONSIGNADO", "CNC", "CONSIGNADO"],
        })
        # None = "Todos": sem recorte.
        distrib_off, _, _ = calcular_distribuicao_produtos_por_loja(df)
        assert set(distrib_off["LOJA"]) == {"A", "B"}

        # Preset BMG/Help mantém o alcance de antes.
        distrib_on, _, numero_on = calcular_distribuicao_produtos_por_loja(
            df, bancos=BANCOS_BMG_HELP
        )
        assert set(distrib_on["LOJA"]) == {"A"}
        loja_a = distrib_on.iloc[0]
        assert loja_a["TOTAL"] == pytest.approx(1500.0)
        assert loja_a["Consignado (Novo/Refin)"] == 1
        assert "Consignado (Novo/Refin)" in numero_on

        # Banco único, canonizado: "BANCO ITAÚ" na base casa com "ITAU".
        distrib_itau, _, _ = calcular_distribuicao_produtos_por_loja(
            df, bancos=("ITAU",)
        )
        assert set(distrib_itau["LOJA"]) == {"B"}
        assert distrib_itau.iloc[0]["TOTAL"] == pytest.approx(1200.0)

    def test_banco_ausente_com_recorte_zera_tabela_inteira_por_loja(self):
        df = pd.DataFrame({
            "LOJA": ["A", "B"],
            "grupo_dashboard": ["CNC", "CNC"],
            "VALOR": [1000.0, 500.0],
            "TIPO_PRODUTO": ["CNC", "CNC"],
        })
        distrib, moeda, numero = calcular_distribuicao_produtos_por_loja(
            df, bancos=("BMG",)
        )
        assert distrib.empty
        assert list(distrib.columns) == ["LOJA", "TOTAL"]
        assert moeda == ["TOTAL"]
        assert numero == []

    def test_colisao_nome_clt_valor_e_clt_qtd_nao_se_suprimem_por_loja(self):
        # Mesma regressão de TestCalcularDistribuicaoProdutos, na visão
        # por loja (implementação própria, mesmo literal "CLT (Qtd)").
        df = pd.DataFrame({
            "LOJA": ["A"],
            "grupo_dashboard": ["CLT"],
            "categoria_codigo": ["CONSIG_PRIV"],
            "TIPO OPER.": ["Emprestimo"],
            "VALOR": [1500.0],
            "TIPO_PRODUTO": ["CLT"],
        })
        distrib, moeda, numero = calcular_distribuicao_produtos_por_loja(df)
        assert "CLT" in distrib.columns
        assert "CLT (Qtd)" in distrib.columns
        loja_a = distrib.iloc[0]
        assert loja_a["CLT"] == pytest.approx(1500.0)
        assert loja_a["CLT (Qtd)"] == 1
        assert loja_a["TOTAL"] == pytest.approx(1500.0)
        assert "CLT" in moeda
        assert "CLT (Qtd)" in numero
