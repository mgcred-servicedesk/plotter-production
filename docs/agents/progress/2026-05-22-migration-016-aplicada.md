# 2026-05-22 — Migration 016 aplicada e validada

**Agente:** Claude Code (Opus 4.7)
**Tipo:** ops (registro de aplicação)
**Arquivos tocados:** (nenhum)

## Contexto

Migration `016_pagamentos_online_filtro_simples.sql` aplicada
no Supabase de produção. Smoke test bateu com o esperado:
65 propostas, R$ 80.934,66 (17 Antecipação em Conta +
48 Crédito na Conta).

## Pendências resolvidas

- [x] Aplicar `016_pagamentos_online_filtro_simples.sql`.
- [x] Re-validar smoke test contra dados reais.

## Próximos passos

- [ ] Acompanhar primeiros ciclos de upload reais para
      conferir que o número se mantém estável entre uploads
      do mesmo dia.

## Referências

- [2026-05-22-pagamentos-online-migration-016.md](2026-05-22-pagamentos-online-migration-016.md)
