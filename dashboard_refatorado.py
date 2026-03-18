"""
Dashboard interativo de vendas com Streamlit - Versão Refatorada.
Integra todos os cálculos e KPIs dos relatórios Excel e PDF.
"""
import warnings
warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', message='.*ScriptRunContext.*')

import sys
from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from src.config.settings import MESES_ARQUIVO
from src.data_processing.column_mapper import (
    mapear_digitacao,
    mapear_tabelas,
    mapear_metas,
    mapear_loja_regiao,
    adicionar_coluna_subtipo_via_merge,
    aplicar_regras_exclusao_valor_pontos
)
from src.data_processing.pontuacao_loader import (
    calcular_pontos_com_tabela_mensal,
    verificar_produtos_sem_pontuacao
)
from src.dashboard.kpi_dashboard import (
    calcular_kpis_gerais,
    calcular_kpis_por_produto,
    calcular_kpis_por_regiao,
    calcular_ranking_lojas_atingimento,
    calcular_ranking_consultores_atingimento,
    calcular_evolucao_diaria
)

st.set_page_config(
    page_title="Dashboard de Vendas - MGCred",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)


@st.cache_data
def carregar_dados(mes, ano):
    """Carrega e processa dados com cache."""
    mes_nome = {
        1: 'janeiro', 2: 'fevereiro', 3: 'marco', 4: 'abril',
        5: 'maio', 6: 'junho', 7: 'julho', 8: 'agosto',
        9: 'setembro', 10: 'outubro', 11: 'novembro', 12: 'dezembro'
    }[mes]

    df_digitacao = pd.read_excel(f'digitacao/{mes_nome}_{ano}.xlsx')
    df_tabelas = pd.read_excel(f'tabelas/Tabelas_{mes_nome}_{ano}.xlsx')
    df_metas = pd.read_excel(f'metas/metas_{mes_nome}.xlsx')
    df_loja_regiao = pd.read_excel('configuracao/loja_regiao.xlsx')

    df_digitacao = mapear_digitacao(df_digitacao)
    df_tabelas = mapear_tabelas(df_tabelas)
    df_metas = mapear_metas(df_metas)
    df_loja_regiao = mapear_loja_regiao(df_loja_regiao)

    df_consolidado = adicionar_coluna_subtipo_via_merge(
        df_digitacao, df_tabelas
    )
    
    df_consolidado = calcular_pontos_com_tabela_mensal(
        df_consolidado, mes, ano
    )
    
    df_consolidado = aplicar_regras_exclusao_valor_pontos(df_consolidado)

    df_consolidado = df_consolidado.merge(
        df_loja_regiao[['LOJA', 'REGIAO']],
        on='LOJA',
        how='left'
    )
    
    return df_consolidado, df_metas


def formatar_moeda(valor):
    """Formata valor como moeda brasileira."""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace(
        "X", "."
    )


def formatar_numero(valor):
    """Formata número com separador de milhares."""
    return f"{valor:,.0f}".replace(",", ".")


def formatar_percentual(valor):
    """Formata percentual."""
    return f"{valor:.1f}%"


def carregar_estilos_customizados():
    """Carrega CSS customizado e Font Awesome."""
    try:
        with open('assets/dashboard_style.css') as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except FileNotFoundError:
        pass

    font_awesome = '''
    <link rel="stylesheet"
          href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    '''
    st.markdown(font_awesome, unsafe_allow_html=True)


def criar_toggle_tema():
    """Cria toggle de tema com ícones Sol/Lua usando session_state."""
    if 'tema_escuro' not in st.session_state:
        st.session_state.tema_escuro = False
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("**Tema**")
    with col2:
        if st.button("🌙" if not st.session_state.tema_escuro else "☀️", 
                     help="Alternar tema"):
            st.session_state.tema_escuro = not st.session_state.tema_escuro
            st.rerun()
    
    if st.session_state.tema_escuro:
        st.caption("🌙 Modo Escuro")
    else:
        st.caption("☀️ Modo Claro")
    
    aplicar_tema(st.session_state.tema_escuro)
    
    return st.session_state.tema_escuro


