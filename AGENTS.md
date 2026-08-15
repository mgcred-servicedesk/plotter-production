# AGENTS.md — Regras gerais para agentes de IA

Este arquivo define regras de trabalho para qualquer agente de IA
(Claude Code, Windsurf, Cursor, Cody etc.) neste repositório.

Todo conhecimento de projeto (arquitetura, regras de negócio,
convenções e componentes de UI) mora em
[`docs/agents/`](docs/agents/README.md).

## Antes de qualquer mudança — leia

1. [`docs/agents/README.md`](docs/agents/README.md) — índice e princípios inegociáveis.
2. [`docs/agents/architecture.md`](docs/agents/architecture.md) — entrypoint, árvore, banco.
3. [`docs/agents/business-rules.md`](docs/agents/business-rules.md) — regras de negócio.
4. Documento específico da área tocada:
   - Supabase/cache: [`docs/agents/data-layer.md`](docs/agents/data-layer.md)
   - RLS/perfis: [`docs/agents/rls.md`](docs/agents/rls.md)
   - Convenções: [`docs/agents/conventions.md`](docs/agents/conventions.md)
   - UI components: [`docs/agents/ui-components.md`](docs/agents/ui-components.md)

Coordenação (tarefas não triviais):

- Colaboração Codex/Claude/Devin: [`docs/agents/collaboration.md`](docs/agents/collaboration.md)
- Orquestração: [`docs/agents/orchestrator.md`](docs/agents/orchestrator.md)
- Catálogo de subagentes: [`docs/agents/subagents/README.md`](docs/agents/subagents/README.md)
- Protocolo RPI obrigatório: [`docs/agents/rpi-workflow.md`](docs/agents/rpi-workflow.md)

## Princípios inegociáveis

1. **Entrypoint único**: `app.py` (root). Arquivos `dashboard*.py` são obsoletos — não adicionar features.
2. **RLS antes de render**: `aplicar_rls` → `aplicar_rls_metas` → `aplicar_rls_supervisores`, nunca depois de filtros.
3. **Cache dual**: toda função `carregar_*` faz branch `_atual`/`_historico` via `_eh_mes_atual()`.
4. **Width API**: `width="stretch"` em `st.plotly_chart`/`st.dataframe`/`st.button`. `use_container_width=True` é deprecated em Streamlit ≥ 1.35 (exceto `sac.*`).
5. **Dias úteis**: sempre `from src.shared.dias_uteis import calcular_dias_uteis`. Nunca inline.

---

## Orquestração e delegação a subagentes

O desenvolvimento opera em dois canais coordenados: Claude é o caminho
principal de execução/orquestração e Devin atua em paralelo no dashboard
quando estiver disponível. Codex revisa decisões dos dois canais. Na ausência
de Devin, Claude cobre suas subtarefas por meio dos subagentes especializados;
a entrega não fica bloqueada. Papéis, handoff e regra de continuidade em
[`docs/agents/collaboration.md`](docs/agents/collaboration.md).

Tarefas **não triviais** podem ser decompostas e delegadas a
subagentes especializados. Protocolo canônico (tool-neutral) em
[`docs/agents/orchestrator.md`](docs/agents/orchestrator.md); catálogo e
ativação em [`docs/agents/subagents/README.md`](docs/agents/subagents/README.md).

Acione o orquestrador quando a tarefa atender a pelo menos um critério:

- toca **mais de 3 módulos/arquivos**;
- **cruza domínios** (data layer + regras de negócio + UI, etc.);
- impacta princípio inegociável deste arquivo;
- tem escopo ambíguo, requisitos implícitos ou investigação com
  múltiplas hipóteses.

Regras:

- Um subagente por domínio por subtarefa.
- Cada subagente segue RPI e lê os docs do domínio.
- Se detectar domínio cruzado, parar e sinalizar bloqueio para
  reescalar ao orquestrador.
- As mesmas regras de confirmação dos tiers de decisão valem para
  qualquer delegação.

---

## Antes de codar

