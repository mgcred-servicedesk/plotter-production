# 2026-10-26 — Atualizacao da Carteira Elegivel de outubro

**Agente:** Codex
**Tipo:** operacao de dados
**Autorizacao:** usuario solicitou atualizar outubro no Supabase usando o
arquivo em Downloads e reiterou a regra de associacao por consultor.
**Codigo / migrations:** nenhuma alteracao.

## Fonte e preparacao

- Fonte: `analitico_elegiveis_promessa.xlsx`, aba `Export`, cabecalho na
  primeira linha e 6.049 clientes nas linhas 2 a 6050.
- SHA-256: `0001c4c66a72e8434dfdc641c55a4bc18b121b28655809924c0e56bff8dddac9`.
- Todas as ADEs numericas, positivas e unicas; referencia 202610 em todas.
- A coluna manual `Loja` foi relacionada de forma univoca ao cadastro:
  48 lojas, todas com codigo BMG e sem redirecionamento a sucessora.
- Utilizada a lista fechada de 18 campos da RPC existente. Nao foram
  enviados matricula, cadeia de gerencia ou campos de cashback.
- O arquivo nao possui saldo_carteira: preservados os saldos anteriores
  dos 3.210 clientes mantidos; nos 2.839 novos o saldo ficou nulo. Esses
  saldos preservados sao da foto anterior, nao atualizados pelo arquivo.
- Os 1.813 links ausentes na fonte foram mantidos como nulos.

## Operacao executada

- RPC `fn_importar_reconquista_elegivel`, apenas periodo 10/2026
  (`3dbf6e55-c723-46ab-9aac-077b982f517e`), DELETE + INSERT atomico.
- Retorno: removidos 3.248, inseridos/elegiveis 6.049, baixa prioridade
  1.344, sem loja 0, sem consultor identificado 2.045.
- Foto mensal: 3.210 ADEs mantidas, 2.839 novas e 38 da foto anterior
  ausentes na nova lista. Nao houve alteracao no cadastro de pessoas/lojas.
- Copia local completa antes/depois e payload restrito guardados fora do
  repositorio, em pasta temporaria `mgcred-elegiveis-outubro-asup4yzo`.

## Regra por consultor preservada

- A loja manual do arquivo e a atribuicao da carteira. Resolucao da RPC
  por nome completo (ILIKE) + loja, admitindo cadastro sem loja, conforme
  a implementacao vigente. Nome original preservado quando nao resolvido.
- Consultor nao identificado ou carteira em nome de supervisor vai para
  `<SUPERVISOR VIGENTE DA LOJA> · a distribuir` no dashboard, sem perder
  clientes. Nao se transferiu carteira para a loja atual do consultor.
- Reconciliacao real com `carteira_por_consultor` e supervisores de outubro:
  2.332 clientes a distribuir (inclui os 2.045 nao identificados); 19 sem
  supervisor vigente, com o rotulo de pendencia existente.

## Verificacao posterior

- Releitura integral da tabela e view: 6.049 elegiveis, 4.705 prioridade,
  1.344 baixa prioridade; todas as lojas com regiao.
- Campos enviados conferidos linha a linha; saldos numericos preservados
  conferidos; IDs de loja conferidos contra o mapeamento da fonte.
- Quebras por loja e consultor somam ambas 6.049 clientes.
- Contagens de outubro mantidas: Promessa Diaria 187, Liga 155,
  Prestamista 3.361. Carteira Elegivel nao altera cards de apuracao.
- Verificado em UTC: 2026-10-26T15:24:21.477882+00:00.
- Testes existentes: 58 passaram e 2 falharam na navegacao porque os testes
  ainda nao esperam a aba Fim de relacionamento — Liga. Os testes de
  calculo e loader passaram. Nao foram alterados testes ou codigo.
- O cache da carteira no dashboard tem TTL de 600 segundos. Nao houve
  inspecao visual da instancia publicada nem deploy: foi operacao de dados.

## Referencias

- [Carteira Elegivel](../business-rules.md#carteira-elegível--lista-de-trabalho-a-partir-de-102026)
- RPC vigente: migrations 140 e 141.