def aplicar_tema(tema_escuro):
    """Aplica o tema selecionado (claro ou escuro)."""
    import streamlit.components.v1 as components
    
    if tema_escuro:
        tema_script = """
        <script>
            const setTheme = () => {
                const root = window.parent.document.documentElement;
                root.setAttribute('data-theme', 'dark');
            };
            setTheme();
        </script>
        """
    else:
        tema_script = """
        <script>
            const setTheme = () => {
                const root = window.parent.document.documentElement;
                root.removeAttribute('data-theme');
            };
            setTheme();
        </script>
        """
    
    components.html(tema_script, height=0)


def criar_cards_kpis_principais(kpis):
    """Cria cards de KPIs principais com estilização moderna."""
    st.markdown("### 📊 Indicadores Principais de Performance")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        delta_color = "normal"
        if kpis['perc_ating_prata'] >= 100:
            delta_color = "normal"
        elif kpis['perc_ating_prata'] >= 80:
            delta_color = "off"
        else:
            delta_color = "inverse"
        
        st.metric(
            "💰 Total de Vendas",
            formatar_moeda(kpis['total_vendas']),
            f"{formatar_percentual(kpis['perc_ating_prata'])} da meta prata",
            delta_color=delta_color
        )
    
    with col2:
        delta_color = "normal"
        if kpis['perc_ating_prata'] >= 100:
            delta_color = "normal"
        elif kpis['perc_ating_prata'] >= 80:
            delta_color = "off"
        else:
            delta_color = "inverse"
        
        st.metric(
            "⭐ Total de Pontos",
            formatar_numero(kpis['total_pontos']),
            f"{formatar_percentual(kpis['perc_ating_prata'])} da meta prata",
            delta_color=delta_color
        )
    
    with col3:
        delta_color = "normal"
        if kpis['perc_proj'] >= 100:
            delta_color = "normal"
        elif kpis['perc_proj'] >= 90:
            delta_color = "off"
        else:
            delta_color = "inverse"
        
        st.metric(
            "📈 Projeção (Pontos)",
            formatar_numero(kpis['projecao_pontos']),
            f"{formatar_percentual(kpis['perc_proj'])} da meta prata",
            delta_color=delta_color
        )
    
    with col4:
        st.metric(
            "🎯 Meta Prata",
            formatar_numero(kpis['meta_prata']),
            f"{kpis['du_restantes']} DU restantes"
        )
    
    st.markdown("")
    st.markdown("### 📋 Indicadores Operacionais")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        delta_color = "normal"
        if kpis['perc_ating_ouro'] >= 100:
            delta_color = "normal"
        elif kpis['perc_ating_ouro'] >= 80:
            delta_color = "off"
        else:
            delta_color = "inverse"
        
        st.metric(
            "🏆 Meta Ouro",
            formatar_numero(kpis['meta_ouro']),
            f"{formatar_percentual(kpis['perc_ating_ouro'])} atingido",
            delta_color=delta_color
        )
    
    with col2:
        diferenca_media = kpis['media_du'] - kpis['meta_diaria']
        delta_color = "normal" if diferenca_media >= 0 else "inverse"
        
        st.metric(
            "📅 Média por DU",
            formatar_moeda(kpis['media_du']),
            f"Meta diária: {formatar_moeda(kpis['meta_diaria'])}",
            delta_color=delta_color
        )
    
    with col3:
        st.metric(
            "🎫 Ticket Médio",
            formatar_moeda(kpis['ticket_medio']),
            f"{formatar_numero(kpis['total_transacoes'])} transações"
        )
    
    with col4:
        produtividade = (
            kpis['total_transacoes'] / kpis['num_consultores']
            if kpis['num_consultores'] > 0 else 0
        )
        st.metric(
            "📊 Produtividade",
            f"{produtividade:.1f}",
            f"{formatar_numero(kpis['num_consultores'])} consultores"
        )


