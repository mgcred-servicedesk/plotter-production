# 2026-08-25 — Guardas de cadastro no headcount (migration 095)

**Agente:** Claude Code
**Tipo:** bugfix (cross-repo: `Numeros_venda` + `angry-man`)
**Arquivos tocados:**
`database/migrations/095_fn_headcount_guardas_cadastro.sql` (novo),
`docs/HEADCOUNT_ETL.md`;
no `angry-man`: `src/services/import-cadastros.ts`,
`tests/unit/import-consultores.test.ts`, `scripts/generate-templates.ts`,
`public/templates/HC_Colaboradores.{xlsx,csv}`, `docs/headcount.md`
**Commit(s):** —

## Objetivo

Revisar como o headcount passou a ser contado (087–094) contra o
importador do `angry-man` e o template que o RH recebe, e corrigir o que
divergisse. A revisão apontou seis itens; este registro cobre os que
foram implementados.

## O que foi feito

**Migration 095 — `fn_headcount_replace`, mesma assinatura.** Três
guardas, nenhuma mudando número publicado hoje:

1. **`desligados_com_janela_aberta` + `desligados_sem_data`** no bloco
   `diagnostico`. Era o espelho ausente de `ativos_com_janela_fechada`.
2. **Status só muda quando a planilha fala** —
   `coalesce(planilha, banco, 'Ativo (a)')`.
3. **Linha inalterada não é reescrita** —
   `WHERE tgt.status IS DISTINCT FROM EXCLUDED.status`.

**`angry-man`:** o importador manda `status: null` quando a célula está
vazia (sem isso a guarda 2 nunca veria NULL), traduz os contadores novos
em mensagens acionáveis, e **aborta a carga** quando o bloco de
afastamento tem linha recusada. Template com as notas de `STATUS`
corrigidas e regerado. 81 testes passando, `tsc --noEmit` limpo.

## Achados da medição

Leitura pura do banco em 2026-08-25 (`.venv`, sem escrita). Três coisas
só apareceram porque o estado real foi medido antes de escrever SQL.

**1. O furo grave ainda não aconteceu — e é por isso que caberia agora.**
`consultor_vigencia` tem 395 janelas com origem `BACKFILL_*` e `MANUAL`,
**zero `ETL`**: o ledger nunca recebeu escrita do importador. Pessoas com
cadastro `Desligado (a)` e janela ainda aberta: **0**. O contador novo
nasce em 0, então qualquer valor futuro é sinal puro.

O desvio que ele mede: a 091 lê só os ledgers, e janela aberta sem
produção pesa 1,0. Fluxo histórico de saídas = 8,8 pessoas/mês (pico 17
em 07/2026). Sobre o peso de 116,33 de 08/2026, isso é +22,7% de
denominador em 3 meses — produtividade por cabeça caindo 18,5% sem que
nada tenha piorado de verdade.

**2. `updated_at` era carga explosiva, e atinge o bereshit também.** A
094 fazia `ON CONFLICT DO UPDATE` em todas as linhas numa instrução; o
trigger `trg_consultores_updated_at` dispara mude o valor ou não. Um
upload igualava os 424 `updated_at` — e `updated_at` é o desempate de
cadastro duplicado em **dois** consumidores:

- dashboard, `_colapsar_cadastro_recente` (`src/dashboard/loaders.py`):
  comparação estrita, empate deixa vencer a primeira linha que a query
  devolver — ordem que o Postgres não garante;
- Caderno / bereshit, CTE `consultores_mais_recentes` de
  `obter_caderno_fechamento` (migrations 073/075/092):
  `ORDER BY nome_normalizado, updated_at DESC NULLS LAST, id DESC` —
  empate cai no `id DESC`, um UUID aleatório.

Medido: 328 pessoas em 424 linhas, 78 com cadastro duplicado, **27 delas
com `Ativo (a)` E `Desligado (a)` ao mesmo tempo**. Simulando o empate, o
cadastro ativo salta de **167 para 182** — 16 desligados viram ativos
(HELOINA entre eles) e 1 ativa vira desligada (ERICA, cujas janelas
`MANUAL` as 088/089 foram escritas para proteger).

No Caderno isso **não** desloca `weightedHeadcount` nem `productivity`,
que vêm da 091 e leem só os ledgers. Desloca `activeRegistered` e
`countedInRegistry` no bloco de auditoria, e com eles a identidade da
075. No dashboard desloca o universo de ativos de verdade.

