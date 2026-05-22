# 2026-05-21 — Pagamentos Online (extrator DNA)

**Agente:** Claude Code (Opus 4.7)
**Tipo:** feature
**Arquivos tocados:**
- `database/migrations/014_pagamentos_online.sql` (novo)
- `database/INTEGRACAO_PAGAMENTOS_ONLINE.md` (novo)
- `src/dashboard/loaders.py` (apend: loader `carregar_pagamentos_online`)
- `src/dashboard/tabs/pagamentos_online.py` (novo)
- `src/dashboard/permissions.py` (entrada `tab_pagamentos_online`)
- `app.py` (import + abas_disponiveis + dispatch)

**Commit(s):** (a fazer)

## Objetivo

Habilitar uma "estimativa do dia" de pagamentos a partir do extrator
DNA (`relatorio-completo-acompanhamento-propostas.csv`), importado
horariamente pelo angry-man. Visão exclusiva para admin/gestor,
serve enquanto o consolidado oficial não entra em `contratos` (D+1).

## O que foi feito

- Migration `014` cria:
  - `lojas.codigo_dna TEXT UNIQUE` — chave de ligação 1:1 com a
    coluna `Loja` do extrator (mesmo valor de `CÓDIGO` no
    `Codigo Lojas Help.xlsx`). Coluna aditiva, não toca consumo
    existente.
  - Tabela `pagamentos_online` com 14 colunas funcionais + PK
    `proposta` + `imported_at`. Apenas leitura RLS para
    `admin`/`gestor` (demais perfis fail-closed por ausência
    de policy).
  - View `v_pagamentos_online_efetivo` (security_invoker=on)
    aplicando: triplo filtro de "pago online", dedup vs
    `contratos.status_pagamento_cliente='PAGO AO CLIENTE'`, e
    cálculo de `valor_producao`.
- `INTEGRACAO_PAGAMENTOS_ONLINE.md` documenta para o angry-man
  o contrato CSV→DB, estratégia de TRUNCATE+INSERT, mapeamento
  de colunas e ciclo de vida.
- Loader `carregar_pagamentos_online()` em `loaders.py` consome
  a view, normaliza colunas para o padrão do dashboard (UPPER),
  e cacheia com TTL 5min.
- Aba "Pagamentos Online" com KPIs (valor da produção, qtd,
  ticket médio, consultores/lojas), filtros (loja, grupo
  produto, consultor), breakdowns por grupo e por loja, e
  tabela detalhada. Header mostra "atualizado há X" a partir
  do `imported_at`.
- Permissão `tab_pagamentos_online`: admin=True, gestor=True,
  demais=False.

## Decisões não óbvias

- **Coluna em `lojas` em vez de tabela bridge separada.**
  Os códigos batem 1:1 com o cadastro existente — bridge seria
  cerimônia sem ganho. Antecipa futuro acesso à API DNA online
  (terá o mesmo identificador). Risco mitigado: coluna é
  estritamente aditiva, `UNIQUE` permite `NULL` em lojas sem
  contraparte DNA.

- **Status/Situação/Agrupamento ficam na tabela, não só na
  ingestão.** O usuário pediu "aplique o filtro" mas também
  "inclua essas colunas". Mantê-las na tabela permite evoluir
  a regra de "pago online" sem mexer no angry-man, e abre
  espaço para futuras visões (pendentes/em análise) com
  o mesmo backing store.

- **Regra de "pago" + dedup vivem na view, não no Python.**
  Evita lógica espalhada entre Python e SQL. Trocar
  `'PAGO AO CLIENTE'` ou ajustar o triplo filtro é uma
  migração SQL focada.

- **DELETE+INSERT atômico por upload (em vez de upsert por
  `proposta`).** Propostas que **saem** do extrator
  (cancelamentos retroativos) precisam sumir; upsert as
  deixaria presas. O CSV é cumulativo, então substituir
  tudo não perde dado da fonte. Usamos `DELETE` em vez de
  `TRUNCATE` porque o lock é por linha (não bloqueia
  leitores do dashboard) — a diferença de performance é
  desprezível para o volume da tabela (~500-700 linhas).
  Tudo dentro de `BEGIN; DELETE; INSERT; COMMIT;` para
  garantir all-or-nothing.

