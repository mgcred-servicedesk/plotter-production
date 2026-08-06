# 2026-08-06 — Plano: contadores CLT/Consignado em "Emissão e Seguros — Análise Regional"

**Agente:** Claude Code
**Tipo:** feature (planejada, implementada, testada e documentada — ST-01 a ST-04)
**Arquivos tocados:**
- `src/dashboard/tabs/produtos.py` (ST-02 — mask builder estendido, 2 abas novas, total + toggle)
- `tests/test_tabs_produtos.py` (ST-03 — novo, 20 testes)
- `docs/agents/business-rules.md` (ST-04 — seção "CLT e Consignado (Novo/Refin) pagos")
- `docs/agents/progress/2026-08-06-plano-clt-consignado-emissao-seguros.md` (este doc)

**Commit(s):** —

## Objetivo

Na seção "Emissão e Seguros — Análise Regional" (`produtos.py`), acrescentar:
1. Contagem de propostas **CLT pagas**.
2. Contagem de propostas de **Consignado pagas** — apenas subtipos **Novo** e
   **Refin** (excluir Portabilidade e Refin da Portabilidade).
3. Uma flag/filtro que restrinja a contagem de **CLT e Consignado** aos
   bancos **BMG/Help** (excluindo C6 e outros).

Pedido explícito do usuário: registrar como tarefa planejada para evoluir por
etapas — não implementar tudo de uma vez.

## O que foi feito (investigação, via Explore + task-orchestrator)

- Localizada a seção alvo: `src/dashboard/tabs/produtos.py:792-814`
  (`sac.divider` + `st.tabs` sobre `_PRODS_QTD`, linhas 51-99), renderizada
  por `_render_produto_regional` (linha 284). O mask builder atual
  (linhas 336-344) só suporta `tipo_oper` (`.isin()`) OU `subtipo` (match
  único) — **não** suporta `categoria_codigo`, `SUBTIPO.isin([...])`
  (múltiplos valores) nem `BANCO`. Precisa ser estendido, não só receber
  novos itens de config.
- Confirmado em `loaders.py:1600-1618`: o alias `_PORTAB_BANCO_TO_CONSIG`
  (linhas 110-119) sobrescreve **apenas** a coluna `PONTOS` para
  Portabilidade herdar o multiplicador do `CONSIG_<banco>`; o
  `categoria_codigo` da linha continua `"PORTABILIDADE"` sempre. Logo,
  filtrar `categoria_codigo.isin(["CONSIG_BMG","CONSIG_ITAU","CONSIG_C6"]) &
  SUBTIPO.isin(["NOVO","REFIN"])` já exclui automaticamente Portabilidade
  **e** Refin da Portabilidade (que carregam `SUBTIPO="REFIN"` mas
  `categoria_codigo="PORTABILIDADE"`) — não é necessária lógica extra de
  exclusão.
- Confirmado em `schema.sql:385-390`: o dashboard já carrega exclusivamente
  a view `contratos_pagos` (`WHERE status_pagamento_cliente = 'PAGO AO
  CLIENTE'`). Todo contrato no DataFrame já é "pago" por construção — CLT e
  Consignado Novo/Refin seguem essa regra padrão, **sem** precisar da
  exceção `sub_status_banco = 'Liquidada'` usada só para Seguros
  (`docs/agents/business-rules.md:56-70`, que existe porque Seguro/BMG Med
  nunca recebem `status_pagamento_cliente = 'PAGO AO CLIENTE'`).
- `PRODUTOS_DASHBOARD` (`gerais.py:22-27`) já mapeia `CLT →
  ["CONSIG_PRIV"]` e `CONSIGNADO → ["CONSIG_BMG","CONSIG_ITAU","CONSIG_C6"]`.
- Existe uma **segunda config desacoplada** para os cards-resumo
  (`criar_cards_qtd_produto` em `kpi_cards.py:846-867`, alimentada por
  `_PRODUTOS_QTD`/`calcular_kpis_qtd_produtos` em `gerais.py:771-880`, via
  colunas booleanas pré-computadas). É independente de `_PRODS_QTD`
  (produtos.py) — decisão do usuário (abaixo) foi não mexer nela agora.
