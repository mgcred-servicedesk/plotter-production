# Sistema de Análise de Vendas

Sistema completo para análise de vendas com dashboard interativo, geração de relatórios Excel e PDF, baseado em sistema de pontuação por produto.

## 📋 Funcionalidades

- **Processamento automatizado de dados** de vendas mensais
- **Sistema de pontuação** por produto com cálculo de metas Prata e Ouro
- **Dashboard interativo** com Streamlit
- **Relatórios Excel** automatizados e formatados
- **Relatórios PDF** executivos e detalhados
- **Análises comparativas** entre regiões, lojas e consultores
- **KPIs de performance** e produtividade
- **Autenticação e controle de acesso** com Row-Level Security (RLS)

## 🏗️ Estrutura do Projeto

```
Numeros_venda/
├── digitacao/                  # Dados de vendas mensais
├── metas/                      # Metas por loja e consultor
├── tabelas/                    # Tabelas de produtos com pontuação
├── configuracao/               # Configurações (HC, loja-região, supervisores)
├── assets/                     # Logotipo e recursos visuais
├── src/
│   ├── config/
│   │   └── settings.py         # Configurações centralizadas e constantes
│   ├── data_processing/
│   │   ├── column_mapper.py    # Mapeamento de colunas dos arquivos
│   │   ├── loader.py           # Carregamento e pipeline unificado de dados
│   │   ├── business_rules.py   # Regras de negócio
│   │   ├── consolidator.py     # Consolidação de dados
│   │   ├── points_calculator.py# Sistema de pontuação
│   │   └── transformer.py      # Transformação de dados
│   ├── reports/
│   │   ├── formatters.py       # Formatação centralizada (moeda, número, %)
│   │   ├── pdf_styles.py       # Estilos PDF centralizados (cores, tabelas, rodapé)
│   │   ├── pdf_executivo.py    # Relatório PDF executivo (KPIs e gráficos)
│   │   ├── pdf_completo.py     # Relatório PDF completo (todos os rankings)
│   │   ├── pdf_regional.py     # Relatórios PDF por região
│   │   ├── pdf_produto.py      # Relatórios PDF por produto individual
│   │   ├── pdf_produtos_loja.py# Relatório PDF consolidado produtos x lojas
│   │   ├── pdf_charts.py       # Gráficos Matplotlib para PDFs
│   │   ├── resumo_geral.py     # Dados de resumo consolidado
│   │   ├── relatorio_mix.py    # Relatório MIX de produtos
│   │   ├── tabela_produtos.py  # Tabelas por produto com métricas
│   │   ├── tabela_produtos_horizontal.py
│   │   └── tabela_produto_individual.py
│   ├── dashboard/
│   │   ├── auth.py            # Autenticação (login, logout, bcrypt)
│   │   ├── rls.py             # Row-Level Security (filtro por perfil)
│   │   ├── user_mgmt.py       # Gerenciamento de usuários
│   │   ├── kpi_dashboard.py   # Cálculos de KPIs do dashboard
│   │   ├── kpi_analiticos.py  # KPIs analíticos
│   │   └── components/        # Componentes reutilizáveis (tabelas)
│   └── analysis/               # Análises comparativas
├── outputs/
│   ├── relatorios_excel/       # Relatórios Excel gerados
│   └── relatorios_pdf/         # Relatórios PDF gerados
├── gerar_relatorio.py          # Script para gerar relatório Excel
├── gerar_relatorio_pdf.py      # Script para gerar relatórios PDF
├── notebooks/                  # Análises exploratórias
└── tests/                      # Testes automatizados
```

## 🚀 Instalação

### Pré-requisitos

- Python 3.11 ou superior
- pip ou uv para gerenciamento de pacotes

### Passos

1. Clone o repositório ou navegue até o diretório do projeto:
```bash
cd /home/rafaelcerqueira/Projetos/Numeros_venda
```

