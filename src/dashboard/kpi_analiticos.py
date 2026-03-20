"""
Módulo de analíticos avançados para o dashboard.
Contém funções para análises detalhadas de consultores, produtos e regiões.
"""
from typing import Dict, Optional

import pandas as pd

from src.config.settings import LISTA_PRODUTOS, MAPEAMENTO_PRODUTOS


def calcular_analitico_consultores_produtos_loja(
    df: pd.DataFrame,
    df_supervisores: Optional[pd.DataFrame] = None
) -> pd.DataFrame:
    """
    Cria analítico geral de consultores com produtos por loja.
    
    Args:
        df: DataFrame consolidado
        df_supervisores: DataFrame de supervisores para exclusão
    
    Returns:
        DataFrame com análise de consultores por produto e loja
    """
    if 'CONSULTOR' not in df.columns:
        return pd.DataFrame()
    
    df_valido = df[df['VALOR'] > 0].copy()
    
    # Excluir supervisores se fornecido
    if df_supervisores is not None and 'SUPERVISOR' in df_supervisores.columns:
        supervisores = df_supervisores['SUPERVISOR'].unique()
        df_valido = df_valido[
            ~df_valido['CONSULTOR'].isin(supervisores)
        ]
    
    # Criar mapeamento de produtos
    df_valido['PRODUTO_MIX'] = df_valido['TIPO_PRODUTO'].map(
        lambda x: next(
            (k for k, v in MAPEAMENTO_PRODUTOS.items() if x in v),
            'OUTROS'
        )
    )
    
    # Agregar por consultor, loja e produto
    analitico = df_valido.groupby(
        ['CONSULTOR', 'LOJA', 'REGIAO', 'PRODUTO_MIX']
    ).agg({
        'VALOR': ['count', 'sum'],
        'pontos': 'sum'
    }).reset_index()
    
    analitico.columns = [
        'Consultor', 'Loja', 'Região', 'Produto',
        'Qtd', 'Valor', 'Pontos'
    ]
    
    # Calcular ticket médio
    analitico['Ticket Médio'] = (
        analitico['Valor'] / analitico['Qtd']
    ).where(analitico['Qtd'] > 0, 0)
    
    # Ordenar por consultor e pontos
    analitico = analitico.sort_values(
        ['Consultor', 'Pontos'],
        ascending=[True, False]
    )
    
    return analitico


def calcular_media_producao_consultor_regiao(
    df: pd.DataFrame,
    df_supervisores: Optional[pd.DataFrame] = None
) -> pd.DataFrame:
    """
    Calcula média de produção por consultor em cada região.
    Permite comparativo entre regiões.
    
    Args:
        df: DataFrame consolidado
        df_supervisores: DataFrame de supervisores para exclusão
    
    Returns:
        DataFrame com média de produção por consultor por região
    """
    if 'CONSULTOR' not in df.columns or 'REGIAO' not in df.columns:
        return pd.DataFrame()
    
    df_valido = df[df['VALOR'] > 0].copy()
    
    # Excluir supervisores se fornecido
    if df_supervisores is not None and 'SUPERVISOR' in df_supervisores.columns:
        supervisores = df_supervisores['SUPERVISOR'].unique()
        df_valido = df_valido[
            ~df_valido['CONSULTOR'].isin(supervisores)
        ]
    
    # Agregar por região e consultor
    por_consultor = df_valido.groupby(['REGIAO', 'CONSULTOR']).agg({
        'VALOR': 'sum',
        'pontos': 'sum'
    }).reset_index()
    
    # Calcular estatísticas por região
    estatisticas = por_consultor.groupby('REGIAO').agg({
        'VALOR': ['mean', 'median', 'std', 'min', 'max'],
        'pontos': ['mean', 'median', 'std', 'min', 'max'],
        'CONSULTOR': 'count'
    }).reset_index()
    
    estatisticas.columns = [
        'Região',
        'Valor Médio', 'Valor Mediano', 'Valor Desvio',
        'Valor Mínimo', 'Valor Máximo',
        'Pontos Médio', 'Pontos Mediano', 'Pontos Desvio',
        'Pontos Mínimo', 'Pontos Máximo',
        'Num Consultores'
    ]
    
    # Ordenar por pontos médio
    estatisticas = estatisticas.sort_values(
        'Pontos Médio',
        ascending=False
    )
    
    return estatisticas


