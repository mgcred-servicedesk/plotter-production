# Regras de Negócio

Regras obrigatórias em qualquer cálculo de KPI. Divergir delas quebra
produção.

## Pontuação

`pontos = VALOR × PTS`

- `PTS` vem da tabela `pontuacao` via RPC `obter_pontuacao_periodo(p_mes, p_ano)`.
- `VALOR` é o campo `valor` do contrato, sempre convertido com `float(c.get("valor", 0))`.
- Se `conta_pontuacao = False` na categoria → `pontos = 0`.
- Se `conta_valor = False` na categoria → `VALOR = 0` no agregado.

### Portabilidade — alias por banco

A categoria `PORTABILIDADE` **não tem entrada própria** em `pontuacao`. O
multiplicador é herdado do `CONSIG_<banco>` correspondente ao `BANCO` do
contrato:

| `BANCO` (normalizado) | Categoria de pts usada |
|---|---|
| `BMG` / `BANCO BMG` | `CONSIG_BMG` |
| `C6 BANK` / `C6` / `BANCO C6` | `CONSIG_C6` |
| `ITAU` / `ITAÚ` / `BANCO ITAU` / `BANCO ITAÚ` | `CONSIG_ITAU` |

`CONSIG_PRIV` **não se aplica a portabilidade** (produto distinto). Bancos
não mapeados permanecem com `PONTOS = 0`.

Resolvido em código ([`src/dashboard/loaders.py`](../../src/dashboard/loaders.py)
— constante `_PORTAB_BANCO_TO_CONSIG` + override após o lookup de `PONTOS`)
e não via tabela `pontuacao` porque o diferencial é `BANCO`, granularidade
maior que categoria. A migration 013 explicitamente deixou portabilidade
fora do alias estrutural por causa dessa granularidade.

### Diagnóstico de categorias sem pontuação

Categoria presente nos contratos mas **ausente** da tabela `pontuacao` do
período pontua **zero** e distorce silenciosamente os KPIs. O dashboard
detecta isso na carga (`app.py`) e emite `st.warning`:

- `N contratos sem categoria` — `TIPO_PRODUTO` não mapeado em `categorias_produto`.
- `N categorias sem pontuacao` — categoria do contrato sem entrada em `pontuacao`.

Revisar no início de cada período e ao introduzir produtos novos. (Sucessor
vivo do antigo aviso baseado na planilha `pontuacao/pontos_{mes}.xlsx`.)

## Emissão de cartão

`TIPO_PRODUTO ∈ {CARTÃO BENEFICIO, Venda Pré-Adesão}`:

- **Contam apenas como quantidade**.
- `conta_valor = False` e `conta_pontuacao = False` em `categorias_produto`.
- Excluídos de somatórios de valor e pontos; aparecem em KPIs de "unidades produzidas".

## Seguros (BMG Med / Vida Familiar)

Identificação via coluna `TIPO OPER.` (vem de `tipo_operacao` no banco):

| `TIPO OPER.` | Rótulo na UI |
|---|---|
| `BMG MED` | "Med" |
| `Seguro` | "Vida Familiar" |

Regras:

- **Contam apenas como quantidade** (igual cartão).
- No Supabase, esses contratos **não** recebem `status_pagamento_cliente = 'PAGO AO CLIENTE'`.
- Entram em "Contratos Pagos" via `sub_status_banco = 'Liquidada'` combinado com `tipo_operacao ∈ {BMG MED, Seguro}`.
- Têm breakdown próprio no renderer `_render_tab_em_analise` (commit `adae6c1`).

## Super Conta

`SUBTIPO = SUPER CONTA` — subcategoria de CNC.

- **Conta duplamente**: para valor/pontos **como CNC** E separadamente como produção de Super Conta (quantidade).
- No DB: categoria `SUPER_CONTA` com `grupo_dashboard = 'CNC'` e entrada própria em `pontuacao` com o mesmo multiplicador do CNC.

## Pipeline "Em Análise"

O sistema de origem só retorna `status_banco ∈ {EM ANALISE, CANCELADO}` e
**não** atualiza o `status_banco` quando o contrato é pago. O dashboard
deriva "Em Análise" excluindo do conjunto:

| Condição excluída | Motivo |
|---|---|
| `status_pagamento_cliente = 'PAGO AO CLIENTE'` | já pago → remover do pipeline |
| `status_banco = 'CANCELADO'` | cancelado → nunca aparece |
| `sub_status_banco = 'Liquidada'` | seguro liquidado → já "pago" |

Essas três exclusões são **cumulativas**.

## Cancelados — contenção de redigitação

O total de cancelados infla com **redigitações** (a mesma proposta digitada
várias vezes por erro de averbação do banco ou de operação) e com canceladas
que foram redigitadas e **pagas** depois. Para informar o churn corretamente,
a RPC `obter_cancelados_classificados` (migration `032`) classifica cada
cancelado em uma de três classes — matching **no banco**, pelo nome do cliente
(`contratos.cliente`, homônimos = risco aceito), em janela de **7 dias** e por
**`categoria_codigo`** ("mesmo produto"):

| Classe | Critério | Conta? |
|---|---|---|
| `redigitada` | existe outro **cancelamento** do mesmo nome+categoria com `data_cadastro` posterior em ≤7d (vale em cadeia: A→B→C com gaps ≤7d mantém só C) | Não |
| `recuperada` | não-redigitada, mas existe **paga** do mesmo nome+categoria com `data_cadastro` entre o cancelamento e +7d | Não |
| `liquido` | representante final sem paga em 7d (conta mesmo que o cliente seja pago **depois** dos 7d) | **Sim** |

`nome_norm = upper(trim(regexp_replace(cliente, '\s+', ' ', 'g')))`; nome vazio
nunca casa. O **nome nunca sai do banco** — só a coluna `classificacao` (por isso
o matching é SQL, não Python; ver [data-layer.md](data-layer.md)). `valor`/`qtd`/
churn de cancelados passam a usar apenas `liquido`; redigitadas/recuperadas
voltam como contexto (`qtd_bruto`, `qtd_redigitadas`, `qtd_recuperadas`).

**RLS:** o dashboard lê em **escopo completo** (cliente Supabase único; sem GUC
por usuário) e o filtro por perfil é **client-side** via `aplicar_rls(df)`
([rls.md](rls.md)). Logo a classificação é computada no SQL sobre **toda** a
base — redigitações/recuperações por qualquer consultor **são detectadas** — e
só depois as linhas são filtradas ao escopo do usuário. (A RPC é `SECURITY
INVOKER` e herda esse escopo completo.)

### Oportunidades perdidas (por nível de perfil)

A RPC marca a venda capturada **fora do próprio nível** — representante
(não-redigitada) que **não** foi recuperado no próprio nível, mas foi pago por
alguém de fora dele em ≤7 dias:

| Flag | Verdadeiro quando pago por… | Exibido p/ perfil |
|---|---|---|
| `recuperada_outro` | **outro consultor** | consultor |
| `recuperada_outra_loja` | **outra loja** | supervisor |
| `recuperada_outra_regiao` | **outra região** | gerente_comercial |

A semântica respeita o nível: recaptura **dentro** do próprio nível não é perda
(ex.: outro consultor da mesma loja não é perda da loja). Como a leitura é
full-scope, tudo é detectável no SQL; após `aplicar_rls` sobram as canceladas do
escopo do usuário, e o flag do nível alimenta a seção **"Oportunidades
perdidas"** (qtd + valor perdido). São subconjunto de `recuperada`: **não**
alteram a contagem de líquidos. A identidade de quem capturou a venda **não** é
exposta (só o flag e o valor saem do banco). As três colunas vêm da RPC
`obter_cancelados_classificados` (migration 033 — ver [data-layer.md](data-layer.md)).

### Assertividade dos consultores

`assertividade = (1 − redigitadas / total_propostas) × 100` por consultor, com
`total_propostas = pagas + em análise + canceladas (bruto)`. Mede o retrabalho
operacional (redigitação). Como as fontes têm janelas de carga distintas, o
denominador é uma aproximação do período.

## Metas

### Estrutura

- **Meta Prata** (base) e **Meta Ouro** (premium), em pontos.
- Metas gerais (tabela `metas`, `escopo='GERAL'` ou por loja).
- Metas por produto (tabela `metas_produto`).

### Meta diária restante

```
meta_diaria = (Meta Prata - pontos_atuais) / DU_restantes
```