2. Crie um ambiente virtual (recomendado):
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
```

3. Instale as dependências:
```bash
pip install -r requirements.txt
```

4. Configure as variáveis de ambiente:
```bash
cp .env.example .env
# Edite o arquivo .env conforme necessário
```

## 📊 Como Usar

### Dashboard Interativo

Execute o dashboard Streamlit:
```bash
streamlit run src/dashboard/app.py
```

O dashboard estará disponível em `http://localhost:8501`

### Gerar Relatório Excel

Gera um arquivo Excel completo com múltiplas abas (Resumo Geral, Produtos por Loja, Rankings, MIX, etc.):

```bash
python gerar_relatorio.py
```

Ou via importação:
```python
from gerar_relatorio import gerar_relatorio

gerar_relatorio(mes=3, ano=2026)
```

### Gerar Relatórios PDF

Gera 13 arquivos PDF (Executivo, Completo, Regionais, por Produto, Produtos por Loja):

```bash
python gerar_relatorio_pdf.py
```

Ou via importação:
```python
from gerar_relatorio_pdf import main

main(mes=3, ano=2026)
```

**Tipos de relatórios PDF gerados:**
- **Executivo**: KPIs, gráficos de atingimento, evolução diária, TOP 10 lojas/consultores (6-8 páginas)
- **Completo**: Todos os rankings detalhados de lojas, consultores e regiões (15-20 páginas)
- **Regional**: Um PDF por região com análise específica (4-6 páginas cada)
- **Por Produto**: Um PDF para cada produto (CNC, SAQUE, CLT, CONSIGNADO, PACK)
- **Produtos por Loja**: Visão consolidada em formato landscape

## 🎯 Regras de Negócio

### Sistema de Pontuação

Cada produto tem uma pontuação baseada em valor monetário:
- **Cálculo**: Pontos = Valor × PTS (da tabela de produtos)
- **Exemplo**: R$ 500,00 × 5 pts = 2.500 pontos

### Produtos Especiais

#### Emissão de Cartão
- `TIPO OPER.` = `CARTÃO BENEFICIO` ou `Venda Pré-Adesão`
- **NÃO** contam para valores e pontuação
- Contam apenas como quantidade de emissão de cartão

#### Seguros
- `TIPO OPER.` = `BMG MED` → conta como "Med" (quantidade)
- `TIPO OPER.` = `Seguro` → conta como "Vida Familiar" (quantidade)
- **NÃO** contam para valores e pontuação

#### Super Conta
- `SUBTIPO` = `SUPER CONTA`
- **SIM** contam para valores e pontuação
- **TAMBÉM** contam como produção "Super Conta" (quantidade)

### Metas

- **Meta Prata**: Meta base em pontos
- **Meta Ouro**: Meta premium em pontos
- **Meta Diária**: (Meta Prata - Pontos Atuais) / Dias Úteis Restantes

## 📈 KPIs Disponíveis

### KPIs de Vendas
- Valores totais e por período
- Pontuação total e por produto
- Ticket médio

### KPIs de Metas
- % Atingimento Meta Prata
- % Atingimento Meta Ouro
- Meta diária em pontos
- Média de pontos por dia útil

### KPIs de Performance
- Produtividade (Nº consultores × Nº vendas)
- Rankings de consultores, lojas e regiões

### KPIs de Produtos Especiais
- Emissões de cartão
- Seguros (Med e Vida Familiar)
- Super Conta

## 🧪 Testes

Execute os testes automatizados:
```bash
pytest tests/
```

## 📝 Estrutura dos Dados

### Arquivos de Digitação
Localização: `digitacao/`
- Formato: Excel (.xlsx)
- Nomenclatura: `{mes}_{ano}.xlsx` (ex: `marco_2026.xlsx`)
- Colunas principais: TIPO OPER., SUBTIPO, valores, datas

### Arquivos de Metas
Localização: `metas/`
- Formato: Excel (.xlsx)
- Nomenclatura: `metas_{mes}.xlsx`
- Contém: Metas Prata e Ouro por loja e consultor

