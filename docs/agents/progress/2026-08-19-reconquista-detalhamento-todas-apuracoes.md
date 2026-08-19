# 2026-08-19 — Reconquista: analítico deixa de ficar preso à apuração vigente

**Agente:** Claude Code
**Tipo:** feature
**Arquivos tocados:** `src/dashboard/loaders.py`,
`src/dashboard/tabs/analiticos.py`, `tests/test_loaders.py`,
`tests/test_tabs_analiticos.py`, `docs/agents/business-rules.md`,
`docs/agents/data-layer.md`, `docs/agents/ui-components.md`
**Commit(s):** (não commitado)

## Objetivo

O analítico que lista os leads de Reconquista ficava travado no mês
vigente (o mês de `dt_fim_relacionamento`). Pedido: ter a lista inteira
disponível, com a referência de vigência sempre evidenciada — usando as
flags que já separam com precisão o vigente do resto.

## O que foi feito

- **A trava era o fetch, não a UI.** `_fetch_reconquista(ref_ano,
  ref_mes)` filtrava `v_reconquista` no servidor por mês, e o
  Detalhamento só recebia esse corte. Removido.
- **`_reconquista_todos()`** (novo, `@st.cache_data(ttl=600)`): pagina a
  view inteira uma vez por keyset. `_reconquista_cache` passou a fatiar
  os três recortes mensais (`clientes` / `_ant` / `_prox`) em pandas
  (`_fatiar_ref`) — de 3 consultas por período selecionado para 0
  dentro do TTL.
- **`_marcar_vigencia_reconquista`** (novo): deriva por linha
  `apuracao_key`, `apuracao_ref` (`MM/AAAA` = ref + 1, a defasagem) e
  `vigencia` (`Vigente` / `Próxima` / `Histórico` / `Futura` /
  `Sem referência`). Constantes públicas `VIGENCIA_*`.
- **`_filtro_rls_reconquista()`** extraído de
  `_filtrar_rls_reconquista`: a lista completa passa pelo **mesmo**
  recorte por perfil dos cortes mensais, sem segunda implementação.
- **`carregar_reconquista`** devolve `clientes_todos` (RLS'd + marcado)
  e `apuracao_mes`/`apuracao_ano`. Nenhum KPI lê a chave nova.
- **Detalhamento**: pill de escopo (`Vigente · MM/AAAA` ×
  `Todas as apurações · <cobertura>`), colunas "Apuração" e "Vigência"
  nos dois escopos e no CSV, destaque das linhas vigentes no escopo
  completo, filtro "Apuração" (5ª coluna, só no completo), ordenação
  por apuração desc e paginação de 100 (padrão das demais tabelas).
- **Testes**: 11 unitários dos helpers + 5 de render via `AppTest`
  (581 no total, verdes). Equivalência do fatiamento conferida contra o
  filtro server-side em dados reais (07/2026, 08/2026, 01/2026 —
  447/538/370 linhas, conjuntos idênticos).

## Decisões não óbvias

- **Por que puxar a base inteira em vez de um 4º fetch "todos"?** A
  tabela é truncada e realimentada a cada import: 3.248 linhas em 8
  apurações (medido em 08/2026), 4 páginas keyset. Filtrar por mês no
  servidor custava 3 consultas por período **e** refazia tudo a cada
  troca de mês. É exceção deliberada ao "filtre no servidor", não
  licença geral — registrada em `data-layer.md`. Se a base crescer uma
  ordem de grandeza, o filtro volta.
- **KPIs continuam presos à apuração vigente, e isso não é limitação.**
  A apuração da campanha é mensal; somar apurações daria uma conversão
  que não corresponde a prêmio nenhum. Só o Detalhamento navega o
  histórico. Escolha do usuário entre as opções apresentadas.
- **Escopo abre no vigente** (comportamento de hoje), com um clique
  para a lista inteira — o hábito de conferência do mês não muda.
  Escolha do usuário.
- **`st.pills` e não `sac.segmented`** para o escopo, contrariando o
  padrão de sub-seleção dentro de aba: o rótulo carrega o período
  ("Todas as apurações · 02/2026 a 09/2026"), então não tem largura
  previsível, e `sac` roda em iframe — o que não cabe fica inacessível
  (mesmo modo de falha da migração de 2026-08-18). Ganho extra: widget
  nativo é dirigível por `session_state` no `AppTest`, que é como os
  testes de render do escopo funcionam. Documentado em
  `ui-components.md`; `sac.segmented` **segue** o padrão para rótulo
  curto e fixo.
- **Chave `rec_det_escopo`, fora do padrão `nav_*`**, de propósito: não
  é navegação e não deve herdar o CSS de sub-nav.
- **Apuração vigente vazia não encerra mais a sub-aba.** A guarda de
  `_render_reconquista` retornava cedo quando o mês vigente não tinha
  leads — o que, agora, esconderia justamente o histórico que o usuário
  quer consultar. Passa a encerrar só quando não há lead nenhum no
  escopo do perfil.
- **Destaque só no escopo completo**: no vigente toda linha é vigente e
  o realce viraria ruído. (Como `highlight_mask` força `st.dataframe`
  no lugar do AG Grid, não há custo — `exibir_tabela` já usa
  `st.dataframe` por padrão neste projeto.)

## Pendências / follow-ups

- [ ] A tabela do Detalhamento passou a paginar em 100 linhas (antes
      rolava inteira). Alinha com as demais tabelas da aba; confirmar
      com o usuário se o hábito de rolagem faz falta no escopo vigente.
- [ ] `v_reconquista` não tem `flag_elegibilidade` em índice nem a base
      tem índice por `ref_ano/ref_mes` — irrelevante hoje (a leitura é
      full scan de 3k linhas por design), revisitar se a base crescer.

## Referências

- Docs consultados: [business-rules.md](../business-rules.md) (Reconquista v2),
  [data-layer.md](../data-layer.md) (paginação keyset),
  [ui-components.md](../ui-components.md) (sub-navegação e segmented),
  [2026-08-18-responsividade-subnavs.md](2026-08-18-responsividade-subnavs.md)
- Migrations relevantes: 028 (tabela), 030 (view), 053 (flag de elegibilidade)
