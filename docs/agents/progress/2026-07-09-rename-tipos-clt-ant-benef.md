# 2026-07-09 — Rename de tipos: CONSIG PRIV → CLT, CNC ANT → ANT. DE BENEF.

**Agente:** Windsurf
**Tipo:** bugfix
**Arquivos tocados:** `database/migrations/061_backfill_categoria_clt_ant_benef.sql`, `src/dashboard/loaders.py`, `database/schema.sql`, `database/INTEGRACAO.md`
**Commit(s):** (pendente)

## Objetivo

As planilhas de origem renomearam os tipos de produto: `CONSIG PRIV` →
`CLT` e `CNC ANT` → `ANT. DE BENEF.`. Verificar o banco e corrigir.

## O que foi feito

- Diagnóstico no Supabase: o upsert do ETL de 09/07 sobrescreveu
  `produtos.tipo` com os nomes novos e gravou `categoria_id = NULL`
  (19 produtos `CLT`, 1 `ANT. DE BENEF.`). **12.818 contratos** ficaram
  sem `categoria_codigo` no dashboard.
- Migration `061`: backfill de `categoria_id` — `CLT` → `CONSIG_PRIV`,
  `ANT. DE BENEF.` → `ANT_BENEF`.
- `_TIPO_PARA_CATEGORIA` (loaders.py): adicionadas as chaves novas,
  mantendo as antigas para dados históricos.
- Docs de referência atualizados (schema.sql e INTEGRACAO.md §produtos).

## Decisões não óbvias

- **Nomes antigos mantidos nos mapeamentos** — histórico pode conter
  os tipos legados; o mapeamento aceita ambos.
- **Categoria `CONSIG_PRIV` não renomeada** — o `codigo` é chave
  estável usada em todo o código (`PRODUTOS_DASHBOARD`, alias de pts);
  só o `tipo` da origem mudou. `grupo_dashboard` já era `CLT`.
- **Tabela de pontuação (INTEGRACAO.md §4) não alterada** — a planilha
  `pontos_{mes}.xlsx` é outra origem; não confirmado se o rename
  também se aplica lá.

## Pendências / follow-ups

- [ ] Executar a migration 061 no Supabase SQL Editor.
- [ ] **Corrigir o mapeamento tipo → categoria no ETL (repo
      angry-man)** — `produtos` sofre upsert integral a cada import;
      sem essa correção, cada import desfaz o backfill da 061
      (o fallback do loaders.py mitiga no dashboard).
- [ ] Confirmar se a planilha de pontuação também adotou os nomes
      novos e, se sim, atualizar o mapeamento correspondente.

## Referências

- Docs consultados: [docs/agents/data-layer.md](../data-layer.md)
