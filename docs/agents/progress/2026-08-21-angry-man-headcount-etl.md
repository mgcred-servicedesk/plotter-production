# 2026-08-21 — angry-man alinhado ao headcount ponderado (migration 094)

**Agente:** Claude Code
**Tipo:** feature (cross-repo: `Numeros_venda` + `angry-man`)
**Arquivos tocados:**
`database/migrations/094_fn_headcount_replace.sql`, `docs/HEADCOUNT_ETL.md`;
no `angry-man`: `src/services/import-cadastros.ts`,
`src/services/materializar-caderno.ts` (novo), `src/services/import-registry.ts`,
`src/App.tsx`, `src/lib/supabase.ts`,
`supabase/functions/reconquista-rpc/index.ts`,
`scripts/generate-templates.ts`, `tests/unit/import-consultores.test.ts` (novo),
`docs/importacao.md`
**Commit(s):** —

## Objetivo

Com as migrations 087–093 aplicadas, o ETL continuava falando com o schema
antigo. Alinhar o `angry-man` aos três ledgers e ao Caderno ponderado.

## O que foi feito

- **Migration 094 — `fn_headcount_replace`.** Fecha o contrato que a 090 abriu
  pela metade: uma RPC para o arquivo HC inteiro, numa transação, atualizando
  `consultores` + `consultor_vigencia` + (delegado) `consultor_afastamento`.
  Era a peça que `docs/HEADCOUNT_ETL.md` §4.2 registrava como "ainda não
  escrita".
- **`importConsultores` reescrito.** Deixa de fazer upsert direto e passa a
  chamar a RPC. Lê as cinco colunas novas do contrato e traduz o envelope em
  mensagens acionáveis.
- **Card "Rematerializar Caderno"** (`materializar-caderno.ts` + registry +
  App), com opção de rodar **todas as competências fechadas** em série. É o
  passo 3 da ordem de chamada, que não existia em lugar nenhum do `angry-man`.
- **Roteamento web:** `fn_headcount_replace`, `fn_afastamentos_replace` e
  `fn_materializar_caderno` no `RPC_ENDPOINT_MAP` e na whitelist da Edge
  Function.
- **14 testes novos**; suíte do `angry-man` em 75 passando, `tsc --noEmit` limpo.
- `docs/HEADCOUNT_ETL.md` corrigido (ver "Divergência doc × código" abaixo).

## Achados da medição

Três coisas só apareceram porque o estado real foi medido antes de escrever o
SQL.

**1. O importador nunca leu o arquivo real.** `HC_Colaboradores.xlsx` tem
`FILIAL` e `VENDEDOR`; `importConsultores` só aceitava `LOJA` e `NOME`. Toda
linha do arquivo de produção falhava com "Nome do consultor obrigatório".
`import-contratos.ts:48-49` já mapeava esses dois nomes — o de cadastros nunca
recebeu. Bug pré-existente, no caminho de tudo que vinha agora.

**2. `normalizeHeader` preserva underscore.** As colunas do contrato são
`DATA_ADMISSAO`, `TIPO_AFASTAMENTO`… e os alias que escrevi usavam espaço.
Nenhuma casaria. Pego pelos testes, não pela leitura. Agora underscore e espaço
são o mesmo separador (`chaveHeader`).

**3. HELOINA DE AQUINO — desligamento fantasma.** Está no cadastro com
`status = 'Licença Maternidade'`. A regra `eh_ativo` da 087 é `LIKE 'ATIVO%'`,
então ela não passa e o backfill **fechou a janela dela em 2026-05-01**, como
se tivesse sido desligada. Ela não foi: está afastada. Hoje ela nem aparece em
`cabecas`; no desenho correto aparece com peso 0 e volta sozinha quando o
afastamento fechar. É a prova viva de que `STATUS` como canal de afastamento
produz saída falsa — o motivo pelo qual a 094 adota regra própria e mais
estreita: **desligado é só `status LIKE 'DESLIG%'`**.

## Decisões não óbvias

- **`p_reabrir_ativos` não é o padrão.** Pessoa que a planilha declara ativa e
  cuja janela o backfill fechou por inferência é contradição real, e a
  precedência ("declarado vence inferido") mandaria reabrir. Mas reabrir muda
  número já publicado, retroativamente e em massa. Simulado com o export de
  março que está no repositório: **46 janelas seriam reabertas**, das quais 45
  são apenas a planilha estar velha (`Ativo (a)` nela, `Desligado (a)` no
  banco) e 1 é HELOINA. O padrão diagnostica; reabrir é ato explícito. Mesma
  lição da 090: o caminho que mexe em tudo de uma vez não pode ser alcançável
  por acidente.