- **Limpeza de fim de dia separada do consolidado.** Na
  versão anterior eu vinculei o TRUNCATE de fim-de-ciclo
  ao momento em que o consolidado D+1 entra em `contratos`,
  mas isso introduz race condition se a ordem inverter
  (consolidado atrasa, primeiro upload de D+1 entra antes,
  e aí o "TRUNCATE pós-consolidado" wipea o que acabou de
  ser inserido). Decisão revisada: a limpeza vira uma
  operação **diária** (manual ou cron 23:59), independente
  do consolidado. Garante que o dashboard de manhã não
  mostre os pagamentos de ontem com aparência de hoje.

- **Fase inicial 100% manual.** Operador sobe os CSVs no
  angry-man várias vezes ao dia e clica em "Limpar" ao fim
  do expediente. Automação (cron horário + cron diário)
  vira fase 2 depois que o fluxo manual estiver estável.

- **Pré-validação de linhas mínimas no angry-man.** Sem
  isso, um CSV corrompido/vazio dispararia DELETE+INSERT
  com 0 linhas — wipe silencioso. Threshold inicial: 50
  linhas (ajustar conforme baseline observado).

- **Advisory lock no upload** (`pg_advisory_xact_lock`).
  Dois operadores clicando "Upload" simultaneamente não
  causam corrida — o segundo espera o primeiro.

- **TTL do loader: 5min.** Ciclo de ingestão é horário; 5min
  garante que o dashboard reflita a importação mais recente
  rapidamente sem hammering no Supabase.

- **RLS na tabela apesar de gating estar na UI.** A UI já
  esconde a aba para perfis sem permissão, mas a tabela
  precisa de RLS para fechar a porta caso alguém consulte
  via Supabase REST diretamente. Padrão idêntico ao usado
  em `contratos`.

## Premissas a validar

- **Valor exato `'PAGO AO CLIENTE'`** em `contratos.status_pagamento_cliente`
  — confirmado em [schema.sql:390](../../../database/schema.sql) e
  [:705](../../../database/schema.sql). Se o angry-man algum dia
  mudar a string, a dedup quebra silenciosamente. Sugestão de
  follow-up: extrair pra `enum` ou constante.
- **Match `lojas.nome` ↔ `Codigo Lojas Help.xlsx.LOJA`** depende
  do operacional. Doc orienta o angry-man a **logar** matches
  faltantes em vez de criar lojas novas.

## Pendências / follow-ups

- [ ] Aplicar a migration `014` no Supabase (SQL Editor).
- [ ] No angry-man, **fase manual (inicial)**:
      - [ ] Botão "Upload Pagamentos Online": parse CSV +
            filtro Grupo Produto + pré-validação de linhas
            mínimas + DELETE+INSERT atômico com advisory lock.
      - [ ] Botão "Limpar Pagamentos Online": DELETE simples.
      - [ ] Fluxo separado para UPSERT de `lojas.codigo_dna`
            a partir do Excel.
- [ ] No angry-man, **fase automação (futura)**:
      - [ ] Cron horário para upload automático.
      - [ ] Cron diário 23:59 para limpeza.
      - [ ] Alerta de queda anormal de count entre uploads.
- [ ] Smoke test em produção com o primeiro upload real.
- [ ] Considerar adicionar coluna `data_status` nos filtros da
      aba (hoje sempre traz tudo que está na view; quando o
      truncate funcionar bem, vai estar sempre limitado ao dia).

## Patterns criados ou atualizados

(nenhum padrão novo do tipo `patterns/` — feature segue padrões
existentes: loader + cache, aba via `permissions.py`, view com
`security_invoker`.)

## Referências

- Especificação do CSV: `uploads/relatorio-completo-acompanhamento-propostas.csv`
- Mapeamento de lojas: `uploads/Codigo Lojas Help.xlsx`
- Doc do contrato: [`database/INTEGRACAO_PAGAMENTOS_ONLINE.md`](../../../database/INTEGRACAO_PAGAMENTOS_ONLINE.md)
- Docs consultados:
  [data-layer.md](../data-layer.md),
  [rls.md](../rls.md),
  [ui-components.md](../ui-components.md)
