# 2026-08-31 — Plano: produtividade gerencial sem cobertura de afastamentos

**Agente:** Codex
**Tipo:** research + plan (IMPLEMENT pendente de aprovação)
**Arquivos tocados nesta sessão:** somente este documento
**Commit(s):** —

## Objetivo

Materializar na origem a produtividade individual prevista no contrato v2 do
Bereshit e usar parte dessa base no dashboard do `Numeros_venda` para mostrar
a evolução de produtividade no nível do gerente comercial.

A primeira entrega não espera o arquivo de afastamentos do RH. Ela mede
produção paga por **dia útil elegível no vínculo** e publica explicitamente:

```text
consideredDaysBasis = ELIGIBLE_LINK_DAYS
absenceCoverage = NONE
```

Essa métrica não representa presença real. Férias, faltas e afastamentos não
registrados não são descontados. Por isso a entrega é exploratória: não libera
score, alerta, quadrante, ranking decisório nem automação de RH.

Este plano parte da pesquisa aprovada em 2026-08-31 e do contrato registrado
no penúltimo commit do Bereshit (`24af90a`).

=== PLAN ===
Abordagem escolhida: criar uma única apuração SQL derivada de fato diário, com coleções mensal e semanal congeladas por competência; publicar a base transitória ELIGIBLE_LINK_DAYS sem consultar afastamentos; consumir os snapshots fechados numa subvisão Produtividade da aba Evolução, sempre após RLS, agregando a carteira atual do gerente e suas lojas.
Alternativas descartadas:
  - calcular a evolução apenas em pandas a partir de contratos: duplicaria a regra do Caderno, não preservaria snapshots e faria dashboard e Bereshit divergirem.
  - reutilizar fn_headcount_ponderado como denominador individual: a função retorna somente loja, aplica piso a fronteiras inferidas e hoje pode descontar afastamentos de cobertura parcial; ela não representa consideredWorkingDays por pessoa.
  - usar quantidade de consultores que produziram: remove os zerados do denominador e faz a média subir quando mais pessoas deixam de vender.
  - colocar a feature em Rankings: a superfície atual usa dados nominais pré-RLS e ranking individual sem afastamentos seria inadequado para decisão gerencial.
  - criar uma nova aba principal: Evolução já é a superfície temporal e o gerente já possui muitas abas; uma subvisão mantém a navegação centralizada.
  - chamar dias elegíveis de dias trabalhados: a origem ainda não comprova presença diária.
  - recalcular meses fechados ao vivo: mudanças posteriores de ledger alterariam o passado sem revisão nem rematerialização explícita.
Critérios de aceitação:
  - [ ] Toda linha mensal e semanal publica consideredDaysBasis = ELIGIBLE_LINK_DAYS e absenceCoverage = NONE.
  - [ ] A apuração transitória não consulta consultor_afastamento e a UI não usa a expressão dias efetivamente trabalhados.
  - [ ] Numerador individual inclui somente produção paga de consultores, excluindo supervisores pela âncora da competência e excluindo VAI E VEM.
  - [ ] Soma de paidEffective individual por loja/competência reconcilia com productivity.paidByConsultants da mesma revisão, com tolerância monetária de R$ 0,01.
  - [ ] 0 <= consideredWorkingDays <= periodWorkingDays em todas as linhas.
  - [ ] Transferência cria segmentos por consultantId + storeId sem duplicar produção ou dias.
  - [ ] O identificador provisório é a chave de nome normalizado usada pelos ledgers; a apuração falha com diagnóstico se detectar homônimo ou identidade ambígua.
  - [ ] Linha com pago = 0 e dias = 0 usa produtividade 0 por proteção; pago > 0 com dias = 0 bloqueia a publicação com diagnóstico e nunca cai para quantidade de produtores.
  - [ ] Semanas usam ISO segunda-domingo e somente as oito semanas completas mais recentes até o fechamento são publicadas.
  - [ ] Mensal e semanal derivam da mesma CTE diária e usam a data de pagamento como data do evento pago.
  - [ ] Competências fechadas permanecem congeladas até rematerialização deliberada.
  - [ ] A visão gerencial usa somente competências fechadas e interrompe variação quando há lacuna ou mudança de base.
  - [ ] Gerente sem escopo, sem REGIAO_ATUAL ou sem loja permitida recebe resultado vazio, nunca dados globais.
  - [ ] Gerente com múltiplas regiões vê somente a união das lojas da própria carteira atual.
  - [ ] A UI mostra produção dos consultores, dias elegíveis, produtividade por dia elegível, variação contra a competência anterior e decomposição por loja.
  - [ ] A UI mostra aviso permanente sobre ausência de cobertura e não oferece score, alerta, quadrante ou ranking individual nesta fase.
  - [ ] Card, série, tabela e exportação reconciliam para o mesmo filtro e competência.
  - [ ] Loaders novos seguem fetch sem cache + wrappers _atual/_historico; snapshots históricos usam TTL longo.
  - [ ] Migrations contêm consultas de verificação de invariantes, grants mínimos e rollback documentado.
  - [ ] ruff check passa em cada Python alterado e a suíte pytest afetada passa integralmente.
