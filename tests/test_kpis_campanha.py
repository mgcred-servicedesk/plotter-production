"""Campanha Semestral 2026-H2 — regras de elegibilidade, ranking e ritmo.

## O que esta suite protege

A campanha tem meta propria (R$ 75 mi em VALOR), recorte proprio de
produtos e criterio proprio de desempate. Nada disso existe no
dashboard de vendas, entao nao ha outra suite que pegue uma regressao
aqui.

Os dois pontos onde o numero cala em vez de gritar:

1. **Elegibilidade.** SAQUE fora, Super Conta dentro (como CNC). Um
   erro aqui move a apuracao em milhoes sem nenhum erro na tela.
2. **Dependencia do fallback de categoria.** ANT. DE BENEF. e CLT
   chegam da view SEM `categoria_codigo` (o ETL zera `categoria_id`
   quando a planilha renomeia o tipo — migration 061). Em 16/09/2026
   eram 27% dos contratos da janela e R$ 4,19 mi. Se o fallback deixar
   de rodar antes da campanha, duas das cinco familias somem.
   `TestDependenciaDoFallback` e a catraca disso.

## O frame desta suite

Uma linha por familia elegivel, mais as exclusoes:

| cat             | familia        | elegivel? |
|-----------------|----------------|-----------|
| CNC             | CNC            | sim       |
| SUPER_CONTA     | CNC            | sim       |
| CONSIG_PRIV     | CLT            | sim       |
| CONSIG_BMG      | Consignado     | sim       |
| PORTABILIDADE   | Consignado     | sim       |
| ANT_BENEF       | Ant. de Benef. | sim       |
| FGTS            | FGTS           | sim       |
| SAQUE           | —              | **nao**   |
| CNC_13          | —              | **nao**   |
"""

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

import src.dashboard.pages.campanhas as campanhas_page
from src.dashboard.pages.campanhas import assets_da_campanha

from src.dashboard.kpis.campanha import (
    CAMPANHAS,
    SEMESTRAL_2026H2 as CAMP,
    Campanha,
    COLUNA_PREMIADO,
    Condicao,
    apurar,
    apurar_por_familia,
    campanha_padrao,
    contemplacao,
    marcar_contemplados,
    campanha_por_slug,
    filtrar_elegiveis,
    filtrar_janela,
    preparar,
    ranking,
    ritmo,
    rotulo_desempate,
)

CAMPANHA_INICIO = CAMP.inicio
CAMPANHA_FIM = CAMP.fim
META_VALOR = CAMP.meta_valor
CATEGORIAS_ELEGIVEIS = CAMP.categorias_elegiveis
CATEGORIAS_DESEMPATE = CAMP.categorias_desempate
COL_DESEMPATE = rotulo_desempate(CAMP)

_CATS = [
    "CNC",
    "SUPER_CONTA",
    "CONSIG_PRIV",
    "CONSIG_BMG",
    "PORTABILIDADE",
    "ANT_BENEF",
    "FGTS",
    "SAQUE",
    "CNC_13",
]


def _com_meta(meta: float) -> Campanha:
    """A campanha de sempre, so que com outra meta.

    ``apurar`` le a meta da campanha (nao ha mais parametro ``meta``):
    testar atingimento exige uma campanha com meta redonda.
    """
    return replace(CAMP, meta_valor=meta)


def _frame(**extra) -> pd.DataFrame:
    n = len(_CATS)
    base = {
        "categoria_codigo": list(_CATS),
        "VALOR": [100.0] * n,
        "pontos": [10.0] * n,
        "CONSULTOR": [f"C{i}" for i in range(n)],
        "LOJA": ["L1"] * n,
        "DATA": [pd.Timestamp("2026-08-15")] * n,
    }
    base.update(extra)
    return pd.DataFrame(base)


# ══════════════════════════════════════════════════════
# Elegibilidade
# ══════════════════════════════════════════════════════


