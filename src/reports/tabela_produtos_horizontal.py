import pandas as pd
from src.reports.tabela_produtos import calcular_dias_uteis


def criar_tabela_produtos_horizontal(df, df_metas, ano, mes, dia_atual=None):
    """
    Cria tabela horizontal de produtos por loja, agrupada por região.
    
    Para cada produto com meta individual (CNC, SAQUE, CLT, CONSIGNADO, PACK):
    - Loja
    - Valor do produto
    - Meta do produto
    - % Atingimento
    - Média DU
    - Ticket Médio
    - Projeção
    - % Projeção
    
    Args:
        df: DataFrame consolidado com vendas
        df_metas: DataFrame com metas
        ano: Ano do relatório
        mes: Mês do relatório
        dia_atual: Dia atual para cálculo de dias úteis
    
    Returns:
        dict com DataFrames agrupados por região
    """
    du_total, du_decorridos, du_restantes = calcular_dias_uteis(ano, mes, dia_atual)
    
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
    
    if 'REGIAO' not in df.columns or 'LOJA' not in df.columns:
        return {}
    
    regioes = sorted(df['REGIAO'].unique())
    tabelas_por_regiao = {}
    
    for regiao in regioes:
        df_regiao = df[df['REGIAO'] == regiao].copy()
        
        lojas = sorted(df_regiao['LOJA'].unique())
        dados_lojas = []
        
        for loja in lojas:
            df_loja = df_regiao[df_regiao['LOJA'] == loja].copy()
            
            mask_emissao = df_loja['TIPO_PRODUTO'].isin(produtos_emissao)
            df_loja.loc[mask_emissao, 'VALOR'] = 0
            
            linha_loja = {'Loja': loja}
            
            for produto_mix, tipos in mapeamento_produtos.items():
                df_produto = df_loja[df_loja['TIPO_PRODUTO'].isin(tipos)]
                
                valor = df_produto['VALOR'].sum()
                pontos = df_produto['pontos'].sum()
                quantidade = len(df_produto)
                
                coluna_meta = mapeamento_colunas_meta.get(produto_mix, f'{produto_mix} LOJA')
                meta = 0
                if coluna_meta in df_metas.columns:
                    meta_loja = df_metas[df_metas['LOJA'] == loja]
                    if not meta_loja.empty:
                        meta_valor = meta_loja[coluna_meta].iloc[0]
                        meta = pd.to_numeric(meta_valor, errors='coerce')
                        if pd.isna(meta):
                            meta = 0
                
                perc_ating = (valor / meta * 100) if meta > 0 else 0
                
                media_du = valor / du_decorridos if du_decorridos > 0 else 0
                ticket_medio = valor / quantidade if quantidade > 0 else 0
                projecao = media_du * du_total
                
                perc_projecao = (projecao / meta * 100) if meta > 0 else 0
                
                nome_produto = f'{produto_mix}*' if produto_mix == 'PACK' else produto_mix
                
                linha_loja[f'{nome_produto}'] = valor
                linha_loja[f'Meta {nome_produto}'] = meta
                linha_loja[f'% Ating. {nome_produto}'] = perc_ating
                linha_loja[f'Média DU {nome_produto}'] = media_du
                linha_loja[f'Ticket Médio {nome_produto}'] = ticket_medio
                linha_loja[f'Projeção {nome_produto}'] = projecao
                linha_loja[f'% Proj. {nome_produto}'] = perc_projecao
            
            dados_lojas.append(linha_loja)
        
        if dados_lojas:
            df_tabela = pd.DataFrame(dados_lojas)
            
            linha_total = {'Loja': f'TOTAL {regiao}'}
            
            for produto_mix in mapeamento_produtos.keys():
                nome_produto = f'{produto_mix}*' if produto_mix == 'PACK' else produto_mix
                
                linha_total[f'{nome_produto}'] = df_tabela[f'{nome_produto}'].sum()
                linha_total[f'Meta {nome_produto}'] = df_tabela[f'Meta {nome_produto}'].sum()
                
                total_valor = linha_total[f'{nome_produto}']
                total_meta = linha_total[f'Meta {nome_produto}']
                
                linha_total[f'% Ating. {nome_produto}'] = (total_valor / total_meta * 100) if total_meta > 0 else 0
                linha_total[f'Média DU {nome_produto}'] = total_valor / du_decorridos if du_decorridos > 0 else 0
                linha_total[f'Ticket Médio {nome_produto}'] = df_tabela[f'Ticket Médio {nome_produto}'].mean()
                linha_total[f'Projeção {nome_produto}'] = (linha_total[f'Média DU {nome_produto}'] * du_total)
                linha_total[f'% Proj. {nome_produto}'] = (linha_total[f'Projeção {nome_produto}'] / total_meta * 100) if total_meta > 0 else 0
            
            df_tabela = pd.concat([df_tabela, pd.DataFrame([linha_total])], ignore_index=True)
            tabelas_por_regiao[regiao] = df_tabela
    
    return tabelas_por_regiao
