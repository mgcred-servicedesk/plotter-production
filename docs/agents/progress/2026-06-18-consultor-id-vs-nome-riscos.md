# 2026-06-18 — Consultores: gap id × nome e riscos de consistência

**Agente:** Claude Code (delegado a `data-layer-supabase`)
**Tipo:** investigação (read-only — nenhum código alterado)
**Arquivos analisados:** `database/schema.sql`, `database/migrations/006_perfil_consultor.sql`,
`src/dashboard/loaders.py`, `src/dashboard/rls.py`,
`src/dashboard/kpis/rankings.py`, `src/dashboard/kpis/gerais.py`

## Objetivo

Verificar como o projeto trata consultores, dado que a informação fica em
uma **tabela separada** (`consultores`). Levantar riscos de consistência.

## Achado central

O banco identifica consultor por **`id`** (PK `consultores.id`;
`contratos.consultor_id` FK nullable; UNIQUE `(nome, loja_id)` — o mesmo
nome pode existir em lojas diferentes). Mas a **aplicação colapsa tudo para
a string `CONSULTOR` (nome)**: groupby de rankings, escopo RLS
(`rls.py:74-76` `df[df["CONSULTOR"].isin(escopo)]`) e `excluir_supervisores`
(`gerais.py:51-52`) operam por nome. As policies RLS no Postgres
(`pol_contratos_consultor`, `pol_metas_consultor`, migração 006) usam
`consultor_id` corretamente, mas o dashboard re-filtra em pandas por nome.

## Riscos (todos PRÉ-EXISTENTES — não introduzidos nesta sessão)

- **R1 — Colisão de nome (ALTO).** Dois consultores homônimos em lojas
  distintas (dois `id`) são somados numa linha de ranking; `Loja=("LOJA",
  "first")` mostra só uma loja. Pior: escopo `["JOÃO SILVA"]` no
  `aplicar_rls` mostra os contratos **dos dois** (vazamento app-side; a
  policy do banco por `id` está correta, mas não é o que o usuário vê).
- **R2 — Consultor em >1 loja no período (MÉDIO).** `Loja=first` atribui
  pontos/meta a uma loja arbitrária; `aplicar_rls_metas` puxa metas de
  todas as lojas que ele tocou.
- **R3 — Supervisor que também vende (MÉDIO).** `excluir_supervisores`
  remove por nome; um supervisor vendedor tem as vendas excluídas, e um
  homônimo de supervisor é excluído por engano.
- **R4 — Cadastro × contratos (MÉDIO).** Consultor no cadastro sem
  contratos → zero contexto de metas (`aplicar_rls_metas` acha
  `df_dados["LOJA"].unique()` vazio), embora `consultores.loja_id` saiba a
  loja. `consultor_id = NULL` (cadastro deletado, `ON DELETE SET NULL`) →
  `CONSULTOR=""` vira um "consultor fantasma" nos rankings.
- **R5 — Escopo por nome nas metas (MÉDIO).** `aplicar_rls_metas` /
  `_fetch_metas_consultor` derivam a loja do consultor pela presença de
  contratos, não por `consultores.loja_id` (documentado como intencional em
  `rls.py:116-118`), divergindo da policy do banco.

## Divergências doc × código

- `rls.md` documenta a aproximação por nome corretamente, mas **não**
  sinalizava o gap id×nome como risco (corrigido: ver nota em `rls.md`).
- `schema.sql::chk_usuarios_perfil` não inclui `consultor` (adicionado pela
  migração 006). Esperado no modelo de migrations; o schema consolidado
  está defasado quanto ao perfil consultor.

## Encaminhamento

- Correção de R1 (chavear por `id` ponta a ponta) é mudança **estrutural
  cross-domínio** (schema/views → loaders → rls). Será planejada à parte
  pelo orquestrador antes de qualquer código (ver follow-up).

## Correção (contexto de domínio do usuário, 2026-06-18)

O usuário esclareceu o domínio — isto **refuta R1 e R3 como bugs** e
**descarta o plano name→id** (que teria introduzido um bug):

- **Não há consultores homônimos** → o nome identifica unicamente a pessoa;
  os cenários de colisão/vazamento de R1 não ocorrem.
- **Consultores são transferidos de loja no mês** e ganham nova linha em
  `consultores` (novo `consultor_id` por loja, **mesmo `nome`**). Logo,
  **agregar por nome é o correto** para "produção do consultor conta para ele";
  chavear por `id` **fragmentaria** o consultor transferido. ⇒ **Plano R1
  (name→id) descartado.**
- **Produção da loja** já é por `contratos.loja_id` (coluna NOT NULL própria;
  a view deriva `loja` de `c.loja_id`, não do consultor) — correta e
  independente da transferência.
- **R3:** supervisores podem vender, mas a produção conta **só para a loja**.
  É exatamente o que `excluir_supervisores` faz (remove supervisor dos rankings
  de consultor; mantém nas agregações de loja). Comportamento **correto**.

**Resíduos menores (opcionais, não-bugs):**
- **R2** — em rankings de consultor, `Loja=("LOJA","first")` exibe **uma** loja
  arbitrária para um consultor transferido (a soma da produção está certa; só o
  rótulo de loja é cosmético).
- **R4** — **tratado na ingestão**: o consultor é obtido do próprio contrato
  quando não encontrado no cadastro, de modo que `consultor_id` fica populado.
  A view `v_contratos_dashboard` (migração 017) usa `con.nome` direto, sem
  fallback, justamente porque na prática `consultor_id` não fica NULL — logo o
  "consultor fantasma" (`""`) não ocorre. (O fallback explícito
  `COALESCE(con.nome, …consultor_nome…, '(Sem Consultor)')` existe nas tabelas
  de Reconquista — migrações 025/026/028/030 — que guardam o nome bruto.)

## Referências

- Investigação delegada ao subagente `data-layer-supabase` (sessão 2026-06-18).
- [rls.md](../rls.md), [data-layer.md](../data-layer.md).
