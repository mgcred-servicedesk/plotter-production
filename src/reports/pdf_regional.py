"""
Gerador de Relatório PDF Regional com análise específica por região.
Focado em comparação e performance regional.
"""
from datetime import datetime
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.enums import TA_CENTER

from src.config.settings import (
    MESES_PT,
    MAPEAMENTO_PRODUTOS,
)
from src.reports.formatters import (
    formatar_moeda,
    formatar_numero,
    formatar_percentual,
)
from src.reports.pdf_charts import (
    criar_grafico_barras_top10,
    criar_grafico_pizza_produtos,
)
from src.reports.pdf_styles import (
    criar_rodape,
    get_titulo_style,
    get_subtitulo_style,
    get_secao_style,
)
from src.reports.resumo_geral import criar_resumo_geral


def criar_capa_regional(regiao, mes, ano):
    """Cria capa do relatório regional."""
    elementos = []

    titulo_style = get_titulo_style(22)
    subtitulo_style = get_subtitulo_style(14)

    elementos.append(Spacer(1, 2*cm))
    
    logo_path = Path('assets/logotipo-mg-cred.png')
    if logo_path.exists():
        logo = Image(str(logo_path), width=5*cm, height=2.5*cm)
        elementos.append(logo)
        elementos.append(Spacer(1, 1*cm))

    titulo = Paragraph(
        f"RELATÓRIO REGIONAL<br/>{regiao}",
        titulo_style
    )
    elementos.append(titulo)

    subtitulo = Paragraph(
        f"{MESES_PT[mes]} de {ano}",
        subtitulo_style
    )
    elementos.append(subtitulo)

    elementos.append(Spacer(1, 2*cm))

    data_geracao = Paragraph(
        f"Gerado em: {datetime.now().strftime('%d/%m/%Y às %H:%M')}",
        subtitulo_style
    )
    elementos.append(data_geracao)

    elementos.append(PageBreak())

    return elementos


def criar_resumo_regiao(df_regiao, regiao, df_metas):
    """Cria resumo consolidado da região."""
    elementos = []
    styles = getSampleStyleSheet()

    titulo_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#1F4E78'),
        spaceAfter=10,
        fontName='Helvetica-Bold'
    )

    elementos.append(Paragraph(f"RESUMO DA REGIÃO {regiao}", titulo_style))
    elementos.append(Spacer(1, 0.3*cm))

    total_qtd = len(df_regiao[df_regiao['VALOR'] > 0])
    total_valor = df_regiao['VALOR'].sum()
    total_pontos = df_regiao['pontos'].sum()
    ticket_medio = total_valor / total_qtd if total_qtd > 0 else 0

    meta_regiao = 0
    if 'REGIAO' in df_metas.columns and 'META_PRATA' in df_metas.columns:
        meta_regiao = df_metas[df_metas['REGIAO'] == regiao][
            'META_PRATA'
        ].sum()

    atingimento = (total_pontos / meta_regiao * 100
                   if meta_regiao > 0 else 0)

    dados_tabela = [
        ['Métrica', 'Valor'],
        ['Quantidade Total', formatar_numero(total_qtd)],
        ['Valor Total', formatar_moeda(total_valor)],
        ['Pontos Totais', formatar_numero(total_pontos)],
        ['Meta Prata', formatar_numero(meta_regiao)],
        ['Atingimento %', formatar_percentual(atingimento)],
        ['Ticket Médio', formatar_moeda(ticket_medio)],
    ]

    tabela = Table(dados_tabela, colWidths=[10*cm, 6*cm])
    tabela.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F4E78')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.white, colors.HexColor('#F8F9FA')]),
    ]))

    elementos.append(tabela)
    elementos.append(Spacer(1, 0.5*cm))

    return elementos


