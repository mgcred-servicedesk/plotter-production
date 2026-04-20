"""
Módulo para criação de tabelas por produto.
"""
import pandas as pd
from typing import Optional
from src.data_processing.points_calculator import (
    calcular_percentual_meta,
    calcular_meta_diaria,
    calcular_media_dia_util
)


def criar_tabela_produto(
    df: pd.DataFrame,
    produto: str,
    meta_prata: float,
    meta_ouro: float,
    dias_uteis_decorridos: int,
    dias_uteis_restantes: int
) -> dict:
    """
    Cria tabela de um produto específico com todas as métricas.
    
    Colunas da tabela:
    - Valor: Valor monetário total do produto
    - Pontos: Pontuação calculada
    - Meta Prata: Meta prata em pontos
    - % Meta Prata: Percentual de atingimento da meta prata
    - Meta Ouro: Meta ouro em pontos
    - % Meta Ouro: Percentual de atingimento da meta ouro
    - Média DU: Média de pontos por dia útil
    - Meta diária: Pontos necessários por dia para atingir meta prata
    
    Args:
        df: DataFrame filtrado para o produto específico.
        produto: Nome do produto.
        meta_prata: Meta prata em pontos.
        meta_ouro: Meta ouro em pontos.
        dias_uteis_decorridos: Dias úteis já decorridos.
        dias_uteis_restantes: Dias úteis restantes.
    
    Returns:
        Dicionário com métricas do produto.
    """
    valor_total = df['VALOR'].sum() if 'VALOR' in df.columns else 0
    pontos_total = df['pontos'].sum() if 'pontos' in df.columns else 0
    
    perc_meta_prata = calcular_percentual_meta(pontos_total, meta_prata)
    perc_meta_ouro = calcular_percentual_meta(pontos_total, meta_ouro)
    
    media_du = calcular_media_dia_util(pontos_total, dias_uteis_decorridos)
    
    meta_diaria = calcular_meta_diaria(
        pontos_total,
        meta_prata,
        dias_uteis_restantes
    )
    
    return {
        'Produto': produto,
        'Valor': valor_total,
        'Pontos': pontos_total,
        'Meta Prata': meta_prata,
        '% Meta Prata': perc_meta_prata,
        'Meta Ouro': meta_ouro,
        '% Meta Ouro': perc_meta_ouro,
        'Média DU': media_du,
        'Meta Diária': meta_diaria
    }


def criar_tabelas_todos_produtos(
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    dias_uteis_decorridos: int,
    dias_uteis_restantes: int,
    coluna_produto: str = 'PRODUTO'
) -> pd.DataFrame:
    """
    Cria tabelas para todos os produtos.
    
    Args:
        df: DataFrame com dados de vendas e pontuação.
        df_metas: DataFrame com metas por produto.
        dias_uteis_decorridos: Dias úteis já decorridos.
        dias_uteis_restantes: Dias úteis restantes.
        coluna_produto: Nome da coluna de produto.
    
    Returns:
        DataFrame com tabelas de todos os produtos.
    """
    if coluna_produto not in df.columns:
        raise ValueError(f"Coluna '{coluna_produto}' não encontrada")
    
    produtos = df[coluna_produto].unique()
    
    tabelas = []
    for produto in produtos:
        df_produto = df[df[coluna_produto] == produto]
        
        meta_prata = 0
        meta_ouro = 0
        if coluna_produto in df_metas.columns:
            meta_produto = df_metas[df_metas[coluna_produto] == produto]
            if not meta_produto.empty:
                meta_prata = meta_produto['META_PRATA'].iloc[0] if 'META_PRATA' in meta_produto.columns else 0
                meta_ouro = meta_produto['META_OURO'].iloc[0] if 'META_OURO' in meta_produto.columns else 0
        
        tabela = criar_tabela_produto(
            df_produto,
            produto,
            meta_prata,
            meta_ouro,
            dias_uteis_decorridos,
            dias_uteis_restantes
        )
        
        tabelas.append(tabela)
    
    return pd.DataFrame(tabelas)


def criar_tabelas_por_regiao(
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    dias_uteis_decorridos: int,
    dias_uteis_restantes: int
) -> dict:
    """
    Cria tabelas de produtos agrupadas por região.
    
    Args:
        df: DataFrame com dados de vendas.
        df_metas: DataFrame com metas.
        dias_uteis_decorridos: Dias úteis já decorridos.
        dias_uteis_restantes: Dias úteis restantes.
    
    Returns:
        Dicionário com DataFrames de tabelas por região.
    """
    if 'REGIAO' not in df.columns:
        raise ValueError("DataFrame não possui coluna 'REGIAO'")
    
    regioes = df['REGIAO'].unique()
    
    tabelas_por_regiao = {}
    for regiao in regioes:
        df_regiao = df[df['REGIAO'] == regiao]
        
        tabelas = criar_tabelas_todos_produtos(
            df_regiao,
            df_metas,
            dias_uteis_decorridos,
            dias_uteis_restantes
        )
        
        tabelas_por_regiao[regiao] = tabelas
    
    return tabelas_por_regiao