- **`origem = 'MANUAL'` é intocável.** Não estava no contrato. Sem essa guarda,
  a primeira carga do HC sobrescreveria as janelas MANUAL de ERICA — que as
  088/089 foram escritas para criar — e faria isso de novo a cada upload, em
  silêncio. A 077 já tinha resolvido o mesmo conflito para supervisores:
  divergência se **reporta**, não se aplica. Aqui a regra é a mesma.

- **Produção não se desmente.** Admissão declarada depois do primeiro contrato
  digitado é contradição factual; a 094 reporta e não escreve. A assimetria é
  deliberada e vem da 087 — produção prova presença, a falta dela não prova
  ausência. Por isso o inverso não vale: desligamento sem produção posterior é
  aceito sem discussão.

- **Modo `SKIP`, que não existe na 090.** `SNAPSHOT` vazio é recusado de
  propósito. Mas "arquivo sem as colunas" e "arquivo dizendo que ninguém está
  afastado" são afirmações diferentes que um array vazio não distingue. SQL não
  vê a diferença; o `angry-man` vê. Quem decide é a presença da **coluna**, não
  do valor.

- **Card próprio para o Caderno, não gancho pós-import.** Uma janela de
  vigência atravessa várias competências, então a carga de agosto pode mudar o
  denominador de maio. Pendurar a materialização no fim de um import sugeriria
  que só a competência importada muda — que é falso. Em série, nunca em
  paralelo: ~4 s cada, em compute Nano.

- **`RETURNING xmax = 0` descartado.** Distinguiria insert de update numa
  passada, mas depende de detalhe interno não garantido pela documentação. A
  contagem prévia custa um index scan e não depende de nada.

## Divergência doc × código corrigida

`docs/HEADCOUNT_ETL.md` §6 dizia que `activeConsultants` ficaria
"`integer`, inalterado". A decisão final (092, aplicada) foi outra: ele passa a
ser point-in-time (`cabecas` do ledger) e a contagem de cadastro migrou para
`headcountDiagnostics.countedInRegistry`. A tabela foi corrigida com nota do
que mudou. A identidade auditável da 075 não quebra — ela fecha agora sobre
`countedInRegistry`, dentro do próprio bloco de diagnóstico.

## Pendências / follow-ups

- [ ] **094 é sua para aplicar** — arquivo entregue com bloco de validação
      (recusas, dry run em `BEGIN/ROLLBACK`, checagem de idempotência).
- [ ] ⚠️ **Não carregar o `HC_Colaboradores.xlsx` do repositório.** É export de
      março; `fn_headcount_replace` faz upsert em `consultores.status` e
      **reativaria 45 desligados**. Exigir export fresco. Registrado também no
      cabeçalho da migration.
- [ ] **Redeploy da Edge Function `reconquista-rpc`** — a whitelist mudou. Sem
      isso o modo web falha com "Funcao nao permitida"; o Electron não é
      afetado (chama a RPC direto).
- [ ] **RH acrescentar as cinco colunas** ao HC. Até lá o import roda em `SKIP`
      e o comportamento é o de hoje.
- [ ] **Passo Python** (segue pendente, independente disto):
      `carregar_consultores_ativos(mes, ano)` com coluna `PESO`; denominadores
      de `gerais.py` / `pontuacao.py` / `produtos.py` somam `PESO`. É o que faz
      dashboard e Caderno concordarem.
- [ ] Rematerializar as 14 competências — agora com botão próprio no
      `angry-man`, depois que o bereshit passar a ler `weightedHeadcount`.
- [ ] Confirmar com o ETL o contrato de R$ 568,98 que sumiu de HELP SÃO GONÇALO
      em 07/2026 entre 18/08 e 21/08.
- [ ] Revisar o caso HELOINA depois da primeira carga com `TIPO_AFASTAMENTO`:
      a janela dela precisa ser reaberta e o afastamento registrado.

## Referências

- [docs/HEADCOUNT_ETL.md](../../HEADCOUNT_ETL.md) — contrato de ETL (atualizado)
- [progress/2026-08-21-caderno-headcount-ponderado.md](2026-08-21-caderno-headcount-ponderado.md)
- [progress/2026-08-20-consultor-vigencia-granularidade-dia.md](2026-08-20-consultor-vigencia-granularidade-dia.md)
- Migrations: 086/087 (ledger), 089/090 (afastamento), 091 (peso), 092 (Caderno), 094 (esta)
