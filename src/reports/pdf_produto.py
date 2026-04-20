"""
Módulo para geração de relatórios PDF individuais por produto.
Cria um relatório focado para cada produto: CNC, SAQUE, CLT, CONSIGNADO, PACK.
"""
import pandas as pd
from pathlib import Path
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, PageBreak, Image
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from src.config.settings import (
    MESES_PT,
    MAPEAMENTO_PRODUTOS,
    MAPEAMENTO_COLUNAS_META,
)
from src.reports.formatters import (
    formatar_moeda,
    formatar_numero,
    formatar_percentual,
)
from src.reports.pdf_charts import criar_grafico_pizza_produtos
from src.reports.pdf_styles import criar_rodape
from src.reports.tabela_produtos import calcular_dias_uteis

OUTPUT_DIR_PDF = 'outputs/relatorios_pdf'


def criar_cabecalho_produto(mes, ano, produto_nome):
    """Cria cabeçalho do relatório de produto."""
    styles = getSampleStyleSheet()
    
    titulo_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1F4E78'),
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    subtitulo_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.HexColor('#6C757D'),
        spaceAfter=20,
        alignment=TA_CENTER
    )
    
    mes_nome = MESES_PT.get(mes, str(mes))
    
    titulo = Paragraph(
        f"RELATÓRIO DE PRODUTO - {produto_nome}",
        titulo_style
    )
    
    subtitulo = Paragraph(
        f"{mes_nome.upper()}/{ano}",
        subtitulo_style
    )
    
    return [titulo, subtitulo]


def criar_kpis_produto(df, df_metas, produto_nome, ano, mes, dia_atual=None):
    """Cria seção de KPIs do produto."""
    du_total, du_decorridos, du_restantes = calcular_dias_uteis(ano, mes, dia_atual)
    
    tipos_produto = MAPEAMENTO_PRODUTOS.get(produto_nome, [])
    coluna_meta = MAPEAMENTO_COLUNAS_META.get(produto_nome, f'{produto_nome} LOJA')
    
    df_produto = df[df['TIPO_PRODUTO'].isin(tipos_produto)]
    
    valor_total = df_produto['VALOR'].sum()
    quantidade = len(df_produto)
    
    meta_total = 0
    if coluna_meta in df_metas.columns:
        meta_total = pd.to_numeric(df_metas[coluna_meta], errors='coerce').fillna(0).sum()
    
    perc_ating = (valor_total / meta_total * 100) if meta_total > 0 else 0
    media_du = valor_total / du_decorridos if du_decorridos > 0 else 0
    meta_diaria = meta_total / du_total if du_total > 0 else 0
    projecao = media_du * du_total
    perc_projecao = (projecao / meta_total * 100) if meta_total > 0 else 0
    ticket_medio = valor_total / quantidade if quantidade > 0 else 0
    
    styles = getSampleStyleSheet()
    elementos = []
    
    titulo = Paragraph(
        "<b>INDICADORES GERAIS</b>",
        ParagraphStyle(
            'SectionTitle',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#1F4E78'),
            spaceAfter=12
        )
    )
    elementos.append(titulo)
    
    dados_kpis = [
        ['Indicador', 'Valor'],
        ['Valor Total Realizado', formatar_moeda(valor_total)],
        ['Meta do Produto', formatar_moeda(meta_total)],
        ['Meta Diária', formatar_moeda(meta_diaria)],
        ['% Atingimento', formatar_percentual(perc_ating)],
        ['Quantidade de Vendas', formatar_numero(quantidade)],
        ['Ticket Médio', formatar_moeda(ticket_medio)],
        ['Média por Dia Útil', formatar_moeda(media_du)],
        ['Projeção Fim do Mês', formatar_moeda(projecao)],
        ['% Projeção', formatar_percentual(perc_projecao)],
    ]
    
    tabela = Table(dados_kpis, colWidths=[10*cm, 6*cm])
    tabela.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F4E78')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.white, colors.HexColor('#F8F9FA')]),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
    ]))
    
    elementos.append(tabela)
    
    return elementos


