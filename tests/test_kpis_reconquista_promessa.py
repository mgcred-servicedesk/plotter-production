"""
Promessa Diaria (V3, >= 09/2026) em ``kpis/reconquista.py``.

Regras fixadas aqui: a contagem do card e SO `elegivel = true` (o
retorno INSS e o status nao filtram), pendente = retorno vazio, badge
"Efetivada" vem so da liga e indisponivel (`liga=None`) nunca vira
False, e a quebra por pessoa exclui supervisor do CADASTRO enquanto a
quebra por loja os mantem.
"""
import pandas as pd
import pytest

from src.dashboard.kpis.reconquista import (
    marcar_efetivada,
    promessa_v3_vigente,
    promessas_por_consultor,
    promessas_por_loja,
    totais_promessa,
)


def _prom(linhas):
    """Frame da view a partir de dicts parciais (defaults de uma
    promessa elegivel, pendente, so PROMESSA, 09/2026)."""
    base = {
        "co_adesao": 1, "ano": 2026, "mes": 9,
        "elegivel": True, "retorno_inss": None,
        "status_cliente_atual": "PROMESSA",
        "loja": "L1", "regiao": "R1", "consultor": "ANA",
        "supervisor": "SUP", "consultor_identificado": True,
    }
    return pd.DataFrame([{**base, **linha} for linha in linhas])


@pytest.mark.unit
class TestPromessaV3Vigente:
    def test_agosto_2026_e_legado(self):
        assert promessa_v3_vigente(8, 2026) is False

    def test_setembro_2026_e_v3(self):
        assert promessa_v3_vigente(9, 2026) is True

    def test_virada_de_ano(self):
        assert promessa_v3_vigente(12, 2025) is False
        assert promessa_v3_vigente(1, 2027) is True


@pytest.mark.unit
class TestTotaisPromessa:
    def test_conta_so_elegivel_true(self):
        df = _prom([
            {"co_adesao": 1, "elegivel": True},
            {"co_adesao": 2, "elegivel": True},
            {"co_adesao": 3, "elegivel": False},
        ])
        t = totais_promessa(df)
        assert t["promessas"] == 2
        assert t["nao_elegiveis"] == 1

    def test_elegivel_nulo_nao_conta_nem_vira_nao_elegivel(self):
        df = _prom([
            {"co_adesao": 1, "elegivel": True},
            {"co_adesao": 2, "elegivel": None},
        ])
        t = totais_promessa(df)
        assert t["promessas"] == 1
        assert t["nao_elegiveis"] == 0

    def test_nao_elegivel_nao_entra_nas_quebras_de_retorno_e_status(self):
        df = _prom([
            {"co_adesao": 1, "elegivel": True,
             "retorno_inss": "REGISTRO ACEITO"},
            {"co_adesao": 2, "elegivel": False,
             "retorno_inss": "REGISTRO ACEITO",
             "status_cliente_atual": "FDR E PROMESSA"},
        ])
        t = totais_promessa(df)
        assert t["retorno_aceito"] == 1
        assert t["fdr_e_promessa"] == 0
        assert t["pct_retorno_aceito"] == 100.0

    def test_retorno_nao_aceito_nao_tira_a_promessa_da_conta(self):
        df = _prom([
            {"co_adesao": 1, "retorno_inss": "NÃO ACEITO"},
            {"co_adesao": 2, "retorno_inss": "REGISTRO ACEITO"},
        ])
        t = totais_promessa(df)
        assert t["promessas"] == 2
        assert t["retorno_nao_aceito"] == 1
        assert t["retorno_aceito"] == 1
        assert t["pct_retorno_aceito"] == 50.0

    def test_promessa_e_fdr_e_promessa_contam_as_duas(self):
        df = _prom([
            {"co_adesao": 1, "status_cliente_atual": "PROMESSA"},
            {"co_adesao": 2, "status_cliente_atual": "FDR E PROMESSA"},
            {"co_adesao": 3, "status_cliente_atual": "FDR E PROMESSA"},
        ])
        t = totais_promessa(df)
        assert t["promessas"] == 3
        assert t["so_promessa"] == 1
        assert t["fdr_e_promessa"] == 2

    @pytest.mark.parametrize("vazio", [None, float("nan"), "", "  "])
    def test_retorno_vazio_e_pendente(self, vazio):
        t = totais_promessa(_prom([{"retorno_inss": vazio}]))
        assert t["retorno_pendente"] == 1
        assert t["retorno_outros"] == 0

    def test_retorno_desconhecido_cai_em_outros_e_nao_some(self):
        df = _prom([
            {"co_adesao": 1, "retorno_inss": "EM ANALISE"},
            {"co_adesao": 2, "retorno_inss": "REGISTRO ACEITO"},
            {"co_adesao": 3, "retorno_inss": None},
            {"co_adesao": 4, "retorno_inss": "NAO ACEITO"},
        ])
        t = totais_promessa(df)
        assert t["retorno_outros"] == 1
        assert (
            t["retorno_aceito"] + t["retorno_pendente"]
            + t["retorno_nao_aceito"] + t["retorno_outros"]
        ) == t["promessas"] == 4

    def test_rotulo_com_e_sem_acento_equivalem(self):
        df = _prom([
            {"co_adesao": 1, "retorno_inss": "Não Aceito "},
            {"co_adesao": 2, "retorno_inss": "nao aceito"},
        ])
        assert totais_promessa(df)["retorno_nao_aceito"] == 2

    @pytest.mark.parametrize("vazio", [pd.DataFrame(), None])
    def test_frame_vazio_zera_tudo(self, vazio):
        t = totais_promessa(vazio)
        assert t["promessas"] == 0
        assert t["nao_elegiveis"] == 0
        assert t["pct_retorno_aceito"] == 0.0
        assert t["efetivadas"] == 0

    def test_so_nao_elegiveis_da_zero_promessas_sem_dividir_por_zero(self):
        t = totais_promessa(_prom([{"elegivel": False}]))
        assert t["promessas"] == 0
        assert t["nao_elegiveis"] == 1
        assert t["pct_retorno_aceito"] == 0.0

    def test_efetivadas_conta_so_elegiveis_com_badge(self):
        df = _prom([
            {"co_adesao": 1, "efetivada": True},
            {"co_adesao": 2, "efetivada": False},
            {"co_adesao": 3, "elegivel": False, "efetivada": True},
        ])
        assert totais_promessa(df)["efetivadas"] == 1

    def test_efetivadas_none_quando_badge_indisponivel(self):
        df = marcar_efetivada(_prom([{"co_adesao": 1}]), None)
        assert totais_promessa(df)["efetivadas"] is None

    def test_efetivadas_none_quando_frame_sem_coluna_de_badge(self):
        assert totais_promessa(_prom([{"co_adesao": 1}]))["efetivadas"] is None