class TestElegibilidade:
    def test_saque_fica_de_fora(self):
        """SAQUE de cartao foi excluido explicitamente pelo usuario."""
        assert "SAQUE" not in CATEGORIAS_ELEGIVEIS
        assert "SAQUE_BENEFICIO" not in CATEGORIAS_ELEGIVEIS
        out = filtrar_elegiveis(_frame(), CAMP)
        assert "SAQUE" not in set(out["categoria_codigo"])

    def test_super_conta_conta_como_cnc(self):
        """Decisao do usuario (09/2026): R$ 3,73 mi dependiam disso."""
        assert "SUPER_CONTA" in CATEGORIAS_ELEGIVEIS
        assert "SUPER_CONTA" in CATEGORIAS_DESEMPATE

    def test_cnc_13_nao_entra_sem_decisao(self):
        """CNC_13 e categoria propria — nao foi nomeada na campanha.

        13º e produto de nov/dez, DENTRO da janela. Este teste falha de
        proposito no dia em que alguem incluir CNC_13 sem registrar a
        decisao, forcando a conversa em vez do commit silencioso.
        """
        assert "CNC_13" not in CATEGORIAS_ELEGIVEIS

    def test_as_cinco_familias_entram(self):
        out = filtrar_elegiveis(_frame(), CAMP)
        assert set(out["categoria_codigo"]) == {
            "CNC",
            "SUPER_CONTA",
            "CONSIG_PRIV",
            "CONSIG_BMG",
            "PORTABILIDADE",
            "ANT_BENEF",
            "FGTS",
        }

    def test_frame_vazio_nao_quebra(self):
        assert filtrar_elegiveis(pd.DataFrame(), CAMP).empty

    def test_sem_coluna_categoria_devolve_vazio(self):
        """Sem `categoria_codigo` nao da para afirmar elegibilidade."""
        df = pd.DataFrame({"VALOR": [1.0]})
        assert filtrar_elegiveis(df, CAMP).empty


class TestDependenciaDoFallback:
    """ANT. DE BENEF. e CLT so existem na campanha via fallback.

    Simula o que a view entrega crua: `categoria_codigo` nula nessas
    duas familias. Se alguem remover `_preencher_categoria_fallback` do
    caminho da campanha, a apuracao cai ~19% em silencio — este teste e
    o que grita.
    """

    def test_categoria_nula_nao_e_elegivel(self):
        df = pd.DataFrame(
            {
                "categoria_codigo": [None, None],
                "VALOR": [1000.0, 2000.0],
                "pontos": [1.0, 1.0],
                "DATA": [pd.Timestamp("2026-08-15")] * 2,
            }
        )
        assert filtrar_elegiveis(df, CAMP).empty
        assert apurar(preparar(df, CAMP), CAMP)["valor"] == 0.0

    def test_com_fallback_aplicado_entram(self):
        df = pd.DataFrame(
            {
                "categoria_codigo": ["ANT_BENEF", "CONSIG_PRIV"],
                "VALOR": [1000.0, 2000.0],
                "pontos": [1.0, 1.0],
                "DATA": [pd.Timestamp("2026-08-15")] * 2,
            }
        )
        assert apurar(preparar(df, CAMP), CAMP)["valor"] == 3000.0


# ══════════════════════════════════════════════════════
# Janela
# ══════════════════════════════════════════════════════


class TestJanela:
    @pytest.mark.parametrize(
        "dia,dentro",
        [
            ("2026-06-30", False),
            ("2026-07-01", True),   # limite inferior inclusivo
            ("2026-09-15", True),
            ("2026-12-31", True),   # limite superior inclusivo
            ("2027-01-01", False),
        ],
    )
    def test_limites_inclusivos(self, dia, dentro):
        df = _frame(
            categoria_codigo=["CNC"],
            VALOR=[100.0],
            pontos=[1.0],
            CONSULTOR=["C1"],
            LOJA=["L1"],
            DATA=[pd.Timestamp(dia)],
        )
        assert (not filtrar_janela(df, CAMP).empty) is dentro

    def test_data_nula_sai(self):
        """Sem data nao da para afirmar que foi paga na janela."""
        df = _frame(
            categoria_codigo=["CNC"],
            VALOR=[100.0],
            pontos=[1.0],
            CONSULTOR=["C1"],
            LOJA=["L1"],
            DATA=[pd.NaT],
        )
        assert filtrar_janela(df, CAMP).empty


