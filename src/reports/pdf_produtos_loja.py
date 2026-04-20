"""
Módulo para geração de relatório PDF consolidado "Produtos por Loja".
Formato landscape otimizado para exibir todos os produtos em uma única visualização.
"""
import pandas as pd
from pathlib import Path
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, PageBreak
)
from reportlab.lib.enums import TA_CENTER

from src.config.settings import (
    MESES_PT,
    MAPEAMENTO_PRODUTOS,
    MAPEAMENTO_COLUNAS_META,
)
from src.reports.formatters import (
    formatar_moeda_compacta as formatar_moeda,
    formatar_percentual,
)
from src.reports.pdf_styles import criar_rodape
from src.reports.tabela_produtos import calcular_dias_uteis

OUTPUT_DIR_PDF = 'outputs/relatorios_pdf'


def criar_cabecalho_produtos_loja(mes, ano):
    """Cria cabeçalho do relatório consolidado."""
    styles = getSampleStyleSheet()
    
    titulo_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#1F4E78'),
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    subtitulo_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#6C757D'),
        spaceAfter=15,
        alignment=TA_CENTER
    )
    
    mes_nome = MESES_PT.get(mes, str(mes))
    
    titulo = Paragraph(
        "RELATÓRIO CONSOLIDADO - PRODUTOS POR LOJA",
        titulo_style
    )
    
    subtitulo = Paragraph(
        f"{mes_nome.upper()}/{ano}",
        subtitulo_style
    )
    
    return [titulo, subtitulo]


def criar_resumo_executivo_produtos(df, df_metas, ano, mes, dia_atual=None):
    """Cria resumo executivo de todos os produtos."""
    du_total, du_decorridos, du_restantes = calcular_dias_uteis(ano, mes, dia_atual)
    
    mapeamento_produtos = {
        k + ('*' if k == 'PACK' else ''): v
        for k, v in MAPEAMENTO_PRODUTOS.items()
    }
    
    mapeamento_colunas_meta = {
        k + ('*' if k == 'PACK' else ''): v
        for k, v in MAPEAMENTO_COLUNAS_META.items()
    }
    
    elementos = []
    styles = getSampleStyleSheet()
    
    titulo = Paragraph(
        "<b>RESUMO EXECUTIVO - TODOS OS PRODUTOS</b>",
        ParagraphStyle(
            'SectionTitle',
            parent=styles['Heading2'],
            fontSize=13,
            textColor=colors.HexColor('#1F4E78'),
            spaceAfter=10
        )
    )
    elementos.append(titulo)
    
    resumo_produtos = []
    
    for produto_nome, tipos in mapeamento_produtos.items():
        df_produto = df[df['TIPO_PRODUTO'].isin(tipos)]
        valor_total = df_produto['VALOR'].sum()
        
        coluna_meta = mapeamento_colunas_meta.get(produto_nome, f'{produto_nome} LOJA')
        meta_total = 0
        if coluna_meta in df_metas.columns:
            meta_total = pd.to_numeric(df_metas[coluna_meta], errors='coerce').fillna(0).sum()
        
        perc_ating = (valor_total / meta_total * 100) if meta_total > 0 else 0
        
        resumo_produtos.append({
            'Produto': produto_nome,
            'Valor': valor_total,
            'Meta': meta_total,
            '% Ating': perc_ating
        })
    
    df_resumo = pd.DataFrame(resumo_produtos)
    
    dados_tabela = [['Produto', 'Valor Realizado', 'Meta', '% Atingimento']]
    
    for _, row in df_resumo.iterrows():
        dados_tabela.append([
            row['Produto'],
            formatar_moeda(row['Valor']),
            formatar_moeda(row['Meta']),
            formatar_percentual(row['% Ating'])
        ])
    
    total = {
        'Produto': 'TOTAL GERAL',
        'Valor': df_resumo['Valor'].sum(),
        'Meta': df_resumo['Meta'].sum(),
        '% Ating': 0
    }
    if total['Meta'] > 0:
        total['% Ating'] = (total['Valor'] / total['Meta'] * 100)
    
    dados_tabela.append([
        total['Produto'],
        formatar_moeda(total['Valor']),
        formatar_moeda(total['Meta']),
        formatar_percentual(total['% Ating'])
    ])
    
    tabela = Table(dados_tabela, colWidths=[5*cm, 5*cm, 5*cm, 4*cm])
    tabela.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F4E78')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2),
         [colors.white, colors.HexColor('#F8F9FA')]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#E7E6E6')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    
    elementos.append(tabela)
    
    return elementos


