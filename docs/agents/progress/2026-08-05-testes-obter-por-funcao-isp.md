# 2026-08-05 — `TestObterKpisPeriodo` substituída por 6 classes por função (ST-03)

**Agente:** Claude Code (`test-automation-specialist`)
**Tipo:** refactor de testes
**Arquivos tocados:** `tests/test_kpis_gerais.py`
**Commit(s):** ver `refactor/kpis-periodo-isp-fase3` (ST-03)

## Objetivo

Fechar a fase 3 do ISP em `kpis/gerais.py`: `obter_kpis_periodo` (14
kwargs, `KpisPeriodo` de 8 campos, uma chave de cache só) foi decomposta
em 6 funções independentes no ST-01 (`64b49f6`) e `app.py` migrado no
ST-02 (`34d16eb`); `tests/test_kpis_gerais.py` ainda importava os nomes
antigos e quebrava a coleta (`ImportError: KpisPeriodo`).

## O que foi feito

- Import: `KpisPeriodo`/`obter_kpis_periodo` → `KpisPipeline` +
  `PRODUTOS_DASHBOARD` + as 6 `obter_*_periodo`.
- `TestObterKpisPeriodo` (236 linhas, 1 classe) virou **6 classes**, uma
  por função (`TestObterKpisGeraisPeriodo`, `TestObterKpisPipelinePeriodo`,
  `TestObterMediasPeriodo`, `TestObterMediasOrganizacaoPeriodo`,
  `TestObterMetasProdDiariasPeriodo`, `TestObterKpisQtdPeriodo`) + 1 nova
  (`TestLimparCacheKpis`, function própria que também merece classe
  própria pela convenção `Test<NomeDaFuncao>`).
- Fixtures/kwargs-builders extraídos para **módulo** (não repetidos 6x):
  `df_metas_produto_periodo`/`df_escopo_a`/`df_escopo_b` (`@pytest.fixture`,
  mesmos DataFrames literais do antigo `_df_metas_produto`/`_df_a`/`_df_b`)
  e `_kwargs_gerais`/`_kwargs_pipeline`/`_kwargs_medias`/
  `_kwargs_medias_organizacao`/`_kwargs_metas_prod_diarias`/
  `_kwargs_kpis_qtd` (funções simples, um builder por assinatura — cada
  uma só pega o subconjunto de kwargs que sua função pede).
- **Os 3 invariantes do teste antigo foram replicados nas 6 funções, sem
  exceção**, incluindo o mais importante: `test_mudanca_escopo_invalida_e_recalcula`
  (dois "gerentes" mesmo role, escopos R1/R2 vs R3 — a fronteira de RLS
  documentada em `_chave_kpis`). Para funções sem diferença óbvia de
  valor entre escopos (`medias_organizacao`, que é PRÉ-RLS por
  propósito), a asserção usa `df_full` distinto por chamada mesmo assim,
  para provar que a chave nova realmente disparou recálculo com o dado
  novo — não só que a chave mudou.
- Em vez de literais numéricos hardcoded para os novos KPIs (pipeline,
  médias, qtd), os testes de miss/hit/escopo comparam o retorno de
  `obter_X_periodo` contra uma chamada direta a `calcular_X(...)` com os
  MESMOS argumentos — mais robusto a mudanças futuras em `calcular_*` e
  menos sujeito a erro de aritmética manual do que hardcodar o número.
- `test_cache_mantem_dict_com_as_8_chaves_do_kpis_periodo` removido (não
  existe mais um dict único); substituído por 1 teste de forma por
  função, cada um verificando a estrutura REAL do cache daquela função
  (lida do código-fonte, não assumida): `kpis_gerais`/`medias`/
  `medias_organizacao` cacheiam o **dict de retorno direto**;
  `kpis_pipeline` cacheia um **dict de 2 chaves nomeadas**
  (`KpisPipeline._fields`); `metas_prod_diarias`/`kpis_qtd` cacheiam uma
  **lista** de 1 item por produto (não um dict — confirmado lendo
  `calcular_metas_produto_diarias`/`calcular_kpis_qtd_produtos`).
- `test_limpar_cache_kpis_forca_recalculo` reescrito para as 12 chaves
  (6 `_cache` + 6 `_chave`): chama as 6, confirma as 12 presentes,
  `limpar_cache_kpis`, confirma as 12 ausentes, chama as 6 de novo com a
  MESMA chave de escopo e confirma `id()` novo em cada um dos 6 caches.
  `test_limpar_cache_kpis_e_idempotente` mantido sem alteração.
