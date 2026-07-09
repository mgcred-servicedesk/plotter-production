# 2026-07-09 — Linter Supabase: segurança (058) e performance (059/060)

**Agente:** Claude Code
**Tipo:** segurança + perf (migrations)
**Arquivos tocados:** `database/migrations/058_revoke_security_definer_anon.sql`,
`database/migrations/059_consolidar_rls_pagamentos_online.sql`,
`database/migrations/060_drop_indexes_nao_usados_churn.sql`
**Commit(s):** a78c0bb (migrations, commit do usuário)

## Objetivo

Fechar os avisos do Supabase Advisor: 9 de SECURITY (funções
SECURITY DEFINER executáveis por anon/authenticated), 5 de
PERFORMANCE (policies permissivas duplicadas em pagamentos_online)
e triagem de 16 INFOs (unused indexes + unindexed FK).

## O que foi feito

- **058**: REVOKE explícito de anon/authenticated (+ GRANT
  service_role) em fn_importar_reconquista, fn_lojas_sucessao_apply
  e fn_web_login; zumbis v1 (fn_upsert_macica,
  fn_importar_reconquista_snapshot) revogados condicionalmente via
  `to_regprocedure` (a 031, que os dropa, nunca foi aplicada).
- **059**: policies de pagamentos_online consolidadas no padrão da
  011 — uma policy de SELECT (`IN ('admin','gestor')`) + três de
  escrita admin-only, com `(SELECT obter_perfil_atual())` (initplan:
  1 avaliação por query, não por linha×policy). Semântica idêntica,
  fail-closed preservado.
- **060**: drop de 3 unused indexes em tabelas com churn do ETL
  (idx_pagamentos_online_data_status, idx_reconquista_status,
  idx_produtos_categoria_id) — economia de WAL/escrita por import.
- Aplicadas em produção pelo usuário em 09/jul (junto com 054–057 +
  restart; `fn_diag_work_mem` confirmou `work_mem=12MB` no pool).

## Decisões não óbvias

- **Por que os REVOKEs antigos não funcionavam**: 020/023/029/053
  revogavam só de PUBLIC; no Supabase, anon/authenticated recebem
  EXECUTE **direto** via `ALTER DEFAULT PRIVILEGES` do schema — o
  REVOKE FROM PUBLIC não remove grants diretos. Toda migration
  futura que criar função de escrita deve revogar explicitamente de
  anon E authenticated (RPCs de leitura do dashboard continuam com
  GRANT explícito a anon/authenticated, como 052/056/057).
- **fn_web_login perdeu o grant a anon** (a 010 o preservava): todo
  login hoje passa pela Edge Function auth-login com service_role
  (web) ou IPC service_role (Electron) — verificado no repo
  angry-man; o dashboard Streamlit nem usa a função (auth.py lê
  `usuarios` + bcrypt no Python). Nenhum caminho anon restava.
- **Índices dropados na 060 vs mantidos**: só os 3 de tabelas
  reescritas por inteiro a cada import (ganho real de Disk IO,
  critério do usuário). Os 9 de tabelas pequenas foram MANTIDOS:
  ganho ~zero e 6 cobrem FKs (dropar trocaria o INFO unused_index
  pelo INFO unindexed_foreign_keys). O unindexed FK de
  loja_regiao_vigencia.regiao_id foi aceito sem índice novo (tabela
  minúscula; índice novo viraria unused_index no próximo lint).
- **idx_produtos_categoria_id nasce no schema.sql do angry-man**,
  não em migration deste repo — precisa ser removido lá também ou
  um rebuild do schema o recria.

## Pendências / follow-ups

- [ ] Decisão migration 031 (destrutiva: dropa reconquista_snapshot
      ~6.410 linhas de histórico v1 + macicas + funções v1). Rodá-la
      elimina os 3 idx_rsnap_* e os zumbis revogados na 058.
- [ ] angry-man: remover idx_produtos_categoria_id do
      database/schema.sql; aplicar spec IS DISTINCT FROM + TRUNCATE.
- [ ] Opcional (decisão do usuário): `ALTER DEFAULT PRIVILEGES IN
      SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM anon,
      authenticated` — novas funções nasceriam sem grant; exige
      GRANT explícito em toda RPC de leitura (padrão já seguido).
- [ ] Re-rodar Security/Performance Advisor para confirmar que os
      14 warnings sumiram.

## Referências

- Diagnóstico Disk IO: [2026-07-08-disk-io-budget-diagnostico-work-mem.md](2026-07-08-disk-io-budget-diagnostico-work-mem.md)
- Keyset/_json: [2026-07-09-keyset-pagination-rpcs-json.md](2026-07-09-keyset-pagination-rpcs-json.md)
- Padrão de consolidação RLS: migration 011
