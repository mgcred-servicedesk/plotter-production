"""
Dashboard interativo de vendas com Streamlit.
"""
import sys
from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from src.data_processing.column_mapper import (
    mapear_digitacao,
    mapear_tabelas,
    mapear_metas,
    mapear_loja_regiao,
    adicionar_coluna_subtipo_via_merge,
    aplicar_regras_exclusao_valor_pontos
)
from src.data_processing.pontuacao_loader import (
    calcular_pontos_com_tabela_mensal
)
from src.reports.tabela_produtos import calcular_dias_uteis
from src.reports.resumo_geral import criar_resumo_geral


st.set_page_config(
    page_title="Dashboard de Vendas",
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
    
    df_consolidado = adicionar_coluna_subtipo_via_merge(df_digitacao, df_tabelas)
    
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
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_numero(valor):
    """Formata número com separador de milhares."""
    return f"{valor:,.0f}".replace(",", ".")


def criar_metricas_principais(df, df_metas, ano, mes, dia_atual):
    """Cria cards de métricas principais."""
    du_total, du_decorridos, du_restantes = calcular_dias_uteis(ano, mes, dia_atual)
    
    total_vendas = df['VALOR'].sum()
    total_pontos = df['pontos'].sum()
    
    meta_total = 0
    if 'META  LOJA PRATA' in df_metas.columns:
        meta_total = df_metas['META  LOJA PRATA'].sum()
    
    perc_ating = (total_vendas / meta_total * 100) if meta_total > 0 else 0
    media_du = total_vendas / du_decorridos if du_decorridos > 0 else 0
    projecao = media_du * du_total
    perc_proj = (projecao / meta_total * 100) if meta_total > 0 else 0
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric(
            "Total de Vendas",
            formatar_moeda(total_vendas),
            f"{perc_ating:.1f}% da meta"
        )
    
    with col2:
        st.metric(
            "Meta do Mês",
            formatar_moeda(meta_total),
            f"{du_restantes} dias úteis restantes"
        )
    
    with col3:
        st.metric(
            "Projeção",
            formatar_moeda(projecao),
            f"{perc_proj:.1f}% da meta"
        )
    
    with col4:
        st.metric(
            "Média por DU",
            formatar_moeda(media_du),
            f"{du_decorridos} dias decorridos"
        )
    
    with col5:
        st.metric(
            "Total de Pontos",
            formatar_numero(total_pontos),
            f"{df['LOJA'].nunique()} lojas"
        )


def criar_grafico_produtos(df, df_metas, ano, mes, dia_atual):
    """Cria gráfico de produtos com metas e projeções."""
    du_total, du_decorridos, du_restantes = calcular_dias_uteis(ano, mes, dia_atual)
    
    mapeamento_produtos = {
        'CNC': ['CNC'],
        'SAQUE': ['SAQUE', 'SAQUE BENEFICIO'],
        'CLT': ['CONSIG PRIV'],
        'CONSIGNADO': ['CONSIG', 'Portabilidade'],
        'PACK': ['FGTS', 'CNC 13º']
    }
    
    mapeamento_colunas_meta = {
        'CNC': 'CNC LOJA',
        'SAQUE': 'SAQUE LOJA',
        'CLT': 'CLT',
        'CONSIGNADO': 'CONSIGNADO',
        'PACK': 'META  LOJA FGTS & ANT. BEN.13º'
    }
    
    produtos_emissao = ['EMISSAO', 'EMISSAO CC', 'EMISSAO CB']
    
    dados_produtos = []
    
    for produto_nome, tipos in mapeamento_produtos.items():
        df_produto = df[df['TIPO_PRODUTO'].isin(tipos)].copy()
        
        mask_emissao = df_produto['TIPO_PRODUTO'].isin(produtos_emissao)
        df_produto.loc[mask_emissao, 'VALOR'] = 0
        
        valor = df_produto['VALOR'].sum()
        
        coluna_meta = mapeamento_colunas_meta.get(produto_nome, f'{produto_nome} LOJA')
        meta_total = 0
        if coluna_meta in df_metas.columns:
            meta_total = df_metas[coluna_meta].sum()
        
        media_du = valor / du_decorridos if du_decorridos > 0 else 0
        projecao = media_du * du_total
        
        dados_produtos.append({
            'Produto': produto_nome,
            'Realizado': valor,
            'Meta': meta_total,
            'Projeção': projecao
        })
    
    df_produtos = pd.DataFrame(dados_produtos)
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        name='Realizado',
        x=df_produtos['Produto'],
        y=df_produtos['Realizado'],
        marker_color='#366092',
        text=df_produtos['Realizado'].apply(lambda x: formatar_moeda(x)),
        textposition='outside'
    ))
    
    fig.add_trace(go.Bar(
        name='Meta',
        x=df_produtos['Produto'],
        y=df_produtos['Meta'],
        marker_color='#1F4E78',
        text=df_produtos['Meta'].apply(lambda x: formatar_moeda(x)),
        textposition='outside'
    ))
    
    fig.add_trace(go.Scatter(
        name='Projeção',
        x=df_produtos['Produto'],
        y=df_produtos['Projeção'],
        mode='lines+markers',
        marker=dict(size=10, color='#FF6B6B'),
        line=dict(width=3, color='#FF6B6B'),
        text=df_produtos['Projeção'].apply(lambda x: formatar_moeda(x)),
        textposition='top center'
    ))
    
    fig.update_layout(
        title='Produtos: Realizado vs Meta vs Projeção',
        xaxis_title='Produto',
        yaxis_title='Valor (R$)',
        barmode='group',
        height=500,
        hovermode='x unified',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    return fig


def criar_grafico_regional(df, df_metas):
    """Cria gráfico de análise regional."""
    if 'REGIAO' not in df.columns:
        return None
    
    analise = df.groupby('REGIAO').agg({
        'VALOR': 'sum',
        'pontos': 'sum',
        'LOJA': 'nunique'
    }).reset_index()
    
    analise = analise.sort_values('pontos', ascending=False)
    
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=('Valor por Região', 'Pontos por Região'),
        specs=[[{'type': 'bar'}, {'type': 'bar'}]]
    )
    
    fig.add_trace(
        go.Bar(
            x=analise['REGIAO'],
            y=analise['VALOR'],
            name='Valor',
            marker_color='#366092',
            text=analise['VALOR'].apply(lambda x: formatar_moeda(x)),
            textposition='outside'
        ),
        row=1, col=1
    )
    
    fig.add_trace(
        go.Bar(
            x=analise['REGIAO'],
            y=analise['pontos'],
            name='Pontos',
            marker_color='#1F4E78',
            text=analise['pontos'].apply(lambda x: formatar_numero(x)),
            textposition='outside'
        ),
        row=1, col=2
    )
    
    fig.update_layout(
        height=500,
        showlegend=False,
        title_text="Análise por Região"
    )
    
    return fig


