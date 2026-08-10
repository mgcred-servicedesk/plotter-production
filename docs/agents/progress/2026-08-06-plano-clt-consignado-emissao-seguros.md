# 2026-08-06 — Plano: contadores CLT/Consignado em "Emissão e Seguros — Análise Regional"

**Agente:** Claude Code
**Tipo:** feature (planejada, implementada, testada e documentada — ST-01 a
ST-04; correção de alcance da flag BMG/Help — ST-05 a ST-08; extensão do
contador de total às 4 abas restantes — ST-09; produção de supervisor
volta a contar, marcada — ST-10)
**Arquivos tocados:**
- `src/dashboard/tabs/produtos.py` (ST-02 — mask builder estendido, 2 abas
  novas, total + toggle; ST-06 — `_render_total_produto` devolve a máscara
  de banco e `_render_produto_regional` a reaplica nas tabelas; ST-09 —
  `total_label`/`total_help` em Emissão/Super Conta/BMG Med/Vida Familiar,
  sem `toggle_banco`; ST-10 — `_mask_supervisor` nova, total e tabelas
  passam a contar sobre `df` completo com marcação de supervisor)
- `tests/test_tabs_produtos.py` (ST-03 — novo, 20 testes; ST-07 — +7 testes
  da propagação da flag para as tabelas, 2 classes novas; ST-09 — 1 teste
  corrigido + 3 novos, classe `TestRenderProdutoRegionalTotalSemToggle`;
  ST-10 — +11 testes, classes `TestMaskSupervisor` e
  `TestRenderProdutoRegionalProducaoSupervisor`)
