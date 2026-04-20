"""
Gerador de tabela detalhada por produto com métricas e metas.
"""
import pandas as pd
import numpy as np

from src.shared.dias_uteis import calcular_dias_uteis  # noqa: F401


def criar_tabela_produtos_por_loja(df, df_metas, ano, mes, dia_atual=None):
    """
    Cria tabela de vendas de produtos por loja, agrupada por região.
    
    Produtos de EMISSÃO são excluídos do cálculo de valores.
    
    Args:
        df: DataFrame com dados consolidados (deve ter TIPO_PRODUTO, LOJA, REGIAO).
        df_metas: DataFrame com metas por loja.
        ano: Ano do período.
        mes: Mês do período.
        dia_atual: Dia atual para cálculo de dias úteis (opcional).
    
    Returns:
        DataFrame com produtos por loja agrupados por região.
    """
    if 'TIPO_PRODUTO' not in df.columns:
        raise ValueError("Coluna 'TIPO_PRODUTO' não encontrada no DataFrame")
    if 'LOJA' not in df.columns:
        raise ValueError("Coluna 'LOJA' não encontrada no DataFrame")
    if 'REGIAO' not in df.columns:
        raise ValueError("Coluna 'REGIAO' não encontrada no DataFrame")
    
    df_filtrado = df.copy()
    produtos_emissao = ['EMISSAO', 'EMISSAO CC', 'EMISSAO CB']
    mask_emissao = df_filtrado['TIPO_PRODUTO'].isin(produtos_emissao)
    df_filtrado.loc[mask_emissao, 'VALOR'] = 0
    
    tabela = df_filtrado.groupby(['REGIAO', 'LOJA', 'TIPO_PRODUTO']).agg({
        'VALOR': 'sum',
        'pontos': 'sum'
    }).reset_index()
    
    tabela = tabela.sort_values(['REGIAO', 'LOJA', 'pontos'], ascending=[True, True, False])
    
    tabela.columns = ['Região', 'Loja', 'Produto', 'Valor', 'Pontos']
    
    return tabela


def criar_tabela_por_produto(df, df_metas, ano, mes, dia_atual=None):
    """
    Cria tabela detalhada por produto com métricas e metas.
    
    DEPRECATED: Use criar_tabela_produtos_por_loja para análise por loja.
    
    Colunas:
    - Produto
    - Valor
    - Pontos
    - Meta Prata
    - % Meta Prata
    - Meta Ouro
    - % Meta Ouro
    - Média DU (Dia Útil)
    - Meta diária (pontos necessários por dia para atingir Meta Prata)
    
    Args:
        df: DataFrame com dados consolidados.
        df_metas: DataFrame com metas por loja.
        ano: Ano do período.
        mes: Mês do período.
        dia_atual: Dia atual para cálculo de dias úteis (opcional).
    
    Returns:
        DataFrame com tabela por produto.
    """
    total_du, du_decorridos, du_restantes = calcular_dias_uteis(ano, mes, dia_atual)
    
    if 'PRODUTO' not in df.columns:
        raise ValueError("Coluna 'PRODUTO' não encontrada no DataFrame")
    
    tabela = df.groupby('PRODUTO').agg({
        'VALOR': 'sum',
        'pontos': 'sum'
    }).reset_index()
    
    tabela.columns = ['Produto', 'Valor', 'Pontos']
    
    tabela = tabela.sort_values('Pontos', ascending=False)
    
    if df_metas is not None and 'META_PRATA' in df_metas.columns:
        meta_prata_total = df_metas['META_PRATA'].sum()
        meta_ouro_total = df_metas['META_OURO'].sum() if 'META_OURO' in df_metas.columns else meta_prata_total * 1.2
    else:
        pontos_total = tabela['Pontos'].sum()
        meta_prata_total = pontos_total
        meta_ouro_total = pontos_total * 1.2
    
    pontos_total_geral = tabela['Pontos'].sum()
    
    if pontos_total_geral > 0:
        tabela['Meta Prata'] = (tabela['Pontos'] / pontos_total_geral) * meta_prata_total
        tabela['Meta Ouro'] = (tabela['Pontos'] / pontos_total_geral) * meta_ouro_total
    else:
        tabela['Meta Prata'] = 0
        tabela['Meta Ouro'] = 0
    
    tabela['% Meta Prata'] = (tabela['Pontos'] / tabela['Meta Prata'] * 100).fillna(0)
    tabela['% Meta Ouro'] = (tabela['Pontos'] / tabela['Meta Ouro'] * 100).fillna(0)
    
    if du_decorridos > 0:
        tabela['Média DU'] = tabela['Pontos'] / du_decorridos
    else:
        tabela['Média DU'] = 0
    
    if du_restantes > 0:
        pontos_faltantes = tabela['Meta Prata'] - tabela['Pontos']
        pontos_faltantes = pontos_faltantes.clip(lower=0)
        tabela['Meta Diária'] = pontos_faltantes / du_restantes
    else:
        tabela['Meta Diária'] = 0
    
    tabela = tabela[[
        'Produto', 'Valor', 'Pontos',
        'Meta Prata', '% Meta Prata',
        'Meta Ouro', '% Meta Ouro',
        'Média DU', 'Meta Diária'
    ]]
    
    linha_total = pd.DataFrame([{
        'Produto': 'TOTAL',
        'Valor': tabela['Valor'].sum(),
        'Pontos': tabela['Pontos'].sum(),
        'Meta Prata': meta_prata_total,
        '% Meta Prata': (tabela['Pontos'].sum() / meta_prata_total * 100) if meta_prata_total > 0 else 0,
        'Meta Ouro': meta_ouro_total,
        '% Meta Ouro': (tabela['Pontos'].sum() / meta_ouro_total * 100) if meta_ouro_total > 0 else 0,
        'Média DU': tabela['Pontos'].sum() / du_decorridos if du_decorridos > 0 else 0,
        'Meta Diária': ((meta_prata_total - tabela['Pontos'].sum()) / du_restantes) if du_restantes > 0 and meta_prata_total > tabela['Pontos'].sum() else 0
    }])
    
    tabela = pd.concat([tabela, linha_total], ignore_index=True)
    
    return tabela


