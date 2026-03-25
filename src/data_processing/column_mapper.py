"""
Módulo para mapeamento de colunas dos arquivos reais para o padrão do sistema.
"""
import pandas as pd
from typing import Dict, Optional


MAPEAMENTO_DIGITACAO = {
    'VENDEDOR': 'CONSULTOR',
    'FILIAL': 'LOJA',
    'VLR BASE': 'VALOR',
    'TABELA': 'PRODUTO',
    'DATA STATUS PAGAMENTO CLIENTE': 'DATA',
    'DATA CAD.': 'DATA_CADASTRO',
    'TIPO OPER.': 'TIPO OPER.'
}

MAPEAMENTO_METAS = {
    'LOJA': 'LOJA',
    'PRATA LOJA': 'META_PRATA',
    'OURO LOJA': 'META_OURO',
    'PRATA CONSULTOR': 'PRATA CONSULTOR',
    'OURO CONSULTOR': 'OURO CONSULTOR',
    'CONSULTOR': 'CONSULTOR',
    'REGIÃO': 'REGIAO',
    'PERIFL': 'PERFIL'
}

MAPEAMENTO_TABELAS = {
    'TABELA': 'PRODUTO',
    'PTS': 'PTS',
    'SUBTIPO': 'SUBTIPO',
    'TIPO': 'TIPO_PRODUTO',
    'PRODUTO PTS': 'PRODUTO_PTS'
}

MAPEAMENTO_HC = {
    'VENDEDOR': 'CONSULTOR',
    'FILIAL': 'LOJA',
    'STATUS': 'STATUS'
}

MAPEAMENTO_LOJA_REGIAO = {
    'LOJA': 'LOJA',
    'REGIÃO': 'REGIAO',
    'GERENTE': 'GERENTE'
}


def mapear_colunas(
    df: pd.DataFrame,
    mapeamento: Dict[str, str],
    manter_originais: bool = False
) -> pd.DataFrame:
    """
    Mapeia colunas de um DataFrame conforme dicionário de mapeamento.
    
    Args:
        df: DataFrame a ser mapeado.
        mapeamento: Dicionário {nome_original: nome_novo}.
        manter_originais: Se True, mantém colunas originais além das mapeadas.
    
    Returns:
        DataFrame com colunas mapeadas.
    """
    df_mapped = df.copy()
    
    colunas_para_renomear = {}
    for col_original, col_nova in mapeamento.items():
        if col_original in df_mapped.columns:
            colunas_para_renomear[col_original] = col_nova
    
    if manter_originais:
        for col_original, col_nova in colunas_para_renomear.items():
            df_mapped[col_nova] = df_mapped[col_original]
    else:
        df_mapped = df_mapped.rename(columns=colunas_para_renomear)
    
    return df_mapped


def higienizar_vendedor(vendedor: str) -> str:
    """
    Remove código antes do "-" no campo VENDEDOR.
    
    Exemplo: "3771 - YASMIM VELASCO DA SILVA" -> "YASMIM VELASCO DA SILVA"
    
    Args:
        vendedor: String com código e nome do vendedor.
    
    Returns:
        Nome do vendedor sem o código.
    """
    if pd.isna(vendedor):
        return ''
    
    vendedor_str = str(vendedor).strip()
    
    if ' - ' in vendedor_str:
        partes = vendedor_str.split(' - ', 1)
        return partes[1].strip()
    
    return vendedor_str


def mapear_digitacao(df: pd.DataFrame) -> pd.DataFrame:
    """
    Mapeia colunas do arquivo de digitação.
    
    Args:
        df: DataFrame de digitação bruto.
    
    Returns:
        DataFrame com colunas mapeadas.
    """
    df_mapped = mapear_colunas(df, MAPEAMENTO_DIGITACAO, manter_originais=False)
    
    if 'CONSULTOR' in df_mapped.columns:
        df_mapped['CONSULTOR'] = df_mapped['CONSULTOR'].apply(higienizar_vendedor)
    
    return df_mapped


def mapear_metas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Mapeia colunas do arquivo de metas.
    
    Args:
        df: DataFrame de metas bruto.
    
    Returns:
        DataFrame com colunas mapeadas.
    """
    return mapear_colunas(df, MAPEAMENTO_METAS, manter_originais=True)


def mapear_tabelas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Mapeia colunas do arquivo de tabelas de produtos.
    
    Args:
        df: DataFrame de tabelas bruto.
    
    Returns:
        DataFrame com colunas mapeadas.
    """
    return mapear_colunas(df, MAPEAMENTO_TABELAS, manter_originais=False)


