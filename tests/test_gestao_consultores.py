"""
Testes da camada de KPIs da aba de Gestao
(src/dashboard/kpis/gestao.py).

Cobre a agregacao por produto MIX (mapeamento categoria_codigo),
a exclusao de supervisores e o filtro multi-criterio combinado por E.
"""
import pandas as pd
import pytest

from src.dashboard.kpis.gestao import (
    PRODUTOS_GESTAO,
    filtrar_por_criterios,
    vendas_mix_por_consultor,
)


@pytest.fixture
def df_gestao():
    """Pagos com categoria_codigo cobrindo varios produtos MIX.

    - Joao (R1): CNC 10k, CLT (CONSIG_PRIV) 5k, Consignado (CONSIG_BMG) 40k
    - Maria (R1): CNC 20k
    - Pedro (R2): Consignado (CONSIG_ITAU) 30k, linha VALOR=0 (ignorada)
    - Chefe (R2): supervisor que vendeu CNC 1k -> deve ser excluido
    """
    return pd.DataFrame({
        "REGIAO": ["R1", "R1", "R1", "R1", "R2", "R2", "R2"],
        "LOJA": ["A", "A", "A", "B", "C", "C", "C"],
        "CONSULTOR": [
            "Joao", "Joao", "Joao", "Maria", "Pedro", "Pedro", "Chefe",
        ],
        "categoria_codigo": [
            "CNC", "CONSIG_PRIV", "CONSIG_BMG", "CNC",
            "CONSIG_ITAU", "SAQUE", "CNC",
        ],
        "VALOR": [
            10000.0, 5000.0, 40000.0, 20000.0, 30000.0, 0.0, 1000.0,
        ],
    })


@pytest.fixture
def df_sup():
    return pd.DataFrame({"SUPERVISOR": ["Chefe"]})


def test_agrega_valor_por_produto_mix(df_gestao, df_sup):
    tabela = vendas_mix_por_consultor(df_gestao, df_sup)

    joao = tabela.set_index("Consultor").loc["Joao"]
    assert joao["CNC"] == 10000.0
    assert joao["CLT"] == 5000.0  # CONSIG_PRIV -> CLT
    assert joao["Consignado"] == 40000.0  # CONSIG_BMG -> Consignado
    assert joao["Saque"] == 0.0
    assert joao["Total"] == 55000.0


def test_exclui_supervisores(df_gestao, df_sup):
    tabela = vendas_mix_por_consultor(df_gestao, df_sup)
    assert "Chefe" not in set(tabela["Consultor"])


def test_consignado_soma_bancos():
    df = pd.DataFrame({
        "CONSULTOR": ["Ana", "Ana", "Ana"],
        "categoria_codigo": ["CONSIG_BMG", "CONSIG_ITAU", "CONSIG_C6"],
        "VALOR": [10000.0, 15000.0, 5000.0],
    })
    tabela = vendas_mix_por_consultor(df)
    assert tabela.loc[0, "Consignado"] == 30000.0


def test_ignora_valor_zero_e_ordena_por_regiao(df_gestao, df_sup):
    tabela = vendas_mix_por_consultor(df_gestao, df_sup)
    # Pedro tem Saque com VALOR 0 -> nao soma nada em Saque
    pedro = tabela.set_index("Consultor").loc["Pedro"]
    assert pedro["Saque"] == 0.0
    assert pedro["Consignado"] == 30000.0
    # Ordenacao por (Regiao, Consultor)
    assert list(tabela["Regiao"]) == sorted(tabela["Regiao"])


def test_filtro_menor_que(df_gestao, df_sup):
    tabela = vendas_mix_por_consultor(df_gestao, df_sup)
    res = filtrar_por_criterios(
        tabela, {"CNC": {"modo": "menor", "max": 15000.0}}
    )
    # Joao (CNC 10k) entra; Maria (CNC 20k) sai; Pedro (CNC 0) entra
    nomes = set(res["Consultor"])
    assert "Joao" in nomes
    assert "Pedro" in nomes
    assert "Maria" not in nomes


def test_filtro_multicriterio_and(df_gestao, df_sup):
    tabela = vendas_mix_por_consultor(df_gestao, df_sup)
    criterios = {
        "CLT": {"modo": "menor", "max": 15000.0},
        "CNC": {"modo": "menor", "max": 15000.0},
        "Consignado": {"modo": "menor", "max": 35000.0},
    }
    res = filtrar_por_criterios(tabela, criterios)
    # Joao tem Consignado 40k (>= 35k) -> sai pelo AND
    # Pedro: CLT 0, CNC 0, Consignado 30k -> entra
    nomes = set(res["Consultor"])
    assert nomes == {"Pedro"}


def test_filtro_entre(df_gestao, df_sup):
    tabela = vendas_mix_por_consultor(df_gestao, df_sup)
    res = filtrar_por_criterios(
        tabela, {"CNC": {"modo": "entre", "min": 15000.0, "max": 25000.0}}
    )
    assert set(res["Consultor"]) == {"Maria"}


def test_sem_criterios_retorna_tudo(df_gestao, df_sup):
    tabela = vendas_mix_por_consultor(df_gestao, df_sup)
    res = filtrar_por_criterios(tabela, {})
    assert len(res) == len(tabela)


def test_df_vazio_ou_sem_colunas():
    assert vendas_mix_por_consultor(pd.DataFrame()).empty
    df_incompleto = pd.DataFrame({"CONSULTOR": ["X"], "VALOR": [10.0]})
    assert vendas_mix_por_consultor(df_incompleto).empty


def test_produtos_gestao_separam_fgts_ant_ben():
    assert set(PRODUTOS_GESTAO) == {
        "CNC", "CLT", "Saque", "Consignado", "FGTS", "Ant.Ben.",
    }
    # 13o (CNC_13) fica de fora desta visao
    todos_codigos = [c for cats in PRODUTOS_GESTAO.values() for c in cats]
    assert "CNC_13" not in todos_codigos


def test_fgts_e_ant_ben_separados_e_13o_excluido():
    df = pd.DataFrame({
        "CONSULTOR": ["Ana", "Ana", "Ana"],
        "categoria_codigo": ["FGTS", "ANT_BENEF", "CNC_13"],
        "VALOR": [10000.0, 7000.0, 5000.0],
    })
    ana = vendas_mix_por_consultor(df).set_index("Consultor").loc["Ana"]
    assert ana["FGTS"] == 10000.0
    assert ana["Ant.Ben."] == 7000.0
    # 13o nao entra em nenhuma coluna nem no Total
    assert ana["Total"] == 17000.0
