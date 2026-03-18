# Sistema de Avisos para Produtos Sem Pontuação

## 📋 Visão Geral

Sistema implementado para detectar e alertar sobre produtos que não possuem pontuação definida nas tabelas de pontuação mensais, evitando problemas de cálculo de pontos e facilitando a manutenção das tabelas.

## 🎯 Objetivo

Alertar automaticamente quando houver produtos nos dados de vendas que:
- Não estão mapeados na tabela de pontuação mensal (`pontuacao/pontos_{mes}.xlsx`)
- Não possuem `TIPO_PRODUTO` definido na tabela de produtos (`tabelas/Tabelas_{mes}_{ano}.xlsx`)

## 🛠️ Implementação

### 1. Função de Verificação

**Localização**: `src/data_processing/pontuacao_loader.py`

```python
def verificar_produtos_sem_pontuacao(df: pd.DataFrame) -> dict:
    """
    Verifica produtos sem pontuação e retorna informações detalhadas.
    
    Returns:
        dict: {
            'tem_problemas': bool,
            'total_registros': int,
            'valor_total': float,
            'produtos': list[dict]
        }
    """
```

### 2. Avisos Automáticos

#### No Terminal/Console
Quando `calcular_pontos_com_tabela_mensal()` é chamado com `mostrar_avisos=True` (padrão):

```
⚠️  AVISO: 17 registros sem pontuação identificada!
   Valor total afetado: R$ 99,404.01
   Produtos sem pontuação:
   - INSS FLEX DIGITAL TOKEN FRAN - Digital Token - Não: R$ 81,654.21 (TIPO: None)
   - NOVO • INSS • • INSS ML NORMAL MAIOR 10K - WEB INVALID: R$ 17,749.80 (TIPO: None)
```

#### No Dashboard Streamlit
Exibe um expander colapsável com detalhes dos produtos sem pontuação:

```
⚠️ Atenção: 17 registros sem pontuação identificada
```

Ao expandir, mostra:
- Valor total afetado
- Instruções sobre onde adicionar os produtos
- Tabela com lista completa de produtos, valores e tipos

## 📊 Informações Fornecidas

Para cada produto sem pontuação, o sistema fornece:
- **Nome do Produto**: Nome completo do produto
- **Valor Total**: Soma de todos os valores desse produto
- **Tipo Produto**: TIPO_PRODUTO mapeado (ou None se não mapeado)

## 🔧 Como Corrigir Produtos Sem Pontuação

### Opção 1: Adicionar à Tabela de Pontuação Mensal

1. Abrir arquivo `pontuacao/pontos_{mes}.xlsx`
2. Adicionar nova linha com:
   - **PRODUTO**: Nome do produto (em MAIÚSCULAS)
   - **PRODUÇÃO**: 1
   - **PONTOS**: Valor de pontuação

**Exemplo**:
```
PRODUTO              PRODUÇÃO  PONTOS
PORTABILIDADE        1         1.0
SAQUE                1         2.5
```

### Opção 2: Adicionar à Tabela de Produtos

Se o produto não aparece na tabela de produtos:

1. Abrir arquivo `tabelas/Tabelas_{mes}_{ano}.xlsx`
2. Adicionar o produto com seu respectivo `TIPO_PRODUTO` e `PTS`

### Opção 3: Atualizar Mapeamento

Se o produto existe mas o mapeamento está incorreto:

1. Editar `src/data_processing/pontuacao_loader.py`
2. Atualizar função `criar_mapeamento_tipo_produto()`
3. Adicionar mapeamento: `'TIPO_PRODUTO_DADOS': 'PRODUTO_TABELA_PONTUACAO'`

## 📈 Exemplo de Uso

### No Código Python

```python
from src.data_processing.pontuacao_loader import (
    calcular_pontos_com_tabela_mensal,
    verificar_produtos_sem_pontuacao
)

# Calcular pontos com avisos
df = calcular_pontos_com_tabela_mensal(df_vendas, mes=3, ano=2026)

# Verificar manualmente
info = verificar_produtos_sem_pontuacao(df)
if info['tem_problemas']:
    print(f"Produtos sem pontuação: {len(info['produtos'])}")
    print(f"Valor afetado: R$ {info['valor_total']:,.2f}")
```

### No Dashboard

O aviso aparece automaticamente após carregar os dados, logo abaixo da mensagem de sucesso.

## 🎨 Estrutura do Aviso no Dashboard

```
✅ Dados carregados: 6,415 registros | Última atualização: 18/03/2026

⚠️ Atenção: 17 registros sem pontuação identificada [▼]
    ┌─────────────────────────────────────────────────────┐
    │ ⚠️ Valor total afetado: R$ 99,404.01                │
    │                                                      │
    │ Os produtos abaixo não possuem pontuação definida   │
    │ na tabela de pontuação mensal...                    │
    │                                                      │
    │ [Tabela com produtos]                               │
    └─────────────────────────────────────────────────────┘
```

## 🔍 Monitoramento

### Verificar Regularmente

- Após adicionar novos produtos ao sistema
- Após atualizar tabelas de pontuação mensais
- No início de cada mês
- Quando o total de pontos divergir do esperado

### Métricas Importantes

- **Total de registros sem pontuação**: Deve ser 0 idealmente
- **Valor total afetado**: Impacto financeiro dos produtos não mapeados
- **% do total**: `(valor_afetado / valor_total) * 100`

## ✅ Boas Práticas

1. **Revisar avisos mensalmente**: Verificar produtos sem pontuação no início de cada mês
2. **Documentar decisões**: Anotar por que certos produtos não têm pontuação
3. **Manter tabelas atualizadas**: Adicionar novos produtos assim que aparecerem
4. **Validar cálculos**: Comparar total calculado com total esperado

## 🚨 Quando Se Preocupar

- **Valor afetado > 1% do total**: Impacto significativo nos KPIs
- **Produtos recorrentes**: Mesmo produto aparece sem pontuação por vários meses
- **Produtos de alto valor**: Produtos individuais com valor > R$ 10.000

## 📝 Histórico de Mudanças

- **2026-03-18**: Sistema de avisos implementado
  - Função `verificar_produtos_sem_pontuacao()`
  - Avisos automáticos no terminal
  - Expander no dashboard Streamlit
  - Documentação criada
