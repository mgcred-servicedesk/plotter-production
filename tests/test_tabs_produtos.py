"""
Testes dos helpers puros de contagem em ``src/dashboard/tabs/produtos.py``
(``_norm``, ``_mask_falsa``, ``_mask_subtab``, ``_mask_banco``) — o mask
builder das abas de "Emissão e Seguros — Análise Regional", incluindo os
novos itens CLT e Consignado (Novo/Refin) e a flag "Somente BMG/Help" —
e do render dessas abas (``_render_produto_regional``), via
``streamlit.testing.v1.AppTest``.

Ver
``docs/agents/progress/2026-08-06-plano-clt-consignado-emissao-seguros.md``
para a especificação de negócio (ST-01) e a decisão de implementação
(ST-02) por trás dos testes de mask (ST-03). O caso mais importante do
mask builder é a exclusão automática de Portabilidade/Refin-da-
Portabilidade em Consignado: essas linhas mantêm
``categoria_codigo == "PORTABILIDADE"`` mesmo tendo ``SUBTIPO`` igual a
Novo/Refin, então o filtro por ``categoria_codigo`` já as exclui sem
lógica extra.

As classes ``TestComposicaoMaskSubtabBanco`` e
``TestRenderProdutoRegionalFiltroBanco`` (ST-07) cobrem o bug reportado
na ST-05 e corrigido na ST-06: antes, a flag "Somente BMG/Help" só
filtrava o KPI do topo — as tabelas por região/loja/consultor abaixo
continuavam com todos os bancos, o que deixava o perfil
``gerente_comercial`` (cuja visão principal É a tabela) sem conseguir
filtrar a produção de fato. A correção fez ``_render_total_produto``
devolver a máscara de banco já aplicada, que ``_render_produto_regional``
agora combina (AND) com a máscara de cada subtab antes de alimentar
tanto ``_contar_por_regiao`` quanto ``_contar_por_loja_consultor``.
"""
import re

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from src.dashboard.tabs.produtos import (
    _BANCOS_BMG_HELP,
    _PREFIXOS_COMPARATIVO,
    _PRODS_QTD,
    _contar_por_loja_consultor,
    _contar_por_regiao,
    _mask_banco,
    _mask_falsa,
    _mask_subtab,
    _mask_supervisor,
    _mes_comparativo_full,
    _norm,
    limpar_cache_comparativos,
)


def _cfg(label: str) -> dict:
    """Busca a config de uma aba de ``_PRODS_QTD`` pelo rótulo."""
    return next(p for p in _PRODS_QTD if p["label"] == label)


@pytest.mark.unit
class TestNorm:
    def test_normaliza_espaco_e_caixa(self):
        serie = pd.Series([" bmg ", "Help", "C6 Bank", "refin "])
        assert _norm(serie).tolist() == [
            "BMG", "HELP", "C6 BANK", "REFIN",
        ]


@pytest.mark.unit
class TestMaskFalsa:
    def test_mascara_toda_falsa_alinhada_ao_indice(self):
        df = pd.DataFrame({"X": [1, 2, 3]}, index=[10, 20, 30])
        mask = _mask_falsa(df)
        assert mask.tolist() == [False, False, False]
        assert mask.index.tolist() == [10, 20, 30]


