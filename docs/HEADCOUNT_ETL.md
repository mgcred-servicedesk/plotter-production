# Headcount — contrato de ETL (angry-man)

> **Projetos afetados:** `Numeros_venda` (dashboard) · `angry-man` (ETL) · `bereshit` (Caderno)
> **Status:** implementado no angry-man em 2026-08-21 (migrations 090/094);
> guardas de cadastro em 2026-08-25 (migration 095, §4.3); importação do
> cadastro histórico de e-mails preparada na migration 097 (§4.5), ainda
> dependente de aplicação e deploy.
> Pendente: o RH acrescentar as cinco colunas novas ao arquivo.
> **Origem:** decisões do usuário em 2026-08-20 (ver
> [progress/2026-08-20](agents/progress/2026-08-20-consultor-vigencia-granularidade-dia.md))

## 1. O que muda e por quê

`consultores` responde **"qual é a situação hoje"** e nunca **"desde quando"**.
É a mesma raiz do problema que a migration 086 corrigiu um nível abaixo: sem
data de evento, o cadastro de hoje reescreve todos os meses.

Três datas passam a ser comunicadas por upload:

| Data | Fallback enquanto o arquivo não sobe | Exposição medida |
|---|---|---|
| **Admissão** | data do **primeiro contrato digitado** | 124 pessoas (42%) com admissão censurada |
| **Desligamento** | fim do mês do **último contrato** | até **13,5%** do denominador |
| **Afastamento** | não há — hoje é invisível | 4 casos conhecidos, sem data |

**Regra de precedência (vale para as três):** o valor derivado da produção é
*fallback*, nunca verdade. Assim que o arquivo trouxer a data real, ela
sobrescreve — e a linha passa a `origem = 'ETL'`, que é justamente o que a
coluna `origem` de `consultor_vigencia` existe para marcar: separar **fato
informado** de **inferência**.

> ⚠️ **Depois que o ETL começar a escrever, não pode mais haver rebuild em
> massa de `consultor_vigencia`.** O rebuild da 087 apaga `origem LIKE
> 'BACKFILL%'` e preserva `ETL`/`MANUAL` — mas reinsere linhas derivadas para
> as mesmas pessoas, criando janelas duplicadas e violando
> `uq_cv_consultor_loja_aberta`. Correção passa a ser incremental, via as RPCs.

## 2. Um arquivo só: `HC_Colaboradores.xlsx`

Decisão do usuário (2026-08-20): afastamento vem no **próprio arquivo de
headcount**, não em arquivo separado. Isso casa com a semântica escolhida — o
HC já é uma **foto do quadro**, e foto é exatamente o que `SNAPSHOT` espera.

Colunas hoje: `FILIAL`, `VENDEDOR`, `STATUS`, `Obs`.

`STATUS` passou a seguir a mesma precedência das datas (migration
095): **célula vazia preserva o status que já está no banco**, e
`Ativo (a)` vale só para pessoa nova. Antes, branco virava
`Ativo (a)` e reativava desligado a cada upload — o status era a
única coluna do arquivo fora da regra "vazio nunca significa 'não
tem'".

Colunas a acrescentar:

| Coluna | Obrigatória | Formato | Vazio significa |
|---|---|---|---|
| `DATA_ADMISSAO` | não | `AAAA-MM-DD` | usar fallback (1º contrato) |
| `DATA_DESLIGAMENTO` | não | `AAAA-MM-DD` | usar fallback (fim do mês do último contrato) |
| `TIPO_AFASTAMENTO` | não | vocabulário fechado | pessoa não está afastada |
| `AFASTAMENTO_INICIO` | se houver tipo | `AAAA-MM-DD` | — |
| `AFASTAMENTO_FIM` | não | `AAAA-MM-DD` | retorno desconhecido |

`Obs` continua existindo como texto livre para anotação humana, mas **deixa de
ser canal de dado**: quem carrega afastamento passa a ser `TIPO_AFASTAMENTO`.
Hoje o mesmo fato viaja por dois canais ad-hoc — a `Obs` e, em 1 caso, o
próprio `STATUS` (`Licença Maternidade`).