def obter_template_grafico(tema_escuro=False):
    """Retorna configuração de template para gráficos baseado no tema."""
    if tema_escuro:
        return {
            'template': 'plotly_dark',
            'paper_bgcolor': '#1A1A1A',
            'plot_bgcolor': '#2D2D2D',
            'font_color': '#E8F1F8'
        }
    else:
        return {
            'template': 'plotly_white',
            'paper_bgcolor': '#FFFFFF',
            'plot_bgcolor': '#F8F9FA',
            'font_color': '#2C3E50'
        }


def criar_grafico_produtos_completo(df_produtos, tema_escuro=False):
    """Cria gráfico completo de produtos."""
    template_config = obter_template_grafico(tema_escuro)
    
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=(
            'Realizado vs Meta',
            '% Atingimento por Produto',
            'Projeção vs Meta',
            'Ticket Médio por Produto'
        ),
        specs=[
            [{'type': 'bar'}, {'type': 'bar'}],
            [{'type': 'scatter'}, {'type': 'bar'}]
        ],
        vertical_spacing=0.12,
        horizontal_spacing=0.1
    )
    
    fig.add_trace(
        go.Bar(
            name='Realizado',
            x=df_produtos['Produto'],
            y=df_produtos['Valor'],
            marker_color='#366092',
            text=df_produtos['Valor'].apply(lambda x: formatar_moeda(x)),
            textposition='outside',
            showlegend=True
        ),
        row=1, col=1
    )
    
    fig.add_trace(
        go.Bar(
            name='Meta',
            x=df_produtos['Produto'],
            y=df_produtos['Meta'],
            marker_color='#1F4E78',
            text=df_produtos['Meta'].apply(lambda x: formatar_moeda(x)),
            textposition='outside',
            showlegend=True
        ),
        row=1, col=1
    )
    
    cores_ating = df_produtos['% Atingimento'].apply(
        lambda x: '#28A745' if x >= 100 else '#FF6B6B'
    )
    
    fig.add_trace(
        go.Bar(
            name='% Atingimento',
            x=df_produtos['Produto'],
            y=df_produtos['% Atingimento'],
            marker_color=cores_ating,
            text=df_produtos['% Atingimento'].apply(
                lambda x: f"{x:.1f}%"
            ),
            textposition='outside',
            showlegend=False
        ),
        row=1, col=2
    )
    
    fig.add_trace(
        go.Scatter(
            name='Projeção',
            x=df_produtos['Produto'],
            y=df_produtos['Projeção'],
            mode='lines+markers',
            marker=dict(size=10, color='#FF6B6B'),
            line=dict(width=3, color='#FF6B6B'),
            text=df_produtos['Projeção'].apply(lambda x: formatar_moeda(x)),
            textposition='top center',
            showlegend=True
        ),
        row=2, col=1
    )
    
    fig.add_trace(
        go.Scatter(
            name='Meta',
            x=df_produtos['Produto'],
            y=df_produtos['Meta'],
            mode='lines+markers',
            marker=dict(size=8, color='#1F4E78'),
            line=dict(width=2, color='#1F4E78', dash='dash'),
            showlegend=False
        ),
        row=2, col=1
    )
    
    fig.add_trace(
        go.Bar(
            name='Ticket Médio',
            x=df_produtos['Produto'],
            y=df_produtos['Ticket Médio'],
            marker_color='#6C757D',
            text=df_produtos['Ticket Médio'].apply(
                lambda x: formatar_moeda(x)
            ),
            textposition='outside',
            showlegend=False
        ),
        row=2, col=2
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
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        title_text="Análise Completa de Produtos",
        template=template_config['template'],
        paper_bgcolor=template_config['paper_bgcolor'],
        plot_bgcolor=template_config['plot_bgcolor'],
        font=dict(color=template_config['font_color'])
    )
    
    return fig