@pytest.mark.unit
class TestMaskSubtab:
    # ── Não-regressão das 4 abas antigas ────────────────────────
    # tipo_oper e subtipo isolados devem se comportar exatamente como
    # o if/else inline que existia antes de _mask_subtab existir.

    def test_nao_regressao_tipo_oper_emissao_cartao_beneficio(self):
        sub = _cfg("Emissão")["subtabs"][0]
        valor = sub["tipo_oper"][0]
        df = pd.DataFrame({
            "TIPO OPER.": [
                valor, valor.lower(), "Venda Pré-Adesão", "Outro",
            ],
        })
        assert _mask_subtab(df, sub).tolist() == [
            True, False, False, False,
        ]

    def test_nao_regressao_tipo_oper_emissao_venda_pre_adesao(self):
        sub = _cfg("Emissão")["subtabs"][1]
        valor = sub["tipo_oper"][0]
        df = pd.DataFrame({
            "TIPO OPER.": [valor, "CARTÃO BENEFICIO", "Outro"],
        })
        assert _mask_subtab(df, sub).tolist() == [True, False, False]

    def test_nao_regressao_tipo_oper_bmg_med(self):
        sub = _cfg("BMG Med")["subtabs"][0]
        valor = sub["tipo_oper"][0]
        df = pd.DataFrame({
            "TIPO OPER.": [valor, valor.lower(), "Outro"],
        })
        assert _mask_subtab(df, sub).tolist() == [True, False, False]

    def test_nao_regressao_tipo_oper_vida_familiar(self):
        sub = _cfg("Vida Familiar")["subtabs"][0]
        valor = sub["tipo_oper"][0]
        df = pd.DataFrame({
            "TIPO OPER.": [valor, valor.lower(), "Outro"],
        })
        assert _mask_subtab(df, sub).tolist() == [True, False, False]

    def test_nao_regressao_subtipo_super_conta(self):
        sub = _cfg("Super Conta")["subtabs"][0]
        df = pd.DataFrame({
            "SUBTIPO": [
                "SUPER CONTA", "super conta ", " Super Conta", "OUTRO",
            ],
        })
        # subtipo (diferente de tipo_oper) É normalizado
        assert _mask_subtab(df, sub).tolist() == [
            True, True, True, False,
        ]

    # ── CLT ──────────────────────────────────────────────────────

    def test_clt_conta_categoria_consig_priv(self):
        sub = _cfg("CLT")["subtabs"][0]
        df = pd.DataFrame({
            "categoria_codigo": ["CONSIG_PRIV", "CONSIG_PRIV", "CNC"],
            "TIPO OPER.": ["Emprestimo", "Emprestimo", "Emprestimo"],
        })
        assert _mask_subtab(df, sub).tolist() == [True, True, False]

    def test_clt_exclui_seguro_prestamista_variacoes_caixa_espaco(self):
        sub = _cfg("CLT")["subtabs"][0]
        df = pd.DataFrame({
            "categoria_codigo": ["CONSIG_PRIV"] * 4,
            "TIPO OPER.": [
                "Seguro Prestamista",
                " seguro prestamista ",
                "SEGURO PRESTAMISTA",
                "Emprestimo",
            ],
        })
        assert _mask_subtab(df, sub).tolist() == [
            False, False, False, True,
        ]

    def test_clt_sem_coluna_tipo_oper_nao_quebra_e_zera_contagem(self):
        # Prova o item mais sensível do comportamento defensivo: sem
        # "TIPO OPER." não dá para provar a exclusão do Seguro
        # Prestamista, então o critério inteiro zera (AND com False),
        # mesmo com categoria batendo.
        sub = _cfg("CLT")["subtabs"][0]
        df = pd.DataFrame({
            "categoria_codigo": ["CONSIG_PRIV", "CONSIG_PRIV"],
        })
        assert _mask_subtab(df, sub).tolist() == [False, False]

    # ── Consignado (Novo/Refin) ─────────────────────────────────

    def test_consignado_conta_bmg_itau_c6_novo_refin_normalizado(self):
        sub = _cfg("Consignado (Novo/Refin)")["subtabs"][0]
        df = pd.DataFrame({
            "categoria_codigo": [
                "CONSIG_BMG", "CONSIG_ITAU", "CONSIG_C6", "CONSIG_BMG",
            ],
            "SUBTIPO": ["NOVO", "REFIN", "refin ", "novo"],
        })
        assert _mask_subtab(df, sub).tolist() == [
            True, True, True, True,
        ]

    def test_consignado_exclui_portabilidade_mesmo_com_subtipo_novo_refin(
        self,
    ):
        # Caso mais importante do plano: Portabilidade e Refin da
        # Portabilidade carregam SUBTIPO igual a Novo/Refin, mas
        # categoria_codigo continua "PORTABILIDADE" — o filtro por
        # categoria já exclui as duas sem lógica extra.
        sub = _cfg("Consignado (Novo/Refin)")["subtabs"][0]
        df = pd.DataFrame({
            "categoria_codigo": [
                "PORTABILIDADE", "PORTABILIDADE", "CONSIG_BMG",
            ],
            "SUBTIPO": ["NOVO", "REFIN", "NOVO"],
        })
        assert _mask_subtab(df, sub).tolist() == [
            False, False, True,
        ]

    def test_consignado_exclui_margem_complementar(self):
        sub = _cfg("Consignado (Novo/Refin)")["subtabs"][0]
        df = pd.DataFrame({
            "categoria_codigo": ["CONSIG_BMG", "CONSIG_BMG"],
            "SUBTIPO": ["MARGEM COMPLEMENTAR", "NOVO"],
        })
        assert _mask_subtab(df, sub).tolist() == [False, True]

    # ── Coluna ausente zera o critério (defensivo, por tipo) ────

    def test_coluna_tipo_oper_ausente_zera_criterio_tipo_oper(self):
        sub = {"tipo_oper": ["CARTÃO BENEFICIO"]}
        df = pd.DataFrame({"OUTRA": [1, 2]})
        assert _mask_subtab(df, sub).tolist() == [False, False]

    def test_coluna_subtipo_ausente_zera_criterio_subtipo(self):
        sub = {"subtipo": "SUPER CONTA"}
        df = pd.DataFrame({"OUTRA": [1, 2]})
        assert _mask_subtab(df, sub).tolist() == [False, False]

    def test_coluna_categoria_ausente_zera_criterio_categoria(self):
        sub = {"categoria": ["CONSIG_PRIV"]}
        df = pd.DataFrame({"OUTRA": [1, 2]})
        assert _mask_subtab(df, sub).tolist() == [False, False]

    def test_coluna_subtipo_ausente_zera_criterio_subtipos(self):
        sub = {"subtipos": ["NOVO", "REFIN"]}
        df = pd.DataFrame({"OUTRA": [1, 2]})
        assert _mask_subtab(df, sub).tolist() == [False, False]

    def test_sem_criterios_retorna_mascara_falsa(self):
        df = pd.DataFrame({"X": [1, 2, 3]})
        assert _mask_subtab(df, {}).tolist() == [False, False, False]


@pytest.mark.unit
class TestMaskBanco:
    def test_flag_bmg_help_aceita_variacoes_normalizadas(self):
        df = pd.DataFrame({
            "BANCO": [
                "BMG", "Banco Bmg", "HELP", "banco help",
                "C6 BANK", "ITAU-360",
            ],
        })
        mask = _mask_banco(df, _BANCOS_BMG_HELP)
        assert mask.tolist() == [
            True, True, True, True, False, False,
        ]

    def test_coluna_banco_ausente_retorna_mascara_falsa(self):
        df = pd.DataFrame({"X": [1, 2]})
        assert _mask_banco(df, _BANCOS_BMG_HELP).tolist() == [
            False, False,
        ]