# ══════════════════════════════════════════════════════
# Apuracao
# ══════════════════════════════════════════════════════


class TestApuracao:
    def test_soma_so_elegiveis(self):
        """7 elegiveis x 100 = 700; SAQUE e CNC_13 ficam fora."""
        assert apurar(preparar(_frame(), CAMP), CAMP)["valor"] == 700.0

    def test_atingimento_e_falta(self):
        ap = apurar(preparar(_frame(), CAMP), _com_meta(1000.0))
        assert ap["valor"] == 700.0
        assert ap["atingimento"] == pytest.approx(0.7)
        assert ap["falta"] == pytest.approx(300.0)

    def test_falta_nunca_negativa(self):
        ap = apurar(preparar(_frame(), CAMP), _com_meta(100.0))
        assert ap["falta"] == 0.0

    def test_valor_cnc_soma_cnc_e_super_conta(self):
        assert apurar(preparar(_frame(), CAMP), CAMP)["valor_cnc"] == 200.0

    def test_meta_default_e_75_milhoes(self):
        assert META_VALOR == 75_000_000.0

    def test_por_familia_soma_o_total(self):
        df = preparar(_frame(), CAMP)
        fam = apurar_por_familia(df, CAMP)
        assert fam["Valor"].sum() == apurar(df, CAMP)["valor"]
        assert fam["% do Total"].sum() == pytest.approx(100.0)

    def test_por_familia_mostra_familia_zerada(self):
        """Familia sem venda aparece zerada, nao some."""
        df = preparar(_frame(categoria_codigo=["CNC"] + _CATS[1:]), CAMP)
        fam = apurar_por_familia(df, CAMP)
        assert len(fam) == 5
        assert "FGTS" in set(fam["Família"])


# ══════════════════════════════════════════════════════
# Ranking
# ══════════════════════════════════════════════════════


class TestRanking:
    def test_ordena_por_pontos(self):
        df = pd.DataFrame(
            {
                "categoria_codigo": ["CNC"] * 3,
                "VALOR": [10.0, 10.0, 10.0],
                "pontos": [5.0, 30.0, 20.0],
                "CONSULTOR": ["A", "B", "C"],
                "DATA": [pd.Timestamp("2026-08-01")] * 3,
            }
        )
        out = ranking(preparar(df, CAMP), "CONSULTOR", CAMP)
        assert out["CONSULTOR"].tolist() == ["B", "C", "A"]
        assert out["#"].tolist() == [1, 2, 3]

    def test_desempate_por_producao_cnc(self):
        """Pontos iguais: ganha quem produziu mais CNC.

        A tem mais VALOR total, mas B tem mais CNC. O criterio da
        campanha e CNC — B vence.
        """
        df = pd.DataFrame(
            {
                "categoria_codigo": ["FGTS", "CNC", "CNC", "FGTS"],
                "VALOR": [900.0, 100.0, 500.0, 500.0],
                "pontos": [10.0, 10.0, 10.0, 10.0],
                "CONSULTOR": ["A", "A", "B", "B"],
                "DATA": [pd.Timestamp("2026-08-01")] * 4,
            }
        )
        out = ranking(preparar(df, CAMP), "CONSULTOR", CAMP)
        assert out["CONSULTOR"].tolist() == ["B", "A"]
        assert out.loc[0, COL_DESEMPATE] == 500.0
        assert out.loc[1, COL_DESEMPATE] == 100.0

    def test_super_conta_vale_no_desempate(self):
        """B so ganha porque Super Conta conta como CNC."""
        df = pd.DataFrame(
            {
                "categoria_codigo": ["CNC", "SUPER_CONTA"],
                "VALOR": [100.0, 500.0],
                "pontos": [10.0, 10.0],
                "CONSULTOR": ["A", "B"],
                "DATA": [pd.Timestamp("2026-08-01")] * 2,
            }
        )
        out = ranking(preparar(df, CAMP), "CONSULTOR", CAMP)
        assert out["CONSULTOR"].tolist() == ["B", "A"]

    def test_empate_real_divide_posicao(self):
        """Empate nos DOIS criterios nao inventa vencedor."""
        df = pd.DataFrame(
            {
                "categoria_codigo": ["CNC", "CNC"],
                "VALOR": [100.0, 100.0],
                "pontos": [10.0, 10.0],
                "CONSULTOR": ["A", "B"],
                "DATA": [pd.Timestamp("2026-08-01")] * 2,
            }
        )
        assert ranking(preparar(df, CAMP), "CONSULTOR", CAMP)["#"].tolist() == [1, 1]

    def test_ranking_de_loja(self):
        df = pd.DataFrame(
            {
                "categoria_codigo": ["CNC", "CNC"],
                "VALOR": [100.0, 300.0],
                "pontos": [10.0, 30.0],
                "LOJA": ["L1", "L2"],
                "DATA": [pd.Timestamp("2026-08-01")] * 2,
            }
        )
        out = ranking(preparar(df, CAMP), "LOJA", CAMP)
        assert out["LOJA"].tolist() == ["L2", "L1"]

    def test_top_n(self):
        assert len(ranking(preparar(_frame(), CAMP), "CONSULTOR", CAMP, top=3)) == 3

    def test_vazio_preserva_schema(self):
        out = ranking(pd.DataFrame(), "CONSULTOR", CAMP)
        assert out.empty
        assert "Pontos" in out.columns


