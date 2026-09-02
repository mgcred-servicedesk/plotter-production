"""
Testes de ``carregar_vinculos_consultores``
(``src/dashboard/loaders.py``) — o denominador individual lido do
ledger ``consultor_vigencia``.

O cliente Supabase e monkeypatchado: os testes verificam a CONTAGEM de
dias uteis por janela e os filtros de populacao (supervisor pela ancora,
loja inativa, backoffice), nao a query.
"""
from datetime import date

import pandas as pd
import pytest

from src.dashboard import loaders


class _RespostaFake:
    def __init__(self, data):
        self.data = data


class _QueryFake:
    """Encadeia .select/.lte/.or_ e devolve as linhas no .execute()."""

    def __init__(self, data):
        self._data = data

    def select(self, *_a, **_k):
        return self

    def lte(self, *_a, **_k):
        return self

    def or_(self, *_a, **_k):
        return self

    def execute(self):
        return _RespostaFake(self._data)


class _ClienteFake:
    def __init__(self, linhas):
        self._linhas = linhas

    def table(self, nome):
        assert nome == "consultor_vigencia"
        return _QueryFake(self._linhas)


def _linha(nome, loja, inicio, fim=None):
    return {
        "nome": nome,
        "nome_normalizado": " ".join(nome.upper().split()),
        "vigencia_inicio": inicio,
        "vigencia_fim": fim,
        "lojas": {"nome": loja},
    }


@pytest.fixture
def julho_sem_feriados(monkeypatch):
    """Julho/2026: 23 dias uteis, nenhum feriado."""
    monkeypatch.setattr(
        loaders, "carregar_feriados", lambda mes, ano: set()
    )
    monkeypatch.setattr(
        loaders,
        "carregar_lojas_ativas",
        lambda: pd.DataFrame(
            {
                "LOJA": ["LOJA A", "LOJA B", "VAI E VEM"],
                "REGIAO_ATUAL": ["R1", "R2", "R1"],
            }
        ),
    )
    monkeypatch.setattr(
        loaders,
        "carregar_supervisores",
        lambda mes, ano: pd.DataFrame(
            {"SUPERVISOR": ["CHEFE"], "LOJA": ["LOJA A"], "REGIAO": ["R1"]}
        ),
    )


def _fetch(monkeypatch, linhas):
    monkeypatch.setattr(loaders, "_sb", lambda: _ClienteFake(linhas))
    return loaders._fetch_vinculos_consultores(7, 2026)


