"""
Módulo para carregamento de dados de arquivos Excel.
"""
import pandas as pd
from pathlib import Path
from typing import Optional, Dict, List
import glob
from src.config.settings import (
    DATA_DIR_DIGITACAO,
    DATA_DIR_METAS,
    DATA_DIR_TABELAS,
    DATA_DIR_CONFIGURACAO
)


def carregar_digitacao(mes: Optional[int] = None, ano: Optional[int] = None) -> pd.DataFrame:
    """
    Carrega dados de digitação (vendas) de um mês específico ou todos os meses.
    
    Args:
        mes: Número do mês (1-12). Se None, carrega todos os meses.
        ano: Ano (ex: 2026). Se None, carrega todos os anos.
    
    Returns:
        DataFrame com dados de vendas.
    """
    if mes and ano:
        meses_pt = {
            1: 'janeiro', 2: 'fevereiro', 3: 'marco', 4: 'abril',
            5: 'maio', 6: 'junho', 7: 'julho', 8: 'agosto',
            9: 'setembro', 10: 'outubro', 11: 'novembro', 12: 'dezembro'
        }
        mes_nome = meses_pt.get(mes, '')
        arquivo = DATA_DIR_DIGITACAO / f"{mes_nome}_{ano}.xlsx"
        
        if not arquivo.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {arquivo}")
        
        df = pd.read_excel(arquivo)
        df['mes'] = mes
        df['ano'] = ano
        return df
    else:
        arquivos = glob.glob(str(DATA_DIR_DIGITACAO / "*.xlsx"))
        if not arquivos:
            raise FileNotFoundError(
                f"Nenhum arquivo encontrado em {DATA_DIR_DIGITACAO}"
            )
        
        dfs = []
        for arquivo in arquivos:
            df = pd.read_excel(arquivo)
            nome_arquivo = Path(arquivo).stem
            partes = nome_arquivo.split('_')
            if len(partes) >= 2:
                mes_nome = partes[0]
                ano_str = partes[1]
                
                meses_map = {
                    'janeiro': 1, 'fevereiro': 2, 'marco': 3, 'abril': 4,
                    'maio': 5, 'junho': 6, 'julho': 7, 'agosto': 8,
                    'setembro': 9, 'outubro': 10, 'novembro': 11, 'dezembro': 12
                }
                
                df['mes'] = meses_map.get(mes_nome.lower(), 0)
                df['ano'] = int(ano_str)
            
            dfs.append(df)
        
        return pd.concat(dfs, ignore_index=True)


def carregar_metas(mes: Optional[int] = None, ano: Optional[int] = None) -> pd.DataFrame:
    """
    Carrega dados de metas por loja e consultor.
    
    Args:
        mes: Número do mês (1-12). Se None, carrega todos os meses.
        ano: Ano (ex: 2026). Se None, carrega todos os anos.
    
    Returns:
        DataFrame com metas por loja e consultor.
    """
    if mes:
        meses_pt = {
            1: 'janeiro', 2: 'fevereiro', 3: 'marco', 4: 'abril',
            5: 'maio', 6: 'junho', 7: 'julho', 8: 'agosto',
            9: 'setembro', 10: 'outubro', 11: 'novembro', 12: 'dezembro'
        }
        mes_nome = meses_pt.get(mes, '')
        arquivo = DATA_DIR_METAS / f"metas_{mes_nome}.xlsx"
        
        if not arquivo.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {arquivo}")
        
        df = pd.read_excel(arquivo)
        df['mes'] = mes
        if ano:
            df['ano'] = ano
        return df
    else:
        arquivos = glob.glob(str(DATA_DIR_METAS / "*.xlsx"))
        if not arquivos:
            raise FileNotFoundError(
                f"Nenhum arquivo encontrado em {DATA_DIR_METAS}"
            )
        
        dfs = []
        for arquivo in arquivos:
            df = pd.read_excel(arquivo)
            nome_arquivo = Path(arquivo).stem
            
            if 'metas_' in nome_arquivo:
                mes_nome = nome_arquivo.replace('metas_', '')
                
                meses_map = {
                    'janeiro': 1, 'fevereiro': 2, 'marco': 3, 'abril': 4,
                    'maio': 5, 'junho': 6, 'julho': 7, 'agosto': 8,
                    'setembro': 9, 'outubro': 10, 'novembro': 11, 'dezembro': 12
                }
                
                df['mes'] = meses_map.get(mes_nome.lower(), 0)
            
            dfs.append(df)
        
        return pd.concat(dfs, ignore_index=True)