# ══════════════════════════════════════════════════════
# Ritmo
# ══════════════════════════════════════════════════════


class TestRitmo:
    def test_janela_tem_184_dias(self):
        r = ritmo({"valor": 0.0, "meta": META_VALOR}, CAMP, date(2026, 7, 1))
        assert r["dias_total"] == 184  # jul..dez/2026

    def test_primeiro_dia_conta_como_um(self):
        r = ritmo({"valor": 0.0, "meta": META_VALOR}, CAMP, date(2026, 7, 1))
        assert r["dias_decorridos"] == 1
        assert r["dias_restantes"] == 183

    def test_antes_do_inicio_nao_tem_dia_decorrido(self):
        r = ritmo({"valor": 0.0, "meta": META_VALOR}, CAMP, date(2026, 6, 1))
        assert r["dias_decorridos"] == 0
        assert r["ritmo_dia"] == 0.0

    def test_depois_do_fim_satura(self):
        r = ritmo({"valor": 0.0, "meta": META_VALOR}, CAMP, date(2027, 3, 1))
        assert r["dias_decorridos"] == r["dias_total"]
        assert r["dias_restantes"] == 0

    def test_projecao_linear(self):
        """Metade do tempo com metade da meta projeta a meta cheia."""
        meio = CAMPANHA_INICIO + timedelta(days=91)
        r = ritmo({"valor": META_VALOR / 2, "meta": META_VALOR}, CAMP, meio)
        assert r["projecao_vs_meta"] == pytest.approx(1.0, rel=0.02)

    def test_necessario_por_dia(self):
        r = ritmo(
            {"valor": 0.0, "meta": 184.0}, CAMP, date(2026, 7, 1)
        )
        assert r["necessario_dia"] == pytest.approx(184.0 / 183)

    def test_meta_batida_nao_pede_mais_por_dia(self):
        r = ritmo(
            {"valor": META_VALOR * 2, "meta": META_VALOR},
            CAMP,
            date(2026, 9, 1),
        )
        assert r["necessario_dia"] == 0.0


# ══════════════════════════════════════════════════════
# Registro de campanhas
# ══════════════════════════════════════════════════════


