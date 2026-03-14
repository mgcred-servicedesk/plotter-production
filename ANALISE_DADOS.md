# Análise dos Dados Disponíveis

## 📊 Resumo da Inspeção

Data da análise: 13/03/2026

## ✅ Arquivos Disponíveis

### 1. Digitação (Vendas)
- ✅ `digitacao/janeiro_2026.xlsx` (1.86 MB)
- ✅ `digitacao/fevereiro_2026.xlsx` (2.86 MB)
- ✅ `digitacao/marco_2026.xlsx` (1.27 MB)

**Exemplo analisado**: março_2026.xlsx
- **Registros**: 4.590 transações
- **Colunas**: 52 colunas

### 2. Metas
- ✅ `metas/metas_janeiro.xlsx` (18 KB)
- ✅ `metas/metas_fevereiro.xlsx` (18 KB)
- ✅ `metas/metas_marco.xlsx` (18 KB)

**Exemplo analisado**: metas_marco.xlsx
- **Registros**: 45 lojas
- **Colunas**: 40 colunas (metas por produto e nível)

### 3. Tabelas de Produtos
- ✅ `tabelas/Tabelas_janeiro_2026.xlsx` (50 KB)
- ✅ `tabelas/Tabelas_fevereiro_2026.xlsx` (50 KB)
- ✅ `tabelas/Tabelas_marco_2026.xlsx` (50 KB)

**Exemplo analisado**: Tabelas_marco_2026.xlsx
- **Registros**: 884 produtos/tabelas
- **Colunas**: 7 colunas
- **✅ Coluna PTS presente**: Sim (6 valores únicos de pontuação)

### 4. Configuração
- ✅ `configuracao/HC_Colaboradores.xlsx` (27 KB)
  - **Registros**: 239 colaboradores
  - **Colunas**: 4 (FILIAL, VENDEDOR, STATUS, Obs)

- ✅ `configuracao/loja_regiao.xlsx` (14 KB)
  - **Registros**: 47 lojas
  - **Colunas**: 10 (LOJA, COD BMG, REGIÃO, e-mail, GERENTE, etc.)

---

## 🔍 Mapeamento de Colunas

### Digitação (Vendas) - Mapeamento Necessário

| Esperado no Sistema | Nome Real no Arquivo | Status |
|---------------------|---------------------|--------|
| `CONSULTOR` | `VENDEDOR` | ✅ Mapear + Higienizar |
| `LOJA` | `FILIAL` | ✅ Mapear |
| `VALOR` | `VLR BASE` | ✅ Mapear |
| `PRODUTO` | `TABELA` | ✅ Mapear |
| `TIPO OPER.` | `TIPO OPER.` | ✅ OK |
| `SUBTIPO` | **NÃO EXISTE** | ⚠️ Obter via JOIN |
| `DATA` | `DATA CAD.` | ✅ Mapear |

### Regras de Negócio - Validação

#### ✅ Emissão de Cartão
Encontrados em `TIPO OPER.`:
- ✅ `CARTÃO BENEFICIO` (84 registros em março)
- ✅ `Venda Pré-Adesão` (78 registros em março)

#### ⚠️ Seguros
**Problema identificado**:
- ❌ `BMG MED` - NÃO encontrado em `TIPO OPER.`
- ❌ `Seguro` - NÃO encontrado em `TIPO OPER.`

**Solução**: 
- `BMG MED` aparece na coluna `TABELA` (nas tabelas de produtos)
- Precisamos usar a coluna `TABELA` para identificar seguros
- Fazer merge com tabelas de produtos para identificar tipo

#### ⚠️ Super Conta
**Problema identificado**:
- Não existe coluna `SUBTIPO` em digitação
- `SUPER CONTA` aparece na tabela de produtos (coluna `SUBTIPO`)

**Solução**:
- Fazer merge de digitação com tabelas usando coluna `TABELA`
- Usar `SUBTIPO` da tabela de produtos

### Tabelas de Produtos - Estrutura