@pytest.mark.unit
class TestVinculosConsultores:
    COLS = [
        "CONSULTOR", "LOJA", "REGIAO", "REGIAO_ATUAL",
        "DIAS_ELEGIVEIS", "DU_COMPETENCIA", "BASE_DIAS",
        "COBERTURA_AFASTAMENTO",
    ]

    def test_janela_aberta_cobre_a_competencia_inteira(
        self, julho_sem_feriados, monkeypatch
    ):
        out = _fetch(monkeypatch, [_linha("Ana", "LOJA A", "2020-01-01")])

        assert list(out.columns) == self.COLS
        assert int(out.iloc[0]["DIAS_ELEGIVEIS"]) == 23
        assert int(out.iloc[0]["DU_COMPETENCIA"]) == 23

    def test_base_e_cobertura_saem_declaradas_em_toda_linha(
        self, julho_sem_feriados, monkeypatch
    ):
        """A leitura errada do numero e o risco: a base vai junto."""
        out = _fetch(monkeypatch, [_linha("Ana", "LOJA A", "2020-01-01")])

        assert set(out["BASE_DIAS"]) == {"ELIGIBLE_LINK_DAYS"}
        assert set(out["COBERTURA_AFASTAMENTO"]) == {"NONE"}

    def test_entrada_no_meio_do_mes_conta_so_os_dias_de_vinculo(
        self, julho_sem_feriados, monkeypatch
    ):
        # 20/07/2026 e segunda: sobram 10 dias uteis ate 31/07.
        out = _fetch(monkeypatch, [_linha("Bia", "LOJA A", "2026-07-20")])

        assert int(out.iloc[0]["DIAS_ELEGIVEIS"]) == 10

    def test_janela_fechada_e_meio_aberta_no_fim(
        self, julho_sem_feriados, monkeypatch
    ):
        # Fim 2026-07-20 NAO cobre o proprio dia 20: [inicio, fim).
        out = _fetch(
            monkeypatch,
            [_linha("Bia", "LOJA A", "2020-01-01", "2026-07-20")],
        )

        assert int(out.iloc[0]["DIAS_ELEGIVEIS"]) == 13

    def test_transferencia_gera_dois_segmentos_que_somam_o_mes(
        self, julho_sem_feriados, monkeypatch
    ):
        out = _fetch(
            monkeypatch,
            [
                _linha("Ana", "LOJA A", "2020-01-01", "2026-07-20"),
                _linha("Ana", "LOJA B", "2026-07-20"),
            ],
        )

        assert len(out) == 2
        assert int(out["DIAS_ELEGIVEIS"].sum()) == 23
        assert set(out["LOJA"]) == {"LOJA A", "LOJA B"}

    def test_supervisor_na_ancora_sai_do_denominador(
        self, julho_sem_feriados, monkeypatch
    ):
        out = _fetch(
            monkeypatch,
            [
                _linha("Ana", "LOJA A", "2020-01-01"),
                _linha("Chefe", "LOJA A", "2020-01-01"),
            ],
        )

        assert list(out["CONSULTOR"]) == ["Ana"]

    def test_backoffice_sai(self, julho_sem_feriados, monkeypatch):
        out = _fetch(
            monkeypatch,
            [
                _linha("Ana", "LOJA A", "2020-01-01"),
                _linha("Duda", "VAI E VEM", "2020-01-01"),
            ],
        )

        assert list(out["CONSULTOR"]) == ["Ana"]

    def test_loja_inativa_sai_pelo_inner_join(
        self, julho_sem_feriados, monkeypatch
    ):
        out = _fetch(
            monkeypatch,
            [
                _linha("Ana", "LOJA A", "2020-01-01"),
                _linha("Edu", "LOJA FECHADA", "2020-01-01"),
            ],
        )

        assert list(out["CONSULTOR"]) == ["Ana"]

    def test_regiao_vem_da_loja_e_alimenta_o_rls(
        self, julho_sem_feriados, monkeypatch
    ):
        out = _fetch(
            monkeypatch,
            [
                _linha("Ana", "LOJA A", "2020-01-01"),
                _linha("Bia", "LOJA B", "2020-01-01"),
            ],
        ).set_index("CONSULTOR")

        assert out.loc["Ana", "REGIAO"] == "R1"
        assert out.loc["Bia", "REGIAO"] == "R2"
        # aplicar_rls do gerente recorta por REGIAO_ATUAL.
        assert out.loc["Bia", "REGIAO_ATUAL"] == "R2"

    def test_janela_fora_da_competencia_nao_entra(
        self, julho_sem_feriados, monkeypatch
    ):
        out = _fetch(
            monkeypatch,
            [_linha("Ana", "LOJA A", "2020-01-01", "2026-06-30")],
        )

        assert out.empty
        assert list(out.columns) == self.COLS

    def test_feriado_reduz_os_dias_uteis(self, monkeypatch):
        monkeypatch.setattr(
            loaders,
            "carregar_feriados",
            lambda mes, ano: {date(2026, 7, 9)},
        )
        monkeypatch.setattr(
            loaders,
            "carregar_lojas_ativas",
            lambda: pd.DataFrame(
                {"LOJA": ["LOJA A"], "REGIAO_ATUAL": ["R1"]}
            ),
        )
        monkeypatch.setattr(
            loaders, "carregar_supervisores",
            lambda mes, ano: pd.DataFrame(columns=["SUPERVISOR", "LOJA"]),
        )

        out = _fetch(monkeypatch, [_linha("Ana", "LOJA A", "2020-01-01")])

        assert int(out.iloc[0]["DIAS_ELEGIVEIS"]) == 22
        assert int(out.iloc[0]["DU_COMPETENCIA"]) == 22

    def test_ledger_vazio_devolve_frame_tipado(
        self, julho_sem_feriados, monkeypatch
    ):
        out = _fetch(monkeypatch, [])

        assert out.empty
        assert list(out.columns) == self.COLS
