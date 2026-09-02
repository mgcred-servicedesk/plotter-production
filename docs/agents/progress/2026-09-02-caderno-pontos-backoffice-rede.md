# 2026-09-02 — Pontos do backoffice no resultado geral do Caderno

**Agente:** Codex
**Tipo:** bugfix
**Arquivos tocados:** `database/migrations/108_caderno_pontos_backoffice_rede.sql`, `docs/agents/business-rules.md`; contrato, domínio, UI e testes no repositório `bereshit`
**Commit(s):** não commitado

## Objetivo

Corrigir a Leitura Executiva de 08/2026, que bloqueava Meta Prata, ritmo da
rede e gerências porque o resumo incluía pontos de `VAI E VEM` e a série
mensal os excluía.

## O que foi feito

- Criada a migration 108, sem alterar a 096 já aplicada.
- `monthlyPoints` passa a transportar `VAI E VEM` com
  `comparisonScope = NETWORK_ONLY`; as demais linhas usam `STORE_REGION`.
- `summary.backoffice` passa a expor `effectivePoints` para auditoria.
- Ranking, contagem de lojas, regiões, produtividade, headcount e ranking por
  produto continuam excluindo `VAI E VEM`.
- O Bereshit inclui `NETWORK_ONLY` na rede e o exclui das superfícies de loja
  e região, inclusive CSV e detecção de mudanças históricas.

## Decisões não óbvias

- **Por que não retirar os pontos do resumo?** — A operação confirmou que a
  produção e os pontos de Vai e Vem pertencem ao resultado geral; somente a
  comparação territorial é proibida.
- **Por que não tolerar simplesmente a diferença no frontend?** — Isso faria
  Meta Prata e ritmo continuarem usando um subtotal, apenas escondendo a
  inconsistência.
- **Compatibilidade histórica** — snapshots sem `comparisonScope` são lidos
  como `STORE_REGION`; nenhum snapshot antigo precisa ser republicado para
  continuar abrindo.

## Pendências / follow-ups

- [ ] Aplicar, nesta ordem, migrations 106, 107 e 108.
- [ ] Validar `fn_contar_pagamentos_sem_vinculo_origem(8, 2026) = 0`.
- [ ] Rematerializar 08/2026 e conferir a Leitura Executiva publicada.

## Patterns criados ou atualizados

- Nenhum.

## Referências

- Docs consultados: [business-rules.md](../business-rules.md), [architecture.md](../architecture.md), [data-layer.md](../data-layer.md), [conventions.md](../conventions.md)
