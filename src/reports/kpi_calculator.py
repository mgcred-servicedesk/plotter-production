"""
Módulo para cálculo de KPIs e métricas de performance.
"""
import pandas as pd
import numpy as np
from typing import Optional, Dict


def calcular_ticket_medio(
    df: pd.DataFrame,
    coluna_valor: str = 'VALOR'
) -> float:
    """
    Calcula ticket médio (valor total / número de transações).
    
    Args:
        df: DataFrame com dados de vendas.
        coluna_valor: Nome da coluna de valor.
    
    Returns:
        Ticket médio.
    """
    if coluna_valor not in df.columns or len(df) == 0:
        return 0.0
    
    return df[coluna_valor].sum() / len(df)


def calcular_produtividade(
    df: pd.DataFrame,
    coluna_consultor: str = 'CONSULTOR'
) -> float:
    """
    Calcula produtividade (nº consultores × nº vendas).
    
    Args:
        df: DataFrame com dados de vendas.
        coluna_consultor: Nome da coluna de consultor.
    
    Returns:
        Índice de produtividade.
    """
    if coluna_consultor not in df.columns or len(df) == 0:
        return 0.0
    
    num_consultores = df[coluna_consultor].nunique()
    num_vendas = len(df)
    
    if num_consultores == 0:
        return 0.0
    
    return num_vendas / num_consultores


def calcular_kpis_vendas(df: pd.DataFrame) -> Dict[str, float]:
    """
    Calcula KPIs de vendas.
    
    Returns:
        Dicionário com KPIs de vendas.
    """
    kpis = {
        'total_valor': df['VALOR'].sum() if 'VALOR' in df.columns else 0,
        'total_pontos': df['pontos'].sum() if 'pontos' in df.columns else 0,
        'total_transacoes': len(df),
        'ticket_medio': calcular_ticket_medio(df)
    }
    
    if 'PRODUTO' in df.columns:
        kpis['num_produtos_distintos'] = df['PRODUTO'].nunique()
    
    return kpis


def calcular_kpis_metas(
    df: pd.DataFrame,
    meta_prata_total: float,
    meta_ouro_total: float
) -> Dict[str, float]:
    """
    Calcula KPIs de metas.
    
    Args:
        df: DataFrame com dados de vendas.
        meta_prata_total: Meta prata total.
        meta_ouro_total: Meta ouro total.
    
    Returns:
        Dicionário com KPIs de metas.
    """
    pontos_total = df['pontos'].sum() if 'pontos' in df.columns else 0
    
    perc_meta_prata = (pontos_total / meta_prata_total * 100) if meta_prata_total > 0 else 0
    perc_meta_ouro = (pontos_total / meta_ouro_total * 100) if meta_ouro_total > 0 else 0
    
    kpis = {
        'pontos_total': pontos_total,
        'meta_prata': meta_prata_total,
        'meta_ouro': meta_ouro_total,
        'perc_meta_prata': perc_meta_prata,
        'perc_meta_ouro': perc_meta_ouro,
        'atingiu_meta_prata': perc_meta_prata >= 100,
        'atingiu_meta_ouro': perc_meta_ouro >= 100
    }
    
    return kpis


def calcular_kpis_performance(df: pd.DataFrame) -> Dict[str, float]:
    """
    Calcula KPIs de performance.
    
    Returns:
        Dicionário com KPIs de performance.
    """
    kpis = {}
    
    if 'CONSULTOR' in df.columns:
        kpis['num_consultores'] = df['CONSULTOR'].nunique()
        kpis['produtividade'] = calcular_produtividade(df)
        
        if 'pontos' in df.columns:
            pontos_por_consultor = df.groupby('CONSULTOR')['pontos'].sum()
            kpis['media_pontos_consultor'] = pontos_por_consultor.mean()
            kpis['mediana_pontos_consultor'] = pontos_por_consultor.median()
    
    if 'LOJA' in df.columns:
        kpis['num_lojas'] = df['LOJA'].nunique()
    
    if 'REGIAO' in df.columns:
        kpis['num_regioes'] = df['REGIAO'].nunique()
    
    return kpis


