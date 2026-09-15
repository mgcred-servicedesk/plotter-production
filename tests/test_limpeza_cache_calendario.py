"""
Limpeza de cache após o CRUD de feriados — cirúrgica, e provada.

## O que estava errado

`feriados_mgmt._limpar_cache_feriados` tentava
`_carregar_feriados_cached.clear()`, mas essa função criava o
`@st.cache_data` POR DENTRO e não tinha `.clear()`. O `AttributeError`
era engolido por `except: pass`, e quem de fato fazia o feriado
aparecer era o `st.cache_data.clear()` logo abaixo — que derrubava
contratos, metas e todo o resto de TODOS os usuários.

## O que "cirúrgico" precisa cobrir

Feriado não mora só no cache de feriados. Dias úteis também entram em:

- `carregar_headcount_ponderado` — a RPC `fn_headcount_ponderado`
  (091/096) lê `public.feriados` no SQL;
- `_vinculos_consultores_atual` / `_historico` — `DIAS_ELEGIVEIS` vem
  de `_dias_uteis_competencia`.

`TestCatracaCachesDeCalendario` deriva essa lista do código e das
migrations, para que um cache novo dependente de feriado não fique
desatualizado pelo TTL em silêncio.

Os KPIs em `session_state` são tratados à parte, pela revisão da chave
(`tests/test_kpis_gerais.py::TestCalendarioNaRevisao`).
"""
import ast
import inspect
import re
from pathlib import Path

import pandas as pd
import pytest
import streamlit as st

import src.shared.dias_uteis as du
from src.dashboard import feriados_mgmt, loaders

_MIGRATIONS = Path(__file__).resolve().parent.parent / "database" / "migrations"


@pytest.fixture(autouse=True)
def _cache_limpo():
    st.cache_data.clear()
    yield
    st.cache_data.clear()


@pytest.mark.unit
class TestLimparCacheFeriados:
    def test_refaz_a_consulta(self, monkeypatch):
        chamadas = []
        monkeypatch.setattr(
            du, "carregar_feriados_supabase",
            lambda mes, ano: chamadas.append((mes, ano)) or set(),
        )
        du._carregar_feriados_cached(9, 2026)
        du._carregar_feriados_cached(9, 2026)
        assert len(chamadas) == 1, "a segunda chamada deveria ser cache hit"

        du.limpar_cache_feriados()
        du._carregar_feriados_cached(9, 2026)
        assert len(chamadas) == 2

    def test_nao_derruba_os_outros_caches(self, monkeypatch):
        """É o ponto da mudança: um feriado não pode custar a recarga
        de contratos e metas de todo mundo."""
        monkeypatch.setattr(
            du, "carregar_feriados_supabase", lambda mes, ano: set()
        )
        chamadas = []

        @st.cache_data
        def _outro_cache(x):
            chamadas.append(x)
            return x

        _outro_cache(1)
        du.limpar_cache_feriados()
        _outro_cache(1)
        assert len(chamadas) == 1


@pytest.mark.unit
class TestLimparCachesDeCalendario:
    def test_recarrega_headcount_e_vinculos(self, monkeypatch):
        rpcs = []
        fetches = []

        class _Rpc:
            def execute(self):
                return type("R", (), {"data": []})()

        class _Cliente:
            def rpc(self, nome, params):
                rpcs.append(nome)
                return _Rpc()

        monkeypatch.setattr(loaders, "_sb", lambda: _Cliente())
        monkeypatch.setattr(
            loaders, "_fetch_vinculos_consultores",
            lambda mes, ano, ate=None: fetches.append((mes, ano))
            or pd.DataFrame(),
        )

        def carregar_tudo():
            loaders.carregar_headcount_ponderado(6, 2026)
            loaders._vinculos_consultores_atual(6, 2026)
            loaders._vinculos_consultores_historico(5, 2026)

        carregar_tudo()
        carregar_tudo()
        assert (len(rpcs), len(fetches)) == (1, 2), "segunda rodada = cache"

        loaders.limpar_caches_de_calendario()
        carregar_tudo()
        assert (len(rpcs), len(fetches)) == (2, 4)


