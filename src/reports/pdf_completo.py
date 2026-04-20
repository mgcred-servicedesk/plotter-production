"""
Gerador de Relatório PDF Completo com todos os dados detalhados.
Equivalente ao relatório Excel com todas as informações organizadas.
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
from src.reports.pdf_styles import (
    MARGENS_COMPACTAS,
    criar_rodape,
    get_secao_style,
    get_table_style_moderno,
    get_titulo_style,
)
from src.reports.resumo_geral import criar_resumo_geral


def criar_cabecalho_completo(mes, ano):
    """Cria cabeçalho do relatório completo."""
    elementos = []

    logo_path = Path('assets/logotipo-mg-cred.png')
    if logo_path.exists():
        logo = Image(str(logo_path), width=5*cm, height=2.5*cm)
        elementos.append(logo)
        elementos.append(Spacer(1, 0.5*cm))

    titulo_style = get_titulo_style(20)

    titulo = Paragraph(
        f"RELATÓRIO COMPLETO DE VENDAS - {MESES_PT[mes]}/{ano}",
        titulo_style
    )
    elementos.append(titulo)
    elementos.append(Spacer(1, 0.5*cm))

    return elementos


def criar_secao_totais_gerais(resumo):
    """Cria seção com totais gerais consolidados."""
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

    elementos.append(Paragraph("RESUMO GERAL CONSOLIDADO", titulo_style))
    elementos.append(Spacer(1, 0.3*cm))

    totais = resumo.get('totais_gerais', pd.DataFrame())
    if not totais.empty:
        dados_tabela = [['Métrica', 'Valor']]

        for _, row in totais.iterrows():
            metrica = str(row['Métrica'])
            valor = row['Valor']

            if 'R$' in metrica or 'Valor' in metrica or 'Ticket' in metrica:
                valor_fmt = formatar_moeda(valor)
            elif '%' in metrica:
                valor_fmt = formatar_percentual(valor)
            else:
                valor_fmt = formatar_numero(valor)

            dados_tabela.append([metrica, valor_fmt])

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


def criar_secao_ranking(titulo, df, colunas_exibir, larguras=None):
    """Cria seção genérica de ranking."""
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

    elementos.append(Paragraph(titulo, titulo_style))
    elementos.append(Spacer(1, 0.3*cm))

    if df.empty:
        elementos.append(Paragraph("Sem dados disponíveis", styles['Normal']))
        elementos.append(Spacer(1, 0.5*cm))
        return elementos

    if larguras is None:
        largura_total = 18
        larguras = [largura_total / len(colunas_exibir) * cm
                    for _ in colunas_exibir]

    dados_tabela = [colunas_exibir]

    for _, row in df.iterrows():
        linha = []
        for col in colunas_exibir:
            if col not in row.index:
                linha.append('-')
                continue

            valor = row[col]

            if pd.isna(valor):
                linha.append('-')
            elif 'Posição' in col or 'Qtd' in col:
                linha.append(formatar_numero(valor))
            elif 'Valor' in col or 'Ticket' in col or 'Média DU' in col:
                linha.append(formatar_moeda(valor))
            elif 'Pontos' in col or 'Meta' in col:
                linha.append(formatar_numero(valor))
            elif '%' in col or 'Atingimento' in col:
                linha.append(formatar_percentual(valor))
            else:
                texto = str(valor)
                if 'Consultor' in col or 'Loja' in col:
                    texto = texto[:18]
                else:
                    texto = texto[:25]
                linha.append(texto)

        dados_tabela.append(linha)

    tabela = Table(dados_tabela, colWidths=larguras)
    
    fonte_cabecalho = 8 if 'Consultor' in titulo else 9
    fonte_corpo = 6 if 'Consultor' in titulo else 8
    
    tabela.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F4E78')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), fonte_cabecalho),
        ('FONTSIZE', (0, 1), (-1, -1), fonte_corpo),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.white, colors.HexColor('#F8F9FA')]),
    ]))

    elementos.append(tabela)
    elementos.append(Spacer(1, 0.5*cm))

    return elementos


def criar_todas_secoes_rankings(resumo):
    """Cria todas as seções de rankings do relatório."""
    elementos = []

    elementos.extend(criar_secao_ranking(
        "TOP 10 LOJAS - POR PONTOS",
        resumo.get('top_lojas', pd.DataFrame()),
        ['Posição', 'Loja', 'Qtd', 'Valor', 'Pontos', 'Ticket Médio'],
        [2*cm, 5*cm, 2.5*cm, 3*cm, 3*cm, 3*cm]
    ))

    elementos.extend(criar_secao_ranking(
        "TOP 10 LOJAS - POR TICKET MÉDIO",
        resumo.get('top_lojas_ticket_medio', pd.DataFrame()),
        ['Posição', 'Loja', 'Qtd', 'Valor', 'Pontos', 'Ticket Médio'],
        [2*cm, 5*cm, 2.5*cm, 3*cm, 3*cm, 3*cm]
    ))

    elementos.append(PageBreak())

    elementos.extend(criar_secao_ranking(
        "TOP 10 LOJAS - POR MÉDIA DU",
        resumo.get('top_lojas_media_du', pd.DataFrame()),
        ['Posição', 'Loja', 'Qtd', 'Pontos', 'Média DU', 'Ticket Médio'],
        [2*cm, 5*cm, 2.5*cm, 3*cm, 3*cm, 3*cm]
    ))

    elementos.extend(criar_secao_ranking(
        "TOP 10 LOJAS - POR ATINGIMENTO META PRATA",
        resumo.get('top_lojas_atingimento', pd.DataFrame()),
        ['Posição', 'Loja', 'Pontos', 'Meta Prata', 'Atingimento %'],
        [2*cm, 6*cm, 3*cm, 3*cm, 3*cm]
    ))

    elementos.append(PageBreak())

    elementos.extend(criar_secao_ranking(
        "TOP 10 CONSULTORES - POR PONTOS",
        resumo.get('top_consultores', pd.DataFrame()),
        ['Posição', 'Consultor', 'Loja', 'Qtd', 'Pontos', 'Ticket Médio'],
        [1.5*cm, 5*cm, 3*cm, 2*cm, 3*cm, 3*cm]
    ))

    elementos.extend(criar_secao_ranking(
        "TOP 10 CONSULTORES - POR TICKET MÉDIO",
        resumo.get('top_consultores_ticket_medio', pd.DataFrame()),
        ['Posição', 'Consultor', 'Loja', 'Qtd', 'Pontos', 'Ticket Médio'],
        [1.5*cm, 5*cm, 3*cm, 2*cm, 3*cm, 3*cm]
    ))

    elementos.append(PageBreak())

    elementos.extend(criar_secao_ranking(
        "TOP 10 CONSULTORES - POR MÉDIA DU",
        resumo.get('top_consultores_media_du', pd.DataFrame()),
        ['Posição', 'Consultor', 'Loja', 'Pontos', 'Média DU'],
        [1.5*cm, 6*cm, 3*cm, 3*cm, 3*cm]
    ))

    elementos.extend(criar_secao_ranking(
        "TOP 10 CONSULTORES - POR ATINGIMENTO META PRATA",
        resumo.get('top_consultores_atingimento', pd.DataFrame()),
        ['Posição', 'Consultor', 'Loja', 'Pontos', 'Meta Prata', 'Atingimento %'],
        [1.5*cm, 5*cm, 3*cm, 3*cm, 2.5*cm, 2.5*cm]
    ))

    elementos.append(PageBreak())

    elementos.extend(criar_secao_ranking(
        "RANKING DE REGIÃO - POR PONTOS",
        resumo.get('ranking_regiao_pontos', pd.DataFrame()),
        ['Posição', 'Região', 'Qtd', 'Valor', 'Pontos', 'Ticket Médio'],
        [2*cm, 4*cm, 2.5*cm, 3*cm, 3*cm, 3*cm]
    ))

    elementos.extend(criar_secao_ranking(
        "RANKING DE REGIÃO - POR TICKET MÉDIO",
        resumo.get('ranking_regiao_ticket_medio', pd.DataFrame()),
        ['Posição', 'Região', 'Qtd', 'Pontos', 'Ticket Médio'],
        [2*cm, 5*cm, 3*cm, 3*cm, 3*cm]
    ))

    elementos.append(PageBreak())

    elementos.extend(criar_secao_ranking(
        "RANKING DE REGIÃO - POR MÉDIA DU",
        resumo.get('ranking_regiao_media_du', pd.DataFrame()),
        ['Posição', 'Região', 'Pontos', 'Média DU', 'Ticket Médio'],
        [2*cm, 5*cm, 3*cm, 3*cm, 3*cm]
    ))

    elementos.extend(criar_secao_ranking(
        "RANKING DE REGIÃO - POR ATINGIMENTO META PRATA",
        resumo.get('ranking_regiao_atingimento', pd.DataFrame()),
        ['Posição', 'Região', 'Pontos', 'Meta Prata', 'Atingimento %'],
        [2*cm, 5*cm, 3*cm, 3*cm, 3*cm]
    ))

    elementos.append(PageBreak())

    resumo_produtos = resumo.get('resumo_produtos_mix', pd.DataFrame())
    if not resumo_produtos.empty:
        elementos.extend(criar_secao_ranking(
            "RESUMO POR PRODUTO (MIX)",
            resumo_produtos,
            ['Produto', 'Qtd', 'Valor', 'Pontos', 'Ticket Médio'],
            [4*cm, 3*cm, 4*cm, 4*cm, 3*cm]
        ))
        
        styles = getSampleStyleSheet()
        nota = Paragraph(
            "<i>* PACK = FGTS, ANT. BEN. e CNC 13º</i>",
            styles['Normal']
        )
        elementos.append(nota)
        elementos.append(Spacer(1, 0.5*cm))

    resumo_regiao = resumo.get('resumo_por_regiao', pd.DataFrame())
    if not resumo_regiao.empty:
        elementos.extend(criar_secao_ranking(
            "RESUMO POR REGIÃO",
            resumo_regiao,
            ['Região', 'Qtd', 'Valor', 'Pontos', 'Atingimento %'],
            [4*cm, 3*cm, 4*cm, 4*cm, 3*cm]
        ))

    return elementos


def gerar_relatorio_completo_pdf(df, mes, ano, df_metas, dia_atual=None, df_supervisores=None):
    """
    Gera relatório PDF completo com todos os dados detalhados.

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
    arquivo_pdf = output_dir / f'relatorio_completo_{mes:02d}_{ano}_{timestamp}.pdf'

    doc = SimpleDocTemplate(
        str(arquivo_pdf),
        pagesize=A4,
        rightMargin=1.5*cm,
        leftMargin=1.5*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )

    elementos = []

    resumo = criar_resumo_geral(df, df_metas, ano, mes, dia_atual, df_supervisores)

    elementos.extend(criar_cabecalho_completo(mes, ano))
    elementos.extend(criar_secao_totais_gerais(resumo))
    elementos.append(PageBreak())
    elementos.extend(criar_todas_secoes_rankings(resumo))

    doc.build(
        elementos,
        onFirstPage=criar_rodape,
        onLaterPages=criar_rodape,
    )

    return str(arquivo_pdf)
