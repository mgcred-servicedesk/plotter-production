"""
Regras da Reconquista e do acelerador (``kpis/reconquista.py``).

Testes de **caracterização**: fixam o comportamento que já rodava
dentro de `loaders.py` antes da Etapa 2 da revisão de 09/2026. Boa
parte destas ~300 linhas não era exercitada — o módulo saiu da extração
com 39% de cobertura, e o que faltava eram justamente as faixas de
prêmio, a base elegível e as quebras por loja/consultor.

O teste da apuração mensal (`_marcar_vigencia_reconquista`, `_fatiar_ref`)
já existia e continua em `tests/test_loaders.py`, importando pela
fachada — a etapa preserva as interfaces públicas.
"""
import pandas as pd
import pytest

from src.dashboard.kpis.reconquista import (
    _faixa_premio_conversao,
    _juntar_producao,
    _mask_elegivel,
    _mes_apuracao_anterior,
    _mes_apuracao_seguinte,
    _norm_texto,
    _por_consultor_reconquista,
    _por_loja_reconquista,
    _totais_reconquista,
)


def _clientes(**overrides):
    base = {
        "co_adesao": [1, 2, 3, 4],
        "status": [
            "EFETIVADA", "PROMESSA", "SEM RECONQUISTA", "EFETIVADA",
        ],
        "loja": ["L1", "L1", "L2", "L2"],
        "regiao": ["R1", "R1", "R2", "R2"],
        "consultor": ["A", "A", "B", "B"],
        "flag_elegibilidade": ["ELEGIVEL"] * 4,
        "saldo_contabil": [100.0, 200.0, 300.0, 400.0],
        "dias_atraso": [10, 20, 30, 40],
    }
    base.update(overrides)
    return pd.DataFrame(base)


@pytest.mark.unit
class TestFaixaPremioConversao:
    """Tabela de negócio: o % sobre a base ELEGÍVEL define o ajuste
    sobre o prêmio CNC (indicador, não calcula R$)."""

    @pytest.mark.parametrize("pct,ajuste", [
        (0.0, -20), (10.0, -20),          # 0 a 10 -> -20
        (10.1, -10), (20.0, -10),         # 10,1 a 20 -> -10
        (20.1, 0), (29.99, 0),            # 20,1 a 29,99 -> 0
        (30.0, 10), (39.99, 10),          # 30 a 39,99 -> +10
        (40.0, 20), (100.0, 20),          # >= 40 -> +20
    ])
    def test_limites_das_faixas(self, pct, ajuste):
        assert _faixa_premio_conversao(pct)["ajuste_pct"] == ajuste

    def test_limite_superior_e_inclusivo_nas_negativas(self):
        """Documentado na docstring da regra: 10 ainda é -20%, mas 30 já
        é +10%. A assimetria é intencional."""
        assert _faixa_premio_conversao(10.0)["ajuste_pct"] == -20
        assert _faixa_premio_conversao(10.01)["ajuste_pct"] == -10
        assert _faixa_premio_conversao(29.99)["ajuste_pct"] == 0
        assert _faixa_premio_conversao(30.0)["ajuste_pct"] == 10

    def test_rotulo_traz_sinal_e_neutro_por_extenso(self):
        assert _faixa_premio_conversao(0.0)["rotulo"] == (
            "-20% sobre prêmio CNC"
        )
        assert _faixa_premio_conversao(25.0)["rotulo"] == "0 (neutro)"
        assert _faixa_premio_conversao(50.0)["rotulo"] == (
            "+20% sobre prêmio CNC"
        )

    def test_devolve_as_tres_chaves_do_contrato(self):
        assert set(_faixa_premio_conversao(0.0)) == {
            "ajuste_pct", "rotulo", "cor",
        }


