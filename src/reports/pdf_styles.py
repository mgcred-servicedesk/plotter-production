"""
Estilos centralizados para relatórios PDF.

Define paleta de cores, estilos de tabela, cabeçalhos, rodapé
e configurações de documento padronizadas.
"""
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import TableStyle


CORES = {
    'primary': '#1F4E78',
    'primary_light': '#366092',
    'accent': '#4472C4',
    'success': '#28A745',
    'danger': '#DC3545',
    'warning': '#FFC107',
    'info': '#17A2B8',
    'secondary': '#6C757D',
    'light': '#F8F9FA',
    'dark': '#343A40',
    'zebra': '#F8F9FA',
    'total_bg': '#E7E6E6',
    'header_bg': '#1F4E78',
}

MARGENS_PADRAO = {
    'rightMargin': 2 * cm,
    'leftMargin': 2 * cm,
    'topMargin': 2 * cm,
    'bottomMargin': 2 * cm,
}

MARGENS_COMPACTAS = {
    'rightMargin': 1.5 * cm,
    'leftMargin': 1.5 * cm,
    'topMargin': 1.5 * cm,
    'bottomMargin': 1.5 * cm,
}


def get_titulo_style(font_size=20):
    """Retorna estilo de titulo principal."""
    styles = getSampleStyleSheet()
    return ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=font_size,
        textColor=colors.HexColor(CORES['primary']),
        spaceAfter=20,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )


def get_subtitulo_style(font_size=14):
    """Retorna estilo de subtitulo."""
    styles = getSampleStyleSheet()
    return ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=font_size,
        textColor=colors.HexColor(CORES['secondary']),
        spaceAfter=20,
        alignment=TA_CENTER,
        fontName='Helvetica'
    )


def get_secao_style(font_size=14):
    """Retorna estilo de titulo de secao."""
    styles = getSampleStyleSheet()
    return ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontSize=font_size,
        textColor=colors.HexColor(CORES['primary']),
        spaceAfter=10,
        fontName='Helvetica-Bold'
    )


def get_regiao_style(font_size=14):
    """Retorna estilo para titulo de regiao (fundo colorido)."""
    styles = getSampleStyleSheet()
    return ParagraphStyle(
        'RegionTitle',
        parent=styles['Heading2'],
        fontSize=font_size,
        textColor=colors.whitesmoke,
        backColor=colors.HexColor(CORES['primary']),
        spaceAfter=12,
        alignment=TA_CENTER,
        leftIndent=10,
        rightIndent=10
    )


def get_table_style_moderno(
    fonte_cabecalho=10,
    fonte_corpo=8,
    cor_cabecalho=None
):
    """
    Retorna estilo moderno para tabelas PDF.

    Usa zebra-striping e bordas suaves.

    Args:
        fonte_cabecalho: Tamanho da fonte do cabecalho.
        fonte_corpo: Tamanho da fonte do corpo.
        cor_cabecalho: Cor hex do cabecalho (padrao: primary).

    Returns:
        TableStyle configurado.
    """
    if cor_cabecalho is None:
        cor_cabecalho = CORES['primary']

    return TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0),
         colors.HexColor(cor_cabecalho)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), fonte_cabecalho),
        ('FONTSIZE', (0, 1), (-1, -1), fonte_corpo),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.white, colors.HexColor(CORES['zebra'])]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ])


def get_table_style_com_total(
    fonte_cabecalho=10,
    fonte_corpo=8,
    cor_cabecalho=None
):
    """
    Retorna estilo moderno com destaque na linha de total.

    Args:
        fonte_cabecalho: Tamanho da fonte do cabecalho.
        fonte_corpo: Tamanho da fonte do corpo.
        cor_cabecalho: Cor hex do cabecalho (padrao: primary).

    Returns:
        TableStyle configurado.
    """
    if cor_cabecalho is None:
        cor_cabecalho = CORES['primary']

    return TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0),
         colors.HexColor(cor_cabecalho)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), fonte_cabecalho),
        ('FONTSIZE', (0, 1), (-1, -1), fonte_corpo),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2),
         [colors.white, colors.HexColor(CORES['zebra'])]),
        ('BACKGROUND', (0, -1), (-1, -1),
         colors.HexColor(CORES['total_bg'])),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ])


def get_table_style_kpi(cor_cabecalho=None):
    """Retorna estilo para tabelas de KPI (metrica/valor)."""
    if cor_cabecalho is None:
        cor_cabecalho = CORES['primary']

    return TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0),
         colors.HexColor(cor_cabecalho)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.white, colors.HexColor(CORES['zebra'])]),
    ])


def criar_rodape(canvas, doc):
    """
    Cria rodape com numero de pagina e data de geracao.

    Uso: doc.build(elementos,
                   onFirstPage=criar_rodape,
                   onLaterPages=criar_rodape)
    """
    canvas.saveState()

    page_num = canvas.getPageNumber()
    text = f"Pagina {page_num}"
    canvas.setFont('Helvetica', 9)
    canvas.drawRightString(A4[0] - 2 * cm, 1.5 * cm, text)

    data_geracao = datetime.now().strftime("%d/%m/%Y %H:%M")
    canvas.drawString(2 * cm, 1.5 * cm, f"Gerado em: {data_geracao}")

    canvas.restoreState()
