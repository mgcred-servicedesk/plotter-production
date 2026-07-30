# 2026-07-29 — Subproduto (SUBTIPO) nas tabelas analíticas

**Agente:** Devin
**Tipo:** feature + bugfix
**Arquivos tocados:** `src/dashboard/tabs/analiticos.py`,
`src/dashboard/loaders.py`, `tests/test_tabs_analiticos.py` (novo),
`tests/test_loaders.py`, `docs/agents/data-layer.md`

## Objetivo

O relatório analítico de propostas mostrava só "Produto" (`TIPO_PRODUTO`),
sem a classificação de subproduto. Expor o subproduto que já existe no
banco e identificar melhorias correlatas.

## O que foi feito

- **Nenhuma mudança de banco/RPC foi necessária**: `produtos.subtipo` já é
  exposto por `v_contratos_dashboard`, `v_contratos_em_analise` e pelas
  RPCs de cancelados, e os três loaders já mapeavam a coluna `SUBTIPO`.
  Só faltava exibi-la.
- `_COLS_PRODUTO = ["grupo_dashboard", "TIPO_PRODUTO", "SUBTIPO"]` —
  hierarquia Grupo → Produto → Subproduto adicionada às 4 tabelas da aba
  Analíticos (Propostas Pagas, Em Análise, Cancelados e busca por Nº ADE).
  Os CSVs herdam as colunas automaticamente.
- `_filtrar_detalhamento(df, key_prefix)` — substitui os três blocos de
  filtro duplicados (Loja/Consultor/Produto) e adiciona **Subproduto em
  cascata** (opções derivadas do recorte já filtrado). Keys de
  `session_state` preservadas (`det_pago_*`, `det_analise_*`,
  `det_cancel_*`).
- `_opcoes_coluna(df, coluna)` — opções de selectbox ignorando NaN
  (pagos) e `""` (em análise/cancelados, onde o join de produto não
  resolveu).
- **Bugfix**: `_preencher_categoria_fallback(df)` extraído de
  `_executar_consolidacao` para nível de módulo (junto de
  `_TIPO_PARA_CATEGORIA`) e aplicado também a `_fetch_contratos_em_analise`
  e `_fetch_contratos_cancelados`. Antes o fallback existia só para pagos:
  em jul/2026, 44 das 457 propostas em análise (`CLT`, `ANT. DE BENEF.`)
  chegavam sem `grupo_dashboard` e ficavam fora do filtro "Produto" e do
  quadro por produto da aba Em Análise.
- Testes: `TestPreencherCategoriaFallback` (4 casos) e
  `tests/test_tabs_analiticos.py` (5 casos). Suíte: 268 passed.

## Decisões não óbvias

- **"Subproduto" = `SUBTIPO` (`produtos.subtipo`), não `PRODUTO`
  (`produtos.tabela`)** — `subtipo` traz a classificação comercial
  (`NOVO`, `REFIN`, `MARGEM COMPLEMENTAR`, `SUPER CONTA`, `13º`);
  `tabela` é o nome da variante/tabela (ex: "HELP CNC NOVO"), granular
  demais para leitura. `PRODUTO` continua carregado e não exibido.
- **Coluna "Grupo" adicionada junto** (escolha do usuário) — o filtro
  "Produto" sempre filtrou por `grupo_dashboard` (CNC/PACK/CONSIGNADO)
  enquanto a coluna exibida era `TIPO_PRODUTO`; filtrar "PACK" e ver
  "FGTS" na tabela confundia. Agora as duas dimensões aparecem.
- **Valor bruto do `SUBTIPO`, sem esconder redundância** — em FGTS,
  SAQUE e PORTABILIDADE o subtipo repete o tipo. Blanquear traria
  perda de fidelidade no CSV; mantido cru.
- **`Grupo` vazio nos aceleradores é correto** — BMG MED, Seguro e
  Emissão têm `grupo_dashboard NULL` em `categorias_produto` por design
  (não entram no MIX). O fallback não inventa grupo para eles.
- **Cascata reseta o `session_state` antes de instanciar o widget** —
  ao trocar o Produto, o Subproduto selecionado pode não existir mais nas
  opções; depois da instanciação o `session_state` é imutável no rerun.
- **Fallback só preenche colunas existentes** (`campo in df.columns`) —
  em análise/cancelados não expõem `grupo_meta`/`conta_pontuacao`; sem a
  guarda, o `df.loc` criaria colunas novas quase todas NaN.

## Impacto em números exibidos

O fallback faz as propostas `CLT` e `ANT. DE BENEF.` passarem a ser
atribuídas aos grupos `CLT` e `PACK` nos quadros por produto de **Em
Análise** e **Cancelados** (antes ficavam fora do agrupamento). Totais
gerais não mudam; a soma dos grupos, sim — e agora fecha com o total.

## Pendências / follow-ups

- [ ] **Corrigir o mapeamento tipo → categoria no ETL (repo angry-man)** —
      segue valendo o follow-up de `2026-07-09-rename-tipos-clt-ant-benef.md`;
      o fallback client-side é mitigação, não correção.
- [ ] **Digitação detalhe segue sem grupo** — a RPC
      `obter_digitacao_diaria_detalhe` pré-agrega por
      `grupo_dashboard`/`categoria_codigo` no banco e não expõe
      `tipo_produto`, então o fallback client-side **não** alcança esses
      pivots: em jul/2026, 533 das 2.974 linhas voltam com grupo e
      categoria NULL (CLT / Ant. de Benef. / Conta Simples). Correção
      exige o fix no ETL ou uma migration que devolva `tipo_produto`.
- [ ] Quadro de MIX por subproduto (% REFIN vs NOVO vs MARGEM
      COMPLEMENTAR por loja/consultor) — usuário adiou para tarefa
      separada. Dado já disponível no DF; em jul/2026 o CNC é 84% REFIN,
      informação hoje invisível nos KPIs.

## Referências

- Docs consultados: [data-layer.md](../data-layer.md),
  [business-rules.md](../business-rules.md),
  [progress/2026-07-09-rename-tipos-clt-ant-benef.md](2026-07-09-rename-tipos-clt-ant-benef.md)
- Migration relacionada: `database/migrations/061_backfill_categoria_clt_ant_benef.sql`
