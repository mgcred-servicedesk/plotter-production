# 2026-05-22 — Pagamentos Online: migration 016 (correção do caminho)

**Agente:** Claude Code (Opus 4.7)
**Tipo:** correção (ops + migration)
**Arquivos tocados:**
- `database/migrations/014_pagamentos_online.sql` (revertido ao estado aplicado em prod)
- `database/migrations/016_pagamentos_online_filtro_simples.sql` (novo)

**Commit(s):** (a fazer)

## Contexto

A entrada [2026-05-22-pagamentos-online-filtro-simples](2026-05-22-pagamentos-online-filtro-simples.md)
editou a migration 014 in-place assumindo que ela ainda não
estava em produção. Quando a entrada
[2026-05-22-migrations-014-015-aplicadas](2026-05-22-migrations-014-015-aplicadas.md)
registrou a aplicação, a confirmação foi feita **após** as edições,
gerando ambiguidade.

No smoke test, a view retornou 0 registros embora houvesse 65
linhas com `agrupamento='Paga'` na tabela. `pg_get_viewdef` em
prod revelou que a view aplicada **era a versão com triplo
filtro** — ou seja, a migration 014 foi rodada **antes** do
refactor in-place. A simplificação ficou apenas no arquivo,
não no banco.

## O que foi feito

- **Revertida** a migration 014 ao seu estado original
  (triplo filtro + índice composto `idx_pagamentos_online_triplo`).
  Agora o arquivo bate com o que está aplicado em prod.
- **Criada** migration 016 (`016_pagamentos_online_filtro_simples.sql`)
  com:
  - `CREATE OR REPLACE VIEW` aplicando o filtro simplificado
    (`agrupamento='Paga'` + dedup).
  - `DROP INDEX idx_pagamentos_online_triplo` +
    `CREATE INDEX idx_pagamentos_online_agrupamento` para
    coerência semântica.

## Decisão

Migrations já aplicadas em prod são imutáveis. O caminho
canônico é nova migration com `CREATE OR REPLACE`. Reverter
014 mantém a consistência entre arquivo e banco; 016
documenta exatamente a delta funcional.

## Pendências

- [ ] Aplicar `016_pagamentos_online_filtro_simples.sql` no
      Supabase.
- [ ] Re-validar smoke test (esperado: 65 propostas, R$ 80.934,66
      antes do dedup, contagem real após dedup vs `contratos`).

## Lição aprendida

Editar migration in-place só é seguro quando a migration
ainda não foi rodada em **nenhum** ambiente (ideal: ainda
nem commitada). Quando há dúvida, fazer `pg_get_viewdef` /
`\d tabela` antes de decidir o caminho.

## Referências

- [2026-05-22-pagamentos-online-filtro-simples.md](2026-05-22-pagamentos-online-filtro-simples.md)
- [2026-05-22-migrations-014-015-aplicadas.md](2026-05-22-migrations-014-015-aplicadas.md)