> A cópia de `HC_Colaboradores.xlsx` neste repositório é um **export velho** —
> 47 dos 242 nomes divergem do banco, 45 deles `Ativo (a)` na planilha e
> `Desligado (a)` no banco. Não usar como referência de estado atual.

### 2.1 Exceção: cadastro histórico de e-mails

`Cadastro_Afastamentos_2026.xlsx` não é uma foto atual de headcount. É uma
coleção histórica de eventos, em duas abas, e por isso entra por uma porta
separada: `fn_movimentacoes_rh_import` (097). A terceira aba, `Leia-me`, é
metadado e nunca vira movimento.

O angry-man localiza o cabeçalho real na linha 4, converte apenas `Licença
médica` e `Licença maternidade` para o vocabulário fechado e mantém os demais
tipos como pendência. Datas citadas dentro do campo livre de motivo não são
interpretadas: o arquivo declara que ocorrências recorrentes foram agrupadas,
logo transformar a primeira e a última menção em uma janela contínua seria
inventar ausência.

O fluxo é `dry-run` seguido de aplicação somente se o banco não encontrar
pendências. Nomes não resolvidos, loja não reconhecida, correção `MANUAL` e
produção na data do desligamento ou depois dela bloqueiam a transação inteira.
Motivo e remetente não saem do browser.

## 3. Afastamento — semântica e RPC

### 3.1 Colunas (subconjunto do arquivo acima)

| Coluna | Obrigatória | Formato | Observação |
|---|---|---|---|
| `nome` | sim | texto | sem o código antes do `" - "`, como já se faz hoje |
| `tipo` | sim | vocabulário fechado | `AFASTAMENTO_MEDICO`, `LICENCA_MATERNIDADE`, `LICENCA_NAO_REMUNERADA`, `FERIAS` |
| `data_inicio` | sim | `AAAA-MM-DD` | |
| `data_fim` | não | `AAAA-MM-DD` | deixar vazio quando o retorno não é conhecido |
| `observacao` | não | texto | |

Vocabulário **fechado** de propósito: texto livre é exatamente como a coluna
`Obs` chegou ao estado atual — 4 grafias para 3 conceitos, 2 delas
desatualizadas.

### 3.2 RPC

```
fn_afastamentos_replace(p_rows jsonb, p_modo text DEFAULT 'SNAPSHOT')
  -> jsonb {modo, count, inseridos, atualizados,
            fechados_por_producao, fechados_por_ausencia,
            abertos_antes, abertos_depois}
```

- **`SNAPSHOT`** (padrão, uso normal): o arquivo é a foto de quem está
  afastado. **Quem sumiu do arquivo retornou** e a janela fecha sozinha — o RH
  nunca precisa informar retorno, que é justamente o que ele não faz.
- **`UPSERT`**: correção pontual. Só mexe nas linhas enviadas; ausência não
  fecha nada. É o modo para consertar informação equivocada — inclusive uma
  `data_inicio` errada, que corrige a janela aberta em vez de duplicar.

**`SNAPSHOT` com array vazio é recusado.** Fecharia todas as janelas de uma vez
e inflaria o denominador em silêncio. Encerrar todo mundo é ato explícito:
`UPSERT` com `data_fim` preenchida, uma linha por pessoa.

**Validação é tudo-ou-nada:** uma linha inválida derruba a carga inteira e
devolve `invalidas` com as linhas problemáticas. Nada é aplicado pela metade.

### 3.3 Privacidade — leia antes de logar qualquer coisa

`consultor_afastamento` guarda **motivo de afastamento**: dado pessoal
sensível (saúde, gravidez). Diferente de `supervisor_vigencia` e
`consultor_vigencia`, ela **não tem grant para `anon`/`authenticated`** — o
projeto usa uma chave Supabase compartilhada, e o que `anon` lê qualquer
portador da chave lê.

- O ETL chama a RPC com `service_role`, nunca com a chave pública.
- **Não logar `tipo` nem `observacao`** em texto claro. O envelope de retorno
  é agregado de propósito — pode ser logado inteiro.
- O dashboard nunca lê a tabela: ele recebe **peso agregado**, nunca o motivo.

