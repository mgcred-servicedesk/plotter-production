"""
Regra do MIX no dashboard de vendas (decisão do usuário, 10/2026).

O quadro só pode dizer "meta atingida" quando o total do MIX bate a
meta **e** cada produto com meta bate 100% da própria. Se o total ou
algum produto já bateu e ainda há produto abaixo, o quadro avisa quanto
falta em cada produto restante. O excedente de um produto não cobre a
falta de outro: "quanto falta" é a soma das faltas por produto.

Vale para o card "🎯 Falta para Meta", o bloco "Para Onde Estamos
Indo" e a Meta Diária do consultor. Os asserts de render ancoram em
texto visível (mesma convenção de ``test_ui_kpi_cards_pontuacao.py``).
"""
import pytest
from streamlit.testing.v1 import AppTest

from src.dashboard.kpis.gerais import avaliar_regra_mix, projetar_regra_mix
from src.dashboard.ui.kpi_cards_reforma import mensagem_regra_mix
from src.dashboard.ui.prioridades_acao import calcular_planejamento_consultor


def _prod(produto, valor, meta):
    return {"produto": produto, "valor_atual": valor, "meta_total": meta}


# Total 148.500 contra meta MIX 130.000 (batido), mas CLT 5.000 abaixo.
PRODUTOS_TOTAL_BATIDO_CLT_PENDENTE = [
    _prod("CNC", 60000.0, 40000.0),
    _prod("CLT", 10000.0, 15000.0),
    _prod("SAQUE", 500.0, 0.0),  # sem meta: fora da regra
    _prod("CONSIGNADO", 70000.0, 67000.0),
    _prod("FGTS_ANT_BEN_CNC13", 8000.0, 8000.0),
]
TOTAL_148K = 148500.0
META_MIX_130K = 130000.0

PRODUTOS_TODOS_BATIDOS = [
    _prod("CNC", 41000.0, 40000.0),
    _prod("CLT", 15000.0, 15000.0),
    _prod("SAQUE", 0.0, 0.0),
    _prod("CONSIGNADO", 67500.0, 67000.0),
    _prod("FGTS_ANT_BEN_CNC13", 9000.0, 8000.0),
]


@pytest.mark.unit
class TestAvaliarRegraMix:
    def test_total_batido_com_produto_pendente_nao_e_meta_atingida(self):
        regra = avaliar_regra_mix(
            PRODUTOS_TOTAL_BATIDO_CLT_PENDENTE, TOTAL_148K, META_MIX_130K
        )
        assert regra["total_batido"]
        assert not regra["atingida"]
        assert regra["parcial"]
        assert regra["pendentes"] == [{"produto": "CLT", "falta": 5000.0}]
        # Excedente de CNC/Consignado não cobre a falta de CLT.
        assert regra["falta"] == pytest.approx(5000.0)

    def test_todos_os_produtos_na_meta_e_meta_atingida(self):
        total = sum(p["valor_atual"] for p in PRODUTOS_TODOS_BATIDOS)
        regra = avaliar_regra_mix(PRODUTOS_TODOS_BATIDOS, total, META_MIX_130K)
        assert regra["atingida"]
        assert not regra["parcial"]
        assert regra["falta"] == 0.0

    def test_produto_sem_meta_nao_entra_na_regra(self):
        regra = avaliar_regra_mix(
            PRODUTOS_TOTAL_BATIDO_CLT_PENDENTE, TOTAL_148K, META_MIX_130K
        )
        produtos_avaliados = regra["batidos"] + [
            p["produto"] for p in regra["pendentes"]
        ]
        assert "SAQUE" not in produtos_avaliados

    def test_produto_batido_sem_total_e_parcial_e_soma_as_faltas(self):
        produtos = [
            _prod("CNC", 45000.0, 40000.0),   # batido (+5.000)
            _prod("CLT", 5000.0, 15000.0),    # falta 10.000
            _prod("CONSIGNADO", 37000.0, 67000.0),  # falta 30.000
        ]
        regra = avaliar_regra_mix(produtos, 87000.0, 122000.0)
        assert not regra["total_batido"]
        assert regra["parcial"]
        assert regra["batidos"] == ["CNC"]
        assert [p["produto"] for p in regra["pendentes"]] == [
            "CONSIGNADO", "CLT",
        ]
        # 40.000 de falta por produto > 35.000 de falta no total.
        assert regra["falta"] == pytest.approx(40000.0)

    def test_nada_batido_nao_e_parcial(self):
        produtos = [_prod("CNC", 1000.0, 40000.0), _prod("CLT", 0.0, 15000.0)]
        regra = avaliar_regra_mix(produtos, 1000.0, 55000.0)
        assert not regra["parcial"]
        assert not regra["atingida"]
        assert regra["falta"] == pytest.approx(54000.0)

    def test_sem_meta_mix_nunca_atingida(self):
        regra = avaliar_regra_mix(PRODUTOS_TODOS_BATIDOS, 500000.0, 0.0)
        assert not regra["tem_meta"]
        assert not regra["atingida"]
        assert not regra["parcial"]

    def test_perc_nao_atingida_desconta_o_que_falta_nos_produtos(self):
        # Total 114,2% da meta, mas faltam 5.000 em CLT: o excedente
        # de CNC/Consignado não compensa -> (130.000 - 5.000) / 130.000.
        regra = avaliar_regra_mix(
            PRODUTOS_TOTAL_BATIDO_CLT_PENDENTE, TOTAL_148K, META_MIX_130K
        )
        assert regra["perc"] == pytest.approx(125000 / 130000 * 100)
        assert regra["perc"] < 100

    def test_perc_atingida_e_o_do_total_e_pode_passar_de_100(self):
        total = sum(p["valor_atual"] for p in PRODUTOS_TODOS_BATIDOS)
        regra = avaliar_regra_mix(PRODUTOS_TODOS_BATIDOS, total, META_MIX_130K)
        assert regra["perc"] == pytest.approx(total / META_MIX_130K * 100)
        assert regra["perc"] > 100

    def test_perc_sem_meta_e_zero(self):
        assert avaliar_regra_mix(PRODUTOS_TODOS_BATIDOS, 1.0, 0.0)["perc"] == 0

    def test_sem_metas_por_produto_cai_so_no_total(self):
        assert avaliar_regra_mix(None, 140000.0, 130000.0)["atingida"]
        regra = avaliar_regra_mix([], 120000.0, 130000.0)
        assert not regra["atingida"]
        assert regra["falta"] == pytest.approx(10000.0)


