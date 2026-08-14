# 2026-08-14 — Produção pelo VLR BRUTO em Cobrança Consignável

**Agente:** Claude Code
**Tipo:** feature (regra de negócio + schema)
**Arquivos tocados:** `database/migrations/067_valor_consolidado_cobranca_consignavel.sql` (novo),
`src/dashboard/loaders.py`, `src/dashboard/tabs/analiticos.py`,
`tests/test_loaders_cobranca_consignavel.py` (novo),
`docs/agents/business-rules.md`, `docs/agents/data-layer.md`,
`database/INTEGRACAO.md`
**Commit(s):** — (pendente)

## Objetivo

Em propostas NOVAS de consignado BMG da modalidade Cobrança Consignável o
cliente usa parte do valor para quitar débitos com o banco, e o `VLR BRUTO`
(venda cheia) difere do `VLR BASE`. A produção de loja/consultor usava o
`VLR BASE`; passa a considerar o `VLR BRUTO` nessas operações.

## O que foi feito

- **Migration 067**: função `fn_eh_cobranca_consignavel` (critério único) +
  duas colunas ao final de `v_contratos_dashboard`:
  `is_cobranca_consignavel` e
  `valor_consolidado = CASE WHEN qualifica THEN GREATEST(valor_bruto, valor) ELSE valor END`.
  Bloco de validação com 8 queries de conferência.
- **`_COLS_CONTRATOS_PAGOS`**: `valor_consolidado → VALOR`, `valor → VALOR_BASE`.
  Nenhum dos ~40 consumidores de `VALOR` foi tocado.
- **`_fetch_cobranca_consignavel`**: máscara de critério em pandas substituída
  por `.eq("is_cobranca_consignavel", True)`. Sobrou só a reconferência de mês.
- `_cache_version` 3 → 4 em `consolidar_dados`/`_consolidar_*`.
- Sub-aba Cobrança Consignável passa a exibir **Valor Base / Valor Bruto /
  Valor Considerado**; métrica renomeada de "Valor Total" para "Valor
  Considerado".
- 14 testes novos (562 no total).

## Decisões não óbvias

- **Trocar a fonte de `VALOR` em vez de tocar os 40 consumidores.** A
  alternativa (coluna `VALOR_CONSOLIDADO` paralela, aplicada só nos KPIs de
  produção) deixaria ranking, ticket médio, metas e gráficos em `VLR BASE` —
  números divergentes entre abas, sem ninguém saber qual está certo. Como
  consequência aceita e confirmada, a **pontuação segue junto**
  (`pontos = VALOR × PTS`).
- **Critério em função SQL, não inline na view.** O predicado alimenta DUAS
  colunas derivadas; inline, ficaria escrito duas vezes e uma edição futura
  poderia atualizar só uma — produção subindo com a flag dizendo que não
  qualifica. Como função, as duas não têm como divergir, e alterar a regra
  vira `CREATE OR REPLACE FUNCTION` sem reescrever a view (evitando a
  restrição de ordem de colunas do `CREATE OR REPLACE VIEW`).
- **`fn_eh_cobranca_consignavel` SEM `SET search_path = ''`** — desvio
  consciente da convenção das migrations 019/066. A cláusula `SET` grava
  `pg_proc.proconfig` e o planner **recusa inlinear** função SQL com
  `proconfig` (`inline_function`, `clauses.c`); sem inlining seriam ~64k
  chamadas por carga de período num compute Nano. A convenção protege funções
  `SECURITY DEFINER` e/ou que referenciam tabelas; esta é `SECURITY INVOKER` e
  não toca objeto nenhum — só argumentos e builtins, qualificados com
  `pg_catalog.`. **Não reintroduzir "por convenção" sem medir o EXPLAIN.**
  `PARALLEL SAFE` é obrigatório pelo mesmo tipo de razão: o default é
  `PARALLEL UNSAFE`, que desabilitaria plano paralelo em *toda* query da view.
- **`GREATEST` (nunca reduzir), decidido contra o literal da regra.** Se o
  `VLR BRUTO` vier menor que o `VLR BASE` (dado sujo do ETL), a produção não
  cai. A linha **continua** contando no contador — o critério de lá é
  `|bruto − base| > 0,005` em qualquer direção, então a contagem já em
  produção desde 08/2026 não mudou de comportamento.
- **Escopo só-pagos.** `v_contratos_em_analise`, `v_contratos_cancelados` e as
  RPCs `obter_digitacao_diaria*` seguem em `VLR BASE` — decisão de negócio,
  não limitação técnica (as duas views têm os joins necessários, se um dia for
  preciso estender).
