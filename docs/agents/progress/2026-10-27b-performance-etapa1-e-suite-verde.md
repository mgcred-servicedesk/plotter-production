# 2026-10-27 — Performance do time: Etapa 1 fechada e suíte verde

**Agente:** Claude Code (orquestração + subagentes biz-rules, ui-dash, data-layer, testing)
**Tipo:** bugfix / refactor
**Arquivos tocados:** `app.py`, `src/dashboard/kpis/gestao.py`,
`src/dashboard/kpis/produtividade.py`, `src/dashboard/tabs/gestao_consultores.py`,
`src/dashboard/loaders.py`, `docs/agents/business-rules.md`, 8 arquivos em `tests/`
(`src/dashboard/ui/charts.py` só com a alteração local herdada)
**Commit(s):** — (nada commitado)

## Objetivo

Atuar no [handoff do Devin](2026-10-27-handoff-performance-conversao.md):
Etapa 1 (revisar os cinco grupos de alterações locais e fechar a lacuna do
callback de competência sem pagamentos) e, em frente paralela, as 5 falhas
pré-existentes da suíte.

## O que foi feito

- **Revisão dos cinco grupos** (alterações locais herdadas, preservadas):
  agregação em R$/dia sem vínculo, meta do Total, variação por mês-calendário
  e lacunas no gráfico estavam corretos. Bloqueios na UI de critérios tinham
  bug (F3, abaixo).
- **D1 — competência indisponível.** `_carregar_competencia_gestao` devolve
  `(None, None, sup)` quando a base consolidada **global** está vazia;
  `_render_tendencia` junta os meses num único aviso e o subtítulo soma a
  janela (na série · indisponíveis · sem colaborador no escopo).
- **D2 — produção sem vínculo declarada.** `construir_tabela` publica
  `attrs["sem_vinculo"]` em `prod_dia` acima do consultor; a aba mostra
  legenda com pessoas e R$ (MIX inteiro).
- **F3** — o bloqueio "R$/dia + período personalizado" saía antes dos widgets
  e o Streamlit descartava produtos/limiares (o aviso "preset preservado" era
  falso). Agora critérios e presets são renderizados antes do bloqueio.
- **F4** — `_motivo_meta_indisponivel` dava razão falsa para acelerador em
  R$/dia e a razão do pack para Total sem meta de produto; agora uma razão por
  grupo, e o Total distingue pack parcial, produto sem meta e meta conjunta
  ausente (`_motivo_total_sem_meta`, lendo só a matriz de `matriz_metas`).
- **F5** — sem o mês anterior na série, a variação volta vazia (antes marcava
  o time inteiro como "ausente no anterior").
- **F6** — o "whitespace" do handoff era CR: 4 linhas CRLF em arquivos LF,
  normalizadas.
- **5 falhas:** `cache_version=1` no par `_fim_relacionamento_liga_*` com
  passagem explícita no dispatcher (risco real, não teste velho); testes de
  sub-nav da Reconquista e de chaves de `obter_medias_periodo` atualizados;
  par FDR incluído nos testes que travam o dispatcher (allowlist inalterada).
- `business-rules.md` (casos de borda da produtividade) passou a registrar D1,
  D2 e F5.

**Resultado:** suíte 1761 ✓ / 5 ✗ → **1848 ✓ / 0 ✗**; `ruff check src/ app.py`
limpo; `git diff --check` limpo exceto o arquivo CRLF (pendência abaixo).

## Decisões não óbvias

- **Mês globalmente vazio é lacuna, não zero** (D1, usuário). O handoff
  sugeria carregar o ledger nesse caso; isso desenharia R$ 0/dia para todo
  mundo num mês sem dado. Escopo filtrado vazio com base presente segue R$ 0/dia.
- **`valor` do `sem_vinculo` é o MIX inteiro**, independente de
  `produtos_total` — é o que saiu da razão. Com filtro de produto, está em
  base diferente do Total visível (a legenda diz isso). Recorte vazio volta sem
  attrs.
- **Sabotagem obrigatória**: cada correção foi desfeita à mão e derrubou ao
  menos um teste novo (ST-03: 15 sabotagens; ST-05: 7), com sha256 conferido
  na restauração. O `test_intervalo_personalizado_...` antigo passava por acaso
  (MagicMock) — substituído por AppTest que prova a preservação de estado
  pelos dois caminhos de saída do bloqueio.
- **Comportamentos fixados em teste** (confirmar se são de produto): limiar não
  é convertido ao trocar R$/dia ↔ valor (Streamlit 1.61.1 mantém o estado do
  `number_input` com `key`); preset salvo no bloqueio grava o recorte inteiro e
  sempre cai no bloqueio ao reaplicar; um só dos frames `None` já conta como
  indisponível; sub-aba FDR aparece em qualquer mês com período de apuração,
  inclusive antes de 10/2026.
- **Premissa:** o callback aninhado de `app.py` não é executado por teste;
  só o contrato da aba está coberto.

## Pendências / follow-ups

- [ ] Revisão do Codex: D1 e o bloqueio duro de meta incompatível (`st.error` +
  `return` em `incompativeis`).
- [ ] QA visual desktop/mobile da aba Gestão (não feito nesta rodada).
- [ ] Mesma perda de estado em outros `return` antecipados de
  `_render_criterios`: data final ainda não escolhida, intervalo sem contrato,
  `tabela.empty`; e `gestao_minimo`/`gestao_incluir_zerados` condicionais.
- [ ] Último mês da janela indisponível: a variação compara os dois últimos
  meses presentes e a legenda diz "duas últimas competências fechadas" — sem
  spec; decidir.
- [ ] Erro de carga em `consolidar_dados` dentro da série ainda derruba a
  sub-visão inteira (já era assim).
- [ ] `tests/test_loader_fim_relacionamento_liga.py` é o único arquivo CRLF do
  repo (veio assim em 11469a9); normalizar = diff de ~165 linhas.
- [ ] `_fim_relacionamento_liga_historico` nunca roda via dispatcher nos testes
  (autouse força mês atual); `producao_lojas`/`num_lojas_digitais` só têm a
  chave testada, não o valor; docstring de
  `test_dispatcher_passa_a_versao_explicitamente` diz que default sozinho não
  muda a chave — no 1.61.1 o código-fonte entra na chave.
- [ ] Etapas 2–4 do handoff, cada uma com RPI próprio.

## Patterns criados ou atualizados

Nenhum. Candidato: "AppTest + espião que chama a função real + prova de estado
de widget com sabotagem" (harness em `tests/test_tabs_gestao_presets.py`).

## Referências

- Handoff: [2026-10-27-handoff-performance-conversao.md](2026-10-27-handoff-performance-conversao.md)
- Docs consultados: [collaboration.md](../collaboration.md),
  [orchestrator.md](../orchestrator.md), [rpi-workflow.md](../rpi-workflow.md),
  [business-rules.md](../business-rules.md), [rls.md](../rls.md),
  [data-layer.md](../data-layer.md)
