# 2026-08-13 — Distribuição de Produtos: contadores CLT/Consignado + toggle BMG/Help

**Agente:** Claude Code (orquestrado: `biz-rules` + `ui-dash` + `testing`)
**Tipo:** feature
**Arquivos tocados:** `src/dashboard/kpis/produtos.py`, `src/dashboard/tabs/analiticos.py`, `tests/test_kpis_produtos.py`, `docs/agents/business-rules.md`
**Commit(s):** (pendente)

## Objetivo

Acrescentar à tabela "Distribuição de Produtos" (Analíticos) duas colunas de
quantidade — CLT e Consignado (Novo/Refin) —, reusando o critério já
canônico dos contadores de "Emissão e Seguros — Análise Regional", e um
toggle "Somente BMG/Help" que restringe a **tabela inteira** (valor +
quantidade + TOTAL) aos bancos BMG/Help — escopo mais amplo que o toggle
homônimo da Análise Regional (que só afeta a aba onde está ligado).

## O que foi feito

- `_mascaras_aceleradores(df)` (`kpis/produtos.py`): 4-tuple → 6-tuple,
  acrescentando `mask_clt` e `mask_consig`:
  - **CLT** — `categoria_codigo == "CONSIG_PRIV"` **e** `TIPO OPER.` ≠
    `SEGURO PRESTAMISTA` (normalizado).
  - **Consignado** — `categoria_codigo ∈ {CONSIG_BMG, CONSIG_ITAU,
    CONSIG_C6}` **e** `SUBTIPO ∈ {NOVO, REFIN}` (normalizado; exclui
    Portabilidade/Margem Complementar automaticamente).
  - Coluna necessária ausente ⇒ máscara toda-False, mesmo padrão
    defensivo das outras 4 máscaras.
- Nova constante `_BANCOS_BMG_HELP` + helper `_mask_banco_bmg_help(df)`.
- `calcular_distribuicao_produtos` e `calcular_distribuicao_produtos_por_loja`
  ganharam `somente_bmg_help: bool = False`: recorta `df` no topo, logo
  após o guard clause, antes de qualquer máscara — pivot de valor, as 6
  máscaras, TOTAL e merges de LOJA/REGIAO herdam o filtro sem branch extra.
- `analiticos.py`: `st.toggle("Somente BMG/Help", key="dist_prod_bmg_help")`
  em `_render_distribuicao_produtos`, repassado aos 3 call sites
  (`supervisor`, `ver_consultor`, visão por loja).
- `tests/test_kpis_produtos.py`: 9 testes novos (24 no total) — CLT/
  Consignado com normalização e exclusões automáticas, toggle recortando
  valor+quantidade+TOTAL juntos, `BANCO` ausente zerando a tabela, e
  regressão da colisão de nome `CLT`/`CLT (Qtd)` (por consultor e por
  loja).
- `business-rules.md`: subseção "Reuso em 'Distribuição de Produtos'"
  com tabela comparando o alcance dos dois toggles homônimos.

## Decisões não óbvias

- **Coluna de quantidade chama-se `CLT (Qtd)`, não `CLT`.** `CONSIG_PRIV`
  tem `grupo_dashboard = 'CLT'` (`database/schema.sql:1242`), então o
  pivot de valor já emite uma coluna `CLT`. Nome repetido faria
  `pv_val.merge(pv_qtd)` gerar `CLT_x`/`CLT_y`, e os filtros `[c for c in
  ... if c in distrib.columns]` derrubariam **as duas** — R$ de CLT
  sumiria do TOTAL sem erro nenhum (reproduzido antes do fix). `CONSIGNADO`
  (valor) × `Consignado (Novo/Refin)` (qtd) não colidem, só CLT levou
  sufixo. Coberto por teste de regressão dedicado nas duas funções.
- **`mask_cred` (pivot de valor) não mudou** — CLT/Consignado já apareciam
  nas colunas de valor via `grupo_dashboard`; as colunas novas são só
  quantidade somada por cima, mesmo tratamento que Super Conta já recebe
  (conta em valor **e** em quantidade). Excluir de `mask_cred` teria
  removido receita real do TOTAL.
- **Filtro de banco no topo da função, não por coluna** — decisão
  explícita do usuário: o toggle aqui afeta **todos** os produtos (CNC,
  FGTS, Saque, aceleradores...), não só CLT/Consignado, diferente do
  toggle da Análise Regional (que só existe dentro das abas CLT/
  Consignado). `BANCO` ausente + flag ligada zera a tabela inteira, mesma
  regra de "critério sem coluna zera a contagem".
- **`_BANCOS_BMG_HELP` duplicada, não importada** de
  `tabs/produtos.py:54` — importar da UI para a camada de KPI inverteria
  a direção de dependência entre camadas. Se a lista mudar, mudar nos
  dois lugares (comentário cruzado em ambos os arquivos).
- **Assimetria valor × quantidade é esperada, não bug**: no R$ da coluna
  `CLT` entra `Seguro Prestamista`, na `CLT (Qtd)` não; no R$ de
  `CONSIGNADO` entra `MARGEM COMPLEMENTAR`, na quantidade não.
- **`BANCO` ausente + flag ligada confirmado empiricamente** (não
  assumido): resultado é `DataFrame` vazio com só a coluna `TOTAL`
  (`colunas_moeda == ["TOTAL"]`, `colunas_numero == []`).

## Pendências / follow-ups

- Se a lista de bancos BMG/Help mudar, sincronizar as duas cópias de
  `_BANCOS_BMG_HELP` (`kpis/produtos.py` e `tabs/produtos.py`).
- Rótulo `CLT (Qtd)` é literal em código + testes + docs — mudança de
  rótulo no futuro exige atualizar os três.

## Patterns criados ou atualizados

Nenhum — reaproveitado o padrão já documentado em
`.claude/agent-memory/test-automation-specialist/pattern_verify_composed_against_direct_calc.md`
(comparar `True` vs. `False` do toggle no mesmo `df`).

## Referências

- Docs consultados: [business-rules.md](../business-rules.md) §§ "CLT e
  Consignado (Novo/Refin) pagos", "Flag Somente BMG/Help", "Super Conta"
- Spec original do filtro de banco:
  [progress/2026-08-06](2026-08-06-plano-clt-consignado-emissao-seguros.md)
- Mudança anterior nesta mesma tabela:
  [progress/2026-08-12](2026-08-12-distribuicao-produtos-por-loja.md)
- Schema: `database/schema.sql:1230-1245` (`grupo_dashboard` de
  `CONSIG_PRIV` = `CLT`; `CONSIG_{BMG,ITAU,C6}` = `CONSIGNADO`)
