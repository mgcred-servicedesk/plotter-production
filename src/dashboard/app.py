"""
Aplicação principal do Dashboard Streamlit.
"""
import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config.settings import DASHBOARD_TITLE, DASHBOARD_ICON, DASHBOARD_LAYOUT
from src.data_processing.consolidator import (
    consolidar_dados_mes,
    criar_resumo_periodo,
    calcular_dias_uteis
)
from src.reports.kpi_calculator import calcular_kpis_completos

st.set_page_config(
    page_title=DASHBOARD_TITLE,
    page_icon=DASHBOARD_ICON,
    layout=DASHBOARD_LAYOUT,
    initial_sidebar_state="expanded"
)


@st.cache_data(ttl=3600)
def carregar_dados(mes: int, ano: int):
    """Carrega e cacheia dados consolidados."""
    return consolidar_dados_mes(mes, ano, aplicar_regras=True)


@st.cache_data(ttl=3600)
def carregar_resumo(mes: int, ano: int):
    """Carrega e cacheia resumo do período."""
    return criar_resumo_periodo(mes, ano)


def main():
    """Função principal do dashboard."""
    
    st.title(f"{DASHBOARD_ICON} {DASHBOARD_TITLE}")
    
    with st.sidebar:
        st.header("Filtros")
        
        ano = st.selectbox(
            "Ano",
            options=[2024, 2025, 2026],
            index=2
        )
        
        mes = st.selectbox(
            "Mês",
            options=list(range(1, 13)),
            format_func=lambda x: {
                1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
                5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
                9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
            }[x],
            index=2
        )
        
        st.divider()
        
        st.markdown("### Navegação")
        st.markdown("""
        Use as páginas no menu lateral para:
        - 📊 **Visão Geral**: Overview completo
        - 🗺️ **Por Região**: Análise regional
        - 🏪 **Por Loja**: Análise por loja
        - 👤 **Por Consultor**: Análise individual
        - 📦 **Produtos**: Análise de produtos
        - 📈 **Comparativos**: Comparações
        """)
    
    try:
        with st.spinner('Carregando dados...'):
            df = carregar_dados(mes, ano)
            resumo = carregar_resumo(mes, ano)
        
        st.success(f"✓ Dados carregados: {len(df)} registros")
        
        st.header("Resumo Executivo")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "Total de Vendas",
                f"R$ {resumo.get('total_valor', 0):,.2f}"
                .replace(",", "X").replace(".", ",")
                .replace("X", "."),
                help="Valor total de vendas no período"
            )
        
        with col2:
            st.metric(
                "Total de Pontos",
                f"{resumo.get('total_pontos', 0):,.0f}"
                .replace(",", "."),
                help="Pontuação total acumulada"
            )
        
        with col3:
            st.metric(
                "Consultores",
                resumo.get('num_consultores', 0),
                help="Número de consultores ativos"
            )
        
        with col4:
            st.metric(
                "Lojas",
                resumo.get('num_lojas', 0),
                help="Número de lojas"
            )
        
        st.divider()
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Dias Úteis")
            dias_dec, dias_rest = calcular_dias_uteis(mes, ano)
            
            st.metric("Dias Úteis Decorridos", dias_dec)
            st.metric("Dias Úteis Restantes", dias_rest)
        
        with col2:
            st.subheader("Produtos Especiais")
            
            col_a, col_b = st.columns(2)
            with col_a:
                st.metric("Emissões de Cartão", resumo.get('emissoes_cartao', 0))
                st.metric("Seguros Med", resumo.get('seguros_med', 0))
            
            with col_b:
                st.metric("Seguros Vida Familiar", resumo.get('seguros_vida_familiar', 0))
                st.metric("Super Contas", resumo.get('super_contas', 0))
        
        st.divider()
        
        st.info("""
        💡 **Dica**: Use as páginas no menu lateral para análises mais detalhadas:
        - Análise por região, loja ou consultor
        - Tabelas de produtos com metas
        - Comparativos e rankings
        """)
        
    except FileNotFoundError as e:
        st.error(f"❌ Erro ao carregar dados: {e}")
        st.info("Verifique se os arquivos de dados estão disponíveis para o período selecionado.")
    
    except Exception as e:
        st.error(f"❌ Erro inesperado: {e}")
        st.exception(e)


if __name__ == "__main__":
    main()