def criar_distribuicao_por_regiao(df, produto_nome):
    """Cria seção de distribuição por região."""
    tipos_produto = MAPEAMENTO_PRODUTOS.get(produto_nome, [])
    df_produto = df[df['TIPO_PRODUTO'].isin(tipos_produto)]
    
    if 'REGIAO' not in df_produto.columns:
        return []
    
    resumo_regiao = df_produto.groupby('REGIAO').agg({
        'VALOR': 'sum',
        'LOJA': 'nunique'
    }).reset_index()
    
    resumo_regiao.columns = ['Região', 'Valor', 'Lojas']
    resumo_regiao = resumo_regiao.sort_values('Valor', ascending=False)
    
    elementos = []
    styles = getSampleStyleSheet()
    
    elementos.append(Spacer(1, 0.5*cm))
    
    titulo = Paragraph(
        "<b>DISTRIBUIÇÃO POR REGIÃO</b>",
        ParagraphStyle(
            'SectionTitle',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#1F4E78'),
            spaceAfter=12
        )
    )
    elementos.append(titulo)
    
    df_grafico = resumo_regiao.copy()
    df_grafico['Produto'] = df_grafico['Região']
    df_grafico['Pontos'] = df_grafico['Valor']
    
    grafico = criar_grafico_pizza_produtos(
        df_grafico,
        f'Distribuição de Valor por Região - {produto_nome}'
    )
    
    img = Image(grafico, width=14*cm, height=10*cm)
    elementos.append(img)
    elementos.append(Spacer(1, 0.5*cm))
    
    dados_tabela = [['Região', 'Valor', 'Lojas', '%']]
    total_valor = resumo_regiao['Valor'].sum()
    
    for _, row in resumo_regiao.iterrows():
        percentual = (row['Valor'] / total_valor * 100) if total_valor > 0 else 0
        dados_tabela.append([
            row['Região'],
            formatar_moeda(row['Valor']),
            formatar_numero(row['Lojas']),
            formatar_percentual(percentual)
        ])
    
    tabela = Table(dados_tabela, colWidths=[5*cm, 4*cm, 3*cm, 3*cm])
    tabela.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F4E78')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.white, colors.HexColor('#F8F9FA')]),
    ]))
    
    elementos.append(tabela)
    
    return elementos


def criar_ranking_lojas_produto(df, df_metas, produto_nome, ano, mes, dia_atual=None):
    """Cria rankings de lojas para o produto."""
    du_total, du_decorridos, du_restantes = calcular_dias_uteis(ano, mes, dia_atual)
    
    tipos_produto = MAPEAMENTO_PRODUTOS.get(produto_nome, [])
    coluna_meta = MAPEAMENTO_COLUNAS_META.get(produto_nome, f'{produto_nome} LOJA')
    
    df_produto = df[df['TIPO_PRODUTO'].isin(tipos_produto)]
    
    ranking = df_produto.groupby('LOJA').agg({
        'VALOR': 'sum',
        'REGIAO': 'first'
    }).reset_index()
    
    ranking.columns = ['Loja', 'Valor', 'Região']
    
    if coluna_meta in df_metas.columns:
        metas = df_metas[['LOJA', coluna_meta]].copy()
        metas['Meta'] = pd.to_numeric(metas[coluna_meta], errors='coerce').fillna(0)
        ranking = ranking.merge(metas[['LOJA', 'Meta']], left_on='Loja', right_on='LOJA', how='left')
        ranking = ranking.drop('LOJA', axis=1)
        ranking['Meta'] = ranking['Meta'].fillna(0)
    else:
        ranking['Meta'] = 0
    
    ranking['% Ating'] = (ranking['Valor'] / ranking['Meta'] * 100).where(
        ranking['Meta'] > 0, 0
    )
    
    elementos = []
    styles = getSampleStyleSheet()
    
    elementos.append(PageBreak())
    
    titulo = Paragraph(
        "<b>TOP 10 LOJAS - POR VALOR</b>",
        ParagraphStyle(
            'SectionTitle',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#1F4E78'),
            spaceAfter=12
        )
    )
    elementos.append(titulo)
    
    top_valor = ranking.sort_values('Valor', ascending=False).head(10).copy()
    top_valor.insert(0, 'Posição', range(1, len(top_valor) + 1))
    
    dados_tabela = [['Pos', 'Loja', 'Região', 'Valor', 'Meta', '% Ating']]
    
    for _, row in top_valor.iterrows():
        dados_tabela.append([
            int(row['Posição']),
            row['Loja'],
            row['Região'],
            formatar_moeda(row['Valor']),
            formatar_moeda(row['Meta']),
            formatar_percentual(row['% Ating'])
        ])
    
    tabela = Table(dados_tabela, colWidths=[1.5*cm, 4*cm, 3*cm, 3*cm, 3*cm, 2.5*cm])
    tabela.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F4E78')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.white, colors.HexColor('#F8F9FA')]),
    ]))
    
    elementos.append(tabela)
    elementos.append(Spacer(1, 0.8*cm))
    
    titulo2 = Paragraph(
        "<b>TOP 10 LOJAS - POR % ATINGIMENTO</b>",
        ParagraphStyle(
            'SectionTitle',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#1F4E78'),
            spaceAfter=12
        )
    )
    elementos.append(titulo2)
    
    top_ating = ranking[ranking['Meta'] > 0].sort_values('% Ating', ascending=False).head(10).copy()
    top_ating.insert(0, 'Posição', range(1, len(top_ating) + 1))
    
    dados_tabela2 = [['Pos', 'Loja', 'Região', 'Valor', 'Meta', '% Ating']]
    
    for _, row in top_ating.iterrows():
        dados_tabela2.append([
            int(row['Posição']),
            row['Loja'],
            row['Região'],
            formatar_moeda(row['Valor']),
            formatar_moeda(row['Meta']),
            formatar_percentual(row['% Ating'])
        ])
    
    tabela2 = Table(dados_tabela2, colWidths=[1.5*cm, 4*cm, 3*cm, 3*cm, 3*cm, 2.5*cm])
    tabela2.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F4E78')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.white, colors.HexColor('#F8F9FA')]),
    ]))
    
    elementos.append(tabela2)
    
    return elementos


