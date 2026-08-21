# 2026-08-20 — Consultor: ledger em granularidade de dia (087) e regras de headcount ponderado

**Agente:** Claude Code
**Tipo:** bugfix de regra de negócio + preparação de feature
**Arquivos tocados:** `database/migrations/087_consultor_vigencia_granularidade_dia.sql`,
`database/migrations/088_vigencias_historicas_alcantara.sql`,
`database/migrations/089_consultor_afastamento.sql`,
`database/migrations/090_fn_afastamentos_replace.sql`, `docs/HEADCOUNT_ETL.md`,
`requirements-dev.txt`
**Commit(s):** (pendente)

## Objetivo

Dar precisão à contagem de consultores ativos, hoje cega a afastamentos
(doença, licença, férias) e a transferências de loja dentro do mês. Esta
entrada registra o **diagnóstico** do que existia, as **regras aprovadas**
pelo usuário e a **primeira migration** do plano.

## O que foi feito

- **Diagnóstico.** Existiam três contagens distintas de "consultor ativo":
  1. denominador das médias de KPI — vem da **produção**
     (`df["CONSULTOR"].nunique()` em `kpis/gerais.py`, `pontuacao.py`,
     `produtos.py`): quem não digitou contrato no mês não existe;
  2. universo de controle — vem do **cadastro** (`carregar_consultores_ativos`);
  3. headcount do Caderno — mesmo cadastro, via `obter_caderno_fechamento`.
- **Achado principal:** o RH **já informa** afastamento na coluna `Obs` de
  `HC_Colaboradores.xlsx` (2 licenças maternidade, 1 afastamento médico, 1
  licença médica) e o ETL **descarta** — `consultores` só tem
  `(nome, loja_id, status)`.
- **Ressalva descoberta em 2026-08-20:** a cópia de `HC_Colaboradores.xlsx` no
  repositório é um **export velho**, não o que o RH tem hoje — **47 dos 242
  nomes divergem** do banco, 45 deles `Ativo (a)` na planilha e
  `Desligado (a)` no banco. O banco está mais fresco. Toda análise de caso
  individual tem de ser feita contra o banco, não contra o arquivo.
- O banco usa o STATUS como canal de afastamento em **1 caso**
  (`Licença Maternidade`); a `Obs` da planilha é o outro canal. Dois canais
  ad-hoc para o mesmo fato — é isso que a 089 substitui.
- **Migration 087:** rebuild do `consultor_vigencia` em granularidade de dia,
  com as três correções do backfill da 086. Sintaxe validada com parser
  Postgres; algoritmo simulado em pandas sobre a base real (141.297
  contratos), com as 4 invariantes passando.

## Decisões não óbvias

- **Produção prova presença; a falta dela não prova ausência.** Princípio que
  amarra o resto. Medido: a cobertura de dias com digitação é 82% (mediana) em
  meses de regime, mas **21% dos meses de regime têm cobertura < 25%** — usar
  digitação como medida de dias presentes classificaria um quinto do quadro
  como ausente. Serve para *provar presença* e *fechar ausência*, nunca para
  abri-la. Também elimina a circularidade de derivar o denominador da
  produtividade da própria produção.
- **RH acerta o começo, digitação acerta o fim.** Validado nos 4 nomes com
  `Obs`: ERICA (marcada `Licenciado (a)` hoje) voltou a produzir em jul/2026 —
  8 e 9 contratos; ANA LETICIA (`Ativo (a)` + "Afastamento médico") é a maior
  produtora desde mar/2026. A `Obs` está desatualizada em 2 dos 4 casos. Por
  isso a **data de retorno não precisa vir do RH**: a janela de afastamento
  entra aberta e a primeira digitação a fecha.
- **Discriminador de transferência intra-mês = sobreposição das janelas de
  dias**, não um limiar de percentual. Medido: dos 38 pares (pessoa, mês) com
  mais de uma loja, 25 têm janelas disjuntas (transferência real) e 13 se
  sobrepõem — e são exatamente os de minoria ínfima (286/4, 96/1, 93/4),
  digitação avulsa. Mês decide **qual** loja (protege do ruído, como na 086);
  dia decide **quando** troca.
