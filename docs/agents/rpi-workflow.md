# RPI Workflow — Research, Plan, Implement

Protocolo obrigatório para qualquer mudança não trivial neste projeto.
Nenhum agente pode pular fases. Usuário aprova **explicitamente** entre fases.
Arquivo consumido por todos os harnesses (`CLAUDE.md`, `.windsurf/rules/`, `.devin/rules/`).

---

## Fase 1 — RESEARCH

### Responsabilidades
- Ler todos os docs de `docs/agents/` relevantes para o domínio tocado.
- Mapear **todos** os arquivos/módulos afetados — não supostos.
- Verificar testes existentes em `tests/` para o domínio.
- Listar perguntas em aberto. Nunca inferir requisitos não declarados.
- Identificar quais princípios inegociáveis (`AGENTS.md`) a tarefa toca.

### Output obrigatório (bloco literal, copiado aqui)
```
=== RESEARCH ===
Domínio: [ex: dashboard, data-layer, RLS, testes]
Docs lidos: [lista com caminho]
Arquivos impactados: [lista com razão]
Dependências identificadas: [lista]
Princípios inegociáveis tocados: [lista ou "nenhum"]
Perguntas em aberto: [lista — se vazia, justificar]
```

**Aguardar confirmação do usuário antes de prosseguir.**

---

## Fase 2 — PLAN

### Responsabilidades
- Propor abordagem técnica com trade-offs explícitos.
- Listar alternativas descartadas e por quê foram descartadas.
- Definir critérios de aceitação (AC) verificáveis e mensuráveis.
- Identificar riscos e mitigação concreta para cada risco.
- Listar todos os arquivos a criar, editar e deletar.

### Output obrigatório
```
=== PLAN ===
Abordagem escolhida: [descrição técnica]
Alternativas descartadas:
  - [alternativa A]: [razão]
  - [alternativa B]: [razão]
Critérios de aceitação:
  - [ ] [critério verificável e mensurável]
  - [ ] ...
Arquivos a criar: [lista com propósito]
Arquivos a editar: [lista com o que muda]
Arquivos a deletar: [lista — exige confirmação explícita do usuário]
Riscos:
  - [risco]: [mitigação]
```

**Aguardar aprovação explícita antes de qualquer edição de código.**

---

## Fase 3 — IMPLEMENT

### Responsabilidades
- Executar **exatamente** o plano aprovado. Sem limpezas ou refatorações extras.
- Rodar `ruff check` após cada arquivo Python editado.
- Rodar a suíte de testes afetada ao final (`.venv/bin/python -m pytest tests/`).
- Documentar decisões não óbvias tomadas durante a implementação.

### Output obrigatório ao final
```
=== IMPLEMENT SUMMARY ===
Implementado: [lista do que foi feito]
Desviou do plano: [se sim — o quê e por quê]
Ruff check: [passou | N erros corrigidos]
Testes rodados: [quais, resultado]
Decisões durante impl: [se houver]
Follow-ups: [tarefas abertas identificadas]
```

---

## Exceções: quando NÃO usar RPI completo

Para mudanças **triviais** (typo, ajuste de cor, 1 linha sem impacto lógico):
```
TRIVIAL — sem RPI completo
O que farei: [1-2 frases]
```
Aguardar confirmação se a mudança tocar qualquer lógica de negócio, RLS ou cache.

---

## Gatilho de escalada ao orquestrador

Se durante RESEARCH ou PLAN o agente identificar:
- Tarefa toca **mais de 3 módulos**
- Impacta **princípio inegociável**
- Requer **mais de um domínio simultâneo**

```
=== ESCALADA PARA ORQUESTRADOR ===
Razão: [motivo concreto]
Domínios envolvidos: [lista]
Subagentes sugeridos: [ver docs/agents/subagents/README.md]
```

Ver `docs/agents/orchestrator.md`.