def criar_detalhamento_por_regiao(df, df_metas, produto_nome, ano, mes, dia_atual=None):
    """Cria detalhamento de lojas por região."""
    du_total, du_decorridos, du_restantes = calcular_dias_uteis(ano, mes, dia_atual)
    
    tipos_produto = MAPEAMENTO_PRODUTOS.get(produto_nome, [])
    coluna_meta = MAPEAMENTO_COLUNAS_META.get(produto_nome, f'{produto_nome} LOJA')
    
    if 'REGIAO' not in df.columns:
        return []
    
    df_produto = df[df['TIPO_PRODUTO'].isin(tipos_produto)]
    regioes = sorted(df_produto['REGIAO'].unique())
    
    elementos = []
    styles = getSampleStyleSheet()
    
    for regiao in regioes:
        elementos.append(PageBreak())
        
        titulo = Paragraph(
            f"<b>REGIÃO: {regiao}</b>",
            ParagraphStyle(
                'RegionTitle',
                parent=styles['Heading2'],
                fontSize=14,
                textColor=colors.whitesmoke,
                backColor=colors.HexColor('#1F4E78'),
                spaceAfter=12,
                alignment=TA_CENTER,
                leftIndent=10,
                rightIndent=10
            )
        )
        elementos.append(titulo)
        
        df_regiao = df_produto[df_produto['REGIAO'] == regiao]
        lojas = sorted(df_regiao['LOJA'].unique())
        
        dados_lojas = []
        
        for loja in lojas:
            df_loja = df_regiao[df_regiao['LOJA'] == loja]
            
            valor = df_loja['VALOR'].sum()
            quantidade = len(df_loja)
            
            meta = 0
            if coluna_meta in df_metas.columns:
                meta_loja = df_metas[df_metas['LOJA'] == loja]
                if not meta_loja.empty:
                    meta = pd.to_numeric(meta_loja[coluna_meta].iloc[0], errors='coerce')
                    if pd.isna(meta):
                        meta = 0
            
            perc_ating = (valor / meta * 100) if meta > 0 else 0
            media_du = valor / du_decorridos if du_decorridos > 0 else 0
            meta_diaria = meta / du_total if du_total > 0 else 0
            ticket_medio = valor / quantidade if quantidade > 0 else 0
            projecao = media_du * du_total
            perc_projecao = (projecao / meta * 100) if meta > 0 else 0
            
            dados_lojas.append({
                'Loja': loja,
                'Valor': valor,
                'Meta': meta,
                'Meta Diária': meta_diaria,
                '% Ating': perc_ating,
                'Média DU': media_du,
                'Ticket Médio': ticket_medio,
                'Projeção': projecao,
                '% Proj': perc_projecao
            })
        
        df_tabela = pd.DataFrame(dados_lojas)
        df_tabela = df_tabela.sort_values('% Ating', ascending=False)
        
        total = {
            'Loja': f'TOTAL {regiao}',
            'Valor': df_tabela['Valor'].sum(),
            'Meta': df_tabela['Meta'].sum(),
            'Meta Diária': 0,
            '% Ating': 0,
            'Média DU': df_tabela['Média DU'].sum(),
            'Ticket Médio': df_tabela['Ticket Médio'].mean(),
            'Projeção': df_tabela['Projeção'].sum(),
            '% Proj': 0
        }
        
        if total['Meta'] > 0:
            total['Meta Diária'] = total['Meta'] / du_total
            total['% Ating'] = (total['Valor'] / total['Meta'] * 100)
            total['% Proj'] = (total['Projeção'] / total['Meta'] * 100)
        
        df_tabela = pd.concat([df_tabela, pd.DataFrame([total])], ignore_index=True)
        
        dados_tabela = [[
            'Loja', 'Valor', 'Meta', 'Meta Diária', '% Ating',
            'Média DU', 'Ticket Médio', 'Projeção', '% Proj'
        ]]
        
        for idx, row in df_tabela.iterrows():
            is_total = str(row['Loja']).startswith('TOTAL')
            dados_tabela.append([
                row['Loja'],
                formatar_moeda(row['Valor']),
                formatar_moeda(row['Meta']),
                formatar_moeda(row['Meta Diária']),
                formatar_percentual(row['% Ating']),
                formatar_moeda(row['Média DU']),
                formatar_moeda(row['Ticket Médio']),
                formatar_moeda(row['Projeção']),
                formatar_percentual(row['% Proj'])
            ])
        
        tabela = Table(dados_tabela, colWidths=[
            3*cm, 2.2*cm, 2.2*cm, 2.2*cm, 1.8*cm,
            2.2*cm, 2.2*cm, 2.2*cm, 1.8*cm
        ])
        
        style_list = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F4E78')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2),
             [colors.white, colors.HexColor('#F8F9FA')]),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#E7E6E6')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ]
        
        tabela.setStyle(TableStyle(style_list))
        elementos.append(tabela)
    
    return elementos


