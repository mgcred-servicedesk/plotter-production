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
    COLUNA_LOJA_CONSULTOR,
    excluir_desligados,
    MARCA_MULTIPLAS_LOJAS,
    COLUNA_MEDIA_DU,
    COLUNA_PREMIADO,
    Condicao,
    apurar,
    apurar_por_familia,
    campanha_padrao,
    contemplacao,
    dias_uteis_campanha,
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

    def test_desempate_por_cnc_e_em_PONTOS_nao_em_valor(self):
        """O teste que separa os dois criterios possiveis.

        Empate no total de pontos. Em CNC, A produziu **mais valor**
        (900 contra 100) e B fez **mais pontos** (9 contra 1). Se o
        desempate fosse por valor, A venceria; sendo por pontos, vence
        B — que e a regra que o usuario confirmou em 16/09/2026.

        Sem valor e pontos discordando, o teste passaria nos dois
        criterios e nao provaria nada.
        """
        df = pd.DataFrame(
            {
                "categoria_codigo": ["CNC", "FGTS", "CNC", "FGTS"],
                "VALOR": [900.0, 100.0, 100.0, 900.0],
                "pontos": [1.0, 9.0, 9.0, 1.0],
                "CONSULTOR": ["A", "A", "B", "B"],
                "DATA": [pd.Timestamp("2026-08-01")] * 4,
            }
        )
        out = ranking(preparar(df, CAMP), "CONSULTOR", CAMP)
        assert out["Pontos"].tolist() == [10.0, 10.0]   # empate no total
        assert out["CONSULTOR"].tolist() == ["B", "A"]
        assert out.loc[0, COL_DESEMPATE] == 9.0   # pontos de CNC, nao 100
        assert out.loc[1, COL_DESEMPATE] == 1.0   # nao 900

    def test_super_conta_vale_no_desempate(self):
        """B so ganha porque Super Conta conta como CNC — em pontos."""
        df = pd.DataFrame(
            {
                "categoria_codigo": ["CNC", "SUPER_CONTA"],
                "VALOR": [100.0, 100.0],
                "pontos": [10.0, 10.0],
                "CONSULTOR": ["A", "B"],
                "DATA": [pd.Timestamp("2026-08-01")] * 2,
            }
        )
        # Empate perfeito: os dois tem 10 pontos, e os 10 sao de CNC
        # (Super Conta inclusa) — dividem a posicao.
        out = ranking(preparar(df, CAMP), "CONSULTOR", CAMP)
        assert out[COL_DESEMPATE].tolist() == [10.0, 10.0]
        assert out["#"].tolist() == [1, 1]

    def test_familia_fora_do_desempate_nao_soma(self):
        """FGTS nao entra no desempate, por mais pontos que tenha."""
        df = pd.DataFrame(
            {
                "categoria_codigo": ["CNC", "FGTS"],
                "VALOR": [10.0, 10.0],
                "pontos": [5.0, 5.0],
                "CONSULTOR": ["A", "B"],
                "DATA": [pd.Timestamp("2026-08-01")] * 2,
            }
        )
        out = ranking(preparar(df, CAMP), "CONSULTOR", CAMP)
        por_nome = dict(zip(out["CONSULTOR"], out[COL_DESEMPATE]))
        assert por_nome["A"] == 5.0
        assert por_nome["B"] == 0.0

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
        assert rotulo_desempate(CAMP) == "CNC (pts, desempate)"
        outra = replace(CAMP, familia_desempate="FGTS")
        assert rotulo_desempate(outra) == "FGTS (pts, desempate)"

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


