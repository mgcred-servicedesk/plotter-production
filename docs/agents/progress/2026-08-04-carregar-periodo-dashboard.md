# 2026-08-04 — `carregar_periodo_dashboard` extraída para `loaders.py` (ST-05)

**Agente:** Claude Code (`data-layer`, via `task-orchestrator`)
**Tipo:** refactor
**Arquivos tocados:** `app.py`, `src/dashboard/loaders.py`
**Commit(s):** ver branch `refactor/app-py-solid-fase1`

## Objetivo

Fase 1 do refactor SOLID/SRP de `app.py`. O bloco de `main()` que montava
os sete frames do período (pagos + metas + supervisores, categorias,
metas por produto, em análise, cancelados) misturava três coisas:
sequenciamento de carga, aplicação das regras já extraídas nas ST-03/04 e
o reporte de progresso para o `st.status`. Extrair a **montagem dos
dados**, deixando a UI de progresso em `main()`.

## O que foi feito

- Nova função pública `carregar_periodo_dashboard(mes, ano, on_progress=None)`
  em `src/dashboard/loaders.py`, em seção própria ("Carga do periodo do
  dashboard") logo após o cluster de consolidação.
- Novo `NamedTuple` `DadosPeriodo` com os sete frames
  (`df`, `df_metas`, `df_sup`, `categorias`, `df_metas_produto`,
  `df_analise`, `df_cancelados`).
- `loaders.py` passou a importar `aplicar_conta_valor`
  (`kpis/detalhes_cards`) e `filtrar_janela_recente` (`kpis/gerais`).
  Sem ciclo: nenhum módulo de `kpis/` importa `loaders`.
- `main()` chama a função em uma linha e continua dona do
  skeleton/`st.status`, do `_eh_primeira`, do `_n_cancel_admin` e do
  early-return de `df.empty`.
- Seis imports ficaram órfãos em `app.py` (`aplicar_conta_valor`,
  `filtrar_janela_recente`, `carregar_categorias`,
  `carregar_contratos_em_analise`, `carregar_contratos_cancelados`,
  `carregar_metas_produto`) e saíram — seriam `F401`.
  `consolidar_dados` e `aplicar_nomes_display_produto` **permanecem**:
  ainda são usados no lazy-load de mês anterior/YoY da aba Produtos.

## Decisões não óbvias

- **`NamedTuple` em vez de tupla simples** — são sete valores e cinco
  deles são `pd.DataFrame`; trocar `df_metas` por `df_sup` na ordem seria
  um erro silencioso. `NamedTuple` desempacota exatamente como tupla, então
  o call site não muda de estilo. **Sinalizado:** é um padrão ausente do
  codebase até aqui (só tuplas anônimas e `Tuple[...]`); adotado porque a
  aridade justifica, não como convenção nova a espalhar.
- **Onde cortar o `on_progress`** — a função recebe
  `Callable[[str], None]` e emite o **rótulo cru** ("Carregando contratos
  pagos..."). A formatação `:shimmer[...]` e o ciclo de vida do widget
  ficam no `_upd_status` de `main()`. O loader sabe em que etapa está; só
  a UI sabe como isso se desenha. Wrapper interno `_progresso` faz o
  guard de `None` uma vez, em vez de repetir `if on_progress is not None`
  quatro vezes.
- **Nenhum cache na função nova** — cada loader chamado já tem política
  própria de TTL (`_atual` vs `_historico`). Um `@st.cache_data` aqui
  duplicaria a chave `(mes, ano)` com invalidação mais grossa e faria o
  botão "Atualizar Dados" ter dois níveis de cache para limpar.
  Documentado na docstring.
- **RLS continua fora** — a função devolve os frames **completos**, sem
  `aplicar_rls`. `main()` precisa dos snapshots pré-RLS (`df_full`,
  `df_metas_full`, ...) para o heatmap comparativo; aplicar RLS dentro do
  loader quebraria isso. O contrato "loader não recorta por perfil" está
  na docstring para não ser revertido por engano.
- **Mudança de ordem aceita** — `aplicar_nomes_display_produto` agora roda
  **antes** do teardown do `st.status` (antes rodava depois). É rename
  puro em pandas, não altera contagem de linhas e não toca UI; o único
  consumidor entre os dois pontos (`_n_cancel_admin = len(df_cancelados)`)
  é invariante a rename.
- **Premissa a validar:** o instante único de `datetime.now()` usado como
  `referencia` das duas janelas agora é capturado **dentro** do loader.
  Continua sendo um só instante para os dois frames (que era o ponto da
  ST-03), mas deixou de ser injetável a partir de `main()`. Se algum dia
  for preciso congelar esse instante em teste E2E, o parâmetro precisa
  subir para a assinatura de `carregar_periodo_dashboard`.

## Pendências / follow-ups

- [ ] O lazy-load de mês anterior/YoY da aba Produtos (`app.py`, dentro de
      `if tab == "Produtos"`) repete `consolidar_dados` +
      `aplicar_nomes_display_produto` + `aplicar_rls`. Não é a mesma
      composição desta ST (não carrega categorias/metas/pipeline) e não
      entrou aqui. Avaliar numa rodada futura se cabe uma variante enxuta.
- [ ] `DadosPeriodo` não tem teste dedicado — a função é composição de
      loaders que batem no Supabase, então cobri-la exige fake do cliente
      ou monkeypatch dos seis loaders. Decidir com o `test-automation`
      se vale.

## Patterns criados ou atualizados

Nenhum.

## Referências

- Handoff anterior:
  [2026-08-04-nomes-display-produto-loaders.md](2026-08-04-nomes-display-produto-loaders.md)
  (ST-04) e
  [2026-08-04-extracao-regras-pipeline-app-py.md](2026-08-04-extracao-regras-pipeline-app-py.md)
  (ST-03)
- Docs consultados: [docs/agents/rpi-workflow.md](../rpi-workflow.md),
  [docs/agents/data-layer.md](../data-layer.md)
