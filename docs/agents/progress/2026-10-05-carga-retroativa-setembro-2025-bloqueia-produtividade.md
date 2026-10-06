# 2026-10-05 — A carga retroativa de 09/2025 bloqueou a produtividade individual

**Agente:** Claude Code
**Tipo:** bugfix (dado + guarda)
**Arquivos tocados:** `database/migrations/129_vigencia_setembro_2025_e_guarda_sucessao.sql`
**Commit(s):** —

## Objetivo

A rematerialização de 09/2025 falhou com `unlinkedPaidOriginEvents: 744`
(`overlappingEligibleDays: 0`). Descobrir a causa e desbloquear.

## Causa

O período 09/2025 foi carregado em **2026-10-05**, depois do rebuild do ledger
da 087 (**2026-08-20**), que registra "o período 09/2025 não existe na base".
Sem setembro, as regras da 087 fecharam janelas em 01/09, abriram em 01/10,
deixaram três pessoas sem janela e empurraram transferências para 01/10.
10/2025 também bloqueava (730), pelos mesmos contratos pagos em outubro.

Segunda causa, menor (20 eventos): o ETL rotula a loja pelo **lote de carga**.
Engenho Novo e Campo Grande Nova vieram PDV só em 08/2025 (HELP em 07 e 09),
com contratos de fim de julho/agosto atravessando os lotes. Nenhuma partição
por data do ledger cobre isso sem sobreposição.

## O que foi feito

- **129 aplicada.** 25 janelas ajustadas e 3 criadas, com as regras de
  fronteira da 087 (entrada/transferência no 1º contrato, saída no fim do mês do
  último). A guarda de origem compara a loja canônica
  (`coalesce(sucessora_id, id)`) dos dois lados.
- Vereditos da operação (2026-10-05): PDV Engenho Novo / PDV Campo Grande Nova
  são os nomes antigos das HELP (reinauguração); JUAN VICTOR e RAYANE NUNES
  trocaram Mesquita ↔ Queimados no período (fronteira 04/09 pela produção);
  LETYCIA foi de Alcântara Carrefour para HELP Alcântara (01/09).
- `fn_materializar_caderno(9, 2025)` e `(10, 2025)` executados sem erro.

## Fecho — medido em 2026-10-05

| | antes | depois |
|---|---|---|
| guarda 09/2025 | 744 | **0** |
| guarda 10/2025 | 730 | **0** |
| guarda 06 / 07 / 08/2025 | 10 / 16 / 34 | 6 / 12 / 10 |
| guarda 08 e 09/2026 | 0 | 0 |
| pares de janelas sobrepostas | 0 | 0 |

Snapshots 09 e 10/2025: regras do parser do Bereshit sem nenhuma linha inválida
(115/872 e 119/894 linhas, base única) e conciliação por loja contra
`paidByConsultants` sem divergência > R$ 0,01 nas 45 lojas de cada mês.

## Decisões não óbvias

- **Guarda por loja canônica, não ledger em PDV/HELP sobreposto.** O rótulo
  alterna por lote; sobrepor janelas acenderia `overlappingEligibleDays` e
  contaria o dia duas vezes.
- **Origem das linhas ajustadas preservada; criadas como `BACKFILL_PRODUCAO`.**
  São inferência de produção — um rebuild hoje as recriaria idênticas. `MANUAL`
  mudaria o peso no `fn_headcount_ponderado` (sem piso de 50%).
- **O Caderno de 10/2025 foi republicado** (o de 2026-08-31 foi sobrescrito):
  o headcount ponderado de outubro muda com as fronteiras corrigidas.

## Pendências / follow-ups

- [ ] Resíduo da guarda em 06, 07 e 08/2025 (6 / 12 / 10) — bloqueará a
      produtividade individual dessas competências quando materializada.
- [ ] `obter_produtividade_individual` filtra loja `ativo`; janelas PDV de
      08/2025 somam zero dias. Loja canônica resolveria também ali.
- [ ] Alerta para carga retroativa posterior ao backfill: período com contratos
      e nenhuma abertura/fechamento de janela no dia 1.