def criar_tabela_ranking_lojas(df, df_metas, top_n=20):
    """Cria tabela de ranking de lojas."""
    ranking = df.groupby('LOJA').agg({
        'VALOR': 'sum',
        'pontos': 'sum',
        'REGIAO': 'first'
    }).reset_index()
    
    ranking = ranking.sort_values('pontos', ascending=False).head(top_n)
    ranking['Posição'] = range(1, len(ranking) + 1)
    
    ranking['Valor'] = ranking['VALOR'].apply(formatar_moeda)
    ranking['Pontos'] = ranking['pontos'].apply(formatar_numero)
    
    ranking = ranking[['Posição', 'LOJA', 'REGIAO', 'Valor', 'Pontos']]
    ranking.columns = ['#', 'Loja', 'Região', 'Valor', 'Pontos']
    
    return ranking


def criar_tabela_ranking_consultores(df, top_n=20):
    """Cria tabela de ranking de consultores."""
    ranking = df.groupby('CONSULTOR').agg({
        'VALOR': 'sum',
        'pontos': 'sum',
        'LOJA': 'first'
    }).reset_index()
    
    ranking = ranking.sort_values('pontos', ascending=False).head(top_n)
    ranking['Posição'] = range(1, len(ranking) + 1)
    
    ranking['Valor'] = ranking['VALOR'].apply(formatar_moeda)
    ranking['Pontos'] = ranking['pontos'].apply(formatar_numero)
    
    ranking = ranking[['Posição', 'CONSULTOR', 'LOJA', 'Valor', 'Pontos']]
    ranking.columns = ['#', 'Consultor', 'Loja', 'Valor', 'Pontos']
    
    return ranking


