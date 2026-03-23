"""
Módulo para aplicação de regras de negócio específicas.
"""
import pandas as pd
from typing import Tuple
from src.config.settings import (
    COLUNAS_TIPO_OPER,
    COLUNA_SUBTIPO,
    TIPO_OPER_CARTAO_BENEFICIO,
    TIPO_OPER_VENDA_PRE_ADESAO,
    TIPO_OPER_BMG_MED,
    TIPO_OPER_SEGURO,
    SUBTIPO_SUPER_CONTA
)


def identificar_emissao_cartao(df: pd.DataFrame) -> pd.Series:
    """
    Identifica produtos de emissão de cartão.
    
    Regra: TIPO OPER. = 'CARTÃO BENEFICIO' ou 'Venda Pré-Adesão'
    Estes produtos NÃO contam para valores e pontuação.
    
    Args:
        df: DataFrame com dados de vendas.
    
    Returns:
        Series booleana indicando se é emissão de cartão.
    """
    if COLUNAS_TIPO_OPER not in df.columns:
        return pd.Series([False] * len(df), index=df.index)
    
    return df[COLUNAS_TIPO_OPER].isin([
        TIPO_OPER_CARTAO_BENEFICIO,
        TIPO_OPER_VENDA_PRE_ADESAO
    ])


def identificar_seguro_med(df: pd.DataFrame) -> pd.Series:
    """
    Identifica produtos de seguro Med.

    Regra: TIPO OPER. = 'BMG MED'
    Estes produtos NÃO contam para valores e pontuação —
    apenas quantidade é contabilizada.

    Nota (Supabase): esses contratos não possuem
    status_pagamento_cliente = 'PAGO AO CLIENTE'. São
    carregados via sub_status_banco = 'Liquidada' combinado
    com tipo_operacao IN ('BMG MED', 'Seguro').

    Args:
        df: DataFrame com dados de vendas.

    Returns:
        Series booleana indicando se é seguro Med.
    """
    if COLUNAS_TIPO_OPER not in df.columns:
        return pd.Series([False] * len(df), index=df.index)

    return df[COLUNAS_TIPO_OPER] == TIPO_OPER_BMG_MED


def identificar_seguro_vida_familiar(df: pd.DataFrame) -> pd.Series:
    """
    Identifica produtos de seguro Vida Familiar.

    Regra: TIPO OPER. = 'Seguro'
    Estes produtos NÃO contam para valores e pontuação —
    apenas quantidade é contabilizada.

    Nota (Supabase): esses contratos não possuem
    status_pagamento_cliente = 'PAGO AO CLIENTE'. São
    carregados via sub_status_banco = 'Liquidada' combinado
    com tipo_operacao IN ('BMG MED', 'Seguro').

    Args:
        df: DataFrame com dados de vendas.

    Returns:
        Series booleana indicando se é seguro Vida Familiar.
    """
    if COLUNAS_TIPO_OPER not in df.columns:
        return pd.Series([False] * len(df), index=df.index)

    return df[COLUNAS_TIPO_OPER] == TIPO_OPER_SEGURO


def identificar_super_conta(df: pd.DataFrame) -> pd.Series:
    """
    Identifica produtos Super Conta.
    
    Regra: SUBTIPO = 'SUPER CONTA'
    Estes produtos SIM contam para valores e pontuação,
    E TAMBÉM contam como produção Super Conta (quantidade).
    
    Args:
        df: DataFrame com dados de vendas.
    
    Returns:
        Series booleana indicando se é Super Conta.
    """
    if COLUNA_SUBTIPO not in df.columns:
        return pd.Series([False] * len(df), index=df.index)
    
    return df[COLUNA_SUBTIPO] == SUBTIPO_SUPER_CONTA


def aplicar_regras_exclusao(df: pd.DataFrame) -> pd.Series:
    """
    Identifica produtos que devem ser EXCLUÍDOS do cálculo de valores e pontuação.
    
    Produtos excluídos:
    - Emissão de cartão (CARTÃO BENEFICIO, Venda Pré-Adesão)
    - Seguros (BMG MED, Seguro)
    
    Args:
        df: DataFrame com dados de vendas.
    
    Returns:
        Series booleana indicando se deve ser excluído (True = excluir).
    """
    emissao_cartao = identificar_emissao_cartao(df)
    seguro_med = identificar_seguro_med(df)
    seguro_vida = identificar_seguro_vida_familiar(df)
    
    return emissao_cartao | seguro_med | seguro_vida


