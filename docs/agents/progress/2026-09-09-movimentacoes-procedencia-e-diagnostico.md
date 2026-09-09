# 2026-09-09 — Movimentações: procedência no 3º ledger, doutrina única e detector

**Agente:** Claude Code
**Tipo:** research / feature
**Arquivos tocados:**
`database/migrations/113_supervisor_vigencia_origem.sql`,
`database/migrations/114_movimentacoes_rh_respeita_supervisor_manual.sql`,
`database/migrations/115_headcount_desligamento_fecha_por_producao.sql`,
`database/migrations/116_diag_vinculo_foto_x_ledger.sql`,
`database/migrations/117_fn_movimentacoes_replace.sql`,
`database/migrations/118_vigencia_transferencia_livia_penha.sql`,
`database/migrations/119_admissoes_setembro_cinco_consultores.sql`,
`database/migrations/120_validacao_de_data_sem_to_date.sql`,
e no `angry-man`: `src/services/import-movimentacoes-vinculo.ts` (novo),
`src/services/import-registry.ts`, `src/services/import-cadastros.ts`,
`src/lib/supabase.ts`, `src/lib/xlsx-parser.ts`,
`supabase/functions/reconquista-rpc/index.ts`,
`scripts/generate-templates.ts`, `docs/{importacao,schema,headcount,deploy}.md`,
`tests/unit/import-movimentacoes-vinculo.test.ts` (novo),
`tests/unit/xlsx-parser.test.ts`
**Commit(s):** (não commitado — **113–120 todas aplicadas** pelo usuário
em 2026-09-09 e verificadas contra o banco)

## Objetivo

Revisar como o projeto trata movimentações de consultores e supervisores,
dado que o dashboard consome tudo que o angry-man sobe, e propor ajuste na
forma de fazer upload de cargo, afastamento e desligamento.

## O que foi feito

**Revisão.** Mapeadas as quatro portas de escrita (`fn_headcount_replace`,
`fn_afastamentos_replace`, `fn_supervisores_replace`,
`fn_movimentacoes_rh_import`) mais uma quinta não declarada: o ETL de
contratos, que insere em `consultores` como efeito colateral. Seis lacunas
levantadas, todas verificadas no código — ver seção seguinte.

**Verificação das migrations 109–112**, aplicadas pelo usuário em 08/09.
As quatro bateram integralmente com as pós-condições dos próprios
cabeçalhos. Detalhe fora do esperado: JOYCE ganhou 6 contratos em
CASCADURA desde a medição de 08/09, **todos datados de 25–31/08** — carga
retroativa do ETL, não produção fantasma nova. A fronteira de 01/09
continua limpa (zero CASCADURA ≥ 01/09, zero LARGO < 01/09, zero
ALCANTARA). `fn_contar_pagamentos_sem_vinculo_origem`: 53 em 09/2026
(era 58 antes das migrations) e 17 em 08/2026.

**Oito migrations escritas** (113–120). As 113–119 foram aplicadas pelo
usuário em 2026-09-09 e verificadas contra o banco depois — `origem` criada
com 59 linhas `LEGADO`, as duas RPCs novas respondendo, LIVIA e as cinco
admissões no ledger, e o detector marcando `divergencias 0`,
`sem_janela_aberta 0`, `papel_sem_vinculo 0`. A **120** corrige o bug de validação de
data descrito abaixo e também foi aplicada: o bloco de verificação dela
rodou contra o banco e passou nos 12 casos — as quatro chamadas que antes
devolviam `22008` agora devolvem pendência de linha, ano bissexto (2028 e
2000) continua válido, século não bissexto (2100) é recusado, último dia
de cada mês passa, e a checagem de ordem segue funcionando.

**Lado angry-man** ajustado para consumir a porta nova — importador,
whitelist, template e envelopes. Detalhe na seção própria.

## Decisões não óbvias

- **`supervisor_vigencia` era o único ledger sem `origem`** (076), e por
  isso ficava fora das três guardas de "correção humana não se desfaz por
  carga de arquivo". O buraco é verificável na 100: a guarda
  `CORRECAO_MANUAL_EXISTENTE` consulta `consultor_vigencia` e
  `consultor_afastamento` e **não** consulta `supervisor_vigencia` — que a
  mesma função atualiza logo adiante sem condição nenhuma. A promoção do
  HUGO (110) era desfeita em silêncio pelo primeiro arquivo de RH que
  trouxesse o nome dele. **113** cria a coluna; **114** fecha a guarda.