@pytest.mark.unit
class TestMaskSupervisor:
    """``_mask_supervisor`` identifica linhas de produção de supervisor
    dentro do frame — usada tanto pela legenda do KPI de total quanto
    pela separação da linha "(Supervisor)" na visão por consultor (ver
    ``TestRenderProdutoRegionalProducaoSupervisor``).
    """

    def test_marca_linhas_de_supervisor_conhecido(self):
        df = pd.DataFrame({
            "CONSULTOR": ["Joao", "Maria", "Chefe Supervisor"],
        })
        mask = _mask_supervisor(df, {"CHEFE SUPERVISOR"})
        assert mask.tolist() == [False, False, True]

    def test_supervisores_norm_vazio_retorna_mascara_falsa(self):
        df = pd.DataFrame({
            "CONSULTOR": ["Joao", "Chefe Supervisor"],
        })
        assert _mask_supervisor(df, set()).tolist() == [False, False]

    def test_coluna_consultor_ausente_retorna_mascara_falsa(self):
        df = pd.DataFrame({"OUTRA": [1, 2]})
        assert _mask_supervisor(
            df, {"CHEFE SUPERVISOR"}
        ).tolist() == [False, False]

    def test_normaliza_espaco_e_caixa_para_comparar(self):
        df = pd.DataFrame({
            "CONSULTOR": [
                " chefe supervisor ",
                "CHEFE SUPERVISOR",
                "Chefe Supervisor",
                "Outro",
            ],
        })
        mask = _mask_supervisor(df, {"CHEFE SUPERVISOR"})
        assert mask.tolist() == [True, True, True, False]


@pytest.mark.unit
class TestComposicaoMaskSubtabBanco:
    """ST-07 — ponto cego da ST-03: ela testava ``_mask_subtab`` e
    ``_mask_banco`` isoladas, nunca a composição ``mask & mask_banco``
    que ``_render_produto_regional`` agora aplica (ST-06) antes de
    alimentar tanto o KPI quanto as tabelas. Aqui provamos que a
    composição das duas máscaras reais do módulo produz o mesmo total
    que ``_contar_por_regiao``/``_contar_por_loja_consultor`` enxergam
    quando recebem essa máscara composta — sem depender de Streamlit.

    O comportamento de render (widget ligado/desligado, região que
    some da tela, consultor que fica zerado mas não some) é coberto à
    parte em ``TestRenderProdutoRegionalFiltroBanco``, via ``AppTest``.
    """

    def test_consignado_composicao_bate_kpi_e_tabela_por_regiao(self):
        sub = _cfg("Consignado (Novo/Refin)")["subtabs"][0]
        cfg_banco = _cfg("Consignado (Novo/Refin)")["toggle_banco"]
        df = pd.DataFrame({
            "categoria_codigo": [
                "CONSIG_BMG", "CONSIG_BMG", "CONSIG_BMG",
            ],
            "SUBTIPO": ["NOVO", "NOVO", "NOVO"],
            "BANCO": ["BMG", "C6 BANK", "C6 BANK"],
            "REGIAO": ["R1", "R1", "R2"],
            "LOJA": ["L1", "L1", "L2"],
        })
        mask_subtab = _mask_subtab(df, sub)
        mask_banco = _mask_banco(df, cfg_banco["bancos"])
        mask_composta = mask_subtab & mask_banco

        # Linha BMG conta; as duas C6 BANK (uma na mesma loja da BMG,
        # outra sozinha em R2/L2) ficam de fora.
        assert mask_composta.tolist() == [True, False, False]

        tabela = _contar_por_regiao(
            df, mask_composta, sub["nome_col"],
        )
        # KPI (soma da mascara) bate com o total que a tabela exibiria.
        assert int(tabela[sub["nome_col"]].sum()) == int(
            mask_composta.sum()
        )
        # R2/L2 so tinha a linha C6 BANK: some inteira da tabela (sem
        # esqueleto na visao por regiao), nao aparece so zerada.
        assert "R2" not in tabela["REGIAO"].tolist()
        assert tabela.loc[
            tabela["REGIAO"] == "R1", sub["nome_col"]
        ].iloc[0] == 1

    def test_clt_composicao_bate_kpi_e_tabela_por_loja_consultor(self):
        sub = _cfg("CLT")["subtabs"][0]
        cfg_banco = _cfg("CLT")["toggle_banco"]
        df = pd.DataFrame({
            "categoria_codigo": ["CONSIG_PRIV", "CONSIG_PRIV"],
            "TIPO OPER.": ["Emprestimo", "Emprestimo"],
            "BANCO": ["BMG", "C6 BANK"],
            "LOJA": ["L1", "L1"],
            "CONSULTOR": ["Fulano BMG", "Fulano C6"],
        })
        mask_subtab = _mask_subtab(df, sub)
        mask_banco = _mask_banco(df, cfg_banco["bancos"])
        mask_composta = mask_subtab & mask_banco

        assert mask_composta.tolist() == [True, False]

        tabela = _contar_por_loja_consultor(
            df, mask_composta, sub["nome_col"],
        )
        assert int(tabela[sub["nome_col"]].sum()) == int(
            mask_composta.sum()
        )
        assert tabela["CONSULTOR"].tolist() == ["Fulano BMG"]


# ── Cache pré-RLS do mês comparativo (fix documentado em ────────────
# docs/agents/progress/2026-08-10-fix-evolucao-du-regiao-mes-comparativo.md)
#
# ``_mes_comparativo_full``/``limpar_cache_comparativos`` só leem/gravam
# ``st.session_state`` (sem widget, sem rerun) — usar o ``session_state``
# real em modo "bare" (fora de ``streamlit run``) é suficiente: get/set
# funcionam normalmente, só emitem um warning no stderr. Diferente das
# classes de render acima, não precisa de ``AppTest``. Como o objeto é
# um singleton do processo, cada classe limpa antes/depois de cada teste
# para não vazar estado entre testes.