## 4. Admissão e desligamento

Vazio significa **"use o fallback"**, não "não tem". Enquanto a coluna vier
vazia, o comportamento é exatamente o de hoje.

### 4.1 Efeito de cada data

- **`DATA_ADMISSAO`** substitui `vigencia_inicio` da primeira janela da pessoa
  e apaga a marca `BACKFILL_CENSURADO`. É o que resolve a limitação que a 087
  aceita como permanente: 05/2025 subestimar o headcount para sempre.
- **`DATA_DESLIGAMENTO`** substitui o `vigencia_fim` da última janela. É a
  maior exposição aberta — a regra atual **infere ausência a partir do
  silêncio**, que é o oposto do princípio adotado, e vale até 13,5% do
  denominador.

### 4.2 RPC

```
fn_headcount_replace(p_rows jsonb,
                     p_modo_afastamento text DEFAULT 'SNAPSHOT',
                     p_reabrir_ativos boolean DEFAULT false)
  -> jsonb {count, cadastro, admissao, desligamento,
            afastamento, diagnostico}
```

Escrita na **migration 094**. Numa transação só: atualiza `consultores` (a
foto), grava as datas em `consultor_vigencia` marcando `origem = 'ETL'`, e
delega o bloco de afastamento para `fn_afastamentos_replace`. Mesmo desenho de
`fn_supervisores_replace` (077) — foto e ledger mudam juntos ou não mudam.

`fn_afastamentos_replace` continua acessível diretamente — é por ela que se faz
correção pontual em modo `UPSERT`.

Três guardas que o desenho original não previa e a medição pediu:

| Guarda | Por quê |
|---|---|
| **Produção não se desmente** | Contrato digitado antes da admissão declarada (ou depois do desligamento declarado) vira divergência **reportada**, não escrita. Produção prova presença; a planilha não pode apagar isso. |
| **`MANUAL` é intocável** | Janela com `origem = 'MANUAL'` é correção humana. Carga de arquivo não a sobrescreve — reporta e segue, como a 077 faz. Sem isso, a primeira carga do HC apagaria a correção de ERICA que as 088/089 foram escritas para fazer. |
| **`p_modo_afastamento = 'SKIP'`** | `SNAPSHOT` vazio é recusado pela 090 (fecharia todas as janelas). Mas "arquivo sem as colunas" e "arquivo dizendo que ninguém está afastado" são afirmações diferentes que um array vazio não distingue. O angry-man manda `SKIP` quando a coluna `TIPO_AFASTAMENTO` não existe no arquivo. |

**`p_reabrir_ativos` não é o padrão.** Pessoa que a planilha declara ativa e
cuja janela o backfill fechou por inferência é contradição real — mas reabrir
muda número já publicado, retroativamente e em massa. O envelope sempre devolve
`ativos_com_janela_fechada`; reabrir é ato explícito.

> Medido em 2026-08-21 com o export de março que está no repositório:
> `ativos_com_janela_fechada = 46`. Desses, **45 são a planilha velha**
> (`Ativo (a)` nela, `Desligado (a)` no banco) e 1 é HELOINA. Com
> `p_reabrir_ativos` ligado, aquela carga reabriria 46 janelas de uma vez.

### 4.3 Guardas da migration 095

Três correções na mesma função, mesma assinatura — sem `DROP`, sem
redeploy obrigatório do angry-man. Todas medidas contra o banco real em
2026-08-25, antes da primeira carga, e nenhuma altera número publicado
hoje.

| Guarda | Por quê |
|---|---|
| **`desligados_com_janela_aberta`** no `diagnostico` | O espelho de `ativos_com_janela_fechada`, que faltava. Planilha diz que a pessoa saiu, o ledger tem janela aberta, `DATA_DESLIGAMENTO` veio vazia: não há data para aplicar — e a 094 também não dizia nada. Como a 091 lê só os ledgers, janela aberta sem produção **pesa 1,0**: a pessoa segue dividindo a produção depois de ter saído. Acompanha `desligados_sem_data` com o `ultimo_contrato` de cada uma, que é a data que o backfill usaria. |
| **Status só muda quando a planilha fala** | `coalesce(planilha, banco, 'Ativo (a)')`. Célula vazia preserva; `Ativo (a)` vale só para pessoa nova. |
| **Linha inalterada não é reescrita** | `WHERE tgt.status IS DISTINCT FROM EXCLUDED.status`. Sem isso o upload carimba `now()` em todas as linhas na mesma instrução e iguala os `updated_at` — que é o desempate de cadastro duplicado tanto no dashboard (`_colapsar_cadastro_recente`) quanto no Caderno (`consultores_mais_recentes`, CTE das migrations 073/075/092). Simulado com todos empatados: o cadastro ativo salta de 167 para 182 pessoas. |

