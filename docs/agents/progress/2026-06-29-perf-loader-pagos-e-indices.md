# 2026-06-29 — Perf: loader de pagos + indices compostos RLS

**Agente:** Devin
**Tipo:** perf
**Arquivos tocados:** `src/dashboard/loaders.py`,
`database/migrations/040_indexes_compostos_rls.sql`, `app.py` (docstring)
**Commit(s):** (a commitar)

## Objetivo

Continuacao do backlog de performance aberto apos a 039 (cancelados).
Atacar a carga de `v_contratos_dashboard` (maior custo da "primeira carga")
e os filtros RLS por loja sem indice composto.

## O que foi feito

- **`_fetch_contratos_pagos`**: `select("*")` -> select explicito das 23
  colunas consumidas (+ `id` so para o order estavel). DataFrame montado
  direto de `pd.DataFrame(all_data).reindex(...).rename(...)` em vez do
  loop linha-a-linha de dicts. Conversoes numericas/datas vetorizadas.
- **`_COLS_CONTRATOS_PAGOS`**: novo dict de mapeamento coluna-fonte ->
  nome canonico, no topo do modulo.
- **Migration 040** (`CREATE INDEX CONCURRENTLY`): `(periodo_id, loja_id)`
  e `(loja_id, data_cadastro)` para o filtro de loja que a policy
  `pol_contratos_select` (011) injeta em perfis nao-admin.
- **`app.py`**: docstring corrigida — citava `v_pontuacao_efetiva`
  (objeto nao usado em runtime; app usa a RPC `obter_pontuacao_periodo`).

## Decisões não óbvias

- **Equivalencia semantica preservada no loader** — `None` de LEFT JOIN
  (loja/regiao/grupos), `valor_parcela` nulo -> 0 e `conta_valor` None
  passam exatamente como antes. Verificado com simulacao lado-a-lado
  (`assert_frame_equal`) cobrindo os casos-limite; a mascara downstream
  `conta_valor == False` mantem o mesmo resultado. NAO se fez `fillna("")`
  nas strings nem `fillna(True)` nas flags de proposito (mudaria None->X).
- **Indices 040 sao HIPOTESE a validar** — o app filtra loja/regiao/
  consultor client-side; o unico filtro de loja no SQL vem da RLS
  server-side para perfis nao-admin. Logo o ganho depende da seletividade
  do escopo e do plano. EXPLAIN deve rodar AUTENTICADO como nao-admin;
  como admin/gestor a policy nao filtra por loja e os indices nao sao
  exercitados. Comandos de DROP incluidos caso o planner os ignore.
- **`CONCURRENTLY`** para nao bloquear escritas na `contratos` (logo apos
  a reescrita da 039); exige rodar cada statement FORA de transacao.
- **`v_pontuacao_efetiva` NAO foi dropada** — apenas sinalizada. Regra do
  projeto: nao deprecar/remover objeto unilateralmente (ver follow-up).

## Pendências / follow-ups

- [ ] Rodar os EXPLAIN ANALYZE da 040 (perfil nao-admin) e manter so os
      indices efetivamente usados; derrubar o resto.
- [ ] Confirmar (DROP em migration futura) se `v_pontuacao_efetiva` e
      realmente objeto morto — grep nao achou consumo em runtime.
- [ ] (Opcional) vetorizar os `.apply(axis=1)` triviais em
      `tabs/em_analise.py`, `tabs/regioes.py` (ganho pequeno, dados ja
      agregados).

## Referências

- Migration anterior: `database/migrations/039_contratos_cliente_norm.sql`
- RLS: `database/migrations/011_consolidar_rls_policies.sql`
- Docs: [docs/agents/data-layer.md](../data-layer.md),
  [docs/agents/rls.md](../rls.md)
