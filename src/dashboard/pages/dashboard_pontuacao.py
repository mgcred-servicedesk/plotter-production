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
        df, du_decorridos, df_sup
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
