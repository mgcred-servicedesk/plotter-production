# 2026-06-26 — "Último Dia Apurado" passa a ser DIGITAÇÃO (e bate com o total do dia)

**Agente:** Claude Code (inline; migração + data layer + UI)
**Tipo:** fix/feature
**Arquivos tocados:** `database/migrations/037_fn_digitacao_diaria_detalhe.sql`
(novo), `src/dashboard/loaders.py`, `src/dashboard/pages/detalhes_cards.py`,
`app.py`
**Commit(s):** (ainda não commitado)

## Problema

O quadro "Último Dia Apurado" (página Em Análise) pivotava os contratos
**em análise** do último dia — então NÃO batia com a digitação. O usuário
quer que esse quadro seja sobre **digitação** (todos os status digitados) e
**bata** com o nº de digitados do dia exibido nos "Últimos 7 Dias".

## Causa

`obter_digitacao_diaria` ([035](../../database/migrations/035_fn_digitacao_diaria.sql))
lê `public.contratos` direto (todos os status), mas só devolve **agregado por
dia** — sem quebra por região/produto. Não dava para montar o pivot batendo
com o total.

## Solução (decisões do usuário)

- **Célula do pivot = Valor digitado (R$)** (consistente com os outros pivots;
  o Total bate com `valor_digitado` do dia).
- **Migração 037** (RPC novo) — o usuário aplica no Supabase.

### Migração 037 — `obter_digitacao_diaria_detalhe`
Mesma base/janela/segurança do 035 (contratos direto, todos os status, janela
mês-calendário, valor bruto, SECURITY INVOKER → herda `pol_contratos_select`),
só que agrupando por `(data_cadastro, regiao, grupo_dashboard)`. Dimensões via
os mesmos LEFT JOINs de `v_contratos_dashboard` (lojas→regioes,
produtos→categorias_produto). LEFT JOIN garante que **a soma do detalhe ==
agregado** (contratos sem loja/produto caem em NULL → "OUTROS" na UI).

### Loader
`carregar_digitacao_diaria_detalhe(mes, ano)` (TTL 15min corrente / 6h
histórico) mapeia a saída para o **mesmo formato** que o pivot já consome:
`DATA_CADASTRO, REGIAO, grupo_dashboard, VALOR (bruto), qtd_digitada`. **Sem
`conta_valor`** (digitação é volume bruto — o pivot não zera nada).

### UI
`render_detalhe_em_analise` ganhou o parâmetro `df_digitacao_detalhe`. O quadro
agora faz `filtrar_ultimo_dia(df_digitacao_detalhe)` +
`detalhe_analise_pivot(..., "REGIAO", "grupo_dashboard")` (reuso total das
funções puras). Renomeado para "Digitação do Último Dia — dd/mm/aaaa".

## Decisões não óbvias

- **Reuso sem código novo de pivot:** o loader entrega `VALOR`/`REGIAO`/
  `grupo_dashboard`/`DATA_CADASTRO`, então `filtrar_ultimo_dia` e
  `detalhe_analise_pivot` (já testados) servem sem alteração. A ausência de
  `conta_valor` no df faz `_aplicar_conta_valor` devolver tudo bruto.
- **Último dia vem da digitação, não da análise:** o filtro usa o df de
  digitação detalhada (mesma base do agregado dos 7 dias), então o dia do
  pivot == dia mais recente da série.
- **Os demais quadros seguem sobre EM ANÁLISE** — só o "Último Dia" virou
  digitação (escopo exato do pedido).

## ⚠️ Pendência obrigatória

- [ ] **Aplicar a migração 037 no Supabase SQL Editor.** Até lá, o loader
  chama um RPC inexistente e o quadro quebra. (Migração imutável: 037 é nova,
  não edita o 035.)
- [ ] Conferir no app que o Total do pivot == "Digitados" do dia nos 7 dias.

## Validação local

- Smoke-test: pivot do último dia soma exatamente o total digitado do dia.
- Suíte: 184 passes; ruff limpo (sem testes de RPC — exige Supabase).
