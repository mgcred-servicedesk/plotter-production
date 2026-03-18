"""
Módulo para carregamento de tabelas de pontuação mensais.
"""
import pandas as pd
from pathlib import Path
from typing import Optional
from src.config.settings import MESES_ARQUIVO


PONTUACAO_DIR = Path('pontuacao')


def carregar_pontuacao_mensal(mes: int, ano: int) -> pd.DataFrame:
    """
    Carrega tabela de pontuação específica do mês.

    Args:
        mes: Número do mês (1-12)
        ano: Ano (ex: 2026)

    Returns:
        DataFrame com colunas PRODUTO e PONTOS

    Raises:
        FileNotFoundError: Se arquivo de pontuação não existir
    """
    mes_nome = MESES_ARQUIVO.get(mes, '')
    arquivo = PONTUACAO_DIR / f"pontos_{mes_nome}.xlsx"

    if not arquivo.exists():
        raise FileNotFoundError(
            f"Arquivo de pontuação não encontrado: {arquivo}\n"
            f"Certifique-se de que existe o arquivo "
            f"'pontos_{mes_nome}.xlsx' na pasta 'pontuacao/'"
        )

    df = pd.read_excel(arquivo, sheet_name='Pontuacao')

    if 'PRODUTO' not in df.columns or 'PONTOS' not in df.columns:
        raise ValueError(
            f"Arquivo {arquivo} deve conter colunas 'PRODUTO' e 'PONTOS'"
        )

    df = df[['PRODUTO', 'PONTOS']].copy()
    df['PRODUTO'] = df['PRODUTO'].str.strip().str.upper()
    df['PONTOS'] = pd.to_numeric(df['PONTOS'], errors='coerce').fillna(0)

    df = df.drop_duplicates(subset=['PRODUTO'])

    return df


def criar_mapeamento_tipo_produto():
    """
    Cria mapeamento entre TIPO_PRODUTO dos dados e nomes da tabela de pontuação.
    
    Baseado na tabela de pontuação mensal (pontos_{mes}.xlsx):
    - CNC: 5.0 pontos
    - CNC 13: 1.5 pontos
    - CARTÃO: 2.5 pontos
    - FGTS: 1.5 pontos
    - CONSIG Itau: 0.5 pontos
    - CONSIG BMG: 1.0 pontos
    - CONSIG C6: 1.0 pontos
    - CONSIG PRIV: 3.0 pontos
    - ANT. DE BENEF.: 1.5 pontos
    
    Returns:
        Dicionário com mapeamento
    """
    return {
        'CNC': 'CNC',
        'CNC 13º': 'CNC 13',
        'CNC 13': 'CNC 13',
        'CNC ANT': 'ANT. DE BENEF.',
        'SAQUE': 'SAQUE',
        'SAQUE BENEFICIO': 'SAQUE BENEFICIO',
        'CONSIG': 'CONSIG BMG',
        'CONSIG PRIV': 'CONSIG PRIV',
        'CONSIG BMG': 'CONSIG BMG',
        'CONSIG ITAU': 'CONSIG ITAU',
        'CONSIG Itau': 'CONSIG ITAU',
        'CONSIG C6': 'CONSIG C6',
        'FGTS': 'FGTS',
        'EMISSAO': 'CARTÃO',
        'EMISSAO CB': 'CARTÃO',
        'EMISSAO CC': 'CARTÃO',
        'Portabilidade': 'PORTABILIDADE',
        'PORTABILIDADE': 'PORTABILIDADE',
    }


