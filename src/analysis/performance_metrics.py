"""
Módulo para métricas de performance individual e análises aprofundadas.
"""
import pandas as pd
from typing import Dict, Optional
import numpy as np


def analisar_consultor(
    df: pd.DataFrame,
    consultor: str
) -> Dict[str, any]:
    """
    Analisa performance de um consultor específico.
    
    Args:
        df: DataFrame com dados consolidados.
        consultor: Nome do consultor a analisar.
    
    Returns:
        Dicionário com análise do consultor.
    """
    if 'CONSULTOR' not in df.columns:
        raise ValueError("DataFrame não possui coluna 'CONSULTOR'")
    
    df_consultor = df[df['CONSULTOR'] == consultor]
    
    if len(df_consultor) == 0:
        return {'erro': f'Consultor {consultor} não encontrado'}
    
    analise = {
        'consultor': consultor,
        'total_valor': df_consultor['VALOR'].sum() if 'VALOR' in df_consultor.columns else 0,
        'total_pontos': df_consultor['pontos'].sum() if 'pontos' in df_consultor.columns else 0,
        'total_transacoes': len(df_consultor),
        'ticket_medio': df_consultor['VALOR'].mean() if 'VALOR' in df_consultor.columns else 0
    }
    
    if 'LOJA' in df_consultor.columns:
        analise['loja'] = df_consultor['LOJA'].iloc[0]
    
    if 'REGIAO' in df_consultor.columns:
        analise['regiao'] = df_consultor['REGIAO'].iloc[0]
    
    if 'META_PRATA' in df_consultor.columns:
        meta_prata = df_consultor['META_PRATA'].iloc[0]
        analise['meta_prata'] = meta_prata
        analise['perc_meta_prata'] = (analise['total_pontos'] / meta_prata * 100) if meta_prata > 0 else 0
    
    if 'META_OURO' in df_consultor.columns:
        meta_ouro = df_consultor['META_OURO'].iloc[0]
        analise['meta_ouro'] = meta_ouro
        analise['perc_meta_ouro'] = (analise['total_pontos'] / meta_ouro * 100) if meta_ouro > 0 else 0
    
    if 'PRODUTO' in df_consultor.columns:
        analise['num_produtos_distintos'] = df_consultor['PRODUTO'].nunique()
        analise['produto_mais_vendido'] = df_consultor['PRODUTO'].mode()[0] if len(df_consultor['PRODUTO'].mode()) > 0 else ''
    
    return analise


def comparar_consultor_com_media(
    df: pd.DataFrame,
    consultor: str,
    nivel_comparacao: str = 'loja'
) -> Dict[str, any]:
    """
    Compara performance do consultor com média do nível especificado.
    
    Args:
        df: DataFrame com dados consolidados.
        consultor: Nome do consultor.
        nivel_comparacao: Nível de comparação ('loja', 'regiao', 'geral').
    
    Returns:
        Dicionário com comparação.
    """
    analise_consultor = analisar_consultor(df, consultor)
    
    if 'erro' in analise_consultor:
        return analise_consultor
    
    if nivel_comparacao == 'loja' and 'loja' in analise_consultor:
        df_comparacao = df[df['LOJA'] == analise_consultor['loja']]
    elif nivel_comparacao == 'regiao' and 'regiao' in analise_consultor:
        df_comparacao = df[df['REGIAO'] == analise_consultor['regiao']]
    else:
        df_comparacao = df
    
    if 'CONSULTOR' in df_comparacao.columns and 'pontos' in df_comparacao.columns:
        pontos_por_consultor = df_comparacao.groupby('CONSULTOR')['pontos'].sum()
        media_pontos = pontos_por_consultor.mean()
        mediana_pontos = pontos_por_consultor.median()
    else:
        media_pontos = 0
        mediana_pontos = 0
    
    comparacao = {
        'consultor': consultor,
        'pontos_consultor': analise_consultor['total_pontos'],
        'media_pontos': media_pontos,
        'mediana_pontos': mediana_pontos,
        'diferenca_vs_media': analise_consultor['total_pontos'] - media_pontos,
        'percentual_vs_media': ((analise_consultor['total_pontos'] - media_pontos) / media_pontos * 100) if media_pontos > 0 else 0,
        'acima_da_media': analise_consultor['total_pontos'] > media_pontos
    }
    
    return comparacao


