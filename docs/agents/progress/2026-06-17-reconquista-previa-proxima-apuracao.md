# 2026-06-17 — Reconquista: bloco-prévia da próxima apuração

**Agente:** Claude Code
**Tipo:** feature
**Arquivos tocados:** `src/dashboard/loaders.py`, `src/dashboard/ui/kpi_cards_reforma.py`
**Commit(s):** (não commitado)

## Objetivo

No bloco de cards do Reconquista (header), exibir — entre os 4 cards
principais e a observação `ℹ️ resultado definitivo...` — uma **prévia** da
apuração seguinte (mês+1), antecipando as **promessas** que já se acumulam
na esteira antes da virada da maciça. Pedido: "mostrar previamente como
estará em julho" enquanto a apuração de junho (ref maio) já fechou.

## O que foi feito

- `loaders.py`: novo helper `_mes_apuracao_seguinte` (rollover dez→jan).
- `_reconquista_cache`: passou a buscar também `clientes_prox =
  _fetch_reconquista(ano, mes)` — o **próprio mês selecionado** é o `ref`
  da apuração seguinte.
- `_filtrar_rls_reconquista`: aplica RLS também sobre `clientes_prox`.
- `carregar_reconquista`: deriva e retorna `prox` =
  `{ref_mes, ref_ano, apuracao_mes, apuracao_ano, totais}`.
- `kpi_cards_reforma.py`: nova `_render_previa_reconquista`, chamada dentro
  de `render_cards_reconquista` logo após os 4 cards e antes da observação.
  Espelha os 4 cards (Clientes na esteira / Efetivadas / Promessas / Sem
  reconquista) **dentro de um `st.expander` colapsado por padrão** (mesmo
  padrão de "Onde Agir Agora"); o label nomeia a prévia
  (`🔮 Prévia · Apuração de <mês+1> — fim de relacionamento em <mês selecionado>`)
  e os quadros só aparecem ao expandir.

## Decisões não óbvias

- **`ref` da prévia = o próprio mês selecionado.** A apuração `M` exibe
  `dt_fim` de `M-1` (defasagem); logo a apuração `M+1` exibe `dt_fim` de
  `M`. Portanto a prévia busca o mês selecionado como `ref` direto, sem
  reusar `_mes_apuracao_anterior`.
- **Visibilidade = "sempre que houver dados"** (escolha do usuário): a
  prévia só renderiza se `total > 0` na esteira. Trade-off aceito: em meses
  históricos a "prévia" pode coincidir com uma apuração já fechada.
- **Card de Efetivadas adaptativo.** Como `EFETIVADA` depende de
  `dt_macica > dt_fim`, na esteira ela tende a 0. O card mostra
  "consolida após a virada da maciça" quando `efet == 0` e o percentual
  normal quando já há valor (caso histórico).
- **Sem variação "vs período anterior" na prévia** — comparar mês parcial
  (acumulando) com mês fechado seria enganoso. (Os cards principais
  mantêm essa variação via `promessas_anterior`.)
- E501 (line-too-long) não é enforced pelo ruff do projeto; mantido o
  padrão de linhas longas em HTML inline já presente no arquivo.

## Pendências / follow-ups

- [ ] Validação visual no dashboard rodando (Supabase) — não executado nesta sessão.

## Referências

- Docs consultados: [business-rules.md](../business-rules.md) (seção Reconquista v2)