def classificar_produtos(df: pd.DataFrame) -> pd.DataFrame:
    """
    Classifica todos os produtos conforme regras de negócio.
    
    Adiciona colunas ao DataFrame:
    - is_emissao_cartao: Se é emissão de cartão
    - is_seguro_med: Se é seguro Med
    - is_seguro_vida_familiar: Se é seguro Vida Familiar
    - is_super_conta: Se é Super Conta
    - conta_valor_pontuacao: Se conta para valores e pontuação
    
    Args:
        df: DataFrame com dados de vendas.
    
    Returns:
        DataFrame com colunas de classificação adicionadas.
    """
    df = df.copy()
    
    df['is_emissao_cartao'] = identificar_emissao_cartao(df)
    df['is_seguro_med'] = identificar_seguro_med(df)
    df['is_seguro_vida_familiar'] = identificar_seguro_vida_familiar(df)
    df['is_super_conta'] = identificar_super_conta(df)
    
    excluir = aplicar_regras_exclusao(df)
    df['conta_valor_pontuacao'] = ~excluir
    
    return df


def contar_produtos_especiais(df: pd.DataFrame) -> dict:
    """
    Conta quantidades de produtos especiais.
    
    Args:
        df: DataFrame com dados de vendas classificados.
    
    Returns:
        Dicionário com contagens de cada tipo de produto especial.
    """
    if 'is_emissao_cartao' not in df.columns:
        df = classificar_produtos(df)
    
    return {
        'emissao_cartao': df['is_emissao_cartao'].sum(),
        'seguro_med': df['is_seguro_med'].sum(),
        'seguro_vida_familiar': df['is_seguro_vida_familiar'].sum(),
        'super_conta': df['is_super_conta'].sum()
    }


def filtrar_para_calculo_pontuacao(df: pd.DataFrame) -> pd.DataFrame:
    """
    Filtra DataFrame para incluir apenas produtos que contam para pontuação.
    
    Args:
        df: DataFrame com dados de vendas.
    
    Returns:
        DataFrame filtrado com apenas produtos que contam para pontuação.
    """
    if 'conta_valor_pontuacao' not in df.columns:
        df = classificar_produtos(df)
    
    return df[df['conta_valor_pontuacao']].copy()


def validar_regras_negocio(df: pd.DataFrame) -> dict:
    """
    Valida se as regras de negócio podem ser aplicadas ao DataFrame.
    
    Args:
        df: DataFrame com dados de vendas.
    
    Returns:
        Dicionário com status de validação.
    """
    validacao = {
        'tem_coluna_tipo_oper': COLUNAS_TIPO_OPER in df.columns,
        'tem_coluna_subtipo': COLUNA_SUBTIPO in df.columns,
        'pode_aplicar_regras': True
    }
    
    if not validacao['tem_coluna_tipo_oper']:
        validacao['pode_aplicar_regras'] = False
        validacao['mensagem'] = f"Coluna '{COLUNAS_TIPO_OPER}' não encontrada"
    
    return validacao


def gerar_relatorio_regras(df: pd.DataFrame) -> pd.DataFrame:
    """
    Gera relatório resumido da aplicação das regras de negócio.
    
    Args:
        df: DataFrame com dados de vendas.
    
    Returns:
        DataFrame com resumo das regras aplicadas.
    """
    df_classificado = classificar_produtos(df)
    
    resumo = {
        'Categoria': [
            'Total de Registros',
            'Emissão de Cartão',
            'Seguro Med',
            'Seguro Vida Familiar',
            'Super Conta',
            'Conta para Pontuação',
            'NÃO Conta para Pontuação'
        ],
        'Quantidade': [
            len(df_classificado),
            df_classificado['is_emissao_cartao'].sum(),
            df_classificado['is_seguro_med'].sum(),
            df_classificado['is_seguro_vida_familiar'].sum(),
            df_classificado['is_super_conta'].sum(),
            df_classificado['conta_valor_pontuacao'].sum(),
            (~df_classificado['conta_valor_pontuacao']).sum()
        ]
    }
    
    return pd.DataFrame(resumo)
