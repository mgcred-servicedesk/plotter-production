"""
RLS aplicada ao frame da Promessa Diaria (`v_reconquista_promessa`).

Mesmo mecanismo da Reconquista (`_filtro_rls_reconquista`, colunas
minusculas `regiao`/`loja`/`consultor`): a view e GLOBAL (a chave do
app ignora RLS no banco), entao o recorte por perfil e client-side e
precisa negar quando falta informacao (fail-closed). Aqui o que muda
em relacao a `test_rls_reconquista.py` e o frame: tem promessas em
nome do supervisor e nao elegiveis, que o recorte nao pode distinguir.
"""
import pandas as pd
import pytest

import src.dashboard.rls as rls_mod
from src.dashboard.kpis.reconquista import totais_promessa
from src.dashboard.loaders import _filtro_rls_reconquista


@pytest.fixture
def promessas():
    """R1: L1 (consultoras ANA e SUP, SUP = supervisora) e L2; R2: L3."""
    return pd.DataFrame({
        "co_adesao": [1, 2, 3, 4, 5],
        "regiao": ["R1", "R1", "R1", "R1", "R2"],
        "loja": ["L1", "L1", "L1", "L2", "L3"],
        "consultor": ["ANA", "ANA", "SUP", "BRUNO", "CARLA"],
        "supervisor": ["SUP", "SUP", "SUP", "SUP2", "SUP3"],
        "elegivel": [True, False, True, True, True],
        "retorno_inss": [None] * 5,
        "status_cliente_atual": ["PROMESSA"] * 5,
    })


def _set_perfil(monkeypatch, perfil):
    monkeypatch.setattr(rls_mod, "_obter_perfil_efetivo", lambda: perfil)


def _ades(monkeypatch, promessas, perfil):
    _set_perfil(monkeypatch, perfil)
    filtro = _filtro_rls_reconquista()
    out = promessas if filtro is None else filtro(promessas)
    return sorted(out["co_adesao"].tolist()), out


@pytest.mark.unit
class TestRlsPromessa:
    @pytest.mark.parametrize("role", ["admin", "gestor"])
    def test_gestor_e_admin_veem_tudo(self, monkeypatch, promessas, role):
        ades, _ = _ades(monkeypatch, promessas,
                        {"perfil": role, "escopo": []})
        assert ades == [1, 2, 3, 4, 5]

    def test_gerente_so_a_regiao(self, monkeypatch, promessas):
        ades, _ = _ades(monkeypatch, promessas,
                        {"perfil": "gerente_comercial", "escopo": ["R1"]})
        assert ades == [1, 2, 3, 4]

    def test_gerente_de_duas_regioes(self, monkeypatch, promessas):
        ades, _ = _ades(
            monkeypatch, promessas,
            {"perfil": "gerente_comercial", "escopo": ["R1", "R2"]},
        )
        assert ades == [1, 2, 3, 4, 5]

    def test_supervisor_so_a_sua_loja_incluindo_as_em_nome_dele(
        self, monkeypatch, promessas
    ):
        ades, out = _ades(monkeypatch, promessas,
                          {"perfil": "supervisor", "escopo": ["L1"]})
        assert ades == [1, 2, 3]
        assert "SUP" in set(out["consultor"])   # promessa em nome dele

    def test_consultor_so_as_proprias(self, monkeypatch, promessas):
        ades, _ = _ades(monkeypatch, promessas,
                        {"perfil": "consultor", "escopo": ["ANA"]})
        assert ades == [1, 2]

    def test_contagem_do_card_segue_o_recorte(self, monkeypatch, promessas):
        _, out = _ades(monkeypatch, promessas,
                       {"perfil": "supervisor", "escopo": ["L1"]})
        t = totais_promessa(out)
        assert t["promessas"] == 2        # ADEs 1 e 3
        assert t["nao_elegiveis"] == 1    # ADE 2

    @pytest.mark.parametrize("perfil", [
        None,
        {},
        {"escopo": ["L1"]},
        {"perfil": None, "escopo": ["L1"]},
        {"perfil": "supervisor", "escopo": []},
        {"perfil": "supervisor", "escopo": None},
        {"perfil": "desconhecido", "escopo": ["L1"]},
    ])
    def test_sem_informacao_devolve_frame_vazio(
        self, monkeypatch, promessas, perfil
    ):
        _set_perfil(monkeypatch, perfil)
        filtro = _filtro_rls_reconquista()
        assert filtro is not None   # None = "sem recorte" = vazamento
        out = filtro(promessas)
        assert out.empty
        assert list(out.columns) == list(promessas.columns)

    @pytest.mark.parametrize("role,coluna", [
        ("gerente_comercial", "regiao"),
        ("supervisor", "loja"),
        ("consultor", "consultor"),
    ])
    def test_coluna_de_escopo_ausente_nega(
        self, monkeypatch, promessas, role, coluna
    ):
        _set_perfil(monkeypatch, {"perfil": role, "escopo": ["X"]})
        out = _filtro_rls_reconquista()(promessas.drop(columns=[coluna]))
        assert out.empty

    def test_escopo_inexistente_nao_traz_nada(self, monkeypatch, promessas):
        ades, _ = _ades(monkeypatch, promessas,
                        {"perfil": "supervisor", "escopo": ["L_X"]})
        assert ades == []