Arquivos a criar: `database/migrations/NNN_produtividade_individual_v2.sql`, usando o próximo número livre após reconciliar 095/096 (apuração diária, coleções e materialização privada); `src/dashboard/kpis/produtividade.py` (funções puras de agregação, benchmark e evolução); `tests/test_kpis_produtividade.py`; `tests/test_loaders_produtividade.py`; `tests/test_tabs_evolucao_produtividade.py`; `docs/agents/progress/AAAA-MM-DD-produtividade-individual-implementacao.md` (handoff final).
Arquivos a editar: database/migrations/096_produtividade_populacao_unica.sql somente se o proprietário confirmar que o rascunho local ainda pertence a esta frente; src/dashboard/loaders.py; src/dashboard/permissions.py; src/dashboard/tabs/evolucao.py; src/dashboard/ui/charts.py; app.py; tests/test_permissions.py; tests/test_rls.py; tests/test_app_smoke.py; docs/HEADCOUNT_ETL.md; docs/agents/business-rules.md. O Bereshit recebe handoff separado para adaptar a leitura caso a coleção individual fique em RPC privada.
Arquivos a deletar: nenhum.
Riscos:
  - cobertura parcial de afastamentos contaminar a base: a apuração v1 ignora explicitamente consultor_afastamento e publica base/cobertura em toda linha.
  - numerador e denominador usarem populações diferentes: migration 096 e datas de supervisor são checkpoint obrigatório antes da nova migration.
  - dados nominais entrarem no snapshot público: coleção individual fica privada/service_role; não ampliar grants de anon/authenticated.
  - nome não ser identidade permanente: usar a moeda atual dos ledgers apenas como chave provisória, com diagnóstico de homônimo e follow-up para identificador mestre.
  - pagamento não representar o dia do trabalho: rotular como produtividade de produção paga; não inferir atendimento/originação.
  - mês corrente distorcer tendência: primeira curva usa somente competências fechadas.
  - carteira atual reescrever a leitura territorial: declarar que a visão é da carteira atual olhando o histórico; manager histórico fica apenas como auditoria.
  - lojas inativas ou sem região atual escaparem do recorte: join obrigatório com cadastro atual e falha fechada quando não houver correspondência.
  - worktree existente ser sobrescrito: preservar 095/096 e alterações Python locais; reconciliar autoria e estado antes da primeira edição.

## Decisões de produto para esta primeira entrega

As decisões abaixo delimitam o incremento e evitam que o implementador
reabra o escopo das fases futuras:

1. **Métrica:** `paidEffective / consideredWorkingDays`, apresentada como
   “produtividade por dia elegível”. Não é a mesma unidade de
   `paidByConsultants / weightedHeadcount`, que permanece como produtividade
   mensal por gente-mês nos cards existentes.
2. **Evento do numerador:** pagamento, usando `data_status_pagamento`, porque
   `paidEffective` e a competência atual já seguem essa data. A tela deve
   dizer “produção paga”; a série não mede cadência de digitação.
3. **Território:** carteira atual do gerente olhando para trás, consistente
   com `aplicar_rls(... REGIAO_ATUAL)`. Região/gerente histórico permanece no
   payload para auditoria, mas não concede acesso.
