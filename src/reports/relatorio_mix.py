"""
Gerador de relatório MIX de produtos com métricas detalhadas.
"""
import pandas as pd
import numpy as np
from src.reports.tabela_produtos import calcular_dias_uteis


def criar_relatorio_mix(df, df_metas, ano, mes, dia_atual=None):
    """
    Cria relatório detalhado do MIX de produtos com métricas individuais.
    
    Produtos do MIX:
    - CNC
    - SAQUE
    - CLT (CONSIG PRIV)
    - CONSIGNADO (inclui portabilidade)
    - PACK (FGTS + CNC 13 + ANTECIP)
    
    Métricas:
    - Realizado (quantidade e valor)
    - Meta
    - Atingimento (%)
    - Média DU (Dia Útil)
    - Ticket Médio
    - Meta Diária
    
    Args:
        df: DataFrame com dados consolidados.
        df_metas: DataFrame com metas por loja.
        ano: Ano do período.
        mes: Mês do período.
        dia_atual: Dia atual para cálculo de dias úteis (opcional).
    
    Returns:
        DataFrame com relatório MIX.
    """
    total_du, du_decorridos, du_restantes = calcular_dias_uteis(ano, mes, dia_atual)
    
    mapeamento_produtos = {
        'CNC': ['CNC'],
        'SAQUE': ['SAQUE', 'SAQUE BENEFICIO'],
        'CLT': ['CONSIG PRIV'],
        'CONSIGNADO': ['CONSIG', 'Portabilidade'],
        'PACK': ['FGTS', 'CNC 13º']
    }
    
    mapeamento_metas = {
        'CNC': 'CNC LOJA',
        'SAQUE': 'SAQUE LOJA',
        'CLT': 'CLT',
        'CONSIGNADO': 'CONSIGNADO',
        'PACK': 'META  LOJA FGTS & ANT. BEN.13º'
    }
    
    resultados = []
    
    for produto_mix, tipos_produto in mapeamento_produtos.items():
        df_produto = df[df_filtrar_por_tipos(df, tipos_produto)]
        
        qtd_realizada = len(df_produto)
        valor_realizado = df_produto['VALOR'].sum()
        pontos_realizados = df_produto['pontos'].sum()
        
        ticket_medio = valor_realizado / qtd_realizada if qtd_realizada > 0 else 0
        media_du = qtd_realizada / du_decorridos if du_decorridos > 0 else 0
        
        coluna_meta = mapeamento_metas.get(produto_mix)
        meta_total = 0
        if coluna_meta and coluna_meta in df_metas.columns:
            meta_total = df_metas[coluna_meta].sum()
        
        atingimento = (qtd_realizada / meta_total * 100) if meta_total > 0 else 0
        meta_diaria = meta_total / total_du if total_du > 0 else 0
        
        resultados.append({
            'Produto': produto_mix,
            'Qtd Realizada': qtd_realizada,
            'Valor Realizado': valor_realizado,
            'Pontos': pontos_realizados,
            'Meta': meta_total,
            'Atingimento (%)': atingimento,
            'Ticket Médio': ticket_medio,
            'Média DU': media_du,
            'Meta Diária': meta_diaria,
            'DU Decorridos': du_decorridos,
            'DU Restantes': du_restantes
        })
    
    df_mix = pd.DataFrame(resultados)
    
    totais = {
        'Produto': 'TOTAL MIX',
        'Qtd Realizada': df_mix['Qtd Realizada'].sum(),
        'Valor Realizado': df_mix['Valor Realizado'].sum(),
        'Pontos': df_mix['Pontos'].sum(),
        'Meta': df_mix['Meta'].sum(),
        'Atingimento (%)': (df_mix['Qtd Realizada'].sum() / df_mix['Meta'].sum() * 100) if df_mix['Meta'].sum() > 0 else 0,
        'Ticket Médio': df_mix['Valor Realizado'].sum() / df_mix['Qtd Realizada'].sum() if df_mix['Qtd Realizada'].sum() > 0 else 0,
        'Média DU': df_mix['Qtd Realizada'].sum() / du_decorridos if du_decorridos > 0 else 0,
        'Meta Diária': df_mix['Meta'].sum() / total_du if total_du > 0 else 0,
        'DU Decorridos': du_decorridos,
        'DU Restantes': du_restantes
    }
    
    df_mix = pd.concat([df_mix, pd.DataFrame([totais])], ignore_index=True)
    
    return df_mix


