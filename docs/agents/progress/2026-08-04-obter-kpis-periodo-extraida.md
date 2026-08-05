# 2026-08-04 — `obter_kpis_periodo` extraída para `kpis/gerais.py` (ST-07)

**Agente:** Claude Code (`biz-rules`, via `task-orchestrator`)
**Tipo:** refactor
**Arquivos tocados:** `app.py`, `src/dashboard/kpis/gerais.py`,
`tests/test_app_helpers.py`
**Commit(s):** ver branch `refactor/app-py-solid-fase1`

## Objetivo

Fase 1 do refactor SOLID/SRP de `app.py`. O bloco de `main()` que
montava a chave de cache de KPIs e encadeava os sete cálculos do período
era o trecho mais sensível da fase: a tupla `chave_kpis` é a **fronteira
de cache entre perfis**. Extrair o bloco inteiro (chave + cálculo +
gravação no `session_state`) para o módulo de KPI, sem alterar um
componente sequer da chave.

## O que foi feito

- Nova função pública `obter_kpis_periodo(...)` (keyword-only) em
  `src/dashboard/kpis/gerais.py`, em seção própria ("Composicao dos KPIs
  do periodo (com cache manual)") no fim do arquivo.
- Novo `NamedTuple` `KpisPeriodo` com os oito valores, na mesma ordem das
  chaves já gravadas em `_kpis_cache`.
- Novo helper privado `_chave_kpis(...)` — só a montagem da tupla.
- `_ritmo_organizacao` e `_serie_diaria_pago` **movidos** de `app.py`
  para `kpis/gerais.py`, verbatim.
- `main()` passou a fazer uma chamada só, desempacotando posicionalmente
  nos mesmos nomes locais de antes (`kpis`, `kpis_analise`, ...) — zero
  diff a jusante no corpo de `main()`.
- Seis imports ficaram órfãos em `app.py` e saíram (`calcular_kpis_gerais`,
  `calcular_kpis_cancelados`, `calcular_kpis_qtd_produtos`,
  `calcular_medias_du_por_nivel`, `calcular_medias_organizacao`,
  `calcular_metas_produto_diarias`). **`calcular_kpis_analise` permanece**:
  ainda é usado no early-return de `df.empty` (dashboard sem contratos
  pagos, só pipeline em análise).
- `tests/test_app_helpers.py` passou a importar de
  `src.dashboard.kpis.gerais`. Lógica dos testes existentes intacta.

## Decisões não óbvias

- **Onde ficaram `_ritmo_organizacao` / `_serie_diaria_pago`: em
  `kpis/gerais.py`.** São cálculo puro sobre DataFrames, não chamam
  `st.*` e só são consumidos pelo bloco extraído. Mantê-los em `app.py`
  para injetá-los como parâmetro deixaria código de KPI fora do módulo
  de KPI e acoplaria `main()` a um detalhe interno da composição. Foram
  copiados **verbatim** (inclusive a sintaxe `str | None`, que difere do
  `Optional[...]` do resto de `gerais.py`) — mover sem editar mantém o
  diff auditável como movimentação pura; alinhar o estilo seria mudança
  fora do escopo, e o ruff do projeto (`select = E4,E7,E9,F`) não cobre
  `UP*`. **Não existem duas cópias**: `app.py` não tem mais as funções.
- **`session_state` injetado, não importado.** Nenhum módulo de `kpis/`
  importa Streamlit no topo (`src/shared/dias_uteis.py` até usa
  `st.cache_data`, mas com import **adiado** dentro da função). Importar
  `streamlit` em `kpis/gerais.py` quebraria essa invariante e contrariaria
  o precedente da ST-05 (a função extraída não conhece Streamlit; quem
  chama decide a UI). O parâmetro é tipado `MutableMapping[str, Any]`:
  `st.session_state` satisfaz estruturalmente e um `dict` comum serve em
  teste. **Consequência para a ST-T2:** a função é exercitável sem
  runtime do Streamlit.
- **O cache continua sendo gravado como `dict`**, não como o `NamedTuple`.
  Assim o formato de `_kpis_cache` não muda: os `pop` do botão "Atualizar
  Dados" (`app.py`) seguem válidos e um cache remanescente de sessão viva
  não vira `AttributeError`. O `KpisPeriodo` é construído na saída, via
  `KpisPeriodo(**session_state["_kpis_cache"])`.
- **`NamedTuple` em vez de tupla anônima** — oito valores, quatro deles
  `Dict`. Mesmo argumento do `DadosPeriodo` da ST-05, que já estabeleceu
  o padrão nesta branch; não é padrão novo sendo introduzido aqui.
- **`_chave_kpis` como função separada** — é uma abstração a mais, mas
  isola a fronteira de segurança num ponto testável e documentável. Sem
  ela, provar a equivalência da chave exigiria executar todo o pipeline
  de cálculo. A docstring dela descreve os seis componentes e por que
  cada um existe.
- **Os dois filtros de UI passaram a ser relidos do `session_state`
  dentro da função** (antes vinham das locais `_ui_lojas` /
  `_consultor_selecionado` de `main()`). A chave já lia
  `st.session_state` diretamente; agora o bloco todo tem uma fonte só.
  Auditado: os **únicos** escritores de `ui_filtro_lojas` /
  `ui_filtro_consultor` no codebase estão em `src/dashboard/ui/sidebar.py`
  e rodam em `render_sidebar_filtros_perfil`, chamado **antes** da
  chamada. Contrato registrado na docstring.

## Prova de equivalência da chave de cache

Três verificações, todas verdes:

1. **Chave, old × new** — script ad-hoc (scratchpad, não commitado)
   comparando `_chave_kpis` com a expressão literal copiada de
   `git show HEAD:app.py` (linhas 608-615; única alteração:
   `st.session_state` → `session_state`, para rodar fora do Streamlit).
   Matriz de 3 meses × 2 anos × 6 roles × 10 perfis (incl. `None`, sem
   chave `escopo`, escopo vazio e escopo em ordem trocada) × 27
   `session_state` (lojas `None`/`[]`/ordens diferentes, consultor
   `None`/`""`/nomes, chaves ausentes) = **9720 combinações, tupla e
   tipos idênticos em todas**. Mais 9 recortes distintos → 9 chaves
   distintas (nenhuma colisão entre perfis).
2. **Bloco de cálculo, old × new** — diff textual do bloco antigo
   (`git show HEAD:app.py`, 616-709) contra o corpo da função nova,
   normalizando indentação e os renomes `df_f`→`df`, `df_metas_f`→
   `df_metas`, `df_metas_prod_f`→`df_metas_produto`, `df_analise_f`→
   `df_analise`, `df_cancelados_f`→`df_cancelados`, `df_sup_f`→`df_sup`,
   `st.session_state`→`session_state`, `chave_kpis`→`chave`: **idêntico
   linha a linha**, exceto as duas linhas do `_perfil_media` (item 3).
3. **`_perfil_media`, old × new** — as duas linhas do item 2 comparadas
   por execução sobre 6 roles × 27 `session_state` = **162 combinações,
   resultado idêntico**. (`bool(x)` e `x` têm a mesma verdade; `_ui_lojas`
   era literalmente `session_state.get("ui_filtro_lojas") or []`.)

Adicionalmente, teste de regressão permanente `TestChaveKpis` em
`tests/test_app_helpers.py` (5 casos): composição/ordem dos seis
componentes, escopos distintos não colidem (dois gerentes de mesmo
`role`), período/role/filtros invalidam, seleção de lojas independe da
ordem, e normalização de ausentes (`None` → `()`/`""`) sem colidir com
filtro real.

## Pendências / follow-ups

- [ ] `tests/test_app_helpers.py` agora testa código que vive em
      `kpis/gerais.py` — o nome do arquivo ficou histórico. Renomear
      (ex.: `test_kpis_periodo.py`) é decisão da **ST-T2**; não foi feito
      aqui para não conflitar com a ST de testes nem apagar histórico de
      arquivo sem instrução.
- [ ] `obter_kpis_periodo` em si não tem teste dedicado (só os helpers e
      a chave). É o alvo natural da **ST-T2**: cache miss × hit,
      invalidação por troca de escopo e o guard de divisão por zero de
      `perc_ating_valor` quando `meta_mix = 0`. Smoke manual feito nesta
      ST cobriu os três caminhos, mas não ficou versionado.
- [ ] `du_decorridos` é calculado duas vezes em `main()` (antes e depois
      do RLS, linhas ~426 e ~541) e só o segundo chega aqui. Não foi
      tocado — é pré-existente e fora do escopo da ST-07.

## Patterns criados ou atualizados

Nenhum.

## Referências

- Handoff anterior: [2026-08-04-carregar-periodo-dashboard.md](2026-08-04-carregar-periodo-dashboard.md)
  (ST-05, precedente do `NamedTuple` e do "função extraída não conhece
  Streamlit") e [2026-08-04-diagnostico-pontuacao-extraido.md](2026-08-04-diagnostico-pontuacao-extraido.md)
  (ST-08)
- Docs consultados: [docs/agents/rpi-workflow.md](../rpi-workflow.md),
  [docs/agents/business-rules.md](../business-rules.md),
  [docs/agents/rls.md](../rls.md)
