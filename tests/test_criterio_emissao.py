"""
Emissão de cartão: UM critério, `TIPO_PRODUTO ∈ PRODUTOS_EMISSAO`.

## Por que existe

Até 09/2026 "Emissão" tinha dois critérios. A consolidação (zeragem de
valor e pontos), os cards de quantidade do topo, a aba Produtos e o
contador da aba Em Análise usavam `TIPO OPER. ∈ {CARTÃO BENEFICIO,
Venda Pré-Adesão}`; `mascaras_aceleradores` (rankings, Gestão,
Distribuição, Aceleradores) usava `TIPO_PRODUTO`. O Caderno, em SQL,
também usa `TIPO_PRODUTO`.

Verificado na base inteira em 2026-09-15: os dois concordam em tudo,
menos em 3 propostas, todas **operação de emissão com produto de
SAQUE**. Saque é produção com valor. Decisão do usuário: o critério é o
produto.

## O frame desta suíte

As três formas que existem no dado, mais uma de controle:

| linha | TIPO_PRODUTO    | TIPO OPER.        | é emissão? |
|-------|-----------------|-------------------|------------|
| A     | EMISSAO         | CARTÃO BENEFICIO  | sim        |
| B     | EMISSAO CC      | Venda Pré-Adesão  | sim        |
| C     | SAQUE BENEFICIO | CARTÃO BENEFICIO  | **não**    |
| D     | SAQUE           | Venda Pré-Adesão  | **não**    |
| E     | CNC             | CONTRATO NOVO     | não        |

`TestCatracaConsistencia` passa o MESMO frame pelas seis superfícies:
todas precisam concordar que só A e B são emissão. É o que impede um
quinto critério de nascer em silêncio.
"""
from pathlib import Path

import pandas as pd
import pytest

_RAIZ = Path(__file__).resolve().parent.parent
_EMISSAO = [True, True, False, False, False]


def _frame(**extra):
    base = {
        "LOJA": ["L1"] * 5,
        "REGIAO": ["R1"] * 5,
        "CONSULTOR": ["ANA", "BIA", "CAIO", "DANI", "EDU"],
        "TIPO_PRODUTO": [
            "EMISSAO", "EMISSAO CC", "SAQUE BENEFICIO", "SAQUE", "CNC",
        ],
        "TIPO OPER.": [
            "CARTÃO BENEFICIO", "Venda Pré-Adesão", "CARTÃO BENEFICIO",
            "Venda Pré-Adesão", "CONTRATO NOVO",
        ],
        "SUBTIPO": ["", "", "", "", "NOVO"],
        "categoria_codigo": ["CARTAO", "CARTAO", "SAQUE_BENEFICIO", "SAQUE", "CNC"],
        "VALOR": [100.0, 50.0, 300.0, 200.0, 1000.0],
    }
    base.update(extra)
    return pd.DataFrame(base)


@pytest.mark.unit
class TestEhEmissao:
    def test_criterio_e_o_produto_nao_a_operacao(self):
        from src.dashboard.kpis.consolidacao import eh_emissao

        assert eh_emissao(_frame()).tolist() == _EMISSAO

    @pytest.mark.parametrize("valor", [" emissao cb ", "Emissao Cc", "EMISSAO"])
    def test_normaliza_caixa_e_espaco(self, valor):
        from src.dashboard.kpis.consolidacao import eh_emissao

        assert eh_emissao(pd.DataFrame({"TIPO_PRODUTO": [valor]})).tolist() == [True]

    def test_nulos_e_coluna_toda_nula_nao_levantam(self):
        from src.dashboard.kpis.consolidacao import eh_emissao

        df = pd.DataFrame({"TIPO_PRODUTO": [None, float("nan"), ""]})
        assert eh_emissao(df).tolist() == [False, False, False]
        tudo_nan = pd.DataFrame({"TIPO_PRODUTO": [float("nan")] * 2})
        assert eh_emissao(tudo_nan).tolist() == [False, False]

    def test_sem_a_coluna_nada_e_emissao(self):
        from src.dashboard.kpis.consolidacao import eh_emissao

        assert eh_emissao(pd.DataFrame({"X": [1, 2]})).tolist() == [False, False]