O contador **não fecha janela**. Fechar exigiria uma data, e a única
disponível seria inferida — o oposto de "declarado vence inferido".
Fechar por status seria parâmetro novo, logo assinatura nova, logo `DROP`
+ redeploy coordenado. A 095 faz o número **aparecer**; agir sobre ele
continua sendo ato explícito.

Campos novos no envelope, nada removido nem renomeado:
`cadastro.inalterados`, `diagnostico.desligados_com_janela_aberta`,
`diagnostico.desligados_sem_data`. `cadastro.atualizados` muda de
significado — linhas *alteradas*, não linhas *tocadas*.

### 4.4 Tudo-ou-nada: onde vale e onde não vale

O §3.2 diz que uma linha inválida derruba a carga inteira. O importador
aplica isso de forma **assimétrica**, de propósito:

- **Bloco de afastamento — aborta.** Em `SNAPSHOT`, ausência significa
  retorno: a 090 fecha a janela de quem sumiu do arquivo. Uma linha
  recusada sairia do bloco e ficaria indistinguível de "voltou ao
  trabalho" — um erro de digitação no tipo encerraria o afastamento da
  pessoa e a devolveria ao denominador. Então a carga inteira para.
- **Datas de admissão/desligamento — avisam e seguem.** Data ilegível
  cai no fallback derivado da produção, que é exatamente o que já vale
  hoje. Não muda nada, e derrubar o arquivo por uma célula mal digitada
  seria pior que o defeito.

A régua é o efeito, não a severidade: recusa que **escreve** aborta;
recusa que apenas **mantém o estado atual** avisa.

### 4.5 RPC de movimentos históricos (migration 097)

```text
fn_movimentacoes_rh_import(
  p_afastamentos jsonb,
  p_desligamentos jsonb,
  p_validar_apenas boolean DEFAULT true
)
```

A função valida identidade, loja, datas, duplicidades, janelas `MANUAL` e
contratos posteriores antes de qualquer escrita. Na aplicação, atualiza a foto
de consultores, fecha as vigências de consultor e supervisor, encerra eventual
afastamento aberto no desligamento e executa o fechamento de afastamentos por
produção. Reimportar o mesmo evento já fechado não o reabre.

O envelope contém somente contagens e códigos por número de linha; nunca nome,
tipo ou observação. `EXECUTE` permanece exclusivo de `service_role`.

## 5. Ordem de chamada

```
1. carga de contratos          (já existe)
2. fn_headcount_replace        arquivo HC inteiro — cadastro + vigência +
                               afastamento numa transação. O bloco de
                               afastamento é delegado internamente à 090,
                               que fecha por produção ANTES de fechar por
                               ausência, para não perder a data exata.
3. fn_materializar_caderno(mes, ano)   para cada competência afetada
```

O passo 3 **não é opcional**: `caderno_fechamento_snapshot` congela o payload
(migration 080). Sem rematerializar, o Caderno que o bereshit publica diverge
do dashboard.

## 6. Contrato com o bereshit

Requisito do usuário (2026-08-20): **o bereshit tem que refletir o Dashboard.**
Os dois passam a publicar o mesmo denominador e a mesma produtividade.

Implementação que atende sem quebrar a auditoria:

| Campo | Antes | Depois (migration 092, aplicada em 2026-08-21) |
|---|---|---|
| `activeConsultants` | `integer` do cadastro de HOJE | **`integer` point-in-time** — as `cabecas` do ledger na competência |
| `weightedHeadcount` | — | **novo**, `numeric` — o denominador real |
| `productivity` | `pago / activeConsultants` | **`pago / weightedHeadcount`** |
| `headcountDiagnostics.countedInRegistry` | — | **novo** — o antigo `activeConsultants` (contagem de cadastro), para auditoria |

