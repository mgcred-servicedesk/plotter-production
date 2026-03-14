"""
Módulo para cálculo de pontuação por produto.
"""
import pandas as pd
import numpy as np
from typing import Optional


def calcular_pontos_produto(
    valor: float,
    pts: float
) -> float:
    """
    Calcula pontos de um produto.
    
    Fórmula: Pontos = Valor × PTS
    Exemplo: R$ 500,00 × 5 pts = 2.500 pontos
    
    Args:
        valor: Valor monetário do produto.
        pts: Pontuação por unidade monetária.
    
    Returns:
        Pontuação calculada.
    """
    if pd.isna(valor) or pd.isna(pts):
        return 0.0
    
    return float(valor * pts)


def adicionar_pontuacao(
    df_vendas: pd.DataFrame,
    df_tabelas: pd.DataFrame,
    coluna_valor: str = 'VALOR',
    coluna_produto: str = 'PRODUTO',
    coluna_pts: str = 'PTS'
) -> pd.DataFrame:
    """
    Adiciona coluna de pontuação ao DataFrame de vendas.
    
    Faz merge com tabela de produtos para obter PTS e calcula pontuação.
    
    Args:
        df_vendas: DataFrame com dados de vendas.
        df_tabelas: DataFrame com tabelas de produtos (contém PTS).
        coluna_valor: Nome da coluna de valor no df_vendas.
        coluna_produto: Nome da coluna de produto para fazer o merge.
        coluna_pts: Nome da coluna PTS no df_tabelas.
    
    Returns:
        DataFrame de vendas com coluna 'pontos' adicionada.
    """
    df = df_vendas.copy()
    
    if coluna_produto in df.columns and coluna_produto in df_tabelas.columns:
        df = df.merge(
            df_tabelas[[coluna_produto, coluna_pts]],
            on=coluna_produto,
            how='left'
        )
    else:
        df[coluna_pts] = 0
    
    if coluna_valor in df.columns and coluna_pts in df.columns:
        df['pontos'] = df.apply(
            lambda row: calcular_pontos_produto(
                row.get(coluna_valor, 0),
                row.get(coluna_pts, 0)
            ),
            axis=1
        )
    else:
        df['pontos'] = 0
    
    return df


def agregar_pontos_por_consultor(
    df: pd.DataFrame,
    coluna_consultor: str = 'CONSULTOR'
) -> pd.DataFrame:
    """
    Agrega pontuação por consultor.
    
    Args:
        df: DataFrame com dados de vendas e pontuação.
        coluna_consultor: Nome da coluna de consultor.
    
    Returns:
        DataFrame agregado por consultor com total de pontos.
    """
    if 'pontos' not in df.columns:
        raise ValueError("DataFrame não possui coluna 'pontos'")
    
    if coluna_consultor not in df.columns:
        raise ValueError(f"DataFrame não possui coluna '{coluna_consultor}'")
    
    return df.groupby(coluna_consultor).agg({
        'pontos': 'sum',
        'VALOR': 'sum' if 'VALOR' in df.columns else lambda x: 0
    }).reset_index()


def agregar_pontos_por_loja(
    df: pd.DataFrame,
    coluna_loja: str = 'LOJA'
) -> pd.DataFrame:
    """
    Agrega pontuação por loja.
    
    Args:
        df: DataFrame com dados de vendas e pontuação.
        coluna_loja: Nome da coluna de loja.
    
    Returns:
        DataFrame agregado por loja com total de pontos.
    """
    if 'pontos' not in df.columns:
        raise ValueError("DataFrame não possui coluna 'pontos'")
    
    if coluna_loja not in df.columns:
        raise ValueError(f"DataFrame não possui coluna '{coluna_loja}'")
    
    return df.groupby(coluna_loja).agg({
        'pontos': 'sum',
        'VALOR': 'sum' if 'VALOR' in df.columns else lambda x: 0
    }).reset_index()


def agregar_pontos_por_regiao(
    df: pd.DataFrame,
    df_loja_regiao: pd.DataFrame,
    coluna_loja: str = 'LOJA'
) -> pd.DataFrame:
    """
    Agrega pontuação por região.
    
    Args:
        df: DataFrame com dados de vendas e pontuação.
        df_loja_regiao: DataFrame com mapeamento loja-região.
        coluna_loja: Nome da coluna de loja.
    
    Returns:
        DataFrame agregado por região com total de pontos.
    """
    if 'pontos' not in df.columns:
        raise ValueError("DataFrame não possui coluna 'pontos'")
    
    df_com_regiao = df.merge(
        df_loja_regiao,
        on=coluna_loja,
        how='left'
    )
    
    if 'REGIAO' not in df_com_regiao.columns:
        raise ValueError("Mapeamento loja-região não possui coluna 'REGIAO'")
    
    return df_com_regiao.groupby('REGIAO').agg({
        'pontos': 'sum',
        'VALOR': 'sum' if 'VALOR' in df_com_regiao.columns else lambda x: 0
    }).reset_index()


