"""
Testes dos helpers puros de presets em
``src/dashboard/tabs/gestao_consultores.py``.

Um preset e a serializacao do recorte inteiro da aba (nivel, metrica,
combinacao, produtos e criterios) gravada em ``gestao_presets`` como
jsonb. O que precisa ser garantido aqui e o ida-e-volta: o que
``_config_atual`` grava, ``_rotulo_de`` reconhece de volta como opcao
de widget — inclusive quando o preset vem de uma versao anterior da
aba, sem alguma chave.

Alem dos helpers puros, o modulo cobre o que a aba DESENHA: o
bloqueio de produtividade no periodo personalizado, o aviso de meta
indisponivel e a legenda de producao sem vinculo em ``_render_criterios``
(sob ``AppTest``, porque dependem de estado de widget) e a competencia
indisponivel da serie em ``_render_tendencia``.
"""
import re
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.config.settings import PACK_SPLIT_LABELS
from src.dashboard.formatters import formatar_moeda
from src.dashboard.loaders import (
    CAMPO_CADASTRO,
    CAMPO_PAGAMENTO,
    MAX_MESES_INTERVALO,
    meses_do_intervalo,
)
from src.dashboard.kpis.gestao import (
    BASE_ABSOLUTA,
    BASE_MEDIA_GRUPO,
    BASE_MEDIA_REGIAO,
    BASE_META,
    COL_TOTAL,
    MODO_ATE,
    MODO_ENTRE,
    NIVEL_CONSULTOR,
    COMB_MINIMO,
    METRICA_PROD_DIA,
    METRICA_TICKET,
    METRICA_VALOR,
    NIVEL_LOJA,
    NIVEL_REGIAO,
    NIVEL_SUPERVISOR,
    construir_tabela,
    diagnosticar_criterios,
    matriz_metas,
)
from src.dashboard.kpis.produtividade import (
    COL_CONSULTOR as COL_CONSULTOR_PROD,
    COL_DIAS as COL_DIAS_PROD,
    COL_IDX_CARTEIRA,
    COL_PROD_DIA,
    COL_PRODUCAO as COL_PRODUCAO_PROD,
    COL_SHARE_LOJA,
    produtividade_por_consultor,
)
from src.dashboard.tabs import gestao_consultores as tab
from src.dashboard.tabs.gestao_consultores import (
    _CORTE_MAX,
    _recortar_e_ordenar,
    _ATALHOS_PERIODO,
    _COLUNAS_CRITERIO,
    _PRODUTOS_DEFAULT,
    _competencias_fechadas,
    _du_apuracao,
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


def _rotulo(mapa, interno):
    """Rotulo de UI de um valor interno; falha alto se o mapa mudou."""
    rotulos = [r for r, v in mapa.items() if v == interno]
    assert len(rotulos) == 1, interno
    return rotulos[0]


def _rotulos_citados(texto):
    """Rotulos de criterio que um aviso nomeia, sem o Total.

    O aviso de meta sempre fala do Total; o que distingue as causas e
    QUEM MAIS ele aponta. Os rotulos mais longos primeiro, para que
    'CNC 13º' nao seja lido como 'CNC'.
    """
    rotulos = sorted(_COLUNAS_CRITERIO, key=len, reverse=True)
    padrao = "|".join(re.escape(r) for r in rotulos)
    return set(re.findall(padrao, texto)) - {COL_TOTAL}


def _dados_meta(**metas):
    """Metas do mes das lojas A e B: uma coluna por ``NOME=valor``.

    ``CNC``, ``CLT``, ``SAQUE``, ``CONSIGNADO`` sao individuais;
    ``FGTS_ANT_BENEF_13`` e a meta CONJUNTA do pack.
    """
    return pd.DataFrame(
        {"LOJA": ["A", "B"], **{nome: [v, v] for nome, v in metas.items()}}
    )


def _tabela_e_metas(produtos, dados_meta):
    """Tabela e matriz de metas pelas funcoes reais, como a aba as monta."""
    df = pd.DataFrame({
        "CONSULTOR": ["ANA", "BIA"], "LOJA": ["A", "B"],
        "REGIAO": ["R1", "R1"], "categoria_codigo": ["CNC", "CNC"],
        "VALOR": [1000.0, 2000.0],
    })
    tabela = construir_tabela(df, produtos_total=produtos or None)
    metas = matriz_metas(tabela, dados_meta, produtos_total=produtos or None)
    return tabela, metas


def _motivo_do_total(produtos, dados_meta):
    """Aviso de um criterio Total ('% da meta') que a aba ignorou."""
    tabela, metas = _tabela_e_metas(produtos, dados_meta)
    criterios = {
        COL_TOTAL: {"modo": MODO_ATE, "base": BASE_META, "max": 80.0}
    }
    ignorados = diagnosticar_criterios(tabela, criterios, metas)
    # Guarda do cenario: e a meta do Total que falta, nao outra coisa.
    assert ignorados == [COL_TOTAL]
    return _motivo_meta_indisponivel(
        False, NIVEL_CONSULTOR, ignorados, METRICA_VALOR,
        produtos_total=produtos, metas=metas,
    )


_PACK = list(PACK_SPLIT_LABELS.values())  # FGTS, ANT. DE BENEF., CNC 13º


@pytest.mark.unit
class TestMotivoMetaPorGrupo:
    """No nivel consultor cada grupo ignorado ganha a PROPRIA razao.

    Antes, todo criterio ignorado caia no texto do pack ('meta
    conjunta') ou, em prod_dia, num 'a aba desliga a base' que nem
    sempre era verdade. Agora a razao sai do que faltou de fato na
    matriz de metas. Um motivo certo para o produto errado manda o
    gestor investigar a coisa errada.
    """

    def test_acelerador_em_prod_dia_tem_a_mesma_razao_que_em_valor(self):
        """O alvo do acelerador e em contratos e vale em QUALQUER metrica.

        'A aba desliga a base nesta metrica' seria falso para ele: a
        razao que sobra e a de sempre, nenhuma meta gravada.
        """
        ignorados = ["BMG Med", "Emissao"]

        em_prod_dia = _motivo_meta_indisponivel(
            False, NIVEL_CONSULTOR, ignorados, METRICA_PROD_DIA
        )
        em_valor = _motivo_meta_indisponivel(
            False, NIVEL_CONSULTOR, ignorados, METRICA_VALOR
        )

        assert em_prod_dia == em_valor
        assert "desliga" not in em_prod_dia
        assert _rotulos_citados(em_prod_dia) == {"BMG Med", "Emissao"}

    def test_nivel_acima_de_consultor_vence_a_metrica_no_acelerador(self):
        msg = _motivo_meta_indisponivel(
            False, NIVEL_LOJA, ["BMG Med"], METRICA_PROD_DIA
        )

        assert NIVEL_LOJA in msg
        assert "desliga" not in msg

    def test_total_com_pack_parcial_aponta_so_o_pack_selecionado(self):
        produtos = ["CLT", "FGTS"]

        msg = _motivo_do_total(
            produtos, _dados_meta(CLT=8.0, FGTS_ANT_BENEF_13=3.0)
        )

        # O CLT tem meta em toda loja: nao pode ser apontado.
        assert _rotulos_citados(msg) == {"FGTS"}

    @pytest.mark.parametrize(
        "dados_meta",
        [
            pytest.param(_dados_meta(CNC=10.0), id="coluna_ausente"),
            pytest.param(_dados_meta(CNC=10.0, CLT=None), id="coluna_vazia"),
        ],
    )
    def test_total_com_produto_sem_meta_aponta_o_produto(self, dados_meta):
        msg = _motivo_do_total(["CNC", "CLT"], dados_meta)

        assert _rotulos_citados(msg) == {"CLT"}
        # Nao e problema de pack, e o texto nao manda olhar para la.
        assert "pack" not in msg

    def test_total_com_pack_inteiro_sem_meta_conjunta_nao_culpa_produto(
        self,
    ):
        """Todo produto tem meta e o pack esta completo: falta o alvo
        conjunto, que nao e de nenhum item."""
        msg = _motivo_do_total(["CNC", *_PACK], _dados_meta(CNC=10.0))

        assert _rotulos_citados(msg) == set()

    def test_sem_selecao_explicita_o_total_vale_o_mix_inteiro(self):
        """``produtos_total`` vazio e o MIX inteiro, como na tabela."""
        msg = _motivo_do_total(
            [],
            _dados_meta(
                CNC=10.0, CLT=8.0, CONSIGNADO=5.0, FGTS_ANT_BENEF_13=3.0
            ),  # sem Saque
        )

        assert _rotulos_citados(msg) == {"Saque"}

    def test_mes_sem_nenhuma_meta_aponta_todos_os_produtos_do_total(self):
        msg = _motivo_do_total(["CNC", "CLT"], pd.DataFrame())

        assert _rotulos_citados(msg) == {"CNC", "CLT"}

    def test_causas_diferentes_do_mesmo_criterio_dao_razoes_diferentes(self):
        """O Total e o criterio ignorado nos tres; a causa muda."""
        razoes = {
            _motivo_do_total(
                ["CLT", "FGTS"], _dados_meta(CLT=8.0, FGTS_ANT_BENEF_13=3.0)
            ),
            _motivo_do_total(["CNC", "CLT"], _dados_meta(CNC=10.0)),
            _motivo_do_total(["CNC", *_PACK], _dados_meta(CNC=10.0)),
        }

        assert len(razoes) == 3

    def test_varios_grupos_ignorados_somam_a_razao_de_cada_um(self):
        """Produto, item do pack, Total e acelerador no mesmo aviso."""
        produtos = ["CLT", "FGTS"]
        _, metas = _tabela_e_metas(produtos, _dados_meta())
        contexto = dict(produtos_total=produtos, metas=metas)
        grupos = [["CLT"], ["FGTS"], [COL_TOTAL], ["Emissao"]]

        por_grupo = [
            _motivo_meta_indisponivel(
                False, NIVEL_CONSULTOR, grupo, METRICA_VALOR, **contexto
            )
            for grupo in grupos
        ]
        junto = _motivo_meta_indisponivel(
            False, NIVEL_CONSULTOR,
            [rotulo for grupo in grupos for rotulo in grupo],
            METRICA_VALOR, **contexto,
        )

        assert len(set(por_grupo)) == len(grupos)
        assert all(razao in junto for razao in por_grupo)


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


@pytest.mark.unit
class TestDuApuracao:
    """Referencia dos cards de dias em Performance do time.

    Devolve ``(DU considerados, DU do mes)``. Os dois so divergem no
    mes em curso, onde o loader trunca os dias elegiveis na ultima data
    com dado — e o card precisa dizer "de N DU decorridos" em vez de
    "na competencia".
    """

    def _vinculos(self, du_mes, du_dec=None):
        dados = {
            "CONSULTOR": ["ANA", "BIA"],
            "DIAS_ELEGIVEIS": [20, 10],
            "DU_COMPETENCIA": du_mes,
        }
        if du_dec is not None:
            dados["DU_DECORRIDOS"] = du_dec
        return pd.DataFrame(dados)

    def test_competencia_fechada_nao_diverge(self):
        assert _du_apuracao(self._vinculos([21, 21], [21, 21])) == (21, 21)

    def test_mes_em_curso_devolve_o_decorrido_e_o_do_mes(self):
        """O card le 2 como teto, mas ainda sabe que o mes tem 21."""
        assert _du_apuracao(self._vinculos([21, 21], [2, 2])) == (2, 21)

    def test_sem_a_coluna_de_decorridos_cai_para_o_du_do_mes(self):
        """Retrocompat: frame antigo (sem truncagem) nao quebra o card."""
        assert _du_apuracao(self._vinculos([21, 21])) == (21, 21)

    def test_sem_nenhuma_coluna_de_du(self):
        df = self._vinculos([21, 21]).drop(columns=["DU_COMPETENCIA"])

        assert _du_apuracao(df) == (None, None)

    def test_vinculos_vazio_ou_ausente(self):
        assert _du_apuracao(None) == (None, None)
        assert _du_apuracao(pd.DataFrame()) == (None, None)

    def test_du_nulo_ou_zero_nao_vira_referencia(self):
        assert _du_apuracao(self._vinculos([None, None])) == (None, None)
        assert _du_apuracao(self._vinculos([0, 0])) == (None, None)


@pytest.mark.unit
class TestCorteEOrdenacaoDaPerformance:
    """O corte e a ordenacao nao podem esconder indice AUSENTE.

    Indice ``NaN`` acontece quando a loja inteira nao vendeu no
    periodo: o benchmark do grupo vai a zero e a divisao devolve
    ausente. Sao pessoas com R$ 0/dia — o pior caso possivel —, e as
    duas leituras que existem para achar baixa performance (o corte e a
    ordem crescente) as escondiam.
    """

    def _prod(self):
        """Tres pessoas: uma acima da rede, uma abaixo, uma sem indice."""
        return pd.DataFrame({
            COL_CONSULTOR_PROD: ["FORTE", "FRACA", "SEM INDICE"],
            COL_DIAS_PROD: [20, 20, 20],
            COL_PRODUCAO_PROD: [20000.0, 2000.0, 0.0],
            COL_PROD_DIA: [1000.0, 100.0, 0.0],
            COL_IDX_CARTEIRA: [180.0, 18.0, float("nan")],
            COL_SHARE_LOJA: [75.0, 25.0, float("nan")],
        })

    def test_corte_baixo_mantem_quem_esta_sem_indice(self):
        visao = _recortar_e_ordenar(
            self._prod(), "Menor produtividade", corte=50
        )

        nomes = set(visao[COL_CONSULTOR_PROD])
        assert "FORTE" not in nomes  # 180% da rede, acima do corte
        assert "FRACA" in nomes  # 18% da rede
        # Sem o guarda de `isna`, o `<=` descartava esta linha em
        # silencio — a pessoa que o corte de 50% mais procura.
        assert "SEM INDICE" in nomes

    def test_corte_no_maximo_nao_filtra_ninguem(self):
        visao = _recortar_e_ordenar(
            self._prod(), "Menor produtividade", corte=_CORTE_MAX
        )

        assert len(visao) == 3

    def test_ordem_crescente_poe_indice_ausente_no_topo(self):
        visao = _recortar_e_ordenar(
            self._prod(), "Mais abaixo da media da carteira",
            corte=_CORTE_MAX
        )

        # Lista do pior para o melhor: quem esta sem indice abre a
        # lista, nunca a fecha.
        assert visao.iloc[0][COL_CONSULTOR_PROD] == "SEM INDICE"
        assert visao.iloc[-1][COL_CONSULTOR_PROD] == "FORTE"

    def test_ordem_decrescente_deixa_ausente_no_fim(self):
        visao = _recortar_e_ordenar(
            self._prod(), "Maior produtividade", corte=_CORTE_MAX
        )

        assert visao.iloc[0][COL_CONSULTOR_PROD] == "FORTE"
        assert visao.iloc[-1][COL_CONSULTOR_PROD] == "SEM INDICE"

    def test_sem_dia_elegivel_nunca_entra_na_tabela(self):
        prod = self._prod()
        prod.loc[len(prod)] = {
            COL_CONSULTOR_PROD: "ORFA",
            COL_DIAS_PROD: 0,
            COL_PRODUCAO_PROD: 5000.0,
            COL_PROD_DIA: float("nan"),
            COL_IDX_CARTEIRA: float("nan"),
            COL_SHARE_LOJA: float("nan"),
        }

        visao = _recortar_e_ordenar(
            prod, "Menor produtividade", corte=_CORTE_MAX
        )

        # Producao sem vinculo tem expander proprio de diagnostico; na
        # tabela ela viraria uma linha sem denominador nenhum.
        assert "ORFA" not in set(visao[COL_CONSULTOR_PROD])


# ══════════════════════════════════════════════════════
# Sub-visao Criterios sob AppTest: bloqueio, aviso de meta, legenda
# ══════════════════════════════════════════════════════
#
# O que importa aqui depende de estado de widget, e widget so "vale"
# dentro de um script run: fora dele todo widget volta ao padrao e
# `session_state` nao o segura. Por isso estes testes rodam
# `_render_criterios` de verdade em `AppTest.from_function` (mesmo
# padrao de test_tabs_analiticos_reconquista_carteira.py) e conferem
# estado de widget, chamadas e o que foi desenhado — nao o que um `st`
# falso registrou. `_render_tendencia`, sem widget que decida o
# resultado, segue com `st` falso (secao mais abaixo).

_PROD_DIA = _rotulo(_METRICAS, METRICA_PROD_DIA)
_VALOR = _rotulo(_METRICAS, METRICA_VALOR)


def _script_criterios(df, vinculos, metas, com_periodo):
    from src.dashboard.tabs import gestao_consultores as tab

    tab._render_criterios(
        df, None, None, metas,
        carregar_intervalo=(
            (lambda ini, fim, campo: (df, None)) if com_periodo else None
        ),
        df_vinculos=vinculos,
    )


@pytest.fixture
def ambiente(monkeypatch):
    """Costuras de I/O da aba trocadas por stubs; devolve o que registrou.

    ``tabelas``: ``metrica`` de cada chamada a ``construir_tabela``
    (espiao que chama a funcao real, para a aba seguir renderizando).
    ``salvos``: configs enviadas a ``salvar_preset_gestao``.
    Tudo por ``monkeypatch``: nada vaza para os outros testes do modulo.
    """
    registro = SimpleNamespace(tabelas=[], salvos=[])
    construir_real = tab.construir_tabela

    def espiao(*args, **kwargs):
        registro.tabelas.append(kwargs.get("metrica"))
        return construir_real(*args, **kwargs)

    def salvar(usuario_id, nome, config, compartilhar):
        registro.salvos.append(config)
        return True, "ok"

    monkeypatch.setattr(tab, "usuario_logado", lambda: {"id": "u1"})
    monkeypatch.setattr(tab, "carregar_presets_gestao", lambda usuario_id: [])
    monkeypatch.setattr(tab, "salvar_preset_gestao", salvar)
    monkeypatch.setattr(tab, "construir_tabela", espiao)
    return registro


def _dados_criterios(com_produtor_sem_vinculo=True):
    """Pagos de duas lojas e o ledger de vinculos.

    ANA e BRUNO na loja A, CARLA na B. SEM VINCULO produziu R$ 9.500 na
    loja A (CNC 9.000 + CLT 500) e, por padrao, nao tem janela no
    ledger; com ``com_produtor_sem_vinculo=False`` ele ganha uma.
    """
    df = pd.DataFrame({
        "CONSULTOR": ["ANA", "BRUNO", "CARLA", "SEM VINCULO", "SEM VINCULO"],
        "LOJA": ["A", "A", "B", "A", "A"],
        "REGIAO": ["R1", "R1", "R2", "R1", "R1"],
        "categoria_codigo": [
            "CONSIG_PRIV", "CNC", "CNC", "CNC", "CONSIG_PRIV",
        ],
        "VALOR": [1000.0, 2000.0, 3000.0, 9000.0, 500.0],
    })
    ledger = {"ANA": ("A", "R1", 10), "BRUNO": ("A", "R1", 20),
              "CARLA": ("B", "R2", 5)}
    if not com_produtor_sem_vinculo:
        ledger["SEM VINCULO"] = ("A", "R1", 8)
    vinculos = pd.DataFrame([
        {"CONSULTOR": c, "LOJA": lj, "REGIAO": rg, "REGIAO_ATUAL": rg,
         "DIAS_ELEGIVEIS": d}
        for c, (lj, rg, d) in ledger.items()
    ])
    return df, vinculos


def _app(df, vinculos, metas=None, com_periodo=False):
    at = AppTest.from_function(
        _script_criterios, default_timeout=30,
        kwargs=dict(
            df=df, vinculos=vinculos, metas=metas, com_periodo=com_periodo
        ),
    )
    at.run()
    assert not at.exception
    return at


def _chaves(at):
    """``key`` de todos os widgets que a aba pode ter na tela."""
    return {
        w.key
        for lista in (
            at.multiselect, at.selectbox, at.number_input, at.toggle,
            at.text_input, at.button,
        )
        for w in lista
        if w.key
    }


_AUSENTE = "<ausente do session_state>"


def _estado(at, chaves):
    """Valor de cada chave no session_state; ``_AUSENTE`` se sumiu."""
    saida = {}
    for chave in chaves:
        try:
            saida[chave] = at.session_state[chave]
        except KeyError:
            saida[chave] = _AUSENTE
    return saida


def _sem_periodo(config):
    return {k: v for k, v in config.items() if k != "periodo"}


def _recorte_fora_do_padrao():
    """Cada eixo que o bloqueio nao pode zerar, longe do padrao.

    O CLT cobre modo, base, minimo e maximo. O Total leva um maximo
    ABSOLUTO cujo padrao depende da metrica (700 em R$/dia, 15.000 em
    R$): se a troca de metrica reiniciasse o widget, o valor voltaria a
    ser outro numero e o teste veria.
    """
    return {
        "gestao_produtos": ["CLT", "Total"],
        "gestao_modo_CLT": _rotulo(_MODOS, MODO_ENTRE),
        "gestao_base_CLT": _rotulo(_BASES, BASE_MEDIA_GRUPO),
        "gestao_min_CLT": 25.0,
        "gestao_max_CLT": 80.0,
        "gestao_max_Total": 456.0,
    }


def _montar_recorte(at):
    """Leva a tela ao recorte de ``_recorte_fora_do_padrao`` em prod_dia.

    Um passo por vez, como o gestor: o widget so existe depois de o
    anterior ter rodado (os controles do CLT, com o CLT selecionado; o
    minimo, com o modo Entre) e a base vem antes dos numeros que ela
    reescala.
    """
    esperado = _recorte_fora_do_padrao()
    at.selectbox(key="gestao_metrica").set_value(_PROD_DIA).run()
    at.multiselect(key="gestao_produtos").set_value(
        esperado["gestao_produtos"]
    ).run()
    at.selectbox(key="gestao_modo_CLT").set_value(
        esperado["gestao_modo_CLT"]
    ).run()
    at.selectbox(key="gestao_base_CLT").set_value(
        esperado["gestao_base_CLT"]
    ).run()
    at.number_input(key="gestao_min_CLT").set_value(esperado["gestao_min_CLT"])
    at.number_input(key="gestao_max_CLT").set_value(esperado["gestao_max_CLT"])
    at.number_input(key="gestao_max_Total").set_value(
        esperado["gestao_max_Total"]
    )
    at.run()
    assert not at.exception
    return esperado


@pytest.mark.unit
class TestBloqueioDeProdutividadeNoPeriodoPersonalizado:
    """Produtividade por dia nao fecha numa faixa livre de datas.

    Os dias elegiveis sao do mes da sidebar, nao da faixa: com periodo
    personalizado + prod_dia a aba nao apura. O bloqueio, porem, nao
    pode custar o recorte do gestor — o Streamlit descarta o estado de
    todo widget que sai da tela num run, entao produtos e limiares so
    sobrevivem se continuarem renderizados enquanto a aba espera.
    """

    def test_intervalo_personalizado_nao_calcula_taxa_com_vinculo_mensal(
        self, ambiente
    ):
        df, vinculos = _dados_criterios()
        at = _app(df, vinculos, com_periodo=True)
        at.toggle(key="gestao_periodo_ativo").set_value(True).run()
        # Controle: o periodo livre em valor apura (o espiao esta ligado).
        calculadas = len(ambiente.tabelas)
        assert calculadas > 0

        at.selectbox(key="gestao_metrica").set_value(_PROD_DIA).run()

        assert not at.exception
        assert len(ambiente.tabelas) == calculadas  # nada recalculado
        assert len(at.warning) == 1  # so o aviso do bloqueio

    @pytest.mark.parametrize("saida", ["desliga_periodo", "troca_metrica"])
    def test_recorte_sobrevive_ao_bloqueio_pelos_dois_caminhos(
        self, ambiente, saida
    ):
        df, vinculos = _dados_criterios()
        at = _app(df, vinculos, com_periodo=True)
        esperado = _montar_recorte(at)
        # Ponto de partida: nada do recorte e o que um reset devolveria.
        assert _estado(at, esperado) == esperado
        assert esperado["gestao_produtos"] != _PRODUTOS_DEFAULT
        calculadas = len(ambiente.tabelas)

        at.toggle(key="gestao_periodo_ativo").set_value(True).run()

        # Bloqueado: aviso, nenhuma apuracao e o recorte ainda na tela.
        assert not at.exception
        assert len(at.warning) == 1
        assert len(ambiente.tabelas) == calculadas
        assert set(esperado) | {
            "gestao_preset_nome", "gestao_preset_salvar",
        } <= _chaves(at)
        assert _estado(at, esperado) == esperado

        if saida == "desliga_periodo":
            at.toggle(key="gestao_periodo_ativo").set_value(False).run()
        else:
            at.selectbox(key="gestao_metrica").set_value(_VALOR).run()

        # Saiu do bloqueio: voltou a apurar, com o recorte de antes.
        assert not at.exception
        assert _estado(at, esperado) == esperado
        assert len(ambiente.tabelas) == calculadas + 1

    def test_salvar_com_o_bloqueio_ativo_grava_o_mesmo_recorte(
        self, ambiente
    ):
        """Preset salvo enquanto a aba espera nao pode sair pela metade."""
        df, vinculos = _dados_criterios()
        at = _app(df, vinculos, com_periodo=True)
        _montar_recorte(at)

        def salvar(nome):
            at.text_input(key="gestao_preset_nome").set_value(nome).run()
            at.button(key="gestao_preset_salvar").click().run()
            assert not at.exception

        salvar("normal")
        at.toggle(key="gestao_periodo_ativo").set_value(True).run()
        salvar("bloqueado")

        normal, bloqueado = ambiente.salvos
        assert normal["periodo"]["ativo"] is False
        assert bloqueado["periodo"]["ativo"] is True
        # Fora o bloco do periodo (datas de hoje), e o mesmo recorte.
        assert _sem_periodo(bloqueado) == _sem_periodo(normal)
        # E o recorte de verdade, nao dois vazios iguais.
        assert bloqueado["metrica"] == METRICA_PROD_DIA
        assert bloqueado["produtos"] == ["CLT", "Total"]
        assert bloqueado["criterios"]["CLT"] == {
            "modo": MODO_ENTRE, "base": BASE_MEDIA_GRUPO,
            "min": 25.0, "max": 80.0,
        }
        assert bloqueado["criterios"]["Total"] == {
            "modo": MODO_ATE, "base": BASE_ABSOLUTA, "max": 456.0,
        }


@pytest.mark.unit
class TestAvisoDeMetaNaAba:
    """A aba entrega ao aviso o contexto de que ele precisa.

    ``_motivo_meta_indisponivel`` so acerta a causa do Total se receber
    ``produtos_total`` e a matriz de metas; sem eles cai no texto
    generico. Aqui o que se confere e o que a aba REALMENTE mostra.
    """

    def _aviso_do_total(self, produtos, dados_meta):
        df, vinculos = _dados_criterios()
        at = _app(df, vinculos, metas=dados_meta)
        at.multiselect(key="gestao_produtos").set_value(produtos).run()
        at.selectbox(key="gestao_base_Total").set_value(
            _rotulo(_BASES, BASE_META)
        ).run()
        assert not at.exception
        return [w.value for w in at.warning]

    def test_total_sem_meta_de_produto_aponta_o_produto_e_nao_o_pack(
        self, ambiente
    ):
        avisos = self._aviso_do_total(
            ["CNC", "CLT", "Total"], _dados_meta(CNC=10000.0)  # sem CLT
        )

        assert len(avisos) == 1
        assert _rotulos_citados(avisos[0]) == {"CLT"}
        assert "pack" not in avisos[0]

    def test_total_com_pack_parcial_aponta_o_pack_selecionado(self, ambiente):
        avisos = self._aviso_do_total(
            ["CNC", "FGTS", "Total"],
            _dados_meta(CNC=10000.0, FGTS_ANT_BENEF_13=6000.0),
        )

        assert len(avisos) == 1
        assert _rotulos_citados(avisos[0]) == {"FGTS"}

    def test_com_todas_as_metas_o_total_nao_e_ignorado(self, ambiente):
        """Controle: o aviso nasce da meta que falta, nao do criterio."""
        avisos = self._aviso_do_total(
            ["CNC", "CLT", "Total"], _dados_meta(CNC=10000.0, CLT=8000.0)
        )

        assert avisos == []

    def test_acelerador_em_prod_dia_tem_motivo_de_acelerador(self, ambiente):
        """O alvo do acelerador e em contratos: em R$/dia ele segue valendo.

        Sem meta de acelerador gravada, o aviso aponta a falta da meta
        — nao uma suposta regra da aba que a 'desligaria' nesta metrica.
        """
        df, vinculos = _dados_criterios()
        at = _app(df, vinculos, metas=_dados_meta(CNC=10000.0))
        at.selectbox(key="gestao_metrica").set_value(_PROD_DIA).run()
        at.multiselect(key="gestao_produtos").set_value(["Emissao"]).run()
        at.selectbox(key="gestao_base_Emissao").set_value(
            _rotulo(_BASES, BASE_META)
        ).run()

        assert not at.exception
        (aviso,) = [
            w.value for w in at.warning
            if _rotulos_citados(w.value) == {"Emissao"}
        ]
        assert "desliga" not in aviso

    def test_produto_na_meta_com_prod_dia_para_no_erro_de_unidade(
        self, ambiente, monkeypatch
    ):
        """O motivo 'meta mensal x numero por dia' e inalcancavel pela aba.

        Produto na base '% da meta' com a metrica por dia e barrado antes
        pelo erro de unidade; o aviso de criterio ignorado nem e montado.
        """
        motivos = []
        motivo_real = tab._motivo_meta_indisponivel

        def espiao(*args, **kwargs):
            motivos.append(args)
            return motivo_real(*args, **kwargs)

        monkeypatch.setattr(tab, "_motivo_meta_indisponivel", espiao)
        df, vinculos = _dados_criterios()
        at = _app(df, vinculos, metas=_dados_meta(CNC=10000.0, CLT=8000.0))
        at.selectbox(key="gestao_base_CLT").set_value(
            _rotulo(_BASES, BASE_META)
        ).run()
        assert len(at.error) == 0  # controle: em valor a meta do CLT vale

        at.selectbox(key="gestao_metrica").set_value(_PROD_DIA).run()

        assert not at.exception
        (erro,) = [e.value for e in at.error]
        assert _rotulos_citados(erro) == {"CLT"}
        assert motivos == []


@pytest.mark.unit
class TestLegendaDeProducaoSemVinculo:
    """Em prod_dia agregado a aba conta quem ficou fora da razao.

    A legenda le ``tabela.attrs["sem_vinculo"]``: quantas pessoas com
    producao paga nao tem vinculo no ledger e quanto, no MIX inteiro,
    elas produziram. E a unica caption desta sub-visao que abre com a
    contagem em negrito — e por ai que os testes a reconhecem.
    """

    VALOR_FORA = 9500.0  # SEM VINCULO: CNC 9.000 + CLT 500

    def _prod_dia(self, nivel, vinculos, produtos=None):
        df, _ = _dados_criterios()
        at = _app(df, vinculos)
        at.selectbox(key="gestao_nivel").set_value(
            _rotulo(_NIVEIS, nivel)
        ).run()
        at.selectbox(key="gestao_metrica").set_value(_PROD_DIA).run()
        if produtos:
            at.multiselect(key="gestao_produtos").set_value(produtos).run()
        assert not at.exception
        return at

    @staticmethod
    def _legendas(at):
        return [
            c.value for c in at.caption if re.match(r"\*\*\d+\*\*", c.value)
        ]

    def test_nivel_loja_mostra_a_contagem_e_o_valor(self, ambiente):
        _, vinculos = _dados_criterios()

        at = self._prod_dia(NIVEL_LOJA, vinculos)

        (legenda,) = self._legendas(at)
        assert re.match(r"\*\*1\*\*", legenda)  # uma pessoa
        assert formatar_moeda(self.VALOR_FORA) in legenda

    def test_valor_da_legenda_e_o_mix_inteiro_nao_o_do_criterio(
        self, ambiente
    ):
        """O texto diz 'MIX inteiro': com so o CNC selecionado, o valor
        continua incluindo os R$ 500 de CLT."""
        _, vinculos = _dados_criterios()

        at = self._prod_dia(NIVEL_LOJA, vinculos, produtos=["CNC"])

        (legenda,) = self._legendas(at)
        assert formatar_moeda(self.VALOR_FORA) in legenda
        assert formatar_moeda(9000.0) not in legenda

    def test_chave_zerada_nao_gera_legenda(self, ambiente):
        """A chave existe com pessoas=0 e a legenda fica de fora."""
        df, ledger_completo = _dados_criterios(com_produtor_sem_vinculo=False)
        publicado = construir_tabela(
            df, None, nivel=NIVEL_LOJA, metrica=METRICA_PROD_DIA,
            df_vinculos=ledger_completo,
        ).attrs["sem_vinculo"]
        assert publicado == {"pessoas": 0, "valor": 0.0}
        # Controle: o mesmo caminho, com uma pessoa fora, mostra a legenda
        # — assim "nenhuma" abaixo nao e o reconhecimento falhando.
        _, com_lacuna = _dados_criterios()
        assert len(self._legendas(self._prod_dia(NIVEL_LOJA, com_lacuna))) == 1

        at = self._prod_dia(NIVEL_LOJA, ledger_completo)

        assert self._legendas(at) == []

    @pytest.mark.parametrize(
        "nivel, esperadas",
        [
            (NIVEL_LOJA, 1),
            (NIVEL_SUPERVISOR, 1),
            (NIVEL_REGIAO, 1),
            # No consultor a linha da pessoa ja sai ausente na tabela.
            (NIVEL_CONSULTOR, 0),
        ],
    )
    def test_legenda_so_aparece_acima_do_consultor(
        self, ambiente, nivel, esperadas
    ):
        _, vinculos = _dados_criterios()

        at = self._prod_dia(nivel, vinculos)

        assert len(self._legendas(at)) == esperadas


def test_tendencia_preserva_mes_com_vinculo_e_sem_pagamentos(monkeypatch):
    """Escopo sem pagamento com a base global presente: R$ 0/dia.

    ``pago.iloc[:0]`` e DataFrame VAZIO, nao ``None``: a competencia
    existe e so nao tem producao no recorte — continua na serie, nunca
    vira lacuna (``TestTendenciaComCompetenciaIndisponivel``).
    """
    from unittest.mock import MagicMock
    from src.dashboard.tabs import gestao_consultores as tab
    from src.dashboard.kpis.produtividade import produtividade_por_consultor

    interface = MagicMock()
    interface.radio.return_value = next(iter(tab._JANELAS_TENDENCIA))
    interface.multiselect.return_value = []
    vin = pd.DataFrame({
        "CONSULTOR": ["ANA"], "LOJA": ["A"], "REGIAO": ["R1"],
        "REGIAO_ATUAL": ["R1"], "DIAS_ELEGIVEIS": [10],
    })
    pago = pd.DataFrame({
        "CONSULTOR": ["ANA"], "LOJA": ["A"], "REGIAO": ["R1"],
        "VALOR": [1000.0],
    })
    grafico = MagicMock()
    monkeypatch.setattr(tab, "st", interface)
    monkeypatch.setattr(tab, "_competencias_fechadas", lambda *args: [(7, 2026), (8, 2026)])
    monkeypatch.setattr(tab, "criar_grafico_produtividade", grafico)
    monkeypatch.setattr(tab, "chart_card_open", lambda *args, **kwargs: None)
    monkeypatch.setattr(tab, "chart_card_close", lambda: None)
    tab._render_tendencia(
        produtividade_por_consultor(pago, vin), 8, 2026,
        lambda mes, ano: (pago if mes == 7 else pago.iloc[:0], vin, None),
    )
    carteira = grafico.call_args.args[0].set_index("Competencia")
    assert carteira.loc["2026-07", COL_PROD_DIA] == pytest.approx(100.0)
    assert carteira.loc["2026-08", COL_PROD_DIA] == 0.0


# ── Serie de tendencia: competencia INDISPONIVEL ──────

# Seis competencias fechadas fixas (a janela real depende de "hoje").
_JANELA = [(4, 2026), (5, 2026), (6, 2026), (7, 2026), (8, 2026), (9, 2026)]
_JANELA_ISO = [f"{a:04d}-{m:02d}" for m, a in _JANELA]
_PAGO = pd.DataFrame({
    "CONSULTOR": ["ANA", "BRUNO"], "LOJA": ["A", "A"],
    "REGIAO": ["R1", "R1"], "VALOR": [1000.0, 3000.0],
})
_VIN = pd.DataFrame({
    "CONSULTOR": ["ANA", "BRUNO"], "LOJA": ["A", "A"],
    "REGIAO": ["R1", "R1"], "REGIAO_ATUAL": ["R1", "R1"],
    "DIAS_ELEGIVEIS": [20, 20],
})
# O que o loader de competencia devolve em cada situacao.
_INDISPONIVEL = (None, None, pd.DataFrame({"SUPERVISOR": ["CHEFE"]}))
_SEM_COLABORADOR = (_PAGO.iloc[:0], _VIN.iloc[:0], None)


def _renderizar_tendencia(monkeypatch, retornos=None):
    """Roda ``_render_tendencia`` com um ``st`` falso; devolve o desenhado.

    ``retornos``: ``{(mes, ano): (df, df_vinculos, df_sup)}`` do loader
    de competencia; mes fora do mapa devolve o escopo normal (ANA e
    BRUNO com pagamento e vinculo). O grafico e o REAL, so espiado: o que
    importa e o que ele desenha com o que a aba lhe passa.
    """
    retornos = retornos or {}
    interface = MagicMock()
    interface.radio.return_value = next(iter(tab._JANELAS_TENDENCIA))
    interface.multiselect.return_value = []
    desenhado = SimpleNamespace(st=interface, subtitulos=[], graficos=[])
    grafico_real = tab.criar_grafico_produtividade

    def grafico(carteira, detalhe=None, competencias=None):
        desenhado.graficos.append(SimpleNamespace(
            carteira=carteira.copy(), competencias=competencias
        ))
        return grafico_real(carteira, detalhe, competencias=competencias)

    monkeypatch.setattr(tab, "st", interface)
    monkeypatch.setattr(tab, "_competencias_fechadas", lambda *args: _JANELA)
    monkeypatch.setattr(tab, "criar_grafico_produtividade", grafico)
    monkeypatch.setattr(
        tab, "chart_card_open",
        lambda titulo, **kw: desenhado.subtitulos.append(kw.get("subtitle")),
    )
    monkeypatch.setattr(tab, "chart_card_close", lambda: None)
    tab._render_tendencia(
        produtividade_por_consultor(_PAGO, _VIN), 9, 2026,
        lambda mes, ano: retornos.get((mes, ano), (_PAGO, _VIN, None)),
    )
    return desenhado


def _meses_avisados(desenhado):
    """Competencias MM/AAAA do unico aviso, na ordem em que aparecem."""
    return re.findall(r"\d{2}/\d{4}", desenhado.st.warning.call_args.args[0])


def _contagens_do_subtitulo(subtitulo):
    """Os numeros do subtitulo do card (zero quando a parte nao existe)."""
    def numero(padrao):
        achado = re.search(padrao, subtitulo)
        return int(achado.group(1)) if achado else 0

    return {
        "na_serie": numero(r"^(\d+) de \d+"),
        "janela": numero(r"^\d+ de (\d+)"),
        "indisponiveis": numero(r"(\d+) indisponivel"),
        "sem_colaborador": numero(r"(\d+) sem colaborador"),
    }


@pytest.mark.unit
class TestTendenciaComCompetenciaIndisponivel:
    """Competencia sem base consolidada e LACUNA na serie, nunca R$ 0/dia.

    O loader devolve ``(None, None, sup)`` quando a base consolidada
    GLOBAL do mes esta vazia (antes do RLS). A aba deixa o mes fora da
    serie, avisa UMA vez e o grafico mostra o buraco. Escopo vazio com
    a base presente e outra coisa: DataFrames vazios, sem aviso.
    """

    def test_um_unico_aviso_com_os_meses_em_ordem_cronologica(
        self, monkeypatch
    ):
        # Chaves fora de ordem de proposito: a ordem vem da janela.
        desenhado = _renderizar_tendencia(
            monkeypatch, {(7, 2026): _INDISPONIVEL, (5, 2026): _INDISPONIVEL}
        )

        assert desenhado.st.warning.call_count == 1
        assert _meses_avisados(desenhado) == ["05/2026", "07/2026"]

    def test_subtitulo_conta_cada_mes_da_janela_uma_unica_vez(
        self, monkeypatch
    ):
        desenhado = _renderizar_tendencia(monkeypatch, {
            (5, 2026): _INDISPONIVEL,
            (7, 2026): _INDISPONIVEL,
            (6, 2026): _SEM_COLABORADOR,
        })

        contagens = _contagens_do_subtitulo(desenhado.subtitulos[-1])
        assert contagens == {
            "na_serie": 3, "janela": 6,
            "indisponiveis": 2, "sem_colaborador": 1,
        }
        # Nenhum mes pulado fica sem explicacao.
        assert (
            contagens["na_serie"] + contagens["indisponiveis"]
            + contagens["sem_colaborador"]
        ) == contagens["janela"]

    def test_serie_sem_lacuna_nao_cita_indisponivel_nem_escopo_vazio(
        self, monkeypatch
    ):
        desenhado = _renderizar_tendencia(monkeypatch)

        assert desenhado.st.warning.call_count == 0
        assert _contagens_do_subtitulo(desenhado.subtitulos[-1]) == {
            "na_serie": 6, "janela": 6,
            "indisponiveis": 0, "sem_colaborador": 0,
        }

    def test_grafico_recebe_a_janela_inteira_e_desenha_o_buraco(
        self, monkeypatch
    ):
        desenhado = _renderizar_tendencia(monkeypatch, {
            (5, 2026): _INDISPONIVEL,
            (7, 2026): _INDISPONIVEL,
            (6, 2026): _SEM_COLABORADOR,
        })

        (chamada,) = desenhado.graficos
        assert chamada.competencias == _JANELA_ISO
        # A carteira so tem os meses que existem...
        assert list(chamada.carteira["Competencia"]) == [
            "2026-04", "2026-08", "2026-09",
        ]
        # ...e o grafico completa a grade: NaN nos tres meses sem dado.
        (carteira,) = desenhado.st.plotly_chart.call_args.args[0].data
        assert list(carteira.x) == _JANELA_ISO
        assert [x for x, y in zip(carteira.x, carteira.y) if pd.isna(y)] == [
            "2026-05", "2026-06", "2026-07",
        ]

    def test_mes_anterior_ao_ultimo_indisponivel_deixa_a_variacao_vazia(
        self, monkeypatch
    ):
        """Sem o mes calendario anterior nao ha comparacao — e a aba diz
        que a variacao exige competencias consecutivas."""
        desenhado = _renderizar_tendencia(
            monkeypatch, {(8, 2026): _INDISPONIVEL}
        )

        legendas = [c.args[0] for c in desenhado.st.caption.call_args_list]
        assert any("consecutiv" in legenda for legenda in legendas)

    def test_lacuna_longe_do_fim_nao_atrapalha_a_variacao(self, monkeypatch):
        """Controle: com o mes anterior ao ultimo presente, a variacao e
        calculada e nao ha aviso de competencias consecutivas."""
        desenhado = _renderizar_tendencia(
            monkeypatch, {(7, 2026): _INDISPONIVEL}
        )

        legendas = [c.args[0] for c in desenhado.st.caption.call_args_list]
        assert len(legendas) == 1
        assert "consecutiv" not in legendas[0]

    def test_todos_indisponiveis_mantem_o_aviso_e_nao_desenha_grafico(
        self, monkeypatch
    ):
        desenhado = _renderizar_tendencia(
            monkeypatch, {mes_ano: _INDISPONIVEL for mes_ano in _JANELA}
        )

        assert desenhado.st.warning.call_count == 1
        assert _meses_avisados(desenhado) == [
            f"{m:02d}/{a}" for m, a in _JANELA
        ]
        assert desenhado.st.info.call_count == 1  # "sem dados na janela"
        assert desenhado.st.plotly_chart.call_count == 0
        assert desenhado.subtitulos == []

    @pytest.mark.parametrize(
        "retorno",
        [
            pytest.param((_PAGO, None, None), id="sem_vinculos"),
            pytest.param((None, _VIN, None), id="sem_pagamentos"),
        ],
    )
    def test_um_dos_frames_ausente_ja_e_competencia_indisponivel(
        self, monkeypatch, retorno
    ):
        desenhado = _renderizar_tendencia(monkeypatch, {(6, 2026): retorno})

        assert _meses_avisados(desenhado) == ["06/2026"]
        contagens = _contagens_do_subtitulo(desenhado.subtitulos[-1])
        assert contagens["indisponiveis"] == 1

    def test_escopo_vazio_com_base_presente_nao_e_indisponivel(
        self, monkeypatch
    ):
        desenhado = _renderizar_tendencia(
            monkeypatch, {(6, 2026): _SEM_COLABORADOR}
        )

        assert desenhado.st.warning.call_count == 0
        contagens = _contagens_do_subtitulo(desenhado.subtitulos[-1])
        assert (contagens["indisponiveis"], contagens["sem_colaborador"]) == (
            0, 1,
        )


def test_grafico_produtividade_explicita_lacunas_entre_meses():
    from src.dashboard.ui.charts import criar_grafico_produtividade

    carteira = pd.DataFrame({
        "Competencia": ["2026-07", "2026-09"],
        COL_PROD_DIA: [100.0, 200.0],
    })
    consultores = carteira.assign(Consultor="ANA")
    fig = criar_grafico_produtividade(carteira, consultores)
    for trace in fig.data:
        assert list(trace.x) == ["2026-07", "2026-08", "2026-09"]
        assert pd.isna(trace.y[1])
        assert trace.connectgaps is False


def _executar_callback_real_gestao(
    mes=10, ano=2026, referencia=None, **sobrescritas
):
    """Executa o callback de app.py sem iniciar autenticacao/Streamlit."""
    import ast
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    arvore = ast.parse((Path(__file__).parents[1] / "app.py").read_text())
    callback = next(
        no for no in ast.walk(arvore)
        if isinstance(no, ast.FunctionDef) and no.name == "_render_gestao"
    )
    modulo = ast.Module(body=[callback], type_ignores=[])
    ast.fix_missing_locations(modulo)

    class DataFixa(date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 28)

    cadastro = pd.DataFrame({
        "CONSULTOR": ["ANA", "NEGADO"], "LOJA": ["A", "B"],
        "REGIAO": ["R1", "R2"], "REGIAO_ATUAL": ["R1", "R2"],
        "DIAS_ELEGIVEIS": [20, 20],
    })
    eventos = []

    def rls(df):
        eventos.append("rls")
        out = df[df["REGIAO"] == "R1"].copy()
        out.attrs["autorizado"] = True
        return out

    def ui(df):
        assert df.attrs.get("autorizado"), "UI nao pode anteceder RLS"
        eventos.append("ui")
        return df[df["LOJA"] == "A"].copy()

    def rls_metas(metas, contexto):
        eventos.append("rls_metas")
        assert set(contexto["LOJA"]) <= {"A"}
        return metas[metas["REGIAO"] == "R1"].copy()

    def ui_metas(metas, contexto):
        eventos.append("ui_metas")
        assert set(metas["LOJA"]) <= {"A"}
        return metas[metas["LOJA"].isin(contexto["LOJA"])].copy()

    def vinculos(m, a, ate=None):
        out = cadastro.copy()
        if ate is not None:
            out["DIAS_ELEGIVEIS"] = 10
        return out

    # `df` (consolidado pos-RLS do mes) e `dados_prestamista` sao nomes
    # livres de _render_gestao; o `ui` falso exige frame autorizado.
    df_autorizado = cadastro.iloc[:0].copy()
    df_autorizado.attrs["autorizado"] = True
    render = MagicMock()
    ledger = MagicMock(side_effect=vinculos)
    consolidar = MagicMock(return_value=(pd.DataFrame(), None, None))
    ambiente = {
        "pd": pd, "date": DataFixa, "mes": mes, "ano": ano,
        "data_ref_apuracao": referencia,
        "df_f": cadastro.iloc[:0], "df_sup_f": pd.DataFrame(),
        "df": df_autorizado, "dados_prestamista": {},
        "carregar_consultores_ativos": lambda: cadastro.copy(),
        "carregar_vinculos_consultores": ledger,
        "carregar_metas_produto_consultor": lambda m, a: pd.DataFrame({
            "LOJA": ["A", "B"], "CNC": [10000.0, 20000.0],
        }),
        "carregar_universo_lojas": lambda m, a: cadastro.copy(),
        "aplicar_rls": rls, "aplicar_filtros_ui": ui,
        "aplicar_rls_metas": rls_metas, "filtrar_metas_ui": ui_metas,
        "render_tab_gestao": render, "consolidar_dados": consolidar,
    }
    ambiente.update(sobrescritas)
    exec(compile(modulo, "app.py", "exec"), ambiente)
    ambiente["_render_gestao"]()
    return SimpleNamespace(
        render=render, ledger=ledger, consolidar=consolidar,
        cadastro=cadastro, eventos=eventos,
    )


def test_callback_gestao_mes_corrente_entrega_ledger_integral_e_cortado():
    executado = _executar_callback_real_gestao(referencia=date(2026, 10, 20))
    chamadas = executado.ledger.call_args_list
    assert chamadas[0].args == (10, 2026)
    assert chamadas[1].args == (10, 2026, date(2026, 10, 20))
    argumentos = executado.render.call_args.kwargs
    assert argumentos["periodo_aberto"] is True
    assert argumentos["df_vinculos"]["DIAS_ELEGIVEIS"].tolist() == [10]
    assert argumentos["df_vinculos_mes"]["DIAS_ELEGIVEIS"].tolist() == [20]


def test_callback_gestao_mes_fechado_nao_corta_na_ultima_venda():
    executado = _executar_callback_real_gestao(9, referencia=date(2026, 9, 5))
    assert [c.args for c in executado.ledger.call_args_list] == [(9, 2026)]
    argumentos = executado.render.call_args.kwargs
    assert argumentos["periodo_aberto"] is False
    assert argumentos["df_vinculos"]["DIAS_ELEGIVEIS"].tolist() == [20]


@pytest.mark.parametrize("referencia", [None, date(2026, 10, 31)])
def test_callback_gestao_corrente_nao_avanca_alem_de_hoje(referencia):
    executado = _executar_callback_real_gestao(referencia=referencia)
    assert executado.ledger.call_args_list[1].args[-1] == date(2026, 10, 28)


def test_callback_gestao_preserva_meta_de_loja_sem_vendas_apos_rls():
    executado = _executar_callback_real_gestao()
    metas = executado.render.call_args.args[3]
    assert metas["LOJA"].tolist() == ["A"]
    assert metas["CNC"].tolist() == [10000.0]
    assert executado.eventos.index("rls_metas") < executado.eventos.index("ui_metas")


def test_callback_contexto_das_metas_inclui_vinculos_do_mes():
    """Vinculo do mes fora do universo e sem pagamento (ex.: admissao
    futura) precisa estar no contexto que autoriza as metas da loja."""
    lojas_do_contexto = []

    def vinculos(m, a, ate=None):
        return pd.DataFrame({
            "CONSULTOR": ["NOVO"], "LOJA": ["C"], "REGIAO": ["R1"],
            "REGIAO_ATUAL": ["R1"], "DIAS_ELEGIVEIS": [0],
        })

    def rls_metas(metas, contexto):
        lojas_do_contexto.extend(contexto["LOJA"])
        return metas.iloc[:0]

    _executar_callback_real_gestao(
        carregar_vinculos_consultores=vinculos,
        aplicar_rls_metas=rls_metas,
        filtrar_metas_ui=lambda metas, contexto: metas,
        aplicar_filtros_ui=lambda df: df,
    )
    assert "C" in lojas_do_contexto


def test_callback_historico_global_vazio_e_lacuna_sem_carregar_ledger():
    executado = _executar_callback_real_gestao()
    callback = executado.render.call_args.kwargs["carregar_competencia"]
    antes = executado.ledger.call_count
    assert callback(7, 2026) == (None, None, None)
    assert executado.ledger.call_count == antes


def test_callback_historico_escopo_vazio_preserva_ledger_autorizado():
    executado = _executar_callback_real_gestao()
    executado.consolidar.return_value = (
        executado.cadastro[executado.cadastro["LOJA"] == "B"], None, None
    )
    callback = executado.render.call_args.kwargs["carregar_competencia"]
    pagos, vinculos, _ = callback(7, 2026)
    assert pagos.empty
    assert vinculos["CONSULTOR"].tolist() == ["ANA"]


def _app_performance_metas(caso):
    from datetime import date
    import pandas as pd
    from src.dashboard.tabs.gestao_consultores import _render_performance

    hoje = date.today()
    pago = pd.DataFrame({
        "CONSULTOR": ["ANA"], "LOJA": ["A"], "REGIAO": ["R1"],
        "categoria_codigo": ["CNC"], "VALOR": [1000.0], "pontos": [1000.0],
    })
    vin = pd.DataFrame({
        "CONSULTOR": ["ANA"], "LOJA": ["A"], "REGIAO": ["R1"],
        "REGIAO_ATUAL": ["R1"], "DIAS_ELEGIVEIS": [5],
        "DU_COMPETENCIA": [20], "DU_DECORRIDOS": [5],
    })
    # Espelha o loader real (pivot com fill_value=0): todas as colunas de
    # produto presentes; coluna ausente vira SEM META (motivo c).
    metas = pd.DataFrame({
        "LOJA": ["A"], "CNC": [10000.0], "CLT": [0.0], "SAQUE": [0.0],
        "CONSIGNADO": [0.0], "FGTS_ANT_BENEF_13": [0.0],
    })
    if caso == "sem_producao":
        pago = pago.iloc[:0]
    if caso == "sem_meta":
        metas = metas.iloc[:0]
    if caso == "sem_dias":
        vin = vin.iloc[:0]
    _render_performance(
        pago, None, vin, hoje.month, hoje.year + (caso == "futuro"),
        df_metas=metas, df_vinculos_mes=vin.assign(DIAS_ELEGIVEIS=20),
        periodo_aberto=caso != "futuro",
    )


@pytest.mark.parametrize("caso", ["sem_producao", "sem_meta", "sem_dias", "futuro"])
def test_performance_nova_ui_explicita_ausencias_sem_falhar(caso):
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_function(_app_performance_metas, args=(caso,)).run(timeout=15)
    assert not app.exception
    if caso == "sem_dias":
        assert any("Ledger" in aviso.value for aviso in app.warning)
        assert len(app.dataframe) == 0
    elif caso == "futuro":
        assert any("futura" in aviso.value for aviso in app.info)
        assert len(app.dataframe) == 0
    else:
        principal = app.dataframe[0].value
        assert principal.iloc[0]["Consultor"] == "ANA"
        if caso == "sem_meta":
            assert principal.iloc[0]["Situacao MIX"] == "SEM META"
            assert pd.isna(principal.iloc[0]["Atingimento MIX %"])
        else:
            assert principal.iloc[0]["Situacao MIX"] == "PENDENTE"
            assert principal.iloc[0]["Falta MIX"] == 10000.0
            assert principal.iloc[0]["Ritmo necessario R$/dia"] == pytest.approx(10000.0 / 15)


def test_callback_gestao_futuro_nao_e_periodo_em_curso():
    executado = _executar_callback_real_gestao(11)
    assert executado.render.call_args.kwargs["periodo_aberto"] is False
    assert [c.args for c in executado.ledger.call_args_list] == [(11, 2026)]

def _app_vinculo_futuro(cenario):
    """Performance com periodo aberto: ANA/CAIO elegiveis, BIA com vinculo futuro.

    Cenario "A": pivot completo na loja A; loja B fora do pivot.
    Cenario "B": pivot sem a coluna FGTS_ANT_BENEF_13 (coluna ausente).
    O espiao em st.download_button guarda o CSV exportado no session_state.
    """
    from datetime import date
    from unittest.mock import patch

    import pandas as pd
    import streamlit as st

    from src.dashboard.tabs.gestao_consultores import _render_performance

    hoje = date.today()
    pago = pd.DataFrame({
        "CONSULTOR": ["ANA", "CAIO"], "LOJA": ["A", "B"],
        "REGIAO": ["R1", "R1"], "categoria_codigo": ["CNC", "CNC"],
        "VALOR": [1000.0, 500.0], "pontos": [1000.0, 500.0],
    })
    vin = pd.DataFrame({
        "CONSULTOR": ["ANA", "BIA", "CAIO"], "LOJA": ["A", "A", "B"],
        "REGIAO": ["R1", "R1", "R1"], "REGIAO_ATUAL": ["R1", "R1", "R1"],
        "DIAS_ELEGIVEIS": [5, 0, 5],
        "DU_COMPETENCIA": [20, 20, 20], "DU_DECORRIDOS": [5, 5, 5],
    })
    vin_mes = vin.assign(DIAS_ELEGIVEIS=[20, 15, 20])
    metas = pd.DataFrame({
        "LOJA": ["A"], "CNC": [10000.0], "CLT": [0.0], "SAQUE": [0.0],
        "CONSIGNADO": [0.0], "FGTS_ANT_BENEF_13": [0.0],
    })
    if cenario == "B":
        metas = metas.drop(columns="FGTS_ANT_BENEF_13")

    original = st.download_button

    def _espiao(*args, **kwargs):
        st.session_state["_csv"] = kwargs["data"]
        return original(*args, **kwargs)

    with patch.object(st, "download_button", side_effect=_espiao):
        _render_performance(
            pago, None, vin, hoje.month, hoje.year,
            df_metas=metas, df_vinculos_mes=vin_mes, periodo_aberto=True,
        )


def _expander_por_prefixo(app, prefixo):
    achados = [e for e in app.expander if e.label.startswith(prefixo)]
    return achados[0] if achados else None


def _rodar_vinculo_futuro(cenario):
    app = AppTest.from_function(_app_vinculo_futuro, args=(cenario,)).run(timeout=30)
    assert not app.exception
    return app


@pytest.mark.unit
class TestVinculoFuturoNaPerformance:
    """Etapa 2: VINCULO FUTURO fora da base e do CSV, com bloco proprio."""

    def test_bloco_mostra_meta_dias_restantes_e_ritmo(self):
        bloco = _expander_por_prefixo(_rodar_vinculo_futuro("A"), "Vinculo futuro")
        assert bloco is not None
        tab_vf = bloco.dataframe[0].value
        assert tab_vf["Consultor"].tolist() == ["BIA"]
        linha = tab_vf.iloc[0]
        assert linha["Situacao MIX"] == "VINCULO FUTURO"
        assert linha["Meta MIX"] == 10000.0
        assert linha["Falta MIX"] == 10000.0
        assert linha["Dias restantes"] == 15
        assert linha["Ritmo necessario R$/dia"] == pytest.approx(10000.0 / 15)
        assert linha["Motivo sem meta"] == ""

    def test_bloco_nao_traz_colunas_de_produtividade(self):
        tab_vf = _expander_por_prefixo(
            _rodar_vinculo_futuro("A"), "Vinculo futuro"
        ).dataframe[0].value
        for coluna in (
            "Dias elegiveis", "R$/dia elegivel", "% da loja", "% da regiao",
            "vs. media da carteira", "Na loja", "Producao paga",
        ):
            assert coluna not in tab_vf.columns

    def test_fora_da_tabela_principal_e_da_base_dos_cards(self):
        app = _rodar_vinculo_futuro("A")
        principal = app.dataframe[0].value
        assert "BIA" not in principal["Consultor"].tolist()
        assert "Motivo sem meta" not in principal.columns
        card = [m for m in app.metric if m.label == "Time com MIX atingido"][0]
        # Y = elegiveis (ANA, CAIO); BIA nao entra.
        assert card.proto.delta.endswith("de 2 elegiveis")

    def test_legenda_de_contagem_presente(self):
        app = _rodar_vinculo_futuro("A")
        assert any(
            c.value.startswith("1 pessoa(s) com vinculo futuro")
            for c in app.caption
        )

    def test_motivo_so_no_expander_de_pendencias(self):
        app = _rodar_vinculo_futuro("A")
        pend = _expander_por_prefixo(
            app, "Produtos pendentes e origem da meta"
        ).dataframe[0].value
        assert "Motivo sem meta" in pend.columns
        motivos = dict(zip(pend["Consultor"], pend["Motivo sem meta"]))
        assert motivos["CAIO"] == "Loja sem meta individual no mes"
        comp = _expander_por_prefixo(
            app, "Comparacoes de produtividade no escopo"
        ).dataframe[0].value
        assert "Motivo sem meta" not in comp.columns

    def test_csv_tem_motivo_e_nao_exporta_vinculo_futuro(self):
        csv = _rodar_vinculo_futuro("A").session_state["_csv"]
        assert "Motivo sem meta" in csv.splitlines()[0]
        assert "BIA" not in csv
        assert "ANA" in csv

    def test_bloco_permanece_com_corte_em_zero(self):
        app = _rodar_vinculo_futuro("A")
        app.slider(key="perf_corte").set_value(0).run(timeout=30)
        assert not app.exception
        assert any("Nenhum colaborador dentro do corte" in i.value for i in app.info)
        bloco = _expander_por_prefixo(app, "Vinculo futuro")
        assert bloco is not None
        assert bloco.dataframe[0].value["Consultor"].tolist() == ["BIA"]
        # Base dos cards inalterada pelo corte.
        card = [m for m in app.metric if m.label == "Time com MIX atingido"][0]
        assert card.proto.delta.endswith("de 2 elegiveis")
        assert _expander_por_prefixo(app, "Produtos pendentes") is None

    def test_coluna_de_produto_ausente_mostra_motivo_c(self):
        app = _rodar_vinculo_futuro("B")
        tab_vf = _expander_por_prefixo(app, "Vinculo futuro").dataframe[0].value
        assert pd.isna(tab_vf.iloc[0]["Meta MIX"])
        assert tab_vf.iloc[0]["Motivo sem meta"].startswith(
            "Meta nao cadastrada no mes:"
        )
        pend = _expander_por_prefixo(
            app, "Produtos pendentes e origem da meta"
        ).dataframe[0].value
        motivos = dict(zip(pend["Consultor"], pend["Motivo sem meta"]))
        assert motivos["ANA"].startswith("Meta nao cadastrada no mes:")
        # Precedencia a>b>c: loja fora do pivot fica no motivo (b).
        assert motivos["CAIO"] == "Loja sem meta individual no mes"
