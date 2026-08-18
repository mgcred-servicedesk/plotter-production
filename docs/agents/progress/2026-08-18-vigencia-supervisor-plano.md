# 2026-08-18 — Vigência temporal de supervisor: diagnóstico e plano

**Agente:** Claude Code
**Tipo:** research + feature (076-079 APLICADAS e verificadas em 2026-08-18;
Python escrito, deploy pendente)
**Arquivos tocados:** `database/migrations/076_supervisor_vigencia.sql`,
`077_fn_manutencao_supervisor_vigencia.sql`,
`078_supervisor_vigencia_correcoes_historicas.sql`,
`079_caderno_supervisor_point_in_time.sql`, `src/dashboard/loaders.py`,
`src/dashboard/kpis/comparativos.py`, `src/dashboard/chat_ia/tools.py`,
`tests/test_kpis_comparativos.py`
**Commit(s):** (esta sessão)

## Objetivo

Usuário levantou que o cálculo de consultores ativos ao longo do tempo
confronta a lista de vendedores da loja com a tabela `supervisores` e
omite quem casa — mas o caso de **consultor promovido a supervisor** não
foi previsto no design do banco. Pesquisar e planejar uma melhoria.

## Diagnóstico

`supervisores` é uma **foto do presente** (a 063 reforçou: foto única,
quem sai da planilha deixa de existir), aplicada como filtro
**retroativo sobre toda a história**. O papel não tem dimensão temporal,
então o erro é bidirecional:

1. **Promoção** (consultor → supervisor): ao entrar na planilha, todos os
   meses em que a pessoa vendia como consultor são apagados das visões
   consultor-level. O headcount da loja cai em 1 **nos meses passados**, a
   média por consultor daqueles meses infla, e a produção dela sai do
   total em `calcular_medias_du_por_nivel` e
   `calcular_assertividade_consultores` (`kpis/gerais.py`).
2. **Saída da supervisão** (desligamento/rebaixamento): ao sair da
   planilha, os meses em que a pessoa **era** supervisor voltam a poluir o
   ranking de consultores.