- **Fronteira exata quando verificada, de mês quando inferida.** Entrada e
  transferência ganham data exata; **saída sem data do RH fecha no fim do mês**
  — fechar no dia seguinte ao último contrato encolheria o denominador por
  inferência (quem vendeu dia 10 e trabalhou até dia 30 sumiria de 20 DU).
- **Piso de 50% aplica-se ao peso TOTAL da pessoa, nunca à repartição entre
  lojas.** Se aplicado na repartição, um split real de 30/70 vira 50/50 e a
  transferência perde a informação de maior permanência.
- **Ausência declarada de mês inteiro pesa 0, sem piso.** Caso ERICA: 7 meses
  de licença numa loja de 5 consultores — o piso de 50% recuperaria menos da
  metade do erro (denominador 4,5 em vez de 4,0).
- **`consultores.created_at` não é data de admissão** — 239 das 425 linhas
  nasceram na carga inicial de 21/03/2026. Só serve para quem entrou nas
  cargas incrementais posteriores; é assim que a 087 trata os `BACKFILL_PISO`.
- **Coluna `DESDE` da 088 (prevista pela 086) fica cancelada** — decisão do
  usuário: admissão = primeiro contrato digitado. Supervisor mantém a lógica
  própria das 076/082.
- **Piso de 50% só vale para fronteira INFERIDA** (aprovado 2026-08-20).
  Fronteira declarada com data — retorno, afastamento, promoção, transferência
  — usa a fração pura. O caso que forçou a distinção: ERICA volta em 19/06 e
  vira supervisora em 15/07; com piso, junho e julho empatavam em 0,50, apagando
  a diferença entre 8 e 10 dias úteis. Sem piso: 0,36 e 0,43.
- **A exclusão de supervisor tem de ser feita pelo LEITOR**, subtraindo a janela
  de supervisão da janela de vínculo — nunca no backfill. É o que permite
  corrigir o papel de alguém sem reprocessar o ledger de consultor.
- **`consultor_vigencia` é vínculo pessoa↔loja, não papel.** A pessoa continua
  vinculada à loja enquanto supervisora e enquanto afastada; quem zera o peso é
  o ledger de afastamento, e quem tira do eixo consultor é o de supervisão. Três
  ledgers ortogonais, um por pergunta.
- **Assumimos** que a competência 05/2025 subestima o headcount para sempre:
  124 das 297 pessoas (42%) têm o primeiro contrato no início da base e são
  marcadas `BACKFILL_CENSURADO`.
- **MARIANA era consultora e foi promovida** — confirmado pelo usuário em
  2026-08-20. Libera os 611 contratos de volta ao eixo consultor em 6
  competências publicadas.
- **`consultor_afastamento` não é legível por `anon`**, ao contrário de
  `supervisor_vigencia` e `consultor_vigencia`. Ela guarda motivo de
  afastamento — dado pessoal sensível (saúde, gravidez) — e o projeto usa uma
  chave Supabase compartilhada: o que `anon` lê, qualquer portador da chave lê.
  RLS fail-closed, sem policy de leitura; o acesso é por RPC `SECURITY DEFINER`
  que devolve **peso agregado, nunca o tipo nem o nome**. O dashboard precisa
  saber que a pessoa pesa 0; não precisa saber por quê.
- **Data de início da licença da ERICA = 12/01/2026 é ESTIMADA**, escolhida pelo
  usuário para linearizar a sucessão de HELP ALCANTARA (MARIANA assume em
  13/01). Não contradiz o dado: produção zero em dez/2025 e jan/2026 é
  compatível com presença, porque ela era supervisora — supervisor nesta base
  produz de 1 a 22 contratos/mês.
- **Fallback é fallback, não verdade.** Admissão e desligamento derivados da
  produção são provisórios; quando o arquivo trouxer a data real ela
  sobrescreve e a linha vira `origem = 'ETL'`. É exatamente para isso que a
  coluna `origem` existe desde a 086 — separar fato informado de inferência.
  **Consequência dura:** depois que o ETL começar a escrever, não pode mais
  haver rebuild em massa de `consultor_vigencia` (o rebuild preserva
  `ETL`/`MANUAL` mas reinsere derivadas, duplicando janelas).
