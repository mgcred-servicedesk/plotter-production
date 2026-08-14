"""
Testes do valor consolidado (migration 067) e da Cobrança Consignável em
``src/dashboard/loaders.py``.

O critério de negócio ("é Cobrança Consignável?") **não é testado aqui**:
desde a 067 ele vive em ``fn_eh_cobranca_consignavel`` no Postgres e é
aplicado como filtro server-side. A suíte equivalente é o bloco de
validação da própria migration (``database/migrations/
067_valor_consolidado_cobranca_consignavel.sql``, seção 4) — rodar as
queries 1-3 de lá a cada alteração da função.

O que dá para cobrir em pytest é o contrato da camada de dados: de onde
`VALOR`/`VALOR_BASE` vêm, coerção de tipos, invariantes e o fato de o
filtro ser server-side. Como ``_sb()`` é lazy (só é chamado dentro do
lambda que ``_paginar_keyset`` executa), basta monkeypatchar
``carregar_periodo`` + ``_paginar_keyset`` — nenhuma conexão é aberta.
"""
import pandas as pd
import pytest

from src.dashboard import loaders


class _FakeQuery:
    """Query fluente que registra os filtros em vez de executá-los.

    Padrão novo nesta suíte (os demais testes monkeypatcham funções do
    módulo). Existe porque a garantia que mais importa na 067 — o
    critério ser aplicado pelo servidor, e não em pandas — só é
    observável na query montada.
    """

    def __init__(self, registro: dict):
        self._registro = registro

    def from_(self, tabela):
        self._registro["tabela"] = tabela
        return self

    def select(self, colunas):
        self._registro["colunas"] = colunas
        return self

    def eq(self, coluna, valor):
        self._registro.setdefault("eq", {})[coluna] = valor
        return self

    def gt(self, coluna, valor):  # usado pelo keyset a partir da 2a pagina
        self._registro.setdefault("gt", {})[coluna] = valor
        return self

    def order(self, coluna):
        self._registro["order"] = coluna
        return self

    def limit(self, n):
        self._registro["limit"] = n
        return self

    def execute(self):
        return self


@pytest.fixture
def periodo_stub(monkeypatch):
    """Período resolvido sem tocar o banco."""
    monkeypatch.setattr(
        loaders, "carregar_periodo", lambda m, a: {"id": "periodo-1"}
    )


def _linha_pagos(**overrides):
    """Linha crua de v_contratos_dashboard (nomes de coluna do banco)."""
    linha = {
        "contrato_id": 1,
        "num_proposta": "P1",
        "data_status_pagamento": "2026-08-10",
        "data_cadastro": "2026-08-01",
        "loja": "LOJA A",
        "regiao": "R1",
        "regiao_atual": "R1",
        "consultor": "FULANO",
        "produto": "TAB",
        "tipo_produto": "CONSIG",
        "subtipo": "NOVO",
        "tipo_operacao": "Contrato Novo",
        # A view garante valor_consolidado >= valor; aqui eles sao
        # DIFERENTES de proposito, para pegar um mapeamento que
        # apontasse as duas colunas do DF para `valor`.
        "valor_consolidado": 1200.0,
        "valor": 1000.0,
        "prazo": "96",
        "valor_parcela": 50.0,
        "banco": "BMG",
        "convenio": "INSS",
        "sub_status_banco": None,
        "categoria_codigo": "CONSIG_BMG",
        "grupo_dashboard": "CONSIG",
        "grupo_meta": "CONSIG",
        "conta_valor": True,
        "conta_pontuacao": True,
        "created_at": "2026-08-10T12:00:00Z",
    }
    linha.update(overrides)
    return linha


@pytest.mark.unit
class TestFetchContratosPagosValorConsolidado:
    """VALOR vem de valor_consolidado; VALOR_BASE, de valor."""

    def test_valor_vem_do_consolidado_e_base_do_valor(
        self, monkeypatch, periodo_stub
    ):
        monkeypatch.setattr(
            loaders, "_paginar_keyset", lambda q, c: [_linha_pagos()]
        )
        df = loaders._fetch_contratos_pagos(8, 2026)

        assert df.loc[0, "VALOR"] == 1200.0
        assert df.loc[0, "VALOR_BASE"] == 1000.0

    def test_select_pede_as_duas_colunas_de_valor(
        self, monkeypatch, periodo_stub
    ):
        registro = {}

        def _capturar(montar_query, coluna_chave):
            montar_query()
            return []

        monkeypatch.setattr(loaders, "_sb", lambda: _FakeQuery(registro))
        monkeypatch.setattr(loaders, "_paginar_keyset", _capturar)
        loaders._fetch_contratos_pagos(8, 2026)

        colunas = registro["colunas"].split(",")
        assert "valor_consolidado" in colunas
        assert "valor" in colunas

    def test_valores_invalidos_viram_zero(self, monkeypatch, periodo_stub):
        monkeypatch.setattr(
            loaders,
            "_paginar_keyset",
            lambda q, c: [
                _linha_pagos(valor_consolidado=None, valor="nao-numero")
            ],
        )
        df = loaders._fetch_contratos_pagos(8, 2026)

        assert df.loc[0, "VALOR"] == 0.0
        assert df.loc[0, "VALOR_BASE"] == 0.0

    def test_invariante_valor_nunca_menor_que_base(
        self, monkeypatch, periodo_stub
    ):
        """"Nunca reduzir" (GREATEST da 067), na camada de fetch.

        Vale AQUI, não no frame consolidado: `_executar_consolidacao`
        zera VALOR de conta_valor=False e de emissão, sem tocar em
        VALOR_BASE.
        """
        monkeypatch.setattr(
            loaders,
            "_paginar_keyset",
            lambda q, c: [
                _linha_pagos(valor_consolidado=1200.0, valor=1000.0),
                _linha_pagos(
                    contrato_id=2, valor_consolidado=500.0, valor=500.0
                ),
            ],
        )
        df = loaders._fetch_contratos_pagos(8, 2026)

        assert (df["VALOR"] >= df["VALOR_BASE"]).all()

    def test_datas_seguem_datetime(self, monkeypatch, periodo_stub):
        monkeypatch.setattr(
            loaders, "_paginar_keyset", lambda q, c: [_linha_pagos()]
        )
        df = loaders._fetch_contratos_pagos(8, 2026)

        for col in ("DATA", "DATA_CADASTRO", "CREATED_AT"):
            assert pd.api.types.is_datetime64_any_dtype(df[col]), col


