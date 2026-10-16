# 2026-10-16 — Reconquista: Carteira Elegível substitui o export (≥ 10/2026)

**Agente:** Claude Code
**Tipo:** feature
**Arquivos tocados:** `database/migrations/140_reconquista_elegivel.sql`, `src/dashboard/kpis/reconquista.py`, `src/dashboard/loaders.py`, `src/dashboard/tabs/analiticos.py`, `src/dashboard/ui/kpi_cards_reforma.py`, `tests/test_kpis_reconquista_carteira.py`, `tests/test_loader_reconquista_carteira.py`, `tests/test_tabs_analiticos_reconquista_carteira.py`, `docs/agents/business-rules.md`, `docs/agents/data-layer.md`; angry-man: `src/services/import-reconquista-elegivel.ts`, `src/services/import-registry.ts`, `src/lib/supabase.ts`, `supabase/functions/reconquista-rpc/index.ts`, `tests/unit/import-reconquista-elegivel.test.ts`, `docs/importacao.md`
**Commit(s):** — (não commitado)

## Objetivo

O usuário vai importar o `Extrator_elegiveis.xlsx` (foto mensal da
carteira elegível) como analítico da Reconquista, e o export antigo
(`reconquista_YYYYMM.xlsx`) deixa de ser importado. Pediu também para
apontar quais sub-abas deixam de servir.

## O que foi feito

- Migration 140 (não aplicada): `reconquista_elegivel`, a view com
  `consultor_identificado` e a RPC por período. As validações bloqueiam
  antes do DELETE (anomes ≠ período, ADE duplicada, flags desconhecidas,
  chave fora da lista). Deny + REVOKE na tabela e na view.
- `carregar_carteira_elegivel` é um loader próprio, chamado só pela
  sub-aba. Os badges Prometido/Efetivado cruzam com a Promessa Diária e a
  liga globais.
- Sub-aba "Carteira Elegível" (≥ 10/2026) no lugar de Por Loja e
  Detalhamento. "Clientes na esteira" sai do card a partir de 10/2026.
- angry-man: card `reconquista_elegivel`, whitelist da Edge Function e
  mapa do cliente.
- Testes: 59 no Numeros_venda e 23 no angry-man.
  - 14 sabotagens no Python (13 regras + 1 controle) e 5 no TS; todas
    pegas, código restaurado.
  - Importador rodado contra o arquivo real: 2926 linhas / 311 de baixa
    prioridade / saldo igual ao Total do BI.

## Decisões não óbvias

- **Carteira em nome de supervisor vai para "· a distribuir"**, não é
  excluída (escolha do usuário). Isso diverge de propósito da Promessa
  Diária: lá a promessa é fato consumado; aqui é lead a trabalhar, e
  excluir esconderia 152 leads (5%). O sufixo é diferente de "· sem
  consultor identificado" porque a linha cobre os dois casos.
- **Corte por data (`carteira_elegivel_vigente`) decide a sub-nav, não o
  status do import.** Assim 10/2026 sem arquivo mostra "não importada" em
  vez de ressuscitar as sub-abas do export congelado.
- **Loader fora de `carregar_reconquista`**: o card roda em todo rerun; a
  carteira tem cerca de 3 mil linhas e só a sub-aba precisa dela.
- **"Prometido" vale para qualquer linha da Promessa Diária** (elegível
  ou não): é ação feita sobre o cliente, não a conta do card.
- **Linha sem ADE fora do rodapé recusa o arquivo** (não só a linha). O
  usuário aprovou "recusar"; a lista de trabalho incompleta passaria
  despercebida.
- **Link só `https://`** vira link clicável (defesa contra `javascript:`).
- **Nada foi apagado.** O export, `carregar_reconquista` (parte export) e
  os renders de Por Loja/Detalhamento seguem, porque os meses ≤ 09/2026
  usam. O card "Reconquista MG CRED" do angry-man fica sem uso; a remoção
  é decisão do usuário.

## Pendências / follow-ups

- [x] Usuário aplicou a 140 (SQL Editor). Conferido: tabela/view/RPC,
      RLS ligada, 0 grants residuais, só service_role executa. Smoke test
      das recusas (anomes errado, flag de atuação, `nu_matricula`): OK.
- [x] Redeploy da Edge Function `reconquista-rpc` → **v13**
      (`verify_jwt=false` mantido; a v12 conferida antes = repo).
- [x] Build angry-man **1.4.8** (Setup .exe + zip em `release/win-x64/`).
      `app.asar`: card e RPC presentes; só a chave `anon`, sem
      service_role.
- [x] Runbook operacional em `angry-man/docs/importacao.md` § Reconquista
      — rotina mensal (3 cards, passo a passo, log esperado, recusas,
      conferência SQL); ponteiros em `RECONQUISTA_MIGRATION.md`,
      `deploy.md` e `business-rules.md`.
- [ ] **Bug no 1º import** (`column reference "baixa_prioridade" is
      ambiguous`, 42702): a coluna de saída `baixa_prioridade` do RETURNS
      TABLE colide com a coluna da tabela no `RETURNING` sem qualificar.
      Nada foi gravado. Fix na **migration 141** (alias `t` + RETURNING
      qualificado) — usuário aplica.
      *Lição:* o smoke test da 140 só cobriu recusas, que abortam antes do
      INSERT. Smoke test de RPC tem que incluir o **caminho de sucesso**
      (em transação revertida), e coluna de RETURNS TABLE não deve
      repetir nome de coluna da tabela tocada.
- [x] Saldo da carteira omitido no dashboard (card, colunas do detalhe e
      das quebras, CSVs) a pedido do usuário; segue só como critério de
      ordem. Teste + 3 sabotagens.
- [ ] Usuário importa 10/2026 e confere: 2926 / 311 / sem_consultor 137.
- [ ] Cadastro: TAMIRES (nome curto), HELOINA, CLAUDIA CRISTINA
      (VIEIRA RODRIGUES × CORREA VIEIRA) e as lojas sem supervisor
      (MADUREIRA, LARGO DA SEGUNDA FEIRA, DIGITAL). O usuário vai corrigir.
- [ ] Decidir se o card "Reconquista MG CRED" sai do angry-man.

## Referências

- [business-rules.md § Carteira Elegível](../business-rules.md#carteira-elegível--lista-de-trabalho-a-partir-de-102026)
- [2026-10-16d](2026-10-16d-promessa-lead-sem-consultor-supervisor.md) (regra do supervisor vigente)
