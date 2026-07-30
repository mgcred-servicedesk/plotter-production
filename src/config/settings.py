"""
Constantes de domínio do dashboard.

Formatação PT-BR vive em `src/dashboard/formatters.py`; a taxonomia de
produto (grupos, metas, flags) e os feriados/períodos vêm do Supabase
(`categorias_produto`, `feriados`, `periodos`). Este módulo guarda apenas
constantes que não têm fonte no banco.
"""

# Produtos de emissão (CARTÃO/Pré-Adesão) — contam só como quantidade.
PRODUTOS_EMISSAO = ['EMISSAO', 'EMISSAO CC', 'EMISSAO CB']

# Desmembramento do grupo 'PACK' nas suas três categorias. A chave é o
# `categoria_codigo` (verdade dos contratos / RPCs); o valor é o rótulo
# exibido — o mesmo texto do tipo na planilha de origem (coluna "Produto"
# = `TIPO_PRODUTO`). Espelha `PRODUTOS_DASHBOARD['FGTS_ANT_BEN_CNC13']`
# (src/dashboard/kpis/gerais.py). Consumido via
# `src.dashboard.kpis.produtos.adicionar_produto_detalhado`.
PACK_SPLIT_LABELS = {
    'FGTS': 'FGTS',
    'ANT_BENEF': 'ANT. DE BENEF.',
    'CNC_13': 'CNC 13º',
}

# Rótulo do PACK agregado — usado onde o pack NÃO é desmembrado, isto é,
# nas superfícies que comparam valor × meta (a meta `FGTS_ANT_BENEF_13`
# é conjunta, não existe alvo por categoria). Deriva dos mesmos nomes do
# desmembramento para que as duas leituras usem o mesmo vocabulário.
PACK_LABEL_AGREGADO = ' / '.join(PACK_SPLIT_LABELS.values())

# Mapeamento de nomes de display para grupo_dashboard.
# Substitui labels internos por nomes amigáveis na interface
# sem alterar chaves de dados ou banco.
NOMES_DISPLAY_PRODUTO = {
    'PACK': PACK_LABEL_AGREGADO,
}
