"""
Testes dos helpers puros de contagem em ``src/dashboard/tabs/produtos.py``
(``_norm``, ``_mask_falsa``, ``_mask_subtab``, ``_mask_banco``) — o mask
builder das abas de "Emissão e Seguros — Análise Regional", incluindo os
novos itens CLT e Consignado (Novo/Refin) e a flag "Somente BMG/Help".

Ver
``docs/agents/progress/2026-08-06-plano-clt-consignado-emissao-seguros.md``
para a especificação de negócio (ST-01) e a decisão de implementação
(ST-02) por trás destes testes (ST-03). O caso mais importante é a
exclusão automática de Portabilidade/Refin-da-Portabilidade em
Consignado: essas linhas mantêm ``categoria_codigo == "PORTABILIDADE"``
mesmo tendo ``SUBTIPO`` igual a Novo/Refin, então o filtro por
``categoria_codigo`` já as exclui sem lógica extra.
"""
import pandas as pd
import pytest

from src.dashboard.tabs.produtos import (
    _BANCOS_BMG_HELP,
    _PRODS_QTD,
    _mask_banco,
    _mask_falsa,
    _mask_subtab,
    _norm,
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
