# 2026-05-22 — Pagamentos Online: simplificação do filtro

**Agente:** Claude Code (Opus 4.7)
**Tipo:** refactor (regra de negócio)
**Arquivos tocados:**
- `database/migrations/014_pagamentos_online.sql` (view + índice)
- `database/INTEGRACAO_PAGAMENTOS_ONLINE.md` (texto da regra)
- `src/dashboard/loaders.py` (comentário do bloco)
- `src/dashboard/tabs/pagamentos_online.py` (docstring)

**Commit(s):** (a fazer)

## Objetivo

Simplificar a regra de "pago online" para considerar apenas
`Agrupamento='Paga'`. O triplo filtro original (`Status='Concluída'`
AND `Situação='Concluída'` AND `Agrupamento='Paga'`) era redundante
para os grupos importados — uma vez que a proposta entra no
agrupamento `Paga`, o pagamento já está efetivado.

## O que foi feito

- View `v_pagamentos_online_efetivo`: removidas as condições
  `status='Concluída'` e `situacao='Concluída'` do `WHERE`. Resta
  `agrupamento='Paga'` + dedup vs consolidado.
- Índice `idx_pagamentos_online_triplo` (composto) substituído por
  `idx_pagamentos_online_agrupamento`. Volume da tabela (~500-700
  linhas) torna isso irrelevante para performance; é só
  consistência semântica.
- `INTEGRACAO_PAGAMENTOS_ONLINE.md` §3 e §5 atualizados.
- Docstrings de `loaders.py` e `tabs/pagamentos_online.py`
  refletindo o novo filtro.

## Decisões não óbvias

- **Editei a migration 014 in-place em vez de criar nova.**
  A migration está untracked e o progress de 2026-05-21 marca
  "[ ] Aplicar a migration 014 no Supabase" como pendente — ela
  ainda não foi aplicada em produção. Editar in-place evita
  poluir o histórico com uma migration corretiva já no commit
  inicial. Se já tivesse rodado em prod, o caminho seria
  migration 016 com `CREATE OR REPLACE VIEW`.
- **Colunas `status` e `situacao` permanecem na tabela.**
  Mesma justificativa do progress anterior: preservam
  espaço para visões futuras (pendentes, em análise) sem
  exigir mudança no ingestor.

## Premissas a validar

- Para os grupos importados (`Antecipação em Conta`,
  `Crédito na Conta`), `Agrupamento='Paga'` implica
  pagamento efetivado. Confirmar com operacional se algum
  estado anômalo (ex.: estorno tardio) poderia entrar com
  `Agrupamento='Paga'` mas `Situação` diferente de
  `Concluída`. Se sim, repor a condição de `Situação`.

## Pendências / follow-ups

- [ ] Aplicar migration 014 (já com o filtro simplificado).
- [ ] Smoke test pós-aplicação com upload real.

## Referências

- Doc do contrato: [`database/INTEGRACAO_PAGAMENTOS_ONLINE.md`](../../../database/INTEGRACAO_PAGAMENTOS_ONLINE.md)
- Entrada anterior: [2026-05-21-pagamentos-online.md](2026-05-21-pagamentos-online.md)