def criar_top_lojas_regiao(df_regiao):
    """Cria ranking de lojas da região."""
    elementos = []
    styles = getSampleStyleSheet()

    titulo_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#1F4E78'),
        spaceAfter=10,
        fontName='Helvetica-Bold'
    )

    elementos.append(Paragraph("TOP LOJAS DA REGIÃO", titulo_style))
    elementos.append(Spacer(1, 0.3*cm))

    df_valido = df_regiao[df_regiao['VALOR'] > 0].copy()

    if 'LOJA' not in df_valido.columns:
        elementos.append(Paragraph("Sem dados disponíveis", styles['Normal']))
        return elementos

    top_lojas = df_valido.groupby('LOJA', as_index=False).agg({
        'VALOR': ['count', 'sum'],
        'pontos': 'sum'
    })

    top_lojas.columns = ['Loja', 'Qtd', 'Valor', 'Pontos']
    top_lojas['Ticket Médio'] = (
        top_lojas['Valor'] / top_lojas['Qtd']
    ).where(top_lojas['Qtd'] > 0, 0)

    top_lojas = top_lojas.sort_values('Pontos', ascending=False).head(10)
    top_lojas.insert(0, 'Posição', range(1, len(top_lojas) + 1))

    if not top_lojas.empty:
        grafico = criar_grafico_barras_top10(
            top_lojas,
            'Loja',
            'Pontos',
            'TOP Lojas da Região por Pontos',
            '#1F4E78'
        )

        img = Image(grafico, width=16*cm, height=8*cm)
        elementos.append(img)
        elementos.append(Spacer(1, 0.5*cm))

        dados_tabela = [['Pos', 'Loja', 'Qtd', 'Pontos', 'Ticket Médio']]

        for _, row in top_lojas.iterrows():
            dados_tabela.append([
                str(int(row['Posição'])),
                str(row['Loja']),
                formatar_numero(row['Qtd']),
                formatar_numero(row['Pontos']),
                formatar_moeda(row['Ticket Médio'])
            ])

        tabela = Table(
            dados_tabela,
            colWidths=[2*cm, 6*cm, 3*cm, 4*cm, 4*cm]
        )
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

    elementos.append(PageBreak())

    return elementos


def criar_top_consultores_regiao(df_regiao):
    """Cria ranking de consultores da região."""
    elementos = []
    styles = getSampleStyleSheet()

    titulo_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#1F4E78'),
        spaceAfter=10,
        fontName='Helvetica-Bold'
    )

    elementos.append(Paragraph("TOP CONSULTORES DA REGIÃO", titulo_style))
    elementos.append(Spacer(1, 0.3*cm))

    df_valido = df_regiao[df_regiao['VALOR'] > 0].copy()

    if 'CONSULTOR' not in df_valido.columns:
        elementos.append(Paragraph("Sem dados disponíveis", styles['Normal']))
        return elementos

    top_consultores = df_valido.groupby('CONSULTOR', as_index=False).agg({
        'VALOR': ['count', 'sum'],
        'pontos': 'sum',
        'LOJA': 'first'
    })

    top_consultores.columns = ['Consultor', 'Qtd', 'Valor', 'Pontos', 'Loja']
    top_consultores['Ticket Médio'] = (
        top_consultores['Valor'] / top_consultores['Qtd']
    ).where(top_consultores['Qtd'] > 0, 0)

    top_consultores = top_consultores.sort_values(
        'Pontos', ascending=False
    ).head(10)
    top_consultores.insert(0, 'Posição', range(1, len(top_consultores) + 1))

    if not top_consultores.empty:
        grafico = criar_grafico_barras_top10(
            top_consultores,
            'Consultor',
            'Pontos',
            'TOP Consultores da Região por Pontos',
            '#28A745'
        )

        img = Image(grafico, width=16*cm, height=8*cm)
        elementos.append(img)
        elementos.append(Spacer(1, 0.5*cm))

        dados_tabela = [[
            'Pos', 'Consultor', 'Loja', 'Qtd', 'Pontos', 'Ticket Médio'
        ]]

        for _, row in top_consultores.iterrows():
            dados_tabela.append([
                str(int(row['Posição'])),
                str(row['Consultor'])[:25],
                str(row['Loja']),
                formatar_numero(row['Qtd']),
                formatar_numero(row['Pontos']),
                formatar_moeda(row['Ticket Médio'])
            ])

        tabela = Table(
            dados_tabela,
            colWidths=[1.5*cm, 5*cm, 3*cm, 2.5*cm, 3*cm, 3*cm]
        )
        tabela.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#28A745')),
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

    elementos.append(PageBreak())

    return elementos


