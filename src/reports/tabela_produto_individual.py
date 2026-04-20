"""
Módulo para criar relatórios individuais por produto.
"""

import pandas as pd
from src.reports.tabela_produtos import calcular_dias_uteis


def criar_tabela_produto_individual(df, df_metas, produto_nome, ano, mes, dia_atual=None):
    """
    Cria tabela individual para um produto específico, agrupada por região.
    
    Para cada loja, exibe:
    - Loja
    - Valor
    - Meta
    - Meta Diária
    - % Atingimento
    - Média DU
    - Ticket Médio
    - Projeção
    - % Projeção
    
    Ordenado por % Atingimento (decrescente) dentro de cada região.
    
    Args:
        df: DataFrame consolidado com vendas
        df_metas: DataFrame com metas
        produto_nome: Nome do produto ('CNC', 'SAQUE', 'CLT', 'CONSIGNADO', 'PACK')
        ano: Ano do relatório
        mes: Mês do relatório
        dia_atual: Dia atual para cálculo de dias úteis
        
    Returns:
        dict com DataFrames agrupados por região
    """
    du_total, du_decorridos, du_restantes = calcular_dias_uteis(ano, mes, dia_atual)
    
    mapeamento_produtos = {
        'CNC': ['CNC'],
        'SAQUE': ['SAQUE', 'SAQUE BENEFICIO'],
        'CLT': ['CONSIG PRIV'],
        'CONSIGNADO': ['CONSIG', 'Portabilidade'],
        'PACK': ['FGTS', 'CNC 13º']
    }
    
    mapeamento_colunas_meta = {
        'CNC': 'CNC LOJA',
        'SAQUE': 'SAQUE LOJA',
        'CLT': 'CLT',
        'CONSIGNADO': 'CONSIGNADO',
        'PACK': 'META  LOJA FGTS & ANT. BEN.13º'
    }
    
    produtos_emissao = ['EMISSAO', 'EMISSAO CC', 'EMISSAO CB']
    
    if 'REGIAO' not in df.columns or 'LOJA' not in df.columns:
        return {}
    
    if produto_nome not in mapeamento_produtos:
        return {}
    
    tipos_produto = mapeamento_produtos[produto_nome]
    coluna_meta = mapeamento_colunas_meta.get(produto_nome, f'{produto_nome} LOJA')
    
    regioes = sorted(df['REGIAO'].unique())
    tabelas_por_regiao = {}
    
    for regiao in regioes:
        df_regiao = df[df['REGIAO'] == regiao].copy()
        
        lojas = sorted(df_regiao['LOJA'].unique())
        dados_lojas = []
        
        for loja in lojas:
            df_loja = df_regiao[df_regiao['LOJA'] == loja].copy()
            
            mask_emissao = df_loja['TIPO_PRODUTO'].isin(produtos_emissao)
            df_loja.loc[mask_emissao, 'VALOR'] = 0
            
            df_produto = df_loja[df_loja['TIPO_PRODUTO'].isin(tipos_produto)]
            
            valor = df_produto['VALOR'].sum()
            quantidade = len(df_produto)
            
            meta = 0
            if coluna_meta in df_metas.columns:
                meta_loja = df_metas[df_metas['LOJA'] == loja]
                if not meta_loja.empty:
                    meta_valor = meta_loja[coluna_meta].iloc[0]
                    meta = pd.to_numeric(meta_valor, errors='coerce')
                    if pd.isna(meta):
                        meta = 0
            
            perc_ating = (valor / meta * 100) if meta > 0 else 0
            media_du = valor / du_decorridos if du_decorridos > 0 else 0
            ticket_medio = valor / quantidade if quantidade > 0 else 0
            projecao = media_du * du_total
            perc_projecao = (projecao / meta * 100) if meta > 0 else 0
            
            meta_restante = meta - valor
            if du_restantes > 0 and meta_restante > 0:
                meta_diaria = meta_restante / du_restantes
            else:
                meta_diaria = 0
            
            dados_lojas.append({
                'Loja': loja,
                'Valor': valor,
                'Meta': meta,
                'Meta Diária': meta_diaria,
                '% Ating.': perc_ating,
                'Média DU': media_du,
                'Ticket Médio': ticket_medio,
                'Projeção': projecao,
                '% Proj.': perc_projecao
            })
        
        if dados_lojas:
            df_tabela = pd.DataFrame(dados_lojas)
            df_tabela = df_tabela.sort_values('% Ating.', ascending=False)
            
            linha_total = {
                'Loja': f'TOTAL {regiao}',
                'Valor': df_tabela['Valor'].sum(),
                'Meta': df_tabela['Meta'].sum(),
                '% Ating.': 0,
                'Média DU': 0,
                'Ticket Médio': df_tabela['Ticket Médio'].mean(),
                'Projeção': 0,
                '% Proj.': 0,
                'Meta Diária': 0
            }
            
            total_valor = linha_total['Valor']
            total_meta = linha_total['Meta']
            
            linha_total['% Ating.'] = (total_valor / total_meta * 100) if total_meta > 0 else 0
            linha_total['Média DU'] = total_valor / du_decorridos if du_decorridos > 0 else 0
            linha_total['Projeção'] = linha_total['Média DU'] * du_total
            linha_total['% Proj.'] = (linha_total['Projeção'] / total_meta * 100) if total_meta > 0 else 0
            
            meta_restante = total_meta - total_valor
            if du_restantes > 0 and meta_restante > 0:
                linha_total['Meta Diária'] = meta_restante / du_restantes
            else:
                linha_total['Meta Diária'] = 0
            
            df_tabela = pd.concat([df_tabela, pd.DataFrame([linha_total])], ignore_index=True)
            tabelas_por_regiao[regiao] = df_tabela
    
    return tabelas_por_regiao
