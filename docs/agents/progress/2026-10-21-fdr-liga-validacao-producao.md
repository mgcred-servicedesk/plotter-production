# 2026-10-21 — Validacao em producao de Fim de relacionamento Liga

**Agente:** Codex (orquestrador e subagentes de dominio)
**Tipo:** feature / validacao
**Arquivos relacionados:** migration 143, importador FDR Liga, loader e analitico de Reconquista
**Commit(s):** alteracoes locais ainda nao commitadas/publicadas

## Objetivo

Conferir a estrutura e carga reais no Supabase e a integracao local do
Angry-man e do dashboard com a foto de outubro/2026 aprovada pelo usuario.
Este registro complementa o progress DBA anterior, sem alterar seu historico.

## Resultados de producao

Resultados remotos conferidos pelo orquestrador apos os testes locais:

- Migration `143_fim_relacionamento_liga.sql` aplicada com sucesso no
  projeto Supabase utilizado pelos dois repositorios.
- Edge Function `reconquista-rpc` versao 14 ativa com a RPC FDR na whitelist.
- Carga da foto de 10/2026: **231 adesoes**, **229 contabilizadas** e
  **duas com qtde zero**, conferidas contra o arquivo fornecido.
- Todas as lojas foram associadas (`sem_loja = 0`). Uma linha permaneceu
  sem consultor resolvido (`sem_consultor = 1`): `HELOINA DE AQUINO NUNES`,
  HELP RAMOS. O nome exato nao existe em `consultores`; a origem foi
  preservada para exibicao e eventual correcao de cadastro/reimportacao.
- Bloco SQL transacional com rollback passou no banco remoto.
- Acesso anon a tabela, view e RPC de importacao negado; permissao de
  execucao da RPC para `service_role` confirmada.

## Integracao e verificacoes locais

- Loader real, recorte RLS e AppTest com dados do Supabase passaram:
  metricas **231 / 229 / 2** e filtro de nao contabilizadas com **duas linhas**.
- Angry-man: **257 testes**, type check TypeScript e build aprovados.
- Dashboard: **62 testes** e Ruff aprovados.
- A migration manteve o conteudo SQL aplicado; houve somente normalizacao
  de fins de linha para LF nos arquivos DBA/documentacao.

## Limites da entrega e follow-ups

- Os resultados acima confirmam migration, Edge Function e carga no banco;
  os frontends Angry-man/dashboard continuam com alteracoes locais, ainda
  sem commit, push ou deploy. A validacao local nao afirma publicacao da UI.
- Corrigir o cadastro de consultor pendente apenas quando houver
  identificacao confirmada; nao criar vinculo arbitrario.
- Quando os frontends forem publicados, conferir o novo card de importacao
  e a sub-aba em Analiticos > Reconquista no ambiente publicado.

## Referencias

- [Banco e testes locais](2026-10-21-fdr-liga-banco.md)
- [Camada de dados](../data-layer.md)
