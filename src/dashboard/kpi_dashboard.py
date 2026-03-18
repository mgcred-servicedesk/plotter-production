"""
Módulo centralizado de cálculos de KPIs para o dashboard Streamlit.
Integra todos os cálculos dos relatórios Excel e PDF.
"""
import pandas as pd
from typing import Dict, Tuple, Optional
from src.reports.tabela_produtos import calcular_dias_uteis


def calcular_kpis_gerais(
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    ano: int,
    mes: int,
    dia_atual: Optional[int] = None
) -> Dict:
    """
    Calcula KPIs gerais do dashboard.
    
    Args:
        df: DataFrame consolidado
        df_metas: DataFrame de metas
        ano: Ano de referência
        mes: Mês de referência
        dia_atual: Dia atual para cálculo de projeções
    
    Returns:
        Dicionário com KPIs gerais
    """
    du_total, du_decorridos, du_restantes = calcular_dias_uteis(
        ano, mes, dia_atual
    )
    
    total_vendas = df['VALOR'].sum()
    total_pontos = df['pontos'].sum()
    total_transacoes = len(df)
    
    meta_prata = 0
    meta_ouro = 0
    if 'META_PRATA' in df_metas.columns:
        meta_prata = pd.to_numeric(
            df_metas['META_PRATA'], errors='coerce'
        ).fillna(0).sum()
    if 'META_OURO' in df_metas.columns:
        meta_ouro = pd.to_numeric(
            df_metas['META_OURO'], errors='coerce'
        ).fillna(0).sum()
    
    perc_ating_prata = (
        (total_pontos / meta_prata * 100) if meta_prata > 0 else 0
    )
    perc_ating_ouro = (
        (total_pontos / meta_ouro * 100) if meta_ouro > 0 else 0
    )
    
    media_du = total_vendas / du_decorridos if du_decorridos > 0 else 0
    media_du_pontos = total_pontos / du_decorridos if du_decorridos > 0 else 0
    meta_diaria = meta_prata / du_total if du_total > 0 else 0
    projecao = media_du * du_total
    projecao_pontos = media_du_pontos * du_total
    perc_proj = (projecao_pontos / meta_prata * 100) if meta_prata > 0 else 0
    
    ticket_medio = total_vendas / total_transacoes if total_transacoes > 0 else 0
    
    return {
        'total_vendas': total_vendas,
        'total_pontos': total_pontos,
        'total_transacoes': total_transacoes,
        'meta_prata': meta_prata,
        'meta_ouro': meta_ouro,
        'meta_diaria': meta_diaria,
        'perc_ating_prata': perc_ating_prata,
        'perc_ating_ouro': perc_ating_ouro,
        'media_du': media_du,
        'media_du_pontos': media_du_pontos,
        'projecao': projecao,
        'projecao_pontos': projecao_pontos,
        'perc_proj': perc_proj,
        'ticket_medio': ticket_medio,
        'du_total': du_total,
        'du_decorridos': du_decorridos,
        'du_restantes': du_restantes,
        'num_lojas': df['LOJA'].nunique() if 'LOJA' in df.columns else 0,
        'num_consultores': (
            df['CONSULTOR'].nunique() if 'CONSULTOR' in df.columns else 0
        ),
        'num_regioes': (
            df['REGIAO'].nunique() if 'REGIAO' in df.columns else 0
        )
    }


