# 2026-09-15 — Limpeza de cache do CRUD de feriados: cirúrgica, e provada

**Agente:** Claude Code
**Tipo:** bugfix
**Arquivos tocados:** `src/shared/dias_uteis.py`, `src/dashboard/loaders.py`,
`src/dashboard/feriados_mgmt.py`, `src/dashboard/kpis/gerais.py`,
`tests/test_kpis_gerais.py`, `tests/test_limpeza_cache_calendario.py` (novo),
`docs/agents/data-layer.md`

## Objetivo

Follow-up da Etapa 3 ([2026-09-14c](2026-09-14c-etapa3-criterios-paginacao-falhas.md)):
`limpar_cache_feriados` fazia `st.cache_data.clear()` — o CRUD de um
feriado derrubava o cache de tudo.

## O que a investigação mudou

O follow-up estava mal descrito. Três achados:

1. **A limpeza cirúrgica nunca rodou.** Havia duas funções. A de
   `dias_uteis` não era chamada por ninguém. A do CRUD
   (`feriados_mgmt`) chamava `_carregar_feriados_cached.clear()`, mas o
   `@st.cache_data` era criado *dentro* da função — sem `.clear()`. O
   `AttributeError` era engolido por `except: pass`, e o que fazia o
   feriado aparecer era o `st.cache_data.clear()` global logo abaixo.
   Remover só a "bala de canhão" teria deixado o feriado 24h sem efeito.

2. **Feriado alimenta outros caches.** `fn_headcount_ponderado`
   (091/096) lê `public.feriados` no SQL; os vínculos derivam
   `DIAS_ELEGIVEIS` de `_dias_uteis_competencia`.

3. **KPIs em `session_state` nunca invalidavam com feriado** — bug da
   classe da Etapa 1, com outra entrada faltando. `calcular_kpis_gerais`
   calcula `du_total` por dentro; feriado num dia ainda não decorrido
   não mudava frame nem `du_decorridos`, então a chave ficava igual. E
   o `st.cache_data.clear()` global não toca `session_state`: valia para
   a sessão de **todo** usuário, não só do admin. Reproduzido antes da
   correção (`du_total` 22 → 22, deveria ser 21).

## Decisões não óbvias

- **Custo no Nano era menor do que eu disse.** Cadastro de feriado é
  raro; o clear global custava pouco no total. O ganho real da tarefa é
  correção (itens 1 e 3), não banda.

- **Calendário entra na revisão via `calcular_dias_uteis`, não via
  conjunto de feriados.** A chave passa a depender exatamente do que o
  cálculo consome. Só nas três funções que usam `du_total` interno
  (gerais, metas diárias, qtd); as outras três recebem `du_decorridos`
  pronto e já invalidam. Não custa request: feriados são cacheados.

- **Com a revisão, o CRUD não precisa limpar `session_state`.** Limpar
  pelo CRUD só alcançaria a sessão do admin; a revisão alcança todas.

- **Composição no CRUD, não em `dias_uteis`.** `src/shared` não importa
  `src/dashboard`. Cada módulo dono expõe a própria limpeza
  (`limpar_cache_feriados`, `limpar_caches_de_calendario`) e
  `feriados_mgmt` junta — o mesmo padrão do botão "Atualizar Dados".

- **Catraca derivada, não lista decorada.** Aceitar limpeza cirúrgica
  traz o risco de um cache novo dependente de feriado ficar fora. O
  teste deriva a dependência do código (grafo de chamadas de `loaders`
  até `carregar_feriados`) e das migrations (última definição de cada
  função SQL que lê `feriados`) e compara com `CACHES_DE_CALENDARIO`.
  Hoje acha exatamente os 3 mapeados à mão.

- **`limpar_cache_feriados` reaproveitada** (decisão do usuário), sem
  `try/except` e sem a linha morta `__wrapped__ = None`.

## Verificação por sabotagem

| Sabotagem | Testes que quebram |
|---|---|
| calendário fora da revisão | 3 (`TestCalendarioNaRevisao`) |
| tirar um cache de `CACHES_DE_CALENDARIO` | 2 (limpeza + catraca) |
| voltar `st.cache_data.clear()` no CRUD | 1 |
| `limpar_cache_feriados` não limpar | 1 |

Suíte: 1.095 → 1.106, ruff limpo.

## Pendências / follow-ups

- [ ] `obter_produtividade_individual` também lê `feriados`, mas o
      dashboard não a chama; a versão publicada/caderno é materializada
      no servidor — limpar cache do cliente não a atualiza.
- [ ] A catraca cobre só `loaders.py`. Cache dependente de feriado em
      outro módulo não seria detectado (hoje não há).
