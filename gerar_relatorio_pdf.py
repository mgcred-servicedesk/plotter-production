"""
Script para gerar relatório PDF de vendas.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.data_processing.column_mapper import (
    mapear_digitacao,
    mapear_tabelas,
    mapear_metas,
    mapear_loja_regiao,
    adicionar_coluna_subtipo_via_merge,
    aplicar_regras_exclusao_valor_pontos
)
from src.reports.pdf_executivo import gerar_relatorio_executivo_pdf
from src.reports.pdf_completo import gerar_relatorio_completo_pdf
from src.reports.pdf_regional import gerar_relatorio_regional_pdf
from src.reports.pdf_produto import gerar_relatorio_produto_pdf
from src.reports.pdf_produtos_loja import gerar_relatorio_produtos_loja_pdf


def carregar_e_processar_dados(mes, ano):
    """Carrega e processa todos os dados necessários."""
    import pandas as pd
    
    print(f"\n{'='*80}")
    print(f"CARREGANDO DADOS - {mes:02d}/{ano}")
    print(f"{'='*80}")
    
    mes_nome = {
        1: 'janeiro', 2: 'fevereiro', 3: 'marco', 4: 'abril',
        5: 'maio', 6: 'junho', 7: 'julho', 8: 'agosto',
        9: 'setembro', 10: 'outubro', 11: 'novembro', 12: 'dezembro'
    }[mes]
    
    print(f"\n1. Carregando digitação...")
    df_digitacao = pd.read_excel(f'digitacao/{mes_nome}_{ano}.xlsx')
    print(f"   ✓ {len(df_digitacao)} registros carregados")
    
    print(f"\n2. Carregando tabelas de produtos...")
    df_tabelas = pd.read_excel(f'tabelas/Tabelas_{mes_nome}_{ano}.xlsx')
    print(f"   ✓ {len(df_tabelas)} produtos carregados")
    
    print(f"\n3. Carregando metas...")
    df_metas = pd.read_excel(f'metas/metas_{mes_nome}.xlsx')
    print(f"   ✓ {len(df_metas)} lojas com metas")
    
    print(f"\n4. Carregando configuração loja-região...")
    df_loja_regiao = pd.read_excel('configuracao/loja_regiao.xlsx')
    print(f"   ✓ {len(df_loja_regiao)} lojas mapeadas")
    
    print(f"\n5. Aplicando mapeamentos...")
    df_digitacao = mapear_digitacao(df_digitacao)
    df_tabelas = mapear_tabelas(df_tabelas)
    df_metas = mapear_metas(df_metas)
    df_loja_regiao = mapear_loja_regiao(df_loja_regiao)
    print(f"   ✓ Colunas mapeadas")
    
    print(f"\n6. Fazendo JOIN com tabelas...")
    df_consolidado = adicionar_coluna_subtipo_via_merge(df_digitacao, df_tabelas)
    print(f"   ✓ JOIN realizado: {len(df_consolidado)} registros")
    
    print(f"\n7. Calculando pontuação...")
    df_consolidado['pontos'] = df_consolidado['VALOR'] * df_consolidado['PTS']
    print(f"   ✓ Total de pontos: {df_consolidado['pontos'].sum():,.0f}")
    
    print(f"\n8. Aplicando regras de exclusão...")
    df_consolidado = aplicar_regras_exclusao_valor_pontos(df_consolidado)
    emissoes = df_consolidado['is_emissao_cartao'].sum()
    print(f"   ✓ {emissoes} produtos de emissão excluídos")
    
    print(f"\n9. Adicionando região...")
    df_consolidado = df_consolidado.merge(
        df_loja_regiao[['LOJA', 'REGIAO']],
        on='LOJA',
        how='left'
    )
    print(f"   ✓ Região adicionada")
    
    print(f"\n10. Totais finais:")
    print(f"   - Valor total: R$ {df_consolidado['VALOR'].sum():,.2f}")
    print(f"   - Pontos totais: {df_consolidado['pontos'].sum():,.0f}")
    
    return df_consolidado, df_metas


def main(mes=3, ano=2026):
    """Gera todos os relatórios PDF (13 arquivos no total)."""
    print(f"\n{'#'*80}")
    print(f"# GERAÇÃO DE RELATÓRIOS PDF")
    print(f"# Período: {mes:02d}/{ano}")
    print(f"{'#'*80}")
    
    df, df_metas = carregar_e_processar_dados(mes, ano)
    
    ultima_data = df['DATA'].max()
    dia_atual = ultima_data.day if hasattr(ultima_data, 'day') else None
    
    print(f"\n{'='*80}")
    print(f"GERANDO ARQUIVOS PDF")
    print(f"{'='*80}")
    
    print(f"\n1. Gerando Relatório EXECUTIVO (KPIs e Visualizações)...")
    arquivo_executivo = gerar_relatorio_executivo_pdf(
        df, mes, ano, df_metas, dia_atual=dia_atual
    )
    print(f"   ✓ Relatório Executivo gerado: {arquivo_executivo}")
    
    print(f"\n2. Gerando Relatório COMPLETO (Todos os Dados)...")
    arquivo_completo = gerar_relatorio_completo_pdf(
        df, mes, ano, df_metas, dia_atual=dia_atual
    )
    print(f"   ✓ Relatório Completo gerado: {arquivo_completo}")
    
    print(f"\n3. Gerando Relatórios REGIONAIS (Por Região)...")
    arquivos_regionais = gerar_relatorio_regional_pdf(
        df, mes, ano, df_metas, dia_atual=dia_atual
    )
    if arquivos_regionais:
        print(f"   ✓ {len(arquivos_regionais)} relatórios regionais gerados")
    else:
        print(f"   ⚠ Nenhum relatório regional gerado")
    
    print(f"\n4. Gerando Relatórios POR PRODUTO (5 produtos)...")
    produtos = ['CNC', 'SAQUE', 'CLT', 'CONSIGNADO', 'PACK']
    arquivos_produtos = []
    for produto in produtos:
        arquivo_produto = gerar_relatorio_produto_pdf(
            df, df_metas, produto, mes, ano, dia_atual=dia_atual
        )
        arquivos_produtos.append(arquivo_produto)
        print(f"   ✓ Relatório {produto} gerado")
    
    print(f"\n5. Gerando Relatório PRODUTOS POR LOJA (Consolidado)...")
    arquivo_produtos_loja = gerar_relatorio_produtos_loja_pdf(
        df, df_metas, mes, ano, dia_atual=dia_atual
    )
    print(f"   ✓ Relatório Produtos por Loja gerado")
    
    total_arquivos = (
        1 + 1 + len(arquivos_regionais) + len(arquivos_produtos) + 1
    )
    
    print(f"\n{'#'*80}")
    print(f"# ✓ RELATÓRIOS PDF GERADOS COM SUCESSO!")
    print(f"# Executivo: 1 arquivo")
    print(f"# Completo: 1 arquivo")
    print(f"# Regionais: {len(arquivos_regionais)} arquivo(s)")
    print(f"# Por Produto: {len(arquivos_produtos)} arquivo(s)")
    print(f"# Produtos por Loja: 1 arquivo")
    print(f"# TOTAL: {total_arquivos} arquivos PDF gerados")
    print(f"# Total de pontos: {df['pontos'].sum():,.0f}")
    print(f"# Total de vendas: R$ {df['VALOR'].sum():,.2f}")
    print(f"{'#'*80}\n")
    
    return {
        'executivo': arquivo_executivo,
        'completo': arquivo_completo,
        'regionais': arquivos_regionais,
        'produtos': arquivos_produtos,
        'produtos_loja': arquivo_produtos_loja
    }


if __name__ == "__main__":
    arquivo = main(mes=3, ano=2026)
