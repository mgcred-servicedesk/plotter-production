# 2026-07-08 — Disk IO Budget (Supabase): diagnóstico e work_mem

**Agente:** Claude Code
**Tipo:** research + infra (migration)
**Arquivos tocados:** `database/migrations/054_work_mem_authenticator.sql`
**Commit(s):** (pendente)

## Objetivo

Investigar o aviso do Supabase de depleção do Disk IO Budget do projeto
(compute **Nano**, plano Free) e propor/aplicar correções.

## O que foi feito

- Diagnóstico completo via `pg_stat_statements`, `pg_stat_database` e
  `pg_stat_user_tables` (resultados colados pelo usuário do SQL Editor).
- **Leitura descartada como causa**: cache hit 99,9999%; `blks_read`
  total ~58 MB desde fev/2026; `contratos` tem 68 MB (banco inteiro em
  memória).
- **Dreno 1 — temp files**: 107 GB acumulados (63 mil arquivos).
  Spillers atuais: queries paginadas de `v_contratos_dashboard`
  (`ORDER BY id` + OFFSET, ~0,5 MB de temp/chamada, ~13,5 mil chamadas).
- **Dreno 2 — churn de escrita do ETL** (repo externo): `contratos` com
  1,39M updates vs 200k inserts (~7 reescritas/linha — upserts que
  regravam sem mudança); `pagamentos_online` delete-all + reinsert
  (69 autovacuums); `produtos` reescrita 29×/linha; WAL ~3,4 GB nos
  top 10.
- Criada migration `054_work_mem_authenticator.sql`
  (`work_mem = 12MB` no role `authenticator`) — mata o spill dos sorts.
- Achado lateral (CPU, não disco): `obter_cancelados_classificados`
  custa ~2,6 s/chamada com ~14 GB de tráfego lógico de buffer; a
  paginação `.range()` sobre RPC reexecuta a função inteira por página
  (o PostgREST computa o resultado completo e fatia).

## Decisões não óbvias

- **work_mem no role `authenticator`, não `ALTER DATABASE`** — escopa o
  aumento às queries da API (dashboard + ETL); SQL Editor/autovacuum
  seguem no default. Em Nano (0,5 GB RAM) RAM é o recurso escasso.
- **12MB e não 16/32** — compute Nano; work_mem é por nó de sort por
  query concorrente. Subir junto com eventual upgrade de compute.
- **Correção do churn fica no repo do ETL** — guarda `IS DISTINCT FROM`
  no `ON CONFLICT DO UPDATE` e `TRUNCATE` em vez de DELETE em
  `pagamentos_online`. Fora do escopo deste repo; spec entregue ao
  usuário na conversa.
- **Recomendado upgrade Free/Nano → Pro/Micro** — produção da MGCred em
  free tier é subdimensionada; correções valem de qualquer forma.

## Pendências / follow-ups

- [x] Usuário rodou a 054 no SQL Editor (2026-07-08; `rolconfig`
      confirmado com `work_mem=12MB`). Efeito pleno após reciclagem do
      pool ou restart da API.
- [ ] Acompanhar `temp_files`/`temp_bytes` por 48h (baseline anotado
      na conversa).
- [x] Auditoria de índices feita (contadores desde fev/2026): usuário
      aprovou remoção de 5 índices → criada migration 055
      (`drop_indexes_nao_usados_contratos`). Pendente rodar no SQL
      Editor. Tier 2 (avaliar depois do ETL corrigido):
      `data_status_pagamento` (84), `loja_id` (86),
      `status_pagamento` (202).
- [ ] Achado da auditoria: existe um clone VAZIO de `contratos` em
      outro schema (índices homônimos com 8KB/0 scans). Identificar
      schema e decidir limpeza.
- [ ] Aplicar spec do upsert no repo do ETL.
- [ ] `SELECT extensions.pg_stat_statements_reset();` para janela limpa
      de medição pós-correções.
- [ ] Decisão do upgrade de plano/compute.
- [ ] (Backlog, CPU/latência) reduzir reexecução das RPCs paginadas:
      RPC devolvendo JSON único (`json_agg`) e/ou keyset pagination em
      `v_contratos_dashboard`; índice em `contratos (cliente_norm)`.

## Patterns criados ou atualizados

- (nenhum)

## Referências

- Docs consultados: [docs/agents/data-layer.md](../data-layer.md)
- Guia Supabase: High Disk IO Consumption (link do e-mail de aviso)