def carregar_tabelas_produtos(mes: Optional[int] = None, ano: Optional[int] = None) -> pd.DataFrame:
    """
    Carrega tabelas de produtos com pontuação (PTS).
    
    Args:
        mes: Número do mês (1-12). Se None, carrega todos os meses.
        ano: Ano (ex: 2026). Se None, carrega todos os anos.
    
    Returns:
        DataFrame com especificação de produtos e pontuação.
    """
    if mes and ano:
        meses_pt = {
            1: 'janeiro', 2: 'fevereiro', 3: 'marco', 4: 'abril',
            5: 'maio', 6: 'junho', 7: 'julho', 8: 'agosto',
            9: 'setembro', 10: 'outubro', 11: 'novembro', 12: 'dezembro'
        }
        mes_nome = meses_pt.get(mes, '')
        arquivo = DATA_DIR_TABELAS / f"Tabelas_{mes_nome}_{ano}.xlsx"
        
        if not arquivo.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {arquivo}")
        
        df = pd.read_excel(arquivo)
        df['mes'] = mes
        df['ano'] = ano
        return df
    else:
        arquivos = glob.glob(str(DATA_DIR_TABELAS / "*.xlsx"))
        if not arquivos:
            raise FileNotFoundError(
                f"Nenhum arquivo encontrado em {DATA_DIR_TABELAS}"
            )
        
        dfs = []
        for arquivo in arquivos:
            df = pd.read_excel(arquivo)
            nome_arquivo = Path(arquivo).stem
            
            partes = nome_arquivo.replace('Tabelas_', '').split('_')
            if len(partes) >= 2:
                mes_nome = partes[0]
                ano_str = partes[1]
                
                meses_map = {
                    'janeiro': 1, 'fevereiro': 2, 'marco': 3, 'abril': 4,
                    'maio': 5, 'junho': 6, 'julho': 7, 'agosto': 8,
                    'setembro': 9, 'outubro': 10, 'novembro': 11, 'dezembro': 12
                }
                
                df['mes'] = meses_map.get(mes_nome.lower(), 0)
                df['ano'] = int(ano_str)
            
            dfs.append(df)
        
        return pd.concat(dfs, ignore_index=True)


def carregar_hc_colaboradores() -> pd.DataFrame:
    """
    Carrega dados de headcount de colaboradores.
    
    Returns:
        DataFrame com informações de colaboradores.
    """
    arquivo = DATA_DIR_CONFIGURACAO / "HC_Colaboradores.xlsx"
    
    if not arquivo.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {arquivo}")
    
    return pd.read_excel(arquivo)


def carregar_loja_regiao() -> pd.DataFrame:
    """
    Carrega mapeamento de loja para região.
    
    Returns:
        DataFrame com mapeamento loja-região.
    """
    arquivo = DATA_DIR_CONFIGURACAO / "loja_regiao.xlsx"
    
    if not arquivo.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {arquivo}")
    
    return pd.read_excel(arquivo)


def validar_estrutura_digitacao(df: pd.DataFrame) -> Dict[str, bool]:
    """
    Valida se o DataFrame de digitação possui as colunas necessárias.
    
    Args:
        df: DataFrame de digitação.
    
    Returns:
        Dicionário com status de validação de cada coluna.
    """
    colunas_esperadas = ['TIPO OPER.', 'SUBTIPO']
    
    validacao = {}
    for coluna in colunas_esperadas:
        validacao[coluna] = coluna in df.columns
    
    return validacao


def validar_estrutura_tabelas(df: pd.DataFrame) -> Dict[str, bool]:
    """
    Valida se o DataFrame de tabelas possui as colunas necessárias.
    
    Args:
        df: DataFrame de tabelas de produtos.
    
    Returns:
        Dicionário com status de validação de cada coluna.
    """
    colunas_esperadas = ['PTS', 'SUBTIPO']
    
    validacao = {}
    for coluna in colunas_esperadas:
        validacao[coluna] = coluna in df.columns
    
    return validacao


def listar_arquivos_disponiveis() -> Dict[str, List[str]]:
    """
    Lista todos os arquivos disponíveis em cada diretório de dados.
    
    Returns:
        Dicionário com lista de arquivos por diretório.
    """
    return {
        'digitacao': [
            Path(f).name for f in glob.glob(str(DATA_DIR_DIGITACAO / "*.xlsx"))
        ],
        'metas': [
            Path(f).name for f in glob.glob(str(DATA_DIR_METAS / "*.xlsx"))
        ],
        'tabelas': [
            Path(f).name for f in glob.glob(str(DATA_DIR_TABELAS / "*.xlsx"))
        ],
        'configuracao': [
            Path(f).name for f in glob.glob(str(DATA_DIR_CONFIGURACAO / "*.xlsx"))
        ]
    }