@pytest.mark.unit
class TestMaskElegivel:
    """A base elegível é o DENOMINADOR da conversão. Quem sai dela
    continua visível nos analíticos — só fora da conta."""

    @pytest.mark.parametrize("flag", [
        "NAO ELEGIVEL", "NÃO ELEGÍVEL", "nao elegivel", "  NÃO ELEGIVEL ",
    ])
    def test_nao_elegivel_sai_com_ou_sem_acento(self, flag):
        assert not _mask_elegivel(
            _clientes(flag_elegibilidade=[flag] * 4)
        ).any()

    @pytest.mark.parametrize("flag", ["ELEGIVEL", "", None, "INTERIM"])
    def test_resto_conta_como_elegivel(self, flag):
        """Decisão de negócio: vazio, nulo e interim contam."""
        assert _mask_elegivel(
            _clientes(flag_elegibilidade=[flag] * 4)
        ).all()

    def test_sem_a_coluna_todos_sao_elegiveis(self):
        df = _clientes().drop(columns=["flag_elegibilidade"])
        assert _mask_elegivel(df).all()

    def test_frame_vazio_ou_none(self):
        assert _mask_elegivel(pd.DataFrame()).empty
        assert _mask_elegivel(None).empty


@pytest.mark.unit
class TestTotaisReconquista:
    def test_conversao_e_efetivada_sobre_elegiveis(self):
        totais = _totais_reconquista(_clientes())
        assert totais["total"] == 4
        assert totais["efetivadas"] == 2
        assert totais["promessas"] == 1
        assert totais["sem_reconquista"] == 1
        assert totais["conversao"] == pytest.approx(50.0)

    def test_nao_elegivel_sai_do_denominador_mas_conta_no_geral(self):
        """O caso que a regra existe para resolver: 2 não elegíveis não
        podem puxar a conversão para baixo."""
        totais = _totais_reconquista(_clientes(flag_elegibilidade=[
            "ELEGIVEL", "ELEGIVEL", "NAO ELEGIVEL", "NAO ELEGIVEL",
        ]))
        assert totais["total"] == 2          # denominador
        assert totais["total_geral"] == 4    # contexto
        assert totais["nao_elegivel"] == 2
        assert totais["efetivadas"] == 1
        assert totais["conversao"] == pytest.approx(50.0)

    def test_todos_inelegiveis_nao_divide_por_zero(self):
        totais = _totais_reconquista(
            _clientes(flag_elegibilidade=["NAO ELEGIVEL"] * 4)
        )
        assert totais["total"] == 0
        assert totais["total_geral"] == 4
        assert totais["nao_elegivel"] == 4
        assert totais["conversao"] == 0.0

    @pytest.mark.parametrize("entrada", [
        None, pd.DataFrame(), pd.DataFrame({"outra": [1]}),
    ])
    def test_schema_estavel_mesmo_sem_dado(self, entrada):
        """A UI lê estas chaves sempre — a prévia usa os mesmos totais."""
        totais = _totais_reconquista(entrada)
        assert set(totais) == {
            "total", "total_geral", "nao_elegivel", "efetivadas",
            "promessas", "sem_reconquista", "conversao", "faixa",
            "cobranca_consignavel", "acelerador_no_escopo",
            "acelerador_perfil", "faixa_agregada",
        }

    def test_chaves_do_acelerador_nascem_neutras(self):
        """Estão aqui só para o schema ser estável; quem preenche de
        fato é `carregar_reconquista`, sob o gate de perfil."""
        totais = _totais_reconquista(_clientes())
        assert totais["cobranca_consignavel"] == 0
        assert totais["acelerador_no_escopo"] is False
        assert totais["acelerador_perfil"] is None
        assert totais["faixa_agregada"] is None