def criar_tabela_por_consultor(df, df_metas, ano, mes, dia_atual=None, df_supervisores=None):
    """
    Cria tabela detalhada por consultor com métricas e metas.
    
    Supervisores são excluídos desta análise, pois são avaliados
    pela métrica de suas lojas.
    
    Args:
        df: DataFrame com dados consolidados.
        df_metas: DataFrame com metas por loja.
        ano: Ano do período.
        mes: Mês do período.
        dia_atual: Dia atual para cálculo de dias úteis (opcional).
        df_supervisores: DataFrame com supervisores por loja (opcional).
    
    Returns:
        DataFrame com tabela por consultor (sem supervisores).
    """
    total_du, du_decorridos, du_restantes = calcular_dias_uteis(ano, mes, dia_atual)
    
    if 'CONSULTOR' not in df.columns:
        raise ValueError("Coluna 'CONSULTOR' não encontrada no DataFrame")
    
    df_consultores = df.copy()
    
    if df_supervisores is not None and 'SUPERVISOR' in df_supervisores.columns:
        lista_supervisores = df_supervisores['SUPERVISOR'].unique().tolist()
        df_consultores = df_consultores[~df_consultores['CONSULTOR'].isin(lista_supervisores)]
    
    tabela = df_consultores.groupby('CONSULTOR').agg({
        'VALOR': 'sum',
        'pontos': 'sum',
        'LOJA': 'first'
    }).reset_index()
    
    tabela.columns = ['Consultor', 'Valor', 'Pontos', 'Loja']
    
    tabela = tabela.sort_values('Pontos', ascending=False)
    
    if df_metas is not None and 'META_PRATA' in df_metas.columns:
        meta_prata_total = df_metas['META_PRATA'].sum()
        meta_ouro_total = df_metas['META_OURO'].sum() if 'META_OURO' in df_metas.columns else meta_prata_total * 1.2
    else:
        pontos_total = tabela['Pontos'].sum()
        meta_prata_total = pontos_total
        meta_ouro_total = pontos_total * 1.2
    
    num_consultores = len(tabela)
    if num_consultores > 0:
        tabela['Meta Prata'] = meta_prata_total / num_consultores
        tabela['Meta Ouro'] = meta_ouro_total / num_consultores
    else:
        tabela['Meta Prata'] = 0
        tabela['Meta Ouro'] = 0
    
    tabela['% Meta Prata'] = (tabela['Pontos'] / tabela['Meta Prata'] * 100).fillna(0)
    tabela['% Meta Ouro'] = (tabela['Pontos'] / tabela['Meta Ouro'] * 100).fillna(0)
    
    if du_decorridos > 0:
        tabela['Média DU'] = tabela['Pontos'] / du_decorridos
    else:
        tabela['Média DU'] = 0
    
    if du_restantes > 0:
        pontos_faltantes = tabela['Meta Prata'] - tabela['Pontos']
        pontos_faltantes = pontos_faltantes.clip(lower=0)
        tabela['Meta Diária'] = pontos_faltantes / du_restantes
    else:
        tabela['Meta Diária'] = 0
    
    tabela = tabela[[
        'Consultor', 'Loja', 'Valor', 'Pontos',
        'Meta Prata', '% Meta Prata',
        'Meta Ouro', '% Meta Ouro',
        'Média DU', 'Meta Diária'
    ]]
    
    return tabela


