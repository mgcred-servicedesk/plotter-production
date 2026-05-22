# Integração — Pagamentos Online (extrator DNA)

Documentação do contrato de ingestão para o projeto
**angry-man**, especificamente para a feature de Pagamentos
Online (estimativa do dia em andamento).

> **Banco:** Supabase (PostgreSQL) — mesmo do dashboard
> **Schema:** `public`
> **Autenticação:** service_role key (mesma usada para os
> demais imports do angry-man — bypassa RLS)
> **Migração base:** `database/migrations/014_pagamentos_online.sql`

Documento complementar a [`INTEGRACAO.md`](INTEGRACAO.md). Use este
arquivo como única fonte de verdade para a feature de Pagamentos
Online; o `INTEGRACAO.md` continua valendo para o consolidado
mensal.

---

## 1. Visão geral do fluxo

```
                +-----------------------------+
                |  Operador / Sistema DNA     |
                +--------------+--------------+
                               |
                               | extrator CSV (cumulativo)
                               v
                +--------------+--------------+
                | angry-man                   |
                |  - parse CSV                |
                |  - filtra Grupo Produto     |
                |  - DELETE + INSERT atomico  |
                +--------------+--------------+
                               |
                               v
            +--------------------------------------+
            | Supabase                             |
            |  - pagamentos_online (raw filtrado)  |
            |  - v_pagamentos_online_efetivo (view)|
            +--------------------------------------+
                               ^
                               | leitura
                               |
            +--------------------------------------+
            | Dashboard (este repo) — aba          |
            | "Pagamentos Online" (admin/gestor)   |
            +--------------------------------------+
```

**Ciclo de vida (operações):**

São duas operações distintas no angry-man:

1. **Upload de arquivo (substituição do snapshot)**
   - Disparado **manualmente** na fase inicial (operador faz upload
     do CSV no angry-man várias vezes ao dia); por cron horário
     na fase futura.
   - Cada upload executa, em uma única transação:
     `DELETE FROM pagamentos_online; INSERT ...`.
   - O CSV é cumulativo dentro do dia, então substituir tudo evita
     duplicidade e remove propostas que saíram do extrator
     (cancelamentos retroativos).

2. **Limpeza de fim de dia (zerar antes de D+1)**
   - Disparado **manualmente** na fase inicial (botão "Limpar
     Pagamentos Online" no angry-man, acionado pelo operador ao
     fim do expediente); por cron diário na fase futura (ex.: 23:59
     ou 00:01, antes do primeiro upload de D+1).
   - Executa `DELETE FROM pagamentos_online;` simples.
   - **Por que existe**: sem essa limpeza, o dashboard mostraria
     os pagamentos do dia D como se fossem do dia D+1 até o
     primeiro upload novo entrar — dado obsoleto travestido de
     atualizado. Com a limpeza, a aba mostra "Nenhuma proposta paga
     online" até o primeiro upload do dia.

> **Timing crítico**: a limpeza precisa acontecer **antes** do
> primeiro upload do dia seguinte. Se a ordem inverter, o upload
> recém-enviado é apagado. Quando automatizar, agende a limpeza
> em horário sem tráfego (23:59) e o cron do primeiro upload de
> D+1 só a partir das 06:00. Na fase manual, basta o operador
> clicar "Limpar" antes de qualquer upload na manhã seguinte.

A view `v_pagamentos_online_efetivo` é robusta a sobreposições:
se uma ADE aparecer no extrator DNA **e** já estiver consolidada
em `contratos` como `'PAGO AO CLIENTE'`, ela é automaticamente
removida da contagem online (evita duplicar pagamento).

---

## 2. Fontes de entrada

### 2.1 Extrator DNA (upload manual; cron horário no futuro)

**Arquivo:** `relatorio-completo-acompanhamento-propostas.csv`

| Atributo | Valor |
|---|---|
| Encoding | UTF-8 com BOM (`utf-8-sig` no pandas) |
| Separador | `;` (ponto e vírgula) |
| Quebra de linha | CRLF |
| Decimal | `.` |
| Datas | `dd/mm/aaaa` |
| Horas | `HH:MM:SS` (coluna separada) |

**Colunas relevantes** (o CSV tem 33; abaixo só as que vão pra
`pagamentos_online`):

| Coluna CSV | Coluna DB | Tipo |
|---|---|---|
| `Data Implantação` | `data_implantacao` | DATE |
| `Data Status` | `data_status` | DATE |
| `Proposta` | `proposta` (PK) | TEXT |
| `Cliente` | `cliente` | TEXT |
| `Grupo Produto` | `grupo_produto` | TEXT |
| `Produto` | `produto` | TEXT |
| `Loja` | `loja_codigo` | TEXT |
| `Usuário Nome` | `usuario_nome` | TEXT |
| `Status` | `status` | TEXT |
| `Situação` | `situacao` | TEXT |
| `Agrupamento` | `agrupamento` | TEXT |
| `Valor Liquido Digitado` | `valor_liquido_digitado` | NUMERIC(12,2) |
| `Valor Liquido Aprovado` | `valor_liquido_aprovado` | NUMERIC(12,2) |
| `Valor Seguro Aprovado` | `valor_seguro_aprovado` | NUMERIC(12,2) |

