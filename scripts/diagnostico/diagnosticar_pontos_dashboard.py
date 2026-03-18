"""
Script para diagnosticar problema com cálculo de pontos no dashboard.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
from src.config.settings import MESES_ARQUIVO

print("=" * 80)
print("DIAGNÓSTICO DO CÁLCULO DE PONTOS NO DASHBOARD")
print("=" * 80)

# Testar com dados de março 2026
mes = 3
ano = 2026
mes_nome = MESES_ARQUIVO.get(mes, '')

print(f"\n1. Testando com dados de {mes_nome.capitalize()} {ano}...")

try:
    # Importar função de carregamento do dashboard
    from dashboard_refatorado import carregar_dados
    
    print("   ✓ Função carregar_dados importada")
    
    # Carregar dados
    print("\n2. Carregando dados...")
    df, df_metas = carregar_dados(mes, ano)
    
    print(f"   ✓ Dados carregados: {len(df)} registros")
    print(f"   ✓ Colunas disponíveis: {list(df.columns)}")
    
    # Verificar se coluna pontos existe
    print("\n3. Verificando coluna 'pontos'...")
    if 'pontos' in df.columns:
        print("   ✓ Coluna 'pontos' encontrada")
        total_pontos = df['pontos'].sum()
        print(f"   ✓ Total de pontos: {total_pontos:,.0f}")
        
        # Verificar se há valores nulos
        nulos = df['pontos'].isna().sum()
        if nulos > 0:
            print(f"   ⚠️  {nulos} valores nulos encontrados")
        else:
            print("   ✓ Nenhum valor nulo")
        
        # Verificar se há zeros
        zeros = (df['pontos'] == 0).sum()
        if zeros > 0:
            print(f"   ⚠️  {zeros} registros com pontos = 0")
            print("\n   Produtos com pontos = 0:")
            produtos_zero = df[df['pontos'] == 0]['PRODUTO'].value_counts()
            for produto, count in produtos_zero.head(10).items():
                print(f"      - {produto}: {count} registros")
        else:
            print("   ✓ Nenhum registro com pontos = 0")
        
        # Mostrar amostra de dados
        print("\n4. Amostra de dados (primeiras 5 linhas):")
        colunas_exibir = ['PRODUTO', 'VALOR', 'pontos']
        if 'PONTOS' in df.columns:
            colunas_exibir.insert(2, 'PONTOS')
        print(df[colunas_exibir].head(5).to_string(index=False))
        
        # Verificar cálculo
        print("\n5. Verificando cálculo (primeiras 5 linhas):")
        if 'PONTOS' in df.columns:
            for idx in range(min(5, len(df))):
                row = df.iloc[idx]
                esperado = row['VALOR'] * row['PONTOS']
                calculado = row['pontos']
                status = "✓" if abs(esperado - calculado) < 0.01 else "✗"
                print(
                    f"   {status} {row['PRODUTO']}: "
                    f"R$ {row['VALOR']:,.2f} × {row['PONTOS']} = "
                    f"{esperado:,.0f} (calculado: {calculado:,.0f})"
                )
        else:
            print("   ⚠️  Coluna PONTOS não encontrada para verificação")
        
    else:
        print("   ✗ Coluna 'pontos' NÃO encontrada!")
        print("   Colunas disponíveis:", list(df.columns))
    
    # Verificar se PONTOS existe
    print("\n6. Verificando coluna 'PONTOS'...")
    if 'PONTOS' in df.columns:
        print("   ✓ Coluna 'PONTOS' encontrada")
        print(f"   Valores únicos: {sorted(df['PONTOS'].dropna().unique())}")
    else:
        print("   ✗ Coluna 'PONTOS' NÃO encontrada")
    
except Exception as e:
    print(f"\n✗ ERRO: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 80)
print("DIAGNÓSTICO CONCLUÍDO")
print("=" * 80)
