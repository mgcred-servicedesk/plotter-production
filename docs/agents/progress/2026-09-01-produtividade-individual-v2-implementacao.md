# 2026-09-01 — Implementação do snapshot privado de produtividade v2

**Agente:** Codex
**Tipo:** implement
**Arquivos desta frente:** `database/migrations/101_produtividade_individual_v2.sql`,
`docs/agents/business-rules.md`; integração correspondente no Bereshit
**Commit(s):** —

## Objetivo

Materializar as coleções nominais previstas pelo contrato v2 sem ampliar a
exposição do Caderno agregado e fazer o Bereshit compor os dados somente no
servidor, depois da autenticação.

## Implementado

- snapshot privado `produtividade_individual_snapshot`, com RLS e grants
  exclusivos da `service_role`;
- apuração mensal e das oito semanas ISO completas a partir do mesmo fato
  diário de vínculos e pagamentos;
- base declarada `ELIGIBLE_LINK_DAYS`, cobertura `NONE` e revisão 1;
- exclusão de supervisores pela âncora da competência, lojas inativas e
  `VAI E VEM`;
- publicação atômica com o Caderno agregado;
- bloqueio para produção sem vínculo, sobreposição diária e divergência por
  loja contra `paidByConsultants`;
- RPC privada de leitura por competência.

O Bereshit passou a consultar essa tabela com a `service_role`, validar o
snapshot privado e compor as duas coleções com o payload agregado. Snapshots
anteriores continuam abrindo sem inventar dados individuais.

## Validação antes da aplicação

- sintaxe PostgreSQL validada com `pglast`;
- 33 testes de produtividade/vínculos do dashboard passaram;
- `ruff` passou nos módulos de produtividade e loaders;
- testes, lint e build do Bereshit cobrem parser, composição e compatibilidade.

Simulação somente leitura de 08/2026:

- 21 dias úteis;
- R$ 9.526.883,22 tanto no agregado quanto no individual;
- zero divergências por loja;
- zero sobreposições pessoa × dia;
- três pares pessoa × loja com produção positiva e sem vínculo correspondente.

## Bloqueios de dados do piloto 08/2026

1. `KASSIANE FONSECA FELICIO` — R$ 3.718,54 em `HELP LARANJEIRAS`, sem
   vigência no ledger;
2. `PRISCILA MARCIANA TRANCOSO CORREA DOS SANTOS` — R$ 672,27 em
   `HELP CAXIAS CENTRO`, sem vigência no ledger;
3. `MIZAEL BARBOSA NETO` — R$ 747,99 em `HELP RIO COMPRIDO` em 12/08,
   enquanto o ledger o mantém em `HELP LARANJEIRAS` até 01/09.

O arquivo de afastamentos disponível não contém esses nomes nem datas de
admissão/transferência. As datas precisam ser confirmadas pelo RH/operação e
registradas no ledger antes do piloto; primeira produção paga não será usada
como substituto de data de vínculo.

## Próximos passos operacionais

1. Aplicar a migration 101 no Supabase.
2. Corrigir os três vínculos com datas confirmadas.
3. Executar `fn_materializar_caderno(8, 2026)`.
4. Conferir os diagnósticos privados e abrir `/produtividade` no Bereshit.
5. Repetir para duas competências adicionais antes do backfill aprovado.
