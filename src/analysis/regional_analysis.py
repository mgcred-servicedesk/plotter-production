"""
Módulo para análise por região.
"""
import pandas as pd
from typing import Dict, Optional
from src.reports.kpi_calculator import calcular_ticket_medio, calcular_produtividade


def analisar_regiao(
    df: pd.DataFrame,
    regiao: str
) -> Dict[str, any]:
    """
    Analisa performance de uma região específica.
    
    Args:
        df: DataFrame com dados consolidados.
        regiao: Nome da região a analisar.
    
    Returns:
        Dicionário com análise da região.
    """
    if 'REGIAO' not in df.columns:
        raise ValueError("DataFrame não possui coluna 'REGIAO'")
    
    df_regiao = df[df['REGIAO'] == regiao]
    
    if len(df_regiao) == 0:
        return {'erro': f'Região {regiao} não encontrada'}
    
    analise = {
        'regiao': regiao,
        'total_valor': df_regiao['VALOR'].sum() if 'VALOR' in df_regiao.columns else 0,
        'total_pontos': df_regiao['pontos'].sum() if 'pontos' in df_regiao.columns else 0,
        'total_transacoes': len(df_regiao),
        'ticket_medio': calcular_ticket_medio(df_regiao),
        'num_lojas': df_regiao['LOJA'].nunique() if 'LOJA' in df_regiao.columns else 0,
        'num_consultores': df_regiao['CONSULTOR'].nunique() if 'CONSULTOR' in df_regiao.columns else 0,
        'produtividade': calcular_produtividade(df_regiao)
    }
    
    if 'META_PRATA' in df_regiao.columns:
        meta_prata_total = df_regiao['META_PRATA'].sum()
        analise['meta_prata'] = meta_prata_total
        analise['perc_meta_prata'] = (analise['total_pontos'] / meta_prata_total * 100) if meta_prata_total > 0 else 0
    
    if 'META_OURO' in df_regiao.columns:
        meta_ouro_total = df_regiao['META_OURO'].sum()
        analise['meta_ouro'] = meta_ouro_total
        analise['perc_meta_ouro'] = (analise['total_pontos'] / meta_ouro_total * 100) if meta_ouro_total > 0 else 0
    
    return analise


