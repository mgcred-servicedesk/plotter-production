# 2026-06-26 — Cancelados: redig set-based (migration 036)

**Agente:** Claude Code (supabase-schema-rls)
**Tipo:** bugfix / perf
**Arquivos tocados:** `database/migrations/036_cancelados_redig_setbased.sql`
**Commit(s):** (a commitar)

## Objetivo

`obter_cancelados_classificados(p_mes, p_ano)` estourava o
`statement_timeout` do Supabase (erro 57014, ~8,3s) quando chamada por
`src/dashboard/loaders.py::carregar_contratos_cancelados`. A 034 ja tinha
otimizado a recuperacao (6 EXISTS -> 1 JOIN agregado), mas o CTE `redig`
seguiu como EXISTS correlacionado.

## O que foi feito

- Nova migration 036 (CREATE OR REPLACE; 034 imutavel, intocada).
- CTE `redig` reescrito de EXISTS correlacionado self-join para LEFT JOIN
  agregado set-based com `bool_or` — mesmo padrao do CTE `matches` da 034.
  Elimina o nested-loop O(|canc|^2) (~1.982^2 ~= 4M comparacoes).
- `SET statement_timeout = '15000'` adicionado a definicao da funcao (junto
  de `SET search_path = ''`) como rede de seguranca; custo de base sobre
  ~2k cancelados e real e irreduzivel.
- `canc`, `paga`, `matches`, SELECT final, classificacao, as 3 flags de
  oportunidade, logica de datas, `STABLE`, `GRANT` -> IDENTICOS a 034.

## Decisões não óbvias

- **Por que LEFT JOIN e nao INNER + recompor?** — o final faz
  `JOIN redig rd ON rd.id = f.id`, exigindo UMA linha por cancelado
  (inclusive nome vazio). INNER dropparia cancelados sem match e quebraria
  o join 1:1. LEFT JOIN preserva todos, espelhando o `FROM canc a` da 034.
- **Guarda `nome_norm <> ''` na clausula ON + repetida em `is_redig`** —
  na ON garante que linhas de nome vazio nao casam nenhum `b`
  (`bool_or = false`); repetida no `is_redig` para paridade literal com a
  034. Ambas as rotas dao `false`, sem divergencia.
- **`GROUP BY a.id, a.nome_norm`** — `id` (UUID PK) e unico e determina
  `nome_norm`; o segundo termo so satisfaz a regra de SELECT fora de
  agregado. Nao altera cardinalidade (1:1 com canc).
- **Desigualdade ESTRITA `>` em `data_cadastro`** preservada (nao `>=`):
  um cancelado nunca redigita a si mesmo nem casa empate de data.
- **statement_timeout local de 15s** em vez de afrouxar o global — isola o
  risco a esta funcao de custo conhecido.

## Pendências / follow-ups

- [ ] Aplicar a 036 no Supabase SQL Editor e confirmar tempo < 15s no
      periodo 6/2026 (sem psql/EXPLAIN no ambiente do agente).
- [ ] Validar que a contagem de `redigitada` no dashboard bate com a 034
      apos aplicar (deve ser identica — so o plano mudou).

## Referências

- Migration base: `database/migrations/034_cancelados_otimizacao_join.sql`
- Caller: `src/dashboard/loaders.py::carregar_contratos_cancelados`
- Docs consultados: [docs/agents/data-layer.md](../data-layer.md),
  [docs/agents/rls.md](../rls.md), [docs/agents/conventions.md](../conventions.md)