def adicionar_pontuacao_mensal(
    df_vendas: pd.DataFrame,
    mes: int,
    ano: int
) -> pd.DataFrame:
    """
    Adiciona pontuação mensal ao DataFrame de vendas.

    Faz merge com tabela de pontuação do mês específico usando TIPO_PRODUTO.

    Args:
        df_vendas: DataFrame com dados de vendas (deve ter TIPO_PRODUTO)
        mes: Número do mês (1-12)
        ano: Ano (ex: 2026)

    Returns:
        DataFrame de vendas com coluna 'PONTOS' adicionada
    """
    df_pontuacao = carregar_pontuacao_mensal(mes, ano)

    if 'TIPO_PRODUTO' not in df_vendas.columns:
        raise ValueError(
            "DataFrame de vendas deve ter coluna 'TIPO_PRODUTO'"
        )

    mapeamento = criar_mapeamento_tipo_produto()
    
    df_vendas['PRODUTO_PONTUACAO'] = (
        df_vendas['TIPO_PRODUTO'].map(mapeamento)
    )

    df_result = df_vendas.merge(
        df_pontuacao,
        left_on='PRODUTO_PONTUACAO',
        right_on='PRODUTO',
        how='left',
        suffixes=('', '_pts')
    )

    df_result['PONTOS'] = df_result['PONTOS'].fillna(0)

    df_result = df_result.drop(columns=['PRODUTO_PONTUACAO'])
    if 'PRODUTO_pts' in df_result.columns:
        df_result = df_result.drop(columns=['PRODUTO_pts'])

    return df_result


def verificar_produtos_sem_pontuacao(df: pd.DataFrame) -> dict:
    """
    Verifica produtos sem pontuação e retorna informações detalhadas.
    
    Args:
        df: DataFrame com dados de vendas processados
        
    Returns:
        Dicionário com informações sobre produtos sem pontuação
    """
    sem_pontuacao = df[df['PONTOS'] == 0]
    
    if len(sem_pontuacao) == 0:
        return {
            'tem_problemas': False,
            'total_registros': 0,
            'valor_total': 0,
            'produtos': []
        }
    
    produtos_detalhes = sem_pontuacao.groupby('PRODUTO').agg({
        'VALOR': 'sum',
        'TIPO_PRODUTO': 'first'
    }).reset_index()
    produtos_detalhes = produtos_detalhes.sort_values('VALOR', ascending=False)
    
    return {
        'tem_problemas': True,
        'total_registros': len(sem_pontuacao),
        'valor_total': sem_pontuacao['VALOR'].sum(),
        'produtos': produtos_detalhes.to_dict('records')
    }


def calcular_pontos_com_tabela_mensal(
    df_vendas: pd.DataFrame,
    mes: int,
    ano: int,
    mostrar_avisos: bool = True
) -> pd.DataFrame:
    """
    Calcula pontos usando tabela de pontuação mensal.

    Args:
        df_vendas: DataFrame com dados de vendas (deve ter VALOR e PRODUTO)
        mes: Número do mês (1-12)
        ano: Ano (ex: 2026)
        mostrar_avisos: Se True, exibe avisos sobre produtos sem pontuação

    Returns:
        DataFrame com coluna 'pontos' calculada
    """
    df = adicionar_pontuacao_mensal(df_vendas, mes, ano)

    if 'VALOR' not in df.columns:
        raise ValueError("DataFrame deve ter coluna 'VALOR'")

    df['pontos'] = df['VALOR'] * df['PONTOS']
    
    if mostrar_avisos:
        info = verificar_produtos_sem_pontuacao(df)
        if info['tem_problemas']:
            import warnings
            msg = (
                f"\n⚠️  AVISO: {info['total_registros']} registros "
                f"sem pontuação identificada!\n"
                f"   Valor total afetado: R$ {info['valor_total']:,.2f}\n"
                f"   Produtos sem pontuação:\n"
            )
            for produto in info['produtos'][:5]:
                tipo = produto.get('TIPO_PRODUTO', 'None')
                msg += (
                    f"   - {produto['PRODUTO'][:60]}: "
                    f"R$ {produto['VALOR']:,.2f} "
                    f"(TIPO: {tipo})\n"
                )
            if len(info['produtos']) > 5:
                msg += f"   ... e mais {len(info['produtos']) - 5} produtos\n"
            
            warnings.warn(msg, UserWarning, stacklevel=2)

    return df
