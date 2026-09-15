"""
Testes do resumo por loja no fim do Dashboard de Pontuação
(``pages/dashboard_pontuacao.py :: _render_resumo_lojas``).

Cobre o que o cálculo puro não cobre: o gate por perfil
(``resumo_lojas_pontuacao``), a ocultação com consultor selecionado
(meta de LOJA não se compara com a produção de uma pessoa) e o aviso
nomeando lojas sem meta. Roda via ``AppTest.from_function``, mesma
técnica de ``test_ui_prioridades_pontuacao.py``; asserts em texto
visível.
"""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest


def _app(consultor_selecionado: bool, perfil: str = "admin"):
    import pandas as pd

    from src.dashboard.pages.dashboard_pontuacao import _render_resumo_lojas
    from src.dashboard.permissions import pode_ver

    if not pode_ver("resumo_lojas_pontuacao", perfil):
        return
    _render_resumo_lojas(
        df=pd.DataFrame({"LOJA": ["A", "DIGITAL"], "pontos": [5000.0, 800.0]}),
        df_metas_loja=pd.DataFrame(
            {"LOJA": ["A"], "META_PRATA": [10000.0], "META_OURO": [20000.0]}
        ),
        kpis={"du_total": 20, "du_decorridos": 10, "du_restantes": 10},
        consultor_selecionado=consultor_selecionado,
    )


def _textos(at) -> str:
    partes = [c.value for c in at.caption] + [m.value for m in at.markdown]
    partes += [i.value for i in at.info]
    return "\n".join(str(p) for p in partes)


@pytest.mark.unit
class TestRenderResumoLojas:
    def test_renderiza_e_nomeia_loja_sem_meta(self):
        at = AppTest.from_function(_app, kwargs={"consultor_selecionado": False})
        at.run()
        assert not at.exception
        txt = _textos(at)
        assert "Resumo por Loja" in txt
        assert "Sem Meta Prata cadastrada" in txt
        assert "DIGITAL" in txt
        assert "indisponível com um consultor" not in txt

    def test_consultor_selecionado_oculta_tabela(self):
        at = AppTest.from_function(_app, kwargs={"consultor_selecionado": True})
        at.run()
        assert not at.exception
        txt = _textos(at)
        assert "indisponível com um consultor selecionado" in txt
        assert "Sem Meta Prata cadastrada" not in txt
        assert len(at.dataframe) == 0



def _pagina(perfil: str):
    import pandas as pd

    from src.dashboard.pages.dashboard_pontuacao import (
        render_dashboard_pontuacao,
    )

    render_dashboard_pontuacao(
        kpis={
            "du_total": 20, "du_decorridos": 10, "du_restantes": 10,
            "meta_prata": 10000, "meta_ouro": 20000, "total_pontos": 5000,
        },
        df=pd.DataFrame({
            "LOJA": ["A"], "pontos": [5000.0], "VALOR": [5000.0],
            "categoria_codigo": ["CNC"], "CONSULTOR": ["x"],
        }),
        df_analise=pd.DataFrame(),
        df_cancelados=pd.DataFrame(),
        df_metas_produto=pd.DataFrame(),
        df_sup=pd.DataFrame(),
        mapa_pontos={"CNC": 1.0},
        du_decorridos=10,
        perfil=perfil,
        df_metas_loja=pd.DataFrame(
            {"LOJA": ["A"], "META_PRATA": [10000.0], "META_OURO": [20000.0]}
        ),
    )


@pytest.mark.unit
class TestGatePaginaPontuacao:
    """Gate de perfil na página real — não só na matriz."""

    @pytest.mark.parametrize("perfil", ["admin", "gestor", "gerente_comercial"])
    def test_perfis_gerenciais_veem_resumo_no_fim(self, perfil):
        at = AppTest.from_function(_pagina, kwargs={"perfil": perfil})
        at.run(timeout=30)
        assert not at.exception
        titulos = [m.value for m in at.markdown if m.value.startswith("###")]
        assert titulos[-1] == "### 🏪 Resumo por Loja"

    @pytest.mark.parametrize("perfil", ["supervisor", "consultor"])
    def test_supervisor_e_consultor_nao_veem(self, perfil):
        at = AppTest.from_function(_pagina, kwargs={"perfil": perfil})
        at.run(timeout=30)
        assert not at.exception
        assert "Resumo por Loja" not in _textos(at)


def _pagina_regioes(perfil: str):
    import pandas as pd

    from src.dashboard.pages.dashboard_pontuacao import _render_resumo_lojas

    _render_resumo_lojas(
        df=pd.DataFrame({
            "LOJA": ["A", "B"],
            "REGIAO": ["SUL", "NORTE"],
            "pontos": [5000.0, 800.0],
        }),
        df_metas_loja=pd.DataFrame({
            "LOJA": ["A", "B"],
            "REGIAO": ["SUL", "NORTE"],
            "META_PRATA": [10000.0, 2000.0],
            "META_OURO": [20000.0, 4000.0],
        }),
        kpis={"du_total": 20, "du_decorridos": 10, "du_restantes": 10},
        consultor_selecionado=False,
        perfil=perfil,
        mes=9,
        ano=2026,
    )


