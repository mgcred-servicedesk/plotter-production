# 2026-11-26 — Performance do banco: cancelados com `paga` MATERIALIZED e índice sem uso

**Agente:** Claude Code
**Tipo:** research / bugfix (performance)
**Arquivos tocados:** `database/migrations/149_cancelados_paga_materialized.sql`, `database/migrations/150_drop_idx_contratos_status_pagamento.sql`
**Commit(s):** —

## Objetivo

O usuário pediu uma nova verificação do banco para otimizar as queries e
reduzir o carregamento dos indicadores, avaliando índices e outras soluções.

## O que foi feito

- Diagnóstico pelo `pg_stat_statements` (desde 15/10/2026), por
  `pg_stat_user_tables` e `pg_stat_user_indexes`, por EXPLAIN ANALYZE e
  pelos advisors. Banco com 146 MB (era 68 MB em julho), cache hit de 100% e
  nenhum arquivo temporário gerado pelas queries do dashboard.
- **149:** `obter_cancelados_classificados` passa a usar `paga AS MATERIALIZED`.
  Era 29,5% do tempo do banco (média 2,7 s, máximo 27 s).
- **150:** remove `idx_contratos_status_pagamento`, que tem 0 scans desde
  sempre e ocupa 2,2 MB na tabela que mais recebe escrita.
- Paridade da 149 medida antes de aplicar, com a nova versão criada como
  função temporária da sessão (`pg_temp`): de 06 a 11/2026, mesmas linhas e
  0 diferenças nos dois sentidos (`EXCEPT ALL`).

## Decisões não óbvias

- **A causa da função de cancelados é o cache de plano do plpgsql, não só a
  estimativa errada.** Na mesma conexão, as 5 primeiras chamadas usam plano
  custom (cerca de 100 ms aquecido). A partir da 6ª, o plpgsql adota o plano
  genérico, que inlina o `paga` e faz nested loop com um range scan de pagos
  POR cancelado. A conexão fica presa nisso: 3,3–4,1 s por chamada. Como as
  conexões do PostgREST duram dias, quase toda chamada em produção cai no
  genérico. Com `MATERIALIZED`, o genérico fica estável em 50–80 ms.
- **O cruzamento de recuperação é a condição, não a causa.** O `redig`
  (redigitação, cancelado × cancelado) custa cerca de 5 ms. O `matches`
  (cancelado × pago) é onde o plano ruim se manifesta. A regra não mudou.
- **Índice novo não é a alavanca.** Os 13 avisos de FK sem índice estão em
  tabelas de importação que são apagadas e reinseridas: o índice só
  aumentaria a escrita. As milhões de leituras sequenciais em
  `consultores`/`lojas`/`regioes` são em tabelas com até 478 linhas, e ler
  tudo é o plano certo.
- **`v_contratos_dashboard` não tem problema de plano.** A página aquecida
  leva 30–46 ms. A média alta (175–539 ms) vem da conexão fria (cerca de
  650 ms na 1ª query) e da disputa de CPU com a função de cancelados.
- **Descartado: modalidade inline nos wrappers `_json`.** Ganho medido de
  cerca de 45 ms aquecido e nenhum ganho com a conexão fria (o custo frio
  está na função interna). Não paga uma terceira cópia da regra de modalidade
  que a 135 evitou de propósito.
- **Adiado: filtro de linha inalterada no `fn_admin_import` para `produtos` /
  `produtos_modalidade_periodo`.** A importação de Tabelas roda cerca de 12
  vezes em 42 dias, então a invalidação de planos é rara. Além disso, o
  angry-man confere `qtdGravadas !== versoes.length`, e pular linhas
  inalteradas faria essa conferência acusar erro.
- **`SET statement_timeout` mantido na 149**, embora seja ineficaz, para a
  migration mudar uma coisa só.

## Pendências / follow-ups

- [x] 149 aplicada via MCP em 26/11/2026 (registro `20261126171834`).
      Paridade contra a foto anterior (17:12:57 UTC): hashes idênticos de 06
      a 11/2026. O wrapper `_json` ficou estável em cerca de 190 ms (11/2026)
      e 245 ms (10/2026) depois de 10 chamadas seguidas, contra 1,7–4 s antes.
      Agora a maior parte do tempo que sobra está no wrapper (modalidade por
      linha + json_agg), e não mais na função interna.
- [x] 150 aplicada pelo usuário no SQL Editor em 26/11/2026 (o
      `apply_migration` do MCP foi recusado na confirmação de comando
      destrutivo, então ela não aparece em `supabase_migrations`, como a 055).
      Verificado: índice ausente, `contratos` com 13 índices, nenhum inválido.
- [ ] Medir a média do wrapper de cancelados no `pg_stat_statements` alguns
      dias depois.
- [ ] Custo de conexão fria (cerca de 650 ms) e CPU instável são limites do
      Nano: o upgrade para Micro segue recomendado.

## Patterns criados ou atualizados

- Nenhum.

## Referências

- Docs consultados: [data-layer.md](../data-layer.md), progress de
  2026-07-08 (Disk IO) e 2026-10-08 (statement_timeout)