- Padrão de referência para o toggle de filtro: `_filtrar_detalhamento`
  em `src/dashboard/tabs/analiticos.py:62-109` (cascata com
  `session_state`, reset quando a opção some do recorte).

## Decisões não óbvias

- **BANCO para o filtro BMG/Help = `BANCO.isin(["BMG", "HELP"])`.**
  Confirmado diretamente pelo usuário. Ressalva registrada durante o
  planejamento: `"HELP"` aparece dezenas de vezes no codebase como prefixo
  de **nome de loja** (`HELP BANGU`, `HELP CAMPO GRANDE`, migrations
  050/062) — não confundir a coluna `LOJA`/nome do PDV com a coluna
  `BANCO` ao implementar o filtro. O dado de teste em
  `tests/test_kpis_detalhes_cards.py:673,687` que mostrava `"HELP"` como
  valor de `BANCO` era fixture sintética, mas bateu com a confirmação do
  usuário.
- **Escopo restrito à Análise Regional.** Os novos contadores **não** vão
  para o card-resumo "Emissão e Seguros" (`kpi_cards.py`) nesta etapa — só
  para as abas em `produtos.py`. Motivo: CLT e Consignado já têm cards de
  meta em R$ no resumo; adicionar contagem ali seria escopo extra/possível
  redundância, decisão de produto adiada.
- **Toggle BMG/Help vive dentro das abas CLT e Consignado** (revisado em
  2026-08-06 — inicialmente previsto só para Consignado) e afeta **somente
  o número total** exibido em cada aba — não repropaga para tabelas
  detalhadas de loja/região dentro das mesmas abas (nessa primeira
  versão).
- **Rótulos propostos (não confirmados ainda):** "CLT" e "Consignado
  (Novo/Refin)", consistentes com os rótulos já usados nas abas existentes
  (Super Conta, BMG Med, Vida Familiar). Confirmar ao implementar.

### ST-01 — validação contra dado real (2026-08-06)

Query read-only sobre `v_contratos_dashboard` (base completa de pagos)
confirmou/ajustou premissas:

- **`categoria_codigo` de CLT é derivado, não vem do banco.** As linhas
  `TIPO_PRODUTO='CLT'` só viram `CONSIG_PRIV` via
  `_preencher_categoria_fallback` (`loaders.py:219-273`). O filtro
  `categoria_codigo == "CONSIG_PRIV"` só é válido **no DataFrame do app**,
  nunca em SQL direto.
- **`CONSIG_ITAU` e `CONSIG_C6` têm 0 linhas hoje** — todo consignado
  chega como `CONSIG_BMG` no ETL, independente do banco real. Manter os 3
  no `.isin()` é inofensivo (robusto a mudança futura do ETL); a
  distinção de banco existe só na coluna `BANCO`.
- **`HELP` nunca ocorre como `BANCO` em CLT nem em Consignado.** Valores
  reais de `BANCO` nessas categorias: `BMG`, `C6 BANK`, `ITAU-360`,
  `MASTER`, `VCTEX`. `HELP` (40k+ linhas na base) só aparece em CNC / CNC
  13º / Antecipação de Benefício / CPT — categorias fora do escopo desta
  feature. **Decisão do usuário: manter `BANCO.isin(["BMG","HELP"])`
  mesmo assim** (sem efeito prático hoje, preparado para o caso de um dia
  existir CLT/Consignado via Help) — rótulo do toggle continua "BMG/Help".
- **Normalização necessária.** A base não é uniformemente maiúscula
  (`Portabilidade` × `PORTABILIDADE` convivem em `SUBTIPO`/`TIPO_PRODUTO`
  em outros pontos). Todos os filtros (`SUBTIPO`, `BANCO`) devem aplicar
  `.astype(str).str.strip().str.upper()` antes de comparar — mesmo padrão
  já usado em `loaders.py:1665-1670` (Super Conta) e
  `_PORTAB_BANCO_TO_CONSIG` (`loaders.py:110-119`).