def calcular_ranking_ticket_medio(
    df: pd.DataFrame,
    tipo: str = 'loja',
    top_n: int = 10,
    df_supervisores: Optional[pd.DataFrame] = None
) -> pd.DataFrame:
    """
    Cria ranking por ticket médio (lojas ou consultores).
    Exclui supervisores quando tipo='consultor'.
    
    Args:
        df: DataFrame consolidado
        tipo: 'loja' ou 'consultor'
        top_n: Número de itens no ranking
        df_supervisores: DataFrame de supervisores para exclusão
    
    Returns:
        DataFrame com ranking por ticket médio
    """
    df_valido = df[df['VALOR'] > 0].copy()
    
    if tipo == 'loja':
        if 'LOJA' not in df.columns:
            return pd.DataFrame()
        
        ranking = df_valido.groupby('LOJA').agg({
            'VALOR': ['count', 'sum'],
            'pontos': 'sum'
        }).reset_index()
        
        ranking.columns = ['Loja', 'Qtd', 'Valor', 'Pontos']
        
        if 'REGIAO' in df.columns:
            df_regiao = df[['LOJA', 'REGIAO']].drop_duplicates()
            ranking = ranking.merge(
                df_regiao,
                left_on='Loja',
                right_on='LOJA'
            )
            ranking = ranking.drop('LOJA', axis=1)
    
    else:  # consultor
        if 'CONSULTOR' not in df.columns:
            return pd.DataFrame()
        
        # Excluir supervisores
        if df_supervisores is not None and 'SUPERVISOR' in df_supervisores.columns:
            supervisores = df_supervisores['SUPERVISOR'].unique()
            df_valido = df_valido[~df_valido['CONSULTOR'].isin(supervisores)]
        
        ranking = df_valido.groupby('CONSULTOR').agg({
            'VALOR': ['count', 'sum'],
            'pontos': 'sum',
            'LOJA': 'first'
        }).reset_index()
        
        ranking.columns = ['Consultor', 'Qtd', 'Valor', 'Pontos', 'Loja']
        
        if 'REGIAO' in df.columns:
            df_regiao = df[['LOJA', 'REGIAO']].drop_duplicates()
            ranking = ranking.merge(
                df_regiao,
                left_on='Loja',
                right_on='LOJA',
                how='left'
            )
            ranking = ranking.drop('LOJA', axis=1)
    
    # Calcular ticket médio
    ranking['Ticket Médio'] = (
        ranking['Valor'] / ranking['Qtd']
    ).where(ranking['Qtd'] > 0, 0)
    
    # Ordenar e pegar top N
    ranking = ranking.sort_values('Ticket Médio', ascending=False).head(top_n)
    ranking.insert(0, 'Posição', range(1, len(ranking) + 1))
    
    return ranking


