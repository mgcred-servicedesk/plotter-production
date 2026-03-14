"""
Módulo para comparação entre lojas.
"""
import pandas as pd
from typing import Dict, List, Optional
from src.reports.kpi_calculator import calcular_ticket_medio, calcular_produtividade


def analisar_loja(
    df: pd.DataFrame,
    loja: str
) -> Dict[str, any]:
    """
    Analisa performance de uma loja específica.
    
    Args:
        df: DataFrame com dados consolidados.
        loja: Nome da loja a analisar.
    
    Returns:
        Dicionário com análise da loja.
    """
    if 'LOJA' not in df.columns:
        raise ValueError("DataFrame não possui coluna 'LOJA'")
    
    df_loja = df[df['LOJA'] == loja]
    
    if len(df_loja) == 0:
        return {'erro': f'Loja {loja} não encontrada'}
    
    analise = {
        'loja': loja,
        'total_valor': df_loja['VALOR'].sum() if 'VALOR' in df_loja.columns else 0,
        'total_pontos': df_loja['pontos'].sum() if 'pontos' in df_loja.columns else 0,
        'total_transacoes': len(df_loja),
        'ticket_medio': calcular_ticket_medio(df_loja),
        'num_consultores': df_loja['CONSULTOR'].nunique() if 'CONSULTOR' in df_loja.columns else 0,
        'produtividade': calcular_produtividade(df_loja)
    }
    
    if 'REGIAO' in df_loja.columns:
        analise['regiao'] = df_loja['REGIAO'].iloc[0]
    
    if 'META_PRATA' in df_loja.columns:
        meta_prata_total = df_loja['META_PRATA'].sum()
        analise['meta_prata'] = meta_prata_total
        analise['perc_meta_prata'] = (analise['total_pontos'] / meta_prata_total * 100) if meta_prata_total > 0 else 0
    
    if 'META_OURO' in df_loja.columns:
        meta_ouro_total = df_loja['META_OURO'].sum()
        analise['meta_ouro'] = meta_ouro_total
        analise['perc_meta_ouro'] = (analise['total_pontos'] / meta_ouro_total * 100) if meta_ouro_total > 0 else 0
    
    return analise


def comparar_lojas(
    df: pd.DataFrame,
    lojas: Optional[List[str]] = None
) -> pd.DataFrame:
    """
    Compara performance entre lojas.
    
    Args:
        df: DataFrame com dados consolidados.
        lojas: Lista de lojas a comparar. Se None, compara todas.
    
    Returns:
        DataFrame com comparação entre lojas.
    """
    if 'LOJA' not in df.columns:
        raise ValueError("DataFrame não possui coluna 'LOJA'")
    
    if lojas is None:
        lojas = df['LOJA'].unique()
    
    comparacoes = []
    for loja in lojas:
        analise = analisar_loja(df, loja)
        if 'erro' not in analise:
            comparacoes.append(analise)
    
    return pd.DataFrame(comparacoes)


def comparar_lojas_por_perfil(
    df: pd.DataFrame,
    df_metas: pd.DataFrame
) -> pd.DataFrame:
    """
    Compara lojas pelo perfil conforme tabela de metas.
    
    Args:
        df: DataFrame com dados consolidados.
        df_metas: DataFrame com metas e perfis de lojas.
    
    Returns:
        DataFrame com comparação por perfil.
    """
    df_comparacao = comparar_lojas(df)
    
    if 'LOJA' in df_metas.columns and 'PERFIL' in df_metas.columns:
        df_perfil = df_metas[['LOJA', 'PERFIL']].drop_duplicates()
        df_comparacao = df_comparacao.merge(df_perfil, on='LOJA', how='left')
    
    return df_comparacao


def ranking_lojas_por_metrica(
    df: pd.DataFrame,
    metrica: str = 'total_pontos',
    top_n: Optional[int] = None
) -> pd.DataFrame:
    """
    Cria ranking de lojas por métrica específica.
    
    Args:
        df: DataFrame com dados consolidados.
        metrica: Métrica para ranking.
        top_n: Número de lojas a retornar. Se None, retorna todas.
    
    Returns:
        DataFrame com ranking de lojas.
    """
    df_comparacao = comparar_lojas(df)
    
    if metrica not in df_comparacao.columns:
        raise ValueError(f"Métrica '{metrica}' não encontrada")
    
    df_ranking = df_comparacao.sort_values(metrica, ascending=False)
    df_ranking['posicao'] = range(1, len(df_ranking) + 1)
    
    if top_n:
        df_ranking = df_ranking.head(top_n)
    
    return df_ranking


def analisar_consultores_por_loja(
    df: pd.DataFrame,
    loja: str
) -> pd.DataFrame:
    """
    Analisa todos os consultores de uma loja.
    
    Args:
        df: DataFrame com dados consolidados.
        loja: Nome da loja.
    
    Returns:
        DataFrame com análise de consultores da loja.
    """
    if 'LOJA' not in df.columns or 'CONSULTOR' not in df.columns:
        raise ValueError("DataFrame deve ter colunas 'LOJA' e 'CONSULTOR'")
    
    df_loja = df[df['LOJA'] == loja]
    
    consultores = df_loja.groupby('CONSULTOR').agg({
        'pontos': 'sum',
        'VALOR': 'sum' if 'VALOR' in df_loja.columns else lambda x: 0
    }).reset_index()
    
    consultores.columns = ['CONSULTOR', 'total_pontos', 'total_valor']
    
    if 'META_PRATA' in df_loja.columns:
        metas = df_loja.groupby('CONSULTOR')['META_PRATA'].first().reset_index()
        consultores = consultores.merge(metas, on='CONSULTOR', how='left')
        consultores['perc_meta_prata'] = (consultores['total_pontos'] / consultores['META_PRATA'] * 100).fillna(0)
    
    consultores = consultores.sort_values('total_pontos', ascending=False)
    consultores['posicao'] = range(1, len(consultores) + 1)
    
    return consultores


