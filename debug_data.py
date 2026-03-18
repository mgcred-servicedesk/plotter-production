"""Debug: Verificar estrutura da coluna DATA."""
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from src.data_processing.column_mapper import (
    mapear_digitacao,
    mapear_tabelas,
    mapear_loja_regiao,
    adicionar_coluna_subtipo_via_merge,
    aplicar_regras_exclusao_valor_pontos
)

mes = 3
ano = 2026
mes_nome = 'marco'

df_digitacao = pd.read_excel(f'digitacao/{mes_nome}_{ano}.xlsx')
df_tabelas = pd.read_excel(f'tabelas/Tabelas_{mes_nome}_{ano}.xlsx')
df_loja_regiao = pd.read_excel('configuracao/loja_regiao.xlsx')

df_digitacao = mapear_digitacao(df_digitacao)
df_tabelas = mapear_tabelas(df_tabelas)
df_loja_regiao = mapear_loja_regiao(df_loja_regiao)

df_consolidado = adicionar_coluna_subtipo_via_merge(df_digitacao, df_tabelas)
df_consolidado['pontos'] = df_consolidado['VALOR'] * df_consolidado['PTS']
df_consolidado = aplicar_regras_exclusao_valor_pontos(df_consolidado)

df_consolidado = df_consolidado.merge(
    df_loja_regiao[['LOJA', 'REGIAO']],
    on='LOJA',
    how='left'
)

print("=" * 80)
print("DEBUG: Análise da coluna DATA")
print("=" * 80)

print(f"\nTotal de registros: {len(df_consolidado)}")
print(f"\nTipo da coluna DATA: {df_consolidado['DATA'].dtype}")
print(f"\nPrimeiros 10 valores de DATA:")
print(df_consolidado['DATA'].head(10))

print(f"\n\nDatas únicas:")
datas_unicas = df_consolidado['DATA'].unique()
print(f"Quantidade de datas únicas: {len(datas_unicas)}")
print(f"\nDatas únicas ordenadas:")
for data in sorted(datas_unicas):
    count = len(df_consolidado[df_consolidado['DATA'] == data])
    print(f"  {data}: {count} transações")

print(f"\n\nGroupBy por DATA:")
evolucao = df_consolidado.groupby('DATA').agg({
    'VALOR': 'sum',
    'pontos': 'sum'
}).reset_index()

print(f"Linhas após groupby: {len(evolucao)}")
print(f"\nPrimeiras 10 linhas do groupby:")
print(evolucao.head(10))

print(f"\n\nVerificando se DATA contém timestamp:")
print(df_consolidado['DATA'].head(5).apply(lambda x: type(x)))
