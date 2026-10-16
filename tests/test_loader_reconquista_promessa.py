"""
`carregar_reconquista` com a Promessa Diaria (V3, >= 09/2026, mig. 137).

Exercita a ORQUESTRACAO: estados `promessa_status`, qual fonte vira
`totais["promessas"]`, o que nunca pode virar zero/numero do export, o
badge de efetivacao pela liga GLOBAL e a separacao entre
`totais["efetivadas"]` (liga) e `totais["promessas_efetivadas"]` (badge).
Todas as cargas sao substituidas; `_liga_desde` roda de verdade sobre
um `_liga_periodo` stubado.
"""
import pandas as pd
import pytest

from src.dashboard import loaders
from src.dashboard.kpis.reconquista import (
    PROMESSA_ERRO,
    PROMESSA_FORA,
    PROMESSA_NAO_IMPORTADA,
    PROMESSA_OK,
)


def _export(ref_ano, ref_mes):
    """Export do banco com 5 PROMESSA elegiveis: o numero que NUNCA
    deve aparecer no card V3."""
    return pd.DataFrame({
        "co_adesao": [1, 2, 3, 4, 5],
        "status": ["PROMESSA"] * 5,
        "flag_elegibilidade": ["ELEGIVEL"] * 5,
        "ref_ano": [ref_ano] * 5,
        "ref_mes": [ref_mes] * 5,
        "loja": ["L1"] * 5,
        "regiao": ["R1"] * 5,
        "consultor": ["ANA"] * 5,
        "saldo_contabil": [1.0] * 5,
        "dias_atraso": [0] * 5,
    })


def _promessa():
    """Promessa Diaria 09/2026: 4 elegiveis (3 ANA/L1, 1 BRUNO/L2) + 1
    nao elegivel; SUP e supervisora (cadastro) com 1 promessa em L1."""
    return pd.DataFrame({
        "co_adesao": [100, 101, 102, 103, 104, 105],
        "ano": [2026] * 6,
        "mes": [9] * 6,
        "elegivel": [True, True, True, True, False, True],
        "retorno_inss": [
            "REGISTRO ACEITO", "NÃO ACEITO", None, "REGISTRO ACEITO",
            "REGISTRO ACEITO", None,
        ],
        "status_cliente_atual": [
            "PROMESSA", "PROMESSA", "FDR E PROMESSA", "PROMESSA",
            "PROMESSA", "PROMESSA",
        ],
        "loja": ["L1", "L1", "L1", "L2", "L1", "L1"],
        "regiao": ["R1", "R1", "R1", "R2", "R1", "R1"],
        "consultor": ["ANA", "ANA", "ANA", "BRUNO", "ANA", "SUP"],
        "supervisor": ["SUP"] * 6,
        "consultor_identificado": [True] * 6,
    })


def _liga_p(*linhas):
    return pd.DataFrame(
        linhas, columns=["co_adesao", "ano", "mes", "qtde", "loja",
                         "regiao", "consultor"],
    )


