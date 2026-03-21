# Guia de Integração — Banco de Dados MGCred

Documentação técnica para o projeto **angry-man** (inserção de dados)
e **plotter-production** (leitura/dashboard).

> **Banco:** Supabase (PostgreSQL)
> **Schema:** `public`
> **SDK Python:** `supabase>=2.22` (recomendado `2.28.3`)
> **Autenticação:** service_role key (bypassa RLS para escrita)

---

## Índice

0. [Pré-requisitos de Conexão](#0-pré-requisitos-de-conexão)
1. [Visão Geral](#1-visão-geral)
2. [Ordem de Inserção (Dependências)](#2-ordem-de-inserção-dependências)
3. [Tabelas de Configuração (carga única)](#3-tabelas-de-configuração-carga-única)
4. [Tabelas de Dados (carga mensal)](#4-tabelas-de-dados-carga-mensal)
5. [Regras de Negócio na Inserção](#5-regras-de-negócio-na-inserção)
6. [Como o Dashboard Lê os Dados](#6-como-o-dashboard-lê-os-dados)
7. [Views e Funções Disponíveis](#7-views-e-funções-disponíveis)
8. [Pontuação — Regra de Fallback](#8-pontuação--regra-de-fallback)
9. [Categorias de Produto — Referência Completa](#9-categorias-de-produto--referência-completa)
10. [Mapeamento de Metas — Referência Completa](#10-mapeamento-de-metas--referência-completa)
11. [Perfis de Usuário](#11-perfis-de-usuário)
12. [Checklist de Validação Pós-Carga](#12-checklist-de-validação-pós-carga)

---

## 0. Pré-requisitos de Conexão

### API Key

O projeto usa a **service_role key** do Supabase, que bypassa
RLS (necessário para inserção de dados).

Onde encontrar: **Supabase Dashboard → Settings → API Keys**.

Dois formatos são aceitos (ambos funcionam com `supabase>=2.22`):

| Formato | Onde encontrar | Exemplo |
|---------|---------------|---------|
| **Novo** (recomendado) | Aba "API Keys" | `sb_secret_MczXH-bJDH...` |
| **Legacy** (JWT) | Aba "Legacy API Keys" → service_role | `eyJhbGciOiJIUzI1Ni...` |

> **IMPORTANTE:** Versões do SDK Python anteriores a `2.22` só
> aceitam o formato JWT legacy. Use `supabase>=2.28.3`.

### Conexão em Python

```python
import os
from supabase import create_client, Client

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)
```

### GRANTs obrigatórios

Se o schema foi criado do zero (executando `schema.sql` no
SQL Editor), é necessário garantir que as roles da API tenham
acesso. Execute **uma vez** no SQL Editor:

```sql
GRANT USAGE ON SCHEMA public
    TO anon, authenticated, service_role;

GRANT ALL ON ALL TABLES IN SCHEMA public
    TO anon, authenticated, service_role;

GRANT ALL ON ALL SEQUENCES IN SCHEMA public
    TO anon, authenticated, service_role;

GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public
    TO anon, authenticated, service_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL ON TABLES
    TO anon, authenticated, service_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL ON SEQUENCES
    TO anon, authenticated, service_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT EXECUTE ON FUNCTIONS
    TO anon, authenticated, service_role;
```

Sem isso, qualquer query via API retornará
`permission denied for schema public`.

---

## 1. Visão Geral

```
┌─────────────────────────────────────────────────────────────┐
│                     FONTES DE DADOS                         │
│  (planilhas Excel importadas pelo projeto angry-man)        │
├─────────────┬──────────────┬────────────┬───────────────────┤
│ loja_regiao │ HC_Colaborad │ Supervisor │ Tabelas_{m}_{a}   │
│ .xlsx       │ ores.xlsx    │ es.xlsx    │ .xlsx             │
├─────────────┼──────────────┼────────────┼───────────────────┤
│ digitacao/  │ metas/       │ pontuacao/ │                   │
│ {m}_{a}.xlsx│ metas_{m}    │ pontos_{m} │                   │
│             │ .xlsx        │ .xlsx      │                   │
└──────┬──────┴──────┬───────┴─────┬──────┴────────┬──────────┘
       │             │             │               │
       ▼             ▼             ▼               ▼
┌─────────────────────────────────────────────────────────────┐
│                    SUPABASE (PostgreSQL)                     │
├─────────────────────────────────────────────────────────────┤
│  regioes ─┐                                                 │
│  lojas ───┤ Configuração     categorias_produto (seed)      │
│  consult. ┤ (carga única)    periodos                       │
│  supervis.┘                                                 │
│                                                             │
│  produtos ──┐                                               │
│  contratos ─┤ Dados mensais                                 │
│  metas ─────┤                                               │
│  pontuacao ─┘                                               │
│                                                             │
│  contratos_pagos (view)                                     │
│  v_pontuacao_efetiva (view)                                 │
│  obter_pontuacao_periodo() (função)                         │
├─────────────────────────────────────────────────────────────┤
│                    DASHBOARD (Streamlit)                     │
│                    plotter-production                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Ordem de Inserção (Dependências)

As tabelas possuem FKs entre si. **A ordem de inserção deve ser
respeitada** para evitar violações de integridade referencial.

### Fase 1 — Tabelas sem dependências

Podem ser inseridas em paralelo:

| # | Tabela               | Tipo             | Frequência     |
|---|----------------------|------------------|----------------|
| 1 | `regioes`            | Configuração     | Única/rara     |
| 2 | `periodos`           | Referência       | Sob demanda    |
| 3 | `categorias_produto` | Referência       | Já tem seed    |

### Fase 2 — Dependem da Fase 1

| # | Tabela          | Depende de                    | Frequência  |
|---|-----------------|-------------------------------|-------------|
| 4 | `lojas`         | `regioes`                     | Única/rara  |
| 5 | `pontuacao`     | `periodos`, `categorias_produto` | Mensal   |
| 6 | `produtos`      | `categorias_produto`          | Mensal      |

### Fase 3 — Dependem da Fase 2

| # | Tabela          | Depende de                    | Frequência  |
|---|-----------------|-------------------------------|-------------|
| 7 | `consultores`   | `lojas`                       | Única/rara  |
| 8 | `supervisores`  | `lojas`, `regioes`            | Única/rara  |
| 9 | `metas`         | `periodos`, `lojas`           | Mensal      |

### Fase 4 — Dependem de tudo

| #  | Tabela       | Depende de                              | Frequência |
|----|--------------|----------------------------------------|------------|
| 10 | `contratos`  | `periodos`, `lojas`, `consultores`, `produtos` | Mensal |

### Resumo visual

```
regioes ──────────┐
                  ├── lojas ──────────┐
periodos ─────────┤                   ├── consultores
                  │                   ├── supervisores
categorias_prod. ─┤                   ├── metas
                  ├── produtos ───────┤
                  ├── pontuacao       └── contratos
```

---

## 3. Tabelas de Configuração (carga única)

Essas tabelas são carregadas uma vez e atualizadas raramente
(quando há mudanças na estrutura organizacional).

### 3.1 `regioes`

**Origem:** `configuracao/loja_regiao.xlsx` (coluna REGIAO, valores
únicos)

```sql
-- UPSERT por nome
INSERT INTO regioes (nome)
VALUES ('LESTE')
ON CONFLICT (nome) DO NOTHING;
```

| Coluna | Tipo | Obrigatório | Descrição            |
|--------|------|-------------|----------------------|
| nome   | TEXT | Sim         | Nome da região       |

**Valores esperados:** ~5 regiões (ex: LESTE, OESTE, NORTE, SUL,
CENTRO)

---

### 3.2 `lojas`

**Origem:** `configuracao/loja_regiao.xlsx`

```sql
-- UPSERT por nome
INSERT INTO lojas (nome, cod_bmg, regiao_id, gerente, perfil)
VALUES (
    'LOJA CENTRO 01',
    12345,
    (SELECT id FROM regioes WHERE nome = 'CENTRO'),
    'JOAO SILVA',
    'A'
)
ON CONFLICT (nome) DO UPDATE SET
    cod_bmg   = EXCLUDED.cod_bmg,
    regiao_id = EXCLUDED.regiao_id,
    gerente   = EXCLUDED.gerente,
    perfil    = EXCLUDED.perfil;
```

| Coluna    | Tipo    | Obrigatório | Descrição                   |
|-----------|---------|-------------|-----------------------------|
| nome      | TEXT    | Sim         | Nome da loja (chave única)  |
| cod_bmg   | INTEGER | Não         | Código BMG                  |
| regiao_id | UUID    | Não         | FK → `regioes.id`           |
| gerente   | TEXT    | Não         | Nome do gerente             |
| perfil    | TEXT    | Não         | Perfil da loja              |

**Resolução de FK:** Buscar `regiao_id` por nome:
`SELECT id FROM regioes WHERE nome = ?`

---

### 3.3 `consultores`

**Origem:** `configuracao/HC_Colaboradores.xlsx`

```sql
INSERT INTO consultores (nome, loja_id, status)
VALUES (
    'YASMIM VELASCO DA SILVA',
    (SELECT id FROM lojas WHERE nome = 'LOJA CENTRO 01'),
    'Ativo (a)'
)
ON CONFLICT (nome, loja_id) DO UPDATE SET
    status = EXCLUDED.status;
```

| Coluna  | Tipo | Obrigatório | Descrição                          |
|---------|------|-------------|------------------------------------|
| nome    | TEXT | Sim         | Nome do consultor (sem código)     |
| loja_id | UUID | Não         | FK → `lojas.id`                    |
| status  | TEXT | Sim         | 'Ativo (a)' ou 'Inativo (a)'      |

> **IMPORTANTE:** O nome do consultor na planilha vem como
> `"3771 - YASMIM VELASCO DA SILVA"`. Remover o código antes do
> `" - "`, inserindo apenas o nome limpo.

---

### 3.4 `supervisores`

**Origem:** `configuracao/Supervisores.xlsx`

```sql
INSERT INTO supervisores (nome, loja_id, regiao_id)
VALUES (
    'CARLOS MENDES',
    (SELECT id FROM lojas WHERE nome = 'LOJA CENTRO 01'),
    (SELECT id FROM regioes WHERE nome = 'CENTRO')
)
ON CONFLICT (nome, loja_id) DO UPDATE SET
    regiao_id = EXCLUDED.regiao_id;
```

| Coluna    | Tipo | Obrigatório | Descrição               |
|-----------|------|-------------|-------------------------|
| nome      | TEXT | Sim         | Nome (sem código)       |
| loja_id   | UUID | Não         | FK → `lojas.id`         |
| regiao_id | UUID | Não         | FK → `regioes.id`       |

> Mesma regra de limpeza de nome que consultores.

---

### 3.5 `periodos`

**Criação sob demanda** — inserir antes de qualquer dado mensal.

```sql
INSERT INTO periodos (mes, ano, referencia)
VALUES (3, 2026, 'Mar/26')
ON CONFLICT (mes, ano) DO NOTHING;
```

| Coluna     | Tipo    | Obrigatório | Descrição                 |
|------------|---------|-------------|---------------------------|
| mes        | INTEGER | Sim         | 1–12                      |
| ano        | INTEGER | Sim         | 2020–2100                 |
| referencia | TEXT    | Sim         | Label curto (ex: Mar/26)  |

**Formato de `referencia`:** Abreviação de 3 letras do mês + `/` +
últimos 2 dígitos do ano. Exemplos: `Jan/26`, `Fev/26`, `Mar/26`.

---

### 3.6 `categorias_produto`

**Já populada pelo schema** (15 registros seed). Normalmente
**não precisa de inserção pelo angry-man**.

Só inserir se surgir uma categoria nova de produto no negócio.

```sql
-- Consultar categorias existentes
SELECT codigo, nome, grupo_dashboard, grupo_meta,
       conta_valor, conta_pontuacao
FROM categorias_produto
ORDER BY ordem;
```

---

## 4. Tabelas de Dados (carga mensal)

Essas tabelas recebem dados novos a cada mês.

### 4.1 `produtos`

**Origem:** `tabelas/Tabelas_{mes}_{ano}.xlsx`
**Estratégia:** UPSERT por `tabela` (nome do produto).

```sql
INSERT INTO produtos (tabela, tipo_operacao, tipo, subtipo,
                      banco, categoria_id)
VALUES (
    'DEBITO EM CONTA',
    'NORMAL',
    'CNC',
    'NOVO',
    'HELP',
    (SELECT id FROM categorias_produto WHERE codigo = 'CNC')
)
ON CONFLICT (tabela) DO UPDATE SET
    tipo_operacao = EXCLUDED.tipo_operacao,
    tipo          = EXCLUDED.tipo,
    subtipo       = EXCLUDED.subtipo,
    banco         = EXCLUDED.banco,
    categoria_id  = EXCLUDED.categoria_id;
```

| Coluna        | Tipo | Obrigatório | Descrição                       |
|---------------|------|-------------|---------------------------------|
| tabela        | TEXT | Sim         | Nome do produto (chave única)   |
| tipo_operacao | TEXT | Não         | Tipo de operação                |
| tipo          | TEXT | Não         | Tipo do produto (CNC, FGTS...) |
| subtipo       | TEXT | Não         | Subtipo (NOVO, REFIN, SUPER CONTA...) |
| banco         | TEXT | Não         | Banco de origem                 |
| categoria_id  | UUID | Não         | FK → `categorias_produto.id`    |

#### Resolução de `categoria_id`

O campo `tipo` da planilha deve ser mapeado para `categorias_produto.codigo`.
Use a tabela de mapeamento abaixo:

| tipo (planilha)              | codigo (categorias_produto) |
|------------------------------|-----------------------------|
| `CNC`                        | `CNC`                       |
| `CNC 13º` ou `CNC 13`       | `CNC_13`                    |
| `CNC ANT`                    | `ANT_BENEF`                 |
| `SAQUE`                      | `SAQUE`                     |
| `SAQUE BENEFICIO`            | `SAQUE_BENEFICIO`           |
| `CONSIG` ou `CONSIG BMG`    | `CONSIG_BMG`                |
| `CONSIG ITAU`                | `CONSIG_ITAU`               |
| `CONSIG C6`                  | `CONSIG_C6`                 |
| `CONSIG PRIV`                | `CONSIG_PRIV`               |
| `FGTS`                       | `FGTS`                      |
| `EMISSAO`, `EMISSAO CB`, `EMISSAO CC` | `CARTAO`          |
| `Portabilidade`              | `PORTABILIDADE`             |
| `BMG MED`                    | `BMG_MED`                   |
| `Seguro`                     | `SEGURO_VIDA`               |

**Caso especial — SUPER CONTA:** Quando `subtipo = 'SUPER CONTA'`,
o `categoria_id` deve ser `SUPER_CONTA`, independentemente do `tipo`.

```sql
-- Query para resolver categoria_id na importação
SELECT id FROM categorias_produto
WHERE codigo = :codigo_mapeado;
```

---

### 4.2 `contratos`

**Origem:** Planilha completa de contratos (digitação)
**Estratégia:** UPSERT por `contrato_id` (ID do sistema origem).

```sql
INSERT INTO contratos (
    periodo_id, loja_id, consultor_id, produto_id,
    contrato_id, cliente, valor, prazo, valor_parcela,
    tipo_operacao, data_cadastro, status_banco,
    data_status_banco, status_pagamento_cliente,
    data_status_pagamento, banco, convenio,
    num_proposta, sub_status_banco
)
VALUES (
    -- periodo_id: derivar de data_status_pagamento
    (SELECT id FROM periodos
     WHERE mes = EXTRACT(MONTH FROM '2026-03-15'::DATE)
       AND ano = EXTRACT(YEAR FROM '2026-03-15'::DATE)),
    -- loja_id: resolver por nome
    (SELECT id FROM lojas WHERE nome = 'LOJA CENTRO 01'),
    -- consultor_id: resolver por nome + loja
    (SELECT id FROM consultores
     WHERE nome = 'YASMIM VELASCO DA SILVA'
       AND loja_id = (SELECT id FROM lojas
                      WHERE nome = 'LOJA CENTRO 01')),
    -- produto_id: resolver por nome (tabela)
    (SELECT id FROM produtos WHERE tabela = 'DEBITO EM CONTA'),
    -- contrato_id: ID do sistema origem
    123456789,
    'MARIA DA SILVA',
    15000.00,
    '84',
    285.00,
    'NORMAL',
    '2026-03-10',
    'PAGO',
    '2026-03-14',
    'PAGO AO CLIENTE',
    '2026-03-15',
    'BMG',
    'INSS',
    'PROP-001',
    NULL
)
ON CONFLICT (contrato_id) DO UPDATE SET
    periodo_id               = EXCLUDED.periodo_id,
    status_banco             = EXCLUDED.status_banco,
    data_status_banco        = EXCLUDED.data_status_banco,
    status_pagamento_cliente = EXCLUDED.status_pagamento_cliente,
    data_status_pagamento    = EXCLUDED.data_status_pagamento,
    sub_status_banco         = EXCLUDED.sub_status_banco;
```

| Coluna                      | Tipo         | Obrigatório | Descrição |
|-----------------------------|--------------|-------------|-----------|
| contrato_id                 | BIGINT       | **Sim**     | ID sistema origem (chave dedup) |
| loja_id                     | UUID         | **Sim**     | FK → `lojas.id` |
| valor                       | NUMERIC(15,2)| **Sim**     | Valor base do contrato |
| periodo_id                  | UUID         | Não*        | FK → `periodos.id` |
| consultor_id                | UUID         | Não         | FK → `consultores.id` |
| produto_id                  | UUID         | Não         | FK → `produtos.id` |
| cliente                     | TEXT         | Não         | Nome do cliente |
| prazo                       | TEXT         | Não         | Prazo em meses |
| valor_parcela               | NUMERIC(15,2)| Não         | Valor da parcela |
| tipo_operacao               | TEXT         | Não         | NORMAL, CARTÃO BENEFICIO, etc. |
| data_cadastro               | DATE         | Não         | Data de cadastro |
| status_banco                | TEXT         | Não         | EM ANALISE, CANCELADO, PAGO... |
| data_status_banco           | DATE         | Não         | Data do status |
| status_pagamento_cliente    | TEXT         | Não         | PAGO AO CLIENTE, NAO PAGO... |
| data_status_pagamento       | DATE         | Não         | Data do pagamento |
| banco                       | TEXT         | Não         | Banco (BMG, ITAU, C6...) |
| convenio                    | TEXT         | Não         | Convênio (INSS, SIAPE...) |
| num_proposta                | TEXT         | Não         | Número da proposta |
| sub_status_banco            | TEXT         | Não         | Sub-status |

#### Regras para `periodo_id`

- **Se `status_pagamento_cliente = 'PAGO AO CLIENTE'`:** derivar
  `periodo_id` do campo `data_status_pagamento`
  (mês/ano do pagamento).
- **Caso contrário:** `periodo_id = NULL`.

```sql
-- Derivar periodo_id de data_status_pagamento
CASE
    WHEN status_pagamento_cliente = 'PAGO AO CLIENTE'
         AND data_status_pagamento IS NOT NULL
    THEN (
        SELECT id FROM periodos
        WHERE mes = EXTRACT(MONTH FROM data_status_pagamento)
          AND ano = EXTRACT(YEAR FROM data_status_pagamento)
    )
    ELSE NULL
END
```

#### Regras para `consultor_id`

O nome do consultor na planilha vem como
`"3771 - YASMIM VELASCO DA SILVA"`. **Limpar o código** antes de
buscar:

```python
# Python
nome_limpo = nome_original.split(" - ", 1)[1].strip()
```

```sql
-- SQL
SELECT id FROM consultores
WHERE nome = 'YASMIM VELASCO DA SILVA'
  AND loja_id = :loja_id;
```

---

### 4.3 `metas`

**Origem:** `metas/metas_{mes}.xlsx`
**Estratégia:** UPSERT por
`(periodo_id, loja_id, produto, escopo, nivel)`.

A planilha tem ~40 colunas que devem ser **desnormalizadas** em
linhas. Cada coluna da planilha vira um registro com:
`produto`, `escopo`, `nivel`.

```sql
INSERT INTO metas (periodo_id, loja_id, produto,
                   escopo, nivel, valor)
VALUES (
    (SELECT id FROM periodos WHERE mes = 3 AND ano = 2026),
    (SELECT id FROM lojas WHERE nome = 'LOJA CENTRO 01'),
    'GERAL',
    'LOJA',
    'PRATA',
    500000.00
)
ON CONFLICT (periodo_id, loja_id, produto, escopo, nivel)
DO UPDATE SET valor = EXCLUDED.valor;
```

| Coluna     | Tipo          | Obrigatório | Descrição |
|------------|---------------|-------------|-----------|
| periodo_id | UUID          | **Sim**     | FK → `periodos.id` |
| loja_id    | UUID          | **Sim**     | FK → `lojas.id` |
| produto    | TEXT          | **Sim**     | Tipo de meta (ver mapeamento §10) |
| escopo     | TEXT          | **Sim**     | `'LOJA'` ou `'CONSULTOR'` |
| nivel      | TEXT          | Não         | `'BRONZE'`, `'PRATA'`, `'OURO'` ou `NULL` |
| valor      | NUMERIC(15,2) | **Sim**    | Valor da meta |

#### Valores válidos para `produto`

```
GERAL, CNC, SAQUE, EMISSAO, SUPER_CONTA, VIDA_FAMILIAR,
FGTS, CLT, FGTS_ANT_BENEF_13, BMG_MED, MIX, CONSIGNADO
```

Esses valores correspondem ao campo `grupo_meta` em
`categorias_produto` (exceto `GERAL` que é transversal).

> O mapeamento completo de colunas da planilha → registros
> normalizados está na seção §10.

---

### 4.4 `pontuacao`

**Origem:** `pontuacao/pontos_{mes}.xlsx`
**Estratégia:** UPSERT por `(periodo_id, categoria_id)`.

```sql
INSERT INTO pontuacao (periodo_id, categoria_id,
                       producao, pontos)
VALUES (
    (SELECT id FROM periodos WHERE mes = 3 AND ano = 2026),
    (SELECT id FROM categorias_produto WHERE codigo = 'CNC'),
    1,
    5.0000
)
ON CONFLICT (periodo_id, categoria_id)
DO UPDATE SET
    producao = EXCLUDED.producao,
    pontos   = EXCLUDED.pontos;
```

| Coluna       | Tipo          | Obrigatório | Descrição |
|--------------|---------------|-------------|-----------|
| periodo_id   | UUID          | **Sim**     | FK → `periodos.id` |
| categoria_id | UUID          | **Sim**     | FK → `categorias_produto.id` |
| producao     | INTEGER       | Sim         | Fator de produção (default 1) |
| pontos       | NUMERIC(10,4) | Sim         | Multiplicador (VALOR × PONTOS) |

#### Resolução de `categoria_id`

A planilha `pontos_{mes}.xlsx` tem uma coluna PRODUTO com nomes
que devem ser mapeados para `categorias_produto.codigo`:

| PRODUTO (planilha)   | codigo (categorias_produto) |
|----------------------|-----------------------------|
| `CNC`                | `CNC`                       |
| `CNC 13`             | `CNC_13`                    |
| `CARTÃO`             | `CARTAO`                    |
| `FGTS`               | `FGTS`                      |
| `CONSIG Itau`        | `CONSIG_ITAU`               |
| `CONSIG BMG`         | `CONSIG_BMG`                |
| `CONSIG C6`          | `CONSIG_C6`                 |
| `CONSIG PRIV`        | `CONSIG_PRIV`               |
| `ANT. DE BENEF.`     | `ANT_BENEF`                 |
| `SAQUE`              | `SAQUE`                     |
| `SAQUE BENEFICIO`    | `SAQUE_BENEFICIO`           |
| `PORTABILIDADE`      | `PORTABILIDADE`             |

> **Fallback:** Se um período não tem dados de pontuação, o
> dashboard usa automaticamente os do período anterior. Veja §8.

---

## 5. Regras de Negócio na Inserção

### 5.1 Produtos que NÃO contam para valor e pontuação

As categorias com `conta_valor = false` e `conta_pontuacao = false`
na tabela `categorias_produto` não entram nos KPIs monetários
nem de pontos. **Contam apenas por quantidade.**

| Categoria      | tipo_operacao na planilha            |
|----------------|--------------------------------------|
| `CARTAO`       | `CARTÃO BENEFICIO`, `Venda Pré-Adesão` |
| `BMG_MED`      | `BMG MED`                            |
| `SEGURO_VIDA`  | `Seguro`                             |

O angry-man deve inserir esses contratos normalmente. A exclusão
de valor/pontos é feita **na leitura** pelo dashboard, usando as
flags `conta_valor` e `conta_pontuacao` de `categorias_produto`.

### 5.2 Super Conta

Identificada por `subtipo = 'SUPER CONTA'` na planilha de produtos.
É a **única categoria que depende do subtipo** em vez do tipo.
Conta para valor e pontuação normalmente.

### 5.3 Deduplicação de contratos

O campo `contrato_id` (BIGINT) é a chave de deduplicação.
Se um contrato já existe, o UPSERT atualiza apenas os campos
de status (que podem mudar ao longo do tempo).

### 5.4 Limpeza de nomes de consultores/supervisores

Nomes na planilha vêm no formato `"CÓDIGO - NOME"`.
Exemplo: `"3771 - YASMIM VELASCO DA SILVA"`

**Sempre** remover o código, inserindo apenas `"YASMIM VELASCO DA
SILVA"`.

---

## 6. Como o Dashboard Lê os Dados

O dashboard (plotter-production) consome os dados assim:

### 6.1 Dados de vendas (contratos pagos)

```sql
-- View principal do dashboard
SELECT c.*, p.tabela AS produto_nome,
       p.tipo, p.subtipo, p.categoria_id,
       cp.codigo AS categoria_codigo,
       cp.grupo_dashboard, cp.conta_valor,
       cp.conta_pontuacao,
       l.nome AS loja_nome,
       r.nome AS regiao_nome,
       con.nome AS consultor_nome
FROM contratos_pagos c
JOIN lojas l ON l.id = c.loja_id
JOIN regioes r ON r.id = l.regiao_id
LEFT JOIN produtos p ON p.id = c.produto_id
LEFT JOIN categorias_produto cp ON cp.id = p.categoria_id
LEFT JOIN consultores con ON con.id = c.consultor_id
WHERE c.periodo_id = :periodo_id;
```

### 6.2 Pontuação do período

```sql
-- Com fallback automático
SELECT * FROM obter_pontuacao_periodo(3, 2026);

-- Ou via view materializada
SELECT * FROM v_pontuacao_efetiva
WHERE mes = 3 AND ano = 2026;
```

### 6.3 Metas do período

```sql
SELECT m.*, l.nome AS loja_nome
FROM metas m
JOIN lojas l ON l.id = m.loja_id
WHERE m.periodo_id = :periodo_id;
```

### 6.4 Cálculo de pontos por contrato

O dashboard calcula pontos assim:

```
pontos_contrato = valor × pontos_da_categoria
```

Onde `pontos_da_categoria` vem de `obter_pontuacao_periodo(mes, ano)`
ou `v_pontuacao_efetiva`, filtrado pela `categoria_id` do produto
do contrato.

**Produtos com `conta_pontuacao = false` recebem pontos = 0.**

### 6.5 Agrupamentos do dashboard

O dashboard agrupa contratos em 5 grupos de produto usando
`categorias_produto.grupo_dashboard`:

| grupo_dashboard | Inclui categorias                                    |
|-----------------|------------------------------------------------------|
| `CNC`           | CNC                                                  |
| `SAQUE`         | SAQUE, SAQUE_BENEFICIO                               |
| `CLT`           | CONSIG_PRIV                                          |
| `CONSIGNADO`    | CONSIG_BMG, CONSIG_ITAU, CONSIG_C6, PORTABILIDADE   |
| `PACK`          | FGTS, CNC_13, ANT_BENEF                             |

Categorias com `grupo_dashboard = NULL` são **produtos especiais**
exibidos separadamente (CARTAO, BMG_MED, SEGURO_VIDA, SUPER_CONTA).

---

## 7. Views e Funções Disponíveis

### 7.1 `contratos_pagos` (view)

Filtra apenas contratos com
`status_pagamento_cliente = 'PAGO AO CLIENTE'`.
Respeita RLS (`security_invoker`).

### 7.2 `v_pontuacao_efetiva` (view)

Cross join de `periodos × categorias_produto` com fallback
automático. Para cada período e categoria, retorna:

| Coluna             | Descrição                              |
|--------------------|----------------------------------------|
| periodo_id         | UUID do período                        |
| mes, ano           | Mês e ano                              |
| referencia         | Label (ex: Mar/26)                     |
| categoria_id       | UUID da categoria                      |
| categoria_codigo   | Código (ex: CNC)                       |
| categoria_nome     | Nome (ex: CNC)                         |
| grupo_dashboard    | Grupo do dashboard                     |
| grupo_meta         | Grupo de meta                          |
| conta_valor        | Se conta para KPIs de valor            |
| conta_pontuacao    | Se conta para KPIs de pontos           |
| pontos             | Multiplicador efetivo                  |
| producao           | Fator de produção                      |
| is_fallback        | `true` se herdou de período anterior   |

### 7.3 `obter_pontuacao_periodo(mes, ano)` (função)

Retorna pontuação efetiva para um mês/ano específico.
Se não houver dados para o período, busca o período anterior
mais recente (até 24 meses para trás).

```sql
SELECT * FROM obter_pontuacao_periodo(4, 2026);
-- Se abril não tem dados, retorna dados de março
-- com is_fallback = true
```

---

## 8. Pontuação — Regra de Fallback

### Comportamento

Pontuações podem mudar mensalmente. Porém, nem sempre o mês atual
tem seus dados de pontuação inseridos a tempo.

**Regra:** Se o período solicitado não tem registros em `pontuacao`,
usar os do período anterior mais recente que tenha dados.

### Exemplo

| Período | CNC   | FGTS  | Origem    |
|---------|-------|-------|-----------|
| Jan/26  | 6.0   | 1.5   | Próprio   |
| Fev/26  | 5.5   | 1.5   | Próprio   |
| Mar/26  | 5.5   | 2.0   | Próprio   |
| Abr/26  | —     | —     | ← Usa Mar |
| Mai/26  | —     | —     | ← Usa Mar |

Quando Abr/26 for inserido com seus próprios dados, o fallback
deixa de se aplicar automaticamente.

### Para o angry-man

- **Inserir pontuação assim que disponível.** Se o mês ainda não
  tem dados, não precisa fazer nada — o fallback cuida.
- **Garantir que o `periodo_id` exista** em `periodos` antes de
  inserir.
- **Inserir todas as categorias do mês** de uma vez (não
  inserções parciais).

---

## 9. Categorias de Produto — Referência Completa

```
┌─────────────────┬──────────────────────┬───────────────┬──────────────────┬───────┬───────┐
│ codigo          │ nome                 │ grupo_dash.   │ grupo_meta       │ valor │ pts   │
├─────────────────┼──────────────────────┼───────────────┼──────────────────┼───────┼───────┤
│ CNC             │ CNC                  │ CNC           │ CNC              │ ✓     │ ✓     │
│ CNC_13          │ CNC 13               │ PACK          │ FGTS_ANT_BENEF_13│ ✓     │ ✓     │
│ FGTS            │ FGTS                 │ PACK          │ FGTS             │ ✓     │ ✓     │
│ ANT_BENEF       │ Ant. de Benef.       │ PACK          │ FGTS_ANT_BENEF_13│ ✓     │ ✓     │
│ SAQUE           │ Saque                │ SAQUE         │ SAQUE            │ ✓     │ ✓     │
│ SAQUE_BENEFICIO │ Saque Beneficio      │ SAQUE         │ SAQUE            │ ✓     │ ✓     │
│ CONSIG_BMG      │ Consig BMG           │ CONSIGNADO    │ CONSIGNADO       │ ✓     │ ✓     │
│ CONSIG_ITAU     │ Consig Itau          │ CONSIGNADO    │ CONSIGNADO       │ ✓     │ ✓     │
│ CONSIG_C6       │ Consig C6            │ CONSIGNADO    │ CONSIGNADO       │ ✓     │ ✓     │
│ CONSIG_PRIV     │ Consig Priv          │ CLT           │ CLT              │ ✓     │ ✓     │
│ PORTABILIDADE   │ Portabilidade        │ CONSIGNADO    │ CONSIGNADO       │ ✓     │ ✓     │
│ SUPER_CONTA     │ Super Conta          │ —             │ SUPER_CONTA      │ ✓     │ ✓     │
│ CARTAO          │ Cartao               │ —             │ EMISSAO          │ ✗     │ ✗     │
│ BMG_MED         │ BMG Med              │ —             │ BMG_MED          │ ✗     │ ✗     │
│ SEGURO_VIDA     │ Seguro Vida Familiar │ —             │ VIDA_FAMILIAR    │ ✗     │ ✗     │
└─────────────────┴──────────────────────┴───────────────┴──────────────────┴───────┴───────┘
```

---

## 10. Mapeamento de Metas — Referência Completa

Cada coluna da planilha de metas vira um registro normalizado:

| Coluna na planilha               | produto            | escopo     | nivel  |
|----------------------------------|--------------------|------------|--------|
| BRONZE LOJA                      | GERAL              | LOJA       | BRONZE |
| PRATA LOJA                       | GERAL              | LOJA       | PRATA  |
| OURO LOJA                        | GERAL              | LOJA       | OURO   |
| BRONZE CONSULTOR                 | GERAL              | CONSULTOR  | BRONZE |
| PRATA CONSULTOR                  | GERAL              | CONSULTOR  | PRATA  |
| OURO CONSULTOR                   | GERAL              | CONSULTOR  | OURO   |
| CNC LOJA                         | CNC                | LOJA       | NULL   |
| CNC CONSULTOR                    | CNC                | CONSULTOR  | NULL   |
| SAQUE LOJA                       | SAQUE              | LOJA       | NULL   |
| SAQUE CONSULTOR                  | SAQUE              | CONSULTOR  | NULL   |
| EMISSAO                          | EMISSAO            | LOJA       | NULL   |
| EMISSAO CONSULTOR BRONZE         | EMISSAO            | CONSULTOR  | BRONZE |
| EMISSAO CONSULTOR PRATA          | EMISSAO            | CONSULTOR  | PRATA  |
| EMISSAO CONSULTOR OURO           | EMISSAO            | CONSULTOR  | OURO   |
| SUPER CONTA                      | SUPER_CONTA        | LOJA       | NULL   |
| SUPER CONTA CONS. BRONZE         | SUPER_CONTA        | CONSULTOR  | BRONZE |
| SUPER CONTA CONS. PRATA          | SUPER_CONTA        | CONSULTOR  | PRATA  |
| SUPER CONTA CONS. OURO           | SUPER_CONTA        | CONSULTOR  | OURO   |
| VIDA FAMILIAR                    | VIDA_FAMILIAR      | LOJA       | NULL   |
| VIDA FAMILIAR BRONZE             | VIDA_FAMILIAR      | CONSULTOR  | BRONZE |
| VIDA FAMILIAR PRATA              | VIDA_FAMILIAR      | CONSULTOR  | PRATA  |
| VIDA FAMILIAR OURO               | VIDA_FAMILIAR      | CONSULTOR  | OURO   |
| META FGTS                        | FGTS               | LOJA       | NULL   |
| META FGTS (CONSULTOR)            | FGTS               | CONSULTOR  | NULL   |
| CLT                              | CLT                | LOJA       | NULL   |
| CLT CONSULTOR                    | CLT                | CONSULTOR  | NULL   |
| META LOJA FGTS & ANT BEN 13     | FGTS_ANT_BENEF_13  | LOJA       | NULL   |
| META /FGTS/ANT BENEF 13         | FGTS_ANT_BENEF_13  | CONSULTOR  | NULL   |
| BMG MED                          | BMG_MED            | LOJA       | NULL   |
| BMG MED CONSULTOR BRONZE         | BMG_MED            | CONSULTOR  | BRONZE |
| BMG MED CONSULTOR PRATA          | BMG_MED            | CONSULTOR  | PRATA  |
| BMG MED CONSULTOR OURO           | BMG_MED            | CONSULTOR  | OURO   |
| MIX LOJA                         | MIX                | LOJA       | NULL   |
| CONSIGNADO                       | CONSIGNADO         | LOJA       | NULL   |
| CONSIG TOTAL CONSULTOR           | CONSIGNADO         | CONSULTOR  | NULL   |

---

## 11. Perfis de Usuário

O sistema possui 4 perfis com diferentes níveis de acesso:

| Perfil | Visão dos dados | Gerenciar usuários | Escopo |
|--------|-----------------|--------------------|--------|
| `admin` | Global (todos os dados) | Sim (CRUD completo) | Não precisa |
| `gestor` | Global (todos os dados) | Não (só alterar própria senha) | Não precisa |
| `gerente_comercial` | Filtrado por região | Não | Lista de regiões |
| `supervisor` | Filtrado por loja | Não | Lista de lojas |

### Criação de usuários

Usuários são criados pelo **admin** via dashboard (aba
"Usuarios") ou diretamente no banco:

```sql
-- Inserir usuario (senha é hash bcrypt)
INSERT INTO usuarios (usuario, nome, perfil, senha_hash, ativo)
VALUES (
    'rafael.cerqueira',
    'Rafael Silva Cerqueira',
    'gestor',
    -- hash bcrypt gerado pelo Python:
    -- from src.dashboard.auth import gerar_hash_senha
    -- gerar_hash_senha('senha_inicial')
    '$2b$12$...',
    true
);

-- Para gestor e admin: não precisa de escopo
-- Para gerente_comercial: inserir escopos de região
INSERT INTO usuario_escopos (usuario_id, regiao_id)
VALUES (
    (SELECT id FROM usuarios WHERE usuario = 'joao.gerente'),
    (SELECT id FROM regioes WHERE nome = 'LESTE')
);

-- Para supervisor: inserir escopos de loja
INSERT INTO usuario_escopos (usuario_id, loja_id)
VALUES (
    (SELECT id FROM usuarios WHERE usuario = 'maria.supervisora'),
    (SELECT id FROM lojas WHERE nome = 'LOJA CENTRO 01')
);
```

### Seed do admin inicial

```bash
.venv/bin/python scripts/seed_admin.py
# Cria usuario 'admin' com senha 'mgcred2026'
```

---

## 12. Checklist de Validação Pós-Carga

Queries para validar que os dados foram inseridos corretamente.

### Verificar integridade referencial

```sql
-- Contratos com loja inexistente
SELECT contrato_id FROM contratos
WHERE loja_id NOT IN (SELECT id FROM lojas);

-- Contratos com consultor inexistente
SELECT contrato_id FROM contratos
WHERE consultor_id IS NOT NULL
  AND consultor_id NOT IN (SELECT id FROM consultores);

-- Contratos com produto inexistente
SELECT contrato_id FROM contratos
WHERE produto_id IS NOT NULL
  AND produto_id NOT IN (SELECT id FROM produtos);

-- Produtos sem categoria
SELECT tabela, tipo FROM produtos
WHERE categoria_id IS NULL;
```

### Verificar completude mensal

```sql
-- Contar contratos por período
SELECT p.referencia, COUNT(c.id)
FROM periodos p
LEFT JOIN contratos c ON c.periodo_id = p.id
GROUP BY p.referencia
ORDER BY p.ano, p.mes;

-- Verificar se pontuação existe para o período
SELECT p.referencia,
       COUNT(pt.id) AS categorias_com_pontos,
       (SELECT COUNT(*) FROM categorias_produto
        WHERE ativo = true) AS total_categorias
FROM periodos p
LEFT JOIN pontuacao pt ON pt.periodo_id = p.id
GROUP BY p.referencia, p.ano, p.mes
ORDER BY p.ano, p.mes;

-- Verificar metas do período
SELECT p.referencia, COUNT(m.id) AS total_metas,
       COUNT(DISTINCT m.loja_id) AS lojas_com_meta
FROM periodos p
LEFT JOIN metas m ON m.periodo_id = p.id
GROUP BY p.referencia, p.ano, p.mes
ORDER BY p.ano, p.mes;
```

### Verificar pontuação com fallback

```sql
-- Ver pontuação efetiva do mês atual
-- (mostra se está usando fallback)
SELECT categoria_codigo, pontos, periodo_origem,
       is_fallback
FROM obter_pontuacao_periodo(
    EXTRACT(MONTH FROM CURRENT_DATE)::INTEGER,
    EXTRACT(YEAR FROM CURRENT_DATE)::INTEGER
);
```

### Verificar categorias sem pontuação

```sql
-- Categorias ativas que nunca tiveram pontuação
SELECT cp.codigo, cp.nome
FROM categorias_produto cp
WHERE cp.ativo = true
  AND NOT EXISTS (
    SELECT 1 FROM pontuacao pt
    WHERE pt.categoria_id = cp.id
  );
```