- `docs/agents/business-rules.md` (ST-04 — seção "CLT e Consignado
  (Novo/Refin) pagos"; ST-08 — subseção "Flag Somente BMG/Help" corrigida
  para alcance total + tabelas; ST-09 — subseção "Contadores dos demais
  produtos" + correção de citação de view incorreta; ST-10 — subseção
  "Produção de supervisor" + nota de exceção em "Exclusão de
  supervisores")
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
- [x] **ST-05 (business-rules-kpi-expert):** feito — investigação do bug
      "`gerente_comercial` não consegue filtrar produção". RLS e dado
      descartados; causa = alcance da flag (só o total). Decisão do
      usuário: propagar para as tabelas.
- [x] **ST-06 (streamlit-ui-specialist):** feito — ver seção acima.
      `_render_total_produto` devolve a máscara de banco;
      `_render_produto_regional` a reaplica por AND no mask de cada
      subtab, valendo para as duas visões (região/loja e loja/consultor).
      **Supera** a decisão da ST-02 ("flag afeta somente o total").
- [x] **ST-07 (test-automation-specialist):** feito — ver seção acima.
      +7 testes em `tests/test_tabs_produtos.py` (composição de máscaras
      + `AppTest` com o toggle ligado), validados contra o `produtos.py`
      pré-ST-06 para provar que pegam o bug. `pytest tests/` → 463 passed.
- [x] **ST-08 (business-rules-kpi-expert):** feito — ver seção abaixo.
      Subseção "Flag Somente BMG/Help" em `docs/agents/business-rules.md`
      corrigida para o alcance atual (total **+** tabelas, todos os
      perfis) e este doc fechado.

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

### ST-05 — bug reportado: gerente_comercial "não consegue filtrar produção" (2026-08-06)

Usuário relatou que, ao marcar "Somente BMG/Help", `gerente_comercial` não
consegue filtrar a produção. Investigado com dado real
(`v_contratos_dashboard`) antes de mexer em código:

- **RLS e dado descartados como causa.** `aplicar_rls` (`rls.py:38-93`)
  só filtra linhas, nunca colunas — `BANCO` sempre chega intacta para
  todos os perfis. Nenhuma linha de CLT/Consignado tem `REGIAO_ATUAL`
  nula (0 órfãs de `loja_regiao_vigencia`) nem `BANCO` nula. Simulação
  ponta a ponta do KPI para os 4 `gerente_comercial` ativos
  (jacqueline/robson/sandra/glenda, cada um com escopo = sua região, que
  batem exatamente com as 4 regiões que têm produção BMG) mostrou o
  toggle sempre cortando ~10-20% da produção — **nunca zerando**.
- **Causa real: escopo da flag, não bug.** O toggle (`_render_total_produto`,
  ST-02) só filtra o KPI do topo, nunca as tabelas por região/loja/consultor
  abaixo — decisão explícita tomada durante o planejamento original desta
  feature. `gerente_comercial` é o único perfil cuja visão principal **é**
  a tabela por loja/consultor (`visao_por_loja`, `produtos.py:490`), não o
  KPI agregado — então, do ponto de vista dele, marcar a flag não muda
  nada no que ele realmente olha.
- **Decisão do usuário:** propagar a flag também para as tabelas
  (região/loja/consultor), em todos os perfis — não só para
  `gerente_comercial`. Vira ST-06 (implementação) + ST-07 (testes) +
  ST-08 (docs).

### ST-06 — flag BMG/Help passa a filtrar também as tabelas (2026-08-10)

Arquivo tocado: `src/dashboard/tabs/produtos.py` (só ele). Implementa a
decisão da ST-05. **Supera a decisão registrada na ST-02** ("a flag afeta
somente o número total, não repropaga para tabelas") — aquela entrada
continua válida como histórico, não como comportamento atual.

- **`_render_total_produto` passou de `-> None` para
  `-> Optional[pd.Series]`**: devolve a **máscara de banco já aplicada
  ao total** (alinhada ao índice do frame recebido) ou `None` quando não
  há filtro ativo — flag desligada **ou** aba sem `toggle_banco`.
  Alternativa descartada: devolver `(somente_banco: bool, cfg_banco:
  dict | None)`. O `cfg_banco` seria redundante (o chamador já tem
  `cfg`) e obrigaria a repetir no chamador a condicional
  `if somente_banco and cfg_banco: ... _mask_banco(...)` que já existe
  dentro da função — duas cópias da mesma regra, e `_mask_banco`
  calculado duas vezes. Com a máscara pronta o chamador só faz
  `if mask_banco is not None`.
- **Acoplamento assumido:** a máscara retornada só vale sobre o **mesmo
  frame** passado a `_render_total_produto`. Hoje é sempre `df_p` nos
  dois call sites (total e loop de subtabs), e está dito na docstring.
- **O AND entra antes do `if visao_por_loja`**, no `mask` de cada
  subtab — então vale igual para `_contar_por_regiao` (Admin/Gestor) e
  `_contar_por_loja_consultor` (`gerente_comercial`), sem branch novo.
- **4 abas antigas intactas por construção**: não declaram `total_label`,
  logo `_render_total_produto` nem é chamada e `mask_banco` fica `None`.
- **Textos atualizados** (ficaram mentirosos com a mudança): comentário
  de config de `toggle_banco` no topo do arquivo, docstring de
  `_render_total_produto` e o `help` dos **dois** toggles (era
  "Restringe apenas o total acima… As tabelas por região/loja continuam
  com todos os bancos", virou "Restringe o total acima e as tabelas
  desta aba aos bancos BMG e Help").
- **Efeito colateral esperado, não é bug:** na visão por região
  (Admin/Gestor) não há esqueleto de linhas — região/loja que fica sem
  nenhuma linha após o filtro **some da tela** (com fixture: região R2
  desaparece). Na visão `gerente_comercial` o esqueleto de consultores
  preserva as linhas zeradas. Assimetria preexistente do render, só fica
  mais visível agora.
- **Coluna `BANCO` ausente + flag ligada zera a aba inteira** (KPI e
  tabelas), coerente com o "critério sem coluna zera a contagem" já
  adotado em `_mask_subtab`. Antes zerava só o KPI. Sem exceção nos dois
  perfis.

Validação (a suíte formal é a ST-07):

- Headless `streamlit.testing.v1.AppTest` chamando
  `_render_produto_regional` direto, com frame sintético (sem Supabase)
  e perfil injetado em `st.session_state["usuario_logado"]`, diffando o
  inventário de widgets **contra o baseline extraído de
  `git show HEAD:…/produtos.py`**. Matriz 6 abas × 2 perfis
  (`admin`, `gerente_comercial`) × toggle on/off:
  1. 4 abas antigas: inventário **idêntico** ao baseline nos 2 perfis.
  2. Abas novas com toggle **off**: única diferença vs. baseline é o
     texto do `help` do toggle.
  3. Abas novas com toggle **on**: tabelas mudam (era o bug).
  4. Mesma matriz no baseline: tabelas **não** mudavam — confirma que o
     cenário reproduzia o bug antes do fix.
- Conferência numérica: KPI passa a bater com a soma das tabelas nos dois
  perfis (CLT 3→2 e Consignado 3→1 ao ligar a flag, em KPI **e** tabelas).
- Bordas sem exceção: frame vazio, `BANCO` ausente e os dois combinados,
  nos 2 perfis, nas abas nova e antiga.
- `.venv/bin/ruff check src/ app.py` limpo; `pytest tests/` **456 passed**
  (mesma contagem da ST-03 — os 20 testes de `_mask_subtab`/`_mask_banco`
  não foram tocados, a mudança é em como o chamador os combina).

Status das subtarefas derivadas da ST-05: ST-06 (esta) feita; **ST-07
(testes formais) e ST-08 (docs/business-rules) seguem em aberto** —
`business-rules.md` ainda descreve a flag como restrita ao total.

### ST-07 — testes formais da propagação da flag para as tabelas (2026-08-10)

Arquivo tocado: `tests/test_tabs_produtos.py` (extensão — os 20 testes da
ST-03 continuam intactos e passando).

- **Confirmado no início da ST-07: a mudança da ST-06 ainda não estava
  commitada** (`git status` mostrava `produtos.py` modificado, "Commit(s):
  —" no cabeçalho deste doc). Os testes novos foram escritos e validados
  contra o working tree, não contra HEAD.
- **7 testes novos, 2 classes:**
  - `TestComposicaoMaskSubtabBanco` (2 testes, pandas puro, sem
    Streamlit): prova que `_mask_subtab(df, sub) & _mask_banco(df,
    bancos)` — a composição que `_render_produto_regional` agora aplica
    — produz o mesmo total que `_contar_por_regiao`/
    `_contar_por_loja_consultor` enxergam ao receber essa máscara
    composta, para CLT e Consignado.
  - `TestRenderProdutoRegionalFiltroBanco` (5 testes, via
    `streamlit.testing.v1.AppTest`): chama `_render_produto_regional`
    de verdade (não só as funções de máscara), com o toggle
    efetivamente ligado via pré-set de `session_state` antes do
    primeiro `.run()` — fora de um script run real, `st.toggle` sempre
    volta ao padrão `False`, então só dá para provar "flag ligada" com
    `AppTest`. Cobre: toggle desligado (baseline, ambos os bancos
    contam), toggle ligado excluindo C6 BANK do KPI **e** da tabela por
    região (perfil `admin`) **e** da tabela por loja/consultor (perfil
    `gerente_comercial` — o cenário literal do bug da ST-05), coluna
    `BANCO` ausente com flag ligada zerando o KPI **e** as tabelas
    (comportamento novo da ST-06, antes zerava só o KPI), e uma aba
    antiga sem `toggle_banco` (Super Conta) renderizando sem widget de
    toggle/metric e sem regressão de contagem.
  - **Alternativa descartada:** cobrir só a composição pura (o que o
    handoff chamava de "preferencial") e pular o `AppTest`. Descartada
    porque não protege contra o tipo exato de regressão que causou o
    bug: uma composição de máscaras correta em isolamento não prova que
    `_render_produto_regional` de fato a aplica antes de alimentar
    `_contar_por_regiao`/`_contar_por_loja_consultor` — que é
    exatamente onde o bug morava (o valor certo existia, só não estava
    sendo usado no lugar certo). Confirmado empiricamente abaixo.
- **Validação de que os testes pegam o bug de verdade:** `git stash push
  --keep-index -m … -- src/dashboard/tabs/produtos.py` (stash cirúrgico
  só desse arquivo, sem tocar nos outros arquivos modificados no working
  tree) para rodar a suíte nova contra o `produtos.py` de HEAD (pré-ST-06,
  `_render_total_produto` retornando `None`). Resultado: os 3 testes de
  "toggle ligado" de `TestRenderProdutoRegionalFiltroBanco` **falham**
  (tabela não muda / não zera, exatamente o bug relatado); o teste de
  "toggle desligado" e o de aba antiga continuam passando (comportamento
  não mudou nesses casos); os 2 testes de `TestComposicaoMaskSubtabBanco`
  também continuam passando nos dois — como esperado, eles testam a
  composição em si, não a fiação, então não distinguem as duas versões.
  `git stash pop` restaurou o working tree em seguida.
- **Padrão novo no arquivo (não pré-existente em `tests/`):** uso de
  `streamlit.testing.v1.AppTest` dentro de um teste formal do pytest.
  Já havia precedente de `AppTest` no projeto, mas só como script ad hoc
  de validação de refactor em `scratchpad/` (ver
  `docs/agents/patterns/validar-refactor-de-ui-com-apptest.md`), nunca
  commitado em `tests/`. Aqui o uso é diferente: não é diff baseline ×
  atual, é asserção direta de regra de negócio (KPI e tabela têm que
  bater). Técnica: `AppTest.from_function` com uma função top-level
  parametrizada (`_script_render_produto_regional(cfg_label,
  perfil_role, df, df_analise, df_sup, du_total, du_dec)`) — o corpo
  importa tudo que precisa e é chamado via `args`/`kwargs`, então o
  mesmo script serve para todos os cenários sem duplicar código-fonte
  por teste. Sinalizando aqui por ser padrão novo no arquivo, conforme
  `CLAUDE.md`.
- `.venv/bin/ruff check tests/test_tabs_produtos.py` → limpo.
  `.venv/bin/python -m pytest tests/` → **463 passed** (456 pré-existentes
  + 7 novos), mesmo warning pré-existente da ST-03.

**ST-08 (docs/business-rules) segue em aberto** — `business-rules.md`
ainda descreve a flag como restrita ao total; fora do escopo desta
subtarefa (domínio de `business-rules-kpi-expert`, não de testes).

### ST-08 — documentação alinhada ao alcance atual da flag (2026-08-10)

Arquivos tocados: `docs/agents/business-rules.md` e este doc. **Nenhuma
mudança em `src/` ou `tests/`.** Fecha a série ST-05 → ST-08.

> As linhas "ST-07/ST-08 seguem em aberto" nas seções ST-06 e ST-07 acima
> são histórico (doc append-only) — o checklist de pendências é a fonte
> de status atual, e lá as três estão marcadas.

Em `business-rules.md`, seção "CLT e Consignado (Novo/Refin) pagos":

- **Subseção "Flag Somente BMG/Help"**: linha `Alcance` da tabela
  filtro × alcance passou de "só o total exibido no topo da aba —
  tabelas por região/loja seguem com todos os bancos" para "a aba
  inteira — total **e** tabelas, em todos os perfis (região/loja para
  Admin/Gestor, loja/consultor para `gerente_comercial`)". Acrescentada
  linha `Escopo` deixando explícito que o toggle é por aba (chave de
  sessão própria) e não vaza para a outra aba nem para o resto do
  dashboard — antes isso só estava implícito.
- **Consequências do recorte único documentadas**: total passa a bater
  com a soma das tabelas (salvo linha órfã sem `REGIAO`/`LOJA`);
  assimetria de esqueleto entre as duas visões (região/loja sem linha
  **some** da tela; consultores zerados **permanecem**); `BANCO` ausente
  com flag ligada zera a aba inteira, não só o KPI.
- **Bloco de histórico em citação** registrando que até 2026-08-10 a flag
  restringia só o total, o sintoma relatado ("`gerente_comercial` não
  consegue filtrar produção") e a causa — alcance, não RLS nem dado
  (`BANCO` nunca nula, nenhuma região órfã, corte de ~10-20% que nunca
  zera). Motivo de manter na doc canônica e não só aqui: é a pergunta
  que volta ("a flag não funciona para o gerente"), e a resposta é uma
  regra de alcance, não um bug.
- **"Onde está implementado"** ganhou o mecanismo: `_render_total_produto`
  devolve a máscara de banco já aplicada ao total e
  `_render_produto_regional` a reaplica por AND em `_mask_subtab` antes
  de `_contar_por_regiao` / `_contar_por_loja_consultor` — um recorte só,
  sem branch por perfil; a máscara vale apenas sobre o mesmo frame
  (`df_p`).
- **Follow-up da coluna "Análise" qualificado**: se CLT/Consignado
  ganharem a coluna de digitados, a flag precisará ser estendida ao frame
  `df_a` — hoje ele não recebe a máscara de banco (verificado no código:
  `mask_dig` é montada sem `mask_banco`). Sem impacto atual porque as
  duas abas não declaram `col_dig_tipo`/`col_dig_subtipo`.

Verificação: comportamento relido no código antes de escrever
(`produtos.py` — config de `toggle_banco`, `_render_total_produto`,
composição em `_render_produto_regional`), não a partir do texto das
ST-05/ST-06. `.venv/bin/ruff check src/ app.py` limpo (confirmando que
nada em código foi tocado nesta subtarefa).

### ST-09 — total_label estendido a Emissão/Super Conta/BMG Med/Vida Familiar (2026-08-10)

Pedido do usuário: os contadores "Propostas pagas" do ST-02/ST-06 (CLT,
Consignado) criaram um card que as outras 4 abas de "Emissão e Seguros —
Análise Regional" não tinham. Pediu para estender o mesmo card às 4,
**sem** a flag "Somente BMG/Help" — essa continua exclusiva de
CLT/Consignado.

- **`produtos.py`**: as 4 configs (`_PRODS_QTD`) ganharam `total_label`
  ("Propostas pagas") e `total_help`, no mesmo padrão de CLT/Consignado.
  **Nenhum código novo** — `_render_total_produto`/`_render_produto_regional`
  já eram genéricos (`if cfg.get("total_label"):` já existia desde o
  ST-06; `toggle_banco` ausente na config já significava "sem flag" antes
  desta mudança, só nunca tinha sido exercitado por nenhuma aba real). Só
  dado de configuração mudou.
- **Critério de cada contador** (documentado em `business-rules.md`,
  subseção nova "Contadores dos demais produtos"):
  - Emissão: `TIPO OPER. ∈ {CARTÃO BENEFICIO, Venda Pré-Adesão}` — soma
    as 2 subtabs (`_render_total_produto` faz OR entre todas as
    `subtabs` do cfg, não só a primeira).
  - Super Conta: `SUBTIPO = SUPER CONTA`.
  - BMG Med: `TIPO OPER. = BMG MED`.
  - Vida Familiar: `TIPO OPER. = Seguro`.
- **Verificado antes de implementar (via `business-rules-kpi-expert`)**:
  BMG Med e Vida Familiar não recebem `status_pagamento_cliente = 'PAGO
  AO CLIENTE'` — entram no frame do dashboard pela exceção
  `sub_status_banco = 'Liquidada'` (`v_contratos_dashboard`, ver
  `database/schema.sql:704-708`). Confirmado que isso **não** exige
  filtro extra no contador: toda linha do frame já chega paga-ou-
  liquidada por construção da view, mesma lógica já documentada para
  CLT/Consignado. Dado real consultado (read-only): das 3986 linhas
  `TIPO OPER. = Seguro`, 2697 são `Liquidada` e **zero** são `PAGO AO
  CLIENTE` — se o contador dependesse dessa coluna, daria 0.
- **Correção de divergência doc × código encontrada de passagem**: a
  seção "CLT e Consignado" de `business-rules.md` afirmava que "o
  dashboard carrega só a view `contratos_pagos`". Falso — o loader usa
  `v_contratos_dashboard` (`src/dashboard/loaders.py:337`);
  `contratos_pagos` existe no schema mas não é consumida pelo app. A
  conclusão de negócio (CLT/Consignado só entram via `PAGO AO CLIENTE`,
  nunca via `Liquidada`) continua correta — só a view citada estava
  errada. Corrigido no mesmo commit desta subtarefa.
- **Teste desatualizado corrigido**: `test_tabs_produtos.py` tinha
  `test_aba_antiga_sem_toggle_banco_no_render_nao_regride`, que usava
  Super Conta como exemplo de "aba sem total_label" e afirmava
  `len(at.metric) == 0`. Deixou de ser verdade. Renomeado para
  `test_aba_sem_toggle_banco_super_conta_tem_metric_mas_nao_toggle`,
  assertivas ajustadas (`metric == ["2"]`, `toggle` continua vazio).
- **Testes novos** (`test-automation-specialist`, classe
  `TestRenderProdutoRegionalTotalSemToggle`): 1 por aba nova (Emissão,
  BMG Med, Vida Familiar — Super Conta já coberta pelo teste corrigido
  acima), via `AppTest`, confirmando `st.metric` com valor certo e
  **nenhum** `st.toggle` desenhado. O caso de Emissão prova
  explicitamente a soma das 2 subtabs (2 Cartão Benefício + 1 Venda
  Pré-Adesão → metric `"3"`, não `"2"` nem `"1"`).
- Suíte completa: `472 passed` (era 469). `ruff check` limpo em
  `src/dashboard/tabs/produtos.py` e `tests/test_tabs_produtos.py`.
- **Fora de escopo, não implementado**: coluna "Análise" (digitados) para
  as abas novas — nenhuma pediu; cards-resumo (`kpi_cards.py`) seguem sem
  estes contadores, mesma decisão já registrada no ST-08.

### ST-10 — produção de supervisor volta a contar, marcada (2026-08-10)

Origem: usuário reportou (após o ST-09) que os números de Super Conta e
BMG Med divergiam entre o card "Aceleradores" e os contadores novos desta
seção. Investigado e confirmado com dado real (agosto/2026, via
`business-rules-kpi-expert`): a causa era **completa** — supervisor tem
produção nesses dois produtos no mês (Super Conta 136 vs. 134, BMG Med 86
vs. 85; Vida Familiar 72/72 sem diferença por não ter produção de
supervisor no período; Emissão 0/0 nos dois lados). `calcular_kpis_qtd_produtos`
(`kpis/gerais.py:806-897`, alimenta o Aceleradores) nunca excluiu
supervisor; `_render_produto_regional` sempre excluiu via `_excluir_sup`
antes de contar qualquer coisa. Ambos os caminhos recebem o mesmo `df_f`
(`app.py:673` e `app.py:808`).

Pedido do usuário, com duas partes: (1) produção de supervisor deve
**contar** e ficar **identificável** como tal; (2) não pode interferir em
nenhum cálculo de média nem KPI que mede consultor. Apresentei 2 opções
via `AskUserQuestion` (voltar a contar marcado × manter excluído com
aviso à parte); escolhida a primeira ("Recomendado").

**Implementação** (`produtos.py`, só este arquivo em código):

- `_mask_supervisor(df, supervisores_norm)` — nova função pura, mesma
  família de `_mask_banco`/`_mask_falsa`.
- `_render_total_produto` ganhou `mask_supervisor` opcional: o `st.metric`
  do total passou a somar sobre `df` **completo** (antes era `df_p`, sem
  supervisor); se a interseção mask-do-produto × mask-de-supervisor for
  > 0, um `st.caption` abaixo do metric informa quanto.
- `_render_produto_regional`: `dfs_ef` (as duas visões) passam a ser
  construídas sobre `df` completo, não mais `df_p`. `df_p` continua
  existindo, mas só serve pro esqueleto de consultores zerados e pro
  frame de digitados (`df_a`) — nunca mais pras contagens de efetivados.
  - **Visão Admin/Gestor** (por região/loja): produção de supervisor
    entra anônima e somada no total da loja (não há linha por pessoa
    nessa visão — é a granularidade "conta pra loja" já documentada em
    `docs/agents/rls.md`). Loja afetada ganha `" *"` no nome; legenda no
    rodapé da seção quando pelo menos uma loja foi marcada.
  - **Visão `gerente_comercial`** (por loja/consultor): produção de
    supervisor é separada do `df_merged` **antes** do merge com
    esqueleto/digitados (que são exclusivos de consultor de verdade) e
    reintroduzida só na hora de renderizar, como linha própria por loja,
    rotulada `"<nome> (Supervisor)"`, sempre depois dos consultores reais
    (nunca entra no `sort_values(ef_base, ...)`) e antes da linha "Total"
    — que soma tudo, incluindo essa linha. Coluna "Análise" fica sempre
    `0` nessa linha (digitados de supervisor não são computados —
    limitação conhecida, não bug).
  - Interação com a flag "Somente BMG/Help": `mask_banco` (agora também
    indexada sobre o `df` completo, sem precisar de reindex) entra por
    AND tanto na contagem quanto na detecção de "quais lojas têm
    supervisor" — supervisor fora do banco filtrado não aparece marcado.

**Validação antes de delegar testes formais:** rodei um script `AppTest`
ad hoc (não commitado, `scratchpad/`) cobrindo os 4 cenários (Admin/Gestor
com supervisor, `gerente_comercial` com supervisor, Emissão com 2 subtabs,
CLT com toggle BMG/Help ligado) e conferi os valores manualmente antes de
escrever a especificação pro `test-automation-specialist` — reduziu risco
de o subagente "inventar" um número errado e o teste validar a
implementação contra si mesma.

**Testes formais** (`test-automation-specialist`, só `test_tabs_produtos.py`
tocado): +11 testes.
- `TestMaskSupervisor` (4) — função pura: marca supervisor conhecido,
  `supervisores_norm` vazio, coluna `CONSULTOR` ausente, normalização
  espaço/caixa.
- `TestRenderProdutoRegionalProducaoSupervisor` (7), via `AppTest`:
  Admin/Gestor com total+loja marcada+legenda de rodapé;
  `gerente_comercial` provando que a linha de supervisor nunca participa
  do sort (cenário deliberado: supervisor com produção **maior** que os
  consultores, ainda assim sempre por último — provado por posição no
  HTML, não só pelo valor); Emissão com supervisor somando as 2 subtabs;
  toggle BMG/Help incluindo e excluindo supervisor conforme o banco bate;
  2 testes de "sem produção de supervisor" (Admin/Gestor e
  `gerente_comercial`) confirmando que nenhuma caption/marcação aparece
  quando `df_sup` existe mas não tem produção no período.
- Nenhum dos 472 testes pré-existentes precisou de ajuste: nenhum passava
  `df_sup` com nomes reais, então a mudança de comportamento (que só
  ativa quando há sobreposição `CONSULTOR` × `SUPERVISOR`) ficou invisível
  pra eles — confirmado antes de delegar, rodando a suíte pré-mudança.
- Suíte completa: `483 passed` (era 472). `ruff check` limpo em
  `produtos.py` e `test_tabs_produtos.py`.

**Documentação**: `business-rules.md` ganhou a subseção "Produção de
supervisor — conta pro total, marcada, fora do ranking" (dentro de "CLT e
Consignado…", que já documenta o mecanismo compartilhado de
`_render_produto_regional`) e uma nota de exceção em "Exclusão de
supervisores" (a regra geral do dashboard, que continua valendo — só o
total desta seção deixou de excluir).

## Referências

- Conversa: pedido do usuário em 2026-08-06 para acrescentar contadores de
  CLT/Consignado pagos na Análise Regional, com flag BMG/Help; evoluído em
  2026-08-10 (ST-09) para estender o contador de total às 4 abas restantes.
- Docs consultados: [business-rules.md](../business-rules.md),
  [data-layer.md](../data-layer.md).
