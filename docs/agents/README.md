# Referência para Agentes de IA — MGCred Plotter

Esta pasta é a **fonte única de verdade** para qualquer agente de IA
(Claude Code, Windsurf, Cursor, Cody, etc.) que trabalhe neste projeto.

`CLAUDE.md` (root), `AGENTS.md` (root), `.windsurf/rules/*.md` e
`.windsurf/skills/*/SKILL.md` são **pontos de entrada específicos de cada
ferramenta** que apontam para este diretório. Todo conhecimento de
projeto mora aqui; os entry points contêm apenas regras comportamentais
da respectiva ferramenta.

## Índice

### Conhecimento de projeto (leitura)

| Arquivo | Escopo |
|---|---|
| [architecture.md](architecture.md) | Entrypoint único (`app.py`), árvore de diretórios, legados, banco de dados |
| [business-rules.md](business-rules.md) | Pontuação, cartão, seguros BMG/Vida, Super Conta, pipeline Em Análise, metas |
| [data-layer.md](data-layer.md) | Supabase (views `v_*`, RPCs), paginação, estratégia de cache `_atual`/`_historico` |
| [rls.md](rls.md) | Ordem obrigatória de RLS, hierarquia dos 5 perfis |
| [conventions.md](conventions.md) | Nomenclatura, formatters PT-BR, Width API, chart template, paleta |
| [ui-components.md](ui-components.md) | streamlit-antd-components, `exibir_tabela`, tab renderer |

### Contribuições de agentes (escrita)

| Pasta | Propósito | Quando escrever |
|---|---|---|
| [patterns/](patterns/) | Documentar "como fazer X" descoberto/decidido | Ao identificar um padrão repetível não óbvio pelo código |
| [progress/](progress/) | Log append-only de sessões/decisões | Ao fim de tarefa com decisão não capturada pelo commit |

Ambas as pastas têm `TEMPLATE.md`. Copie, renomeie e preencha.

## Princípios

1. **Single source of truth.** Cada regra mora em **um** arquivo. Demais linkam.
2. **Tool-neutral.** Sem prefixo de ferramenta no conteúdo. Qualquer agente consome.
3. **Patterns curtos.** ~1 tela. Se crescer, quebrar em sub-patterns.
4. **Progress é append-only.** Nunca editar entradas anteriores — só adicionar.
5. **Código não mora aqui.** Estes docs descrevem decisões/padrões; implementação vive em `src/` e `app.py`.

## Regras de negócio críticas (resumo de 1 linha)

- **Pontos** = `VALOR × PTS` (tabela `pontuacao`, via RPC `obter_pontuacao_periodo`).
- **Cartão** (`CARTÃO BENEFICIO`, `Venda Pré-Adesão`) — só quantidade.
- **Seguros** (`BMG MED`, `Seguro` → "Vida Familiar") — só quantidade; entram em "Pagos" via `sub_status_banco = 'Liquidada'`.
- **Super Conta** — subtipo de CNC; conta para valor/pontos E como produção separada.
- **Pipeline Em Análise** — exclui `PAGO AO CLIENTE`, `CANCELADO`, `Liquidada`.

Detalhes em [business-rules.md](business-rules.md).

## Princípios inegociáveis (obrigatórios em qualquer mudança)

1. **Entrypoint único**: `app.py` (root). `dashboard*.py` são obsoletos.
2. **RLS antes de render**: `aplicar_rls` → `aplicar_rls_metas` → `aplicar_rls_supervisores`.
3. **Cache dual**: toda função `carregar_*` faz branch `_atual`/`_historico` via `_eh_mes_atual()`.
4. **Width API**: `width="stretch"` em `st.plotly_chart`/`st.dataframe`/`st.button` (Streamlit ≥ 1.35).
5. **Nunca** calcular dias úteis inline — sempre `from src.shared.dias_uteis import calcular_dias_uteis`.