class TestContratoConfirmadoDaPremiacao:
    """Valores confirmados pelo usuario em 16/09/2026.

    Nao sao detalhe de implementacao: decidem quem recebe premio. Um
    ajuste silencioso aqui muda pagamento, entao ficam pinados.
    """

    def test_os_tres_degraus_na_ordem(self):
        assert [c.rotulo for c in CAMP.condicoes] == [
            "Meta global",
            "Meta de CNC",
            "Meta de CLT",
        ]

    def test_metas_confirmadas(self):
        g, cnc, clt = CAMP.condicoes
        assert (g.familia, g.meta) == (None, 75_000_000.0)
        assert (cnc.familia, cnc.meta) == ("CNC", 23_000_000.0)
        assert (clt.familia, clt.meta) == ("CLT", 7_500_000.0)

    def test_vagas_confirmadas(self):
        assert [(c.consultores, c.lojas) for c in CAMP.condicoes] == [
            (8, 4),
            (12, 6),
            (16, 8),
        ]

    def test_meta_global_bate_com_a_meta_da_campanha(self):
        """A 1a condicao e a meta global — nao pode divergir do termometro."""
        assert CAMP.condicoes[0].meta == CAMP.meta_valor

    def test_bloco_de_44_5_mi_esta_fora_por_ora(self):
        """Consignado + Antecipacao + FGTS nao e degrau (usuario, 16/09).

        Existe na arte e soma 44,5 mi (75 - 23 - 7,5), mas o usuario o
        deixou fora "no momento". Este teste falha se alguem o incluir
        sem registrar a decisao.

        Nota de modelagem: incluir NAO e so acrescentar uma linha —
        `Condicao.familia` aponta para UMA familia, e o bloco abrange
        tres. Exigiria agrupa-las ou permitir varias familias por
        condicao.
        """
        escopos = {c.familia for c in CAMP.condicoes}
        assert "Consignado" not in escopos
        assert "Ant. de Benef." not in escopos
        assert "FGTS" not in escopos
        # E a aritmetica que torna o bloco tentador continua valendo:
        outras = sum(
            c.meta for c in CAMP.condicoes if c.familia is not None
        )
        assert CAMP.meta_valor - outras == 44_500_000.0


class TestLojaDoConsultor:
    """A coluna Loja do ranking de consultores.

    Numa janela de seis meses a pessoa pode ter sido transferida — o
    projeto agrega consultor por NOME justamente para nao fragmentar a
    producao de quem mudou (ver `rls.md`).
    """

    def _df(self, lojas, datas):
        n = len(lojas)
        return pd.DataFrame(
            {
                "categoria_codigo": ["CNC"] * n,
                "VALOR": [100.0] * n,
                "pontos": [10.0] * n,
                "CONSULTOR": ["A"] * n,
                "LOJA": lojas,
                "DATA": [pd.Timestamp(d) for d in datas],
            }
        )

    def test_loja_unica_aparece_limpa(self):
        df = self._df(["L1", "L1"], ["2026-07-01", "2026-08-01"])
        out = ranking(preparar(df, CAMP), "CONSULTOR", CAMP, com_loja=True)
        assert out.loc[0, COLUNA_LOJA_CONSULTOR] == "L1"

    def test_transferido_mostra_a_loja_mais_recente(self):
        """Pagou em L1 em julho e em L2 em setembro -> L2."""
        df = self._df(["L1", "L2"], ["2026-07-01", "2026-09-01"])
        out = ranking(preparar(df, CAMP), "CONSULTOR", CAMP, com_loja=True)
        assert out.loc[0, COLUNA_LOJA_CONSULTOR].startswith("L2")

    def test_transferido_sai_marcado(self):
        """O asterisco avisa que houve mais de uma loja na janela.

        Sem ele a coluna afirmaria uma lotacao unica que nao existiu.
        """
        df = self._df(["L1", "L2"], ["2026-07-01", "2026-09-01"])
        out = ranking(preparar(df, CAMP), "CONSULTOR", CAMP, com_loja=True)
        assert out.loc[0, COLUNA_LOJA_CONSULTOR] == "L2 *"

    def test_ordem_das_linhas_nao_decide_a_loja(self):
        """Mais recente e por DATA, nao pela ordem em que veio o frame."""
        df = self._df(["L2", "L1"], ["2026-09-01", "2026-07-01"])
        out = ranking(preparar(df, CAMP), "CONSULTOR", CAMP, com_loja=True)
        assert out.loc[0, COLUNA_LOJA_CONSULTOR] == "L2 *"

    def test_sem_com_loja_nao_cria_a_coluna(self):
        df = self._df(["L1"], ["2026-08-01"])
        out = ranking(preparar(df, CAMP), "CONSULTOR", CAMP)
        assert COLUNA_LOJA_CONSULTOR not in out.columns

    def test_ranking_vazio_com_loja_preserva_schema(self):
        out = ranking(pd.DataFrame(), "CONSULTOR", CAMP, com_loja=True)
        assert COLUNA_LOJA_CONSULTOR in out.columns


