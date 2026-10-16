"""
Regras da Carteira Elegivel (`kpis/reconquista.py`, migration 140).

Foto mensal da carteira a trabalhar — so analitico. O que se protege:
  - o corte de vigencia (>= 10/2026) que troca as sub-abas do export;
  - baixa prioridade CONTA como elegivel, mas vem DEPOIS na ordem;
  - badges "prometido"/"efetivado" so com periodo >= o da carteira, e
    fonte ilegivel vira NA (nunca "nao trabalhado");
  - na quebra por consultor nenhum lead some: sem consultor identificado
    E carteira em nome de supervisor vao para "<SUPERVISOR VIGENTE> · a
    distribuir" (decisao do usuario, 16/10/2026).
"""
import pandas as pd
import pytest

from src.dashboard.kpis.reconquista import (
    ROTULO_NAO_INFORMADO,
    ROTULO_SEM_SUPERVISOR,
    SUFIXO_A_DISTRIBUIR,
    SUFIXO_SEM_CONSULTOR,
    carteira_elegivel_vigente,
    carteira_por_consultor,
    carteira_por_dimensao,
    carteira_por_loja,
    marcar_trabalhado,
    ordenar_carteira,
    promessas_por_consultor,
    totais_carteira,
)


def _carteira(**over) -> pd.DataFrame:
    """10/2026, loja L1 (supervisora SUP) e L2 (sem supervisor):
    1 ANA prioridade 100; 2 ANA baixa 500; 3 BRUNO prioridade 300;
    4 nome nao identificado em L1, prioridade 50; 5 carteira em nome
    da SUP em L1, prioridade 0; 6 ZE nao identificado em L2, baixa,
    saldo ausente."""
    df = pd.DataFrame({
        "co_adesao": [1, 2, 3, 4, 5, 6],
        "ano": [2026] * 6,
        "mes": [10] * 6,
        "elegivel": [True] * 6,
        "baixa_prioridade": [False, True, False, False, False, True],
        "status_cliente_anterior": [
            "SEM RECONQUISTA", "FDR", "SEM RECONQUISTA", "FDR",
            "SEM RECONQUISTA", "SEM RECONQUISTA",
        ],
        "saldo_carteira": [100.0, 500.0, 300.0, 50.0, 0.0, None],
        "banco_origem": ["BMG", "BMG", "ITAU", None, "BMG", "BMG"],
        "motivo_impedido_operar": [None, "ACAO", None, None, None, "SAC"],
        "loja": ["L1", "L1", "L1", "L1", "L1", "L2"],
        "regiao": ["R1"] * 5 + ["R2"],
        "consultor": ["ANA", "ANA", "BRUNO", "FULANO", "SUP", "ZE"],
        "consultor_identificado": [True, True, True, False, True, False],
    })
    for k, v in over.items():
        df[k] = v
    return df


def _sup() -> pd.DataFrame:
    return pd.DataFrame({"SUPERVISOR": ["SUP"], "LOJA": ["L1"]})


def _badges_ok(df: pd.DataFrame) -> pd.DataFrame:
    return marcar_trabalhado(df, pd.DataFrame(), pd.DataFrame())


@pytest.mark.unit
class TestVigencia:
    @pytest.mark.parametrize("mes, ano, esperado", [
        (9, 2026, False), (10, 2026, True), (11, 2026, True),
        (1, 2027, True), (12, 2025, False),
    ])
    def test_corte_em_10_2026(self, mes, ano, esperado):
        assert carteira_elegivel_vigente(mes, ano) is esperado


@pytest.mark.unit
class TestOrdenacao:
    def test_prioritarios_primeiro_maior_saldo_antes(self):
        ades = ordenar_carteira(_carteira())["co_adesao"].tolist()
        # prioridade por saldo desc (3, 1, 4, 5) e depois baixa (2, 6).
        assert ades == [3, 1, 4, 5, 2, 6]

    def test_baixa_prioridade_de_saldo_alto_nao_sobe(self):
        ades = ordenar_carteira(_carteira())["co_adesao"].tolist()
        assert ades.index(2) > ades.index(5)   # 500 baixa < 0 prioridade

    def test_prioridade_nula_vai_para_o_fim(self):
        df = _carteira(baixa_prioridade=[False, True, None, False, False,
                                         True])
        assert ordenar_carteira(df)["co_adesao"].tolist()[-1] == 3