def analisar_produtos_vendidos_consultor(
    df: pd.DataFrame,
    consultor: str
) -> pd.DataFrame:
    """
    Analisa produtos vendidos por um consultor.
    
    Args:
        df: DataFrame com dados consolidados.
        consultor: Nome do consultor.
    
    Returns:
        DataFrame com análise de produtos do consultor.
    """
    if 'CONSULTOR' not in df.columns or 'PRODUTO' not in df.columns:
        raise ValueError("DataFrame deve ter colunas 'CONSULTOR' e 'PRODUTO'")
    
    df_consultor = df[df['CONSULTOR'] == consultor]
    
    produtos = df_consultor.groupby('PRODUTO').agg({
        'pontos': 'sum',
        'VALOR': 'sum' if 'VALOR' in df_consultor.columns else lambda x: 0,
        'PRODUTO': 'count'
    }).reset_index()
    
    produtos.columns = ['PRODUTO', 'total_pontos', 'total_valor', 'quantidade']
    
    produtos = produtos.sort_values('total_pontos', ascending=False)
    produtos['percentual_pontos'] = (produtos['total_pontos'] / produtos['total_pontos'].sum() * 100)
    
    return produtos


def analisar_evolucao_consultor(
    df: pd.DataFrame,
    consultor: str
) -> pd.DataFrame:
    """
    Analisa evolução temporal de um consultor.
    
    Args:
        df: DataFrame com dados de múltiplos períodos.
        consultor: Nome do consultor.
    
    Returns:
        DataFrame com evolução do consultor.
    """
    if 'CONSULTOR' not in df.columns:
        raise ValueError("DataFrame não possui coluna 'CONSULTOR'")
    
    if 'mes' not in df.columns or 'ano' not in df.columns:
        return pd.DataFrame()
    
    df_consultor = df[df['CONSULTOR'] == consultor]
    
    evolucao = df_consultor.groupby(['ano', 'mes']).agg({
        'pontos': 'sum',
        'VALOR': 'sum' if 'VALOR' in df_consultor.columns else lambda x: 0
    }).reset_index()
    
    evolucao = evolucao.sort_values(['ano', 'mes'])
    
    evolucao['variacao_pontos'] = evolucao['pontos'].diff()
    evolucao['variacao_pontos_perc'] = evolucao['pontos'].pct_change() * 100
    
    return evolucao


def identificar_consultores_outliers(
    df: pd.DataFrame,
    metodo: str = 'iqr'
) -> pd.DataFrame:
    """
    Identifica consultores com performance outlier.
    
    Args:
        df: DataFrame com dados consolidados.
        metodo: Método de detecção ('iqr' ou 'zscore').
    
    Returns:
        DataFrame com consultores outliers.
    """
    if 'CONSULTOR' not in df.columns or 'pontos' not in df.columns:
        return pd.DataFrame()
    
    pontos_por_consultor = df.groupby('CONSULTOR')['pontos'].sum().reset_index()
    
    if metodo == 'iqr':
        Q1 = pontos_por_consultor['pontos'].quantile(0.25)
        Q3 = pontos_por_consultor['pontos'].quantile(0.75)
        IQR = Q3 - Q1
        
        limite_inferior = Q1 - 1.5 * IQR
        limite_superior = Q3 + 1.5 * IQR
        
        outliers = pontos_por_consultor[
            (pontos_por_consultor['pontos'] < limite_inferior) |
            (pontos_por_consultor['pontos'] > limite_superior)
        ]
        
        outliers['tipo'] = outliers['pontos'].apply(
            lambda x: 'Alto' if x > limite_superior else 'Baixo'
        )
    
    elif metodo == 'zscore':
        media = pontos_por_consultor['pontos'].mean()
        desvio = pontos_por_consultor['pontos'].std()
        
        pontos_por_consultor['zscore'] = (pontos_por_consultor['pontos'] - media) / desvio
        outliers = pontos_por_consultor[abs(pontos_por_consultor['zscore']) > 2]
        
        outliers['tipo'] = outliers['zscore'].apply(
            lambda x: 'Alto' if x > 0 else 'Baixo'
        )
    
    else:
        return pd.DataFrame()
    
    return outliers