class TestDiasUteisDaCampanha:
    """DU somados mes a mes na janela — `calcular_dias_uteis` e mensal."""

    def test_antes_do_inicio_nao_tem_du_decorrido(self):
        total, dec = dias_uteis_campanha(CAMP, date(2026, 6, 1))
        assert total > 0
        assert dec == 0

    def test_depois_do_fim_decorrido_iguala_o_total(self):
        total, dec = dias_uteis_campanha(CAMP, date(2027, 3, 1))
        assert dec == total

    def test_no_meio_fica_entre_zero_e_o_total(self):
        total, dec = dias_uteis_campanha(CAMP, date(2026, 9, 16))
        assert 0 < dec < total

    def test_total_nao_depende_de_hoje(self):
        """O total da janela e fixo; so o decorrido anda."""
        t1, _ = dias_uteis_campanha(CAMP, date(2026, 7, 2))
        t2, _ = dias_uteis_campanha(CAMP, date(2026, 12, 30))
        assert t1 == t2

    def test_decorrido_cresce_com_o_tempo(self):
        _, d1 = dias_uteis_campanha(CAMP, date(2026, 8, 31))
        _, d2 = dias_uteis_campanha(CAMP, date(2026, 9, 30))
        assert d2 > d1

    def test_semestre_tem_ordem_de_grandeza_plausivel(self):
        """6 meses uteis ficam na casa dos 120-132 dias."""
        total, _ = dias_uteis_campanha(CAMP, date(2026, 9, 16))
        assert 110 <= total <= 135


class TestMediaDuNasTabelas:
    """A coluna que substituiu "Contratos" no ranking e nas familias.

    Quantidade nao diz nada numa campanha apurada em VALOR — um
    contrato de R$ 500 e um de R$ 50 mil contavam igual. O denominador
    e o MESMO para todas as linhas (DU decorridos da campanha), o que
    as torna comparaveis entre si e com o card do topo.
    """

    def _df(self):
        return pd.DataFrame(
            {
                "categoria_codigo": ["CNC", "CNC", "FGTS"],
                "VALOR": [1000.0, 500.0, 300.0],
                "pontos": [10.0, 5.0, 3.0],
                "CONSULTOR": ["A", "B", "B"],
                "LOJA": ["L1", "L2", "L2"],
                "DATA": [pd.Timestamp("2026-08-01")] * 3,
            }
        )

    # ── ranking ────────────────────────────────────

    def test_ranking_nao_tem_mais_contratos(self):
        out = ranking(preparar(self._df(), CAMP), "CONSULTOR", CAMP,
                      du_decorridos=10)
        assert "Contratos" not in out.columns
        assert COLUNA_MEDIA_DU in out.columns

    def test_ranking_divide_valor_pelos_du(self):
        out = ranking(preparar(self._df(), CAMP), "CONSULTOR", CAMP,
                      du_decorridos=10)
        por_nome = dict(zip(out["CONSULTOR"], out[COLUNA_MEDIA_DU]))
        assert por_nome["A"] == 100.0        # 1000 / 10
        assert por_nome["B"] == 80.0         # (500 + 300) / 10

    def test_ranking_du_zero_nao_divide_por_zero(self):
        """Campanha nao comecou: media zero, nao ZeroDivisionError."""
        out = ranking(preparar(self._df(), CAMP), "CONSULTOR", CAMP,
                      du_decorridos=0)
        assert set(out[COLUNA_MEDIA_DU]) == {0.0}

    def test_ranking_vazio_preserva_a_coluna(self):
        out = ranking(pd.DataFrame(), "CONSULTOR", CAMP, du_decorridos=10)
        assert COLUNA_MEDIA_DU in out.columns
        assert "Contratos" not in out.columns

    def test_media_du_nao_reordena_o_ranking(self):
        """A ordem e por PONTOS — media/DU e so leitura de contexto."""
        a = ranking(preparar(self._df(), CAMP), "CONSULTOR", CAMP,
                    du_decorridos=1)
        b = ranking(preparar(self._df(), CAMP), "CONSULTOR", CAMP,
                    du_decorridos=999)
        assert a["CONSULTOR"].tolist() == b["CONSULTOR"].tolist()

    # ── producao por familia ───────────────────────

    def test_familia_nao_tem_mais_contratos(self):
        out = apurar_por_familia(preparar(self._df(), CAMP), CAMP, 10)
        assert "Contratos" not in out.columns
        assert COLUNA_MEDIA_DU in out.columns

    def test_familia_divide_valor_pelos_du(self):
        out = apurar_por_familia(preparar(self._df(), CAMP), CAMP, 10)
        por_fam = dict(zip(out["Família"], out[COLUNA_MEDIA_DU]))
        assert por_fam["CNC"] == 150.0       # (1000 + 500) / 10
        assert por_fam["FGTS"] == 30.0       # 300 / 10

    def test_familia_du_zero_nao_divide_por_zero(self):
        out = apurar_por_familia(preparar(self._df(), CAMP), CAMP, 0)
        assert set(out[COLUNA_MEDIA_DU]) == {0.0}

    def test_soma_das_familias_bate_com_o_card_do_topo(self):
        """A media/DU total e a soma das medias/DU das familias.

        Vale porque o denominador e o mesmo em todas as linhas — e a
        propriedade que justifica essa escolha de denominador.
        """
        df = preparar(self._df(), CAMP)
        fam = apurar_por_familia(df, CAMP, 10)
        assert fam[COLUNA_MEDIA_DU].sum() == pytest.approx(
            apurar(df, CAMP)["valor"] / 10
        )


