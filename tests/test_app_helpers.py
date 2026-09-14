"""
Testes dos helpers puros que sustentam o bloco de KPIs do dashboard
(``_ritmo_organizacao``, ``serie_diaria_pago``) e da chave de cache
(``_chave_kpis``).

Os três nasceram em ``app.py`` e migraram para ``kpis/gerais.py`` junto
com o bloco de KPIs do período (ST-07 — hoje decomposto na família
``obter_*_periodo``): são cálculo puro, não chamam ``st.*``
— ``_chave_kpis`` recebe o ``session_state`` injetado.
"""
import pandas as pd
import pytest

from src.dashboard.kpis.gerais import (
    _chave_kpis,
    _revisao_entradas,
    _revisao_frame,
    _ritmo_organizacao,
    serie_diaria_pago,
)

# Revisao fixa para os testes de chave: eles isolam os componentes 1-6,
# entao o 7o precisa ficar constante entre as chamadas comparadas.
_DF_BASE = pd.DataFrame({"VALOR": [1.0], "LOJA": ["A"]})
_DF_MAIOR = pd.DataFrame({"VALOR": [1.0, 2.0], "LOJA": ["A", "B"]})
_REV = _revisao_entradas(_DF_BASE, 10)


@pytest.mark.unit
class TestRitmoOrganizacao:
    def test_perfil_sem_referencia(self):
        df = pd.DataFrame({"REGIAO": ["R1"], "LOJA": ["A"], "VALOR": [1.0]})
        assert _ritmo_organizacao(
            "gerente_comercial", df, df, pd.DataFrame()
        ) == (None, 1)
        assert _ritmo_organizacao("admin", df, df, pd.DataFrame()) == (None, 1)

    def test_supervisor_normaliza_por_lojas(self):
        df_f = pd.DataFrame({"REGIAO": ["R1"], "LOJA": ["A"]})
        df_full = pd.DataFrame({
            "REGIAO": ["R1", "R1", "R2"],
            "LOJA": ["A", "B", "C"],
        })
        df_reg, norm = _ritmo_organizacao(
            "supervisor", df_f, df_full, pd.DataFrame()
        )
        assert norm == 2  # lojas A, B em R1
        assert set(df_reg["LOJA"]) == {"A", "B"}

    def test_consultor_exclui_supervisores(self):
        df_f = pd.DataFrame({"REGIAO": ["R1"], "CONSULTOR": ["X"]})
        df_full = pd.DataFrame({
            "REGIAO": ["R1", "R1", "R1"],
            "CONSULTOR": ["X", "Y", "S"],
        })
        df_sup = pd.DataFrame({"SUPERVISOR": ["S"]})
        _df_reg, norm = _ritmo_organizacao("consultor", df_f, df_full, df_sup)
        assert norm == 2  # X, Y (S é supervisor, excluído)

    def test_df_vazio(self):
        empty = pd.DataFrame()
        assert _ritmo_organizacao("supervisor", empty, empty, empty) == (
            None, 1
        )


@pytest.mark.unit
class TestSerieDiariaPago:
    def test_serie_com_dois_ou_mais_dias(self):
        df = pd.DataFrame({
            "DATA": pd.to_datetime(
                ["2026-06-01", "2026-06-01", "2026-06-02"]
            ),
            "VALOR": [100.0, 50.0, 200.0],
        })
        assert serie_diaria_pago(df) == [150.0, 200.0]

    def test_um_dia_retorna_none(self):
        df = pd.DataFrame({
            "DATA": pd.to_datetime(["2026-06-01"]),
            "VALOR": [100.0],
        })
        assert serie_diaria_pago(df) is None

    def test_sem_data_ou_vazio(self):
        assert serie_diaria_pago(pd.DataFrame({"VALOR": [1.0]})) is None
        assert serie_diaria_pago(pd.DataFrame()) is None


