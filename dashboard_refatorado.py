"""
Dashboard interativo de vendas com Streamlit - Versão Refatorada.
Integra todos os cálculos e KPIs dos relatórios Excel e PDF.
"""

import sys
import warnings
from pathlib import Path

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

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*ScriptRunContext.*")

st.set_page_config(
    page_title="Dashboard de Vendas - MGCred",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


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


def formatar_moeda(valor):
    """Formata valor como moeda brasileira."""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_numero(valor):
    """Formata número com separador de milhares."""
    return f"{valor:,.0f}".replace(",", ".")


def formatar_percentual(valor):
    """Formata percentual."""
    return f"{valor:.1f}%"


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


def criar_cards_kpis_principais(kpis):
    """Cria cards de KPIs principais com estilização moderna."""
    st.markdown("### 📊 Indicadores Principais de Performance")

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
            "💰 Total de Vendas",
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
            "⭐ Total de Pontos",
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
            "📈 Projeção (Pontos)",
            formatar_numero(kpis["projecao_pontos"]),
            f"{formatar_percentual(kpis['perc_proj'])} da meta prata",
            delta_color=delta_color,
        )

    with col4:
        st.metric(
            "🎯 Meta Prata",
            formatar_numero(kpis["meta_prata"]),
            f"{kpis['du_restantes']} DU restantes",
        )

    st.markdown("")
    st.markdown("### 📋 Indicadores Operacionais")

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
            "🏆 Meta Ouro",
            formatar_numero(kpis["meta_ouro"]),
            f"{formatar_percentual(kpis['perc_ating_ouro'])} atingido",
            delta_color=delta_color,
        )

    with col2:
        diferenca_media = kpis["media_du"] - kpis["meta_diaria"]
        delta_color = "normal" if diferenca_media >= 0 else "inverse"

        st.metric(
            "📅 Média por DU",
            formatar_moeda(kpis["media_du"]),
            f"Meta diária: {formatar_moeda(kpis['meta_diaria'])}",
            delta_color=delta_color,
        )

    with col3:
        st.metric(
            "🎫 Ticket Médio",
            formatar_moeda(kpis["ticket_medio"]),
            f"{formatar_numero(kpis['total_transacoes'])} transações",
        )

    with col4:
        produtividade = (
            kpis["total_transacoes"] / kpis["num_consultores"]
            if kpis["num_consultores"] > 0
            else 0
        )
        st.metric(
            "📊 Produtividade",
            f"{produtividade:.1f}",
            f"{formatar_numero(kpis['num_consultores'])} consultores",
        )

    # Segunda linha de KPIs
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        producao_media = (
            kpis["total_pontos"] / kpis["num_consultores"]
            if kpis["num_consultores"] > 0
            else 0
        )
        st.metric(
            "📈 Produção Média/Consultor",
            formatar_numero(producao_media),
            "pontos por consultor",
        )

    with col2:
        st.metric(
            "🏪 Lojas Ativas",
            formatar_numero(kpis["num_lojas"]),
            f"{formatar_numero(kpis['num_regioes'])} regiões",
        )

    with col3:
        st.metric(
            "👥 Consultores Ativos",
            formatar_numero(kpis["num_consultores"]),
            f"Média: {producao_media:.0f} pts",
        )

    with col4:
        valor_medio_consultor = (
            kpis["total_vendas"] / kpis["num_consultores"]
            if kpis["num_consultores"] > 0
            else 0
        )
        st.metric(
            "💰 Valor Médio/Consultor",
            formatar_moeda(valor_medio_consultor),
            "valor por consultor",
        )


def obter_template_grafico():
    """Retorna configuração base para gráficos Plotly.

    Fundos transparentes permitem que o tema do Streamlit
    (config.toml) controle cores de fundo e texto
    automaticamente via st.plotly_chart(theme='streamlit').
    """
    return {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
    }