@pytest.mark.unit
class TestMesComparativoFull:
    """``_mes_comparativo_full`` expõe o snapshot pré-RLS que
    ``_carregar_mes_comparativo`` passou a cachear sob
    ``<prefixo>_cache_full`` — a peça que faltava para o "Mês Anterior"
    do painel de Evolução Média DU por Região não ficar zerado para
    regiões fora do escopo do perfil (ver ``TestCalcularEvolucaoMediaDu``
    em ``tests/test_kpis_regioes.py`` para a prova do efeito no KPI).
    """

    @pytest.fixture(autouse=True)
    def _limpa_session_state(self):
        st.session_state.clear()
        yield
        st.session_state.clear()

    def test_retorna_cache_full_quando_chave_existe(self):
        df_full = pd.DataFrame({
            "REGIAO": ["R1", "R2"], "VALOR": [1000.0, 2000.0],
        })
        st.session_state["_df_ant_cache_full"] = df_full
        # Mesmo objeto guardado, não uma cópia (mesma garantia do
        # ``_cache`` pós-RLS de sempre).
        assert _mes_comparativo_full("_df_ant") is df_full

    def test_retorna_vazio_quando_chave_ausente(self):
        resultado = _mes_comparativo_full("_df_ant")
        assert isinstance(resultado, pd.DataFrame)
        assert resultado.empty

    def test_prefixos_nao_se_misturam(self):
        df_ant = pd.DataFrame({"REGIAO": ["R1"], "VALOR": [1.0]})
        df_ano_ant = pd.DataFrame({"REGIAO": ["R2"], "VALOR": [2.0]})
        st.session_state["_df_ant_cache_full"] = df_ant
        st.session_state["_df_ano_ant_cache_full"] = df_ano_ant

        assert _mes_comparativo_full("_df_ant") is df_ant
        assert _mes_comparativo_full("_df_ano_ant") is df_ano_ant


@pytest.mark.unit
class TestLimparCacheComparativos:
    """Antes do fix, ``limpar_cache_comparativos`` só removia
    ``<prefixo>_cache``/``<prefixo>_chave`` — a chave nova
    ``_cache_full`` sobreviveria a um "Atualizar Dados" e o painel
    continuaria comparando contra um snapshot pré-RLS desatualizado.
    """

    @pytest.fixture(autouse=True)
    def _limpa_session_state(self):
        st.session_state.clear()
        yield
        st.session_state.clear()

    def test_remove_cache_full_dos_dois_prefixos(self):
        for prefixo in _PREFIXOS_COMPARATIVO:
            st.session_state[f"{prefixo}_cache"] = pd.DataFrame({"X": [1]})
            st.session_state[f"{prefixo}_cache_full"] = pd.DataFrame(
                {"X": [1]}
            )
            st.session_state[f"{prefixo}_chave"] = ("chave",)

        limpar_cache_comparativos()

        for prefixo in _PREFIXOS_COMPARATIVO:
            assert f"{prefixo}_cache" not in st.session_state
            assert f"{prefixo}_cache_full" not in st.session_state
            assert f"{prefixo}_chave" not in st.session_state

    def test_chaves_ausentes_nao_lanca_excecao(self):
        # session_state vazio: pop(..., None) não deve quebrar.
        limpar_cache_comparativos()


# ── Render das abas (ST-07 — AppTest) ────────────────────────────────
#
# ``_render_produto_regional``/``_render_total_produto`` chamam widgets
# Streamlit (``st.toggle``, ``st.metric``, ``st.columns``) que fora de
# um script run real sempre devolvem o valor padrao (toggle sempre
# False) — nao da para simular "flag ligada" so importando as funcoes.
# ``AppTest.from_function`` roda o corpo da funcao abaixo como um script
# de verdade, permitindo pre-setar ``session_state`` (inclusive a chave
# do toggle) antes do primeiro ``run()``.
#
# A funcao precisa ser top-level e autocontida (imports no corpo): o
# AppTest extrai o source via ``inspect`` e executa isolado, so
# recebendo ``df``/``cfg_label``/``perfil_role`` etc. via args/kwargs.

def _script_render_produto_regional(
    cfg_label, perfil_role, df, df_analise, df_sup, du_total, du_dec,
):
    import pandas as pd  # noqa: F401  (necessario no script isolado)
    import streamlit as st

    from src.dashboard.tabs.produtos import (
        _PRODS_QTD,
        _render_produto_regional,
    )

    st.session_state["usuario_logado"] = {"perfil": perfil_role}
    cfg = next(p for p in _PRODS_QTD if p["label"] == cfg_label)
    _render_produto_regional(df, df_analise, cfg, du_total, du_dec, df_sup)


def _run_render(
    cfg_label: str,
    perfil_role: str,
    df: pd.DataFrame,
    *,
    toggle_key: str = None,
    toggle_on: bool = False,
    df_analise: pd.DataFrame = None,
    df_sup: pd.DataFrame = None,
    du_total: int = 20,
    du_dec: int = 10,
) -> AppTest:
    """Monta e roda o ``AppTest`` de uma aba de ``_PRODS_QTD``.

    ``toggle_key`` pré-seta ``session_state`` antes do primeiro
    ``run()`` — é a única forma de simular o toggle "ligado" (widgets
    fora de contexto sempre voltam ao valor padrão, ``False``).
    """
    at = AppTest.from_function(
        _script_render_produto_regional,
        kwargs=dict(
            cfg_label=cfg_label,
            perfil_role=perfil_role,
            df=df,
            df_analise=(
                df_analise if df_analise is not None else pd.DataFrame()
            ),
            df_sup=df_sup if df_sup is not None else pd.DataFrame(),
            du_total=du_total,
            du_dec=du_dec,
        ),
    )
    if toggle_key and toggle_on:
        at.session_state[toggle_key] = True
    at.run()
    return at


