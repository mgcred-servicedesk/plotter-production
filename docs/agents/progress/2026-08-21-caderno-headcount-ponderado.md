# 2026-08-21 — Caderno: headcount point-in-time e produtividade sobre o peso (092)

**Agente:** Claude Code
**Tipo:** bugfix de regra de negócio (quebra de contrato deliberada)
**Arquivos tocados:** `database/migrations/092_caderno_headcount_ponderado.sql`
**Commit(s):** (pendente)

## Objetivo

Fechar o item 092 da fila de [2026-08-20](2026-08-20-consultor-vigencia-granularidade-dia.md):
`obter_caderno_fechamento` passa a consumir a `fn_headcount_ponderado` (091)
em vez de contar o cadastro de hoje. É a migration que destrava a
rematerialização das 14 competências, segurada desde a 088.

## O que foi feito

- **092 escrita e validada** (ainda **não aplicada**). Cópia da 085 com o
  diff restrito às CTEs de headcount e produtividade — produção, metas,
  ranking, série mensal, MIX e produto ficam byte-idênticos, conferido por
  `diff` do corpo da função.
- Contrato v1.7: `summary.activeConsultants` e
  `productivity[].activeConsultants` passam a ser `cabecas` (inteiro
  point-in-time); nascem `summary.weightedHeadcount` e
  `productivity[].weightedHeadcount`; `productivity[].productivity` passa a
  ser PAGO / **peso**.
- Sintaxe validada com `pglast` (4 statements; corpo da função parseia), e
  cada número do bloco de validação **medido contra o banco** antes de
  escrever o SQL.

## A patologia, agora medida ponta a ponta

O headcount do Caderno devolvia **124 fixo** em quase toda competência — não
porque o quadro fosse estável, mas porque só existe UMA foto de cadastro e ela
é a de hoje:

| competência | cadastro (hoje) | `cabecas` (ledger) | peso |
|---|---|---|---|
| 07/2025 | 124 | 108 | 101,5652 |
| 12/2025 | 124 | 130 | 123,9347 |
| 02/2026 | 124 | 118 | 115,3889 |
| 03/2026 | 124 | 128 | 122,5001 |
| 06/2026 | 124 | 134 | 123,8573 |
| 07/2026 | 122 | 122 | 114,3043 |

## Decisões não óbvias

- **`activeConsultants` passa a sair do ledger** (usuário, 2026-08-21). A
  decisão de 20/08 — "segue inteiro (auditoria de cadastro)" — comportava as
  duas leituras: *continua sendo inteiro* ou *continua vindo do cadastro*. A
  diferença chega a 16 pessoas (07/2025). Escolhido point-in-time; a
  alternativa deixaria o Caderno publicando dois inteiros que discordam entre
  si e **não** resolveria o drift, porque a versão ao vivo continuaria sendo
  reescrita por qualquer carga de RH.
- **A identidade do `headcountDiagnostics` muda de significado.** Até a 085
  valia `activeRegistered = activeConsultants + supervisorsExcluded +
  withoutActiveStore + backofficeExcluded`. Com `activeConsultants` vindo de
  outra foto, essa soma deixa de fechar. Em vez de largar a auditoria, o
  número antigo entra no próprio bloco como **`countedInRegistry`** e a
  identidade continua valendo lá dentro. Ler
  `countedInRegistry <> activeConsultants` não é defeito: é a distância entre
  o cadastro de hoje e o quadro daquele mês, agora visível em vez de
  silenciosa.
- **Os dois filtros do leitor ficam no leitor.** A 091 devolve toda loja com
  vínculo, inclusive backoffice (VAI E VEM aparece com peso 2,0) e loja
  inativa — ela responde "quem estava onde", não "o que entra no Caderno".
  Reaplicar `tem_loja_ativa` e `NOT eh_backoffice` na 092 mantém a 091
  reutilizável pelo dashboard (093) sem herdar as regras de recorte do
  relatório.