> Nulos esperados em campos de valor: o CSV usa string vazia.
> Tratar como `NULL` no banco (não 0).

### 2.2 Códigos de Loja Help (carga eventual)

**Arquivo:** `Codigo Lojas Help.xlsx`

| Atributo | Valor |
|---|---|
| Sheet | `Planilha1` |
| Colunas | `CÓDIGO`, `LOJA`, `status` |

Esta planilha atualiza o campo `lojas.codigo_dna` (UPSERT por
`lojas.nome` ↔ `LOJA`). Cargas dela só são necessárias quando o
catálogo de lojas muda (loja nova, mudança de status). Não é
horário.

---

## 3. Filtros aplicados na ingestão

**Obrigatório antes de inserir em `pagamentos_online`:**

```python
df = df[df["Grupo Produto"].isin([
    "Antecipação em Conta",
    "Crédito na Conta",
])]
```

Cartão BMG e demais grupos não entram. Esses são os únicos
produtos do escopo de "Pagamentos Online".

**O que NÃO é filtrado na ingestão** (fica na view):

- A regra de "pago online" (`Agrupamento='Paga'`) **fica na view**.
  Isso permite evoluir a regra sem mexer no ingestor e mantém a
  tabela útil para futuras visões (ex: pendentes, em análise).
  `Status` e `Situação` continuam sendo armazenados na tabela mas
  não entram no filtro atual — `Agrupamento='Paga'` já é
  suficiente para os grupos importados.

---

## 4. Estratégia de inserção

### 4.1 Upload de arquivo — DELETE + INSERT atômico

Cada upload de CSV no angry-man (manual ou via cron futuro)
substitui integralmente o conteúdo de `pagamentos_online` em
**uma única transação**:

```python
# Pseudocódigo recomendado
df_filtered = parse_and_filter(csv_path)  # ja filtrou Grupo Produto

# Pre-validacao: aborta se o arquivo parece corrompido/vazio
MIN_LINHAS = 50  # ajustar conforme baseline observado
if len(df_filtered) < MIN_LINHAS:
    raise IngestaoSuspeita(
        f"CSV com {len(df_filtered)} linhas — abaixo do minimo "
        f"esperado ({MIN_LINHAS}). Upload abortado."
    )

# Tudo dentro de uma transacao via RPC ou raw SQL
sql = """
    BEGIN;
      SELECT pg_advisory_xact_lock(20260521);  -- evita ciclos concorrentes
      DELETE FROM pagamentos_online;
      INSERT INTO pagamentos_online
        (proposta, data_implantacao, data_status, cliente,
         grupo_produto, produto, loja_codigo, usuario_nome,
         status, situacao, agrupamento,
         valor_liquido_digitado, valor_liquido_aprovado,
         valor_seguro_aprovado)
      VALUES %s;
    COMMIT;
"""
executar_transacao(sql, df_filtered.to_records())
```

Por que **DELETE** em vez de **TRUNCATE**:

- `DELETE` usa locks por linha (`ROW EXCLUSIVE`) — leitores do
  dashboard não são bloqueados durante o upload.
- `TRUNCATE` exige `ACCESS EXCLUSIVE` na tabela, bloqueando
  qualquer SELECT até o COMMIT.
- A diferença de performance é desprezível para o volume da
  tabela (~500–700 linhas).

Por que **transação única** (BEGIN/COMMIT):

- Se o INSERT falhar (rede, validação, etc.), o DELETE é
  desfeito automaticamente — não fica tabela vazia.
- Leitores do dashboard veem ou o estado antigo completo ou o
  novo completo (MVCC). Nunca um meio-termo.

Por que **advisory lock**:

- Se dois operadores clicarem "Upload" simultaneamente, o
  segundo espera o primeiro — não há corrida.
- O id `20260521` é arbitrário; só precisa ser único no
  Supabase para esta operação.

Por que **pré-validação de linhas mínimas**:

- CSV corrompido / extrator com bug poderia chegar com 0
  linhas. Sem essa validação, o DELETE wipea tudo e o INSERT
  não popula nada — dashboard fica zerado silenciosamente.
- Logue também o delta `count_anterior → count_novo` por
  upload. Queda anormal (ex.: >80%) merece alerta.

### 4.2 `lojas.codigo_dna` — UPSERT por nome