def criar_grafico_produtos_completo(df_produtos):
    """Cria gráfico completo de produtos."""
    template_config = obter_template_grafico()

    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=(
            "Realizado vs Meta",
            "% Atingimento por Produto",
            "Projeção vs Meta",
            "Ticket Médio por Produto",
        ),
        specs=[
            [{"type": "bar"}, {"type": "bar"}],
            [{"type": "scatter"}, {"type": "bar"}],
        ],
        vertical_spacing=0.12,
        horizontal_spacing=0.1,
    )

    fig.add_trace(
        go.Bar(
            name="Realizado",
            x=df_produtos["Produto"],
            y=df_produtos["Valor"],
            marker_color="#366092",
            text=df_produtos["Valor"].apply(lambda x: formatar_moeda(x)),
            textposition="outside",
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
            marker_color="#1F4E78",
            text=df_produtos["Meta"].apply(lambda x: formatar_moeda(x)),
            textposition="outside",
            showlegend=True,
        ),
        row=1,
        col=1,
    )

    cores_ating = df_produtos["% Atingimento"].apply(
        lambda x: "#28A745" if x >= 100 else "#FF6B6B"
    )

    fig.add_trace(
        go.Bar(
            name="% Atingimento",
            x=df_produtos["Produto"],
            y=df_produtos["% Atingimento"],
            marker_color=cores_ating,
            text=df_produtos["% Atingimento"].apply(lambda x: f"{x:.1f}%"),
            textposition="outside",
            showlegend=False,
        ),
        row=1,
        col=2,
    )

    fig.add_trace(
        go.Scatter(
            name="Projeção",
            x=df_produtos["Produto"],
            y=df_produtos["Projeção"],
            mode="lines+markers",
            marker=dict(size=10, color="#FF6B6B"),
            line=dict(width=3, color="#FF6B6B"),
            text=df_produtos["Projeção"].apply(lambda x: formatar_moeda(x)),
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
            marker=dict(size=8, color="#1F4E78"),
            line=dict(width=2, color="#1F4E78", dash="dash"),
            showlegend=False,
        ),
        row=2,
        col=1,
    )

    fig.add_trace(
        go.Bar(
            name="Ticket Médio",
            x=df_produtos["Produto"],
            y=df_produtos["Ticket Médio"],
            marker_color="#6C757D",
            text=df_produtos["Ticket Médio"].apply(lambda x: formatar_moeda(x)),
            textposition="outside",
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
    fig.update_yaxes(title_text="Ticket Médio (R$)", row=2, col=2)

    fig.update_layout(
        height=700,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        title_text="Análise Completa de Produtos",
        paper_bgcolor=template_config["paper_bgcolor"],
        plot_bgcolor=template_config["plot_bgcolor"],
    )

    return fig


def criar_grafico_evolucao_diaria(df_evolucao, kpis):
    """Cria gráfico de evolução diária."""
    template_config = obter_template_grafico()

    fig = make_subplots(
        rows=2,
        cols=1,
        subplot_titles=("Evolução Diária de Vendas", "Evolução Acumulada vs Meta"),
        vertical_spacing=0.15,
    )

    fig.add_trace(
        go.Bar(
            name="Valor Diário",
            x=df_evolucao["DATA"],
            y=df_evolucao["VALOR"],
            marker_color="#366092",
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
            marker=dict(size=6, color="#1F4E78"),
            line=dict(width=3, color="#1F4E78"),
            showlegend=True,
        ),
        row=2,
        col=1,
    )

    fig.add_hline(
        y=kpis["meta_prata"],
        line_dash="dash",
        line_color="#28A745",
        annotation_text="Meta Prata",
        row=2,
        col=1,
    )

    fig.add_hline(
        y=kpis["projecao"],
        line_dash="dot",
        line_color="#FF6B6B",
        annotation_text="Projeção",
        row=2,
        col=1,
    )

    fig.update_xaxes(title_text="Data", row=1, col=1)
    fig.update_xaxes(title_text="Data", row=2, col=1)

    fig.update_yaxes(title_text="Valor (R$)", row=1, col=1)
    fig.update_yaxes(title_text="Valor Acumulado (R$)", row=2, col=1)

    fig.update_layout(
        height=700,
        showlegend=True,
        hovermode="x unified",
        paper_bgcolor=template_config["paper_bgcolor"],
        plot_bgcolor=template_config["plot_bgcolor"],
    )

    return fig


def criar_grafico_regional(df_regioes):
    """Cria gráfico de análise regional."""
    template_config = obter_template_grafico()

    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=("Valor por Região", "% Atingimento por Região"),
        specs=[[{"type": "bar"}, {"type": "bar"}]],
    )

    df_sorted = df_regioes.sort_values("Valor", ascending=False)

    fig.add_trace(
        go.Bar(
            x=df_sorted["Região"],
            y=df_sorted["Valor"],
            name="Valor",
            marker_color="#366092",
            text=df_sorted["Valor"].apply(lambda x: formatar_moeda(x)),
            textposition="outside",
        ),
        row=1,
        col=1,
    )

    cores_ating = df_sorted["% Atingimento"].apply(
        lambda x: "#28A745" if x >= 100 else "#FF6B6B"
    )

    fig.add_trace(
        go.Bar(
            x=df_sorted["Região"],
            y=df_sorted["% Atingimento"],
            name="% Atingimento",
            marker_color=cores_ating,
            text=df_sorted["% Atingimento"].apply(lambda x: f"{x:.1f}%"),
            textposition="outside",
        ),
        row=1,
        col=2,
    )

    fig.update_layout(
        height=500,
        showlegend=False,
        title_text="Análise por Região",
        paper_bgcolor=template_config["paper_bgcolor"],
        plot_bgcolor=template_config["plot_bgcolor"],
    )

    return fig


def main():
    """Função principal do dashboard."""
    carregar_estilos_customizados()

    st.title("📊 Dashboard de Vendas - MGCred")
    st.markdown("**Análise Completa de Performance e KPIs**")
    st.markdown("---")

    with st.sidebar:
        st.header("⚙️ Configurações")

        ano = st.selectbox("Ano", [2024, 2025, 2026], index=2)
        mes = st.selectbox(
            "Mês",
            list(range(1, 13)),
            index=2,
            format_func=lambda x: {
                1: "Janeiro",
                2: "Fevereiro",
                3: "Março",
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

        st.markdown("---")
        st.info("📅 Dados atualizados automaticamente")

        st.markdown("---")
        st.markdown("### 📖 Legenda")
        st.markdown("**DU**: Dias Úteis")
        st.markdown("**Meta Prata**: Meta principal")
        st.markdown("**Meta Ouro**: Meta desafio")
        st.markdown("**PACK**: FGTS + ANT. BEN. + CNC 13º")

    try:
        with st.spinner("🔄 Carregando dados..."):
            df, df_metas, df_supervisores = carregar_dados(mes, ano)

        ultima_data = df["DATA"].max()
        dia_atual = ultima_data.day if hasattr(ultima_data, "day") else None

        regioes_disponiveis = ["Todas"]
        if "REGIAO" in df.columns:
            regioes_disponiveis += sorted(df["REGIAO"].unique().tolist())

        with st.sidebar:
            st.markdown("---")
            st.markdown("### 📌 Filtros Globais")

            filtro_regiao = st.selectbox(
                "Região",
                regioes_disponiveis,
                help="Filtrar todos os dados por região específica",
            )

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

        st.success(
            f"✅ Dados carregados: {len(df_filtrado):,} registros | "
            f"Última atualização: {ultima_data.strftime('%d/%m/%Y')}"
            + (f" | Região: {filtro_regiao}" if filtro_regiao != "Todas" else "")
        )

        info_sem_pontuacao = verificar_produtos_sem_pontuacao(df_filtrado)
        if info_sem_pontuacao["tem_problemas"]:
            with st.expander(
                f"⚠️ Atenção: {info_sem_pontuacao['total_registros']} "
                f"registros sem pontuação identificada",
                expanded=False,
            ):
                st.warning(
                    f"**Valor total afetado:** "
                    f"R$ {info_sem_pontuacao['valor_total']:,.2f}\n\n"
                    f"Os produtos abaixo não possuem pontuação definida "
                    f"na tabela de pontuação mensal. "
                    f"Verifique se precisam ser adicionados à tabela "
                    f"`pontuacao/pontos_{MESES_ARQUIVO[mes]}.xlsx` "
                    f"ou ao arquivo `tabelas/Tabelas_{MESES_ARQUIVO[mes]}_{ano}.xlsx`."
                )

                df_sem_pontuacao = pd.DataFrame(
                    info_sem_pontuacao["produtos"]
                )
                df_sem_pontuacao.columns = [
                    "Produto", "Valor Total", "Tipo Produto"
                ]
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

        st.markdown("---")

        tabs = st.tabs(
            [
                "📊 Produtos",
                "🗺️ Regiões",
                "🏆 Rankings",
                "📈 Analíticos",
                "📉 Evolução",
                "📋 Detalhes",
            ]
        )

        with tabs[0]:
            st.markdown("### 📦 Análise de Produtos")

            df_produtos = calcular_kpis_por_produto(
                df_filtrado,
                df_metas_filtrado,
                ano,
                mes,
                dia_atual,
                df_supervisores=df_supervisores_filtrado,
            )

            fig_produtos = criar_grafico_produtos_completo(df_produtos)
            st.plotly_chart(fig_produtos, width="stretch")

            st.markdown("### 📊 Tabela de KPIs por Produto")

            exibir_tabela(df_produtos)

            st.info("💡 **PACK** = FGTS + ANT. BEN. + CNC 13º")

        with tabs[1]:
            st.markdown("### 🗺️ Análise por Região")

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
                st.plotly_chart(fig_regional, width="stretch")

                st.markdown("### 📊 Tabela de KPIs por Região")

                exibir_tabela(df_regioes)
            else:
                st.warning("Dados regionais não disponíveis")

        with tabs[2]:
            st.markdown("### 🏆 Rankings de Performance")

            ranking_tabs = st.tabs(["🏪 Lojas", "👥 Consultores", "📦 Por Produto"])

            with ranking_tabs[0]:
                st.markdown("#### Rankings de Lojas")

                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("**Top 10 por Atingimento**")
                    ranking_lojas = calcular_ranking_lojas_atingimento(
                        df_filtrado, df_metas_filtrado, top_n=10
                    )

                    if not ranking_lojas.empty:
                        exibir_tabela(
                            ranking_lojas,
                        )
                    else:
                        st.warning("Dados não disponíveis")

                with col2:
                    st.markdown("**Top 10 por Ticket Médio**")
                    ranking_ticket = calcular_ranking_ticket_medio(
                        df_filtrado, tipo="loja", top_n=10
                    )

                    if not ranking_ticket.empty:
                        exibir_tabela(
                            ranking_ticket,
                        )
                    else:
                        st.warning("Dados não disponíveis")

            with ranking_tabs[1]:
                st.markdown("#### Rankings de Consultores")

                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("**Top 10 por Atingimento**")
                    ranking_consultores = calcular_ranking_consultores_atingimento(
                        df_filtrado,
                        df_metas_filtrado,
                        top_n=10,
                        df_supervisores=df_supervisores_filtrado,
                    )

                    if not ranking_consultores.empty:
                        exibir_tabela(
                            ranking_consultores,
                        )
                    else:
                        st.warning("Dados não disponíveis")

                with col2:
                    st.markdown("**Top 10 por Ticket Médio**")
                    ranking_ticket = calcular_ranking_ticket_medio(
                        df_filtrado,
                        tipo="consultor",
                        top_n=10,
                        df_supervisores=df_supervisores_filtrado,
                    )

                    if not ranking_ticket.empty:
                        exibir_tabela(
                            ranking_ticket,
                        )
                    else:
                        st.warning("Dados não disponíveis")

            with ranking_tabs[2]:
                st.markdown("#### Rankings por Produto")

                tipo_ranking = st.radio(
                    "Visualizar ranking de:", ["Lojas", "Consultores"], horizontal=True
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
                                f"📦 {produto}",
                                expanded=False,
                            ):
                                exibir_tabela(
                                    ranking,
                                )
                else:
                    st.warning("Dados não disponíveis")

        with tabs[3]:
            st.markdown("### 📈 Analíticos Detalhados")

            analitico_tabs = st.tabs(
                [
                    "👥 Consultores por Produto",
                    "🗺️ Produção por Região",
                    "📊 Distribuição de Produtos",
                ]
            )

            with analitico_tabs[0]:
                st.markdown("#### Analítico de Consultores por Produto e Loja")

                df_analitico = calcular_analitico_consultores_produtos_loja(
                    df_filtrado, df_supervisores_filtrado
                )

                if not df_analitico.empty:
                    st.info(
                        f"📊 Total de {df_analitico['Consultor'].nunique()} "
                        f"consultores analisados"
                    )

                    # Filtros
                    col1, col2 = st.columns(2)

                    with col1:
                        consultores_disponiveis = ["Todos"] + sorted(
                            df_analitico["Consultor"].unique().tolist()
                        )
                        consultor_filtro = st.selectbox(
                            "Filtrar por Consultor", consultores_disponiveis
                        )

                    with col2:
                        produtos_disponiveis = ["Todos"] + sorted(
                            df_analitico["Produto"].unique().tolist()
                        )
                        produto_filtro = st.selectbox(
                            "Filtrar por Produto", produtos_disponiveis
                        )

                    # Aplicar filtros
                    df_analitico_filtrado = df_analitico.copy()
                    if consultor_filtro != "Todos":
                        df_analitico_filtrado = df_analitico_filtrado[
                            df_analitico_filtrado["Consultor"] == consultor_filtro
                        ]
                    if produto_filtro != "Todos":
                        df_analitico_filtrado = df_analitico_filtrado[
                            df_analitico_filtrado["Produto"] == produto_filtro
                        ]

                    exibir_tabela(
                        df_analitico_filtrado,
                    )

                    # Estatísticas resumidas
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
                        st.metric(
                            "Ticket Médio Geral",
                            formatar_moeda(
                                df_analitico_filtrado["Valor"].sum()
                                / df_analitico_filtrado["Qtd"].sum()
                                if df_analitico_filtrado["Qtd"].sum() > 0
                                else 0
                            ),
                        )
                else:
                    st.warning("Dados não disponíveis")

            with analitico_tabs[1]:
                st.markdown("#### Média de Produção por Consultor em Cada Região")

                df_media_regiao = calcular_media_producao_consultor_regiao(
                    df_filtrado, df_supervisores_filtrado
                )

                if not df_media_regiao.empty:
                    st.info("📊 Comparativo de produtividade média entre regiões")

                    # Gráfico de barras comparativo
                    fig = go.Figure()

                    fig.add_trace(
                        go.Bar(
                            x=df_media_regiao["Região"],
                            y=df_media_regiao["Pontos Médio"],
                            name="Pontos Médio",
                            marker_color="#1F4E78",
                        )
                    )

                    fig.update_layout(
                        title="Média de Pontos por Consultor por Região",
                        xaxis_title="Região",
                        yaxis_title="Pontos Médio",
                        height=400,
                    )

                    st.plotly_chart(fig, width="stretch")

                    st.markdown("**Estatísticas Detalhadas**")
                    df_display = df_media_regiao.drop(
                        ["Valor Desvio", "Pontos Desvio"],
                        axis=1,
                    )
                    exibir_tabela(df_display)
                else:
                    st.warning("Dados não disponíveis")

            with analitico_tabs[2]:
                st.markdown("#### Distribuição de Produtos por Consultor")

                df_distribuicao = calcular_distribuicao_produtos_consultor(
                    df_filtrado, df_supervisores_filtrado
                )

                if not df_distribuicao.empty:
                    st.info(
                        "📊 Visualização da distribuição "
                        "de produtos por consultor"
                    )

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
                    st.warning("Dados não disponíveis")

        with tabs[4]:
            st.markdown("### 📉 Evolução Temporal")

            df_evolucao = calcular_evolucao_diaria(df_filtrado, ano, mes)

            if not df_evolucao.empty:
                fig_evolucao = criar_grafico_evolucao_diaria(
                    df_evolucao, kpis
                )
                st.plotly_chart(fig_evolucao, width="stretch")

                col1, col2, col3 = st.columns(3)

                with col1:
                    melhor_dia = df_evolucao.loc[df_evolucao["VALOR"].idxmax()]
                    st.metric(
                        "🌟 Melhor Dia",
                        melhor_dia["DATA"].strftime("%d/%m"),
                        formatar_moeda(melhor_dia["VALOR"]),
                    )

                with col2:
                    media_diaria = df_evolucao["VALOR"].mean()
                    st.metric(
                        "📊 Média Diária",
                        formatar_moeda(media_diaria),
                        f"{len(df_evolucao)} dias com vendas",
                    )

                with col3:
                    dias_acima_meta = (
                        df_evolucao["VALOR"] >= kpis["meta_diaria"]
                    ).sum()
                    perc_dias_meta = (
                        dias_acima_meta / len(df_evolucao) * 100
                        if len(df_evolucao) > 0
                        else 0
                    )
                    st.metric(
                        "✅ Dias Acima da Meta",
                        f"{dias_acima_meta}",
                        f"{perc_dias_meta:.1f}% dos dias",
                    )
            else:
                st.warning("Dados de evolução não disponíveis")

        with tabs[5]:
            st.markdown("### 📋 Dados Detalhados")

            st.markdown("#### Filtros")
            col1, col2, col3 = st.columns(3)

            with col1:
                lojas_disponiveis = ["Todas"] + sorted(
                    df_filtrado["LOJA"].unique().tolist()
                )
                loja_filtro = st.selectbox(
                    "Loja", lojas_disponiveis
                )

            with col2:
                if "REGIAO" in df_filtrado.columns:
                    regioes_detalhe = [
                        "Todas"
                    ] + sorted(
                        df_filtrado["REGIAO"].unique().tolist()
                    )
                    regiao_filtro = st.selectbox(
                        "Região (detalhe)",
                        regioes_detalhe,
                    )
                else:
                    regiao_filtro = "Todas"

            with col3:
                produtos_disponiveis = [
                    "Todos"
                ] + sorted(
                    [
                        str(x)
                        for x in df_filtrado[
                            "TIPO_PRODUTO"
                        ].unique()
                        if pd.notna(x)
                    ]
                )
                produto_filtro = st.selectbox(
                    "Produto", produtos_disponiveis
                )

            df_detalhes = df_filtrado.copy()

            if loja_filtro != "Todas":
                df_detalhes = df_detalhes[
                    df_detalhes["LOJA"] == loja_filtro
                ]

            if (
                regiao_filtro != "Todas"
                and "REGIAO" in df_filtrado.columns
            ):
                df_detalhes = df_detalhes[
                    df_detalhes["REGIAO"] == regiao_filtro
                ]

            if produto_filtro != "Todos":
                df_detalhes = df_detalhes[
                    df_detalhes["TIPO_PRODUTO"]
                    == produto_filtro
                ]

            st.markdown(
                f"**{len(df_detalhes):,} registros "
                f"encontrados**"
            )

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(
                    "Total Valor",
                    formatar_moeda(
                        df_detalhes["VALOR"].sum()
                    ),
                )
            with col2:
                st.metric(
                    "Total Pontos",
                    formatar_numero(
                        df_detalhes["pontos"].sum()
                    ),
                )
            with col3:
                ticket = (
                    df_detalhes["VALOR"].sum()
                    / len(df_detalhes)
                    if len(df_detalhes) > 0
                    else 0
                )
                st.metric(
                    "Ticket Médio",
                    formatar_moeda(ticket),
                )

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

    except FileNotFoundError as e:
        st.error(f"❌ Erro ao carregar dados: {e}")
        st.info(
            "Verifique se os arquivos de dados estão disponíveis "
            "para o período selecionado."
        )
    except Exception as e:
        st.error(f"❌ Erro inesperado: {e}")
        st.exception(e)


if __name__ == "__main__":
    main()
