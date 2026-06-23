# 2026-06-18 — Design patterns: reuso e manutenção

**Agente:** Claude Code
**Tipo:** refactor (qualidade)
**Arquivos tocados:** `src/dashboard/kpis/rankings.py`, `app.py`,
`src/dashboard/ui/kpi_cards_reforma.py`, `src/dashboard/components/tables.py`
(rankings highlight prévio), `tests/test_kpis_rankings.py` (cobertura existente),
remoção de `src/data_processing`, `src/reports`, `src/analysis`
**Commit(s):** (não commitado)

## Objetivo

Melhorar reuso e manutenibilidade após auditoria de design. Arquitetura em
camadas (loaders → kpis → tabs/ui/components) está sã; o débito era duplicação
localizada + funções gigantes.

## O que foi feito

- **#3 Dirs legados removidos:** `data_processing`, `reports`, `analysis` —
  tinham 0 `.py` (só `__pycache__` órfão do pipeline de relatórios já removido);
  zero imports.
- **#1 Builders de ranking** (`kpis/rankings.py`, 406→307 linhas): extraídos
  `_preparar`, `_agrupar`, `_anexar_regiao`, `_ticket`, `_atingimento`,
  `_rankear`. As 7 funções de ranking agora compõem esses helpers preservando
  saída exata (19 testes verdes).
- **#2 Vetorização:** os `.apply(lambda r: ..., axis=1)` de Ticket/Atingimento
  (6×) viraram operações vetorizadas (`_ticket`/`_atingimento`). Eram todos em
  `rankings.py`; `regioes.py`/`gerais.py` não tinham apply row-wise (os que
  existiam estavam nas funções de região já removidas em sessão anterior).
- **#4 `app.py main()` (parcial, seguro):** extraídos `_render_aviso_pontuacao_fallback`,
  `_ritmo_organizacao`, `_serie_diaria_pago` — os blocos coesos mais aninhados.
- **#5 SOLID em `kpi_cards_reforma.py` (parcial, seguro):** helper puro
  `_card_contexto(label, valor, sub, valor_style)`; os 8 cards do Reconquista
  passaram a usá-lo (saída byte-idêntica verificada).

## Decisões não óbvias

- **Builders de ranking preservam diferenças por função.** Não unifiquei tudo
  num único `_ranking_base` com flags porque cada ranking difere em colunas
  (REGIAO sim/não, drop de Qtd/Meta, coluna de ordenação). Helpers pequenos +
  composição mantêm a saída idêntica sem regressão (travada pelos 19 testes).
- **`_card_contexto` só cobre os cards do Reconquista.** Os outros sites
  `mg-kpi-context` **não** são duplicatas: `render_kpis_contexto` não aplica
  `.replace(",",".")` (mesclar mudaria formatação numérica);
  `render_cards_produto_mix`/`render_cards_aceleradores` usam `style` de
  container customizado. Forçá-los no helper mudaria saída ou super-generalizaria.
- **Verificação sem runtime.** `app.py` e os cards UI não têm teste de runtime
  (precisam de Streamlit+Supabase). Mitigação: extrações puras verificadas por
  equivalência byte-a-byte (cards) + `import`/AST smoke (app.py) + suíte (75
  testes). Mudanças foram conservadoras por isso.

## Pendências / follow-ups

- [ ] **#4 profundo:** orquestração de KPIs (~120 linhas) e dispatch de abas
      (~250 linhas) em `main()` continuam inline. Decompor com segurança pede
      um **objeto de contexto/estado** (em vez de ~20 parâmetros) e, idealmente,
      um smoke test de runtime do dashboard antes.
- [ ] **#5 profundo:** separar compute × render nas funções `render_*` de
      `kpi_cards_reforma.py` (SRP). Vale criar cobertura de teste de UI primeiro.

## Referências

- Auditoria de design pattern (sessão 2026-06-18).