# ══════════════════════════════════════════════════════
# RLS so no analitico
# ══════════════════════════════════════════════════════


class TestRlsSoNoAnalitico:
    """Rankings e posicoes sao da rede; RLS so recorta o analitico.

    Decisao do usuario (09/2026). Os dois lados quebram calados:
    ranking recortado mostra um supervisor em 1º da propria loja
    (posicao falsa) e contemplacao contra os R$ 75 mi com a producao de
    uma loja so; analitico sem recorte expoe ADE/banco/valor da rede
    inteira a quem nao responde por ela.
    """

    @staticmethod
    def _df() -> pd.DataFrame:
        return pd.DataFrame({
            "categoria_codigo": ["CNC", "CNC", "FGTS", "CONSIG_PRIV"],
            "VALOR": [1000.0, 800.0, 300.0, 200.0],
            "pontos": [100.0, 80.0, 30.0, 20.0],
            "CONSULTOR": ["Ana", "Bia", "Caio", "Duda"],
            "LOJA": ["L1", "L2", "L2", "L3"],
            "REGIAO": ["R1", "R1", "R1", "R2"],
            "DATA": [pd.Timestamp("2026-08-15")] * 4,
            "DATA_CADASTRO": [pd.Timestamp("2026-08-10")] * 4,
            "BANCO": ["B"] * 4,
            "TIPO_PRODUTO": ["X"] * 4,
            "NUM_PROPOSTA": ["1", "2", "3", "4"],
            "CONTRATO_ID": [1, 2, 3, 4],
        })

    @staticmethod
    def _perfil(monkeypatch, perfil):
        import src.dashboard.rls as rls_mod

        monkeypatch.setattr(rls_mod, "_obter_perfil_efetivo", lambda: perfil)

    # ── o analitico recorta ────────────────────────

    def test_supervisor_ve_so_as_proprias_lojas(self, monkeypatch):
        self._perfil(monkeypatch, {"perfil": "supervisor", "escopo": ["L2"]})
        out = campanhas_page.tabela_analitico(self._df())
        assert set(out["Loja"]) == {"L2"}
        assert len(out) == 2

    def test_gerente_ve_so_as_proprias_regioes(self, monkeypatch):
        self._perfil(
            monkeypatch, {"perfil": "gerente_comercial", "escopo": ["R2"]}
        )
        out = campanhas_page.tabela_analitico(self._df())
        assert out["Nº ADE"].tolist() == ["4"]

    def test_sem_perfil_nao_expoe_nada(self, monkeypatch):
        self._perfil(monkeypatch, None)
        assert campanhas_page.tabela_analitico(self._df()).empty

    def test_admin_ve_tudo(self, monkeypatch):
        self._perfil(monkeypatch, {"perfil": "admin", "escopo": []})
        assert len(campanhas_page.tabela_analitico(self._df())) == 4

    # ── o painel NAO recorta ───────────────────────

    def _renderizar_painel(self, monkeypatch, aba):
        """Roda `_render_painel` capturando cada tabela exibida."""
        tabelas = {}

        def exibir(df, *a, key=None, highlight_mask=None, **kw):
            tabelas[key or f"sem_key_{len(tabelas)}"] = df
            tabelas[f"mask:{key}"] = highlight_mask

        pg = campanhas_page
        monkeypatch.setattr(
            pg,
            "carregar_consolidado_intervalo",
            lambda ini, fim: (self._df(), pd.DataFrame(), None),
        )
        monkeypatch.setattr(pg, "exibir_tabela", exibir)
        monkeypatch.setattr(pg, "botao_exportar_csv", lambda *a, **k: None)
        monkeypatch.setattr(pg, "assets_da_campanha", lambda *a: [])
        monkeypatch.setattr(
            pg, "carregar_consultores_desligados",
            lambda: list(getattr(self, "_desligados", [])),
        )
        # calendario de feriados vem do Supabase; aqui so importa o recorte
        monkeypatch.setattr(pg, "dias_uteis_campanha", lambda c, h: (127, 55))
        monkeypatch.setattr(pg.st, "radio", lambda *a, **k: aba)
        monkeypatch.setattr(pg.st, "plotly_chart", lambda *a, **k: None)
        monkeypatch.setattr(pg.sac, "divider", lambda *a, **k: None)
        pg._render_painel(CAMP, date(2026, 9, 16))
        return tabelas

    def test_ranking_de_lojas_e_da_rede_para_supervisor(self, monkeypatch):
        self._perfil(monkeypatch, {"perfil": "supervisor", "escopo": ["L2"]})
        t = self._renderizar_painel(monkeypatch, "Lojas")
        rk = t[f"tab_{CAMP.slug}_ranking_lojas"]
        assert set(rk["LOJA"]) == {"L1", "L2", "L3"}
        # posicao na rede: L2 (110 pts) na frente de L1 (100)
        assert rk.iloc[0]["LOJA"] == "L2"
        # e o analitico, na mesma pagina, continua recortado
        assert set(t["tab_campanha_analitico"]["Loja"]) == {"L2"}

    def test_ranking_de_consultores_e_da_rede_para_consultor(
        self, monkeypatch
    ):
        self._perfil(monkeypatch, {"perfil": "consultor", "escopo": ["Duda"]})
        t = self._renderizar_painel(monkeypatch, "Consultores")
        rk = t[f"tab_{CAMP.slug}_ranking_consultores"]
        assert set(rk["CONSULTOR"]) == {"Ana", "Bia", "Caio", "Duda"}
        assert rk.loc[rk["CONSULTOR"] == "Duda", "#"].item() == 4
        assert t["tab_campanha_analitico"]["Consultor"].tolist() == ["Duda"]

    def test_familias_somam_a_rede_para_supervisor(self, monkeypatch):
        self._perfil(monkeypatch, {"perfil": "supervisor", "escopo": ["L1"]})
        t = self._renderizar_painel(monkeypatch, "Lojas")
        fam = next(
            df for df in t.values() if "Família" in getattr(df, "columns", [])
        )
        assert fam["Valor"].sum() == pytest.approx(2300.0)