class TestRegistro:
    """O registro e a fonte unica: campanha nova = entrada nova."""

    def test_slugs_sao_unicos(self):
        """Slug duplicado colidiria em session_state e na pasta de arte."""
        slugs = [c.slug for c in CAMPANHAS]
        assert len(slugs) == len(set(slugs))

    def test_busca_por_slug(self):
        assert campanha_por_slug(CAMP.slug) is CAMP
        assert campanha_por_slug("nao-existe") is None

    def test_padrao_prefere_a_vigente(self):
        """Com o semestre em curso, a padrao e a vigente."""
        assert campanha_padrao(date(2026, 9, 16)) is CAMP

    def test_padrao_fora_da_vigencia_nao_quebra(self):
        assert campanha_padrao(date(2030, 1, 1)) is not None

    def test_desempate_precisa_existir_nas_familias(self):
        """Desempate orfao daria ranking sem criterio, em silencio."""
        with pytest.raises(ValueError, match="familia_desempate"):
            replace(CAMP, familia_desempate="INEXISTENTE")

    def test_fim_antes_do_inicio_e_recusado(self):
        with pytest.raises(ValueError, match="fim anterior"):
            replace(CAMP, inicio=date(2026, 12, 1), fim=date(2026, 7, 1))

    def test_campanha_e_imutavel(self):
        """Campanha em curso nao muda de regra no meio."""
        with pytest.raises(Exception):
            CAMP.meta_valor = 1.0

    def test_rotulo_do_desempate_segue_a_familia(self):
        assert rotulo_desempate(CAMP) == "CNC (desempate)"
        outra = replace(CAMP, familia_desempate="FGTS")
        assert rotulo_desempate(outra) == "FGTS (desempate)"

    def test_campanha_alternativa_muda_a_elegibilidade(self):
        """Prova que a regra vem da campanha, nao de constante global.

        ``condicoes=()`` nao e detalhe: as da CAMP apontam para CNC e
        CLT, que somem quando as familias sao trocadas — e a guarda de
        ``__post_init__`` recusa condicao orfa.
        """
        so_fgts = replace(
            CAMP,
            familias={"FGTS": ("FGTS",)},
            familia_desempate="FGTS",
            condicoes=(),
        )
        out = filtrar_elegiveis(_frame(), so_fgts)
        assert set(out["categoria_codigo"]) == {"FGTS"}
        assert apurar(preparar(_frame(), so_fgts), so_fgts)["valor"] == 100.0


# ══════════════════════════════════════════════════════
# Assets da campanha
# ══════════════════════════════════════════════════════


class TestAssets:
    """Arte e ilustracao: a ausencia dela nunca derruba a apuracao."""

    def test_pasta_inexistente_devolve_vazio(self):
        assert assets_da_campanha("campanha-que-nao-existe", "hero") == []

    def test_descobre_por_prefixo_em_ordem(self, tmp_path, monkeypatch):
        pasta = tmp_path / "minha-campanha"
        pasta.mkdir()
        for nome in ("hero.png", "rodape-2.png", "rodape-1.png", "leia.txt"):
            (pasta / nome).touch()
        monkeypatch.setattr(campanhas_page, "_RAIZ_ASSETS", tmp_path)

        heros = assets_da_campanha("minha-campanha", "hero")
        assert [p.name for p in heros] == ["hero.png"]

        rodapes = assets_da_campanha("minha-campanha", "rodape")
        assert [p.name for p in rodapes] == ["rodape-1.png", "rodape-2.png"]

    def test_ignora_extensao_nao_suportada(self, tmp_path, monkeypatch):
        pasta = tmp_path / "c"
        pasta.mkdir()
        (pasta / "hero.pdf").touch()
        (pasta / "hero.png").touch()
        monkeypatch.setattr(campanhas_page, "_RAIZ_ASSETS", tmp_path)
        achados = assets_da_campanha("c", "hero")
        assert [p.name for p in achados] == ["hero.png"]

    def test_pasta_da_campanha_vigente_existe(self):
        """A pasta precisa existir para o usuario soltar a arte nela."""
        assert (Path("assets/campanhas") / CAMP.slug).is_dir()


# ══════════════════════════════════════════════════════
# CSS dos cards
# ══════════════════════════════════════════════════════


