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
