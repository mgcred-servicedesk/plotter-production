# 2026-07-29 — Nomenclatura de produto: desmembramento do PACK e rótulos canônicos

**Agente:** Claude Code
**Tipo:** feature + refactor
**Arquivos tocados:** `src/config/settings.py`,
`src/dashboard/kpis/produtos.py`, `src/dashboard/kpis/detalhes_cards.py`,
`src/dashboard/kpis/gestao.py`, `src/dashboard/ui/kpi_cards.py`,
`src/dashboard/ui/kpi_cards_pontuacao.py`,
`src/dashboard/ui/kpi_cards_reforma.py`,
`src/dashboard/ui/prioridades_acao.py`,
`src/dashboard/ui/prioridades_pontuacao.py`,
`src/dashboard/tabs/pagamentos_online.py`, `tests/*`,
`docs/agents/business-rules.md`, `docs/agents/architecture.md`

Continua [2026-07-29-subproduto-analiticos.md](2026-07-29-subproduto-analiticos.md)
(que desmembrou o PACK em Analíticos, Em Análise, rankings e distribuição).

## Objetivo

Fechar a nomenclatura de produto/subproduto: aplicar o desmembramento do
PACK em **tudo que agrupa PACK**, manter a **linha agregada** onde há
comparação valor × meta, e **padronizar os rótulos** pelos nomes da
planilha de origem.

## Decisões do usuário (respostas que guiaram a implementação)

1. **Onde desmembrar:** tudo que agrupa PACK.
2. **Superfícies com meta** (aba Produtos, heatmap região×produto, KPIs
   por região, cards MIX): manter a linha agregada do pack — a meta
   `FGTS_ANT_BENEF_13` é conjunta, não existe alvo por categoria.
3. **Rótulos:** padronizar tudo pelos nomes da planilha; o agregado passa
   a ser a junção dos três (`FGTS / ANT. DE BENEF. / CNC 13º`).
4. **Aba Gestão:** incluir o 13º (antes fora da visão), mesmo alterando o
   Total exibido.

## O que foi feito

- **Fonte única dos rótulos em `src/config/settings.py`**:
  `PACK_SPLIT_LABELS` (chaveado por `categoria_codigo`) e
  `PACK_LABEL_AGREGADO = " / ".join(...)`. `NOMES_DISPLAY_PRODUTO['PACK']`
  passou a derivar da constante. `kpis/produtos.py` importa e reexporta
  `PACK_SPLIT_LABELS` (imports existentes seguem funcionando).
- **6 grafias viraram 1.** Antes: `FGTS/Ant. Ben./CNC 13o` (settings),
  `FGTS/Ant.Ben./13o` (kpi_cards), `FGTS/Ant.Ben./13º` (kpi_cards_pontuacao,
  kpi_cards_reforma, prioridades_acao, prioridades_pontuacao). Todas
  apontam para `PACK_LABEL_AGREGADO`.
- **Desmembramento nas superfícies que faltavam:**
  - `detalhe_medias_por_produto` — quadro "Por Produto" das páginas
    *Média por Consultor* e *Média por Loja*.
  - `detalhe_analise_por_produto` / `detalhe_cancelados_por_produto` —
    não renderizados hoje (ver follow-ups), alinhados por coerência da API.
  - Helper `_por_produto_detalhado(agregador, df, *args)` em
    `kpis/detalhes_cards.py`: aplica `adicionar_produto_detalhado`, delega
    ao agregador genérico e renomeia a dimensão para `Produto`.
  - `PRODUTOS_GESTAO` (aba Gestão) — as 3 categorias derivadas de
    `PRODUTOS_DASHBOARD['FGTS_ANT_BEN_CNC13']` + `PACK_SPLIT_LABELS`,
    em vez de duas entradas hardcoded.
- **Alias da aba Pagamentos Online**: `Ant. Ben.` → `ANT. DE BENEF.` (o
  chip mostra o nome interno do produto; a fonte é o extrator DNA, não o
  PACK).
- **Docs**: nova seção "PACK — meta conjunta e desmembramento" em
  `business-rules.md` com a tabela agregado × desmembrado; `architecture.md`
  atualizado para citar as novas constantes de `settings.py`.
- **Testes**: 274 passed. Novos — desmembramento em
  `detalhe_analise_por_produto`, `detalhe_medias_por_produto`,
  `calcular_distribuicao_produtos`, PACK desmembrado em 3 colunas na
  Gestão, e um **teste de guarda** (`test_pack_permanece_agregado`) que
  trava o agregado em `calcular_kpis_por_produto` — a superfície com meta.

## Decisões não óbvias

- **Rótulos moram em `settings.py`, não em `kpis/produtos.py`** — a UI
  (`ui/kpi_cards*`, `ui/prioridades*`) precisa do rótulo agregado, e
  `settings` é a camada mais baixa (sem imports internos). Manter a
  constante em `kpis/` obrigaria módulos de UI a importar de `kpis/` só
  por causa de uma string.
- **O agregado deriva do split (`" / ".join`)** — impossível os dois
  vocabulários divergirem de novo; renomear um tipo do pack atualiza as
  duas leituras.
- **Coluna-dimensão dos quadros por produto virou `Produto`** — a tabela
  das páginas de Média exibia o cabeçalho cru `grupo_dashboard`. Como a
  dimensão passou a ser `PRODUTO_DETALHADO`, renomear na saída era
  necessário de todo jeito; `Produto` é o mesmo termo das demais tabelas.
- **Aba Gestão: `Total` mudou de valor** — antes somava 6 colunas (13º
  fora), agora soma 7. Números da aba sobem para consultores com produção
  de CNC 13º; foi escolha explícita do usuário.
- **Card de meta pode quebrar em 2 linhas** — `.mg-prod-name` (0.72rem,
  uppercase, sem `nowrap`) com um rótulo ~2× mais longo. Sem `truncate`
  no CSS, o texto envolve em vez de cortar; se incomodar, a correção é
  local (uma variante curta só para o card, alimentada pela mesma
  constante).

## Pendências / follow-ups

- [ ] **`detalhe_analise_por_produto` e `detalhe_cancelados_por_produto`
      não são chamados por nenhuma tela** (só por testes) — as páginas de
      detalhe usam os *pivots* (`detalhe_*_pivot`). Ficaram consistentes
      com as irmãs, mas são candidatas a remoção. **Não apagadas** — decisão
      do usuário.
- [ ] Validar visualmente o card de meta do pack e o eixo do gráfico de
      produtos com o rótulo longo (não roda headless).
- [ ] Segue valendo o follow-up do ETL (repo angry-man): tipos renomeados
      voltam com `categoria_id NULL`; o fallback client-side é mitigação.
      Ver [2026-07-09-rename-tipos-clt-ant-benef.md](2026-07-09-rename-tipos-clt-ant-benef.md).
- [ ] `obter_digitacao_diaria_detalhe` pré-agrega no banco e não expõe
      `tipo_produto` — linhas sem categoria seguem fora do desmembramento
      naquele pivot.

## Referências

- Docs consultados: [business-rules.md](../business-rules.md),
  [conventions.md](../conventions.md), [data-layer.md](../data-layer.md)
- Progress anteriores: [2026-06-29-split-pack-detalhe-cards.md](2026-06-29-split-pack-detalhe-cards.md),
  [2026-06-23-filtro-gestao-consultores.md](2026-06-23-filtro-gestao-consultores.md),
  [2026-07-07-higienizar-fgts-ant-ben-cnc13-insights.md](2026-07-07-higienizar-fgts-ant-ben-cnc13-insights.md)