def criar_tabela_por_loja(df, df_metas, ano, mes, dia_atual=None):
    """
    Cria tabela detalhada por loja com métricas e metas.
    
    Args:
        df: DataFrame com dados consolidados.
        df_metas: DataFrame com metas por loja.
        ano: Ano do período.
        mes: Mês do período.
        dia_atual: Dia atual para cálculo de dias úteis (opcional).
    
    Returns:
        DataFrame com tabela por loja.
    """
    total_du, du_decorridos, du_restantes = calcular_dias_uteis(ano, mes, dia_atual)
    
    if 'LOJA' not in df.columns:
        raise ValueError("Coluna 'LOJA' não encontrada no DataFrame")
    
    tabela = df.groupby('LOJA').agg({
        'VALOR': 'sum',
        'pontos': 'sum',
        'CONSULTOR': 'nunique'
    }).reset_index()
    
    tabela.columns = ['Loja', 'Valor', 'Pontos', 'Consultores']
    
    if df_metas is not None and 'LOJA' in df_metas.columns:
        metas = df_metas[['LOJA', 'META_PRATA', 'META_OURO']].copy()
        tabela = tabela.merge(metas, left_on='Loja', right_on='LOJA', how='left')
        tabela = tabela.drop('LOJA', axis=1)
        tabela['Meta Prata'] = tabela['META_PRATA'].fillna(0)
        tabela['Meta Ouro'] = tabela['META_OURO'].fillna(0)
        tabela = tabela.drop(['META_PRATA', 'META_OURO'], axis=1)
    else:
        pontos_total = tabela['Pontos'].sum()
        num_lojas = len(tabela)
        if num_lojas > 0:
            tabela['Meta Prata'] = pontos_total / num_lojas
            tabela['Meta Ouro'] = (pontos_total * 1.2) / num_lojas
        else:
            tabela['Meta Prata'] = 0
            tabela['Meta Ouro'] = 0
    
    tabela['% Meta Prata'] = (tabela['Pontos'] / tabela['Meta Prata'] * 100).replace([np.inf, -np.inf], 0).fillna(0)
    tabela['% Meta Ouro'] = (tabela['Pontos'] / tabela['Meta Ouro'] * 100).replace([np.inf, -np.inf], 0).fillna(0)
    
    if du_decorridos > 0:
        tabela['Média DU'] = tabela['Pontos'] / du_decorridos
    else:
        tabela['Média DU'] = 0
    
    if du_restantes > 0:
        pontos_faltantes = tabela['Meta Prata'] - tabela['Pontos']
        pontos_faltantes = pontos_faltantes.clip(lower=0)
        tabela['Meta Diária'] = pontos_faltantes / du_restantes
    else:
        tabela['Meta Diária'] = 0
    
    tabela = tabela.sort_values('Pontos', ascending=False)
    
    tabela = tabela[[
        'Loja', 'Consultores', 'Valor', 'Pontos',
        'Meta Prata', '% Meta Prata',
        'Meta Ouro', '% Meta Ouro',
        'Média DU', 'Meta Diária'
    ]]
    
    return tabela