### Tabelas de Produtos
Localização: `tabelas/`
- Formato: Excel (.xlsx)
- Contém: Especificação de produtos com coluna PTS (pontos)

### Configurações
Localização: `configuracao/`
- `HC_Colaboradores.xlsx`: Headcount de colaboradores
- `loja_regiao.xlsx`: Mapeamento loja-região
- `Supervisores.xlsx`: Lista de supervisores (excluídos de análises de consultores)
- `usuarios.json`: Cadastro de usuários do dashboard (login, perfil, escopo)

## 🔐 Autenticação e Controle de Acesso

### Login
O dashboard exige autenticação para acesso. Credenciais padrão: `admin` / `admin123`.

### Perfis de Acesso (Row-Level Security)

| Perfil | Acesso | Escopo |
|--------|--------|--------|
| `admin` | Todos os dados | Sem restrição |
| `gerente_comercial` | Dados da(s) região(ões) atribuída(s) | Regiões |
| `supervisor` | Dados da(s) loja(s) atribuída(s) | Lojas |

### Funcionalidades
- **Gerenciamento de usuários** (admin): criar, ativar/desativar, resetar senhas
- **Alterar senha**: disponível para todos os perfis
- **Visualizar Como** (admin): simular a visão de outro perfil/escopo
- Senhas armazenadas com hash bcrypt
- Usuários cadastrados em `configuracao/usuarios.json`

## 🛠️ Tecnologias Utilizadas

- **Python 3.11+**
- **Pandas 2.2+**: Manipulação de dados
- **NumPy 1.26+**: Cálculos numéricos
- **Plotly 5.20+**: Gráficos interativos
- **Matplotlib 3.8+**: Gráficos para relatórios PDF
- **Streamlit 1.35+**: Dashboard web
- **openpyxl**: Leitura/escrita de Excel
- **ReportLab**: Geração de PDF
- **python-dotenv**: Variáveis de ambiente
- **bcrypt**: Hash de senhas para autenticação
- **pytest**: Testes automatizados

## 🏗️ Arquitetura dos Módulos Centralizados

### Formatação (`src/reports/formatters.py`)
Funções únicas de formatação reutilizadas por todos os relatórios:
- `formatar_moeda()` — R$ X.XXX,XX
- `formatar_moeda_compacta()` — R$ 1,5M / R$ 500K
- `formatar_numero()` — X.XXX
- `formatar_percentual()` — XX,XX%

### Estilos PDF (`src/reports/pdf_styles.py`)
Estilos centralizados para consistência visual em todos os PDFs:
- Paleta de cores padrão (`CORES`)
- Estilos de tabela (moderno, com total, KPI)
- Estilos de parágrafo (título, subtítulo, seção, região)
- Rodapé padronizado com número de página e data

### Constantes (`src/config/settings.py`)
Configurações e constantes de negócio centralizadas:
- `MAPEAMENTO_PRODUTOS` — Mapeamento produto MIX → tipos de produto
- `MAPEAMENTO_COLUNAS_META` — Mapeamento produto → coluna de meta
- `MESES_PT` / `MESES_ARQUIVO` — Nomes de meses em português
- `LISTA_PRODUTOS` — Lista dos 5 produtos MIX

### Pipeline de Dados (`src/data_processing/loader.py`)
- `carregar_e_processar_dados(mes, ano)` — Pipeline unificado de carga, mapeamento, JOIN, pontuação e regras de exclusão

## 📄 Licença

Este projeto é de uso interno da empresa.

## 👥 Contribuindo

Para contribuir com o projeto:
1. Siga as convenções de código PEP 8
2. Documente funções com docstrings em português
3. Adicione testes para novas funcionalidades
4. Mantenha o código limpo e legível

## 📞 Suporte

Para dúvidas ou problemas, entre em contato com a equipe de desenvolvimento.