- **Peso 0 com pago > 0 devolve produtividade 0**, mesmo idioma que a 085 já
  usava para `ativos = 0`. Medido: 1 loja em 07/2025 (PDV BELFORD ROXO II, sem
  nenhuma linha no ledger) contra 2 no critério antigo — o ledger piora nada
  aqui.

## O impacto é de cauda, não de patamar — e isso muda o aviso às lojas

Comparando os 14 snapshots publicados contra o denominador novo:

| competência | lojas | média | **mediana** | maior alta |
|---|---|---|---|---|
| 05/2025 | 43 | +20,2% | **+0,0%** | HELP TIJUCA ALMIRANTE +200% |
| 07/2025 | 43 | +17,1% | **+0,0%** | HELP VICENTE DE CARVALHO +200% |
| 03/2026 | 45 | +6,3% | **+0,0%** | HELP COPACABANA +358% |
| 05/2026 | 45 | −0,7% | **+0,0%** | HELP COPACABANA +233% |
| 07/2026 | 47 | +6,5% | **+0,0%** | HELP COPACABANA +150% |

**A mediana é +0,0% nas 14 competências.** A maioria das lojas não muda nada —
para elas `peso = cabecas = cadastro`. A média é puxada por poucos outliers, e
o outlier se repete: HELP COPACABANA aparece em quase todo mês.

