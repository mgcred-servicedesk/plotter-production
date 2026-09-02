# 2026-09-02 — Validação da origem do pagamento na produtividade

**Agente:** Codex
**Tipo:** fix
**Arquivo desta frente:**
`database/migrations/105_produtividade_validacao_origem_pagamento.sql`
**Commit(s):** —

## Problema observado

O piloto de 08/2026 encontrou cinco segmentos semanais com pagamento positivo
e zero dias na loja do contrato. Quatro eram pagamentos tardios legítimos:
Ana Leticia, Renan, Mizael e Victor cadastraram os contratos quando ainda
tinham vínculo na loja de origem e receberam o pagamento depois da mudança.

O quinto caso era diferente: 17 contratos de 18/08 apontavam para Iluara,
admitida somente em 25/08. A operação confirmou que o único contrato digitado
por ela foi em 31/08 e não estava pago.

## Correção

A migration 105 mantém o numerador no eixo de `data_status_pagamento`, mas
passa a validar a atribuição do contrato contra a vigência na
`data_cadastro`. Os contadores de segmento mensal/semanal sem dias continuam
no diagnóstico, mas o bloqueio usa `unlinkedPaidOriginEvents` e sobreposição.

Assim, atraso de pagamento após transferência não falsifica o ledger, enquanto
os 17 contratos indevidos de Iluara continuam bloqueando até serem reimportados
com o vendedor correto.