- **Linhas antigas recebem `'LEGADO'`, não `'ETL'`** — decisão do usuário
  (sem backfill de procedência). 'LEGADO' afirma exatamente o que se sabe:
  procedência desconhecida. Marcar tudo como 'ETL' seria mais curto e
  diria uma inverdade sobre pelo menos cinco migrations conhecidas (078,
  081, 084, 088, 110). As linhas LEGADO seguem **sem proteção** — o
  comportamento delas não muda; a guarda vale só para o que vier depois.

- **`'BACKFILL_PRODUCAO'` entrou no CHECK de `supervisor_vigencia`** porque
  a 114 precisa dele: quando o desligamento fecha pela produção, a janela
  de supervisor fecha na mesma data derivada e a procedência tem de dizer
  que a data veio da produção. `'BACKFILL_PISO'` ficou de fora — não há
  piso de supervisão, e valor que nunca pode ocorrer não pertence a um
  CHECK.

- **Duas portas resolviam o mesmo conflito em direções opostas.** Produção
  digitada em ou depois do desligamento declarado: a 095 classificava
  `divergencia_producao` e **não escrevia**; a 100 **escrevia** a data
  derivada (último contrato + 1) e reportava. Decisão do usuário: vale a
  da 100 — produção prova presença. **115** leva a 095 para lá.

- **Na 115, `divergencia_manual` subiu para antes das cláusulas de
  produção.** Enquanto as duas apenas reportavam, a ordem era indiferente;
  agora a de produção **escreve**, e sem a inversão ela passaria por cima
  de uma janela MANUAL.

- **`recusada_ordem` passou a ser avaliada contra a data efetiva** — fechar
  em `último + 1` também não pode preceder o início de uma janela aberta.

- **A 115 não muda número nenhum hoje**: o `HC_Colaboradores` nunca foi
  importado (`consultor_vigencia` tinha zero linhas `origem='ETL'` em
  08/09, e essa é a única porta que as escreve). Mudar a função antes da
  primeira carga é o melhor momento possível.

- **O detector (116) diagnostica e não decide.** Em 08/09 a foto acertou 4
  das 5 divergências e **nada nos dados separava os casos**: JOYCE (erro de
  filial) e HUGO (promoção legítima) tinham forma idêntica. Uma função que
  escolhesse um lado erraria ~20% das vezes, escrevendo.

- **A CTE `foto` da 116 copia literalmente `consultores_mais_recentes`
  (092).** Deduplicar por outro critério acusaria divergências que a tela
  não mostra e perderia as que mostra.

- **A porta nova (117) é função nova, não parâmetro na 100.** A 082 já
  documenta a armadilha: `CREATE OR REPLACE` casa por assinatura, então
  parâmetro novo com DEFAULT cria uma **segunda** função e a chamada de 3
  argumentos do angry-man fica ambígua. Custo declarado: RPC nova = 2
  registros na whitelist + redeploy da Edge Function.

- **A 117 escreve `origem = 'MANUAL'`, não `'ETL'`** — decisão de projeto,
  não descuido. Não é carga em massa: é a operação declarando um evento
  por vez, que é o que as 109–112 fazem. E `MANUAL` é o que **imuniza**:
  o rebuild do backfill (087) apaga só `BACKFILL%`, e
  `fn_supervisores_replace` fecha supervisão por **ausência** na planilha
  (082) — uma promoção gravada como ETL seria desfeita pelo primeiro
  import em que a Supervisores.xlsx ainda não listasse a pessoa. O custo
  do outro lado: supervisão MANUAL não fecha por planilha; encerrar passa
  a ser `REBAIXAMENTO` ou `fn_aplicar_mudanca_supervisor(..., 'FIM')`.

- **Produção do lado errado da fronteira reporta, não bloqueia (117).** A
  109 exigia fronteira limpa e abortava; como regra geral isso teria
  recusado a transferência da CAROLINA por **1 contrato avulso** no dia da
  virada. Mesmo erro que a 100 corrigiu do outro lado (6 desligamentos
  bloqueando 25). Sai em `divergencias` com a contagem exata.