def _contagens_na_linha(html: str, nome_linha: str) -> list:
    """Extrai, em ordem, os numeros das colunas da linha ``nome_linha``.

    As tabelas HTML (``_html_tabela_regional``/``_html_tabela_loja``)
    tem a celula de nome (Loja/Consultor) seguida de 0+ colunas
    numericas (``Análise`` quando a aba declara ``col_dig_*``, a(s)
    coluna(s) de efetivados e "Proj"). CLT/Consignado nao tem
    "Análise"; abas antigas com ``col_dig_subtipo``/``col_dig_tipo``
    (ex.: Super Conta) tem. O regex casa a linha inteira e devolve
    todas as colunas numericas na ordem em que aparecem no HTML.
    """
    m = re.search(
        r'<td class="mg-rt-td mg-rt-td--loja">'
        + re.escape(nome_linha)
        + r'</td>((?:<td class="mg-rt-td mg-rt-td--num[^"]*">'
        r'\d+</td>)+)',
        html,
    )
    assert m, f"linha {nome_linha!r} nao encontrada em: {html}"
    return [int(n) for n in re.findall(r">(\d+)<", m.group(1))]


@pytest.mark.unit
class TestRenderProdutoRegionalFiltroBanco:
    """ST-07 — regressao do bug ST-05 (corrigido na ST-06): liga o
    toggle "Somente BMG/Help" de verdade (via ``AppTest``) e confirma
    que o KPI do topo e as tabelas por regiao/loja/consultor mudam
    JUNTOS. O caso mais importante e o de ``gerente_comercial``
    (``test_toggle_on_clt_exclui_c6_bank_kpi_e_tabela_por_consultor``):
    era exatamente o perfil cuja visao principal e a tabela, entao o
    bug relatado ("nao consegue filtrar producao") era invisivel para
    ele antes da ST-06.
    """

    def test_toggle_off_consignado_conta_todos_os_bancos(self):
        df = pd.DataFrame({
            "categoria_codigo": ["CONSIG_BMG", "CONSIG_BMG"],
            "SUBTIPO": ["NOVO", "NOVO"],
            "BANCO": ["BMG", "C6 BANK"],
            "REGIAO": ["R1", "R1"],
            "LOJA": ["L1", "L1"],
        })
        at = _run_render(
            "Consignado (Novo/Refin)", "admin", df,
            toggle_key="prod_qtd_consig_bmg_help", toggle_on=False,
        )
        assert not at.exception
        assert [t.value for t in at.toggle] == [False]
        assert [m.value for m in at.metric] == ["2"]
        assert len(at.markdown) == 1
        assert _contagens_na_linha(at.markdown[0].value, "L1")[0] == 2

    def test_toggle_on_consignado_exclui_c6_bank_kpi_e_tabela_por_regiao(
        self,
    ):
        df = pd.DataFrame({
            "categoria_codigo": [
                "CONSIG_BMG", "CONSIG_BMG", "CONSIG_BMG",
            ],
            "SUBTIPO": ["NOVO", "NOVO", "NOVO"],
            "BANCO": ["BMG", "C6 BANK", "C6 BANK"],
            "REGIAO": ["R1", "R1", "R2"],
            "LOJA": ["L1", "L1", "L2"],
        })
        at = _run_render(
            "Consignado (Novo/Refin)", "admin", df,
            toggle_key="prod_qtd_consig_bmg_help", toggle_on=True,
        )
        assert not at.exception
        assert [t.value for t in at.toggle] == [True]
        # KPI cai de 3 (antes do fix, o que a tabela ainda mostraria)
        # para 1 — e a tabela precisa bater, nao so o numero do topo.
        assert [m.value for m in at.metric] == ["1"]
        # R2/L2 so tinha linha C6 BANK: some inteira (sem esqueleto na
        # visao por regiao) em vez de aparecer zerada.
        assert len(at.markdown) == 1
        assert "R2" not in at.markdown[0].value
        assert _contagens_na_linha(at.markdown[0].value, "L1")[0] == 1

    def test_toggle_on_clt_exclui_c6_bank_kpi_e_tabela_por_consultor(
        self,
    ):
        # Caso mais importante: perfil gerente_comercial, cuja visao
        # principal E a tabela por consultor — era o perfil que
        # reportou o bug na ST-05.
        df = pd.DataFrame({
            "categoria_codigo": ["CONSIG_PRIV", "CONSIG_PRIV"],
            "TIPO OPER.": ["Emprestimo", "Emprestimo"],
            "BANCO": ["BMG", "C6 BANK"],
            "LOJA": ["L1", "L1"],
            "CONSULTOR": ["Fulano BMG", "Fulano C6"],
        })
        at = _run_render(
            "CLT", "gerente_comercial", df,
            toggle_key="prod_qtd_clt_bmg_help", toggle_on=True,
        )
        assert not at.exception
        assert [m.value for m in at.metric] == ["1"]
        assert len(at.markdown) == 1
        html = at.markdown[0].value
        # Na visao por loja/consultor ha esqueleto: o consultor C6
        # BANK continua na tabela, so que zerado — nao some como a
        # regiao some na visao por regiao.
        assert _contagens_na_linha(html, "Fulano BMG")[0] == 1
        assert _contagens_na_linha(html, "Fulano C6")[0] == 0

    def test_toggle_on_sem_coluna_banco_zera_kpi_e_tabela_inteira(self):
        # ST-06: coluna BANCO ausente + flag ligada zera a aba inteira
        # (KPI e tabelas), nao so o KPI como antes do fix.
        df = pd.DataFrame({
            "categoria_codigo": ["CONSIG_BMG", "CONSIG_BMG"],
            "SUBTIPO": ["NOVO", "NOVO"],
            "REGIAO": ["R1", "R2"],
            "LOJA": ["L1", "L2"],
        })
        at = _run_render(
            "Consignado (Novo/Refin)", "admin", df,
            toggle_key="prod_qtd_consig_bmg_help", toggle_on=True,
        )
        assert not at.exception
        assert [m.value for m in at.metric] == ["0"]
        assert len(at.markdown) == 0
        assert [i.value for i in at.info] == [
            "Sem dados para este produto no período."
        ]

    def test_aba_sem_toggle_banco_super_conta_tem_metric_mas_nao_toggle(
        self,
    ):
        # Super Conta ganhou total_label/total_help (mesmo contador
        # "Propostas pagas" de CLT/Consignado), mas continua SEM
        # toggle_banco — a flag "Somente BMG/Help" e exclusiva de
        # CLT/Consignado. Prova que uma aba sem toggle_banco na config
        # nao desenha nenhum st.toggle, mesmo tendo st.metric agora.
        sub = _cfg("Super Conta")["subtabs"][0]
        df = pd.DataFrame({
            "SUBTIPO": [sub["subtipo"], sub["subtipo"]],
            "REGIAO": ["R1", "R1"],
            "LOJA": ["L1", "L1"],
        })
        at = _run_render("Super Conta", "admin", df)
        assert not at.exception
        assert len(at.toggle) == 0
        assert [m.value for m in at.metric] == ["2"]
        assert len(at.markdown) == 1
        # Ordem das colunas desta aba: Análise (0, sem df_analise),
        # Super Conta (2), Proj (4) — igual a antes da ST-06, essa
        # aba nunca teve toggle_banco/mask_banco envolvidos.
        assert _contagens_na_linha(at.markdown[0].value, "L1") == [
            0, 2, 4,
        ]


