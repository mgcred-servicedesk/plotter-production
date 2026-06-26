# 2026-06-26 — Drill-down dos cards oculto para supervisor/consultor + ajustes na série diária

**Agente:** Devin
**Tipo:** feature / bugfix
**Arquivos tocados:** `src/dashboard/permissions.py`,
`src/dashboard/ui/kpi_cards_reforma.py`, `app.py`,
`src/dashboard/pages/detalhes_cards.py`
**Commit(s):** (ainda não commitado)

## Objetivo

1. Remover os botões de detalhe (drill-down) dos cards de contexto para os
   perfis **Supervisor** e **Consultor** — esses perfis não acessam as
   páginas de detalhe.
2. Ajustar o quadro "Últimos 7 Dias (Digitação)": ordenar do dia mais
   recente para o mais antigo e renomear o título.

## O que foi feito

- **Nova chave de permissão `cards_drilldown`** em `permissions.py`
  (admin/gestor/gerente_comercial = `True`; supervisor/consultor = `False`).
- `render_kpis_reforma` faz `return` antes da fileira de botões 🔍 quando
  `pode_ver("cards_drilldown", perfil)` é falso. Os cards-resumo
  gerenciais continuam visíveis para esses perfis.
- `app.py`: a promoção do query param `?card=` passou a exigir
  `cards_drilldown` (antes era `cards_gerenciais`), fechando o roteamento
  para param forjado por supervisor/consultor (defesa em profundidade).
- Docstring de `pages/detalhes_cards.py` atualizado para refletir o novo gate.
- Série "Últimos 7 Dias": ordenação invertida (mais recente no topo) e
  título alterado para **"Digitação — Últimos 7 Dias"**.

## Decisões não óbvias

- **Chave nova `cards_drilldown` em vez de reaproveitar `cards_gerenciais`** —
  `cards_gerenciais` é intencionalmente `True` para supervisor/consultor
  (eles veem os cards-resumo) e também porteia a página de Pontuação;
  repurposá-la teria efeitos colaterais indesejados. Só os **botões** e o
  **roteamento do drill-down** migraram para a chave nova.
- **Gate em duas camadas (UI + roteamento)** — ocultar o botão não basta:
  o código já tratava `?card=` forjado como fail-closed, então o gate do
  query param também foi movido para `cards_drilldown`.
- **Inversão da série é só de exibição** — o `Var. %` continua calculado vs.
  o dia anterior (ascendente) antes do `iloc[::-1]`, então os percentuais
  permanecem corretos com o dia mais recente no topo.

## Pendências / follow-ups

- [ ] Commit das mudanças (a pedido do usuário, ainda não feito).

## Referências

- Docs consultados: [docs/agents/rls.md](../rls.md),
  [docs/agents/ui-components.md](../ui-components.md)
- Sessão anterior relacionada:
  [progress/2026-06-26-digitacao-detalhe-paginacao.md](2026-06-26-digitacao-detalhe-paginacao.md)
