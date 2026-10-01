# 2026-10-01 — A previsão de transferência da 087 bloqueou o fechamento de setembro

**Agente:** Claude Code
**Tipo:** bugfix (dado, não código)
**Arquivos tocados:** `database/migrations/124_vigencia_previsao_transferencia_desmentida.sql`,
`125_contratos_atribuicao_errada_setembro.sql`, `126_vigencia_admissao_cassiane.sql`
**Commit(s):** —

## Objetivo

`fn_materializar_caderno(9, 2026)`, chamada pelo angry-man para republicar o
Caderno de fechamento, falhou com `unlinkedPaidOriginEvents: 164`. Descobrir a
causa e entregar o caminho de desbloqueio.

## O que foi feito

- Guarda da 105 reproduzida fora do banco e conferida contra
  `fn_contar_pagamentos_sem_vinculo_origem(9, 2026)`: **164, bate exato**.
  São **R$ 347.089,55** (2,6% do `monthlyPaidTotal`) em 8 pessoas e 4 causas.
  `overlappingEligibleDays` está em 0 — o bloqueio é inteiro da origem.
- Causa dos 129 maiores identificada na CTE `transferidos` da **087**, não em
  carga nova nem em erro de cálculo.
- Migration **124** entregue (não aplicada): desfaz as 3 previsões desmentidas
  (CAMILLY, ANA CLARA, VICTOR) e registra a transferência real de GISELLE.
- Confirmado que a **106 nunca foi aplicada** — os 17 contratos de 18/08 ainda
  apontam para Iluara. As guardas dela seguem todas verdes (ADEs, loja, data,
  cadastro único de Patrícia e Iluara em Cascadura, vigência de supervisão).
- `absenceCoverage: "NONE"` é constante da `ruleRevision 1`, não dado faltando.
  O ledger tem 2 afastamentos no total e nenhum cruza setembro.

## A mecânica, em uma passada

A CTE `transferidos` da 087 é o único ramo do backfill que **afirma presença
sem nenhum contrato que a sustente**: "ativo hoje numa loja diferente da última
em que digitou… a janela nova começa no mês seguinte". Rodando em
**2026-08-20 20:42**, ela criou 7 janelas abertas em **01/09** e fechou na mesma
data a janela da loja onde a pessoa produzia.

A loja da janela nova sai da **foto** (`consultores` deduplicado por
`updated_at DESC`). A carga de HC de **2026-08-11 20:44** tocou a linha *antiga*
de três dessas pessoas — o par (nome, loja_id) de `uq_consultores_nome_loja` faz
o ETL INSERIR cadastro novo na loja nova em vez de mover a pessoa, e o
`updated_at` decide qual das duas é a verdade. A foto velha venceu o dedup, e o
ledger copiou a foto.

| pessoa | previsão 01/09 | produção real | na loja prevista |
|---|---|---|---|
| CAMILLY | HELP COPACABANA | LARANJEIRAS 04/08..30/09 (159) | zero desde 04/08 |
| ANA CLARA | HELP S.J. DE MERITI | VILAR DOS TELES 20/07..30/09 | zero desde 20/07 |
| VICTOR | HELP COPACABANA | COPACABANA NOVA 04/08..04/09 | zero, **nunca** |

Das 7 previsões, 3 estavam erradas. As outras (DJANE, PATRICIA, e as MANUAL/ETL
de HUGO, JOYCE, PEDRO) batem com a produção.

## Decisões não óbvias

- **A 116 não vê esse erro, e não é falha dela.** Para CAMILLY e ANA CLARA foto e
  ledger *concordam* — o ledger copiou a foto. O detector compara os dois e não vê
  nada; quem viu foi a guarda da 105, que compara o ledger com a **produção**. As
  duas superfícies não são redundantes, e este caso é a prova. Fica o follow-up de
  uma sexta checagem na 116.

- **Depois da 124 o detector passa de 3 para 4 divergências, e isso é ganho.**
  GISELLE sai (foto e ledger passam a concordar), CAMILLY e ANA CLARA entram.
  O erro sai do ledger, onde falsificava o denominador em silêncio, e vai para o
  detector, que é onde pergunta aberta deve morar.

- **`DELETE` na janela prevista, não fechamento** — mesmo argumento da 121. Fechar
  afirmaria "esteve nesta loja de 01/09 até X", o oposto do medido, e manteria peso
  no denominador da loja errada; `chk_cv_vigencia_ordem` nem admite duração zero.

- **`MANUAL` na janela reaberta** — a 087 apaga `origem LIKE 'BACKFILL%'` e preserva
  ETL/MANUAL (razão da 118). Reaberta como `BACKFILL_PRODUCAO`, um rebuild futuro
  com a foto ainda velha recriaria exatamente a previsão que a 124 desfaz.