def _liga(*linhas):
    return pd.DataFrame(
        linhas, columns=["co_adesao", "ano", "mes", "qtde"]
    )


@pytest.mark.unit
class TestMarcarEfetivada:
    def test_mesmo_periodo_marca_e_referencia_o_periodo(self):
        out = marcar_efetivada(_prom([{"co_adesao": 1}]),
                               _liga((1, 2026, 9, 1)))
        assert bool(out["efetivada"].iloc[0]) is True
        assert out["efetivada_ref"].iloc[0] == "09/2026"

    def test_periodo_posterior_marca(self):
        out = marcar_efetivada(_prom([{"co_adesao": 1}]),
                               _liga((1, 2026, 11, 1)))
        assert bool(out["efetivada"].iloc[0]) is True
        assert out["efetivada_ref"].iloc[0] == "11/2026"

    def test_ref_e_o_primeiro_periodo(self):
        liga = _liga((1, 2026, 11, 1), (1, 2026, 10, 1), (1, 2027, 1, 1))
        out = marcar_efetivada(_prom([{"co_adesao": 1}]), liga)
        assert out["efetivada_ref"].iloc[0] == "10/2026"

    def test_virada_de_ano_ordena_cronologicamente(self):
        prom = _prom([{"co_adesao": 1, "ano": 2026, "mes": 12}])
        liga = _liga((1, 2027, 1, 1), (1, 2026, 12, 1))
        out = marcar_efetivada(prom, liga)
        assert out["efetivada_ref"].iloc[0] == "12/2026"

    def test_periodo_anterior_a_promessa_nao_marca(self):
        out = marcar_efetivada(_prom([{"co_adesao": 1}]),
                               _liga((1, 2026, 8, 1)))
        assert bool(out["efetivada"].iloc[0]) is False
        assert pd.isna(out["efetivada_ref"].iloc[0])

    def test_qtde_zero_nao_marca(self):
        out = marcar_efetivada(_prom([{"co_adesao": 1}]),
                               _liga((1, 2026, 9, 0)))
        assert bool(out["efetivada"].iloc[0]) is False

    def test_qtde_zero_antes_nao_esconde_qtde_um_depois(self):
        liga = _liga((1, 2026, 9, 0), (1, 2026, 10, 1))
        out = marcar_efetivada(_prom([{"co_adesao": 1}]), liga)
        assert out["efetivada_ref"].iloc[0] == "10/2026"

    def test_ade_fora_da_liga_nao_marca_e_so_a_cruzada_marca(self):
        prom = _prom([{"co_adesao": 1}, {"co_adesao": 2}])
        out = marcar_efetivada(prom, _liga((2, 2026, 9, 1)))
        assert out["efetivada"].tolist() == [False, True]

    def test_liga_none_e_indisponivel_nunca_false(self):
        out = marcar_efetivada(_prom([{"co_adesao": 1}]), None)
        assert out["efetivada"].isna().all()
        assert out["efetivada_ref"].isna().all()

    def test_liga_lida_e_vazia_e_false_nao_indisponivel(self):
        out = marcar_efetivada(_prom([{"co_adesao": 1}]), _liga())
        assert not out["efetivada"].isna().any()
        assert bool(out["efetivada"].iloc[0]) is False

    def test_nao_muta_o_frame_de_entrada(self):
        prom = _prom([{"co_adesao": 1}])
        marcar_efetivada(prom, _liga((1, 2026, 9, 1)))
        assert "efetivada" not in prom.columns


