"""
Constantes de domínio do dashboard.

Formatação PT-BR vive em `src/dashboard/formatters.py`; a taxonomia de
produto (grupos, metas, flags) e os feriados/períodos vêm do Supabase
(`categorias_produto`, `feriados`, `periodos`). Este módulo guarda apenas
constantes que não têm fonte no banco.
"""

# Produtos de emissão (CARTÃO/Pré-Adesão) — contam só como quantidade.
PRODUTOS_EMISSAO = ['EMISSAO', 'EMISSAO CC', 'EMISSAO CB']

# Mapeamento de nomes de display para grupo_dashboard.
# Substitui labels internos por nomes amigáveis na interface
# sem alterar chaves de dados ou banco.
NOMES_DISPLAY_PRODUTO = {
    'PACK': 'FGTS/Ant. Ben./CNC 13o',
}