def mapear_hc(df: pd.DataFrame) -> pd.DataFrame:
    """
    Mapeia colunas do arquivo de HC.
    
    Args:
        df: DataFrame de HC bruto.
    
    Returns:
        DataFrame com colunas mapeadas.
    """
    return mapear_colunas(df, MAPEAMENTO_HC, manter_originais=False)


def mapear_loja_regiao(df: pd.DataFrame) -> pd.DataFrame:
    """
    Mapeia colunas da planilha de configuração loja-região.
    
    Args:
        df: DataFrame com dados de loja-região.
    
    Returns:
        DataFrame com colunas mapeadas.
    """
    df = df.copy()
    
    if 'REGIÃO' in df.columns:
        df = df.rename(columns={'REGIÃO': 'REGIAO'})
    
    colunas_necessarias = ['LOJA', 'REGIAO']
    for col in colunas_necessarias:
        if col not in df.columns:
            raise ValueError(f"Coluna '{col}' não encontrada no DataFrame")
    
    return df[colunas_necessarias]


def mapear_supervisores(df: pd.DataFrame) -> pd.DataFrame:
    """
    Mapeia colunas da planilha de supervisores.
    
    Args:
        df: DataFrame com dados de supervisores.
    
    Returns:
        DataFrame com colunas mapeadas (LOJA, SUPERVISOR).
    """
    df = df.copy()
    
    mapeamento = {
        'LOJA': 'LOJA',
        'SUPERVISOR': 'SUPERVISOR'
    }
    
    colunas_disponiveis = df.columns.tolist()
    colunas_mapeadas = {}
    
    for col_original, col_destino in mapeamento.items():
        if col_original in colunas_disponiveis:
            colunas_mapeadas[col_original] = col_destino
    
    if not colunas_mapeadas:
        raise ValueError("Nenhuma coluna esperada encontrada no DataFrame de supervisores")
    
    df_mapeado = df[list(colunas_mapeadas.keys())].copy()
    df_mapeado.columns = list(colunas_mapeadas.values())
    
    if 'SUPERVISOR' in df_mapeado.columns:
        df_mapeado['SUPERVISOR'] = df_mapeado['SUPERVISOR'].apply(higienizar_vendedor)
    
    return df_mapeado


def validar_mapeamento(
    df: pd.DataFrame,
    colunas_esperadas: list
) -> Dict[str, bool]:
    """
    Valida se as colunas esperadas existem após mapeamento.
    
    Args:
        df: DataFrame mapeado.
        colunas_esperadas: Lista de colunas que devem existir.
    
    Returns:
        Dicionário com status de cada coluna.
    """
    validacao = {}
    for coluna in colunas_esperadas:
        validacao[coluna] = coluna in df.columns
    
    return validacao


def adicionar_coluna_subtipo_via_merge(
    df_digitacao: pd.DataFrame,
    df_tabelas: pd.DataFrame
) -> pd.DataFrame:
    """
    Adiciona coluna SUBTIPO ao DataFrame de digitação via merge com tabelas.
    
    Isso é necessário porque SUBTIPO não existe em digitação,
    mas existe nas tabelas de produtos.
    
    Args:
        df_digitacao: DataFrame de digitação (já mapeado).
        df_tabelas: DataFrame de tabelas de produtos (já mapeado).
    
    Returns:
        DataFrame de digitação com coluna SUBTIPO adicionada.
    """
    if 'PRODUTO' not in df_digitacao.columns:
        raise ValueError("DataFrame de digitação deve ter coluna 'PRODUTO'")
    
    if 'PRODUTO' not in df_tabelas.columns or 'SUBTIPO' not in df_tabelas.columns:
        raise ValueError("DataFrame de tabelas deve ter colunas 'PRODUTO' e 'SUBTIPO'")
    
    colunas_merge = ['PRODUTO', 'SUBTIPO', 'TIPO_PRODUTO', 'PTS']
    colunas_disponiveis = [col for col in colunas_merge if col in df_tabelas.columns]
    
    df_tabelas_unique = df_tabelas[colunas_disponiveis].drop_duplicates(subset=['PRODUTO'])
    
    df_result = df_digitacao.merge(
        df_tabelas_unique,
        on='PRODUTO',
        how='left',
        suffixes=('', '_tabela')
    )
    
    return df_result