- **A 124 não toca em `consultores`.** A foto é produto da carga de HC (094/095):
  corrigir `loja_id` ali seria desfeito na carga seguinte. O conserto durável é no
  `HC_Colaboradores`.

- **A 124 não decide o destino de VICTOR.** O cadastro dele em HELP SÃO JOÃO DE
  MERITI (criado 23/09, zero produção lá) pode ser transferência real sem produção
  ainda, ou ADE errada como na 121. A migration afirma só o que a produção prova:
  em 03 e 04/09 ele estava em COPACABANA NOVA. A 116 segue reportando-o.

- **A 124 + a 106 não desbloqueiam setembro.** Levam de 164 para **3**, e os três
  restantes dependem de veredito da operação, não dos dados. Agosto, sim, fica em 0
  só com a 106.

- **Agosto também estava bloqueado** (17, todos de Iluara) e os snapshots publicados
  são de **02/09**, anteriores às 8 janelas fechadas retroativamente na carga de HC
  de 23/09. As duas competências voltam juntas — é o follow-up aberto no registro de
  2026-09-23f.

## Pendências / follow-ups

- [x] ~~Aplicar **106** e **124**.~~ **Feito 2026-10-01.** Medido depois de aplicar:
      08/2026 em **0**, 09/2026 em **3**, os 17 contratos agora em Patrícia, as quatro
      linhas do tempo idênticas ao bloco de verificação da 124, e o detector foi de 3
      para **4** divergências — Giselle saiu, Camilly e Ana Clara entraram, exatamente
      como previsto.
- [x] ~~**CASSIANE** — falta a data de admissão.~~ **Resolvido:** a operação declarou
      **15/09/2026**. Migration **126** entregue. O primeiro contrato é de 24/09, então
      o fallback da R1 custaria **7 dias úteis** (12/21 contra 5/21).
- [x] ~~**MARCELA** — ADE errada ou retorno?~~ **Resolvido:** registro errado. A venda é
      de **MARCELLA NUNES DEODATO**, de HELP RIO COMPRIDO. Migration **125**, caso 1.
- [x] ~~**MIZAEL** — onde ele estava em 08/09?~~ **Resolvido:** a transferência de 04/09
      vale; o contrato estava atribuído à loja antiga. Migration **125**, caso 2.
- [x] ~~Aplicar **125** e **126**.~~ **Resolvido 2026-10-01, e melhor do que o
      planejado.** A **126** foi aplicada (janela da Cassiane em SJM desde 15/09,
      `MANUAL`). A **125 NÃO foi aplicada e não precisa ser**: a operação corrigiu as
      duas ADEs **no extrator** e subiu a carga. `created_at` das duas linhas não mudou,
      então foi UPDATE no lugar, sem duplicar contrato, e o estado final é idêntico ao
      que a 125 afirmaria. Isso elimina o risco que a própria 125 registrava — correção
      no banco volta atrás na próxima carga; correção na origem, não.
- [ ] **Rematerializar:** `fn_materializar_caderno(8, 2026)` e `(9, 2026)`. A guarda de
      origem está em **0 nas duas competências** e `overlappingEligibleDays` em 0, mas
      resta o terceiro portão da 101: a conciliação por loja (R$ 0,01) entre
      `consultantProductivity.paidEffective` e `productivity.paidByConsultants`. Só a
      execução diz.
- [ ] **A 125 fica no repo como registro, marcada `NAO APLICAR`.** Decidir se vale
      manter ou remover — remover é chamada do usuário, não minha.
- [ ] **Corrigir a foto na origem** para CAMILLY, ANA CLARA e VICTOR. Enquanto o
      `HC_Colaboradores` trouxer a loja antiga, o dashboard mostra a pessoa na loja
      errada e qualquer rebuild do backfill recria a previsão — agora colidindo com
      `uq_cv_consultor_loja_aberta`, porque a janela certa passou a ser MANUAL.
      Confirmado: a planilha do repo (25/03) já lista CAMILLY em HELP COPACABANA e
      ANA CLARA em HELP SÃO JOÃO DE MERITI.
- [ ] **A planilha de HC não tem coluna de data de admissão.** Só FILIAL, VENDEDOR,
      STATUS e Obs. É por isso que `acao_adm = 'criar_janela'` da 095 nunca pôde ser
      usada e toda admissão aparece primeiro como bloqueio — a 119 (cinco pessoas) e a
      126 (Cassiane) fizeram à mão o serviço daquela porta.
- [ ] **Avaliar a CTE `transferidos` da 087.** Ela escreve inferência com cara de fato
      e errou 3 de 7. O lugar dela talvez seja o detector da 116, não o ledger.
- [ ] **Sexta checagem na 116:** janela aberta cuja loja não tem produção da pessoa na
      competência corrente, havendo produção em outra loja. Era o único sinal que teria
      pegado CAMILLY e ANA CLARA antes do bloqueio.