@pytest.mark.unit
class TestCatracaConsistencia:
    """As seis superfícies, o mesmo frame, a mesma resposta."""

    def test_consolidacao_flag_e_zeragem(self):
        from src.dashboard.kpis.consolidacao import consolidar_pontuacao

        df = _frame(conta_valor=[True] * 5, conta_pontuacao=[True] * 5, BANCO=["BMG"] * 5)
        pontos = pd.DataFrame({
            "categoria_codigo": ["CARTAO", "SAQUE_BENEFICIO", "SAQUE", "CNC"],
            "pontos": [1.0, 1.0, 1.0, 1.0],
        })
        out, _ = consolidar_pontuacao(df, pontos, lambda: pd.DataFrame())

        assert out["is_emissao_cartao"].tolist() == _EMISSAO
        # Saque com operação de cartão conta valor e pontos.
        assert out["VALOR"].tolist() == [0.0, 0.0, 300.0, 200.0, 1000.0]
        assert out["pontos"].tolist() == [0.0, 0.0, 300.0, 200.0, 1000.0]

    def test_conta_valor_de_analise_e_cancelados(self):
        from src.dashboard.kpis.detalhes_cards import aplicar_conta_valor

        out = aplicar_conta_valor(_frame())
        assert out["VALOR"].tolist() == [0.0, 0.0, 300.0, 200.0, 1000.0]

    def test_mascaras_aceleradores(self):
        from src.dashboard.kpis.gerais import mascaras_aceleradores

        assert mascaras_aceleradores(_frame())["Emissao"].tolist() == _EMISSAO

    def test_card_de_quantidade_pago_e_em_analise(self):
        from src.dashboard.kpis.consolidacao import eh_emissao
        from src.dashboard.kpis.gerais import calcular_kpis_qtd_produtos

        pagos = _frame()
        pagos["is_emissao_cartao"] = eh_emissao(pagos)
        res = calcular_kpis_qtd_produtos(
            pagos, _frame(), pd.DataFrame(), du_total=20, du_decorridos=10,
        )
        emissao = next(r for r in res if r["produto"] == "EMISSAO")
        assert (emissao["qtd_paga"], emissao["qtd_analise"]) == (2, 2)

    def test_subtabs_da_aba_produtos(self):
        from src.dashboard.tabs.produtos import _PRODS_QTD, _mask_subtab

        cfg = next(p for p in _PRODS_QTD if p["label"] == "Emissão")
        df = _frame()
        uniao = pd.Series(False, index=df.index)
        for sub in cfg["subtabs"]:
            uniao |= _mask_subtab(df, sub)
        assert uniao.tolist() == _EMISSAO

    def test_nenhum_criterio_por_operacao_fora_da_divisao_de_exibicao(self):
        """Os literais de operação só podem aparecer como DIMENSÃO de
        exibição (as sub-abas "Cartão Benefício" / "Venda Pré-Adesão"),
        sempre junto de ``emissao: True``. Em qualquer outro arquivo de
        ``src/`` eles voltariam a ser critério."""
        permitidos = {
            Path("src/dashboard/tabs/produtos.py"),
            Path("src/shared/texto.py"),  # só docstring
        }
        achados = []
        for arq in (_RAIZ / "src").rglob("*.py"):
            rel = arq.relative_to(_RAIZ)
            if rel in permitidos:
                continue
            texto = arq.read_text(encoding="utf-8")
            for literal in ("CARTÃO BENEFICIO", "Venda Pré-Adesão"):
                if literal in texto:
                    achados.append(f"{rel}: {literal}")
        assert achados == []


@pytest.mark.unit
class TestSubtabsExigemProdutoDeEmissao:
    def test_cada_subtab_declara_emissao(self):
        from src.dashboard.tabs.produtos import _PRODS_QTD

        cfg = next(p for p in _PRODS_QTD if p["label"] == "Emissão")
        assert all(sub.get("emissao") is True for sub in cfg["subtabs"])

    def test_operacao_de_cartao_com_produto_saque_fica_fora(self):
        from src.dashboard.tabs.produtos import _mask_subtab

        sub = {"tipo_oper": ["CARTÃO BENEFICIO"], "emissao": True}
        assert _mask_subtab(_frame(), sub).tolist() == [True, False, False, False, False]
