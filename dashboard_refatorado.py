"""
Dashboard interativo de vendas com Streamlit - Versão Refatorada.
Integra todos os cálculos e KPIs dos relatórios Excel e PDF.

Frontend: streamlit-antd-components para navegação,
AG Grid para tabelas, CSS design system customizado.
"""

import sys
import warnings
from pathlib import Path

import streamlit_antd_components as sac
from src.dashboard.components.tables import exibir_tabela
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).parent))

from src.config.settings import MESES_ARQUIVO
from src.dashboard.kpi_analiticos import (
    calcular_analitico_consultores_produtos_loja,
    calcular_distribuicao_produtos_consultor,
    calcular_media_producao_consultor_regiao,
    calcular_ranking_por_produto,
    calcular_ranking_ticket_medio,
)
from src.dashboard.kpi_dashboard import (
    calcular_evolucao_diaria,
    calcular_kpis_gerais,
    calcular_kpis_por_produto,
    calcular_kpis_por_regiao,
    calcular_ranking_consultores_atingimento,
    calcular_ranking_lojas_atingimento,
)
from src.data_processing.column_mapper import (
    adicionar_coluna_subtipo_via_merge,
    aplicar_regras_exclusao_valor_pontos,
    mapear_digitacao,
    mapear_loja_regiao,
    mapear_metas,
    mapear_supervisores,
    mapear_tabelas,
)
from src.data_processing.pontuacao_loader import (
    calcular_pontos_com_tabela_mensal,
    verificar_produtos_sem_pontuacao,
)
from src.dashboard.auth import (
    fazer_logout,
    tela_login,
    usuario_logado,
    PERFIS,
)
from src.dashboard.rls import (
    aplicar_rls,
    aplicar_rls_metas,
    aplicar_rls_supervisores,
    obter_regioes_permitidas,
)
from src.dashboard.user_mgmt import render_pagina_usuarios

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*ScriptRunContext.*")

