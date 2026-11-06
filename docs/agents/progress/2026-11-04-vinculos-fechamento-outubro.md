# 2026-11-04 — Migration para vinculos do fechamento de outubro

## Escopo autorizado

Preparar migration para aplicacao pelo usuario, sem executar escrita remota.
Arquivo: `database/migrations/147_vinculos_fechamento_outubro_2026.sql`.

## Fatos e decisoes

- Operacao confirmou transferencia em 01/10/2026 de Alessandra para Mage,
  Vitoria para Caxias Guanabara e Roberta para Belford Roxo. Consulta atual
  encontrou as tres transferencias ja registradas como MANUAL. A migration
  aceita tanto o estado anterior quanto esse estado final, sem duplicar.
- Dalila: admissao em 22/09/2026, Campo Grande Nova. Leticia: admissao em
  21/09/2026, Campo Grande Calcadao. Nao tinham janelas de vinculo na consulta.
- Heloina: corrigir o fim indevido em 01/05 para ultimo dia de vinculo
  03/11/2026, inclusive; fim exclusivo 04/11 conforme a regra da migration 142.
- Inicio do afastamento declarado em 01/05/2026. Tipo LICENCA_MATERNIDADE
  sustentado pelo status do cadastro de Bonsucesso, nao inferido de saude.
  Regra vigente da 089 fecha pelo primeiro contrato posterior: confirmado
  em contratos (todos os status) em 20/10/2026. Guarda aborta se esse fato mudar.
- A migration atualiza todas as linhas de cadastro da Heloina para Desligado (a),
  conforme o padrao 142, preservando contratos e a janela anterior de Ramos.
- Nao antecipa as transferencias para absorver contratos de setembro. Esses
  contratos e o caso Victor Felipe continuam pendentes de decisao operacional.
- Nao exige guarda de origem zerada nem rematerializa automaticamente.
- Vinculo prolongado desde maio, afastamento e admissoes podem alterar os
  indicadores historicos; revisar competencias anteriores antes de republicar.

## Validacao e limites

- Sintaxe SQL e corpo PL/pgSQL validados com pglast no ambiente do projeto.
- Pre-condicoes conferidas por consultas somente leitura ao Supabase.
- Confirmado: primeira digitacao da Heloina em 20/10 e nenhum contrato a
  partir de 04/11 na consulta de 04/11.
- Sem execucao transacional de teste: PostgreSQL local indisponivel e Docker
  sem integracao nesta distribuicao WSL. Nao testada contra banco isolado.
- Nenhuma migration aplicada, nenhum snapshot rematerializado/publicado.
- Alteracoes locais preexistentes preservadas.

## Ajuste apos falha na primeira aplicacao (04/11)

- A aplicacao abortou em `admissao tem janela diferente da declarada: DALILA`.
  A carga do HC das 21:27 criou as janelas de Dalila e Leticia com origem ETL,
  na loja e data declaradas. A transacao reverteu; nada foi gravado.
- Guarda de admissao passa a aceitar origem `MANUAL` ou `ETL` (mesma loja,
  inicio e fim aberto). Nao converte ETL para MANUAL: janela MANUAL bloqueia
  o desligamento via HC (ver commit cc9b168).
- Com isso, das 35 pendencias apuradas restam 10: 3 da Heloina (147) e 7
  contratos de setembro (148). Demais guardas conferidas no estado atual.
