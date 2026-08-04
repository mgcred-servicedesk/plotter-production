"""
Testes dos helpers puros do intervalo livre de datas
(``src/dashboard/loaders.py``), usados pela aba de Gestao.

O dashboard e mensal, mas a Gestao apura faixas livres. Como
``contratos.periodo_id`` e DERIVADO de ``data_status_pagamento``, o
conjunto de meses que cobre um intervalo de PAGAMENTO e exato. Por
CADASTRO nao e: um contrato digitado em maio e pago em julho vive no
periodo de julho, entao a varredura precisa ir alem da data final.
"""
from datetime import date

import pandas as pd
import pytest

from src.dashboard import loaders
from src.dashboard.loaders import (
    CAMPO_CADASTRO,
    CAMPO_PAGAMENTO,
    carregar_contratos_pagos_intervalo,
    filtrar_por_intervalo,
    meses_do_intervalo,
)


@pytest.mark.unit
class TestMesesDoIntervalo:
    def test_intervalo_dentro_de_um_mes(self):
        meses = meses_do_intervalo(
            date(2026, 5, 3), date(2026, 5, 28), CAMPO_PAGAMENTO
        )
        assert meses == [(5, 2026)]

    def test_intervalo_cruzando_meses(self):
        meses = meses_do_intervalo(
            date(2026, 4, 20), date(2026, 6, 10), CAMPO_PAGAMENTO
        )
        assert meses == [(4, 2026), (5, 2026), (6, 2026)]

    def test_intervalo_cruzando_o_ano(self):
        meses = meses_do_intervalo(
            date(2025, 11, 15), date(2026, 2, 3), CAMPO_PAGAMENTO
        )
        assert meses == [
            (11, 2025), (12, 2025), (1, 2026), (2, 2026),
        ]

    def test_fim_antes_do_inicio_devolve_vazio(self):
        assert meses_do_intervalo(
            date(2026, 6, 1), date(2026, 5, 1), CAMPO_PAGAMENTO
        ) == []

    def test_datas_ausentes_devolvem_vazio(self):
        assert meses_do_intervalo(None, date(2026, 5, 1)) == []
        assert meses_do_intervalo(date(2026, 5, 1), None) == []

    def test_cadastro_varre_ate_hoje(self):
        """Cadastrado em maio pode ter sido pago em julho."""
        meses = meses_do_intervalo(
            date(2026, 5, 1),
            date(2026, 5, 31),
            CAMPO_CADASTRO,
            hoje=date(2026, 7, 15),
        )
        assert meses == [(5, 2026), (6, 2026), (7, 2026)]

    def test_cadastro_nao_encurta_quando_fim_e_futuro(self):
        meses = meses_do_intervalo(
            date(2026, 5, 1),
            date(2026, 9, 30),
            CAMPO_CADASTRO,
            hoje=date(2026, 7, 15),
        )
        assert meses[-1] == (9, 2026)

    def test_pagamento_nao_varre_alem_do_fim(self):
        """Por pagamento, o periodo_id garante que nao ha nada fora."""
        meses = meses_do_intervalo(
            date(2026, 5, 1),
            date(2026, 5, 31),
            CAMPO_PAGAMENTO,
            hoje=date(2026, 7, 15),
        )
        assert meses == [(5, 2026)]


@pytest.fixture
def df_datas():
    return pd.DataFrame({
        "CONSULTOR": ["A", "B", "C", "D", "E"],
        "DATA": pd.to_datetime([
            "2026-04-30", "2026-05-01", "2026-05-15",
            "2026-05-31", "2026-06-01",
        ]),
        "DATA_CADASTRO": pd.to_datetime([
            "2026-04-01", "2026-04-20", "2026-05-10",
            "2026-05-25", "2026-05-30",
        ]),
        "VALOR": [1.0] * 5,
    })


