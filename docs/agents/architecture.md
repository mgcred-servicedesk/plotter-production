# Arquitetura

## Entrypoint

**`app.py`** (root) é o **único** entrypoint autoritativo. Consome Supabase
diretamente (views `v_*` e RPCs). Autocontido: não depende dos módulos de
KPI antigos nem dos loaders Excel.

Comando: `streamlit run app.py`

Após a refatoração SOLID de 2026-08 (`refactor/app-py-solid-fase1`, SRP +
OCP), `app.py` é um **orquestrador fino** (~864 linhas): autentica, monta
sidebar (via `ui/sidebar.py`, incluindo o seletor de Período), carrega
dados do período numa chamada (`loaders.py::carregar_periodo_dashboard`),
aplica RLS, calcula KPIs numa chamada
(`kpis/gerais.py::obter_kpis_periodo`) e despacha render das abas via um
**registro único** (`_AbaNav`, ver [ui-components.md](ui-components.md))
para `src/dashboard/{tabs,pages}/*`. Toda lógica pesada vive em
`src/dashboard/{loaders,kpis,ui,tabs,pages}/`.

Features novas vão **sempre** para `app.py` na raiz. Os antigos
`dashboard*.py` e o pipeline Excel/PDF (`src/reports/`,
`src/data_processing/`, `gerar_relatorio*.py`) foram **removidos** do
projeto — o `app.py` consome o Supabase diretamente.

## Árvore

```
app.py                         ← ★ main entry point (orquestrador)
src/
  config/
    supabase_client.py         ← get_supabase_client()
    settings.py                ← PRODUTOS_EMISSAO, PACK_SPLIT_LABELS/PACK_LABEL_AGREGADO, NOMES_DISPLAY_PRODUTO (taxonomia vem do banco)
  shared/
    dias_uteis.py              ← calcular_dias_uteis() + carregar_feriados()
  dashboard/
    auth.py                    ← tela_login, usuario_logado, fazer_logout, PERFIS
    rls.py                     ← aplicar_rls, aplicar_rls_metas, aplicar_rls_supervisores
    permissions.py             ← pode_ver() — matriz de permissões de abas e cards
    loaders.py                 ← carregar_* (contratos pagos/analise/cancelados, metas,
                                 pontuação, períodos, categorias, lojas, consultores).
                                 Implementa cache dual _atual/_historico.
    formatters.py              ← formatadores específicos do dashboard
    user_mgmt.py               ← render_pagina_usuarios()
    feriados_mgmt.py           ← render_pagina_feriados()
    kpis/                      ← cálculo de KPIs por domínio
      gerais.py                ← calcular_kpis_gerais, _analise, _cancelados,
                                 _qtd_produtos, medias_du_por_nivel, metas_produto_diarias
      produtos.py              ← KPIs por produto (PRODUTOS_DASHBOARD)
      regioes.py               ← evolução MoM D.U., análise por produto/região
      rankings.py              ← rankings de lojas, supervisores, consultores
      consultor.py             ← KPIs do dashboard individual do consultor
      evolucao.py              ← séries temporais
    tabs/                      ← render de cada aba
      produtos.py, regioes.py, rankings.py, analiticos.py, evolucao.py,
      em_analise.py, detalhes.py, consultor.py, pagamentos_online.py
    ui/                        ← componentes visuais
      sidebar.py                ← render_theme_toggle, render_sidebar_usuario,
                                   render_sidebar_visualizar_como, render_sidebar_filtros_perfil,
                                   aplicar_filtros_ui, filtrar_metas_ui, render_periodo
      theme.py                 ← sistema de temas (CHART_THEME, CSS vars, aplicar_tema),
                                   ocultar_widgets_nativos, render_overlay_fresh_login
      theme_claro_avancado.py  ← variante de tema claro
      header.py                ← render_header, render_status_bar
      kpi_cards.py             ← cards de KPIs principais, metas e quantidade
      kpi_cards_reforma.py     ← KPIs dominantes da reforma (render_kpis_reforma)
      resumo_executivo.py      ← farol/resumo executivo narrativo
      prioridades_acao.py      ← bloco "onde agir agora"
      charts.py                ← funções de criação de gráficos Plotly
      skeleton.py              ← loading state
    components/
      tables.py                ← exibir_tabela()
    pages/
      dashboard_pontuacao.py   ← dashboard de pontuação + render_diagnostico_pontuacao
      config.py                ← render_pagina_config() (usuários/feriados p/ admin, "Minha Conta" p/ demais)
      detalhes_cards.py         ← render_detalhe_* + render_drilldown_card() (dispatch dos 4 cards)
database/
  migrations/                  ← migrations numeradas (001…)
  schema.sql
assets/
  dashboard_style.css          ← design system + tema CSS custom properties
  logotipo-mg-cred.png
configuracao/                  ← planilhas auxiliares (HC, lojas, supervisores)
```

