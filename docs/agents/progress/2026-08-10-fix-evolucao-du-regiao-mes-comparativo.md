# 2026-08-10 — Fix: comparativo "Mês Anterior" zerado por região no painel Evolução Média DU

**Agente:** Claude Code
**Tipo:** bugfix
**Arquivos tocados:** `src/dashboard/tabs/produtos.py`
**Commit(s):** —

## Objetivo

Não foi um pedido direto — apareceu como efeito colateral de um subagente
(`streamlit-ui-specialist`) durante a ST-06 do plano de
[CLT/Consignado](2026-08-06-plano-clt-consignado-emissao-seguros.md),
enquanto investigava o comportamento de `gerente_comercial` em
`_render_produto_regional`. O usuário confirmou, depois de eu flagar a
mudança não solicitada, que o problema já era conhecido ("dados de média
para comparativo regional não estava disponível") e pediu para manter e
formalizar.

## O que foi feito

- `_carregar_mes_comparativo` (`produtos.py`) agora cacheia, em paralelo
  ao `<prefixo>_cache` pós-RLS, um snapshot **pré-RLS**
  (`<prefixo>_cache_full`) do mesmo mês — mesma ideia do `df_full` que
  `app.py` já mantém pro mês atual (`app.py:391-399`), sem query extra
  (só guarda a referência ao frame antes de `aplicar_rls`).
- Função nova `_mes_comparativo_full(prefixo)` lê esse cache.
- `render_tab_produtos` passa a alimentar `calcular_evolucao_media_du`
  (painel "Evolução Média DU por Região") com
  `_mes_comparativo_full(_PREFIXO_MES_ANT)` no lugar do `df_ant`
  pós-RLS.
- `limpar_cache_comparativos` também limpa a chave `_cache_full`.
- Documentado o padrão (pré-RLS, só agregado por região pode sair dele)
  em [docs/agents/rls.md](../rls.md#exceção-agregados-cross-região-pré-rls-df_full).

## Decisões não óbvias

- **Por que isso é seguro (não é bypass de RLS):** o lado "Mês Atual" do
  mesmo painel já usava `df_full` (pré-RLS) desde antes desta mudança —
  o painel é uma comparação **entre regiões**, propositalmente
  cross-perfil. O bug era a **assimetria**: só um lado do comparativo
  ficava pré-RLS. `calcular_evolucao_media_du`
  (`src/dashboard/kpis/regioes.py:283`) só devolve `groupby("REGIAO")`
  agregado — Região/Mês Anterior/Mês Atual/% Evolução + linha TOTAL —
  nunca contrato ou consultor individual, então nenhuma linha crua vaza
  para um perfil que não deveria vê-la.
- **Sintoma antes do fix:** para `gerente_comercial`, toda região que não
  fosse a sua aparecia com "Mês Anterior" = 0, inflando ou zerando o
  `% Evolução` de forma incoerente (ex: -100% ou "N/A" para regiões
  alheias, mesmo com produção real no mês anterior).
- **Escopo desta correção:** só o painel "Evolução Média DU por Região"
  (`render_tab_produtos`, chamada a `calcular_evolucao_media_du`). Não
  mexe em nenhuma outra tabela/KPI da aba Produtos — as demais seguem
  100% pós-RLS.

## Pendências / follow-ups

- [x] Adicionar teste de regressão cobrindo o cenário: `gerente_comercial`
      com escopo de uma região, comparativo "Mês Anterior" de outra
      região não deve zerar.
      **Feito em 2026-08-10 (test-automation-specialist).** 6 testes
      novos:
      - `tests/test_tabs_produtos.py::TestMesComparativoFull` (3 testes)
        — `_mes_comparativo_full` retorna o mesmo objeto cacheado sob
        `<prefixo>_cache_full` quando a chave existe (`is`, não cópia),
        `pd.DataFrame()` vazio quando ausente, e os dois prefixos
        (`_df_ant`/`_df_ano_ant`) não se misturam. Usa `st.session_state`
        real em modo bare (sem `AppTest` — a função não depende de
        widget/rerun), com fixture local de limpeza antes/depois de
        cada teste (não é fixture compartilhada em `conftest.py`).
      - `tests/test_tabs_produtos.py::TestLimparCacheComparativos`
        (2 testes) — confirma que `limpar_cache_comparativos` remove
        `<prefixo>_cache_full` (não só `_cache`/`_chave`) para os dois
        prefixos de `_PREFIXOS_COMPARATIVO`, e que rodar com
        `session_state` vazio não lança exceção.
      - `tests/test_kpis_regioes.py::TestCalcularEvolucaoMediaDu::test_mes_anterior_pre_rls_evita_zerar_regiao_alheia_do_gerente`
        (1 teste, o mais importante) — chama `calcular_evolucao_media_du`
        direto duas vezes com o mesmo "mês atual" (2 regiões, como
        `df_full`) e duas variantes de "mês anterior": pós-RLS (só a
        região do gerente, simulando `aplicar_rls`) vs. pré-RLS (as
        duas regiões). Prova que a variante antiga zera "Mês Anterior"
        da região alheia (0.0, "% Evolução" 0.0) e a variante nova
        preserva o valor real (100.0, "% Evolução" +130%), com a
        própria região do gerente idêntica nas duas — isola a diferença
        exatamente na região alheia.
      - Confirmado por `git stash` cirúrgico de `src/dashboard/tabs/produtos.py`
        (reversão temporária do fix): os testes de
        `TestMesComparativoFull`/`TestLimparCacheComparativos` quebram a
        coleção do módulo inteiro com `ImportError` (a função
        `_mes_comparativo_full` não existe pré-fix) — prova direta de
        que pegariam a regressão. O teste em `test_kpis_regioes.py`
        continua passando pré-fix, como esperado: `calcular_evolucao_media_du`
        em si nunca teve bug, o bug era só o call site (`produtos.py`
        passando `df_ant` pós-RLS em vez de `_mes_comparativo_full`);
        esse teste documenta/prova a diferença de comportamento entre
        as duas entradas possíveis, não uma regressão local da função.
      - Item 4 da tarefa original (integração leve tocando
        `_carregar_mes_comparativo`, mockando `consolidar_dados`/
        `aplicar_rls`) foi deliberadamente **não** implementado — a
        própria tarefa marcou como opcional e priorizou o teste acima.
      - Suíte completa: `469 passed`. `ruff check` limpo nos dois
        arquivos tocados.

## Referências

- Descoberto e revertido de escopo durante
  [2026-08-06-plano-clt-consignado-emissao-seguros.md](2026-08-06-plano-clt-consignado-emissao-seguros.md)
  (ST-05/ST-06).
- Padrão documentado em [docs/agents/rls.md](../rls.md).