- **A 117 não mexe em `consultores`.** `uq_consultores_nome_loja` é
  (nome, loja_id): "mover" seria UPDATE que colide quando já existe linha
  no destino, ou INSERT que cria mais uma duplicata. A 109 mostrou o
  tamanho do problema (FK `ON DELETE SET NULL` em `contratos`,
  `ON DELETE CASCADE` em `usuario_escopos`). Foto e ledger têm portas
  separadas — e uma transferência declarada antes da primeira produção na
  loja nova vai aparecer no detector até o ETL criar o cadastro. Nesse
  caso o **ledger** é que está certo.

- **`PESSOA_DUPLICADA` na 117 recusa duas movimentações da mesma pessoa
  na mesma carga.** A temp `mv` resolve o estado de todos **antes** de
  escrever, então a segunda linha leria uma foto vencida. Duas
  movimentações exigem duas cargas em ordem cronológica. CAROLINA e THAIS
  (112) são duas *pessoas* numa carga, o que funciona.

## Medição do detector — 2026-09-09

Rodada por reimplementação da mesma lógica em Python contra o banco real,
antes de aplicar a 116. 437 linhas em `consultores`, 336 pessoas após
dedup, 175 ativas.

| Lista | N | Quem |
|---|---|---|
| `divergencias` | 1 | LIVIA GOMES DE SANT ANNA |
| `sem_janela_aberta` | 5 | BRUNO, GISELLE, MARIA LUISA, MATHEUS, STEPHANIA |
| `multiplas_janelas` | 0 | — |
| `cadastros_orfaos` | 2 | LETICIA MAESSE, RENATA BUAS |
| `papel_sem_vinculo` | 0 | — |

As cinco divergências de 08/09 saíram (109–112 aplicadas). **O que entrou
no lugar, em um único dia, é o argumento da revisão inteira:**

- **LIVIA** — cadastro (LIVIA, HELP PENHA) **criado em 09/09** pelo ETL de
  contratos, forma idêntica ao caso JOYCE. Ledger diz BONSUCESSO desde
  12/05 (`BACKFILL_PRODUCAO`); 09/2026 está partido em 5 contratos
  BONSUCESSO e 5 PENHA. A regra da "loja dominante do mês" (087) **empata**
  aqui, como empatava na CAROLINA (112).
- **Os cinco sem janela não têm janela nenhuma, nem fechada** — cadastros
  criados em 08 e 09/09, produzindo só em 09/2026. São admissões novas.
  Como a 091 lê só o ledger, cada um está no **numerador** e fora do
  **denominador**: a média da loja sobe por gente que existe e não é
  contada.

## Pendências / follow-ups

- [x] Aplicar **113 → 120**. Feito em 2026-09-09, na ordem, e verificado
      contra o banco depois de cada bloco.
- [ ] **Rematerializar o Caderno de 08/2026 e 09/2026** — o único passo
      que ficou. A 119 mexe em agosto, competência **já publicada**: o
      denominador de NOVA IGUAÇU, PRAÇA SECA e MADUREIRA cresce +0,3810 /
      +0,2381 / +0,2381 e a produtividade das três **cai**, porque as
      pessoas entram com peso e produção zero no mês. Está correto — elas
      estavam contratadas — mas é mudança visível em número publicado, e
      enquanto o Caderno não for rematerializado ele diverge do dashboard.
- [x] **Redeploy da Edge Function** `reconquista-rpc` — feito em
      2026-09-09, **v8 → v9**, `verify_jwt` preservado em `false`.
      Smoke-test pós-deploy: POST sem token devolve 401 e GET devolve 405,
      as duas respostas do fonte que subiu. O diff era puramente aditivo
      (2 entradas na whitelist + comentários). Falta o teste ponta a ponta
      pelo modo web, que exige login de admin/gestor no app.
- [x] **Revisar o angry-man** — feito em 2026-09-09. Escopo coberto: (a) `fn_movimentacoes_replace`
      precisa de importador novo e de 2 registros na whitelist da Edge
      Function `reconquista-rpc`; (b) `import-cadastros.ts` não lê os
      campos que a 115 acrescentou (`aplicados_por_producao`,
      `divergencias_aplicadas`) nem o `manuais_preservadas` da 113 —
      quem importa não vê que a data gravada difere da que digitou;
      (c) `import-movimentacoes-rh.ts` já tratava `divergencias` e serviu
      de modelo. Além do escopo previsto, saiu daí o bug de validação de
      data (seção própria) e a correção do atalho ISO em `parseBRDate`.