def criar_grafico_evolucao_diaria(df_evolucao, kpis, tema_escuro=False):
    """Cria gráfico de evolução diária."""
    template_config = obter_template_grafico(tema_escuro)
    
    fig = make_subplots(
        rows=2, cols=1,
        subplot_titles=(
            'Evolução Diária de Vendas',
            'Evolução Acumulada vs Meta'
        ),
        vertical_spacing=0.15
    )
    
    fig.add_trace(
        go.Bar(
            name='Valor Diário',
            x=df_evolucao['DATA'],
            y=df_evolucao['VALOR'],
            marker_color='#366092',
            showlegend=True
        ),
        row=1, col=1
    )
    
    fig.add_trace(
        go.Scatter(
            name='Valor Acumulado',
            x=df_evolucao['DATA'],
            y=df_evolucao['Valor Acumulado'],
            mode='lines+markers',
            marker=dict(size=6, color='#1F4E78'),
            line=dict(width=3, color='#1F4E78'),
            showlegend=True
        ),
        row=2, col=1
    )
    
    fig.add_hline(
        y=kpis['meta_prata'],
        line_dash="dash",
        line_color="#28A745",
        annotation_text="Meta Prata",
        row=2, col=1
    )
    
    fig.add_hline(
        y=kpis['projecao'],
        line_dash="dot",
        line_color="#FF6B6B",
        annotation_text="Projeção",
        row=2, col=1
    )
    
    fig.update_xaxes(title_text="Data", row=1, col=1)
    fig.update_xaxes(title_text="Data", row=2, col=1)
    
    fig.update_yaxes(title_text="Valor (R$)", row=1, col=1)
    fig.update_yaxes(title_text="Valor Acumulado (R$)", row=2, col=1)
    
    fig.update_layout(
        height=700,
        showlegend=True,
        hovermode='x unified',
        template=template_config['template'],
        paper_bgcolor=template_config['paper_bgcolor'],
        plot_bgcolor=template_config['plot_bgcolor'],
        font=dict(color=template_config['font_color'])
    )
    
    return fig


