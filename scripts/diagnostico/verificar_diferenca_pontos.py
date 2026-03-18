"""
Script para verificar diferença entre pontos calculados e esperados.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
from dashboard_refatorado import carregar_dados

mes = 3
ano = 2026

print("=" * 80)
print("ANÁLISE DE DIFERENÇA DE PONTOS")
print("=" * 80)

print(f"\n1. Carregando dados de março {ano}...")
df, df_metas = carregar_dados(mes, ano)

total_calculado = df['pontos'].sum()
total_esperado = 20567417.05

print(f"\n2. Comparação de totais:")
print(f"   Calculado: {total_calculado:,.2f} pontos")
print(f"   Esperado:  {total_esperado:,.2f} pontos")
print(f"   Diferença: {total_calculado - total_esperado:,.2f} pontos")
print(f"   % Diferença: {((total_calculado / total_esperado) - 1) * 100:.2f}%")

print(f"\n3. Análise por TIPO_PRODUTO:")
print("-" * 80)
analise = df.groupby('TIPO_PRODUTO').agg({
    'VALOR': 'sum',
    'pontos': 'sum',
    'PONTOS': 'first'
}).reset_index()

analise = analise.sort_values('pontos', ascending=False)
print(analise.to_string(index=False))

print(f"\n4. Verificando se há produtos com PONTOS diferentes do esperado:")
print("-" * 80)

# Verificar se algum produto tem pontuação duplicada ou errada
if 'PONTOS' in df.columns:
    pontos_por_tipo = df.groupby('TIPO_PRODUTO')['PONTOS'].unique()
    for tipo, pontos_unicos in pontos_por_tipo.items():
        if len(pontos_unicos) > 1:
            print(f"   ⚠️  {tipo}: múltiplos valores de PONTOS: {pontos_unicos}")
        else:
            print(f"   ✓ {tipo}: {pontos_unicos[0]} pontos")

print(f"\n5. Verificando produtos sem pontuação (PONTOS = 0):")
print("-" * 80)
sem_pontos = df[df['PONTOS'] == 0]
if len(sem_pontos) > 0:
    print(f"   {len(sem_pontos)} registros sem pontuação")
    print(f"   Valor total: R$ {sem_pontos['VALOR'].sum():,.2f}")
    print("\n   Produtos sem pontuação (top 10):")
    produtos_sem_pontos = sem_pontos.groupby('TIPO_PRODUTO').agg({
        'VALOR': 'sum',
        'PRODUTO': 'count'
    }).reset_index()
    produtos_sem_pontos.columns = ['TIPO_PRODUTO', 'VALOR', 'QTD']
    produtos_sem_pontos = produtos_sem_pontos.sort_values('VALOR', ascending=False)
    print(produtos_sem_pontos.head(10).to_string(index=False))
else:
    print("   ✓ Todos os produtos têm pontuação")

print(f"\n6. Comparando com cálculo usando PTS (método antigo):")
print("-" * 80)
if 'PTS' in df.columns:
    df['pontos_pts'] = df['VALOR'] * df['PTS']
    total_pts = df['pontos_pts'].sum()
    print(f"   Total com PTS: {total_pts:,.2f} pontos")
    print(f"   Total com PONTOS: {total_calculado:,.2f} pontos")
    print(f"   Diferença: {total_calculado - total_pts:,.2f} pontos")
    
    # Verificar onde há diferença
    df['diferenca'] = df['pontos'] - df['pontos_pts']
    com_diferenca = df[df['diferenca'] != 0]
    if len(com_diferenca) > 0:
        print(f"\n   {len(com_diferenca)} registros com diferença entre PTS e PONTOS")
        print("\n   Análise por TIPO_PRODUTO:")
        diff_por_tipo = com_diferenca.groupby('TIPO_PRODUTO').agg({
            'diferenca': 'sum',
            'PRODUTO': 'count',
            'PTS': 'first',
            'PONTOS': 'first'
        }).reset_index()
        diff_por_tipo.columns = ['TIPO_PRODUTO', 'DIFERENCA', 'QTD', 'PTS', 'PONTOS']
        print(diff_por_tipo.to_string(index=False))

print("\n" + "=" * 80)