- [x] **LIVIA** — resolvido. Operação confirmou em 2026-09-09:
      transferida para HELP PENHA em **04/09/2026**; até 03/09 era de
      BONSUCESSO. Fronteira medida **limpa e disjunta** (BONSUCESSO
      02–03/09 ×5, PENHA 04–08/09 ×5, zero dos dois lados errados), então
      declarado e inferido coincidem — diferente da JOYCE e da CAROLINA.
      Migration **118** escrita, não aplicada.
- [x] **Os cinco sem janela** — resolvido. Operação informou as datas em
      2026-09-09; migration **119** escrita, não aplicada.

      | Pessoa | Loja | Admissão | 1º contrato | Gap |
      |---|---|---|---|---|
      | STEPHANIA LANA LOPES | NOVA IGUAÇU | **20/08** | 04/09 | 8 DU |
      | BRUNO VINICIUS MARTINS DA SILVA | PRAÇA SECA | **25/08** | 04/09 | 5 DU |
      | MARIA LUISA DE MORAIS BRANDAO | MADUREIRA | **25/08** | 08/09 | 5 DU |
      | GISELLE GALVAO DE FARIAS | BONSUCESSO | **04/09** | 04/09 | — |
      | MATHEUS DUTRA DOS SANTOS DE OLIVEIRA | CAXIAS GUANABARA | **04/09** | 04/09 | — |

      **Três das cinco foram admitidas antes de vender** — é a "admissão
      censurada" da 087 acontecendo ao vivo, e a medida exata do que o
      fallback do primeiro contrato perderia. Nenhuma tem contrato antes
      da própria data declarada, então não há `divergencia_producao`.
- [ ] **Migration 106 continua NÃO aplicada** — ILUARA ainda tem os 17
      contratos de 18/08, e `fn_contar_pagamentos_sem_vinculo_origem(8,
      2026)` marca exatamente 17 por causa disso. A 107 não foi conferida.
- [ ] **BARBARA DE SOUZA PECANHA** (follow-up da 110, ainda aberto):
      `consultor_vigencia` aberta em MADUREIRA desde 2025-10-06
      (`BACKFILL_PRODUCAO`), produção zero desde 07/2026 (3 contratos em
      06/2026, 1 em 07/2026). Entra no denominador de MADUREIRA em 09/2026
      com peso 1,0.