- **Afastamento entra em modo SNAPSHOT** (usuário, 2026-08-20), com UPSERT para
  correção. O motivo é a assimetria medida: o RH acerta o início e erra o fim,
  então ausência do arquivo passa a significar retorno — ninguém precisa
  informar. SNAPSHOT vazio é recusado, senão um arquivo quebrado fecharia todas
  as janelas e inflaria o denominador em silêncio.
- **`pglast` adicionado a `requirements-dev.txt`** com consentimento explícito
  do usuário, para validar sintaxe e corpos plpgsql das migrations antes da
  execução.

## O caso ERICA — o contraexemplo que validou o desenho

A janela de consultora da ERICA em HELP ALCANTARA CARREFOUR (19/06 a
15/07/2026) é **invisível para qualquer backfill derivado de produção**: ela
trabalhou o período inteiro e digitou zero contrato. O primeiro contrato dela
na loja é de 20/07 — cinco dias depois de já ter virado supervisora.

Consequência: a 087, mais precisa que a 086 em todo o resto, é **mais errada**
neste caso (dataria o vínculo em 20/07 em vez de 01/07). Não invalida o
princípio — produção prova presença, e é isso que mantém a janela dela aberta
durante os 7 meses de licença. Mostra o limite: produção **não prova em que
loja nem em que papel**. Daí a necessidade de entrada manual no ledger.

A [migration 081](../../../database/migrations/081_supervisor_vigencia_alcantara_carrefour.sql)
já tinha passado por este caso e, sob a premissa incompleta "ERICA só assumiu
em 15/07/2026", apagou a passagem anterior dela por HELP ALCANTARA. A 088
restaura com piso (início anterior à base) e fim em 13/01/2026.

## A composição dos três ledgers, verificada em produção

HELP ALCANTARA em 03/2026 (DU=22), pela `fn_headcount_ponderado`: **peso 3,7273,
4 cabeças** — de 8 pessoas com vínculo na loja. Quem saiu, e por quê:

| Pessoa | dias | motivo |
|---|---|---|
| LETYCIA · MICHELLE · RICARDO | 22/22 | — |
| MARIA NATTALLY | 16/22 | entrou no meio do mês |
| **ERICA** | **0** | **afastamento** |
| **MARIANA** | **0** | **papel** (supervisora desde 13/01) |
| KATHYANNE · LIVIA | 0 | vínculo não cobre a competência |

Duas exclusões na mesma loja e no mesmo mês, **por razões diferentes** — é a
prova de que os três ledgers ortogonais compõem como desenhado, e não se
sobrepõem.

## A chave do `.env` é `service_role` — impacto no desenho de privacidade

Descoberto em 2026-08-20 ao verificar a 089: o JWT em `SUPABASE_KEY` traz
`role: service_role`, não `anon`.

Consequências, se a aplicação rodar com essa chave:

- **RLS é integralmente contornada.** `service_role` ignora policies, então a
  metade *server-side* do defense-in-depth não existe — sobra só o
  `aplicar_rls` client-side.
- **A proteção da 089 não alcança o dashboard.** A tabela nasceu sem grant para
  `anon`/`authenticated` justamente porque "o que `anon` lê, qualquer portador
  da chave lê". Com `service_role`, o app lê `tipo` e `observacao` de qualquer
  forma. A proteção passa a depender de **disciplina de aplicação** — nunca
  fazer `SELECT` na tabela, só consumir peso agregado via RPC.

`src/config/supabase_client.py` lê `st.secrets` primeiro e cai no `.env` só
localmente, então isso é **certo para execução local** e *desconhecido* para o
deploy. Pendente confirmar qual chave está no Streamlit Cloud.

## Snapshot: duas divergências sobrepostas (medido 2026-08-20, pós-088)

Comparando `obter_caderno_fechamento` ao vivo contra o `caderno_fechamento_snapshot`
(todos gerados em 18/08), a divergência tem **duas causas independentes**:

**(1) Efeito da 088 — por loja, nas competências até 13/01/2026:**

