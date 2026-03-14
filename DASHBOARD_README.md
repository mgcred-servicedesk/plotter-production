# 📊 Dashboard de Vendas - MGCred

## Visão Geral

Dashboard interativo desenvolvido com Streamlit que integra todos os cálculos e KPIs dos relatórios Excel e PDF, proporcionando uma análise completa e em tempo real da performance de vendas.

## 🚀 Como Executar

### Opção 1: Dashboard Refatorado (Recomendado)
```bash
streamlit run dashboard_refatorado.py
```

### Opção 2: Dashboard Original
```bash
streamlit run dashboard.py
```

## 📋 Funcionalidades

### 1. **Indicadores Principais** (Topo da Página)

#### Primeira Linha de KPIs:
- **💰 Total de Vendas**: Valor total realizado com % de atingimento da meta prata
- **🎯 Meta Prata**: Meta principal do mês com dias úteis restantes
- **📈 Projeção**: Projeção de fim de mês com % da meta
- **📅 Média por DU**: Média diária com meta diária de referência
- **⭐ Total de Pontos**: Pontuação total com número de lojas

#### Segunda Linha de KPIs:
- **🏆 Meta Ouro**: Meta desafio com % de atingimento
- **🎫 Ticket Médio**: Valor médio por transação
- **👥 Consultores**: Número de consultores ativos
- **📊 Produtividade**: Vendas por consultor

### 2. **Aba: 📊 Produtos**

Análise completa de todos os produtos (CNC, SAQUE, CLT, CONSIGNADO, PACK):

#### Gráficos:
1. **Realizado vs Meta**: Comparação visual de performance
2. **% Atingimento por Produto**: Indicador de sucesso (verde ≥100%, vermelho <100%)
3. **Projeção vs Meta**: Previsão de fim de mês
4. **Ticket Médio por Produto**: Análise de valor médio

#### Tabela de KPIs por Produto:
- Valor realizado
- Meta do produto
- **Meta Diária** (novo!)
- % Atingimento
- Quantidade de vendas
- Ticket Médio
- Média por DU
- Projeção
- % Projeção

### 3. **Aba: 🗺️ Regiões**

Análise regional completa:

#### Gráficos:
- **Valor por Região**: Ranking de performance
- **% Atingimento por Região**: Indicador de sucesso regional

#### Tabela de KPIs por Região:
- Valor total
- Pontos totais
- Meta Prata
- % Atingimento
- Número de lojas
- Número de consultores
- Média por DU
- Projeção

### 4. **Aba: 🏆 Rankings**

Rankings de performance com base em atingimento de metas:

#### Top 10 Lojas por Atingimento:
- Posição no ranking
- Nome da loja
- Região
- Quantidade de vendas
- Valor total
- Pontos
- Meta Prata
- **% Atingimento** (critério de ordenação)
- Ticket Médio

#### Top 10 Consultores por Atingimento:
- Posição no ranking
- Nome do consultor
- Loja
- Quantidade de vendas
- Valor total
- Pontos
- Meta Prata (proporcional)
- **% Atingimento** (critério de ordenação)
- Ticket Médio

### 5. **Aba: 📈 Evolução**

Análise temporal de vendas:

#### Gráficos:
1. **Evolução Diária de Vendas**: Barras com vendas por dia
2. **Evolução Acumulada vs Meta**: Linha acumulada com referências de meta e projeção

#### Métricas de Evolução:
- **🌟 Melhor Dia**: Dia com maior volume de vendas
- **📊 Média Diária**: Média de vendas por dia
- **✅ Dias Acima da Meta**: Quantidade e % de dias que superaram a meta diária

### 6. **Aba: 📋 Detalhes**

Visualização detalhada dos dados com filtros:

#### Filtros Disponíveis:
- Loja específica
- Região
- Tipo de produto

#### Métricas do Filtro:
- Total de valor filtrado
- Total de pontos filtrados
- Ticket médio do filtro

#### Tabela Detalhada:
- Data
- Loja
- Região
- Consultor
- Tipo de Produto
- Valor
- Pontos

## 🎨 Paleta de Cores