- **93 linhas de CLT têm `TIPO OPER. = 'Seguro Prestamista'`.** Achado
  não previsto no escopo original. **Decisão do usuário: excluir essas
  linhas do contador de CLT pago** — CLT pago passa a ser
  `categoria_codigo == "CONSIG_PRIV" & TIPO OPER. normalizado !=
  "SEGURO PRESTAMISTA"`.
- **Risco anotado, não bloqueante:** `MARGEM COMPLEMENTAR` (~925 linhas,
  ~8% do consignado) fica fora do contador Novo/Refin por não ser nem
  Novo nem Refin — comportamento consistente com o pedido original
  (só Novo+Refin contam), não precisa de decisão adicional.
- **Risco anotado, não bloqueante:** `ITAU-360` (valor real de `BANCO`)
  não está listado em `_PORTAB_BANCO_TO_CONSIG`, que só reconhece
  `ITAU`/`ITAÚ`/variações com espaço — divergência preexistente com
  `business-rules.md:21-26`, sem impacto nesta feature, mas vale um
  follow-up separado.

**Especificação final do filtro** (para a ST-02 implementar):

```python
_norm = lambda s: s.astype(str).str.strip().str.upper()

# CLT pago (exclui Seguro Prestamista)
mask_clt = (
    (df["categoria_codigo"] == "CONSIG_PRIV")
    & (_norm(df["TIPO OPER."]) != "SEGURO PRESTAMISTA")
)

# Consignado pago — só Novo/Refin (exclui Portabilidade automaticamente,
# pois Portabilidade mantém categoria_codigo == "PORTABILIDADE")
mask_consignado = (
    df["categoria_codigo"].isin(["CONSIG_BMG", "CONSIG_ITAU", "CONSIG_C6"])
    & _norm(df["SUBTIPO"]).isin(["NOVO", "REFIN"])
)

# Flag BMG/Help — aplicada via AND sobre qualquer uma das duas acima
mask_banco_bmg_help = _norm(df["BANCO"]).isin(["BMG", "BANCO BMG", "HELP", "BANCO HELP"])
```

Ordem de aplicação: categoria → subtipo/tipo-oper → banco (quando a flag
estiver ativa). Guardar cada acesso de coluna com `if col in df.columns`,
seguindo o padrão já usado em `_render_produto_regional`
(`produtos.py:336-352`).

### ST-02 — implementação de UI (2026-08-06)

Arquivo tocado: `src/dashboard/tabs/produtos.py` (só ele).

- **Mask builder extraído para `_mask_subtab(df, sub)`** (módulo-level,
  junto de `_contar_por_regiao`). Antes era um `if/else` inline dentro de
  `_render_produto_regional` que aceitava `tipo_oper` **ou** `subtipo`.
  Agora combina por **AND** os critérios presentes no dict de subtab:
  `tipo_oper` (isin cru), `subtipo` (== normalizado), `categoria`
  (`categoria_codigo.isin`), `subtipos` (`SUBTIPO.isin` normalizado) e
  `excluir_tipo_oper` (`~TIPO OPER..isin` normalizado). `_norm`,
  `_mask_falsa` e `_mask_banco` são helpers novos do mesmo módulo.
- **`tipo_oper` continua sem normalização** — de propósito. Os rótulos de
  `_PRODS_QTD` ("CARTÃO BENEFICIO", "Venda Pré-Adesão", "BMG MED",
  "Seguro") batem 1:1 com o dado; normalizar mudaria a contagem das 4
  abas antigas (ex.: "Seguro" passaria a casar com "SEGURO PRESTAMISTA"
  se alguém trocasse `==` por comparação normalizada frouxa).
- **Coluna ausente zera a contagem**, inclusive para `excluir_tipo_oper`:
  sem `TIPO OPER.` não dá para provar a exclusão do Seguro Prestamista, e
  total silenciosamente inflado é pior que zero. Mantém o comportamento
  defensivo que já existia.
- **Coluna "Análise" virou opcional.** Aba que não declara `col_dig_tipo`
  nem `col_dig_subtipo` (as duas novas) recebe `df_dig` só com as chaves
  de merge — o `col_exib` já filtrava por coluna existente, então a
  coluna some sozinha. Decisão: CLT/Consignado **não** ganham contagem de
  digitados nesta versão (não estava na especificação); se fizer sentido
  depois, é só acrescentar a chave na config.