| Loja | 12/2025 snapshot | ao vivo | produtividade |
|---|---|---|---|
| HELP ALCANTARA | 4 | **5** | 69.125 → 55.300 (−20%) |
| HELP ALCANTARA CARREFOUR | 4 | **3** | 65.135 → 86.847 (+33%) |

**(2) Drift de cadastro desde 18/08 — em TODAS as 14 competências:**
`summary.activeConsultants` foi de 119 para **124** em 07/2025, 02/2026,
03/2026 e 06/2026 — competências que a 088 **não toca**. Não é efeito da
migration: é o cadastro tendo mudado depois que o snapshot foi congelado.

É a própria patologia que a 086 diagnosticou, agora visível de fora: o headcount
do Caderno lê o cadastro de HOJE, então **toda atualização de cadastro reescreve
as 14 competências**.

**Correção à instrução da 088** (a migration está aplicada e é imutável): ela
manda rematerializar 6 competências, escolhidas pelo eixo de **produção** (onde
a MARIANA produziu). Mas o eixo de **headcount** muda em todas as competências
anteriores a 13/01/2026, e o drift muda as 14. Rematerializar só 6 deixaria o
relatório internamente inconsistente — parte com cadastro de 18/08, parte com o
de hoje.

**Decisão recomendada: segurar a rematerialização até a 091.** Rematerializar
agora só recongela um número errado diferente — o headcount continuaria vindo do
cadastro do dia. Quando o headcount virar point-in-time, rematerializar as 14 de
uma vez, junto com o deploy do bereshit.

## Exposição da regra de saída inferida (medido 2026-08-20)

`consultor_vigencia` fecha por **saída inferida** em 129 janelas (contra 99 por
transferência e 168 abertas): sem data de desligamento, a janela termina no fim
do mês do último contrato. Isso **infere ausência a partir do silêncio**, que é
o oposto do princípio adotado — mas não há alternativa sem a data real.

A defasagem **não é mensurável** no schema atual: `consultores` não tem coluna
de desligamento, e `updated_at` é carimbo de lote (158 dos 160 desligados na
mesma data, 11/08/2026). Dá para medir a **sensibilidade** — de quanto o
headcount sobe se a saída real for K meses depois do último contrato:

| K | Impacto médio no denominador | Pior competência |
|---|---|---|
| +1 mês | ~5% | 12,6% (09/2025) |
| +2 meses | ~9% | 18,9% (09/2025) |
| **+3 meses** | **13,5%** | **26,8% (09/2025)** |

Direção do erro: subestimar o denominador **infla a produtividade**. As médias
por loja publicadas hoje são, nesse eixo, otimistas.

Limite superior, não estimativa: só vale para quem ficou **trabalhando** sem
vender. Quem ficou afastado pesa 0 de qualquer forma — e o único caso
verificável (ANNA CLARA, 8 meses de defasagem) era exatamente esse, neutro.
O valor real depende da proporção entre os dois, que só a data de desligamento
do RH resolve.

## Pendências / follow-ups

- [x] **087 APLICADA e verificada** (2026-08-20). Os 8 checks passam com os
      valores **exatos** da simulação em pandas: 396 linhas / 297 pessoas
      (124+1+271 por origem), 168 abertas = cadastro ativo, 71 com mais de uma
      janela, 0 sobreposições, 0 janelas anteriores a 2025, 0 divergências de
      emenda, 223 janelas fora do dia 1º, e a invariante central sem nenhuma
      violação nas 16 competências. O SQL e a simulação concordam linha a
      linha — o método de validar em pandas antes de escrever o SQL se
      confirmou
- [x] **088 APLICADA e verificada** (2026-08-20). Os 5 checks passam: linha do
      tempo de HELP ALCANTARA com 2 janelas emendadas, as duas passagens da
      ERICA sem sobreposição, vínculo dela emendando em 19/06 com `origem
      MANUAL`, invariante da 077 de pé (47 abertas = 47 na foto), MARIANA
      começando em 13/01/2026
- [ ] **REMATERIALIZAÇÃO — segurar até a 091.** Ver "Snapshot: duas
      divergências sobrepostas" abaixo. **A instrução da 088 está incompleta**
      (e a migration é imutável, então fica corrigida aqui)