class TestDestaqueDoEscopo(TestRlsSoNoAnalitico):
    """Destaque visual do escopo nos rankings da rede.

    Mesma regra do dashboard de vendas (`_make_highlight_fn`). Herda o
    frame e o render de `TestRlsSoNoAnalitico` — os testes de la rodam
    de novo aqui, o que e barato e confirma que o destaque nao mexe no
    recorte.
    """

    _LOJAS = f"tab_{CAMP.slug}_ranking_lojas"
    _CONS = f"tab_{CAMP.slug}_ranking_consultores"

    def _destacados(self, t, chave, coluna):
        mask = t[f"mask:{chave}"]
        if mask is None:
            return set()
        return set(t[chave].loc[mask, coluna])

    def test_supervisor_destaca_a_propria_loja(self, monkeypatch):
        self._perfil(monkeypatch, {"perfil": "supervisor", "escopo": ["L2"]})
        t = self._renderizar_painel(monkeypatch, "Lojas")
        assert self._destacados(t, self._LOJAS, "LOJA") == {"L2"}

    def test_gerente_destaca_as_lojas_da_regiao(self, monkeypatch):
        self._perfil(
            monkeypatch, {"perfil": "gerente_comercial", "escopo": ["R1"]}
        )
        t = self._renderizar_painel(monkeypatch, "Lojas")
        assert self._destacados(t, self._LOJAS, "LOJA") == {"L1", "L2"}

    def test_gerente_destaca_consultores_das_suas_lojas(self, monkeypatch):
        self._perfil(
            monkeypatch, {"perfil": "gerente_comercial", "escopo": ["R2"]}
        )
        t = self._renderizar_painel(monkeypatch, "Consultores")
        assert self._destacados(t, self._CONS, "CONSULTOR") == {"Duda"}

    def test_consultor_destaca_o_proprio_nome(self, monkeypatch):
        self._perfil(monkeypatch, {"perfil": "consultor", "escopo": ["Bia"]})
        t = self._renderizar_painel(monkeypatch, "Consultores")
        assert self._destacados(t, self._CONS, "CONSULTOR") == {"Bia"}

    def test_admin_nao_tem_destaque(self, monkeypatch):
        self._perfil(monkeypatch, {"perfil": "admin", "escopo": []})
        t = self._renderizar_painel(monkeypatch, "Lojas")
        assert t[f"mask:{self._LOJAS}"] is None

    def test_consultor_que_mudou_de_loja_e_do_grupo_da_loja_atual(
        self, monkeypatch
    ):
        """A coluna Loja sai com a marca de multiplas lojas.

        Sem remover a marca, "L2 *" nao casa com "L2" e quem foi
        transferido para a loja do supervisor some do destaque — calado.
        O grupo e o da loja ATUAL (a que a coluna mostra); a loja de
        origem nao destaca, mesmo tendo producao dele.
        """
        extra = pd.DataFrame({
            "categoria_codigo": ["CNC"],
            "VALOR": [50.0],
            "pontos": [5.0],
            "CONSULTOR": ["Ana"],
            "LOJA": ["L3"],
            "REGIAO": ["R2"],
            "DATA": [pd.Timestamp("2026-09-01")],   # depois de L1
            "DATA_CADASTRO": [pd.Timestamp("2026-08-30")],
            "BANCO": ["B"],
            "TIPO_PRODUTO": ["X"],
            "NUM_PROPOSTA": ["5"],
            "CONTRATO_ID": [5],
        })
        base = self._df()
        monkeypatch.setattr(
            TestRlsSoNoAnalitico, "_df",
            staticmethod(lambda: pd.concat([base, extra], ignore_index=True)),
        )
        self._perfil(monkeypatch, {"perfil": "supervisor", "escopo": ["L3"]})
        t = self._renderizar_painel(monkeypatch, "Consultores")
        rk = t[self._CONS]
        assert rk.loc[rk["CONSULTOR"] == "Ana", "Loja"].item().endswith("*")
        assert self._destacados(t, self._CONS, "CONSULTOR") == {"Ana", "Duda"}

        self._perfil(monkeypatch, {"perfil": "supervisor", "escopo": ["L1"]})
        t = self._renderizar_painel(monkeypatch, "Consultores")
        assert "Ana" not in self._destacados(t, self._CONS, "CONSULTOR")


