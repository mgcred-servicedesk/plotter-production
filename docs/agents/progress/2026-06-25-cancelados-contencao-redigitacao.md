# 2026-06-25 — Contenção de cancelados redigitados + assertividade

**Agente:** Claude Code
**Tipo:** feature
**Arquivos tocados:** `database/migrations/032_cancelados_classificados.sql`,
`src/dashboard/loaders.py`, `src/dashboard/kpis/gerais.py`,
`src/dashboard/kpis/pontuacao.py`, `src/dashboard/ui/kpi_cards.py`,
`src/dashboard/tabs/analiticos.py`, `tests/test_kpis_gerais.py`,
`tests/test_kpis_pontuacao.py`, `docs/agents/business-rules.md`
**Commit(s):** (pendente)

## Objetivo

O KPI de cancelados inflava com redigitações (mesma proposta digitada várias
vezes) e com canceladas redigitadas e pagas depois. Criar contenção: contar só
a última cancelada do cliente por produto em 7 dias, removendo redigitadas e
recuperadas; medir assertividade dos consultores.

## O que foi feito

- Nova RPC `obter_cancelados_classificados` (migration 032) classifica cada
  cancelado em `redigitada` / `recuperada` / `liquido` via matching por nome +
  `categoria_codigo` em janela de 7 dias. Retorna as colunas da RPC antiga +
  `classificacao`.
- Loader `_fetch_contratos_cancelados` passou a usar a nova RPC e mapeia
  `CLASSIFICACAO`.
- `calcular_kpis_cancelados` conta só `liquido` (valor/qtd/churn) e devolve
  `qtd_bruto`/`qtd_redigitadas`/`qtd_recuperadas`; helper compartilhado
  `separar_cancelados_liquidos`. `calcular_pontos_cancelados` espelha a regra.
- Nova `calcular_assertividade_consultores` (função pura) + render na sub-aba
  "Cancelados" (analíticos): card org-level + tabela por consultor; coluna
  `Classificacao` e resumo bruto×líquido no detalhamento. Card "Cancelados"
  da home ganhou nota de redigitadas/recuperadas "fora da conta".
- Testes novos em `test_kpis_gerais.py` e `test_kpis_pontuacao.py`.
- **Hardening RLS (fail-closed):** `aplicar_rls` / `aplicar_rls_metas` /
  `aplicar_rls_supervisores` passam a retornar DataFrame **vazio** quando um
  perfil não-admin/gestor está sem escopo (ou coluna ausente / perfil
  desconhecido), em vez da base completa. Auditoria confirmou que a feature
  cross-consultor não vaza dados de outros perfis (matching global no SQL,
  filtro client-side via `aplicar_rls`). Cobertura em `test_rls_cancelados.py`.
- **Resumo executivo:** novo pill "🔁 N contratos redigitados (fora dos
  cancelados) · M recuperadas" em Ações Prioritárias quando há redigitação.
- Total da suíte: 128 testes passam.

## Decisões não óbvias

- **Modelo de acesso (corrigido):** o dashboard lê em **escopo completo**
  (cliente Supabase único, sem GUC por usuário) e filtra por perfil
  **client-side** via `aplicar_rls(df)`. Logo a classificação SQL é **global**
  (cross-consultor detectado) e **não** precisa de `SECURITY DEFINER` — a RPC
  `SECURITY INVOKER` basta. (Caveat anterior, de que consultor só via os
  próprios, estava incorreto.)
- **Oportunidades perdidas:** coluna `recuperada_outro` na mesma RPC marca
  cancelados cuja venda foi capturada por outro consultor. Seção "Oportunidades
  perdidas" (qtd + valor, anônima) só no escopo consultor; não altera líquidos.
- **Matching no SQL, não no Python** — o nome do cliente (PII; CPF não é
  armazenado por segurança) **nunca sai do banco**; só a `classificacao`/flag.
- **`obter_contratos_cancelados` (RPC antiga) ficou intocada** e agora está
  **sem uso** — sinalizada para o usuário decidir remover (não removida
  unilateralmente).
- **Fórmula de assertividade** (`1 − redigitadas/total_propostas`) **confirmada
  pelo usuário** — retorna o percentual de assertividade. Denominador é
  aproximado por janelas de carga distintas (pagos por período de pagamento ×
  cancelados por `data_cadastro`).
- Anchor da janela = `data_cadastro` (digitação), conforme alinhado.
- `obter_contratos_cancelados` (RPC antiga) **mantida por ora e documentada
  para remoção futura** em [data-layer.md](../data-layer.md).

## Pendências / follow-ups

- [ ] Aplicar migration 032 no Supabase e validar por SQL manual
      (`SELECT classificacao, count(*) FROM obter_cancelados_classificados(...)`).
- [ ] Remover `obter_contratos_cancelados` em migration futura (`DROP FUNCTION`)
      quando confirmado que nada mais a consome.
- [ ] Avaliar índice funcional sobre o nome normalizado se a RPC ficar lenta.
- [ ] **Escopo consultor:** apontar oportunidades capturadas por outro consultor
      (perda de venda) — requer RPC `SECURITY DEFINER` restrita ao próprio
      consultor (RLS normal bloqueia ver a venda do outro). Em definição.

## Referências

- Docs consultados: [business-rules.md](../business-rules.md),
  [data-layer.md](../data-layer.md), [rls.md](../rls.md)
- Migration base: `003_view_contratos_cancelados.sql`
