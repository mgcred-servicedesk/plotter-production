# CLAUDE.md — Regras de comportamento (Claude Code)

Este arquivo contém **apenas** regras de comportamento específicas do
Claude Code. Todo conhecimento de projeto (arquitetura, regras de
negócio, padrões, convenções) mora em [`docs/agents/`](docs/agents/README.md).

## Antes de qualquer mudança — leia

1. [`AGENTS.md`](AGENTS.md) — ponto de entrada canônico (princípios inegociáveis).
2. [`docs/agents/README.md`](docs/agents/README.md) — índice completo.
3. O documento específico para a área que você vai tocar:
   - Arquitetura: [`docs/agents/architecture.md`](docs/agents/architecture.md)
   - Regras de negócio: [`docs/agents/business-rules.md`](docs/agents/business-rules.md)
   - Supabase / cache: [`docs/agents/data-layer.md`](docs/agents/data-layer.md)
   - RLS / perfis: [`docs/agents/rls.md`](docs/agents/rls.md)
   - Convenções (naming, formatters, Width API, cores): [`docs/agents/conventions.md`](docs/agents/conventions.md)
   - Componentes de UI (sac, exibir_tabela, tab renderer): [`docs/agents/ui-components.md`](docs/agents/ui-components.md)

Coordenação (quando a tarefa for não trivial):
   - Colaboração Codex/Claude/Devin: [`docs/agents/collaboration.md`](docs/agents/collaboration.md)
   - Orquestração: [`docs/agents/orchestrator.md`](docs/agents/orchestrator.md)
   - Catálogo de subagentes: [`docs/agents/subagents/README.md`](docs/agents/subagents/README.md)
   - Protocolo RPI obrigatório: [`docs/agents/rpi-workflow.md`](docs/agents/rpi-workflow.md)

---

## Orquestração e delegação a subagentes

Claude é o canal principal de execução e orquestração. Devin pode receber
subtarefas de dashboard em paralelo quando estiver trabalhando; Codex revisa
as decisões duradouras e cross-domínio. Se Devin estiver ausente, **não
aguarde nem bloqueie a tarefa**: decomponha o escopo e acione os subagentes
do catálogo (`ui-dash`, `testing`, `biz-rules`, `data-layer`, `dba`) conforme
cada domínio. O contrato completo de disponibilidade, handoff e revisão está
em [`docs/agents/collaboration.md`](docs/agents/collaboration.md).

Tarefas **não triviais** podem ser decompostas e delegadas a subagentes
especializados. Protocolo canônico (tool-neutral) em
[`docs/agents/orchestrator.md`](docs/agents/orchestrator.md); catálogo e
ativação em [`docs/agents/subagents/README.md`](docs/agents/subagents/README.md).

**Acione o `task-orchestrator`** (via Agent/Task tool) quando a tarefa atender
a pelo menos um critério:

- toca **mais de 3 módulos/arquivos**;
- **cruza domínios** (data layer + regras de negócio + UI, etc.);
- impacta princípio inegociável (`AGENTS.md`);
- tem escopo ambíguo, requisitos implícitos ou investigação com múltiplas hipóteses.

O orquestrador **nunca escreve código**: entrega um plano de subtarefas e, após
sua aprovação, delega cada uma ao subagente do domínio. Tarefa trivial (uma
linha, ajuste de texto, correção óbvia de domínio único) **não** passa pelo
orquestrador — vai direto ao subagente ou é feita inline.

**Subagentes especializados** (`subagent_type` no Agent/Task tool): catálogo
completo (domínio → `subagent_type`) em
[`docs/agents/subagents/README.md`](docs/agents/subagents/README.md).

Regras: **um subagente por domínio por subtarefa**; cada um segue o RPI
([`docs/agents/rpi-workflow.md`](docs/agents/rpi-workflow.md)) e lê os docs do
seu domínio; ao detectar domínio cruzado, **para** e emite o bloco `BLOQUEIO`
para reescalar ao orquestrador. As mesmas regras de confirmação dos *tiers de
decisão* (abaixo) valem para qualquer subagente antes de delegar itens de
"perguntar primeiro" / "nunca sem instrução".

---

## Antes de codar