def calcular_ranking_por_produto(
    df: pd.DataFrame,
    tipo: str = 'loja',
    top_n: int = 10,
    df_supervisores: Optional[pd.DataFrame] = None
) -> Dict[str, pd.DataFrame]:
    """
    Cria rankings por produto (lojas ou consultores).
    Exclui supervisores quando tipo='consultor'.
    
    Args:
        df: DataFrame consolidado
        tipo: 'loja' ou 'consultor'
        top_n: Número de itens no ranking
        df_supervisores: DataFrame de supervisores para exclusão
    
    Returns:
        Dicionário com DataFrames de ranking por produto
    """
    df_valido = df[df['VALOR'] > 0].copy()
    
    # Excluir supervisores se for ranking de consultores
    if tipo == 'consultor' and df_supervisores is not None and 'SUPERVISOR' in df_supervisores.columns:
        supervisores = df_supervisores['SUPERVISOR'].unique()
        df_valido = df_valido[~df_valido['CONSULTOR'].isin(supervisores)]
    
    # Criar mapeamento de produtos
    df_valido['PRODUTO_MIX'] = df_valido['TIPO_PRODUTO'].map(
        lambda x: next(
            (k for k, v in MAPEAMENTO_PRODUTOS.items() if x in v),
            'OUTROS'
        )
    )
    
    rankings = {}
    
    for produto in LISTA_PRODUTOS:
        df_produto = df_valido[df_valido['PRODUTO_MIX'] == produto]
        
        if len(df_produto) == 0:
            rankings[produto] = pd.DataFrame()
            continue
        
        if tipo == 'loja':
            if 'LOJA' not in df.columns:
                continue
            
            ranking = df_produto.groupby('LOJA').agg({
                'VALOR': ['count', 'sum'],
                'pontos': 'sum'
            }).reset_index()
            
            ranking.columns = ['Loja', 'Qtd', 'Valor', 'Pontos']
        
        else:  # consultor
            if 'CONSULTOR' not in df.columns:
                continue
            
            ranking = df_produto.groupby('CONSULTOR').agg({
                'VALOR': ['count', 'sum'],
                'pontos': 'sum',
                'LOJA': 'first'
            }).reset_index()
            
            ranking.columns = ['Consultor', 'Qtd', 'Valor', 'Pontos', 'Loja']
        
        # Calcular ticket médio
        ranking['Ticket Médio'] = (
            ranking['Valor'] / ranking['Qtd']
        ).where(ranking['Qtd'] > 0, 0)
        
        # Ordenar e pegar top N
        ranking = ranking.sort_values('Pontos', ascending=False).head(top_n)
        ranking.insert(0, 'Posição', range(1, len(ranking) + 1))
        
        rankings[produto] = ranking
    
    return rankings


def calcular_distribuicao_produtos_consultor(
    df: pd.DataFrame,
    df_supervisores: Optional[pd.DataFrame] = None
) -> pd.DataFrame:
    """
    Calcula distribuição de produtos por consultor.
    
    Args:
        df: DataFrame consolidado
        df_supervisores: DataFrame de supervisores para exclusão
    
    Returns:
        DataFrame com distribuição de produtos por consultor
    """
    if 'CONSULTOR' not in df.columns:
        return pd.DataFrame()
    
    df_valido = df[df['VALOR'] > 0].copy()
    
    # Excluir supervisores se fornecido
    if df_supervisores is not None and 'SUPERVISOR' in df_supervisores.columns:
        supervisores = df_supervisores['SUPERVISOR'].unique()
        df_valido = df_valido[
            ~df_valido['CONSULTOR'].isin(supervisores)
        ]
    
    # Criar mapeamento de produtos
    df_valido['PRODUTO_MIX'] = df_valido['TIPO_PRODUTO'].map(
        lambda x: next(
            (k for k, v in MAPEAMENTO_PRODUTOS.items() if x in v),
            'OUTROS'
        )
    )
    
    # Criar pivot table
    distribuicao = df_valido.pivot_table(
        index='CONSULTOR',
        columns='PRODUTO_MIX',
        values='pontos',
        aggfunc='sum',
        fill_value=0
    ).reset_index()
    
    # Adicionar total
    distribuicao['TOTAL'] = distribuicao[LISTA_PRODUTOS].sum(axis=1)
    
    # Adicionar loja e região
    if 'LOJA' in df.columns:
        df_info = df[['CONSULTOR', 'LOJA']].drop_duplicates()
        distribuicao = distribuicao.merge(df_info, on='CONSULTOR', how='left')
    
    if 'REGIAO' in df.columns:
        df_regiao = df[['LOJA', 'REGIAO']].drop_duplicates()
        distribuicao = distribuicao.merge(
            df_regiao,
            on='LOJA',
            how='left'
        )
    
    # Ordenar por total
    distribuicao = distribuicao.sort_values('TOTAL', ascending=False)
    
    return distribuicao