@pytest.mark.unit
class TestRenderProdutoRegionalTotalSemToggle:
    """Cobertura das 3 abas que ganharam ``total_label``/``total_help``
    sem ``toggle_banco`` (Emissão, BMG Med, Vida Familiar — Super Conta,
    a quarta, já é coberta em
    ``TestRenderProdutoRegionalFiltroBanco.
    test_aba_sem_toggle_banco_super_conta_tem_metric_mas_nao_toggle``).
    Diferente de CLT/Consignado, nenhuma delas desenha ``st.toggle`` —
    só o ``st.metric`` do total precisa aparecer, com o valor correto.

    Caso mais importante: Emissão tem 2 subtabs (Cartão Benefício +
    Venda Pré-Adesão) e ``_render_total_produto`` faz OR entre as
    máscaras de todas as ``subtabs`` do cfg — o teste
    ``test_emissao_total_soma_cartao_beneficio_e_venda_pre_adesao``
    prova que o metric do topo soma as duas colunas combinadas, não só
    uma delas isoladamente.
    """

    def test_emissao_total_soma_cartao_beneficio_e_venda_pre_adesao(
        self,
    ):
        cfg = _cfg("Emissão")
        val_cartao = cfg["subtabs"][0]["tipo_oper"][0]
        val_venda = cfg["subtabs"][1]["tipo_oper"][0]
        df = pd.DataFrame({
            "TIPO OPER.": [val_cartao, val_cartao, val_venda, "Outro"],
            "REGIAO": ["R1", "R1", "R1", "R1"],
            "LOJA": ["L1", "L1", "L1", "L1"],
        })
        at = _run_render("Emissão", "admin", df)
        assert not at.exception
        assert len(at.toggle) == 0
        # Soma das duas subtabs (2 Cartão Benefício + 1 Venda
        # Pré-Adesão), nao so uma delas.
        assert [m.value for m in at.metric] == ["3"]
        assert len(at.markdown) == 1
        # Análise(0), Cartão Benefício(2), Venda Pré-Adesão(1),
        # Total(3), Proj(6, = 3/10*20).
        assert _contagens_na_linha(at.markdown[0].value, "L1") == [
            0, 2, 1, 3, 6,
        ]

    def test_bmg_med_total_e_metric_sem_toggle(self):
        sub = _cfg("BMG Med")["subtabs"][0]
        valor = sub["tipo_oper"][0]
        df = pd.DataFrame({
            "TIPO OPER.": [valor, valor, "Outro"],
            "REGIAO": ["R1", "R1", "R1"],
            "LOJA": ["L1", "L1", "L1"],
        })
        at = _run_render("BMG Med", "admin", df)
        assert not at.exception
        assert len(at.toggle) == 0
        assert [m.value for m in at.metric] == ["2"]
        assert len(at.markdown) == 1
        # Análise(0), BMG Med(2), Proj(4, = 2/10*20).
        assert _contagens_na_linha(at.markdown[0].value, "L1") == [
            0, 2, 4,
        ]

    def test_vida_familiar_total_e_metric_sem_toggle(self):
        sub = _cfg("Vida Familiar")["subtabs"][0]
        valor = sub["tipo_oper"][0]
        df = pd.DataFrame({
            "TIPO OPER.": [valor, valor, valor, "Outro"],
            "REGIAO": ["R1", "R1", "R1", "R1"],
            "LOJA": ["L1", "L1", "L1", "L1"],
        })
        at = _run_render("Vida Familiar", "admin", df)
        assert not at.exception
        assert len(at.toggle) == 0
        assert [m.value for m in at.metric] == ["3"]
        assert len(at.markdown) == 1
        # Análise(0), Vida Familiar(3), Proj(6, = 3/10*20).
        assert _contagens_na_linha(at.markdown[0].value, "L1") == [
            0, 3, 6,
        ]