def calcular_consistencia_consultor(
    df: pd.DataFrame,
    consultor: str
) -> Dict[str, float]:
    """
    Calcula métricas de consistência de performance do consultor.
    
    Args:
        df: DataFrame com dados de múltiplos períodos.
        consultor: Nome do consultor.
    
    Returns:
        Dicionário com métricas de consistência.
    """
    evolucao = analisar_evolucao_consultor(df, consultor)
    
    if evolucao.empty or 'pontos' not in evolucao.columns:
        return {}
    
    consistencia = {
        'media_pontos': evolucao['pontos'].mean(),
        'desvio_padrao': evolucao['pontos'].std(),
        'coeficiente_variacao': (evolucao['pontos'].std() / evolucao['pontos'].mean() * 100) if evolucao['pontos'].mean() > 0 else 0,
        'minimo': evolucao['pontos'].min(),
        'maximo': evolucao['pontos'].max(),
        'amplitude': evolucao['pontos'].max() - evolucao['pontos'].min()
    }
    
    return consistencia


def gerar_relatorio_performance_consultor(
    df: pd.DataFrame,
    consultor: str
) -> Dict[str, any]:
    """
    Gera relatório completo de performance do consultor.
    
    Args:
        df: DataFrame com dados consolidados.
        consultor: Nome do consultor.
    
    Returns:
        Dicionário com relatório completo.
    """
    relatorio = {}
    
    relatorio['dados_basicos'] = analisar_consultor(df, consultor)
    
    if 'erro' not in relatorio['dados_basicos']:
        relatorio['comparacao_loja'] = comparar_consultor_com_media(df, consultor, 'loja')
        relatorio['comparacao_regiao'] = comparar_consultor_com_media(df, consultor, 'regiao')
        relatorio['produtos'] = analisar_produtos_vendidos_consultor(df, consultor)
        
        if 'mes' in df.columns and 'ano' in df.columns:
            relatorio['evolucao'] = analisar_evolucao_consultor(df, consultor)
            relatorio['consistencia'] = calcular_consistencia_consultor(df, consultor)
    
    return relatorio


def identificar_top_performers(
    df: pd.DataFrame,
    top_n: int = 10,
    criterio: str = 'pontos'
) -> pd.DataFrame:
    """
    Identifica top performers.
    
    Args:
        df: DataFrame com dados consolidados.
        top_n: Número de consultores a retornar.
        criterio: Critério para ranking ('pontos', 'valor', 'transacoes').
    
    Returns:
        DataFrame com top performers.
    """
    if 'CONSULTOR' not in df.columns:
        return pd.DataFrame()
    
    if criterio == 'pontos':
        coluna = 'pontos'
    elif criterio == 'valor':
        coluna = 'VALOR'
    else:
        coluna = 'pontos'
    
    if coluna not in df.columns:
        return pd.DataFrame()
    
    ranking = df.groupby('CONSULTOR').agg({
        coluna: 'sum'
    }).reset_index()
    
    ranking = ranking.sort_values(coluna, ascending=False)
    ranking['posicao'] = range(1, len(ranking) + 1)
    
    return ranking.head(top_n)