@pytest.fixture
def ambiente(monkeypatch):
    """Substitui toda carga de `carregar_reconquista`.

    `estado["promessa"]`: DataFrame ou Exception (`_promessa_periodo`).
    `estado["ligas"]`: {(mes, ano): DataFrame | Exception} para
    `_liga_periodo` (o card da liga e o badge leem dele; periodo ausente
    = vazio). `estado["supervisores"]`: DataFrame ou Exception.
    `estado["chamadas_promessa"]`: argumentos recebidos.
    """
    estado = {
        "promessa": _promessa(),
        "ligas": {},
        "supervisores": pd.DataFrame({"SUPERVISOR": ["SUP"]}),
        "perfil": {"perfil": "gestor"},
        "filtro": None,
        "chamadas_promessa": [],
    }

    def _cache(mes, ano):
        ref_mes, ref_ano = loaders._mes_apuracao_anterior(mes, ano)
        return {
            "ref_mes": ref_mes, "ref_ano": ref_ano,
            "clientes": _export(ref_ano, ref_mes),
            "clientes_ant": _export(ref_ano, ref_mes),
            "clientes_prox": pd.DataFrame(),
        }

    def _promessa_periodo(mes, ano):
        estado["chamadas_promessa"].append((mes, ano))
        if isinstance(estado["promessa"], Exception):
            raise estado["promessa"]
        return estado["promessa"]

    def _liga_periodo(mes, ano):
        v = estado["ligas"].get((mes, ano), _liga_p())
        if isinstance(v, Exception):
            raise v
        return v

    def _supervisores(mes, ano):
        if isinstance(estado["supervisores"], Exception):
            raise estado["supervisores"]
        return estado["supervisores"]

    monkeypatch.setattr(loaders, "_reconquista_cache", _cache)
    monkeypatch.setattr(
        loaders, "_reconquista_todos", lambda: _export(2026, 8)
    )
    monkeypatch.setattr(loaders, "_promessa_periodo", _promessa_periodo)
    monkeypatch.setattr(loaders, "_liga_periodo", _liga_periodo)
    monkeypatch.setattr(
        loaders, "_filtro_rls_reconquista", lambda: estado["filtro"]
    )
    monkeypatch.setattr(
        loaders, "_filtrar_rls_reconquista", lambda dados: dados
    )
    monkeypatch.setattr(
        loaders, "_obter_perfil_efetivo", lambda: estado["perfil"]
    )
    monkeypatch.setattr(loaders, "aplicar_rls", lambda df: df)
    monkeypatch.setattr(
        loaders, "carregar_cobranca_consignavel",
        lambda mes, ano: pd.DataFrame({"CONSULTOR": ["ANA"]}),
    )
    monkeypatch.setattr(loaders, "carregar_supervisores", _supervisores)
    monkeypatch.setattr(
        loaders, "carregar_consultores_ativos",
        lambda: pd.DataFrame({"CONSULTOR": ["ANA", "BRUNO", "SUP"]}),
    )
    monkeypatch.setattr(
        loaders, "carregar_faixa_acelerador",
        lambda qtd, mes, ano: {
            "rotulo": f"faixa-{qtd}", "is_fallback": False,
            "is_deflator": False,
        },
    )
    return estado


@pytest.mark.unit
class TestEstadosPromessa:
    def test_ok_conta_elegiveis_do_arquivo_e_nao_do_export(self, ambiente):
        out = loaders.carregar_reconquista(9, 2026)
        t = out["totais"]
        assert t["promessa_status"] == PROMESSA_OK
        assert t["promessas"] == 5          # 4 + SUP; export tem 5 tambem
        assert t["nao_elegiveis"] == 1
        assert len(out["promessas"]) == 6   # frame lista tambem a nao elegivel

    def test_numero_vem_do_arquivo_mesmo_diferindo_do_export(self, ambiente):
        ambiente["promessa"] = _promessa().iloc[:2]   # 2 elegiveis
        t = loaders.carregar_reconquista(9, 2026)["totais"]
        assert t["promessas"] == 2   # export teria 5

    def test_insights_do_retorno_inss(self, ambiente):
        t = loaders.carregar_reconquista(9, 2026)["totais"]
        assert t["retorno_aceito"] == 2
        assert t["retorno_nao_aceito"] == 1
        assert t["retorno_pendente"] == 2
        assert t["fdr_e_promessa"] == 1

    def test_agosto_e_fora_e_nao_le_a_promessa(self, ambiente):
        out = loaders.carregar_reconquista(8, 2026)
        t = out["totais"]
        assert t["promessa_status"] == PROMESSA_FORA
        assert ambiente["chamadas_promessa"] == []
        assert t["promessas"] == 5            # export, regra intocada
        assert out["promessas"].empty
        assert out["promessas_por_loja"].empty

    def test_nao_importada_nao_vira_zero_nem_numero_do_export(
        self, ambiente
    ):
        ambiente["promessa"] = pd.DataFrame()
        t = loaders.carregar_reconquista(9, 2026)["totais"]
        assert t["promessa_status"] == PROMESSA_NAO_IMPORTADA
        assert t["promessas"] is None
        assert t["promessas_efetivadas"] is None
        assert t["nao_elegiveis"] is None

    def test_erro_de_leitura_vira_none_nunca_numero_do_export(
        self, ambiente
    ):
        ambiente["promessa"] = RuntimeError("view ausente")
        out = loaders.carregar_reconquista(9, 2026)
        t = out["totais"]
        assert t["promessa_status"] == PROMESSA_ERRO
        assert t["promessas"] is None
        assert out["promessas"].empty
        assert out["promessas_por_loja"].empty

    def test_nao_importada_e_decidida_antes_do_rls(self, ambiente):
        """Global vazio = nao importada. Escopo que esvazia o arquivo
        IMPORTADO e zero legitimo, nao 'nao importada'."""
        ambiente["filtro"] = lambda df: df.iloc[0:0]
        t = loaders.carregar_reconquista(9, 2026)["totais"]
        assert t["promessa_status"] == PROMESSA_OK
        assert t["promessas"] == 0

    def test_sem_promessa_global_e_nao_importada_mesmo_com_export_cheio(
        self, ambiente
    ):
        ambiente["promessa"] = pd.DataFrame()
        out = loaders.carregar_reconquista(9, 2026)
        assert out["totais"]["promessa_status"] == PROMESSA_NAO_IMPORTADA
        assert out["totais"]["total"] == 5   # export segue la, ignorado

    def test_v3_nao_tem_promessas_anterior(self, ambiente):
        t = loaders.carregar_reconquista(9, 2026)["totais"]
        assert "promessas_anterior" not in t

    def test_legado_mantem_promessas_anterior(self, ambiente):
        t = loaders.carregar_reconquista(8, 2026)["totais"]
        assert t["promessas_anterior"] == 5