- **Sem fallback defensivo em `_fetch_contratos_pagos`.** Um `try/except` que
  caísse para `valor` faria o dashboard exibir duas definições de produção
  conforme o estado do banco — o "engulir erro silenciosamente" que o
  `AGENTS.md` proíbe, em cima do número principal do negócio. Sem defesa o
  PostgREST devolve `42703` e o app quebra na carga, antes de qualquer usuário
  ver número errado (fail-closed). A janela é fechada pela ordem de deploy, e a
  067 é semanticamente neutra enquanto `valor_bruto` for NULL.
  **Assimetria intencional** com `_fetch_cobranca_consignavel`, que *mantém* o
  `try/except`: lá o degradado é zero, o caso neutro documentado de um contador
  de acelerador — aqui não existe "produção neutra".
- **`VALOR_BASE` fica cru** — não recebe os zeramentos de `conta_valor=False`
  nem de emissão que o `VALOR` recebe em `_executar_consolidacao`. Precedente
  no próprio arquivo: `PONTOS` (taxa crua) convive com `pontos` (computado).
  Consequência: a invariante `VALOR >= VALOR_BASE` vale na camada de **fetch**,
  não no frame consolidado — é onde o teste a ancora.
- **Divergência aceita com `_preencher_categoria_fallback`.** O mapa
  `_TIPO_PARA_CATEGORIA` leva `CONSIG`/`CONSIG BMG` → `CONSIG_BMG` quando
  `produtos.categoria_id` é NULL; o SQL usa `cp.codigo` cru. Uma linha assim
  não recebe o uplift — subnotifica, nunca superestima. **Zero mudança no
  contador** (o frame da Cobrança Consignável nunca aplicou o fallback).
  Replicar o mapa em SQL foi descartado: recriaria a duplicação de regra em
  duas linguagens que a 067 existe para eliminar. Monitorado pela query 6 do
  bloco de validação.
- **Constantes `_BANCOS_COBRANCA_CONSIGNAVEL` e `_TOLERANCIA_VALOR`
  removidas** (autorizado): mantê-las criaria duas fontes do mesmo critério em
  duas linguagens, e o ruff não avisaria (F401 não pega constante de módulo).
- **Padrão de teste novo autorizado**: fake fluente de `_sb()` (`from_`/
  `select`/`eq`/`order`/`limit` → `self`), isolado no arquivo novo. Sem ele
  não há como afirmar que o filtro é server-side, que é justamente a garantia
  central da mudança.

## Verificação

- `.venv/bin/python -m pytest tests/` — **562 passed** (548 baseline + 14 novos).
- `.venv/bin/ruff check src/ app.py tests/` — limpo.
- O bloco de validação da migration 067 (seção 4) **é a suíte do critério**,
  que deixou de ser alcançável por pytest. Rodar as queries 1-3 a cada
  alteração de `fn_eh_cobranca_consignavel`.

### Pós-aplicação (067 e 068 aplicadas em 2026-08-14) — **30/30 OK**

Blocos de validação das duas migrations, executados contra a base:

| Check | Resultado |
|---|---|
| Bordas de `fn_eh_cobranca_consignavel` (9 casos) | conforme, incl. `bruto < base` ⇒ conta no contador, não no valor |
| `is_cobranca_consignavel` / `valor_consolidado` NULL | 0 e 0 |
| `valor_consolidado < valor` | 0 — invariante "nunca reduz" |
| **Gate: qualificam / uplift** | **2 e R$ 15.429,70** — bateu com a prévia |
| `is_deflator` (068) | true só na ordem 1; exatamente 1 deflator por período |
| RPC 3 colunas, bordas 0→12, fallback temporal, pré-vigência | sem regressão |

**End-to-end pelo código de produção** (`_fetch_contratos_pagos` e
`_fetch_cobranca_consignavel` reais contra o Supabase):

- 08/2026: 2.222 linhas; `VALOR`/`VALOR_BASE` float64; `VALOR >= VALOR_BASE` em
  todas; exatamente 2 divergem.
- Produção 08/2026: **R$ 3.606.056,61 (VLR BASE) → R$ 3.621.486,31
  (consolidada)** — delta R$ 15.429,70 (0,43%).
- **06/2026 (4.950 linhas) e 07/2026 (6.470 linhas): `VALOR == VALOR_BASE` em
  100% das linhas** — nenhum histórico mudou, como previsto.
- `streamlit run app.py` → HTTP 200, sem erro no log.

