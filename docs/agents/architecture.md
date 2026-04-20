# Arquitetura

## Entrypoint

**`app.py`** (root) é o **único** entrypoint autoritativo. Consome Supabase
diretamente (views `v_*` e RPCs). Autocontido: não depende dos módulos de
KPI antigos nem dos loaders Excel.

Comando: `streamlit run app.py`

### Arquivos legados (não usar / não modificar)

- `dashboard.py`
- `dashboard_refatorado.py`
- `dashboard_supabase.py`
- `src/dashboard/app.py` (entry antigo; mantido por histórico)

Todos têm deprecation notice no topo. Features novas **vão para `app.py`** na raiz.

## Árvore

```
app.py                         ← ★ main entry point
src/
  config/
    supabase_client.py         ← get_supabase_client()
    settings.py                ← MESES_PT, LISTA_PRODUTOS, constantes
  shared/
    dias_uteis.py              ← calcular_dias_uteis() + carregar_feriados()
  dashboard/
    auth.py                    ← tela_login, usuario_logado, fazer_logout, PERFIS
    rls.py                     ← aplicar_rls, aplicar_rls_metas, aplicar_rls_supervisores
    user_mgmt.py               ← render_pagina_usuarios()
    feriados_mgmt.py           ← render_pagina_feriados()
    components/
      tables.py                ← exibir_tabela()
  data_processing/             ← legado (pipeline Excel; usado só por relatórios)
  reports/                     ← geradores Excel e PDF
database/
  migrations/                  ← 001_views_dashboard.sql → 005_tabela_feriados.sql
  schema.sql
assets/
  dashboard_style.css          ← design system + tema CSS custom properties
  logotipo-mg-cred.png
configuracao/                  ← planilhas auxiliares (HC, lojas, supervisores)
outputs/                       ← relatorios_excel/, relatorios_pdf/
```

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