def identificar_tipo_produto_real(df: pd.DataFrame) -> pd.DataFrame:
    """
    Identifica o tipo real do produto baseado nas colunas disponíveis.
    
    Adiciona colunas:
    - is_bmg_med: Se é seguro BMG MED
    - is_seguro_vida: Se é seguro Vida Familiar
    - is_emissao_cartao: Se é produto de emissão de cartão
    - is_super_conta: Se é CNC com subtipo SUPER CONTA
    
    Args:
        df: DataFrame com dados consolidados (após merge com tabelas).
    
    Returns:
        DataFrame com colunas de identificação adicionadas.
    """
    df = df.copy()
    
    if 'TIPO_PRODUTO' in df.columns:
        df['is_bmg_med'] = df['TIPO_PRODUTO'].fillna('').str.upper() == 'BMG MED'
    else:
        df['is_bmg_med'] = False
    
    if 'PRODUTO' in df.columns:
        df['is_seguro_vida'] = df['PRODUTO'].fillna('').str.upper().str.contains('SEGURO|VIDA FAMILIAR')
    else:
        df['is_seguro_vida'] = False
    
    if 'TIPO OPER.' in df.columns:
        df['is_emissao_cartao'] = df['TIPO OPER.'].isin(['CARTÃO BENEFICIO', 'Venda Pré-Adesão'])
    else:
        df['is_emissao_cartao'] = False
    
    if 'SUBTIPO' in df.columns:
        df['is_super_conta'] = (
            df['SUBTIPO'].fillna('').str.upper() == 'SUPER CONTA'
        )
    else:
        df['is_super_conta'] = False
    
    return df


def aplicar_regras_exclusao_valor_pontos(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica regras de negócio para excluir produtos de valor e pontuação.
    
    Produtos de emissão de cartão (CARTÃO BENEFICIO e Venda Pré-Adesão):
    - Contam apenas por quantidade
    - Não entram em valores monetários
    - Não geram pontuação
    
    Args:
        df: DataFrame com dados consolidados.
    
    Returns:
        DataFrame com regras aplicadas.
    """
    df = df.copy()
    
    if 'is_emissao_cartao' not in df.columns:
        df = identificar_tipo_produto_real(df)
    
    if 'VALOR' in df.columns:
        df.loc[df['is_emissao_cartao'], 'VALOR'] = 0
    
    if 'pontos' in df.columns:
        df.loc[df['is_emissao_cartao'], 'pontos'] = 0
    
    return df


def preparar_metas_por_consultor(
    df_metas: pd.DataFrame,
    df_digitacao: pd.DataFrame
) -> pd.DataFrame:
    """
    Prepara metas por consultor distribuindo metas da loja.
    
    Como as metas são por loja e não por consultor,
    esta função distribui a meta da loja igualmente entre os consultores.
    
    Args:
        df_metas: DataFrame de metas (por loja).
        df_digitacao: DataFrame de digitação (com consultores).
    
    Returns:
        DataFrame com metas por consultor.
    """
    if 'LOJA' not in df_metas.columns:
        raise ValueError("DataFrame de metas deve ter coluna 'LOJA'")
    
    if 'CONSULTOR' not in df_digitacao.columns or 'LOJA' not in df_digitacao.columns:
        raise ValueError("DataFrame de digitação deve ter colunas 'CONSULTOR' e 'LOJA'")
    
    consultores_por_loja = df_digitacao.groupby('LOJA')['CONSULTOR'].nunique().reset_index()
    consultores_por_loja.columns = ['LOJA', 'num_consultores']
    
    df_metas_expandido = df_metas.merge(consultores_por_loja, on='LOJA', how='left')
    
    df_metas_expandido['num_consultores'] = df_metas_expandido['num_consultores'].fillna(1)
    
    if 'META_PRATA' in df_metas_expandido.columns:
        df_metas_expandido['META_PRATA_CONSULTOR'] = (
            df_metas_expandido['META_PRATA'] / df_metas_expandido['num_consultores']
        )
    
    if 'META_OURO' in df_metas_expandido.columns:
        df_metas_expandido['META_OURO_CONSULTOR'] = (
            df_metas_expandido['META_OURO'] / df_metas_expandido['num_consultores']
        )
    
    consultores_unicos = df_digitacao[['LOJA', 'CONSULTOR']].drop_duplicates()
    
    df_metas_consultor = consultores_unicos.merge(
        df_metas_expandido[['LOJA', 'META_PRATA_CONSULTOR', 'META_OURO_CONSULTOR']],
        on='LOJA',
        how='left'
    )
    
    df_metas_consultor = df_metas_consultor.rename(columns={
        'META_PRATA_CONSULTOR': 'META_PRATA',
        'META_OURO_CONSULTOR': 'META_OURO'
    })
    
    return df_metas_consultor
