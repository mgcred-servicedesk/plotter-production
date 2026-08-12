# 2026-08-12 — Distribuição de Produtos: Top N → paginação + visão por Loja/Consultor

**Agente:** Claude Code (orquestrado: `business-rules-kpi-expert`, `streamlit-ui-specialist`, `test-automation-specialist`)
**Tipo:** feature
**Arquivos tocados:** `src/dashboard/kpis/produtos.py`, `src/dashboard/tabs/analiticos.py`, `tests/test_kpis_produtos.py`
**Commit(s):** (não commitado)

## Objetivo

Em Analíticos > Distribuição de Produtos, remover o `st.slider` "Exibir top
N consultores" (Top 5–50) e substituir por paginação. Supervisor mantém a
visão por Consultor (já restrita por RLS de loja), agora paginada. Gerente
Comercial/Admin/Gestor passam a abrir numa visão agregada por **Loja**
(nova), paginada, com toggle "Ver por Consultor" que revela busca local.

## O que foi feito

- `calcular_distribuicao_produtos_por_loja(df)` nova em
  `kpis/produtos.py`, logo após `calcular_distribuicao_produtos`: mesmo
  pivot/máscaras, eixo `LOJA` em vez de `CONSULTOR`, **sem**
  `excluir_supervisores`. Guard-clause sem `"LOJA"` → `(DataFrame(), [],
  [])`. Colunas: `LOJA` | `REGIAO` (se existir) | valores (ordem
  alfabética) | `TOTAL` | aceleradores presentes (`BMG Med`, `Vida
  Familiar`, `Emissao`, `Super Conta`). Retorno idêntico em forma ao da
  versão por consultor — pluga direto em `exibir_tabela`.
- Helper privado `_mascaras_aceleradores(df)` extraído e compartilhado
  pelas duas funções (comportamento da versão por consultor inalterado).
- `analiticos.py`: bloco `elif menu == "Distribuicao de Produtos":`
  reduzido a `_render_distribuicao_produtos(df, df_sup, perfil)` + 2
  helpers (`_render_distribuicao_por_loja`,
  `_render_distribuicao_por_consultor`, este último compartilhado entre
  supervisor e o toggle ligado). Paginação via `exibir_tabela(...,
  paginacao=100, key=...)`. CSV sempre exporta o dataset completo
  (independente de busca/paginação na tela).
- `tests/test_kpis_produtos.py`: classe
  `TestCalcularDistribuicaoProdutosPorLoja`, 6 testes — guard-clause,
  agregação/ordenação por loja, supervisor incluído no total da loja ×
  excluído por consultor (teste comparativo), PACK desmembrado,
  acelerador por quantidade, não-duplicação de loja com região variável.

## Decisões não óbvias

- **Supervisor entra no total da loja, sem exclusão.** Decisão de
  negócio confirmada com o usuário antes da implementação; segue o
  precedente já documentado em
  [business-rules.md](../business-rules.md) § "Produção de supervisor —
  conta pro total, marcada, fora do ranking": supervisor nunca vira
  linha própria em nenhuma visão, mas sua produção soma no agregado de
  loja (igual ao card "Aceleradores").
- **`drop_duplicates("LOJA")` no merge de região, não do par `(LOJA,
  REGIAO)`.** Loja que troca de região no meio do período (vigência
  temporal SCD2, `loja_regiao_vigencia`) duplicaria a linha inteira com
  o par — a versão por consultor usa o par e tem esse bug pré-existente
  (ver follow-up).
- **Busca de consultor com key local (`dist_prod_busca_cons`), sem
  reaproveitar `_render_consultor_subselect`** (`ui/sidebar.py`): aquele
  grava em `session_state["ui_filtro_consultor"]`, filtro **global** que
  vazaria a seleção para o resto do dashboard.
- **Supervisor sem toggle nem busca** — decisão de negócio confirmada:
  sempre vê por consultor (equipe já pequena via RLS de loja).
- **`st.caption` de transparência** na visão por loja, avisando que o
  total inclui produção do supervisor — sem isso, alternar o toggle faz
  os números mudarem sem explicação aparente.

## Pendências / follow-ups

- [x] ~~`calcular_distribuicao_produtos` (por consultor) usa
      `drop_duplicates()` do par `(LOJA, REGIAO)` — loja que troca de
      região no período duplicaria a linha do consultor~~ — **investigado
      e descartado.** `contratos.periodo_id` é derivado de
      `data_status_pagamento` e o loader sempre filtra
      `.eq("periodo_id", periodo["id"])`
      ([loaders.py:339](../../src/dashboard/loaders.py)), então todo
      registro do `df` já pertence a um único período. Dentro desse
      período, a migration
      [051_regiao_ancora_periodo_pagamento.sql](../../database/migrations/051_regiao_ancora_periodo_pagamento.sql)
      resolve `regiao` em `v_contratos_dashboard` por uma âncora **única
      por período** (`make_date(periodo.ano, periodo.mes, 1)`, não a
      `data_cadastro` de cada contrato) — toda linha da mesma loja no
      mesmo período recebe exatamente a mesma região, por construção.
      Uma loja nunca aparece com 2 regiões dentro de um período (atual ou
      futuro); um remanejamento produz corte limpo entre períodos
      (período novo = região nova para toda a loja; períodos passados
      permanecem com a região antiga, imutáveis). O cenário sintético de
      120 consultores que reproduziu 360 linhas violava essa invariante
      real do schema (região variável por loja dentro do mesmo período,
      que não ocorre em dado de produção) — não representa um risco
      real. `drop_duplicates("LOJA")` (nova função, por loja) e
      `drop_duplicates()` do par (função existente, por consultor)
      produzem o mesmo resultado sob a garantia do schema; nenhuma
      correção necessária.

## Patterns criados ou atualizados

Nenhum novo pattern formal. Reforça `pattern_verify_composed_against_direct_calc.md`
(memória do agente de testes): validar função derivada contra a chamada
direta da função "irmã" em vez de hardcodar literais.

## Referências

- Docs consultados: [business-rules.md](../business-rules.md) (§§
  "Produção de supervisor", "Exclusão de supervisores"),
  [ui-components.md](../ui-components.md), [rpi-workflow.md](../rpi-workflow.md).
- Verificação: `.venv/bin/ruff check src/ app.py tests/` limpo;
  `.venv/bin/python -m pytest tests/` → 489 passed (483 baseline + 6
  novos), 1 warning pré-existente (confirmado via `git stash` que já
  ocorria antes desta mudança).