def calcular_kpis_produtos_especiais(df: pd.DataFrame) -> Dict[str, int]:
    """
    Calcula KPIs de produtos especiais.
    
    Args:
        df: DataFrame com dados classificados.
    
    Returns:
        Dicionário com contagens de produtos especiais.
    """
    kpis = {}
    
    if 'is_emissao_cartao' in df.columns:
        kpis['emissoes_cartao'] = int(df['is_emissao_cartao'].sum())
    
    if 'is_seguro_med' in df.columns:
        kpis['seguros_med'] = int(df['is_seguro_med'].sum())
    
    if 'is_seguro_vida_familiar' in df.columns:
        kpis['seguros_vida_familiar'] = int(df['is_seguro_vida_familiar'].sum())
    
    if 'is_super_conta' in df.columns:
        kpis['super_contas'] = int(df['is_super_conta'].sum())
    
    return kpis


def calcular_kpis_completos(
    df: pd.DataFrame,
    meta_prata_total: Optional[float] = None,
    meta_ouro_total: Optional[float] = None
) -> Dict[str, any]:
    """
    Calcula todos os KPIs do sistema.
    
    Args:
        df: DataFrame com dados consolidados.
        meta_prata_total: Meta prata total (opcional).
        meta_ouro_total: Meta ouro total (opcional).
    
    Returns:
        Dicionário com todos os KPIs.
    """
    kpis = {}
    
    kpis['vendas'] = calcular_kpis_vendas(df)
    
    if meta_prata_total and meta_ouro_total:
        kpis['metas'] = calcular_kpis_metas(df, meta_prata_total, meta_ouro_total)
    
    kpis['performance'] = calcular_kpis_performance(df)
    kpis['produtos_especiais'] = calcular_kpis_produtos_especiais(df)
    
    return kpis


def comparar_periodos(
    df_atual: pd.DataFrame,
    df_anterior: pd.DataFrame,
    metrica: str = 'pontos'
) -> Dict[str, float]:
    """
    Compara métrica entre dois períodos.
    
    Args:
        df_atual: DataFrame do período atual.
        df_anterior: DataFrame do período anterior.
        metrica: Nome da métrica a comparar.
    
    Returns:
        Dicionário com comparação.
    """
    if metrica not in df_atual.columns or metrica not in df_anterior.columns:
        return {
            'valor_atual': 0,
            'valor_anterior': 0,
            'variacao_absoluta': 0,
            'variacao_percentual': 0
        }
    
    valor_atual = df_atual[metrica].sum()
    valor_anterior = df_anterior[metrica].sum()
    
    variacao_absoluta = valor_atual - valor_anterior
    variacao_percentual = ((valor_atual - valor_anterior) / valor_anterior * 100) if valor_anterior > 0 else 0
    
    return {
        'valor_atual': valor_atual,
        'valor_anterior': valor_anterior,
        'variacao_absoluta': variacao_absoluta,
        'variacao_percentual': variacao_percentual
    }


def criar_ranking_consultores(
    df: pd.DataFrame,
    top_n: Optional[int] = None
) -> pd.DataFrame:
    """
    Cria ranking de consultores por pontuação.
    
    Args:
        df: DataFrame com dados de vendas.
        top_n: Número de consultores a retornar. Se None, retorna todos.
    
    Returns:
        DataFrame com ranking de consultores.
    """
    if 'CONSULTOR' not in df.columns or 'pontos' not in df.columns:
        return pd.DataFrame()
    
    ranking = df.groupby('CONSULTOR').agg({
        'pontos': 'sum',
        'VALOR': 'sum' if 'VALOR' in df.columns else lambda x: 0
    }).reset_index()
    
    ranking = ranking.sort_values('pontos', ascending=False)
    ranking['posicao'] = range(1, len(ranking) + 1)
    
    if top_n:
        ranking = ranking.head(top_n)
    
    return ranking


def criar_ranking_lojas(
    df: pd.DataFrame,
    top_n: Optional[int] = None
) -> pd.DataFrame:
    """
    Cria ranking de lojas por pontuação.
    
    Args:
        df: DataFrame com dados de vendas.
        top_n: Número de lojas a retornar. Se None, retorna todos.
    
    Returns:
        DataFrame com ranking de lojas.
    """
    if 'LOJA' not in df.columns or 'pontos' not in df.columns:
        return pd.DataFrame()
    
    ranking = df.groupby('LOJA').agg({
        'pontos': 'sum',
        'VALOR': 'sum' if 'VALOR' in df.columns else lambda x: 0
    }).reset_index()
    
    ranking = ranking.sort_values('pontos', ascending=False)
    ranking['posicao'] = range(1, len(ranking) + 1)
    
    if 'REGIAO' in df.columns:
        df_regiao = df[['LOJA', 'REGIAO']].drop_duplicates()
        ranking = ranking.merge(df_regiao, on='LOJA', how='left')
    
    if top_n:
        ranking = ranking.head(top_n)
    
    return ranking


