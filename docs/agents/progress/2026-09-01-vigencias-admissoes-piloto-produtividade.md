# 2026-09-01 — Vigências de admissão do piloto de produtividade

**Agente:** Codex
**Tipo:** fix
**Arquivos desta frente:**
`database/migrations/102_vigencias_admissoes_piloto_produtividade.sql`
**Commit(s):** —

## Contexto confirmado pela operação

- Kassiane Fonseca Felicio foi admitida em 25/08/2026 e pertence à Help
  Laranjeiras.
- Priscila Marciana Trancoso Correa dos Santos foi admitida em 11/08/2026 e
  pertence à Help Caxias Centro.
- Mizael Barbosa Neto pertence à Help Laranjeiras e apenas cobriu falta de
  pessoal em alguns dias na Help Rio Comprido; não houve transferência
  permanente.

## Implementado

A migration 102 registra as duas admissões como vigências `MANUAL`, sem usar
a primeira produção paga como aproximação. A aplicação é idempotente, resolve
cada loja por nome único e aborta diante de uma vigência conflitante.

Mizael ficou deliberadamente fora da correção: o ledger diário exige que cada
dia pertença a uma única loja. Assim que os dias exatos da cobertura forem
informados, a vigência de Laranjeiras poderá ser repartida e esses dias poderão
ser atribuídos a Rio Comprido sem transformar a cobertura em transferência.

## Próximo passo

Confirmar as datas exatas, inclusive quando não consecutivas, em que Mizael
trabalhou na Help Rio Comprido durante agosto de 2026.