**3. Linha de afastamento recusada equivalia a "voltou ao trabalho".**
Tipo fora do vocabulário ou `AFASTAMENTO_INICIO` faltando zeravam
`afastamentoTipo` e a linha caía fora do bloco. Em `SNAPSHOT`, ausência
**é** retorno: a 090 fecha a janela por ausência. Um erro de digitação no
tipo encerrava o afastamento e devolvia a pessoa ao denominador. Os dois
testes que fixavam esse comportamento foram reescritos.

## Decisões não óbvias

- **A 095 não fecha janela, só reporta.** Fechar exigiria uma data, e a
  única disponível é inferida (fim do mês do último contrato) — o oposto
  de "declarado vence inferido". E fechar por status seria parâmetro
  novo, logo assinatura nova, logo `DROP FUNCTION` + redeploy coordenado
  do `angry-man` (o aviso da 094 sobre sobrecarga). Fica como decisão
  separada do usuário. A migration faz o número **aparecer**.

- **Assinatura preservada de propósito.** Só campos novos no envelope,
  nada removido nem renomeado, então a versão atual do `angry-man`
  continua funcionando sem redeploy — apenas não mostra os campos novos.
  `cadastro.atualizados` muda de significado (linhas alteradas, não
  linhas tocadas) e ganha `inalterados` ao lado; nenhuma decisão
  automática depende dele.

- **Tudo-ou-nada assimétrico, e a régua é o efeito.** Recusa que
  **escreve** aborta (afastamento, porque fecha janela e muda o
  denominador); recusa que apenas **mantém o estado atual** avisa e segue
  (data ilegível, que cai no fallback já vigente). Derrubar o arquivo
  inteiro por uma célula de data mal digitada seria pior que o defeito.
  Registrado em `docs/HEADCOUNT_ETL.md` §4.4.

- **Contador conta PESSOA e exige que nenhuma linha a declare ativa.**
  Desligado numa loja e ativo em outra é transferência, não saída — 77
  das 328 pessoas têm mais de uma loja, então contar linha daria falso
  positivo em massa.

- **`pglast` em vez de banco de teste.** A 095 foi validada com
  `parse_sql` + `parse_plpgsql` (requirements-dev) e cada statement novo
  reparseado isolado. Não substitui execução — o bloco de validação do
  arquivo cobre o resto.

## Divergência doc × código corrigida

`angry-man/docs/headcount.md` §3 afirmava que "o dashboard não conta mais
cabeças para dividir a produção". Falso: quem lê `fn_headcount_ponderado`
é o Caderno (092). Nenhum arquivo Python do `Numeros_venda` referencia a
função — `carregar_consultores_ativos()` segue lendo a foto de
`consultores`, sem competência e sem peso. Corrigido com nota do que
ainda falta.

## Pendências / follow-ups

- [ ] **095 é sua para aplicar** — arquivo com bloco de validação em 7
      passos (assinatura única, recusas, idempotência real, `updated_at`
      intocado, status preservado, contador disparando, transferência não
      virando saída), todos em `BEGIN/ROLLBACK`.
- [ ] **Decidir sobre fechar janela por status** — parâmetro novo exige
      `DROP FUNCTION` + redeploy do `angry-man` na mesma janela.
      Alternativa: RPC dedicada de desligamento pontual.
- [ ] **Passo Python** (segue pendente, e é o que faz dashboard e Caderno
      concordarem): `carregar_consultores_ativos(mes, ano)` sobre
      `fn_headcount_ponderado`, denominadores de `gerais.py` /
      `pontuacao.py` / `produtos.py` somando peso.
- [ ] **Redeploy da Edge Function `reconquista-rpc`** — continua pendente
      da sessão de 21/ago (whitelist já no código).
- [ ] **RH acrescentar as cinco colunas.** Até lá o import roda em `SKIP`.
- [ ] Itens da revisão **não** implementados, por serem de menor impacto:
      `Obs` saiu do template (o contrato §2 dizia que continuaria) e
      `observacao` de afastamento nunca é enviado pelo importador, apesar
      de constar no contrato §3.1 e ser lido pela 094.
- [ ] `ativos_com_janela_fechada` conta linha, não pessoa — mesma
      assimetria que o contador novo evita. Não tocado para não mexer em
      número já reportado.

## Referências

- [HEADCOUNT_ETL.md](../../HEADCOUNT_ETL.md) — contrato, §4.3 e §4.4 novas
- [progress/2026-08-21-angry-man-headcount-etl.md](2026-08-21-angry-man-headcount-etl.md)
- [progress/2026-08-21-caderno-headcount-ponderado.md](2026-08-21-caderno-headcount-ponderado.md)
- Migrations: 091 (peso), 092 (Caderno), 094 (RPC), 095 (esta)
