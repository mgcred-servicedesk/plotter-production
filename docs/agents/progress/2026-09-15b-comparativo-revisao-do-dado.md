# 2026-09-15 — Mês comparativo congelado na sessão

**Agente:** Claude Code
**Tipo:** bugfix
**Arquivos tocados:** `src/dashboard/tabs/produtos.py`,
`tests/test_tabs_produtos.py`, `docs/agents/ui-components.md`

## Objetivo

Follow-up da Etapa 1 ([2026-09-14](2026-09-14-etapa1-rls-e-caches.md)):
`_carregar_mes_comparativo` tinha o mesmo bug de atualidade da chave dos
KPIs.

## O que foi feito

A chave do memo em `session_state` tinha período, perfil, escopo e
filtros, sem nada do dado. Enquanto esses componentes não mudavam,
`consolidar_dados` não era chamada: o TTL do loader não tinha efeito e
uma correção retroativa num mês passado (reativação de cancelado,
ajuste de ETL) não chegava a quem já estava com a aba aberta. Só
"Atualizar Dados" renovava o frame. Reproduzido antes da correção: a
sessão mostrava R$ 100 com o dado já em R$ 350, e o snapshot pré-RLS
também ficava parado.

Agora `consolidar_dados` é consultada a cada render e a chave passa a
ser `(escopo, _revisao_frame(frame))`. Nomes, RLS e filtros só são
refeitos quando o dado ou o escopo mudam.

## Decisões não óbvias

- **Revisão em vez de expiração por tempo** (escolha do usuário).
  Custo medido de um cache hit do `st.cache_data`: 1,9 ms com 5 mil
  linhas, 2,9 ms com 8 mil e 10,8 ms com 15 mil, mais ~0,4 ms do
  fingerprint, vezes 2 comparativos por rerun da aba Produtos. Nenhum
  request. A alternativa (o memo expirar após o TTL do período) teria
  custo zero, mas atraso de até 2× o TTL.

- **`_revisao_frame` importada de `kpis/gerais.py`**, embora privada.
  Preferi isso a duplicar a função: é a mesma impressão digital, com os
  mesmos trade-offs documentados lá.

- **A falha deixou de ficar congelada.** Antes, o frame vazio da falha
  era memoizado sob a chave de escopo e a curva sumia até "Atualizar
  Dados". Agora o próximo rerun tenta de novo, como já acontece com o
  mês atual no `app.py`. Durante uma indisponibilidade prolongada, isso
  significa uma tentativa por rerun da aba — o mesmo que já ocorre com
  a carga principal. Na sabotagem, a revisão na chave sozinha já impede
  o congelamento; o `pop` da chave no `except` é redundância explícita.

## Verificação por sabotagem

| Sabotagem | Testes que quebram |
|---|---|
| revisão fora da chave | 2 (correção retroativa + snapshot pré-RLS) |
| revisão fora + falha memoizada | 3 |

Suíte: 1.106 → 1.111, ruff limpo.

## Pendências / follow-ups

- [ ] **Dia 1º (data-layer, decisão do usuário: só registrar).** No dia
      1º, o mês recém-fechado passa de `_consolidar_atual` (TTL 30min)
      para `_consolidar_historico` (TTL 24h). Se for carregado antes de
      o ETL trazer os pagamentos do último dia (o consolidado fecha no
      dia anterior), fica sem eles por até 24h — em **qualquer** tela
      desse mês, não só no comparativo. Esta correção não resolve isso.
      Decidir com o horário real do ETL; tratar o mês anterior como
      "atual" nos primeiros dias custa mais requests no Nano.
- [ ] **`_diag_pontuacao` sobrescrito pelo comparativo.**
      `consolidar_dados` grava o diagnóstico na sessão como efeito
      colateral, então carregar o mês anterior sobrescreve o do mês
      atual. Hoje não aparece porque o `app.py` regrava antes de ler,
      mas só quando o diagnóstico do mês atual não é vazio; nesse caso,
      o admin veria o diagnóstico do mês anterior.
