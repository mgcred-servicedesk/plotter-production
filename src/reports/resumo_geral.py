import pandas as pd
import numpy as np
from src.reports.tabela_produtos import calcular_dias_uteis


def criar_resumo_geral(df, df_metas, ano, mes, dia_atual=None, df_supervisores=None):
    """
    Cria relatório de resumo geral consolidado.
    
    Args:
        df: DataFrame consolidado com vendas
        df_metas: DataFrame com metas
        ano: Ano do relatório
        mes: Mês do relatório
        dia_atual: Dia atual para cálculo de dias úteis
        df_supervisores: DataFrame com supervisores (opcional)
    
    Returns:
        dict com DataFrames de cada seção do resumo
    """
    du_total, du_decorridos, du_restantes = calcular_dias_uteis(ano, mes, dia_atual)
    dias_uteis_info = {
        'total': du_total,
        'decorridos': du_decorridos,
        'restantes': du_restantes
    }
    
    resumo = {}
    
    resumo['totais_gerais'] = _criar_totais_gerais(
        df, df_metas, dias_uteis_info
    )
    
    resumo['por_regiao'] = _criar_resumo_por_regiao(
        df, df_metas, dias_uteis_info
    )
    
    resumo['top_lojas'] = _criar_top_lojas(df, top_n=10)
    
    resumo['top_lojas_ticket_medio'] = _criar_top_lojas_ticket_medio(
        df, top_n=10
    )
    
    resumo['top_lojas_media_du'] = _criar_top_lojas_media_du(
        df, dias_uteis_info, top_n=10
    )
    
    resumo['top_lojas_por_produto'] = _criar_top_lojas_por_produto(
        df, dias_uteis_info, top_n=10
    )
    
    resumo['top_lojas_atingimento'] = _criar_top_lojas_atingimento(
        df, df_metas, top_n=10
    )
    
    resumo['top_consultores'] = _criar_top_consultores(df, df_supervisores, top_n=10)
    
    resumo['top_consultores_ticket_medio'] = _criar_top_consultores_ticket_medio(
        df, df_supervisores, top_n=10
    )
    
    resumo['top_consultores_media_du'] = _criar_top_consultores_media_du(
        df, df_supervisores, dias_uteis_info, top_n=10
    )
    
    resumo['top_consultores_por_produto'] = _criar_top_consultores_por_produto(
        df, df_supervisores, dias_uteis_info, top_n=10
    )
    
    resumo['top_consultores_atingimento'] = _criar_top_consultores_atingimento(
        df, df_metas, df_supervisores, top_n=10
    )
    
    resumo['ranking_regiao_pontos'] = _criar_ranking_regiao_pontos(df)
    
    resumo['ranking_regiao_ticket_medio'] = _criar_ranking_regiao_ticket_medio(
        df
    )
    
    resumo['ranking_regiao_media_du'] = _criar_ranking_regiao_media_du(
        df, dias_uteis_info
    )
    
    resumo['ranking_regiao_por_produto'] = _criar_ranking_regiao_por_produto(
        df, dias_uteis_info
    )
    
    resumo['ranking_regiao_atingimento'] = _criar_ranking_regiao_atingimento(
        df, df_metas
    )
    
    resumo['resumo_produtos_mix'] = _criar_resumo_produtos_mix(
        df, df_metas, dias_uteis_info
    )
    
    resumo['resumo_por_regiao'] = resumo['por_regiao']
    
    return resumo


