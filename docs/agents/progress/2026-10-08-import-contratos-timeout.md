# 2026-10-08 — Import de contratos estourando statement_timeout

**Agente:** Claude Code
**Tipo:** bugfix
**Arquivos tocados:** `database/migrations/133_fn_admin_import_pula_contratos_inalterados.sql`, `angry-man/src/services/import-contratos.ts`; role `service_role` (config direta no banco)
**Commit(s):** —

## Objetivo

Import de contratos do angry-man falhando em todos os lotes com
"canceling statement due to statement timeout".

## O que foi feito

- Diagnóstico: upsert de 1000 contratos via `fn_admin_import` custava
  ~1,6s sozinho (UPDATE non-HOT mantendo os 14 índices de `contratos`,
  mesmo para linhas idênticas); 4 lotes em paralelo na CPU Nano → 4-8s,
  acima do teto de 8s do `authenticator`. pg_stat_statements já mostrava
  máx. 7,5s antes do incidente.
- Destravar (aplicado pelo usuário): `ALTER ROLE service_role SET
  statement_timeout = '30s'`.
- Migration 133: `fn_admin_import` ganha `WHERE (...) IS DISTINCT FROM
  (EXCLUDED...)` no DO UPDATE **só para contratos**. 1000 linhas iguais:
  ~1,6s → ~0,2-0,4s.
- angry-man: lote de contratos 1000×4 → 500×2.

## Decisões não óbvias

- **Filtro só em contratos** — as outras 7 tabelas da whitelist têm
  trigger `atualizar_updated_at`; pular o UPDATE deixaria de bumpar
  `updated_at`, que `loaders.py` usa como desempate.
- **`count` continua sendo o tamanho do lote** (o app soma `data.length`
  como processados); a chave nova `alterados` traz o que foi de fato
  gravado. A Edge Function hoje a ignora.
- **30s vale para o dashboard também** — ele usa a mesma chave
  `service_role`. Aceito para destravar; revisitar depois da 133 e do
  lote menor (talvez voltar a 8s).

## Pendências / follow-ups

- [x] Migration 133 aplicada em 2026-10-08 (verificada: count=1000/alterados=0; grants e assinatura únicos mantidos).
- [x] angry-man 1.4.4 gerado (Setup + zip win-x64) = 1.4.3 + lote 500×2. Não commitado — a árvore do angry-man ainda carrega o trabalho da 1.4.3 (desktop sem service_role) sem commit.
- [ ] Distribuir o 1.4.4 e commitar o angry-man.
- [ ] Depois de ambos, decidir se o `service_role` volta para 8s
      (`ALTER ROLE service_role RESET statement_timeout`).

## Referências

- Memória: statement_timeout de função é ineficaz (teto vem do role).