def comparar_regioes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compara performance entre todas as regiões.
    
    Args:
        df: DataFrame com dados consolidados.
    
    Returns:
        DataFrame com comparação entre regiões.
    """
    if 'REGIAO' not in df.columns:
        raise ValueError("DataFrame não possui coluna 'REGIAO'")
    
    regioes = df['REGIAO'].unique()
    
    comparacoes = []
    for regiao in regioes:
        analise = analisar_regiao(df, regiao)
        if 'erro' not in analise:
            comparacoes.append(analise)
    
    return pd.DataFrame(comparacoes)


def ranking_regioes_por_metrica(
    df: pd.DataFrame,
    metrica: str = 'total_pontos'
) -> pd.DataFrame:
    """
    Cria ranking de regiões por métrica específica.
    
    Args:
        df: DataFrame com dados consolidados.
        metrica: Métrica para ranking.
    
    Returns:
        DataFrame com ranking de regiões.
    """
    df_comparacao = comparar_regioes(df)
    
    if metrica not in df_comparacao.columns:
        raise ValueError(f"Métrica '{metrica}' não encontrada")
    
    df_ranking = df_comparacao.sort_values(metrica, ascending=False)
    df_ranking['posicao'] = range(1, len(df_ranking) + 1)
    
    return df_ranking


def analisar_lojas_por_regiao(
    df: pd.DataFrame,
    regiao: str
) -> pd.DataFrame:
    """
    Analisa todas as lojas de uma região.
    
    Args:
        df: DataFrame com dados consolidados.
        regiao: Nome da região.
    
    Returns:
        DataFrame com análise de lojas da região.
    """
    if 'REGIAO' not in df.columns or 'LOJA' not in df.columns:
        raise ValueError("DataFrame deve ter colunas 'REGIAO' e 'LOJA'")
    
    df_regiao = df[df['REGIAO'] == regiao]
    
    lojas = df_regiao.groupby('LOJA').agg({
        'pontos': 'sum',
        'VALOR': 'sum' if 'VALOR' in df_regiao.columns else lambda x: 0,
        'CONSULTOR': 'nunique' if 'CONSULTOR' in df_regiao.columns else lambda x: 0
    }).reset_index()
    
    lojas.columns = ['LOJA', 'total_pontos', 'total_valor', 'num_consultores']
    
    lojas['ticket_medio'] = lojas.apply(
        lambda row: calcular_ticket_medio(
            df_regiao[df_regiao['LOJA'] == row['LOJA']]
        ),
        axis=1
    )
    
    lojas = lojas.sort_values('total_pontos', ascending=False)
    lojas['posicao'] = range(1, len(lojas) + 1)
    
    return lojas


def analisar_consultores_por_regiao(
    df: pd.DataFrame,
    regiao: str
) -> pd.DataFrame:
    """
    Analisa todos os consultores de uma região.
    
    Args:
        df: DataFrame com dados consolidados.
        regiao: Nome da região.
    
    Returns:
        DataFrame com análise de consultores da região.
    """
    if 'REGIAO' not in df.columns or 'CONSULTOR' not in df.columns:
        raise ValueError("DataFrame deve ter colunas 'REGIAO' e 'CONSULTOR'")
    
    df_regiao = df[df['REGIAO'] == regiao]
    
    consultores = df_regiao.groupby('CONSULTOR').agg({
        'pontos': 'sum',
        'VALOR': 'sum' if 'VALOR' in df_regiao.columns else lambda x: 0,
        'LOJA': 'first' if 'LOJA' in df_regiao.columns else lambda x: ''
    }).reset_index()
    
    consultores.columns = ['CONSULTOR', 'total_pontos', 'total_valor', 'LOJA']
    
    consultores = consultores.sort_values('total_pontos', ascending=False)
    consultores['posicao'] = range(1, len(consultores) + 1)
    
    return consultores


def calcular_metricas_agregadas_regiao(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula métricas agregadas por região.
    
    Args:
        df: DataFrame com dados consolidados.
    
    Returns:
        DataFrame com métricas agregadas.
    """
    if 'REGIAO' not in df.columns:
        raise ValueError("DataFrame não possui coluna 'REGIAO'")
    
    metricas = df.groupby('REGIAO').agg({
        'pontos': ['sum', 'mean', 'median'],
        'VALOR': ['sum', 'mean'] if 'VALOR' in df.columns else lambda x: 0,
        'CONSULTOR': 'nunique' if 'CONSULTOR' in df.columns else lambda x: 0,
        'LOJA': 'nunique' if 'LOJA' in df.columns else lambda x: 0
    }).reset_index()
    
    metricas.columns = [
        'REGIAO',
        'pontos_total', 'pontos_media', 'pontos_mediana',
        'valor_total', 'valor_medio',
        'num_consultores', 'num_lojas'
    ]
    
    return metricas


def identificar_regioes_destaque(
    df: pd.DataFrame,
    criterio: str = 'pontos'
) -> Dict[str, str]:
    """
    Identifica regiões de destaque (melhor e pior performance).
    
    Args:
        df: DataFrame com dados consolidados.
        criterio: Critério para avaliação ('pontos', 'valor', 'produtividade').
    
    Returns:
        Dicionário com regiões de destaque.
    """
    df_comparacao = comparar_regioes(df)
    
    if criterio == 'pontos':
        coluna = 'total_pontos'
    elif criterio == 'valor':
        coluna = 'total_valor'
    elif criterio == 'produtividade':
        coluna = 'produtividade'
    else:
        coluna = 'total_pontos'
    
    if coluna not in df_comparacao.columns:
        return {}
    
    melhor = df_comparacao.loc[df_comparacao[coluna].idxmax()]
    pior = df_comparacao.loc[df_comparacao[coluna].idxmin()]
    
    return {
        'melhor_regiao': melhor['regiao'],
        'melhor_valor': melhor[coluna],
        'pior_regiao': pior['regiao'],
        'pior_valor': pior[coluna]
    }
