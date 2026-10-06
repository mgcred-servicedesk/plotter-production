# 2026-10-06 — Estorno pós-pagamento fora da produção

**Agente:** Claude Code
**Tipo:** bugfix
**Arquivos tocados:** `database/migrations/130_estorno_pos_pagamento_fora_da_producao.sql`, `docs/agents/business-rules.md`
**Commit(s):** —

## Objetivo

Na produção paga de out/2026 até o dia 5, a apuração manual dava 1.682.810,25
e o dashboard mostrava 1.683.581,26. A diferença de R$ 771,01 era o contrato
3011756 (proposta 10586022, HELP SÃO CRISTOVÃO, CNC Débito em Conta - REFIN),
pago e depois cancelado (estorno) em 05/10. O usuário confirmou o estorno e
decidiu: tirar o estorno da produção sem mudar meses fechados.

## O que foi feito

- Migration 130 (não aplicada; quem aplica é o usuário):
  - `fn_eh_estorno_pos_pagamento(status_banco, data_status_banco, data_status_pagamento)`;
  - `v_contratos_dashboard` passa a excluir os pagos que a função marca;
  - `obter_cancelados_classificados`: o CTE `paga` recebe o mesmo filtro.
- Regra documentada em `business-rules.md` (seção "Estorno pós-pagamento").
- Medido antes de aplicar (predicado inline, só leitura):
  - a regra tira só o 3011756;
  - outubro até o dia 5 fica em 1.682.810,25;
  - os 7 casos de borda dão o resultado esperado.

## Decisões não óbvias

- **Corte em 01/10/2026, e não "todo CANCELADO pago".** `CANCELADO` +
  `PAGO` também é a assinatura dos reativados antigos (20 linhas,
  nov/25–fev/26, vendas reais). Desde set/2026 a origem manda os reativados
  como `EM ANÁLISE`. Setembro já está fechado, então o corte começa em outubro.
- **Mesmo mês do pagamento.** Meses fechados não mudam. Estorno em mês
  posterior continua contando no mês do pagamento, e não há lançamento
  negativo no mês do cancelamento. O usuário descartou essa alternativa por
  ser mais complexa (pontuação e metas).
- **`date_trunc` com cast para `TIMESTAMP`.** Sobre `DATE`, o `date_trunc`
  resolve para a versão `timestamptz`, que é STABLE. Isso quebraria o
  IMMUTABLE e o inlining da função.
- **Risco aceito:** se a origem deixar de corrigir um reativado para
  `EM ANÁLISE`, uma venda real sai da produção. Subnotificar é preferível
  a inflar.

## Pendências / follow-ups

- [ ] Usuário aplicar a 130 no Supabase e rodar o bloco de validação (seção 4).
- [ ] `contratos_pagos` (view legada, sem consumidor no app) não recebeu o
      filtro. Avaliar remoção em outra tarefa.

## Referências

- Docs consultados: [business-rules.md](../business-rules.md)
