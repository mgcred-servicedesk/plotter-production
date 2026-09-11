# 2026-09-11 — Meta individual do consultor substitui o rateio da meta da loja

**Agente:** Claude Code (subagente `biz-rules`)
**Tipo:** bugfix / regra de negócio
**Arquivos tocados:** `src/dashboard/kpis/gerais.py`,
`src/dashboard/kpis/rankings.py`, `src/dashboard/tabs/rankings.py`,
`src/dashboard/chat_ia/tools.py`, `app.py`,
`docs/agents/business-rules.md`
**Commit(s):** (não commitado nesta sessão)

## Objetivo

Eliminar duas distorções de atingimento: (1) o ranking de consultores
rateava a meta da loja pelo nº de consultores que produziram, premiando
quem estava em loja desfalcada; (2) os cards/KPIs comparavam os pontos
de um único consultor contra a meta da LOJA INTEIRA (~2x subestimado),
propagando para o dashboard de Pontuação.

## O que foi feito

- `resolver_loja_principal` (`kpis/gerais.py`): loja do consultor no
  período = a de maior pontuação; empate → nome alfabético. Substitui
  `("LOJA", "first")` em `_agrupar` (escopo consultor).
- `metas_pontos_consultor` (`kpis/gerais.py`): frame de **uma linha**
  com `META_PRATA`/`META_OURO` de escopo CONSULTOR da loja resolvida,
  preservando `REGIAO`/`REGIAO_ATUAL`/`META_BRONZE` do escopo LOJA.
- `calcular_ranking_consultores`: novo kwarg `df_metas_consultor`; o
  rateio foi **removido sem fallback**. `df_metas` (escopo LOJA) segue
  na assinatura (dois call sites) mas não participa mais do cálculo —
  documentado na docstring. `calcular_ranking_lojas` intocado.
- `meta_individual_por_loja` (`kpis/rankings.py`): lookup puro, reusado
  pela aba para avisar quais lojas exibidas estão sem meta individual.
- `tabs/rankings.py`: `df_metas_cons` propagado por `_render_par`,
  `_render_consultores`, `_render_secao_regiao`, `_render_regioes` e
  `render_tab_rankings`; `st.caption("⚠ ...")` nomeia as lojas sem meta.
- `app.py`: aba Rankings recebe `carregar_metas_produto_consultor`
  org-wide (como `df_metas_full`); no recorte de um consultor,
  `df_metas_kpis` alimenta só `obter_kpis_gerais_periodo`.
- `chat_ia/tools.py`: `tool_ranking_periodo` carrega as metas de
  consultor (`aplicar_rls_metas` sobre o frame) — sem isso o chat
  responderia 0% para todo mundo.

## Validação (08/2026, dados reais)

| Consultor | Loja | Pontos | Meta | Atingimento |
|---|---|---|---|---|
| ELAINE GUARDENGUI DA SILVA | HELP ITABORAI | 607.108 | 320.000 | **189,7%** (1º) |
| VITOR GONCALVES MOURA | HELP TIJUCA ALMIRANTE | 614.916 | 360.000 | **170,8%** (2º) |
| PAULA VIRGINIA G. GONCALVES | HELP PENHA | 314.777 | 360.000 | **87,4%** (32º) |
| CAMILLY DE OLIVEIRA LAURIA | HELP LARANJEIRAS | 210.808 | 320.000 | **65,9%** (53º) |

Todos batem com a apuração do usuário. CAMILLY saiu do 11º (131,8%
pelo rateio). Cards: CAMILLY 16,5% → 65,9%; PAULA 32,5% → 87,4%.

## Decisões não óbvias

- **Loja por maior pontuação, não por contagem de contratos** — a meta
  é em pontos, então o critério de "onde ele trabalha" acompanha a
  mesma unidade. 6 consultores com 2 lojas em 08/2026.
- **`df_metas_kpis` local em vez de reatribuir `df_metas_f`** — o
  `df_metas_f` também alimenta `render_tab_regioes`, o `ChatContext` e
  `obter_kpis_qtd_periodo`; trocá-lo globalmente entregaria um frame de
  uma linha para consumidores que esperam escopo LOJA. Só os KPIs
  gerais mudam de fonte. `_chave_kpis` **não** foi tocada
  (`ui_filtro_consultor` já é o componente 6 da chave).
- **Metas da aba Rankings vão org-wide (sem `aplicar_rls_metas`)** —
  espelha `df_metas_full`: a aba compara todo mundo. No chat IA, ao
  contrário, o frame passa por `aplicar_rls_metas` porque o
  `ChatContext` é pós-RLS por contrato.
- **`_mpc` vazio mantém o escopo LOJA nos cards, mas com aviso** — não
  é fallback silencioso: a caption diz que a comparação é com a meta da
  loja. Sem produção no período não há loja ⇒ meta 0 + aviso.
- **Premissa:** um único consultor no recorte. Com mais de um nome em
  `df_f`, `metas_pontos_consultor` devolve frame vazio (meta 0) + aviso,
  em vez de somar metas de pessoas diferentes.

## Pendências / follow-ups

- [ ] **Testes (outro subagente):** `tests/test_kpis_rankings.py::
  TestCalcularRankingConsultores::test_meta_rateada_por_consultores_da_loja`
  e `tests/test_chat_ia_tools.py::TestToolRankingPeriodo::
  test_consultor_atingimento` codificam o rateio removido e falham.
  O teste do chat precisa de `monkeypatch` em
  `carregar_metas_produto_consultor` no namespace de `chat_ia.tools`
  (hoje a chamada vai à rede durante o teste).
- [ ] **DIGITAL sem meta em nenhum escopo:** 3 consultores, 425.008
  pontos em 08/2026, atingimento 0% (já era 0% antes — o rateio de uma
  meta inexistente também dava 0). O aviso novo passa a exibir isso na
  aba. Decidir: cadastrar meta para DIGITAL ou excluí-la do ranking de
  consultores como o VAI E VEM.
- [ ] Aceleradores nos cards de quantidade (escopo CONSULTOR) — outro
  subagente.

## Referências

- Docs consultados: [business-rules.md](../business-rules.md) (seções
  Metas, Exclusão de supervisores, Lojas de backoffice),
  [rpi-workflow.md](../rpi-workflow.md), [conventions.md](../conventions.md)
