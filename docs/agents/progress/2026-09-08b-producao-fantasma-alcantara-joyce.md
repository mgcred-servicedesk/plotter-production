# 2026-09-08 — Produção fantasma em HELP ALCANTARA (Joyce) e revisão das migrations 109–112

**Agente:** Claude Code
**Tipo:** bugfix / research
**Arquivos tocados:** `database/migrations/109_vigencia_transferencia_joyce_largo_segunda_feira.sql`
**Commit(s):** (não commitado)

## Objetivo

Verificar se as migrations 109–112 tinham sido aplicadas, revisá-las para
aplicação, e eliminar o efeito fantasma em que JOYCE ANNY DA SILVA FOCHT
DE JESUS aparecia no dashboard ligada a HELP ALCANTARA.

## O que foi feito

- Constatado que **nenhuma** das quatro (109–112) foi aplicada. O projeto
  não tem tabela de registro de migrations: a verificação é por efeito no
  dado.
- **111 e 112**: todas as guardas passam contra o banco de hoje. Aplicam
  limpo, sem alteração.
- **110**: guardas passam, mas ver a pendência abaixo (dessincronização de
  `supervisores`).
- **109 reescrita** para tratar a produção fantasma: nova etapa 5
  (reatribuição dos contratos do cadastro órfão), etapa de remoção
  renumerada para 6, `LOCK TABLE public.contratos` adicionado, três
  pós-condições novas e números do cabeçalho remedidos.
- Dry-run das guardas da 109 v2 contra o banco: todas passam; moveria 1
  contrato para LARGO e 0 para CASCADURA.

## Decisões não óbvias

- **A produção fantasma tem raiz no CONTRATO, não no cadastro.** O
  contrato 3000625 (04/09, R$ 346,26, PAGO AO CLIENTE) chegou em 08/09 às
  14:32 com `loja_id = HELP ALCANTARA`. O cadastro órfão
  `(JOYCE, HELP ALCANTARA)` foi a causa da escolha da loja pelo ETL, mas
  em 08/09 ele já era só o ponto de ancoragem — apagá-lo sozinho não
  removeria a linha do dashboard.

- **A ordem "reatribuir, depois remover" é obrigatória.**
  `contratos.consultor_id` é `ON DELETE SET NULL`. Remover o cadastro com
  contrato pendurado não apagaria o contrato: deixaria `consultor_id`
  NULL, trocando produção na loja errada por produção sem consultor
  nenhum. A guarda original da 109 (exigir zero contratos) é o que
  impedia esse desfecho — foi mantida, agora como pós-verificação da
  etapa 5.

- **A reatribuição usa a fronteira do ledger, não uma lista de
  contratos.** Contratos do órfão com `data_cadastro >= 2026-09-01` vão
  para LARGO; anteriores vão para CASCADURA. Hoje só existe um (04/09),
  mas a origem já provou que grava mais sob a filial errada, e a regra
  precisa valer para o que chegar até a aplicação. Hardcodar 3000625
  deixaria a migration errada no dia seguinte.

- **`loja_id` e `consultor_id` mudam juntos.** `v_contratos_dashboard`
  (migration 065) deriva `loja` de `contratos.loja_id` e `consultor` de
  `consultores.nome` via `consultor_id`. Mover só a loja deixaria o
  contrato preso ao órfão e bloquearia a remoção.

- **Duas telas mostravam duas lojas erradas, pela mesma raiz.** Nas telas
  que usam a loja do contrato, ela aparecia dentro de ALCANTARA com
  R$ 346,26. Na aba de gestão, `_esqueleto_vinculos` identifica a pessoa
  pela loja de maior permanência **no ledger** e `_producao_por_consultor`
  soma a produção por **nome** — então os R$ 10.631,16 inteiros apareciam
  creditados a CASCADURA. Nenhuma das duas mostrava LARGO, que é a loja
  certa.

- **Direção da transferência confirmada pelo usuário:** CASCADURA até
  31/08/2026, LARGO DA SEGUNDA FEIRA a partir de 01/09/2026. A produção
  sustenta: 163 contratos em CASCADURA (04/05 a 31/08), 6 em LARGO (02/09
  a 04/09), nenhum fora dessas faixas.

- **`origem = 'MANUAL'` continua sendo a blindagem do ledger de
  consultor.** `fn_headcount_replace` (095) classifica linha MANUAL como
  `divergencia_manual` e reporta em vez de aplicar; o rebuild do backfill
  apaga só `origem LIKE 'BACKFILL%'`. Verificado no código, não assumido.

## Pendências / follow-ups

- [ ] **110 dessincroniza `supervisores` do ledger.** Hoje as duas fontes
      estão idênticas (47 = 47, zero divergência). A 110 escreve só em
      `supervisor_vigencia`. `fn_supervisores_replace` (082) reconcilia o
      ledger a partir da planilha: na próxima carga com a planilha antiga,
      BARBARA entra em `_sup_novos` (reabre janela) e HUGO em
      `_sup_saidas` (fecha por sucessão) — **a promoção é revertida**.
      `supervisor_vigencia` não tem coluna `origem`, então a proteção
      MANUAL não existe deste lado. Alternativa canônica:
      `fn_aplicar_mudanca_supervisor(..., 'FIM')` +
      `(..., 'INICIO')`, que mantém foto e ledger atômicos.
- [ ] **O ETL de contratos continua criando pessoa nova por (nome, loja).**
      Terceira ocorrência registrada (Joyce, Hugo, Mizael). Ver
      [2026-09-08-cadastro-por-nome-loja-cria-pessoa-nova.md](2026-09-08-cadastro-por-nome-loja-cria-pessoa-nova.md).
      Enquanto a origem não for corrigida, cada carga pode produzir um novo
      caso destes.
- [ ] Pós-condição da 111 exige exatamente 4 segmentos no ledger do
      Mizael. Passa hoje (são 3), mas é acoplamento a número absoluto.
- [ ] 109 e 110 contam janelas na loja de destino sem filtrar
      `vigencia_fim IS NULL`; 111 e 112 filtram. Fail-closed nas quatro,
      mas vale unificar.

## Referências

- Docs consultados: [data-layer.md](../data-layer.md),
  [business-rules.md](../business-rules.md)
- Migrations lidas: 065 (view), 076/082 (ledger de supervisor), 086/087
  (ledger de consultor), 095 (headcount), 101 (produtividade individual),
  105 (diagnóstico de origem)
