"""
Script para gerar relatório PDF de vendas.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.config.settings import LISTA_PRODUTOS
from src.data_processing.loader import (
    carregar_e_processar_dados,
)
from src.reports.pdf_executivo import (
    gerar_relatorio_executivo_pdf,
)
from src.reports.pdf_completo import (
    gerar_relatorio_completo_pdf,
)
from src.reports.pdf_regional import (
    gerar_relatorio_regional_pdf,
)
from src.reports.pdf_produto import (
    gerar_relatorio_produto_pdf,
)
from src.reports.pdf_produtos_loja import (
    gerar_relatorio_produtos_loja_pdf,
)


def main(mes=3, ano=2026):
    """Gera todos os relatórios PDF (13 arquivos no total)."""
    print(f"\n{'#'*80}")
    print(f"# GERAÇÃO DE RELATÓRIOS PDF")
    print(f"# Período: {mes:02d}/{ano}")
    print(f"{'#'*80}")
    
    df, df_metas, df_supervisores, dia_atual = (
        carregar_e_processar_dados(mes, ano)
    )
    
    print(f"\n{'='*80}")
    print(f"GERANDO ARQUIVOS PDF")
    print(f"{'='*80}")
    
    print(f"\n1. Gerando Relatório EXECUTIVO (KPIs e Visualizações)...")
    arquivo_executivo = gerar_relatorio_executivo_pdf(
        df, mes, ano, df_metas, dia_atual=dia_atual, df_supervisores=df_supervisores
    )
    print(f"   ✓ Relatório Executivo gerado: {arquivo_executivo}")
    
    print(f"\n2. Gerando Relatório COMPLETO (Todos os Dados)...")
    arquivo_completo = gerar_relatorio_completo_pdf(
        df, mes, ano, df_metas, dia_atual=dia_atual, df_supervisores=df_supervisores
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
    arquivos_produtos = []
    for produto in LISTA_PRODUTOS:
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