def calcular_kpis_por_produto(
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    ano: int,
    mes: int,
    dia_atual: Optional[int] = None
) -> pd.DataFrame:
    """
    Calcula KPIs detalhados por produto.
    
    Returns:
        DataFrame com KPIs por produto
    """
    du_total, du_decorridos, du_restantes = calcular_dias_uteis(
        ano, mes, dia_atual
    )
    
    mapeamento_produtos = {
        'CNC': ['CNC'],
        'SAQUE': ['SAQUE', 'SAQUE BENEFICIO'],
        'CLT': ['CONSIG PRIV'],
        'CONSIGNADO': ['CONSIG', 'Portabilidade'],
        'PACK': ['FGTS', 'CNC 13º']
    }
    
    mapeamento_colunas_meta = {
        'CNC': 'CNC LOJA',
        'SAQUE': 'SAQUE LOJA',
        'CLT': 'CLT',
        'CONSIGNADO': 'CONSIGNADO',
        'PACK': 'META  LOJA FGTS & ANT. BEN.13º'
    }
    
    produtos_emissao = ['EMISSAO', 'EMISSAO CC', 'EMISSAO CB']
    
    dados_produtos = []
    
    for produto_nome, tipos in mapeamento_produtos.items():
        df_produto = df[df['TIPO_PRODUTO'].isin(tipos)].copy()
        
        mask_emissao = df_produto['TIPO_PRODUTO'].isin(produtos_emissao)
        df_produto.loc[mask_emissao, 'VALOR'] = 0
        
        valor = df_produto['VALOR'].sum()
        quantidade = len(df_produto)
        
        coluna_meta = mapeamento_colunas_meta.get(
            produto_nome, f'{produto_nome} LOJA'
        )
        meta_total = 0
        if coluna_meta in df_metas.columns:
            meta_total = pd.to_numeric(
                df_metas[coluna_meta], errors='coerce'
            ).fillna(0).sum()
        
        perc_ating = (valor / meta_total * 100) if meta_total > 0 else 0
        media_du = valor / du_decorridos if du_decorridos > 0 else 0
        meta_diaria = meta_total / du_total if du_total > 0 else 0
        ticket_medio = valor / quantidade if quantidade > 0 else 0
        projecao = media_du * du_total
        perc_proj = (projecao / meta_total * 100) if meta_total > 0 else 0
        
        dados_produtos.append({
            'Produto': produto_nome,
            'Valor': valor,
            'Meta': meta_total,
            'Meta Diária': meta_diaria,
            '% Atingimento': perc_ating,
            'Quantidade': quantidade,
            'Ticket Médio': ticket_medio,
            'Média DU': media_du,
            'Projeção': projecao,
            '% Projeção': perc_proj
        })
    
    return pd.DataFrame(dados_produtos)


def calcular_kpis_por_regiao(
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    ano: int,
    mes: int,
    dia_atual: Optional[int] = None
) -> pd.DataFrame:
    """
    Calcula KPIs por região.
    
    Returns:
        DataFrame com KPIs por região
    """
    if 'REGIAO' not in df.columns:
        return pd.DataFrame()
    
    du_total, du_decorridos, du_restantes = calcular_dias_uteis(
        ano, mes, dia_atual
    )
    
    regioes = sorted(df['REGIAO'].unique())
    dados_regioes = []
    
    for regiao in regioes:
        df_regiao = df[df['REGIAO'] == regiao]
        
        valor_total = df_regiao['VALOR'].sum()
        pontos_total = df_regiao['pontos'].sum()
        num_lojas = df_regiao['LOJA'].nunique()
        num_consultores = df_regiao['CONSULTOR'].nunique()
        
        meta_prata_regiao = 0
        if 'META_PRATA' in df_metas.columns:
            lojas_regiao = df_regiao['LOJA'].unique()
            meta_prata_regiao = df_metas[
                df_metas['LOJA'].isin(lojas_regiao)
            ]['META_PRATA'].sum()
        
        perc_ating = (
            (pontos_total / meta_prata_regiao * 100)
            if meta_prata_regiao > 0 else 0
        )
        media_du = valor_total / du_decorridos if du_decorridos > 0 else 0
        projecao = media_du * du_total
        
        dados_regioes.append({
            'Região': regiao,
            'Valor': valor_total,
            'Pontos': pontos_total,
            'Meta Prata': meta_prata_regiao,
            '% Atingimento': perc_ating,
            'Nº Lojas': num_lojas,
            'Nº Consultores': num_consultores,
            'Média DU': media_du,
            'Projeção': projecao
        })
    
    return pd.DataFrame(dados_regioes)


