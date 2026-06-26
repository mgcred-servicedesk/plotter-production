# 2026-06-26 — Página "Em Análise": cards por Região + resumos em pivot

**Agente:** Claude Code (inline; UI + KPI)
**Tipo:** feature (UX/UI)
**Arquivos tocados:** `src/dashboard/kpis/detalhes_cards.py`,
`src/dashboard/pages/detalhes_cards.py`, `tests/test_kpis_detalhes_cards.py`
**Commit(s):** (ainda não commitado)

## Objetivo

Reformular a página de drill-down do card "Em Análise": em vez de tabelas
longas, surfar os KPIs como **cards por Região** no topo e **resumos em
pivot** (matriz no formato da imagem-referência do usuário). Serve de
molde para as outras 3 páginas (Cancelados, Média/Consultor, Média/Loja).

## Decisões do usuário (travadas via pergunta)

- **Formato das tabelas-resumo:** pivot/matriz (Região nas linhas × produto
  ou banco nas colunas, com coluna e linha de Total) — não lista longa.
- **Dimensão das linhas:** por **Região** (coerente com os cards do topo e
  seguro em qualquer perfil; consultor-level fica para depois).
- **"Resumo do último dia apurado" (DIGITAÇÃO d-1):** usa **contratos em
  análise** filtrados pelo último `DATA_CADASTRO` — não digitação total
  (o RPC de digitação só entrega agregado diário, sem quebra por dimensão).

## O que foi feito

### Funções puras (`kpis/detalhes_cards.py`)
- `detalhe_analise_pivot(df, linha, coluna)` — pivot de VALOR (`pivot_table`
  sum) com coluna `Total` (soma da linha) e linha `Total` (soma da coluna).
  Aplica `conta_valor`, nulos viram `OUTROS`, colunas/linhas ordenadas
  alfabeticamente com `Total` por último.
- `filtrar_ultimo_dia(df_analise)` → `(df, rotulo dd/mm/aaaa)`. Compara só a
  parte de data (`normalize`); linhas com data nula nunca entram.
- `detalhe_digitacao_diaria(...)` ganhou `ultimos_dias: Optional[int]`.

### UI (`pages/detalhes_cards.py`)
- `_render_cards_regiao_analise` — cards `mg-kpi-context` por região:
  Valor (principal), Qtd, Média DU, Projeção e **farol**.
- `_exibir_pivot` — passa todas as colunas não-dimensão como `colunas_moeda`
  ao `exibir_tabela`.
- `render_detalhe_em_analise` reescrita: cards por Região → último dia apurado
  (pivot) lado a lado com últimos 7 dias (digitação) via `st.columns([3,2])`
  → análise por produto (pivot) → análise por banco (pivot).

### Testes
- 13 testes novos (pivot, filtro do último dia, `ultimos_dias`). Suíte: 179
  passes; ruff limpo.

## Decisões não óbvias

- **Pivot é padrão novo de renderização** (matriz com Totais), sinalizado e
  centralizado em `detalhe_analise_pivot` — `exibir_tabela` já aceita
  qualquer df, então o pivot só precisa marcar as colunas de moeda.
- **Farol da Região compara VALOR vs. a MÉDIA de Valor entre as regiões**
  (não Média DU), porque o KPI principal do card é o Valor e "a média" =
  média dos valores exibidos. Reusa `_calcular_indicador_media`
  (`ui/kpi_cards_reforma.py`, banda de ±10%) para manter o mesmo critério
  de farol dos cards de produto.
- **`ultimos_dias` corta só a EXIBIÇÃO**: a `Var. %`/`Var. Qtd` continua
  calculada sobre a série completa e a "Projeção do mês" usa o acumulado do
  **mês inteiro** (computado antes do `tail`), não a janela de 7 dias.
- **`detalhe_analise_por_produto` continua existindo** (e testada) no módulo
  de KPIs; apenas saiu do import da página, pois a tabela longa "Por Produto"
  foi substituída pelo pivot. Não foi removida.
- **"Último dia apurado" e "Análise por Produto" são o MESMO pivot**
  (Região × produto), diferindo só pelo filtro de data — espelha a imagem
  (DIGITAÇÃO d-1 e ANALISE têm produtos nas colunas).

## Pendências / follow-ups

- [ ] Validação visual no app rodando (`.venv/bin/streamlit run app.py`):
  larguras dos cards/pivots e a coluna estreita (2/5) da digitação.
- [ ] Replicar o padrão (cards + pivot) nas 3 páginas restantes: Cancelados,
  Média/Consultor, Média/Loja.
- [ ] Avaliar dimensão das linhas por perfil (gerente→região, supervisor→loja,
  consultor→produto) quando formos além do nível gerencial.

## Referências

- Continuação de [2026-06-25-detalhes-cards-kpi.md](2026-06-25-detalhes-cards-kpi.md)
- Docs: [ui-components.md](../ui-components.md), [conventions.md](../conventions.md)