> ⚠️ Esta tabela foi **corrigida em 2026-08-21**. A versão anterior dizia que
> `activeConsultants` ficaria "inalterado". A decisão final (092) foi outra: ele
> passa a ser point-in-time, e a contagem de cadastro migra para
> `countedInRegistry`, dentro do bloco de diagnóstico.

O tipo continua `integer` — o que muda é a fonte. A identidade auditável que a
075 expôs (`activeRegistered = activeConsultants + supervisorsExcluded +
withoutActiveStore + backofficeExcluded`) **não quebra**, porque ela fecha
agora sobre `countedInRegistry`, dentro do próprio bloco de diagnóstico. Foi
por isso que o campo novo nasceu ali e não no `summary`.

Medido nas seis competências verificadas: `countedInRegistry` marca **124 fixo**
em cinco delas, enquanto `activeConsultants` varia de 108 a 134. É a patologia
inteira visível numa linha.

> ⚠️ **Dependência de deploy entre projetos.** No intervalo entre a migration
> entrar e o bereshit passar a ler `weightedHeadcount`, o relatório fica
> **internamente inconsistente**: mostraria headcount inteiro com produtividade
> calculada sobre o peso, e quem dividisse à mão não bateria. Os dois têm de
> sair na mesma janela, junto com a rematerialização dos snapshots.


## 7. O lado Python — o dashboard passou a dividir pelo mesmo peso

> Implementado em 2026-08-25. Era a pendência que mantinha os dois lados
> discordando, e a razão de o §6 nunca ter fechado de fato.

Até aqui o Caderno já dividia por `weightedHeadcount`, mas o dashboard
continuava dividindo por **quem produziu no período**. A distância entre
os dois números é pequena (em 07/2026: ~113 produtores contra peso
112,4782), e por isso passou tanto tempo despercebida. O problema não é o
tamanho, é a **direção**:

> Excluir quem não vendeu faz a média do dashboard **subir** exatamente
> no mês em que mais gente não vendeu — enquanto a do Caderno **desce**.
> Andando em sentidos opostos, nenhuma reconciliação era possível.

`carregar_headcount_ponderado(mes, ano)` (`src/dashboard/loaders.py`) lê
`fn_headcount_ponderado` e devolve peso/cabeças por loja. Reaplica os
**mesmos dois filtros** que a 092 reaplica sobre a 091 — loja inativa e
backoffice (`LOJAS_BACKOFFICE = {"VAI E VEM"}`, o mesmo literal do CTE
`lojas_backoffice`) — porque a 091 responde "quem estava onde", não "o
que entra na média". Supervisores já saem dentro da própria 091.

O escopo do denominador vem do **filtro**, nunca da produção: uma loja
dentro do escopo continua no denominador mesmo sem contrato no período.
É o princípio que `aplicar_rls_metas` já seguia, e usar presença de
contrato como proxy reintroduziria o viés inteiro.

Verificado ponta a ponta em 07/2026: o peso somado pelo loader dá
**112,4782**, idêntico ao `weightedHeadcount` que o Caderno publica —
derivado por dois caminhos independentes (loader Python e SQL da 092).

**Uma granularidade que não existe:** com **um consultor selecionado** na
sidebar, `peso_headcount_escopo` devolve `None` e o card volta a dividir
por quem produziu. A 091 agrega por LOJA e não há peso por pessoa;
restringir a uma pessoa deixaria o denominador da loja inteira contra a
produção de uma só. O retorno das médias traz
`denominador_consultores` (`"peso"` ou `"produtores"`) para que o rodapé
do card diga por qual dos dois a média foi dividida.

**Mês corrente:** o peso é sempre o da competência inteira (a 091 calcula
sobre os DU cheios do mês); a divisão por `du_decorridos` continua
separada. Quem saiu no meio já entra com peso parcial e quem está com
janela aberta pesa 1,0 de qualquer forma.
