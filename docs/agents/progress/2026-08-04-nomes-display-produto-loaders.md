# 2026-08-04 — `aplicar_nomes_display_produto` extraída para `loaders.py` (ST-04)

**Agente:** Claude Code (`data-layer`, via `task-orchestrator`)
**Tipo:** refactor
**Arquivos tocados:** `app.py`, `src/dashboard/loaders.py`,
`tests/test_loaders.py`
**Commit(s):** ver branch `refactor/app-py-solid-fase1`

## Objetivo

Fase 1 do refactor SOLID/SRP de `app.py`. A closure local
`_aplicar_nomes_display` dentro de `main()` (troca de chave interna de
`grupo_dashboard` pelo rótulo de UI, via `NOMES_DISPLAY_PRODUTO`) tinha
**5 call sites** — 3 na carga (`df`, `df_analise`, `df_cancelados`) e 2
no lazy-load da aba Produtos (mês anterior e YoY) — mais um **6º ponto
que reimplementava a mesma regra inline** para `categorias`.

## O que foi feito

- Nova função pública `aplicar_nomes_display_produto(frame)` em
  `src/dashboard/loaders.py`, na seção "Categorias e periodos",
  imediatamente após `carregar_categorias`. Corpo idêntico ao da closure.
- `NOMES_DISPLAY_PRODUTO` passou a ser importado por `loaders.py`; o
  import correspondente saiu de `app.py` (ficaria órfão → `F401`).
- Os 6 pontos de `app.py` passaram a chamar a função — incluindo o bloco
  de `categorias`, que deixou de duplicar a lógica inline.
- 5 testes unitários novos em `tests/test_loaders.py`
  (`TestAplicarNomesDisplayProduto`): renomeia chave mapeada, não muta o
  original, preserva colunas/índice, passa direto em frame vazio ou sem
  a coluna, e trata `categorias` como qualquer outro frame.

## Decisões não óbvias

- **Por que `loaders.py` e não um módulo novo de "display"?** — decisão
  do usuário. A troca acontece na **fronteira de carga**, antes de
  qualquer cálculo, e o módulo já expõe transformações puras públicas
  ao lado dos loaders (`meses_do_intervalo`, `filtrar_por_intervalo`).
  Não é regra de negócio nem renderização: é normalização de
  vocabulário sobre o que acabou de ser carregado.
- **Por que ao lado de `carregar_categorias`?** — `categorias` é um dos
  frames de entrada da função e a única outra fonte de `grupo_dashboard`
  além dos contratos. Mantém as duas pontas do vocabulário juntas.
- **Unificar o bloco de `categorias` muda comportamento?** — Não, em
  conteúdo. O bloco antigo fazia `.copy()` **incondicional** + `replace`
  guardado só por `in columns`; a função guarda também por `.empty` e,
  nesse caso degenerado, devolve **o próprio objeto** em vez de uma
  cópia. Equivalência verificada em 5 cenários (normal, `grupo_dashboard`
  nulo, vazio sem colunas, vazio com a coluna, sem a coluna): `equals`,
  colunas, índice e dtypes idênticos nos cinco.
- **A cópia defensiva perdida importa?** — Não. Nenhum consumidor de
  `categorias` escreve nela (só máscaras booleanas de leitura em
  `kpis/produtos.py`, `kpis/regioes.py`, `ui/prioridades_acao.py`), e
  `carregar_categorias()` é `@st.cache_data`, que já devolve uma cópia
  por chamada — o objeto do cache nunca era o alvo do `.copy()`.
- **Premissa a validar:** a checagem `frame.empty` continua sendo uma
  otimização, não semântica. Se algum dia um consumidor passar a mutar o
  frame retornado, o contrato "devolve o próprio objeto quando não há o
  que renomear" precisa virar cópia sempre.

## Pendências / follow-ups

- [ ] `src/dashboard/kpis/produtos.py:47` aplica `NOMES_DISPLAY_PRODUTO`
      de novo, por docstring como "rede de segurança", dentro de uma
      função maior. Não é call site da closure e não entrou nesta ST.
      Avaliar se pode delegar a `aplicar_nomes_display_produto` ou se a
      rede de segurança deixou de ser necessária agora que a troca é
      única e centralizada na carga.
- [ ] `src/dashboard/tabs/regioes.py:79` usa
      `NOMES_DISPLAY_PRODUTO.get(g, g)` sobre uma lista de labels (não um
      DataFrame) — fora do contrato da função. Só mapear se algum dia
      houver variante para sequências.

## Patterns criados ou atualizados

Nenhum.

## Referências

- Handoff anterior:
  [2026-08-04-extracao-regras-pipeline-app-py.md](2026-08-04-extracao-regras-pipeline-app-py.md)
  (ST-03)
- Docs consultados: [docs/agents/rpi-workflow.md](../rpi-workflow.md),
  [docs/agents/data-layer.md](../data-layer.md)
