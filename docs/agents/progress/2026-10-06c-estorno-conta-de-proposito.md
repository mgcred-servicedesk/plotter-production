# 2026-10-06 — Estorno pós-pagamento: filtro descartado, conta de propósito

**Agente:** Claude Code
**Tipo:** docs
**Arquivos tocados:** `docs/agents/business-rules.md`, `database/migrations/` (130 descartada e renumeração)
**Commit(s):** —

## Objetivo

Reverter a decisão registrada em
[2026-10-06-estorno-pos-pagamento-fora-da-producao.md](2026-10-06-estorno-pos-pagamento-fora-da-producao.md).
O usuário decidiu **não** tirar da produção o estorno pós-pagamento
(`CANCELADO` entre os pagos).

## O que foi feito

- Apagado o arquivo da migration 130 de estorno (`130_estorno_pos_pagamento_fora_da_producao.sql`).
  Ela nunca foi aplicada, e `fn_eh_estorno_pos_pagamento` não existe no banco.
- A migration de Cobrança Consignável, escrita como 131, foi renumerada
  para **130** e parte da view da 067, sem filtro de estorno.
- `business-rules.md`: a seção "Estorno pós-pagamento — fora da produção"
  foi trocada por "`CANCELADO` entre os pagos — conta de propósito
  (alerta)", com a consulta que lista os casos do mês.

## Decisões não óbvias

- **Por que não filtrar:** a linha contando como pago é sinal de que a
  proposta saiu da ordem natural. O usuário prefere que uma pessoa
  investigue a deixar uma regra esconder o caso.
- Consequência aceita: a apuração manual por `status_banco = 'EM ANÁLISE'`
  fica abaixo do dashboard pelo valor desses casos. Em out/2026 é o
  contrato 3011756, R$ 771,01.

## Pendências / follow-ups

- [ ] Avaliar um aviso no dashboard para os pagos com `CANCELADO` do mês (não pedido ainda).
