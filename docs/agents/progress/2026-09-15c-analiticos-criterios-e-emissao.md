# 2026-09-15 — Analíticos: critério canônico nos Aceleradores e a divergência de Emissão

**Agente:** Claude Code
**Tipo:** refactor + investigação
**Arquivos tocados:** `src/dashboard/tabs/analiticos.py`,
`src/dashboard/kpis/gerais.py`, `tests/test_tabs_analiticos.py`,
`docs/agents/business-rules.md`

## Objetivo

Follow-up da Etapa 2: `tabs/analiticos.py` tinha 1.400 linhas e 19% de
cobertura, e a hipótese era que ainda escondia regra de negócio dentro
dos renderers.

## O mapa, e a hipótese que não se confirmou

A maior parte do arquivo é apresentação legítima. Com 191 linhas,
`_render_reconquista_detalhamento` é quase só widget, filtro de tela e
renomeação de colunas; a vigência já vem marcada pelo loader. Cancelados
filtrados na tela também estão certos: `separar_cancelados_liquidos` lê
`CLASSIFICACAO`, pré-computada por linha, e não depende das outras
linhas do recorte.

**Descartado de propósito:** dividir o arquivo por sub-aba (muita
mudança de linhas, nenhum bug corrigido) e perseguir o número de
cobertura (widget exige `AppTest`, com ganho desproporcional).

## O que foi feito

1. **Expanders de Emissão e Super Conta usam `mascaras_aceleradores`**
   via `_linhas_acelerador`. Eram uma quarta superfície para o
   critério, escrita inline. BMG Med e Vida Familiar continuam em
   `_pool_seguros`, que responde outra pergunta: a união das três
   fontes com deduplicação.
2. **`NR_ADE`**: três cópias inline da regra de fallback
   `NUM_PROPOSTA → CONTRATO_ID` passaram a usar `_nr_ade`, que já
   existia no arquivo.
3. **`mascaras_aceleradores` ganhou `astype(str)` antes de `.str`.**
   Com a coluna `TIPO_PRODUTO` toda nula (dtype float), ela levantava
   `AttributeError`, e o inline antigo não levantava. Sem essa
   correção, a troca do item 1 poderia quebrar os expanders num período
   sem produto resolvido. O resultado para texto não muda.

## Decisões não óbvias

- **Prova de equivalência contra o código antigo, copiado no teste.**
  `_criterio_inline_*` guarda verbatim a máscara antiga e é comparada
  com a canônica em frames com casos de borda: pagos **com** a flag
  `is_super_conta`, em análise **sem** ela, maiúsculas e minúsculas,
  espaços, `""`, `None`, `NaN` e coluna toda nula. A troca só é válida
  porque as duas marcam as mesmas linhas.
- **Um teste de mecanismo além da equivalência:** com a máscara
  canônica substituída, o expander muda junto. Esse é o motivo da
  troca: quando a regra de Emissão for decidida, os Aceleradores seguem
  sem edição.

## Verificação por sabotagem

| Sabotagem | Testes que quebram |
|---|---|
| tirar o `astype(str)` da máscara canônica | 2 (coluna toda NaN) |
| helper com critério próprio | 3 (inclui o de mecanismo) |
| máscara canônica sem `strip` no Super Conta | 1: **só** em análise, porque os pagos usam a flag |

A terceira linha mostra por que os frames variados importam: um frame
só de pagos não pegaria a regressão.

Suíte: 1.111 → 1.122, ruff limpo.

## Divergência de Emissão (achado, não corrigido)

"Emissão" tem **dois critérios** no código:

| Superfície | Critério |
|---|---|
| `consolidacao.is_emissao_cartao` (zera valor e pontos) e contador da aba Produtos (`_PRODS_QTD`) | `TIPO OPER. ∈ {CARTÃO BENEFICIO, Venda Pré-Adesão}` |
| `mascaras_aceleradores`: rankings, Gestão, Distribuição e Aceleradores | `TIPO_PRODUTO ∈ {EMISSAO, EMISSAO CC, EMISSAO CB}` |

Na Etapa 3 unifiquei as quatro máscaras sem notar que a Emissão da
consolidação usa outra coluna. O `business-rules.md` escrevia
`TIPO_PRODUTO` com os valores de `TIPO OPER.`; corrigi o texto para
refletir o código e marquei a divergência como aberta.

Verificação combinada: o usuário roda no SQL Editor (uma query
agregada) e a regra é decidida com o resultado.

```sql
SELECT tipo_operacao, tipo_produto, count(*) AS qtd
FROM v_contratos_dashboard
WHERE data_status_pagamento >= date '2026-06-01'
  AND (tipo_operacao IN ('CARTÃO BENEFICIO', 'Venda Pré-Adesão')
       OR upper(tipo_produto) IN ('EMISSAO', 'EMISSAO CC', 'EMISSAO CB'))
GROUP BY 1, 2
ORDER BY 3 DESC;
```

## Pendências / follow-ups

- [ ] **Decidir o critério único de Emissão** com o resultado do SQL.
- [ ] Ticket médio: em Pagas divide pela contagem de contratos com
      `VALOR > 0`, igual a `calcular_kpis_gerais`; em Análise e
      Cancelados divide pela contagem total de linhas. Pode ser
      intencional, porque a consolidação só zera emissão nos pagos.
      Pergunta registrada, sem mudança.