### Auditoria de consolidação — todo KPI que soma valor

Método: cada KPI rodado **duas vezes** sobre 08/2026 — com o frame real
(`VALOR` = consolidado) e com um frame-controle (`VALOR := VALOR_BASE`,
simulando o dashboard pré-067). Delta esperado = R$ 15.429,70. KPI que deveria
mover e não move seria bug.

**Todos os 20 pontos de agregação propagaram o valor consolidado:**

| Módulo | Delta |
|---|---|
| `gerais.calcular_kpis_gerais` → `total_vendas` | 15.429,70 |
| produção por loja (HELP BANGU / SÃO GONÇALO) | 3.421,21 / 12.008,49 |
| pontos totais (`VALOR × PTS`) | 15.429,70 |
| `rankings`: lojas, consultores, ticket médio, média/DU | 15.429,70 (cada) |
| `regioes.calcular_kpis_por_regiao` | 15.429,70 |
| `produtos`: `kpis_por_produto`, distribuição (TOTAL e CONSIGNADO), por loja | 15.429,70 |
| `evolucao.calcular_evolucao_diaria` | 15.429,70 |
| `comparativos.calcular_evolucao_por_entidade` | 15.429,70 |
| `gestao.construir_tabela` (Total e Consignado) | 15.429,70 |
| `detalhes_cards.aplicar_conta_valor` | 15.429,70 |
| `prioridades_acao`: loja, consultor, região | propaga (soma mista de gaps/percentuais) |

Casos com delta **diferente** de 15.429,70, todos explicados:

- `regioes.calcular_kpis_por_produto_regiao` → 48.291,91 = `Valor` (15.429,70)
  + `Projeção` (32.402,37, o uplift escalado pelos DU restantes) + `Ticket
  Médio` (457,14) + percentuais. Colunas **derivadas** do Valor.
- `heatmap_regiao_produto[0]` (ranking) → delta 0. **Correto**: R$ 15 mil não
  muda posição de região. Já o `[1]` (% atingimento) moveu: GLENDA/CONSIGNADO
  +0,21 p.p. e JACQUELINE/CONSIGNADO +0,66 p.p.
- `aceleradores_loja`/`_consultor` → delta 0. **Correto**: são contagem.
- `indice_perda` → imune, calculado sobre **quantidade**.

**Inventário das fontes de valor** (só 2 pontos leem `v_contratos_dashboard`,
ambos via mapa do loader — sem bypass no código):

| Fonte | Valor | Escopo |
|---|---|---|
| `v_contratos_dashboard` → pagos e Cobrança Consignável | **consolidado** | ✅ na regra |
| RPC em análise / cancelados / digitação diária | VLR BASE | fora, por decisão |
| `v_pagamentos_online_efetivo` | fonte própria | não relacionado |
| `v_reconquista` (`saldo_contabil`) | não é valor de contrato | não relacionado |

**Mistura consolidado × base — 2 pontos, ambos aceitáveis e medidos:**

1. `gerais.py:347` `valor_total_digitado = pagos + análise` — só denominador de
   `variacao_analise`, nunca exibido como produção. Efeito medido: **−0,09 p.p.**
   (30,3023% → 30,2122%). Comentário no código esclarecido nesta sessão, porque
   a palavra "base" ali virou ambígua depois que `VALOR_BASE` passou a existir.
2. `prioridades_acao.calcular_prioridades_produto` → `perc_se_pagos` projeta
   "se os contratos em análise forem pagos" somando pipeline (base) ao
   realizado (consolidado). Direção **conservadora** — subestima a projeção.

### Estado do ambiente encontrado na auditoria (antes de aplicar)

A auditoria somente-leitura corrigiu três premissas do plano original:

- **065: aplicada.** `contratos.valor_bruto`/`valor_liquido` existem e a view
  expõe o `COALESCE`.
- **066: aplicada em versão ANTERIOR à do repo.** A tabela
  `faixas_acelerador_reconquista` existe com as 4 faixas (seed de 2026-08-11
  15:40 -03) mas **sem a coluna `is_deflator`**, e a RPC devolve só
  `{rotulo, is_fallback}`. O arquivo foi editado in-place depois de aplicado
  (commit `b7b4dcd`, 2026-08-12 11:50 -03) — ver "Follow-up 066" abaixo.
