# 2026-09-25 — Saque no cartão Gov pontua por CARTAO_GOV

**Agente:** Claude Code
**Tipo:** bugfix
**Arquivos tocados:** `src/dashboard/kpis/consolidacao.py`,
`src/dashboard/pages/dashboard_pontuacao.py`,
`database/migrations/123_caderno_saque_cartao_gov.sql`,
`tests/test_kpis_consolidacao.py`, `docs/agents/business-rules.md`
**Commit(s):** (não commitado)

## Objetivo

Investigar por que o total de pontos de 09/2026 exibia 22.179.389 quando o
usuário esperava 22.134.141, e fazer o saque no cartão Gov pontuar 1 real =
1 ponto em vez de 2,5.

## O que foi feito

- **Diagnóstico do gap de 45.247,86.** Dashboard e Caderno SQL concordavam
  à casa do centavo (22.179.388,86), então não era divergência de
  implementação. O gap decompõe em **42.411,65 de VAI E VEM** (4
  portabilidades C6, que entram no total da rede por decisão de 02/09/2026,
  migration 108, mas ficam fora de lojas/regiões/ranking) + ~2.836 de um
  item pequeno. Os 13.622,70 do saque Gov **não** eram o gap.
- **Causa raiz do saque Gov:** a migration 122 criou `CARTAO_GOV` e
  destravou o import, mas a linha era **tarifa sem consumidor** — 0
  produtos com `categoria_id → CARTAO_GOV` e 0 categorias com
  `categoria_pts_id → CARTAO_GOV`. Os saques Gov seguiam em `SAQUE` →
  alias `CARTAO` → 2,5.
- Override por **convênio** em `consolidar_pontuacao`, ao lado do de
  Portabilidade (`_mascara_saque_gov`), + a mesma regra no `CASE` de
  `categoria_pontos` do Caderno (migration 123).
- Diagnóstico (`saque_gov_reclassificado` / `saque_gov_sem_pontuacao`)
  exposto no expander de admin.
- 13 testes em `TestSaqueCartaoGov`, validados contra 5 sabotagens da
  correção (remover o gate de vigência, remover o filtro de convênio, cair
  para 0 sem `CARTAO_GOV`, arrastar `PORTABILIDADE`, ignorar
  `SAQUE_BENEFICIO`).

Efeito medido em 09/2026: **22.179.388,86 → 22.165.766,16** (−13.622,70, os
2 saques Gov). 08/2026 inalterado.

## Decisões não óbvias

- **Por que convênio e não produto/categoria?** `produtos.categoria_id` sai
  de `tipo`/`subtipo` (angry-man, `import-produtos.ts`), e Gov e INSS
  compartilham tipo **e** nome de tabela: `SAQUE COMPLEMENTAR - Digital
  Token - Não` tem 4.286 INSS contra 9 Gov. Remapear o produto arrastaria
  os 4.286. O convênio vive no contrato — granularidade maior que
  categoria, idêntico ao `BANCO` da Portabilidade, que a 013 deixou fora do
  alias estrutural pelo mesmo motivo.
- **Só `GOVERNO DO RJ`.** SIAPE (−1.493.874,44 no histórico), prefeituras,
  COMLURB e GOVERNO MG foram oferecidos com os números e recusados.
- **Não retroativo.** Corte em 09/2026; sem ele, 615.968,95 pontos se
  moveriam de 05/2025 a 08/2026 e todo caderno publicado passaria a
  divergir do comunicado. O gate é por `DATA` (não por parâmetro
  `mes`/`ano`) para não mudar a assinatura de `consolidar_pontuacao` — 22
  call sites em testes — e porque `periodo_id` é derivado de
  `data_status_pagamento`, o que torna as duas formas equivalentes e faz a
  regra valer também na consolidação por intervalo. Medido: 0 de 17.304
  saques com `DATA` nula.
- **Sem `CARTAO_GOV` no período, mantém a taxa antiga** em vez de cair para
  0 (o `coalesce(pc.pontos, 0)` do SQL faria isso naturalmente — daí a
  guarda `EXISTS` na migration). Zerar apagaria produção paga em silêncio.
- **Assumimos que `SAQUE_BENEFICIO` entra junto** com `SAQUE`. Os dois
  aliasam para `CARTAO` e há produto Gov nos dois. Sem efeito em 09/2026.

## Pendências / follow-ups

- [x] Migration 123 **aplicada** pelo usuário em 25/09/2026. Verificado às
      17:5x UTC: `obter_caderno_fechamento(9, 2026)` devolve
      `effectivePoints = 22165766.16` e `paidEffective = 10775755.94`,
      idênticos ao dashboard. Caderno e Python conciliam.
- [x] **Número validado pelo usuário** em 25/09/2026: apuração manual
      independente deu 22.165.766,16, igual ao dashboard (que exibe
      22.165.766, arredondado corretamente).
- [x] Os **dois** saques Gov do mês entram a 1,0 — o critério é o convênio,
      não o produto. Houve um susto no meio do caminho (o usuário esperava
      22.176.552,66, que deixaria o saque de R$ 7.191,00 a 2,5), resolvido
      como `produtos` desatualizada **do lado da apuração manual**, não da
      regra. Confirma que o convênio é o discriminador correto: os dois
      produtos de saque são idênticos em `produtos` (mesmo tipo, subtipo,
      banco, categoria) e só o `CONVENIO` separa Gov de INSS.
- [ ] Confirmar a premissa de `SAQUE_BENEFICIO` (sem efeito até hoje).
- [x] **Não relacionado a Gov, mas era o grosso do gap original:** os
      42.411,65 do VAI E VEM **não** eram questão de regra. As 4
      portabilidades (978707538/539/768/771, CARLA MARINO, C6 BANK/INSS)
      estão `status_banco = CANCELADO` **e** `status_pagamento_cliente =
      PAGO AO CLIENTE`, canceladas em 02-04/09 e "pagas" em 23-24/09. São
      **100% dos pagos com `CANCELADO` do mês** e repetem a assinatura do
      pagamento fantasma de 21/09/2026 (mesma loja, consultora, produto,
      banco e convênio). Usuário identificou e vai corrigir na origem.
      **Não** excluir `status_banco = 'CANCELADO'` da view de pagos — as 21
      linhas históricas são vendas reais.

## Referências

- Docs consultados: [business-rules.md](../business-rules.md),
  [data-layer.md](../data-layer.md)
- Migrations: 013 (alias), 067 (valor consolidado), 108 (Caderno), 122
  (categoria CARTAO_GOV), 123 (esta)
