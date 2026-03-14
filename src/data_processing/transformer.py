"""
Módulo para transformação e limpeza de dados.
"""
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional, List
import re


def padronizar_nomes_colunas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Padroniza nomes de colunas removendo espaços extras e caracteres especiais.
    
    Args:
        df: DataFrame a ser padronizado.
    
    Returns:
        DataFrame com colunas padronizadas.
    """
    df = df.copy()
    df.columns = df.columns.str.strip()
    return df


def converter_moeda_brasileira(valor: str) -> float:
    """
    Converte string de moeda brasileira para float.
    
    Exemplos:
    - 'R$ 1.500,00' -> 1500.00
    - '1.500,50' -> 1500.50
    - '500' -> 500.00
    
    Args:
        valor: String com valor em formato brasileiro.
    
    Returns:
        Valor convertido para float.
    """
    if pd.isna(valor):
        return 0.0
    
    if isinstance(valor, (int, float)):
        return float(valor)
    
    valor_str = str(valor)
    valor_str = valor_str.replace('R$', '').strip()
    valor_str = valor_str.replace('.', '')
    valor_str = valor_str.replace(',', '.')
    
    try:
        return float(valor_str)
    except ValueError:
        return 0.0


def converter_percentual_brasileiro(valor: str) -> float:
    """
    Converte string de percentual brasileiro para float.
    
    Exemplos:
    - '85,5%' -> 85.5
    - '100%' -> 100.0
    
    Args:
        valor: String com percentual em formato brasileiro.
    
    Returns:
        Valor convertido para float.
    """
    if pd.isna(valor):
        return 0.0
    
    if isinstance(valor, (int, float)):
        return float(valor)
    
    valor_str = str(valor)
    valor_str = valor_str.replace('%', '').strip()
    valor_str = valor_str.replace(',', '.')
    
    try:
        return float(valor_str)
    except ValueError:
        return 0.0


def converter_data_brasileira(data: str, formato: str = '%d/%m/%Y') -> Optional[datetime]:
    """
    Converte string de data brasileira para datetime.
    
    Args:
        data: String com data em formato brasileiro.
        formato: Formato da data (padrão: DD/MM/YYYY).
    
    Returns:
        Objeto datetime ou None se conversão falhar.
    """
    if pd.isna(data):
        return None
    
    if isinstance(data, datetime):
        return data
    
    try:
        return pd.to_datetime(data, format=formato)
    except:
        try:
            return pd.to_datetime(data)
        except:
            return None


def normalizar_nome_pessoa(nome: str) -> str:
    """
    Normaliza nome de pessoa (consultor, vendedor).
    
    - Remove espaços extras
    - Converte para título (primeira letra maiúscula)
    
    Args:
        nome: Nome a ser normalizado.
    
    Returns:
        Nome normalizado.
    """
    if pd.isna(nome):
        return ''
    
    nome_str = str(nome).strip()
    nome_str = ' '.join(nome_str.split())
    nome_str = nome_str.title()
    
    return nome_str


def normalizar_nome_loja(nome: str) -> str:
    """
    Normaliza nome de loja.
    
    - Remove espaços extras
    - Converte para maiúsculas
    
    Args:
        nome: Nome da loja a ser normalizado.
    
    Returns:
        Nome normalizado.
    """
    if pd.isna(nome):
        return ''
    
    nome_str = str(nome).strip()
    nome_str = ' '.join(nome_str.split())
    nome_str = nome_str.upper()
    
    return nome_str


def tratar_valores_nulos(
    df: pd.DataFrame,
    colunas_numericas: Optional[List[str]] = None,
    colunas_texto: Optional[List[str]] = None
) -> pd.DataFrame:
    """
    Trata valores nulos no DataFrame.
    
    Args:
        df: DataFrame a ser tratado.
        colunas_numericas: Lista de colunas numéricas (preenche com 0).
        colunas_texto: Lista de colunas de texto (preenche com '').
    
    Returns:
        DataFrame com valores nulos tratados.
    """
    df = df.copy()
    
    if colunas_numericas:
        for col in colunas_numericas:
            if col in df.columns:
                df[col] = df[col].fillna(0)
    
    if colunas_texto:
        for col in colunas_texto:
            if col in df.columns:
                df[col] = df[col].fillna('')
    
    return df


def aplicar_transformacoes_digitacao(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica todas as transformações necessárias aos dados de digitação.
    
    Args:
        df: DataFrame de digitação bruto.
    
    Returns:
        DataFrame transformado.
    """
    df = df.copy()
    
    df = padronizar_nomes_colunas(df)
    
    if 'VALOR' in df.columns:
        df['VALOR'] = df['VALOR'].apply(
            lambda x: converter_moeda_brasileira(x) if isinstance(x, str) else x
        )
    
    if 'CONSULTOR' in df.columns:
        df['CONSULTOR'] = df['CONSULTOR'].apply(normalizar_nome_pessoa)
    
    if 'LOJA' in df.columns:
        df['LOJA'] = df['LOJA'].apply(normalizar_nome_loja)
    
    if 'DATA' in df.columns:
        df['DATA'] = df['DATA'].apply(converter_data_brasileira)
    
    colunas_numericas = ['VALOR', 'QUANTIDADE', 'QTD']
    colunas_texto = ['CONSULTOR', 'LOJA', 'PRODUTO', 'TIPO OPER.', 'SUBTIPO']
    
    df = tratar_valores_nulos(df, colunas_numericas, colunas_texto)
    
    return df


