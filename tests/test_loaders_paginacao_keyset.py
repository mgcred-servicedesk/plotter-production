"""Testes da paginação keyset com retry de statement_timeout.

Contexto: a carga do dashboard morria com `57014 canceling statement due
to statement timeout` — cancelamento server-side transitório (compute
Nano + ETL escrevendo em `contratos` em paralelo) que abortava a carga
inteira. `_paginar_keyset` passou a reexecutar a página.

O que exige teste aqui não é o retry em si, mas a armadilha que ele
cria: a última tentativa reduz o lote, e comparar `len(batch)` com
`_PAGE_SIZE` (em vez do limite efetivamente usado) encerraria a
paginação cedo — truncando dados EM SILÊNCIO. É o caso
`test_pagina_reduzida_cheia_nao_encerra_a_paginacao`.

Nenhuma conexão é aberta: `_paginar_keyset` só executa o callable que
recebe, então um banco falso em memória cobre todo o contrato.
"""
import pytest
from postgrest.exceptions import APIError

from src.dashboard import loaders


def _timeout() -> APIError:
    """APIError idêntica à que o PostgREST levanta no 57014."""
    return APIError(
        {
            "message": "canceling statement due to statement timeout",
            "code": "57014",
            "hint": None,
            "details": None,
        }
    )


def _erro_permanente() -> APIError:
    """Erro determinístico — retentar só atrasaria a falha."""
    return APIError(
        {
            "message": 'column "inexistente" does not exist',
            "code": "42703",
            "hint": None,
            "details": None,
        }
    )


class _QueryFake:
    """Query fluente: só registra o cursor e delega ao banco falso."""

    def __init__(self, banco, limite):
        self._banco = banco
        self._limite = limite
        self._cursor = None

    def gt(self, coluna, valor):
        self._cursor = valor
        return self

    def execute(self):
        return self._banco.executar(self._limite, self._cursor)


class _Resposta:
    def __init__(self, data):
        self.data = data


class _BancoFake:
    """Linhas {'id': 1..total} servidas por keyset.

    ``roteiro`` é a lista de exceções a levantar, uma por chamada, na
    ordem (None = servir a página normalmente). É o que permite
    programar "as duas primeiras tentativas estouram o timeout".
    """

    def __init__(self, total, roteiro=None):
        self.linhas = [{"id": i} for i in range(1, total + 1)]
        self.roteiro = list(roteiro or [])
        self.chamadas = []

    def montar(self, limite):
        return _QueryFake(self, limite)

    def executar(self, limite, cursor):
        self.chamadas.append((limite, cursor))
        if self.roteiro:
            erro = self.roteiro.pop(0)
            if erro is not None:
                raise erro
        candidatas = [
            linha
            for linha in self.linhas
            if cursor is None or linha["id"] > cursor
        ]
        return _Resposta(candidatas[:limite])


@pytest.fixture(autouse=True)
def _sem_espera(monkeypatch):
    """Neutraliza o backoff: registra as esperas em vez de dormir."""
    esperas = []
    monkeypatch.setattr(loaders.time, "sleep", esperas.append)
    return esperas


class TestPaginacaoSemFalha:
    def test_pagina_unica_parcial(self):
        banco = _BancoFake(total=3)

        linhas = loaders._paginar_keyset(banco.montar, "id")

        assert [linha["id"] for linha in linhas] == [1, 2, 3]
        assert len(banco.chamadas) == 1

    def test_varias_paginas_cheias(self):
        total = loaders._PAGE_SIZE * 2 + 7
        banco = _BancoFake(total=total)

        linhas = loaders._paginar_keyset(banco.montar, "id")

        assert len(linhas) == total
        assert [linha["id"] for linha in linhas] == list(range(1, total + 1))
        # 3 páginas: duas cheias + o resto.
        assert len(banco.chamadas) == 3
        # Keyset de verdade: da 2ª em diante vai cursor, nunca offset.
        assert banco.chamadas[0][1] is None
        assert banco.chamadas[1][1] == loaders._PAGE_SIZE

    def test_resultset_vazio(self):
        banco = _BancoFake(total=0)

        assert loaders._paginar_keyset(banco.montar, "id") == []


class TestRetryStatementTimeout:
    def test_timeout_isolado_e_reexecutado(self, _sem_espera):
        banco = _BancoFake(total=5, roteiro=[_timeout()])

        linhas = loaders._paginar_keyset(banco.montar, "id")

        assert [linha["id"] for linha in linhas] == [1, 2, 3, 4, 5]
        assert len(banco.chamadas) == 2
        assert _sem_espera == [1.5]

    def test_nao_duplica_linhas_ao_reexecutar(self):
        """A tentativa que falhou não pode ter avançado o cursor."""
        banco = _BancoFake(
            total=loaders._PAGE_SIZE + 4,
            roteiro=[None, _timeout()],
        )

        linhas = loaders._paginar_keyset(banco.montar, "id")

        ids = [linha["id"] for linha in linhas]
        assert ids == list(range(1, loaders._PAGE_SIZE + 5))
        assert len(ids) == len(set(ids))

    def test_timeout_persistente_sobe(self, _sem_espera):
        """Banco degradado é para aparecer, não para virar dado parcial."""
        banco = _BancoFake(total=5, roteiro=[_timeout()] * 3)

        with pytest.raises(APIError) as exc:
            loaders._paginar_keyset(banco.montar, "id")

        assert exc.value.code == "57014"
        assert len(banco.chamadas) == len(loaders._TENTATIVAS_PAGINA)

    def test_erro_deterministico_nao_e_reexecutado(self, _sem_espera):
        banco = _BancoFake(total=5, roteiro=[_erro_permanente()])

        with pytest.raises(APIError) as exc:
            loaders._paginar_keyset(banco.montar, "id")

        assert exc.value.code == "42703"
        assert len(banco.chamadas) == 1
        assert _sem_espera == []

    def test_ultima_tentativa_reduz_o_lote(self):
        banco = _BancoFake(total=5, roteiro=[_timeout(), _timeout()])

        loaders._paginar_keyset(banco.montar, "id")

        limites = [limite for limite, _ in banco.chamadas]
        assert limites == [loaders._PAGE_SIZE, loaders._PAGE_SIZE, 250]

    def test_pagina_reduzida_cheia_nao_encerra_a_paginacao(self):
        """Regressão: fim do resultset é len(batch) < limite USADO.

        Com 300 linhas e as duas primeiras tentativas estourando, a 3ª
        volta com 250 — lote cheio para o limite reduzido. Comparar com
        _PAGE_SIZE (1000) daria "página parcial" e devolveria 250 das
        300 linhas, sem erro nenhum.
        """
        banco = _BancoFake(total=300, roteiro=[_timeout(), _timeout()])

        linhas = loaders._paginar_keyset(banco.montar, "id")

        assert len(linhas) == 300
        assert [linha["id"] for linha in linhas] == list(range(1, 301))
        # 4ª chamada: página nova, tentativas resetadas (lote cheio).
        assert banco.chamadas[3] == (loaders._PAGE_SIZE, 250)