class TestLegendaDoAsterisco:
    """O `*` da coluna Loja precisa se explicar na tela.

    Sem legenda a marca e ruido: quem le nao sabe que o consultor
    produziu em outra loja nem que essa producao continua la no ranking
    de lojas.
    """

    def test_aparece_quando_alguem_tem_a_marca(self):
        rk = pd.DataFrame(
            {COLUNA_LOJA_CONSULTOR: ["L1", f"L2{MARCA_MULTIPLAS_LOJAS}"]}
        )
        legenda = campanhas_page.legenda_multiplas_lojas(rk)
        assert legenda and "mais de uma loja" in legenda

    def test_some_quando_ninguem_tem_a_marca(self):
        rk = pd.DataFrame({COLUNA_LOJA_CONSULTOR: ["L1", "L2"]})
        assert campanhas_page.legenda_multiplas_lojas(rk) is None

    def test_ranking_de_lojas_nao_tem_legenda(self):
        """A marca so existe no ranking de consultores."""
        assert campanhas_page.legenda_multiplas_lojas(
            pd.DataFrame({"LOJA": ["L1 *"]})
        ) is None

    def test_marca_da_legenda_e_a_mesma_da_coluna(self):
        """Mudar a marca num lugar e nao no outro quebraria a legenda."""
        rk = ranking(
            preparar(
                pd.DataFrame({
                    "categoria_codigo": ["CNC", "CNC"],
                    "VALOR": [100.0, 100.0],
                    "pontos": [10.0, 10.0],
                    "CONSULTOR": ["Ana", "Ana"],
                    "LOJA": ["L1", "L2"],
                    "DATA": [pd.Timestamp("2026-08-01"),
                             pd.Timestamp("2026-09-01")],
                }),
                CAMP,
            ),
            "CONSULTOR", CAMP, com_loja=True,
        )
        assert campanhas_page.legenda_multiplas_lojas(rk) is not None


