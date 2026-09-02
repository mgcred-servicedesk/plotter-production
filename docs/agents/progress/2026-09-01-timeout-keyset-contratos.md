# 2026-09-01 — Timeout 57014 na paginação keyset de contratos pagos

**Agente:** Claude Code
**Tipo:** bugfix
**Arquivos tocados:** `src/dashboard/loaders.py`,
`database/migrations/098_index_contratos_periodo_keyset.sql`,
`tests/test_loaders_paginacao_keyset.py`,
`tests/test_loaders_cobranca_consignavel.py`
**Commit(s):** (não commitado)

## Objetivo

Investigar `postgrest.exceptions.APIError: {'code': '57014', 'message':
'canceling statement due to statement timeout'}` derrubando a carga do
dashboard em `_fetch_contratos_pagos` → `_paginar_keyset`.

## O que foi feito

- **Diagnóstico:** não é regressão. `v_contratos_dashboard` não muda
  desde a migration 067; as 095/096/097 não a redefinem (a 096 só lê
  dela). O 57014 é cancelamento server-side, não bug de Python.
- **Medição** (08/2026, 5.630 linhas, 6 páginas): `2,32s · 2,02s ·
  1,19s · 1,35s · 1,39s · 1,13s` — a query está saudável em repouso.
  Total ~9,4s de banco para UM mês.
- **Medição da 1ª página por período**, sem correlação com volume:
  `05/2026: 5.627 linhas → 4,13s` vs `01/2026: 7.043 linhas → 0,61s`;
  `08/2026: 5.630 → 2,66s` vs `03/2026: 11.442 → 1,14s`. 7x de
  variância = contenção (ETL do angry-man escrevendo em `contratos`),
  contra teto de 15s por statement.
- **Retry em `_paginar_keyset`** — 3 tentativas por página, só no
  57014, backoff `0 / 1,5s / 4,0s`, a última com lote reduzido (250).
- **Migration 098** — `CREATE INDEX idx_contratos_periodo_keyset ON
  contratos (periodo_id, id)`, para o keyset virar range scan sem sort.
- **9 testes novos** em `tests/test_loaders_paginacao_keyset.py`.
- Validado E2E contra o Supabase real: 5.630 linhas (bate com o
  `count='exact'` da view), zero duplicata, `VALOR` total 9.691.376,60.

## Decisões não óbvias

- **O keyset não tinha eliminado o sort.** Nenhum índice liderava por
  `(periodo_id, id)`: a 055 dropou `idx_contratos_periodo_id` e
  `idx_contratos_periodo_loja`, e o sobrevivente
  `idx_contratos_periodo_status_pag` tem `status_pagamento_cliente` na
  2ª posição — não serve para ordenar por `id`. O planner lia o período
  inteiro e ordenava a cada página. **O custo decrescente medido
  (2,32 → 1,13s) é a impressão digital disso**: cada página reordenava
  o conjunto restante. A 054 já nomeava essa paginação como spiller de
  temp files; `work_mem=12MB` fez o sort caber em RAM, a 098 remove o
  sort.

- **Índice novo contraria a direção da 055** (que dropou 5 índices
  porque `contratos` tem 1,39M updates para 200k inserts e cada índice
  amplifica escrita). Aceito porque não é índice especulativo: casa
  exatamente com o único padrão de acesso do loader mais quente, e o
  que economiza (sort + temp files = **escrita**) é da mesma moeda que
  custa. Se `pg_stat_user_indexes` mostrar `idx_scan` baixo em algumas
  semanas, dropar como a 055 fez.

- **`montar_query` agora recebe o limite** (4 call sites atualizados),
  em vez de fechar sobre `_PAGE_SIZE`. Sem isso o retry não conseguiria
  reduzir o lote.

