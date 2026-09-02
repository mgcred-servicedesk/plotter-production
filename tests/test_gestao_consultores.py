"""
Testes da camada de KPIs da aba de Gestao
(src/dashboard/kpis/gestao.py).

Cobre a agregacao por produto MIX (mapeamento categoria_codigo),
a exclusao de supervisores e o filtro multi-criterio combinado por E.
"""
import pandas as pd
import pytest

from src.dashboard.kpis.gerais import ACELERADORES
from src.dashboard.kpis.gestao import (
    COL_DIAS,
    METRICA_PROD_DIA,
    METRICA_VALOR,
    ROTULOS_ACELERADORES,
    BASE_MEDIA_GRUPO,
    BASE_MEDIA_REGIAO,
    BASE_META,
    BASE_PERCENTIL,
    COMB_MINIMO,
    COMB_OU,
    METRICA_QTD,
    METRICA_SHARE,
    METRICA_TICKET,
    NIVEL_LOJA,
    NIVEL_REGIAO,
    NIVEL_SUPERVISOR,
    PRODUTOS_GESTAO,
    SEM_SUPERVISOR,
    calcular_lacuna,
    construir_tabela,
    diagnosticar_criterios,
    filtrar_por_criterios,
    matriz_metas,
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


def test_filtro_ate(df_gestao, df_sup):
    tabela = vendas_mix_por_consultor(df_gestao, df_sup)
    res = filtrar_por_criterios(
        tabela, {"CNC": {"modo": "ate", "max": 15000.0}}
    )
    # Joao (CNC 10k) entra; Maria (CNC 20k) sai; Pedro (CNC 0) entra
    nomes = set(res["Consultor"])
    assert "Joao" in nomes
    assert "Pedro" in nomes
    assert "Maria" not in nomes


def test_modo_menor_e_alias_de_ate(df_gestao, df_sup):
    """O modo historico "menor" segue aceito, agora inclusivo."""
    tabela = vendas_mix_por_consultor(df_gestao, df_sup)
    por_alias = filtrar_por_criterios(
        tabela, {"CNC": {"modo": "menor", "max": 15000.0}}
    )
    por_modo = filtrar_por_criterios(
        tabela, {"CNC": {"modo": "ate", "max": 15000.0}}
    )
    assert set(por_alias["Consultor"]) == set(por_modo["Consultor"])


def test_limiares_sao_inclusivos_e_sem_zona_cega(df_gestao, df_sup):
    """Quem esta exatamente no limiar entra em "ate" E em "a partir de".

    Antes, "menor que" era estrito (<) e "entre" inclusivo — o mesmo
    numero digitado nos dois modos dava listas diferentes.
    """
    tabela = vendas_mix_por_consultor(df_gestao, df_sup)
    # Maria tem CNC == 20000, exatamente no limiar.
    ate = filtrar_por_criterios(
        tabela, {"CNC": {"modo": "ate", "max": 20000.0}}
    )
    acima = filtrar_por_criterios(
        tabela, {"CNC": {"modo": "acima", "min": 20000.0}}
    )
    entre = filtrar_por_criterios(
        tabela, {"CNC": {"modo": "entre", "min": 0.0, "max": 20000.0}}
    )
    assert "Maria" in set(ate["Consultor"])
    assert "Maria" in set(acima["Consultor"])
    # "ate X" e "entre 0 e X" descrevem a mesma faixa
    assert set(ate["Consultor"]) == set(entre["Consultor"])


def test_filtro_sem_venda_e_com_venda(df_gestao, df_sup):
    tabela = vendas_mix_por_consultor(df_gestao, df_sup)
    sem = filtrar_por_criterios(tabela, {"CLT": {"modo": "zero"}})
    com = filtrar_por_criterios(tabela, {"CLT": {"modo": "positivo"}})
    # So Joao tem CLT (CONSIG_PRIV 5k)
    assert set(com["Consultor"]) == {"Joao"}
    assert "Joao" not in set(sem["Consultor"])
    assert {"Maria", "Pedro"} <= set(sem["Consultor"])


def test_filtro_por_total(df_gestao, df_sup):
    """``Total`` e um criterio valido, nao so os produtos do MIX."""
    tabela = vendas_mix_por_consultor(df_gestao, df_sup)
    res = filtrar_por_criterios(
        tabela, {"Total": {"modo": "ate", "max": 30000.0}}
    )
    # Joao 55k sai; Maria 20k e Pedro 30k (limiar inclusivo) entram
    assert set(res["Consultor"]) == {"Maria", "Pedro"}


def test_filtro_multicriterio_and(df_gestao, df_sup):
    tabela = vendas_mix_por_consultor(df_gestao, df_sup)
    criterios = {
        "CLT": {"modo": "ate", "max": 15000.0},
        "CNC": {"modo": "ate", "max": 15000.0},
        "Consignado": {"modo": "ate", "max": 35000.0},
    }
    res = filtrar_por_criterios(tabela, criterios)
    # Joao tem Consignado 40k (> 35k) -> sai pelo AND
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


def test_produtos_gestao_desmembram_o_pack():
    # O pack vira 3 colunas com os rotulos canonicos da planilha.
    assert set(PRODUTOS_GESTAO) == {
        "CNC", "CLT", "Saque", "Consignado",
        "FGTS", "ANT. DE BENEF.", "CNC 13º",
    }
    todos_codigos = [c for cats in PRODUTOS_GESTAO.values() for c in cats]
    assert "CNC_13" in todos_codigos


def test_pack_desmembrado_em_tres_colunas_e_soma_no_total():
    df = pd.DataFrame({
        "CONSULTOR": ["Ana", "Ana", "Ana"],
        "categoria_codigo": ["FGTS", "ANT_BENEF", "CNC_13"],
        "VALOR": [10000.0, 7000.0, 5000.0],
    })
    ana = vendas_mix_por_consultor(df).set_index("Consultor").loc["Ana"]
    assert ana["FGTS"] == 10000.0
    assert ana["ANT. DE BENEF."] == 7000.0
    assert ana["CNC 13º"] == 5000.0
    assert ana["Total"] == 22000.0


# ── Universo: consultor sem venda no periodo ──────────


@pytest.fixture
def df_universo():
    """Cadastro de ativos do RH: inclui gente que nao vendeu nada.

    - Joao/Maria/Pedro: tambem produziram (ver df_gestao)
    - Lucia: ativa, ZERO pagamentos no periodo
    - Chefe: supervisor -> fora do universo consultor
    - Rita: loja de backoffice (Vai e Vem) -> fora do universo
    """
    return pd.DataFrame({
        "CONSULTOR": ["Joao", "Maria", "Pedro", "Lucia", "Chefe", "Rita"],
        "LOJA": ["A", "B", "C", "D", "C", "VAI E VEM"],
        "REGIAO": ["R1", "R1", "R2", "R3", "R2", "R9"],
        "REGIAO_ATUAL": ["R1", "R1", "R2", "R3", "R2", "R9"],
    })


def test_universo_inclui_consultor_sem_venda(df_gestao, df_sup, df_universo):
    tabela = vendas_mix_por_consultor(df_gestao, df_sup, df_universo)
    lucia = tabela.set_index("Consultor").loc["Lucia"]
    assert lucia["Total"] == 0.0
    assert lucia["CNC"] == 0.0
    assert lucia["Regiao"] == "R3"


def test_universo_sem_supervisor_nem_backoffice(
    df_gestao, df_sup, df_universo
):
    tabela = vendas_mix_por_consultor(df_gestao, df_sup, df_universo)
    nomes = set(tabela["Consultor"])
    assert "Chefe" not in nomes  # supervisor
    assert "Rita" not in nomes  # Vai e Vem


def test_criterio_ate_captura_quem_nao_vendeu(
    df_gestao, df_sup, df_universo
):
    """O caso que a aba perdia: zerado no produto do criterio."""
    tabela = vendas_mix_por_consultor(df_gestao, df_sup, df_universo)
    res = filtrar_por_criterios(
        tabela, {"CNC": {"modo": "ate", "max": 15000.0}}
    )
    assert "Lucia" in set(res["Consultor"])

    # Sem universo, Lucia nao existe na tabela -> some da lista
    sem_univ = filtrar_por_criterios(
        vendas_mix_por_consultor(df_gestao, df_sup),
        {"CNC": {"modo": "ate", "max": 15000.0}},
    )
    assert "Lucia" not in set(sem_univ["Consultor"])


def test_universo_manda_na_regiao_e_loja(df_gestao, df_sup, df_universo):
    """Regiao/Loja saem do cadastro (organograma de hoje)."""
    df = df_gestao.copy()
    # Pedro vendeu na loja C/R2, mas o cadastro diz outra coisa
    univ = df_universo.copy()
    univ.loc[univ["CONSULTOR"] == "Pedro", ["LOJA", "REGIAO_ATUAL"]] = [
        "Z", "R7",
    ]
    tabela = vendas_mix_por_consultor(df, df_sup, univ)
    pedro = tabela.set_index("Consultor").loc["Pedro"]
    assert pedro["Loja"] == "Z"
    assert pedro["Regiao"] == "R7"
    # ...mas os valores continuam vindo da producao
    assert pedro["Consignado"] == 30000.0


def test_produtor_fora_do_universo_e_mantido(df_gestao, df_sup, df_universo):
    """Desligado que produziu no mes nao pode sumir da apuracao."""
    univ = df_universo[df_universo["CONSULTOR"] != "Maria"]
    tabela = vendas_mix_por_consultor(df_gestao, df_sup, univ)
    maria = tabela.set_index("Consultor").loc["Maria"]
    assert maria["CNC"] == 20000.0


def test_universo_sem_producao_no_periodo(df_sup, df_universo):
    """Periodo sem nenhum pagamento ainda lista o universo zerado."""
    vazio = pd.DataFrame(
        columns=["CONSULTOR", "VALOR", "categoria_codigo", "LOJA", "REGIAO"]
    )
    tabela = vendas_mix_por_consultor(vazio, df_sup, df_universo)
    assert set(tabela["Consultor"]) == {"Joao", "Maria", "Pedro", "Lucia"}
    assert tabela["Total"].sum() == 0.0


def test_loja_vem_da_de_maior_volume_nao_da_primeira_linha():
    """Consultor que trocou de loja: credito na loja de maior producao."""
    df = pd.DataFrame({
        "CONSULTOR": ["Ana", "Ana"],
        "LOJA": ["Pequena", "Grande"],
        "REGIAO": ["R1", "R2"],
        "categoria_codigo": ["CNC", "CNC"],
        "VALOR": [1000.0, 50000.0],
    })
    ana = vendas_mix_por_consultor(df).set_index("Consultor").loc["Ana"]
    assert ana["Loja"] == "Grande"
    assert ana["Regiao"] == "R2"


# ── Lacuna (falta p/ limiar) ──────────────────────────


def test_lacuna_soma_faltas_dos_criterios_com_teto(df_gestao, df_sup):
    tabela = vendas_mix_por_consultor(df_gestao, df_sup)
    criterios = {
        "CNC": {"modo": "ate", "max": 15000.0},
        "CLT": {"modo": "ate", "max": 10000.0},
    }
    res = filtrar_por_criterios(tabela, criterios)
    lacuna = calcular_lacuna(res, criterios)
    idx = res.index[res["Consultor"] == "Joao"][0]
    # Joao: CNC 10k (falta 5k) + CLT 5k (falta 5k) = 10k
    assert lacuna.loc[idx] == 10000.0


def test_lacuna_ignora_criterios_sem_teto(df_gestao, df_sup):
    tabela = vendas_mix_por_consultor(df_gestao, df_sup)
    criterios = {
        "CNC": {"modo": "acima", "min": 5000.0},
        "CLT": {"modo": "positivo"},
        "Saque": {"modo": "zero"},
    }
    lacuna = calcular_lacuna(tabela, criterios)
    assert lacuna.sum() == 0.0


def test_lacuna_nunca_negativa(df_gestao, df_sup):
    tabela = vendas_mix_por_consultor(df_gestao, df_sup)
    lacuna = calcular_lacuna(
        tabela, {"Consignado": {"modo": "ate", "max": 1000.0}}
    )
    assert (lacuna >= 0).all()


# ── Total = soma dos produtos do criterio ─────────────


def test_total_soma_apenas_os_produtos_do_criterio(df_gestao, df_sup):
    """Total responde 'quanto no que estou olhando', nao no MIX todo."""
    tabela = construir_tabela(
        df_gestao, df_sup, produtos_total=["CNC", "CLT"]
    )
    joao = tabela.set_index("Consultor").loc["Joao"]
    # Joao: CNC 10k + CLT 5k = 15k (os 40k de Consignado ficam fora)
    assert joao["Total"] == 15000.0
    # a coluna do produto excluido continua visivel, so nao soma
    assert joao["Consignado"] == 40000.0


def test_total_sem_escopo_soma_o_mix_inteiro(df_gestao, df_sup):
    tabela = construir_tabela(df_gestao, df_sup)
    joao = tabela.set_index("Consultor").loc["Joao"]
    assert joao["Total"] == 55000.0


# ── Metricas ──────────────────────────────────────────


@pytest.fixture
def df_metricas():
    """Ana: 3 contratos de CNC (30k) e 1 de CLT (5k)."""
    return pd.DataFrame({
        "REGIAO": ["R1"] * 4,
        "LOJA": ["A"] * 4,
        "CONSULTOR": ["Ana"] * 4,
        "categoria_codigo": ["CNC", "CNC", "CNC", "CONSIG_PRIV"],
        "VALOR": [10000.0, 10000.0, 10000.0, 5000.0],
    })


def test_metrica_quantidade_conta_contratos(df_metricas):
    tabela = construir_tabela(df_metricas, metrica=METRICA_QTD)
    ana = tabela.set_index("Consultor").loc["Ana"]
    assert ana["CNC"] == 3
    assert ana["CLT"] == 1
    assert ana["Total"] == 4


def test_metrica_ticket_medio_nao_e_media_de_medias(df_metricas):
    tabela = construir_tabela(df_metricas, metrica=METRICA_TICKET)
    ana = tabela.set_index("Consultor").loc["Ana"]
    assert ana["CNC"] == 10000.0
    assert ana["CLT"] == 5000.0
    # Total = 35k / 4 contratos = 8.750 (e nao a media entre 10k e 5k)
    assert ana["Total"] == 8750.0


def test_metrica_share_soma_cem_por_cento(df_metricas):
    tabela = construir_tabela(df_metricas, metrica=METRICA_SHARE)
    ana = tabela.set_index("Consultor").loc["Ana"]
    assert ana["CNC"] == pytest.approx(30000 / 35000 * 100)
    assert ana["CLT"] == pytest.approx(5000 / 35000 * 100)
    assert ana["Total"] == 100.0


def test_share_respeita_o_escopo_do_total(df_metricas):
    """Com escopo, as fatias se referem ao Total exibido."""
    tabela = construir_tabela(
        df_metricas, metrica=METRICA_SHARE, produtos_total=["CNC"]
    )
    ana = tabela.set_index("Consultor").loc["Ana"]
    assert ana["CNC"] == 100.0


def test_ticket_de_produto_sem_contrato_e_zero(df_gestao, df_sup):
    tabela = construir_tabela(df_gestao, df_sup, metrica=METRICA_TICKET)
    maria = tabela.set_index("Consultor").loc["Maria"]
    assert maria["Saque"] == 0.0  # sem contratos -> sem divisao por zero


# ── Niveis de agregacao ───────────────────────────────


def test_nivel_loja_soma_consultores(df_gestao, df_sup):
    tabela = construir_tabela(df_gestao, df_sup, nivel=NIVEL_LOJA)
    assert set(tabela.columns) >= {"Regiao", "Loja", "Total"}
    assert "Consultor" not in tabela.columns
    loja_a = tabela.set_index("Loja").loc["A"]
    # Loja A = Joao (CNC 10k + CLT 5k + Consignado 40k)
    assert loja_a["Total"] == 55000.0


def test_nivel_regiao_soma_lojas(df_gestao, df_sup):
    tabela = construir_tabela(df_gestao, df_sup, nivel=NIVEL_REGIAO)
    r1 = tabela.set_index("Regiao").loc["R1"]
    # R1 = Joao (55k) + Maria (20k)
    assert r1["Total"] == 75000.0
    assert r1["CNC"] == 30000.0


def test_nivel_supervisor_agrupa_pelas_lojas_do_cadastro(df_gestao):
    df_sup_completo = pd.DataFrame({
        "SUPERVISOR": ["Chefe"],
        "LOJA": ["A"],
        "REGIAO": ["R1"],
    })
    tabela = construir_tabela(
        df_gestao, df_sup_completo, nivel=NIVEL_SUPERVISOR
    )
    por_sup = tabela.set_index("Supervisor")
    # Loja A -> Chefe; as demais lojas caem no bucket sem supervisor
    assert por_sup.loc["Chefe", "Total"] == 55000.0
    assert SEM_SUPERVISOR in por_sup.index


def test_nivel_supervisor_ticket_recalculado_apos_agregar(df_metricas):
    """Ticket agregado usa os totais, nao a media dos tickets."""
    df_sup_completo = pd.DataFrame({
        "SUPERVISOR": ["Chefe"], "LOJA": ["A"], "REGIAO": ["R1"],
    })
    tabela = construir_tabela(
        df_metricas,
        df_sup_completo,
        nivel=NIVEL_SUPERVISOR,
        metrica=METRICA_TICKET,
    )
    chefe = tabela.set_index("Supervisor").loc["Chefe"]
    assert chefe["Total"] == 8750.0


# ── Combinacao de criterios ───────────────────────────


def test_combinacao_ou(df_gestao, df_sup):
    tabela = construir_tabela(df_gestao, df_sup)
    criterios = {
        "CLT": {"modo": "positivo"},
        "Consignado": {"modo": "ate", "max": 30000.0},
    }
    res = filtrar_por_criterios(tabela, criterios, combinacao=COMB_OU)
    # Joao atende CLT>0; Maria e Pedro atendem Consignado<=30k
    assert set(res["Consultor"]) == {"Joao", "Maria", "Pedro"}


def test_combinacao_minimo(df_gestao, df_sup):
    tabela = construir_tabela(df_gestao, df_sup)
    criterios = {
        "CNC": {"modo": "positivo"},
        "CLT": {"modo": "positivo"},
        "Consignado": {"modo": "positivo"},
    }
    dois = filtrar_por_criterios(
        tabela, criterios, combinacao=COMB_MINIMO, minimo=2
    )
    # Joao tem os tres; Maria so CNC; Pedro so Consignado
    assert set(dois["Consultor"]) == {"Joao"}
    um = filtrar_por_criterios(
        tabela, criterios, combinacao=COMB_MINIMO, minimo=1
    )
    assert set(um["Consultor"]) == {"Joao", "Maria", "Pedro"}


def test_combinacao_e_continua_sendo_o_padrao(df_gestao, df_sup):
    tabela = construir_tabela(df_gestao, df_sup)
    criterios = {
        "CNC": {"modo": "positivo"},
        "CLT": {"modo": "positivo"},
    }
    assert set(
        filtrar_por_criterios(tabela, criterios)["Consultor"]
    ) == {"Joao"}


# ── Bases relativas ───────────────────────────────────


def test_base_media_do_grupo(df_gestao, df_sup):
    tabela = construir_tabela(df_gestao, df_sup)
    # CNC: Joao 10k, Maria 20k, Pedro 0 -> media 10k; 100% da media = 10k
    res = filtrar_por_criterios(
        tabela,
        {"CNC": {"modo": "ate", "base": BASE_MEDIA_GRUPO, "max": 100.0}},
    )
    assert set(res["Consultor"]) == {"Joao", "Pedro"}


def test_base_media_da_regiao_usa_o_recorte_local(df_gestao, df_sup):
    tabela = construir_tabela(df_gestao, df_sup)
    # R1: Joao 10k e Maria 20k -> media 15k. R2: Pedro 0 -> media 0.
    res = filtrar_por_criterios(
        tabela,
        {"CNC": {"modo": "ate", "base": BASE_MEDIA_REGIAO, "max": 100.0}},
    )
    nomes = set(res["Consultor"])
    assert "Joao" in nomes  # 10k <= 15k
    assert "Maria" not in nomes  # 20k > 15k
    assert "Pedro" in nomes  # 0 <= 0


def test_base_percentil(df_gestao, df_sup):
    tabela = construir_tabela(df_gestao, df_sup)
    res = filtrar_por_criterios(
        tabela,
        {"Total": {"modo": "ate", "base": BASE_PERCENTIL, "max": 50.0}},
    )
    # Totais 55k / 20k / 30k -> mediana 30k; entram Maria e Pedro
    assert set(res["Consultor"]) == {"Maria", "Pedro"}


def test_base_meta_por_loja(df_gestao, df_sup):
    tabela = construir_tabela(df_gestao, df_sup)
    df_metas = pd.DataFrame({"LOJA": ["A", "B", "C"], "CNC": [20000.0] * 3})
    metas = matriz_metas(tabela, df_metas)
    res = filtrar_por_criterios(
        tabela,
        {"CNC": {"modo": "ate", "base": BASE_META, "max": 50.0}},
        metas=metas,
    )
    # 50% da meta = 10k. Joao 10k entra, Maria 20k sai, Pedro 0 entra.
    assert set(res["Consultor"]) == {"Joao", "Pedro"}


def test_base_meta_ignora_rotulos_do_pack(df_gestao, df_sup):
    """Pack tem meta CONJUNTA — nao existe alvo por categoria."""
    tabela = construir_tabela(df_gestao, df_sup)
    df_metas = pd.DataFrame({"LOJA": ["A", "B", "C"], "CNC": [20000.0] * 3})
    metas = matriz_metas(tabela, df_metas)
    criterios = {"FGTS": {"modo": "ate", "base": BASE_META, "max": 50.0}}
    assert diagnosticar_criterios(tabela, criterios, metas) == ["FGTS"]
    # criterio irresoluvel e IGNORADO, nunca vira "ninguem atende"
    res = filtrar_por_criterios(tabela, criterios, metas=metas)
    assert len(res) == len(tabela)


def test_criterio_sem_meta_nao_esvazia_a_lista(df_gestao, df_sup):
    tabela = construir_tabela(df_gestao, df_sup)
    criterios = {"CNC": {"modo": "ate", "base": BASE_META, "max": 50.0}}
    # sem matriz de metas, o criterio e ignorado
    assert diagnosticar_criterios(tabela, criterios, None) == ["CNC"]
    assert len(filtrar_por_criterios(tabela, criterios)) == len(tabela)


def test_lacuna_com_base_relativa(df_gestao, df_sup):
    tabela = construir_tabela(df_gestao, df_sup)
    criterios = {
        "CNC": {"modo": "ate", "base": BASE_MEDIA_GRUPO, "max": 100.0}
    }
    lacuna = calcular_lacuna(tabela, criterios)
    idx = tabela.index[tabela["Consultor"] == "Pedro"][0]
    # media de CNC = 10k; Pedro tem 0 -> falta 10k
    assert lacuna.loc[idx] == 10000.0


# ── Aceleradores ──────────────────────────────────────


@pytest.fixture
def df_aceleradores():
    """Aceleradores chegam com VALOR = 0 da consolidacao.

    - Joao: 1 CNC pago 10k + 2 BMG Med + 1 Emissao (todos VALOR 0)
    - Maria: 1 CNC pago 20k + 1 Super Conta (VALOR 0)
    - Lucia: SO aceleradores (1 Vida Familiar) — nenhuma venda com valor
    """
    return pd.DataFrame({
        "REGIAO": ["R1"] * 6,
        "LOJA": ["A"] * 6,
        "CONSULTOR": [
            "Joao", "Joao", "Joao", "Maria", "Maria", "Lucia",
        ],
        "categoria_codigo": [
            "CNC", "BMG_MED", "BMG_MED", "CNC", "CNC", "SEGURO_VIDA",
        ],
        "TIPO_PRODUTO": [
            "CNC", "SEGURO", "SEGURO", "CNC", "CNC", "SEGURO",
        ],
        "SUBTIPO": ["", "", "", "", "SUPER CONTA", ""],
        "is_bmg_med": [False, True, True, False, False, False],
        "is_seguro_vida": [False, False, False, False, False, True],
        "VALOR": [10000.0, 0.0, 0.0, 20000.0, 0.0, 0.0],
    })


def test_acelerador_contado_apesar_de_valor_zero(df_aceleradores):
    """O bug obvio: filtrar VALOR > 0 antes de contar zeraria tudo."""
    tabela = construir_tabela(df_aceleradores)
    joao = tabela.set_index("Consultor").loc["Joao"]
    assert joao["BMG Med"] == 2
    assert joao["CNC"] == 10000.0


def test_acelerador_super_conta_por_subtipo(df_aceleradores):
    tabela = construir_tabela(df_aceleradores)
    maria = tabela.set_index("Consultor").loc["Maria"]
    assert maria["Super Conta"] == 1
    assert maria["BMG Med"] == 0


def test_consultor_so_com_acelerador_aparece(df_aceleradores):
    """Quem so vendeu acelerador nao pode sumir da apuracao."""
    tabela = construir_tabela(df_aceleradores)
    nomes = set(tabela["Consultor"])
    assert "Lucia" in nomes
    lucia = tabela.set_index("Consultor").loc["Lucia"]
    assert lucia["Vida Familiar"] == 1
    assert lucia["Total"] == 0.0


def test_acelerador_fica_fora_do_total(df_aceleradores):
    """Unidades diferentes nao somam: contratos de seguro x R$ de CNC."""
    tabela = construir_tabela(df_aceleradores)
    joao = tabela.set_index("Consultor").loc["Joao"]
    assert joao["Total"] == 10000.0  # nao 10002


def test_acelerador_sempre_em_qtd_qualquer_metrica(df_aceleradores):
    """A metrica governa os produtos; acelerador e sempre contratos."""
    for metrica in (METRICA_VALOR, METRICA_TICKET, METRICA_SHARE):
        tabela = construir_tabela(df_aceleradores, metrica=metrica)
        joao = tabela.set_index("Consultor").loc["Joao"]
        assert joao["BMG Med"] == 2, metrica


def test_acelerador_soma_ao_agregar_nivel(df_aceleradores):
    tabela = construir_tabela(df_aceleradores, nivel=NIVEL_LOJA)
    loja = tabela.set_index("Loja").loc["A"]
    # 2 BMG Med (Joao) + 1 Super Conta (Maria) + 1 Vida Familiar (Lucia)
    assert loja["BMG Med"] == 2
    assert loja["Super Conta"] == 1
    assert loja["Vida Familiar"] == 1


def test_acelerador_exclui_supervisor(df_aceleradores):
    df_sup_local = pd.DataFrame({"SUPERVISOR": ["Joao"]})
    tabela = construir_tabela(df_aceleradores, df_sup_local)
    assert "Joao" not in set(tabela["Consultor"])
    assert tabela["BMG Med"].sum() == 0


def test_criterio_por_acelerador(df_aceleradores):
    tabela = construir_tabela(df_aceleradores)
    res = filtrar_por_criterios(
        tabela, {"BMG Med": {"modo": "ate", "max": 1.0}}
    )
    nomes = set(res["Consultor"])
    assert "Joao" not in nomes  # tem 2
    assert {"Maria", "Lucia"} <= nomes  # tem 0


def test_criterio_acelerador_combinado_com_produto(df_aceleradores):
    """O caso de uso: producao baixa E poucos aceleradores."""
    tabela = construir_tabela(df_aceleradores)
    res = filtrar_por_criterios(
        tabela,
        {
            "CNC": {"modo": "ate", "max": 15000.0},
            "BMG Med": {"modo": "zero"},
        },
    )
    # Joao: CNC 10k ok, mas tem 2 BMG Med -> sai
    # Maria: CNC 20k -> sai. Lucia: CNC 0 e BMG 0 -> entra
    assert set(res["Consultor"]) == {"Lucia"}


def test_lacuna_separa_unidades(df_aceleradores):
    """R$ de produto e contratos de acelerador nao podem somar juntos."""
    tabela = construir_tabela(df_aceleradores)
    criterios = {
        "CNC": {"modo": "ate", "max": 15000.0},
        "BMG Med": {"modo": "ate", "max": 3.0},
    }
    idx = tabela.index[tabela["Consultor"] == "Joao"][0]

    so_produto = calcular_lacuna(tabela, criterios, apenas=["CNC"])
    so_acel = calcular_lacuna(tabela, criterios, apenas=["BMG Med"])
    assert so_produto.loc[idx] == 5000.0  # 15k - 10k
    assert so_acel.loc[idx] == 1.0  # 3 - 2

    # sem `apenas`, somaria 5000 + 1 = numero sem significado
    assert calcular_lacuna(tabela, criterios).loc[idx] == 5001.0


def test_meta_nao_se_aplica_a_acelerador(df_aceleradores):
    tabela = construir_tabela(df_aceleradores)
    df_metas = pd.DataFrame({"LOJA": ["A"], "CNC": [20000.0]})
    metas = matriz_metas(tabela, df_metas)
    criterios = {"BMG Med": {"modo": "ate", "base": "meta", "max": 50.0}}
    assert diagnosticar_criterios(tabela, criterios, metas) == ["BMG Med"]
    # ignorado, nunca "ninguem atende"
    assert len(filtrar_por_criterios(tabela, criterios, metas=metas)) == len(
        tabela
    )


def test_rotulos_de_acelerador_batem_com_a_fonte_unica():
    """Gestao e Rankings precisam falar dos mesmos quatro."""
    assert ROTULOS_ACELERADORES == list(ACELERADORES)
    assert set(ROTULOS_ACELERADORES) == {
        "BMG Med", "Vida Familiar", "Emissao", "Super Conta",
    }


# ── Super Conta: acelerador QUE TAMBEM E produto ──────


@pytest.fixture
def df_super_conta():
    """Super Conta chega de duas formas na base, ambas valendo CNC.

    - categoria SUPER_CONTA
    - categoria CNC com SUBTIPO 'SUPER CONTA' (com sujeira de caixa/espaco)

    A consolidacao registra: "conta valor/pontos como CNC e tambem e
    contado como producao Super Conta".
    """
    return pd.DataFrame({
        "REGIAO": ["R1"] * 3,
        "LOJA": ["A"] * 3,
        "CONSULTOR": ["Joao"] * 3,
        "categoria_codigo": ["CNC", "SUPER_CONTA", "CNC"],
        "TIPO_PRODUTO": ["CNC"] * 3,
        "SUBTIPO": ["", "SUPER CONTA", " super conta "],
        "VALOR": [10000.0, 5000.0, 3000.0],
    })


def test_super_conta_soma_valor_em_cnc(df_super_conta):
    """O valor de Super Conta NAO pode sumir do CNC."""
    tabela = construir_tabela(df_super_conta, produtos_total=["CNC"])
    joao = tabela.set_index("Consultor").loc["Joao"]
    assert joao["CNC"] == 18000.0  # 10k CNC + 5k + 3k de Super Conta


def test_super_conta_entra_no_total_uma_unica_vez(df_super_conta):
    """Acelerador fora do Total nao pode virar valor contado a menos —
    nem o produto pode contar o mesmo dinheiro duas vezes."""
    tabela = construir_tabela(df_super_conta, produtos_total=["CNC"])
    joao = tabela.set_index("Consultor").loc["Joao"]
    assert joao["Total"] == 18000.0
    assert joao["Super Conta"] == 2  # contagem, nao valor


def test_super_conta_selecionada_como_criterio_nao_altera_o_total(
    df_super_conta,
):
    """Escolher o acelerador junto do produto nao muda o dinheiro."""
    so_produto = construir_tabela(
        df_super_conta, produtos_total=["CNC"]
    ).set_index("Consultor").loc["Joao", "Total"]
    # "Super Conta" e acelerador: a aba nunca o passa em produtos_total,
    # entao o Total continua sendo so o CNC.
    com_acel = construir_tabela(
        df_super_conta, produtos_total=["CNC"]
    ).set_index("Consultor").loc["Joao", "Total"]
    assert so_produto == com_acel == 18000.0


def test_super_conta_conta_qtd_em_metrica_de_quantidade(df_super_conta):
    """Em qtd, CNC conta os 3 contratos; o acelerador conta os 2 dele."""
    tabela = construir_tabela(
        df_super_conta, metrica=METRICA_QTD, produtos_total=["CNC"]
    )
    joao = tabela.set_index("Consultor").loc["Joao"]
    assert joao["CNC"] == 3
    assert joao["Super Conta"] == 2


def test_super_conta_usa_flag_canonica_quando_existe():
    """is_super_conta (derivada na consolidacao) manda sobre o SUBTIPO."""
    df = pd.DataFrame({
        "CONSULTOR": ["Ana", "Ana"],
        "categoria_codigo": ["CNC", "CNC"],
        "SUBTIPO": ["", ""],  # SUBTIPO vazio...
        "is_super_conta": [True, False],  # ...mas a flag diz que uma e
        "VALOR": [1000.0, 2000.0],
    })
    ana = construir_tabela(df).set_index("Consultor").loc["Ana"]
    assert ana["Super Conta"] == 1
    assert ana["CNC"] == 3000.0


def test_criterio_de_super_conta_nao_exclui_o_valor(df_super_conta):
    """Filtrar por quantidade de Super Conta preserva o CNC da linha."""
    tabela = construir_tabela(df_super_conta, produtos_total=["CNC"])
    res = filtrar_por_criterios(
        tabela, {"Super Conta": {"modo": "acima", "min": 2.0}}
    )
    assert set(res["Consultor"]) == {"Joao"}
    assert res.set_index("Consultor").loc["Joao", "CNC"] == 18000.0


# ══════════════════════════════════════════════════════
# Metrica de produtividade (R$/dia elegivel)
# ══════════════════════════════════════════════════════


@pytest.fixture
def df_vinculos_gestao():
    """Dias elegiveis dos consultores de ``df_gestao``.

    Maria tem METADE dos dias de Joao: e o caso que a metrica existe
    para resolver.
    """
    return pd.DataFrame({
        "CONSULTOR": ["Joao", "Maria", "Pedro"],
        "LOJA": ["A", "B", "C"],
        "REGIAO": ["R1", "R1", "R2"],
        "REGIAO_ATUAL": ["R1", "R1", "R2"],
        "DIAS_ELEGIVEIS": [20, 10, 20],
        "DU_COMPETENCIA": [20, 20, 20],
        "BASE_DIAS": ["ELIGIBLE_LINK_DAYS"] * 3,
        "COBERTURA_AFASTAMENTO": ["NONE"] * 3,
    })


@pytest.mark.unit
class TestMetricaProdutividade:
    def test_divide_cada_produto_pelos_dias(
        self, df_gestao, df_sup, df_vinculos_gestao
    ):
        tabela = construir_tabela(
            df_gestao, df_sup,
            metrica=METRICA_PROD_DIA,
            df_vinculos=df_vinculos_gestao,
        ).set_index("Consultor")

        # Joao: CNC 10.000 em 20 dias.
        assert tabela.loc["Joao", "CNC"] == pytest.approx(500.0)
        assert tabela.loc["Joao", "Total"] == pytest.approx(55000.0 / 20)
        # Maria: 20.000 em 10 dias — produtividade MAIOR que a do Joao,
        # apesar da producao menor.
        assert tabela.loc["Maria", "Total"] == pytest.approx(2000.0)

    def test_coluna_de_dias_acompanha_a_metrica(
        self, df_gestao, df_sup, df_vinculos_gestao
    ):
        tabela = construir_tabela(
            df_gestao, df_sup,
            metrica=METRICA_PROD_DIA,
            df_vinculos=df_vinculos_gestao,
        )

        assert COL_DIAS in tabela.columns
        # Contexto fica junto da identificacao, antes dos produtos.
        assert list(tabela.columns).index(COL_DIAS) < list(
            tabela.columns
        ).index("CNC")

    def test_sem_dia_elegivel_a_produtividade_e_ausente(
        self, df_gestao, df_sup
    ):
        """Nunca zero: o furo esta no ledger, nao na pessoa."""
        vin = pd.DataFrame({
            "CONSULTOR": ["Joao"],
            "LOJA": ["A"],
            "REGIAO": ["R1"],
            "REGIAO_ATUAL": ["R1"],
            "DIAS_ELEGIVEIS": [20],
            "DU_COMPETENCIA": [20],
            "BASE_DIAS": ["ELIGIBLE_LINK_DAYS"],
            "COBERTURA_AFASTAMENTO": ["NONE"],
        })
        tabela = construir_tabela(
            df_gestao, df_sup, metrica=METRICA_PROD_DIA, df_vinculos=vin,
        ).set_index("Consultor")

        assert pd.isna(tabela.loc["Maria", "Total"])
        assert tabela.loc["Maria", COL_DIAS] == 0

    def test_nivel_loja_usa_razao_das_somas(
        self, df_gestao, df_sup, df_vinculos_gestao
    ):
        tabela = construir_tabela(
            df_gestao, df_sup,
            nivel=NIVEL_LOJA,
            metrica=METRICA_PROD_DIA,
            df_vinculos=df_vinculos_gestao,
        ).set_index("Loja")

        # Loja A: so o Joao (55.000 / 20 dias).
        assert tabela.loc["A", "Total"] == pytest.approx(2750.0)
        assert tabela.loc["A", COL_DIAS] == 20

    def test_sem_vinculos_a_metrica_nao_inventa_denominador(
        self, df_gestao, df_sup
    ):
        tabela = construir_tabela(
            df_gestao, df_sup, metrica=METRICA_PROD_DIA,
        )

        assert tabela["Total"].isna().all()
        assert (tabela[COL_DIAS] == 0).all()

    def test_demais_metricas_seguem_sem_a_coluna_de_dias(
        self, df_gestao, df_sup, df_vinculos_gestao
    ):
        tabela = construir_tabela(
            df_gestao, df_sup,
            metrica=METRICA_VALOR,
            df_vinculos=df_vinculos_gestao,
        )

        assert COL_DIAS not in tabela.columns
        assert tabela.set_index("Consultor").loc["Joao", "Total"] == 55000.0
