# 2026-10-21 — Banco de Fim de relacionamento Liga

**Agente:** Codex (subagente DBA)
**Tipo:** feature
**Arquivos tocados:** `database/migrations/143_fim_relacionamento_liga.sql`, `docs/agents/data-layer.md`
**Commit(s):** ainda nao commitado

## Objetivo

Guardar o novo analitico FDR Liga como foto mensal, usando a associacao
organizacional da Reconquista Liga e preservando a visao do banco.

## O que foi feito

- Migration nova com tabela propria, view `security_invoker`, RPC
  transacional e grants exclusivos de service_role.
- Validacao integral antes do DELETE; erro mantem o periodo anterior.
- Trava da competencia impede mistura entre reimportacoes concorrentes.
- Bloco SQL separado para validacao com rollback, sem inserir fixtures
  de teste no deploy.

## Decisoes nao obvias

- Competencia guarda a foto inteira, mesmo com datas de saida em meses
  diferentes. Os 90 dias sao o recorte da fonte, nao filtro dinamico.
- `qtde = 0` tambem fica no analitico; soma de `qtde` representa a conta
  do banco. Isso nao transforma FDR em Reconquista efetivada.
- Toda ADE repetida bloqueia o arquivo, inclusive linhas identicas;
  nenhuma primeira ocorrencia e escolhida silenciosamente.
- Nome de consultor usa igualdade sem diferenca de caixa em vez de
  `ILIKE` para nomes com `%`/`_` nao funcionarem como curingas.
- `franqueado` e opcional e preservado quando fornecido pelo importador.

## Pendencias / follow-ups

- [ ] Orquestrador revisar e aplicar migration no projeto correto.
- [ ] Executar bloco transacional de validacao e conferir carga real
      de 10/2026: 231 ADEs, 229 contabilizadas e duas com qtde zero.
- [ ] Integrar nova RPC na whitelist/mapa do Angry-man e o novo loader
      com RLS antes de exibir no dashboard (outros subagentes).

## Referencias

- [data-layer.md](../data-layer.md)
- [rls.md](../rls.md)
- Migration 127: resolucao de loja/sucessora/consultor da Liga.

## Validacao local executada

- PostgreSQL 16 Alpine em container isolado `--network none` usando imagem
  local existente; schema minimo com roles e vinculos sinteticos.
- Migration 143 aplicada sem erros; bloco `FDR_VALIDATION_BEGIN` passou
  integralmente com `BEGIN`/`DO`/`ROLLBACK`.
- Carga real do arquivo fornecido passou no banco local: 231 inseridas,
  229 contabilizadas, duas com quantidade zero, e reimportacao 231/231.
- Fixtures adicionais confirmaram sucessora de loja, prioridade de
  consultor na loja, igualdade literal sem curingas, fallback bruto,
  preservacao de outra competencia e rollback da foto apos falha
  simulada de INSERT posterior ao DELETE.
- Leitura da view com role `service_role` funcionou. Ao fim do rollback,
  a tabela local voltou a zero linhas. `git diff --check` sem erros.
- Esta validacao local nao afirma aplicacao, carga ou deploy remotos.