| Coluna | Descrição | Exemplo |
|--------|-----------|---------|
| `TABELA` | Nome da tabela/produto | "DEBITO EM CONTA" |
| `TIPO OPERAÇAO` | Tipo de operação | "NORMAL", "FLEX" |
| `TIPO` | Tipo do produto | "CNC", "BMG MED" |
| `SUBTIPO` | Subtipo | "SUPER CONTA", "REFIN", "NOVO" |
| `BANCO` | Banco | "HELP", "BMG" |
| `PRODUTO PTS` | Nome do produto para pontos | "CNC", "BMG MED" |
| `PTS` | **Pontuação** | 1.0, 5.0, 6.0, 7.0, 8.0, 10.0 |

### Metas - Estrutura

| Coluna | Descrição | Tipo |
|--------|-----------|------|
| `LOJA` | Nome da loja | Texto |
| `PERIFL` | Perfil da loja | "1 - HELP" |
| `REGIÃO` | Região da loja | "JACQUELINE", "SANDRA", etc. |
| `BRONZE CONSULTOR` | Meta bronze consultor | Numérico |
| `PRATA CONSULTOR` | Meta prata consultor | Numérico |
| `OURO CONSULTOR` | Meta ouro consultor | Numérico |
| `BRONZE LOJA` | Meta bronze loja | Numérico |
| `PRATA LOJA` | Meta prata loja | Numérico |
| `OURO LOJA` | Meta ouro loja | Numérico |
| ... | Metas por produto | Numérico |

---

## ⚠️ Ajustes Necessários no Sistema

### 1. Módulo de Carregamento (`loader.py`)
**Ajustes**:
- Mapear `VENDEDOR` → `CONSULTOR` + **Higienizar** (remover código antes do "-")
  - Exemplo: `"3771 - YASMIM VELASCO DA SILVA"` → `"YASMIM VELASCO DA SILVA"`
- Mapear `FILIAL` → `LOJA`
- Mapear `VLR BASE` → `VALOR` (usar valor base, não líquido)
- Mapear `TABELA` → `PRODUTO`
- Mapear `DATA CAD.` → `DATA`

### 2. Módulo de Regras de Negócio (`business_rules.py`)
**Ajustes críticos**:
- ✅ `TIPO OPER.` existe e contém "CARTÃO BENEFICIO" e "Venda Pré-Adesão"
- ⚠️ Seguros: Precisamos identificar via merge com tabelas de produtos
  - Verificar `TIPO` = "BMG MED" na tabela de produtos
  - Criar lógica para identificar "Seguro" (pode estar em TIPO ou PRODUTO PTS)
- ⚠️ Super Conta: Identificar via `SUBTIPO` da tabela de produtos após merge

### 3. Módulo de Pontuação (`points_calculator.py`)
**Ajustes**:
- ✅ Coluna `PTS` existe nas tabelas
- Fazer merge usando `TABELA` (digitação) com `TABELA` (tabelas de produtos)
- Calcular: `pontos = VLR LÍQUIDO × PTS`

### 4. Estrutura de Metas
**Observações**:
- Metas são por LOJA, não por CONSULTOR individual
- Existem metas Bronze, Prata e Ouro
- Metas são por produto (CNC, SAQUE, EMISSAO, SUPER CONTA, etc.)
- **Ajuste necessário**: Sistema espera META_PRATA e META_OURO por consultor
- **Solução**: Distribuir meta da loja pelos consultores ou usar meta da loja

---

## ✅ Viabilidade dos Relatórios

### Relatórios Viáveis com Ajustes

#### 1. ✅ Tabelas por Produto
**Status**: VIÁVEL
- Temos valores (VLR LÍQUIDO)
- Temos pontuação (PTS)
- Temos metas por produto (nas metas)
- **Ajuste**: Adaptar para estrutura de metas por loja

#### 2. ✅ Análise por Região
**Status**: VIÁVEL
- Arquivo `loja_regiao.xlsx` tem mapeamento LOJA → REGIÃO
- Podemos agregar por região

