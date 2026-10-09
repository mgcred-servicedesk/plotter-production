"""Regras puras do Seguro Prestamista CNC (IPV) — kpis/prestamista.py."""
import pandas as pd
import pytest

from src.dashboard.kpis.prestamista import (
    SEMAFORO_AMARELO,
    SEMAFORO_VERDE,
    SEMAFORO_VERMELHO,
    classificar_ipv,
    quebra_prestamista,
    totais_prestamista,
)

META = {"meta_ipv": 0.80, "faixa_alerta": 0.60}


def _propostas():
    return pd.DataFrame({
        "co_adesao": [1, 2, 3, 4, 5, 6, 7],
        "qtd_elegivel": [1, 1, 1, 0, 1, 1, 0],
        "qtd_seguro": [1, 1, 0, 0, 1, 0, 0],
        "regiao": ["R1", "R1", "R1", "R1", "R2", "R2", "R2"],
        "loja": ["L1", "L1", "L2", "L2", "L3", "L3", "L3"],
        "consultor": ["ANA", "ANA", "BIA", "BIA", "CAU", "CAU", "DUDA"],
    })


@pytest.mark.unit
class TestTotais:
    def test_ipv_e_seguros_sobre_elegiveis(self):
        t = totais_prestamista(_propostas())
        assert t == {
            "elegiveis": 5, "seguros": 3, "propostas": 7, "ipv": 3 / 5,
        }

    def test_arquivo_real_bate_com_o_rodape_do_bi(self):
        # Prestamista_CNC.xlsx de 10/2026: 93 / 231 = 40,26%.
        df = pd.DataFrame({
            "qtd_elegivel": [1] * 231 + [0] * 719,
            "qtd_seguro": [1] * 93 + [0] * 857,
        })
        assert totais_prestamista(df)["ipv"] == pytest.approx(0.4026, abs=1e-4)

    @pytest.mark.parametrize("df", [None, pd.DataFrame()])
    def test_sem_dado_ipv_indefinido_nao_zero(self, df):
        assert totais_prestamista(df)["ipv"] is None

    def test_sem_elegivel_ipv_indefinido(self):
        df = pd.DataFrame({"qtd_elegivel": [0, 0], "qtd_seguro": [0, 0]})
        assert totais_prestamista(df)["ipv"] is None

    def test_valores_nulos_viram_zero(self):
        df = pd.DataFrame({"qtd_elegivel": [1, None], "qtd_seguro": [None, 0]})
        t = totais_prestamista(df)
        assert (t["elegiveis"], t["seguros"], t["ipv"]) == (1, 0, 0.0)


@pytest.mark.unit
class TestQuebra:
    def test_por_regiao(self):
        q = quebra_prestamista(_propostas(), ["regiao"]).set_index("regiao")
        assert q.loc["R1", "elegiveis"] == 3 and q.loc["R1", "seguros"] == 2
        assert q.loc["R2", "ipv"] == pytest.approx(0.5)

    def test_consultor_sem_elegivel_aparece_sem_ipv_no_fim(self):
        q = quebra_prestamista(_propostas(), ["consultor"])
        assert list(q["consultor"]) == ["ANA", "CAU", "BIA", "DUDA"]
        assert q.iloc[-1]["ipv"] is None

    def test_dois_niveis(self):
        q = quebra_prestamista(_propostas(), ["loja", "consultor"])
        assert list(q.columns) == [
            "loja", "consultor", "elegiveis", "seguros", "ipv",
        ]
        assert len(q) == 4

    def test_coluna_ausente_devolve_vazio(self):
        q = quebra_prestamista(_propostas().drop(columns="regiao"), ["regiao"])
        assert q.empty and "ipv" in q.columns


