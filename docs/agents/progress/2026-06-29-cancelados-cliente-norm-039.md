# 2026-06-29 — Cancelados: coluna gerada cliente_norm (migration 039)

**Agente:** Devin
**Tipo:** perf
**Arquivos tocados:** `database/migrations/039_contratos_cliente_norm.sql`
**Commit(s):** (a commitar)

## Objetivo

Auditoria de performance focada em exibicao de dados e gargalos, com enfase
nas migrations. O gargalo de maior impacto identificado foi a RPC
`obter_cancelados_classificados`: mesmo apos a 036 ter removido o O(n^2) do
`redig`, o custo de base (~3s, `statement_timeout` de 15s como rede) e
dominado por recalcular `upper(trim(regexp_replace(coalesce(cliente,''),...)))`
em RUNTIME para cada cancelado (~2k) e cada PAGO da janela de ~37 dias.

## O que foi feito

- Nova migration 039 (CREATE OR REPLACE da RPC; 034/036 imutaveis, intocadas).
- Coluna GERADA STORED `contratos.cliente_norm` com a mesma expressao de
  normalizacao da 036 (upper/trim/regexp_replace/coalesce — todas IMMUTABLE,
  logo aceitas em `GENERATED ALWAYS ... STORED`). Materializa a normalizacao
  na escrita.
- RPC reescrita: as DUAS expressoes de `nome_norm` nos CTEs `canc` e `paga`
  viram `c.cliente_norm`. Todo o resto (canc/paga/redig/matches/classificacao/
  3 flags/datas/STABLE/GRANT/statement_timeout) IDENTICO a 036 — equivalencia
  semantica exata.
- Queries `EXPLAIN ANALYZE` (antes/depois) e de sanidade (contagem por
  `classificacao` deve bater) deixadas comentadas no fim do arquivo.

## Decisões não óbvias

- **Por que coluna gerada STORED e NAO indice funcional?** — a normalizacao
  aparece na SELECT-list dos CTEs e o matching e hash-join CTE<->CTE. O planner
  do PostgreSQL nao usa indice de expressao para evitar recomputar uma
  expressao da SELECT-list nem para joins entre CTEs. Indice funcional daria
  ganho ~zero; a coluna materializada elimina o regexp por linha em runtime.
- **Trade-off aceito (lock):** adicionar coluna gerada STORED reescreve a
  tabela `contratos` (lock ACCESS EXCLUSIVE, escritas bloqueadas durante a
  operacao). Confirmado com o usuario; aplicar em janela de baixo movimento /
  fora do ETL. `IF NOT EXISTS` torna idempotente.
- **`v_pontuacao_efetiva` (CROSS JOIN) NAO foi tocada** — auditoria mostrou
  que o app usa a RPC `obter_pontuacao_periodo`, nao a view; a mencao no
  `app.py` e docstring desatualizada. Possivel objeto morto (ver follow-ups).

## Pendências / follow-ups

- [ ] Aplicar a 039 no Supabase SQL Editor (secao 1 reescreve `contratos` —
      janela de baixo movimento) e rodar os `EXPLAIN ANALYZE` antes/depois
      no periodo de maior volume (ex.: 6/2026) para quantificar o ganho.
- [ ] Confirmar que a contagem por `classificacao` e identica antes x depois
      (so o plano deve mudar, nao o resultado).
- [ ] Avaliar se `v_pontuacao_efetiva` e realmente objeto morto e, se sim,
      DROP em migration futura + corrigir docstring do `app.py`.
- [ ] (Backlog perf, fora desta migration) loader de `v_contratos_dashboard`:
      trocar `select("*")` por colunas explicitas e montar o DataFrame sem o
      loop de dicts; indices compostos `(periodo_id, loja_id)`.

## Referências

- Migration base: `database/migrations/036_cancelados_redig_setbased.sql`
- Caller: `src/dashboard/loaders.py::carregar_contratos_cancelados`
- Schema: `database/schema.sql` (`contratos.cliente`, linha ~340)
- Docs consultados: [docs/agents/data-layer.md](../data-layer.md),
  [docs/agents/architecture.md](../architecture.md)
