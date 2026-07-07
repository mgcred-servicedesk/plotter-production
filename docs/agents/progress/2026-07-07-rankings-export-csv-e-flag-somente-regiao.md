# 2026-07-07 — Rankings: export CSV por tabela e flag "Somente dados da regiao"

**Agente:** Claude Code (Fable 5)
**Tipo:** feature
**Arquivos tocados:** `src/dashboard/tabs/rankings.py`,
`src/dashboard/components/tables.py`, `tests/test_ui_tables.py`

## Objetivo

1. Botão de exportar CSV nos rankings, reaproveitando a solução de
   Analíticos (`botao_exportar_csv` de `components/tables.py`).
2. Flag (toggle) que, ligado, restringe **todas** as sub-abas de
   Rankings (Lojas, Consultores, Regioes, Por Produto, Por
   Aceleradores) aos dados da região.

## O que foi feito

- **Export CSV**: `_exibir_ranking`/`_exibir_ranking_pinned` ganharam
  params opcionais `nome`/`key`; `_render_par` ganhou `export_prefix`
  e gera um botão por tabela (padrão Analíticos, escolhido pelo
  usuário). Helper `_slug` normaliza região/produto/acelerador para
  keys e nomes de arquivo. Nomes: `ranking_<contexto>_<sufixo>.csv`
  (ex.: `ranking_lojas_atingimento`, `ranking_produto_loja_fgts`,
  `ranking_regiao_norte_consultores_pontos`).
- **Flag região**: `st.toggle` (`rankings_somente_regiao`) no topo da
  aba; quando ligado, `_filtrar_somente_regiao` filtra o `df`
  org-wide **antes** do dispatch das sub-abas — o recorte propaga
  para todas elas sem tocar cada renderer.
- Com o flag ligado, a seção "Rankings por Regiao" (redundante) é
  ocultada via novo param `com_secao_regiao` em
  `_render_lojas`/`_render_consultores` (escolha do usuário).

## Decisões não óbvias

- **Semântica do flag por perfil** (aprovado pelo usuário):
  admin/gestor têm escopo global, então ligar o flag exibe um
  `selectbox` para escolher a região; demais perfis
  (gerente_comercial/supervisor/consultor) usam a(s) região(ões)
  derivadas do `df_scope` (pós-RLS), **fail-closed** — escopo vazio
  ou sem coluna `REGIAO` ⇒ DataFrame vazio, nunca fallback para
  org-wide.
- **Export × RLS**: os rankings são org-wide (pré-RLS) **por design**
  (comparativo justo — docstring do módulo). O contrato de
  `botao_exportar_csv` exige df já recortado; aqui o CSV espelha
  exatamente o que está renderizado na tela, então não amplia
  exposição. Documentado na docstring de `_exibir_ranking`.
- **Export espelha a tela**: em `_exibir_ranking_pinned` o CSV contém
  Top N + linhas pinadas do escopo (o que o usuário vê), não o
  ranking completo.
- Keys de export colidiriam entre sub-abas apenas se renderizassem
  juntas; como `sac.tabs` renderiza um branch por vez, prefixos
  distintos (`exp_rk_*`, `exp_rk_prod_*`, `exp_rk_acel_*`) bastam.
- **Encoding do CSV (follow-up na mesma sessão)**: o Streamlit
  codifica `str` com `.encode()` (UTF-8 **sem** BOM) e o Excel pt-BR
  sem BOM assume cp1252 — acentos corrompidos justamente no
  consumidor-alvo do helper (`sep=";"`, `decimal=","`). Fix em
  `botao_exportar_csv`: o callable passou a devolver `bytes` em
  `utf-8-sig` (BOM) — vale para todos os botões de export do app.
  Teste `TestBotaoExportarCsv` cobre BOM + round-trip de acentos.

## Premissas

- `REGIAO` presente no `df` org-wide (já era pré-requisito da seção
  por região e da sub-aba Regioes).
- Para perfis regionais, as regiões visíveis no flag vêm dos dados do
  `df_scope` no período filtrado — consultor/supervisor sem venda no
  período não vê nada com o flag ligado (fail-closed aceito).
