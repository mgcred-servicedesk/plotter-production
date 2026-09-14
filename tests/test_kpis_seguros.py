"""
Regras de BMG Med / Vida Familiar (``kpis/seguros.py``).

Testes de **caracterização**: fixam o comportamento que já existia
dentro de `tabs/analiticos.py` antes da Etapa 2 da revisão de 09/2026.
Enquanto a união/dedup/classificação morava no renderer, nada disso era
exercitado (o módulo saiu da extração com 12% de cobertura) — a regra
só era verificável abrindo a aba.

As duas regras que estes produtos têm de diferente do resto do
dashboard:

1. O estado real vive em ``SUB_STATUS``, não em ``status_banco`` —
   `Liquidada` = paga, `Cancelada` = cancelada, **todo o resto** = em
   análise (inclusive vazio e valor desconhecido).
2. A mesma adesão pode aparecer nas três fontes ao mesmo tempo, então a
   união dedupe por ``CONTRATO_ID`` com precedência
   **pago > análise > cancelado**.
"""
import pandas as pd
import pytest

from src.dashboard.kpis.seguros import (
    _classificar_status_seguro,
    _pool_seguros,
)

_TIPO = "BMG MED"


def _fonte(contrato_id, tipo_oper=_TIPO, sub_status="", valor=100.0):
    return pd.DataFrame({
        "CONTRATO_ID": [contrato_id],
        "TIPO OPER.": [tipo_oper],
        "SUB_STATUS": [sub_status],
        "VALOR": [valor],
    })


@pytest.mark.unit
class TestClassificarStatusSeguro:
    def test_liquidada_e_paga_cancelada_e_cancelada(self):
        s = pd.Series(["Liquidada", "Cancelada"])
        assert _classificar_status_seguro(s).tolist() == [
            "Pagas", "Cancelados",
        ]

    @pytest.mark.parametrize("valor", [
        "", "Pendente", "Em Digitacao", "qualquer coisa",
    ])
    def test_todo_o_resto_cai_em_em_analise(self, valor):
        """Regra aberta de propósito: o ciclo desses produtos tem
        estados intermediários demais para enumerar."""
        assert _classificar_status_seguro(
            pd.Series([valor])
        ).tolist() == ["Em Analise"]

    def test_nulo_vira_em_analise(self):
        assert _classificar_status_seguro(
            pd.Series([None])
        ).tolist() == ["Em Analise"]

    def test_espacos_em_volta_nao_atrapalham(self):
        assert _classificar_status_seguro(
            pd.Series(["  Liquidada  "])
        ).tolist() == ["Pagas"]

    def test_comparacao_e_sensivel_a_caixa(self):
        """Caracterização, não endosso: `liquidada` minúsculo NÃO é
        reconhecido como paga. Se a base passar a trazer caixa
        variável, é aqui que quebra."""
        assert _classificar_status_seguro(
            pd.Series(["liquidada"])
        ).tolist() == ["Em Analise"]

    def test_preserva_o_indice_do_frame(self):
        """O resultado é atribuído de volta como coluna (`pool
        ["_STATUS"] = ...`): índice desalinhado viraria NaN."""
        s = pd.Series(["Liquidada", "Cancelada"], index=[7, 9])
        assert _classificar_status_seguro(s).index.tolist() == [7, 9]


@pytest.mark.unit
class TestPoolSeguros:
    def test_une_as_tres_fontes_e_marca_origem(self):
        pool = _pool_seguros(
            _fonte("c1"), _fonte("c2"), _fonte("c3"), _TIPO,
        )
        assert len(pool) == 3
        assert set(pool["_origem"]) == {"pago", "analise", "cancelado"}

    def test_filtra_pelo_tipo_oper_pedido(self):
        df = pd.concat([_fonte("c1"), _fonte("c2", tipo_oper="Seguro")])
        pool = _pool_seguros(df, pd.DataFrame(), pd.DataFrame(), _TIPO)
        assert pool["CONTRATO_ID"].tolist() == ["c1"]

    def test_dedupe_preserva_pago_sobre_analise_e_cancelado(self):
        """Mesma adesão nas três fontes: fica a linha de pagos."""
        pool = _pool_seguros(
            _fonte("mesmo", valor=1.0),
            _fonte("mesmo", valor=2.0),
            _fonte("mesmo", valor=3.0),
            _TIPO,
        )
        assert len(pool) == 1
        assert pool.iloc[0]["_origem"] == "pago"
        assert pool.iloc[0]["VALOR"] == 1.0

    def test_dedupe_preserva_analise_sobre_cancelado(self):
        pool = _pool_seguros(
            pd.DataFrame(), _fonte("mesmo"), _fonte("mesmo"), _TIPO,
        )
        assert len(pool) == 1
        assert pool.iloc[0]["_origem"] == "analise"

    def test_coluna_auxiliar_de_prioridade_nao_vaza(self):
        pool = _pool_seguros(
            _fonte("mesmo"), _fonte("mesmo"), pd.DataFrame(), _TIPO,
        )
        assert "_prio" not in pool.columns

    def test_sem_contrato_id_nao_dedupe(self):
        """Caracterização: sem a coluna de identidade não há como
        deduplicar, e as linhas ficam todas."""
        sem_id = pd.DataFrame({
            "TIPO OPER.": [_TIPO], "SUB_STATUS": [""],
        })
        pool = _pool_seguros(sem_id, sem_id, pd.DataFrame(), _TIPO)
        assert len(pool) == 2

    def test_sub_status_ausente_e_criada_vazia(self):
        """O renderer lê `pool["SUB_STATUS"]` logo em seguida — a
        coluna precisa existir mesmo quando nenhuma fonte a trouxe."""
        sem_sub = pd.DataFrame({
            "CONTRATO_ID": ["c1"], "TIPO OPER.": [_TIPO],
        })
        pool = _pool_seguros(sem_sub, pd.DataFrame(), pd.DataFrame(), _TIPO)
        assert pool["SUB_STATUS"].tolist() == [""]

    def test_sub_status_nulo_vira_string_vazia(self):
        pool = _pool_seguros(
            _fonte("c1", sub_status=None), pd.DataFrame(),
            pd.DataFrame(), _TIPO,
        )
        assert pool["SUB_STATUS"].tolist() == [""]

    @pytest.mark.parametrize("fontes", [
        (pd.DataFrame(), pd.DataFrame(), pd.DataFrame()),
        (None, None, None),
    ])
    def test_nenhuma_fonte_utilizavel_devolve_frame_vazio(self, fontes):
        assert _pool_seguros(*fontes, _TIPO).empty

    def test_fonte_sem_a_coluna_tipo_oper_e_ignorada(self):
        """Frame de outra origem (sem o vocabulário de tipo de
        operação) não derruba a união — é pulado."""
        sem_col = pd.DataFrame({"CONTRATO_ID": ["x"]})
        pool = _pool_seguros(sem_col, _fonte("c1"), pd.DataFrame(), _TIPO)
        assert pool["CONTRATO_ID"].tolist() == ["c1"]

    def test_nenhuma_linha_do_tipo_devolve_vazio(self):
        df = _fonte("c1", tipo_oper="Seguro")
        assert _pool_seguros(df, df, df, _TIPO).empty

    def test_nao_muta_os_frames_de_entrada(self):
        df = _fonte("c1")
        _pool_seguros(df, pd.DataFrame(), pd.DataFrame(), _TIPO)
        assert "_origem" not in df.columns
