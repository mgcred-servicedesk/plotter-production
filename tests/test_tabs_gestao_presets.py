"""
Testes dos helpers puros de presets em
``src/dashboard/tabs/gestao_consultores.py``.

Um preset e a serializacao do recorte inteiro da aba (nivel, metrica,
combinacao, produtos e criterios) gravada em ``gestao_presets`` como
jsonb. O que precisa ser garantido aqui e o ida-e-volta: o que
``_config_atual`` grava, ``_rotulo_de`` reconhece de volta como opcao
de widget — inclusive quando o preset vem de uma versao anterior da
aba, sem alguma chave.
"""
from datetime import date

import pytest

from src.dashboard.loaders import (
    CAMPO_CADASTRO,
    CAMPO_PAGAMENTO,
    MAX_MESES_INTERVALO,
    meses_do_intervalo,
)
from src.dashboard.kpis.gestao import (
    BASE_MEDIA_REGIAO,
    NIVEL_CONSULTOR,
    COMB_MINIMO,
    METRICA_TICKET,
    NIVEL_LOJA,
)
from src.dashboard.tabs.gestao_consultores import (
    _ATALHOS_PERIODO,
    _competencias_fechadas,
    _BASES,
    _COMBINACOES,
    _METRICAS,
    _MODOS,
    _NIVEIS,
    _config_atual,
    _data_por_extenso,
    _datas_do_preset,
    _motivo_meta_indisponivel,
    _periodo_config,
    _rotulo_de,
    faixa_do_atalho,
)


@pytest.mark.unit
class TestRotuloDe:
    def test_encontra_o_rotulo_do_valor_interno(self):
        assert _rotulo_de(_NIVEIS, NIVEL_LOJA, "Consultor") == "Loja"
        assert _rotulo_de(_METRICAS, METRICA_TICKET, "x") == (
            "Ticket medio (R$)"
        )
        assert _rotulo_de(_BASES, BASE_MEDIA_REGIAO, "x") == (
            "% da media da regiao"
        )

    def test_valor_desconhecido_cai_no_padrao(self):
        """Preset gravado por uma versao futura nao pode quebrar a aba."""
        assert _rotulo_de(_NIVEIS, "supervisor_regional", "Consultor") == (
            "Consultor"
        )
        assert _rotulo_de(_METRICAS, None, "Valor pago (R$)") == (
            "Valor pago (R$)"
        )

    def test_todos_os_valores_internos_sao_reconheciveis(self):
        """Nenhum mapa da UI pode ter valor sem rotulo correspondente."""
        for mapa in (_NIVEIS, _METRICAS, _MODOS, _BASES, _COMBINACOES):
            for rotulo, interno in mapa.items():
                assert _rotulo_de(mapa, interno, "__padrao__") == rotulo


@pytest.mark.unit
class TestConfigAtual:
    def test_serializa_o_recorte_inteiro(self):
        criterios = {
            "CLT": {"modo": "ate", "base": "media_grupo", "max": 80.0}
        }
        config = _config_atual(
            NIVEL_LOJA,
            METRICA_TICKET,
            COMB_MINIMO,
            2,
            False,
            ["CLT", "CNC"],
            criterios,
        )
        assert config == {
            "nivel": NIVEL_LOJA,
            "metrica": METRICA_TICKET,
            "combinacao": COMB_MINIMO,
            "minimo": 2,
            "incluir_zerados": False,
            "produtos": ["CLT", "CNC"],
            "criterios": criterios,
            "periodo": {"ativo": False},
        }

    def test_config_sobrevive_ao_ida_e_volta_dos_rotulos(self):
        config = _config_atual(
            NIVEL_LOJA, METRICA_TICKET, COMB_MINIMO, 1, True, [], {}
        )
        assert _rotulo_de(_NIVEIS, config["nivel"], "Consultor") == "Loja"
        assert _rotulo_de(_METRICAS, config["metrica"], "x") == (
            "Ticket medio (R$)"
        )
        assert _rotulo_de(_COMBINACOES, config["combinacao"], "x") == (
            "Pelo menos N criterios"
        )

    def test_tipos_serializaveis_em_json(self):
        """jsonb nao aceita numpy/bool do pandas — precisa ser nativo."""
        import json

        config = _config_atual(
            NIVEL_LOJA, METRICA_TICKET, COMB_MINIMO, 3, True, ["CNC"], {}
        )
        assert json.loads(json.dumps(config)) == config
        assert isinstance(config["minimo"], int)
        assert isinstance(config["incluir_zerados"], bool)


