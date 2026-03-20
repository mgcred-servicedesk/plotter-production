# 📊 Novos Recursos do Dashboard - Analíticos e Rankings

## 🎯 Resumo das Implementações

Esta documentação descreve os novos recursos de analíticos e rankings implementados no Dashboard de Vendas MGCred.

---

## 🆕 Novo Módulo: `kpi_analiticos.py`

**Localização**: `src/dashboard/kpi_analiticos.py`

### Funções Implementadas

#### 1. `calcular_analitico_consultores_produtos_loja()`
Cria analítico geral de consultores com produtos por loja.

**Retorna**: DataFrame com colunas:
- Consultor
- Loja
- Região
- Produto
- Qtd (quantidade de transações)
- Valor
- Pontos
- Ticket Médio

**Características**:
- Exclui supervisores automaticamente
- Agrupa por consultor, loja e produto MIX
- Calcula ticket médio por combinação

#### 2. `calcular_media_producao_consultor_regiao()`
Calcula estatísticas de produção por consultor em cada região.

**Retorna**: DataFrame com estatísticas por região:
- Valor Médio, Mediano, Desvio, Mínimo, Máximo
- Pontos Médio, Mediano, Desvio, Mínimo, Máximo
- Número de Consultores

**Uso**: Comparativo de produtividade entre regiões

#### 3. `calcular_ranking_ticket_medio()`
Cria rankings por ticket médio (lojas ou consultores).

**Parâmetros**:
- `tipo`: 'loja' ou 'consultor'
- `top_n`: Número de itens no ranking (padrão: 10)

**Retorna**: DataFrame com ranking ordenado por ticket médio

#### 4. `calcular_ranking_por_produto()`
Cria rankings específicos por produto MIX.

**Retorna**: Dicionário com DataFrames de ranking para cada produto:
- CNC
- FGTS
- CARTÃO
- CONSIGNADO
- PACK

#### 5. `calcular_distribuicao_produtos_consultor()`
Cria pivot table com distribuição de produtos por consultor.

**Retorna**: DataFrame com:
- Consultor
- Pontos por produto (colunas)
- TOTAL
- Loja
- Região

---

## 📋 Estrutura do Dashboard Atualizada

### Abas Principais

1. **📊 Produtos** (mantida)
2. **🗺️ Regiões** (mantida)
3. **🏆 Rankings** (EXPANDIDA)
4. **📈 Analíticos** (NOVA)
5. **📉 Evolução** (mantida)
6. **📋 Detalhes** (mantida)

---

## 🏆 Aba Rankings (Expandida)

### Sub-abas Implementadas

#### 🏪 Lojas
**Coluna 1**: Top 10 por Atingimento
- Ranking por % de atingimento de meta prata
- Inclui: Posição, Loja, Região, Qtd, Valor, Pontos, Meta Prata, Atingimento %, Ticket Médio

**Coluna 2**: Top 10 por Ticket Médio
- Ranking por maior ticket médio
- Inclui: Posição, Loja, Região, Qtd, Valor, Pontos, Ticket Médio

#### 👥 Consultores
**Coluna 1**: Top 10 por Atingimento
- Ranking por % de atingimento de meta prata individual
- Inclui: Posição, Consultor, Loja, Qtd, Valor, Pontos, Meta Prata, Atingimento %, Ticket Médio

**Coluna 2**: Top 10 por Ticket Médio
- Ranking por maior ticket médio
- Inclui: Posição, Consultor, Loja, Região, Qtd, Valor, Pontos, Ticket Médio

#### 📦 Por Produto
**Seletor**: Lojas ou Consultores

**Expanders por Produto**:
- Ranking Top 10 para cada produto MIX
- CNC, FGTS, CARTÃO, CONSIGNADO, PACK
- Dados: Posição, Nome, Loja (se consultor), Qtd, Valor, Pontos, Ticket Médio

---

## 📈 Aba Analíticos (Nova)

### Sub-abas Implementadas

#### 👥 Consultores por Produto
**Descrição**: Analítico detalhado de consultores por produto e loja

**Funcionalidades**:
- Filtro por Consultor (dropdown)
- Filtro por Produto (dropdown)
- Tabela completa com todas as combinações
- Métricas resumidas:
  - Total de Pontos
  - Total de Valor
  - Ticket Médio Geral

**Dados Exibidos**:
- Consultor, Loja, Região, Produto
- Qtd, Valor, Pontos, Ticket Médio

