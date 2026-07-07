"""Testes do formatador central de tabelas.

Foco: garantir que toda coluna de data — datetime64 (inclusive
tz-aware/UTC) ou texto ISO ('yyyy-mm-dd', com hora/UTC) — seja exibida
no padrao dd/mm/aaaa via column_config (DatetimeColumn), sem
falso-positivo em codigos/textos, e que colunas moeda/percentual/
numero recebam formatters BR no Styler mantendo o dado numerico
(ordenacao correta no st.dataframe).
"""

import pandas as pd

from src.dashboard.components.tables import (
    _formatar_moeda_br,
    _formatar_numero_br,
    _formatar_percentual_br,
    _formatar_pontos_br,
    _preparar_exibicao_br,
)


def _prep(df: pd.DataFrame):
    return _preparar_exibicao_br(df, None, None, None)


class TestFormatacaoDatas:
    def test_datetime64_recebe_config_ddmmaaaa(self):
        df = pd.DataFrame(
            {"DATA": pd.to_datetime(["2026-06-19", "2026-01-05"])}
        )
        df_conv, _, config_datas = _prep(df)
        assert "DATA" in config_datas
        assert pd.api.types.is_datetime64_any_dtype(df_conv["DATA"])

    def test_texto_iso_convertido_para_datetime(self):
        df = pd.DataFrame({"DATA_CADASTRO": ["2026-06-19", "2026-01-05"]})
        df_conv, _, config_datas = _prep(df)
        assert "DATA_CADASTRO" in config_datas
        assert pd.api.types.is_datetime64_any_dtype(
            df_conv["DATA_CADASTRO"]
        )
        assert df_conv["DATA_CADASTRO"].dt.strftime("%d/%m/%Y").tolist() == [
            "19/06/2026",
            "05/01/2026",
        ]

    def test_texto_iso_com_hora_utc(self):
        df = pd.DataFrame(
            {"IMPORTED_AT": ["2026-06-22T15:21:22.347716+00:00"]}
        )
        df_conv, _, config_datas = _prep(df)
        assert "IMPORTED_AT" in config_datas
        assert df_conv["IMPORTED_AT"].dt.strftime("%d/%m/%Y").tolist() == [
            "22/06/2026"
        ]

    def test_datetime_tz_aware(self):
        df = pd.DataFrame(
            {
                "CREATED_AT": pd.to_datetime(
                    ["2026-06-22T15:21:22+00:00"], utc=True
                )
            }
        )
        _, _, config_datas = _prep(df)
        assert "CREATED_AT" in config_datas

    def test_nulo_vira_nat(self):
        df = pd.DataFrame({"DATA_CADASTRO": ["2026-06-19", None]})
        df_conv, _, config_datas = _prep(df)
        assert "DATA_CADASTRO" in config_datas
        assert df_conv["DATA_CADASTRO"].isna().tolist() == [False, True]

    def test_nao_formata_texto_nao_data(self):
        df = pd.DataFrame(
            {"STATUS_BANCO": ["EM ANALISE", "PAGO AO CLIENTE"]}
        )
        df_conv, formatos, config_datas = _prep(df)
        assert config_datas == {}
        assert formatos == {}
        assert df_conv["STATUS_BANCO"].tolist() == [
            "EM ANALISE",
            "PAGO AO CLIENTE",
        ]

    def test_codigo_parecido_com_data_nao_e_convertido(self):
        # Casa o padrao ISO mas e data invalida (mes 56) -> deixa intacto.
        df = pd.DataFrame({"CODIGO": ["1234-56-78", "4321-99-00"]})
        df_conv, _, config_datas = _prep(df)
        assert config_datas == {}
        assert df_conv["CODIGO"].tolist() == ["1234-56-78", "4321-99-00"]


class TestFormatacaoNumerica:
    def test_moeda_mantem_valor_numerico_e_formata_br(self):
        df = pd.DataFrame({"Valor": [1234.5, 9.0]})
        df_conv, formatos, _ = _prep(df)
        # Dado bruto intacto -> ordenacao numerica correta
        assert df_conv["Valor"].tolist() == [1234.5, 9.0]
        assert formatos["Valor"] is _formatar_moeda_br
        assert _formatar_moeda_br(1234.5) == "R$ 1.234,50"

    def test_percentual_formata_br(self):
        df = pd.DataFrame({"% Ating": [95.25]})
        _, formatos, _ = _prep(df)
        assert formatos["% Ating"] is _formatar_percentual_br
        assert _formatar_percentual_br(95.25) == "95,2%"
        assert _formatar_percentual_br(None) == ""

    def test_numero_formata_br(self):
        df = pd.DataFrame({"Qtd": [1500]})
        _, formatos, _ = _prep(df)
        assert formatos["Qtd"] is _formatar_numero_br
        assert _formatar_numero_br(1500) == "1.500"

    def test_nulos_formatam_vazio(self):
        assert _formatar_moeda_br(None) == ""
        assert _formatar_numero_br(None) == ""
        assert _formatar_pontos_br(None) == ""


class TestFormatacaoPontos:
    def test_pontos_por_keyword_formato_contabil(self):
        df = pd.DataFrame({"Pontos": [1234.5]})
        _, formatos, _ = _prep(df)
        assert formatos["Pontos"] is _formatar_pontos_br
        assert _formatar_pontos_br(1234.5) == "1.234,50"
        assert _formatar_pontos_br(1234.567) == "1.234,57"

    def test_pontos_explicito_minusculo(self):
        df = pd.DataFrame({"pontos": [10.0]})
        df_conv, formatos, _ = _preparar_exibicao_br(
            df, None, None, None, ["pontos"]
        )
        assert formatos["pontos"] is _formatar_pontos_br
        # Dado bruto intacto -> ordenacao numerica correta
        assert df_conv["pontos"].tolist() == [10.0]

    def test_meta_prata_ouro_sao_pontos(self):
        df = pd.DataFrame(
            {"Meta Prata": [5000], "Meta Ouro": [8000]}
        )
        _, formatos, _ = _prep(df)
        assert formatos["Meta Prata"] is _formatar_pontos_br
        assert formatos["Meta Ouro"] is _formatar_pontos_br

    def test_total_pontos_prioriza_pontos_sobre_total(self):
        # "TOTAL" e keyword de numero; "Pontos" deve vencer
        df = pd.DataFrame({"TOTAL Pontos": [99.9]})
        _, formatos, _ = _prep(df)
        assert formatos["TOTAL Pontos"] is _formatar_pontos_br

    def test_qtd_continua_inteiro(self):
        df = pd.DataFrame({"Qtd": [15]})
        _, formatos, _ = _prep(df)
        assert formatos["Qtd"] is _formatar_numero_br


class TestBotaoExportarCsv:
    def test_csv_utf8_com_bom_para_excel(self, monkeypatch):
        """Sem BOM o Excel pt-BR assume cp1252 e corrompe acentos."""
        import src.dashboard.components.tables as tables

        capturado = {}
        monkeypatch.setattr(
            tables.st,
            "download_button",
            lambda **kwargs: capturado.update(kwargs),
        )

        df = pd.DataFrame(
            {"Consultor": ["João Conceição"], "Região": ["São Paulo"]}
        )
        tables.botao_exportar_csv(df, "ranking_teste", "exp_teste")

        dados = capturado["data"]()
        assert isinstance(dados, bytes)
        assert dados.startswith(b"\xef\xbb\xbf")
        texto = dados.decode("utf-8-sig")
        assert "João Conceição" in texto
        assert ";" in texto
