"""
Configurações do projeto de análise de vendas.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

DATA_DIR_DIGITACAO = BASE_DIR / os.getenv('DATA_DIR_DIGITACAO', 'digitacao')
DATA_DIR_METAS = BASE_DIR / os.getenv('DATA_DIR_METAS', 'metas')
DATA_DIR_TABELAS = BASE_DIR / os.getenv('DATA_DIR_TABELAS', 'tabelas')
DATA_DIR_CONFIGURACAO = BASE_DIR / os.getenv(
    'DATA_DIR_CONFIGURACAO',
    'configuracao'
)

OUTPUT_DIR_EXCEL = BASE_DIR / os.getenv(
    'OUTPUT_DIR_EXCEL',
    'outputs/relatorios_excel'
)
OUTPUT_DIR_PDF_EXECUTIVO = BASE_DIR / os.getenv(
    'OUTPUT_DIR_PDF_EXECUTIVO',
    'outputs/relatorios_pdf/executivos'
)
OUTPUT_DIR_PDF_DETALHADO = BASE_DIR / os.getenv(
    'OUTPUT_DIR_PDF_DETALHADO',
    'outputs/relatorios_pdf/detalhados'
)

LOCALE = os.getenv('LOCALE', 'pt_BR.UTF-8')
CURRENCY_SYMBOL = os.getenv('CURRENCY_SYMBOL', 'R$')
DATE_FORMAT = os.getenv('DATE_FORMAT', '%d/%m/%Y')

DASHBOARD_TITLE = os.getenv(
    'DASHBOARD_TITLE',
    'Dashboard de Análise de Vendas'
)
DASHBOARD_ICON = os.getenv('DASHBOARD_ICON', '📊')
DASHBOARD_LAYOUT = os.getenv('DASHBOARD_LAYOUT', 'wide')

CACHE_TTL = int(os.getenv('CACHE_TTL', '3600'))

PDF_COMPANY_NAME = os.getenv('PDF_COMPANY_NAME', 'Empresa')
PDF_LOGO_PATH = os.getenv('PDF_LOGO_PATH', '')

COLUNAS_TIPO_OPER = 'TIPO OPER.'
COLUNA_SUBTIPO = 'SUBTIPO'

TIPO_OPER_CARTAO_BENEFICIO = 'CARTÃO BENEFICIO'
TIPO_OPER_VENDA_PRE_ADESAO = 'Venda Pré-Adesão'
TIPO_OPER_BMG_MED = 'BMG MED'
TIPO_OPER_SEGURO = 'Seguro'

SUBTIPO_SUPER_CONTA = 'SUPER CONTA'

MESES_PT = {
    1: 'Janeiro',
    2: 'Fevereiro',
    3: 'Março',
    4: 'Abril',
    5: 'Maio',
    6: 'Junho',
    7: 'Julho',
    8: 'Agosto',
    9: 'Setembro',
    10: 'Outubro',
    11: 'Novembro',
    12: 'Dezembro'
}

MESES_ARQUIVO = {
    1: 'janeiro', 2: 'fevereiro', 3: 'marco', 4: 'abril',
    5: 'maio', 6: 'junho', 7: 'julho', 8: 'agosto',
    9: 'setembro', 10: 'outubro', 11: 'novembro',
    12: 'dezembro'
}

MAPEAMENTO_PRODUTOS = {
    'CNC': ['CNC'],
    'SAQUE': ['SAQUE', 'SAQUE BENEFICIO'],
    'CLT': ['CONSIG PRIV'],
    'CONSIGNADO': ['CONSIG', 'Portabilidade'],
    'PACK': ['FGTS', 'CNC 13º']
}

MAPEAMENTO_COLUNAS_META = {
    'CNC': 'CNC LOJA',
    'SAQUE': 'SAQUE LOJA',
    'CLT': 'CLT',
    'CONSIGNADO': 'CONSIGNADO',
    'PACK': 'META  LOJA FGTS & ANT. BEN.13º'
}

PRODUTOS_EMISSAO = ['EMISSAO', 'EMISSAO CC', 'EMISSAO CB']

LISTA_PRODUTOS = ['CNC', 'SAQUE', 'CLT', 'CONSIGNADO', 'PACK']