def calcular_ranking_lojas_atingimento(
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    top_n: int = 10
) -> pd.DataFrame:
    """
    Cria ranking de lojas por % de atingimento de meta prata.
    
    Returns:
        DataFrame com ranking de lojas
    """
    df_valido = df[df['VALOR'] > 0].copy()
    
    if 'LOJA' not in df_metas.columns:
        return pd.DataFrame()
    
    ranking = df_valido.groupby('LOJA').agg({
        'VALOR': ['count', 'sum'],
        'pontos': 'sum'
    }).reset_index()
    
    ranking.columns = ['Loja', 'Qtd', 'Valor', 'Pontos']
    
    if 'REGIAO' in df.columns:
        df_regiao = df[['LOJA', 'REGIAO']].drop_duplicates()
        ranking = ranking.merge(df_regiao, left_on='Loja', right_on='LOJA')
        ranking = ranking.drop('LOJA', axis=1)
    
    metas_loja = df_metas.set_index('LOJA')
    if 'META_PRATA' in metas_loja.columns:
        ranking = ranking.merge(
            metas_loja[['META_PRATA']].reset_index(),
            left_on='Loja',
            right_on='LOJA',
            how='left'
        )
        ranking['Meta Prata'] = ranking['META_PRATA'].fillna(0)
        ranking = ranking.drop(['LOJA', 'META_PRATA'], axis=1)
    else:
        ranking['Meta Prata'] = 0
    
    ranking['Atingimento %'] = (
        ranking['Pontos'] / ranking['Meta Prata'] * 100
    ).where(ranking['Meta Prata'] > 0, 0)
    
    ranking['Ticket Médio'] = (
        ranking['Valor'] / ranking['Qtd']
    ).where(ranking['Qtd'] > 0, 0)
    
    ranking = ranking.sort_values('Atingimento %', ascending=False).head(top_n)
    ranking.insert(0, 'Posição', range(1, len(ranking) + 1))
    
    return ranking


def calcular_ranking_consultores_atingimento(
    df: pd.DataFrame,
    df_metas: pd.DataFrame,
    top_n: int = 10
) -> pd.DataFrame:
    """
    Cria ranking de consultores por % de atingimento de meta prata.
    
    Returns:
        DataFrame com ranking de consultores
    """
    df_valido = df[df['VALOR'] > 0].copy()
    
    if 'CONSULTOR' not in df.columns:
        return pd.DataFrame()
    
    ranking = df_valido.groupby('CONSULTOR').agg({
        'VALOR': ['count', 'sum'],
        'pontos': 'sum',
        'LOJA': 'first'
    }).reset_index()
    
    ranking.columns = ['Consultor', 'Qtd', 'Valor', 'Pontos', 'Loja']
    
    if 'LOJA' in df_metas.columns and 'META_PRATA' in df_metas.columns:
        metas_loja = df_metas.set_index('LOJA')['META_PRATA']
        
        num_consultores_loja = df_valido.groupby('LOJA')[
            'CONSULTOR'
        ].nunique()
        
        ranking['Meta Prata'] = ranking['Loja'].map(
            lambda x: (
                metas_loja.get(x, 0) / num_consultores_loja.get(x, 1)
                if x in num_consultores_loja.index else 0
            )
        )
    else:
        ranking['Meta Prata'] = 0
    
    ranking['Atingimento %'] = (
        ranking['Pontos'] / ranking['Meta Prata'] * 100
    ).where(ranking['Meta Prata'] > 0, 0)
    
    ranking['Ticket Médio'] = (
        ranking['Valor'] / ranking['Qtd']
    ).where(ranking['Qtd'] > 0, 0)
    
    ranking = ranking.sort_values('Atingimento %', ascending=False).head(top_n)
    ranking.insert(0, 'Posição', range(1, len(ranking) + 1))
    
    return ranking


def calcular_evolucao_diaria(
    df: pd.DataFrame,
    ano: int,
    mes: int
) -> pd.DataFrame:
    """
    Calcula evolução diária de vendas e pontos.
    
    Returns:
        DataFrame com evolução diária
    """
    if 'DATA' not in df.columns:
        return pd.DataFrame()
    
    df_temp = df.copy()
    df_temp['DATA_DIA'] = pd.to_datetime(df_temp['DATA']).dt.date
    
    evolucao = df_temp.groupby('DATA_DIA').agg({
        'VALOR': 'sum',
        'pontos': 'sum'
    }).reset_index()
    
    evolucao = evolucao.rename(columns={'DATA_DIA': 'DATA'})
    evolucao['DATA'] = pd.to_datetime(evolucao['DATA'])
    evolucao = evolucao.sort_values('DATA')
    
    evolucao['Valor Acumulado'] = evolucao['VALOR'].cumsum()
    evolucao['Pontos Acumulados'] = evolucao['pontos'].cumsum()
    
    return evolucao
