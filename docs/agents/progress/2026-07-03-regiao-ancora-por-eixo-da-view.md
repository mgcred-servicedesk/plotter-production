# 2026-07-03 — Região: âncora temporal por eixo de cada view

**Agente:** Claude Code
**Tipo:** bugfix (semântica de KPI / data-layer)
**Arquivos tocados:** `database/migrations/051_regiao_ancora_periodo_pagamento.sql`, `database/migrations/052_cancelados_regiao_atual.sql`
**Commit(s):** (não commitado)

## Objetivo

Em "Onde Agir Agora → Regiões" (gestor/admin), pós-remanejamento H2/2026,
lojas remanejadas apareciam **partidas** entre a região antiga e a nova no
mesmo período — e o realizado por região não batia com as metas. Limpar cache
não resolvia (não era cache).

## O que foi feito

- Diagnóstico read-only provou: banco correto (ledger e `lojas.regiao_id`
  batem com a 050). A causa era **descasamento de eixo temporal**: a 044
  resolvia `regiao` point-in-time **sempre por `data_cadastro`** (venda), mas
  cada view é consumida por um eixo diferente.
- **051** (`CREATE OR REPLACE` das 3 views):
  - `v_contratos_dashboard` (PAGOS): `regiao` = vigência na **competência do
    período de pagamento** (`make_date(per.ano, per.mes, 1)`; `COALESCE` →
    `data_cadastro` quando sem `periodo_id`). Mesmo eixo das metas (RPC 045).
  - `v_contratos_em_analise` e `v_contratos_cancelados`: `regiao` = **região
    atual** da loja (`lojas.regiao_id`), = `regiao_atual`.
- **052** (`CREATE OR REPLACE obter_cancelados_classificados`, base 047): o
  `paga` CTE passa a resolver região pela **região atual** (remove o LATERAL de
  vigência), para o matching "recuperada_outra_regiao" comparar o mesmo eixo dos
  dois lados (cancelado via view 051 + paga).
- Preview read-only (período julho/2026): split cai de **13 linhas → 0**;
  `regiao` passa a bater com `regiao_atual` e com as metas. Python **intocado**
  (loaders/RPCs leem `regiao`/`regiao_atual` das views). 212 testes verdes,
  ruff limpo.

## Decisões não óbvias

- **Por que competência (pagamento) e não `data_cadastro` para os pagos?** — O
  dashboard mede produção por **período de pagamento** e as metas (045) já
  resolvem região por competência. Ancorar o realizado por venda fazia um
  contrato vendido em junho / pago em julho cair na região antiga dentro da
  visão de julho → loja partida e realizado ≠ meta. Só há **um** alinhamento
  coerente: realizado no mesmo eixo da meta. Decisão de negócio confirmada com o
  usuário (2026-07-03): produção do período credita o **dono no pagamento**.
- **Por que em análise / cancelados por região ATUAL?** — Pipeline não tem
  período de pagamento ainda; credita o dono atual (onde pagará). Cancelado
  credita o dono atual (onde a recuperação seria feita). Confirmado pelo
  usuário.
- **Ajuste da 044 (data_cadastro) não foi "errado", foi incompleto** — servia
  como no-op antes do remanejamento; o descasamento só aparece na fronteira de
  período. A 051 refina o eixo por tipo de view.
- **Histórico permanece point-in-time** — para períodos ≤ jun/2026 a competência
  resolve para a região da época; só no período corrente `regiao` coincide com
  `regiao_atual`.

## Pendências / follow-ups

- [ ] **Digitação detalhe (048)** — `obter_digitacao_diaria_detalhe` ainda
  resolve região por `data_cadastro`. Alimenta só a página de drill-down de
  digitação (não o "Onde Agir Agora"). Mesma classe de decisão — o usuário deve
  confirmar se alinha à região atual (digitação = atividade recente).
- [ ] Aplicar **051 e 052** no Supabase SQL Editor (nesta ordem) e limpar cache
  do app ("Atualizar Dados").
- [ ] Validar perf da 052 com `EXPLAIN ANALYZE` (a RPC opera perto do
  `statement_timeout` de 15s; a 052 **remove** um LATERAL, então deve melhorar).

## Referências

- Base: [044_views_regiao_vigencia.sql](../../../database/migrations/044_views_regiao_vigencia.sql),
  [045_fn_metas_geral_loja_vigencia.sql](../../../database/migrations/045_fn_metas_geral_loja_vigencia.sql),
  [047_cancelados_regiao_vigencia.sql](../../../database/migrations/047_cancelados_regiao_vigencia.sql)
- Docs: [docs/agents/data-layer.md](../data-layer.md), [docs/agents/business-rules.md](../business-rules.md)