@pytest.mark.unit
class TestBadgeEfetivacao:
    def test_cruza_com_a_liga_e_conta_efetivadas(self, ambiente):
        ambiente["ligas"][(9, 2026)] = _liga_p(
            (100, 2026, 9, 1, "L1", "R1", "ANA"),
            (103, 2026, 9, 0, "L2", "R2", "BRUNO"),
        )
        out = loaders.carregar_reconquista(9, 2026)
        assert out["totais"]["promessas_efetivadas"] == 1
        marcadas = out["promessas"].set_index("co_adesao")
        assert bool(marcadas.loc[100, "efetivada"]) is True
        assert marcadas.loc[100, "efetivada_ref"] == "09/2026"
        assert bool(marcadas.loc[103, "efetivada"]) is False

    def test_liga_de_periodo_posterior_tambem_efetiva(
        self, ambiente, monkeypatch
    ):
        import datetime as dt

        class _Agora(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 11, 5)

        monkeypatch.setattr(loaders, "datetime", _Agora)
        ambiente["ligas"][(11, 2026)] = _liga_p(
            (101, 2026, 11, 1, "L1", "R1", "ANA"),
        )
        out = loaders.carregar_reconquista(9, 2026)
        marcadas = out["promessas"].set_index("co_adesao")
        assert marcadas.loc[101, "efetivada_ref"] == "11/2026"

    def test_falha_na_liga_do_badge_deixa_badge_none_e_liga_intacta(
        self, ambiente, monkeypatch
    ):
        """O card da liga (periodo 09) le OK; o badge falha ao ler um
        periodo posterior. Promessa segue OK e `efetivadas` da liga nao
        e tocado."""
        import datetime as dt

        class _Agora(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 10, 5)

        monkeypatch.setattr(loaders, "datetime", _Agora)
        ambiente["ligas"][(9, 2026)] = _liga_p(
            (900, 2026, 9, 1, "L1", "R1", "ANA"),
            (901, 2026, 9, 1, "L1", "R1", "ANA"),
        )
        ambiente["ligas"][(10, 2026)] = RuntimeError("timeout")
        # O card da liga so le o periodo selecionado; o badge, ate
        # outubro -> levanta em 10/2026.
        out = loaders.carregar_reconquista(9, 2026)
        t = out["totais"]
        assert t["promessa_status"] == PROMESSA_OK
        assert t["promessas"] == 5
        assert t["promessas_efetivadas"] is None
        assert out["promessas"]["efetivada"].isna().all()
        assert t["efetivadas"] == 2   # liga do card, intacta

    def test_efetivadas_da_liga_nao_e_sobrescrito_pelo_badge(
        self, ambiente
    ):
        ambiente["ligas"][(9, 2026)] = _liga_p(
            (100, 2026, 9, 1, "L1", "R1", "ANA"),
            (900, 2026, 9, 1, "L1", "R1", "ANA"),
            (901, 2026, 9, 1, "L2", "R2", "BRUNO"),
        )
        t = loaders.carregar_reconquista(9, 2026)["totais"]
        assert t["efetivadas"] == 3             # liga inteira
        assert t["promessas_efetivadas"] == 1   # so a ADE 100

    def test_badge_usa_a_liga_global_e_nao_a_do_perfil(self, ambiente):
        """ADE 100 (promessa de L1) foi efetivada em liga atribuida a
        L2. Com RLS de L1 ela continua efetivada."""
        ambiente["ligas"][(9, 2026)] = _liga_p(
            (100, 2026, 9, 1, "L2", "R2", "BRUNO"),
        )
        ambiente["filtro"] = lambda df: df[df["loja"] == "L1"]
        out = loaders.carregar_reconquista(9, 2026)
        t = out["totais"]
        assert t["promessas_efetivadas"] == 1
        assert bool(
            out["promessas"].set_index("co_adesao").loc[100, "efetivada"]
        ) is True
        # ...enquanto a liga do card segue o RLS (L1 nao tem nada).
        assert t["efetivadas"] == 0

    def test_rls_recorta_a_promessa_e_a_contagem(self, ambiente):
        ambiente["filtro"] = lambda df: df[df["loja"] == "L2"]
        out = loaders.carregar_reconquista(9, 2026)
        assert out["totais"]["promessas"] == 1
        assert set(out["promessas"]["loja"]) == {"L2"}