@pytest.mark.unit
class TestQuebrasPorLojaEConsultor:
    def test_por_loja_agrupa_estados_e_conversao(self):
        g = _por_loja_reconquista(_clientes()).set_index("loja")
        assert g.loc["L1", "total_clientes"] == 2
        assert g.loc["L1", "efetivadas"] == 1
        assert g.loc["L1", "conversao_pct"] == pytest.approx(50.0)
        assert g.loc["L2", "efetivadas"] == 1

    def test_por_loja_usa_so_elegiveis(self):
        g = _por_loja_reconquista(_clientes(flag_elegibilidade=[
            "ELEGIVEL", "NAO ELEGIVEL", "ELEGIVEL", "ELEGIVEL",
        ])).set_index("loja")
        assert g.loc["L1", "total_clientes"] == 1

    def test_por_loja_traz_medias_de_saldo_e_atraso(self):
        g = _por_loja_reconquista(_clientes()).set_index("loja")
        assert g.loc["L1", "saldo_medio"] == pytest.approx(150.0)
        assert g.loc["L1", "dias_atraso_medio"] == pytest.approx(15.0)

    def test_por_loja_ordena_por_efetivadas_desc(self):
        clientes = _clientes(status=[
            "PROMESSA", "PROMESSA", "EFETIVADA", "EFETIVADA",
        ])
        assert _por_loja_reconquista(clientes)["loja"].tolist()[0] == "L2"

    def test_por_loja_anexa_a_faixa_da_conversao(self):
        g = _por_loja_reconquista(_clientes()).set_index("loja")
        assert g.loc["L1", "faixa"] == "+20% sobre prêmio CNC"

    def test_por_consultor_espelha_a_quebra_por_loja(self):
        g = _por_consultor_reconquista(_clientes()).set_index("consultor")
        assert g.loc["A", "total_clientes"] == 2
        assert g.loc["A", "efetivadas"] == 1
        assert g.loc["A", "conversao_pct"] == pytest.approx(50.0)

    @pytest.mark.parametrize("func", [
        _por_loja_reconquista, _por_consultor_reconquista,
    ])
    @pytest.mark.parametrize("entrada", [None, pd.DataFrame()])
    def test_quebras_sem_dado_devolvem_frame_vazio(self, func, entrada):
        assert func(entrada).empty

    @pytest.mark.parametrize("func,coluna", [
        (_por_loja_reconquista, "loja"),
        (_por_consultor_reconquista, "consultor"),
    ])
    def test_sem_a_coluna_de_agrupamento_devolve_vazio(self, func, coluna):
        assert func(_clientes().drop(columns=[coluna])).empty

    @pytest.mark.parametrize("func", [
        _por_loja_reconquista, _por_consultor_reconquista,
    ])
    def test_todos_inelegiveis_devolve_vazio(self, func):
        assert func(
            _clientes(flag_elegibilidade=["NAO ELEGIVEL"] * 4)
        ).empty


@pytest.mark.unit
class TestApuracaoMensal:
    """Defasagem de 1 mês: a apuração de M exibe dt_fim de M-1."""

    def test_mes_anterior(self):
        assert _mes_apuracao_anterior(9, 2026) == (8, 2026)

    def test_mes_anterior_atravessa_o_ano(self):
        assert _mes_apuracao_anterior(1, 2026) == (12, 2025)

    def test_mes_seguinte(self):
        assert _mes_apuracao_seguinte(9, 2026) == (10, 2026)

    def test_mes_seguinte_atravessa_o_ano(self):
        assert _mes_apuracao_seguinte(12, 2026) == (1, 2027)


