# 2026-08-21 — Triagem dos 17 avisos de performance (plano Nano)

**Agente:** Claude Code
**Tipo:** research / docs
**Arquivos tocados:** nenhum código — backup em `data/backup_reconquista_v1/` (gitignored)
**Commit(s):** (n/a)

## Objetivo

Analisar os 17 avisos INFO do Performance Advisor (3 `unindexed_foreign_keys`
+ 14 `unused_index`) e decidir, no contexto do plano Nano, o que ajustar e o
que aceitar conscientemente.

## O que foi feito

- Triagem dos 17 sob o critério da [054](../../../database/migrations/054_work_mem_authenticator.sql):
  **14 são para ignorar** (todos previstos ou já decididos), 3 dependiam da 031.
- Backup de `reconquista_snapshot` (6.410 linhas) e `macicas` (1) para
  `data/backup_reconquista_v1/`, antes de aplicar a 031.

## Decisões não óbvias

- **O critério certo não é "índice não usado", é "índice em tabela que
  escreve".** A 054 já tinha medido: neste banco a leitura não consome disco
  (cache hit 99,9999%, o banco inteiro cabe em memória) — o dreno de Disk IO é
  **escrita**. Logo um índice em tabela estática de 60 linhas custa
  literalmente nada, e o advisor não sabe disso. Foi esse critério que separou
  os 17 em "agir" e "aceitar", não a severidade do lint.

