# 2026-06-18 — Metas regionais desacopladas da presença de contratos

**Agente:** Claude Code
**Tipo:** bugfix + cleanup (follow-up do code-review do commit d1d7ff4)
**Arquivos tocados:** `src/dashboard/kpis/regioes.py`, `src/dashboard/loaders.py`,
`src/dashboard/ui/kpi_cards_reforma.py`, `tests/test_kpis_regioes.py`
**Commit(s):** (não commitado)

## Objetivo

O commit anterior (2026-06-16) desacoplou o **total global** de metas da
presença de contratos (loja com meta e zero contrato passou a contar). Mas as
KPIs **por região** continuaram derivando o escopo da região a partir dos
contratos, então o total global deixou de bater com a soma das regiões
(ex.: HELP PAVUNA contava no global, mas sumia da sua região). Bug #1 do
code-review.

## O que foi feito

- `kpis/regioes.py`: novo helper `_metas_da_regiao(df_metas, regiao, lojas_regiao)`.
  Quando o DataFrame de metas traz a coluna `REGIAO` (caso de produção, após
  `_fetch_metas`/`_fetch_metas_produto`), recorta por `REGIAO == regiao`
  (desacoplado de contratos). Quando **não** traz `REGIAO`, cai para o proxy
  antigo `LOJA.isin(lojas_com_contrato)`. Aplicado em 3 pontos:
  `calcular_kpis_por_regiao`, `calcular_heatmap_regiao_produto` e
  `calcular_kpis_por_produto_regiao`.
- `loaders.py`: extraído `_reanexar_regiao(df_pivot, fonte)` para remover a
  duplicação do bloco "drop_duplicates(LOJA) + merge" presente em
  `_fetch_metas` e `_fetch_metas_produto` (cleanup #8).
- `kpi_cards_reforma.py`: removidos 4 guards mortos `if total else 0.0` em
  `_render_previa_reconquista` (o early-return `if total == 0` já garante
  `total > 0`) (cleanup #10).
- `tests/test_kpis_regioes.py`: novo teste
  `test_meta_inclui_loja_sem_contrato_via_regiao` travando a correção.

## Decisões não óbvias

- **Fallback por contratos preservado.** O helper só usa `REGIAO` quando ela
  existe. As fixtures de teste (`df_metas_lojas`, `df_metas_produto_lojas`)
  **não** têm `REGIAO`, então os testes existentes seguem pelo caminho antigo
  e continuam verdes — a mudança é retrocompatível e só altera o comportamento
  em produção, onde as metas carregam `REGIAO`.
- **Código morto removido (com confirmação do usuário).** `regioes.py` tinha
  duas funções públicas sem nenhum caller na app — só referenciadas por
  testes: `calcular_ranking_regioes` (rankings regionais por **pontos**) e
  `calcular_media_producao_regiao`. Git confirma que ambos os callers foram
  apagados no commit `a049c17` ("replace points-based rankings with
  value/quantity metrics"); a aba regional viva usa `calcular_kpis_por_regiao`
  / `calcular_kpis_por_produto_regiao` (baseadas em valor/%). Removidas as duas
  funções + suas classes de teste (`TestCalcularRankingRegioes`,
  `TestCalcularMediaProducaoRegiao`) + o import `excluir_supervisores` (que
  ficara órfão). Suíte caiu de 79 → 75 testes, ruff limpo.
- **Achados do review refutados pelo schema (não tocados):**
  - *Inner join derrubaria metas órfãs no histórico* — `metas.loja_id` é
    `NOT NULL REFERENCES lojas(id) ON DELETE CASCADE`; `lojas!inner` nunca
    derruba linha que o left join manteria (no histórico, sem filtro `ativo`).
  - *Meta por consultor seria soma de todos os consultores da loja* — a tabela
    `metas` não tem coluna de consultor; a UNIQUE
    `(periodo_id, loja_id, produto, escopo, nivel)` garante 1 linha
    CONSULTOR por (loja, produto). O pivot por LOJA é identidade.

## Pendências / follow-ups

- [ ] Validação visual no dashboard rodando (Supabase) — não executado.
- [ ] **Decisão do usuário** sobre achados adiados do review:
      #2 `_filtrar_metas_ui` (consultor sem contrato → metas zeram),
      #6 fetch ansioso do `clientes_prox` (prévia colapsada),
      #7 helper de card (refator de display, sem cobertura de teste),
      #5 nome de loja duplicado → REGIAO arbitrária, #9 refator do
      `aplicar_rls_metas`.
- [ ] Regiões com meta mas **zero** contrato no período não aparecem na aba
      (o loop itera `df["REGIAO"].unique()` dos contratos) — caso raro, não
      tratado.

## Referências

- Code-review (xhigh) do commit d1d7ff4.
- Docs: [data-layer.md](../data-layer.md), [rls.md](../rls.md).
