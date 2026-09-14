"""
Ausência de feriado × falha ao consultar (``shared/dias_uteis.py``).

Até 09/2026 as duas coisas produziam o mesmo `set()` vazio, e o vazio
vinha de DENTRO da função cacheada: uma indisponibilidade de 1 segundo
virava "nenhum feriado neste mês" por **24 horas**. Sem erro na tela —
só números errados, porque sem feriados o `total_du` infla, a meta
diária cai e a projeção sobe.

O que estes testes travam:

1. `set()` significa "nenhum feriado" e pode ser cacheado;
2. falha levanta `FeriadosIndisponiveis`, que o `st.cache_data` **não**
   guarda — o próximo rerun tenta de novo;
3. `carregar_feriados` ainda devolve `set()` (derrubar o dashboard por
   causa do calendário seria pior), mas registra antes, para a UI
   avisar que os dias úteis daquele período estão estimados.

Os testes de cálculo de dias úteis em si estão em `tests/test_loaders.py`
e nos de KPI; aqui é só o contrato de falha.
"""
import pytest

import src.shared.dias_uteis as du
from src.shared.dias_uteis import (
    FeriadosIndisponiveis,
    calcular_dias_uteis,
    carregar_feriados,
    carregar_feriados_supabase,
    esquecer_falhas_feriados,
    periodos_com_feriados_indisponiveis,
)


@pytest.fixture(autouse=True)
def _limpar_registro():
    """Zera registro de degradação E o cache do Streamlit.

    O cache é keyed por (mes, ano) e sobrevive entre testes: sem
    limpá-lo, o sucesso de um teste serviria a falha esperada do
    seguinte — que foi exatamente o que aconteceu ao escrever estes.
    """
    import streamlit as st

    st.cache_data.clear()
    esquecer_falhas_feriados()
    yield
    st.cache_data.clear()
    esquecer_falhas_feriados()


class _RespFake:
    def __init__(self, data):
        self.data = data


def _cliente(resposta=None, erro=None):
    """Cliente Supabase falso: devolve `resposta` ou levanta `erro`."""
    class _Query:
        def select(self, *_, **__): return self
        def gte(self, *_, **__): return self
        def lt(self, *_, **__): return self

        def execute(self):
            if erro is not None:
                raise erro
            return _RespFake(resposta)

    class _Cliente:
        def table(self, *_): return _Query()

    return _Cliente()


def _mockar_cliente(monkeypatch, **kwargs):
    import src.config.supabase_client as mod
    monkeypatch.setattr(
        mod, "get_supabase_client", lambda: _cliente(**kwargs)
    )


@pytest.mark.unit
class TestCarregarFeriadosSupabase:
    def test_devolve_as_datas_do_periodo(self, monkeypatch):
        _mockar_cliente(monkeypatch, resposta=[
            {"data": "2026-09-07"}, {"data": "2026-09-21"},
        ])
        from datetime import date
        assert carregar_feriados_supabase(9, 2026) == {
            date(2026, 9, 7), date(2026, 9, 21),
        }

    def test_vazio_significa_nenhum_feriado(self, monkeypatch):
        """Resposta vazia é resposta VÁLIDA — mês sem feriado existe."""
        _mockar_cliente(monkeypatch, resposta=[])
        assert carregar_feriados_supabase(9, 2026) == set()

    def test_falha_levanta_em_vez_de_devolver_vazio(self, monkeypatch):
        """O coração da correção: antes, isto devolvia `set()` e o
        chamador não tinha como distinguir de 'mês sem feriado'."""
        _mockar_cliente(monkeypatch, erro=ConnectionError("sem rede"))
        with pytest.raises(FeriadosIndisponiveis):
            carregar_feriados_supabase(9, 2026)

    def test_preserva_a_causa_original(self, monkeypatch):
        _mockar_cliente(monkeypatch, erro=ConnectionError("sem rede"))
        with pytest.raises(FeriadosIndisponiveis) as exc:
            carregar_feriados_supabase(9, 2026)
        assert isinstance(exc.value.__cause__, ConnectionError)