def df_filtrar_por_tipos(df, tipos_produto):
    """
    Filtra DataFrame por tipos de produto.
    
    Args:
        df: DataFrame com dados.
        tipos_produto: Lista de tipos de produto.
    
    Returns:
        Máscara booleana para filtro.
    """
    if 'TIPO_PRODUTO' not in df.columns:
        return pd.Series([False] * len(df))
    
    return df['TIPO_PRODUTO'].isin(tipos_produto)


def criar_relatorio_mix_por_loja(df, df_metas, ano, mes, dia_atual=None):
    """
    Cria relatório MIX detalhado por loja.
    
    Args:
        df: DataFrame com dados consolidados.
        df_metas: DataFrame com metas por loja.
        ano: Ano do período.
        mes: Mês do período.
        dia_atual: Dia atual para cálculo de dias úteis (opcional).
    
    Returns:
        DataFrame com relatório MIX por loja.
    """
    total_du, du_decorridos, du_restantes = calcular_dias_uteis(ano, mes, dia_atual)
    
    mapeamento_produtos = {
        'CNC': ['CNC'],
        'SAQUE': ['SAQUE', 'SAQUE BENEFICIO'],
        'CLT': ['CONSIG PRIV'],
        'CONSIGNADO': ['CONSIG', 'Portabilidade'],
        'PACK': ['FGTS', 'CNC 13º']
    }
    
    mapeamento_metas = {
        'CNC': 'CNC LOJA',
        'SAQUE': 'SAQUE LOJA',
        'CLT': 'CLT',
        'CONSIGNADO': 'CONSIGNADO',
        'PACK': 'META  LOJA FGTS & ANT. BEN.13º'
    }
    
    resultados = []
    
    lojas = df['LOJA'].unique()
    
    for loja in lojas:
        df_loja = df[df['LOJA'] == loja]
        regiao = df_loja['REGIAO'].iloc[0] if 'REGIAO' in df_loja.columns and len(df_loja) > 0 else ''
        
        for produto_mix, tipos_produto in mapeamento_produtos.items():
            df_produto = df_loja[df_filtrar_por_tipos(df_loja, tipos_produto)]
            
            qtd_realizada = len(df_produto)
            valor_realizado = df_produto['VALOR'].sum()
            pontos_realizados = df_produto['pontos'].sum()
            
            ticket_medio = valor_realizado / qtd_realizada if qtd_realizada > 0 else 0
            media_du = qtd_realizada / du_decorridos if du_decorridos > 0 else 0
            
            coluna_meta = mapeamento_metas.get(produto_mix)
            meta_loja = 0
            if coluna_meta and coluna_meta in df_metas.columns:
                meta_loja_df = df_metas[df_metas['LOJA'] == loja]
                if len(meta_loja_df) > 0:
                    meta_loja = meta_loja_df[coluna_meta].iloc[0]
            
            atingimento = (qtd_realizada / meta_loja * 100) if meta_loja > 0 else 0
            meta_diaria = meta_loja / total_du if total_du > 0 else 0
            
            resultados.append({
                'Região': regiao,
                'Loja': loja,
                'Produto': produto_mix,
                'Qtd Realizada': qtd_realizada,
                'Valor Realizado': valor_realizado,
                'Pontos': pontos_realizados,
                'Meta': meta_loja,
                'Atingimento (%)': atingimento,
                'Ticket Médio': ticket_medio,
                'Média DU': media_du,
                'Meta Diária': meta_diaria
            })
    
    df_mix_loja = pd.DataFrame(resultados)
    df_mix_loja = df_mix_loja.sort_values(['Região', 'Loja', 'Produto'])
    
    return df_mix_loja
