"""
Script para comparar produtos dos dados com tabela de pontuação.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
from src.data_processing.pontuacao_loader import carregar_pontuacao_mensal
from src.config.settings import MESES_ARQUIVO

mes = 3
ano = 2026
mes_nome = MESES_ARQUIVO.get(mes, '')

print("=" * 80)
print("COMPARAÇÃO DE PRODUTOS: DADOS vs TABELA DE PONTUAÇÃO")
print("=" * 80)

# Carregar tabela de pontuação
print(f"\n1. Carregando tabela de pontuação de {mes_nome}...")
df_pontuacao = carregar_pontuacao_mensal(mes, ano)
print(f"   ✓ {len(df_pontuacao)} produtos na tabela de pontuação")
print("\n   Produtos na tabela de pontuação:")
for produto in sorted(df_pontuacao['PRODUTO'].unique()):
    pontos = df_pontuacao[df_pontuacao['PRODUTO'] == produto]['PONTOS'].iloc[0]
    print(f"      - '{produto}' ({pontos} pontos)")

# Carregar dados de vendas
print(f"\n2. Carregando dados de vendas de {mes_nome} {ano}...")
arquivo_vendas = f'digitacao/{mes_nome}_{ano}.xlsx'
df_vendas = pd.read_excel(arquivo_vendas)

if 'PRODUTO' in df_vendas.columns:
    produtos_vendas = df_vendas['PRODUTO'].dropna().unique()
    print(f"   ✓ {len(produtos_vendas)} produtos únicos nos dados de vendas")
    
    print("\n3. Produtos nos dados de vendas (top 20):")
    contagem = df_vendas['PRODUTO'].value_counts().head(20)
    for produto, count in contagem.items():
        print(f"      - '{produto}' ({count} registros)")
    
    # Verificar correspondência
    print("\n4. Verificando correspondência...")
    produtos_pontuacao_set = set(df_pontuacao['PRODUTO'].str.upper().str.strip())
    produtos_vendas_upper = df_vendas['PRODUTO'].str.upper().str.strip()
    
    correspondentes = []
    nao_correspondentes = []
    
    for produto in produtos_vendas[:100].unique():  # Primeiros 100 únicos
        produto_upper = str(produto).upper().strip()
        if produto_upper in produtos_pontuacao_set:
            correspondentes.append(produto)
        else:
            nao_correspondentes.append(produto)
    
    print(f"\n   ✓ {len(correspondentes)} produtos com correspondência")
    print(f"   ⚠️  {len(nao_correspondentes)} produtos SEM correspondência")
    
    if correspondentes:
        print("\n   Produtos COM correspondência (primeiros 10):")
        for p in correspondentes[:10]:
            print(f"      - '{p}'")
    
    if nao_correspondentes:
        print("\n   Produtos SEM correspondência (primeiros 10):")
        for p in nao_correspondentes[:10]:
            print(f"      - '{p}'")
    
    # Verificar se precisa de mapeamento
    print("\n5. Análise de mapeamento necessário...")
    print("   A tabela de pontuação usa nomes simplificados:")
    print("   - CNC, CARTÃO, FGTS, etc.")
    print("\n   Os dados de vendas usam nomes completos:")
    print("   - 'Cred Cta-Antec 13 Sal 1 Camp', 'REFIN-DEBITO EM CONTA', etc.")
    print("\n   ⚠️  É NECESSÁRIO criar um mapeamento entre os nomes!")

else:
    print("   ✗ Coluna PRODUTO não encontrada nos dados")

print("\n" + "=" * 80)