def aplicar_transformacoes_metas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica todas as transformações necessárias aos dados de metas.
    
    Args:
        df: DataFrame de metas bruto.
    
    Returns:
        DataFrame transformado.
    """
    df = df.copy()
    
    df = padronizar_nomes_colunas(df)
    
    if 'CONSULTOR' in df.columns:
        df['CONSULTOR'] = df['CONSULTOR'].apply(normalizar_nome_pessoa)
    
    if 'LOJA' in df.columns:
        df['LOJA'] = df['LOJA'].apply(normalizar_nome_loja)
    
    colunas_metas = ['META_PRATA', 'META_OURO', 'META PRATA', 'META OURO']
    for col in colunas_metas:
        if col in df.columns:
            df[col] = df[col].apply(
                lambda x: converter_moeda_brasileira(x) if isinstance(x, str) else x
            )
    
    if 'META PRATA' in df.columns and 'META_PRATA' not in df.columns:
        df['META_PRATA'] = df['META PRATA']
    
    if 'META OURO' in df.columns and 'META_OURO' not in df.columns:
        df['META_OURO'] = df['META OURO']
    
    colunas_numericas = ['META_PRATA', 'META_OURO']
    colunas_texto = ['CONSULTOR', 'LOJA']
    
    df = tratar_valores_nulos(df, colunas_numericas, colunas_texto)
    
    return df


def aplicar_transformacoes_tabelas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica todas as transformações necessárias às tabelas de produtos.
    
    Args:
        df: DataFrame de tabelas bruto.
    
    Returns:
        DataFrame transformado.
    """
    df = df.copy()
    
    df = padronizar_nomes_colunas(df)
    
    if 'PTS' in df.columns:
        df['PTS'] = pd.to_numeric(df['PTS'], errors='coerce').fillna(0)
    
    if 'PRODUTO' in df.columns:
        df['PRODUTO'] = df['PRODUTO'].str.strip()
    
    colunas_numericas = ['PTS', 'VALOR']
    colunas_texto = ['PRODUTO', 'SUBTIPO', 'TIPO']
    
    df = tratar_valores_nulos(df, colunas_numericas, colunas_texto)
    
    return df


def remover_duplicatas(
    df: pd.DataFrame,
    colunas_chave: Optional[List[str]] = None,
    manter: str = 'first'
) -> pd.DataFrame:
    """
    Remove registros duplicados do DataFrame.
    
    Args:
        df: DataFrame a ser processado.
        colunas_chave: Colunas para identificar duplicatas. Se None, usa todas.
        manter: Qual duplicata manter ('first', 'last', False para remover todas).
    
    Returns:
        DataFrame sem duplicatas.
    """
    df = df.copy()
    
    if colunas_chave:
        df = df.drop_duplicates(subset=colunas_chave, keep=manter)
    else:
        df = df.drop_duplicates(keep=manter)
    
    return df


def adicionar_coluna_periodo(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adiciona coluna de período (AAAA-MM) baseado em mes e ano.
    
    Args:
        df: DataFrame com colunas 'mes' e 'ano'.
    
    Returns:
        DataFrame com coluna 'periodo' adicionada.
    """
    df = df.copy()
    
    if 'mes' in df.columns and 'ano' in df.columns:
        df['periodo'] = df.apply(
            lambda row: f"{int(row['ano'])}-{int(row['mes']):02d}",
            axis=1
        )
    
    return df


def formatar_valor_brasileiro(valor: float) -> str:
    """
    Formata valor float para string em formato brasileiro.
    
    Args:
        valor: Valor numérico.
    
    Returns:
        String formatada (ex: 'R$ 1.500,00').
    """
    if pd.isna(valor):
        return 'R$ 0,00'
    
    return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')


def formatar_percentual_brasileiro(valor: float) -> str:
    """
    Formata percentual float para string em formato brasileiro.
    
    Args:
        valor: Valor percentual.
    
    Returns:
        String formatada (ex: '85,5%').
    """
    if pd.isna(valor):
        return '0,0%'
    
    return f"{valor:.1f}%".replace('.', ',')