- **Azul Principal**: #366092 (Realizado)
- **Azul Escuro**: #1F4E78 (Meta)
- **Verde**: #28A745 (Positivo/Atingido)
- **Vermelho**: #FF6B6B (Negativo/Não Atingido)
- **Cinza**: #6C757D (Neutro)

## 📊 Cálculos e KPIs

### Dias Úteis (DU)
- **DU Total**: Total de dias úteis do mês
- **DU Decorridos**: Dias úteis já transcorridos
- **DU Restantes**: Dias úteis restantes até o fim do mês

### Métricas de Performance
- **% Atingimento**: (Pontos Realizados / Meta) × 100
- **Média por DU**: Valor Total / DU Decorridos
- **Meta Diária**: Meta Total / DU Total
- **Projeção**: Média por DU × DU Total
- **% Projeção**: (Projeção / Meta) × 100
- **Ticket Médio**: Valor Total / Quantidade de Transações
- **Produtividade**: Transações / Número de Consultores

### Produtos Especiais
- **PACK**: Agrupa FGTS + ANT. BEN. + CNC 13º

## 🔧 Arquitetura Técnica

### Módulos Criados

#### `src/dashboard/kpi_dashboard.py`
Módulo centralizado de cálculos de KPIs:
- `calcular_kpis_gerais()`: KPIs principais do dashboard
- `calcular_kpis_por_produto()`: KPIs detalhados por produto
- `calcular_kpis_por_regiao()`: KPIs por região
- `calcular_ranking_lojas_atingimento()`: Ranking de lojas
- `calcular_ranking_consultores_atingimento()`: Ranking de consultores
- `calcular_evolucao_diaria()`: Evolução temporal

### Integração com Relatórios

O dashboard utiliza os mesmos cálculos dos relatórios:
- **Excel**: `src/reports/product_tables.py`, `src/reports/kpi_calculator.py`
- **PDF**: `src/reports/pdf_executivo.py`, `src/reports/pdf_produto.py`
- **Processamento**: `src/data_processing/column_mapper.py`

## 📱 Sidebar (Barra Lateral)

### Configurações:
- **Ano**: Seleção do ano (2024, 2025, 2026)
- **Mês**: Seleção do mês (Janeiro a Dezembro)

### Filtros Globais:
- **Região**: Filtrar todos os dados por região (em desenvolvimento)

### Legenda:
- **DU**: Dias Úteis
- **Meta Prata**: Meta principal
- **Meta Ouro**: Meta desafio
- **PACK**: FGTS + ANT. BEN. + CNC 13º

## 🎯 Diferenciais do Dashboard Refatorado

1. **Integração Completa**: Todos os cálculos dos relatórios Excel e PDF
2. **Meta Diária**: Indicador essencial para relatórios parciais
3. **Rankings por Atingimento**: Foco em performance real vs meta
4. **Evolução Temporal**: Análise dia a dia com projeções
5. **Visualizações Avançadas**: Gráficos interativos com Plotly
6. **Performance**: Cache de dados para carregamento rápido
7. **Responsivo**: Layout wide que aproveita toda a tela

## 📈 Próximas Melhorias

- [ ] Filtros globais por região funcionais
- [ ] Comparação entre períodos (mês a mês)
- [ ] Exportação de dados filtrados
- [ ] Análise de tendências com IA
- [ ] Alertas de performance
- [ ] Dashboard mobile-friendly
- [ ] Integração com banco de dados

## 🐛 Troubleshooting

### Erro: "FileNotFoundError"
- Verifique se os arquivos de dados existem para o período selecionado
- Estrutura esperada:
  - `digitacao/{mes}_{ano}.xlsx`
  - `tabelas/Tabelas_{mes}_{ano}.xlsx`
  - `metas/metas_{mes}.xlsx`
  - `configuracao/loja_regiao.xlsx`

### Dashboard não carrega
- Execute: `pip install streamlit plotly pandas openpyxl`
- Verifique se está no diretório correto do projeto

### Dados não aparecem
- Limpe o cache: Pressione 'C' no dashboard
- Ou adicione `?clear_cache=1` na URL

## 📞 Suporte

Para dúvidas ou problemas, consulte a documentação dos módulos ou entre em contato com a equipe de desenvolvimento.

---

**Desenvolvido com ❤️ para MGCred**
