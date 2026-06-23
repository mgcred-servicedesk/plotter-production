# 2026-06-23 — Filtro de Gestão (consultores por faixa de valor pago)

**Agente:** Claude Code
**Tipo:** feature
**Arquivos tocados:** `src/dashboard/kpis/gestao.py` (novo), `src/dashboard/tabs/gestao_consultores.py` (novo), `tests/test_gestao_consultores.py` (novo), `app.py`, `src/dashboard/permissions.py`
**Commit(s):** (não commitado no momento do registro)

## Objetivo

Adicionar uma aba **Gestão** que permite à liderança listar consultores
pelo **valor pago** em cada produto do MIX, aplicando um filtro
multi-critério por faixa de valor (combinado por **E**) para apoiar
decisões de gestão de equipe.

## O que foi feito

- **Camada de KPI** (`src/dashboard/kpis/gestao.py`):
  - `PRODUTOS_GESTAO` — mapa produto → `categoria_codigo` derivado de
    `PRODUTOS_DASHBOARD` (MIX global), com duas diferenças: FGTS e
    Ant.Ben. ficam **separados** (não agregados) e o 13º (`CNC_13`) fica
    **de fora** desta visão.
  - `vendas_mix_por_consultor(df, df_sup)` — tabela por consultor com o
    VALOR pago em cada produto + `Total`. Considera apenas `VALOR > 0`,
    exclui supervisores (via `excluir_supervisores`) e mantém `Regiao`/
    `Loja` quando presentes. Espera `df` **já filtrado por RLS** (não faz
    query nem RLS aqui).
  - `filtrar_por_criterios(tabela, criterios)` — filtro por faixa por
    produto, combinado por **E**. Modos: `"menor"` (`valor < max`) e
    `"entre"` (`min <= valor <= max`, inclusivo). Sem critérios → tabela
    inalterada.
- **Aba/UI** (`src/dashboard/tabs/gestao_consultores.py`):
  `render_tab_gestao` com multiselect de produtos (default
  `CLT, CNC, Consignado`), controles por produto (modo + faixas),
  contagem de consultores que atendem, **foco por produto** (exibe só as
  colunas dos produtos selecionados) e exportação CSV (`;`/`,`).
- **Permissões** (`src/dashboard/permissions.py`): nova entrada
  `tab_gestao` na `MATRIZ` — visível para `admin`, `gestor` e
  `gerente_comercial`; oculta para `supervisor` e `consultor`.
- **Integração** (`app.py`): import de `render_tab_gestao`, entrada
  `("tab_gestao", "Gestao", "funnel-fill")` na lista de abas (gating via
  `pode_ver`) e dispatch `render_tab_gestao(df_f, df_sup_f)`.
- **Testes** (`tests/test_gestao_consultores.py`): 11 casos cobrindo
  agregação por produto MIX, soma de bancos em Consignado, exclusão de
  supervisores, ignorar `VALOR=0`, ordenação por região, os modos
  "menor"/"entre", combinação por E, separação FGTS/Ant.Ben. e exclusão
  do 13º. **11 passed**; `ruff check` limpo nos arquivos novos.

## Decisões não óbvias

- **FGTS e Ant.Ben. separados (vs. agregados no MIX global)** — a gestão
  precisa medir cada um isoladamente; por isso `PRODUTOS_GESTAO`
  desmembra o grupo "FGTS/Ant.Ben./13º" do `PRODUTOS_DASHBOARD`. Os
  demais produtos continuam **derivados** de `PRODUTOS_DASHBOARD` para
  não divergir da taxonomia global.
- **13º (`CNC_13`) fora da visão** — decisão de escopo: não entra em
  nenhuma coluna nem no `Total` por enquanto (ver follow-up).
- **RLS aplicado fora da camada de KPI** — `vendas_mix_por_consultor`
  recebe o `df` já filtrado por RLS em `app.py` (`df_f`/`df_sup_f`),
  seguindo a separação de responsabilidades do projeto: o
  `gerente_comercial` vê apenas as próprias regiões sem lógica de RLS
  acoplada à aba.
- **Filtro combinado por E (não OU)** — critérios de produtos distintos
  são interseção: um consultor só aparece se atender a **todos**. Modo
  "menor" usa `<` (exclusivo) e "entre" usa `between` (inclusivo) —
  assimetria intencional para o caso de uso "abaixo de X".
- **Foco por produto na UI** — ao selecionar produtos, a tabela esconde
  as colunas dos demais produtos e o `Total`, reduzindo ruído; sem
  seleção, mostra a visão geral completa.

## Pendências / follow-ups

- [ ] Decidir se o 13º (`CNC_13`) deve ganhar coluna própria nesta visão.
- [ ] Sem teste de UI para `render_tab_gestao` (cobertura só na camada de
  KPI) — alinhar com o padrão do projeto para abas Streamlit.

## Patterns criados ou atualizados

- Nenhum pattern novo. Reaproveita `PRODUTOS_DASHBOARD`/
  `excluir_supervisores` (gerais.py), `exibir_tabela` e o gating por
  `MATRIZ`/`pode_ver`.

## Referências

- Docs consultados: [docs/agents/rls.md](../rls.md),
  [docs/agents/business-rules.md](../business-rules.md),
  [docs/agents/ui-components.md](../ui-components.md)
