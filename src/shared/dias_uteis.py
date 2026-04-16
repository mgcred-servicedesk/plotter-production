"""
Calculo de dias uteis com suporte a feriados.

Modulo compartilhado entre o dashboard (app.py) e os
relatorios (src/reports/). Feriados sao carregados do
Supabase e cacheados por 24h no Streamlit.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import pandas as pd


def carregar_feriados_supabase(
    mes: int,
    ano: int,
) -> set[date]:
    """Busca feriados do mes/ano no Supabase.

    Usa query direta na tabela feriados filtrando
    por intervalo de datas do mes. Retorna set vazio
    se a tabela ainda nao existir (fallback seguro).

    Returns:
        Conjunto de datas de feriados do periodo.
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
    except Exception:
        return set()

    datas = set()
    for row in resp.data or []:
        d = row.get("data")
        if d:
            datas.add(date.fromisoformat(str(d)))
    return datas


def _carregar_feriados_cached(
    mes: int,
    ano: int,
) -> set[date]:
    """Wrapper cacheado para uso no Streamlit.

    Importa st apenas quando necessario para nao
    quebrar execucoes CLI (relatorios PDF/Excel).
    """
    import streamlit as st

    @st.cache_data(ttl=86400, show_spinner=False)
    def _cached(mes: int, ano: int) -> set[date]:
        return carregar_feriados_supabase(mes, ano)

    return _cached(mes, ano)


def carregar_feriados(
    mes: int,
    ano: int,
) -> set[date]:
    """Ponto de entrada unico para obter feriados.

    Tenta usar cache do Streamlit; se nao estiver
    rodando dentro do Streamlit, busca direto.
    Retorna set vazio em caso de qualquer falha.
    """
    try:
        return _carregar_feriados_cached(mes, ano)
    except Exception:
        try:
            return carregar_feriados_supabase(mes, ano)
        except Exception:
            return set()


def limpar_cache_feriados() -> None:
    """Limpa cache de feriados apos CRUD na tela admin."""
    try:
        import streamlit as st
        _carregar_feriados_cached.__wrapped__ = None
        st.cache_data.clear()
    except Exception:
        pass


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