- [ ] **`docs/HEADCOUNT_ETL.md` precisa da §4.4 atualizada** quando a 115
      for aplicada: a assimetria descrita ali ("datas de
      admissão/desligamento avisam e seguem") passa a valer só para
      admissão e para o caso acima de 30 dias.
- [ ] **Espelho na admissão, não decidido.** A 095 ainda classifica
      contrato *antes* da admissão declarada como `divergencia_producao`
      sem escrever. Sob "produção prova presença" o simétrico seria puxar
      o início da janela para o primeiro contrato — mas isso muda número
      já publicado em outra direção, e não foi o que o usuário decidiu.

## Bug encontrado ao exercitar a 117 — data impossível explode em vez de virar pendência

Descoberto rodando `fn_movimentacoes_replace` contra o banco real em
dry-run, depois de aplicada. As duas portas de movimentação validavam data
em três fases, e a terceira era um round-trip
`to_char(to_date(t,'YYYY-MM-DD'),'YYYY-MM-DD') <> t`, escrito para pegar
31/02 supondo que `to_date` normalizaria para 03/03.

**Ele não normaliza.** Nesta versão do PostgreSQL `to_date` **lança** para
valor fora de faixa, então a comparação nunca acontece e a exceção sobe.
Medido:

| Chamada | Resultado |
|---|---|
| `fn_movimentacoes_rh_import` afastamento `2026-02-31` | `22008` |
| `fn_movimentacoes_rh_import` desligamento `2026-04-31` | `22008` |
| `fn_movimentacoes_rh_import` desligamento `2026-02-29` | `22008` |
| `fn_movimentacoes_replace` transferência `2026-02-31` | `22008` |

O defeito é **pré-existente na 097** e foi herdado pela 117 ao copiar o
desenho. Nada é escrito errado — a transação aborta — mas quebra o
contrato "pendência por número de linha": quem importa recebe
`date/time field value out of range` sem linha e sem causa. E o arquivo de
RH é digitado à mão a partir de e-mails, onde 31/04 acontece.

**Migration 120** corrige as duas comparando o dia com o último dia real
do mês via `make_date(ano, mes, 1) + interval '1 month' - interval '1 day'`,
sem chamar `to_date` nenhuma vez. `pg_catalog.date_part('day', ...)` e não
`extract(day FROM ...)`: `EXTRACT` é construção do parser e não aceita
qualificação de schema, que é obrigatória sob `SET search_path = ''`.

**O caminho era alcançável pela UI.** `parseBRDate` recusa `31/04/2026`
(caminho BR faz round-trip com `new Date`) mas deixava passar
`2026-04-31` — o atalho ISO só conferia a faixa 1..31, e os templates
aceitam as duas grafias explicitamente. Corrigido em
`src/lib/xlsx-parser.ts` com o mesmo padrão de round-trip já usado na
própria função, agora em UTC para não reintroduzir o shift de fuso que o
atalho existia para evitar.

## Lado angry-man (2026-09-09)

- **Importador novo** `import-movimentacoes-vinculo.ts` → card
  "Transferências e Cargo". Dry-run, tudo-ou-nada, tradução dos 15 códigos
  de pendência, divergências de produção visíveis sem bloquear.
  7 testes.
- **Diferença deliberada em relação ao importador de RH:** lá grafia de
  loja desconhecida vira aviso agregado (a loja é informativa); aqui
  derruba a linha, porque a loja **é** a movimentação.
- **Whitelist da Edge Function** `reconquista-rpc` +
  `RPC_ENDPOINT_MAP`: `fn_movimentacoes_replace` e
  `fn_diag_vinculo_divergente`. **Exige redeploy** — sem ele o modo web
  recusa com HTTP 400 e o Electron funciona, então o bug aparece só para
  metade dos usuários. Documentado em `docs/deploy.md`, que não tinha o
  comando em lugar nenhum.
- **Envelopes atualizados** em `import-cadastros.ts`: `manuais_preservadas`
  (113) e `aplicados_por_producao` / `divergencias_aplicadas` (115). A
  mensagem de desligamento divergente foi reescrita — antes dizia sempre
  "não aplicado", que depois da 115 só vale acima de 30 dias.
- **Template** `Movimentacoes_Vinculo` (xlsx + csv) com as regras na aba
  `Instrucoes`.

## Estado final medido — 2026-09-09, com as 113–120 aplicadas

| Detector | N |
|---|---|
| `divergencias` | 0 |
| `sem_janela_aberta` | 0 |
| `multiplas_janelas` | 0 |
| `cadastros_orfaos` | 2 (LETICIA, RENATA — informativo) |
| `papel_sem_vinculo` | 0 |

Procedência nos três ledgers:

- `consultor_vigencia` — 261 `BACKFILL_PRODUCAO`, 123 `BACKFILL_CENSURADO`,
  **25 `MANUAL`** (eram 9 em 08/09; 109–112, 118 e 119 somaram 16),
  1 `BACKFILL_PISO`
- `supervisor_vigencia` — 59 `LEGADO`, como a 113 previa
- `consultor_afastamento` — 1 `MANUAL`, 1 `ETL`

`fn_contar_pagamentos_sem_vinculo_origem`: **44 em 09/2026** — era 58 em
08/09, caiu a 53 com as 109–112, e a 118 (contratos da LIVIA em PENHA) mais
a 119 (as cinco admissões) levaram aos 44. **17 em 08/2026**, inalterado,
porque a migration 106 continua não aplicada.

## Referências

- Docs consultados: [HEADCOUNT_ETL.md](../../HEADCOUNT_ETL.md),
  [business-rules.md](../business-rules.md), [data-layer.md](../data-layer.md)
- Migrations: 076/082 (supervisor), 086/087 (consultor_vigencia),
  089/090 (afastamento), 094/095 (`fn_headcount_replace`),
  097/099/100 (`fn_movimentacoes_rh_import`), 105 (padrão de diagnóstico),
  109–112 (as correções manuais verificadas aqui)
- Entradas relacionadas:
  [2026-09-08-cadastro-por-nome-loja-cria-pessoa-nova.md](2026-09-08-cadastro-por-nome-loja-cria-pessoa-nova.md),
  [2026-08-25-headcount-guardas-cadastro.md](2026-08-25-headcount-guardas-cadastro.md)
