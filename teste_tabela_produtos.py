"""
Script de teste para validar tabela de produtos com métricas e metas.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
from src.data_processing.column_mapper import (
    mapear_digitacao,
    mapear_tabelas,
    mapear_metas,
    mapear_loja_regiao,
    adicionar_coluna_subtipo_via_merge,
    aplicar_regras_exclusao_valor_pontos
)
from src.reports.tabela_produtos import (
    calcular_dias_uteis,
    criar_tabela_por_produto,
    criar_tabela_por_consultor,
    criar_tabela_por_loja
)


def main():
    print("\n" + "="*80)
    print("TESTE - TABELA DE PRODUTOS COM MÉTRICAS E METAS")
    print("="*80)
    
    mes = 3
    ano = 2026
    dia_atual = 12
    
    print(f"\n1. Calculando dias úteis de {mes:02d}/{ano}...")
    total_du, du_decorridos, du_restantes = calcular_dias_uteis(ano, mes, dia_atual)
    print(f"   - Total de dias úteis: {total_du}")
    print(f"   - Dias úteis decorridos (até dia {dia_atual}): {du_decorridos}")
    print(f"   - Dias úteis restantes: {du_restantes}")
    
    print(f"\n2. Carregando dados...")
    df_digitacao = pd.read_excel(f'digitacao/marco_{ano}.xlsx')
    df_tabelas = pd.read_excel(f'tabelas/Tabelas_marco_{ano}.xlsx')
    df_metas = pd.read_excel(f'metas/metas_marco.xlsx')
    df_loja_regiao = pd.read_excel('configuracao/loja_regiao.xlsx')
    
    print(f"\n3. Processando dados...")
    df_digitacao = mapear_digitacao(df_digitacao)
    df_tabelas = mapear_tabelas(df_tabelas)
    df_metas = mapear_metas(df_metas)
    df_loja_regiao = mapear_loja_regiao(df_loja_regiao)
    
    df = adicionar_coluna_subtipo_via_merge(df_digitacao, df_tabelas)
    df['pontos'] = df['VALOR'] * df['PTS']
    df = aplicar_regras_exclusao_valor_pontos(df)
    
    df = df.merge(df_loja_regiao[['LOJA', 'REGIAO']], on='LOJA', how='left')
    
    print(f"   ✓ {len(df)} registros processados")
    print(f"   ✓ Total de pontos: {df['pontos'].sum():,.0f}")
    print(f"   ✓ Total de vendas: R$ {df['VALOR'].sum():,.2f}")
    
    print(f"\n4. Gerando tabela por PRODUTO...")
    tabela_produtos = criar_tabela_por_produto(df, df_metas, ano, mes, dia_atual)
    print(f"\n{tabela_produtos.to_string(index=False)}")
    
    print(f"\n5. Gerando tabela por LOJA (top 10)...")
    tabela_lojas = criar_tabela_por_loja(df, df_metas, ano, mes, dia_atual)
    print(f"\n{tabela_lojas.head(10).to_string(index=False)}")
    
    print(f"\n6. Gerando tabela por CONSULTOR (top 10)...")
    tabela_consultores = criar_tabela_por_consultor(df, df_metas, ano, mes, dia_atual)
    print(f"\n{tabela_consultores.head(10).to_string(index=False)}")
    
    print(f"\n{'='*80}")
    print("✓ TESTE CONCLUÍDO COM SUCESSO!")
    print(f"{'='*80}\n")
    
    return tabela_produtos, tabela_lojas, tabela_consultores


if __name__ == "__main__":
    tabela_produtos, tabela_lojas, tabela_consultores = main()