def benchmarking_lojas_similares(
    df: pd.DataFrame,
    loja_referencia: str,
    criterio_similaridade: str = 'num_consultores',
    num_lojas: int = 5
) -> pd.DataFrame:
    """
    Faz benchmarking com lojas similares.
    
    Args:
        df: DataFrame com dados consolidados.
        loja_referencia: Loja de referência para comparação.
        criterio_similaridade: Critério para definir similaridade.
        num_lojas: Número de lojas similares a retornar.
    
    Returns:
        DataFrame com lojas similares e comparação.
    """
    df_comparacao = comparar_lojas(df)
    
    if loja_referencia not in df_comparacao['loja'].values:
        return pd.DataFrame()
    
    loja_ref = df_comparacao[df_comparacao['loja'] == loja_referencia].iloc[0]
    
    if criterio_similaridade not in df_comparacao.columns:
        criterio_similaridade = 'num_consultores'
    
    valor_ref = loja_ref[criterio_similaridade]
    
    df_comparacao['diferenca'] = abs(df_comparacao[criterio_similaridade] - valor_ref)
    df_comparacao = df_comparacao[df_comparacao['loja'] != loja_referencia]
    df_comparacao = df_comparacao.sort_values('diferenca')
    
    return df_comparacao.head(num_lojas)


def calcular_metricas_agregadas_loja(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula métricas agregadas por loja.
    
    Args:
        df: DataFrame com dados consolidados.
    
    Returns:
        DataFrame com métricas agregadas.
    """
    if 'LOJA' not in df.columns:
        raise ValueError("DataFrame não possui coluna 'LOJA'")
    
    metricas = df.groupby('LOJA').agg({
        'pontos': ['sum', 'mean', 'median'],
        'VALOR': ['sum', 'mean'] if 'VALOR' in df.columns else lambda x: 0,
        'CONSULTOR': 'nunique' if 'CONSULTOR' in df.columns else lambda x: 0
    }).reset_index()
    
    metricas.columns = [
        'LOJA',
        'pontos_total', 'pontos_media', 'pontos_mediana',
        'valor_total', 'valor_medio',
        'num_consultores'
    ]
    
    if 'REGIAO' in df.columns:
        df_regiao = df[['LOJA', 'REGIAO']].drop_duplicates()
        metricas = metricas.merge(df_regiao, on='LOJA', how='left')
    
    return metricas


def identificar_lojas_destaque(
    df: pd.DataFrame,
    criterio: str = 'pontos'
) -> Dict[str, str]:
    """
    Identifica lojas de destaque (melhor e pior performance).
    
    Args:
        df: DataFrame com dados consolidados.
        criterio: Critério para avaliação.
    
    Returns:
        Dicionário com lojas de destaque.
    """
    df_comparacao = comparar_lojas(df)
    
    if criterio == 'pontos':
        coluna = 'total_pontos'
    elif criterio == 'valor':
        coluna = 'total_valor'
    elif criterio == 'produtividade':
        coluna = 'produtividade'
    elif criterio == 'ticket_medio':
        coluna = 'ticket_medio'
    else:
        coluna = 'total_pontos'
    
    if coluna not in df_comparacao.columns:
        return {}
    
    melhor = df_comparacao.loc[df_comparacao[coluna].idxmax()]
    pior = df_comparacao.loc[df_comparacao[coluna].idxmin()]
    
    return {
        'melhor_loja': melhor['loja'],
        'melhor_valor': melhor[coluna],
        'pior_loja': pior['loja'],
        'pior_valor': pior[coluna]
    }


def analisar_evolucao_loja(
    df: pd.DataFrame,
    loja: str
) -> pd.DataFrame:
    """
    Analisa evolução temporal de uma loja.
    
    Args:
        df: DataFrame com dados de múltiplos períodos.
        loja: Nome da loja.
    
    Returns:
        DataFrame com evolução da loja.
    """
    if 'LOJA' not in df.columns:
        raise ValueError("DataFrame não possui coluna 'LOJA'")
    
    if 'mes' not in df.columns or 'ano' not in df.columns:
        return pd.DataFrame()
    
    df_loja = df[df['LOJA'] == loja]
    
    evolucao = df_loja.groupby(['ano', 'mes']).agg({
        'pontos': 'sum',
        'VALOR': 'sum' if 'VALOR' in df_loja.columns else lambda x: 0
    }).reset_index()
    
    evolucao = evolucao.sort_values(['ano', 'mes'])
    
    evolucao['variacao_pontos'] = evolucao['pontos'].diff()
    evolucao['variacao_pontos_perc'] = evolucao['pontos'].pct_change() * 100
    
    return evolucao