@pytest.mark.unit
class TestTotais:
    def test_baixa_prioridade_conta_como_elegivel(self):
        t = totais_carteira(_badges_ok(_carteira()))
        assert t["elegiveis"] == 6
        assert t["prioridade"] == 4
        assert t["baixa_prioridade"] == 2

    def test_saldo_ignora_ausente_e_conta_zero_de_verdade(self):
        t = totais_carteira(_badges_ok(_carteira()))
        assert t["saldo_total"] == pytest.approx(950.0)
        assert t["saldo_prioridade"] == pytest.approx(450.0)
        assert t["saldo_zero"] == 1

    def test_fdr_anterior_e_sem_consultor(self):
        t = totais_carteira(_badges_ok(_carteira()))
        assert t["fdr_anterior"] == 2
        assert t["sem_consultor"] == 2

    def test_nao_elegivel_fica_fora_da_conta(self):
        df = _carteira(elegivel=[True, True, True, True, True, False])
        t = totais_carteira(_badges_ok(df))
        assert t["elegiveis"] == 5
        assert t["nao_elegiveis"] == 1
        assert t["baixa_prioridade"] == 1

    def test_badge_indisponivel_vira_none_e_nao_zero(self):
        t = totais_carteira(marcar_trabalhado(_carteira(), None, None))
        assert t["prometidos"] is None
        assert t["efetivados"] is None


@pytest.mark.unit
class TestMarcarTrabalhado:
    def _prom(self, *linhas):
        return pd.DataFrame(linhas, columns=["co_adesao", "ano", "mes"])

    def _liga(self, *linhas):
        return pd.DataFrame(
            linhas, columns=["co_adesao", "ano", "mes", "qtde"]
        )

    def test_prometido_no_mes_ou_depois(self):
        prom = self._prom((1, 2026, 10), (3, 2026, 11))
        df = marcar_trabalhado(_carteira(), prom, self._liga())
        por_ade = df.set_index("co_adesao")
        assert por_ade.loc[1, "prometido_ref"] == "10/2026"
        assert por_ade.loc[3, "prometido_ref"] == "11/2026"
        assert not bool(por_ade.loc[2, "prometido"])

    def test_promessa_anterior_a_foto_nao_marca(self):
        prom = self._prom((1, 2026, 9))
        df = marcar_trabalhado(_carteira(), prom, self._liga())
        assert not df["prometido"].any()

    def test_promessa_nao_elegivel_tambem_marca(self):
        """Acao feita sobre o cliente, nao a conta do card."""
        prom = self._prom((1, 2026, 10)).assign(elegivel=False)
        df = marcar_trabalhado(_carteira(), prom, self._liga())
        assert bool(df.set_index("co_adesao").loc[1, "prometido"])

    def test_efetivado_so_com_qtde_1(self):
        liga = self._liga((1, 2026, 10, 1), (3, 2026, 10, 0))
        df = marcar_trabalhado(_carteira(), self._prom(), liga)
        por_ade = df.set_index("co_adesao")
        assert bool(por_ade.loc[1, "efetivado"])
        assert not bool(por_ade.loc[3, "efetivado"])

    def test_fonte_ilegivel_vira_na_nunca_false(self):
        df = marcar_trabalhado(_carteira(), None, self._liga())
        assert df["prometido"].isna().all()
        assert not df["efetivado"].isna().any()
        df = marcar_trabalhado(_carteira(), self._prom(), None)
        assert df["efetivado"].isna().all()


