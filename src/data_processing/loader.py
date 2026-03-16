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
    DATA_DIR_CONFIGURACAO,
    MESES_ARQUIVO,
)
from src.data_processing.column_mapper import (
    mapear_digitacao,
    mapear_tabelas,
    mapear_metas,
    mapear_loja_regiao,
    mapear_supervisores,
    adicionar_coluna_subtipo_via_merge,
    aplicar_regras_exclusao_valor_pontos,
)


MESES_NOME_PARA_NUM = {
    v: k for k, v in MESES_ARQUIVO.items()
}


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
        mes_nome = MESES_ARQUIVO.get(mes, '')
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
                
                df['mes'] = MESES_NOME_PARA_NUM.get(
                    mes_nome.lower(), 0
                )
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
        mes_nome = MESES_ARQUIVO.get(mes, '')
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
                
                df['mes'] = MESES_NOME_PARA_NUM.get(
                    mes_nome.lower(), 0
                )
            
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
        mes_nome = MESES_ARQUIVO.get(mes, '')
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


def carregar_supervisores() -> pd.DataFrame:
    """
    Carrega dados de supervisores.

    Returns:
        DataFrame com supervisores mapeados.
    """
    arquivo = DATA_DIR_CONFIGURACAO / "Supervisores.xlsx"

    if not arquivo.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {arquivo}"
        )

    return pd.read_excel(arquivo)


def listar_arquivos_disponiveis() -> Dict[str, List[str]]:
    """
    Lista todos os arquivos disponíveis em cada
    diretório de dados.

    Returns:
        Dicionário com lista de arquivos por diretório.
    """
    return {
        'digitacao': [
            Path(f).name
            for f in glob.glob(
                str(DATA_DIR_DIGITACAO / "*.xlsx")
            )
        ],
        'metas': [
            Path(f).name
            for f in glob.glob(
                str(DATA_DIR_METAS / "*.xlsx")
            )
        ],
        'tabelas': [
            Path(f).name
            for f in glob.glob(
                str(DATA_DIR_TABELAS / "*.xlsx")
            )
        ],
        'configuracao': [
            Path(f).name
            for f in glob.glob(
                str(DATA_DIR_CONFIGURACAO / "*.xlsx")
            )
        ]
    }


def carregar_e_processar_dados(mes, ano):
    """
    Carrega e processa todos os dados necessários
    para geração de relatórios.

    Pipeline unificado: carrega arquivos, mapeia colunas,
    faz JOIN com tabelas, calcula pontuação, aplica regras
    de exclusão e adiciona região.

    Args:
        mes: Mês do relatório (1-12).
        ano: Ano do relatório.

    Returns:
        Tupla (df_consolidado, df_metas,
               df_supervisores, dia_atual)
    """
    mes_nome = MESES_ARQUIVO[mes]

    print(f"\n{'=' * 80}")
    print(f"CARREGANDO DADOS - {mes:02d}/{ano}")
    print(f"{'=' * 80}")

    print("\n1. Carregando digitação...")
    df_digitacao = pd.read_excel(
        f'digitacao/{mes_nome}_{ano}.xlsx'
    )
    print(f"   ✓ {len(df_digitacao)} registros carregados")

    print("\n2. Carregando tabelas de produtos...")
    df_tabelas = pd.read_excel(
        f'tabelas/Tabelas_{mes_nome}_{ano}.xlsx'
    )
    print(f"   ✓ {len(df_tabelas)} produtos carregados")

    print("\n3. Carregando metas...")
    df_metas = pd.read_excel(
        f'metas/metas_{mes_nome}.xlsx'
    )
    print(f"   ✓ {len(df_metas)} lojas com metas")

    print("\n4. Carregando configuração loja-região...")
    df_loja_regiao = pd.read_excel(
        'configuracao/loja_regiao.xlsx'
    )
    print(f"   ✓ {len(df_loja_regiao)} lojas mapeadas")

    print("\n5. Carregando supervisores...")
    df_supervisores = pd.read_excel(
        'configuracao/Supervisores.xlsx'
    )
    print(
        f"   ✓ {len(df_supervisores)} supervisores"
    )

    print("\n6. Aplicando mapeamentos...")
    df_digitacao = mapear_digitacao(df_digitacao)
    df_tabelas = mapear_tabelas(df_tabelas)
    df_metas = mapear_metas(df_metas)
    df_loja_regiao = mapear_loja_regiao(df_loja_regiao)
    df_supervisores = mapear_supervisores(df_supervisores)
    print("   ✓ Colunas mapeadas")

    print("\n7. Identificando última data registrada...")
    df_digitacao['DATA'] = pd.to_datetime(
        df_digitacao['DATA']
    )
    d_menos_1 = df_digitacao['DATA'].max().date()
    dia_atual = d_menos_1.day
    print(
        f"   ✓ Última data: "
        f"{d_menos_1.strftime('%d/%m/%Y')}"
    )
    print(
        f"   ✓ Análise baseada em {dia_atual} dias"
    )

    print("\n8. Fazendo JOIN com tabelas...")
    df_consolidado = adicionar_coluna_subtipo_via_merge(
        df_digitacao, df_tabelas
    )
    print(
        f"   ✓ JOIN realizado: "
        f"{len(df_consolidado)} registros"
    )

    print("\n9. Calculando pontuação...")
    df_consolidado['pontos'] = (
        df_consolidado['VALOR'] * df_consolidado['PTS']
    )
    print(
        f"   ✓ Total de pontos: "
        f"{df_consolidado['pontos'].sum():,.0f}"
    )

    print("\n10. Aplicando regras de exclusão...")
    df_consolidado = aplicar_regras_exclusao_valor_pontos(
        df_consolidado
    )
    emissoes = df_consolidado['is_emissao_cartao'].sum()
    print(
        f"   ✓ {emissoes} produtos de emissão "
        f"excluídos de valores/pontos"
    )

    print("\n11. Adicionando região...")
    df_consolidado = df_consolidado.merge(
        df_loja_regiao[['LOJA', 'REGIAO']],
        on='LOJA',
        how='left'
    )
    print("   ✓ Região adicionada")

    print("\n12. Totais finais:")
    print(
        f"   - Valor total: "
        f"R$ {df_consolidado['VALOR'].sum():,.2f}"
    )
    print(
        f"   - Pontos totais: "
        f"{df_consolidado['pontos'].sum():,.0f}"
    )
    num_sup = len(df_supervisores)
    print(
        f"   - Supervisores (excluídos de análises "
        f"de consultores): {num_sup}"
    )

    return (
        df_consolidado,
        df_metas,
        df_supervisores,
        dia_atual,
    )