@pytest.mark.unit
class TestChaveKpis:
    """A chave de cache e a fronteira entre perfis.

    Se dois recortes diferentes colidirem na mesma chave, o segundo
    perfil recebe o KPI calculado para o primeiro. Estes testes existem
    para que essa colisao apareca como falha, e nao em producao.
    """

    def _ss(self, lojas=None, consultor=None):
        return {
            "ui_filtro_lojas": lojas,
            "ui_filtro_consultor": consultor,
        }

    def test_composicao_e_ordem(self):
        chave = _chave_kpis(
            6,
            2026,
            "gerente_comercial",
            {"perfil": "gerente_comercial", "escopo": ["R1", "R2"]},
            self._ss(lojas=["B", "A"], consultor="FULANO"),
            _REV,
        )
        assert chave == (
            6, 2026, "gerente_comercial", ("R1", "R2"), ("A", "B"), "FULANO",
            _REV,
        )

    def test_escopos_distintos_nao_colidem(self):
        """Dois gerentes tem o mesmo role — so o escopo os separa."""
        base = self._ss()
        chave_a = _chave_kpis(
            6, 2026, "gerente_comercial", {"escopo": ["REGIAO_A"]}, base, _REV
        )
        chave_b = _chave_kpis(
            6, 2026, "gerente_comercial", {"escopo": ["REGIAO_B"]}, base, _REV
        )
        assert chave_a != chave_b

    def test_role_periodo_e_filtros_invalidam(self):
        args = (6, 2026, "supervisor", {"escopo": ["L1"]})
        base = _chave_kpis(*args, self._ss(), _REV)
        assert base != _chave_kpis(7, 2026, *args[2:], self._ss(), _REV)
        assert base != _chave_kpis(6, 2025, *args[2:], self._ss(), _REV)
        assert base != _chave_kpis(
            *args[:2], "consultor", args[3], self._ss(), _REV
        )
        assert base != _chave_kpis(*args, self._ss(lojas=["L1"]), _REV)
        assert base != _chave_kpis(*args, self._ss(consultor="FULANO"), _REV)

    def test_revisao_dos_dados_invalida(self):
        """O 7o componente: dado novo com a MESMA selecao de UI e
        perfil precisa mudar a chave — senao a tela segue no numero da
        carga anterior ate alguem mexer num filtro."""
        args = (6, 2026, "supervisor", {"escopo": ["L1"]})
        base = _chave_kpis(*args, self._ss(), _REV)
        outra = _chave_kpis(
            *args, self._ss(), _revisao_entradas(_DF_MAIOR, 10),
        )
        assert base != outra

    def test_lojas_independem_da_ordem_de_selecao(self):
        args = (6, 2026, "gerente_comercial", {"escopo": ["R1"]})
        assert _chave_kpis(
            *args, self._ss(lojas=["A", "B"]), _REV
        ) == _chave_kpis(*args, self._ss(lojas=["B", "A"]), _REV)

    def test_ausencias_normalizam_sem_colidir_com_valor_real(self):
        """None/ausente vira ()/"" — e nunca igual a um filtro de fato."""
        vazio = _chave_kpis(6, 2026, None, None, {}, _REV)
        assert vazio == (6, 2026, None, (), (), "", _REV)
        assert vazio == _chave_kpis(6, 2026, None, None, self._ss(), _REV)
        # perfil sem chave 'escopo' cai no default [] (nao KeyError)
        assert _chave_kpis(6, 2026, "admin", {"perfil": "admin"}, {}, _REV) == (
            6, 2026, "admin", (), (), "", _REV,
        )


@pytest.mark.unit
class TestRevisaoDosDados:
    """``_revisao_frame`` / ``_revisao_entradas`` — o 7o componente da
    chave. Nao e fronteira de seguranca (isso sao os componentes 3-6);
    e a de ATUALIDADE: sem ela, uma recarga dos loaders no fim do TTL
    nao invalidava nada e o KPI ficava preso na carga anterior."""

    def test_mesmo_frame_mesma_revisao(self):
        df = pd.DataFrame({"VALOR": [1.0, 2.0], "LOJA": ["A", "B"]})
        assert _revisao_frame(df) == _revisao_frame(df.copy())

    def test_linha_a_mais_muda_a_revisao(self):
        df = pd.DataFrame({"VALOR": [1.0], "LOJA": ["A"]})
        maior = pd.DataFrame({"VALOR": [1.0, 2.0], "LOJA": ["A", "B"]})
        assert _revisao_frame(df) != _revisao_frame(maior)

    def test_valor_corrigido_muda_a_revisao(self):
        """Mesma contagem de linhas, valor diferente — o caso do ETL
        corrigindo um contrato ja existente."""
        antes = pd.DataFrame({"VALOR": [100.0], "LOJA": ["A"]})
        depois = pd.DataFrame({"VALOR": [150.0], "LOJA": ["A"]})
        assert _revisao_frame(antes) != _revisao_frame(depois)

    def test_coluna_nova_muda_a_revisao(self):
        """O incidente das metas de nivel (META_PRATA...): o frame
        ganhou colunas e o consumidor seguia lendo o formato antigo."""
        antes = pd.DataFrame({"LOJA": ["A"]})
        depois = pd.DataFrame({"LOJA": ["A"], "META_PRATA": [1.0]})
        assert _revisao_frame(antes) != _revisao_frame(depois)

    def test_nan_nao_impede_cache_hit(self):
        """``float('nan') != float('nan')`` — deixado cru, faria a
        chave nunca mais bater e o cache nunca mais acertar."""
        df = pd.DataFrame({"VALOR": [float("nan")], "LOJA": ["A"]})
        assert _revisao_frame(df) == _revisao_frame(df.copy())

    def test_frame_vazio_e_none(self):
        assert _revisao_frame(None) == ()
        assert _revisao_frame(pd.DataFrame()) == (0, (), ())
        # vazio COM schema nao colide com vazio sem schema
        assert _revisao_frame(
            pd.DataFrame({"VALOR": []})
        ) != _revisao_frame(pd.DataFrame())

    def test_escalares_entram_como_estao(self):
        """``dia_atual`` / ``du_decorridos`` / ``peso_headcount`` sao a
        "data de referencia" da revisao: mudam o resultado sem mudar
        nenhum frame."""
        df = pd.DataFrame({"VALOR": [1.0]})
        assert _revisao_entradas(df, 10) != _revisao_entradas(df, 11)
        assert _revisao_entradas(df, None) != _revisao_entradas(df, 0)

    def test_revisao_e_hashavel(self):
        """A chave inteira vai para comparacao (==) hoje, mas precisa
        seguir hashavel para nao travar um cache por dict amanha."""
        df = pd.DataFrame({"VALOR": [1.0], "LOJA": ["A"]})
        assert hash(_revisao_entradas(df, 10, None)) is not None
