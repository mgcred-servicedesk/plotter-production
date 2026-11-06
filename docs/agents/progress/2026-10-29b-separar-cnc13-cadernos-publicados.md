# 2026-10-29 — CNC 13º separado nos Cadernos já publicados (migration 146)

**Agente:** Claude Code
**Tipo:** bugfix (dados publicados do Caderno)
**Arquivos tocados:** `database/migrations/146_caderno_separar_cnc13_publicados.sql`,
`docs/agents/business-rules.md`
**Commit(s):** — (não commitado; migration aplicada em 2026-10-29)

Continua [2026-10-29-nome-unico-e-cnc13-no-caderno.md](2026-10-29-nome-unico-e-cnc13-no-caderno.md).

## Objetivo

Com a 145 aplicada, o CNC 13º só sairia separado nos Cadernos publicados
depois dela. O usuário decidiu que ler os dois juntos é ruim para o negócio
também nos 17 já publicados (05/2025 a 09/2026).

## O que foi feito

- `fn_separar_cnc13_snapshot(mes, ano)`: troca só o grupo CNC de `mix` e
  `productRanking` pelo CNC e CNC_13 do cálculo atual, depois de provar que
  os dois somados dão o CNC publicado — no total e loja a loja (pago,
  produção válida, pontos e gerente). Se não der, `RAISE` e nada muda.
- O payload ganha `contractVersion = 'v1.10'` e `mixRevision`; `gerado_em`
  não muda. O payload anterior vai para `caderno_fechamento_snapshot_revisao`
  (RLS sem policy).
- A migration chama a função para os 17 meses, um por instrução.

## Decisões não óbvias

- **Separar no snapshot, não republicar.** `fn_materializar_caderno`
  recalcula tudo: moveria a produtividade por loja congelada, a produção
  válida do Consignado em 06, 07 e 09/2026 (tabelas reclassificadas depois da
  publicação — 1, 2 e 11 lojas) e recusaria 03 e 04/2026 pelos pagamentos sem
  vínculo (10 e 16). A separação toca só o que a decisão pede.
- **Conferido antes, de novo dentro da função.** Em 2026-10-29, nos 17
  meses, CNC + CNC_13 atuais = CNC publicado no MIX e em todas as lojas do
  ranking. A função repete a conferência na hora de aplicar, porque os
  contratos podem mudar entre a medição e a aplicação.
- **Primeiro histórico de revisões do Caderno.** A tabela nova cobre esta
  revisão; `fn_materializar_caderno` ainda sobrescreve sem arquivar.
- **Testada em Postgres 17 local** com Caderno sintético: separa, recusa
  divergência no total e por loja, é idempotente e não toca no resto.

## Pendências / follow-ups

- [x] Aplicar a 146. Aplicada em 2026-10-29, antes do deploy do Bereshit.
      Conferido: 17 de 17 em `v1.10`, CNC + CNC_13 = CNC arquivado, shares
      somando 1 e resto do payload com md5 idêntico ao arquivado.
- [ ] Publicar o Bereshit com suporte a `CNC_13` (branch
      `feat/alinhamento-dashboard`; `origin/main` ainda em `5f9e16b`). Até
      lá, a versão em produção descarta o CNC 13º de 05/2025 e 02–04/2026.
- [ ] Opcional: fazer `fn_materializar_caderno` arquivar o payload anterior
      em `caderno_fechamento_snapshot_revisao` antes de sobrescrever.

## Referências

- Bereshit: `docs/CONTRATO_DADOS.md`, seção "146".