- [ ] **Medir pares de nomes a um caractere de distância** em `consultores`.
      MARCELA/MARCELLA não deve ser o único par, e o próximo erro desses só aparece no
      próximo bloqueio.
- [x] ~~**A correção da 125 é no banco, não na origem.**~~ **Resolvido:** a operação
      corrigiu na origem, não no banco. Era exatamente a saída certa.

## Fecho — tudo medido em 2026-10-01, depois da última carga

| | antes | depois |
|---|---|---|
| `fn_contar_pagamentos_sem_vinculo_origem(8, 2026)` | 17 | **0** |
| `fn_contar_pagamentos_sem_vinculo_origem(9, 2026)` | 164 | **0** |
| `sem_janela_aberta` (116) | 1 (Cassiane) | **0** |
| `divergencias` (116) | 3 | 4 — as fotos velhas, agora visíveis |

As quatro previsões numéricas bateram exatas depois de aplicadas as migrations:

| loja | peso | cabeças | pago set/2026 |
|---|---|---|---|
| HELP SÃO JOÃO DE MERITI | 2,0000 → **2,5714** | 2 → **3** | 514.038,38 (inalterado) |
| HELP RIO COMPRIDO | 3,9524 | 5 | 318.753,90 → **319.888,66** |
| HELP MEIER | 2,0000 | 2 | 206.013,17 → **205.249,85** |
| HELP LARANJEIRAS | 2,1429 | 3 | 458.597,03 → **458.225,59** |

Rede: peso 112,7618 → **113,3332**, cabeças 122 → **123**.

## Segunda rodada — os três vereditos (2026-10-01)

Depois da 106 e da 124, sobraram 3 eventos, **R$ 3.091,65**, 0,02% do mês, um contrato
cada. Nenhum tinha evidência unilateral; a operação decidiu os três no mesmo dia.

| caso | veredito | onde | efeito |
|---|---|---|---|
| ADE 979085158 | não é da MARCELA (desligada); é de **MARCELLA NUNES DEODATO** | 125 §1 | MEIER −763,32 → RIO COMPRIDO |
| ADE 10457301 | transferência de 04/09 **vale**; contrato na loja antiga | 125 §2 | LARANJEIRAS −371,44 → RIO COMPRIDO |
| CASSIANE | admissão em **15/09** | 126 | SJM peso 2,0000 → 2,5714 |

Decisões não óbvias desta rodada:

- **A 111 foi atropelada pelo calendário, não errou.** Ela foi escrita em 08/09
  registrando que "os últimos contratos em LARANJEIRAS são de 02/09 e 03/09". O
  contrato que bloqueou foi gravado em **09/09 13:18**, no dia seguinte. O aviso dela
  ("declarado vence inferido") agora corta para o outro lado: quem cede é o contrato.

- **Na 125 o contrato muda de loja E de cadastro.** `uq_consultores_nome_loja` dá a
  Mizael uma linha por loja; contrato em Rio Comprido apontando para o cadastro de
  Laranjeiras seria inconsistente para quem resolve o nome pelo `consultor_id` (a CTE
  `producao` da 116). A guarda da 105 não notaria — ela casa por `nome_normalizado` —
  e isso é razão para acertar os dois, não para deixar passar um.

- **Guarda nova nas duas correções de contrato:** a destinatária precisa ter vigência
  na loja na `data_cadastro`. Sem ela a correção só mudaria o furo de lugar.

- **Diferente da 106, aqui o valor fica no ranking.** Lá a produção foi para Patrícia,
  supervisora, e saiu de `paidByConsultants`. Marcella e Mizael são consultores: o
  numerador troca de loja e continua contando para alguém.

- **A queda de 22,2% em SJM é exata.** O numerador da loja não muda com a 126 — a
  produção da Cassiane já estava contada —, então a razão cai por `2,0000 / 2,5714`
  independente de escopo. Com o fallback de 24/09 a queda seria −10,6%, e errada.
  `origem = 'MANUAL'` conta como redução **declarada** na 091, logo fração pura, sem o
  piso de 50% que pegaria origem inferida — a lição que o registro de 23/09 deixou.

- **Os 164 se decompõem em 4 causas, não 1:** previsão da 087 (129), transferência não
  registrada (15), atribuição errada do ETL (2+17 de agosto) e admissão sem janela (1).
  Só a primeira era invisível às duas superfícies de controle.

## Referências

- Docs consultados: [business-rules.md](../business-rules.md), [data-layer.md](../data-layer.md)
- Registro anterior desta frente: [2026-09-23f](2026-09-23f-remocao-cadastro-indevido-matheus-phelipe.md)
- Migrations relacionadas: 086/087 (ledger e a CTE `transferidos`), 101 (snapshot
  individual), 105 (guarda de origem), 106 (reatribuição Iluara→Patrícia, pendente),
  116 (detector), 118 (molde da transferência MANUAL), 119 (admissões de setembro),
  121 (molde do `DELETE` no ledger)