def main():
    """Função principal do dashboard."""
    st.title("📊 Dashboard de Vendas")
    st.markdown("---")
    
    with st.sidebar:
        st.header("⚙️ Configurações")
        
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
    
    try:
        with st.spinner("Carregando dados..."):
            df, df_metas = carregar_dados(mes, ano)
        
        ultima_data = df['DATA'].max()
        dia_atual = ultima_data.day if hasattr(ultima_data, 'day') else None
        
        st.success(f"✅ Dados carregados: {len(df)} registros | Última data: {ultima_data.strftime('%d/%m/%Y')}")
        
        st.markdown("### 📈 Métricas Principais")
        criar_metricas_principais(df, df_metas, ano, mes, dia_atual)
        
        st.markdown("---")
        
        tab1, tab2, tab3, tab4 = st.tabs([
            "📊 Produtos",
            "🗺️ Regiões",
            "🏆 Rankings",
            "📋 Detalhes"
        ])
        
        with tab1:
            st.markdown("### Análise de Produtos")
            fig_produtos = criar_grafico_produtos(df, df_metas, ano, mes, dia_atual)
            st.plotly_chart(fig_produtos, use_container_width=True)
            
            st.markdown("### Detalhamento por Produto")
            col1, col2 = st.columns(2)
            
            with col1:
                produto_selecionado = st.selectbox(
                    "Selecione o produto",
                    ['CNC', 'SAQUE', 'CLT', 'CONSIGNADO', 'PACK']
                )
            
            mapeamento_produtos = {
                'CNC': ['CNC'],
                'SAQUE': ['SAQUE', 'SAQUE BENEFICIO'],
                'CLT': ['CONSIG PRIV'],
                'CONSIGNADO': ['CONSIG', 'Portabilidade'],
                'PACK': ['FGTS', 'CNC 13º']
            }
            
            df_produto_sel = df[df['TIPO_PRODUTO'].isin(mapeamento_produtos[produto_selecionado])]
            
            ranking_produto = df_produto_sel.groupby('LOJA').agg({
                'VALOR': 'sum',
                'REGIAO': 'first'
            }).reset_index().sort_values('VALOR', ascending=False).head(10)
            
            fig_produto_lojas = px.bar(
                ranking_produto,
                x='LOJA',
                y='VALOR',
                color='REGIAO',
                title=f'Top 10 Lojas - {produto_selecionado}',
                labels={'VALOR': 'Valor (R$)', 'LOJA': 'Loja'},
                height=400
            )
            
            st.plotly_chart(fig_produto_lojas, use_container_width=True)
        
        with tab2:
            st.markdown("### Análise por Região")
            fig_regional = criar_grafico_regional(df, df_metas)
            if fig_regional:
                st.plotly_chart(fig_regional, use_container_width=True)
            
            if 'REGIAO' in df.columns:
                st.markdown("### Detalhamento Regional")
                regiao_selecionada = st.selectbox(
                    "Selecione a região",
                    sorted(df['REGIAO'].unique())
                )
                
                df_regiao = df[df['REGIAO'] == regiao_selecionada]
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total de Vendas", formatar_moeda(df_regiao['VALOR'].sum()))
                with col2:
                    st.metric("Total de Pontos", formatar_numero(df_regiao['pontos'].sum()))
                with col3:
                    st.metric("Número de Lojas", df_regiao['LOJA'].nunique())
                
                ranking_lojas_regiao = df_regiao.groupby('LOJA').agg({
                    'VALOR': 'sum',
                    'pontos': 'sum'
                }).reset_index().sort_values('pontos', ascending=False)
                
                fig_lojas_regiao = px.bar(
                    ranking_lojas_regiao,
                    x='LOJA',
                    y='VALOR',
                    title=f'Lojas da Região {regiao_selecionada}',
                    labels={'VALOR': 'Valor (R$)', 'LOJA': 'Loja'},
                    height=400
                )
                
                st.plotly_chart(fig_lojas_regiao, use_container_width=True)
        
        with tab3:
            st.markdown("### 🏆 Rankings")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### Top 20 Lojas")
                ranking_lojas = criar_tabela_ranking_lojas(df, df_metas, top_n=20)
                st.dataframe(ranking_lojas, use_container_width=True, hide_index=True)
            
            with col2:
                st.markdown("#### Top 20 Consultores")
                ranking_consultores = criar_tabela_ranking_consultores(df, top_n=20)
                st.dataframe(ranking_consultores, use_container_width=True, hide_index=True)
        
        with tab4:
            st.markdown("### 📋 Dados Detalhados")
            
            st.markdown("#### Filtros")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                lojas_disponiveis = ['Todas'] + sorted(df['LOJA'].unique().tolist())
                loja_filtro = st.selectbox("Loja", lojas_disponiveis)
            
            with col2:
                if 'REGIAO' in df.columns:
                    regioes_disponiveis = ['Todas'] + sorted(df['REGIAO'].unique().tolist())
                    regiao_filtro = st.selectbox("Região", regioes_disponiveis)
                else:
                    regiao_filtro = 'Todas'
            
            with col3:
                produtos_disponiveis = ['Todos'] + sorted(df['TIPO_PRODUTO'].unique().tolist())
                produto_filtro = st.selectbox("Produto", produtos_disponiveis)
            
            df_filtrado = df.copy()
            
            if loja_filtro != 'Todas':
                df_filtrado = df_filtrado[df_filtrado['LOJA'] == loja_filtro]
            
            if regiao_filtro != 'Todas' and 'REGIAO' in df.columns:
                df_filtrado = df_filtrado[df_filtrado['REGIAO'] == regiao_filtro]
            
            if produto_filtro != 'Todos':
                df_filtrado = df_filtrado[df_filtrado['TIPO_PRODUTO'] == produto_filtro]
            
            st.markdown(f"**{len(df_filtrado)} registros encontrados**")
            
            colunas_exibir = ['DATA', 'LOJA', 'CONSULTOR', 'TIPO_PRODUTO', 'VALOR', 'pontos']
            if 'REGIAO' in df_filtrado.columns:
                colunas_exibir.insert(2, 'REGIAO')
            
            df_exibir = df_filtrado[colunas_exibir].copy()
            df_exibir['VALOR'] = df_exibir['VALOR'].apply(lambda x: f"R$ {x:,.2f}")
            df_exibir['pontos'] = df_exibir['pontos'].apply(lambda x: f"{x:,.0f}")
            
            st.dataframe(df_exibir, use_container_width=True, hide_index=True)
    
    except FileNotFoundError as e:
        st.error(f"❌ Erro ao carregar dados: {e}")
        st.info("Verifique se os arquivos de dados estão disponíveis para o período selecionado.")
    except Exception as e:
        st.error(f"❌ Erro inesperado: {e}")
        st.exception(e)


if __name__ == "__main__":
    main()