- Exponha sua compreensão da tarefa antes de escrever código.
- Confirme o plano com o usuário antes de começar.
- Se faltar informação, liste perguntas em aberto — nunca inferir requisitos.
- Apresente opções e trade-offs quando houver mais de uma abordagem.
- Identifique quais arquivos/módulos a mudança toca antes de propor.

## Durante a implementação

- **Nunca instale novos pacotes sem pedir antes.**
- Prefira editar código existente a criar novas abstrações.
- Em refatoração, mude **apenas** o que a tarefa pede — sem limpezas não relacionadas.
- Não introduza padrões novos (não presentes no codebase) sem sinalizar.
- Siga convenções existentes sem perguntar; documente a escolha depois se não existir convenção.
- Tratamento de erros: siga padrão existente. Se não houver e impacto for baixo, use idioma da linguagem e documente. Alto impacto → pare e discuta.
- **Nunca engula erros silenciosamente.**

### Exclusão de código

- Nunca apague ou deprecie código unilateralmente.
- Se parecer não usado, **sinalize**: descreva o que é, por que parece desnecessário, consequência de remover.
- Aguarde confirmação explícita antes de remover.

### Migrations (Supabase)

- Migration já aplicada no Supabase é **imutável** — nunca edite in-place.
- Para alterar um objeto existente, crie uma nova migration numerada com
  `CREATE OR REPLACE` (numeração sequencial em `database/migrations/`).

## Após codar

- Rode `ruff check` e corrija erros que você introduziu.
- Resuma decisões tomadas, alternativas descartadas e por quê.
- Liste premissas explicitamente para o usuário validar.
- Registre decisões não óbvias em [`docs/agents/progress/`](docs/agents/progress/) (use o template).
- Peça ao usuário para atualizar contexto do projeto quando a tarefa fechar.

## Tiers de decisão

| Ação | Regra |
|---|---|
| Seguir padrões existentes, corrigir próprios erros | Fazer sempre — sem confirmação |
| Novos arquivos com decisão estrutural, novas dependências, tratamento de erro sem padrão | Perguntar primeiro |
| Apagar/deprecar código, criar arquivos de config/infra, alterar APIs públicas, logar credenciais | Nunca sem instrução explícita |

- Todas as decisões de impacto duradouro pertencem ao usuário.
- Velocidade nunca é motivo para pular confirmação.
- Se uma instrução introduz risco ou débito, diga claramente uma vez — depois siga o que o usuário decidir, salvo problema irreversível.

## Contribuição à base de conhecimento

Quando descobrir/decidir algo não óbvio, contribua de volta:

- **Padrão reutilizável?** Copie [`docs/agents/patterns/TEMPLATE.md`](docs/agents/patterns/TEMPLATE.md) e crie `docs/agents/patterns/<slug>.md`.
- **Decisão não óbvia no fim da sessão?** Anexe entrada em [`docs/agents/progress/`](docs/agents/progress/) (append-only — nunca edite entradas anteriores).
- **Divergência doc × código?** O código é a verdade. Corrija o doc ou abra follow-up no `progress/`.

## Rodando o projeto

> Sempre use os binários do `.venv` — nunca o Python/ruff do sistema.

```bash
# Dashboard (entrypoint único — Supabase direto)
.venv/bin/streamlit run app.py
```

> O pipeline de relatórios Excel/PDF (`gerar_relatorio*.py`, `src/reports/`,
> `src/data_processing/`) foi removido — o `app.py` consome o Supabase
> diretamente e é a única superfície do projeto.

## Testes e lint

```bash
.venv/bin/python -m pytest tests/                                  # suíte completa
.venv/bin/python -m pytest tests/test_kpis_gerais.py               # um arquivo
.venv/bin/python -m pytest tests/test_kpis_gerais.py::TestCalcularKpisGerais  # uma classe/teste
.venv/bin/ruff check src/ app.py
```

Testes em `tests/` (`test_kpis_*.py`, um por domínio de KPI). Fixtures
compartilhadas em `tests/conftest.py`. `pytest.ini` já aplica `-v` e
`--strict-markers`; markers: `unit`, `integration`, `slow`, `data_validation`.