@pytest.mark.unit
class TestQuebrasPromessa:
    def test_por_consultor_exclui_supervisor_e_por_loja_mantem(
        self, ambiente
    ):
        out = loaders.carregar_reconquista(9, 2026)
        cons = set(out["promessas_por_consultor"]["consultor"])
        assert cons == {"ANA", "BRUNO"}
        por_loja = out["promessas_por_loja"].set_index("loja")
        assert por_loja.loc["L1", "promessas"] == 4   # 3 ANA + 1 SUP
        assert out["totais"]["promessas"] == 5

    def test_supervisores_levantando_deixa_por_consultor_none(
        self, ambiente
    ):
        ambiente["supervisores"] = RuntimeError("cadastro fora")
        out = loaders.carregar_reconquista(9, 2026)
        assert out["promessas_por_consultor"] is None
        # O resto do bloco nao cai junto.
        assert out["totais"]["promessa_status"] == PROMESSA_OK
        assert out["totais"]["promessas"] == 5
        assert not out["promessas_por_loja"].empty

    def test_sem_promessa_ok_as_quebras_ficam_vazias(self, ambiente):
        ambiente["promessa"] = pd.DataFrame()
        out = loaders.carregar_reconquista(9, 2026)
        assert out["promessas_por_loja"].empty
        assert out["promessas_por_consultor"].empty


@pytest.mark.unit
class TestSemConsultorIdentificadoLoader:
    def test_lead_sem_consultor_vai_para_o_supervisor_da_loja(
        self, ambiente
    ):
        prom = _promessa()
        prom.loc[prom["co_adesao"] == 103, "consultor_identificado"] = False
        ambiente["promessa"] = prom
        ambiente["supervisores"] = pd.DataFrame(
            {"SUPERVISOR": ["SUP", "SUP2"], "LOJA": ["L1", "L2"]}
        )
        out = loaders.carregar_reconquista(9, 2026)
        cons = out["promessas_por_consultor"].set_index("consultor")
        assert "BRUNO" not in cons.index
        assert cons.loc["SUP2 · sem consultor identificado", "promessas"] == 1

    def test_view_sem_a_coluna_deixa_por_consultor_none(self, ambiente):
        ambiente["promessa"] = _promessa().drop(
            columns=["consultor_identificado"]
        )
        out = loaders.carregar_reconquista(9, 2026)
        assert out["promessas_por_consultor"] is None
        assert out["totais"]["promessa_status"] == PROMESSA_OK
        assert not out["promessas_por_loja"].empty