- **Total + toggle**: `_render_total_produto` desenha
  `st.columns([1, 2])` com `st.metric("Propostas pagas", …, help=…)` à
  esquerda e o `st.toggle("Somente BMG/Help", key=…)` à direita. O widget
  é instanciado **antes** do `st.metric` (a coluna é container: ordem de
  execução não muda o layout) porque o valor da flag entra na conta. Só
  renderiza para cfg que declara `total_label` — as 4 abas antigas ficam
  visualmente idênticas.
- **Chaves de `session_state`**: `prod_qtd_clt_bmg_help` e
  `prod_qtd_consig_bmg_help` (uma por aba, independentes). Não há cascata
  a resetar — o toggle é binário e suas opções nunca somem do recorte,
  ao contrário do selectbox de `_filtrar_detalhamento`.
- **Divergência assumida (registrada, não é bug):** o total conta sobre
  `df_p` (frame já sem supervisores) **sem** depender de `REGIAO`/`LOJA`
  preenchidos; as tabelas usam `groupby(["REGIAO","LOJA"])`, que descarta
  linha sem região. Com linha órfã, o total do topo fica ≥ soma dos
  totais das tabelas.
- **Rótulos confirmados na implementação:** abas "CLT" e "Consignado
  (Novo/Refin)"; KPI "Propostas pagas" (a aba já nomeia o produto);
  toggle "Somente BMG/Help".

Validação (a suíte formal é a ST-03):

- Script de não-regressão comparando `_mask_subtab` contra uma cópia do
  builder antigo, para as 4 abas antigas × 4 frames (completo, sem
  `TIPO OPER.`, sem `SUBTIPO`, vazio): máscaras **idênticas**.
- Máscaras novas sobre fixture sintética: CLT ignora as duas grafias de
  Seguro Prestamista; Consignado pega NOVO/`"refin "` e descarta
  `PORTABILIDADE` (categoria) e `MARGEM COMPLEMENTAR`; flag BMG/Help
  mantém `"Help"`/`"bmg "` e corta `C6 BANK`.
- Render headless (`streamlit.testing.v1.AppTest`) das 6 abas em perfil
  regional e `gerente_comercial`, incluindo os cenários de frame vazio e
  de produto sem nenhuma linha: sem exceção, toggle altera só o KPI
  (Consignado 3 → 2), tabelas inalteradas.
- `.venv/bin/ruff check src/ app.py` limpo; `pytest tests/` 436 passed.

### ST-03 — testes formais (2026-08-06)

Arquivo criado: `tests/test_tabs_produtos.py` (novo — não havia testes
para `src/dashboard/tabs/produtos.py`; `tests/test_kpis_produtos.py` já
existente testa um módulo diferente, `src/dashboard/kpis/produtos.py`).

- 20 testes, 4 classes (`TestNorm`, `TestMaskFalsa`, `TestMaskSubtab`,
  `TestMaskBanco`), marker `unit`, seguindo a convenção de
  `tests/test_tabs_analiticos.py` (precedente mais próximo: também testa
  helper puro de um módulo `tabs/*.py`).
- Testado diretamente via import (`_norm`, `_mask_falsa`, `_mask_subtab`,
  `_mask_banco`, `_BANCOS_BMG_HELP`, `_PRODS_QTD`) — sem
  `AppTest`/Streamlit, a lógica é pandas puro.
- **Não-regressão das 4 abas antigas**: em vez de dicts sintéticos, os
  testes buscam a config real de `_PRODS_QTD` por rótulo
  (`_cfg("Emissão")["subtabs"][0]`, etc.) e usam o valor exato de
  `tipo_oper`/`subtipo` do config para montar o DataFrame — mais robusto
  a mudança de rótulo do que hardcodar a string acentuada duas vezes.
  Confirma que `tipo_oper` continua **sem** normalização (case-sensitive)
  e que `subtipo` continua normalizado.
