"""
Configuração de fixtures para testes pytest.
"""
import sys
from pathlib import Path

import pytest
import pandas as pd

# Adicionar diretório raiz ao path
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


@pytest.fixture
def sample_vendas_df():
    """DataFrame de vendas de exemplo para testes."""
    return pd.DataFrame({
        'DATA': ['2026-03-01', '2026-03-01', '2026-03-02'],
        'LOJA': ['LOJA A', 'LOJA A', 'LOJA B'],
        'CONSULTOR': ['João', 'Maria', 'Pedro'],
        'TIPO_PRODUTO': ['CNC', 'EMISSAO', 'CNC 13º'],
        'PRODUTO': ['CNC NORMAL', 'CARTÃO BMG', 'CNC 13 SALARIO'],
        'VALOR': [1000.0, 500.0, 800.0]
    })


@pytest.fixture
def sample_metas_df():
    """DataFrame de metas de exemplo para testes."""
    return pd.DataFrame({
        'LOJA': ['LOJA A', 'LOJA B'],
        'META_PRATA': [50000, 40000],
        'META_OURO': [80000, 60000]
    })


@pytest.fixture
def mes_teste():
    """Mês padrão para testes."""
    return 3


@pytest.fixture
def ano_teste():
    """Ano padrão para testes."""
    return 2026


# ──────────────────────────────────────────────────────────────────
# Fixtures para os módulos KPI ativos (src/dashboard/kpis/*)
# ──────────────────────────────────────────────────────────────────


@pytest.fixture
def sem_feriados(monkeypatch):
    """Neutraliza o acesso ao Supabase em ``calcular_dias_uteis``.

    Faz ``carregar_feriados`` retornar conjunto vazio, tornando o
    cálculo de dias úteis determinístico (apenas seg-sex do calendário)
    e sem dependência de banco nos testes.
    """
    import src.shared.dias_uteis as du

    monkeypatch.setattr(du, "carregar_feriados", lambda mes, ano: set())


@pytest.fixture
def sample_categorias_df():
    """Categorias com mapeamento grupo_dashboard → grupo_meta."""
    return pd.DataFrame({
        "grupo_dashboard": ["CNC", "SAQUE", None],
        "grupo_meta": ["CNC", "SAQUE", None],
    })


@pytest.fixture
def sample_metas_produto_df():
    """Metas por grupo_meta (colunas nomeadas como os grupos)."""
    return pd.DataFrame({"CNC": [3000.0], "SAQUE": [2000.0]})


@pytest.fixture
def sample_pagos_produto_df():
    """Contratos pagos com grupo_dashboard e VALOR."""
    return pd.DataFrame({
        "CONSULTOR": ["João", "Maria", "Pedro", "Ana"],
        "grupo_dashboard": ["CNC", "CNC", "SAQUE", "SAQUE"],
        "VALOR": [1000.0, 500.0, 800.0, 0.0],
    })


@pytest.fixture
def sample_supervisores_df():
    """Supervisores a excluir das contagens."""
    return pd.DataFrame({"SUPERVISOR": ["Chefe"]})


@pytest.fixture
def mapa_pontos():
    """categoria_codigo → pontos por real (PTS)."""
    return {"CNC": 1.0, "SAQUE": 2.0, "CONSIG_PRIV": 1.5}


@pytest.fixture
def sample_pontos_df():
    """df de pagos com coluna ``pontos`` já consolidada."""
    return pd.DataFrame({
        "LOJA": ["A", "A", "B"],
        "CONSULTOR": ["João", "Maria", "Pedro"],
        "categoria_codigo": ["CNC", "SAQUE", "CNC"],
        "VALOR": [600.0, 200.0, 0.0],
        "pontos": [600.0, 400.0, 0.0],
    })


@pytest.fixture
def sample_analise_df():
    """Contratos em análise (sem coluna ``pontos`` — calculada na hora)."""
    return pd.DataFrame({
        "categoria_codigo": ["CNC", "SAQUE", "EMISSAO"],
        "VALOR": [1000.0, 500.0, 300.0],
        "conta_pontuacao": [True, True, False],
    })