def _criar_totais_gerais(df, df_metas, dias_uteis_info):
    """Cria tabela com totais gerais consolidados."""
    df_valido = df[df['VALOR'] > 0].copy()
    
    total_qtd = len(df_valido)
    total_valor = df_valido['VALOR'].sum()
    total_pontos = df_valido['pontos'].sum()
    
    if 'META_PRATA' in df_metas.columns:
        meta_total = pd.to_numeric(
            df_metas['META_PRATA'], errors='coerce'
        ).fillna(0).sum()
    elif 'PRATA LOJA' in df_metas.columns:
        meta_total = pd.to_numeric(
            df_metas['PRATA LOJA'], errors='coerce'
        ).fillna(0).sum()
    else:
        meta_total = 0
    
    atingimento = (total_pontos / meta_total * 100) if meta_total > 0 else 0
    
    ticket_medio = total_valor / total_qtd if total_qtd > 0 else 0
    
    du_decorridos = dias_uteis_info['decorridos']
    du_total = dias_uteis_info['total']
    du_restantes = dias_uteis_info['restantes']
    
    media_du_valor = total_valor / du_decorridos if du_decorridos > 0 else 0
    media_du_pontos = total_pontos / du_decorridos if du_decorridos > 0 else 0
    projecao_pontos = media_du_pontos * du_total if du_total > 0 else 0
    
    meta_diaria = meta_total / du_total if du_total > 0 else 0
    perc_atingimento = (total_pontos / meta_total * 100) if meta_total > 0 else 0
    perc_expectativa = (projecao_pontos / meta_total * 100) if meta_total > 0 else 0
    
    totais = pd.DataFrame([{
        'Métrica': 'Quantidade Total',
        'Valor': total_qtd
    }, {
        'Métrica': 'Valor Total (R$)',
        'Valor': total_valor
    }, {
        'Métrica': 'Pontos Totais',
        'Valor': total_pontos
    }, {
        'Métrica': 'Meta Total',
        'Valor': meta_total
    }, {
        'Métrica': 'Atingimento (%)',
        'Valor': perc_atingimento
    }, {
        'Métrica': 'Ticket Médio (R$)',
        'Valor': ticket_medio
    }, {
        'Métrica': 'Média por DU (R$)',
        'Valor': media_du_valor
    }, {
        'Métrica': 'Média por DU (Pontos)',
        'Valor': media_du_pontos
    }, {
        'Métrica': 'Projeção (Pontos)',
        'Valor': projecao_pontos
    }, {
        'Métrica': 'Expectativa (%)',
        'Valor': perc_expectativa
    }, {
        'Métrica': 'Meta Diária',
        'Valor': meta_diaria
    }, {
        'Métrica': 'DU Decorridos',
        'Valor': du_decorridos
    }, {
        'Métrica': 'DU Restantes',
        'Valor': du_restantes
    }, {
        'Métrica': 'DU Total',
        'Valor': du_total
    }])
    
    return totais


def _criar_resumo_por_regiao(df, df_metas, dias_uteis_info):
    """Cria resumo consolidado por região."""
    df_valido = df[df['VALOR'] > 0].copy()
    
    if 'REGIAO' not in df_valido.columns:
        return pd.DataFrame()
    
    resumo_regiao = df_valido.groupby('REGIAO').agg({
        'VALOR': ['count', 'sum'],
        'pontos': 'sum'
    }).reset_index()
    
    resumo_regiao.columns = ['Região', 'Qtd', 'Valor', 'Pontos']
    
    if 'REGIAO' in df_metas.columns and 'META_PRATA' in df_metas.columns:
        metas_regiao = df_metas.groupby('REGIAO').agg({
            'META_PRATA': lambda x: pd.to_numeric(x, errors='coerce').fillna(0).sum()
        }).reset_index()
        metas_regiao.columns = ['Região', 'Meta']
    else:
        metas_regiao = pd.DataFrame(columns=['Região', 'Meta'])
    
    resumo_regiao = resumo_regiao.merge(metas_regiao, on='Região', how='left')
    resumo_regiao['Meta'] = resumo_regiao['Meta'].fillna(0)
    
    resumo_regiao['Atingimento %'] = (
        resumo_regiao['Pontos'] / resumo_regiao['Meta'] * 100
    ).where(resumo_regiao['Meta'] > 0, 0)
    
    resumo_regiao['Ticket Médio'] = (
        resumo_regiao['Valor'] / resumo_regiao['Qtd']
    ).where(resumo_regiao['Qtd'] > 0, 0)
    
    du_decorridos = dias_uteis_info['decorridos']
    resumo_regiao['Média DU'] = (
        resumo_regiao['Valor'] / du_decorridos
    ) if du_decorridos > 0 else 0
    
    resumo_regiao = resumo_regiao.sort_values('Pontos', ascending=False)
    
    return resumo_regiao