class TestCssDosCards:
    """O CSS que iguala a altura dos cards precisa ficar NA campanha.

    Sem escopo, `[data-testid="stMetric"] { height: 100% }` vale para o
    app inteiro e mexe em Vendas e Pontuacao junto. Medido com
    Playwright: fora do container o degrau 93/118 se mantem; dentro,
    118/118/118/118.
    """

    def test_toda_regra_e_escopada(self):
        corpo = campanhas_page._CSS_CARDS
        corpo = corpo[corpo.index("<style>") + 7: corpo.index("</style>")]
        seletores = [
            linha.strip()
            for bloco in corpo.split("}")
            for linha in bloco.split("{")[0].split(",")
            if linha.strip()
        ]
        assert seletores, "CSS vazio — o teste nao esta lendo as regras"
        for sel in seletores:
            assert sel.startswith(f".st-key-{campanhas_page._CHAVE_CARDS}"), (
                f"seletor sem escopo da campanha: {sel!r}"
            )

    def test_chave_bate_com_a_classe_usada_no_css(self):
        assert (
            f".st-key-{campanhas_page._CHAVE_CARDS}"
            in campanhas_page._CSS_CARDS
        )


# ══════════════════════════════════════════════════════
# Condicoes de premiacao (cascata)
# ══════════════════════════════════════════════════════


def _producao(cnc=0.0, clt=0.0, outros=0.0) -> pd.DataFrame:
    """Frame com producao dirigida por familia, dentro da janela."""
    return pd.DataFrame(
        {
            "categoria_codigo": ["CNC", "CONSIG_PRIV", "CONSIG_BMG"],
            "VALOR": [cnc, clt, outros],
            "pontos": [0.0, 0.0, 0.0],
            "CONSULTOR": ["A", "B", "C"],
            "LOJA": ["L1", "L2", "L3"],
            "DATA": [pd.Timestamp("2026-08-01")] * 3,
        }
    )


class TestCascataDePremiacao:
    """A regra que decide quem recebe — nenhuma outra suite a cobre.

    Degraus (usuario, 09/2026): global R$ 75 mi -> 8c/4l; + CNC
    R$ 23 mi -> 12c/6l; + CLT R$ 7,5 mi -> 16c/8l. **Cumulativos**.
    """

    def test_sem_meta_global_ninguem_e_contemplado(self):
        """Mesmo com CNC e CLT batidos: a global trava tudo."""
        df = preparar(_producao(cnc=23e6, clt=7.5e6, outros=1e6), CAMP)
        r = contemplacao(df, CAMP)
        assert r["consultores"] == 0
        assert r["lojas"] == 0
        assert r["atual"] is None

    def test_so_a_global_da_8_e_4(self):
        df = preparar(_producao(cnc=20e6, clt=5e6, outros=50e6), CAMP)
        r = contemplacao(df, CAMP)
        assert (r["consultores"], r["lojas"]) == (8, 4)

    def test_global_mais_cnc_da_12_e_6(self):
        df = preparar(_producao(cnc=23e6, clt=5e6, outros=47e6), CAMP)
        r = contemplacao(df, CAMP)
        assert (r["consultores"], r["lojas"]) == (12, 6)

    def test_clt_sem_cnc_nao_promove(self):
        """O caso que a cascata existe para impedir."""
        df = preparar(_producao(cnc=20e6, clt=7.5e6, outros=47.5e6), CAMP)
        r = contemplacao(df, CAMP)
        assert (r["consultores"], r["lojas"]) == (8, 4)
        clt = r["degraus"][2]
        assert clt["atingida"] is True     # a meta de CLT foi batida
        assert clt["liberada"] is False    # mas a cascata parou no CNC

    def test_cascata_completa_da_16_e_8(self):
        df = preparar(_producao(cnc=23e6, clt=7.5e6, outros=44.5e6), CAMP)
        r = contemplacao(df, CAMP)
        assert (r["consultores"], r["lojas"]) == (16, 8)
        assert all(d["liberada"] for d in r["degraus"])

    def test_meta_exata_conta_como_atingida(self):
        """>= e nao >: bater a meta na mosca premia."""
        df = preparar(_producao(cnc=23e6, clt=7.5e6, outros=44.5e6), CAMP)
        assert contemplacao(df, CAMP)["degraus"][0]["atingida"] is True

    def test_um_centavo_a_menos_nao_atinge(self):
        df = preparar(_producao(cnc=23e6, clt=7.5e6, outros=44.5e6 - 0.01), CAMP)
        assert contemplacao(df, CAMP)["consultores"] == 0

    def test_escopo_global_soma_todas_as_familias(self):
        df = preparar(_producao(cnc=1e6, clt=2e6, outros=3e6), CAMP)
        assert contemplacao(df, CAMP)["degraus"][0]["realizado"] == 6e6

    def test_escopo_de_familia_nao_soma_as_outras(self):
        df = preparar(_producao(cnc=1e6, clt=2e6, outros=3e6), CAMP)
        degraus = contemplacao(df, CAMP)["degraus"]
        assert degraus[1]["realizado"] == 1e6   # CNC
        assert degraus[2]["realizado"] == 2e6   # CLT

    def test_frame_vazio_nao_contempla(self):
        r = contemplacao(pd.DataFrame(), CAMP)
        assert (r["consultores"], r["lojas"]) == (0, 0)

    def test_campanha_sem_condicoes_nao_contempla(self):
        sem = replace(CAMP, condicoes=())
        r = contemplacao(preparar(_frame(), CAMP), sem)
        assert (r["consultores"], r["lojas"]) == (0, 0)
        assert r["degraus"] == []


