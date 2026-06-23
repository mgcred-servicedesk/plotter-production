# Subagentes — Índice e Protocolo de Ativação

Cada subagente é um contexto especializado responsável por **um único
domínio**. O orquestrador ([`orchestrator.md`](../orchestrator.md)) aloca
subagentes por subtarefa. Documento **tool-neutral**: vale para Claude Code,
Windsurf e qualquer outro harness.

> Princípio: subagentes **não redefinem** conhecimento de projeto. Toda
> regra de negócio, convenção e arquitetura mora em `docs/agents/*.md`.
> Os arquivos de harness (`.claude/agents/*.md`, `.windsurf/skills/*`)
> são apenas o **invólucro de ativação** de cada ferramenta — eles linkam
> para os docs, nunca os duplicam.

---

## Catálogo de subagentes

| Slug | Harness Claude (`.claude/agents/`) | Domínio | Lê (`docs/agents/`) |
|------|------------------------------------|---------|---------------------|
| `testing` | `test-automation-specialist.md` | Testes pytest, fixtures, cobertura | `architecture.md`, `business-rules.md`, `conventions.md` |
| `ui-dash` | `streamlit-ui-specialist.md` | Streamlit UI, componentes, estilos | `ui-components.md`, `conventions.md`, `rls.md` |
| `biz-rules` | `business-rules-kpi-expert.md` | Regras de negócio, KPIs, pontuação | `business-rules.md`, `data-layer.md` |
| `data-layer` | `data-layer-supabase.md` | Supabase access, views, RPCs, cache | `data-layer.md`, `architecture.md` |
| `dba` | `supabase-schema-rls.md` | Migrações Supabase, schema, RLS | `rls.md`, `data-layer.md` |

O orquestrador (`task-orchestrator`) **não** consta no catálogo de domínio:
ele decompõe e delega, nunca executa nem delega para si mesmo. Ver
[`orchestrator.md`](../orchestrator.md).

---

## Protocolo de ativação

### Claude Code — subagente real via `Task` tool

No Claude Code, a definição do subagente (`.claude/agents/<nome>.md`) já é
carregada automaticamente como system prompt ao instanciar via `Task` tool
com `subagent_type: <nome>`. Portanto o orquestrador passa **apenas** a
subtarefa e os critérios de aceitação — não precisa pedir ao subagente que
"leia sua própria definição". O subagente, por sua vez, segue o RPI e lê os
docs listados em "Lê" do seu domínio.

Prompt que o orquestrador passa ao instanciar cada subagente:

```
Subtarefa [ST-NN]: [DESCRIÇÃO]

Contexto de handoff (se houver): [link p/ entry em docs/agents/progress/]

Critérios de aceitação:
  - [AC-1]
  - [AC-2]

Execute o protocolo RPI completo (docs/agents/rpi-workflow.md).
Aguarde aprovação do usuário entre as fases RESEARCH → PLAN → IMPLEMENT.
Se detectar domínio cruzado, pare e emita o bloco BLOQUEIO (ver abaixo).
```

`subagent_type` por slug:

| Slug | `subagent_type` |
|------|-----------------|
| `testing` | `test-automation-specialist` |
| `ui-dash` | `streamlit-ui-specialist` |
| `biz-rules` | `business-rules-kpi-expert` |
| `data-layer` | `data-layer-supabase` |
| `dba` | `supabase-schema-rls` |

### Windsurf — skill por domínio

Cada subagente tem uma skill correspondente em `.windsurf/skills/`:

| Slug | Skill path |
|------|-----------|
| `testing` | `.windsurf/skills/testing/SKILL.md` |
| `ui-dash` | `.windsurf/skills/streamlit-dashboards/SKILL.md` (já existente) |
| `biz-rules` | `.windsurf/skills/biz-rules/SKILL.md` |
| `data-layer` | `.windsurf/skills/data-layer/SKILL.md` |
| `dba` | `.windsurf/skills/dba/SKILL.md` |

Ativação manual no Windsurf: o usuário inclui a skill na sessão antes de
passar a subtarefa. O subagente então segue o protocolo RPI sequencialmente.

---

## Regras de composição

- **Um subagente por domínio por subtarefa.** Se a tarefa cruza domínios,
  o orquestrador decompõe em subtarefas menores antes de delegar.

- **Handoff entre subagentes.** Quando ST-02 depende de ST-01: o subagente
  de ST-01 registra seu output em `docs/agents/progress/` antes de encerrar.
  O subagente de ST-02 lê esse entry como contexto inicial (passado pelo
  orquestrador no campo "Contexto de handoff").

- **Conflito de domínio.** Se durante a execução o subagente perceber que
  precisa tocar outro domínio, para e escala ao orquestrador:

  ```
  BLOQUEIO — domínio cruzado detectado
  Subtarefa: [ST-NN]
  Domínio extra: [qual]
  Razão: [o que foi encontrado]
  Sugestão: [novo slug a acionar, se claro]
  ```

- **Nunca duplicar conhecimento de projeto.** Subagentes não redefinem
  regras de negócio nem convenções — linkam para `docs/agents/*.md`.

---

## Referências

- [`orchestrator.md`](../orchestrator.md) — protocolo de orquestração.
- [`rpi-workflow.md`](../rpi-workflow.md) — protocolo RPI obrigatório.
- [`README.md`](../README.md) — índice geral dos docs de agentes.