def _criar_top_lojas(df, top_n=10):
    """Cria ranking das top N lojas por pontos."""
    df_valido = df[df['VALOR'] > 0].copy()
    
    top_lojas = df_valido.groupby('LOJA').agg({
        'VALOR': ['count', 'sum'],
        'pontos': 'sum'
    }).reset_index()
    
    top_lojas.columns = ['Loja', 'Qtd', 'Valor', 'Pontos']
    
    top_lojas['Ticket Médio'] = (
        top_lojas['Valor'] / top_lojas['Qtd']
    ).where(top_lojas['Qtd'] > 0, 0)
    
    top_lojas = top_lojas.sort_values('Pontos', ascending=False).head(top_n)
    top_lojas.insert(0, 'Posição', range(1, len(top_lojas) + 1))
    
    return top_lojas


def _criar_top_lojas_ticket_medio(df, top_n=10):
    """Cria ranking das top N lojas por ticket médio."""
    df_valido = df[df['VALOR'] > 0].copy()
    
    top_lojas = df_valido.groupby('LOJA').agg({
        'VALOR': ['count', 'sum'],
        'pontos': 'sum'
    }).reset_index()
    
    top_lojas.columns = ['Loja', 'Qtd', 'Valor', 'Pontos']
    
    top_lojas['Ticket Médio'] = (
        top_lojas['Valor'] / top_lojas['Qtd']
    ).where(top_lojas['Qtd'] > 0, 0)
    
    top_lojas = top_lojas.sort_values('Ticket Médio', ascending=False).head(top_n)
    top_lojas.insert(0, 'Posição', range(1, len(top_lojas) + 1))
    
    return top_lojas


def _criar_top_lojas_media_du(df, dias_uteis_info, top_n=10):
    """Cria ranking das top N lojas por média DU."""
    df_valido = df[df['VALOR'] > 0].copy()
    
    top_lojas = df_valido.groupby('LOJA').agg({
        'VALOR': ['count', 'sum'],
        'pontos': 'sum'
    }).reset_index()
    
    top_lojas.columns = ['Loja', 'Qtd', 'Valor', 'Pontos']
    
    du_decorridos = dias_uteis_info['decorridos']
    top_lojas['Média DU'] = (
        top_lojas['Valor'] / du_decorridos
    ) if du_decorridos > 0 else 0
    
    top_lojas['Ticket Médio'] = (
        top_lojas['Valor'] / top_lojas['Qtd']
    ).where(top_lojas['Qtd'] > 0, 0)
    
    top_lojas = top_lojas.sort_values('Média DU', ascending=False).head(top_n)
    top_lojas.insert(0, 'Posição', range(1, len(top_lojas) + 1))
    
    return top_lojas


def _criar_top_lojas_por_produto(df, dias_uteis_info, top_n=10):
    """Cria ranking das top N lojas por cada produto do MIX."""
    mapeamento_produtos = {
        'CNC': ['CNC'],
        'SAQUE': ['SAQUE', 'SAQUE BENEFICIO'],
        'CLT': ['CONSIG PRIV'],
        'CONSIGNADO': ['CONSIG', 'Portabilidade'],
        'PACK': ['FGTS', 'CNC 13º']
    }
    
    rankings = {}
    
    for produto_mix, tipos in mapeamento_produtos.items():
        df_produto = df[
            (df['TIPO_PRODUTO'].isin(tipos)) & (df['VALOR'] > 0)
        ].copy()
        
        if len(df_produto) == 0:
            continue
        
        ranking = df_produto.groupby('LOJA').agg({
            'VALOR': ['count', 'sum'],
            'pontos': 'sum'
        }).reset_index()
        
        ranking.columns = ['Loja', 'Qtd', 'Valor', 'Pontos']
        
        ranking['Ticket Médio'] = (
            ranking['Valor'] / ranking['Qtd']
        ).where(ranking['Qtd'] > 0, 0)
        
        du_decorridos = dias_uteis_info['decorridos']
        ranking['Média DU'] = (
            ranking['Valor'] / du_decorridos
        ) if du_decorridos > 0 else 0
        
        ranking = ranking.sort_values('Pontos', ascending=False).head(top_n)
        ranking.insert(0, 'Posição', range(1, len(ranking) + 1))
        
        rankings[produto_mix] = ranking
    
    return rankings


