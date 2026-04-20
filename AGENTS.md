# AGENTS.md — Ponto de entrada para agentes de IA

Arquivo lido por qualquer agente de IA (Claude Code, Windsurf, Cursor,
Cody, etc.) que trabalhe neste projeto. **Curto por design** — todo
conhecimento de projeto mora em [`docs/agents/`](docs/agents/README.md).

## Leia antes de qualquer mudança

1. [`docs/agents/README.md`](docs/agents/README.md) — índice e princípios inegociáveis.
2. [`docs/agents/architecture.md`](docs/agents/architecture.md) — entrypoint, árvore, banco.
3. [`docs/agents/business-rules.md`](docs/agents/business-rules.md) — regras de negócio.

Demais referências (cache, RLS, convenções, UI) estão linkadas no README.

## Princípios inegociáveis

1. **Entrypoint único**: `app.py` (root). Arquivos `dashboard*.py` são obsoletos — não adicionar features.
2. **RLS antes de render**: `aplicar_rls` → `aplicar_rls_metas` → `aplicar_rls_supervisores`, nunca depois de filtros.
3. **Cache dual**: toda função `carregar_*` faz branch `_atual`/`_historico` via `_eh_mes_atual()`.
4. **Width API**: `width="stretch"` em `st.plotly_chart`/`st.dataframe`/`st.button`. `use_container_width=True` é deprecated em Streamlit ≥ 1.35 (exceto `sac.*`).
5. **Dias úteis**: sempre `from src.shared.dias_uteis import calcular_dias_uteis`. Nunca inline.

## Como contribuir com a base de conhecimento

- **Descobriu/decidiu como fazer X?** Copie [`docs/agents/patterns/TEMPLATE.md`](docs/agents/patterns/TEMPLATE.md) e crie `docs/agents/patterns/<slug>.md`.
- **Fechou uma tarefa com decisão não óbvia?** Copie [`docs/agents/progress/TEMPLATE.md`](docs/agents/progress/TEMPLATE.md) e crie `docs/agents/progress/AAAA-MM-DD-<slug>.md`. Append-only — nunca edite entradas anteriores.
- **Encontrou divergência entre doc e código?** Corrija o doc (ou abra follow-up no `progress/`). O código é a verdade; o doc deve acompanhar.

## Regras comportamentais por ferramenta

Cada agente segue regras adicionais específicas da sua ferramenta:

- Claude Code: [`CLAUDE.md`](CLAUDE.md)
- Windsurf: [`.windsurf/rules/`](.windsurf/rules/) e [`.windsurf/skills/`](.windsurf/skills/)
- (adicione outros conforme forem introduzidos)

Essas regras **não devem duplicar** conhecimento de projeto — apenas
orientar comportamento (quando perguntar, como decidir, decision tiers).
