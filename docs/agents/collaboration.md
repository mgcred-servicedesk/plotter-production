# Colaboração entre Codex, Claude e Devin

Este documento define o contrato canônico de coordenação entre os agentes
que desenvolvem o dashboard. As regras de projeto continuam nos demais
documentos de `docs/agents/`; os entrypoints de cada ferramenta apenas
explicam como executar este contrato.

## Papéis

| Participante | Responsabilidade |
|---|---|
| **Codex — revisão de decisões** | Revisa escopo, trade-offs, riscos, aderência aos princípios inegociáveis, coerência doc × código e critérios de aceite. Não é o canal primário de implementação. |
| **Claude — execução e orquestração** | Conduz RPI, decompõe tarefas, implementa e aciona os subagentes por domínio. Garante a continuidade quando Devin não estiver trabalhando. |
| **Devin — desenvolvimento do dashboard** | Atua em paralelo quando disponível e designado, com foco em Streamlit, UI/UX, visualizações, responsividade, performance percebida, QA visual e smoke tests. |
| **Subagentes do Claude** | Executam subtarefas atômicas de `ui-dash`, `testing`, `biz-rules`, `data-layer` e `dba`, inclusive as que caberiam ao Devin quando ele estiver ausente. |

Responsabilidade primária não cria uma segunda fonte de verdade nem
autoriza um agente a atravessar domínios sem replanejamento.

## Dois canais de desenvolvimento

1. **Canal Claude:** sempre disponível como caminho principal. Claude
   orquestra a entrega e distribui cada subtarefa ao especialista adequado.
2. **Canal Devin:** caminho paralelo para trabalho de dashboard quando Devin
   estiver ativo e receber uma subtarefa com escopo e aceite definidos.

Codex revisa decisões dos dois canais. A revisão é obrigatória para decisões
duradouras, tarefas cross-domínio e mudanças que toquem princípios
inegociáveis; ajustes triviais seguem o fluxo TRIVIAL do RPI.

## Regra de continuidade

A ausência de Devin **nunca bloqueia** a entrega. Nesse caso, Claude:

1. mantém a orquestração da tarefa;
2. decompõe o trabalho que iria para Devin em subtarefas atômicas;
3. delega pelo catálogo de `subagents/README.md`, normalmente `ui-dash` e
   `testing`, acrescentando `biz-rules`, `data-layer` ou `dba` conforme o
   domínio;
4. preserva as mesmas aprovações, critérios de aceite e revisão de Codex.

Claude não entrega uma subtarefa multidomínio inteira a um único subagente
para simular o papel de Devin.

## Fluxo e handoff

```text
Requisito
  → Research e decisões revisadas por Codex
  → Claude orquestra e define o responsável primário
      ├─ Devin ativo: executa a subtarefa de dashboard
      └─ Devin ausente: subagentes do Claude cobrem os domínios
  → revisão cruzada, testes e QA
  → registro append-only em progress/
```

Todo handoff deve informar objetivo, arquivos, critérios de aceite,
dependências, decisões já aprovadas e testes esperados. Dois agentes não
editam simultaneamente os mesmos arquivos. Se surgir domínio adicional, o
executor para e devolve o bloqueio ao orquestrador.

## Fonte de verdade e encerramento

- Conhecimento de projeto: `docs/agents/`.
- Mecânica do Claude: `CLAUDE.md` e catálogo de subagentes.
- Mecânica do Devin: `.devin/rules/` e `.devin/skills/`.
- Decisões não óbvias e handoffs duradouros: `docs/agents/progress/`.
- Divergência doc × código: o código é a verdade; corrigir o documento
  canônico ou registrar follow-up.

Uma tarefa não trivial só encerra depois da revisão das decisões, dos testes
do domínio e do QA proporcional ao risco visual/operacional.
