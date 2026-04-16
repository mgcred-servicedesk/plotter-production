"""
Pagina de gerenciamento de feriados (admin only).

Permite listar, adicionar e remover feriados usados
no calculo de dias uteis do dashboard e relatorios.
"""
from datetime import date, datetime

import pandas as pd
import streamlit as st

from src.config.supabase_client import get_supabase_client

TIPOS_FERIADO = {
    "nacional": "Nacional",
    "estadual": "Estadual",
    "municipal": "Municipal",
    "ponto_facultativo": "Ponto Facultativo",
}


def _carregar_feriados_ano(ano: int) -> list[dict]:
    """Busca todos os feriados de um ano no banco."""
    sb = get_supabase_client()
    resp = (
        sb.table("feriados")
        .select("id, data, descricao, tipo")
        .gte("data", f"{ano}-01-01")
        .lte("data", f"{ano}-12-31")
        .order("data")
        .execute()
    )
    return resp.data or []


def _adicionar_feriado(
    data: date,
    descricao: str,
    tipo: str,
) -> tuple[bool, str]:
    """Insere um feriado no banco."""
    if data.weekday() >= 5:
        return False, (
            "A data selecionada cai em um fim de semana. "
            "Feriados em fins de semana nao afetam dias "
            "uteis e nao precisam ser cadastrados."
        )

    sb = get_supabase_client()
    try:
        sb.table("feriados").insert({
            "data": data.isoformat(),
            "descricao": descricao,
            "tipo": tipo,
        }).execute()
        return True, f"Feriado '{descricao}' adicionado."
    except Exception as e:
        msg = str(e)
        if "duplicate" in msg.lower() or "unique" in msg.lower():
            return False, (
                "Ja existe um feriado cadastrado nesta data."
            )
        return False, f"Erro ao adicionar: {msg}"


def _remover_feriado(feriado_id: int) -> tuple[bool, str]:
    """Remove um feriado pelo ID."""
    sb = get_supabase_client()
    try:
        sb.table("feriados").delete().eq(
            "id", feriado_id,
        ).execute()
        return True, "Feriado removido."
    except Exception as e:
        return False, f"Erro ao remover: {str(e)}"


def _limpar_cache_feriados():
    """Limpa cache de dias uteis apos alteracao."""
    try:
        from src.shared.dias_uteis import (
            _carregar_feriados_cached,
        )
        _carregar_feriados_cached.clear()
    except Exception:
        pass
    st.cache_data.clear()


def _render_lista_feriados(ano: int):
    """Exibe tabela de feriados do ano com botao de remover."""
    feriados = _carregar_feriados_ano(ano)

    if not feriados:
        st.info(
            f"Nenhum feriado cadastrado para {ano}."
        )
        return

    df = pd.DataFrame(feriados)
    df["data"] = pd.to_datetime(df["data"]).dt.strftime(
        "%d/%m/%Y",
    )
    df["dia_semana"] = pd.to_datetime(
        df["data"], format="%d/%m/%Y",
    ).dt.strftime("%A")

    # Traduzir dias da semana
    dias_pt = {
        "Monday": "Segunda",
        "Tuesday": "Terca",
        "Wednesday": "Quarta",
        "Thursday": "Quinta",
        "Friday": "Sexta",
        "Saturday": "Sabado",
        "Sunday": "Domingo",
    }
    df["dia_semana"] = df["dia_semana"].map(
        lambda x: dias_pt.get(x, x),
    )
    df["tipo_label"] = df["tipo"].map(
        lambda x: TIPOS_FERIADO.get(x, x),
    )

    # Exibir tabela
    df_exibir = df[
        ["data", "dia_semana", "descricao", "tipo_label"]
    ].copy()
    df_exibir.columns = [
        "Data", "Dia", "Descricao", "Tipo",
    ]
    st.dataframe(
        df_exibir,
        hide_index=True,
        width="stretch",
    )

    # Botao de remover
    st.markdown("**Remover Feriado**")
    opcoes = {
        f"{r['data']} — {r['descricao']}": r["id"]
        for r in feriados
    }
    if opcoes:
        sel = st.selectbox(
            "Selecionar feriado para remover",
            list(opcoes.keys()),
            key="sel_remover_feriado",
        )
        if st.button(
            "Remover",
            key="btn_remover_feriado",
            type="secondary",
        ):
            ok, msg = _remover_feriado(opcoes[sel])
            if ok:
                _limpar_cache_feriados()
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)


def _render_adicionar_feriado(ano: int):
    """Formulario para adicionar novo feriado."""
    st.markdown("**Adicionar Feriado**")

    with st.form("form_adicionar_feriado"):
        col1, col2 = st.columns(2)

        with col1:
            data = st.date_input(
                "Data",
                value=date(ano, 1, 1),
                min_value=date(ano, 1, 1),
                max_value=date(ano, 12, 31),
                format="DD/MM/YYYY",
                key="input_data_feriado",
            )
            descricao = st.text_input(
                "Descricao",
                placeholder="Ex: Tiradentes",
                key="input_desc_feriado",
            )

        with col2:
            tipo = st.selectbox(
                "Tipo",
                list(TIPOS_FERIADO.keys()),
                format_func=lambda x: TIPOS_FERIADO[x],
                key="input_tipo_feriado",
            )

        submit = st.form_submit_button(
            "Adicionar", type="primary",
        )

    if submit:
        if not descricao or not descricao.strip():
            st.error("Informe a descricao do feriado.")
            return

        ok, msg = _adicionar_feriado(
            data, descricao.strip(), tipo,
        )
        if ok:
            _limpar_cache_feriados()
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)


def render_pagina_feriados():
    """Renderiza pagina de gerenciamento de feriados."""
    ano_atual = datetime.now().year
    ano = st.selectbox(
        "Ano",
        list(range(ano_atual - 1, ano_atual + 2)),
        index=1,
        key="sel_ano_feriado",
    )

    _render_lista_feriados(ano)
    st.divider()
    _render_adicionar_feriado(ano)