def calcular_percentual_meta(
    pontos_atual: float,
    meta: float
) -> float:
    """
    Calcula percentual de atingimento de meta.
    
    Args:
        pontos_atual: Pontuação atual.
        meta: Meta em pontos.
    
    Returns:
        Percentual de atingimento (0-100+).
    """
    if pd.isna(meta) or meta == 0:
        return 0.0
    
    return (pontos_atual / meta) * 100


def calcular_meta_diaria(
    pontos_atual: float,
    meta_prata: float,
    dias_uteis_restantes: int
) -> float:
    """
    Calcula meta diária em pontos.
    
    Fórmula: (Meta Prata - Pontos Atuais) / Dias Úteis Restantes
    
    Args:
        pontos_atual: Pontuação atual.
        meta_prata: Meta prata em pontos.
        dias_uteis_restantes: Número de dias úteis restantes no mês.
    
    Returns:
        Meta diária em pontos.
    """
    if dias_uteis_restantes <= 0:
        return 0.0
    
    falta = meta_prata - pontos_atual
    
    if falta <= 0:
        return 0.0
    
    return falta / dias_uteis_restantes


def calcular_media_dia_util(
    pontos_total: float,
    dias_uteis_decorridos: int
) -> float:
    """
    Calcula média de pontos por dia útil.
    
    Args:
        pontos_total: Pontuação total acumulada.
        dias_uteis_decorridos: Número de dias úteis decorridos.
    
    Returns:
        Média de pontos por dia útil.
    """
    if dias_uteis_decorridos <= 0:
        return 0.0
    
    return pontos_total / dias_uteis_decorridos


def adicionar_metricas_metas(
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    dias_uteis_decorridos: int,
    dias_uteis_restantes: int,
    coluna_chave: str = 'CONSULTOR'
) -> pd.DataFrame:
    """
    Adiciona métricas de metas ao DataFrame.
    
    Adiciona colunas:
    - meta_prata
    - meta_ouro
    - perc_meta_prata
    - perc_meta_ouro
    - media_dia_util
    - meta_diaria
    
    Args:
        df: DataFrame com pontuação por consultor/loja.
        df_metas: DataFrame com metas.
        dias_uteis_decorridos: Dias úteis já decorridos no mês.
        dias_uteis_restantes: Dias úteis restantes no mês.
        coluna_chave: Coluna para fazer o merge (CONSULTOR ou LOJA).
    
    Returns:
        DataFrame com métricas de metas adicionadas.
    """
    df = df.copy()
    
    if 'META_PRATA' in df_metas.columns and 'META_OURO' in df_metas.columns:
        df = df.merge(
            df_metas[[coluna_chave, 'META_PRATA', 'META_OURO']],
            on=coluna_chave,
            how='left'
        )
    else:
        df['META_PRATA'] = 0
        df['META_OURO'] = 0
    
    df['meta_prata'] = df['META_PRATA'].fillna(0)
    df['meta_ouro'] = df['META_OURO'].fillna(0)
    
    df['perc_meta_prata'] = df.apply(
        lambda row: calcular_percentual_meta(
            row.get('pontos', 0),
            row.get('meta_prata', 0)
        ),
        axis=1
    )
    
    df['perc_meta_ouro'] = df.apply(
        lambda row: calcular_percentual_meta(
            row.get('pontos', 0),
            row.get('meta_ouro', 0)
        ),
        axis=1
    )
    
    df['media_dia_util'] = df.apply(
        lambda row: calcular_media_dia_util(
            row.get('pontos', 0),
            dias_uteis_decorridos
        ),
        axis=1
    )
    
    df['meta_diaria'] = df.apply(
        lambda row: calcular_meta_diaria(
            row.get('pontos', 0),
            row.get('meta_prata', 0),
            dias_uteis_restantes
        ),
        axis=1
    )
    
    return df


def ranking_por_pontuacao(
    df: pd.DataFrame,
    coluna_nome: str = 'CONSULTOR',
    top_n: Optional[int] = None
) -> pd.DataFrame:
    """
    Cria ranking por pontuação.
    
    Args:
        df: DataFrame com pontuação.
        coluna_nome: Nome da coluna para identificação.
        top_n: Número de registros a retornar. Se None, retorna todos.
    
    Returns:
        DataFrame ordenado por pontuação com ranking.
    """
    if 'pontos' not in df.columns:
        raise ValueError("DataFrame não possui coluna 'pontos'")
    
    df_ranking = df.copy()
    df_ranking = df_ranking.sort_values('pontos', ascending=False)
    df_ranking['ranking'] = range(1, len(df_ranking) + 1)
    
    if top_n:
        df_ranking = df_ranking.head(top_n)
    
    return df_ranking