- `pontos_atuais`: pontuação acumulada do período vigente.
- `DU_restantes`: via `calcular_dias_uteis(ano, mes, dia_atual)` — considera feriados do DB.

### Projeção

```python
media_du  = total / du_dec if du_dec > 0 else 0
projecao  = media_du * du_total
perc_proj = projecao / meta * 100 if meta > 0 else 0
```

## Emissão de contrato — zeragem de valor

Commit `292ab90`: contratos de categoria "emissão" (quando aplicável) têm
`VALOR` zerado na consolidação para não inflar totais. Ver script
`scripts/diagnostico/diagnosticar_valor_total.py` para referência.

## Exclusão de supervisores

Supervisores **não aparecem** em análises consultor-level:

```python
def _excluir_supervisores(df, df_sup):
    if df_sup is not None and "SUPERVISOR" in df_sup.columns and "CONSULTOR" in df.columns:
        return df[~df["CONSULTOR"].isin(df_sup["SUPERVISOR"].unique())].copy()
    return df.copy()
```

Aplicar **antes** de rankings, contagens de consultores e médias por consultor.

## Reconquista (v2)

Campanha de retenção. Fonte: export único `reconquista.xlsx`, **1 linha por
cliente** (`co_adesao`), já classificado em `status`. Tabela `reconquista`
(truncada e realimentada a cada carga via RPC `fn_importar_reconquista`);
leitura pela view `v_reconquista`. Loader: `carregar_reconquista(mes, ano)`.

### Estados (validados 100% contra o arquivo)

- **EFETIVADA** — reconquista confirmada: `dt_macica > dt_fim_relacionamento`.
- **PROMESSA** — aceite via DNA **ou** produção de CNC (exceto antecipação)
  após o fim: (`dt_dna > dt_fim_relacionamento` ou
  `dt_producao > dt_fim_relacionamento`) e não-efetivada.
- **SEM RECONQUISTA** — demais (a trabalhar).

### Apuração mensal com defasagem de 1 mês

O mês de apuração `M` exibe os contratos com `dt_fim_relacionamento` em
`M-1` (os de `M` só entram na esteira no mês seguinte). A defasagem é
aplicada no **loader** (`_mes_apuracao_anterior`); a view expõe o mês real
de `dt_fim` em `ref_ano`/`ref_mes`.

| Apuração (seleção) | `dt_fim_relacionamento` | EFET / PROM / SEM |
|---|---|---|
| Maio/2026 | Abril/2026 | 36 / 23 / 249 |
| Junho/2026 | Maio/2026 | 0 / 33 / 288 |

EFETIVADA "zerada" no mês mais recente é **esperado**: depende de
`dt_macica > dt_fim`; quando a maciça desses contratos virar (novo
`dt_macica` no próximo export), eles migram para EFETIVADA.

### Elegibilidade (coluna `flag_elegibilidade`)

O arquivo traz `flag_elegibilidade` (`ELEGIVEL` / `NAO ELEGIVEL`). **Só
ELEGIVEL entram na apuração/conversão** (numerador e denominador); os
`NAO ELEGIVEL` continuam visíveis nos analíticos (detalhe por cliente),
apenas fora da conta. **NULL / sem flag ⇒ ELEGIVEL** (interim, até o
arquivo com a flag ser importado). Helper: `_mask_elegivel` (loaders).

### KPI — conversão e faixa de prêmio (substitui a meta fixa)

Sem meta de 30%. O objetivo é o **% de conversão** sobre a base elegível
= `EFETIVADA / total ELEGIVEL` do mês de referência, mapeado numa faixa
de prêmio/deflator sobre o prêmio CNC (indicador — não calcula R$):

| % Conversão | Ajuste sobre prêmio CNC |
|---|---|
| 0 a 10% | −20% |
| 10,1 a 20% | −10% |
| 20,1 a 29,99% | 0 |
| 30 a 39,99% | +10% |
| ≥ 40% | +20% |

Fronteiras contínuas (limite superior inclusivo nas negativas):
`_faixa_premio_conversao` (loaders). PROMESSA é pipeline; SEM RECONQUISTA
é a trabalhar.

> **LGPD:** `nu_matricula` **não** é armazenada. `co_adesao` identifica o
> contrato, não a pessoa.