def _df_sup(*nomes):
    return pd.DataFrame({"SUPERVISOR": list(nomes)})


@pytest.mark.unit
class TestQuebras:
    @pytest.fixture
    def prom(self):
        return _prom([
            {"co_adesao": 1, "consultor": "ANA", "loja": "L1"},
            {"co_adesao": 2, "consultor": "ANA", "loja": "L1"},
            {"co_adesao": 3, "consultor": "Carla Souza", "loja": "L1"},
            {"co_adesao": 4, "consultor": "BRUNO", "loja": "L2",
             "regiao": "R2"},
            {"co_adesao": 5, "consultor": "BRUNO", "loja": "L2",
             "regiao": "R2", "elegivel": False},
        ])

    def test_por_consultor_exclui_supervisor_do_cadastro(self, prom):
        out = promessas_por_consultor(prom, _df_sup("carla souza"))
        assert set(out["consultor"]) == {"ANA", "BRUNO"}

    def test_por_consultor_criterio_e_o_cadastro_nao_a_coluna_supervisor(
        self, prom
    ):
        # A coluna `supervisor` do arquivo cita ANA, mas o cadastro nao:
        # ANA permanece. Quem manda e o cadastro.
        prom["supervisor"] = "ANA"
        out = promessas_por_consultor(prom, _df_sup("CARLA SOUZA"))
        assert "ANA" in set(out["consultor"])
        assert "Carla Souza" not in set(out["consultor"])

    def test_por_consultor_conta_so_elegiveis(self, prom):
        out = promessas_por_consultor(prom, _df_sup()).set_index("consultor")
        assert out.loc["BRUNO", "promessas"] == 1
        assert out.loc["ANA", "promessas"] == 2

    def test_por_loja_mantem_supervisor_e_soma_a_loja_toda(self, prom):
        out = promessas_por_loja(prom).set_index("loja")
        assert out.loc["L1", "promessas"] == 3   # inclui Carla Souza
        assert out.loc["L2", "promessas"] == 1   # nao elegivel fora

    def test_total_por_loja_difere_do_por_consultor_so_pelo_supervisor(
        self, prom
    ):
        por_loja = promessas_por_loja(prom)["promessas"].sum()
        por_cons = promessas_por_consultor(
            prom, _df_sup("Carla Souza")
        )["promessas"].sum()
        assert por_loja - por_cons == 1

    def test_cadastro_none_nao_exclui_ninguem(self, prom):
        out = promessas_por_consultor(prom, None)
        assert "Carla Souza" in set(out["consultor"])

    def test_efetivadas_na_quebra_vem_do_badge(self, prom):
        marcado = marcar_efetivada(prom, _liga((1, 2026, 9, 1)))
        out = promessas_por_loja(marcado).set_index("loja")
        assert out.loc["L1", "efetivadas"] == 1
        assert out.loc["L2", "efetivadas"] == 0

    def test_efetivadas_na_quebra_e_na_sem_badge(self, prom):
        marcado = marcar_efetivada(prom, None)
        out = promessas_por_loja(marcado)
        assert out["efetivadas"].isna().all()

    @pytest.mark.parametrize("fn", [
        lambda d: promessas_por_loja(d),
        lambda d: promessas_por_consultor(d, _df_sup()),
    ])
    def test_frame_vazio_ou_none_devolve_vazio(self, fn):
        assert fn(pd.DataFrame()).empty
        assert fn(None).empty

    def test_ordena_por_promessas_desc(self, prom):
        out = promessas_por_loja(prom)
        assert out["loja"].tolist() == ["L1", "L2"]


