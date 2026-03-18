"""
Script para analisar as tabelas de pontuação mensais.
"""
import pandas as pd
import os

# Listar arquivos de pontuação
pasta_pontuacao = 'pontuacao'
arquivos = os.listdir(pasta_pontuacao)
print("=" * 80)
print("ARQUIVOS DE PONTUAÇÃO ENCONTRADOS")
print("=" * 80)
for arquivo in sorted(arquivos):
    print(f"  - {arquivo}")

print("\n" + "=" * 80)
print("ANÁLISE DAS TABELAS DE PONTUAÇÃO")
print("=" * 80)

# Analisar cada arquivo
for arquivo in sorted(arquivos):
    if arquivo.endswith('.xlsx'):
        caminho = os.path.join(pasta_pontuacao, arquivo)
        print(f"\n📁 Arquivo: {arquivo}")
        print("-" * 80)
        
        # Listar abas
        excel_file = pd.ExcelFile(caminho)
        print(f"   Abas disponíveis: {excel_file.sheet_names}")
        
        # Analisar cada aba
        for aba in excel_file.sheet_names:
            print(f"\n   📊 Aba: {aba}")
            df = pd.read_excel(caminho, sheet_name=aba)
            print(f"      Dimensões: {df.shape[0]} linhas x {df.shape[1]} colunas")
            print(f"      Colunas: {list(df.columns)}")
            
            # Mostrar primeiras linhas
            print(f"\n      Primeiras 3 linhas:")
            print(df.head(3).to_string(index=False))
            
            # Verificar se tem coluna PTS
            if 'PTS' in df.columns:
                print(f"\n      ✓ Coluna PTS encontrada")
                print(f"        - Valores únicos de PTS: {sorted(df['PTS'].dropna().unique())}")
            else:
                print(f"\n      ⚠️  Coluna PTS NÃO encontrada")

print("\n" + "=" * 80)
print("ANÁLISE DO ARQUIVO DE TABELAS ATUAL")
print("=" * 80)

# Verificar arquivo de tabelas atual (março 2026)
tabelas_path = 'tabelas/Tabelas_marco_2026.xlsx'
if os.path.exists(tabelas_path):
    print(f"\n📁 Arquivo: {tabelas_path}")
    print("-" * 80)
    
    excel_file = pd.ExcelFile(tabelas_path)
    print(f"   Abas disponíveis: {excel_file.sheet_names}")
    
    for aba in excel_file.sheet_names:
        print(f"\n   📊 Aba: {aba}")
        df = pd.read_excel(tabelas_path, sheet_name=aba)
        print(f"      Dimensões: {df.shape[0]} linhas x {df.shape[1]} colunas")
        print(f"      Colunas: {list(df.columns)}")
        
        if 'PTS' in df.columns:
            print(f"\n      ✓ Coluna PTS encontrada")
            print(f"        - Valores únicos de PTS: {sorted(df['PTS'].dropna().unique())}")
            
            if 'PRODUTO' in df.columns:
                print(f"\n      Produtos com pontuação:")
                pts_por_produto = df.groupby('PRODUTO')['PTS'].first()
                for produto, pts in pts_por_produto.items():
                    print(f"        - {produto}: {pts} pontos")
else:
    print(f"\n⚠️  Arquivo {tabelas_path} não encontrado")

print("\n" + "=" * 80)