def _criar_top_lojas_atingimento(df, df_metas, top_n=10):
    """Cria ranking das top N lojas por atingimento de meta prata."""
    df_valido = df[df['VALOR'] > 0].copy()
    
    if 'LOJA' not in df_valido.columns:
        return pd.DataFrame()
    
    top_lojas = df_valido.groupby('LOJA', as_index=False).agg({
        'VALOR': ['count', 'sum'],
        'pontos': 'sum'
    })
    
    top_lojas.columns = ['Loja', 'Qtd', 'Valor', 'Pontos']
    
    if 'LOJA' in df_metas.columns and 'META_PRATA' in df_metas.columns:
        metas_loja = df_metas[['LOJA', 'META_PRATA']].copy()
        metas_loja['Meta Prata'] = pd.to_numeric(
            metas_loja['META_PRATA'], errors='coerce'
        ).fillna(0)
        
        top_lojas = top_lojas.merge(
            metas_loja[['LOJA', 'Meta Prata']],
            left_on='Loja',
            right_on='LOJA',
            how='left'
        )
        top_lojas = top_lojas.drop('LOJA', axis=1)
        top_lojas['Meta Prata'] = top_lojas['Meta Prata'].fillna(0)
    else:
        top_lojas['Meta Prata'] = 0
    
    top_lojas['Atingimento %'] = (
        top_lojas['Pontos'] / top_lojas['Meta Prata'] * 100
    ).where(top_lojas['Meta Prata'] > 0, 0)
    
    top_lojas['Ticket Médio'] = (
        top_lojas['Valor'] / top_lojas['Qtd']
    ).where(top_lojas['Qtd'] > 0, 0)
    
    top_lojas = top_lojas[
        ['Loja', 'Qtd', 'Valor', 'Pontos', 'Meta Prata',
         'Atingimento %', 'Ticket Médio']
    ]
    
    top_lojas = top_lojas.sort_values('Atingimento %', ascending=False).head(top_n)
    top_lojas.insert(0, 'Posição', range(1, len(top_lojas) + 1))
    
    return top_lojas


def _criar_top_consultores(df, df_supervisores=None, top_n=10):
    """Cria ranking dos top N consultores por pontos."""
    df_valido = df[df['VALOR'] > 0].copy()
    
    if df_supervisores is not None and 'SUPERVISOR' in df_supervisores.columns:
        lista_supervisores = df_supervisores['SUPERVISOR'].dropna().unique().tolist()
        df_valido = df_valido[~df_valido['CONSULTOR'].isin(lista_supervisores)]
    
    top_consultores = df_valido.groupby('CONSULTOR').agg({
        'VALOR': ['count', 'sum'],
        'pontos': 'sum',
        'LOJA': 'first'
    }).reset_index()
    
    top_consultores.columns = ['Consultor', 'Qtd', 'Valor', 'Pontos', 'Loja']
    
    top_consultores['Ticket Médio'] = (
        top_consultores['Valor'] / top_consultores['Qtd']
    ).where(top_consultores['Qtd'] > 0, 0)
    
    top_consultores = top_consultores[
        ['Consultor', 'Loja', 'Qtd', 'Valor', 'Pontos', 'Ticket Médio']
    ]
    
    top_consultores = top_consultores.sort_values(
        'Pontos', ascending=False
    ).head(top_n)
    top_consultores.insert(0, 'Posição', range(1, len(top_consultores) + 1))
    
    return top_consultores