def criar_ranking_regioes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cria ranking de regiões por pontuação.
    
    Args:
        df: DataFrame com dados de vendas.
    
    Returns:
        DataFrame com ranking de regiões.
    """
    if 'REGIAO' not in df.columns or 'pontos' not in df.columns:
        return pd.DataFrame()
    
    ranking = df.groupby('REGIAO').agg({
        'pontos': 'sum',
        'VALOR': 'sum' if 'VALOR' in df.columns else lambda x: 0
    }).reset_index()
    
    ranking = ranking.sort_values('pontos', ascending=False)
    ranking['posicao'] = range(1, len(ranking) + 1)
    
    if 'LOJA' in df.columns:
        num_lojas = df.groupby('REGIAO')['LOJA'].nunique().reset_index()
        num_lojas.columns = ['REGIAO', 'num_lojas']
        ranking = ranking.merge(num_lojas, on='REGIAO', how='left')
    
    return ranking


def calcular_evolucao_mensal(
    df: pd.DataFrame,
    metrica: str = 'pontos'
) -> pd.DataFrame:
    """
    Calcula evolução mensal de uma métrica.
    
    Args:
        df: DataFrame com dados de múltiplos meses.
        metrica: Nome da métrica a analisar.
    
    Returns:
        DataFrame com evolução mensal.
    """
    if 'mes' not in df.columns or 'ano' not in df.columns:
        return pd.DataFrame()
    
    if metrica not in df.columns:
        return pd.DataFrame()
    
    evolucao = df.groupby(['ano', 'mes']).agg({
        metrica: 'sum'
    }).reset_index()
    
    evolucao = evolucao.sort_values(['ano', 'mes'])
    
    evolucao['variacao'] = evolucao[metrica].diff()
    evolucao['variacao_perc'] = evolucao[metrica].pct_change() * 100
    
    return evolucao


def identificar_outliers(
    df: pd.DataFrame,
    coluna: str = 'pontos',
    metodo: str = 'iqr'
) -> pd.DataFrame:
    """
    Identifica outliers em uma métrica.
    
    Args:
        df: DataFrame com dados.
        coluna: Nome da coluna a analisar.
        metodo: Método de detecção ('iqr' ou 'zscore').
    
    Returns:
        DataFrame com outliers identificados.
    """
    if coluna not in df.columns:
        return pd.DataFrame()
    
    df_result = df.copy()
    
    if metodo == 'iqr':
        Q1 = df[coluna].quantile(0.25)
        Q3 = df[coluna].quantile(0.75)
        IQR = Q3 - Q1
        
        limite_inferior = Q1 - 1.5 * IQR
        limite_superior = Q3 + 1.5 * IQR
        
        df_result['is_outlier'] = (df[coluna] < limite_inferior) | (df[coluna] > limite_superior)
    
    elif metodo == 'zscore':
        media = df[coluna].mean()
        desvio = df[coluna].std()
        
        df_result['zscore'] = (df[coluna] - media) / desvio
        df_result['is_outlier'] = abs(df_result['zscore']) > 3
    
    return df_result[df_result['is_outlier']]


def calcular_concentracao_vendas(
    df: pd.DataFrame,
    nivel: str = 'consultor'
) -> Dict[str, float]:
    """
    Calcula concentração de vendas (Curva ABC).
    
    Args:
        df: DataFrame com dados de vendas.
        nivel: Nível de análise ('consultor', 'loja', 'produto').
    
    Returns:
        Dicionário com métricas de concentração.
    """
    if nivel == 'consultor':
        coluna = 'CONSULTOR'
    elif nivel == 'loja':
        coluna = 'LOJA'
    elif nivel == 'produto':
        coluna = 'PRODUTO'
    else:
        return {}
    
    if coluna not in df.columns or 'pontos' not in df.columns:
        return {}
    
    vendas_por_nivel = df.groupby(coluna)['pontos'].sum().sort_values(ascending=False)
    total_vendas = vendas_por_nivel.sum()
    
    vendas_acumuladas = vendas_por_nivel.cumsum()
    percentual_acumulado = (vendas_acumuladas / total_vendas * 100)
    
    top_20_perc = (percentual_acumulado <= 80).sum() / len(vendas_por_nivel) * 100
    
    return {
        'total_itens': len(vendas_por_nivel),
        'top_20_perc_itens': top_20_perc,
        'concentracao_top_20': percentual_acumulado[percentual_acumulado.index[int(len(vendas_por_nivel) * 0.2)]] if len(vendas_por_nivel) > 0 else 0
    }