- **Caso mais importante coberto**:
  `test_consignado_exclui_portabilidade_mesmo_com_subtipo_novo_refin` —
  linha com `categoria_codigo="PORTABILIDADE"` e `SUBTIPO` em
  `["NOVO","REFIN"]` não conta, provando que o filtro por
  `categoria_codigo` já exclui Portabilidade/Refin-da-Portabilidade sem
  lógica extra.
- **Defensivo**: testado que a ausência de `TIPO OPER.` não quebra
  `_mask_subtab` com `excluir_tipo_oper` (usando a config real de CLT) e,
  isoladamente, que cada um dos outros 4 critérios (`tipo_oper`,
  `subtipo`, `categoria`, `subtipos`) zera sozinho quando a coluna
  correspondente falta.
- `.venv/bin/python -m pytest tests/` → **456 passed** (20 novos + 436
  pré-existentes), 1 warning pré-existente e não relacionado
  (`test_ui_tables.py::TestFormatacaoDatas::test_codigo_parecido_com_data_nao_e_convertido`).
  `.venv/bin/ruff check tests/test_tabs_produtos.py` → limpo.

## Pendências / follow-ups

- [x] **ST-01 (business-rules-kpi-expert):** regra formalizada e validada
      contra dado real — ver especificação final acima.
- [x] **ST-02 (streamlit-ui-specialist):** feito — ver seção acima.
      Escopo original: estender o mask builder de
      `_render_produto_regional` (`produtos.py:284-360`) para suportar
      `categoria_codigo` + `SUBTIPO.isin([...])` + `BANCO.isin([...])`
      opcional; adicionar as 2 novas abas a `_PRODS_QTD`; implementar o
      toggle BMG/Help (padrão `_filtrar_detalhamento`,
      `analiticos.py:62-109`) em **ambas** as abas (CLT e Consignado),
      afetando só o total exibido em cada uma.
- [x] **ST-03 (test-automation-specialist):** feito — ver seção acima.
      `tests/test_tabs_produtos.py` cobre exclusão automática de
      Portabilidade/Refin-Portabilidade, contagem correta de CLT
      (incluindo exclusão de `TIPO OPER.='Seguro Prestamista'`), o filtro
      BMG/Help e não-regressão do mask builder estendido.
- [x] **ST-04 (business-rules-kpi-expert):** feito — seção "CLT e
      Consignado (Novo/Refin) pagos" em `docs/agents/business-rules.md`
      (entre "Super Conta" e "PACK"), cobrindo os dois filtros, a
      normalização, a exclusão automática de Portabilidade (linkando a
      seção "Portabilidade — alias por banco" em vez de duplicar), a flag
      BMG/Help, onde está implementado e os follow-ups conhecidos.
- [x] Rótulos das abas confirmados na ST-02: "CLT" e "Consignado
      (Novo/Refin)".

**Follow-ups que continuam em aberto** (fora do escopo desta feature):

- [ ] Avaliar se CLT/Consignado devem ganhar coluna "Análise"
      (digitados) — ficaram sem, por não estar na especificação. Basta
      acrescentar `col_dig_tipo`/`col_dig_subtipo` na config de
      `_PRODS_QTD` se fizer sentido.
- [ ] Reavaliar depois se os cards-resumo (`kpi_cards.py` /
      `calcular_kpis_qtd_produtos`, config desacoplada) também devem
      ganhar os novos contadores (adiado nesta rodada).
- [ ] **Divergência preexistente `ITAU-360`:** valor real de `BANCO` que
      não está em `_PORTAB_BANCO_TO_CONSIG` (que só reconhece
      `ITAU`/`ITAÚ`/variações com espaço) → portabilidade desse banco
      pontuaria 0. Não é desta feature; exige decisão sobre
      `business-rules.md:21-26` (tabela do alias) vs. o dado real.

## Referências

- Conversa: pedido do usuário em 2026-08-06 para acrescentar contadores de
  CLT/Consignado pagos na Análise Regional, com flag BMG/Help.
- Docs consultados: [business-rules.md](../business-rules.md),
  [data-layer.md](../data-layer.md).
