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

## 🏗️ Estrutura do Projeto

```
Numeros_venda/
├── digitacao/              # Dados de vendas mensais
├── metas/                  # Metas por loja e consultor
├── tabelas/                # Tabelas de produtos com pontuação
├── configuracao/           # Configurações (HC, loja-região)
├── src/
│   ├── data_processing/    # Processamento de dados
│   ├── reports/            # Geração de relatórios
│   ├── dashboard/          # Dashboard Streamlit
│   ├── analysis/           # Análises comparativas
│   └── config/             # Configurações
├── outputs/
│   ├── relatorios_excel/   # Relatórios Excel gerados
│   └── relatorios_pdf/     # Relatórios PDF gerados
├── notebooks/              # Análises exploratórias
└── tests/                  # Testes automatizados
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

### Gerar Relatórios Excel

```python
from src.reports.excel_generator import gerar_relatorio_excel

# Gerar relatório do mês atual
gerar_relatorio_excel(mes=3, ano=2026)
```

### Gerar Relatórios PDF

```python
from src.reports.pdf_generator import gerar_pdf_executivo, gerar_pdf_detalhado

# Gerar PDF executivo
gerar_pdf_executivo(mes=3, ano=2026)

# Gerar PDF detalhado
gerar_pdf_detalhado(mes=3, ano=2026)
```

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

## 🛠️ Tecnologias Utilizadas

- **Python 3.11+**
- **Pandas 2.2+**: Manipulação de dados
- **NumPy 1.26+**: Cálculos numéricos
- **Plotly 5.20+**: Gráficos interativos
- **Streamlit 1.35+**: Dashboard web
- **openpyxl**: Leitura/escrita de Excel
- **ReportLab**: Geração de PDF
- **pytest**: Testes automatizados

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
