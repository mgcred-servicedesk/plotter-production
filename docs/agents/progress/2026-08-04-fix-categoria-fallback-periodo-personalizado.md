# 2026-08-04 — Fix: categoria_codigo NULL zera produtos no período personalizado da Gestão

**Agente:** Claude Code
**Tipo:** bugfix
**Arquivos tocados:** `src/dashboard/loaders.py`, `tests/test_loaders_intervalo.py`
**Commit(s):** (não commitado ainda)

## Objetivo

Usuário reportou que, na aba Gestão, com "Período personalizado" ativo
(01/01/2026–30/06/2026) e critério CLT em modo "Com venda (> 0)", a
produção aparecia zerada (0 de 172 consultores, R$ 0,00), mesmo
havendo vendas de CLT no período.

## O que foi feito

- Confirmado contra o Supabase real: 1.643 linhas com
  `tipo_produto = 'CLT'` em jan–jun/2026, todas com
  `categoria_codigo = NULL` (categoria_id não backfillado — ver
  migration 061 e `_TIPO_PARA_CATEGORIA` em `loaders.py`).
- Identificado que `_preencher_categoria_fallback` é chamada em 3
  lugares (contratos em análise, cancelados, `_executar_consolidacao`
  — usado pela visão normal de mês da sidebar) mas **não** em
  `carregar_contratos_pagos_intervalo`, o loader exclusivo do período
  personalizado da Gestão.
- Adicionada a chamada `df = _preencher_categoria_fallback(df)` em
  `carregar_contratos_pagos_intervalo` (`loaders.py`), uma vez sobre o
  DataFrame já concatenado dos meses do intervalo, espelhando o padrão
  de `_executar_consolidacao`.
- Adicionado teste de regressão
  (`TestCarregarContratosPagosIntervalo` em
  `tests/test_loaders_intervalo.py`) que reproduz o cenário (CLT com
  `categoria_codigo=None`) via `carregar_contratos_pagos` e
  `carregar_categorias` mockados — falha sem o fix (`categoria_codigo`
  fica `None`), passa com ele (`CONSIG_PRIV`).
- A pedido do usuário, verificado o escopo real do problema no
  Supabase (histórico completo, sem filtro de data): 13.601 linhas com
  `categoria_codigo` NULL, distribuídas em `tipo_produto` = ANT. DE
  BENEF. (8.360), CLT (2.668), CPT (2.544), CONTA SIMPLES (18) e
  PAPCARD (11). CLT **não era o único** produto do MIX da Gestão
  afetado: ANT. DE BENEF. (mapeado para `ANT_BENEF`, rótulo do pack
  FGTS/ANT.BENEF./CNC13º) tinha o mesmo sintoma, em volume ainda maior.
  Como o fix é genérico (roda sobre o DataFrame inteiro, não por
  produto), já cobre os dois sem ajuste adicional. CPT/CONTA
  SIMPLES/PAPCARD ficam de fora do fallback (nunca estiveram em
  `_TIPO_PARA_CATEGORIA`) e fora do MIX da Gestão — lacuna de dados
  preexistente e mais ampla, não o mesmo bug, não tocada aqui (ver
  pendências).

## Decisões não óbvias

- **Fallback aplicado uma vez no DataFrame concatenado, não por mês**
  — evita repetir a leitura de `carregar_categorias()` (já é
  `@st.cache_data(ttl=86400)`, então seria barato de qualquer forma,
  mas manter uma única chamada por intervalo é mais simples e
  consistente com o resto da função, que já concatena antes de
  filtrar por data).
- **Não tentei verificar a correção com uma query real no Supabase**
  (script bare fora do Streamlit) — bateu em
  `statement timeout` (57014) no compute Nano ao buscar meses inteiros
  fora do fluxo normal da app. Evitei repetir a query pesada contra a
  instância (ver `project_supabase_disk_io_nano` na memória). A
  cobertura ficou no teste unitário, que exercita a função real
  `_preencher_categoria_fallback` (só os loaders de rede foram
  mockados).

## Pendências / follow-ups

- [ ] Considerar corrigir a causa raiz no ETL (categoria_id não
  backfillado quando um `tipo_produto` é renomeado na planilha de
  origem) — o fallback é um remendo em memória, não a correção
  definitiva (já apontado no docstring de `_preencher_categoria_fallback`).
- [x] CPT ("CREDITO PESSOAL PARA TODOS"), CONTA SIMPLES e PAPCARD somam
  2.573 linhas com `categoria_codigo` NULL e sem entrada em
  `_TIPO_PARA_CATEGORIA` — ficam sem categoria em QUALQUER superfície
  (não só período personalizado), inclusive fora do MIX da Gestão.
  **Esclarecido pelo usuário (2026-08-04): são produtos temporariamente
  fora de comercialização.** Não é bug — manter os registros como
  estão (sem categoria) para o caso de a comercialização voltar. Sem
  ação necessária.

## Referências

- Docs consultados: [docs/agents/data-layer.md](../data-layer.md)
