"""
Paginação dos loaders de cadastro (item 6 da revisão de 09/2026).

`carregar_consultores_ativos` e `_fetch_vinculos_consultores` liam a
tabela inteira em UMA resposta. Passando do teto da API, a leitura
truncava **em silêncio**: pessoas sumiriam do universo de ativos e dias
elegíveis sumiriam do denominador de produtividade, sem erro nenhum —
só médias mais altas do que deveriam.

## Por que a suíte não pegava

Os duplos de Supabase ignoravam `.order`/`.limit`/`.gt` e devolviam
tudo num `.execute()`. Um loader sem paginação passava exatamente como
um paginado. `ClienteFakePaginado` (conftest) honra o contrato do
keyset, então a ausência de paginação vira falha.

## Custo no plano Nano

Paginar **não** acrescenta request enquanto os dados couberem numa
página: `_paginar_keyset` encerra quando a página volta incompleta
(`len(batch) < limite`). O request extra só aparece quando há mais de
uma página — que é exatamente o caso em que hoje se perdiam dados.
`ClienteFakePaginado.paginas` mede isso, e é o que
`test_uma_pagina_nao_custa_request_extra` trava.
"""
import pandas as pd
import pytest

from src.dashboard import loaders
from tests.conftest import ClienteFakePaginado


def _consultor(i: int, nome: str | None = None, loja: str = "LOJA A"):
    return {
        "id": f"{i:08d}",
        "nome": nome or f"CONSULTOR {i:04d}",
        "status": "Ativo (a)",
        "updated_at": "2026-09-01T00:00:00+00:00",
        "lojas": {"nome": loja, "ativo": True, "regioes": {"nome": "R1"}},
    }


@pytest.fixture(autouse=True)
def _sem_cache():
    """`carregar_consultores_ativos` é `@st.cache_data` (TTL 30min) e
    não recebe argumentos: sem limpar, o resultado do primeiro teste
    serviria todos os outros."""
    loaders.carregar_consultores_ativos.clear()
    yield
    loaders.carregar_consultores_ativos.clear()


def _carregar(monkeypatch, linhas):
    cliente = ClienteFakePaginado(linhas, tabela="consultores")
    monkeypatch.setattr(loaders, "_sb", lambda: cliente)
    return loaders.carregar_consultores_ativos(), cliente


@pytest.mark.unit
class TestConsultoresAtivosPaginado:
    def test_traz_todo_mundo_alem_da_primeira_pagina(self, monkeypatch):
        """O bug: com `_PAGE_SIZE` linhas ou mais, quem ficasse fora da
        primeira página simplesmente não existia para o dashboard."""
        total = loaders._PAGE_SIZE + 37
        df, _ = _carregar(monkeypatch, [_consultor(i) for i in range(total)])
        assert len(df) == total

    def test_nenhum_nome_se_perde_nem_se_repete_entre_paginas(
        self, monkeypatch
    ):
        """Chave repetida no keyset pularia linhas na virada da página —
        por isso a paginação é por `id` (PK) e não por `nome`."""
        total = loaders._PAGE_SIZE * 2 + 5
        esperados = {f"CONSULTOR {i:04d}" for i in range(total)}
        df, _ = _carregar(monkeypatch, [_consultor(i) for i in range(total)])
        assert set(df["CONSULTOR"]) == esperados
        assert len(df) == len(esperados)

    def test_uma_pagina_nao_custa_request_extra(self, monkeypatch):
        """O que interessa no Nano: com o volume de hoje (~112 ativos),
        paginar custa exatamente o mesmo que a leitura única de antes."""
        df, cliente = _carregar(
            monkeypatch, [_consultor(i) for i in range(112)]
        )
        assert len(df) == 112
        assert cliente.paginas == 1

    def test_duas_paginas_quando_passa_do_limite(self, monkeypatch):
        """O request a mais aparece só onde antes havia perda de dado."""
        _, cliente = _carregar(
            monkeypatch,
            [_consultor(i) for i in range(loaders._PAGE_SIZE + 1)],
        )
        assert cliente.paginas == 2

    def test_pagina_exatamente_cheia_confirma_o_fim(self, monkeypatch):
        """Página cheia é indistinguível de "há mais": é preciso pedir a
        seguinte para saber. Custa 1 request e evita truncar."""
        df, cliente = _carregar(
            monkeypatch, [_consultor(i) for i in range(loaders._PAGE_SIZE)]
        )
        assert len(df) == loaders._PAGE_SIZE
        assert cliente.paginas == 2

    def test_tabela_vazia_devolve_frame_tipado(self, monkeypatch):
        df, cliente = _carregar(monkeypatch, [])
        assert df.empty
        assert list(df.columns) == [
            "CONSULTOR", "LOJA", "REGIAO", "REGIAO_ATUAL",
        ]
        assert cliente.paginas == 1

    def test_colapso_de_nome_duplicado_sobrevive_a_paginacao(
        self, monkeypatch
    ):
        """A regra que torna `nome` impróprio como chave de keyset: a
        tabela TEM nomes duplicados, e vence o `updated_at` mais
        recente — inclusive quando as duas linhas caem em páginas
        diferentes."""
        antiga = _consultor(0, nome="ANA")
        nova = _consultor(loaders._PAGE_SIZE + 1, nome="ANA")
        nova["status"] = "Desligado"
        nova["updated_at"] = "2026-09-10T00:00:00+00:00"
        recheio = [_consultor(i) for i in range(1, loaders._PAGE_SIZE + 1)]

        df, cliente = _carregar(monkeypatch, [antiga, *recheio, nova])
        assert cliente.paginas >= 2
        # O desligamento mais recente vence: ANA sai do universo.
        assert "ANA" not in set(df["CONSULTOR"])

    def test_inativos_continuam_fora(self, monkeypatch):
        desligado = _consultor(1)
        desligado["status"] = "Desligado"
        df, _ = _carregar(monkeypatch, [_consultor(0), desligado])
        assert len(df) == 1

    def test_loja_inativa_continua_fora(self, monkeypatch):
        fechada = _consultor(1)
        fechada["lojas"]["ativo"] = False
        df, _ = _carregar(monkeypatch, [_consultor(0), fechada])
        assert len(df) == 1