@pytest.mark.unit
class TestDimensao:
    def test_banco_conta_clientes_e_saldo(self):
        d = carteira_por_dimensao(_carteira(), "banco_origem")
        bmg = d.set_index("banco_origem").loc["BMG"]
        assert bmg["clientes"] == 4
        assert bmg["saldo"] == pytest.approx(600.0)

    def test_vazio_vira_nao_informado_e_nao_some(self):
        d = carteira_por_dimensao(_carteira(), "banco_origem")
        assert ROTULO_NAO_INFORMADO in d["banco_origem"].tolist()
        assert d["clientes"].sum() == 6


@pytest.mark.unit
class TestPorLoja:
    def test_loja_inclui_supervisor_e_sem_consultor(self):
        q = carteira_por_loja(_badges_ok(_carteira())).set_index("loja")
        assert q.loc["L1", "elegiveis"] == 5
        assert q.loc["L1", "prioridade"] == 4
        assert q.loc["L1", "baixa_prioridade"] == 1

    def test_badge_indisponivel_vira_na_na_coluna(self):
        q = carteira_por_loja(marcar_trabalhado(_carteira(), None, None))
        assert q["prometidos"].isna().all()
        assert q["efetivados"].isna().all()


@pytest.mark.unit
class TestPorConsultor:
    def test_nenhum_lead_some(self):
        q = carteira_por_consultor(_badges_ok(_carteira()), _sup())
        assert q["elegiveis"].sum() == 6

    def test_supervisor_e_sem_consultor_vao_para_a_distribuir(self):
        q = carteira_por_consultor(_badges_ok(_carteira()), _sup())
        linhas = q.set_index("consultor")["elegiveis"].to_dict()
        assert linhas["SUP" + SUFIXO_A_DISTRIBUIR] == 2   # FULANO + SUP
        assert "SUP" not in linhas
        assert "FULANO" not in linhas

    def test_loja_sem_supervisor_tem_rotulo_explicito(self):
        q = carteira_por_consultor(_badges_ok(_carteira()), _sup())
        assert ROTULO_SEM_SUPERVISOR.format(loja="L2") in q[
            "consultor"
        ].tolist()

    def test_consultor_identificado_fica_no_proprio_nome(self):
        q = carteira_por_consultor(_badges_ok(_carteira()), _sup())
        linhas = q.set_index("consultor")["elegiveis"].to_dict()
        assert linhas["ANA"] == 2
        assert linhas["BRUNO"] == 1

    def test_match_de_supervisor_ignora_acento_e_caixa(self):
        df = _carteira(consultor=["ANA", "ANA", "BRUNO", "FULANO",
                                  "Súp", "ZE"])
        q = carteira_por_consultor(_badges_ok(df), _sup())
        assert "Súp" not in q["consultor"].tolist()

    def test_supervisor_vigente_e_o_do_cadastro_da_loja(self):
        """A carteira da SUP em L1 vai para quem supervisiona L1 HOJE."""
        sup = pd.DataFrame({"SUPERVISOR": ["SUP", "NOVA"],
                            "LOJA": ["L9", "L1"]})
        q = carteira_por_consultor(_badges_ok(_carteira()), sup)
        assert "NOVA" + SUFIXO_A_DISTRIBUIR in q["consultor"].tolist()

    def test_sem_a_coluna_identificado_levanta(self):
        df = _badges_ok(_carteira()).drop(columns="consultor_identificado")
        with pytest.raises(KeyError):
            carteira_por_consultor(df, _sup())

    def test_promessa_continua_excluindo_supervisor(self):
        """Regressao: o sufixo novo nao muda a regra da Promessa Diaria."""
        prom = _carteira().assign(
            retorno_inss=None, status_cliente_atual="PROMESSA",
        )
        q = promessas_por_consultor(prom, _sup())
        nomes = q["consultor"].tolist()
        assert "SUP" not in nomes
        assert "SUP" + SUFIXO_SEM_CONSULTOR in nomes
        assert not any(SUFIXO_A_DISTRIBUIR in n for n in nomes)