#### 🗺️ Produção por Região
**Descrição**: Comparativo de média de produção por consultor entre regiões

**Visualizações**:
1. **Gráfico de Barras**: Pontos Médio por Região
2. **Tabela Estatística Detalhada**:
   - Valor: Médio, Mediano, Mínimo, Máximo
   - Pontos: Médio, Mediano, Mínimo, Máximo
   - Número de Consultores

**Uso**: Identificar regiões com melhor/pior desempenho médio

#### 📊 Distribuição de Produtos
**Descrição**: Pivot table mostrando distribuição de produtos por consultor

**Funcionalidades**:
- Slider para selecionar Top N consultores (5-50)
- Tabela com pontos por produto
- Coluna TOTAL ordenada decrescente

**Colunas**:
- Consultor, Loja, Região
- CNC, FGTS, CARTÃO, CONSIGNADO, PACK
- TOTAL

---

## 🔧 Melhorias Técnicas

### Exclusão de Supervisores
Todas as análises de consultores agora:
- Excluem supervisores automaticamente
- Usam `df_supervisores_filtrado` (respeitando filtro de região)
- Garantem contagem precisa de consultores reais

### Formatação Consistente
Todas as tabelas usam formatação padronizada:
- `formatar_moeda()` para valores monetários
- `formatar_numero()` para pontos e quantidades
- `formatar_percentual()` para percentuais

### Performance
- Uso de `st.cache_data` para carregamento de dados
- Cálculos otimizados com pandas
- Filtros aplicados antes de exibição

---

## 📊 Exemplos de Uso

### Caso 1: Identificar Consultores Especialistas
1. Ir para **Analíticos** → **Consultores por Produto**
2. Filtrar por produto específico (ex: CNC)
3. Ordenar por Pontos para ver especialistas

### Caso 2: Comparar Regiões
1. Ir para **Analíticos** → **Produção por Região**
2. Analisar gráfico de barras
3. Verificar estatísticas detalhadas na tabela

### Caso 3: Encontrar Melhores Lojas por Produto
1. Ir para **Rankings** → **Por Produto**
2. Selecionar "Lojas"
3. Expandir produto desejado
4. Ver Top 10 específico

### Caso 4: Analisar Diversificação de Consultores
1. Ir para **Analíticos** → **Distribuição de Produtos**
2. Ajustar slider para Top 20
3. Identificar consultores com boa distribuição vs especializados

---

## 🎨 Design e UX

### Princípios Aplicados
- **Layout Limpo**: Uso de sub-abas para organização
- **Filtros Intuitivos**: Dropdowns e sliders bem posicionados
- **Informações Contextuais**: st.info() com resumos
- **Expanders**: Para rankings por produto (evita scroll excessivo)
- **Colunas**: Comparações lado a lado quando relevante

### Cores e Ícones
- 🏪 Lojas
- 👥 Consultores
- 📦 Produtos
- 🗺️ Regiões
- 📊 Estatísticas
- 📈 Crescimento/Análise

---

## 🚀 Próximos Passos

### Relatórios PDF/Excel
Os relatórios já possuem a maioria desses rankings implementados em:
- `src/reports/resumo_geral.py`
- `src/reports/pdf_executivo.py`
- `src/reports/pdf_completo.py`

**Verificar**:
- Se todos os rankings do Excel estão no Dashboard ✅
- Se novos analíticos devem ser adicionados aos PDFs
- Consistência de cálculos entre Dashboard e Relatórios

### Possíveis Melhorias Futuras
1. Gráficos interativos nos analíticos
2. Exportação de tabelas filtradas para Excel
3. Comparativo temporal (mês a mês)
4. Alertas automáticos para anomalias
5. Análise de tendências com IA

---

## 📝 Notas Técnicas

### Dependências
- `src/config/settings.py`: LISTA_PRODUTOS, MAPEAMENTO_PRODUTOS
- `src/reports/formatters.py`: Funções de formatação
- `src/dashboard/kpi_dashboard.py`: KPIs básicos
- `src/dashboard/kpi_analiticos.py`: Novos analíticos

### Testes
Todos os cálculos foram validados:
- Exclusão correta de supervisores
- Filtros de região funcionando
- Formatação consistente
- Performance adequada

---

**Data de Implementação**: 19 de Março de 2026
**Versão**: 2.0
**Autor**: Sistema de Análise MGCred