def gerar_relatorio_produto_pdf(df, df_metas, produto_nome, mes, ano, dia_atual=None):
    """
    Gera relatório PDF individual para um produto específico.
    
    Args:
        df: DataFrame com dados consolidados
        df_metas: DataFrame com metas
        produto_nome: Nome do produto ('CNC', 'SAQUE', 'CLT', 'CONSIGNADO', 'PACK')
        mes: Mês do relatório
        ano: Ano do relatório
        dia_atual: Dia atual para cálculo de dias úteis
        
    Returns:
        Path do arquivo PDF gerado
    """
    mes_nome = MESES_PT.get(mes, str(mes)).lower()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    output_dir = Path(OUTPUT_DIR_PDF)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    filename = f"relatorio_{produto_nome.lower()}_{mes:02d}_{ano}_{timestamp}.pdf"
    filepath = output_dir / filename
    
    doc = SimpleDocTemplate(
        str(filepath),
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )
    
    elementos = []
    
    elementos.extend(criar_cabecalho_produto(mes, ano, produto_nome))
    elementos.append(Spacer(1, 0.5*cm))
    
    elementos.extend(criar_kpis_produto(df, df_metas, produto_nome, ano, mes, dia_atual))
    
    elementos.extend(criar_distribuicao_por_regiao(df, produto_nome))
    
    elementos.extend(criar_ranking_lojas_produto(df, df_metas, produto_nome, ano, mes, dia_atual))
    
    elementos.extend(criar_detalhamento_por_regiao(df, df_metas, produto_nome, ano, mes, dia_atual))
    
    if produto_nome == 'PACK':
        styles = getSampleStyleSheet()
        elementos.append(Spacer(1, 0.5*cm))
        nota = Paragraph(
            "<i>* PACK = FGTS, ANT. BEN. e CNC 13º</i>",
            styles['Normal']
        )
        elementos.append(nota)
    
    doc.build(
        elementos,
        onFirstPage=criar_rodape,
        onLaterPages=criar_rodape,
    )
    
    return filepath
