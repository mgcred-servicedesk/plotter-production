"""
RLS da Reconquista (``loaders._filtro_rls_reconquista``) e a decisão
central de autorização (``rls.decidir_rls``).

## Por que este arquivo existe

A revisão de 09/2026 encontrou **duas** implementações de RLS com
comportamentos divergentes para o MESMO perfil: ``rls.aplicar_rls``
negava acesso quando faltava informação (escopo vazio, coluna de escopo
ausente, perfil desconhecido), enquanto o recorte da Reconquista
devolvia a base **inteira** nos mesmos casos — ele tratava "não sei
recortar" como "não precisa recortar".

A correção tem duas partes, e este arquivo cobre as duas:

1. ``decidir_rls`` — a decisão de QUEM vê o que passa a viver em um
   lugar só, com três saídas e só três (global / recortar por coluna /
   negar). O mapa ``role -> coluna`` continua do chamador, porque o
   nome da coluna muda com o dataset: ``REGIAO``/``LOJA``/``CONSULTOR``
   nos frames do dashboard, ``regiao``/``loja``/``consultor``
   minúsculos na view da Reconquista.
2. O adaptador de cada dataset nega quando a coluna de escopo não
   existe **naquele frame** — é a parte que a decisão central não pode
   saber por ele.

``_negar`` devolve frame vazio PRESERVANDO o schema: a UI da Reconquista
lê colunas por nome (``status``, ``loja``, ``consultor``) e um
``pd.DataFrame()`` cru viraria ``KeyError`` em vez de tela vazia.
"""
import pandas as pd
import pytest

import src.dashboard.rls as rls_mod
from src.dashboard.loaders import (
    _filtrar_rls_reconquista,
    _filtro_rls_reconquista,
)
from src.dashboard.rls import decidir_rls

# Mapa role -> coluna da view de Reconquista (minúsculas), igual ao que
# `_filtro_rls_reconquista` passa para `decidir_rls`.
_COLUNAS_RECONQUISTA = {
    "gerente_comercial": "regiao",
    "supervisor": "loja",
    "consultor": "consultor",
}


@pytest.fixture
def clientes():
    """Dois leads em escopos disjuntos (R1/L1/A e R2/L2/B)."""
    return pd.DataFrame({
        "co_adesao": [1, 2],
        "regiao": ["R1", "R2"],
        "loja": ["L1", "L2"],
        "consultor": ["A", "B"],
        "status": ["EFETIVADA", "PROMESSA"],
    })


def _set_perfil(monkeypatch, perfil):
    monkeypatch.setattr(rls_mod, "_obter_perfil_efetivo", lambda: perfil)


@pytest.mark.unit
class TestDecidirRls:
    """As três saídas da decisão central, e só elas."""

    @pytest.mark.parametrize("role", ["admin", "gestor"])
    def test_perfis_globais(self, monkeypatch, role):
        _set_perfil(monkeypatch, {"perfil": role, "escopo": []})
        decisao = decidir_rls(_COLUNAS_RECONQUISTA)
        assert decisao.global_ is True
        assert decisao.coluna is None

    @pytest.mark.parametrize("role,coluna", [
        ("gerente_comercial", "regiao"),
        ("supervisor", "loja"),
        ("consultor", "consultor"),
    ])
    def test_perfis_com_escopo_recortam(self, monkeypatch, role, coluna):
        _set_perfil(monkeypatch, {"perfil": role, "escopo": ["X"]})
        decisao = decidir_rls(_COLUNAS_RECONQUISTA)
        assert decisao.global_ is False
        assert decisao.coluna == coluna
        assert decisao.escopo == ("X",)

    @pytest.mark.parametrize("perfil", [
        None,
        {},
        {"escopo": ["X"]},
        {"perfil": None, "escopo": ["X"]},
        {"perfil": "desconhecido", "escopo": ["X"]},
        {"perfil": "supervisor"},
        {"perfil": "supervisor", "escopo": []},
        {"perfil": "supervisor", "escopo": None},
    ])
    def test_informacao_faltando_nega(self, monkeypatch, perfil):
        """Fail-closed: nem global, nem coluna para recortar."""
        _set_perfil(monkeypatch, perfil)
        decisao = decidir_rls(_COLUNAS_RECONQUISTA)
        assert decisao.global_ is False
        assert decisao.coluna is None

    def test_escopo_vira_tupla(self, monkeypatch):
        """A decisão não pode carregar a lista mutável do perfil — quem
        recebe não deve conseguir alargar o próprio escopo sem querer."""
        escopo = ["R1"]
        _set_perfil(
            monkeypatch, {"perfil": "gerente_comercial", "escopo": escopo}
        )
        decisao = decidir_rls(_COLUNAS_RECONQUISTA)
        escopo.append("R2")
        assert decisao.escopo == ("R1",)