A direção (2) **já está viva em produção**: os 5 ex-supervisores que o doc
[2026-07-08](2026-07-08-universo-consultores-dedup-e-vai-e-vem.md) mandava
explicitamente NÃO deletar ("mantê-los é necessário p/ excluir a produção
histórica deles") foram removidos pelo replace-style da
[063](../../../database/migrations/063_fn_supervisores_replace.sql):
ALANA SOUZA DO NASCIMENTO, LEONARDO MEYER ROLY, MICHELE TINOCO DA
CONCEICAO, TALITA PINTO DA SILVA, THAIS REBELLO DE ALMEIDA — **86
contratos** entre 05/2025 e 03/2026 voltaram a contar como produção de
consultor. O mesmo doc já previa o desfecho: "Risco só se algum for
recontratado como consultor — aí seria caso de vigência temporal, como
loja_regiao_vigencia."

O mesmo vale para a **loja** do supervisor: a atribuição é sempre à loja
atual, nunca à que ele supervisionava na competência — foi exatamente o
que a [062](../../../database/migrations/062_conciliar_supervisores_rh.sql)
corrigiu à mão, caso a caso.

### Estado verificado no banco (leitura, 2026-08-18)

| Verificação | Resultado |
|---|---|
| `supervisores` | 47 linhas, 47 nomes distintos |
| Também constam como consultor **ativo** no RH | 44 dos 47 |
| Contratos de supervisores atuais na base | 6.129, em 15 competências (05/2025 → 08/2026) |
| Datas nas planilhas de origem | **nenhuma** — `HC_Colaboradores.xlsx` = FILIAL/VENDEDOR/STATUS/Obs; `Supervisores.xlsx` = LOJA/SUPERVISOR/REGIÃO |

Consequência da última linha: **o backfill não pode ser derivado**. A
vigência só pode ser capturada no evento (daqui pra frente) ou informada
manualmente para os casos conhecidos.

## Decisões tomadas (usuário, nesta sessão)

- **Âncora temporal = competência, ÚLTIMO dia** (revisado ainda em
  2026-08-18 — ver "Revisão da âncora" abaixo). A escolha original está
  registrada logo em seguida, com o motivo da troca.
- ~~**Âncora temporal = competência, 1º dia.**~~ O papel vigente no dia 1º
  vale para o mês inteiro. Promovido em 20/jul → julho fecha como
  consultor (produção conta, entra no denominador), agosto é o 1º mês como
  supervisor. Uma regra só para produção e headcount — descartada a data
  exata do contrato (`data_cadastro`), que deixaria o mês internamente
  inconsistente: a pessoa apareceria no ranking de julho e fora do
  headcount de julho ao mesmo tempo.
- **Backfill = congelar + corrigir casos conhecidos.** Piso `2020-01-01`
  para todos (reproduz exatamente o número de hoje) + correção pontual com
  datas reais das promoções conhecidas e das 5 saídas. Descartado
  "corrigir tudo com datas do RH" (mudaria números já publicados sem
  necessidade) e "só congelar" (deixaria os 86 contratos errados de pé).
- **Escopo = só vigência de supervisor.** Vigência do roster de
  consultores (admissão/desligamento) e modelo genérico de cargo ficam
  como track separado.

## Revisão da âncora (mesma sessão)

A âncora do 1º dia produzia um resultado indefensável em **08/2026**:
LETICIA ALVARENGA GOMES FREITAS e PAMELA CRISTINA MOREIRA DE PAIVA, ambas
**desligadas em 04/08**, apareciam como supervisoras do mês inteiro,
enquanto quem assumiu e de fato fechou agosto (MARIANA em BELFORD ROXO SÃO
JOSÉ, DJANE em RAMOS, EVILLYN em COPACABANA, RAIANE em COPACABANA NOVA) só
entraria em setembro. Usuário confirmou a troca para o **fim da
competência**: quem fechou o mês responde por ele.

Ponto que tornou a troca barata: **não exige mentir nas datas**. As
vigências seguem gravadas com a data real do evento (RAIANE 18/08, cascata
04/08); muda só a pergunta que o leitor faz ao ledger. Por isso a âncora é
reversível — trocar de volta é reescrever uma CTE, não o histórico.

Migration **085** (v1.6) + `carregar_supervisores(mes, ano)`. Efeito
medido: **07/2026 é a única competência fechada que muda** (ERICA vira
supervisora, EMANUELE deixa de ser → `sup` 43→44, `ativos` 118→117);
06/2026 e anteriores intocados; 08/2026 nasce com a regra nova. Exige
**republicar 07/2026** (`fn_materializar_caderno(7, 2026)`), já que o
Caderno é congelado.

Convenção de borda: janela meio-aberta `[início, fim)` — quem encerra
exatamente no último dia do mês não cobre esse dia, e o mês fica com o
sucessor.

## Plano aprovado

Reusa o desenho que o projeto já validou para loja→região (043 → 049), em
vez de inventar outro: `supervisores` continua sendo o ponteiro do
organograma **atual** (papel de `lojas.regiao_id`), e um ledger SCD2 guarda
as janelas.

Ver DDL final em
[076_supervisor_vigencia.sql](../../../database/migrations/076_supervisor_vigencia.sql).
Pontos do desenho:

- Chave = **nome normalizado**, não FK: é a moeda de identidade que o
  codebase inteiro já usa (`supervisores` nunca teve vínculo com
  `consultores`). A coluna é **gerada** a partir de `nome`
  (`GENERATED ALWAYS AS ... STORED`), então as duas nunca divergem e o
  match deixa de depender do ETL uniformizar espaços/caixa — resolve de
  quebra o follow-up pendente da
  [2026-07-09](2026-07-09-supervisor-como-consultor-exclusao-global.md)
  ("match exato funciona porque o ETL uniformiza").
- **Granularidade (pessoa, loja)**, não (pessoa): corrigido durante a
  implementação da 076. `supervisor multi-loja` é regra documentada
  ("soma os consultores de todas as suas lojas",
  [business-rules.md](../business-rules.md)), então um índice único por
  pessoa proibiria duas linhas abertas legítimas. O índice parcial
  `uq_sv_supervisor_loja_aberta` espelha `uq_supervisores_nome_loja`, com
  `coalesce` no `loja_id` porque UNIQUE com NULLS DISTINCT não dispara —
  foi assim que o import antigo duplicava linhas de loja nula (063).
- **Sem `regiao_id`**: a região point-in-time já vem de
  `loja_regiao_vigencia` (043) via loja. Replicar aqui criaria uma segunda
  fonte de verdade que a 063 tinha acabado de centralizar em
  `lojas.regiao_id`.

| # | O quê | Efeito no número publicado |
|---|---|---|
| **076** ✅ escrita | Tabela + índices + RLS leitura (padrão 043) + backfill: 1 linha aberta por supervisor atual com piso `2020-01-01` | **Nenhum** — no-op observável, nada consome ainda |
| **077** ✅ escrita | `fn_aplicar_mudanca_supervisor(nome, loja, data_efetiva, ação)` (padrão 049) + `CREATE OR REPLACE fn_supervisores_replace`: para de dar DELETE cego, passa a diferenciar a planilha contra as linhas abertas e fechar/abrir vigências | Nenhum |
| **078** ✅ escrita | Correções de história: 3 promoções + saída da Pamela + reabertura dos 5 ex-supervisores | Muda os meses corrigidos, **depois que a 079 entrar** |
| **079** ✅ escrita | `CREATE OR REPLACE obter_caderno_fechamento` (v1.5) — resolve supervisor por vigência na competência | Muda `supervisorsExcluded` de meses passados |

Diff da 079 contra a 075: **uma única CTE** (`supervisores_normalizados`
passa a ler o ledger na âncora `make_date(p_ano, p_mes, 1)`) + comentários.
O resto das ~450 linhas é byte-idêntico. Delta esperado, verificado contra o
banco em 2026-08-18: 06/2026 `supervisorsExcluded −3` / `activeConsultants
+3`; 08/2026 `−2` / `+2` (TAMIRES já era supervisora desde 01/07); 09/2026
sem diferença. `activeRegistered` e `backofficeExcluded` não mudam em
competência nenhuma.

**Python (escrito, deploy só depois das migrations):**

- `carregar_supervisores(mes, ano)` lê `supervisor_vigencia` na âncora do
  1º dia, com `.or_("vigencia_fim.is.null,vigencia_fim.gt.<âncora>")`. O
  contrato do frame não mudou (`SUPERVISOR`/`LOJA`/`REGIAO`), então os 16
  pontos de `excluir_supervisores` não foram tocados. `REGIAO` passa a vir
  da região atual da loja — o ledger não guarda região de propósito.
- `calcular_evolucao_por_entidade` ganhou `df_supervisores_ant`, com
  fallback para `df_supervisores` quando omitido (preserva o
  comportamento anterior).
- `chat_ia/tools.py` **já carregava** `df_sup_cmp` e o descartava, com
  comentário dizendo que usá-lo "exigiria um segundo parâmetro na função
  de comparação; fora de escopo do MVP". Agora ele é passado.
- 3 testes novos em `test_kpis_comparativos.py` (promoção, fallback e
  saída da supervisão). Suíte: 565 passando, ruff limpo.

> **Ordem de deploy:** migrations 076→079 primeiro, código depois.
> `carregar_supervisores` referencia `supervisor_vigencia`, que não existe
> até a 076 rodar — subir o código antes quebra o dashboard.

**Alavanca que torna isso barato:** `carregar_supervisores()` tem só 2
chamadores (`loaders.py:1596`, dentro de `_executar_consolidacao(mes,
ano)`, e `loaders.py:2585`) e **ambos já vivem em contexto de
competência**. Os 16 pontos de `excluir_supervisores` herdam a
temporalidade sem edição. Único ajuste manual:
`calcular_evolucao_por_entidade` (`kpis/comparativos.py`) passa a receber
duas listas em vez de uma — a docstring já sinalizava o ponto ("o mesmo
`df_supervisores` recorta os dois períodos; o chamador escolhe qual
cadastro usar").

### Dados das promoções (usuário, 2026-08-18)

| Pessoa | Loja | Data efetiva | 1º mês como supervisor (âncora dia 1º) | Produção que volta a contar |
|---|---|---|---|---|
| LINDOMAR GLAUBER DA COSTA ALVES | HELP RIO COMPRIDO | 2026-08-04 | 09/2026 | 1.137 contratos / R$ 1.488.195,64 / 15 competências |
| TAMIRES MARQUES PAULOCINIO | PDV CAMPO GRANDE CF CASTRO | 2026-07-01 | 07/2026 | 1.139 contratos / R$ 1.412.655,34 / 13 competências |
| EVILLYN DE OLIVEIRA ALVES | HELP COPACABANA | 2026-08-04 | 09/2026 | 928 contratos / R$ 1.294.156,68 / 15 competências |

E na direção oposta, produção que volta a ser **excluída**: PAMELA, 492
contratos / R$ 565.500,76 / 11 competências — a saída dela da foto
devolveu o passado de supervisora aos rankings de consultor.

Três coisas apareceram na verificação contra o banco e mudaram o dado
informado:

1. **Grafia da TAMIRES.** Informada como "TAMIRES MARQUES PAULOCINIO DA
   SILVA"; `supervisores`, `consultores` e os contratos gravam **TAMIRES
   MARQUES PAULOCINIO**. Usuário confirmou manter a grafia do banco — o
   ledger casa por nome normalizado, então o "DA SILVA" faria a vigência
   nunca encontrar a produção dela.
2. **EVILLYN não estava em `supervisores`** — a planilha não tinha
   registrado a promoção. Usuário corrigiu a tabela em 2026-08-18
   (EVILLYN dentro, PAMELA fora; segue com 47 linhas). Desambiguação da
   loja: existem **duas** lojas ativas parecidas — HELP COPACABANA (era da
   PAMELA) e HELP COPACABANA NOVA (é da RAIANE). A informada bate com o
   cadastro dela, movido para lá em 11/08, mesma data do desligamento da
   PAMELA.
3. **PAMELA CRISTINA MOREIRA DE PAIVA** ficaria com vigência aberta para
   sempre: sucedida pela EVILLYN e `Desligado (a)` desde 11/08 — é o único
   nome de `supervisores` com cadastro não-ativo. Encerrada em 2026-08-04
   (a passagem de bastão). A data exata é **imaterial**: sob a âncora do
   dia 1º, 04/08 e 11/08 caem os dois em agosto, e ela não produz desde
   05/2026.

### Backfill dos 5 ex-supervisores

Não estão mais em `supervisores`, então o piso da 076 não os alcança —
entram na 078 como linhas **já fechadas** `[2020-01-01, 2026-07-01)`, a
competência da planilha em que o usuário confirmou os desligamentos. A data
é **imaterial**: os cinco estão `Desligado (a)` no RH (fora do headcount) e
nenhum produz depois de 03/2026, então qualquer data ≥ 2026-04-01 dá o
mesmo número.

**Loja:** só a TALITA PINTO DA SILVA tem loja identificada — usuário
informou que ela veio do backoffice e por último exercia o papel de
supervisora do **DIGITAL** até ser desligada (bate com o cadastro: VAI E
VEM antigo, DIGITAL `Desligado (a)` em 11/08). Vale lembrar que DIGITAL
não é backoffice para efeito de métrica — VAI E VEM está fora das médias,
DIGITAL conta. Os outros 4 ficam com `loja_id NULL`: cada um tem dois
cadastros apontando lojas diferentes e `supervisores` não os tem mais, então
não há evidência. Como a exclusão histórica é **por nome**, a loja não muda
nenhum resultado — inferi-la do cadastro conflitante seria fabricar dado.

## Premissas a validar

- **Produção sempre vem de `contratos`** (confirmado pelo usuário em
  2026-08-18): consultor **e** loja saem do próprio contrato
  (`v_contratos_dashboard.consultor` / `.loja`), nunca do cadastro. O
  ledger só decide *se aquele nome é filtrado* na competência; não
  filtrado, aparece a produção lançada em nome dele, na loja em que foi
  lançada. Só o **denominador** (headcount) lê o cadastro.
- **Consequência medida — o denominador desalinha do numerador.** Como o
  headcount usa a loja do cadastro ATUAL, quem trocou de loja tem o head
  numa loja e a produção em outra. Medição em 03/2026 (loja principal de
  produção vs. cadastro atual): **18 de 109** consultores ativos que
  produziram estão desalinhados — LINDOMAR produziu em HELP SÃO JOÃO DE
  MERITI com cadastro em HELP RIO COMPRIDO (136 contratos), TAMIRES em
  HELP CAMPO GRANDE ESTAÇÃO com cadastro em PDV CAMPO GRANDE CF CASTRO
  (194), e assim por diante. Para LINDOMAR isso vale em **14 das 15**
  competências.
  Efeito da 079 nesses três: eles saem de "ausentes do denominador"
  (excluídos como supervisores) para "presentes, porém na loja errada"
  em meses passados. O total da organização fica **mais** correto; a
  produtividade **por loja** ganha um head sem produção correspondente.
  Não é uma classe nova de erro — os outros 15 já estão assim hoje —, mas
  é o argumento mais forte a favor do track de vigência do roster.
- **Limite conhecido do escopo escolhido:** o headcount de um mês passado
  continua saindo do **roster de hoje**. A 079 torna point-in-time a
  *classificação de papel*, não o universo — quem for desligado depois
  some do denominador daquele mês retroativamente. A identidade auditável
  da [075](../../../database/migrations/075_caderno_universo_consultores_auditavel.sql)
  (`activeRegistered = activeConsultants + supervisorsExcluded +
  withoutActiveStore + backofficeExcluded`) continua fechando: segue sendo
  uma partição do cadastro ativo atual, agora particionado pelo papel da
  época.
- **Data real no ledger, âncora só na leitura** (decidido ao escrever a
  077): o ledger guarda a data do evento (04/08 = 04/08) e a âncora do 1º
  dia é regra de *leitura*, aplicada na 079. Assim o ETL não precisa
  conhecer a âncora — promovido em 04/08 ou importado em 18/08, os dois
  caem em agosto e a leitura resolve igual. E a âncora fica reversível:
  mudar a regra é reescrever a 079, não o histórico.
- **`fn_supervisores_replace` manteve a assinatura `(p_rows jsonb)`** e
  deriva a data efetiva de `current_date`. Acrescentar um parâmetro com
  DEFAULT criaria uma *segunda* função (CREATE OR REPLACE casa por
  assinatura) e a chamada de 1 argumento do angry-man ficaria ambígua
  ("function is not unique"). Consequência prática: **o angry-man não
  precisa de redeploy** nesta rodada.

## Pendências / follow-ups

- [ ] **Usuário:** rodar a 076 no SQL Editor (bloco de verificação no
      rodapé da migration). Não foi executada nem validada contra um
      Postgres — não há instância local, e DDL em produção é decisão sua.
- [x] Usuário forneceu as 3 promoções (tabela acima) e a loja da TALITA.
- [x] Usuário corrigiu `supervisores` no banco em 2026-08-18 (PAMELA
      fora, EVILLYN em HELP COPACABANA). A 078 foi tornada
      **independente da ordem** por causa disso: cada caso corrige a linha
      se ela existe e cria se não existe.
- [x] Correção feita **via import do angry-man**, ou seja na origem
      (`configuracao/Supervisores.xlsx`) — sem risco de revert pelo próximo
      import. Confirmado pelo usuário em 2026-08-18.
- [ ] Verificar se há outras promoções não informadas. Candidatos por
      produção que só começa em 2026 — sinal fraco, não distingue promoção
      de contratação nova: GLEICIANE DA PENHA (03/2026), ROBERTA PEIXOTO
      LAZARO (04/2026), WESLEY STELLET LIMA.
- [ ] angry-man (opcional, não bloqueia): passar a data efetiva real da
      mudança em vez de depender do `current_date` da 077.
- [ ] **Achado fora do escopo, não corrigido:**
      `chat_ia/tools.py:84` chama `aplicar_rls_supervisores(df_sup_cmp,
      df_cmp)`. É exatamente o defeito 1 do doc
      [2026-07-09](2026-07-09-supervisor-como-consultor-exclusao-global.md):
      recortar por escopo a lista que serve **só para exclusão** faz
      supervisor vazar como consultor para `gerente_comercial`/`supervisor`.
      O `app.py` removeu essas chamadas por esse motivo; o chat de IA
      (criado em 08/2026) reintroduziu a única que existe hoje. Com
      `df_supervisores_ant` agora em uso, o vazamento passa a valer também
      para o período de comparação. Correção sugerida: remover a chamada
      (a lista de exclusão é sempre global). **Não alterado** — decisão do
      usuário, fora do escopo desta tarefa.
- [x] Testes de vigência em `test_kpis_comparativos.py` (3 novos).
- [x] **076-079 aplicadas no Supabase em 2026-08-18** e verificadas em
      leitura: `supervisor_vigencia` com 53 linhas (47 abertas + 6
      fechadas), invariante `abertas == foto` fechando, as 3 promoções com
      as datas reais, PAMELA fechada em 2026-08-04, os 5 ex-supervisores
      fechados em 2026-07-01, 44 pisos 2020-01-01 restantes. Caderno:
      01 e 06/2026 → 119 ativos / 42 supervisores; 08/2026 → 118 / 43 (a
      diferença é a TAMIRES, supervisora desde 01/07). Identidade auditável
      fecha nas três competências. Delta vs. 075 confirmado (+3 em junho,
      +2 em agosto).
- [ ] Deploy do código Python (depende só das migrations, já aplicadas).
- [x] Performance do Caderno → **migration 080** (materialização). A 1ª
      chamada de `obter_caderno_fechamento` estourou o statement timeout e as
      seguintes levaram 3,6–4,3s; o tempo é praticamente plano por
      competência (custo fixo). O bereshit já convivia com isso via retry de
      57014. Decisão do usuário: Caderno serve **só meses fechados**, mês
      vigente vira projeção (registrada como Fase 7 em
      `bereshit/docs/PLANO_EVOLUCAO_UI_UX.md`).
- [x] **Caso ALCÂNTARA CARREFOUR → migration 081 escrita.**
      Reportado pelo usuário em 2026-08-18 e confirmado no banco: EMANUELE
      LIGIA DE AZEVEDO (desligada 15/07/2026) **não tem linha no ledger** —
      saiu da planilha antes da 076, então seus 57 contratos (06/2025 a
      05/2026) contam como produção de consultora. ERICA CRISTINA MARINS DA
      SILVA está com piso `2020-01-01` mas só assumiu em 15/07/2026. E a
      grafia diverge: ledger/`supervisores` gravam **"ERICA CRISTINA MARINS
      DA SILVA ROSA"**, enquanto `consultores` e os contratos gravam sem o
      "ROSA" — como o match é por nome normalizado, **a exclusão dela nunca
      funcionou**, nem antes nem depois do ledger. Varredura dos 47: é o
      único caso real (RAIANE ALMEIDA SOUZA também não casa, mas não tem
      cadastro nem contrato, então é inerte). Corrigir também na planilha do
      angry-man, senão o import recria a linha órfã.
- [x] **Migration 082 escrita + angry-man ajustado** (tsc limpo, 61 testes
      verdes). Decidido em
      2026-08-18: a data de vigência vai na própria planilha (fonte única);
      par novo abre na data informada, troca na mesma loja fecha o
      antecessor na data do sucessor, saída sem substituto cai em
      `current_date` e é reportada; divergência com vigência já aberta é
      **só reportada**, nunca aplicada em silêncio. angry-man: 1 coluna a
      mais no payload (RPC já mapeada, sem redeploy da Edge Function).
      A 082 traz também a ação `CORRIGIR_INICIO` em
      `fn_aplicar_mudanca_supervisor` — sem ela não haveria caminho para
      consertar uma vigência aberta com data errada, já que `INICIO` é
      no-op por idempotência (foi por isso que a 078 precisou de UPDATEs
      manuais).
- [ ] **Correção da 080 (não editar a migration, já aplicada):** o
      comentário dela manda re-materializar após correção retroativa no
      ledger. Está **incompleto** — o gatilho real é qualquer alteração em
      `consultores`, porque o headcount de mês passado lê o roster de HOJE.
      Comprovado em 2026-08-18: 3 cadastros novos (CAIQUE, JOAO BATISTA,
      CARLA) criados depois do backfill mudaram `activeRegistered` de 163
      para 165 **em todas as competências**, inclusive 06/2025. A validação
      nº 2 da 080 (`publicado == ao vivo`) é, por isso, um teste ruim: falha
      de rotina sem indicar problema. Decisão pendente do usuário: Caderno
      publicado **congelado** (republicar é ato deliberado — recomendado, é
      o que "fechamento" significa) ou **sincronizado** (gancho pós-import
      no angry-man). Só a vigência do roster faz os dois coincidirem.
- [x] **RAIANE ALMEIDA SOUZA → 083 escrita e APLICADA em 2026-08-18 19:29.**
      Primeira tentativa falhou silenciosamente: foi executada **antes da
      082**, quando `fn_aplicar_mudanca_supervisor` ainda era a versão da
      077 e levantava `acao invalida: CORRIGIR_INICIO`. Detectado pelo
      `updated_at` da linha, idêntico ao `created_at` do backfill.
      Verificado depois: COPACABANA NOVA com um supervisor por vez (DJANE
      até 04/08, vão de 14 dias, RAIANE de 18/08), invariante 47 = 47,
      **40 pisos presumidos** restantes.
      **Comentário desatualizado na 083** (aplicada, não editar): o
      cabeçalho afirma que "agosto fecha sem ela como supervisora e
      setembro é o primeiro mês". Isso valia pela âncora do 1º dia; com a
      085, agosto **é** o primeiro mês dela — que é o resultado pedido. Recém-contratada,
      assumiu HELP COPACABANA NOVA em **18/08/2026**; o ledger a registrava
      desde `2020-01-01`. Primeiro uso real de `CORRIGIR_INICIO` (082) —
      `INICIO` seria no-op, já que ela tem linha aberta vinda do backfill.
      Sem efeito em número publicado (ausente de `consultores`, sem
      contratos); evita o erro futuro de contá-la como supervisora em
      competências anteriores à própria contratação. Usuário confirmou que
      ela **nunca foi consultora** — entra direto como supervisora, sem
      fase anterior a preservar. Descartado retroagir o piso: mascararia,
      só para supervisores, o efeito de `consultores` não ter vigência
      (todo recém-contratado infla o headcount de meses passados), ao custo
      de gravar ficção no ledger.
- [x] **Caderno = CONGELADO** (decidido em 2026-08-18). Mês fechado é fato
      congelado na publicação; republicar é ato deliberado. bereshit
      ajustado: lê `obter_caderno_publicado`, seletor lista só
      `caderno_fechamento_snapshot`, NULL vira "competência não publicada"
      (distinto de contrato inválido). `tsc` limpo, 38 testes verdes.
      `database/CONTRATO.md` do bereshit atualizado — inclusive corrigindo
      que a **075 manteve `v1.4`** no COMMENT (adicionou
      `headcountDiagnostics` sem bumpar); v1.5 é a 079.
- [x] **Cadeia de movimentações → migration 084 escrita.** Todas as três
      com data efetiva **04/08/2026**, e usuário confirmou que MARIANA e
      DJANE foram **transferidas** (já eram supervisoras), não promovidas.
      Isso revelou que o backfill da 076 errou não só a data delas: errou a
      **loja** do período histórico, porque colocou cada uma na loja ATUAL
      desde 2020-01-01. Por isso `REMANEJAMENTO` não serve — fecharia uma
      janela afirmando que a MARIANA supervisionou BELFORD ROXO SÃO JOSÉ
      de 2020 a 2026, quando ela estava em RAMOS. A 084 **insere** a janela
      de origem (loja certa) e só então move o início da janela aberta com
      `CORRIGIR_INICIO`. Sem efeito no Caderno: as duas seguem supervisoras
      em todo mês passado (mudou a loja, não o papel) e headcount exclui
      supervisor independentemente da loja. Histórico original: LETICIA ALVARENGA GOMES
      FREITAS (supervisora de HELP BELFORD ROXO SÃO JOSÉ) foi desligada →
      MARIANA CARLA LAMIN DA SILVA saiu de HELP RAMOS para cobri-la →
      DJANE MARIA PEREIRA DOS SANTOS saiu de HELP COPACABANA NOVA para
      cobrir RAMOS → RAIANE assumiu COPACABANA NOVA (083). Estado atual:
      LETICIA **sem linha no ledger** (mais um caso EMANUELE; 8 contratos
      / R$ 838,83), MARIANA e DJANE com piso `2020-01-01` na loja NOVA —
      a MARIANA produziu em HELP RAMOS até 07/2026 e o ledger a coloca em
      BELFORD ROXO SÃO JOSÉ desde 2020.
      Esta cascata é exatamente o que a sucessão da 082 resolveria sozinha
      se a planilha já tivesse a coluna DESDE.
- [ ] Publicar/republicar competência pelo bereshit: `fn_materializar_caderno`
      já é chamável com a service role que ele usa no servidor — falta a
      ação de UI. Hoje publica-se pelo SQL Editor.
- [ ] Verificar se HELP COPACABANA NOVA teve supervisor **antes** da
      RAIANE: o ledger só tem a linha dela, mas a loja produz desde pelo
      menos 05/2026. Um antecessor perdido seria outro caso EMANUELE
      (produção de supervisor contando como de consultor). Pode ter sido
      coberta pela supervisora de HELP COPACABANA — são lojas irmãs.
- [ ] Auditar os **44 pisos `2020-01-01`** restantes — são "vigência
      presumida, não confirmada", e o caso ALCÂNTARA mostra que cada um pode
      esconder uma promoção ou saída não registrada.

## Referências

- Docs consultados: [business-rules.md](../business-rules.md) ("Exclusão
  de supervisores"), [data-layer.md](../data-layer.md),
  [2026-07-08](2026-07-08-universo-consultores-dedup-e-vai-e-vem.md),
  [2026-07-09](2026-07-09-supervisor-como-consultor-exclusao-global.md)
- Precedente de desenho: migrations
  [043](../../../database/migrations/043_loja_regiao_vigencia.sql) e
  [049](../../../database/migrations/049_fn_aplicar_remanejamento_regiao.sql)
