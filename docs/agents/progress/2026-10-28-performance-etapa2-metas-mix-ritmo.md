# 2026-10-28 — Performance do time: Etapa 2 (metas individuais, MIX e ritmo)

**Agente:** Claude Code (orquestração + subagentes biz-rules, ui-dash, testing)
**Tipo:** bugfix / feature
**Arquivos tocados:** `src/dashboard/kpis/produtividade.py`,
`src/dashboard/tabs/gestao_consultores.py`, `src/dashboard/ui/resumo_executivo.py`,
`tests/test_kpis_produtividade.py`, `tests/test_tabs_gestao_presets.py`,
`docs/agents/business-rules.md`
**Commit(s):** — (nada commitado; parte de `0d73059`)

## Objetivo

Etapa 2 do [handoff](2026-10-27-handoff-performance-conversao.md): metas
CONSULTOR da loja principal, ausência de meta explícita, `avaliar_regra_mix`
para pendências e falta, e dias futuros elegíveis no ritmo necessário.

## O que foi feito

- **Ponto de partida:** o commit `0d73059` trouxe, junto com a Etapa 1, um
  trabalho paralelo que já implementava a Etapa 2 em `enriquecer_performance`.
  A rodada revisou essa implementação, corrigiu as bordas e documentou as
  regras (o trabalho não tinha progress nem regra no `business-rules.md`).
- **HEAD vermelho (9 falhas) corrigido.**
  - 8 testes de callback rodavam o `_render_gestao` real de `app.py` via AST,
    mas o ambiente falso não tinha `df` nem `dados_prestamista`; foram
    completados. Isso fecha a premissa da Etapa 1: o D1 no `app.py` agora tem
    teste.
  - 1 teste quebrava porque o rótulo do Resumo Executivo tinha sido trocado
    para "dos produtos MIX atingidos" (E4, revertido).
- **E1 — `VINCULO FUTURO`:** a admissão posterior à data de referência saía
  `SEM VINCULO` e sumia da tela.
  - Agora recebe meta integral, falta, dias restantes e ritmo, num bloco
    próprio da aba.
  - Fica fora da produtividade por dia e da base dos cards.
- **E2 — `Motivo sem meta`:** todo `SEM META` passou a dizer por quê, com cinco
  causas em precedência fixa. Antes, coluna componente ausente no pivô virava
  meta 0 e o MIX encolhia em silêncio (12.000 sem o pack).
- **E3:** dias restantes de vínculo sem término conhecido contam até o fim do
  mês (ratificado e documentado).
- Regras registradas em `business-rules.md`, na subseção "Metas individuais,
  MIX e ritmo na Performance".

**Resultado:** suíte 1870 ✓ / 9 ✗ → **1912 ✓ / 0 ✗**; `ruff check src/ app.py`
e `git diff --check` limpos; `app.py` e `kpis/gerais.py` sem alteração.

## Decisões não óbvias

- **Divergência intencional com o dashboard principal (E2).**
  `calcular_metas_produto_diarias` trata coluna ausente como meta 0; a
  Performance diz `SEM META`.
  - O pivô CONSULTOR usa `fill_value=0`, então loja sem linha de um produto já
    chega como 0. O motivo "não cadastrada" só aparece quando nenhuma loja do
    mês tem o produto.
  - De 06 a 10/2026 os 5 componentes existem nas 47 lojas, e o SAQUE tem 0.
- **`VINCULO FUTURO` é relativo à referência** `min(última venda, hoje)`.
  Quem entrou entre a última venda e hoje também cai nele. Por isso o rótulo
  diz "admissão após a data de referência", não "admissão futura".
- **Sabotagem:** 11 mecanismos no KPI, incluindo os 7 que já existiam em
  `enriquecer_performance`, e 11 no `app.py` e na aba. Todos derrubaram
  teste. O único que não derrubava (contexto de metas sem os vínculos do mês)
  ganhou teste.
- **Comportamentos fixados em teste** (confirmar se são de produto):
  - `VINCULO FUTURO` em loja sem meta mantém a situação, com motivo.
  - Os dias restantes dele são o mês inteiro.
  - Com produção, ele usa a loja de maior pontuação.
  - O CSV exporta a tabela do corte e não inclui `VINCULO FUTURO`.

## Pendências / follow-ups

- [ ] Revisão do Codex de E1/E2 (e, da rodada anterior, D1 e o bloqueio de
  meta incompatível).
- [ ] QA visual desktop/mobile da aba Gestão.
- [ ] Etapa 3. Já existem, com teste:
  - IPV por colaborador na Performance;
  - `resumo_performance_time`, `consistencia_performance` e
    `comparar_historico_proprio`, ainda não ligados na aba; o parâmetro
    `carregar_metas_competencia` de `_render_performance` está sem uso.

  `produtividade_carteira["sem_vinculo"]` e
  `resumo_performance_time["sem_vinculo"]` contam dias == 0 e, portanto,
  incluem `VINCULO FUTURO`.
- [ ] `VINCULO FUTURO` com venda paga também aparece em "Produção sem vínculo
  no ledger" (aceito; rever se incomodar).
- [ ] CSV da Performance sem `VINCULO FUTURO`: incluir ou exportar o bloco à
  parte, se o usuário quiser.
- [ ] Se todo o escopo for `VINCULO FUTURO`, a aba diz "Nenhum colaborador
  dentro do corte escolhido" sem haver corte.
- [ ] Data-layer: o `fill_value=0` do pivô CONSULTOR esconde a ausência de
  meta por loja.
- [ ] `produtividade_por_consultor` quebra (`IntCastingNaNError` em
  `_posicao_na_loja`) se `LOJA` vier `NaN` do ledger; hoje o loader não
  manda (inner join com lojas ativas).

## Patterns criados ou atualizados

Nenhum.

## Referências

- Handoff: [2026-10-27-handoff-performance-conversao.md](2026-10-27-handoff-performance-conversao.md)
- Etapa 1: [2026-10-27b-performance-etapa1-e-suite-verde.md](2026-10-27b-performance-etapa1-e-suite-verde.md)
- Docs consultados: [business-rules.md](../business-rules.md),
  [orchestrator.md](../orchestrator.md), [rpi-workflow.md](../rpi-workflow.md)