@pytest.mark.unit
class TestFlagSepararPorRegiao:
    @pytest.mark.parametrize("perfil", ["admin", "gestor"])
    def test_admin_e_gestor_separam_por_regiao(self, perfil):
        at = AppTest.from_function(_pagina_regioes, kwargs={"perfil": perfil})
        at.run(timeout=30)
        assert not at.exception
        assert len(at.dataframe) == 1  # desligada: tabela única

        at.toggle(key="resumo_lojas_por_regiao").set_value(True).run(timeout=30)
        assert not at.exception
        subtitulos = [m.value for m in at.markdown if m.value.startswith("####")]
        assert subtitulos == ["#### NORTE", "#### SUL", "#### Total geral"]
        assert len(at.dataframe) == 3

    def test_gerente_comercial_nao_ve_a_flag(self):
        at = AppTest.from_function(
            _pagina_regioes, kwargs={"perfil": "gerente_comercial"}
        )
        at.run(timeout=30)
        assert not at.exception
        assert len(at.toggle) == 0
        assert len(at.dataframe) == 1


@pytest.mark.unit
class TestMontarExportacaoResumoLojas:
    """O que vai para o arquivo — números como número, contexto na linha."""

    DU = dict(du_total=20, du_decorridos=10, du_restantes=10)

    @staticmethod
    def _csv(frame) -> list:
        # Mesma serialização de `botao_exportar_csv`.
        return frame.to_csv(index=False, sep=";", decimal=",").splitlines()

    def test_sem_regiao_numeros_arredondados_sem_milhar(self):
        from src.dashboard.kpis.pontuacao import calcular_resumo_lojas_pontuacao
        from src.dashboard.pages.dashboard_pontuacao import (
            montar_exportacao_resumo_lojas,
        )

        df = pd.DataFrame({"LOJA": ["A"], "pontos": [12345.6789]})
        metas = pd.DataFrame(
            {"LOJA": ["A"], "META_PRATA": [30000.0], "META_OURO": [60000.0]}
        )
        resumo = calcular_resumo_lojas_pontuacao(df, metas, **self.DU)
        saida = montar_exportacao_resumo_lojas([(None, resumo)], 10)

        assert "Região" not in saida.columns
        linhas = self._csv(saida)
        assert linhas[0].split(";") == [
            "Loja", "Pontos", "Projeção", "Meta Prata", "Ating. Prata %",
            "Meta Ouro", "Ating. Ouro %", "Meta Diária Prata",
            "Meta Diária Ouro", "Observação",
        ]
        a = linhas[1].split(";")
        # 12345,68 (sem "12.345"); 41,2% vira 41,2 numérico, sem "%"
        assert a[1] == "12345,68"
        assert a[2] == "24691,36"
        assert a[4] == "41,2"
        assert a[-1] == ""

    def test_nao_se_aplica_em_branco_com_observacao(self):
        from src.dashboard.kpis.pontuacao import calcular_resumo_lojas_pontuacao
        from src.dashboard.pages.dashboard_pontuacao import (
            montar_exportacao_resumo_lojas,
        )

        df = pd.DataFrame({"LOJA": ["A", "DIGITAL"], "pontos": [100.0, 50.0]})
        metas = pd.DataFrame(
            {"LOJA": ["A"], "META_PRATA": [1000.0], "META_OURO": [2000.0]}
        )
        resumo = calcular_resumo_lojas_pontuacao(
            df, metas, du_total=20, du_decorridos=20, du_restantes=0
        )
        saida = montar_exportacao_resumo_lojas([(None, resumo)], 0)
        obs = dict(zip(saida["Loja"], saida["Observação"]))
        assert obs["DIGITAL"] == (
            "Sem meta Prata cadastrada; Sem meta Ouro cadastrada"
        )
        assert obs["A"] == (
            "Período encerrado — Prata não atingida; "
            "Período encerrado — Ouro não atingida"
        )
        digital = next(
            linha for linha in self._csv(saida) if linha.startswith("DIGITAL")
        ).split(";")
        assert digital[4] == ""  # Ating. Prata % em branco, nunca 0

    def test_por_regiao_rotula_totais_e_total_geral_no_fim(self):
        from src.dashboard.kpis.pontuacao import (
            calcular_resumo_lojas_pontuacao_por_regiao,
        )
        from src.dashboard.pages.dashboard_pontuacao import (
            montar_exportacao_resumo_lojas,
        )

        df = pd.DataFrame({
            "LOJA": ["A", "B"], "REGIAO": ["SUL", "NORTE"],
            "pontos": [100.0, 200.0],
        })
        sep = calcular_resumo_lojas_pontuacao_por_regiao(
            df, pd.DataFrame(), **self.DU
        )
        saida = montar_exportacao_resumo_lojas(
            sep["regioes"], 10, total_geral=sep["total"]
        )
        assert saida.columns[0] == "Região"
        assert list(zip(saida["Região"], saida["Loja"])) == [
            ("NORTE", "B"), ("NORTE", "TOTAL NORTE"),
            ("SUL", "A"), ("SUL", "TOTAL SUL"),
            ("", "TOTAL GERAL"),
        ]
        assert saida.iloc[-1]["Pontos"] == pytest.approx(300.0)
