"""
Calculo de dias uteis com suporte a feriados.

Feriados sao carregados do Supabase e cacheados por 24h no Streamlit.

## Ausencia de feriado x falha ao consultar

Ate 09/2026 as duas coisas produziam o mesmo resultado: um `set()`
vazio. Como o `set()` vinha de dentro da funcao cacheada, uma
indisponibilidade de 1 segundo virava "nenhum feriado neste mes" por
**24 horas** — e nao ha erro na tela, so numeros errados: sem feriados
o `total_du` fica inflado, a meta diaria cai e a projecao sobe.

Agora sao estados distintos:

- ``set()`` devolvido por `carregar_feriados_supabase` significa, de
  fato, **nenhum feriado no periodo** — e isso pode ser cacheado;
- falha na consulta levanta `FeriadosIndisponiveis`. Excecao **nao e
  cacheada** pelo ``st.cache_data`` (verificado), entao o proximo rerun
  tenta de novo em vez de servir o vazio por 24h.

`carregar_feriados` continua devolvendo `set()` na falha — derrubar o
dashboard inteiro por causa do calendario seria pior —, mas antes
**registra**: log de erro e marca em `periodos_com_feriados_indisponiveis()`,
que a UI le para avisar que os dias uteis daquele periodo estao
estimados sem feriados.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Periodos (mes, ano) cuja carga de feriados falhou nesta sessao. Vive
# em `st.session_state` quando ha Streamlit (cada usuario ve o aviso do
# proprio rerun) e num set de modulo fora dele (CLI/testes).
_CHAVE_DEGRADACAO = "_feriados_indisponiveis"
_degradacao_sem_streamlit: set[tuple[int, int]] = set()


class FeriadosIndisponiveis(RuntimeError):
    """A consulta a tabela de feriados falhou.

    Distinta de "nao ha feriados no periodo", que e um ``set()`` vazio
    devolvido normalmente. Existe para que a falha nao seja cacheada
    como se fosse resposta valida — ver o topo do modulo.
    """


def _registro_degradacao() -> set[tuple[int, int]]:
    """Set de periodos degradados, no melhor armazenamento disponivel."""
    try:
        import streamlit as st

        if _CHAVE_DEGRADACAO not in st.session_state:
            st.session_state[_CHAVE_DEGRADACAO] = set()
        return st.session_state[_CHAVE_DEGRADACAO]
    except Exception:
        return _degradacao_sem_streamlit


def _registrar_falha(mes: int, ano: int, exc: BaseException) -> None:
    """Loga a falha e marca o periodo como degradado."""
    logger.error(
        "Falha ao carregar feriados de %02d/%d — dias uteis do periodo "
        "seguem SEM feriados (total_du inflado, meta diaria subestimada): %s",
        mes, ano, exc,
    )
    try:
        _registro_degradacao().add((mes, ano))
    except Exception:
        pass


def _registrar_sucesso(mes: int, ano: int) -> None:
    """Apaga a marca de degradacao do periodo apos uma carga boa.

    Sem isso o aviso ficaria na tela pelo resto da sessao mesmo depois
    de o Supabase voltar — e o usuario desconfiaria de numero que ja
    esta certo.
    """
    try:
        _registro_degradacao().discard((mes, ano))
    except Exception:
        pass


def periodos_com_feriados_indisponiveis() -> set[tuple[int, int]]:
    """``{(mes, ano)}`` cuja carga de feriados falhou nesta sessao.

    A UI usa para avisar que os dias uteis daquele periodo estao
    estimados sem feriados. Vazio = nenhuma falha registrada.
    """
    return set(_registro_degradacao())


def esquecer_falhas_feriados() -> None:
    """Zera o registro de degradacao (apos recarregar com sucesso)."""
    try:
        _registro_degradacao().clear()
    except Exception:
        pass


def carregar_feriados_supabase(
    mes: int,
    ano: int,
) -> set[date]:
    """Busca feriados do mes/ano no Supabase.

    Returns:
        Conjunto de datas de feriados do periodo. **Vazio significa
        "nenhum feriado"** — nao "nao consegui consultar".

    Raises:
        FeriadosIndisponiveis: a consulta falhou. Nao devolve `set()`
            de proposito: quem chama por dentro do cache precisa que a
            falha suba, para nao ficar 24h cacheada como sucesso.
    """
    from src.config.supabase_client import get_supabase_client

    primeiro = date(ano, mes, 1)
    if mes == 12:
        ultimo = date(ano + 1, 1, 1)
    else:
        ultimo = date(ano, mes + 1, 1)

    try:
        sb = get_supabase_client()
        resp = (
            sb.table("feriados")
            .select("data")
            .gte("data", primeiro.isoformat())
            .lt("data", ultimo.isoformat())
            .execute()
        )
    except Exception as exc:
        raise FeriadosIndisponiveis(
            f"consulta a feriados de {mes:02d}/{ano} falhou"
        ) from exc

    datas = set()
    for row in resp.data or []:
        d = row.get("data")
        if d:
            datas.add(date.fromisoformat(str(d)))
    return datas


_feriados_cacheados = None


def _funcao_cacheada():
    """A funcao ``st.cache_data`` de feriados, criada UMA vez.

    Ate 09/2026 o decorator era aplicado dentro de
    ``_carregar_feriados_cached`` a cada chamada. O cache funcionava
    (o Streamlit identifica a funcao pelo codigo), mas nao havia objeto
    com ``.clear()`` para limpar so ele — e a tentativa de limpar
    falhava em silencio. Guardar a funcao decorada da o ``.clear()``.

    Importa st apenas quando necessario, como antes.
    """
    global _feriados_cacheados
    if _feriados_cacheados is None:
        import streamlit as st

        @st.cache_data(ttl=86400, show_spinner=False)
        def _cached(mes: int, ano: int) -> set[date]:
            return carregar_feriados_supabase(mes, ano)

        _feriados_cacheados = _cached
    return _feriados_cacheados


def _carregar_feriados_cached(
    mes: int,
    ano: int,
) -> set[date]:
    """Wrapper cacheado para uso no Streamlit."""
    return _funcao_cacheada()(mes, ano)


def carregar_feriados(
    mes: int,
    ano: int,
) -> set[date]:
    """Ponto de entrada unico para obter feriados.

    Tenta usar o cache do Streamlit; fora dele, busca direto.

    Devolve `set()` na falha — derrubar o dashboard por causa do
    calendario seria pior que estimar os dias uteis sem feriados — mas
    **registra antes**: log de erro e marca em
    `periodos_com_feriados_indisponiveis()`, para a UI avisar. A falha
    em si nao fica cacheada, entao o proximo rerun tenta de novo.
    """
    try:
        feriados = _carregar_feriados_cached(mes, ano)
        _registrar_sucesso(mes, ano)
        return feriados
    except FeriadosIndisponiveis as exc:
        # Supabase falhou. Nao repetir aqui: `st.cache_data` nao
        # guardou nada, entao o proximo rerun ja e uma nova tentativa.
        _registrar_falha(mes, ano, exc)
        return set()
    except Exception:
        # Streamlit ausente (CLI/teste): cai para a busca direta.
        pass

    try:
        feriados = carregar_feriados_supabase(mes, ano)
        _registrar_sucesso(mes, ano)
        return feriados
    except FeriadosIndisponiveis as exc:
        _registrar_falha(mes, ano, exc)
        return set()


def limpar_cache_feriados() -> None:
    """Limpa SO o cache de feriados, apos CRUD na tela admin.

    Nao limpa quem deriva dias uteis de feriados em outro modulo
    (headcount, vinculos): isso e de ``loaders.limpar_caches_de_calendario``,
    e quem compoe as duas e o CRUD (``feriados_mgmt``).

    Sem ``try/except``: foi um ``except: pass`` que escondeu, por anos,
    que a limpeza cirurgica nunca rodava.
    """
    _funcao_cacheada().clear()


def calcular_dias_uteis(
    ano: int,
    mes: int,
    dia_atual: Optional[int] = None,
    feriados: Optional[set[date]] = None,
) -> tuple[int, int, int]:
    """Calcula total de DU, DU decorridos e restantes.

    Args:
        ano: Ano do periodo.
        mes: Mes (1-12).
        dia_atual: Dia de referencia. Se None, usa hoje.
        feriados: Conjunto de datas de feriados a excluir.
            Se None, tenta carregar do Supabase.

    Returns:
        Tupla (total_dias_uteis, dias_decorridos,
        dias_restantes).
    """
    if feriados is None:
        feriados = carregar_feriados(mes, ano)

    if dia_atual is None:
        data_ref = datetime.now()
    else:
        data_ref = datetime(ano, mes, int(dia_atual))

    primeiro_dia = datetime(ano, mes, 1)
    if mes == 12:
        ultimo_dia = datetime(ano + 1, 1, 1) - pd.Timedelta(
            days=1,
        )
    else:
        ultimo_dia = datetime(ano, mes + 1, 1) - pd.Timedelta(
            days=1,
        )

    # Dias uteis do mes (seg-sex) excluindo feriados
    bdays = pd.bdate_range(primeiro_dia, ultimo_dia)
    bdays_sem_feriados = [
        d for d in bdays if d.date() not in feriados
    ]
    total_du = len(bdays_sem_feriados)

    if data_ref < primeiro_dia:
        return total_du, 0, total_du
    if data_ref > ultimo_dia:
        return total_du, total_du, 0

    bdays_ate_ref = [
        d for d in bdays_sem_feriados if d <= data_ref
    ]
    du_decorridos = len(bdays_ate_ref)
    du_restantes = total_du - du_decorridos

    return total_du, du_decorridos, du_restantes
