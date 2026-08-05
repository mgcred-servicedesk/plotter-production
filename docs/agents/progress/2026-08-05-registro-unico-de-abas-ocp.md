# 2026-08-05 — Registro único de abas em `main()` (Fase 2 — OCP)

**Agente:** Claude Code (`ui-dash`, via `task-orchestrator`)
**Tipo:** refactor
**Arquivos tocados:** `app.py`,
`docs/agents/patterns/validar-refactor-de-ui-com-apptest.md`
**Commit(s):** ver `git log` da branch `refactor/app-py-solid-fase1`
(commit desta ST)

> **Numeração:** o enunciado desta ST chama a anterior (bloco "Período"
> → `ui/sidebar.py`) de **ST-12**; o commit `e2000a5` e a entrada de
> progresso dela dizem **ST-11**. Deixei esta entrada sem número para
> não firmar a divergência — a confirmar com o orquestrador.

## Objetivo

Primeira ST da Fase 2 (OCP). A navegação principal mantinha **duas**
listas paralelas das mesmas 9 abas dentro de `main()`: `abas_disponiveis`
(chave de permissão + rótulo + ícone, usada para montar `st.pills`) e um
`if/elif` de 9 ramos para o despacho. Aba nova exigia lembrar dos dois
lugares — e nada acusava o esquecimento. Objetivo: uma fonte de verdade
só, sem criar módulo novo nem objeto de contexto.

## O que foi feito

- `_AbaNav(NamedTuple)` no topo de `app.py` (seção de helpers de
  `main()`): `permissao`, `rotulo`, `icone`, `render`. O `render` é um
  callable de **aridade zero**.
- `registro_abas`: tupla de 9 `_AbaNav` montada onde `abas_disponiveis`
  vivia, com cada `render` fechando sobre os frames já carregados em
  `main()` (`df_f`, `kpis`, `categorias`, …). Nenhuma assinatura de
  `render_tab_*` mudou.
- Despacho vira lookup: `renders_aba.get(tab)` + `if ... is not None`.
  `rotulos_visiveis` e `icones_aba` passam a derivar do registro.
- Os 3 ramos com trabalho extra continuam idênticos, só mudaram de
  moldura: Rankings (2 loaders + `aplicar_rls`) e Gestao (2 loaders +
  RLS + filtros de UI + a closure `_carregar_intervalo_gestao`) viraram
  `def` locais; Pagamentos Online cabia em expressão e virou lambda,
  **sem** `aplicar_rls` — comportamento atual preservado de propósito.
- `app.py`: 783 → 864 linhas.

## Decisões não óbvias

- **`NamedTuple` em vez de tupla crua, dataclass ou dict de dicts.**
  Precedente da casa (`DadosPeriodo`, `KpisPeriodo`); com 3 dos 4 campos
  `str`, posição sozinha é frágil. Dict de dicts perderia o autocomplete
  e não é usado em lugar nenhum do projeto.
- **Lambda para 7 abas, `def` local para 2.** Não é escolha estética:
  Rankings e Gestao têm *statements* (atribuição, `def` aninhado) antes
  da chamada, e lambda não aceita statement. Inliná-los na lista de
  argumentos caberia sintaticamente, mas enterraria os comentários que
  explicam por que os universos passam por `aplicar_rls`.
- **O registro é local a `main()`, não módulo.** Foi decisão do
  enunciado, e a closure é o que a viabiliza: sem ela, um registro
  no escopo do módulo obrigaria a criar um objeto de contexto com ~17
  campos só para atravessar a fronteira. O custo é `app.py` **crescer**
  81 linhas — a Fase 1 encolhia, esta ST não.
- **`renders_aba` e `icones_aba` são montados a partir das 9 entradas,
  não só das visíveis.** Idêntico ao comportamento anterior (o `if/elif`
  também não checava permissão; o gate está — e continua — em `options`
  do `st.pills`). Montar só as visíveis seria um pouco mais
  fail-closed, mas mudaria um caminho hoje inalcançável, e a validação
  mostrou por quê ele é inalcançável: o `st.pills` **descarta** valor de
  `session_state` fora de `options` e cai no `default` (provado com
  `nav_principal` forjado para `"Gestao"` num supervisor). Se algum dia
  o gate mudar de lugar, essa é a linha a revisitar.
- **Sem `else` no despacho.** `dict.get` + `if is not None` reproduz
  exatamente o "nenhum ramo casou" anterior. Nenhum `st.warning` novo.

## Validação

Matriz **inteira** perfil × aba via `AppTest`, conforme
[patterns/validar-refactor-de-ui-com-apptest.md](../patterns/validar-refactor-de-ui-com-apptest.md):
37 cenários (admin 9, gestor 9, gerente_comercial 7, supervisor 6,
consultor 6) + 2 de chave forjada = **39**, contra o commit `e2000a5`.
**Diff byte a byte vazio**, `0 exceptions`, `0 misses` de VCR nos dois
lados. `ruff` limpo; `pytest` 405 passed.

O achado que quase invalidou a validação: rodando contra o banco vivo
(mês corrente, ETL escrevendo), **dois runs do mesmo baseline** com 4
minutos de intervalo divergiram em 74 linhas estruturais. Foi preciso
congelar os loaders num VCR de `pickle` para o diff medir código.
Detalhes e receita na seção nova do pattern.

## Pendências / follow-ups

- [ ] `tabs/pagamentos_online.py` é a única aba cujo loader **não**
      passa por `aplicar_rls` — preservado como está por instrução
      explícita desta ST. Vale uma decisão consciente (é global por
      natureza? deveria recortar?) numa ST de RLS, não numa de OCP.
- [ ] O registro poderia virar dado de módulo se as abas passassem a
      receber um contexto único em vez de ~17 parâmetros posicionais.
      É a próxima fronteira de OCP, e é decisão de arquitetura — não
      cabia aqui.
- [ ] O helper de inventário `AppTest` + o congelamento de loaders vivem
      só no scratchpad de cada sessão. Se a Fase 2 continuar exigindo a
      matriz inteira, vale promovê-lo a `tests/` ou `tools/`.

## Patterns criados ou atualizados

- Atualizado:
  [patterns/validar-refactor-de-ui-com-apptest.md](../patterns/validar-refactor-de-ui-com-apptest.md)
  — seção nova "o banco muda debaixo do diff" (congelar `carregar_*` em
  `pickle`, gravar com o baseline e diffar dois replays, misses como
  critério de aceite) e o comportamento do `st.pills` com chave forjada.

## Referências

- Handoff anterior:
  [2026-08-05-periodo-extraido-para-ui-sidebar.md](2026-08-05-periodo-extraido-para-ui-sidebar.md)
- Docs consultados: [docs/agents/rpi-workflow.md](../rpi-workflow.md),
  [docs/agents/ui-components.md](../ui-components.md) (atualizado: o
  trecho da navegação primária mostrava o `if/elif`),
  `src/dashboard/permissions.py`