- **A 031 nunca tinha sido aplicada** — descoberto aqui. `reconquista_snapshot`
  existe com **exatamente 6.410 linhas**, o mesmo número que o cabeçalho da 031
  previa quando foi escrita: a tabela está congelada desde a v2 (028-030). Os 3
  `idx_rsnap_*` flagrados são exatamente os que a
  [060](../../../database/migrations/060_drop_indexes_nao_usados_churn.sql#L34)
  dizia que "somem com a 031". Grep por todos os objetos v1 em `src/`, `app.py`,
  `scripts/` e `tests/` volta vazio — nenhum consumidor.

- **Aplicar a 031 quase não economiza IO, e isso foi dito ao usuário.** A tabela
  é estática: sem escrita não há WAL nem página suja, e o autovacuum mal a toca.
  O ganho é higiene (alguns MB, 3 avisos a menos, uma pendência de julho
  fechada) — não economia de Disk IO. Decisão do usuário: exportar e aplicar.

- **Os 3 FKs sem índice: não criar nenhum.** Criar seria o oposto do que o Nano
  pede — custo de escrita e disco para zero benefício de leitura:
  - `produtos.categoria_id` — o índice foi dropado **de propósito** pela 060, que
    já registrou o INFO como aceito. É o aviso previsto chegando.
  - `supervisor_vigencia.loja_id` (58 linhas) — o único acesso
    (`loaders.py:1536`) usa embedding do PostgREST, que resolve filho→pai pela
    **PK de `lojas`**; nunca filtra por `loja_id`.
  - `loja_regiao_vigencia.regiao_id` (83 linhas) — o LATERAL da
    [044:78-87](../../../database/migrations/044_views_regiao_vigencia.sql#L78-L87)
    filtra por `vig.loja_id` (coberto por `idx_lrv_loja_periodo`) e só
    **projeta** `regiao_id`, que depois casa com `regioes.id` (PK).

  O índice de FK só serviria a `DELETE`/`UPDATE` no pai, que é raro e admin,
  contra tabelas de 58 e 83 linhas.

- **Os 11 índices não usados: manter.** Nove já tinham decisão de **2026-07-09**
  registrada no cabeçalho da 060. Os 2 novos são de `gestao_presets`, criada
  pela 064 — a tabela tem **0 linhas**, então "nunca usado" é ausência de dado,
  não índice errado.

- **Por que o backup foi feito via API e não pelo Studio** — 6.410 linhas
  paginadas de 1000 em 1000 com `order("id")`; a contagem confere com o
  planner e com o número do cabeçalho da 031, o que o export manual não
  verificaria. Destino `data/`, que é gitignored (`.gitignore:184`) — os CSVs
  têm dado de cliente (`cod_ade`, `saldo_contabil`, `link`).

## Pendências / follow-ups

- [ ] **Aplicar a 031** no SQL Editor (backup já feito). Ordem e verificação na
      seção abaixo
- [ ] Depois de aplicar, confirmar no advisor que os 3 `idx_rsnap_*` sumiram e
      que o total cai de 17 para 14 avisos
- [ ] **Dispensar (dismiss) os 14 restantes** no painel, para o advisor voltar a
      mostrar só o que é novo. Todos estão justificados aqui e nos cabeçalhos
      da 060 e da 031
- [ ] Auditar drift de índices no mesmo espírito da
      [2026-08-21-rls-deny-explicito](2026-08-21-rls-deny-explicito.md): a 031
      é o caso inverso do RLS de `reconquista` — migration escrita e nunca
      aplicada, em vez de mudança aplicada sem migration. Vale um diff entre
      `pg_indexes`/`pg_class` e o que `database/migrations/` declara

## Checklist de execução da 031

1. Backup — **feito** em `data/backup_reconquista_v1/` (6.410 + 1 linhas)
2. Confirmar que nada consome os objetos v1 (já verificado por grep; refazer
   se houver código novo desde 2026-08-21)
3. Medir o disco antes, para saber o que se ganhou:
   ```sql
   SELECT relname, pg_size_pretty(pg_total_relation_size(oid))
   FROM pg_class WHERE relname IN ('reconquista_snapshot','macicas');
   ```
4. Rodar `031_reconquista_drop_v1.sql` no SQL Editor, **fora da janela do
   import do ETL** (o `DROP TABLE` pega ACCESS EXCLUSIVE)
5. Verificar (esperado: 0 linhas):
   ```sql
   SELECT tablename FROM pg_tables
   WHERE schemaname = 'public'
     AND tablename IN ('reconquista_snapshot','macicas');
   ```
6. Confirmar que o dashboard não mudou — a aba Reconquista lê `v_reconquista`
   (v2), que não toca em nenhum objeto dropado

## Referências

- Docs consultados: [data-layer.md](../data-layer.md)
- Entradas relacionadas: [2026-05-11-supabase-performance-warnings](2026-05-11-supabase-performance-warnings.md),
  [2026-08-21-rls-deny-explicito](2026-08-21-rls-deny-explicito.md)
- Migrations relacionadas: 018 (DDL v1), 028-030 (v2), 031 (drop), 054/055/060 (Disk IO), 064
- Lints: [0001_unindexed_foreign_keys](https://supabase.com/docs/guides/database/database-linter?lint=0001_unindexed_foreign_keys),
  [0005_unused_index](https://supabase.com/docs/guides/database/database-linter?lint=0005_unused_index)

---

## Resultado da aplicação da 031 (2026-08-21, mesmo dia)

Aplicada pelo usuário no SQL Editor. Advisor caiu de **17 para 14 avisos** —
os 3 `idx_rsnap_*` sumiram, e os 14 restantes são exatamente o conjunto
previsto na triagem acima (3 FK sem índice + 11 índices não usados).

Verificado por leitura via `service_role` (PostgREST `PGRST205` — "Could not
find the table in the schema cache"):

| Objeto | Estado |
|---|---|
| `reconquista_snapshot`, `macicas` | ausentes ✓ |
| `v_reconquista_ultimo`, `v_reconquista_por_loja`, `v_reconquista_clientes` | ausentes ✓ |
| `reconquista` (v2) | 3.248 linhas ✓ |
| `v_reconquista` (fonte do dashboard) | 3.248 linhas ✓ |

Contagem idêntica entre tabela e view confirma que a `v_reconquista` continua
resolvendo — a aba Reconquista não foi afetada.

**Não medido:** o disco liberado. O passo 1 da checklist
(`pg_total_relation_size` antes do drop) não foi reportado, e depois do `DROP`
não há como recuperar o número. Sem impacto prático — a estimativa era de
poucos MB e o ganho sempre foi higiene, não IO —, mas fica registrado que o
dado não existe.

**Pendências desta entrada, atualizadas:**

- [x] Aplicar a 031
- [x] Confirmar que os 3 `idx_rsnap_*` sumiram (17 → 14)
- [ ] Dispensar (dismiss) os 14 restantes no painel do advisor
- [ ] Auditar drift de índices (segue aberto)