#### 3. ✅ Análise por Loja
**Status**: VIÁVEL
- Coluna FILIAL identifica a loja
- Metas são por loja

#### 4. ⚠️ Análise por Consultor
**Status**: VIÁVEL COM LIMITAÇÕES
- Temos VENDEDOR (consultor)
- **Limitação**: Metas são por loja, não por consultor
- **Solução**: Mostrar performance do consultor vs média da loja

#### 5. ✅ Rankings
**Status**: VIÁVEL
- Podemos rankear consultores por pontuação
- Podemos rankear lojas por pontuação
- Podemos rankear regiões

#### 6. ✅ Produtos Especiais
**Status**: VIÁVEL COM AJUSTES
- Emissão de cartão: ✅ Identificável via TIPO OPER.
- Seguros: ⚠️ Identificar via tabela de produtos
- Super Conta: ⚠️ Identificar via tabela de produtos

---

## 🔧 Plano de Ajustes

### Prioridade Alta
1. **Criar módulo de mapeamento de colunas**
   - Mapear nomes reais para nomes esperados
   - Criar dicionário de mapeamento configurável

2. **Ajustar regras de negócio**
   - Implementar identificação de seguros via tabela de produtos
   - Implementar identificação de Super Conta via merge

3. **Ajustar estrutura de metas**
   - Adaptar para metas por loja
   - Criar lógica para distribuir/comparar com consultores

### Prioridade Média
4. **Validar cálculo de pontuação**
   - Testar merge de digitação com tabelas
   - Validar cálculo: pontos = valor × PTS

5. **Ajustar dias úteis**
   - Implementar lista de feriados do .env

### Prioridade Baixa
6. **Otimizações**
   - Cache de merges
   - Performance em arquivos grandes

---

## 📋 Checklist de Validação

- [x] Arquivos de digitação existem e são legíveis
- [x] Arquivos de metas existem e são legíveis
- [x] Arquivos de tabelas existem e são legíveis
- [x] Arquivos de configuração existem e são legíveis
- [x] Coluna PTS existe nas tabelas
- [x] Mapeamento loja-região disponível
- [x] Identificação de emissão de cartão possível
- [ ] Identificação de seguros (precisa ajuste)
- [ ] Identificação de Super Conta (precisa ajuste)
- [ ] Metas por consultor (usar metas de loja)
- [ ] Sistema de pontuação (precisa merge)

---

## 🎯 Conclusão

### ✅ VIÁVEL PRODUZIR OS RELATÓRIOS

**Com os ajustes necessários**, conseguimos produzir TODOS os relatórios especificados:

1. ✅ Tabelas por produto com metas
2. ✅ Análise por região
3. ✅ Análise por loja
4. ✅ Análise por consultor (com adaptações)
5. ✅ Rankings de performance
6. ✅ Comparativos
7. ✅ Relatórios Excel formatados
8. ✅ Dashboard interativo

### Próximos Passos Imediatos

1. Criar módulo `column_mapper.py` para mapeamento de colunas
2. Ajustar `loader.py` para usar mapeamento
3. Ajustar `business_rules.py` para identificar produtos via merge
4. Testar pipeline completo com dados reais
5. Validar cálculos de pontuação

### Estimativa de Tempo para Ajustes

- Mapeamento de colunas: 30 minutos
- Ajuste de regras de negócio: 1 hora
- Ajuste de metas: 30 minutos
- Testes e validação: 1 hora
- **Total**: ~3 horas de desenvolvimento

---

## 📊 Dados de Exemplo (Março 2026)

- **4.590 transações** processadas
- **45 lojas** ativas
- **239 colaboradores** no HC
- **884 produtos/tabelas** diferentes
- **10 tipos de operação** principais
- **6 níveis de pontuação** (1, 5, 6, 7, 8, 10 pontos)

**Sistema está pronto para processar os dados reais após os ajustes de mapeamento!**