def _linha_consignavel(**overrides):
    """Linha crua já filtrada pelo servidor (is_cobranca_consignavel)."""
    linha = {
        "contrato_id": 10,
        "num_proposta": "P10",
        "consultor": "FULANO",
        "loja": "LOJA A",
        "regiao": "R1",
        "regiao_atual": "R1",
        "tipo_operacao": "Contrato Novo",
        "subtipo": "NOVO",
        "banco": "BMG",
        "categoria_codigo": "CONSIG_BMG",
        "valor_consolidado": 1200.0,
        "valor": 1000.0,
        "valor_bruto": 1200.0,
        "data_status_pagamento": "2026-08-10",
    }
    linha.update(overrides)
    return linha


@pytest.mark.unit
class TestFetchCobrancaConsignavelServerSide:
    """O critério é filtro do servidor; em Python resta só o mês."""

    def test_filtro_is_cobranca_consignavel_vai_na_query(
        self, monkeypatch, periodo_stub
    ):
        registro = {}

        def _capturar(montar_query, coluna_chave):
            montar_query()
            return []

        monkeypatch.setattr(loaders, "_sb", lambda: _FakeQuery(registro))
        monkeypatch.setattr(loaders, "_paginar_keyset", _capturar)
        loaders._fetch_cobranca_consignavel(8, 2026)

        assert registro["tabela"] == "v_contratos_dashboard"
        assert registro["eq"]["is_cobranca_consignavel"] is True
        assert registro["eq"]["periodo_id"] == "periodo-1"
        assert (
            registro["eq"]["status_pagamento_cliente"]
            == "PAGO AO CLIENTE"
        )

    def test_linha_fora_do_mes_e_descartada(
        self, monkeypatch, periodo_stub
    ):
        monkeypatch.setattr(
            loaders,
            "_paginar_keyset",
            lambda q, c: [
                _linha_consignavel(),
                _linha_consignavel(
                    contrato_id=11, data_status_pagamento="2026-07-31"
                ),
            ],
        )
        df = loaders._fetch_cobranca_consignavel(8, 2026)

        assert len(df) == 1
        assert df.loc[0, "CONTRATO_ID"] == 10

    def test_valor_bruto_ausente_cai_no_valor_base(
        self, monkeypatch, periodo_stub
    ):
        monkeypatch.setattr(
            loaders,
            "_paginar_keyset",
            lambda q, c: [
                _linha_consignavel(
                    valor_bruto=None, valor=1000.0, valor_consolidado=1000.0
                )
            ],
        )
        df = loaders._fetch_cobranca_consignavel(8, 2026)

        assert df.loc[0, "VALOR_BRUTO"] == 1000.0
        assert df.loc[0, "VALOR_BASE"] == 1000.0

    def test_falha_devolve_vazio_com_colunas_esperadas(
        self, monkeypatch, periodo_stub
    ):
        """Contrato que a sub-aba depende quando a 067 não está aplicada."""
        def _explodir(montar_query, coluna_chave):
            raise RuntimeError("column is_cobranca_consignavel does not exist")

        monkeypatch.setattr(loaders, "_paginar_keyset", _explodir)
        df = loaders._fetch_cobranca_consignavel(8, 2026)

        assert df.empty
        assert list(df.columns) == list(
            loaders._COLS_COBRANCA_CONSIGNAVEL.values()
        )

    def test_sem_periodo_devolve_vazio(self, monkeypatch):
        monkeypatch.setattr(loaders, "carregar_periodo", lambda m, a: None)
        df = loaders._fetch_cobranca_consignavel(8, 2026)

        assert df.empty
        assert list(df.columns) == list(
            loaders._COLS_COBRANCA_CONSIGNAVEL.values()
        )


@pytest.mark.unit
class TestPorConsultorCobrancaConsignavel:
    """Agregação por consultor (frame já pós-RLS)."""

    def test_conta_por_consultor(self):
        contratos = pd.DataFrame({
            "CONSULTOR": ["A", "B", "A"],
            "VALOR": [1.0, 2.0, 3.0],
        })
        out = loaders._por_consultor_cobranca_consignavel(contratos)

        assert list(out.columns) == ["consultor", "cobranca_consignavel"]
        assert dict(
            zip(out["consultor"], out["cobranca_consignavel"])
        ) == {"A": 2, "B": 1}

    @pytest.mark.parametrize(
        "frame",
        [None, pd.DataFrame(), pd.DataFrame({"OUTRA": [1]})],
        ids=["none", "vazio", "sem-coluna-consultor"],
    )
    def test_frames_degenerados(self, frame):
        out = loaders._por_consultor_cobranca_consignavel(frame)

        assert out.empty
        assert list(out.columns) == ["consultor", "cobranca_consignavel"]