- **067: não aplicada** (esperado).
- **`angry-man`: já buildado E já em produção.** O bundle
  `dist/assets/index-DoWJCEE2.js` contém `VLR BRUTO`/`valor_bruto`; há
  instaladores 1.2.0 (`.AppImage`/`.deb`/`.exe`) de 2026-08-11. O código-fonte
  segue **não commitado** (10 arquivos modificados no working tree), mas
  **8.701 de 138.945 contratos já têm `valor_bruto` populado** — o ETL rodou.

### Impacto medido da 067 (prévia sobre dado real, antes de aplicar)

Critério da 067 aplicado em Python sobre as 105.370 linhas pagas da view:

| Métrica | Valor |
|---|---|
| Linhas com `\|bruto − base\| > 0,005` | 314 |
| **Qualificam pelo critério completo** | **2** |
| Uplift total | **R$ 15.429,70** |
| Meses afetados | **só 08/2026** — nenhum histórico muda |
| Linhas com bruto < base (onde o `GREATEST` protegeria) | 0 |

Os 2 contratos: `2991146` (HELP BANGU, R$ 34.805,44 → R$ 38.226,65) e
`2994099` (HELP SÃO GONÇALO, R$ 14.341,97 → R$ 26.350,46).

**Validação do critério contra a alternativa mais provável de erro:** 76 linhas
são `CONTRATO NOVO` + `NOVO` + `BMG` com diferença real e são excluídas pelo
`categoria_codigo`. Todas são **CLT** (`CONSIGNADO PRIVADO E-SOCIAL`,
`categoria_codigo` NULL na view → `CONSIG_PRIV` pelo fallback do Python). A
razão `bruto/base` delas é **constante em 1,0753** (desvio-padrão 0,0001,
faixa 1,0749–1,0753) — spread fixo de ~7,5%, estrutural do produto, **não**
cliente quitando débito. Os 2 que qualificam têm razões 1,0983 e **1,8373** —
arbitrárias, exatamente o que a regra de negócio descreve. O filtro por
categoria está correto.

> Consequência para a divergência do `_preencher_categoria_fallback`
> documentada acima: **não se materializa nestes dados**. O mapa manda `CLT` →
> `CONSIG_PRIV`, nunca `CONSIG_BMG`, então SQL e Python concordam em excluir
> essas 76 linhas.

## Ordem de deploy

1. ~~Aplicar 065~~ — feito (antes desta sessão).
2. ~~Aplicar 066~~ — feito, em versão anterior; completada pela 068.
3. ~~Aplicar **067**~~ — **feito em 2026-08-14, validado** (ver acima).
4. ~~Aplicar **068**~~ — **feito em 2026-08-14, validado** (ver acima).
5. **Deploy do Python** (loaders + UI + testes + docs) — pendente.
6. Limpar cache pelo botão de refresh do seletor de período (o bump de
   `_cache_version` cobre o deploy de *código*; aqui o *dado* já mudou antes).
7. Conferência de negócio na UI: sub-aba Cobrança Consignável listando as 2
   propostas, contagem batendo com o card do acelerador, produção de HELP BANGU
   +R$ 3.421,21 e HELP SÃO GONÇALO +R$ 12.008,49 em 08/2026, e o alerta de
   faixa deflatora aparecendo para consultor com total entre 0 e 2 (068).
8. `angry-man`: **commitar** o working tree (o build já está publicado — o
   risco aqui é perder o fonte, não a feature parar de funcionar).

**Efeito da 067 sobre o histórico: nenhum.** `valor_bruto` só está populado nas
importações recentes; nos meses anteriores é NULL, o `COALESCE` devolve
`c.valor`, a função retorna `false` e o `CASE` cai no `ELSE c.valor` ⇒
`valor_consolidado ≡ valor`. Medido: as 2 linhas afetadas estão ambas em
08/2026.

**Rollback:** pelo lado Python — reverter `_COLS_CONTRATOS_PAGOS` para
`"valor": "VALOR"`. Instantâneo e suficiente; a view com colunas extras não
incomoda ninguém (`CREATE OR REPLACE VIEW` não remove colunas de qualquer forma).

## Pendências / follow-ups

- **Deploy do código Python** — 067/068 já estão no banco e validadas; o
  dashboard em produção ainda roda a versão que lê `valor` como `VALOR`. Sem
  risco no intervalo: as colunas novas existem e são ignoradas pelo select
  explícito antigo.

### Migration 068 — completa a 066 (`is_deflator`)

Bug encontrado na auditoria e **corrigido nesta sessão** por
`database/migrations/068_faixas_acelerador_is_deflator.sql`.

