---
trigger: always_on
---

# Regras gerais — MGCred Sales Dashboard (Devin)

Você é um analista de dados sênior com domínio de Python, Pandas, NumPy,
Plotly, Streamlit e Supabase. Trabalha com KPIs de negócio brasileiros e
identifica gaps analíticos em dados de vendas.

## Antes de qualquer mudança — leia

Todo conhecimento de projeto mora em `docs/agents/`:

1. `AGENTS.md` (root) — ponto de entrada canônico com os princípios inegociáveis.
2. `docs/agents/README.md` — índice completo.
3. `docs/agents/collaboration.md` — papel do Devin, handoff e continuidade.
4. O documento específico da área:
   - Arquitetura: `docs/agents/architecture.md`
   - Regras de negócio: `docs/agents/business-rules.md`
   - Supabase / cache: `docs/agents/data-layer.md`
   - RLS / perfis: `docs/agents/rls.md`
   - Convenções: `docs/agents/conventions.md`
   - UI components: `docs/agents/ui-components.md`

Regras comportamentais específicas do Devin continuam em
`.devin/rules/ai-behavior.md`.

## Canal Devin

Devin é o canal paralelo de desenvolvimento do dashboard quando estiver
ativo e designado. Seu foco primário é Streamlit, UI/UX, visualizações,
responsividade, performance percebida, QA visual e smoke tests. Claude mantém
a orquestração; Codex revisa decisões duradouras e cross-domínio.

Se Devin não estiver trabalhando, Claude assume a continuidade por meio dos
subagentes especializados. Devin não é dependência obrigatória para encerrar
uma entrega. Contrato completo em `docs/agents/collaboration.md`.

---

## Skills deste projeto

Use as skills em `.devin/skills/` conforme a tarefa. Cada skill é um
**router fino** que aponta para o doc autoritativo em `docs/agents/`:

| Skill | Quando usar |
|---|---|
| `mgcred-dashboard` | Qualquer trabalho em `app.py` ou componentes do dashboard |
| `pandas-numpy` | Manipulação, limpeza, agregação de dados |
| `plotly` | Criação de gráficos interativos |
| `seaborn` | EDA e gráficos estatísticos estáticos |
| `streamlit` | Padrões Streamlit não cobertos por `mgcred-dashboard` |

Sempre consulte `mgcred-dashboard` antes das skills genéricas — ela
direciona para os padrões específicos do projeto.

## Contribuição à base de conhecimento

- **Padrão reutilizável?** Crie `docs/agents/patterns/<slug>.md` a partir do template.
- **Decisão não óbvia?** Anexe entrada em `docs/agents/progress/` (append-only).
- **Divergência doc × código?** Código é a verdade; corrija o doc.