@pytest.mark.unit
class TestCrudDeFeriados:
    def test_limpa_so_o_calendario(self, monkeypatch):
        chamadas = []
        monkeypatch.setattr(
            feriados_mgmt, "limpar_cache_feriados",
            lambda: chamadas.append("feriados"),
        )
        monkeypatch.setattr(
            feriados_mgmt, "limpar_caches_de_calendario",
            lambda: chamadas.append("calendario"),
        )
        monkeypatch.setattr(
            st.cache_data, "clear",
            lambda: chamadas.append("GLOBAL"),
        )

        feriados_mgmt._limpar_cache_feriados()
        assert chamadas == ["feriados", "calendario"]

    def test_falha_na_limpeza_nao_e_engolida(self, monkeypatch):
        """Foi o `except: pass` que escondeu por anos que a limpeza
        cirúrgica nunca rodava."""
        def _quebra():
            raise AttributeError("sem .clear()")

        monkeypatch.setattr(feriados_mgmt, "limpar_cache_feriados", _quebra)
        with pytest.raises(AttributeError):
            feriados_mgmt._limpar_cache_feriados()


def _rpcs_que_leem_feriados() -> set[str]:
    """Funções SQL cuja definição MAIS RECENTE lê ``feriados``.

    Migrations sobrescrevem com ``CREATE OR REPLACE``, então vale a
    última versão de cada função, na ordem numérica dos arquivos.
    """
    padrao = re.compile(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+(?:public\.)?(\w+)\s*\(",
        re.IGNORECASE,
    )
    corpo_mais_recente: dict[str, str] = {}
    for arquivo in sorted(_MIGRATIONS.glob("*.sql")):
        sql = arquivo.read_text(encoding="utf-8")
        cortes = list(padrao.finditer(sql))
        for i, m in enumerate(cortes):
            fim = cortes[i + 1].start() if i + 1 < len(cortes) else len(sql)
            corpo_mais_recente[m.group(1)] = sql[m.end():fim]
    return {
        nome for nome, corpo in corpo_mais_recente.items()
        if re.search(r"\bferiados\b", corpo)
    }


def _caches_de_loaders_que_alcancam_o_calendario() -> set[str]:
    arvore = ast.parse(inspect.getsource(loaders))
    funcoes = {
        n.name: n for n in arvore.body if isinstance(n, ast.FunctionDef)
    }
    rpcs = _rpcs_que_leem_feriados()

    def referencias(f):
        nomes = {n.id for n in ast.walk(f) if isinstance(n, ast.Name)}
        textos = {
            n.value for n in ast.walk(f)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        }
        return nomes, textos

    memo: dict[str, bool] = {}

    def alcanca(nome, pilha=()):
        if nome in memo:
            return memo[nome]
        if nome in pilha:
            return False
        nomes, textos = referencias(funcoes[nome])
        resultado = (
            "carregar_feriados" in nomes
            or bool(textos & rpcs)
            or any(
                alcanca(g, pilha + (nome,))
                for g in nomes & funcoes.keys() if g != nome
            )
        )
        memo[nome] = resultado
        return resultado

    def cacheada(f):
        return any("cache_data" in ast.unparse(d) for d in f.decorator_list)

    return {
        nome for nome, f in funcoes.items() if cacheada(f) and alcanca(nome)
    }


@pytest.mark.unit
class TestCatracaCachesDeCalendario:
    def test_rpcs_que_leem_feriados_incluem_o_headcount(self):
        """Sanidade do próprio detector: se ele não acha a 091, a
        catraca abaixo passaria vazia."""
        assert "fn_headcount_ponderado" in _rpcs_que_leem_feriados()

    def test_todo_cache_dependente_de_feriado_e_limpo_no_crud(self):
        """Cache de ``loaders`` que alcança ``carregar_feriados`` ou uma
        RPC que lê ``feriados`` precisa estar em
        ``CACHES_DE_CALENDARIO`` — senão o feriado cadastrado leva o TTL
        inteiro para chegar nele."""
        registrados = {f.__name__ for f in loaders.CACHES_DE_CALENDARIO}
        assert _caches_de_loaders_que_alcancam_o_calendario() == registrados
