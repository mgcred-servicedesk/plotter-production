# 2026-08-05 — `obter_kpis_periodo` decomposta em seis funções (ISP, ST-01)

**Agente:** Claude Code (`biz-rules`)
**Tipo:** refactor
**Arquivos tocados:** `src/dashboard/kpis/gerais.py`, `tests/test_app_helpers.py`
**Commit(s):** ver `refactor/kpis-periodo-isp-fase3`

## Objetivo

Quebrar `obter_kpis_periodo` (14 kwargs, `KpisPeriodo` de 8 campos, seis
grupos de cálculo distintos atrás de UMA chave de cache) em funções por
grupo, cada uma com seu próprio par de chaves em `session_state` —
mantendo `_chave_kpis` **literalmente intocada** (é a fronteira de RLS
entre perfis). ST-01 da fase 3; `app.py` (ST-02) e testes (ST-03) vêm
depois.

## O que foi feito

Seis funções cacheadas + uma pura, todas em `kpis/gerais.py`:

| Função | Devolve | Par de chaves |
|---|---|---|
| `obter_kpis_gerais_periodo` | `Dict` | `_kpis_gerais_cache/_chave` |
| `obter_kpis_pipeline_periodo` | `KpisPipeline` | `_kpis_pipeline_cache/_chave` |
| `obter_medias_periodo` | `Dict` | `_medias_cache/_chave` |
| `obter_medias_organizacao_periodo` | `Dict[str, float]` | `_medias_organizacao_cache/_chave` |
| `obter_metas_prod_diarias_periodo` | `List[Dict]` | `_metas_prod_diarias_cache/_chave` |
| `obter_kpis_qtd_periodo` | `List[Dict]` | `_kpis_qtd_cache/_chave` |
| `serie_diaria_pago` | `Optional[list]` | — (sem cache) |

- **Removidos:** `obter_kpis_periodo` e o NamedTuple `KpisPeriodo`.
- **Novo:** NamedTuple `KpisPipeline` (`kpis_analise`, `kpis_cancel`).
- **Renomeado:** `_serie_diaria_pago` → `serie_diaria_pago` (público).
- `limpar_cache_kpis` passa a popar os **doze** nomes (6 pares).
- Intocados: `_chave_kpis`, `_ritmo_organizacao` e todos os `calcular_*`.

## Decisões não óbvias