# ── Produção de supervisor conta no total (decisão 2026-08-10) ──────
#
# ``produtos.py`` passou a somar produção de supervisor no total da
# aba (KPI do topo + tabelas por loja/região), mas ela nunca vira uma
# linha de "consultor": não entra no ranking por produção nem em
# nenhuma média por consultor. Ver docstring de
# ``_render_produto_regional`` (bloco "O total e as tabelas contam
# sobre df completo") para a regra de negócio completa.

@pytest.mark.unit
class TestRenderProdutoRegionalProducaoSupervisor:
    """Cobertura da inclusão de produção de supervisor no total, com a
    marcação/segregação correta por visão:

    - Admin/Gestor (por REGIAO/LOJA): produção de supervisor soma no
      total da loja, anônima — sem linha por pessoa. Loja ganha " *" no
      nome e a seção ganha uma caption de rodapé (uma vez, fora do loop
      de regiões).
    - Gerente Comercial (por LOJA/CONSULTOR): produção de supervisor
      vira uma linha própria por loja, rotulada "<nome> (Supervisor)",
      sempre após os consultores reais (nunca participa do sort por
      produção) e antes da linha "Total".

    Nas duas visões, o ``st.metric`` do topo soma TUDO (com supervisor)
    e ganha uma ``st.caption`` "Inclui N de produção de supervisor..."
    quando essa produção é > 0 dentro do total.
    """

    def test_admin_total_inclui_supervisor_loja_marcada_e_caption_rodape(
        self,
    ):
        sub = _cfg("Super Conta")["subtabs"][0]
        df = pd.DataFrame({
            "SUBTIPO": [sub["subtipo"]] * 4,
            "REGIAO": ["R1"] * 4,
            "LOJA": ["L1"] * 4,
            "CONSULTOR": ["Joao", "Maria", "Chefe Supervisor", "Joao"],
        })
        df_sup = pd.DataFrame({"SUPERVISOR": ["Chefe Supervisor"]})
        at = _run_render("Super Conta", "admin", df, df_sup=df_sup)
        assert not at.exception
        assert [m.value for m in at.metric] == ["4"]
        assert [c.value for c in at.caption] == [
            "Inclui 1 de produção de supervisor (fora de rankings e "
            "médias por consultor).",
            "* Loja com produção de supervisor incluída no total "
            "(fora de rankings e médias por consultor).",
        ]
        assert len(at.markdown) == 1
        html = at.markdown[0].value
        assert "L1 *" in html
        # Análise(0, sem df_analise), Super Conta(4), Proj(8).
        assert _contagens_na_linha(html, "L1 *") == [0, 4, 8]

    def test_gerente_comercial_supervisor_nao_participa_do_sort_fica_apos_consultores(
        self,
    ):
        # Chefe Supervisor produz MAIS que qualquer consultor (3 contra
        # 2 e 1): se a linha participasse do sort por produção ela
        # apareceria primeiro. O comportamento esperado é o oposto —
        # sempre por último, antes só do "Total".
        sub = _cfg("Super Conta")["subtabs"][0]
        df = pd.DataFrame({
            "SUBTIPO": [sub["subtipo"]] * 6,
            "LOJA": ["L1"] * 6,
            "CONSULTOR": [
                "Joao",
                "Maria", "Maria",
                "Chefe Supervisor", "Chefe Supervisor",
                "Chefe Supervisor",
            ],
        })
        df_sup = pd.DataFrame({"SUPERVISOR": ["Chefe Supervisor"]})
        at = _run_render(
            "Super Conta", "gerente_comercial", df, df_sup=df_sup,
        )
        assert not at.exception
        assert [m.value for m in at.metric] == ["6"]
        assert [c.value for c in at.caption] == [
            "Inclui 3 de produção de supervisor (fora de rankings e "
            "médias por consultor).",
        ]
        assert len(at.markdown) == 1
        html = at.markdown[0].value
        pos_maria = html.index(">Maria<")
        pos_joao = html.index(">Joao<")
        pos_sup = html.index("Chefe Supervisor (Supervisor)")
        pos_total = html.index(">Total<")
        assert pos_maria < pos_joao < pos_sup < pos_total
        assert _contagens_na_linha(html, "Maria") == [0, 2, 4]
        assert _contagens_na_linha(html, "Joao") == [0, 1, 2]
        assert _contagens_na_linha(
            html, "Chefe Supervisor (Supervisor)"
        ) == [0, 3, 6]
        assert _contagens_na_linha(html, "Total") == [0, 6, 12]

    def test_gerente_comercial_emissao_supervisor_soma_duas_subtabs(
        self,
    ):
        cfg = _cfg("Emissão")
        val_cartao = cfg["subtabs"][0]["tipo_oper"][0]
        val_venda = cfg["subtabs"][1]["tipo_oper"][0]
        df = pd.DataFrame({
            "TIPO OPER.": [val_cartao, val_cartao, val_venda],
            "LOJA": ["L1", "L1", "L1"],
            "CONSULTOR": [
                "Joao", "Chefe Supervisor", "Chefe Supervisor",
            ],
        })
        df_sup = pd.DataFrame({"SUPERVISOR": ["Chefe Supervisor"]})
        at = _run_render(
            "Emissão", "gerente_comercial", df, df_sup=df_sup,
        )
        assert not at.exception
        assert [m.value for m in at.metric] == ["3"]
        assert [c.value for c in at.caption] == [
            "Inclui 2 de produção de supervisor (fora de rankings e "
            "médias por consultor).",
        ]
        assert len(at.markdown) == 1
        html = at.markdown[0].value
        # Análise(0), Cartão Benefício, Venda Pré-Adesão, Total, Proj.
        assert _contagens_na_linha(html, "Joao") == [0, 1, 0, 1, 2]
        assert _contagens_na_linha(
            html, "Chefe Supervisor (Supervisor)"
        ) == [0, 1, 1, 2, 4]
        assert _contagens_na_linha(html, "Total") == [0, 2, 1, 3, 6]

    def test_toggle_bmg_help_supervisor_incluido_quando_banco_bate(
        self,
    ):
        cfg_banco = _cfg("CLT")["toggle_banco"]
        df = pd.DataFrame({
            "categoria_codigo": ["CONSIG_PRIV"] * 3,
            "TIPO OPER.": ["Emprestimo"] * 3,
            "BANCO": ["BMG", "C6 BANK", "BMG"],
            "REGIAO": ["R1"] * 3,
            "LOJA": ["L1"] * 3,
            "CONSULTOR": ["Joao", "Maria", "Chefe Supervisor"],
        })
        df_sup = pd.DataFrame({"SUPERVISOR": ["Chefe Supervisor"]})
        at = _run_render(
            "CLT", "admin", df, df_sup=df_sup,
            toggle_key=cfg_banco["key"], toggle_on=True,
        )
        assert not at.exception
        assert [t.value for t in at.toggle] == [True]
        assert [m.value for m in at.metric] == ["2"]
        assert [c.value for c in at.caption] == [
            "Inclui 1 de produção de supervisor (fora de rankings e "
            "médias por consultor).",
            "* Loja com produção de supervisor incluída no total "
            "(fora de rankings e médias por consultor).",
        ]
        assert len(at.markdown) == 1
        html = at.markdown[0].value
        assert "L1 *" in html
        # CLT não tem coluna Análise: CLT(2), Proj(4).
        assert _contagens_na_linha(html, "L1 *") == [2, 4]

    def test_toggle_bmg_help_supervisor_excluido_quando_banco_nao_bate(
        self,
    ):
        cfg_banco = _cfg("CLT")["toggle_banco"]
        df = pd.DataFrame({
            "categoria_codigo": ["CONSIG_PRIV"] * 3,
            "TIPO OPER.": ["Emprestimo"] * 3,
            "BANCO": ["BMG", "C6 BANK", "C6 BANK"],
            "REGIAO": ["R1"] * 3,
            "LOJA": ["L1"] * 3,
            "CONSULTOR": ["Joao", "Maria", "Chefe Supervisor"],
        })
        df_sup = pd.DataFrame({"SUPERVISOR": ["Chefe Supervisor"]})
        at = _run_render(
            "CLT", "admin", df, df_sup=df_sup,
            toggle_key=cfg_banco["key"], toggle_on=True,
        )
        assert not at.exception
        assert [m.value for m in at.metric] == ["1"]
        # Chefe Supervisor ficou fora do banco filtrado: não sobra
        # produção de supervisor dentro do total, sem caption nem
        # marcação de loja.
        assert [c.value for c in at.caption] == []
        assert len(at.markdown) == 1
        html = at.markdown[0].value
        assert "L1 *" not in html
        assert _contagens_na_linha(html, "L1") == [1, 2]

    def test_admin_sem_producao_de_supervisor_nao_marca_nada(self):
        sub = _cfg("Super Conta")["subtabs"][0]
        df = pd.DataFrame({
            "SUBTIPO": [sub["subtipo"]] * 2,
            "REGIAO": ["R1", "R1"],
            "LOJA": ["L1", "L1"],
            "CONSULTOR": ["Joao", "Maria"],
        })
        # Supervisor conhecido (df_sup não vazio), mas sem nenhuma
        # linha dele no período — não pode marcar nada.
        df_sup = pd.DataFrame({"SUPERVISOR": ["Chefe Supervisor"]})
        at = _run_render("Super Conta", "admin", df, df_sup=df_sup)
        assert not at.exception
        assert [m.value for m in at.metric] == ["2"]
        assert [c.value for c in at.caption] == []
        assert len(at.markdown) == 1
        html = at.markdown[0].value
        assert "L1 *" not in html
        assert _contagens_na_linha(html, "L1") == [0, 2, 4]

    def test_gerente_comercial_sem_producao_de_supervisor_nao_marca_nada(
        self,
    ):
        sub = _cfg("Super Conta")["subtabs"][0]
        df = pd.DataFrame({
            "SUBTIPO": [sub["subtipo"]] * 2,
            "LOJA": ["L1", "L1"],
            "CONSULTOR": ["Joao", "Maria"],
        })
        df_sup = pd.DataFrame({"SUPERVISOR": ["Chefe Supervisor"]})
        at = _run_render(
            "Super Conta", "gerente_comercial", df, df_sup=df_sup,
        )
        assert not at.exception
        assert [m.value for m in at.metric] == ["2"]
        assert [c.value for c in at.caption] == []
        assert len(at.markdown) == 1
        html = at.markdown[0].value
        assert "(Supervisor)" not in html
        assert _contagens_na_linha(html, "Joao") == [0, 1, 2]
        assert _contagens_na_linha(html, "Maria") == [0, 1, 2]
        assert _contagens_na_linha(html, "Total") == [0, 2, 4]
