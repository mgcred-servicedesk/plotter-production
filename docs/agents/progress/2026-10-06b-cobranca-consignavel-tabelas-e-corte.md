# 2026-10-06 — Cobrança Consignável: tabelas do banco + corte em 08/2026

**Agente:** Claude Code
**Tipo:** feature + bugfix
**Arquivos tocados:** `database/migrations/130_cobranca_consignavel_tabelas_e_corte_agosto_2026.sql`, `docs/agents/business-rules.md`
**Commit(s):** —

## Objetivo

O banco criou em 05/10/2026 as tabelas `COBRANÇA CONSIGNAVEL - NOVO` e
`- REFIN` para apurar a modalidade. O usuário pediu para contar também as
propostas dessas tabelas, REFIN incluído, e para corrigir a inflação de
09/2025.

## O que foi feito

- Migration 130 (não aplicada; base = view da 067):
  - `fn_eh_cobranca_consignavel_por_valor`: sinal de valor da 067 + corte
    de pagamento a partir de 01/08/2026;
  - `fn_eh_tabela_cobranca_consignavel`: reconhece as tabelas pelo nome;
  - `v_contratos_dashboard`: `is_cobranca_consignavel = por_valor OR tabela`.
    O uplift para VLR BRUTO vem só do sinal de valor.
- Simulado inline antes de aplicar:
  - 09/2025 volta a 0 (era 233 contratos e +R$ 181.821,56);
  - 08 e 09/2026 não mudam;
  - 10/2026 vai de 3 para 19 contratos, com uplift inalterado (10.273,28).

## Decisões não óbvias

- **Critério misto (decisão do usuário).** Antes de 05/10 houve propostas
  da modalidade em tabelas normais, que só o sinal de valor reconhece.
- **REFIN produz no VLR BASE (decisão do usuário).** O VLR BRUTO do refin
  inclui o saldo quitado do contrato anterior.
- **Reconhecimento pelo nome da tabela, não por coluna nova em `produtos`.**
  O usuário não escolheu. Evitei criar estrutura; o custo é que uma tabela
  com outro nome exige `CREATE OR REPLACE` da função.
- **09/2025 muda (mês fechado), por exceção.** A inflação nasceu da carga
  retroativa de 05/10/2026; a correção devolve o mês ao valor de antes da
  carga. O usuário pediu a correção explicitamente.
- `fn_eh_cobranca_consignavel` (067) foi mantida e virou o núcleo do sinal
  de valor, então não sobra função morta.

## Pendências / follow-ups

- [ ] Aplicar a 130 e rodar as validações (seção 4).
- [ ] 09/2025 já tinha caderno e produtividade materializados em 05/10 com
      o valor inflado (`fn_materializar_caderno(9, 2025)`). Rematerializar
      depois da 130 se esses números usam produção em valor.

## Referências

- [business-rules.md](../business-rules.md) — Cobrança Consignável (critério e valor consolidado)