class TestGuardasDasCondicoes:
    def test_condicao_para_familia_inexistente_e_recusada(self):
        """Mediria zero e nunca seria atingida — falharia calada."""
        with pytest.raises(ValueError, match="nao esta em familias"):
            replace(
                CAMP,
                condicoes=(Condicao("X", "NAO_EXISTE", 1.0, 1, 1),),
            )

    def test_degrau_que_contempla_menos_que_o_anterior_e_recusado(self):
        with pytest.raises(ValueError, match="cumulativos"):
            replace(
                CAMP,
                condicoes=(
                    Condicao("A", None, 1.0, 8, 4),
                    Condicao("B", "CNC", 2.0, 4, 2),
                ),
            )

    def test_condicao_global_dispensa_familia(self):
        c = replace(CAMP, condicoes=(Condicao("G", None, 1.0, 1, 1),))
        assert c.condicoes[0].familia is None


class TestMarcacaoDeContemplados:
    def _rk(self):
        df = pd.DataFrame(
            {
                "categoria_codigo": ["CNC"] * 4,
                "VALOR": [10.0, 10.0, 10.0, 10.0],
                "pontos": [40.0, 30.0, 20.0, 10.0],
                "CONSULTOR": ["A", "B", "C", "D"],
                "DATA": [pd.Timestamp("2026-08-01")] * 4,
            }
        )
        return ranking(preparar(df, CAMP), "CONSULTOR", CAMP)

    def test_marca_os_n_primeiros(self):
        out = marcar_contemplados(self._rk(), 2)
        assert out[COLUNA_PREMIADO].tolist() == ["Sim", "Sim", "—", "—"]

    def test_zero_vagas_nao_marca_ninguem(self):
        out = marcar_contemplados(self._rk(), 0)
        assert set(out[COLUNA_PREMIADO]) == {"—"}

    def test_empate_na_fronteira_contempla_os_dois(self):
        """Corta por POSICAO densa, nao por linha.

        A e B empatam em pontos E na producao de desempate: dividem a
        posicao 1. Com uma vaga, cortar por linha escolheria um pela
        ordem que o sort deixou por acaso.
        """
        df = pd.DataFrame(
            {
                "categoria_codigo": ["CNC"] * 3,
                "VALOR": [10.0, 10.0, 5.0],
                "pontos": [40.0, 40.0, 10.0],
                "CONSULTOR": ["A", "B", "C"],
                "DATA": [pd.Timestamp("2026-08-01")] * 3,
            }
        )
        out = marcar_contemplados(ranking(preparar(df, CAMP), "CONSULTOR", CAMP), 1)
        assert out["#"].tolist() == [1, 1, 3]
        assert out[COLUNA_PREMIADO].tolist() == ["Sim", "Sim", "—"]

    def test_ranking_vazio_ganha_a_coluna(self):
        out = marcar_contemplados(ranking(pd.DataFrame(), "CONSULTOR", CAMP), 5)
        assert COLUNA_PREMIADO in out.columns
        assert out.empty
