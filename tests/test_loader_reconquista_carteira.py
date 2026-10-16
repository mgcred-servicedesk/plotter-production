"""
`carregar_carteira_elegivel` (Carteira Elegivel, migration 140).

Exercita a ORQUESTRACAO: estados CARTEIRA_*, o vazio decidido ANTES do
RLS, o recorte por perfil, o badge cruzado com a Promessa Diaria e a liga
GLOBAIS (com falha virando NA, nunca "nao trabalhado") e a quebra por
consultor indisponivel (None) sem cadastro de supervisores.
`_promessa_desde`/`_liga_desde` rodam de verdade sobre
`_promessa_periodo`/`_liga_periodo` stubados.
"""
import pandas as pd
import pytest

from src.dashboard import loaders
from src.dashboard.kpis.reconquista import (
    CARTEIRA_ERRO,
    CARTEIRA_FORA,
    CARTEIRA_NAO_IMPORTADA,
    CARTEIRA_OK,
    SUFIXO_A_DISTRIBUIR,
)


def _carteira():
    """10/2026: 1 ANA/L1 prioridade; 2 ANA/L1 baixa; 3 BRUNO/L2
    prioridade; 4 SUP/L1 (supervisora) prioridade."""
    return pd.DataFrame({
        "co_adesao": [1, 2, 3, 4],
        "ano": [2026] * 4,
        "mes": [10] * 4,
        "elegivel": [True] * 4,
        "baixa_prioridade": [False, True, False, False],
        "motivo_impedido_operar": [None, "ACAO", None, None],
        "status_cliente_anterior": ["SEM RECONQUISTA"] * 4,
        "saldo_carteira": [10.0, 20.0, 30.0, 40.0],
        "banco_origem": ["BMG"] * 4,
        "regra_pagamento": ["1° dia Útil Normal"] * 4,
        "loja": ["L1", "L1", "L2", "L1"],
        "regiao": ["R1", "R1", "R2", "R1"],
        "consultor": ["ANA", "ANA", "BRUNO", "SUP"],
        "consultor_identificado": [True] * 4,
    })


@pytest.fixture
def ambiente(monkeypatch):
    """`estado["carteira"]`: DataFrame ou Exception (`_carteira_periodo`).
    `estado["promessas"]` / `estado["ligas"]`: {(mes, ano): DataFrame |
    Exception}; periodo ausente = vazio. `estado["filtro"]`: funcao de
    RLS ou None (global)."""
    estado = {
        "carteira": _carteira(),
        "promessas": {},
        "ligas": {},
        "supervisores": pd.DataFrame({"SUPERVISOR": ["SUP"],
                                      "LOJA": ["L1"]}),
        "filtro": None,
        "chamadas": [],
    }

    def _carteira_periodo(mes, ano):
        estado["chamadas"].append((mes, ano))
        if isinstance(estado["carteira"], Exception):
            raise estado["carteira"]
        return estado["carteira"]

    def _por_periodo(chave, colunas):
        def _ler(mes, ano):
            v = estado[chave].get((mes, ano), pd.DataFrame(columns=colunas))
            if isinstance(v, Exception):
                raise v
            return v
        return _ler

    def _supervisores(mes, ano):
        if isinstance(estado["supervisores"], Exception):
            raise estado["supervisores"]
        return estado["supervisores"]

    monkeypatch.setattr(loaders, "_carteira_periodo", _carteira_periodo)
    monkeypatch.setattr(
        loaders, "_promessa_periodo",
        _por_periodo("promessas", ["co_adesao", "ano", "mes"]),
    )
    monkeypatch.setattr(
        loaders, "_liga_periodo",
        _por_periodo("ligas", ["co_adesao", "ano", "mes", "qtde"]),
    )
    monkeypatch.setattr(
        loaders, "_filtro_rls_reconquista", lambda: estado["filtro"]
    )
    monkeypatch.setattr(loaders, "carregar_supervisores", _supervisores)
    return estado


def _prom(*ades, mes=10):
    return pd.DataFrame({"co_adesao": list(ades), "ano": 2026, "mes": mes})


def _liga(*ades, qtde=1, mes=10):
    return pd.DataFrame({"co_adesao": list(ades), "ano": 2026, "mes": mes,
                         "qtde": qtde})