@pytest.mark.unit
class TestJuntarProducao:
    """Junta efetivadas/cobrança a um universo de nomes — o universo
    manda: quem não tem produção entra com 0, e nenhuma fonte pode
    acrescentar pessoa que não está no cadastro."""

    def _nomes(self, *n):
        return pd.DataFrame({"consultor": list(n)})

    def test_quem_nao_produziu_entra_com_zero(self):
        out = _juntar_producao(
            self._nomes("ANA", "BRUNO"),
            pd.DataFrame({"consultor": ["ANA"], "efetivadas": [3]}),
            pd.DataFrame(),
        ).set_index("consultor")
        assert out.loc["ANA", "efetivadas"] == 3
        assert out.loc["BRUNO", "efetivadas"] == 0
        assert out["cobranca_consignavel"].tolist() == [0, 0]

    def test_producao_de_quem_nao_esta_no_universo_e_descartada(self):
        out = _juntar_producao(
            self._nomes("ANA"),
            pd.DataFrame({
                "consultor": ["ANA", "FANTASMA"], "efetivadas": [1, 9],
            }),
            pd.DataFrame(),
        )
        assert out["consultor"].tolist() == ["ANA"]

    def test_merge_ignora_caixa_e_espacos_em_volta(self):
        out = _juntar_producao(
            self._nomes("JOÃO DA SILVA"),
            pd.DataFrame({
                "consultor": ["  joão da silva "], "efetivadas": [2],
            }),
            pd.DataFrame(),
        )
        assert out["efetivadas"].tolist() == [2]

    def test_acento_divergente_casa(self):
        """A regressão que fechou a lacuna de 09/2026.

        `JOÃO DA SILVA` no cadastro e `JOAO DA SILVA` na fonte de
        produção são a MESMA pessoa. Antes de `normalizar_nome`, o
        merge por `strip + upper` fazia duas chaves e a produção dela
        caía para zero em silêncio — ela não sumia da tabela (o que
        tornaria o erro visível), aparecia zerada."""
        out = _juntar_producao(
            self._nomes("JOÃO DA SILVA"),
            pd.DataFrame({
                "consultor": ["JOAO DA SILVA"], "efetivadas": [2],
            }),
            pd.DataFrame(),
        )
        assert out["efetivadas"].tolist() == [2]

    def test_acento_divergente_no_outro_sentido_tambem_casa(self):
        """Qual lado tem o acento não pode importar."""
        out = _juntar_producao(
            self._nomes("JOAO DA SILVA"),
            pd.DataFrame({
                "consultor": ["JOÃO DA SILVA"], "efetivadas": [2],
            }),
            pd.DataFrame(),
        )
        assert out["efetivadas"].tolist() == [2]

    def test_cedilha_e_til_tambem_dobram(self):
        out = _juntar_producao(
            self._nomes("CONCEIÇÃO"),
            pd.DataFrame({
                "consultor": ["conceicao"], "efetivadas": [5],
            }),
            pd.DataFrame(),
        )
        assert out["efetivadas"].tolist() == [5]

    def test_soma_linhas_repetidas_da_mesma_pessoa(self):
        out = _juntar_producao(
            self._nomes("ANA"),
            pd.DataFrame({
                "consultor": ["ANA", "ana"], "efetivadas": [1, 2],
            }),
            pd.DataFrame(),
        )
        assert out["efetivadas"].tolist() == [3]

    def test_nomes_duplicados_no_universo_viram_uma_linha(self):
        out = _juntar_producao(
            self._nomes("ANA", "ana"), pd.DataFrame(), pd.DataFrame(),
        )
        assert len(out) == 1

    def test_contagens_saem_inteiras(self):
        out = _juntar_producao(
            self._nomes("ANA"), pd.DataFrame(), pd.DataFrame(),
        )
        assert out["efetivadas"].dtype.kind == "i"
        assert out["cobranca_consignavel"].dtype.kind == "i"


@pytest.mark.unit
class TestNormTexto:
    """Alias de `shared/texto.py::normalizar_nome` — mantido porque é o
    nome que `loaders.py` importa. A cobertura da função em si está em
    `tests/test_shared_texto.py`; aqui ficam só os casos que importam
    para a Reconquista."""

    def test_normaliza_caixa_e_espacos_em_volta(self):
        assert _norm_texto(pd.Series(["  ana  "])).tolist() == ["ANA"]

    def test_remove_acento(self):
        """É chave de comparação de NOME — acento é ruído aqui, porque
        os dois lados vêm do banco, digitados em cadastros diferentes.
        Para rótulo de dado contra constante do código a regra é a
        oposta: `normalizar_rotulo` preserva (ver `shared/texto.py`)."""
        assert _norm_texto(pd.Series(["João"])).tolist() == ["JOAO"]

    def test_NAO_colapsa_espaco_interno(self):
        assert _norm_texto(pd.Series(["A  B"])).tolist() == ["A  B"]

    def test_nulo_nao_vira_texto(self):
        """Caracterização: `None` sai como NA, não como string vazia
        nem como o literal "NONE" — então nunca casa com nome nenhum
        no merge, que é o comportamento desejável aqui."""
        assert _norm_texto(pd.Series([None])).isna().all()
