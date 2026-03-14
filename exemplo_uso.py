"""
Script de exemplo de uso do sistema de análise de vendas.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.data_processing.consolidator import (
    consolidar_dados_mes,
    criar_dataset_completo,
    criar_resumo_periodo,
    calcular_dias_uteis
)
from src.reports.kpi_calculator import calcular_kpis_completos
from src.reports.product_tables import criar_tabelas_todos_produtos
from src.analysis.regional_analysis import comparar_regioes
from src.analysis.store_comparison import comparar_lojas
from src.analysis.performance_metrics import identificar_top_performers


def exemplo_basico():
    """Exemplo básico de uso do sistema."""
    print("=" * 80)
    print("EXEMPLO DE USO - SISTEMA DE ANÁLISE DE VENDAS")
    print("=" * 80)
    
    mes = 3
    ano = 2026
    
    print(f"\n1. Carregando e consolidando dados de {mes}/{ano}...")
    try:
        df = consolidar_dados_mes(mes, ano, aplicar_regras=True)
        print(f"   ✓ Dados carregados: {len(df)} registros")
    except Exception as e:
        print(f"   ✗ Erro ao carregar dados: {e}")
        return
    
    print(f"\n2. Calculando dias úteis...")
    dias_decorridos, dias_restantes = calcular_dias_uteis(mes, ano)
    print(f"   ✓ Dias úteis decorridos: {dias_decorridos}")
    print(f"   ✓ Dias úteis restantes: {dias_restantes}")
    
    print(f"\n3. Gerando resumo do período...")
    resumo = criar_resumo_periodo(mes, ano)
    print(f"   ✓ Total de vendas: R$ {resumo.get('total_valor', 0):,.2f}")
    print(f"   ✓ Total de pontos: {resumo.get('total_pontos', 0):,.0f}")
    print(f"   ✓ Número de consultores: {resumo.get('num_consultores', 0)}")
    print(f"   ✓ Número de lojas: {resumo.get('num_lojas', 0)}")
    print(f"   ✓ Número de regiões: {resumo.get('num_regioes', 0)}")
    
    if 'pontos' in df.columns:
        print(f"\n4. Calculando KPIs...")
        kpis = calcular_kpis_completos(df)
        
        print(f"\n   KPIs de Vendas:")
        print(f"   - Total de transações: {kpis['vendas']['total_transacoes']}")
        print(f"   - Ticket médio: R$ {kpis['vendas']['ticket_medio']:,.2f}")
        
        print(f"\n   KPIs de Performance:")
        print(f"   - Produtividade: {kpis['performance'].get('produtividade', 0):.2f}")
        
        print(f"\n   Produtos Especiais:")
        print(f"   - Emissões de cartão: {kpis['produtos_especiais'].get('emissoes_cartao', 0)}")
        print(f"   - Seguros Med: {kpis['produtos_especiais'].get('seguros_med', 0)}")
        print(f"   - Seguros Vida Familiar: {kpis['produtos_especiais'].get('seguros_vida_familiar', 0)}")
        print(f"   - Super Contas: {kpis['produtos_especiais'].get('super_contas', 0)}")
    
    if 'REGIAO' in df.columns:
        print(f"\n5. Comparando regiões...")
        df_regioes = comparar_regioes(df)
        print(f"   ✓ {len(df_regioes)} regiões analisadas")
        print(f"\n   Top 3 Regiões por Pontuação:")
        top_regioes = df_regioes.nlargest(3, 'total_pontos')
        for idx, row in top_regioes.iterrows():
            print(f"   {idx+1}. {row['regiao']}: {row['total_pontos']:,.0f} pontos")
    
    if 'LOJA' in df.columns:
        print(f"\n6. Comparando lojas...")
        df_lojas = comparar_lojas(df)
        print(f"   ✓ {len(df_lojas)} lojas analisadas")
        print(f"\n   Top 5 Lojas por Pontuação:")
        top_lojas = df_lojas.nlargest(5, 'total_pontos')
        for idx, row in top_lojas.iterrows():
            print(f"   {idx+1}. {row['loja']}: {row['total_pontos']:,.0f} pontos")
    
    if 'CONSULTOR' in df.columns:
        print(f"\n7. Identificando top performers...")
        top_consultores = identificar_top_performers(df, top_n=10)
        print(f"   ✓ Top 10 Consultores:")
        for idx, row in top_consultores.iterrows():
            print(f"   {row['posicao']}. {row['CONSULTOR']}: {row['pontos']:,.0f} pontos")
    
    print(f"\n{'=' * 80}")
    print("Exemplo concluído com sucesso!")
    print("=" * 80)


if __name__ == "__main__":
    exemplo_basico()