4. **Período:** somente competências fechadas na curva. O mês corrente pode
   continuar nos cards operacionais existentes, mas não entra na variação da
   nova série nesta fase.
5. **Benchmark:** loja e carteira do gerente são calculados pela razão das
   somas (`sum(paid) / sum(days)`), nunca pela média simples das
   produtividades individuais.
6. **Uso:** exploração gerencial agregada e por loja. O fato individual é
   materializado para o contrato do Bereshit, mas o dashboard não cria
   ranking nominal ou lista de “piores consultores” nesta fase.
7. **Ausências:** a apuração não lê `consultor_afastamento`, mesmo que haja
   algumas linhas manuais. Misturar cobertura parcial e ausência total sem
   uma versão declarada seria menos auditável que a regra transitória.

Qualquer mudança nessas sete decisões exige nova confirmação do usuário e
atualização deste documento antes da implementação.

## Contrato técnico proposto

### Chave de identidade

`consultores.id` não é estável entre lojas: a restrição do cadastro é
`(nome, loja_id)` e transferências podem gerar outro UUID. A moeda temporal
já adotada por `consultor_vigencia` e `supervisor_vigencia` é o nome
normalizado.

Nesta versão:

```text
consultantId = nome_normalizado
consultant   = grafia de exibição mais recente da competência
```

O valor não deve ser tratado como chave corporativa definitiva. Antes de
materializar, a migration precisa produzir diagnóstico de:

- mais de uma grafia ativa para a mesma normalização;
- um mesmo nome normalizado atribuído simultaneamente a pessoas/lojas
  incompatíveis;
- contrato pago sem vínculo temporal correspondente;
- vínculo sem loja ou loja ausente.

Homônimo confirmado bloqueia a publicação até existir um identificador
mestre ou uma tabela de reconciliação. Não inventar UUID a partir do cadastro
atual.

### Coleção mensal

Cada linha de `consultantProductivity` contém:

```text
consultantId
consultant
storeId
store
manager                 # região histórica/auditável
competenceMonth
competenceYear
paidEffective           # somente população consultor
periodWorkingDays       # DU da competência
consideredWorkingDays   # DU cobertos pelo vínculo nesta loja
consideredDaysBasis     # ELIGIBLE_LINK_DAYS
absenceCoverage         # NONE
dailyProductivity       # paid / considered days; 0 se paid = days = 0
ruleRevision
```

O esqueleto nasce dos vínculos e não da produção; assim, consultor elegível
sem venda permanece com `paidEffective = 0`.

O numerador conserva a loja registrada no contrato para reconciliar com o
fechamento. O denominador conserva a loja da vigência. A união por
`consultantId + storeId` expõe, em vez de esconder, contrato pago que não
encontra vínculo; esse caso gera diagnóstico, bloqueia a publicação quando
resultar em pago positivo com zero dias e não é reatribuído a outra loja.

### Coleção semanal

`consultantWeeklyProductivity` usa os mesmos campos de identidade, loja,
base e revisão, acrescentando:

```text
weekStart               # segunda-feira ISO
weekEnd                 # domingo ISO
paidEffective
periodWorkingDays
consideredWorkingDays
dailyProductivity
```

A janela termina no último domingo anterior ou igual ao último dia da
competência fechada e contém, no máximo, oito semanas completas. A função
consulta pagamentos pela data real, inclusive quando a janela atravessa ano
ou competência; não deriva as semanas apenas do frame mensal.

### Materialização e privacidade

O payload individual é nominal e não deve herdar automaticamente o grant
público de `caderno_fechamento_snapshot`/`obter_caderno_publicado`.

Abordagem escolhida:

- criar snapshot individual privado, chaveado por `(ano, mes)`, com RLS
  habilitado e `EXECUTE/SELECT` somente para `service_role`;
- calcular mensal e semanal na mesma função e congelá-los na mesma operação
  lógica de publicação;
- expor uma RPC privada de leitura para Bereshit e dashboard;
- manter a RPC agregada pública sem nomes até que todos os consumidores sejam
  auditados;
- no handoff do Bereshit, compor no servidor o relatório agregado com as duas
  coleções privadas, preservando o contrato TypeScript já implementado.