- **Sintoma:** `carregar_faixa_acelerador` faz
  `bool(linhas[0].get("is_deflator"))` sobre o retorno da RPC, que devolvia só
  `{rotulo, is_fallback}`. `.get` de chave ausente → `None` → `False`. Não
  quebra, mas o alerta de deflator em
  [`kpi_cards_reforma.py:892`](../../../src/dashboard/ui/kpi_cards_reforma.py)
  **nunca dispara** — a faixa "0 a 2" não é sinalizada como desconto.
- **Causa:** a 066 foi aplicada em 2026-08-11 numa versão sem `is_deflator`; o
  arquivo ganhou a coluna depois (commit `b7b4dcd`, 2026-08-12), editado
  in-place — a violação da regra de imutabilidade é a causa raiz.
- **Re-executar a 066 não resolveria.** O arquivo é idempotente na *estrutura*
  (`ADD COLUMN IF NOT EXISTS`, `DROP FUNCTION` antes do `CREATE`), mas o seed
  usa `ON CONFLICT ... DO NOTHING` e as 4 linhas de Ago/26 já existem: a coluna
  nasceria com `DEFAULT false` e a faixa "0 a 2" continuaria sem a flag. O
  núcleo da 068 é justamente o `UPDATE` que faltava.
- **Decisão do `UPDATE`:** marca `ordem = 1` **apenas em períodos que ainda não
  têm nenhum deflator** (`NOT EXISTS`). Duas propriedades: idempotente, e não
  sobrescreve configuração deliberada — a 066 descreve a tabela como
  "configuração editável por SQL, sem deploy", então um período onde alguém já
  moveu a flag fica intacto.
- **Nenhuma mudança de Python.** `_fetch_faixa_acelerador` já lê a chave com
  default `False`; assim que a RPC passar a devolvê-la, a flag flui sozinha.
- **Escopo mínimo:** não toca em RLS/policy (aplicadas pela 066, inalteradas),
  não re-seeda faixas, não tem relação com a 067. Sem GRANTs a restaurar — a
  066 nunca definiu nenhum sobre essa RPC (usa o `EXECUTE` default de `PUBLIC`).

### Outros

- Ganho de custo não medido: `_fetch_cobranca_consignavel` deixou de paginar o
  período inteiro (~16k linhas, ~16 round-trips) e passou a 1 request
  recortado. Capturar baseline de `EXPLAIN (ANALYZE, BUFFERS)` antes da 067
  para comparação (query 8 do bloco de validação).
- **`angry-man` com 10 arquivos não commitados** (incl. `import-contratos.ts`,
  `package.json` 1.1.0 → 1.2.0). O build 1.2.0 já foi gerado e distribuído, e o
  dado já está no banco — o risco é **perder o fonte de algo que já está em
  produção**, não a feature parar.
- Vale confirmar com o negócio se **CLT** também pode ter Cobrança Consignável.
  Os dados dizem que não (razão constante de 1,0753 = spread estrutural), mas é
  uma leitura de dado, não uma regra escrita.
- **Decisão de UI em aberto (levantada na auditoria):** a sub-aba "Propostas
  Pagas" exibe a coluna "Valor" já **consolidada**. Nas 2 propostas de Cobrança
  Consignável isso diverge do `VLR BASE` do arquivo de origem, e ali não há
  coluna de VLR BASE para conciliar. Hoje o trio Base/Bruto/Considerado só
  existe na sub-aba Cobrança Consignável. Opções: (a) manter — quem concilia
  usa a sub-aba dedicada; (b) acrescentar "Valor Base" em Propostas Pagas.
  Não alterado sem decisão sua.
- Verificação visual em browser não feita — sem credenciais de teste nesta
  sessão (mesma lacuna do progress de 2026-08-13).

## Referências

- Docs atualizados: [business-rules.md](../business-rules.md) §"Produção pelo
  VLR BRUTO (valor consolidado)", [data-layer.md](../data-layer.md)
  §"Colunas padronizadas" e §"Invalidar cache quando a semântica muda",
  [INTEGRACAO.md](../../../database/INTEGRACAO.md) §4.2
- Progress relacionados:
  [2026-08-11-acelerador-combinado-reconquista-cobranca-consignavel.md](2026-08-11-acelerador-combinado-reconquista-cobranca-consignavel.md),
  [2026-08-13-aba-cobranca-consignavel.md](2026-08-13-aba-cobranca-consignavel.md)
- Migrations: `065_contratos_valor_bruto.sql`,
  `066_faixas_acelerador_reconquista.sql`,
  `055_drop_indexes_nao_usados_contratos.sql` (por que nenhum índice novo)