def criar_tabela_produtos_por_regiao(df, df_metas, ano, mes, dia_atual=None):
    """Cria tabelas de produtos por loja, agrupadas por região."""
    du_total, du_decorridos, du_restantes = calcular_dias_uteis(ano, mes, dia_atual)
    
    mapeamento_produtos = {
        k + ('*' if k == 'PACK' else ''): v
        for k, v in MAPEAMENTO_PRODUTOS.items()
    }
    
    mapeamento_colunas_meta = {
        k + ('*' if k == 'PACK' else ''): v
        for k, v in MAPEAMENTO_COLUNAS_META.items()
    }
    
    if 'REGIAO' not in df.columns or 'LOJA' not in df.columns:
        return []
    
    regioes = sorted(df['REGIAO'].unique())
    elementos = []
    styles = getSampleStyleSheet()
    
    for regiao in regioes:
        elementos.append(PageBreak())
        
        titulo = Paragraph(
            f"<b>REGIÃO: {regiao}</b>",
            ParagraphStyle(
                'RegionTitle',
                parent=styles['Heading2'],
                fontSize=12,
                textColor=colors.whitesmoke,
                backColor=colors.HexColor('#1F4E78'),
                spaceAfter=10,
                alignment=TA_CENTER,
                leftIndent=8,
                rightIndent=8
            )
        )
        elementos.append(titulo)
        
        df_regiao = df[df['REGIAO'] == regiao]
        lojas = sorted(df_regiao['LOJA'].unique())
        
        dados_lojas = []
        
        for loja in lojas:
            df_loja = df_regiao[df_regiao['LOJA'] == loja]
            
            linha_loja = {'Loja': loja}
            
            for produto_nome, tipos in mapeamento_produtos.items():
                df_produto = df_loja[df_loja['TIPO_PRODUTO'].isin(tipos)]
                valor = df_produto['VALOR'].sum()
                
                coluna_meta = mapeamento_colunas_meta.get(produto_nome, f'{produto_nome} LOJA')
                meta = 0
                if coluna_meta in df_metas.columns:
                    meta_loja = df_metas[df_metas['LOJA'] == loja]
                    if not meta_loja.empty:
                        meta = pd.to_numeric(meta_loja[coluna_meta].iloc[0], errors='coerce')
                        if pd.isna(meta):
                            meta = 0
                
                perc_ating = (valor / meta * 100) if meta > 0 else 0
                
                linha_loja[f'{produto_nome} Vlr'] = valor
                linha_loja[f'{produto_nome} Meta'] = meta
                linha_loja[f'{produto_nome} %'] = perc_ating
            
            dados_lojas.append(linha_loja)
        
        df_tabela = pd.DataFrame(dados_lojas)
        
        total = {'Loja': f'TOTAL {regiao}'}
        for produto_nome in mapeamento_produtos.keys():
            total[f'{produto_nome} Vlr'] = df_tabela[f'{produto_nome} Vlr'].sum()
            total[f'{produto_nome} Meta'] = df_tabela[f'{produto_nome} Meta'].sum()
            if total[f'{produto_nome} Meta'] > 0:
                total[f'{produto_nome} %'] = (total[f'{produto_nome} Vlr'] / total[f'{produto_nome} Meta'] * 100)
            else:
                total[f'{produto_nome} %'] = 0
        
        df_tabela = pd.concat([df_tabela, pd.DataFrame([total])], ignore_index=True)
        
        headers = ['Loja']
        for produto in ['CNC', 'SAQUE', 'CLT', 'CONSIGNADO', 'PACK*']:
            headers.extend([f'{produto}\nVlr', f'{produto}\nMeta', f'{produto}\n%'])
        
        dados_tabela = [headers]
        
        for idx, row in df_tabela.iterrows():
            is_total = str(row['Loja']).startswith('TOTAL')
            linha = [row['Loja']]
            
            for produto in ['CNC', 'SAQUE', 'CLT', 'CONSIGNADO', 'PACK*']:
                linha.append(formatar_moeda(row[f'{produto} Vlr']))
                linha.append(formatar_moeda(row[f'{produto} Meta']))
                linha.append(formatar_percentual(row[f'{produto} %']))
            
            dados_tabela.append(linha)
        
        col_widths = [2.5*cm]
        for _ in range(5):
            col_widths.extend([1.6*cm, 1.6*cm, 1.2*cm])
        
        tabela = Table(dados_tabela, colWidths=col_widths)
        
        style_list = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F4E78')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 6),
            ('FONTSIZE', (0, 1), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
            ('TOPPADDING', (0, 0), (-1, 0), 4),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 2),
            ('TOPPADDING', (0, 1), (-1, -1), 2),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2),
             [colors.white, colors.HexColor('#F8F9FA')]),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#E7E6E6')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]
        
        tabela.setStyle(TableStyle(style_list))
        elementos.append(tabela)
        elementos.append(Spacer(1, 0.3*cm))
    
    return elementos


def gerar_relatorio_produtos_loja_pdf(df, df_metas, mes, ano, dia_atual=None):
    """
    Gera relatório PDF consolidado "Produtos por Loja" em formato landscape.
    
    Args:
        df: DataFrame com dados consolidados
        df_metas: DataFrame com metas
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
    
    filename = f"relatorio_produtos_loja_{mes:02d}_{ano}_{timestamp}.pdf"
    filepath = output_dir / filename
    
    doc = SimpleDocTemplate(
        str(filepath),
        pagesize=landscape(A4),
        rightMargin=1.5*cm,
        leftMargin=1.5*cm,
        topMargin=1.5*cm,
        bottomMargin=1.5*cm
    )
    
    elementos = []
    
    elementos.extend(criar_cabecalho_produtos_loja(mes, ano))
    
    elementos.extend(criar_resumo_executivo_produtos(df, df_metas, ano, mes, dia_atual))
    
    elementos.extend(criar_tabela_produtos_por_regiao(df, df_metas, ano, mes, dia_atual))
    
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
