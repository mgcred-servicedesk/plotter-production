# 2026-08-05 — Call site de KPIs: 6 funções por grupo e cálculo adiado

**Agente:** Claude Code (`ui-dash`, via `task-orchestrator`)
**Tipo:** refactor
**Arquivos tocados:** `app.py`, `docs/agents/architecture.md`
**Commit(s):** ver `refactor/kpis-periodo-isp-fase3` (ST-02)

## Objetivo

Atualizar `app.py` para consumir as seis funções `obter_*_periodo` criadas
no ST-01 (`64b49f6`), que decompôs `obter_kpis_periodo` (14 kwargs →
`KpisPeriodo` de 8 campos, uma chave de cache só). O call site ainda
importava e chamava a API antiga, já removida do módulo.

## O que foi feito

- Import: `obter_kpis_periodo` → as 6 `obter_*_periodo` + `serie_diaria_pago`.
  `calcular_kpis_analise` e `limpar_cache_kpis` seguem como estavam.
- A chamada única desempacotando 8 variáveis virou **dois pontos**:
  - **Ponto A** (mesmo lugar de antes, logo após o RLS + filtros de UI):
    só `obter_kpis_gerais_periodo` → `kpis`.
  - **Ponto B** (novo, logo antes de `render_kpis_reforma`): os outros
    cinco grupos + `serie_diaria_pago(df_f)`, com os **mesmos nomes de
    variável** de antes — nenhum renderer precisou mudar.
- Comentários do bloco antigo (fronteira de perfil da `_chave_kpis`,
  frames `*_full` pré-RLS de propósito) foram adaptados, não apagados.
- `docs/agents/architecture.md`: passo 6 do fluxo reescrito em 6a/6b/6c;
  entrada de `kpis/gerais.py` na árvore atualizada.

## Decisões não óbvias

- **Por que o Ponto B fica DEPOIS dos dois early-returns, e não junto do
  Ponto A?** Entre os dois pontos existem dois `return`: a view de
  pontuação (`dashboard_view == "pontuacao"` → `render_dashboard_pontuacao`,
  que recebe só `kpis`) e o drill-down de card (`card_page` setado →
  `render_drilldown_card`, que lê só `kpis["du_total"]`). Nenhum dos dois
  consome os outros cinco grupos. Enquanto a chamada era **única e
  indivisível**, esses dois caminhos pagavam pipeline, médias, médias da
  organização, metas por produto, KPIs de quantidade e série diária sem
  usar nada disso. Adiar é o ganho de desempenho concreto que a
  decomposição por ISP habilitou — não é ISP por princípio.
  Medido: 9 dos 14 cenários de validação passaram de **6 grupos
  calculados para 1**.
- **Por que o Ponto B fica dentro do `if pode_ver("cards_gerenciais", role)`
  e não fora dele?** É o único lugar depois dos dois `return` — o segundo
  deles mora dentro desse `if`. Hoje a matriz de permissões dá
  `cards_gerenciais` a **todos** os cinco perfis, então nenhum caminho de
  render perde variável; foi verificado por `grep` que nada referencia
  esses nomes depois do bloco. Se algum dia um perfil deixar de ver os
  cards gerenciais, ele simplesmente não computa os cinco grupos — o que
  continua correto, já que também não renderiza quem os consome.
  (Nota: o comentário "Consultor nao ve cards gerenciais" logo acima do
  `if` está desatualizado em relação à matriz; não foi tocado por estar
  fora do escopo desta subtarefa.)
- **`serie_diaria_pago` entra no Ponto B mesmo sendo pura e sem cache.**
  Ela é barata, mas só alimenta `render_kpis_reforma`; deixá-la no Ponto A
  faria a pontuação e o drill-down pagarem um `groupby` por dia à toa,
  contrariando a intenção da mudança.

## Validação

- `.venv/bin/ruff check src/ app.py` — limpo.
- `.venv/bin/python -m pytest tests/ --ignore=tests/test_kpis_gerais.py` —
  354 passed (o `test_kpis_gerais.py` é escopo do ST-03).
- **Paridade via `AppTest`** (padrão
  [validar-refactor-de-ui-com-apptest](../patterns/validar-refactor-de-ui-com-apptest.md)),
  baseline `64b49f6~1` em worktree, loaders congelados em `pickle`,
  14 cenários por versão (5 perfis × normal / pontuação / 4 drill-downs):
  - inventário de render **byte a byte idêntico** (diff vazio);
  - **0 misses** de VCR dos dois lados — a versão nova não pediu nenhum
    dado que a antiga não pedisse;
  - baseline × baseline idêntico (sem ruído de harness);
  - única divergência: as chaves de cache em `session_state`, que é
    exatamente a evidência do adiamento (tabela acima).

## Pendências / follow-ups

- [ ] ST-03: `tests/test_kpis_gerais.py` ainda importa `KpisPeriodo` /
      `obter_kpis_periodo` e está quebrado — intencional, roda depois.
- [ ] Comentário obsoleto em `app.py` ("Consultor nao ve cards
      gerenciais") diverge de `permissions.MATRIZ` — corrigir fora desta ST.

## Patterns criados ou atualizados

- Nenhum novo. Reaplicação de
  [patterns/validar-refactor-de-ui-com-apptest.md](../patterns/validar-refactor-de-ui-com-apptest.md)
  — primeiro uso em que o diff **não** deve ser totalmente vazio: as
  chaves de `session_state` são o sinal procurado, e o critério de aceite
  virou "render idêntico + 0 misses + divergência restrita às chaves".

## Referências

- Subtarefa anterior:
  [2026-08-05-decomposicao-obter-kpis-periodo-isp.md](2026-08-05-decomposicao-obter-kpis-periodo-isp.md)
- Docs consultados: [architecture.md](../architecture.md),
  [rpi-workflow.md](../rpi-workflow.md), [AGENTS.md](../../../AGENTS.md)
