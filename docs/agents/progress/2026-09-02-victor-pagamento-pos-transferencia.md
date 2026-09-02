# 2026-09-02 — Pagamento de Victor posterior à transferência

**Agente:** Codex
**Tipo:** correção de dados
**Arquivo desta frente:**
`database/migrations/107_produtividade_corrige_origem_victor_laranjeiras.sql`
**Commit(s):** —

## Fato confirmado

Victor Felipe Trajano Costa permaneceu em Help Laranjeiras até 03/08/2026 e
passou para Help Copacabana Nova em 04/08/2026. A ADE `978537400`, contrato
`2987344`, foi cadastrada em 20/07/2026 e paga em 04/08/2026.

O contrato hoje aponta para o cadastro de Victor em Copacabana Nova, embora
tenha sido originado durante sua vigência em Laranjeiras. O pagamento no dia
da transferência não altera a origem da produção.

## Implementação e guardas

A migration 107 valida as duas lojas, os dois cadastros de Victor, as janelas
de vigência, a ADE e as datas antes de restaurar `loja_id` e `consultor_id`
para Victor/Laranjeiras. O valor e as datas são conferidos novamente após a
alteração.

A 107 deve ser aplicada depois da 106, que ainda está pendente. Depois das
duas, `fn_contar_pagamentos_sem_vinculo_origem(8, 2026)` deve retornar zero;
só então `08/2026` pode ser rematerializado.