class TestDesligadosForaDoRanking(TestRlsSoNoAnalitico):
    """Desligado nao aparece no ranking de consultores.

    Em 17/09/2026 eram 17 pessoas (R$ 915 mil), todas com status
    "Desligado (a)" no cadastro — nenhuma por grafia divergente.
    """

    _LOJAS = f"tab_{CAMP.slug}_ranking_lojas"
    _CONS = f"tab_{CAMP.slug}_ranking_consultores"
    _ADMIN = {"perfil": "admin", "escopo": []}

    def test_some_do_ranking_de_consultores(self, monkeypatch):
        self._desligados = ["Ana"]
        self._perfil(monkeypatch, self._ADMIN)
        rk = self._renderizar_painel(monkeypatch, "Consultores")[self._CONS]
        assert "Ana" not in set(rk["CONSULTOR"])

    def test_posicoes_sao_recalculadas(self, monkeypatch):
        """Ana era 1ª; sem ela, Bia vira 1ª — desligado nao ocupa vaga."""
        self._desligados = ["Ana"]
        self._perfil(monkeypatch, self._ADMIN)
        rk = self._renderizar_painel(monkeypatch, "Consultores")[self._CONS]
        assert rk.iloc[0]["CONSULTOR"] == "Bia"
        assert rk.iloc[0]["#"] == 1

    def test_producao_continua_no_ranking_de_lojas(self, monkeypatch):
        self._desligados = ["Ana"]
        self._perfil(monkeypatch, self._ADMIN)
        rk = self._renderizar_painel(monkeypatch, "Lojas")[self._LOJAS]
        assert "L1" in set(rk["LOJA"])      # L1 so tem producao da Ana

    def test_totais_da_campanha_nao_mudam(self, monkeypatch):
        self._desligados = ["Ana"]
        self._perfil(monkeypatch, self._ADMIN)
        t = self._renderizar_painel(monkeypatch, "Lojas")
        fam = next(
            df for df in t.values() if "Família" in getattr(df, "columns", [])
        )
        assert fam["Valor"].sum() == pytest.approx(2300.0)

    def test_tela_nao_menciona_desligamento(self, monkeypatch):
        """Regra interna (usuario, 09/2026): o filtro age calado.

        Varre todo texto que a pagina escreve — caption, info, warning,
        markdown, metric — nos dois rankings.
        """
        pg = campanhas_page
        textos = []

        def grava(*a, **k):
            textos.extend(str(x) for x in (*a, *k.values()))

        for nome in ("caption", "info", "warning", "markdown", "write"):
            monkeypatch.setattr(pg.st, nome, grava)
        self._desligados = ["Ana"]
        self._perfil(monkeypatch, self._ADMIN)
        for aba in ("Consultores", "Lojas"):
            self._renderizar_painel(monkeypatch, aba)
        assert textos, "a varredura nao capturou nada"
        assert not [t for t in textos if "deslig" in t.lower()]

    def test_match_ignora_caixa_e_acento(self):
        df = pd.DataFrame({"CONSULTOR": ["Érica Souza", "Bia"]})
        out, n = excluir_desligados(df, ["ERICA SOUZA "])
        assert out["CONSULTOR"].tolist() == ["Bia"]
        assert n == 1

    def test_conta_pessoas_e_nao_contratos(self):
        df = pd.DataFrame({"CONSULTOR": ["Ana", "Ana", "Bia"]})
        assert excluir_desligados(df, ["Ana"])[1] == 1

    def test_sem_desligados_nao_mexe(self):
        df = pd.DataFrame({"CONSULTOR": ["Ana"]})
        out, n = excluir_desligados(df, [])
        assert len(out) == 1 and n == 0