```python
# Pseudocódigo recomendado
df_help = pd.read_excel("Codigo Lojas Help.xlsx")
for _, row in df_help.iterrows():
    supabase.table("lojas").update({
        "codigo_dna": str(row["CÓDIGO"])
    }).eq("nome", row["LOJA"]).execute()
```

> Atenção: o `nome` em `lojas` (cadastro interno) pode divergir
> ortograficamente do `LOJA` do Excel. Validar matches antes de
> rodar em produção; logar nomes não encontrados em vez de criar
> lojas novas automaticamente.

### 4.3 Limpeza de fim de dia

Botão "Limpar Pagamentos Online" no angry-man (ou cron futuro):

```sql
DELETE FROM pagamentos_online;
```

**Quando rodar:**

- Fase manual: o operador clica ao fim do expediente (ou na
  manhã seguinte, **antes** de qualquer upload novo).
- Fase automatizada: cron diário em horário sem tráfego
  (ex.: 23:59). Garantir que o cron de upload do dia seguinte
  só dispara a partir de uma hora razoável (ex.: 06:00).

**Atenção ao timing**: se a limpeza rodar **depois** do
primeiro upload do dia seguinte, apaga dados recém-subidos.
Sempre limpeza antes de upload, nunca o inverso.

---

## 5. Schema (referência rápida)

Definições completas: `database/migrations/014_pagamentos_online.sql`.

### `pagamentos_online`

```sql
CREATE TABLE pagamentos_online (
    proposta                TEXT PRIMARY KEY,
    data_implantacao        DATE NOT NULL,
    data_status             DATE NOT NULL,
    cliente                 TEXT NOT NULL,
    grupo_produto           TEXT NOT NULL,
    produto                 TEXT NOT NULL,
    loja_codigo             TEXT NOT NULL,
    usuario_nome            TEXT,
    status                  TEXT NOT NULL,
    situacao                TEXT NOT NULL,
    agrupamento             TEXT NOT NULL,
    valor_liquido_digitado  NUMERIC(12,2),
    valor_liquido_aprovado  NUMERIC(12,2),
    valor_seguro_aprovado   NUMERIC(12,2),
    imported_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `lojas.codigo_dna`

```sql
ALTER TABLE lojas ADD COLUMN codigo_dna TEXT;
ALTER TABLE lojas ADD CONSTRAINT uq_lojas_codigo_dna UNIQUE (codigo_dna);
```

### `v_pagamentos_online_efetivo`

Aplica:
1. Filtro `Agrupamento='Paga'`.
2. Dedup vs `contratos.status_pagamento_cliente = 'PAGO AO CLIENTE'`.
3. Cálculo de `valor_producao`:
   - se `valor_liquido_aprovado` = 0/NULL → `valor_liquido_digitado`
   - caso contrário → `valor_liquido_aprovado + valor_seguro_aprovado`

---

## 6. Checklist pós-deploy

**Fase 1 — manual (inicial):**

- [ ] Migração `014_pagamentos_online.sql` aplicada
- [ ] Seed inicial de `lojas.codigo_dna` rodado a partir do Excel
- [ ] Smoke test: subir o CSV de exemplo e validar que ele aparece
      em `v_pagamentos_online_efetivo`
- [ ] Botão "Upload Pagamentos Online" no angry-man (pré-validação
      de linhas mínimas + DELETE+INSERT atômico + advisory lock)
- [ ] Botão "Limpar Pagamentos Online" no angry-man
      (DELETE simples)
- [ ] Procedimento operacional documentado: quando subir, quando
      limpar
- [ ] Aba "Pagamentos Online" liberada para admin e gestor

**Fase 2 — automação (futura):**

- [ ] Cron horário do angry-man para upload automático
- [ ] Cron diário em 23:59 para limpeza
- [ ] Alerta de queda anormal (delta `count_anterior → count_novo`
      acima de threshold)
- [ ] Monitoramento de `imported_at` (alertar se >2h sem upload)

---

## 7. FAQ

**O que acontece se uma loja do extrator não existir em `lojas`?**
A view faz `LEFT JOIN` em `lojas.codigo_dna`, então a proposta
aparece mas `loja_nome` vem `NULL`. Logar isso no angry-man pra
alertar o operacional cadastrar a loja em `lojas` primeiro.

**E se o filtro DNA mudar (incluir outro Grupo Produto)?**
Basta atualizar o `isin([...])` no angry-man. A tabela e a view
aceitam qualquer valor — não há constraint de domínio.

**A ingestão precisa ser atômica?**
Sim, em produção. Truncate sem insert subsequente deixaria o
dashboard zerado por uma janela. Usar transação ou rodar em
ordem estrita com lock.

**Quantas linhas por ciclo?**
Amostra real (20/05/2026): 649 linhas brutas; ~520 após filtro
de Grupo Produto. Insert único em batch é suficiente.