@pytest.mark.unit
class TestFiltrarPorIntervalo:
    def test_limites_sao_inclusivos_nas_duas_pontas(self, df_datas):
        res = filtrar_por_intervalo(
            df_datas, date(2026, 5, 1), date(2026, 5, 31), CAMPO_PAGAMENTO
        )
        assert set(res["CONSULTOR"]) == {"B", "C", "D"}

    def test_usa_a_coluna_de_data_escolhida(self, df_datas):
        res = filtrar_por_intervalo(
            df_datas, date(2026, 5, 1), date(2026, 5, 31), CAMPO_CADASTRO
        )
        # Por cadastro entram C, D e E (E foi pago em junho)
        assert set(res["CONSULTOR"]) == {"C", "D", "E"}

    def test_linhas_sem_data_saem(self):
        df = pd.DataFrame({
            "CONSULTOR": ["A", "B"],
            "DATA": pd.to_datetime(["2026-05-10", None]),
        })
        res = filtrar_por_intervalo(
            df, date(2026, 5, 1), date(2026, 5, 31), CAMPO_PAGAMENTO
        )
        assert set(res["CONSULTOR"]) == {"A"}

    def test_coluna_ausente_devolve_intacto(self, df_datas):
        res = filtrar_por_intervalo(
            df_datas, date(2026, 5, 1), date(2026, 5, 31), "NAO_EXISTE"
        )
        assert len(res) == len(df_datas)

    def test_df_vazio(self):
        res = filtrar_por_intervalo(
            pd.DataFrame(), date(2026, 5, 1), date(2026, 5, 31)
        )
        assert res.empty

    def test_nao_muta_o_df_de_origem(self, df_datas):
        antes = len(df_datas)
        filtrar_por_intervalo(
            df_datas, date(2026, 5, 1), date(2026, 5, 2), CAMPO_PAGAMENTO
        )
        assert len(df_datas) == antes


@pytest.mark.unit
class TestCarregarContratosPagosIntervalo:
    """``categoria_id`` NULL no banco (migration 061) tambem precisa do
    fallback no caminho de periodo livre, nao so no mes da sidebar.

    Regressao: CLT (TIPO_PRODUTO) chega com ``categoria_codigo`` vazio
    quando o ETL renomeia o tipo e nao backfilla ``categoria_id`` — sem
    o fallback, o filtro por ``categoria_codigo`` (CONSIG_PRIV) na aba
    de Gestao nao casa nenhuma linha e a producao de CLT no periodo
    personalizado aparece zerada mesmo havendo vendas.
    """

    CATEGORIAS = pd.DataFrame({
        "codigo": ["CONSIG_PRIV"],
        "grupo_dashboard": ["CLT"],
        "grupo_meta": ["CLT"],
        "conta_valor": [True],
        "conta_pontuacao": [True],
    })

    def _mes(self, mes, ano, consultor, data):
        return pd.DataFrame({
            "CONSULTOR": [consultor],
            "TIPO_PRODUTO": ["CLT"],
            "categoria_codigo": [None],
            "grupo_dashboard": [None],
            "conta_valor": [None],
            "VALOR": [1000.0],
            "DATA": pd.to_datetime([data]),
        })

    def test_preenche_categoria_no_periodo_personalizado(self, monkeypatch):
        monkeypatch.setattr(
            loaders, "carregar_categorias", lambda: self.CATEGORIAS
        )
        por_mes = {
            (1, 2026): self._mes(1, 2026, "A", "2026-01-16"),
            (2, 2026): self._mes(2, 2026, "B", "2026-02-26"),
        }
        monkeypatch.setattr(
            loaders,
            "carregar_contratos_pagos",
            lambda mes, ano: por_mes.get((mes, ano), pd.DataFrame()),
        )

        df, aviso = carregar_contratos_pagos_intervalo(
            date(2026, 1, 1), date(2026, 2, 28), CAMPO_PAGAMENTO
        )

        assert aviso == ""
        assert len(df) == 2
        assert set(df["categoria_codigo"]) == {"CONSIG_PRIV"}
        assert set(df["grupo_dashboard"]) == {"CLT"}
