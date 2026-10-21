# 2026-10-21 — Analítico Fim de relacionamento Liga

**Agente:** Codex (subagente UI)
**Tipo:** feature
**Arquivos tocados:** `src/dashboard/tabs/analiticos.py`,
`tests/test_tabs_analiticos.py`
**Commit(s):** alterações locais, sem commit nesta etapa.

## Objetivo

Incluir a foto mensal de Fim de relacionamento Liga dentro de
Analíticos › Reconquista, conforme plano aprovado pelo usuário.

## O que foi feito

- Sub-aba própria com carregamento somente quando selecionada.
- Totais de adesões listadas, contabilizadas e não contabilizadas do
  escopo autorizado entregue pelo loader.
- Detalhe e CSV com filtros de contabilização, loja e consultor,
  quantidade e ambas as datas no formato brasileiro.
- Estados distintos para carga ausente, falha de leitura e ausência
  de dados no escopo do usuário.
- Testes de UI e loader: 62 passaram. Ruff dos dois arquivos de UI limpo.

## Decisões não óbvias

- O detalhe abre em Todas, preservando a conferência integral da foto
  (inclusive quantidade zero). O filtro permite ver cada situação.
- A competência pertence à foto. Datas de saída de meses anteriores
  permanecem no detalhe e não recebem novo recorte de 90 dias.
- As métricas representam o escopo completo do perfil; os filtros
  recortam o detalhe e o CSV. Não se alteram KPIs nem aceleradores.
- Não há corte artificial de vigência da sub-aba. Um mês sem carga
  recebe mensagem explícita, sem virar um zero de negócio.

## Pendências / follow-ups

- Publicação e validação integrada da migration, Edge Function e carga
  ficam com o orquestrador. Esta etapa não publicou nem importou dados.

## Referências

- [ui-components.md](../ui-components.md)
- [rls.md](../rls.md)
- [data-layer.md](../data-layer.md)