- Exponha sua compreensão da tarefa antes de escrever código.
- Confirme o plano com o usuário antes de começar.
- Se faltar informação, liste perguntas em aberto — nunca inferir
  requisitos.
- Apresente opções e trade-offs quando houver mais de uma abordagem.
- Identifique quais arquivos/módulos a mudança toca antes de propor.

## Durante a implementação

- **Nunca instale novos pacotes sem pedir antes.**
- Prefira editar código existente a criar novas abstrações.
- Em refatoração, mude **apenas** o que a tarefa pede.
- Não introduza padrões novos (não presentes no codebase) sem sinalizar.
- Siga convenções existentes sem perguntar; se não existir convenção,
  documente a escolha depois.
- Tratamento de erros: siga padrão existente. Sem padrão e impacto
  localizado, use o idiomático da linguagem e documente. Alto impacto,
  pare e discuta.
- **Nunca engula erros silenciosamente.**

### Exclusão de código

- Nunca apague ou deprecie código unilateralmente.
- Se algo parecer não usado, sinalize: o que é, por que parece
  desnecessário e consequência de remover.
- Aguarde confirmação explícita antes de remover.

### Migrations (Supabase)

- Migration já aplicada no Supabase é **imutável** — nunca editar
  in-place.
- Para alterar objeto existente, criar nova migration numerada com
  `CREATE OR REPLACE` em `database/migrations/`.

## Após codar

- Rode lint e type check configurados no projeto e corrija erros
  introduzidos pela mudança.
- Resuma decisões tomadas, alternativas descartadas e por quê.
- Liste premissas explicitamente para validação do usuário.
- Registre decisões não óbvias em
  [`docs/agents/progress/`](docs/agents/progress/) (append-only).
- Peça ao usuário para atualizar o contexto do projeto ao fechar a
  tarefa.

## Tiers de decisão

| Ação | Regra |
|---|---|
| Seguir padrões existentes, corrigir próprios erros | Fazer sempre — sem confirmação |
| Novos arquivos com decisão estrutural, novas dependências, tratamento de erro sem padrão | Perguntar primeiro |
| Apagar/deprecar código, criar arquivos de config/infra, alterar APIs públicas, logar credenciais | Nunca sem instrução explícita |

- Decisões de impacto duradouro pertencem ao usuário.
- Velocidade nunca é motivo para pular confirmação.
- Se uma instrução introduz risco ou débito, explicitar uma vez;
  depois seguir o que o usuário decidir, salvo problema irreversível.

## Rodando o projeto

Sempre use os binários do `.venv`.

```bash
# Dashboard (entrypoint único — Supabase direto)
.venv/bin/streamlit run app.py
```

## Testes e lint

```bash
.venv/bin/python -m pytest tests/
.venv/bin/python -m pytest tests/test_kpis_gerais.py
.venv/bin/python -m pytest tests/test_kpis_gerais.py::TestCalcularKpisGerais
.venv/bin/ruff check src/ app.py
```

## Como contribuir com a base de conhecimento

- **Descobriu/decidiu como fazer X?** Copie
  [`docs/agents/patterns/TEMPLATE.md`](docs/agents/patterns/TEMPLATE.md)
  e crie `docs/agents/patterns/<slug>.md`.
- **Fechou uma tarefa com decisão não óbvia?** Copie
  [`docs/agents/progress/TEMPLATE.md`](docs/agents/progress/TEMPLATE.md)
  e crie `docs/agents/progress/AAAA-MM-DD-<slug>.md`.
  Append-only — nunca edite entradas anteriores.
- **Encontrou divergência entre doc e código?** Corrija o doc (ou abra
  follow-up no `progress/`). O código é a verdade; o doc deve acompanhar.

## Regras comportamentais por ferramenta

Regras adicionais específicas de cada ferramenta continuam válidas, mas
não devem duplicar conhecimento de projeto:

- Claude Code: [`CLAUDE.md`](CLAUDE.md)
- Devin: [`.devin/rules/`](.devin/rules/) e [`.devin/skills/`](.devin/skills/)
- (adicione outras conforme introduzidas)
