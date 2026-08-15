# 2026-08-15 — Colaboração entre Codex, Claude e Devin

**Agente:** Codex
**Tipo:** docs
**Arquivos tocados:** `AGENTS.md`, `CLAUDE.md`, `docs/agents/README.md`,
`docs/agents/collaboration.md`, `.devin/rules/`, `.devin/skills/`,
`.devin/docs/novos_recursos_dashboard.md`
**Commit(s):** — (pendente)

## Objetivo

Formalizar dois canais harmônicos de desenvolvimento do dashboard, registrar
Codex como revisor de decisões e garantir que a ausência de Devin não bloqueie
o trabalho conduzido por Claude.

## O que foi feito

- Criado contrato canônico com papéis, dois canais, continuidade e handoff.
- Claude registrado como executor/orquestrador principal, capaz de cobrir o
  canal Devin por meio dos subagentes especializados.
- Devin registrado como canal paralelo focado no dashboard quando ativo.
- Codex registrado como revisor de decisões duradouras e cross-domínio.
- Entry points de Claude e Devin reduzidos a instruções operacionais que
  apontam para a mesma fonte de verdade.
- Corrigidas referências `.devin` que se apresentavam como Windsurf.
- Documento antigo de recursos do Devin marcado como histórico, sem apagar
  seu conteúdo.

## Decisões não óbvias

- **Responsabilidade primária, não exclusividade.** Devin pode executar UI e
  QA, mas sua ausência aciona `ui-dash`/`testing` e outros subagentes do Claude
  em vez de bloquear a entrega.
- **Codex revisa, não vira terceiro canal de implementação.** Isso preserva
  uma linha clara de execução e adiciona controle sobre decisões duradouras.
- **Histórico preservado.** O documento Devin de março recebeu contexto e
  links atuais; seu registro original não foi apagado.

## Pendências / follow-ups

- [ ] Validar o primeiro handoff real Claude ↔ Devin contra o contrato e
      ajustar apenas se surgir uma lacuna operacional concreta.

## Patterns criados ou atualizados

Nenhum. O contrato é governança de agentes, não padrão de implementação.

## Referências

- [Contrato de colaboração](../collaboration.md)
- [Orquestrador](../orchestrator.md)
- [Catálogo de subagentes](../subagents/README.md)
- [RPI](../rpi-workflow.md)