@pytest.mark.unit
class TestEstados:
    def test_antes_de_10_2026_e_fora_e_nao_le_nada(self, ambiente):
        out = loaders.carregar_carteira_elegivel(9, 2026)
        assert out["status"] == CARTEIRA_FORA
        assert out["totais"] is None
        assert ambiente["chamadas"] == []

    def test_ok(self, ambiente):
        out = loaders.carregar_carteira_elegivel(10, 2026)
        assert out["status"] == CARTEIRA_OK
        assert out["totais"]["elegiveis"] == 4
        assert out["totais"]["baixa_prioridade"] == 1

    def test_periodo_vazio_e_nao_importada_e_nao_zero(self, ambiente):
        ambiente["carteira"] = _carteira().iloc[0:0]
        out = loaders.carregar_carteira_elegivel(10, 2026)
        assert out["status"] == CARTEIRA_NAO_IMPORTADA
        assert out["totais"] is None

    def test_falha_de_leitura_e_erro_e_nao_zero(self, ambiente):
        ambiente["carteira"] = RuntimeError("timeout")
        out = loaders.carregar_carteira_elegivel(10, 2026)
        assert out["status"] == CARTEIRA_ERRO
        assert out["totais"] is None
        assert out["carteira"].empty

    def test_escopo_sem_cliente_e_zero_legitimo(self, ambiente):
        """Vazio DEPOIS do RLS nao e "nao importada"."""
        ambiente["filtro"] = lambda df: df.iloc[0:0]
        out = loaders.carregar_carteira_elegivel(10, 2026)
        assert out["status"] == CARTEIRA_OK
        assert out["totais"]["elegiveis"] == 0


@pytest.mark.unit
class TestRlsEOrdem:
    def test_rls_recorta_antes_dos_totais_e_quebras(self, ambiente):
        ambiente["filtro"] = lambda df: df[df["loja"] == "L2"]
        out = loaders.carregar_carteira_elegivel(10, 2026)
        assert out["carteira"]["co_adesao"].tolist() == [3]
        assert out["totais"]["elegiveis"] == 1
        assert out["por_loja"]["loja"].tolist() == ["L2"]
        assert out["por_banco"]["clientes"].sum() == 1

    def test_carteira_sai_ordenada_baixa_prioridade_no_fim(self, ambiente):
        ades = loaders.carregar_carteira_elegivel(10, 2026)[
            "carteira"
        ]["co_adesao"].tolist()
        assert ades == [4, 3, 1, 2]

    def test_motivo_so_da_baixa_prioridade(self, ambiente):
        motivo = loaders.carregar_carteira_elegivel(10, 2026)["por_motivo"]
        assert motivo["motivo_impedido_operar"].tolist() == ["ACAO"]


@pytest.mark.unit
class TestBadge:
    def test_cruza_com_promessa_e_liga_de_meses_seguintes(
        self, ambiente, monkeypatch
    ):
        class _Relogio:
            @staticmethod
            def now():
                return pd.Timestamp("2026-11-05")

        monkeypatch.setattr(loaders, "datetime", _Relogio)
        ambiente["promessas"] = {(11, 2026): _prom(1, mes=11)}
        ambiente["ligas"] = {(10, 2026): _liga(3)}
        df = loaders.carregar_carteira_elegivel(10, 2026)[
            "carteira"
        ].set_index("co_adesao")
        assert df.loc[1, "prometido_ref"] == "11/2026"
        assert bool(df.loc[3, "efetivado"])
        assert not bool(df.loc[2, "prometido"])

    def test_badge_usa_fontes_globais_e_nao_as_do_perfil(self, ambiente):
        """Promessa registrada em OUTRA loja ainda marca o cliente."""
        ambiente["filtro"] = lambda df: df[df["loja"] == "L1"]
        ambiente["promessas"] = {(10, 2026): _prom(1).assign(loja="L9")}
        df = loaders.carregar_carteira_elegivel(10, 2026)[
            "carteira"
        ].set_index("co_adesao")
        assert bool(df.loc[1, "prometido"])

    def test_falha_na_promessa_vira_na_sem_derrubar(self, ambiente):
        ambiente["promessas"] = {(10, 2026): RuntimeError("x")}
        out = loaders.carregar_carteira_elegivel(10, 2026)
        assert out["status"] == CARTEIRA_OK
        assert out["carteira"]["prometido"].isna().all()
        assert out["totais"]["prometidos"] is None
        assert out["totais"]["efetivados"] == 0

    def test_falha_na_liga_vira_na_sem_derrubar(self, ambiente):
        ambiente["ligas"] = {(10, 2026): RuntimeError("x")}
        out = loaders.carregar_carteira_elegivel(10, 2026)
        assert out["status"] == CARTEIRA_OK
        assert out["carteira"]["efetivado"].isna().all()
        assert out["totais"]["efetivados"] is None


@pytest.mark.unit
class TestPorConsultor:
    def test_supervisora_vai_para_a_distribuir(self, ambiente):
        q = loaders.carregar_carteira_elegivel(10, 2026)["por_consultor"]
        assert "SUP" + SUFIXO_A_DISTRIBUIR in q["consultor"].tolist()
        assert q["elegiveis"].sum() == 4

    def test_sem_cadastro_de_supervisores_fica_indisponivel(self, ambiente):
        ambiente["supervisores"] = RuntimeError("x")
        out = loaders.carregar_carteira_elegivel(10, 2026)
        assert out["status"] == CARTEIRA_OK
        assert out["por_consultor"] is None
        assert not out["por_loja"].empty

    def test_view_sem_consultor_identificado_fica_indisponivel(
        self, ambiente
    ):
        ambiente["carteira"] = _carteira().drop(
            columns="consultor_identificado"
        )
        out = loaders.carregar_carteira_elegivel(10, 2026)
        assert out["por_consultor"] is None
