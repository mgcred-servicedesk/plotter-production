"""
Gerador de Relatório PDF Executivo com KPIs e visualizações.
Focado em alta gestão com análises visuais e insights principais.
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

from src.config.settings import MESES_PT
from src.reports.formatters import (
    formatar_moeda,
    formatar_numero,
    formatar_percentual,
)
from src.reports.pdf_charts import (
    criar_grafico_atingimento,
    criar_grafico_barras_regioes,
    criar_grafico_barras_top10,
    criar_grafico_evolucao_diaria,
    criar_grafico_pizza_produtos,
    criar_kpi_card_image,
)
from src.reports.pdf_styles import (
    CORES,
    MARGENS_PADRAO,
    criar_rodape,
    get_table_style_moderno,
    get_titulo_style,
    get_subtitulo_style,
    get_secao_style,
)
from src.reports.resumo_geral import criar_resumo_geral
from src.reports.tabela_produtos import calcular_dias_uteis


def criar_capa_executiva(mes, ano, resumo):
    """Cria a página de capa do relatório executivo."""
    elementos = []

    titulo_style = get_titulo_style(24)
    subtitulo_style = get_subtitulo_style(16)

    elementos.append(Spacer(1, 2*cm))
    
    logo_path = Path('assets/logotipo-mg-cred.png')
    if logo_path.exists():
        logo = Image(str(logo_path), width=6*cm, height=3*cm)
        elementos.append(logo)
        elementos.append(Spacer(1, 1*cm))

    titulo = Paragraph(
        "RELATÓRIO EXECUTIVO DE VENDAS",
        titulo_style
    )
    elementos.append(titulo)

    subtitulo = Paragraph(
        f"{MESES_PT[mes]} de {ano}",
        subtitulo_style
    )
    elementos.append(subtitulo)

    elementos.append(Spacer(1, 2*cm))

    totais = resumo.get('totais_gerais', pd.DataFrame())
    if not totais.empty:
        atingimento = totais[totais['Métrica'] == 'Atingimento (%)'][
            'Valor'
        ].values
        expectativa = totais[totais['Métrica'] == 'Expectativa (%)'][
            'Valor'
        ].values

        atingimento_val = atingimento[0] if len(atingimento) > 0 else 0
        expectativa_val = expectativa[0] if len(expectativa) > 0 else 0

        kpi_data = [
            ['INDICADORES PRINCIPAIS', '', ''],
            [
                'Atingimento Atual',
                'Expectativa (Projeção)',
                'Status'
            ],
            [
                formatar_percentual(atingimento_val),
                formatar_percentual(expectativa_val),
                '✓ No Prazo' if atingimento_val >= 30 else '⚠ Atenção'
            ]
        ]

        kpi_table = Table(kpi_data, colWidths=[6*cm, 6*cm, 6*cm])
        kpi_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F4E78')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#E8F4F8')),
            ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 1), (-1, -1), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 2), (-1, -1), [colors.white]),
        ]))

        elementos.append(kpi_table)

    elementos.append(Spacer(1, 2*cm))

    data_geracao = Paragraph(
        f"Gerado em: {datetime.now().strftime('%d/%m/%Y às %H:%M')}",
        subtitulo_style
    )
    elementos.append(data_geracao)

    elementos.append(PageBreak())

    return elementos


def criar_dashboard_performance(resumo, df):
    """Cria página de dashboard com gráficos de performance."""
    elementos = []
    styles = getSampleStyleSheet()

    titulo_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1F4E78'),
        spaceAfter=20,
        fontName='Helvetica-Bold'
    )

    elementos.append(Paragraph("Dashboard de Performance", titulo_style))
    elementos.append(Spacer(1, 0.5*cm))

    totais = resumo.get('totais_gerais', pd.DataFrame())
    if not totais.empty:
        atingimento = totais[totais['Métrica'] == 'Atingimento (%)'][
            'Valor'
        ].values
        expectativa = totais[totais['Métrica'] == 'Expectativa (%)'][
            'Valor'
        ].values
        meta_total = totais[totais['Métrica'] == 'Meta Total'][
            'Valor'
        ].values

        atingimento_val = atingimento[0] if len(atingimento) > 0 else 0
        expectativa_val = expectativa[0] if len(expectativa) > 0 else 0
        meta_val = meta_total[0] if len(meta_total) > 0 else 0

        grafico_atingimento = criar_grafico_atingimento(
            atingimento_val,
            expectativa_val,
            meta_val
        )

        img = Image(grafico_atingimento, width=16*cm, height=6*cm)
        elementos.append(img)
        elementos.append(Spacer(1, 1*cm))

    if 'DATA' in df.columns and 'pontos' in df.columns:
        grafico_evolucao = criar_grafico_evolucao_diaria(
            df,
            'DATA',
            'pontos',
            'Evolução Diária de Pontos'
        )

        img_evolucao = Image(grafico_evolucao, width=16*cm, height=7*cm)
        elementos.append(img_evolucao)

    elementos.append(PageBreak())

    return elementos


def criar_pagina_top_lojas(resumo):
    """Cria página com TOP 10 Lojas."""
    elementos = []
    styles = getSampleStyleSheet()

    titulo_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1F4E78'),
        spaceAfter=20,
        fontName='Helvetica-Bold'
    )

    elementos.append(Paragraph("TOP 10 Lojas", titulo_style))
    elementos.append(Spacer(1, 0.5*cm))

    top_lojas = resumo.get('top_lojas', pd.DataFrame())
    if not top_lojas.empty:
        grafico = criar_grafico_barras_top10(
            top_lojas,
            'Loja',
            'Pontos',
            'TOP 10 Lojas por Pontos',
            '#1F4E78'
        )

        img = Image(grafico, width=16*cm, height=8*cm)
        elementos.append(img)
        elementos.append(Spacer(1, 0.5*cm))

        dados_tabela = [['Pos', 'Loja', 'Qtd', 'Pontos', 'Ticket Médio']]

        for _, row in top_lojas.head(10).iterrows():
            dados_tabela.append([
                str(int(row['Posição'])),
                str(row['Loja'])[:20],
                formatar_numero(row['Qtd']),
                formatar_numero(row['Pontos']),
                formatar_moeda(row['Ticket Médio'])
            ])

        tabela = Table(dados_tabela, colWidths=[1.5*cm, 5*cm, 2.5*cm, 3.5*cm, 3.5*cm])
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


def criar_pagina_top_consultores(resumo):
    """Cria página com TOP 10 Consultores."""
    elementos = []
    styles = getSampleStyleSheet()

    titulo_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1F4E78'),
        spaceAfter=20,
        fontName='Helvetica-Bold'
    )

    elementos.append(Paragraph("TOP 10 Consultores", titulo_style))
    elementos.append(Spacer(1, 0.5*cm))

    top_consultores = resumo.get('top_consultores', pd.DataFrame())
    if not top_consultores.empty:
        grafico = criar_grafico_barras_top10(
            top_consultores,
            'Consultor',
            'Pontos',
            'TOP 10 Consultores por Pontos',
            '#28A745'
        )

        img = Image(grafico, width=16*cm, height=8*cm)
        elementos.append(img)
        elementos.append(Spacer(1, 0.5*cm))

        dados_tabela = [[
            'Pos', 'Consultor', 'Loja', 'Qtd', 'Pontos', 'Ticket Médio'
        ]]

        for _, row in top_consultores.head(10).iterrows():
            dados_tabela.append([
                str(int(row['Posição'])),
                str(row['Consultor'])[:20],
                str(row['Loja'])[:15],
                formatar_numero(row['Qtd']),
                formatar_numero(row['Pontos']),
                formatar_moeda(row['Ticket Médio'])
            ])

        tabela = Table(
            dados_tabela,
            colWidths=[1.2*cm, 4.5*cm, 2.8*cm, 2*cm, 2.8*cm, 2.8*cm]
        )
        tabela.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#28A745')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1),
             [colors.white, colors.HexColor('#F8F9FA')]),
        ]))

        elementos.append(tabela)

    elementos.append(PageBreak())

    return elementos


def criar_pagina_produtos(resumo):
    """Cria página com análise por produto."""
    elementos = []
    styles = getSampleStyleSheet()

    titulo_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1F4E78'),
        spaceAfter=20,
        fontName='Helvetica-Bold'
    )

    elementos.append(Paragraph("Análise por Produto (MIX)", titulo_style))
    elementos.append(Spacer(1, 0.5*cm))

    resumo_produtos = resumo.get('resumo_produtos_mix', pd.DataFrame())
    if not resumo_produtos.empty:
        grafico = criar_grafico_pizza_produtos(
            resumo_produtos,
            'Distribuição de Pontos por Produto'
        )

        img = Image(grafico, width=14*cm, height=10*cm)
        elementos.append(img)
        elementos.append(Spacer(1, 0.5*cm))

        dados_tabela = [['Produto', 'Qtd', 'Valor', 'Pontos', '%']]

        total_pontos = resumo_produtos['Pontos'].sum()

        for _, row in resumo_produtos.iterrows():
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

    elementos.append(PageBreak())

    return elementos


def criar_pagina_regioes(resumo):
    """Cria página com ranking de regiões."""
    elementos = []
    styles = getSampleStyleSheet()

    titulo_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1F4E78'),
        spaceAfter=20,
        fontName='Helvetica-Bold'
    )

    elementos.append(Paragraph("Ranking de Regiões", titulo_style))
    elementos.append(Spacer(1, 0.5*cm))

    resumo_regiao = resumo.get('resumo_por_regiao', pd.DataFrame())
    if not resumo_regiao.empty:
        grafico = criar_grafico_barras_regioes(
            resumo_regiao,
            'Performance por Região'
        )

        img = Image(grafico, width=16*cm, height=8*cm)
        elementos.append(img)
        elementos.append(Spacer(1, 0.5*cm))

        dados_tabela = [[
            'Região', 'Qtd', 'Pontos', 'Meta', 'Ating %', 'Ticket Médio'
        ]]

        for _, row in resumo_regiao.iterrows():
            dados_tabela.append([
                str(row['Região']),
                formatar_numero(row['Qtd']),
                formatar_numero(row['Pontos']),
                formatar_numero(row.get('Meta', 0)),
                formatar_percentual(row.get('Atingimento %', 0)),
                formatar_moeda(row['Ticket Médio'])
            ])

        tabela = Table(
            dados_tabela,
            colWidths=[4*cm, 2.5*cm, 3*cm, 3*cm, 2.5*cm, 3*cm]
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

    return elementos


def gerar_relatorio_executivo_pdf(df, mes, ano, df_metas, dia_atual=None, df_supervisores=None):
    """
    Gera relatório PDF executivo com KPIs e visualizações.

    Args:
        df: DataFrame com dados consolidados
        mes: Mês do relatório
        ano: Ano do relatório
        df_metas: DataFrame com metas
        dia_atual: Dia atual para cálculo de dias úteis
        df_supervisores: DataFrame com supervisores (opcional)

    Returns:
        Caminho do arquivo PDF gerado
    """
    output_dir = Path('outputs/relatorios_pdf')
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    arquivo_pdf = output_dir / f'relatorio_executivo_{mes:02d}_{ano}_{timestamp}.pdf'

    doc = SimpleDocTemplate(
        str(arquivo_pdf),
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )

    elementos = []

    dias_uteis_info = calcular_dias_uteis(ano, mes, dia_atual)
    resumo = criar_resumo_geral(df, df_metas, ano, mes, dia_atual, df_supervisores)

    elementos.extend(criar_capa_executiva(mes, ano, resumo))
    elementos.extend(criar_dashboard_performance(resumo, df))
    elementos.extend(criar_pagina_top_lojas(resumo))
    elementos.extend(criar_pagina_top_consultores(resumo))
    elementos.extend(criar_pagina_produtos(resumo))
    elementos.extend(criar_pagina_regioes(resumo))

    doc.build(
        elementos,
        onFirstPage=criar_rodape,
        onLaterPages=criar_rodape,
    )

    return str(arquivo_pdf)