Se a auditoria provar que nenhum consumidor usa `anon/authenticated`, uma
migration posterior pode restringir `obter_caderno_publicado` e voltar a uma
única RPC. Essa consolidação não faz parte deste incremento.

## Plano de subtarefas

| # | Subtarefa | Toca | Slug subagente | Depende de | Tier | Critério de pronto | Status |
|---|---|---|---|---|---|---|---|
| ST-00 | Congelar o baseline e reconciliar as mudanças locais de headcount | `git status`, 095, 096, Python modificado, docs de progress | `biz-rules` | — | perguntar primeiro | Proprietário confirma o que será preservado; 095/096 têm estado de aplicação conhecido; nenhuma alteração alheia foi sobrescrita | Bloqueada até aprovação do plano |
| ST-01 | Validar regra canônica e medir divergências | consultas somente leitura sobre vínculos, supervisão, lojas inativas, homônimos, feriados e produção sem vínculo | `biz-rules` | ST-00 | seguir padrão | Relatório de 2–3 competências registra contagens, divergências e tolerâncias; decisões deste plano permanecem viáveis | Pendente |
| ST-02 | Finalizar a população única antes da série individual | migration 096 e verificações SQL | `dba` | ST-01 | nunca aplicar sem instrução | `paidByConsultants / weightedHeadcount` fecha; datas de supervisor foram corrigidas; migration revisada, ainda não aplicada automaticamente | Pendente |
| ST-03 | Criar apuração diária e snapshots individuais privados | nova migration `NNN_produtividade_individual_v2.sql`, com próximo número livre | `dba` | ST-02 | nunca aplicar sem instrução | Função gera mensal/semanal da mesma CTE, diagnósticos passam, grants são service_role-only e SQL de verificação está documentado | Pendente |
| ST-04 | Integrar à materialização operacional | `fn_materializar_caderno` ou função companion na mesma migration | `data-layer` | ST-03 | perguntar primeiro | Uma publicação fechada grava agregado e individual de forma idempotente; falha individual não deixa versões desencontradas | Pendente |
| ST-05 | Implementar loaders com contrato e cache corretos | `src/dashboard/loaders.py`, testes do loader | `data-layer` | ST-04 | seguir padrão | Parser produz frames mensais/semanais tipados, cache dual funciona, erro vira estado explícito e RLS pode ser aplicado imediatamente | Pendente |
| ST-06 | Implementar KPIs puros da evolução gerencial | novo `src/dashboard/kpis/produtividade.py`, testes | `biz-rules` | ST-05 | seguir padrão | Razão das somas, lacunas, variação e benchmarks passam casos de zero, transferência e competência ausente | Pendente |
| ST-07 | Aplicar RLS e gate de permissão específicos | `app.py`, `permissions.py`, testes RLS/permissão | `data-layer` | ST-05 | seguir padrão | admin/gestor/gerente autorizados; gerente fail-closed e sem acesso cross-região; supervisor/consultor não veem a subvisão | Pendente |
| ST-08 | Construir subvisão Produtividade em Evolução | `tabs/evolucao.py`, `ui/charts.py`, testes de UI/smoke | `ui-dash` | ST-06, ST-07 | seguir padrão | Série e tabela por loja renderizam lazy, aviso de base é permanente, export fecha com cards e nenhuma decisão nominal é exibida | Pendente |
| ST-09 | Cobrir invariantes ponta a ponta | testes de KPI, loader, RLS, permissions, app smoke | `testing` | ST-03, ST-05, ST-06, ST-07, ST-08 | seguir padrão | testes afetados e suíte completa passam; cobertura inclui gerente multi-região, lacuna, transferência e mudança futura de base | Pendente |
| ST-10 | Documentar e entregar handoff ao Bereshit/Angry-man | `HEADCOUNT_ETL.md`, `business-rules.md`, novo progress | `biz-rules` | ST-09 | seguir padrão | contrato, semântica, privacidade e ordem operacional registrados; handoff indica RPC privada e payload | Pendente |
| ST-11 | Aplicar, conciliar e rematerializar piloto | Supabase + cartão `Operação → Eventuais → Rematerializar Caderno` no Angry-man | `dba` | ST-10 | nunca sem instrução | migrations aplicadas na ordem aprovada; 2–3 competências piloto conciliam; rematerialização retorna sucesso; snapshots e UI validados | Pendente |

