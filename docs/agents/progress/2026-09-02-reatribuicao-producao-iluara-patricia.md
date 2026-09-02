# 2026-09-02 — Reatribuição da produção indicada para Iluara

**Agente:** Codex
**Tipo:** correção de dados
**Arquivo desta frente:**
`database/migrations/106_produtividade_reatribui_iluara_para_patricia.sql`
**Commit(s):** —

## Fato confirmado

A operação confirmou que as 17 propostas de 18/08/2026 foram digitadas por
Patricia Pereira Lopes e posteriormente indicadas para Iluara Borges Cabral.
Como Iluara foi admitida apenas em 25/08/2026, manter as propostas no nome dela
criaria uma atribuição anterior ao vínculo real.

## Decisão

As 17 propostas voltam para Patricia em Help Cascadura. A loja, as ADEs, os
valores e as datas não mudam. Patricia possui vigência de supervisão cobrindo
31/08/2026; portanto, pelas regras vigentes, essa produção permanece no total
da loja e fica fora do numerador e dos rankings de consultores.

## Implementação e guardas

A migration 106 relaciona explicitamente os 17 pares `contrato_id`/ADE,
confere a data de cadastro, a loja, os cadastros de origem e destino e a
vigência de supervisão antes de alterar somente `consultor_id`. Depois da
alteração, exige as 17 propostas em Patricia/Cascadura e confirma que o total
financeiro permaneceu idêntico.

Após a aplicação, `fn_contar_pagamentos_sem_vinculo_origem(8, 2026)` deve cair
de 18 para 1. O caso restante é o contrato `2987344`, hoje associado a
Victor/Copacabana Nova apesar de ter sido cadastrado antes dessa vigência.
