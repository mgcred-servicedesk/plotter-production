"""
Dashboard de Pontuacao — pagina dedicada.

Recebe os DataFrames ja carregados, com RLS e filtros granulares de
UI aplicados pelo ``app.py``. Calcula KPIs em pontos, renderiza os
cards (principais, contexto, MIX) e a secao de prioridades.

Aceleradores aparecem na secao de prioridades por escolha de design
(continuam visiveis para nao perder contexto operacional), mas nao
entram no calculo de pontos.

Permissoes: respeita ``pode_ver('cards_gerenciais', role)``, igual
ao dashboard de vendas.

Alem da pagina, o modulo hospeda ``render_diagnostico_pontuacao`` — o
expander admin-only que audita o mapeamento categoria -> PTS. Nao e uma
pagina (renderiza inline, sem substituir o dashboard), mas mora aqui por
tema: e sobre a mesma pontuacao. Se outros diagnosticos surgirem, vale
promover a um modulo proprio.
"""

from typing import Dict, Optional

import pandas as pd
import streamlit as st

from src.dashboard.kpis.pontuacao import (
    calcular_medias_pontos_por_nivel,
    calcular_mix_pontos,
    calcular_pontos_cancelados,
    calcular_pontos_em_analise,
    calcular_prioridades_pontuacao,
)
from src.dashboard.permissions import pode_ver
from src.dashboard.ui.kpi_cards_pontuacao import render_kpis_pontuacao
from src.dashboard.ui.prioridades_pontuacao import render_prioridades_pontuacao


def render_dashboard_pontuacao(
    *,
    kpis: Dict,
    df: pd.DataFrame,
    df_analise: pd.DataFrame,
    df_cancelados: pd.DataFrame,
    df_metas_produto: pd.DataFrame,
    df_sup: pd.DataFrame,
    mapa_pontos: Dict[str, float],
    du_decorridos: int,
    perfil: Optional[str],
    peso_headcount: Optional[float] = None,
) -> None:
    """Renderiza a pagina de Pontuacao.

    Args:
        kpis: dict de ``calcular_kpis_gerais`` ja calculado em ``main()``
            (contem ``total_pontos``, ``meta_prata``, ``meta_ouro``,
            ``projecao_pontos``, ``perc_proj``, etc).
        df: contratos pagos pos-RLS e pos-filtros.
        df_analise: contratos em analise pos-RLS e pos-filtros.
        df_cancelados: contratos cancelados pos-RLS e pos-filtros.
        df_metas_produto: metas por produto pos-RLS.
        df_sup: supervisores pos-RLS (usado em medias e aceleradores).
        mapa_pontos: categoria_codigo -> PTS (vem de
            ``carregar_pontuacao_efetiva``).
        du_decorridos: dias uteis decorridos no periodo.
        perfil: role efetivo (apos Visualizar Como).
    """
    # Consultor nao ve cards gerenciais — segue a mesma matriz do
    # dashboard de vendas.
    if not pode_ver("cards_gerenciais", perfil):
        st.info(
            "Seu perfil não tem acesso aos KPIs gerenciais da página "
            "de Pontuação."
        )
        return

    meta_prata = float(kpis.get("meta_prata", 0) or 0)
    meta_ouro = float(kpis.get("meta_ouro", 0) or 0)
    du_total = int(kpis.get("du_total", 0) or 0)

    kpis_analise_pts = calcular_pontos_em_analise(
        df_analise, mapa_pontos, du_decorridos
    )
    kpis_cancel_pts = calcular_pontos_cancelados(
        df_cancelados, df, df_analise, mapa_pontos
    )
    medias_pts = calcular_medias_pontos_por_nivel(
        df, du_decorridos, df_sup, peso_headcount=peso_headcount
    )
    mix_pontos = calcular_mix_pontos(df, meta_prata, du_total)

    render_kpis_pontuacao(
        kpis=kpis,
        kpis_analise_pts=kpis_analise_pts,
        kpis_cancel_pts=kpis_cancel_pts,
        medias_pts=medias_pts,
        mix_pontos=mix_pontos,
    )

    prioridades = calcular_prioridades_pontuacao(
        df=df,
        df_analise=df_analise,
        mapa_pontos=mapa_pontos,
        meta_prata=meta_prata,
        meta_ouro=meta_ouro,
    )
    render_prioridades_pontuacao(
        prioridades=prioridades,
        df=df,
        df_metas_produto=df_metas_produto,
        df_sup=df_sup,
        perfil=perfil or "",
    )


def render_diagnostico_pontuacao(diag: Dict) -> None:
    """Renderiza o expander de diagnostico do mapeamento de pontuacao.

    Audita quantos contratos receberam pontos, quais categorias
    aparecem nos contratos vs. na RPC de pontuacao, o mapa
    categoria -> PTS, os TIPO_PRODUTO que ficaram sem categoria e as
    categorias sem match. E ferramenta de suporte, nao KPI.

    Quem decide *quando* exibir (diagnostico presente e perfil admin)
    e o chamador (``app.py``); a funcao apenas renderiza.

    Args:
        diag: dict gravado em ``st.session_state['_diag_pontuacao']``
            por ``consolidar_dados``. Chaves consumidas aqui:
            ``total_contratos``, ``sem_categoria``,
            ``com_pontos_mapeados``, ``categorias_no_contrato``,
            ``categorias_na_pontuacao``, ``mapa_pontos`` e
            ``tipos_sem_categoria`` (opcional).
    """
    with st.expander(
        f"Diagnostico de pontuacao — "
        f"{diag['com_pontos_mapeados']}/{diag['total_contratos']} "
        f"contratos com pontos",
        expanded=False,
    ):
        c1, c2, c3 = st.columns(3)
        c1.metric("Total contratos", diag["total_contratos"])
        c2.metric("Sem categoria", diag["sem_categoria"])
        c3.metric("Com pontos", diag["com_pontos_mapeados"])

        st.markdown("**Categorias nos contratos:**")
        st.code(
            ", ".join(c for c in diag["categorias_no_contrato"] if c)
            or "(vazio)",
        )

        st.markdown("**Categorias na pontuacao (RPC):**")
        st.code(
            ", ".join(diag["categorias_na_pontuacao"]) or "(vazio)",
        )

        st.markdown("**Mapa de pontos:**")
        st.json(diag["mapa_pontos"])

        # Tipos sem categoria (não mapeados pelo fallback)
        tipos_sem_cat = diag.get("tipos_sem_categoria", [])
        if tipos_sem_cat:
            st.warning(
                f"**{diag['sem_categoria']} contratos sem categoria** "
                f"— TIPO_PRODUTO nao mapeado:"
            )
            st.dataframe(
                pd.DataFrame(tipos_sem_cat),
                width="stretch",
                hide_index=True,
            )

        # Categorias sem match
        cats_contrato = {c for c in diag["categorias_no_contrato"] if c}
        cats_pontuacao = set(diag["categorias_na_pontuacao"])
        sem_match = sorted(cats_contrato - cats_pontuacao)
        if sem_match:
            st.warning(
                f"**{len(sem_match)} categorias sem pontuacao:** "
                + ", ".join(sem_match)
            )
