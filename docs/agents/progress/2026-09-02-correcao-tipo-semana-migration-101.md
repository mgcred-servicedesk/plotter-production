# 2026-09-02 — Correção de tipo na semana da migration 101

**Agente:** Codex
**Tipo:** fix
**Arquivo desta frente:** `database/migrations/101_produtividade_individual_v2.sql`
**Commit(s):** —

## Falha observada

A primeira tentativa de executar a migration 101 falhou antes do `COMMIT` com
o erro PostgreSQL `42883`: o alias de
`generate_series(date, date, interval)` é um timestamp com fuso e a expressão
semanal tentava somar o inteiro `6`.

## Correção

A expressão passou de `(s + 6)::date` para
`(s + interval '6 days')::date`. As demais somas inteiras encontradas na
migration têm operando explicitamente convertido para `date` e, portanto,
usam o operador válido `date + integer`.