@pytest.mark.unit
class TestFiltroRlsReconquista:
    @pytest.mark.parametrize("role", ["admin", "gestor"])
    def test_global_nao_recorta(self, monkeypatch, role):
        _set_perfil(monkeypatch, {"perfil": role, "escopo": []})
        assert _filtro_rls_reconquista() is None

    @pytest.mark.parametrize("role,escopo", [
        ("gerente_comercial", ["R1"]),
        ("supervisor", ["L1"]),
        ("consultor", ["A"]),
    ])
    def test_escopo_valido_recorta(self, monkeypatch, clientes, role, escopo):
        _set_perfil(monkeypatch, {"perfil": role, "escopo": escopo})
        recorte = _filtro_rls_reconquista()(clientes)
        assert recorte["co_adesao"].tolist() == [1]

    @pytest.mark.parametrize("perfil", [
        None,
        {"perfil": "supervisor", "escopo": []},
        {"perfil": "supervisor", "escopo": None},
        {"perfil": "desconhecido", "escopo": ["L1"]},
        {"escopo": ["L1"]},
    ])
    def test_sem_informacao_nega_em_vez_de_liberar(
        self, monkeypatch, clientes, perfil
    ):
        """O bug da revisão: cada um destes devolvia a base INTEIRA.

        Note que não é `None` (que o chamador lê como "sem recorte") —
        é uma função que esvazia.
        """
        _set_perfil(monkeypatch, perfil)
        filtro = _filtro_rls_reconquista()
        assert filtro is not None
        recorte = filtro(clientes)
        assert recorte.empty
        assert list(recorte.columns) == list(clientes.columns)

    def test_coluna_de_escopo_ausente_no_frame_nega(
        self, monkeypatch, clientes
    ):
        """Supervisor sobre um frame sem `loja`: sem a coluna não há
        como recortar, então não se entrega nada. Antes, o frame saía
        como veio."""
        _set_perfil(monkeypatch, {"perfil": "supervisor", "escopo": ["L1"]})
        sem_loja = clientes.drop(columns=["loja"])
        recorte = _filtro_rls_reconquista()(sem_loja)
        assert recorte.empty
        assert list(recorte.columns) == list(sem_loja.columns)

    def test_escopo_fora_da_base_nao_traz_nada(self, monkeypatch, clientes):
        _set_perfil(
            monkeypatch, {"perfil": "supervisor", "escopo": ["L_INEXISTENTE"]}
        )
        assert _filtro_rls_reconquista()(clientes).empty

    def test_frame_vazio_e_none_passam_intactos(self, monkeypatch, clientes):
        """Não há o que negar num frame que já não tem linha; `None` é
        chave ausente no dict de dados e segue `None`."""
        _set_perfil(monkeypatch, {"perfil": "supervisor", "escopo": ["L1"]})
        filtro = _filtro_rls_reconquista()
        vazio = clientes.iloc[0:0]
        assert filtro(vazio).empty
        assert filtro(None) is None

    def test_nao_muta_o_frame_de_entrada(self, monkeypatch, clientes):
        _set_perfil(monkeypatch, {"perfil": "supervisor", "escopo": ["L1"]})
        _filtro_rls_reconquista()(clientes)
        assert len(clientes) == 2


@pytest.mark.unit
class TestFiltrarRlsReconquista:
    """``_filtrar_rls_reconquista`` — o dict inteiro dos três recortes
    mensais (`clientes`, `clientes_ant`, `clientes_prox`)."""

    def _dados(self, clientes):
        return {
            "ref_mes": 8,
            "ref_ano": 2026,
            "clientes": clientes,
            "clientes_ant": clientes,
            "clientes_prox": clientes,
        }

    def test_recorta_os_tres_cortes(self, monkeypatch, clientes):
        _set_perfil(monkeypatch, {"perfil": "supervisor", "escopo": ["L1"]})
        out = _filtrar_rls_reconquista(self._dados(clientes))
        for chave in ("clientes", "clientes_ant", "clientes_prox"):
            assert out[chave]["co_adesao"].tolist() == [1], chave
        # Metadados do período não são tocados.
        assert out["ref_mes"] == 8
        assert out["ref_ano"] == 2026

    def test_perfil_sem_escopo_esvazia_os_tres(self, monkeypatch, clientes):
        _set_perfil(monkeypatch, {"perfil": "supervisor", "escopo": []})
        out = _filtrar_rls_reconquista(self._dados(clientes))
        for chave in ("clientes", "clientes_ant", "clientes_prox"):
            assert out[chave].empty, chave

    @pytest.mark.parametrize("role", ["admin", "gestor"])
    def test_global_devolve_o_dict_como_veio(
        self, monkeypatch, clientes, role
    ):
        _set_perfil(monkeypatch, {"perfil": role, "escopo": []})
        dados = self._dados(clientes)
        assert _filtrar_rls_reconquista(dados) is dados
