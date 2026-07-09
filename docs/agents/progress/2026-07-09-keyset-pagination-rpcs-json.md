# 2026-07-09 — Disk IO Budget (parte 2): keyset pagination + RPCs _json

**Agente:** Claude Code
**Tipo:** perf (código + migrations)
**Arquivos tocados:** `src/dashboard/loaders.py`,
`database/migrations/056_fn_diag_work_mem.sql`,
`database/migrations/057_rpcs_json_unico.sql`,
`docs/agents/data-layer.md`
**Commit(s):** (ver git log deste dia)

## Objetivo

Continuação do diagnóstico de 2026-07-08: o Disk IO Budget seguia
queimando (65% em 09/jul) mesmo com a 054 aplicada — GUC de role só
vale em conexões novas do pool. Eliminar os drenos estruturais que
restavam no código do dashboard.

## O que foi feito

- **Keyset pagination** (`_paginar_keyset`, loaders.py) substituiu
  OFFSET nos 3 fetchers de views: `v_contratos_dashboard` (cursor
  `id`), `v_pagamentos_online_efetivo` (cursor `proposta`, PK) e
  `v_reconquista` (cursor `co_adesao`, UNIQUE). Com OFFSET cada página
  reordenava o resultset inteiro (sort → spill p/ temp files); com
  cursor todo request é top-N ≤ 1000 linhas — nunca spilla,
  independente de work_mem.
- **Migration 057**: wrappers aditivos `*_json` (`json_agg` +
  `COALESCE('[]')`) para `obter_contratos_em_analise`,
  `obter_digitacao_diaria_detalhe` e `obter_cancelados_classificados`;
  loaders passaram a chamá-los **uma vez**, sem `.range()` — o
  PostgREST reexecutava a função inteira por página (cancelados:
  ~2,6 s/página).
- **Migration 056**: `fn_diag_work_mem()` — única forma de ver o
  work_mem vigente nas conexões do pool (SQL Editor roda como
  `postgres` e não prova nada).
- `docs/agents/data-layer.md`: keyset vira o padrão canônico; OFFSET
  proibido em novos loaders; padrão `*_json` documentado para RPCs
  com resultset > 1000 linhas.
- Verificação real (script scratchpad): contratos pagos 7/2026 com
  1.524 linhas em 2 páginas — paridade exata com `count=exact` e
  cursor sem duplicatas; reconquista 6/2026 idem (406 linhas);
  259 testes pytest verdes; ruff limpo.

## Decisões não óbvias

- **Ordem de pagamentos_online mudou** (era `data_status desc`, virou
  `proposta asc`): cursor composto via `.or_()` seria complexidade sem
  consumidor — a aba só agrega (max/sum/len). Efeito cosmético
  possível apenas na ordem de grupos não mapeados em `GRUPO_DISPLAY`.
- **Wrappers `_json` aditivos, não CREATE OR REPLACE das originais**:
  mudar tipo de retorno exigiria DROP (quebra atômica entre migration
  e deploy); originais ficam para debug no SQL Editor.
- **`_fetch_reconquista` tinha bug latente**: OFFSET sem ORDER BY —
  ordem instável podia repetir/perder linhas entre páginas. O keyset
  corrige de graça.
- **Sequência de deploy importa**: rodar a 057 no SQL Editor ANTES de
  deployar o app (loaders chamam `*_json`; sem a migration → APIError
  404 nos quadros de em análise/cancelados/digitação detalhe).

## Pendências / follow-ups

- [ ] Usuário: rodar 055 no SQL Editor + **restart do projeto** (ativa
      a 054 no pool) + baseline `temp_files`/`temp_bytes` +
      `pg_stat_statements_reset()`.
- [ ] Usuário: rodar 056 e conferir `work_mem=12MB` via REST (curl no
      corpo da migration).
- [ ] Usuário: rodar 057 (aditiva; não quebra o app em produção) e só
      então deployar este código.
- [ ] Medição 48h pós-deploy: `temp_files` ~parado; nenhum
      `temp_blks_written > 0` nas queries do dashboard; cancelados com
      1 execução por cache-miss; gráfico do Disk IO Budget.
- [ ] Repo do ETL (externo): aplicar spec `IS DISTINCT FROM` +
      TRUNCATE — enquanto não aplicada, parte do consumo persiste
      (WAL + autovacuum).
- [ ] Decisão do upgrade Free/Nano → Pro/Micro.
- [ ] Clone vazio de `contratos` em outro schema (achado da auditoria
      de 08/jul) — identificar e limpar.
- [ ] Futuro: dropar `fn_diag_work_mem` e as RPCs paginadas originais
      quando a medição fechar (migration própria, com aprovação).

## Patterns criados ou atualizados

- Keyset pagination como padrão canônico de paginação
  (docs/agents/data-layer.md, seção Paginação).
- Padrão `*_json` para RPCs com resultset > 1000 linhas
  (docs/agents/data-layer.md, seção RPC).

## Referências

- Diagnóstico: [2026-07-08-disk-io-budget-diagnostico-work-mem.md](2026-07-08-disk-io-budget-diagnostico-work-mem.md)
- Docs: [docs/agents/data-layer.md](../data-layer.md)
