---
name: mgcred-dashboard
description: Use em qualquer trabalho em app.py ou componentes do dashboard. Router para os docs autoritativos em docs/agents/.
---

# MGCred Dashboard — Router

Padrões específicos deste projeto vivem em `docs/agents/`. Este arquivo
apenas indica onde procurar.

## Princípios inegociáveis (resumo)

1. **Entrypoint único**: `app.py` (root). `dashboard*.py` são obsoletos.
2. **RLS antes de render**: `aplicar_rls` → `aplicar_rls_metas` → `aplicar_rls_supervisores`.
3. **Cache dual**: `carregar_*` → branch `_atual`/`_historico` via `_eh_mes_atual()`.
4. **Width API**: `width="stretch"` em Streamlit ≥ 1.35 (exceto `sac.*`).
5. **Dias úteis**: sempre `from src.shared.dias_uteis import calcular_dias_uteis`.

## Onde procurar

| Tópico | Doc |
|---|---|
| Árvore de arquivos, entrypoint, banco | `docs/agents/architecture.md` |
| Pontuação, cartão, seguros, super conta, pipeline, metas | `docs/agents/business-rules.md` |
| Supabase views/RPCs, paginação, cache `_atual`/`_historico`, TTLs | `docs/agents/data-layer.md` |
| Ordem de RLS, hierarquia de 5 perfis, "Visualizar Como" | `docs/agents/rls.md` |
| Naming, formatters PT-BR, Width API, chart template, `CHART_COLORS` | `docs/agents/conventions.md` |
| `sac.divider`/`tabs`/`segmented`, `exibir_tabela`, tab renderer | `docs/agents/ui-components.md` |

## Fluxo recomendado

1. Leia `AGENTS.md` e `docs/agents/README.md` (primeira sessão).
2. Para a tarefa: abra o doc específico da tabela acima.
3. Se a tarefa introduz padrão novo, documente em `docs/agents/patterns/`.
4. Ao fechar tarefa com decisão não óbvia, registre em `docs/agents/progress/`.
