# 2026-06-26 — Página "Cancelados": cards por Região + pivots (mesma lógica do Em Análise)

**Agente:** Claude Code (inline; UI + KPI)
**Tipo:** feature (UX/UI)
**Arquivos tocados:** `src/dashboard/kpis/detalhes_cards.py`,
`src/dashboard/pages/detalhes_cards.py`, `tests/test_kpis_detalhes_cards.py`
**Commit(s):** (ainda não commitado)

## Objetivo

Aplicar à página de drill-down de "Cancelados" o mesmo padrão da página
"Em Análise" (cards por Região + resumos em pivot, no lugar de tabelas
longas). Continuação de
[2026-06-26-em-analise-cards-pivots.md](2026-06-26-em-analise-cards-pivots.md).

## Layout final (Cancelados)

1. **Cards por Região** (cancelados líquidos): Valor, Qtd, Média DU,
   Projeção e **farol invertido**.
2. **Cancelados por Produto** — pivot Região × Produto (líquidos).
3. **Cancelados por Banco** — pivot Região × Banco (líquidos).
4. **Reaproveitamento** — mantido como tabela (composição compacta).

## O que foi feito

- `detalhe_cancelados_pivot(df, linha, coluna)` (kpis): filtra líquidos via
  `separar_cancelados_liquidos` e reusa o pivot genérico
  `detalhe_analise_pivot`.
- Helpers da UI generalizados:
  - `_render_cards_regiao_analise` → `_render_cards_regiao(det, du, vazio_msg,
    maior_e_melhor=True)` — recebe o breakdown por região já pronto; serve
    Análise e Cancelados.
  - novo `_farol_html(valor, media_ref, maior_e_melhor)` — encapsula o farol.
  - `_exibir_pivot(df, linha, coluna)` → `_exibir_pivot(pivot, linha)` — agora
    recebe a matriz já montada (cada página escolhe `detalhe_analise_pivot`
    vs. `detalhe_cancelados_pivot`).
- `render_detalhe_cancelados` reescrita; `render_detalhe_em_analise` ajustada
  para os helpers genéricos.
- Removidas as constantes órfãs `_MOEDA_BREAKDOWN`/`_NUMERO_BREAKDOWN` (eram
  só das tabelas longas substituídas pelos pivots).
- 3 testes novos (`detalhe_cancelados_pivot`). Suíte: 184 passes; ruff limpo.

## Decisões não óbvias

- **Farol INVERTIDO em cancelados** (`maior_e_melhor=False`): ficar ACIMA da
  média de cancelamento é RUIM. `_farol_html` troca só emoji/cor
  verde↔vermelho (#10A37F ↔ #EF4444); a descrição "Acima/Abaixo da média"
  permanece factual e o 🟡 "Na média" não muda.
- **Sem "Último Dia Apurado" nem "Últimos 7 Dias" em cancelados:** não há
  série diária de cancelados (o RPC de digitação cobre todos os status, não
  cancelamento), e a `DATA_CADASTRO` do cancelado é o cadastro original
  (≠ data do cancelamento) — filtrar por ela seria ruído.
- **Pivots de cancelados são só LÍQUIDOS** (redigitadas/recuperadas saem),
  coerente com `detalhe_cancelados_por_produto/_regiao`. O Reaproveitamento é
  quem expõe redigitadas/recuperadas e oportunidades perdidas.
- **`detalhe_analise_pivot` é genérico** (pivot de VALOR); o nome mantém o
  prefixo "analise" por histórico, mas `detalhe_cancelados_pivot` o reusa
  após filtrar líquidos — não foi renomeado para evitar churn.

## Pendências / follow-ups

- [ ] Validação visual no app (`.venv/bin/streamlit run app.py`).
- [ ] Replicar nas 2 páginas restantes: Média/Consultor e Média/Loja.