- **Por que `medias` e `medias_organizacao` separadas, se ambas são
  "médias"?** Sensibilidade de escopo. `obter_medias_periodo` só recebe
  frame **pós-RLS**; `obter_medias_organizacao_periodo` recebe
  `df_full`/`df_sup_full` **pré-RLS de propósito**. Com as duas no mesmo
  call site, auditar "quem toca dado fora do escopo do perfil" vira
  leitura de nome de função, não de corpo de função. Agrupá-las
  esconderia exatamente o que mais precisa ficar visível. O aviso do
  docstring antigo ("deles não sai nenhuma linha para a tela, só médias
  e contagens agregadas") foi preservado literalmente.
- **Por que `analise` e `cancelados` juntas (`KpisPipeline`), se ISP
  pediria separá-las?** Nenhum consumidor pede só uma, e
  `calcular_kpis_cancelados` já depende de `df_analise`. Separar criaria
  dois pares de chaves para dado sempre consumido em bloco — custo de
  manutenção sem ganho de ISP real. ISP é sobre não *obrigar* o cliente a
  depender do que não usa; aqui todo cliente usa as duas.
- **`du_total` via chamada interna, não via parâmetro.**
  `metas_prod_diarias` e `kpis_qtd` precisam do `du_total`, que só nasce
  dentro do grupo "gerais". Passá-lo por parâmetro criaria um contrato de
  **ordem implícito** no call site ("chame gerais antes, senão passa
  zero") — justamente o acoplamento que a decomposição quis remover. As
  duas chamam `obter_kpis_gerais_periodo` internamente: mesmo
  `session_state`, mesma `_chave_kpis`, logo **cache hit** se `app.py` já
  a chamou no mesmo rerun (medido: 0 recálculos no segundo rerun).
  Preço: as duas aceitam `df_metas`/`dia_atual`/`df_sup` sem usá-los
  diretamente — documentado no docstring de cada uma.
- **`obter_kpis_qtd_periodo` mistura pós e pré-RLS de propósito.** Precisa
  de `df_full`/`df_sup_full` para `_ritmo_organizacao` (média DU de
  referência da região). Não é acoplamento acidental: é a mesma regra de
  negócio de sempre — ritmo comparativo exige a região inteira, não o
  escopo do usuário. Dali saem só a base agregada e o normalizador.
- **`serie_diaria_pago` sem cache.** Um `groupby` por dia sobre frame já
  em memória não paga mais um par de chaves em `session_state`.
- **Cache do pipeline gravado como `dict`**, com `KpisPipeline` construído
  na saída — precedente da ST-07 (cache remanescente de sessão viva com
  formato antigo falha alto em vez de virar `AttributeError` mudo).
- **`limpar_cache_kpis` com doze `pop` escritos por extenso**, não montados
  por prefixo em loop: auditoria de cache de KPI começa por `grep` do nome
  da chave, e nome montado em runtime some do grep.
- **`_kpis_cache`/`_kpis_chave` (par antigo) não são mais popados.** Numa
  sessão viva durante o deploy, o dict antigo fica órfão até a sessão
  morrer — ninguém mais o lê. Premissa a validar: aceitável em troca de
  não carregar código de legado que precisaria ser removido depois.

## Validação

- `.venv/bin/ruff check src/ app.py` — limpo.
- Suíte sem `test_kpis_gerais.py`: **354 passed**.
- `tests/test_kpis_gerais.py` **falha na coleta** (`ImportError: KpisPeriodo`)
  — esperado: os testes ainda exercitam o bloco único. Correção é a ST-03.
- **Prova de equivalência** (script de scratch, não versionado): o corpo
  antigo reproduzido literalmente × as seis funções novas, mesmos inputs,
  cinco cenários (gerente sem filtro, gerente+filtro de loja,
  gerente+filtro de consultor, supervisor, consultor — cobrindo os três
  ramos de `_perfil_media` e os dois de `_ritmo_organizacao`).
  **Igualdade campo a campo nos oito campos, em todos os cenários.**
  Traço numérico: `meta_mix` 5000 (3000 CNC + 2000 SAQUE),
  `total_vendas` 1800 → `perc_ating_valor` 36,0% e `gap_valor` 3200.
  Cache: 12 chaves gravadas, 0 recálculos no 2º rerun, `limpar_cache_kpis`
  zera as 12 e força exatamente 1 recálculo, e troca de escopo
  (R1/R2 → R9) devolve 9999 em vez de 1800 — sem vazamento entre perfis.

## Pendências / follow-ups

- [ ] **ST-02** — `app.py`: trocar a chamada única pelas seis (import de
      `KpisPeriodo`/`obter_kpis_periodo` vai quebrar, é esperado).
- [ ] **ST-03** — `tests/test_kpis_gerais.py`: `TestObterKpisPeriodo`
      precisa virar cobertura por função (miss/hit/invalidação por escopo
      em cada um dos seis pares de chaves).
- [ ] **Doc divergente:** `docs/agents/architecture.md` (linha ~16 e passo
      6 do fluxo) descreve "calcula KPIs numa chamada
      (`kpis/gerais.py::obter_kpis_periodo`)". Atualizar junto da ST-02,
      quando o fluxo real de `app.py` estiver definido.

## Referências

- Docs consultados: [docs/agents/business-rules.md](../business-rules.md),
  [docs/agents/rpi-workflow.md](../rpi-workflow.md),
  [AGENTS.md](../../../AGENTS.md)
- Antecedentes: [2026-08-04-obter-kpis-periodo-extraida.md](2026-08-04-obter-kpis-periodo-extraida.md),
  [2026-08-04-teste-obter-kpis-periodo.md](2026-08-04-teste-obter-kpis-periodo.md)