def _criar_top_consultores_ticket_medio(df, df_supervisores=None, top_n=10):
    """Cria ranking dos top N consultores por ticket médio."""
    df_valido = df[df['VALOR'] > 0].copy()
    
    if df_supervisores is not None and 'SUPERVISOR' in df_supervisores.columns:
        lista_supervisores = df_supervisores['SUPERVISOR'].dropna().unique().tolist()
        df_valido = df_valido[~df_valido['CONSULTOR'].isin(lista_supervisores)]
    
    top_consultores = df_valido.groupby('CONSULTOR').agg({
        'VALOR': ['count', 'sum'],
        'pontos': 'sum',
        'LOJA': 'first'
    }).reset_index()
    
    top_consultores.columns = ['Consultor', 'Qtd', 'Valor', 'Pontos', 'Loja']
    
    top_consultores['Ticket Médio'] = (
        top_consultores['Valor'] / top_consultores['Qtd']
    ).where(top_consultores['Qtd'] > 0, 0)
    
    top_consultores = top_consultores[
        ['Consultor', 'Loja', 'Qtd', 'Valor', 'Pontos', 'Ticket Médio']
    ]
    
    top_consultores = top_consultores.sort_values(
        'Ticket Médio', ascending=False
    ).head(top_n)
    top_consultores.insert(0, 'Posição', range(1, len(top_consultores) + 1))
    
    return top_consultores


def _criar_top_consultores_media_du(df, df_supervisores, dias_uteis_info, top_n=10):
    """Cria ranking dos top N consultores por média DU."""
    df_valido = df[df['VALOR'] > 0].copy()
    
    if df_supervisores is not None and 'SUPERVISOR' in df_supervisores.columns:
        lista_supervisores = df_supervisores['SUPERVISOR'].dropna().unique().tolist()
        df_valido = df_valido[~df_valido['CONSULTOR'].isin(lista_supervisores)]
    
    top_consultores = df_valido.groupby('CONSULTOR').agg({
        'VALOR': ['count', 'sum'],
        'pontos': 'sum',
        'LOJA': 'first'
    }).reset_index()
    
    top_consultores.columns = ['Consultor', 'Qtd', 'Valor', 'Pontos', 'Loja']
    
    du_decorridos = dias_uteis_info['decorridos']
    top_consultores['Média DU'] = (
        top_consultores['Valor'] / du_decorridos
    ) if du_decorridos > 0 else 0
    
    top_consultores['Ticket Médio'] = (
        top_consultores['Valor'] / top_consultores['Qtd']
    ).where(top_consultores['Qtd'] > 0, 0)
    
    top_consultores = top_consultores[
        ['Consultor', 'Loja', 'Qtd', 'Valor', 'Pontos', 'Média DU', 'Ticket Médio']
    ]
    
    top_consultores = top_consultores.sort_values(
        'Média DU', ascending=False
    ).head(top_n)
    top_consultores.insert(0, 'Posição', range(1, len(top_consultores) + 1))
    
    return top_consultores