Isso **corrige o aviso registrado em 2026-08-20** ("derruba todas as médias
publicadas... é mudança de patamar"). A direção estava certa mas o formato
não: não é um deslocamento geral, é um punhado de lojas com correção grande.
O aviso deve ser dirigido a essas lojas, não a todas.

## HELP COPACABANA — o outlier que valida o ledger

O cadastro de hoje põe 6 ativos na loja. Onde essas pessoas estavam de fato em
03/2026, segundo `consultor_vigencia`:

| pessoa | 03/2026 |
|---|---|
| CAMILLY | HELP COPACABANA ✓ |
| DJANE | HELP COPACABANA **NOVA** |
| EVILLYN | HELP COPACABANA **NOVA** |
| VICTOR | HELP **LARANJEIRAS** |
| LETICIA | entra só em 25/05/2026 |
| YGOR | entra só em 19/08/2026 |

O denominador antigo dividia o pago de março por gente que estava em outra
loja ou que nem tinha sido admitida. O ledger devolve `cabecas = 2`, `peso =
1,0909` (CAMILLY 22/22 + JOSEPH 2/22; PAMELA sai por ser supervisora). O
+358% é correção, não artefato — e o par COPACABANA / COPACABANA NOVA é
exatamente o tipo de vizinhança que a foto única de cadastro embaralha.

## Invariantes verificadas antes de escrever o SQL

Nas 6 competências medidas, todas passam:

- `peso <= cabecas` em toda loja — 0 violações;
- soma das linhas de `productivity` == `summary.weightedHeadcount` — diff 0,0000
  em todas (nenhuma loja tem gente no ledger sem produção nem meta);
- caso ERICA atravessa 091 → Caderno sem se perder: 06/2026 devolve `cabecas 3`
  e `peso 2,3810` (fração pura 8/21, sem piso, porque a data é declarada);
- identidade do diagnóstico fecha em 0.

## Verificação pós-aplicação (2026-08-21)

**092 APLICADA.** Os 6 primeiros checks passam com os valores **exatos** da
simulação feita antes de escrever o SQL — nenhum ajuste foi necessário:

| check | resultado |
|---|---|
| 1 — `activeConsultants` point-in-time | 108 · 130 · 118 · 128 · 134 · 122, como medido |
| 2 — `weightedHeadcount` | 101,5652 · 123,9347 · 115,3889 · 122,5001 · 123,8573 · 114,3043 |
| 3 — `peso <= cabecas` por loja | 0 violações nas 6 competências |
| 4 — soma das lojas == summary | diff 0,0000 nas 6 |
| 5 — caso ERICA | 06/2026 → 3 e 2,3810; 07/2026 → 4 e 3,3043 |
| 6 — identidade do diagnóstico | 0 nas 6 |

O check 6 mostra a distância que a migration tornou visível:
`countedInRegistry` marca **124 fixo** em 5 das 6 competências enquanto
`activeConsultants` varia de 108 a 134. É a patologia, agora publicada como
dois campos que se explicam em vez de um número só que mentia.

### Check 7 achou uma divergência REAL, e ela não é da 092

`paidEffective` ao vivo diverge do snapshot em **07/2026** — e só nela:

| medida | snapshot (18/08) | ao vivo | diff |
|---|---|---|---|
| paidEffective | 10.144.083,89 | 10.143.514,91 | **−568,98** |
| validProduction | 9.669.556,87 | 9.668.987,89 | −568,98 |
| effectivePoints | 30.557.321,70 | 30.556.468,23 | −853,47 |

Uma única loja muda: **HELP SAO GONCALO** (276.868,34 → 276.299,36). O
contrato de R$ 568,98 **não existe mais** em `v_contratos_dashboard` (busca por
valor na competência devolve 0 de 196 contratos da loja), então saiu da origem
— cancelamento ou correção no ETL entre 18/08 e 21/08, não efeito de migration.
A 092 não toca produção; o diff em `effectivePoints` acompanha na proporção do
produto, o que é coerente com um contrato inteiro removido.

**A rematerialização vai absorver isso, e deve mesmo** — mas quem comparar o
Caderno de julho antes e depois vai ver a produção mudar junto com o
denominador, e as duas causas não têm nada a ver uma com a outra.

### Estado dos snapshots

Os **14 snapshots seguem defasados** (nenhum tem `weightedHeadcount`), todos
gerados em 18/08. `activeConsultants` congelado em 119 contra 102–134 ao vivo.
Correto: a rematerialização está segurada de propósito até o bereshit ler o
campo novo.

## Pendências / follow-ups

- [x] **092 APLICADA e verificada** (2026-08-21) — checks 1 a 6 exatos
- [ ] **Deploy coordenado, na mesma janela** — nesta ordem: (1) aplicar a 092;
      (2) subir o bereshit lendo `weightedHeadcount`; (3) rematerializar as 14.
      Entre (1) e (2) o relatório fica internamente inconsistente
- [ ] **Rematerializar as 14 competências**, não as 6 da instrução da 088 — o
      eixo de headcount muda todas. Bloco pronto no fim da 092 (a tabela
      `caderno_fechamento_snapshot` usa `ano`/`mes`, não `competencia_*`)
- [ ] **Avisar as lojas da cauda**, não todas — ver a tabela de impacto acima
- [ ] **Passo Python** — `carregar_consultores_ativos(mes, ano)` com coluna
      `PESO`; denominadores de `gerais.py` / `pontuacao.py` / `produtos.py`
      somam `PESO`. Segue pendente e é o que faz dashboard e Caderno
      concordarem. **Não chamar de "093"**: o número virou arquivo `.sql`
      (`093_rls_deny_explicito.sql`) — a própria migration registra a
      desambiguação no cabeçalho
- [ ] Confirmar com o ETL o contrato de R$ 568,98 que sumiu de HELP SAO
      GONCALO em 07/2026 (ver check 7). Se foi cancelamento legítimo, nada a
      fazer além de rematerializar
- [ ] Janelas com início em **2026-09-01** (CAMILLY e VICTOR voltando para
      COPACABANA) são futuras em relação a hoje — é o backfill datando a
      posição do cadastro atual no mês seguinte. Não afeta competência
      fechada, mas vale confirmar que é intencional antes do ETL escrever

## Referências

- Entrada anterior: [2026-08-20](2026-08-20-consultor-vigencia-granularidade-dia.md)
- Migrations relacionadas: 085 (base copiada), 088, 089, 090, 091
- Docs consultados: [business-rules.md](../business-rules.md),
  [data-layer.md](../data-layer.md)