@pytest.mark.unit
class TestMensagemRegraMix:
    def test_total_batido_lista_o_que_falta_por_produto(self):
        msg = mensagem_regra_mix(avaliar_regra_mix(
            PRODUTOS_TOTAL_BATIDO_CLT_PENDENTE, TOTAL_148K, META_MIX_130K
        ))
        assert msg.startswith("Total do MIX batido — falta bater:")
        assert "CLT R&#36; 5.0K" in msg
        assert "$" not in msg.replace("&#36;", "")  # nada de LaTeX

    def test_produto_batido_sem_total_cita_o_batido_e_as_faltas(self):
        produtos = [_prod("CNC", 45000.0, 40000.0), _prod("CLT", 0.0, 15000.0)]
        msg = mensagem_regra_mix(avaliar_regra_mix(produtos, 45000.0, 55000.0))
        assert msg.startswith("Já bateu: CNC · Falta:")
        assert "CLT R&#36; 15.0K" in msg

    def test_fora_do_estado_parcial_e_vazia(self):
        total = sum(p["valor_atual"] for p in PRODUTOS_TODOS_BATIDOS)
        assert mensagem_regra_mix(
            avaliar_regra_mix(PRODUTOS_TODOS_BATIDOS, total, META_MIX_130K)
        ) == ""


@pytest.mark.unit
class TestPlanejamentoConsultor:
    def test_gap_segue_a_regra_do_mix(self):
        kpis = {
            "total_vendas": TOTAL_148K,
            "meta_mix": META_MIX_130K,
            "du_restantes": 5,
            "media_du": 10000.0,
            # gap_valor do kpis (total) diria "meta atingida".
            "gap_valor": 0.0,
        }
        plan = calcular_planejamento_consultor(
            kpis, None, PRODUTOS_TOTAL_BATIDO_CLT_PENDENTE
        )
        assert plan["gap_valor"] == pytest.approx(5000.0)
        assert plan["meta_diaria_necessaria"] == pytest.approx(1000.0)
        assert not plan["regra_mix"]["atingida"]


# ── Render (AppTest) ──────────────────────────────────