@pytest.mark.unit
class TestCarregarFeriadosNaoDerruba:
    def test_falha_devolve_vazio_e_registra(self, monkeypatch):
        _mockar_cliente(monkeypatch, erro=ConnectionError("sem rede"))
        assert carregar_feriados(9, 2026) == set()
        assert (9, 2026) in periodos_com_feriados_indisponiveis()

    def test_sucesso_nao_registra_degradacao(self, monkeypatch):
        _mockar_cliente(monkeypatch, resposta=[{"data": "2026-09-07"}])
        carregar_feriados(9, 2026)
        assert periodos_com_feriados_indisponiveis() == set()

    def test_mes_sem_feriado_nao_e_degradacao(self, monkeypatch):
        """A distinção que dá nome ao arquivo: vazio legítimo não pode
        acender o aviso da UI."""
        _mockar_cliente(monkeypatch, resposta=[])
        assert carregar_feriados(9, 2026) == set()
        assert periodos_com_feriados_indisponiveis() == set()

    def test_registra_cada_periodo_que_falhou(self, monkeypatch):
        _mockar_cliente(monkeypatch, erro=ConnectionError("sem rede"))
        carregar_feriados(9, 2026)
        carregar_feriados(8, 2026)
        assert periodos_com_feriados_indisponiveis() == {(9, 2026), (8, 2026)}

    def test_loga_o_erro(self, monkeypatch, caplog):
        """'Nunca engula erros silenciosamente' — o log é o que permite
        descobrir depois que os números do dia estavam estimados."""
        _mockar_cliente(monkeypatch, erro=ConnectionError("sem rede"))
        with caplog.at_level("ERROR"):
            carregar_feriados(9, 2026)
        assert "feriados" in caplog.text.lower()

    def test_sucesso_posterior_apaga_a_marca(self, monkeypatch):
        """O aviso não pode ficar na tela pelo resto da sessão depois
        de o Supabase voltar — o usuário desconfiaria de número certo."""
        chamadas = []

        def _fake(mes, ano):
            chamadas.append(1)
            if len(chamadas) == 1:
                raise FeriadosIndisponiveis("falha transitória")
            return set()

        monkeypatch.setattr(du, "_carregar_feriados_cached", _fake)
        carregar_feriados(9, 2026)
        assert (9, 2026) in periodos_com_feriados_indisponiveis()
        carregar_feriados(9, 2026)
        assert (9, 2026) not in periodos_com_feriados_indisponiveis()

    def test_esquecer_falhas_limpa_o_registro(self, monkeypatch):
        _mockar_cliente(monkeypatch, erro=ConnectionError("sem rede"))
        carregar_feriados(9, 2026)
        esquecer_falhas_feriados()
        assert periodos_com_feriados_indisponiveis() == set()


@pytest.mark.unit
class TestFalhaNaoFicaCacheadaComoSucesso:
    def test_proxima_tentativa_refaz_a_consulta(self, monkeypatch):
        """O bug tinha 24h de duração porque o vazio era cacheado.

        Aqui a primeira chamada falha e a segunda tem de EXECUTAR de
        novo — não pode servir o vazio guardado.
        """
        chamadas = []

        def _fake(mes, ano):
            chamadas.append((mes, ano))
            if len(chamadas) == 1:
                raise FeriadosIndisponiveis("falha transitória")
            from datetime import date
            return {date(2026, 9, 7)}

        monkeypatch.setattr(du, "_carregar_feriados_cached", _fake)

        assert carregar_feriados(9, 2026) == set()
        from datetime import date
        assert carregar_feriados(9, 2026) == {date(2026, 9, 7)}
        assert len(chamadas) == 2


@pytest.mark.unit
class TestImpactoNosDiasUteis:
    """Por que isso importa: feriado a menos = dia útil a mais."""

    def test_feriado_reduz_o_total_de_du(self):
        from datetime import date
        sem = calcular_dias_uteis(2026, 9, 30, feriados=set())[0]
        com = calcular_dias_uteis(
            2026, 9, 30, feriados={date(2026, 9, 7)},
        )[0]
        assert com == sem - 1

    def test_falha_conta_o_mes_sem_feriados(self, monkeypatch):
        """O efeito concreto da degradação: com a consulta falhando, o
        total_du é o do mês inteiro — e é por isso que a UI avisa."""
        _mockar_cliente(monkeypatch, erro=ConnectionError("sem rede"))
        total_degradado = calcular_dias_uteis(2026, 9, 30)[0]
        assert total_degradado == calcular_dias_uteis(
            2026, 9, 30, feriados=set(),
        )[0]
        assert (9, 2026) in periodos_com_feriados_indisponiveis()
