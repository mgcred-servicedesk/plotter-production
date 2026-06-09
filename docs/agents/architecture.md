# Arquitetura

## Entrypoint

**`app.py`** (root) é o **único** entrypoint autoritativo. Consome Supabase
diretamente (views `v_*` e RPCs). Autocontido: não depende dos módulos de
KPI antigos nem dos loaders Excel.

Comando: `streamlit run app.py`

Após a refatoração (`refactor-kpis`), `app.py` é um **orquestrador fino**
(~1440 linhas): autentica, monta sidebar, carrega dados, aplica RLS,
calcula KPIs e delega render para `src/dashboard/tabs/*`. Toda lógica
pesada vive em `src/dashboard/{loaders,kpis,ui,tabs,pages}/`.

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
    settings.py                ← PRODUTOS_EMISSAO, NOMES_DISPLAY_PRODUTO (taxonomia vem do banco)
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
      theme.py                 ← sistema de temas (CHART_THEME, CSS vars, aplicar_tema)
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
      dashboard_pontuacao.py   ← dashboard de pontuação
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
3. Sidebar monta período (ano/mês) e opções de admin.
4. `consolidar_dados(mes, ano)` (em `loaders.py`) → `df, df_metas, df_sup` pagos.
5. `carregar_contratos_em_analise` / `_cancelados` + filtro 30 dias por `DATA_CADASTRO`.
6. **RLS** imediatamente após o load (ver [rls.md](rls.md)).
7. Cálculos: `calcular_kpis_gerais`, `_analise`, `_cancelados`, `_qtd_produtos`,
   `medias_du_por_nivel`, `metas_produto_diarias`.
8. `pode_ver(chave, role)` (de `permissions.py`) decide quais abas/cards renderizam.
9. `render_tab_*` é despachado conforme o item selecionado em `sac.tabs`.

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