def _script_kpis_principais(kpis, metas_produto):
    from src.dashboard.ui.kpi_cards_reforma import render_kpis_principais

    render_kpis_principais(kpis, {}, {}, metas_produto=metas_produto)


def _script_bloco_media_projecao(kpis, metas_produto):
    from src.dashboard.ui.kpi_cards_reforma import render_bloco_media_projecao

    render_bloco_media_projecao(kpis, metas_produto)


def _html(script, kpis, metas_produto) -> str:
    at = AppTest.from_function(
        script, kwargs=dict(kpis=kpis, metas_produto=metas_produto),
    )
    at.run()
    assert not at.exception
    return "\n".join(m.value for m in at.markdown)


def _kpis(total, meta, du_restantes=5):
    return {
        "total_vendas": total,
        "meta_mix": meta,
        "perc_ating_valor": total / meta * 100,
        "gap_valor": max(0.0, meta - total),
        "projecao": total * 1.2,
        "media_du": total / 15,
        "du_restantes": du_restantes,
        "du_total": 20,
        "du_decorridos": 20 - du_restantes,
    }


@pytest.mark.unit
class TestRenderFaltaParaMeta:
    def test_total_batido_com_produto_pendente_nao_diz_atingida(self):
        html = _html(
            _script_kpis_principais,
            _kpis(TOTAL_148K, META_MIX_130K),
            PRODUTOS_TOTAL_BATIDO_CLT_PENDENTE,
        )
        # "% Meta Atingida" é o rótulo do card vizinho; o veredito é o ✓.
        assert "✓ Meta Atingida" not in html
        assert "falta bater" in html
        assert "CLT" in html

    def test_percentual_segue_a_regra_e_mostra_o_total_no_rodape(self):
        html = _html(
            _script_kpis_principais,
            _kpis(TOTAL_148K, META_MIX_130K),
            PRODUTOS_TOTAL_BATIDO_CLT_PENDENTE,
        )
        assert "96.2%" in html  # (130.000 - 5.000) / 130.000
        assert "Total vendido: 114.2% da meta MIX" in html

    def test_percentual_atingida_e_o_do_total_sem_rodape(self):
        total = sum(p["valor_atual"] for p in PRODUTOS_TODOS_BATIDOS)
        html = _html(
            _script_kpis_principais,
            _kpis(total, META_MIX_130K),
            PRODUTOS_TODOS_BATIDOS,
        )
        assert f"{total / META_MIX_130K * 100:.1f}%" in html
        assert "Total vendido" not in html

    def test_todos_os_produtos_na_meta_diz_atingida(self):
        total = sum(p["valor_atual"] for p in PRODUTOS_TODOS_BATIDOS)
        html = _html(
            _script_kpis_principais,
            _kpis(total, META_MIX_130K),
            PRODUTOS_TODOS_BATIDOS,
        )
        assert "✓ Meta Atingida" in html


@pytest.mark.unit
class TestRenderParaOndeEstamosIndo:
    def test_total_batido_com_produto_pendente_nao_diz_atingida(self):
        html = _html(
            _script_bloco_media_projecao,
            _kpis(TOTAL_148K, META_MIX_130K),
            PRODUTOS_TOTAL_BATIDO_CLT_PENDENTE,
        )
        assert "Meta atingida" not in html
        assert "falta bater" in html

    def test_todos_os_produtos_na_meta_diz_atingida(self):
        total = sum(p["valor_atual"] for p in PRODUTOS_TODOS_BATIDOS)
        html = _html(
            _script_bloco_media_projecao,
            _kpis(total, META_MIX_130K),
            PRODUTOS_TODOS_BATIDOS,
        )
        assert "Meta atingida" in html


def _html_resumo(monkeypatch, kpis, metas_produto) -> str:
    from src.dashboard.ui import resumo_executivo

    capturado = []
    monkeypatch.setattr(resumo_executivo.st, "html", capturado.append)
    resumo_executivo.render_resumo_executivo(kpis, {}, {}, metas_produto)
    assert len(capturado) == 1
    return capturado[0]


