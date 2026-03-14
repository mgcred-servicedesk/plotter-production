"""
Módulo para consolidação de múltiplas fontes de dados.
"""
import pandas as pd
from datetime import datetime
from typing import Optional, Tuple
import numpy as np
from src.data_processing.loader import (
    carregar_digitacao,
    carregar_metas,
    carregar_tabelas_produtos,
    carregar_loja_regiao,
    carregar_hc_colaboradores
)
from src.data_processing.transformer import (
    aplicar_transformacoes_digitacao,
    aplicar_transformacoes_metas,
    aplicar_transformacoes_tabelas
)
from src.data_processing.business_rules import classificar_produtos
from src.data_processing.points_calculator import adicionar_pontuacao


def calcular_dias_uteis(
    mes: int,
    ano: int,
    data_referencia: Optional[datetime] = None,
    feriados: Optional[list] = None
) -> Tuple[int, int]:
    """
    Calcula dias úteis decorridos e restantes no mês.
    
    Args:
        mes: Número do mês (1-12).
        ano: Ano.
        data_referencia: Data de referência. Se None, usa data atual.
        feriados: Lista de feriados (strings DD/MM/YYYY).
    
    Returns:
        Tupla (dias_uteis_decorridos, dias_uteis_restantes).
    """
    from pandas.tseries.offsets import BDay
    
    if data_referencia is None:
        data_referencia = datetime.now()
    
    primeiro_dia = datetime(ano, mes, 1)
    
    if mes == 12:
        ultimo_dia = datetime(ano + 1, 1, 1) - pd.Timedelta(days=1)
    else:
        ultimo_dia = datetime(ano, mes + 1, 1) - pd.Timedelta(days=1)
    
    dias_uteis_total = len(pd.bdate_range(primeiro_dia, ultimo_dia))
    
    if data_referencia < primeiro_dia:
        return 0, dias_uteis_total
    
    if data_referencia > ultimo_dia:
        return dias_uteis_total, 0
    
    dias_uteis_decorridos = len(pd.bdate_range(primeiro_dia, data_referencia))
    dias_uteis_restantes = dias_uteis_total - dias_uteis_decorridos
    
    return dias_uteis_decorridos, dias_uteis_restantes


def consolidar_dados_mes(
    mes: int,
    ano: int,
    aplicar_regras: bool = True
) -> pd.DataFrame:
    """
    Consolida todos os dados de um mês específico.
    
    Carrega e consolida:
    - Dados de digitação (vendas)
    - Tabelas de produtos (para pontuação)
    - Mapeamento loja-região
    - Aplica regras de negócio
    - Calcula pontuação
    
    Args:
        mes: Número do mês (1-12).
        ano: Ano.
        aplicar_regras: Se True, aplica regras de negócio.
    
    Returns:
        DataFrame consolidado com todos os dados.
    """
    df_vendas = carregar_digitacao(mes, ano)
    df_vendas = aplicar_transformacoes_digitacao(df_vendas)
    
    df_tabelas = carregar_tabelas_produtos(mes, ano)
    df_tabelas = aplicar_transformacoes_tabelas(df_tabelas)
    
    df_loja_regiao = carregar_loja_regiao()
    
    if aplicar_regras:
        df_vendas = classificar_produtos(df_vendas)
    
    if 'PRODUTO' in df_vendas.columns and 'PRODUTO' in df_tabelas.columns:
        df_vendas = adicionar_pontuacao(
            df_vendas,
            df_tabelas,
            coluna_valor='VALOR',
            coluna_produto='PRODUTO',
            coluna_pts='PTS'
        )
    
    if 'LOJA' in df_vendas.columns and 'LOJA' in df_loja_regiao.columns:
        df_vendas = df_vendas.merge(
            df_loja_regiao[['LOJA', 'REGIAO']],
            on='LOJA',
            how='left'
        )
    
    return df_vendas


