# 2026-10-08 — Portabilidade pontua pela taxa própria (≥ 10/2026)

**Agente:** Claude Code
**Tipo:** feature
**Arquivos tocados:** `src/dashboard/kpis/consolidacao.py`, `src/dashboard/pages/dashboard_pontuacao.py`, `tests/test_kpis_consolidacao.py`, `database/migrations/131_caderno_portabilidade_taxa_propria.sql`, `docs/agents/business-rules.md`
**Commit(s):** —

## Objetivo

A tabela de pontuação de 10/2026 ganhou a linha `PORTABILIDADE = 0,5`,
única para qualquer banco. O dashboard e o Caderno a ignoravam (alias
por banco → CONSIG a 1,0) e outubro estava 231.262,62 pontos acima.

## O que foi feito

- Python: a partir de `DATA >= 2026-10-01`, Portabilidade usa a linha
  `PORTABILIDADE` do período; sem a linha, mantém o alias por banco e
  denuncia em `portabilidade_sem_pontuacao` (aviso no expander de admin).
- Migration 131: a 123 com um `WHEN` novo no `CASE` de `categoria_pontos`
  (mesmas duas guardas). **Não aplicada** — fica com o usuário.
- 10 testes novos em `TestPortabilidadeTaxaPropria`, sabotados: sem a
  regra caem 8; sem a trava de vigência caem 2.
- Conferência com dados reais (2026-10-08): 10/2026 4.555.516,80 →
  4.324.254,18; 03, 04, 08 e 09/2026 idênticos ao Caderno no centavo.

## Decisões não óbvias

- **Trava de vigência além do EXISTS** — 03/2026 e 04/2026 têm linha
  `PORTABILIDADE = 1,0` (importada, nunca consumida). Só o EXISTS
  reescreveria esses meses (hoje iguais porque CONSIG_BMG/C6 também eram
  1,0 — coincidência, não garantia).
- **Sem linha → alias, não zero** — espelha o saque Gov.
- **Banco não mapeado também pega 0,5** — "qualquer banco" (antes ficava
  com 0).
- **`PRODUTO PTS` da planilha de Tabelas não foi tocado** — o importador
  ignora a coluna desde 2026-09-09.

## Pendências / follow-ups

- [ ] Usuário aplicar a 131 no Supabase e rodar a verificação do rodapé.
- [ ] Rematerializar 10/2026 do Caderno após a 131.
- [ ] Até a 131 ser aplicada, dashboard e Caderno divergem em 10/2026.

## Referências

- Docs consultados: [business-rules.md](../business-rules.md#portabilidade--taxa-própria--102026)

## Atualização — 2026-10-08 (fechamento)

- 131 **aplicada** pelo usuário e verificada: `pg_get_functiondef` traz o
  `WHEN` novo; 10/2026 = 4.324.254,18 (bate com o dashboard); 03, 04, 08
  e 09/2026 idênticos aos de antes; diferença = 231.262,62 = metade do
  pago de portabilidade do mês.
- Rematerialização de 10/2026 **só no fim do mês** (processo do usuário),
  não logo após a migration.
- Banco novo: o operacional cadastra a linha de pontuação e as Tabelas
  **antes** de subir a produção. Para a Portabilidade ≥ 10/2026 a taxa é
  única, então banco fora do mapa já pega a linha PORTABILIDADE — o mapa
  por banco só importa para meses ≤ 09/2026.
