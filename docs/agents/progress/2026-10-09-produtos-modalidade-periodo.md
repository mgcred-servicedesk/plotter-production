# 2026-10-09 — Modalidade NORMAL/FLEX versionada por tabela e mês

**Agente:** Claude Code (subagente `dba` / supabase-schema-rls)
**Tipo:** feature
**Arquivos tocados:** `database/migrations/135_produtos_modalidade_periodo.sql`, `database/migrations/136_caderno_modalidade_versionada.sql`, `docs/agents/business-rules.md`, `docs/agents/data-layer.md`
**Commit(s):** — (não commitado; migrations **não aplicadas** — aguardam OK do usuário, 135 antes da 136)

## Objetivo

A planilha de tabelas passa a ser importada todo mês e uma tabela pode
trocar NORMAL↔FLEX. Guardar a modalidade por tabela × mês e fazer o
Caderno, a view de pagos e os Analíticos lerem a versão do **mês do
cadastro**, com fallback (versão anterior → `produtos.tipo_operacao` →
`'SEM TABELA'`).

## O que foi feito

- 135: tabela `produtos_modalidade_periodo` (PK `(produto_id, periodo_id)`,
  CHECK NORMAL/FLEX, `competencia` por trigger, índice
  `(produto_id, competencia DESC) INCLUDE (modalidade)`, RLS leitura
  ampla + GRANT SELECT anon/authenticated); funções
  `fn_modalidade_tabela` e `fn_modalidade_tabela_fallback`;
  `v_contratos_dashboard` + `modalidade`, `modalidade_fallback` no fim;
  wrappers `obter_contratos_em_analise_json` /
  `obter_cancelados_classificados_json` com as duas chaves;
  `fn_admin_import` com a tabela no `v_allowed` (resto byte a byte igual
  à 133 — md5 conferido contra produção).
- 136: `obter_caderno_fechamento` = 131 (md5 conferido contra produção)
  com `modalidade_tabela = v.modalidade` e sem o join por nome em
  `produtos`, que ficou morto.

## Decisões não óbvias

- **Coluna extra `competencia` (fora do contrato inicial, aditiva).**
  `periodo_id` é uuid e não ordena; "última versão até o mês X" via join
  com `periodos` custaria O(meses importados) por contrato. Com a coluna,
  é uma sonda no índice. O trigger a preenche sempre (o importador não
  envia; valor enviado é sobrescrito) e falha com mensagem explícita se o
  `periodo_id` não existir.
- **View inline, não chamada de função.** Função SQL com subquery nunca é
  inlinada (com ou sem `SET search_path`). Medido em ~99k contratos:
  chamada de função SQL com SET ≈ 825 ms; subquery escalar ≈ 27 ms. A view
  replica a regra; as funções continuam canônicas (wrappers JSON, uso
  avulso). Paridade é o item 3 da validação da 135.
- **Caderno lê `v.modalidade`**, não `fn_modalidade_tabela(prod.id, …)`
  como pedia o enunciado: valor idêntico (`prod.tabela = v.produto`,
  chave única), custo ~30x menor sobre ~69k linhas/ano.
- **Wrappers JSON sem mexer no RETURNS TABLE.** `produto_id` vem por
  `LEFT JOIN LATERAL (… WHERE c.id = t.id OFFSET 0)` — nested loop pela
  PK, na ordem da função (EXPLAIN ANALYZE: 3.395 sondas, sem seq scan).
  `json_agg(record)` preserva a ordem das colunas; chaves novas no fim.
- **`modalidade_fallback` = TRUE também para `SEM TABELA`** e para
  `data_cadastro` nula (não veio do mês exato). Nunca NULL.
- **RLS de leitura ampla, não deny** (pedido do coordenador / angry-man):
  o importador lê a tabela com a chave anon para achar o último mês
  importado; deny silencioso faria todo mês parecer o mais recente.

## Validações (read-only, 2026-10-09)

- Tabela vazia (CTE): 165.248/165.248 contratos com produto →
  modalidade = `upper(btrim(produtos.tipo_operacao))`; 0 divergentes;
  1 sem produto → `'SEM TABELA'`.
- Caderno: 125.191 linhas da view — 0 com `modalidade_tabela` diferente da
  expressão antiga, 0 com `classificacao_validade` diferente.
- Fallback (versões fictícias): 8/8 casos ok (mês exato, bordas dia 1 e
  31, versão anterior, só versão posterior → produtos, tabela sem
  versões, sem produto, data nula).
- EXPLAIN de SELECT sem as colunas novas: plano idêntico, custo 4692.68
  nos dois; com `modalidade` selecionada aparece o SubPlan.
- Sintaxe das duas migrations validada com o parser do Postgres
  (pglast/libpg_query), incluindo corpos plpgsql.

## Pendências / follow-ups

- [ ] Usuário aprovar e aplicar 135, depois 136 (rodar a validação no fim de cada arquivo).
- [ ] angry-man: enviar `produto_id` (uuid, resolvido após o upsert de `produtos`); com delete+insert, `deleteWhere` só no **primeiro** lote do mês.
- [ ] Dashboard Python: incluir `modalidade`/`modalidade_fallback` em `_COLS_CONTRATOS_PAGOS` quando alguma tela usar (domínio data-layer).
- [ ] Decisão de negócio: manter, trocar ou remover o critério "CONSIG NOVO com prazo < 96 = FLEX" do Caderno.

## Patterns criados ou atualizados

- nenhum

## Referências

- Docs consultados: [data-layer.md](../data-layer.md), [business-rules.md](../business-rules.md), [rls.md](../rls.md), [rpi-workflow.md](../rpi-workflow.md)
