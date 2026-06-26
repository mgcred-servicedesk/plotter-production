# 2026-06-25 — Funções puras de detalhamento (drill-down) dos cards de KPI

**Agente:** Claude Code (business-rules-kpi-expert)
**Tipo:** feature
**Arquivos tocados:** `src/dashboard/kpis/detalhes_cards.py` (novo), `tests/test_kpis_detalhes_cards.py` (novo)
**Commit(s):** (ainda não commitado)

## Objetivo

Criar a camada de funções puras que alimenta os quadros de detalhamento
(drill-down) dos cards de KPI: análise, digitação diária, cancelados,
reaproveitamento e médias — por produto e por região. Sem Streamlit, sem
tocar app.py/ui/loaders.

## O que foi feito

- Novo módulo `src/dashboard/kpis/detalhes_cards.py` com funções puras:
  - `_projetar(valor, du_decorridos, du_totais)` — projeção linear; `du_decorridos<=0 → 0.0`.
  - `_aplicar_conta_valor(df)` — zera VALOR de linhas `conta_valor=False` sem alterar a contagem (`None`/ausente → trata como True).
  - `detalhe_analise_por_produto/_regiao` — agrega VALOR/Quantidade, Ticket Médio, Média DU, Projeção.
  - `detalhe_digitacao_diaria` — série diária do RPC `obter_digitacao_diaria` (colunas minúsculas) com `Var. Qtd` e `Var. %`, + linha "Projeção do mês".
  - `detalhe_cancelados_por_produto/_regiao` — só cancelados líquidos (via `separar_cancelados_liquidos`).
  - `detalhe_reaproveitamento` — composição (sem projeção): Redigitada/Recuperada + Oportunidade Perdida por nível (flags `RECUPERADA_*`).
  - `detalhe_medias_por_produto/_regiao` — base `consultor` (exclui supervisores) ou `loja`.
- 29 testes unitários novos; suíte completa 159 passes; ruff limpo.

## Colunas de saída (a UI consome)

- Análise/Cancelados: `[dimensão], Valor, Quantidade, Ticket Médio, Média DU, Projeção`.
- Digitação diária: `data_cadastro, qtd_digitada, Var. Qtd, Var. %, valor_digitado` (+ linha "Projeção do mês").
- Reaproveitamento: `Categoria, Quantidade, Valor` (sem projeção).
- Médias: `[dimensão], Valor, Qtd Base, Média, Média DU`.

## Decisões não óbvias

- **Médias padronizadas com base única** — `Média = total_do_grupo / qtd_distinta_no_grupo` e `Média DU = Média / du_decorridos`, sempre com a MESMA base. NÃO replica a divergência de `render_kpis_contexto` (`src/dashboard/ui/kpi_cards_reforma.py:213-219`), que usa `num_lojas` com fallback default `1` (mascara zero) misturando bases. Aqui `Qtd Base` é a contagem distinta real e `du_decorridos<=0 → Média DU = 0` (sem fallback).
- **Variação da digitação na QUANTIDADE** — qtd é a métrica central. `Var. %` trata 1ª linha (sem anterior) e divisão por zero (anterior=0) como `0.0` (replace inf→0, fillna 0). `valor_digitado` é informativo, sem variação própria.
- **Digitação diária usa valor BRUTO do RPC** — NÃO aplica `conta_valor` (a regra de `conta_valor` vale só para breakdowns de análise/cancelados/médias, que vêm dos dfs de contratos).
- **Quantidade conta só `VALOR > 0`** — espelha `calcular_kpis_por_produto`; assumido como a definição canônica de "quantidade" também nos breakdowns de detalhe.
- **Reaproveitamento sem projeção** — é composição de quantidades/valores (semântica migrations 032/033), não série temporal projetável.
- **`fillna("OUTROS")` na dimensão** — agrupamentos por `grupo_dashboard`/`REGIAO` com nulos não somem; viram bucket "OUTROS".

## Pendências / follow-ups

- [ ] UI (streamlit-ui-specialist): renderizar os DataFrames nos cards expansíveis, aplicando formatters de moeda/percentual de `conventions.md`.
- [ ] Data layer (data-layer-supabase): confirmar que o loader do RPC `obter_digitacao_diaria` entrega `data_cadastro`/`qtd_digitada`/`valor_digitado` minúsculas sem renomear.
- [ ] Validar com o usuário: definição de "quantidade" (VALOR>0) e a base default das médias na UI (consultor vs. loja por perfil).

## Referências

- Docs: [business-rules.md](../business-rules.md), [conventions.md](../conventions.md)
- Migrations 032/033 (classificação de cancelados + flags RECUPERADA_*)
- Divergência referenciada: `src/dashboard/ui/kpi_cards_reforma.py` (`render_kpis_contexto`)