@pytest.mark.unit
class TestPeriodoNoPreset:
    def test_periodo_inativo(self):
        assert _periodo_config(False, None, None, CAMPO_PAGAMENTO) == {
            "ativo": False
        }

    def test_periodo_ativo_grava_datas_iso(self):
        cfg = _periodo_config(
            True, date(2026, 5, 1), date(2026, 6, 30), CAMPO_CADASTRO
        )
        assert cfg == {
            "ativo": True,
            "data_ini": "2026-05-01",
            "data_fim": "2026-06-30",
            "campo": CAMPO_CADASTRO,
        }

    def test_ativo_sem_datas_nao_grava_intervalo_quebrado(self):
        """Range meio-preenchido nao pode virar preset invalido."""
        assert _periodo_config(True, date(2026, 5, 1), None, "DATA") == {
            "ativo": False
        }

    def test_ida_e_volta_das_datas(self):
        cfg = _periodo_config(
            True, date(2026, 5, 1), date(2026, 6, 30), CAMPO_PAGAMENTO
        )
        assert _datas_do_preset(cfg) == (date(2026, 5, 1), date(2026, 6, 30))

    def test_preset_com_data_corrompida_nao_quebra(self):
        for periodo in (
            {"ativo": True, "data_ini": "31/05/2026", "data_fim": "x"},
            {"ativo": True, "data_ini": "2026-05-01"},
            {"ativo": True, "data_ini": None, "data_fim": None},
            {},
        ):
            assert _datas_do_preset(periodo) is None

    def test_preset_com_fim_antes_do_inicio_e_descartado(self):
        periodo = {
            "ativo": True,
            "data_ini": "2026-06-30",
            "data_fim": "2026-05-01",
        }
        assert _datas_do_preset(periodo) is None

    def test_config_com_periodo_e_serializavel(self):
        import json

        cfg = _config_atual(
            NIVEL_LOJA,
            METRICA_TICKET,
            COMB_MINIMO,
            1,
            True,
            ["CNC"],
            {},
            _periodo_config(
                True, date(2026, 5, 1), date(2026, 5, 31), CAMPO_PAGAMENTO
            ),
        )
        assert json.loads(json.dumps(cfg)) == cfg


@pytest.mark.unit
class TestMotivoMetaIndisponivel:
    """O aviso precisa apontar a razao REAL, na ordem em que ela cai."""

    def test_periodo_personalizado_vence_os_demais(self):
        msg = _motivo_meta_indisponivel(True, NIVEL_CONSULTOR)
        assert "MENSAL" in msg and "intervalo" in msg

    def test_nivel_acima_de_consultor(self):
        msg = _motivo_meta_indisponivel(False, NIVEL_LOJA)
        assert NIVEL_LOJA in msg

    def test_produto_sem_alvo_individual(self):
        msg = _motivo_meta_indisponivel(False, NIVEL_CONSULTOR)
        assert "conjunta" in msg


