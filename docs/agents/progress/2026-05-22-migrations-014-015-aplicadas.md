# 2026-05-22 — Migrations 014 e 015 aplicadas em produção

**Agente:** Claude Code (Opus 4.7)
**Tipo:** ops (registro de aplicação de migration)
**Arquivos tocados:** (nenhum — entrada apenas para registro)

## Contexto

As migrations da feature de Pagamentos Online foram aplicadas
no Supabase de produção:

- `database/migrations/014_pagamentos_online.sql` — coluna
  `lojas.codigo_dna`, tabela `pagamentos_online`, view
  `v_pagamentos_online_efetivo` (já com o filtro simplificado
  `Agrupamento='Paga'` da entrada
  [2026-05-22-pagamentos-online-filtro-simples](2026-05-22-pagamentos-online-filtro-simples.md)).
- `database/migrations/015_fn_pagamentos_online.sql` — RPCs
  `fn_pagamentos_online_replace` e `fn_pagamentos_online_clear`.

## Pendências resolvidas

- [x] Aplicar migration 014 (originalmente listada em
      [2026-05-21-pagamentos-online](2026-05-21-pagamentos-online.md)).
- [x] Aplicar migration 015.

## Próximos passos

- [ ] Smoke test do primeiro upload real via angry-man.
- [ ] Acompanhar log de queda anormal (delta `count_anterior →
      count_novo`) nos primeiros ciclos.

## Referências

- [2026-05-21-pagamentos-online.md](2026-05-21-pagamentos-online.md)
- [2026-05-22-pagamentos-online-filtro-simples.md](2026-05-22-pagamentos-online-filtro-simples.md)