def criar_produtos_regiao(df_regiao):
    """Cria análise de produtos da região."""
    elementos = []
    styles = getSampleStyleSheet()

    titulo_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#1F4E78'),
        spaceAfter=10,
        fontName='Helvetica-Bold'
    )

    elementos.append(Paragraph("PRODUTOS DA REGIÃO (MIX)", titulo_style))
    elementos.append(Spacer(1, 0.3*cm))

    df_valido = df_regiao[df_regiao['VALOR'] > 0].copy()

    if 'TIPO_PRODUTO' not in df_valido.columns:
        elementos.append(Paragraph("Sem dados disponíveis", styles['Normal']))
        return elementos

    resumo_produtos = []

    for produto_mix, tipos in MAPEAMENTO_PRODUTOS.items():
        df_produto = df_valido[df_valido['TIPO_PRODUTO'].isin(tipos)]

        if len(df_produto) > 0:
            resumo_produtos.append({
                'Produto': produto_mix,
                'Qtd': len(df_produto),
                'Valor': df_produto['VALOR'].sum(),
                'Pontos': df_produto['pontos'].sum()
            })

    df_produtos = pd.DataFrame(resumo_produtos)

    if not df_produtos.empty:
        grafico = criar_grafico_pizza_produtos(
            df_produtos,
            'Distribuição de Pontos por Produto na Região'
        )

        img = Image(grafico, width=14*cm, height=10*cm)
        elementos.append(img)
        elementos.append(Spacer(1, 0.5*cm))

        dados_tabela = [['Produto', 'Qtd', 'Valor', 'Pontos', '%']]

        total_pontos = df_produtos['Pontos'].sum()

        for _, row in df_produtos.iterrows():
            percentual = (row['Pontos'] / total_pontos * 100
                          if total_pontos > 0 else 0)
            dados_tabela.append([
                str(row['Produto']),
                formatar_numero(row['Qtd']),
                formatar_moeda(row['Valor']),
                formatar_numero(row['Pontos']),
                formatar_percentual(percentual)
            ])

        tabela = Table(dados_tabela, colWidths=[4*cm, 3*cm, 4*cm, 4*cm, 3*cm])
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
        elementos.append(Spacer(1, 0.3*cm))
        
        nota = Paragraph(
            "<i>* PACK = FGTS, ANT. BEN. e CNC 13º</i>",
            styles['Normal']
        )
        elementos.append(nota)

    return elementos


def gerar_relatorio_regional_pdf(df, mes, ano, df_metas, dia_atual=None):
    """
    Gera relatórios PDF regionais (um para cada região).

    Args:
        df: DataFrame com dados consolidados
        mes: Mês do relatório
        ano: Ano do relatório
        df_metas: DataFrame com metas
        dia_atual: Dia atual para cálculo de dias úteis

    Returns:
        Lista com caminhos dos arquivos PDF gerados
    """
    output_dir = Path('outputs/relatorios_pdf')
    output_dir.mkdir(parents=True, exist_ok=True)

    arquivos_gerados = []

    if 'REGIAO' not in df.columns:
        print("  ⚠ Coluna REGIAO não encontrada no DataFrame")
        return arquivos_gerados

    regioes = df['REGIAO'].dropna().unique()

    for regiao in sorted(regioes):
        df_regiao = df[df['REGIAO'] == regiao].copy()

        if len(df_regiao) == 0:
            continue

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        nome_arquivo = f'relatorio_regional_{regiao.replace(" ", "_")}_{mes:02d}_{ano}_{timestamp}.pdf'
        arquivo_pdf = output_dir / nome_arquivo

        doc = SimpleDocTemplate(
            str(arquivo_pdf),
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )

        elementos = []

        elementos.extend(criar_capa_regional(regiao, mes, ano))
        elementos.extend(criar_resumo_regiao(df_regiao, regiao, df_metas))
        elementos.append(PageBreak())
        elementos.extend(criar_top_lojas_regiao(df_regiao))
        elementos.extend(criar_top_consultores_regiao(df_regiao))
        elementos.extend(criar_produtos_regiao(df_regiao))

        doc.build(
            elementos,
            onFirstPage=criar_rodape,
            onLaterPages=criar_rodape,
        )

        arquivos_gerados.append(str(arquivo_pdf))
        print(f"  ✓ Relatório regional gerado: {regiao}")

    return arquivos_gerados
