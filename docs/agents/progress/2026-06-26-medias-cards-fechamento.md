# 2026-06-26 — Páginas de Média (Consultor/Loja): cards por Região + fechamento das 4 telas

**Agente:** Claude Code (inline; UI + KPI)
**Tipo:** feature (UX/UI)
**Arquivos tocados:** `src/dashboard/pages/detalhes_cards.py`
**Commit(s):** (ainda não commitado)

## Objetivo

Aplicar o padrão cards-por-Região às duas páginas restantes de drill-down
(Média por Consultor / Média por Loja), fechando as 4 telas. Continuação de
[2026-06-26-cancelados-cards-pivots.md](2026-06-26-cancelados-cards-pivots.md).

## Layout final (Média por Consultor / Loja)

1. **Cards por Região** — KPI principal = **Média** (R$ por consultor/loja na
   região); sub = Qtd da base (consultores/lojas), Total e Média DU; farol
   compara a Média da região com a média entre regiões (maior é melhor).
2. **Por Produto** — tabela-resumo de médias (`grupo_dashboard, Valor, Qtd
   Base, Média, Média DU`).

## Decisões não óbvias

- **KPI principal do card = Média (não Valor):** a página é sobre médias, então
  o headline é a Média por consultor/loja. O Total da região vai no sub. Por
  isso foi criado `_render_cards_regiao_medias` (estrutura de colunas difere de
  `_render_cards_regiao`: tem `Qtd Base`/`Média`, não tem `Quantidade`/`Projeção`).
- **Sem pivot nas médias:** o pivot existente é soma de VALOR (Região × dim);
  não representa "média" (exigiria contagem distinta por célula). O resumo por
  produto fica como **tabela** — coerente com "cards + algumas tabelas".
- **`base_plural` derivado de `base`** dentro de `_render_detalhe_medias`
  ("consultores"/"lojas") — sem mudar a assinatura das funções públicas.
- **Refactor de DRY:** extraídos `_card_regiao` (skeleton do card) e
  `_fileira_cards` (container flex com `margin-bottom`), reusados pelos dois
  renderizadores de cards.

## Estado das 4 páginas (drill-down dos cards gerenciais)

| Página | Topo (cards por Região) | Resumos |
|---|---|---|
| Em Análise | Valor, Qtd, Média DU, Projeção, farol | pivot último dia + 7 dias digitação + pivot produto + pivot banco |
| Cancelados | idem, **farol invertido** | pivot produto + pivot banco + Reaproveitamento |
| Média/Consultor | **Média** principal, Qtd Base, Total, Média DU, farol | tabela médias por produto |
| Média/Loja | idem (base = loja) | tabela médias por produto |

## Pendências / follow-ups

- [ ] Validação visual no app das 4 telas (`.venv/bin/streamlit run app.py`).
- [ ] Suíte: 184 passes; ruff limpo (sem testes novos — só UI nesta etapa).
