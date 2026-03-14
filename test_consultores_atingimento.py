"""Script de teste para verificar TOP 10 Consultores por Atingimento."""
import pandas as pd
from src.data_processing.data_loader import carregar_dados_mes
from src.reports.resumo_geral import criar_resumo_geral

ano = 2026
mes = 3

print("Carregando dados...")
df, df_metas = carregar_dados_mes(ano, mes)

print(f"\nTotal de registros: {len(df)}")
print(f"Total de lojas nas metas: {len(df_metas)}")

print("\nColunas em df_metas:")
print(df_metas.columns.tolist())

print("\nVerificando META_PRATA:")
if 'META_PRATA' in df_metas.columns:
    print(f"META_PRATA encontrada!")
    print(f"Valores não-zero: {(df_metas['META_PRATA'] > 0).sum()}")
    print(f"\nPrimeiras linhas de META_PRATA:")
    print(df_metas[['LOJA', 'META_PRATA']].head(10))
else:
    print("META_PRATA NÃO encontrada!")

print("\nCriando resumo geral...")
resumo = criar_resumo_geral(df, df_metas, ano, mes)

print("\nVerificando top_consultores_atingimento:")
top_cons = resumo.get('top_consultores_atingimento', pd.DataFrame())
print(f"Tipo: {type(top_cons)}")
print(f"Vazio: {top_cons.empty}")
print(f"Shape: {top_cons.shape if not top_cons.empty else 'N/A'}")

if not top_cons.empty:
    print("\nColunas:")
    print(top_cons.columns.tolist())
    print("\nPrimeiras linhas:")
    print(top_cons.head())
    print("\nValores de Meta Prata:")
    print(top_cons['Meta Prata'].describe())
else:
    print("\n❌ DataFrame está VAZIO!")
    
print("\nVerificando consultores únicos no df:")
if 'CONSULTOR' in df.columns:
    print(f"Total de consultores únicos: {df['CONSULTOR'].nunique()}")
    print(f"Consultores por loja:")
    consultores_por_loja = df.groupby('LOJA')['CONSULTOR'].nunique()
    print(consultores_por_loja.head(10))
