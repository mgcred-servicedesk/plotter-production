# 2026-08-04 — Extração das regras de pipeline duplicadas em `app.py` (ST-03)

**Agente:** Claude Code (`biz-rules`, via `task-orchestrator`)
**Tipo:** refactor
**Arquivos tocados:** `app.py`, `src/dashboard/kpis/detalhes_cards.py`,
`src/dashboard/kpis/gerais.py`, `tests/test_kpis_detalhes_cards.py`
**Commit(s):** ver branch `refactor/app-py-solid-fase1`

## Objetivo

Fase 1 do refactor SOLID/SRP de `app.py`. Dentro de `main()` havia dois
blocos de regra de negócio inline e **literalmente duplicados** para
`df_analise` e `df_cancelados`: (1) zerar `VALOR` do que conta só como
quantidade e (2) corte de 30 dias por `DATA_CADASTRO`. Extrair para
funções puras e testáveis, aplicadas de forma idêntica aos dois DFs.

## O que foi feito

- `_aplicar_conta_valor` → **`aplicar_conta_valor`** (pública) em
  `kpis/detalhes_cards.py`, agora com **duas cláusulas cumulativas**:
  `conta_valor=False` **ou** `TIPO OPER.` ∈ `TIPOS_OPER_EMISSAO`
  (novo `frozenset` com `CARTÃO BENEFICIO` / `Venda Pré-Adesão`).
- Nova `filtrar_janela_recente(df, dias=JANELA_PIPELINE_DIAS,
  referencia=None)` em `kpis/gerais.py`, junto de `excluir_supervisores`
  / `excluir_lojas_backoffice`. `JANELA_PIPELINE_DIAS = 30`.
- `main()` passou de ~45 linhas inline (4 blocos duplicados) para 2
  chamadas simétricas, uma por DataFrame.
- `from datetime import datetime` promovido ao topo de `app.py`; o
  import local redundante dentro de `main()` foi removido (era
  **obrigatório**: um `import` local torna o nome local em toda a
  função, o que causaria `UnboundLocalError` no uso anterior a ele).
- Renomeados os 4 call sites internos + o teste existente.

## Decisões não óbvias

- **Por que a regra de VALOR ficou em `kpis/detalhes_cards.py`?** —
  decisão do usuário: já existia lá `_aplicar_conta_valor` com 4 call
  sites e testes. Estender > criar uma terceira implementação.
- **Por que o corte de 30 dias foi para `kpis/gerais.py`, e não junto
  da outra regra?** — `detalhes_cards.py` é, por docstring, "funções
  puras de **detalhamento (drill-down) dos cards**". O corte de 30 dias
  não é drill-down: filtra o DF que alimenta **todas** as abas. O
  precedente mais forte para filtro puro transversal sobre DF de
  contratos é `gerais.py` (`excluir_supervisores`,
  `excluir_lojas_backoffice` + constante `LOJAS_BACKOFFICE` ao lado do
  helper). Bônus: `app.py` já importava de `gerais`.
- **Por que manter o nome `aplicar_conta_valor` mesmo cobrindo duas
  cláusulas?** — `business-rules.md` ("Emissão de cartão") define os
  dois `TIPO OPER.` como produtos cuja categoria *deveria* ter
  `conta_valor=False`; a cláusula é o **fallback** da mesma regra, não
  uma regra nova. Renomear invalidaria 4 call sites e os testes sem
  ganho semântico.
- **Por que `referencia` explícita?** — o código antigo calculava
  `data_corte` **uma vez** para os dois DFs. `datetime.now()` dentro da
  função daria dois cortes distintos. O parâmetro preserva o
  comportamento e torna a função determinística em teste.
- **Extensão do `TIPO OPER.` é no-op nos call sites antigos** (checado):
  `df` (pagas) já chega com `VALOR = 0` nessas linhas via
  `consolidar_dados` (`loaders.py`, `is_emissao_cartao`), e
  `df_analise` / `df_cancelados` são zerados na carga em `app.py`.
- **Ganho colateral (mutação de DF cacheado):** o código antigo fazia
  `df_analise.loc[...] = 0` **in place** sobre o retorno de
  `carregar_contratos_em_analise` / `_cancelados`, que delegam a
  funções `@st.cache_data`. Era seguro só porque `cache_data` devolve
  cópia a cada acesso — dependência frágil e não documentada.
  `aplicar_conta_valor` faz `df.copy()`, então a carga não escreve mais
  no objeto do loader.
- **Premissa:** `DATA_CADASTRO` é datetime garantido pelo loader
  (`pd.to_datetime(errors="coerce")`). A comparação foi mantida **crua**
  (sem coerção defensiva) para preservar o comportamento e porque dtype
  errado deve falhar alto, não ser silenciosamente filtrado. `NaT` sai
  da janela — igual ao comportamento anterior.

## Pendências / follow-ups

- [ ] O par `["CARTÃO BENEFICIO", "Venda Pré-Adesão"]` continua
      **hardcoded em outros 4 pontos**: `loaders.py:1650`,
      `kpis/gerais.py:_PRODUTOS_QTD`, `tabs/produtos.py:44`,
      `tabs/em_analise.py:73`. Consolidar em `TIPOS_OPER_EMISSAO` (ou em
      `config/settings.py`, ao lado de `PRODUTOS_EMISSAO`, que é coisa
      **diferente** — aquele é `TIPO_PRODUTO`). Cruza data-layer + UI:
      exige orquestração, não foi feito aqui.
- [ ] `loaders.py` (`consolidar_dados`) mantém sua própria aplicação da
      regra porque também zera `pontos` e deriva `is_emissao_cartao` —
      não é duplicação pura de `aplicar_conta_valor`. Avaliar se o
      trecho de VALOR pode delegar.
- [ ] ST-T1 (subtarefa separada) — testes das duas funções extraídas,
      incluindo a nova cláusula `TIPO OPER.` e as bordas da janela.

## Patterns criados ou atualizados

Nenhum.

## Referências

- Docs consultados: [docs/agents/business-rules.md](../business-rules.md),
  [docs/agents/rpi-workflow.md](../rpi-workflow.md),
  [docs/agents/conventions.md](../conventions.md)
- Verificação: equivalência numérica old×new confirmada em DF sintético
  (6 linhas cobrindo `conta_valor=False`, `conta_valor=None`, ambos os
  `TIPO OPER.` de emissão, `NaT` e a borda dos 30 dias) — `df.equals`
  `True`, índices idênticos.
