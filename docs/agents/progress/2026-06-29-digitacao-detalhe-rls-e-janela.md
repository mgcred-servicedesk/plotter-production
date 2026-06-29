# 2026-06-29 — Digitação detalhe: fix de escopo RLS na série 7 dias + janela recente

**Tipo:** perf + correção (RLS)
**Arquivos:** `database/migrations/042_fn_digitacao_diaria_detalhe_janela.sql` (NOVA),
`src/dashboard/loaders.py`, `src/dashboard/pages/detalhes_cards.py`, `app.py`,
`tests/test_permissions.py`

## Origem

Pedido era "análise de performance pós-migration 041 + reduzir o over-fetch do
detalhe de digitação". A investigação revelou o **modelo de auth real** e, a
partir dele, um problema de RLS mais sério que a performance.

## Achado central — modelo de auth

A app usa **uma única chave Supabase compartilhada** (singleton, sem JWT por
usuário — confirmado: nenhum `set_session`/`sign_in`/`postgrest.auth` no código).
Logo **toda RPC devolve dado GLOBAL** e o recorte por perfil é **100% client-side**
via `aplicar_rls`. Docstrings de loaders que afirmam "a RLS server-side já
restringe ao escopo" estão **incorretas para o runtime**.

Consequências:
1. A ideia original (param `p_somente_ultimo_dia` calculando `max(data_cadastro)`
   server-side) seria **incorreta** para perfis escopados — o servidor não conhece
   o escopo do usuário; calcularia o último dia GLOBAL, e `aplicar_rls` depois
   poderia esvaziar a tabela. **Descartada.**
2. **Vazamento de escopo vivo:** a série "Últimos 7 Dias" usava o agregado GLOBAL
   `carregar_digitacao_diaria` (sem `aplicar_rls`), então gerente/supervisor/
   consultor (todos com `cards_gerenciais=True`) viam digitação diária de fora do
   escopo. `_agregar_digitacao_diaria` era um fix **construído mas nunca ligado**
   para exatamente isso (tinha testes, zero callers de produção).

## O que foi feito (R1 + R2, aprovado pelo usuário)

- **R1 (RLS):** a série "Últimos 7 Dias" passa a derivar de
  `_agregar_digitacao_diaria(df_digitacao_detalhe)` — o detalhe JÁ recortado por
  `aplicar_rls` em `app.py`. Mesmo escopo do pivot "Último Dia" ao lado. Removido
  o param `df_digitacao` de `render_detalhe_em_analise` e o uso de
  `carregar_digitacao_diaria` (import órfão removido de `app.py`).
- **R2 (perf):** migration 042 adiciona `p_dias_recentes INTEGER DEFAULT NULL`
  à RPC `obter_digitacao_diaria_detalhe`. `NULL` = mês inteiro (retrocompatível);
  `N` = janela dos últimos N dias de calendário (clamp no 1º dia do mês). O loader
  passa a default `_DIGITACAO_DETALHE_DIAS_RECENTES = 14` (entra na chave de cache).
  Como agora os DOIS quadros vêm do detalhe escopado, a janela recente basta —
  corta o payload (~14/30) e neutraliza o crescimento ~2× da 041.

## Decisões / ressalvas

- **Janela = 14 dias** cobre com folga os 7 dias-com-dado exibidos + 1 dia-base da
  Var. % incluindo fins de semana. Tunável (constante no loader). Ressalva: escopo
  dormente há >14 dias mostraria Último Dia / 7 Dias vazios — consistente entre si.
- **`p_dias_recentes` omitido do payload quando `None`** para usar o DEFAULT NULL
  da função (não enviar `null` explícito).
- **Não removido unilateralmente** (sinalizado p/ confirmação): `carregar_digitacao_diaria`
  + wrappers `_digitacao_diaria_atual/historico` + `_fetch_digitacao_diaria` ficaram
  **sem caller de produção** após R1. Candidatos a remoção em follow-up.
- Migration 042 **pendente de aplicação manual no Supabase** (DROP+CREATE; a
  assinatura ganhou um argumento). Até aplicar: o loader chama com `p_dias_recentes`
  → erro se a função antiga (2 args) ainda estiver no banco. **Aplicar antes de
  abrir o drill-down Em Análise.**

## Validação

- `ruff check` nos arquivos tocados: OK.
- `pytest tests/`: 211 passed + novo `test_serie_reflete_apenas_o_escopo_recebido`
  (regressão do vazamento) → 212.

## Follow-ups

- [ ] Aplicar migration 042 no Supabase.
- [ ] Confirmar remoção de `carregar_digitacao_diaria` e wrappers órfãos.
- [ ] Corrigir docstrings de loaders que afirmam "RLS server-side restringe" (o
      recorte é client-side neste runtime) — varrer `loaders.py`.
- [ ] (Aberto da sessão anterior) validar índices 040 via EXPLAIN como não-admin;
      paralelizar reads independentes da primeira carga.
