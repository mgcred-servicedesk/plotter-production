"""Testes do formatador central de tabelas.

Foco: garantir que toda coluna de data — datetime64 (inclusive
tz-aware/UTC) ou texto ISO ('yyyy-mm-dd', com hora/UTC) — seja exibida
no padrao dd/mm/aaaa, sem falso-positivo em codigos/textos.
"""

import pandas as pd

from src.dashboard.components.tables import _formatar_dataframe_br


def _fmt(df: pd.DataFrame) -> pd.DataFrame:
    return _formatar_dataframe_br(df, None, None, None)


class TestFormatacaoDatas:
    def test_datetime64_para_ddmmaaaa(self):
        df = pd.DataFrame(
            {"DATA": pd.to_datetime(["2026-06-19", "2026-01-05"])}
        )
        assert _fmt(df)["DATA"].tolist() == ["19/06/2026", "05/01/2026"]

    def test_texto_iso_para_ddmmaaaa(self):
        df = pd.DataFrame({"DATA_CADASTRO": ["2026-06-19", "2026-01-05"]})
        out = _fmt(df)
        assert out["DATA_CADASTRO"].tolist() == ["19/06/2026", "05/01/2026"]

    def test_texto_iso_com_hora_utc(self):
        df = pd.DataFrame(
            {"IMPORTED_AT": ["2026-06-22T15:21:22.347716+00:00"]}
        )
        assert _fmt(df)["IMPORTED_AT"].tolist() == ["22/06/2026"]

    def test_datetime_tz_aware(self):
        df = pd.DataFrame(
            {
                "CREATED_AT": pd.to_datetime(
                    ["2026-06-22T15:21:22+00:00"], utc=True
                )
            }
        )
        assert _fmt(df)["CREATED_AT"].tolist() == ["22/06/2026"]

    def test_nulo_vira_string_vazia(self):
        df = pd.DataFrame({"DATA_CADASTRO": ["2026-06-19", None]})
        assert _fmt(df)["DATA_CADASTRO"].tolist() == ["19/06/2026", ""]

    def test_nao_formata_texto_nao_data(self):
        df = pd.DataFrame(
            {"STATUS_BANCO": ["EM ANALISE", "PAGO AO CLIENTE"]}
        )
        out = _fmt(df)
        assert out["STATUS_BANCO"].tolist() == [
            "EM ANALISE",
            "PAGO AO CLIENTE",
        ]

    def test_codigo_parecido_com_data_nao_e_convertido(self):
        # Casa o padrao ISO mas e data invalida (mes 56) -> deixa intacto,
        # nao vira vazio.
        df = pd.DataFrame({"CODIGO": ["1234-56-78", "4321-99-00"]})
        out = _fmt(df)
        assert out["CODIGO"].tolist() == ["1234-56-78", "4321-99-00"]