- [x] **ANNA CLARA** — resolvido: desligada em 04/05/2026 e **afastada** todo o
      período desde o último contrato (usuário, 2026-08-20). Sob R2 o peso é 0
      nos dois casos, então o ledger atual já produz o número certo.
      Nenhuma correção necessária
- [x] **Datas passam a vir por upload** (usuário, 2026-08-20): afastamento,
      admissão e desligamento. Contrato especificado em
      [HEADCOUNT_ETL.md](../../HEADCOUNT_ETL.md); RPC de afastamento na 090
- [x] **Afastamento vem no `HC_Colaboradores.xlsx`** (usuário, 2026-08-20) —
      arquivo único, casando com a semântica SNAPSHOT
- [x] **Bereshit reflete o Dashboard** (usuário, 2026-08-20): `activeConsultants`
      segue inteiro (auditoria de cadastro), entra `weightedHeadcount` numérico
      e `productivity` passa a usar o peso
- [ ] **091 — `fn_headcount_replace(p_rows jsonb)`**: uma RPC para o arquivo
      inteiro (foto + datas + afastamento numa transação), no desenho da 077
- [ ] **Deploy coordenado com o bereshit**: entre a migration entrar e ele ler
      `weightedHeadcount`, o relatório fica internamente inconsistente
      (headcount inteiro com produtividade sobre o peso). Têm de sair na mesma
      janela, junto com a rematerialização
- [ ] Reconciliar na fonte o **tipo** do afastamento da ERICA: o usuário
      descreveu licença médica, a planilha registra `Licença maternidade`
- [x] **091 APLICADA e verificada** (2026-08-20). O SQL bate com a simulação em
      pandas em **todas** as medidas: DU (22/23/21 conforme o mês), peso total
      por competência (102,00 · 125,93 · 124,50 · 125,86 · 116,30), cabeças
      (103 · 132 · 130 · 136 · 124), e o caso ERICA (2,3810 em 06/2026 e
      3,3043 em 07/2026). Nenhuma loja com `peso > cabecas`
- [ ] **092** — `obter_caderno_fechamento` consumindo a 091:
      `activeConsultants` segue inteiro, entra `weightedHeadcount`,
      `productivity` passa a usar o peso. É a migration que **quebra contrato**
      com o bereshit e destrava a rematerialização das 14 competências
- [ ] **093** — Python: `carregar_consultores_ativos(mes, ano)` com coluna
      `PESO` (mudança de assinatura, 6 call sites, já aprovada); denominadores
      de `gerais.py` / `pontuacao.py` / `produtos.py` somam `PESO`
- [ ] **Feriados de 2025 — adiado por decisão do usuário** (2026-08-20), não é
      pendência de bug. **2026 é o ano que tem de estar correto** para o
      dashboard e o bereshit; anos anteriores serão corrigidos gradativamente.
      A tabela `feriados` tem 13 linhas, todas de 2026, então o DU de 2025 sai
      1-2 dias maior que o real — subestima a fração de quem teve mês parcial
      em 2025, e é **nulo** para mês cheio (o feriado entra no numerador e no
      denominador)
- [ ] `_colapsar_cadastro_recente` desempata por `updated_at` sem critério
      secundário: as duas linhas da ERICA diferem por **304 ms**, e a ordem
      inversa a tiraria do universo de ativos
- [ ] **ETL** — `Obs` vira campo estruturado com vocabulário fechado
      (`AFASTAMENTO_MEDICO`, `LICENCA_MATERNIDADE`, `LICENCA_NAO_REMUNERADA`,
      `FERIAS`) + data de início obrigatória e retorno opcional
- [ ] Avisar as lojas antes da 090: trocar o denominador de "quem produziu"
      para "ativos ponderados" **derruba todas as médias publicadas** (folga
      medida de +2 a +11 pessoas por competência). É mudança de patamar, não
      refinamento.
- [ ] Os 3 contratos de 2020 (LUDYMILA, MATHEUS, TAIS) parecem erro de
      digitação de ano — vale corrigir na origem, não só filtrar

## Referências

- Docs consultados: [business-rules.md](../business-rules.md),
  [data-layer.md](../data-layer.md), [rls.md](../rls.md)
- Migrations relacionadas: 073, 075, 080, 085, 086