def criar_tabelas_por_loja(
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    dias_uteis_decorridos: int,
    dias_uteis_restantes: int
) -> dict:
    """
    Cria tabelas de produtos agrupadas por loja.
    
    Args:
        df: DataFrame com dados de vendas.
        df_metas: DataFrame com metas.
        dias_uteis_decorridos: Dias úteis já decorridos.
        dias_uteis_restantes: Dias úteis restantes.
    
    Returns:
        Dicionário com DataFrames de tabelas por loja.
    """
    if 'LOJA' not in df.columns:
        raise ValueError("DataFrame não possui coluna 'LOJA'")
    
    lojas = df['LOJA'].unique()
    
    tabelas_por_loja = {}
    for loja in lojas:
        df_loja = df[df['LOJA'] == loja]
        
        tabelas = criar_tabelas_todos_produtos(
            df_loja,
            df_metas,
            dias_uteis_decorridos,
            dias_uteis_restantes
        )
        
        tabelas_por_loja[loja] = tabelas
    
    return tabelas_por_loja


def criar_tabela_hierarquica(
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    dias_uteis_decorridos: int,
    dias_uteis_restantes: int
) -> dict:
    """
    Cria estrutura hierárquica de tabelas: Região → Loja → Produtos.
    
    Args:
        df: DataFrame com dados de vendas.
        df_metas: DataFrame com metas.
        dias_uteis_decorridos: Dias úteis já decorridos.
        dias_uteis_restantes: Dias úteis restantes.
    
    Returns:
        Dicionário hierárquico com tabelas.
    """
    if 'REGIAO' not in df.columns or 'LOJA' not in df.columns:
        raise ValueError("DataFrame deve ter colunas 'REGIAO' e 'LOJA'")
    
    estrutura = {}
    
    regioes = df['REGIAO'].unique()
    for regiao in regioes:
        df_regiao = df[df['REGIAO'] == regiao]
        estrutura[regiao] = {}
        
        lojas = df_regiao['LOJA'].unique()
        for loja in lojas:
            df_loja = df_regiao[df_regiao['LOJA'] == loja]
            
            tabelas = criar_tabelas_todos_produtos(
                df_loja,
                df_metas,
                dias_uteis_decorridos,
                dias_uteis_restantes
            )
            
            estrutura[regiao][loja] = tabelas
    
    return estrutura


def formatar_tabela_produto_excel(df_tabela: pd.DataFrame) -> pd.DataFrame:
    """
    Formata tabela de produto para exportação Excel.
    
    Args:
        df_tabela: DataFrame com tabela de produto.
    
    Returns:
        DataFrame formatado.
    """
    df = df_tabela.copy()
    
    colunas_moeda = ['Valor', 'Meta Prata', 'Meta Ouro', 'Média DU', 'Meta Diária']
    for col in colunas_moeda:
        if col in df.columns:
            df[col] = df[col].round(2)
    
    colunas_percentual = ['% Meta Prata', '% Meta Ouro']
    for col in colunas_percentual:
        if col in df.columns:
            df[col] = df[col].round(1)
    
    if 'Pontos' in df.columns:
        df['Pontos'] = df['Pontos'].round(0)
    
    return df


def adicionar_totalizadores(df_tabela: pd.DataFrame) -> pd.DataFrame:
    """
    Adiciona linha de totalizadores à tabela.
    
    Args:
        df_tabela: DataFrame com tabela de produtos.
    
    Returns:
        DataFrame com linha de total adicionada.
    """
    df = df_tabela.copy()
    
    total = {
        'Produto': 'TOTAL',
        'Valor': df['Valor'].sum() if 'Valor' in df.columns else 0,
        'Pontos': df['Pontos'].sum() if 'Pontos' in df.columns else 0,
        'Meta Prata': df['Meta Prata'].sum() if 'Meta Prata' in df.columns else 0,
        'Meta Ouro': df['Meta Ouro'].sum() if 'Meta Ouro' in df.columns else 0,
        'Média DU': df['Média DU'].mean() if 'Média DU' in df.columns else 0,
        'Meta Diária': df['Meta Diária'].sum() if 'Meta Diária' in df.columns else 0
    }
    
    if 'Pontos' in df.columns and 'Meta Prata' in df.columns:
        total['% Meta Prata'] = calcular_percentual_meta(
            total['Pontos'],
            total['Meta Prata']
        )
    
    if 'Pontos' in df.columns and 'Meta Ouro' in df.columns:
        total['% Meta Ouro'] = calcular_percentual_meta(
            total['Pontos'],
            total['Meta Ouro']
        )
    
    df_total = pd.DataFrame([total])
    df = pd.concat([df, df_total], ignore_index=True)
    
    return df


def filtrar_produtos_top(
    df_tabela: pd.DataFrame,
    top_n: int = 10,
    criterio: str = 'Pontos'
) -> pd.DataFrame:
    """
    Filtra top N produtos por critério.
    
    Args:
        df_tabela: DataFrame com tabela de produtos.
        top_n: Número de produtos a retornar.
        criterio: Coluna para ordenação ('Pontos', 'Valor', etc.).
    
    Returns:
        DataFrame com top N produtos.
    """
    if criterio not in df_tabela.columns:
        raise ValueError(f"Critério '{criterio}' não encontrado")
    
    df = df_tabela.copy()
    df = df[df['Produto'] != 'TOTAL']
    df = df.sort_values(criterio, ascending=False)
    
    return df.head(top_n)