def criar_grafico_regional(df_regioes, tema_escuro=False):
    """Cria gráfico de análise regional."""
    template_config = obter_template_grafico(tema_escuro)
    
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=(
            'Valor por Região',
            '% Atingimento por Região'
        ),
        specs=[[{'type': 'bar'}, {'type': 'bar'}]]
    )
    
    df_sorted = df_regioes.sort_values('Pontos', ascending=False)
    
    fig.add_trace(
        go.Bar(
            x=df_sorted['Região'],
            y=df_sorted['Valor'],
            name='Valor',
            marker_color='#366092',
            text=df_sorted['Valor'].apply(lambda x: formatar_moeda(x)),
            textposition='outside'
        ),
        row=1, col=1
    )
    
    cores_ating = df_sorted['% Atingimento'].apply(
        lambda x: '#28A745' if x >= 100 else '#FF6B6B'
    )
    
    fig.add_trace(
        go.Bar(
            x=df_sorted['Região'],
            y=df_sorted['% Atingimento'],
            name='% Atingimento',
            marker_color=cores_ating,
            text=df_sorted['% Atingimento'].apply(lambda x: f"{x:.1f}%"),
            textposition='outside'
        ),
        row=1, col=2
    )
    
    fig.update_layout(
        height=500,
        showlegend=False,
        title_text="Análise por Região",
        template=template_config['template'],
        paper_bgcolor=template_config['paper_bgcolor'],
        plot_bgcolor=template_config['plot_bgcolor'],
        font=dict(color=template_config['font_color'])
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
        
        tema_escuro = criar_toggle_tema()
        
        st.markdown("---")
        
        ano = st.selectbox("Ano", [2024, 2025, 2026], index=2)
        mes = st.selectbox(
            "Mês",
            list(range(1, 13)),
            index=2,
            format_func=lambda x: {
                1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
                5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
                9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
            }[x]
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
            df, df_metas = carregar_dados(mes, ano)
        
        ultima_data = df['DATA'].max()
        dia_atual = ultima_data.day if hasattr(ultima_data, 'day') else None
        
        regioes_disponiveis = ['Todas']
        if 'REGIAO' in df.columns:
            regioes_disponiveis += sorted(df['REGIAO'].unique().tolist())
        
        with st.sidebar:
            st.markdown("---")
            st.markdown("### 📌 Filtros Globais")
            
            filtro_regiao = st.selectbox(
                "Região",
                regioes_disponiveis,
                help="Filtrar todos os dados por região específica"
            )
        
        df_filtrado = df.copy()
        df_metas_filtrado = df_metas.copy()
        
        if filtro_regiao != 'Todas' and 'REGIAO' in df.columns:
            df_filtrado = df_filtrado[df_filtrado['REGIAO'] == filtro_regiao]
            lojas_regiao = df_filtrado['LOJA'].unique()
            df_metas_filtrado = df_metas_filtrado[
                df_metas_filtrado['LOJA'].isin(lojas_regiao)
            ]
        
        st.success(
            f"✅ Dados carregados: {len(df_filtrado):,} registros | "
            f"Última atualização: {ultima_data.strftime('%d/%m/%Y')}" +
            (f" | Região: {filtro_regiao}" if filtro_regiao != 'Todas' else "")
        )
        
        info_sem_pontuacao = verificar_produtos_sem_pontuacao(df_filtrado)
        if info_sem_pontuacao['tem_problemas']:
            with st.expander(
                f"⚠️ Atenção: {info_sem_pontuacao['total_registros']} "
                f"registros sem pontuação identificada",
                expanded=False
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
                    info_sem_pontuacao['produtos']
                )
                df_sem_pontuacao['VALOR'] = df_sem_pontuacao['VALOR'].apply(
                    lambda x: f"R$ {x:,.2f}"
                )
                df_sem_pontuacao.columns = [
                    'Produto', 'Valor Total', 'Tipo Produto'
                ]
                st.dataframe(
                    df_sem_pontuacao,
                    use_container_width=True,
                    hide_index=True
                )
        
        kpis = calcular_kpis_gerais(
            df_filtrado, df_metas_filtrado, ano, mes, dia_atual
        )
        
        criar_cards_kpis_principais(kpis)
        
        st.markdown("---")
        
        tabs = st.tabs([
            "📊 Produtos",
            "🗺️ Regiões",
            "🏆 Rankings",
            "📈 Evolução",
            "📋 Detalhes"
        ])
        
        with tabs[0]:
            st.markdown("### 📦 Análise de Produtos")
            
            df_produtos = calcular_kpis_por_produto(
                df_filtrado, df_metas_filtrado, ano, mes, dia_atual
            )
            
            fig_produtos = criar_grafico_produtos_completo(
                df_produtos, tema_escuro
            )
            st.plotly_chart(fig_produtos, use_container_width=True)
            
            st.markdown("### 📊 Tabela de KPIs por Produto")
            
            df_produtos_display = df_produtos.copy()
            df_produtos_display['Valor'] = df_produtos_display['Valor'].apply(
                formatar_moeda
            )
            df_produtos_display['Meta'] = df_produtos_display['Meta'].apply(
                formatar_moeda
            )
            df_produtos_display['Meta Diária'] = df_produtos_display[
                'Meta Diária'
            ].apply(formatar_moeda)
            df_produtos_display['% Atingimento'] = df_produtos_display[
                '% Atingimento'
            ].apply(formatar_percentual)
            df_produtos_display['Ticket Médio'] = df_produtos_display[
                'Ticket Médio'
            ].apply(formatar_moeda)
            df_produtos_display['Média DU'] = df_produtos_display[
                'Média DU'
            ].apply(formatar_moeda)
            df_produtos_display['Projeção'] = df_produtos_display[
                'Projeção'
            ].apply(formatar_moeda)
            df_produtos_display['% Projeção'] = df_produtos_display[
                '% Projeção'
            ].apply(formatar_percentual)
            
            st.dataframe(
                df_produtos_display,
                width='stretch',
                hide_index=True
            )
            
            st.info("💡 **PACK** = FGTS + ANT. BEN. + CNC 13º")
        
        with tabs[1]:
            st.markdown("### 🗺️ Análise por Região")
            
            df_regioes = calcular_kpis_por_regiao(
                df_filtrado, df_metas_filtrado, ano, mes, dia_atual
            )
            
            if not df_regioes.empty:
                fig_regional = criar_grafico_regional(
                    df_regioes, tema_escuro
                )
                st.plotly_chart(fig_regional, use_container_width=True)
                
                st.markdown("### 📊 Tabela de KPIs por Região")
                
                df_regioes_display = df_regioes.copy()
                df_regioes_display['Valor'] = df_regioes_display[
                    'Valor'
                ].apply(formatar_moeda)
                df_regioes_display['Pontos'] = df_regioes_display[
                    'Pontos'
                ].apply(formatar_numero)
                df_regioes_display['Meta Prata'] = df_regioes_display[
                    'Meta Prata'
                ].apply(formatar_numero)
                df_regioes_display['% Atingimento'] = df_regioes_display[
                    '% Atingimento'
                ].apply(formatar_percentual)
                df_regioes_display['Média DU'] = df_regioes_display[
                    'Média DU'
                ].apply(formatar_moeda)
                df_regioes_display['Projeção'] = df_regioes_display[
                    'Projeção'
                ].apply(formatar_moeda)
                
                st.dataframe(
                    df_regioes_display,
                    width='stretch',
                    hide_index=True
                )
            else:
                st.warning("Dados regionais não disponíveis")
        
        with tabs[2]:
            st.markdown("### 🏆 Rankings de Performance")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### 🏪 Top 10 Lojas por Atingimento")
                ranking_lojas = calcular_ranking_lojas_atingimento(
                    df_filtrado, df_metas_filtrado, top_n=10
                )
                
                if not ranking_lojas.empty:
                    ranking_lojas_display = ranking_lojas.copy()
                    ranking_lojas_display['Valor'] = ranking_lojas_display[
                        'Valor'
                    ].apply(formatar_moeda)
                    ranking_lojas_display['Pontos'] = ranking_lojas_display[
                        'Pontos'
                    ].apply(formatar_numero)
                    ranking_lojas_display['Meta Prata'] = (
                        ranking_lojas_display['Meta Prata'].apply(
                            formatar_numero
                        )
                    )
                    ranking_lojas_display['Atingimento %'] = (
                        ranking_lojas_display['Atingimento %'].apply(
                            formatar_percentual
                        )
                    )
                    ranking_lojas_display['Ticket Médio'] = (
                        ranking_lojas_display['Ticket Médio'].apply(
                            formatar_moeda
                        )
                    )
                    
                    st.dataframe(
                        ranking_lojas_display,
                        width='stretch',
                        hide_index=True
                    )
                else:
                    st.warning("Dados não disponíveis")
            
            with col2:
                st.markdown("#### 👥 Top 10 Consultores por Atingimento")
                ranking_consultores = (
                    calcular_ranking_consultores_atingimento(
                        df_filtrado, df_metas_filtrado, top_n=10
                    )
                )
                
                if not ranking_consultores.empty:
                    ranking_cons_display = ranking_consultores.copy()
                    ranking_cons_display['Valor'] = ranking_cons_display[
                        'Valor'
                    ].apply(formatar_moeda)
                    ranking_cons_display['Pontos'] = ranking_cons_display[
                        'Pontos'
                    ].apply(formatar_numero)
                    ranking_cons_display['Meta Prata'] = (
                        ranking_cons_display['Meta Prata'].apply(
                            formatar_numero
                        )
                    )
                    ranking_cons_display['Atingimento %'] = (
                        ranking_cons_display['Atingimento %'].apply(
                            formatar_percentual
                        )
                    )
                    ranking_cons_display['Ticket Médio'] = (
                        ranking_cons_display['Ticket Médio'].apply(
                            formatar_moeda
                        )
                    )
                    
                    st.dataframe(
                        ranking_cons_display,
                        width='stretch',
                        hide_index=True
                    )
                else:
                    st.warning("Dados não disponíveis")
        
        with tabs[3]:
            st.markdown("### 📈 Evolução Temporal")
            
            df_evolucao = calcular_evolucao_diaria(df_filtrado, ano, mes)
            
            if not df_evolucao.empty:
                fig_evolucao = criar_grafico_evolucao_diaria(
                    df_evolucao, kpis, tema_escuro
                )
                st.plotly_chart(fig_evolucao, use_container_width=True)
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    melhor_dia = df_evolucao.loc[
                        df_evolucao['VALOR'].idxmax()
                    ]
                    st.metric(
                        "🌟 Melhor Dia",
                        melhor_dia['DATA'].strftime('%d/%m'),
                        formatar_moeda(melhor_dia['VALOR'])
                    )
                
                with col2:
                    media_diaria = df_evolucao['VALOR'].mean()
                    st.metric(
                        "📊 Média Diária",
                        formatar_moeda(media_diaria),
                        f"{len(df_evolucao)} dias com vendas"
                    )
                
                with col3:
                    dias_acima_meta = (
                        df_evolucao['VALOR'] >= kpis['meta_diaria']
                    ).sum()
                    perc_dias_meta = (
                        dias_acima_meta / len(df_evolucao) * 100
                        if len(df_evolucao) > 0 else 0
                    )
                    st.metric(
                        "✅ Dias Acima da Meta",
                        f"{dias_acima_meta}",
                        f"{perc_dias_meta:.1f}% dos dias"
                    )
            else:
                st.warning("Dados de evolução não disponíveis")
        
        with tabs[4]:
            st.markdown("### 📋 Dados Detalhados")
            
            st.markdown("#### Filtros")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                lojas_disponiveis = ['Todas'] + sorted(
                    df_filtrado['LOJA'].unique().tolist()
                )
                loja_filtro = st.selectbox("Loja", lojas_disponiveis)
            
            with col2:
                if 'REGIAO' in df_filtrado.columns:
                    regioes_disponiveis_detalhe = ['Todas'] + sorted(
                        df_filtrado['REGIAO'].unique().tolist()
                    )
                    regiao_filtro = st.selectbox(
                        "Região (detalhe)", regioes_disponiveis_detalhe
                    )
                else:
                    regiao_filtro = 'Todas'
            
            with col3:
                produtos_disponiveis = ['Todos'] + sorted(
                    [str(x) for x in df_filtrado['TIPO_PRODUTO'].unique() 
                     if pd.notna(x)]
                )
                produto_filtro = st.selectbox("Produto", produtos_disponiveis)
            
            df_detalhes = df_filtrado.copy()
            
            if loja_filtro != 'Todas':
                df_detalhes = df_detalhes[df_detalhes['LOJA'] == loja_filtro]
            
            if regiao_filtro != 'Todas' and 'REGIAO' in df_filtrado.columns:
                df_detalhes = df_detalhes[
                    df_detalhes['REGIAO'] == regiao_filtro
                ]
            
            if produto_filtro != 'Todos':
                df_detalhes = df_detalhes[
                    df_detalhes['TIPO_PRODUTO'] == produto_filtro
                ]
            
            st.markdown(f"**{len(df_detalhes):,} registros encontrados**")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(
                    "Total Valor",
                    formatar_moeda(df_detalhes['VALOR'].sum())
                )
            with col2:
                st.metric(
                    "Total Pontos",
                    formatar_numero(df_detalhes['pontos'].sum())
                )
            with col3:
                ticket = (
                    df_detalhes['VALOR'].sum() / len(df_detalhes)
                    if len(df_detalhes) > 0 else 0
                )
                st.metric("Ticket Médio", formatar_moeda(ticket))
            
            colunas_exibir = [
                'DATA', 'LOJA', 'CONSULTOR', 'TIPO_PRODUTO', 'VALOR', 'pontos'
            ]
            if 'REGIAO' in df_detalhes.columns:
                colunas_exibir.insert(2, 'REGIAO')
            
            df_exibir = df_detalhes[colunas_exibir].copy()
            df_exibir['VALOR'] = df_exibir['VALOR'].apply(
                lambda x: f"R$ {x:,.2f}"
            )
            df_exibir['pontos'] = df_exibir['pontos'].apply(
                lambda x: f"{x:,.0f}"
            )
            
            st.dataframe(df_exibir, width='stretch', hide_index=True)
    
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