- Prova explícita de "sem recálculo redundante" da chamada interna a
  `obter_kpis_gerais_periodo` (decisão da ST-01): spy em
  `calcular_kpis_gerais`, chama `obter_kpis_gerais_periodo` direto, depois
  `obter_metas_prod_diarias_periodo` **e** `obter_kpis_qtd_periodo` com a
  MESMA chave — confirma 1 chamada só ao `calcular_kpis_gerais` nos dois
  casos (a subtarefa pedia pelo menos uma das duas; fiz as duas por serem
  baratas e a garantia valer para ambas).
- `TestObterKpisQtdPeriodo` ganhou
  `test_role_supervisor_usa_ritmo_organizacao_para_media_ref` (df dedicado,
  não reaproveita `df_escopo_a`/`b`) para exercitar o ramo
  `role in (supervisor, consultor)` de `_ritmo_organizacao` dentro da
  função composta — o comportamento de `_ritmo_organizacao` em si já é
  coberto por `TestRitmoOrganizacao` em `test_app_helpers.py`.
- `TestObterMediasOrganizacaoPeriodo` ganhou
  `test_granularidade_segue_filtro_ui_quando_gerente_afunila` (também
  com df dedicado — em `df_escopo_a`, LOJA e REGIAO coincidem 1-para-1,
  então agrupar por uma ou por outra dá a MESMA média e não provaria
  nada; o df novo separa REGIAO/LOJA/CONSULTOR em 3 partições distintas).
- Docstrings do módulo e de cada classe atualizadas — nenhuma referência
  órfã a `obter_kpis_periodo`/`KpisPeriodo` como API viva (só como
  narrativa histórica do refactor, que é legítima).
- `tests/test_app_helpers.py` conferido: já cobre `_chave_kpis`,
  `_ritmo_organizacao` e `serie_diaria_pago` com os nomes novos (feito no
  ST-01) — nenhuma duplicação de cobertura introduzida aqui.

## Decisões não óbvias

- **Builders como funções simples, não fixtures, para os kwargs.** Os 3
  DataFrames "grandes" (escopo A/B, metas produto) viraram
  `@pytest.fixture` no módulo (reuso automático em todas as classes do
  arquivo, sem repetir a definição); os kwargs-dict por função **não**
  viraram fixture porque cada teste varia `df`/`perfil`/`role` em
  combinações diferentes (mesma função poderia receber 4 combinações
  distintas até no mesmo teste) — fixture fixa o valor por execução do
  teste, função simples deixa parametrizar. Precedente já existente no
  repo: `_prep` em `test_ui_tables.py` e `_set_perfil` em
  `test_rls_cancelados.py` são funções módulo-level, não fixtures.
- **`TestLimparCacheKpis` como classe própria**, não distribuída dentro
  das 6 outras. A subtarefa listava os testes de `limpar_cache_kpis`
  junto da antiga `TestObterKpisPeriodo`, mas essa função é testada por
  direito próprio (`limpar_cache_kpis` é pública, testada com sua própria
  classe pela convenção `Test<NomeDaFuncao>` do projeto) e o teste é
  inerentemente cross-cutting (chama as 6 para provar que uma única
  função esquece todas) — não cabia em nenhuma das 6 sem favorecer uma
  arbitrariamente.

## Validação

- `.venv/bin/ruff check tests/test_kpis_gerais.py` — limpo.
- `.venv/bin/python -m pytest tests/ -v` — **430 passed**, 1 warning
  pré-existente e não relacionado (`tables.py:321`, parsing de data em
  `test_ui_tables.py`).
- `tests/test_kpis_gerais.py` sozinho, 2 execuções seguidas: **76 passed**
  nas duas (era 13 classes/774 linhas antes → agora 20 classes, cada
  `obter_*_periodo` com miss/hit/escopo + forma do cache).
- Confirmado: todas as 6 classes `TestObter*Periodo` têm
  `test_mudanca_escopo_invalida_e_recalcula`.

## Pendências / follow-ups

- Nenhuma. ST-03 fecha a fase 3 (`refactor/kpis-periodo-isp-fase3`):
  ST-01 (lógica), ST-02 (call site), ST-03 (testes) concluídas.

## Referências

- Docs consultados: [docs/agents/rpi-workflow.md](../rpi-workflow.md),
  [AGENTS.md](../../../AGENTS.md)
- Antecedentes: [2026-08-05-decomposicao-obter-kpis-periodo-isp.md](2026-08-05-decomposicao-obter-kpis-periodo-isp.md) (ST-01),
  [2026-08-05-kpis-periodo-isp-call-site.md](2026-08-05-kpis-periodo-isp-call-site.md) (ST-02)