st.set_page_config(
    page_title="Dashboard de Vendas - MGCred",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ══════════════════════════════════════════════════════
# PALETA DE CORES PARA GRÁFICOS
# ══════════════════════════════════════════════════════

CHART_COLORS = {
    "primary": "#2563eb",
    "primary_dark": "#1e40af",
    "secondary": "#0d9488",
    "success": "#059669",
    "danger": "#dc2626",
    "warning": "#d97706",
    "neutral": "#64748b",
    "purple": "#7c3aed",
    "rose": "#e11d48",
    # Paleta sequencial para barras agrupadas
    "seq": [
        "#2563eb",
        "#0d9488",
        "#7c3aed",
        "#d97706",
        "#059669",
        "#e11d48",
        "#64748b",
        "#0284c7",
    ],
}


# ══════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════


@st.cache_data
def carregar_dados(mes, ano):
    """Carrega e processa dados com cache."""
    mes_nome = {
        1: "janeiro",
        2: "fevereiro",
        3: "marco",
        4: "abril",
        5: "maio",
        6: "junho",
        7: "julho",
        8: "agosto",
        9: "setembro",
        10: "outubro",
        11: "novembro",
        12: "dezembro",
    }[mes]

    df_digitacao = pd.read_excel(f"digitacao/{mes_nome}_{ano}.xlsx")
    df_tabelas = pd.read_excel(f"tabelas/Tabelas_{mes_nome}_{ano}.xlsx")
    df_metas = pd.read_excel(f"metas/metas_{mes_nome}.xlsx")
    df_loja_regiao = pd.read_excel("configuracao/loja_regiao.xlsx")
    df_supervisores = pd.read_excel("configuracao/Supervisores.xlsx")

    df_digitacao = mapear_digitacao(df_digitacao)
    df_tabelas = mapear_tabelas(df_tabelas)
    df_metas = mapear_metas(df_metas)
    df_loja_regiao = mapear_loja_regiao(df_loja_regiao)
    df_supervisores = mapear_supervisores(df_supervisores)

    df_consolidado = adicionar_coluna_subtipo_via_merge(df_digitacao, df_tabelas)
    df_consolidado = calcular_pontos_com_tabela_mensal(df_consolidado, mes, ano)
    df_consolidado = aplicar_regras_exclusao_valor_pontos(df_consolidado)
    df_consolidado = df_consolidado.merge(
        df_loja_regiao[["LOJA", "REGIAO"]], on="LOJA", how="left"
    )

    return df_consolidado, df_metas, df_supervisores


# ══════════════════════════════════════════════════════
# FORMATTERS
# ══════════════════════════════════════════════════════


def formatar_moeda(valor):
    """Formata valor como moeda brasileira."""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_numero(valor):
    """Formata número com separador de milhares."""
    return f"{valor:,.0f}".replace(",", ".")


def formatar_percentual(valor):
    """Formata percentual."""
    return f"{valor:.1f}%"


# ══════════════════════════════════════════════════════
# STYLING & THEMING
# ══════════════════════════════════════════════════════


def carregar_estilos_customizados():
    """Carrega CSS customizado do dashboard."""
    try:
        with open("assets/dashboard_style.css") as f:
            st.markdown(
                f"<style>{f.read()}</style>",
                unsafe_allow_html=True,
            )
    except FileNotFoundError:
        pass


# ══════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════


def _render_header():
    """Renderiza cabeçalho estilizado do dashboard."""
    st.markdown(
        """
        <div class="dashboard-header">
            <h1>Dashboard de Vendas</h1>
            <p>Analise completa de performance e KPIs - MGCred</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_status_bar(num_registros, ultima_data, filtro_regiao):
    """Renderiza barra de status com informações de carregamento."""
    regiao_txt = (
        f" &middot; Regiao: {filtro_regiao}" if filtro_regiao != "Todas" else ""
    )
    status_html = (
        '<div class="status-bar fade-in">'
        '<span class="status-dot"></span>'
        f"<span><strong>{num_registros:,}</strong> registros carregados"
        f" &middot; Atualizado em"
        f" <strong>{ultima_data.strftime('%d/%m/%Y')}</strong>"
        f"{regiao_txt}</span>"
        "</div>"
    )
    st.markdown(status_html, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════
# KPI CARDS
# ══════════════════════════════════════════════════════


def criar_cards_kpis_principais(kpis):
    """Cria cards de KPIs principais com estilização moderna."""
    sac.divider(
        label="Indicadores Principais",
        icon="bar-chart-line",
        align="left",
        color="blue",
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        delta_color = "normal"
        if kpis["perc_ating_prata"] >= 100:
            delta_color = "normal"
        elif kpis["perc_ating_prata"] >= 80:
            delta_color = "off"
        else:
            delta_color = "inverse"

        st.metric(
            "Total de Vendas",
            formatar_moeda(kpis["total_vendas"]),
            f"{formatar_percentual(kpis['perc_ating_prata'])} da meta prata",
            delta_color=delta_color,
        )

    with col2:
        delta_color = "normal"
        if kpis["perc_ating_prata"] >= 100:
            delta_color = "normal"
        elif kpis["perc_ating_prata"] >= 80:
            delta_color = "off"
        else:
            delta_color = "inverse"

        st.metric(
            "Total de Pontos",
            formatar_numero(kpis["total_pontos"]),
            f"{formatar_percentual(kpis['perc_ating_prata'])} da meta prata",
            delta_color=delta_color,
        )

    with col3:
        delta_color = "normal"
        if kpis["perc_proj"] >= 100:
            delta_color = "normal"
        elif kpis["perc_proj"] >= 90:
            delta_color = "off"
        else:
            delta_color = "inverse"

        st.metric(
            "Projecao (Pontos)",
            formatar_numero(kpis["projecao_pontos"]),
            f"{formatar_percentual(kpis['perc_proj'])} da meta prata",
            delta_color=delta_color,
        )

    with col4:
        st.metric(
            "Meta Prata",
            formatar_numero(kpis["meta_prata"]),
            f"{kpis['du_restantes']} DU restantes",
        )

    sac.divider(
        label="Indicadores Operacionais",
        icon="clipboard-data",
        align="left",
        color="blue",
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        delta_color = "normal"
        if kpis["perc_ating_ouro"] >= 100:
            delta_color = "normal"
        elif kpis["perc_ating_ouro"] >= 80:
            delta_color = "off"
        else:
            delta_color = "inverse"

        st.metric(
            "Meta Ouro",
            formatar_numero(kpis["meta_ouro"]),
            f"{formatar_percentual(kpis['perc_ating_ouro'])} atingido",
            delta_color=delta_color,
        )

    with col2:
        diferenca_media = kpis["media_du"] - kpis["meta_diaria"]
        delta_color = "normal" if diferenca_media >= 0 else "inverse"

        st.metric(
            "Media por DU",
            formatar_moeda(kpis["media_du"]),
            f"Meta diaria: {formatar_moeda(kpis['meta_diaria'])}",
            delta_color=delta_color,
        )

    with col3:
        st.metric(
            "Ticket Medio",
            formatar_moeda(kpis["ticket_medio"]),
            f"{formatar_numero(kpis['total_transacoes'])} transacoes",
        )

    with col4:
        produtividade = (
            kpis["total_transacoes"] / kpis["num_consultores"]
            if kpis["num_consultores"] > 0
            else 0
        )
        st.metric(
            "Produtividade",
            f"{produtividade:.1f}",
            f"{formatar_numero(kpis['num_consultores'])} consultores",
        )

    # Terceira linha de KPIs
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        producao_media = (
            kpis["total_pontos"] / kpis["num_consultores"]
            if kpis["num_consultores"] > 0
            else 0
        )
        st.metric(
            "Producao Media/Consultor",
            formatar_numero(producao_media),
            "pontos por consultor",
        )

    with col2:
        st.metric(
            "Lojas Ativas",
            formatar_numero(kpis["num_lojas"]),
            f"{formatar_numero(kpis['num_regioes'])} regioes",
        )

    with col3:
        st.metric(
            "Consultores Ativos",
            formatar_numero(kpis["num_consultores"]),
            f"Media: {producao_media:.0f} pts",
        )

    with col4:
        valor_medio_consultor = (
            kpis["total_vendas"] / kpis["num_consultores"]
            if kpis["num_consultores"] > 0
            else 0
        )
        st.metric(
            "Media/Consultor",
            formatar_moeda(valor_medio_consultor),
            "valor por consultor",
        )


# ══════════════════════════════════════════════════════
# CHART TEMPLATE
# ══════════════════════════════════════════════════════


def obter_template_grafico():
    """Retorna configuração base para gráficos Plotly."""
    return {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": dict(
            family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            size=12,
        ),
        "title_font": dict(size=16, weight=700),
        "legend": dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=11),
            bgcolor="rgba(0,0,0,0)",
        ),
        "margin": dict(l=60, r=30, t=60, b=50),
        "hoverlabel": dict(
            bgcolor="rgba(30,30,46,0.9)",
            font_color="#fff",
            font_size=12,
            bordercolor="rgba(255,255,255,0.1)",
        ),
        "xaxis": dict(
            gridcolor="rgba(128,128,128,0.1)",
            zerolinecolor="rgba(128,128,128,0.15)",
        ),
        "yaxis": dict(
            gridcolor="rgba(128,128,128,0.1)",
            zerolinecolor="rgba(128,128,128,0.15)",
        ),
    }


def _aplicar_template(fig, template_config):
    """Aplica template base a um gráfico Plotly."""
    fig.update_layout(
        paper_bgcolor=template_config["paper_bgcolor"],
        plot_bgcolor=template_config["plot_bgcolor"],
        font=template_config["font"],
        legend=template_config["legend"],
        hoverlabel=template_config["hoverlabel"],
    )
    fig.update_xaxes(
        gridcolor="rgba(128,128,128,0.1)",
        zerolinecolor="rgba(128,128,128,0.15)",
    )
    fig.update_yaxes(
        gridcolor="rgba(128,128,128,0.1)",
        zerolinecolor="rgba(128,128,128,0.15)",
    )
    return fig


# ══════════════════════════════════════════════════════
# CHARTS
# ══════════════════════════════════════════════════════


def criar_grafico_produtos_completo(df_produtos):
    """Cria gráfico completo de produtos."""
    template_config = obter_template_grafico()

    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=(
            "Realizado vs Meta",
            "% Atingimento por Produto",
            "Projecao vs Meta",
            "Ticket Medio por Produto",
        ),
        specs=[
            [{"type": "bar"}, {"type": "bar"}],
            [{"type": "scatter"}, {"type": "bar"}],
        ],
        vertical_spacing=0.14,
        horizontal_spacing=0.10,
    )

    fig.add_trace(
        go.Bar(
            name="Realizado",
            x=df_produtos["Produto"],
            y=df_produtos["Valor"],
            marker_color=CHART_COLORS["primary"],
            marker_line=dict(width=0),
            text=df_produtos["Valor"].apply(formatar_moeda),
            textposition="outside",
            textfont=dict(size=10),
            showlegend=True,
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Bar(
            name="Meta",
            x=df_produtos["Produto"],
            y=df_produtos["Meta"],
            marker_color=CHART_COLORS["primary_dark"],
            marker_line=dict(width=0),
            text=df_produtos["Meta"].apply(formatar_moeda),
            textposition="outside",
            textfont=dict(size=10),
            showlegend=True,
        ),
        row=1,
        col=1,
    )

    cores_ating = df_produtos["% Atingimento"].apply(
        lambda x: CHART_COLORS["success"] if x >= 100 else CHART_COLORS["danger"]
    )

    fig.add_trace(
        go.Bar(
            name="% Atingimento",
            x=df_produtos["Produto"],
            y=df_produtos["% Atingimento"],
            marker_color=cores_ating,
            marker_line=dict(width=0),
            text=df_produtos["% Atingimento"].apply(lambda x: f"{x:.1f}%"),
            textposition="outside",
            textfont=dict(size=10),
            showlegend=False,
        ),
        row=1,
        col=2,
    )

    # Linha de referência 100% no gráfico de atingimento
    fig.add_hline(
        y=100,
        line_dash="dash",
        line_color=CHART_COLORS["neutral"],
        line_width=1,
        opacity=0.5,
        row=2,
        col=2,
    )

    fig.add_trace(
        go.Scatter(
            name="Projecao",
            x=df_produtos["Produto"],
            y=df_produtos["Projeção"],
            mode="lines+markers",
            marker=dict(
                size=10,
                color=CHART_COLORS["rose"],
                line=dict(width=2, color="#fff"),
            ),
            line=dict(width=3, color=CHART_COLORS["rose"]),
            text=df_produtos["Projeção"].apply(formatar_moeda),
            textposition="top center",
            showlegend=True,
        ),
        row=2,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            name="Meta",
            x=df_produtos["Produto"],
            y=df_produtos["Meta"],
            mode="lines+markers",
            marker=dict(size=8, color=CHART_COLORS["primary_dark"]),
            line=dict(
                width=2,
                color=CHART_COLORS["primary_dark"],
                dash="dash",
            ),
            showlegend=False,
        ),
        row=2,
        col=1,
    )

    fig.add_trace(
        go.Bar(
            name="Ticket Medio",
            x=df_produtos["Produto"],
            y=df_produtos["Ticket Médio"],
            marker_color=CHART_COLORS["secondary"],
            marker_line=dict(width=0),
            text=df_produtos["Ticket Médio"].apply(formatar_moeda),
            textposition="outside",
            textfont=dict(size=10),
            showlegend=False,
        ),
        row=2,
        col=2,
    )

    fig.update_xaxes(title_text="Produto", row=1, col=1)
    fig.update_xaxes(title_text="Produto", row=1, col=2)
    fig.update_xaxes(title_text="Produto", row=2, col=1)
    fig.update_xaxes(title_text="Produto", row=2, col=2)

    fig.update_yaxes(title_text="Valor (R$)", row=1, col=1)
    fig.update_yaxes(title_text="% Atingimento", row=1, col=2)
    fig.update_yaxes(title_text="Valor (R$)", row=2, col=1)
    fig.update_yaxes(title_text="Ticket Medio (R$)", row=2, col=2)

    fig.update_layout(
        height=720,
        showlegend=True,
        title_text="Analise Completa de Produtos",
        bargap=0.2,
    )

    _aplicar_template(fig, template_config)

    return fig


def criar_grafico_evolucao_diaria(df_evolucao, kpis):
    """Cria gráfico de evolução diária."""
    template_config = obter_template_grafico()

    fig = make_subplots(
        rows=2,
        cols=1,
        subplot_titles=(
            "Evolucao Diaria de Vendas",
            "Evolucao Acumulada vs Meta",
        ),
        vertical_spacing=0.15,
    )

    fig.add_trace(
        go.Bar(
            name="Valor Diario",
            x=df_evolucao["DATA"],
            y=df_evolucao["VALOR"],
            marker_color=CHART_COLORS["primary"],
            marker_line=dict(width=0),
            showlegend=True,
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            name="Valor Acumulado",
            x=df_evolucao["DATA"],
            y=df_evolucao["Valor Acumulado"],
            mode="lines+markers",
            marker=dict(
                size=5,
                color=CHART_COLORS["primary_dark"],
                line=dict(width=1, color="#fff"),
            ),
            line=dict(width=3, color=CHART_COLORS["primary_dark"]),
            fill="tozeroy",
            fillcolor="rgba(37, 99, 235, 0.08)",
            showlegend=True,
        ),
        row=2,
        col=1,
    )

    fig.add_hline(
        y=kpis["meta_prata"],
        line_dash="dash",
        line_color=CHART_COLORS["success"],
        line_width=2,
        annotation_text="Meta Prata",
        annotation_font=dict(size=11, color=CHART_COLORS["success"]),
        row=2,
        col=1,
    )

    fig.add_hline(
        y=kpis["projecao"],
        line_dash="dot",
        line_color=CHART_COLORS["warning"],
        line_width=2,
        annotation_text="Projecao",
        annotation_font=dict(size=11, color=CHART_COLORS["warning"]),
        row=2,
        col=1,
    )

    fig.update_xaxes(title_text="Data", row=1, col=1)
    fig.update_xaxes(title_text="Data", row=2, col=1)
    fig.update_yaxes(title_text="Valor (R$)", row=1, col=1)
    fig.update_yaxes(title_text="Valor Acumulado (R$)", row=2, col=1)

    fig.update_layout(
        height=720,
        showlegend=True,
        hovermode="x unified",
    )

    _aplicar_template(fig, template_config)

    return fig


def criar_grafico_regional(df_regioes):
    """Cria gráfico de análise regional."""
    template_config = obter_template_grafico()

    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=(
            "Valor por Regiao",
            "% Atingimento por Regiao",
        ),
        specs=[[{"type": "bar"}, {"type": "bar"}]],
    )

    df_sorted = df_regioes.sort_values("Valor", ascending=False)

    fig.add_trace(
        go.Bar(
            x=df_sorted["Região"],
            y=df_sorted["Valor"],
            name="Valor",
            marker_color=CHART_COLORS["primary"],
            marker_line=dict(width=0),
            text=df_sorted["Valor"].apply(formatar_moeda),
            textposition="outside",
            textfont=dict(size=10),
        ),
        row=1,
        col=1,
    )

    cores_ating = df_sorted["% Atingimento"].apply(
        lambda x: CHART_COLORS["success"] if x >= 100 else CHART_COLORS["danger"]
    )

    fig.add_trace(
        go.Bar(
            x=df_sorted["Região"],
            y=df_sorted["% Atingimento"],
            name="% Atingimento",
            marker_color=cores_ating,
            marker_line=dict(width=0),
            text=df_sorted["% Atingimento"].apply(lambda x: f"{x:.1f}%"),
            textposition="outside",
            textfont=dict(size=10),
        ),
        row=1,
        col=2,
    )

    fig.update_layout(
        height=500,
        showlegend=False,
        title_text="Analise por Regiao",
        bargap=0.25,
    )

    _aplicar_template(fig, template_config)

    return fig


def criar_grafico_media_regiao(df_media_regiao):
    """Cria gráfico de média de pontos por região."""
    template_config = obter_template_grafico()

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=df_media_regiao["Região"],
            y=df_media_regiao["Pontos Médio"],
            name="Pontos Medio",
            marker_color=CHART_COLORS["secondary"],
            marker_line=dict(width=0),
            text=df_media_regiao["Pontos Médio"].apply(lambda x: formatar_numero(x)),
            textposition="outside",
            textfont=dict(size=11),
        )
    )

    fig.update_layout(
        title="Media de Pontos por Consultor por Regiao",
        xaxis_title="Regiao",
        yaxis_title="Pontos Medio",
        height=420,
        bargap=0.3,
    )

    _aplicar_template(fig, template_config)

    return fig


# ══════════════════════════════════════════════════════
# TAB CONTENT RENDERERS
# ══════════════════════════════════════════════════════


def _render_tab_produtos(
    df_filtrado,
    df_metas_filtrado,
    ano,
    mes,
    dia_atual,
    df_supervisores_filtrado,
):
    """Renderiza aba de Produtos."""
    sac.divider(
        label="Analise de Produtos",
        icon="box",
        align="left",
        color="blue",
    )

    df_produtos = calcular_kpis_por_produto(
        df_filtrado,
        df_metas_filtrado,
        ano,
        mes,
        dia_atual,
        df_supervisores=df_supervisores_filtrado,
    )

    fig_produtos = criar_grafico_produtos_completo(df_produtos)
    st.plotly_chart(fig_produtos, use_container_width=True)

    sac.divider(
        label="KPIs por Produto",
        icon="table",
        align="left",
        color="gray",
    )
    exibir_tabela(df_produtos)

    st.info("PACK = FGTS + ANT. BEN. + CNC 13o")


def _render_tab_regioes(
    df_filtrado,
    df_metas_filtrado,
    ano,
    mes,
    dia_atual,
    df_supervisores_filtrado,
):
    """Renderiza aba de Regiões."""
    sac.divider(
        label="Analise por Regiao",
        icon="geo-alt",
        align="left",
        color="blue",
    )

    df_regioes = calcular_kpis_por_regiao(
        df_filtrado,
        df_metas_filtrado,
        ano,
        mes,
        dia_atual,
        df_supervisores=df_supervisores_filtrado,
    )

    if not df_regioes.empty:
        fig_regional = criar_grafico_regional(df_regioes)
        st.plotly_chart(fig_regional, use_container_width=True)

        sac.divider(
            label="KPIs por Regiao",
            icon="table",
            align="left",
            color="gray",
        )
        exibir_tabela(df_regioes)
    else:
        st.warning("Dados regionais nao disponiveis")


def _render_tab_rankings(
    df_filtrado,
    df_metas_filtrado,
    df_supervisores_filtrado,
):
    """Renderiza aba de Rankings."""
    sac.divider(
        label="Rankings de Performance",
        icon="trophy",
        align="left",
        color="blue",
    )

    ranking_menu = sac.tabs(
        items=[
            sac.TabsItem(label="Lojas", icon="shop"),
            sac.TabsItem(label="Consultores", icon="people"),
            sac.TabsItem(label="Por Produto", icon="box-seam"),
        ],
        align="start",
        variant="outline",
        use_container_width=True,
    )

    if ranking_menu == "Lojas":
        col1, col2 = st.columns(2)

        with col1:
            sac.divider(
                label="Top 10 por Atingimento",
                icon="graph-up-arrow",
                align="left",
                color="green",
            )
            ranking_lojas = calcular_ranking_lojas_atingimento(
                df_filtrado, df_metas_filtrado, top_n=10
            )
            if not ranking_lojas.empty:
                exibir_tabela(ranking_lojas)
            else:
                st.warning("Dados nao disponiveis")

        with col2:
            sac.divider(
                label="Top 10 por Ticket Medio",
                icon="cash-coin",
                align="left",
                color="orange",
            )
            ranking_ticket = calcular_ranking_ticket_medio(
                df_filtrado, tipo="loja", top_n=10
            )
            if not ranking_ticket.empty:
                exibir_tabela(ranking_ticket)
            else:
                st.warning("Dados nao disponiveis")

    elif ranking_menu == "Consultores":
        col1, col2 = st.columns(2)

        with col1:
            sac.divider(
                label="Top 10 por Atingimento",
                icon="graph-up-arrow",
                align="left",
                color="green",
            )
            ranking_consultores = calcular_ranking_consultores_atingimento(
                df_filtrado,
                df_metas_filtrado,
                top_n=10,
                df_supervisores=df_supervisores_filtrado,
            )
            if not ranking_consultores.empty:
                exibir_tabela(ranking_consultores)
            else:
                st.warning("Dados nao disponiveis")

        with col2:
            sac.divider(
                label="Top 10 por Ticket Medio",
                icon="cash-coin",
                align="left",
                color="orange",
            )
            ranking_ticket = calcular_ranking_ticket_medio(
                df_filtrado,
                tipo="consultor",
                top_n=10,
                df_supervisores=df_supervisores_filtrado,
            )
            if not ranking_ticket.empty:
                exibir_tabela(ranking_ticket)
            else:
                st.warning("Dados nao disponiveis")

    elif ranking_menu == "Por Produto":
        tipo_ranking = sac.segmented(
            items=[
                sac.SegmentedItem(label="Lojas", icon="shop"),
                sac.SegmentedItem(
                    label="Consultores",
                    icon="people",
                ),
            ],
            align="start",
            use_container_width=False,
        )

        tipo = "loja" if tipo_ranking == "Lojas" else "consultor"
        rankings_produto = calcular_ranking_por_produto(
            df_filtrado,
            tipo=tipo,
            top_n=10,
            df_supervisores=df_supervisores_filtrado,
        )

        if rankings_produto:
            for produto, ranking in rankings_produto.items():
                if not ranking.empty:
                    with st.expander(
                        f"{produto}",
                        expanded=False,
                    ):
                        exibir_tabela(ranking)
        else:
            st.warning("Dados nao disponiveis")


def _render_tab_analiticos(
    df_filtrado,
    df_supervisores_filtrado,
):
    """Renderiza aba de Analíticos."""
    sac.divider(
        label="Analiticos Detalhados",
        icon="graph-up",
        align="left",
        color="blue",
    )

    analitico_menu = sac.tabs(
        items=[
            sac.TabsItem(
                label="Consultores por Produto",
                icon="people",
            ),
            sac.TabsItem(
                label="Producao por Regiao",
                icon="geo-alt",
            ),
            sac.TabsItem(
                label="Distribuicao de Produtos",
                icon="pie-chart",
            ),
        ],
        align="start",
        variant="outline",
        use_container_width=True,
    )

    if analitico_menu == "Consultores por Produto":
        df_analitico = calcular_analitico_consultores_produtos_loja(
            df_filtrado, df_supervisores_filtrado
        )

        if not df_analitico.empty:
            st.info(
                f"Total de {df_analitico['Consultor'].nunique()} consultores analisados"
            )

            col1, col2 = st.columns(2)

            with col1:
                consultores_disponiveis = ["Todos"] + sorted(
                    df_analitico["Consultor"].unique().tolist()
                )
                consultor_filtro = st.selectbox(
                    "Filtrar por Consultor",
                    consultores_disponiveis,
                )

            with col2:
                produtos_disponiveis = ["Todos"] + sorted(
                    df_analitico["Produto"].unique().tolist()
                )
                produto_filtro = st.selectbox(
                    "Filtrar por Produto",
                    produtos_disponiveis,
                )

            df_analitico_filtrado = df_analitico.copy()
            if consultor_filtro != "Todos":
                df_analitico_filtrado = df_analitico_filtrado[
                    df_analitico_filtrado["Consultor"] == consultor_filtro
                ]
            if produto_filtro != "Todos":
                df_analitico_filtrado = df_analitico_filtrado[
                    df_analitico_filtrado["Produto"] == produto_filtro
                ]

            exibir_tabela(df_analitico_filtrado)

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(
                    "Total de Pontos",
                    formatar_numero(df_analitico_filtrado["Pontos"].sum()),
                )
            with col2:
                st.metric(
                    "Total de Valor",
                    formatar_moeda(df_analitico_filtrado["Valor"].sum()),
                )
            with col3:
                qtd_total = df_analitico_filtrado["Qtd"].sum()
                st.metric(
                    "Ticket Medio Geral",
                    formatar_moeda(
                        df_analitico_filtrado["Valor"].sum() / qtd_total
                        if qtd_total > 0
                        else 0
                    ),
                )
        else:
            st.warning("Dados nao disponiveis")

    elif analitico_menu == "Producao por Regiao":
        df_media_regiao = calcular_media_producao_consultor_regiao(
            df_filtrado, df_supervisores_filtrado
        )

        if not df_media_regiao.empty:
            st.info("Comparativo de produtividade media entre regioes")

            fig = criar_grafico_media_regiao(df_media_regiao)
            st.plotly_chart(fig, use_container_width=True)

            sac.divider(
                label="Estatisticas Detalhadas",
                icon="table",
                align="left",
                color="gray",
            )
            df_display = df_media_regiao.drop(
                ["Valor Desvio", "Pontos Desvio"],
                axis=1,
            )
            exibir_tabela(df_display)
        else:
            st.warning("Dados nao disponiveis")

    elif analitico_menu == "Distribuicao de Produtos":
        df_distribuicao = calcular_distribuicao_produtos_consultor(
            df_filtrado, df_supervisores_filtrado
        )

        if not df_distribuicao.empty:
            st.info("Visualizacao da distribuicao de produtos por consultor")

            top_n = st.slider(
                "Exibir top N consultores",
                min_value=5,
                max_value=50,
                value=20,
                step=5,
            )

            df_top = df_distribuicao.head(top_n)
            exibir_tabela(df_top)
        else:
            st.warning("Dados nao disponiveis")


def _render_tab_evolucao(df_filtrado, ano, mes, kpis):
    """Renderiza aba de Evolução."""
    sac.divider(
        label="Evolucao Temporal",
        icon="graph-down",
        align="left",
        color="blue",
    )

    df_evolucao = calcular_evolucao_diaria(df_filtrado, ano, mes)

    if not df_evolucao.empty:
        fig_evolucao = criar_grafico_evolucao_diaria(df_evolucao, kpis)
        st.plotly_chart(fig_evolucao, use_container_width=True)

        col1, col2, col3 = st.columns(3)

        with col1:
            melhor_dia = df_evolucao.loc[df_evolucao["VALOR"].idxmax()]
            st.metric(
                "Melhor Dia",
                melhor_dia["DATA"].strftime("%d/%m"),
                formatar_moeda(melhor_dia["VALOR"]),
            )

        with col2:
            media_diaria = df_evolucao["VALOR"].mean()
            st.metric(
                "Media Diaria",
                formatar_moeda(media_diaria),
                f"{len(df_evolucao)} dias com vendas",
            )

        with col3:
            dias_acima_meta = (df_evolucao["VALOR"] >= kpis["meta_diaria"]).sum()
            perc_dias_meta = (
                dias_acima_meta / len(df_evolucao) * 100 if len(df_evolucao) > 0 else 0
            )
            st.metric(
                "Dias Acima da Meta",
                f"{dias_acima_meta}",
                f"{perc_dias_meta:.1f}% dos dias",
            )
    else:
        st.warning("Dados de evolucao nao disponiveis")


def _render_tab_detalhes(df_filtrado):
    """Renderiza aba de Detalhes."""
    sac.divider(
        label="Dados Detalhados",
        icon="clipboard-data",
        align="left",
        color="blue",
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        lojas_disponiveis = ["Todas"] + sorted(df_filtrado["LOJA"].unique().tolist())
        loja_filtro = st.selectbox("Loja", lojas_disponiveis)

    with col2:
        if "REGIAO" in df_filtrado.columns:
            regioes_detalhe = ["Todas"] + sorted(
                df_filtrado["REGIAO"].unique().tolist()
            )
            regiao_filtro = st.selectbox(
                "Regiao (detalhe)",
                regioes_detalhe,
            )
        else:
            regiao_filtro = "Todas"

    with col3:
        produtos_disponiveis = ["Todos"] + sorted(
            [str(x) for x in df_filtrado["TIPO_PRODUTO"].unique() if pd.notna(x)]
        )
        produto_filtro = st.selectbox("Produto", produtos_disponiveis)

    df_detalhes = df_filtrado.copy()

    if loja_filtro != "Todas":
        df_detalhes = df_detalhes[df_detalhes["LOJA"] == loja_filtro]

    if regiao_filtro != "Todas" and "REGIAO" in df_filtrado.columns:
        df_detalhes = df_detalhes[df_detalhes["REGIAO"] == regiao_filtro]

    if produto_filtro != "Todos":
        df_detalhes = df_detalhes[df_detalhes["TIPO_PRODUTO"] == produto_filtro]

    st.markdown(f"**{len(df_detalhes):,} registros encontrados**")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            "Total Valor",
            formatar_moeda(df_detalhes["VALOR"].sum()),
        )
    with col2:
        st.metric(
            "Total Pontos",
            formatar_numero(df_detalhes["pontos"].sum()),
        )
    with col3:
        ticket = (
            df_detalhes["VALOR"].sum() / len(df_detalhes) if len(df_detalhes) > 0 else 0
        )
        st.metric("Ticket Medio", formatar_moeda(ticket))

    colunas_exibir = [
        "DATA",
        "LOJA",
        "CONSULTOR",
        "TIPO_PRODUTO",
        "VALOR",
        "pontos",
    ]
    if "REGIAO" in df_detalhes.columns:
        colunas_exibir.insert(2, "REGIAO")

    df_exibir = df_detalhes[colunas_exibir]
    exibir_tabela(
        df_exibir,
        colunas_moeda=["VALOR"],
        colunas_numero=["pontos"],
    )


# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════


def _render_sidebar_usuario():
    """Renderiza informações do usuário e logout na sidebar."""
    user = usuario_logado()
    if not user:
        return

    sac.divider(
        label="Usuario",
        icon="person-circle",
        align="center",
        color="gray",
    )

    perfil_label = PERFIS.get(user["perfil"], user["perfil"])
    st.markdown(
        f"**{user['nome']}**  \n"
        f"<small style='opacity:0.6'>{perfil_label}</small>",
        unsafe_allow_html=True,
    )

    if user["perfil"] != "admin" and user.get("escopo"):
        st.caption(
            f"Escopo: {', '.join(user['escopo'])}"
        )

    if st.button("Sair", use_container_width=True):
        fazer_logout()
        st.rerun()


def _render_sidebar_visualizar_como(df):
    """
    Renderiza seletor 'Visualizar como' para admin.

    Permite que o admin simule a visão de outro perfil.
    """
    user = usuario_logado()
    if not user or user["perfil"] != "admin":
        return

    sac.divider(
        label="Visualizar Como",
        icon="eye",
        align="center",
        color="gray",
    )

    opcoes_perfil = ["Admin (padrao)", "Gerente Comercial", "Supervisor"]
    perfil_sel = st.selectbox(
        "Simular perfil",
        opcoes_perfil,
        key="sel_visualizar_perfil",
    )

    if perfil_sel == "Admin (padrao)":
        st.session_state.pop("visualizar_como", None)
    elif perfil_sel == "Gerente Comercial":
        regioes = sorted(
            df["REGIAO"].unique().tolist()
        ) if "REGIAO" in df.columns else []
        escopo = st.multiselect(
            "Regioes", regioes,
            key="sel_visualizar_regioes",
        )
        if escopo:
            st.session_state["visualizar_como"] = {
                "perfil": "gerente_comercial",
                "escopo": escopo,
            }
        else:
            st.session_state.pop("visualizar_como", None)
    elif perfil_sel == "Supervisor":
        lojas = sorted(
            df["LOJA"].unique().tolist()
        ) if "LOJA" in df.columns else []
        escopo = st.multiselect(
            "Lojas", lojas,
            key="sel_visualizar_lojas",
        )
        if escopo:
            st.session_state["visualizar_como"] = {
                "perfil": "supervisor",
                "escopo": escopo,
            }
        else:
            st.session_state.pop("visualizar_como", None)


def main():
    """Funcao principal do dashboard."""
    carregar_estilos_customizados()

    # ── Autenticação ──────────────────────────────────
    if not tela_login():
        return

    _render_header()

    with st.sidebar:
        st.image(
            "assets/logotipo-mg-cred.png",
            use_column_width=True,
        )

        _render_sidebar_usuario()

        sac.divider(
            label="Periodo",
            icon="calendar3",
            align="center",
            color="gray",
        )

        ano = st.selectbox("Ano", [2024, 2025, 2026], index=2)
        mes = st.selectbox(
            "Mes",
            list(range(1, 13)),
            index=2,
            format_func=lambda x: {
                1: "Janeiro",
                2: "Fevereiro",
                3: "Marco",
                4: "Abril",
                5: "Maio",
                6: "Junho",
                7: "Julho",
                8: "Agosto",
                9: "Setembro",
                10: "Outubro",
                11: "Novembro",
                12: "Dezembro",
            }[x],
        )

        sac.divider(
            label="Legenda",
            icon="book",
            align="center",
            color="gray",
        )

        st.caption("**DU**: Dias Uteis")
        st.caption("**Meta Prata**: Meta principal")
        st.caption("**Meta Ouro**: Meta desafio")
        st.caption("**PACK**: FGTS + ANT. BEN. + CNC 13o")

    try:
        with st.spinner("Carregando dados..."):
            df, df_metas, df_supervisores = carregar_dados(mes, ano)

        # ── RLS: filtrar dados por perfil ─────────────
        df = aplicar_rls(df)
        df_metas = aplicar_rls_metas(df_metas, df)
        df_supervisores = aplicar_rls_supervisores(
            df_supervisores, df,
        )

        ultima_data = df["DATA"].max()
        dia_atual = ultima_data.day if hasattr(ultima_data, "day") else None

        # ── Regiões permitidas pelo RLS ───────────────
        regioes_todas = ["Todas"]
        if "REGIAO" in df.columns:
            regioes_todas += sorted(df["REGIAO"].unique().tolist())

        regioes_disponiveis = obter_regioes_permitidas(
            regioes_todas,
        )

        with st.sidebar:
            # Visualizar como (admin only)
            _render_sidebar_visualizar_como(df)

            if regioes_disponiveis:
                sac.divider(
                    label="Filtros Globais",
                    icon="funnel",
                    align="center",
                    color="gray",
                )

                filtro_regiao = st.selectbox(
                    "Regiao",
                    regioes_disponiveis,
                    help="Filtrar todos os dados por regiao",
                )
            else:
                filtro_regiao = "Todas"

        df_filtrado = df.copy()
        df_metas_filtrado = df_metas.copy()
        df_supervisores_filtrado = df_supervisores.copy()

        if filtro_regiao != "Todas" and "REGIAO" in df.columns:
            df_filtrado = df_filtrado[df_filtrado["REGIAO"] == filtro_regiao]
            lojas_regiao = df_filtrado["LOJA"].unique()
            df_metas_filtrado = df_metas_filtrado[
                df_metas_filtrado["LOJA"].isin(lojas_regiao)
            ]
            if "REGIAO" in df_supervisores.columns:
                df_supervisores_filtrado = df_supervisores_filtrado[
                    df_supervisores_filtrado["REGIAO"] == filtro_regiao
                ]

        _render_status_bar(len(df_filtrado), ultima_data, filtro_regiao)

        info_sem_pontuacao = verificar_produtos_sem_pontuacao(df_filtrado)
        if info_sem_pontuacao["tem_problemas"]:
            with st.expander(
                f"Atencao: "
                f"{info_sem_pontuacao['total_registros']} "
                f"registros sem pontuacao identificada",
                expanded=False,
            ):
                st.warning(
                    f"**Valor total afetado:** "
                    f"{formatar_moeda(info_sem_pontuacao['valor_total'])}"
                    f"\n\nOs produtos abaixo nao possuem "
                    f"pontuacao definida na tabela de pontuacao "
                    f"mensal. Verifique se precisam ser "
                    f"adicionados a tabela "
                    f"`pontuacao/pontos_"
                    f"{MESES_ARQUIVO[mes]}.xlsx` "
                    f"ou ao arquivo `tabelas/Tabelas_"
                    f"{MESES_ARQUIVO[mes]}_{ano}.xlsx`."
                )

                df_sem_pontuacao = pd.DataFrame(info_sem_pontuacao["produtos"])
                df_sem_pontuacao.columns = ["Produto", "Valor Total", "Tipo Produto"]
                exibir_tabela(
                    df_sem_pontuacao,
                    colunas_moeda=["Valor Total"],
                )

        kpis = calcular_kpis_gerais(
            df_filtrado,
            df_metas_filtrado,
            ano,
            mes,
            dia_atual,
            df_supervisores_filtrado,
        )

        criar_cards_kpis_principais(kpis)

        # ── Navegação principal com sac.tabs ─────────
        user = usuario_logado()
        tab_items = [
            sac.TabsItem(label="Produtos", icon="box"),
            sac.TabsItem(label="Regioes", icon="geo-alt"),
            sac.TabsItem(label="Rankings", icon="trophy"),
            sac.TabsItem(
                label="Analiticos", icon="graph-up",
            ),
            sac.TabsItem(
                label="Evolucao", icon="calendar-range",
            ),
            sac.TabsItem(
                label="Detalhes", icon="clipboard-data",
            ),
        ]

        # Aba de gerenciamento de usuários
        if user and user["perfil"] == "admin":
            tab_items.append(
                sac.TabsItem(
                    label="Usuarios", icon="people",
                ),
            )
        else:
            tab_items.append(
                sac.TabsItem(
                    label="Minha Conta", icon="person-gear",
                ),
            )

        tab_selecionada = sac.tabs(
            items=tab_items,
            align="center",
            variant="outline",
            use_container_width=True,
        )

        if tab_selecionada == "Produtos":
            _render_tab_produtos(
                df_filtrado,
                df_metas_filtrado,
                ano,
                mes,
                dia_atual,
                df_supervisores_filtrado,
            )

        elif tab_selecionada == "Regioes":
            _render_tab_regioes(
                df_filtrado,
                df_metas_filtrado,
                ano,
                mes,
                dia_atual,
                df_supervisores_filtrado,
            )

        elif tab_selecionada == "Rankings":
            _render_tab_rankings(
                df_filtrado,
                df_metas_filtrado,
                df_supervisores_filtrado,
            )

        elif tab_selecionada == "Analiticos":
            _render_tab_analiticos(
                df_filtrado,
                df_supervisores_filtrado,
            )

        elif tab_selecionada == "Evolucao":
            _render_tab_evolucao(
                df_filtrado,
                ano,
                mes,
                kpis,
            )

        elif tab_selecionada == "Detalhes":
            _render_tab_detalhes(df_filtrado)

        elif tab_selecionada in ("Usuarios", "Minha Conta"):
            regioes_lista = sorted(
                df["REGIAO"].unique().tolist()
            ) if "REGIAO" in df.columns else []
            lojas_lista = sorted(
                df["LOJA"].unique().tolist()
            ) if "LOJA" in df.columns else []
            render_pagina_usuarios(
                regioes=regioes_lista,
                lojas=lojas_lista,
            )

    except FileNotFoundError as e:
        st.error(f"Erro ao carregar dados: {e}")
        st.info(
            "Verifique se os arquivos de dados estao "
            "disponiveis para o periodo selecionado."
        )
    except Exception as e:
        st.error(f"Erro inesperado: {e}")
        st.exception(e)


if __name__ == "__main__":
    main()
