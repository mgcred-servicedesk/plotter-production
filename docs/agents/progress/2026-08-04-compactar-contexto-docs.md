# 2026-08-04 — Compactação pontual da documentação de agentes

**Agente:** Claude Code
**Tipo:** docs
**Arquivos tocados:** `CLAUDE.md`
**Commit(s):** (não commitado ainda)

## Objetivo

Usuário pediu para inventariar a documentação (`docs/agents/` +
`AGENTS.md`/`CLAUDE.md`) e avaliar oportunidades de compactar o
"contexto geral" lido por agentes de IA.

## O que foi feito

- Inventário: `CLAUDE.md` (sempre carregado, 147L) → `AGENTS.md` (38L)
  → `docs/agents/README.md` (66L) → docs de domínio (306 a 114 linhas
  cada) → `orchestrator.md`/`rpi-workflow.md`/`subagents/README.md`
  (coordenação, só p/ tarefa não trivial) → `patterns/` (vazio, só
  `TEMPLATE.md`) → `progress/` (60 arquivos, 5.004 linhas, append-only,
  **não** lido por inteiro por nenhuma instrução — não conta como
  "contexto geral" ativo).
- Achadas 2 duplicações candidatas a link único:
  1. Lista de "Princípios inegociáveis" repetida em `AGENTS.md` /
     `docs/agents/README.md` / `.devin/skills/mgcred-dashboard/SKILL.md`.
  2. Tabela domínio → `subagent_type` repetida em `CLAUDE.md` (cópia
     extra do catálogo que já vive, por design, em
     `docs/agents/subagents/README.md`).
- **Aplicado só #2** (`CLAUDE.md`): tabela substituída por link ao
  catálogo canônico. `ruff check` n/a (doc), suíte de testes rodada
  como sanity check (373 passed, sem relação com a mudança).
- **#1 não aplicado** — ver decisão abaixo.

## Decisões não óbvias

- **Duplicação dos "Princípios inegociáveis" é INTENCIONAL**, já
  documentada em
  [2026-04-20-reorganizacao-docs-agentes.md](2026-04-20-reorganizacao-docs-agentes.md):
  "são 5 itens curtos e críticos; queremos que o agente veja **antes**
  de qualquer mudança independente de qual entry point abriu" (Claude
  Code abre `AGENTS.md` primeiro; Devin abre
  `mgcred-dashboard/SKILL.md`; outra ferramenta pode abrir
  `docs/agents/README.md` direto). Cheguei a aplicar um link único em
  `AGENTS.md` antes de encontrar esse registro; revertido a pedido do
  usuário para não contrariar a decisão de 2026-04-20. **Não mexer
  nessa duplicação de novo sem reabrir a discussão com o usuário.**
- **Tabela de subagentes em `CLAUDE.md` não tinha o mesmo respaldo** —
  o sistema de subagentes é posterior à reorganização de 04-20 (não
  existia RPI/orquestrador/catálogo naquela época), então não há
  decisão registrada tornando aquela cópia intencional. Compactada sem
  ressalva.
- **`progress/` não precisa de poda** — é append-only por design e
  nada instrui lê-lo por inteiro; só é referenciado por link pontual
  (ex.: `business-rules.md` → `consultor-id-vs-nome-riscos.md`). Não é
  o alvo certo para "compactar contexto geral".
- **`patterns/` está vazio mas isso não é necessariamente um problema
  agora** — os temas mais recorrentes do `progress/` (cards ×7, RLS
  ×6, gestão ×4, cancelados ×4) já foram absorvidos manualmente nos
  docs centrais (`business-rules.md`, `rls.md`, `ui-components.md`).
  O mecanismo declarado em `AGENTS.md` nunca rodou, mas o gap prático
  é menor do que parece à primeira vista. Fica como observação, não
  como ação tomada.

## Pendências / follow-ups

- [ ] Nenhuma ação pendente desta sessão. Se o usuário quiser revisitar
  a duplicação dos princípios inegociáveis (ex.: trocar por outra
  estratégia de compactação que preserve a visibilidade em cada entry
  point), reabrir como nova decisão — não just reverter unilateralmente.

## Referências

- Docs consultados: [docs/agents/README.md](../README.md),
  [progress/2026-04-20-reorganizacao-docs-agentes.md](2026-04-20-reorganizacao-docs-agentes.md)
