# 2026-04-20 — Reorganização da documentação para agentes de IA

**Agente:** Claude Code
**Tipo:** docs / refactor
**Arquivos tocados:** `AGENTS.md`, `CLAUDE.md`, `docs/agents/*`, `.windsurf/rules/main-rules.md`, `.windsurf/skills/*/SKILL.md`
**Commit(s):** (no commit desta reorganização)

## Objetivo

Permitir que agentes de IA distintos (Claude Code, Windsurf, Cursor, etc.)
leiam a mesma referência de documentação, compartilhem progresso e
documentem como fazem determinadas coisas — sem duplicação entre
`CLAUDE.md` e `.windsurf/skills/*/SKILL.md`.

## O que foi feito

- Criada pasta canônica `docs/agents/` com 6 documentos temáticos:
  `architecture.md`, `business-rules.md`, `data-layer.md`, `rls.md`,
  `conventions.md`, `ui-components.md`, além do `README.md` (índice +
  princípios inegociáveis).
- Criadas subpastas `docs/agents/patterns/` (como fazer X) e
  `docs/agents/progress/` (log de sessões) com `TEMPLATE.md` em cada uma.
- Criado `AGENTS.md` na raiz — ponto de entrada canônico lido por
  qualquer agente.
- `CLAUDE.md` enxugado para regras **apenas comportamentais** do Claude
  Code; conhecimento de projeto remove e linka `docs/agents/*`.
- `.windsurf/rules/main-rules.md` enxugado idem.
- Os 5 `SKILL.md` do Windsurf transformados em **routers finos** que
  listam princípios inegociáveis + tabela de "onde procurar" apontando
  para `docs/agents/*`. Mantidas referências rápidas de API (Streamlit,
  Plotly, Pandas, Seaborn) — essas são genéricas e não duplicam
  conhecimento de projeto.

## Decisões não óbvias

- **`docs/agents/` em vez de `.agents/`** — convenção tool-neutral,
  visível em navegação de arquivos, sem associação com uma ferramenta
  específica. Segue o padrão emergente de `AGENTS.md` no root.
- **Idioma híbrido**: PT para regras de negócio e descrições; EN para
  exemplos de código. Consistente com o restante do código do projeto
  (código EN, comentários PT-BR).
- **5 SKILL.md mantidos separados** (não consolidados): Windsurf dispara
  skills contextualmente por descrição; agrupar perderia o trigger
  granular. Cada um virou um router curto que redireciona ao doc
  autoritativo.
- **Princípios inegociáveis repetidos** em 3 pontos (`AGENTS.md`,
  `docs/agents/README.md`, `mgcred-dashboard/SKILL.md`). Duplicação
  intencional: são 5 itens curtos e críticos; queremos que o agente veja
  **antes** de qualquer mudança independente de qual entry point abriu.
- **Append-only em `progress/`**: nunca editar entradas anteriores,
  somente adicionar. Preserva histórico das decisões de cada sessão.
- **`consultor` documentado mas não implementado**: o perfil está em
  [docs/agents/rls.md](../rls.md) como parte da hierarquia esperada, com
  nota explícita de que não há código ainda em `auth.py`/`rls.py`. Fica
  como follow-up.

## Pendências / follow-ups

- [ ] Implementar perfil `consultor` em `src/dashboard/auth.py` (dict `PERFIS`) e `src/dashboard/rls.py` (ramo filtrando por `df["CONSULTOR"] == user["nome"]`).
- [ ] Avaliar se `.windsurf/docs/novos_recursos_dashboard.md` deve migrar para `docs/agents/patterns/` ou permanecer como documento de features.
- [ ] Primeiros patterns candidatos a extrair para `docs/agents/patterns/`:
  paginação Supabase com `offset`, formato de breakdown
  BMG Med/Vida Familiar, shortcut `_sb()`.

## Patterns criados ou atualizados

Nenhum pattern criado nesta sessão — apenas a infraestrutura
(`patterns/TEMPLATE.md`).

## Referências

- Conversa: reorganização proposta pelo usuário para que agentes
  compartilhem referência única de documentação.
- Docs criados: [docs/agents/README.md](../README.md) e filhos.
- Commits de contexto relevantes:
  - `705885b` — consolidação de `app.py` como entrypoint único.
  - `037ff17` — refactor de cache `_atual`/`_historico` + feriados.
  - `adae6c1` — migração `use_container_width` → `width="stretch"`.