def _df_sup_loja(*pares):
    """Cadastro de supervisores vigentes: pares (SUPERVISOR, LOJA)."""
    return pd.DataFrame(pares, columns=["SUPERVISOR", "LOJA"])


@pytest.mark.unit
class TestSemConsultorIdentificado:
    """Lead sem consultor identificado vai para o supervisor vigente da
    loja (cadastro), numa linha so desses leads — decisao 16/10/2026."""

    @pytest.fixture
    def prom(self):
        return _prom([
            {"co_adesao": 1, "consultor": "ANA", "loja": "L1"},
            # Nome do arquivo sem cadastro na loja L1
            {"co_adesao": 2, "consultor": "FULANA SEM CADASTRO",
             "loja": "L1", "consultor_identificado": False},
            # Nome de supervisora de OUTRA loja, nao resolvido em L2:
            # o lead e da loja L2, nao da pessoa
            {"co_adesao": 3, "consultor": "SUP L1", "loja": "L2",
             "regiao": "R2", "consultor_identificado": False},
            # Supervisora identificada na propria loja: fora da visao
            {"co_adesao": 4, "consultor": "SUP L1", "loja": "L1"},
            # Nao identificado e nao elegivel: fora da conta
            {"co_adesao": 5, "consultor": "OUTRA", "loja": "L1",
             "consultor_identificado": False, "elegivel": False},
        ])

    @pytest.fixture
    def sup(self):
        return _df_sup_loja(("SUP L1", "L1"), ("SUP L2", "L2"))

    def test_lead_vai_para_o_supervisor_da_loja_da_promessa(self, prom, sup):
        out = promessas_por_consultor(prom, sup).set_index("consultor")
        assert out.loc["SUP L1 · sem consultor identificado", "promessas"] == 1
        assert out.loc["SUP L2 · sem consultor identificado", "promessas"] == 1

    def test_nome_do_arquivo_nao_identificado_nao_vira_linha(self, prom, sup):
        out = promessas_por_consultor(prom, sup)
        assert "FULANA SEM CADASTRO" not in set(out["consultor"])

    def test_supervisor_identificado_continua_fora(self, prom, sup):
        # A linha do supervisor tem SO os leads sem consultor: a
        # promessa da propria SUP L1 (ADE 4) nao entra nela.
        out = promessas_por_consultor(prom, sup).set_index("consultor")
        assert "SUP L1" not in out.index
        assert out.loc["SUP L1 · sem consultor identificado", "promessas"] == 1

    def test_nenhum_lead_some(self, prom, sup):
        # Total por consultor = elegiveis - promessas do supervisor
        # identificado (ADE 4). Os nao identificados estao todos la.
        por_cons = promessas_por_consultor(prom, sup)["promessas"].sum()
        assert por_cons == 3

    def test_loja_sem_supervisor_vigente_tem_rotulo_explicito(self, prom):
        out = promessas_por_consultor(
            prom, _df_sup_loja(("SUP L1", "L1"))
        ).set_index("consultor")
        assert out.loc["Sem supervisor vigente · L2", "promessas"] == 1

    def test_loja_com_dois_supervisores_junta_os_nomes(self, prom):
        out = promessas_por_consultor(
            prom,
            _df_sup_loja(("SUP L1", "L1"), ("ZETA", "L2"), ("ALFA", "L2")),
        )
        assert "ALFA / ZETA · sem consultor identificado" in set(
            out["consultor"]
        )

    def test_match_de_loja_ignora_caixa_e_acento(self):
        prom = _prom([
            {"co_adesao": 1, "consultor": "X", "loja": "HELP ALCÂNTARA",
             "consultor_identificado": False},
        ])
        out = promessas_por_consultor(
            prom, _df_sup_loja(("MARIANA", "help alcantara"))
        )
        assert out["consultor"].tolist() == [
            "MARIANA · sem consultor identificado"
        ]

    def test_sem_a_coluna_levanta(self, prom, sup):
        with pytest.raises(KeyError):
            promessas_por_consultor(
                prom.drop(columns=["consultor_identificado"]), sup
            )

    def test_por_loja_nao_muda(self, prom):
        out = promessas_por_loja(prom).set_index("loja")
        assert out.loc["L1", "promessas"] == 3   # ANA + FULANA + SUP L1
        assert out.loc["L2", "promessas"] == 1