@pytest.mark.unit
class TestSemaforo:
    @pytest.mark.parametrize("ipv,cor", [
        (0.80, SEMAFORO_VERDE),
        (0.95, SEMAFORO_VERDE),
        (0.7999, SEMAFORO_AMARELO),
        (0.60, SEMAFORO_AMARELO),
        (0.5999, SEMAFORO_VERMELHO),
        (0.0, SEMAFORO_VERMELHO),
    ])
    def test_limites_inclusivos(self, ipv, cor):
        assert classificar_ipv(ipv, META) == cor

    def test_sem_meta_ou_sem_ipv_sem_cor(self):
        assert classificar_ipv(0.9, None) is None
        assert classificar_ipv(None, META) is None


@pytest.mark.unit
def test_nan_nao_vira_vermelho():
    """Regressao: IPV NaN (consultor sem elegivel) era pintado de vermelho."""
    assert classificar_ipv(float("nan"), META) is None


# ── Situacao por proposta (analiticos) ──────────────────────────────────

from src.dashboard.kpis.prestamista import (  # noqa: E402
    SITUACAO_COM_SEGURO,
    SITUACAO_NAO_ELEGIVEL,
    SITUACAO_SEM_SEGURO,
    marcar_situacao_por_ade,
    pendencias_prestamista,
    situacao_prestamista,
)


@pytest.mark.unit
class TestSituacao:
    @pytest.mark.parametrize("eleg,seg,esperado", [
        (1, 1, SITUACAO_COM_SEGURO),
        (1, 0, SITUACAO_SEM_SEGURO),
        (0, 0, SITUACAO_NAO_ELEGIVEL),
        (0, 1, SITUACAO_COM_SEGURO),  # seguro manda, como no IPV do BI
        (None, None, SITUACAO_NAO_ELEGIVEL),
    ])
    def test_rotulo(self, eleg, seg, esperado):
        assert situacao_prestamista(eleg, seg) == esperado

    def test_pendencias_sao_so_elegiveis_sem_seguro(self):
        pend = pendencias_prestamista(_propostas())
        assert sorted(pend["co_adesao"]) == [3, 6]
        assert set(pend["situacao"]) == {SITUACAO_SEM_SEGURO}

    def test_pendencias_sem_dado(self):
        assert pendencias_prestamista(None).empty

    def test_marca_ade_texto_contra_adesao_inteira(self):
        """Nº ADE do dashboard e texto; Adesao do arquivo e inteiro."""
        ades = pd.Series(["1", " 3 ", "4", "999"])
        marcado = marcar_situacao_por_ade(ades, _propostas())
        assert list(marcado) == [
            SITUACAO_COM_SEGURO, SITUACAO_SEM_SEGURO, SITUACAO_NAO_ELEGIVEL, "",
        ]

    def test_adesao_float_do_banco_nao_vira_ponto_zero(self):
        prop = _propostas().assign(co_adesao=lambda d: d["co_adesao"] * 1.0)
        marcado = marcar_situacao_por_ade(pd.Series(["3"]), prop)
        assert marcado.iloc[0] == SITUACAO_SEM_SEGURO

    def test_sem_arquivo_tudo_em_branco(self):
        marcado = marcar_situacao_por_ade(pd.Series(["1", "2"]), None)
        assert list(marcado) == ["", ""]


from src.dashboard.kpis.prestamista import projetar_prestamista  # noqa: E402


@pytest.mark.unit
class TestProjecao:
    def test_ipv_projetado_e_o_de_hoje(self):
        # 93 / 231 em 5 de 21 DU: ritmo linear mantem a razao.
        p = projetar_prestamista({"seguros": 93, "elegiveis": 231}, 5, 21)
        assert p == {"ipv": pytest.approx(93 / 231)}

    @pytest.mark.parametrize("dec,total,eleg", [(0, 21, 2), (5, 0, 2), (5, 21, 0)])
    def test_sem_du_ou_sem_elegivel_sem_projecao(self, dec, total, eleg):
        assert projetar_prestamista(
            {"seguros": 1, "elegiveis": eleg}, dec, total
        ) is None