@pytest.mark.unit
class TestRenderResumoExecutivo:
    def test_total_batido_com_produto_pendente_nao_diz_atingida(
        self, monkeypatch
    ):
        html = _html_resumo(
            monkeypatch,
            _kpis(TOTAL_148K, META_MIX_130K),
            PRODUTOS_TOTAL_BATIDO_CLT_PENDENTE,
        )
        assert "Meta MIX atingida —" not in html
        assert "96.2% da meta MIX atingida" in html
        assert "falta bater" in html
        assert "Faltam: R$ 5,0K" in html  # falta pela regra, não R$ 0

    def test_todos_os_produtos_na_meta_diz_atingida(self, monkeypatch):
        total = sum(p["valor_atual"] for p in PRODUTOS_TODOS_BATIDOS)
        html = _html_resumo(
            monkeypatch, _kpis(total, META_MIX_130K), PRODUTOS_TODOS_BATIDOS,
        )
        assert "✅" in html
        assert "Meta MIX atingida —" in html


# ── Projeção pela regra ───────────────────────────────
# Caso Bruna (10/2026): Consignado projeta muito acima e esconde CNC,
# CLT e FGTS projetados abaixo — a projeção total dava 247% da meta.
def _prod_proj(produto, valor, meta, projecao):
    return {**_prod(produto, valor, meta), "projecao": projecao}


PRODUTOS_PROJ_CONSIG_ESCONDE = [
    _prod_proj("CNC", 21738.0, 35000.0, 30000.0),           # falta 5.000
    _prod_proj("CLT", 2200.0, 12000.0, 4000.0),             # falta 8.000
    _prod_proj("SAQUE", 0.0, 0.0, 0.0),
    _prod_proj("CONSIGNADO", 97930.0, 61000.0, 230000.0),   # sobra
    _prod_proj("FGTS_ANT_BEN_CNC13", 0.0, 7000.0, 0.0),     # falta 7.000
]
META_MIX_115K = 115000.0
PROJECAO_264K = 264000.0


@pytest.mark.unit
class TestProjetarRegraMix:
    def test_excedente_projetado_nao_compensa_os_outros(self):
        regra = projetar_regra_mix(
            PRODUTOS_PROJ_CONSIG_ESCONDE, PROJECAO_264K, META_MIX_115K
        )
        assert [p["produto"] for p in regra["pendentes"]] == [
            "CLT", "FGTS_ANT_BEN_CNC13", "CNC",
        ]
        # (115.000 - 20.000 que faltam projetados) / 115.000
        assert regra["perc"] == pytest.approx(95000 / 115000 * 100)

    def test_todos_projetados_na_meta_usa_a_projecao_total(self):
        produtos = [
            _prod_proj("CNC", 20000.0, 35000.0, 40000.0),
            _prod_proj("CLT", 8000.0, 12000.0, 13000.0),
        ]
        regra = projetar_regra_mix(produtos, 53000.0, 47000.0)
        assert not regra["pendentes"]
        assert regra["perc"] == pytest.approx(53000 / 47000 * 100)


def _kpis_bruna():
    return {
        "total_vendas": 121868.0,
        "meta_mix": META_MIX_115K,
        "perc_ating_valor": 121868 / 115000 * 100,
        "gap_valor": 0.0,
        "projecao": PROJECAO_264K,
        "media_du": 13500.0,
        "du_restantes": 12,
        "du_total": 21,
        "du_decorridos": 9,
    }


@pytest.mark.unit
class TestRenderProjecaoPelaRegra:
    def test_para_onde_projecao_e_ritmo_por_produto(self):
        html = _html(
            _script_bloco_media_projecao, _kpis_bruna(),
            PRODUTOS_PROJ_CONSIG_ESCONDE,
        )
        assert f"{95000 / 115000 * 100:.1f}%" in html  # Projeção Fim
        assert "acima da meta" not in html
        assert "Fecharemos 17% abaixo da meta" in html
        assert "acima do necessário" not in html
        assert "Ritmo abaixo do necessário em: CLT" in html

    def test_card_meta_atingida_projecao_pela_regra(self):
        html = _html(
            _script_kpis_principais, _kpis_bruna(),
            PRODUTOS_PROJ_CONSIG_ESCONDE,
        )
        assert f"Projeção: {95000 / 115000 * 100:.1f}%" in html

    def test_resumo_proj_mix_e_pill_de_ritmo(self, monkeypatch):
        html = _html_resumo(
            monkeypatch, _kpis_bruna(), PRODUTOS_PROJ_CONSIG_ESCONDE,
        )
        assert f"{95000 / 115000 * 100:.1f}%</div>" in html  # Proj. MIX
        assert "229.6%" not in html  # projeção total / meta
        assert "Ritmo abaixo do necessário em: CLT" in html