def consolidar_com_metas(
    df_vendas: pd.DataFrame,
    mes: int,
    ano: int,
    nivel: str = 'consultor'
) -> pd.DataFrame:
    """
    Consolida dados de vendas com metas.
    
    Args:
        df_vendas: DataFrame com dados de vendas consolidados.
        mes: Número do mês.
        ano: Ano.
        nivel: Nível de agregação ('consultor', 'loja', 'regiao').
    
    Returns:
        DataFrame consolidado com metas.
    """
    df_metas = carregar_metas(mes, ano)
    df_metas = aplicar_transformacoes_metas(df_metas)
    
    if nivel == 'consultor':
        coluna_chave = 'CONSULTOR'
    elif nivel == 'loja':
        coluna_chave = 'LOJA'
    elif nivel == 'regiao':
        coluna_chave = 'REGIAO'
    else:
        raise ValueError(f"Nível inválido: {nivel}")
    
    if coluna_chave in df_vendas.columns and coluna_chave in df_metas.columns:
        df_consolidado = df_vendas.merge(
            df_metas[[coluna_chave, 'META_PRATA', 'META_OURO']],
            on=coluna_chave,
            how='left'
        )
        
        df_consolidado['META_PRATA'] = df_consolidado['META_PRATA'].fillna(0)
        df_consolidado['META_OURO'] = df_consolidado['META_OURO'].fillna(0)
        
        return df_consolidado
    
    return df_vendas


def consolidar_multiplos_meses(
    meses: list,
    anos: list,
    aplicar_regras: bool = True
) -> pd.DataFrame:
    """
    Consolida dados de múltiplos meses.
    
    Args:
        meses: Lista de meses (1-12).
        anos: Lista de anos correspondentes.
        aplicar_regras: Se True, aplica regras de negócio.
    
    Returns:
        DataFrame consolidado com dados de todos os meses.
    """
    if len(meses) != len(anos):
        raise ValueError("Listas de meses e anos devem ter o mesmo tamanho")
    
    dfs = []
    for mes, ano in zip(meses, anos):
        try:
            df = consolidar_dados_mes(mes, ano, aplicar_regras)
            dfs.append(df)
        except FileNotFoundError as e:
            print(f"Aviso: Arquivo não encontrado para {mes}/{ano}: {e}")
            continue
    
    if not dfs:
        raise ValueError("Nenhum dado foi carregado")
    
    return pd.concat(dfs, ignore_index=True)


def criar_dataset_completo(
    mes: int,
    ano: int,
    incluir_metas: bool = True,
    incluir_hc: bool = True
) -> pd.DataFrame:
    """
    Cria dataset completo com todas as informações consolidadas.
    
    Args:
        mes: Número do mês.
        ano: Ano.
        incluir_metas: Se True, inclui informações de metas.
        incluir_hc: Se True, inclui informações de headcount.
    
    Returns:
        DataFrame completo consolidado.
    """
    df = consolidar_dados_mes(mes, ano, aplicar_regras=True)
    
    if incluir_metas:
        df_metas = carregar_metas(mes, ano)
        df_metas = aplicar_transformacoes_metas(df_metas)
        
        if 'CONSULTOR' in df.columns and 'CONSULTOR' in df_metas.columns:
            df = df.merge(
                df_metas[['CONSULTOR', 'META_PRATA', 'META_OURO']],
                on='CONSULTOR',
                how='left'
            )
    
    if incluir_hc:
        try:
            df_hc = carregar_hc_colaboradores()
            if 'CONSULTOR' in df.columns and 'CONSULTOR' in df_hc.columns:
                df = df.merge(
                    df_hc,
                    on='CONSULTOR',
                    how='left'
                )
        except FileNotFoundError:
            pass
    
    dias_decorridos, dias_restantes = calcular_dias_uteis(mes, ano)
    df['dias_uteis_decorridos'] = dias_decorridos
    df['dias_uteis_restantes'] = dias_restantes
    
    return df