- **`_executar_pagina` devolve `(linhas, limite_usado)`** — armadilha
  real: com lote reduzido, comparar `len(batch) < _PAGE_SIZE` daria
  "página parcial" numa página de 250/250 e **truncaria o resultset em
  silêncio**. Coberto por
  `test_pagina_reduzida_cheia_nao_encerra_a_paginacao`, verificado por
  mutação (trocar `limite_usado` por `_PAGE_SIZE` faz o teste falhar,
  devolvendo 250 de 300 linhas sem erro).

- **Só o 57014 é retentado.** Qualquer outro código (permissão, coluna
  inexistente, sintaxe) é determinístico e sobe intacto — retentar só
  atrasaria o erro. Timeout persistente também sobe: banco degradado é
  para aparecer, não para virar resultado parcial silencioso.

- **Premissa:** o teto de 15s por statement vem do comentário da
  migration 052 (`statement_timeout de 15s`), não de leitura direta de
  `pg_settings` — a chave do `.env` é `service_role` e não há RPC para
  inspecionar GUC. Vale confirmar no SQL Editor.

## Resultado após aplicar a 098 (mesmo dia)

Migration aplicada pelo usuário. Medições repetidas com o mesmo método
do diagnóstico:

**Paginação completa de 08/2026 (5.630 linhas, 6 páginas):**

| | p1 | p2 | p3 | p4 | p5 | p6 | total |
|---|---|---|---|---|---|---|---|
| antes | 2,32s | 2,02s | 1,19s | 1,35s | 1,39s | 1,13s | **9,40s** |
| depois | 1,39s | 1,05s | 1,05s | 1,33s | 1,32s | 0,68s | **6,82s** |

O ganho de 27% importa menos que a **mudança de perfil**: antes o custo
era decrescente (2,32 → 1,13s), assinatura do sort reprocessando o
conjunto restante a cada página. Depois é plano (~1,0-1,4s), com a
última página menor só por ter 630 linhas. É o comportamento esperado
de range scan com LIMIT.

**1ª página por período — 3 rodadas × 8 períodos, 24 medições:**

- antes: 0,61s a **4,13s** (variância 6,8x, sem correlação com volume)
- depois: 0,38s a **1,43s**, a esmagadora maioria em ~0,95-1,0s

Casos individuais: 05/2026 4,13s → 0,98s; 08/2026 2,66s → 0,96s. E
03/2026, o maior período (11.442 linhas), ficou em 0,62-0,96s — o
volume deixou de importar, que é exatamente o efeito de o LIMIT parar
de ler o índice em vez de ordenar o período inteiro.

**Margem contra o teto de 15s por statement: de ~3,6x para ~10x** no
pior caso observado. É esse número que fecha o bug: o 57014 exigia uma
degradação de 3,6x sobre o pico; agora exige 10x.

**Integridade preservada:** 5.630 linhas (bate com o `count='exact'`),
zero duplicata, `VALOR` total 9.691.376,60 — idêntico ao medido antes
do índice.

## Pendências / follow-ups

- [x] Aplicar a migration 098 no Supabase — feito em 2026-09-01.
- [ ] Rodar a verificação 1 da 098 (`EXPLAIN ANALYZE`) e confirmar que
      sumiu o nó `Sort`. **Ainda não confirmado diretamente**: não há
      como rodar EXPLAIN via PostgREST. O perfil plano acima é
      evidência indireta forte, mas só o SQL Editor fecha a questão.
- [ ] Confirmar o valor real de `statement_timeout` do role da API.
- [ ] A causa raiz da contenção segue de pé (Nano 0,5 GB + ETL
      concorrente). O retry trata o sintoma, a 098 alarga a margem —
      nenhum dos dois substitui janela de ETL ou upgrade de compute.
- [ ] `app.py:1037` ainda mostra "Erro inesperado" genérico para o
      57014 que escapar das 3 tentativas. Mensagem específica ("banco
      ocupado, tente novamente") ficou fora deste escopo.

## Referências

- Migrations relacionadas: 054 (work_mem/temp files), 055 (drop de
  índices), 040 (índices compostos), 052 (statement_timeout 15s), 067
  (definição atual da view).
- Docs consultados: [data-layer.md](../data-layer.md)