def _criar_top_consultores_por_produto(df, df_supervisores, dias_uteis_info, top_n=10):
    """Cria ranking dos top N consultores por cada produto do MIX."""
    mapeamento_produtos = {
        'CNC': ['CNC'],
        'SAQUE': ['SAQUE', 'SAQUE BENEFICIO'],
        'CLT': ['CONSIG PRIV'],
        'CONSIGNADO': ['CONSIG', 'Portabilidade'],
        'PACK': ['FGTS', 'CNC 13º']
    }
    
    rankings = {}
    
    for produto_mix, tipos in mapeamento_produtos.items():
        df_produto = df[
            (df['TIPO_PRODUTO'].isin(tipos)) & (df['VALOR'] > 0)
        ].copy()
        
        if len(df_produto) == 0:
            continue
        
        if df_supervisores is not None and 'SUPERVISOR' in df_supervisores.columns:
            lista_supervisores = df_supervisores['SUPERVISOR'].dropna().unique().tolist()
            df_produto = df_produto[~df_produto['CONSULTOR'].isin(lista_supervisores)]
        
        ranking = df_produto.groupby('CONSULTOR').agg({
            'VALOR': ['count', 'sum'],
            'pontos': 'sum',
            'LOJA': 'first'
        }).reset_index()
        
        ranking.columns = ['Consultor', 'Qtd', 'Valor', 'Pontos', 'Loja']
        
        ranking['Ticket Médio'] = (
            ranking['Valor'] / ranking['Qtd']
        ).where(ranking['Qtd'] > 0, 0)
        
        du_decorridos = dias_uteis_info['decorridos']
        ranking['Média DU'] = (
            ranking['Valor'] / du_decorridos
        ) if du_decorridos > 0 else 0
        
        ranking = ranking[
            ['Consultor', 'Loja', 'Qtd', 'Valor', 'Pontos', 'Ticket Médio', 'Média DU']
        ]
        
        ranking = ranking.sort_values(
            'Pontos', ascending=False
        ).head(top_n)
        ranking.insert(0, 'Posição', range(1, len(ranking) + 1))
        
        rankings[produto_mix] = ranking
    
    return rankings


def _criar_top_consultores_atingimento(df, df_metas, df_supervisores=None, top_n=10):
    """Cria ranking dos top N consultores por atingimento de meta prata."""
    df_valido = df[df['VALOR'] > 0].copy()
    
    if df_supervisores is not None and 'SUPERVISOR' in df_supervisores.columns:
        lista_supervisores = df_supervisores['SUPERVISOR'].dropna().unique().tolist()
        df_valido = df_valido[~df_valido['CONSULTOR'].isin(lista_supervisores)]
    
    if 'CONSULTOR' not in df_valido.columns:
        return pd.DataFrame()
    
    top_consultores = df_valido.groupby('CONSULTOR', as_index=False).agg({
        'VALOR': ['count', 'sum'],
        'pontos': 'sum',
        'LOJA': 'first'
    })
    
    top_consultores.columns = ['Consultor', 'Qtd', 'Valor', 'Pontos', 'Loja']
    
    if 'LOJA' in df_metas.columns and 'META_PRATA' in df_metas.columns:
        metas_loja = df_metas[['LOJA', 'META_PRATA']].copy()
        metas_loja['Meta Prata Loja'] = pd.to_numeric(
            metas_loja['META_PRATA'], errors='coerce'
        ).fillna(0)
        
        consultores_por_loja = df_valido.groupby('LOJA')['CONSULTOR'].nunique().reset_index()
        consultores_por_loja.columns = ['LOJA', 'Num_Consultores']
        
        metas_loja = metas_loja.merge(consultores_por_loja, on='LOJA', how='left')
        metas_loja['Num_Consultores'] = metas_loja['Num_Consultores'].fillna(1)
        metas_loja['Meta Prata'] = (
            metas_loja['Meta Prata Loja'] / metas_loja['Num_Consultores']
        )
        
        top_consultores = top_consultores.merge(
            metas_loja[['LOJA', 'Meta Prata']],
            left_on='Loja',
            right_on='LOJA',
            how='left'
        )
        top_consultores = top_consultores.drop('LOJA', axis=1)
        top_consultores['Meta Prata'] = top_consultores['Meta Prata'].fillna(0)
    else:
        top_consultores['Meta Prata'] = 0
    
    top_consultores['Atingimento %'] = (
        top_consultores['Pontos'] / top_consultores['Meta Prata'] * 100
    ).where(top_consultores['Meta Prata'] > 0, 0)
    
    top_consultores['Ticket Médio'] = (
        top_consultores['Valor'] / top_consultores['Qtd']
    ).where(top_consultores['Qtd'] > 0, 0)
    
    top_consultores = top_consultores[
        ['Consultor', 'Loja', 'Qtd', 'Valor', 'Pontos', 'Meta Prata',
         'Atingimento %', 'Ticket Médio']
    ]
    
    top_consultores = top_consultores.sort_values(
        'Atingimento %', ascending=False
    ).head(top_n)
    top_consultores.insert(0, 'Posição', range(1, len(top_consultores) + 1))
    
    return top_consultores