@pytest.fixture
def df_rank():
    """Vendas com loja/região/consultor/produto para rankings e regiões.

    Loja A → R1 (consultor João); Loja B → R2 (Maria e Pedro).
    A última linha (Pedro/BMG MED) é um acelerador.
    """
    return pd.DataFrame({
        "LOJA":             ["A", "A", "B", "B"],
        "REGIAO":           ["R1", "R1", "R2", "R2"],
        "CONSULTOR":        ["João", "João", "Maria", "Pedro"],
        "grupo_dashboard":  ["CNC", "SAQUE", "CNC", "CNC"],
        "categoria_codigo": ["CNC", "SAQUE", "CNC", "CNC"],
        "VALOR":            [1000.0, 500.0, 2000.0, 300.0],
        "pontos":           [300.0, 100.0, 400.0, 60.0],
        "TIPO_PRODUTO":     ["CNC", "SAQUE", "CNC", "BMG MED"],
        "SUBTIPO":          ["", "", "", ""],
        "is_bmg_med":       [False, False, False, True],
        "is_seguro_vida":   [False, False, False, False],
    })


@pytest.fixture
def df_metas_lojas():
    """Meta Prata por loja (escopo LOJA)."""
    return pd.DataFrame({"LOJA": ["A", "B"], "META_PRATA": [1000.0, 2000.0]})


@pytest.fixture
def categorias_regioes():
    """Categorias com conta_valor (usado por kpis_por_produto_regiao)."""
    return pd.DataFrame({
        "grupo_dashboard": ["CNC", "SAQUE"],
        "grupo_meta": ["CNC", "SAQUE"],
        "conta_valor": [True, True],
    })


@pytest.fixture
def df_metas_produto_lojas():
    """Metas por produto e por loja (escopo LOJA × produto)."""
    return pd.DataFrame({
        "LOJA": ["A", "B"],
        "CNC": [1000.0, 1000.0],
        "SAQUE": [500.0, 500.0],
    })


# ══════════════════════════════════════════════════════
# Duplo de Supabase que PAGINA de verdade
#
# Os duplos antigos ignoravam `.order`/`.limit`/`.gt` e devolviam a
# lista inteira em um `.execute()`. Com isso, um loader sem paginacao
# passava nos testes exatamente como um paginado — que e a razao de o
# truncamento silencioso do item 6 da revisao de 09/2026 nunca ter
# aparecido na suite.
#
# Este duplo respeita o contrato do keyset: ordena pela chave, corta em
# `limit` e aplica `gt` do cursor. Um loader que esqueca de paginar
# recebe SO a primeira pagina — e o teste falha, como deve.
# ══════════════════════════════════════════════════════


class RespostaFakePaginada:
    def __init__(self, data):
        self.data = data


class QueryFakePaginada:
    """Query fluente que honra order/limit/gt e ignora os filtros.

    Os filtros de servidor (`lte`, `or_`, `eq`, ...) sao no-ops de
    proposito: quem monta o cenario ja passa as linhas que o filtro
    deixaria passar. O que este duplo existe para exercitar e a
    PAGINACAO.
    """

    def __init__(self, linhas, chave):
        self._linhas = linhas
        self._chave = chave
        self._limite = None
        self._cursor = None

    def _noop(self, *_a, **_k):
        return self

    select = lte = gte = lt = or_ = eq = neq = in_ = is_ = _noop

    def order(self, coluna, *_a, **_k):
        assert coluna == self._chave, (
            f"paginacao keyset deve ordenar por {self._chave!r}, "
            f"nao {coluna!r} — chave repetida pula linhas entre paginas"
        )
        return self

    def limit(self, n):
        self._limite = n
        return self

    def gt(self, coluna, valor):
        assert coluna == self._chave
        self._cursor = valor
        return self

    def execute(self):
        linhas = sorted(self._linhas, key=lambda r: r[self._chave])
        if self._cursor is not None:
            linhas = [r for r in linhas if r[self._chave] > self._cursor]
        if self._limite is not None:
            linhas = linhas[: self._limite]
        return RespostaFakePaginada(linhas)


class ClienteFakePaginado:
    """Cliente Supabase falso que pagina. Conta as paginas servidas.

    ``paginas`` permite afirmar o custo em requests — o que importa no
    plano Nano: paginar NAO deve acrescentar request enquanto os dados
    couberem em uma pagina.
    """

    def __init__(self, linhas, chave="id", tabela=None):
        self.linhas = linhas
        self.chave = chave
        self.tabela = tabela
        self.paginas = 0

    def table(self, nome):
        if self.tabela is not None:
            assert nome == self.tabela, f"tabela inesperada: {nome}"
        self.paginas += 1
        return QueryFakePaginada(self.linhas, self.chave)
