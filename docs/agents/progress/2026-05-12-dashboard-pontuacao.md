# 2026-05-12 — Dashboard de Pontuação (página dedicada)

**Agente:** Claude Code
**Tipo:** feature
**Arquivos tocados:** `app.py`, `src/dashboard/ui/header.py`, `src/dashboard/kpis/pontuacao.py` (novo), `src/dashboard/ui/kpi_cards_pontuacao.py` (novo), `src/dashboard/ui/prioridades_pontuacao.py` (novo), `src/dashboard/pages/__init__.py` (novo), `src/dashboard/pages/dashboard_pontuacao.py` (novo)
**Commit(s):** (a fechar pelo usuário)

## Objetivo

Criar uma página dedicada de **Dashboard de Pontuação** ao lado do
Dashboard de Vendas, reaproveitando o esqueleto visual mas trocando
toda a métrica primária de R$ para pontos. Toggle no header alterna
entre as duas visões; o resto do pipeline (auth, RLS, filtros, cache)
é compartilhado.

## O que foi feito

- Novo módulo `src/dashboard/kpis/pontuacao.py` com:
  - `calcular_pontos_em_analise` — soma `VALOR × PTS` em contratos em análise.
  - `calcular_pontos_cancelados` — total de pts cancelados + % perda
    (a UI exibe só % perda por escolha de produto).
  - `calcular_medias_pontos_por_nivel` — média DU em pts por loja/consultor.
  - `calcular_mix_pontos` — cards MIX: peso, meta diária derivada
    do peso × (Meta_Prata / DU_total), fatia da Prata e %
    atingimento contra essa fatia.
  - `calcular_prioridades_pontuacao` — para cada produto MIX: pts
    pagos, pts em análise, peso, e % que fecharia da Meta Prata e
    da Meta Ouro se converter.
- UI nova (`ui/kpi_cards_pontuacao.py` e `ui/prioridades_pontuacao.py`)
  espelhando visualmente a Home de Vendas (`kpi_cards_reforma.py` +
  `prioridades_acao.py`) mas operando em pontos.
- Página `pages/dashboard_pontuacao.py` orquestra cálculos +
  renderização; respeita `pode_ver("cards_gerenciais", role)`.
- `render_header` recebeu argumentos `titulo` e `subtitulo` opcionais
  (default = comportamento original) para refletir a página ativa.
- `app.py`:
  - Lê/escreve `st.session_state["dashboard_view"]` (`"vendas"` |
    `"pontuacao"`).
  - Renderiza `sac.segmented` logo abaixo do header.
  - Constrói `mapa_pontos` a partir de `df_pontos` já carregado
    (`carregar_pontuacao_efetiva`) e dispara
    `render_dashboard_pontuacao(...)` quando `view == "pontuacao"`,
    pulando os cards de vendas, resumo executivo, prioridades_acao e
    abas.

## Decisões não óbvias

- **Peso é realizado no mês corrente** (não histórico/ideal). Validação:
  o usuário confirmou que cada período tem apuração de pesos própria.
  Consequência: a meta diária por produto MIX flutua à medida que a
  composição do mês muda.
- **% atingimento por produto MIX = pontos_produto / (Meta_Prata × peso) × 100**.
  Não criamos meta de pontos por produto na tabela `metas_produto`;
  a fatia da Prata é particionada dinamicamente pelo peso realizado.
- **Cancelados em pontos não aparecem na UI** — exibimos apenas
  `% perda` (mesma quantidade do dashboard de vendas). O total em
  pts é calculado e fica disponível no dict caso seja útil depois.
- **Aceleradores continuam visíveis** na seção de prioridades
  (reuso de `render_prioridades_aceleradores` de `prioridades_acao`),
  porém em **quantidade**. Eles têm `conta_pontuacao = False` por
  categoria → não somam em `total_pontos`, `Meta Prata/Ouro`,
  projeções nem na Meta diária do MIX. Decisão consciente do
  usuário: manter contexto operacional sem interferir nas métricas
  de pontuação.
- **Tabs internas não vêm para a pontuação** nesta fase. A página de
  Pontuação é só Home (cards principais + contexto + MIX + Para Onde
  Estamos Indo + Prioridades). Possível fase 2.
- **Refatoração minimalista no `app.py`**: optei por *não* extrair o
  miolo de `main()` para `pages/dashboard_vendas.py`. Em vez disso,
  o dispatch para pontuação acontece via `if ... return` logo antes
  do bloco de cards de vendas — princípio "mudar só o que a tarefa
  pede". Reaproveita 100% do pipeline de loaders/RLS/cache existente.
- **Cache de KPIs em `session_state`** já existente é compartilhado
  pelas duas views: como `kpis_gerais` já calcula `total_pontos`,
  `meta_prata`, `meta_ouro`, `projecao_pontos`, `perc_proj`, etc, a
  página de Pontuação só precisa derivar KPIs adicionais (em análise
  e cancelados em pts, médias e MIX/prioridades), que são leves.

## Pendências / follow-ups

- [ ] (Fase 2) Tabs internas em modo pontuação — Produtos, Regiões,
      Rankings, Em Análise, Detalhes etc.
- [ ] (Fase 2) Validar comportamento com perfis Supervisor e
      Consultor após login real — testado apenas via smoke test de
      imports + DFs vazios.
- [ ] Avaliar se faz sentido um expander de "Cancelados em pontos"
      (hoje o total em pts é calculado mas não exposto na UI).

## Patterns criados ou atualizados

(nenhum padrão novo identificado — segue convenções existentes de
`kpi_cards_reforma` e `prioridades_acao`)

## Referências

- Conversa: pedido inicial — "Dashboard de Pontuação"
- Docs consultados: [docs/agents/business-rules.md](../business-rules.md)
  (regras de pontuação, `conta_pontuacao`, Meta Prata/Ouro),
  [docs/agents/architecture.md](../architecture.md) (entrypoint
  único, fluxo de carregamento, cache dual).