def _criar_ranking_regiao_pontos(df):
    """Cria ranking de regiões por pontos totais."""
    df_valido = df[df['VALOR'] > 0].copy()
    
    if 'REGIAO' not in df_valido.columns:
        return pd.DataFrame()
    
    ranking = df_valido.groupby('REGIAO').agg({
        'VALOR': ['count', 'sum'],
        'pontos': 'sum'
    }).reset_index()
    
    ranking.columns = ['Região', 'Qtd', 'Valor', 'Pontos']
    
    ranking['Ticket Médio'] = (
        ranking['Valor'] / ranking['Qtd']
    ).where(ranking['Qtd'] > 0, 0)
    
    ranking = ranking.sort_values('Pontos', ascending=False)
    ranking.insert(0, 'Posição', range(1, len(ranking) + 1))
    
    return ranking


def _criar_ranking_regiao_ticket_medio(df):
    """Cria ranking de regiões por ticket médio."""
    df_valido = df[df['VALOR'] > 0].copy()
    
    if 'REGIAO' not in df_valido.columns:
        return pd.DataFrame()
    
    ranking = df_valido.groupby('REGIAO').agg({
        'VALOR': ['count', 'sum'],
        'pontos': 'sum'
    }).reset_index()
    
    ranking.columns = ['Região', 'Qtd', 'Valor', 'Pontos']
    
    ranking['Ticket Médio'] = (
        ranking['Valor'] / ranking['Qtd']
    ).where(ranking['Qtd'] > 0, 0)
    
    ranking = ranking.sort_values('Ticket Médio', ascending=False)
    ranking.insert(0, 'Posição', range(1, len(ranking) + 1))
    
    return ranking


def _criar_ranking_regiao_media_du(df, dias_uteis_info):
    """Cria ranking de regiões por média DU."""
    df_valido = df[df['VALOR'] > 0].copy()
    
    if 'REGIAO' not in df_valido.columns:
        return pd.DataFrame()
    
    ranking = df_valido.groupby('REGIAO').agg({
        'VALOR': ['count', 'sum'],
        'pontos': 'sum'
    }).reset_index()
    
    ranking.columns = ['Região', 'Qtd', 'Valor', 'Pontos']
    
    du_decorridos = dias_uteis_info['decorridos']
    ranking['Média DU'] = (
        ranking['Valor'] / du_decorridos
    ) if du_decorridos > 0 else 0
    
    ranking['Ticket Médio'] = (
        ranking['Valor'] / ranking['Qtd']
    ).where(ranking['Qtd'] > 0, 0)
    
    ranking = ranking.sort_values('Média DU', ascending=False)
    ranking.insert(0, 'Posição', range(1, len(ranking) + 1))
    
    return ranking


def _criar_ranking_regiao_por_produto(df, dias_uteis_info):
    """Cria ranking de regiões por cada produto do MIX."""
    mapeamento_produtos = {
        'CNC': ['CNC'],
        'SAQUE': ['SAQUE', 'SAQUE BENEFICIO'],
        'CLT': ['CONSIG PRIV'],
        'CONSIGNADO': ['CONSIG', 'Portabilidade'],
        'PACK': ['FGTS', 'CNC 13º']
    }
    
    if 'REGIAO' not in df.columns:
        return {}
    
    rankings = {}
    
    for produto_mix, tipos in mapeamento_produtos.items():
        df_produto = df[
            (df['TIPO_PRODUTO'].isin(tipos)) & (df['VALOR'] > 0)
        ].copy()
        
        if len(df_produto) == 0:
            continue
        
        ranking = df_produto.groupby('REGIAO').agg({
            'VALOR': ['count', 'sum'],
            'pontos': 'sum'
        }).reset_index()
        
        ranking.columns = ['Região', 'Qtd', 'Valor', 'Pontos']
        
        ranking['Ticket Médio'] = (
            ranking['Valor'] / ranking['Qtd']
        ).where(ranking['Qtd'] > 0, 0)
        
        du_decorridos = dias_uteis_info['decorridos']
        ranking['Média DU'] = (
            ranking['Valor'] / du_decorridos
        ) if du_decorridos > 0 else 0
        
        ranking = ranking.sort_values('Pontos', ascending=False)
        ranking.insert(0, 'Posição', range(1, len(ranking) + 1))
        
        rankings[produto_mix] = ranking
    
    return rankings