@pytest.mark.unit
class TestVinculosPaginado:
    def _linha(self, i: int):
        return {
            "id": f"{i:08d}",
            "nome": f"CONSULTOR {i:04d}",
            "nome_normalizado": f"CONSULTOR {i:04d}",
            "vigencia_inicio": "2020-01-01",
            "vigencia_fim": None,
            "lojas": {"nome": "LOJA A"},
        }

    @pytest.fixture
    def julho(self, monkeypatch):
        monkeypatch.setattr(
            loaders, "carregar_feriados", lambda mes, ano: set()
        )
        monkeypatch.setattr(
            loaders, "carregar_lojas_ativas",
            lambda: pd.DataFrame(
                {"LOJA": ["LOJA A"], "REGIAO_ATUAL": ["R1"]}
            ),
        )
        monkeypatch.setattr(
            loaders, "carregar_supervisores",
            lambda mes, ano: pd.DataFrame(
                columns=["SUPERVISOR", "LOJA", "REGIAO"]
            ),
        )

    def test_ledger_alem_de_uma_pagina_nao_perde_pessoas(
        self, julho, monkeypatch
    ):
        """O ledger tinha ~400 linhas quando o loader nasceu e a
        docstring dizia "não há o que paginar". Era medição, não
        garantia: cresce uma linha a cada transferência."""
        total = loaders._PAGE_SIZE + 42
        cliente = ClienteFakePaginado(
            [self._linha(i) for i in range(total)],
            tabela="consultor_vigencia",
        )
        monkeypatch.setattr(loaders, "_sb", lambda: cliente)

        out = loaders._fetch_vinculos_consultores(7, 2026)
        assert len(out) == total
        assert cliente.paginas >= 2

    def test_volume_de_hoje_nao_custa_request_extra(
        self, julho, monkeypatch
    ):
        cliente = ClienteFakePaginado(
            [self._linha(i) for i in range(400)],
            tabela="consultor_vigencia",
        )
        monkeypatch.setattr(loaders, "_sb", lambda: cliente)

        out = loaders._fetch_vinculos_consultores(7, 2026)
        assert len(out) == 400
        assert cliente.paginas == 1


@pytest.mark.unit
class TestOutrosDoisEncontradosNaVarredura:
    """Dois loaders que a revisão não nomeou, mas que a varredura pegou
    com o MESMO defeito — e que seria incoerente deixar de fora:

    - `carregar_consultores_cadastro` lê a **mesma tabela** que
      `carregar_consultores_ativos`, já paginada aqui ao lado;
    - `carregar_supervisores` lê um ledger `*_vigencia` com o mesmo
      formato do `consultor_vigencia`. Truncar ali tiraria supervisor
      da lista de EXCLUSÃO — ele voltaria a contar como consultor nas
      médias, inflando o denominador.
    """

    def test_cadastro_traz_todo_mundo_alem_da_primeira_pagina(
        self, monkeypatch
    ):
        loaders.carregar_consultores_cadastro.clear()
        total = loaders._PAGE_SIZE + 12
        linhas = [
            {
                "id": f"{i:08d}",
                "nome": f"CONSULTOR {i:04d}",
                "status": "Ativo (a)",
                "updated_at": "2026-09-01T00:00:00+00:00",
            }
            for i in range(total)
        ]
        cliente = ClienteFakePaginado(linhas, tabela="consultores")
        monkeypatch.setattr(loaders, "_sb", lambda: cliente)
        try:
            assert len(loaders.carregar_consultores_cadastro()) == total
        finally:
            loaders.carregar_consultores_cadastro.clear()

    def test_supervisores_alem_de_uma_pagina(self, monkeypatch):
        loaders.carregar_supervisores.clear()
        total = loaders._PAGE_SIZE + 3
        linhas = [
            {
                "id": f"{i:08d}",
                "nome": f"SUPERVISOR {i:04d}",
                "lojas": {"nome": "LOJA A", "regioes": {"nome": "R1"}},
            }
            for i in range(total)
        ]
        cliente = ClienteFakePaginado(
            linhas, tabela="supervisor_vigencia",
        )
        monkeypatch.setattr(loaders, "_sb", lambda: cliente)
        try:
            out = loaders.carregar_supervisores(7, 2026)
            assert len(out) == total
            assert cliente.paginas >= 2
        finally:
            loaders.carregar_supervisores.clear()

    def test_supervisores_volume_de_hoje_nao_custa_request_extra(
        self, monkeypatch
    ):
        loaders.carregar_supervisores.clear()
        linhas = [
            {
                "id": f"{i:08d}",
                "nome": f"SUPERVISOR {i:04d}",
                "lojas": {"nome": "LOJA A", "regioes": {"nome": "R1"}},
            }
            for i in range(20)
        ]
        cliente = ClienteFakePaginado(
            linhas, tabela="supervisor_vigencia",
        )
        monkeypatch.setattr(loaders, "_sb", lambda: cliente)
        try:
            assert len(loaders.carregar_supervisores(7, 2026)) == 20
            assert cliente.paginas == 1
        finally:
            loaders.carregar_supervisores.clear()