## Fluxo de carregamento (em `app.py`)

1. `tela_login()` → gate de autenticação.
2. `carregar_estilos_customizados()` + `aplicar_tema()` (de `ui/theme.py`).
3. Sidebar (`ui/sidebar.py::render_periodo`) monta período (ano/mês) e opções de admin.
4. `carregar_periodo_dashboard(mes, ano, on_progress=...)` (em `loaders.py`) — uma
   chamada que encapsula `consolidar_dados` (pagos) + categorias + metas de produto +
   `carregar_contratos_em_analise`/`_cancelados`, já aplicando `aplicar_conta_valor`
   (`kpis/detalhes_cards.py`), `filtrar_janela_recente` (30 dias, `kpis/gerais.py`) e
   `aplicar_nomes_display_produto` (`loaders.py`). Devolve o NamedTuple `DadosPeriodo`.
5. **RLS** imediatamente após o load (ver [rls.md](rls.md)).
6. `obter_kpis_periodo(...)` (em `kpis/gerais.py`) — uma chamada que calcula
   `calcular_kpis_gerais`, `_analise`, `_cancelados`, `_qtd_produtos`,
   `medias_du_por_nivel`, `metas_produto_diarias` e memoiza o resultado em
   `st.session_state` por `(mes, ano, role, escopo, filtros de UI)`.
7. `pode_ver(chave, role)` (de `permissions.py`) decide quais abas/cards renderizam.
8. `render_tab_*` é despachado por um **registro único de abas** (`_AbaNav`
   NamedTuple em `app.py`, ver [ui-components.md](ui-components.md)) conforme
   o item selecionado em `st.pills` (não `sac.tabs` — trocado para evitar
   abas inacessíveis por overflow em telas estreitas). Adicionar/remover uma
   aba é uma entrada nesse registro, não um `if/elif`. A aba "Produtos"
   carrega comparativos (mês anterior/YoY) só quando selecionada, via
   helpers internos de `tabs/produtos.py`.
9. Drill-down de cards (`?card=<key>` ou clique) é despachado por
   `pages/detalhes_cards.py::render_drilldown_card`.

## Banco de dados (Supabase)

### Tabelas principais

- `periodos` — mes/ano ↔ id (imutável).
- `categorias_produto` — taxonomia com `grupo_dashboard`, `grupo_meta`, `conta_valor`, `conta_pontuacao`.
- `produtos` — FK → `categorias_produto`.
- `contratos` — fato principal; FKs para lojas, consultores, produtos, periodos.
- `pontuacao` — PTS por categoria/período.
- `metas` — metas GERAL e por LOJA.
- `metas_produto` — metas por produto.
- `feriados` — exceções para cálculo de DU (migração `005`).
- `usuarios` — autenticação + perfil + escopo.

### Views e RPCs (preferidas em vez de joins na aplicação)

- `v_contratos_dashboard` — contratos pagos com todos os joins + flags já resolvidos.
- `v_contratos_cancelados`
- RPC `obter_pontuacao_periodo(p_mes, p_ano)` — calcula pontuação final por consultor/loja/região.

Migrações moram em `database/migrations/` e são numeradas. Veja
[data-layer.md](data-layer.md) para padrões de consumo.

## Stack

| Camada | Lib | Versão mínima |
|---|---|---|
| Data | Pandas | 2.2+ |
| Data | NumPy | 1.26+ |
| Viz interativa | Plotly | 5.20+ |
| Frontend | Streamlit | 1.35+ |
| Componentes | streamlit-antd-components | latest |
| Banco | Supabase (PostgreSQL) | — |
| Excel | openpyxl | — |
| PDF | ReportLab + kaleido | — |
| Charts PDF | Seaborn / Matplotlib | 0.13+ / 3.8+ |
| Dev | ruff, pytest, uv, python-dotenv | — |