## Caminho crítico

```text
ST-00 → ST-01 → ST-02 → ST-03 → ST-04 → ST-05
                                      ├→ ST-06 ─┐
                                      └→ ST-07 ─┼→ ST-08 → ST-09 → ST-10 → ST-11
```

ST-06 e ST-07 podem avançar em paralelo depois que o contrato do loader
estiver congelado. Nenhum subagente aplica migration, publica snapshot ou
rematerializa competência sem confirmação explícita.

## Ordem operacional de implantação

1. Confirmar/corrigir datas de `supervisor_vigencia`.
2. Revisar, versionar e aplicar 095/096 na ordem aprovada.
3. Aplicar a migration de produtividade individual privada.
4. Subir loaders/KPIs/RLS/UI do dashboard.
5. Validar uma competência fechada sem rematerializar o histórico inteiro.
6. Rematerializar 2–3 competências piloto pelo cartão do Angry-man:
   `Operação → Eventuais → Rematerializar Caderno`.
7. Comparar origem, snapshot, dashboard e Bereshit.
8. Só depois rematerializar as demais competências aprovadas.

A lógica de publicação e as migrations pertencem ao `Numeros_venda`; a
execução operacional da rematerialização pertence ao Angry-man. O Bereshit
permanece somente leitura.

## Matriz mínima de testes

| Caso | Resultado esperado |
|---|---|
| Consultor elegível sem pagamento | Linha com dias > 0, pago 0 e produtividade 0 |
| Pagamento sem vínculo correspondente | Diagnóstico explícito e publicação bloqueada; sem reatribuição silenciosa |
| Transferência no meio do mês | Dois segmentos; soma dos dias sem sobreposição |
| Supervisor na âncora da competência | Fora do numerador e do denominador individual |
| VAI E VEM | Fora das coleções e benchmarks |
| Loja sem produção | Permanece no denominador do escopo gerencial |
| Vínculo parcial | Dias limitados à janela, sem piso artificial no campo de dias |
| Afastamento existente no ledger | Não altera esta revisão; cobertura continua NONE |
| Competência sem snapshot | Lacuna, não zero |
| Semana atravessando ano/mês | Segunda-domingo, pagamento e dias sem duplicação |
| Gerente sem escopo | Frame vazio |
| Dois gerentes com mesmo role | Cada um vê apenas suas regiões atuais |
| Loja transferida de região | Histórico aparece na carteira atual; manager histórico fica auditável |
| Base futura diferente | Série interrompe comparação na fronteira |

## Comandos de validação para a fase IMPLEMENT

Depois de cada Python editado:

```bash
.venv/bin/ruff check <arquivo>
```

Ao final:

```bash
.venv/bin/python -m pytest \
  tests/test_kpis_produtividade.py \
  tests/test_loaders_produtividade.py \
  tests/test_tabs_evolucao_produtividade.py \
  tests/test_permissions.py \
  tests/test_rls.py \
  tests/test_app_smoke.py

.venv/bin/python -m pytest tests/
.venv/bin/ruff check .
```

As verificações SQL ficam dentro da migration e devem ser executadas em modo
somente leitura antes e depois da aplicação, registrando resultados no novo
documento de progress.

## Fora de escopo desta entrega

- desconto de férias, faltas ou afastamentos;
- presença real por ponto;
- oportunidades, propostas, conversão ou funil;
- qualidade, cancelamento e efetivação individual;
- score, quadrantes, alertas e recomendações de RH;
- comparação causal antes/depois de transferência;
- reconstrução retroativa automática de snapshots;
- identificador corporativo definitivo para pessoas;
- ranking nominal no dashboard.

## Gate para iniciar IMPLEMENT

Este documento conclui a Fase 2 do RPI. Antes de qualquer edição de código, o
usuário deve aprovar explicitamente:

1. as sete decisões de produto;
2. a materialização individual privada, sem grant público;
3. a ordem ST-00 → ST-11;
4. a execução de migrations e rematerializações como atos separados e
   confirmados.

Após a aprovação, o agente no `Numeros_venda` deve começar por ST-00, nunca
diretamente pela UI.