@pytest.mark.unit
class TestFaixaDoAtalho:
    """Atalhos em pt-BR que substituem o quick-select ingles do calendario."""

    def test_mes_atual(self):
        assert faixa_do_atalho("Mes atual", date(2026, 7, 15)) == (
            date(2026, 7, 1), date(2026, 7, 15)
        )

    def test_mes_anterior_fecha_no_ultimo_dia(self):
        assert faixa_do_atalho("Mes anterior", date(2026, 7, 15)) == (
            date(2026, 6, 1), date(2026, 6, 30)
        )

    def test_mes_anterior_em_janeiro_volta_o_ano(self):
        assert faixa_do_atalho("Mes anterior", date(2026, 1, 10)) == (
            date(2025, 12, 1), date(2025, 12, 31)
        )

    def test_mes_anterior_de_marco_pega_fevereiro_bissexto(self):
        assert faixa_do_atalho("Mes anterior", date(2024, 3, 5)) == (
            date(2024, 2, 1), date(2024, 2, 29)
        )

    def test_ultimos_30_dias_conta_hoje(self):
        """30 dias inclusivos: hoje e um deles."""
        ini, fim = faixa_do_atalho("Ultimos 30 dias", date(2026, 7, 30))
        assert (fim - ini).days == 29
        assert fim == date(2026, 7, 30)
        assert ini == date(2026, 7, 1)

    def test_ultimos_3_meses_sao_corridos_nao_90_dias(self):
        assert faixa_do_atalho("Ultimos 3 meses", date(2026, 7, 15)) == (
            date(2026, 5, 1), date(2026, 7, 15)
        )

    def test_ultimos_3_meses_virando_o_ano(self):
        assert faixa_do_atalho("Ultimos 3 meses", date(2026, 2, 10)) == (
            date(2025, 12, 1), date(2026, 2, 10)
        )

    def test_ano_ate_agora_foi_removido(self):
        """Varreria 12 meses em dezembro — consulta que o Nano nao aguenta."""
        assert "Ano ate agora" not in _ATALHOS_PERIODO
        assert faixa_do_atalho("Ano ate agora", date(2026, 7, 15)) is None

    def test_atalho_desconhecido(self):
        assert faixa_do_atalho("Decada passada", date(2026, 7, 15)) is None

    def test_nenhum_atalho_estoura_o_teto_de_meses(self):
        """Atalho nao pode gerar faixa que o loader vai recusar."""
        hoje = date(2026, 12, 31)
        for nome in _ATALHOS_PERIODO:
            ini, fim = faixa_do_atalho(nome, hoje)
            meses = meses_do_intervalo(ini, fim, CAMPO_PAGAMENTO)
            assert 0 < len(meses) <= MAX_MESES_INTERVALO, nome

    def test_faixas_sempre_terminam_em_ou_antes_de_hoje(self):
        hoje = date(2026, 7, 15)
        for nome in _ATALHOS_PERIODO:
            ini, fim = faixa_do_atalho(nome, hoje)
            assert ini <= fim
            assert fim <= hoje


@pytest.mark.unit
class TestDataPorExtenso:
    def test_dia_um_usa_ordinal(self):
        assert _data_por_extenso(date(2026, 6, 1)) == "1º de junho de 2026"

    def test_demais_dias_usam_cardinal(self):
        assert _data_por_extenso(date(2026, 7, 15)) == "15 de julho de 2026"

    def test_mes_com_acento(self):
        assert _data_por_extenso(date(2026, 3, 9)) == "9 de março de 2026"

    def test_todos_os_meses_tem_nome(self):
        for mes in range(1, 13):
            texto = _data_por_extenso(date(2026, mes, 10))
            assert "de  de" not in texto and texto.count(" de ") == 2


# ══════════════════════════════════════════════════════
# Sub-visao Performance: janela de competencias fechadas
# ══════════════════════════════════════════════════════


@pytest.mark.unit
class TestCompetenciasFechadas:
    def test_mes_corrente_nunca_entra_na_serie(self):
        """Mes pela metade ao lado de meses inteiros desenha queda falsa."""
        hoje = date(2026, 8, 31)
        out = _competencias_fechadas(8, 2026, 3, hoje=hoje)

        assert (8, 2026) not in out
        assert out == [(5, 2026), (6, 2026), (7, 2026)]

    def test_mes_fechado_entra_como_ultimo_da_janela(self):
        out = _competencias_fechadas(7, 2026, 3, hoje=date(2026, 8, 31))

        assert out[-1] == (7, 2026)
        assert out == [(5, 2026), (6, 2026), (7, 2026)]

    def test_ordem_crescente(self):
        out = _competencias_fechadas(6, 2026, 6, hoje=date(2026, 8, 31))

        assert out == sorted(out, key=lambda c: (c[1], c[0]))

    def test_atravessa_a_virada_de_ano(self):
        out = _competencias_fechadas(2, 2026, 4, hoje=date(2026, 8, 31))

        assert out == [(11, 2025), (12, 2025), (1, 2026), (2, 2026)]

    def test_mes_futuro_cai_para_o_ultimo_fechado(self):
        out = _competencias_fechadas(12, 2026, 2, hoje=date(2026, 8, 31))

        assert out == [(6, 2026), (7, 2026)]

    def test_janela_zero_devolve_vazio(self):
        assert _competencias_fechadas(7, 2026, 0, hoje=date(2026, 8, 31)) == []
