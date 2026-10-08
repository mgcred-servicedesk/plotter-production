# 2026-10-08 — Digitação do Último Dia: fim do OUTROS e Portabilidade separada

**Agente:** Claude Code
**Tipo:** bugfix + feature
**Arquivos tocados:** `database/migrations/132_digitacao_detalhe_tipo_produto.sql`, `src/dashboard/loaders.py`, `src/dashboard/kpis/detalhes_cards.py`, `src/dashboard/pages/detalhes_cards.py`, `tests/test_loaders.py`, `tests/test_kpis_detalhes_cards.py`, `docs/agents/business-rules.md`
**Commit(s):** —

## Objetivo

No quadro "Digitação do Último Dia" (página Em Análise) a coluna OUTROS
somava R$ 92.684,00 em 06/10 sem dizer o quê, e a Portabilidade
(R$ 693.258,45) somava junto do consignado Novo/Refin (R$ 597.265,30).

## O que foi feito

- Diagnóstico: OUTROS = CLT (BMG/C6, R$ 74.622,75) + ANT. DE BENEF.
  (HELP, R$ 18.061,25). O `TIPO_TO_CATEGORIA` de
  `angry-man/src/services/import-produtos.ts` não conhece os nomes novos
  e grava `categoria_id = NULL` a cada import (última: 07/10), desfazendo
  a 061. Pagos/análise/cancelados se recuperam pelo fallback do app; a RPC
  da digitação não trazia o tipo.
- Migration 132 (**não aplicada** — fica com o usuário): a RPC devolve
  `tipo_produto` só nas linhas sem categoria; loader aplica o fallback.
- `separar_portabilidade` + uso só no pivot do último dia.
- 7 testes novos; sabotados (sem o fallback / sem o rótulo) caem 4.
- Simulação read-only de 06/10: OUTROS → 0; CLT 74.622,75; ANT. DE BENEF.
  18.061,25; CONSIGNADO 597.265,30; PORTABILIDADE 693.258,45; total do dia
  inalterado (1.677.799,59).

## Decisões não óbvias

- **Opção 2 (contorno no dashboard) por decisão do usuário**; corrigir o
  angry-man fica para depois. Enquanto não for corrigido, qualquer RPC SQL
  que agrupe por `categorias_produto` sem fallback por tipo repete o
  problema.
- **`tipo_produto` só sem categoria** — não aumenta a granularidade da RPC
  e não aciona `eh_emissao` (lê `TIPO_PRODUTO`) em linhas já categorizadas.
- **Separação só neste quadro** (escopo pedido); rótulos `CONSIGNADO` e
  `PORTABILIDADE`, em maiúsculas como as demais colunas do pivot.
- Ordem de deploy livre: app novo tolera a RPC antiga e vice-versa.

## Pendências / follow-ups

- [x] Usuário aplicar a 132 e rodar a verificação do rodapé (ver atualização).
- [ ] Corrigir `TIPO_TO_CATEGORIA` no angry-man (`CLT`, `ANT. DE BENEF.`)
      + backfill — aí o fallback vira rede de segurança.

## Referências

- Docs consultados: [business-rules.md](../business-rules.md#quadro-digitação-do-último-dia-página-em-análise)

## Atualização — 2026-10-08 (coluna por produto)

- Usuário viu OUTROS ainda na tela: a 132 **não está aplicada** (a
  tentativa via MCP foi recusada no prompt; `pg_get_function_result`
  confirma a assinatura antiga). Sem `tipo_produto` o app não tem como
  distinguir CLT de ANT. DE BENEF.
- Acrescentado `rotular_produto_sem_grupo`: tipo sem categoria que nem o
  fallback reconhece vira coluna com o próprio nome, em vez de OUTROS.
  3 testes novos; sabotado, caem 2.

## Atualização — 2026-10-08 (132 aplicada)

- 132 **aplicada pelo usuário** (SQL Editor; o `apply_migration` via MCP
  voltou "declined" duas vezes). Verificado: assinatura com
  `tipo_produto`; preenchido só em CLT/ANT. DE BENEF. (sem categoria);
  totais por dia idênticos ao agregado `obter_digitacao_diaria` (zero
  divergências); `_json` carrega a coluna; GRANTs e `search_path` ok.
- Ponta a ponta com o loader real, 06/10: colunas ANT. DE BENEF.
  18.061,25 · CLT 74.622,75 · CNC 284.506,09 · CONSIGNADO 597.265,30 ·
  FGTS 10.085,75 · PORTABILIDADE 693.258,45; sem OUTROS; total
  1.677.799,59.

## Atualização — 2026-10-08 (Análise por Produto)

- A pedido do usuário, `separar_portabilidade` também no quadro
  "Análise por Produto" (em análise) da mesma página. `rotular_produto_sem_grupo`
  **não** foi aplicado lá: o df de em análise traz `TIPO_PRODUTO` em
  todas as linhas e BMG Med/Seguro/Emissão (sem `grupo_dashboard`)
  virariam colunas próprias — hoje caem em OUTROS zerado e somem.

## Atualização — 2026-10-08 (Distribuição de Produtos)

- `separar_portabilidade` (e `ROTULO_PORTABILIDADE`) movidos para
  `kpis/produtos.py` — `detalhes_cards` importa de `produtos`, o inverso
  seria import circular; reexportados em `detalhes_cards` como já era
  com `adicionar_produto_detalhado`.
- Aplicado nas duas distribuições de Analíticos (consultor e loja), no
  pivot de valor. 2 testes novos; sabotado, caem 4 (com os do helper).
- Pagos reais 10/2026 pelo caminho do app (`_executar_consolidacao`),
  por loja: CONSIGNADO 1.346.772,79 · PORTABILIDADE 520.326,41; TOTAL
  2.931.266,51 inalterado; sem OUTROS (CLT/ANT. DE BENEF. já vinham pelo
  fallback da consolidação).