def _criar_ranking_regiao_atingimento(df, df_metas):
    """Cria ranking de regiões por atingimento de meta."""
    df_valido = df[df['VALOR'] > 0].copy()
    
    if 'REGIAO' not in df_valido.columns:
        return pd.DataFrame()
    
    ranking = df_valido.groupby('REGIAO').agg({
        'VALOR': ['count', 'sum'],
        'pontos': 'sum'
    }).reset_index()
    
    ranking.columns = ['Região', 'Qtd', 'Valor', 'Pontos']
    
    if 'REGIAO' in df_metas.columns and 'META_PRATA' in df_metas.columns:
        metas_regiao = df_metas.groupby('REGIAO').agg({
            'META_PRATA': lambda x: pd.to_numeric(
                x, errors='coerce'
            ).fillna(0).sum()
        }).reset_index()
        metas_regiao.columns = ['Região', 'Meta Prata']
        
        ranking = ranking.merge(metas_regiao, on='Região', how='left')
        ranking['Meta Prata'] = ranking['Meta Prata'].fillna(0)
    else:
        ranking['Meta Prata'] = 0
    
    ranking['Atingimento %'] = (
        ranking['Pontos'] / ranking['Meta Prata'] * 100
    ).where(ranking['Meta Prata'] > 0, 0)
    
    ranking['Ticket Médio'] = (
        ranking['Valor'] / ranking['Qtd']
    ).where(ranking['Qtd'] > 0, 0)
    
    ranking = ranking.sort_values('Atingimento %', ascending=False)
    ranking.insert(0, 'Posição', range(1, len(ranking) + 1))
    
    return ranking


def _criar_resumo_produtos_mix(df, df_metas, dias_uteis_info):
    """Cria resumo consolidado por produto do MIX."""
    mapeamento_produtos = {
        'CNC': ['CNC'],
        'SAQUE': ['SAQUE', 'SAQUE BENEFICIO'],
        'CLT': ['CONSIG PRIV'],
        'CONSIGNADO': ['CONSIG', 'Portabilidade'],
        'PACK': ['FGTS', 'CNC 13º']
    }
    
    resumo_produtos = []
    
    for produto_mix, tipos in mapeamento_produtos.items():
        df_produto = df[
            (df['TIPO_PRODUTO'].isin(tipos)) & (df['VALOR'] > 0)
        ].copy()
        
        if len(df_produto) == 0:
            resumo_produtos.append({
                'Produto': produto_mix,
                'Qtd': 0,
                'Valor': 0,
                'Pontos': 0,
                'Meta': 0,
                'Atingimento %': 0,
                'Ticket Médio': 0,
                'Média DU': 0
            })
            continue
        
        qtd = len(df_produto)
        valor = df_produto['VALOR'].sum()
        pontos = df_produto['pontos'].sum()
        
        ticket_medio = valor / qtd if qtd > 0 else 0
        
        du_decorridos = dias_uteis_info['decorridos']
        media_du = valor / du_decorridos if du_decorridos > 0 else 0
        
        meta = 0
        atingimento = 0
        
        resumo_produtos.append({
            'Produto': produto_mix,
            'Qtd': qtd,
            'Valor': valor,
            'Pontos': pontos,
            'Meta': meta,
            'Atingimento %': atingimento,
            'Ticket Médio': ticket_medio,
            'Média DU': media_du
        })
    
    return pd.DataFrame(resumo_produtos)
