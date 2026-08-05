# 2026-08-05 — Drill-down de cards extraído para `pages/detalhes_cards.py` (ST-10)

**Agente:** Claude Code (`ui-dash`, via `task-orchestrator`)
**Tipo:** refactor
**Arquivos tocados:** `app.py`, `src/dashboard/pages/detalhes_cards.py`
**Commit(s):** ver `git log` da branch `refactor/app-py-solid-fase1`
(commit desta ST)

## Objetivo

Última extração de UI da Fase 1 do refactor SOLID/SRP de `app.py`. O
bloco `if _card_page:` dentro de `if pode_ver("cards_gerenciais", role):`
concentrava o botão de voltar, o dispatch dos quatro cards de drill-down
e a carga do detalhe de digitação. Mover para o módulo que já hospeda as
quatro páginas de detalhe — extração mecânica, sem redesenho.

Era o follow-up registrado na entrada da ST-06 ("o bloco de drill-down
espelha o padrão da config e é candidato natural a uma extração
equivalente").

## O que foi feito

- Novo `render_drilldown_card(card_page, *, df, df_analise,
  df_cancelados, df_sup, du_decorridos, du_total, mes, ano, perfil)` no
  fim de `src/dashboard/pages/detalhes_cards.py`: botão de voltar +
  dispatch dos quatro casos (`em_analise`, `cancelados`,
  `media_consultor`, `media_loja`).
- A carga do detalhe de digitação
  (`aplicar_rls(carregar_digitacao_diaria_detalhe(mes, ano))`) migrou
  junto, para dentro do ramo `em_analise` — daí `mes`/`ano` na
  assinatura.
- `main()` passa a ter só o gate + a chamada + o `return`:

  ```python
  _card_page = st.session_state.get("card_page")
  if _card_page:
      render_drilldown_card(_card_page, ...)
      return
  ```

- Imports órfãos em `app.py` migraram: os quatro `render_detalhe_*`
  viraram um único `render_drilldown_card`;
  `carregar_digitacao_diaria_detalhe` saiu de `app.py` e entrou no
  módulo de páginas (junto de `aplicar_rls`, que **continua** também em
  `app.py`, com nove outros usos).
- `app.py`: 859 → 824 linhas.

## Decisões não óbvias

- **O `return` e o gate `pode_ver("cards_gerenciais", role)` ficaram em
  `main()`** — mesma linha da ST-06: o módulo renderiza, `app.py` decide
  *quando*. Alternativa descartada: a função retornar `bool` para
  `if render_drilldown_card(...): return`, que esconderia o
  short-circuit dentro de um valor de retorno.
- **A carga do detalhe de digitação migrou junto (não ficou em
  `main()`).** Três dos quatro ramos não a consomem; deixá-la fora
  obrigaria `main()` a carregar dado que só um ramo usa, ou a passar um
  DataFrame vazio. É o mesmo critério da ST-09 (dado que só um consumidor
  usa vive junto de quem o usa) — e o enunciado da ST já previa
  `mes`/`ano` entre os parâmetros.
- **`render_drilldown_card` e não `render_detalhe_*`.** O prefixo
  `render_detalhe_` está reservado às quatro páginas; esta é a
  roteadora. O sufixo `_card` casa com a chave de estado (`card_page`) e
  com a chave de permissão (`cards_drilldown`).
- **`card_page` posicional, resto keyword-only.** Acompanha o estilo do
  módulo (as quatro páginas são `*`-only) e deixa o call site legível
  sem repetir `card_page=_card_page`.
- **Não usei o walrus (`if _card_page := ...`) sugerido no enunciado.**
  Não há nenhum `:=` no codebase hoje; manter as duas linhas atuais
  deixa o diff mínimo e não estreia idioma novo numa ST de extração
  mecânica. Se o time quiser adotar, é decisão à parte.
- **Chave desconhecida renderiza só o botão de voltar** (nenhum `else`
  com erro). É exatamente o comportamento anterior — a cadeia
  `if/elif` sem `else` já era assim. O fail-closed real está a montante
  (`_CARDS_VALIDOS` na promoção do query param).
- **O botão "← Voltar ao Dashboard" continua sem `key`** — mesma
  justificativa da ST-06: o outro botão de mesmo rótulo (página de
  Config) nunca renderiza no mesmo run, e o ID auto-gerado depende dos
  parâmetros do widget, não do arquivo de origem.
- **Docstring do módulo atualizada** para dizer que o dispatch agora
  mora nele (a nota de permissões continua válida e não mudou).

## Validação

- `ruff check src/ app.py` limpo; `pytest tests/` **403 passed** (mesmo
  número da ST-09).
- **Prova de identidade do bloco movido:** o corpo do `if _card_page:`
  extraído por AST de `git show HEAD:app.py` — menos o `return` final e
  menos a atribuição `_du_total = kpis.get("du_total", 0)` (virou
  parâmetro) — tem **AST idêntica** ao corpo de `render_drilldown_card`
  sob o mapa de renomes `_card_page→card_page`, `_du_total→du_total`,
  `df_f→df`, `df_analise_f→df_analise`, `df_cancelados_f→df_cancelados`,
  `df_sup_f→df_sup`, `role→perfil`. 2 statements dos dois lados.
- **Regressão visual (padrão `AppTest`):** 8 cenários diffados contra
  worktree do commit anterior — **diff vazio em todos**:
  - `admin` × os 4 valores de `card_page` — contagem de elementos
    distinta por página (em_analise 11, cancelados 9, médias 5 cada),
    provando que cada ramo executou o seu;
  - `gerente_comercial` (escopo `ROBSON`) × `media_loja` e `em_analise`
    — cobre a dimensão `LOJA` de `_dimensao_por_perfil`;
  - `supervisor` (escopo `HELP BANGU`) × `em_analise`;
  - `admin` × chave forjada (`chave_forjada`) → só o botão de voltar, 0
    elementos depois dele.
  - Em todos: `at.exception` vazio, `nav_principal` **ausente** do
    `session_state` (o `return` continua cortando as abas) e
    `_kpis_cache` **presente** (o drill-down continua depois do cálculo
    de KPIs, não antes).
  - `sac.divider` aparece como `component_instance` no inventário do
    `at.main` quando se percorre a árvore de nós direto (não pelos
    acessores tipados) — útil para contar quadros por página.

## Observação (não é regressão desta ST)

`pode_ver("cards_gerenciais", perfil)` é `True` para **todos** os cinco
perfis, incluindo supervisor e consultor. Logo o gate que envolve o
drill-down não fecha para ninguém: um `card_page` já presente no
`session_state` renderiza a página de detalhe mesmo para supervisor —
comportamento **idêntico antes e depois** desta ST (comprovado no
cenário `supervisor_em_analise`, diff vazio).

Na prática o estado é inalcançável para esses perfis: as duas únicas
escritas de `card_page` (`ui/kpi_cards_reforma.py` e a promoção do query
param em `app.py`) são gated por `cards_drilldown`, que é `False` para
supervisor/consultor. O comentário `# Consultor nao ve cards gerenciais`
em `app.py`, porém, diverge da matriz de permissões. Fica como
follow-up.

## Pendências / follow-ups

- [ ] Divergência comentário × matriz: `# Consultor nao ve cards
      gerenciais` em `app.py` vs. `cards_gerenciais["consultor"] = True`
      em `permissions.py`. Decidir qual é a verdade (ajustar comentário
      ou fechar a permissão) — mudança de comportamento, fora do escopo
      de extração.
- [ ] Herdada da ST-01/ST-02/ST-06, ainda aberta: `main()` monta inline
      o bloco "Período" (expander ano/mês + "Atualizar Dados") e o
      `st.image` do logo — sidebar que não migrou.
- [ ] Herdada da ST-02: `IndexError` latente em
      `(_user.get("nome", "").split()[0]) if _user else ""` quando o
      nome é vazio/só espaços.

## Patterns criados ou atualizados

- Atualizado:
  [patterns/validar-refactor-de-ui-com-apptest.md](../patterns/validar-refactor-de-ui-com-apptest.md)
  — inventário por travessia recursiva de `at.main.children` (pega
  `sac.*` como `component_instance` e cobre blocos aninhados) e cenário
  de chave forjada para provar o ramo "nenhum caso casou".

## Referências

- Handoff anterior:
  [2026-08-04-pagina-config-extraida-para-pages-config.md](2026-08-04-pagina-config-extraida-para-pages-config.md)
  (ST-06 — origem do padrão "gate e `return` ficam no `main()`")
- Docs consultados: [docs/agents/rpi-workflow.md](../rpi-workflow.md),
  [docs/agents/ui-components.md](../ui-components.md)