def filtrar_por_periodo(
    df: pd.DataFrame,
    data_inicio: Optional[datetime] = None,
    data_fim: Optional[datetime] = None
) -> pd.DataFrame:
    """
    Filtra DataFrame por período.
    
    Args:
        df: DataFrame com coluna 'DATA'.
        data_inicio: Data inicial do filtro.
        data_fim: Data final do filtro.
    
    Returns:
        DataFrame filtrado.
    """
    if 'DATA' not in df.columns:
        return df
    
    df_filtrado = df.copy()
    
    if data_inicio:
        df_filtrado = df_filtrado[df_filtrado['DATA'] >= data_inicio]
    
    if data_fim:
        df_filtrado = df_filtrado[df_filtrado['DATA'] <= data_fim]
    
    return df_filtrado


def agregar_por_nivel(
    df: pd.DataFrame,
    nivel: str = 'consultor',
    metricas: Optional[list] = None
) -> pd.DataFrame:
    """
    Agrega dados por nível hierárquico.
    
    Args:
        df: DataFrame consolidado.
        nivel: Nível de agregação ('consultor', 'loja', 'regiao').
        metricas: Lista de métricas a agregar. Se None, usa padrão.
    
    Returns:
        DataFrame agregado.
    """
    if nivel == 'consultor':
        coluna_grupo = 'CONSULTOR'
    elif nivel == 'loja':
        coluna_grupo = 'LOJA'
    elif nivel == 'regiao':
        coluna_grupo = 'REGIAO'
    else:
        raise ValueError(f"Nível inválido: {nivel}")
    
    if coluna_grupo not in df.columns:
        raise ValueError(f"Coluna '{coluna_grupo}' não encontrada no DataFrame")
    
    if metricas is None:
        metricas_agg = {
            'pontos': 'sum',
            'VALOR': 'sum'
        }
        
        if 'is_emissao_cartao' in df.columns:
            metricas_agg['is_emissao_cartao'] = 'sum'
        if 'is_seguro_med' in df.columns:
            metricas_agg['is_seguro_med'] = 'sum'
        if 'is_seguro_vida_familiar' in df.columns:
            metricas_agg['is_seguro_vida_familiar'] = 'sum'
        if 'is_super_conta' in df.columns:
            metricas_agg['is_super_conta'] = 'sum'
    else:
        metricas_agg = {m: 'sum' for m in metricas}
    
    df_agregado = df.groupby(coluna_grupo).agg(metricas_agg).reset_index()
    
    if nivel == 'loja' and 'REGIAO' in df.columns:
        df_regiao = df[[coluna_grupo, 'REGIAO']].drop_duplicates()
        df_agregado = df_agregado.merge(df_regiao, on=coluna_grupo, how='left')
    
    return df_agregado


def criar_resumo_periodo(
    mes: int,
    ano: int
) -> dict:
    """
    Cria resumo executivo do período.
    
    Args:
        mes: Número do mês.
        ano: Ano.
    
    Returns:
        Dicionário com resumo do período.
    """
    df = consolidar_dados_mes(mes, ano, aplicar_regras=True)
    
    resumo = {
        'mes': mes,
        'ano': ano,
        'total_registros': len(df),
        'total_valor': df['VALOR'].sum() if 'VALOR' in df.columns else 0,
        'total_pontos': df['pontos'].sum() if 'pontos' in df.columns else 0,
        'num_consultores': df['CONSULTOR'].nunique() if 'CONSULTOR' in df.columns else 0,
        'num_lojas': df['LOJA'].nunique() if 'LOJA' in df.columns else 0,
        'num_regioes': df['REGIAO'].nunique() if 'REGIAO' in df.columns else 0
    }
    
    if 'is_emissao_cartao' in df.columns:
        resumo['emissoes_cartao'] = df['is_emissao_cartao'].sum()
    
    if 'is_seguro_med' in df.columns:
        resumo['seguros_med'] = df['is_seguro_med'].sum()
    
    if 'is_seguro_vida_familiar' in df.columns:
        resumo['seguros_vida_familiar'] = df['is_seguro_vida_familiar'].sum()
    
    if 'is_super_conta' in df.columns:
        resumo['super_contas'] = df['is_super_conta'].sum()
    
    dias_decorridos, dias_restantes = calcular_dias_uteis(mes, ano)
    resumo['dias_uteis_decorridos'] = dias_decorridos
    resumo['dias_uteis_restantes'] = dias_restantes
    
    return resumo
