# Regras de Negócio

Regras obrigatórias em qualquer cálculo de KPI. Divergir delas quebra
produção.

## Pontuação

`pontos = VALOR × PTS`

- `PTS` vem da tabela `pontuacao` via RPC `obter_pontuacao_periodo(p_mes, p_ano)`.
- `VALOR` é o campo `valor` do contrato, sempre convertido com `float(c.get("valor", 0))`.
- Se `conta_pontuacao = False` na categoria → `pontos = 0`.
- Se `conta_valor = False` na categoria → `VALOR = 0` no agregado.

### Portabilidade — alias por banco

A categoria `PORTABILIDADE` **não tem entrada própria** em `pontuacao`. O
multiplicador é herdado do `CONSIG_<banco>` correspondente ao `BANCO` do
contrato:

| `BANCO` (normalizado) | Categoria de pts usada |
|---|---|
| `BMG` / `BANCO BMG` | `CONSIG_BMG` |
| `C6 BANK` / `C6` / `BANCO C6` | `CONSIG_C6` |
| `ITAU` / `ITAÚ` / `BANCO ITAU` / `BANCO ITAÚ` | `CONSIG_ITAU` |

`CONSIG_PRIV` **não se aplica a portabilidade** (produto distinto). Bancos
não mapeados permanecem com `PONTOS = 0`.

Resolvido em código ([`src/dashboard/loaders.py`](../../src/dashboard/loaders.py)
— constante `_PORTAB_BANCO_TO_CONSIG` + override após o lookup de `PONTOS`)
e não via tabela `pontuacao` porque o diferencial é `BANCO`, granularidade
maior que categoria. A migration 013 explicitamente deixou portabilidade
fora do alias estrutural por causa dessa granularidade.

### Diagnóstico de categorias sem pontuação

Categoria presente nos contratos mas **ausente** da tabela `pontuacao` do
período pontua **zero** e distorce silenciosamente os KPIs. O dashboard
detecta isso na carga (`app.py`) e emite `st.warning`:

- `N contratos sem categoria` — `TIPO_PRODUTO` não mapeado em `categorias_produto`.
- `N categorias sem pontuacao` — categoria do contrato sem entrada em `pontuacao`.

Revisar no início de cada período e ao introduzir produtos novos. (Sucessor
vivo do antigo aviso baseado na planilha `pontuacao/pontos_{mes}.xlsx`.)

## Emissão de cartão

`TIPO_PRODUTO ∈ {CARTÃO BENEFICIO, Venda Pré-Adesão}`:

- **Contam apenas como quantidade**.
- `conta_valor = False` e `conta_pontuacao = False` em `categorias_produto`.
- Excluídos de somatórios de valor e pontos; aparecem em KPIs de "unidades produzidas".

## Seguros (BMG Med / Vida Familiar)

Identificação via coluna `TIPO OPER.` (vem de `tipo_operacao` no banco):

| `TIPO OPER.` | Rótulo na UI |
|---|---|
| `BMG MED` | "Med" |
| `Seguro` | "Vida Familiar" |

Regras:

- **Contam apenas como quantidade** (igual cartão).
- No Supabase, esses contratos **não** recebem `status_pagamento_cliente = 'PAGO AO CLIENTE'`.
- Entram em "Contratos Pagos" via `sub_status_banco = 'Liquidada'` combinado com `tipo_operacao ∈ {BMG MED, Seguro}`.
- Têm breakdown próprio no renderer `_render_tab_em_analise` (commit `adae6c1`).

## Super Conta

`SUBTIPO = SUPER CONTA` — subcategoria de CNC.

- **Conta duplamente**: para valor/pontos **como CNC** E separadamente como produção de Super Conta (quantidade).
- No DB: categoria `SUPER_CONTA` com `grupo_dashboard = 'CNC'` e entrada própria em `pontuacao` com o mesmo multiplicador do CNC.

## CLT e Consignado (Novo/Refin) pagos

Contadores de **quantidade** de propostas pagas, exibidos nas abas `CLT` e
`Consignado (Novo/Refin)` da seção "Emissão e Seguros — Análise Regional".

| Contador | Critério (combinado por **AND**) |
|---|---|
| **CLT** | `categoria_codigo = CONSIG_PRIV` **e** `TIPO OPER.` ≠ `SEGURO PRESTAMISTA` |
| **Consignado (Novo/Refin)** | `categoria_codigo ∈ {CONSIG_BMG, CONSIG_ITAU, CONSIG_C6}` **e** `SUBTIPO ∈ {NOVO, REFIN}` |

Comparações de `SUBTIPO` / `TIPO OPER.` / `BANCO` são feitas
**normalizadas** (`.astype(str).str.strip().str.upper()`) — a base não é
uniformemente maiúscula (`Portabilidade` e `PORTABILIDADE` convivem).

- **Não** usam a exceção `sub_status_banco = 'Liquidada'` dos
  [Seguros](#seguros-bmg-med--vida-familiar): a view que alimenta o
  dashboard (`v_contratos_dashboard`, não `contratos_pagos` —
  `src/dashboard/loaders.py:337`) só aplica essa exceção a
  `tipo_operacao ∈ {BMG MED, Seguro}`; para CLT/Consignado toda linha já
  chega paga por `status_pagamento_cliente = 'PAGO AO CLIENTE'`.
- `categoria_codigo` de CLT é **derivado no app** — as linhas chegam com
  categoria nula do banco e só viram `CONSIG_PRIV` em
  `_preencher_categoria_fallback`
  ([`src/dashboard/loaders.py`](../../src/dashboard/loaders.py)). O filtro
  vale no DataFrame do dashboard, **nunca** em SQL direto.
- **Seguro Prestamista fica fora do CLT**: ~93 linhas de `CONSIG_PRIV` têm
  `TIPO OPER. = 'Seguro Prestamista'` — são seguro, não crédito CLT.
- **Portabilidade se exclui sozinha, sem lógica extra.** O alias
  [Portabilidade — alias por banco](#portabilidade--alias-por-banco)
  sobrescreve **apenas** a coluna `PONTOS`; o `categoria_codigo` da linha
  continua `PORTABILIDADE`. Logo Portabilidade e Refin da Portabilidade
  (que carregam `SUBTIPO = REFIN`) já não passam pelo filtro de categoria.
- `MARGEM COMPLEMENTAR` (~8% do consignado) fica de fora por não ser Novo
  nem Refin — comportamento pretendido.
- `CONSIG_ITAU` / `CONSIG_C6` têm **0 linhas** hoje (o ETL manda todo
  consignado para `CONSIG_BMG`); permanecem no filtro por robustez, sem
  efeito prático. A distinção de banco existe **só** na coluna `BANCO`.

### Contadores dos demais produtos (Emissão, Super Conta, BMG Med, Vida Familiar)

Em 2026-08-10 o mesmo contador de topo ("Propostas pagas") foi estendido às
outras 4 abas da seção — **sem** a flag "Somente BMG/Help", que só faz
sentido para CLT/Consignado (onde o banco distingue a régua de
comissionamento; nos demais produtos o banco não é critério de negócio):

| Contador | Critério |
|---|---|
| **Emissão** | `TIPO OPER. ∈ {CARTÃO BENEFICIO, Venda Pré-Adesão}` (soma as duas subtabs) |
| **Super Conta** | `SUBTIPO = SUPER CONTA` |
| **BMG Med** | `TIPO OPER. = BMG MED` |
| **Vida Familiar** | `TIPO OPER. = Seguro` |

BMG Med e Vida Familiar entram no DataFrame pela exceção
`sub_status_banco = 'Liquidada'` (ver
[Seguros](#seguros-bmg-med--vida-familiar)), não por
`PAGO AO CLIENTE` — mas isso já está resolvido na origem
(`v_contratos_dashboard`): toda linha do frame já é paga-ou-liquidada por
construção, então a contagem simples por `TIPO OPER.` não precisa (nem
deve) replicar esse filtro — mesma lógica já vale para CLT/Consignado
acima.

Mesma implementação genérica de `_render_total_produto` /
`_render_produto_regional` (aba sem `toggle_banco` na config simplesmente
não desenha o toggle — ver [Onde está implementado](#onde-está-implementado)).

### Flag "Somente BMG/Help"

Toggle disponível nas abas CLT e Consignado:

| Aspecto | Regra |
|---|---|
| Filtro | `BANCO ∈ {BMG, BANCO BMG, HELP, BANCO HELP}` (normalizado) |
| Alcance | **A aba inteira** — o total no topo **e** as tabelas abaixo, em todos os perfis: por região/loja (Admin/Gestor) e por loja/consultor (`gerente_comercial`) |
| Escopo | Só a aba onde o toggle está ligado (chave de sessão por aba); não afeta a outra aba nem o resto do dashboard |

O recorte é **um só**: a mesma máscara de banco usada no total entra por
`AND` no filtro de cada subtab antes de alimentar as tabelas. Consequências:

- O total do topo **bate** com a soma das tabelas (salvo linha sem
  `REGIAO`/`LOJA`, que entra no total e não no `groupby` — ver
  [Onde está implementado](#onde-está-implementado)).
- Na visão por região não há esqueleto de linhas: região/loja que fica sem
  nenhuma linha após o filtro **some da tela**. Na visão `gerente_comercial`
  o esqueleto de consultores preserva as linhas zeradas.
- `BANCO` ausente do frame com a flag ligada **zera a aba inteira** (total e
  tabelas), coerente com "critério sem coluna zera a contagem".

> **Histórico:** até 2026-08-10 a flag restringia **apenas o total**, e as
> tabelas seguiam com todos os bancos. Isso foi reportado como
> "`gerente_comercial` não consegue filtrar produção": esse perfil usa a
> tabela por loja/consultor como visão principal, não o KPI agregado, então
> a flag parecia não fazer nada. Não era RLS nem dado (`BANCO` nunca nula,
> nenhuma região órfã, o toggle corta ~10-20% da produção e nunca zera) —
> era o alcance da flag. Ver
> [progress/2026-08-06](progress/2026-08-06-plano-clt-consignado-emissao-seguros.md)
> (ST-05/ST-06).

Hoje `HELP` **nunca** ocorre como `BANCO` em CLT nem em Consignado
(validado contra a base completa: `HELP` só aparece em CNC / CNC 13º /
Antecipação de Benefício / CPT), então a flag equivale na prática a
`BANCO = BMG`. Mantida assim por decisão de produto, preparada para o caso
de um dia existir CLT/Consignado via Help. Não confundir com o prefixo
`HELP` em **nome de loja** (`HELP BANGU`, …) — o filtro é sobre `BANCO`,
não `LOJA`.

### Reuso em "Distribuição de Produtos" (Analíticos)

Desde 2026-08-13 os **mesmos dois critérios** alimentam duas colunas de
quantidade na tabela "Distribuição de Produtos"
([`src/dashboard/kpis/produtos.py`](../../src/dashboard/kpis/produtos.py),
`_mascaras_aceleradores`), nas visões por consultor e por loja — ao lado
de BMG Med, Vida Familiar, Emissão e Super Conta:

| Coluna na tabela | Critério |
|---|---|
| `CLT (Qtd)` | idêntico ao contador **CLT** acima |
| `Consignado (Novo/Refin)` | idêntico ao contador **Consignado** acima |

- **São quantidade acrescentada por cima, não substituem o valor.** O R$
  desses produtos já aparecia (e continua aparecendo) nas colunas de valor
  do pivot, via `grupo_dashboard` — `CONSIG_PRIV → CLT` e
  `CONSIG_{BMG,ITAU,C6} → CONSIGNADO`. A máscara de valor (`mask_cred`)
  **não mudou**: continua excluindo só BMG Med / Vida Familiar / Emissão.
  É o mesmo tratamento que [Super Conta](#super-conta) já recebia — conta
  duas vezes, em valor **e** em quantidade.
- Consequência esperada, **não** é divergência: numa mesma linha o R$ da
  coluna `CLT` pode não bater com `CLT (Qtd)` — o valor inclui
  `Seguro Prestamista` (é `grupo_dashboard = CLT`) e a quantidade não;
  em Consignado o valor inclui `MARGEM COMPLEMENTAR` e a quantidade não.
- **Por que `CLT (Qtd)` e não `CLT`**: `CONSIG_PRIV` tem
  `grupo_dashboard = 'CLT'`, então o pivot de valor já emite uma coluna
  chamada `CLT`. Duas colunas homônimas viram `CLT_x`/`CLT_y` no merge e
  **as duas** caem nos filtros `c in distrib.columns` — o R$ de CLT sumiria
  do `TOTAL` silenciosamente. `CONSIGNADO` (valor) × `Consignado
  (Novo/Refin)` (qtd) não colidem, por isso só CLT leva sufixo.

#### Seletor de banco: aqui é selectbox, não toggle

Desde 2026-08-19 a "Distribuição de Produtos" **não** tem toggle
booleano: tem um `st.selectbox("Banco", …)` (`_selecionar_banco`,
[`src/dashboard/tabs/analiticos.py`](../../src/dashboard/tabs/analiticos.py)).

| Opção | Recorte aplicado |
|---|---|
| `Todos` (padrão) | Nenhum — nem exige a coluna `BANCO` |
| `BMG/Help` | Preset composto: `BANCO ∈ {BMG, HELP}` (canônico) — preserva o alcance do toggle anterior |
| `BMG`, `C6`, `MASTER`, … | Um banco só, derivado dos valores presentes no próprio frame |

**Por que aqui divergiu do toggle das abas CLT/Consignado:** naquelas
abas BMG/Help é *regra de comissionamento* — o banco distingue a régua, e
o recorte binário é a pergunta certa. Na Distribuição, que cobre **todos**
os grupos (CNC, FGTS, Saque, PACK, aceleradores), banco não é critério de
negócio: é uma dimensão de análise como qualquer outra. A divergência é
**deliberada** — `produtos.py` continua com `st.toggle`, e deve continuar.

**Valores canônicos.** As opções passam por `canonizar_banco`
([`src/dashboard/kpis/produtos.py`](../../src/dashboard/kpis/produtos.py)):
`_BANCO_ALIAS` funde as variantes de grafia da base (`BANCO BMG → BMG`,
`C6 BANK`/`BANCO C6 → C6`, `BANCO ITAÚ → ITAU`), senão o mesmo banco
apareceria como duas opções partindo a produção ao meio. `ITAU-360` fica
**fora** do mapa de propósito: é canal próprio na base, e fundi-lo com
`ITAU` seria decisão de negócio, não de normalização.

**Alcance do recorte** — o parâmetro é `bancos` (tupla canônica, ou
`None` para "Todos"):

| | "Emissão e Seguros — Análise Regional" | "Distribuição de Produtos" |
|---|---|---|
| Widget | `st.toggle` booleano | `st.selectbox` (Todos / preset / banco) |
| Alcance | Só a aba onde está ligado (CLT **ou** Consignado) | **A tabela inteira**: todas as colunas de valor, todas as de quantidade e o `TOTAL` |
| Como é aplicado | Composição de máscaras por subtab (`AND` em `_mask_subtab`) | Recorte de linhas no topo da função, antes de qualquer máscara |
| Produtos afetados | Só CLT / Consignado | **Todos** — CNC, FGTS, Saque, aceleradores etc. |

O recorte no topo é o que faz pivot de valor, as 6 máscaras, o `TOTAL` e
os merges de `LOJA`/`REGIAO` herdarem o filtro sem branch extra. `BANCO`
ausente do frame com um banco selecionado **zera a tabela inteira** —
mesma regra de "critério declarado sem coluna zera a contagem"; com
`Todos` não zera nada, porque não há critério declarado.

**Duas armadilhas registradas** (ambas com teste):

- A chave de sessão é `dist_prod_banco`, **nova**. A antiga
  `dist_prod_bmg_help` guardava `bool`; reusar o nome num selectbox
  quebraria toda sessão já aberta.
- Guard de cascata antes de instanciar o widget: trocar mês/loja na
  sidebar pode tirar da base o banco selecionado, e o valor órfão volta
  para `Todos` — mesmo padrão do Subproduto em `_filtrar_detalhamento`.

A lista `_BANCOS_BMG_HELP` está **duplicada** em `kpis/produtos.py` e
`tabs/produtos.py` de propósito (importar da UI para a camada de KPI
inverteria a direção de dependência) — se mudar, mudar nos dois.

### Produção de supervisor — conta pro total, marcada, fora do ranking

Diferente do resto do dashboard (ver
[Exclusão de supervisores](#exclusão-de-supervisores)), os contadores desta
seção **não** excluem produção de supervisor do total — desde 2026-08-10
ela conta pra loja/aba, igual ao card "Aceleradores"
(`calcular_kpis_qtd_produtos`), só que **marcada**, nunca misturada ao
ranking/média de consultor:

| Visão | Como aparece |
|---|---|
| KPI do topo | Soma tudo (com supervisor); se houver produção de supervisor, `st.caption` abaixo do metric informa quanto |
| Admin/Gestor (por região/loja) | Produção de supervisor entra **anônima e somada** no total da loja (não há linha por pessoa nesta visão); loja afetada ganha `" *"` no nome, com legenda no rodapé da seção |
| `gerente_comercial` (por loja/consultor) | Linha própria por loja, rotulada `"<nome> (Supervisor)"`, sempre **depois** dos consultores reais (nunca entra no `sort_values` por produção) e **antes** da linha "Total" — que soma tudo, incluindo essa linha |

Motivo da mudança: o card "Aceleradores" sempre somou supervisor (nunca
chamou `excluir_supervisores`); estes contadores excluíam por completo —
divergência que apareceu como "os números não batem" entre as duas
superfícies para Super Conta/BMG Med (produtos onde havia produção de
supervisor no período; nos demais o gap era zero por coincidência de não
ter produção de supervisor naquele mês). A correção alinha o total com o
Aceleradores sem violar a regra geral: supervisor não vira uma linha de
"consultor" em nenhum ranking, esqueleto (consultores zerados) ou coluna
"Análise" (digitados de supervisor não são computados — fica sempre `0`
nessa linha, limitação conhecida, não bug).

### Onde está implementado

[`src/dashboard/tabs/produtos.py`](../../src/dashboard/tabs/produtos.py):
config `_PRODS_QTD`, filtros em `_mask_subtab` / `_mask_banco` /
`_mask_supervisor`, total e toggle em `_render_total_produto`. Critério
declarado cuja coluna não existe no frame **zera** a contagem (total
inflado silenciosamente é pior que zero). Testes em
`tests/test_tabs_produtos.py`.

O alcance único da flag (total + tabelas) sai de `_render_total_produto`
devolvendo a **máscara de banco já aplicada ao total** (`None` quando não há
filtro ativo); `_render_produto_regional` reaplica essa mesma máscara por
`AND` em `_mask_subtab(df, sub)` antes de chamar `_contar_por_regiao` ou
`_contar_por_loja_consultor` — um recorte só, sem branch por perfil. Desde
2026-08-10 esse `df` é o frame **completo** (com supervisor) — `df_p`
(via `_excluir_sup`) continua existindo, mas só serve pro esqueleto de
consultores zerados e pro frame de digitados (`df_a`), nunca mais pras
contagens de efetivados. Na visão por consultor, a produção de supervisor
é separada do `df_merged` **antes** do merge com esqueleto/digitados (que
são exclusivos de consultor de verdade) e reintroduzida só na hora de
renderizar, como linha à parte. O total é contado sem depender de
`REGIAO`/`LOJA`; as tabelas usam `groupby`, que descarta linha órfã — com
órfã, total ≥ soma das tabelas.

Esses contadores **não** estão nos cards-resumo (`kpi_cards.py` /
`calcular_kpis_qtd_produtos`, config desacoplada de `_PRODS_QTD`) —
decisão explícita de escopo. (`calcular_kpis_qtd_produtos` sempre somou
supervisor; ver seção acima.)

Follow-ups conhecidos, não bloqueantes: CLT/Consignado não têm coluna
"Análise" (digitados) — se ganharem, a flag de banco precisa ser estendida
ao frame de digitados (`df_a`), que hoje não recebe a máscara;
`ITAU-360` — valor real de `BANCO` — não está em
`_PORTAB_BANCO_TO_CONSIG`, divergência preexistente que não afeta estes
contadores. Ver
[progress/2026-08-06](progress/2026-08-06-plano-clt-consignado-emissao-seguros.md).

## PACK — meta conjunta e desmembramento

`grupo_dashboard = 'PACK'` agrupa três categorias (`FGTS`, `ANT_BENEF`,
`CNC_13`) que **dividem uma única meta** (`grupo_meta =
FGTS_ANT_BENEF_13`). Não existe alvo por categoria — daí a regra de
exibição:

| Superfície | Dimensão de produto |
|---|---|
| Compara valor × meta: aba Produtos, heatmap região×produto, KPIs por região, cards MIX (valor e pontos), prioridades | **PACK agregado** (`grupo_dashboard`), rotulado `PACK_LABEL_AGREGADO` |
| Não compara com meta: Analíticos, Em Análise, rankings por produto, "sem produção", distribuição por consultor, aba Gestão, páginas de detalhe dos cards | **desmembrado** em `PRODUTO_DETALHADO` |

- Rótulos canônicos em [`src/config/settings.py`](../../src/config/settings.py):
  `PACK_SPLIT_LABELS` (chaveado por `categoria_codigo`) e
  `PACK_LABEL_AGREGADO` (junção dos três). São os nomes do tipo **na
  planilha de origem** — os mesmos que aparecem em `TIPO_PRODUTO`.
  Rótulo novo de produto entra ali, nunca hardcoded na tab.
- O desmembramento é client-side e puro: `adicionar_produto_detalhado(df)`
  (`src/dashboard/kpis/produtos.py`) deriva `PRODUTO_DETALHADO` de
  `categoria_codigo`, com fallback para `grupo_dashboard` quando a
  categoria não veio (digitação legada, join de produto não resolvido).

## Pipeline "Em Análise"

O sistema de origem só retorna `status_banco ∈ {EM ANALISE, CANCELADO}` e
**não** atualiza o `status_banco` quando o contrato é pago. O dashboard
deriva "Em Análise" excluindo do conjunto:

| Condição excluída | Motivo |
|---|---|
| `status_pagamento_cliente = 'PAGO AO CLIENTE'` | já pago → remover do pipeline |
| `status_banco = 'CANCELADO'` | cancelado → nunca aparece |
| `sub_status_banco = 'Liquidada'` | seguro liquidado → já "pago" |

Essas três exclusões são **cumulativas**.

## Cancelados — contenção de redigitação

O total de cancelados infla com **redigitações** (a mesma proposta digitada
várias vezes por erro de averbação do banco ou de operação) e com canceladas
que foram redigitadas e **pagas** depois. Para informar o churn corretamente,
a RPC `obter_cancelados_classificados` (migration `032`) classifica cada
cancelado em uma de três classes — matching **no banco**, pelo nome do cliente
(`contratos.cliente`, homônimos = risco aceito), em janela de **7 dias** e por
**`categoria_codigo`** ("mesmo produto"):

| Classe | Critério | Conta? |
|---|---|---|
| `redigitada` | existe outro **cancelamento** do mesmo nome+categoria com `data_cadastro` posterior em ≤7d (vale em cadeia: A→B→C com gaps ≤7d mantém só C) | Não |
| `recuperada` | não-redigitada, mas existe **paga** do mesmo nome+categoria com `data_cadastro` entre o cancelamento e +7d | Não |
| `liquido` | representante final sem paga em 7d (conta mesmo que o cliente seja pago **depois** dos 7d) | **Sim** |

`nome_norm = upper(trim(regexp_replace(cliente, '\s+', ' ', 'g')))`; nome vazio
nunca casa. O **nome nunca sai do banco** — só a coluna `classificacao` (por isso
o matching é SQL, não Python; ver [data-layer.md](data-layer.md)). `valor`/`qtd`/
churn de cancelados passam a usar apenas `liquido`; redigitadas/recuperadas
voltam como contexto (`qtd_bruto`, `qtd_redigitadas`, `qtd_recuperadas`).

**RLS:** o dashboard lê em **escopo completo** (cliente Supabase único; sem GUC
por usuário) e o filtro por perfil é **client-side** via `aplicar_rls(df)`
([rls.md](rls.md)). Logo a classificação é computada no SQL sobre **toda** a
base — redigitações/recuperações por qualquer consultor **são detectadas** — e
só depois as linhas são filtradas ao escopo do usuário. (A RPC é `SECURITY
INVOKER` e herda esse escopo completo.)

### Oportunidades perdidas (por nível de perfil)

A RPC marca a venda capturada **fora do próprio nível** — representante
(não-redigitada) que **não** foi recuperado no próprio nível, mas foi pago por
alguém de fora dele em ≤7 dias:

| Flag | Verdadeiro quando pago por… | Exibido p/ perfil |
|---|---|---|
| `recuperada_outro` | **outro consultor** | consultor |
| `recuperada_outra_loja` | **outra loja** | supervisor |
| `recuperada_outra_regiao` | **outra região** | gerente_comercial |

A semântica respeita o nível: recaptura **dentro** do próprio nível não é perda
(ex.: outro consultor da mesma loja não é perda da loja). Como a leitura é
full-scope, tudo é detectável no SQL; após `aplicar_rls` sobram as canceladas do
escopo do usuário, e o flag do nível alimenta a seção **"Oportunidades
perdidas"** (qtd + valor perdido). São subconjunto de `recuperada`: **não**
alteram a contagem de líquidos. A identidade de quem capturou a venda **não** é
exposta (só o flag e o valor saem do banco). As três colunas vêm da RPC
`obter_cancelados_classificados` (migration 033 — ver [data-layer.md](data-layer.md)).

### Assertividade dos consultores

`assertividade = (1 − redigitadas / total_propostas) × 100` por consultor, com
`total_propostas = pagas + em análise + canceladas (bruto)`. Mede o retrabalho
operacional (redigitação). Como as fontes têm janelas de carga distintas, o
denominador é uma aproximação do período.

## Metas

### Estrutura

- **Meta Prata** (base) e **Meta Ouro** (premium), em pontos.
- Metas gerais (tabela `metas`, `escopo='GERAL'` ou por loja).
- Metas por produto (tabela `metas_produto`).

### Meta diária restante

```
meta_diaria = (Meta Prata - pontos_atuais) / DU_restantes
```

- `pontos_atuais`: pontuação acumulada do período vigente.
- `DU_restantes`: via `calcular_dias_uteis(ano, mes, dia_atual)` — considera feriados do DB.

### Projeção

```python
media_du  = total / du_dec if du_dec > 0 else 0
projecao  = media_du * du_total
perc_proj = projecao / meta * 100 if meta > 0 else 0
```

## Emissão de contrato — zeragem de valor

Commit `292ab90`: contratos de categoria "emissão" (quando aplicável) têm
`VALOR` zerado na consolidação para não inflar totais. Ver script
`scripts/diagnostico/diagnosticar_valor_total.py` para referência.

## Exclusão de supervisores

Supervisores **não aparecem** em análises consultor-level:

```python
def _excluir_supervisores(df, df_sup):
    if df_sup is not None and "SUPERVISOR" in df_sup.columns and "CONSULTOR" in df.columns:
        return df[~df["CONSULTOR"].isin(df_sup["SUPERVISOR"].unique())].copy()
    return df.copy()
```

Aplicar **antes** de rankings, contagens de consultores e médias por consultor.

> **Exceção documentada:** os contadores de "Emissão e Seguros — Análise
> Regional" (ver
> [Produção de supervisor — conta pro total, marcada, fora do
> ranking](#produção-de-supervisor--conta-pro-total-marcada-fora-do-ranking))
> voltam a somar produção de supervisor no **total** (loja/aba), mas
> continuam nunca deixando o supervisor virar uma linha de "consultor" em
> ranking, esqueleto ou média — a regra acima (nunca aparecer em
> análises consultor-level) segue valendo, só o total deixou de excluir.

## Lojas de backoffice (Vai e Vem)

`VAI E VEM` não é loja de venda: é o **setor de digitação de contratos via
backoffice**. Ele digita contratos impossíveis nas lojas e, quando a proposta
é paga, a produção é **repassada ao consultor de loja** que iniciou a
negociação (raro ficar contrato pago sem remanejar). Consequências:

- Consultores do Vai e Vem **não são ranqueados**, não entram na listagem de
  zerados, nos aceleradores por consultor nem nas médias por consultor; a
  loja não entra nas médias por loja.
- Constante `LOJAS_BACKOFFICE` + helper `excluir_lojas_backoffice` em
  `src/dashboard/kpis/gerais.py`; aplicados em `_preparar` (escopo consultor)
  e nos universos de `rankings.py`, nas médias de `gerais.py`/`pontuacao.py`
  e em `calcular_aceleradores_consultor` (`ui/prioridades_acao.py`).
- **Exceção**: somas de contratos **cancelados** e **em análise** contam o
  Vai e Vem normalmente (sem filtro).
- A loja em si **segue** no ranking/zerados de lojas (escopo da exclusão é o
  eixo consultor).
- Não confundir com `_REGIOES_EXCLUIR_MEDIA` (região `ALEXANDRE` = DIGITAL +
  VAI E VEM, usada só na média da organização p/ gerente_comercial): DIGITAL
  **conta** nas métricas de consultor — a exclusão nova é por **loja**.

## Universo de consultores ativos — cadastro duplicado

A tabela `consultores` tem nomes duplicados (ex.: desligamento registrado em
linha nova, deixando o `Ativo (a)` antigo órfão). Os loaders
(`carregar_consultores_cadastro` / `carregar_consultores_ativos`) colapsam
cada nome normalizado no registro de `updated_at` **mais recente** antes do
filtro de status, e o status casa por **prefixo** `ativo` (substring aceitaria
`Inativo (a)`). Fonte da verdade do headcount é a planilha do RH — divergência
entre universo e RH indica cadastro desatualizado no Supabase, não bug.

## Reconquista (v2)

Campanha de retenção. Fonte: export único `reconquista.xlsx`, **1 linha por
cliente** (`co_adesao`), já classificado em `status`. Tabela `reconquista`
(truncada e realimentada a cada carga via RPC `fn_importar_reconquista`);
leitura pela view `v_reconquista`. Loader: `carregar_reconquista(mes, ano)`.

### Estados (validados 100% contra o arquivo)

- **EFETIVADA** — reconquista confirmada: `dt_macica > dt_fim_relacionamento`.
- **PROMESSA** — aceite via DNA **ou** produção de CNC (exceto antecipação)
  após o fim: (`dt_dna > dt_fim_relacionamento` ou
  `dt_producao > dt_fim_relacionamento`) e não-efetivada.
- **SEM RECONQUISTA** — demais (a trabalhar).

### Apuração mensal com defasagem de 1 mês

O mês de apuração `M` exibe os contratos com `dt_fim_relacionamento` em
`M-1` (os de `M` só entram na esteira no mês seguinte). A defasagem é
aplicada no **loader** (`_mes_apuracao_anterior`); a view expõe o mês real
de `dt_fim` em `ref_ano`/`ref_mes`.

| Apuração (seleção) | `dt_fim_relacionamento` | EFET / PROM / SEM |
|---|---|---|
| Maio/2026 | Abril/2026 | 36 / 23 / 249 |
| Junho/2026 | Maio/2026 | 0 / 33 / 288 |

EFETIVADA "zerada" no mês mais recente é **esperado**: depende de
`dt_macica > dt_fim`; quando a maciça desses contratos virar (novo
`dt_macica` no próximo export), eles migram para EFETIVADA.

### Elegibilidade (coluna `flag_elegibilidade`)

O arquivo traz `flag_elegibilidade` (`ELEGIVEL` / `NAO ELEGIVEL`). **Só
ELEGIVEL entram na apuração/conversão** (numerador e denominador); os
`NAO ELEGIVEL` continuam visíveis nos analíticos (detalhe por cliente),
apenas fora da conta. **NULL / sem flag ⇒ ELEGIVEL** (interim, até o
arquivo com a flag ser importado). Helper: `_mask_elegivel` (loaders).

### Analítico: apuração vigente × lista completa

A **apuração é mensal** — KPIs, conversão, faixa de prêmio, quebra por
loja e acelerador leem só a apuração vigente (`clientes`, o corte de
`dt_fim_relacionamento` em `M-1`). Somar apurações produziria uma
conversão que não corresponde a prêmio nenhum.

O **analítico de leads (Detalhamento)** não tem essa restrição: recebe
`clientes_todos` — a mesma base sem o filtro de mês, com o mesmo recorte
de RLS — e alterna entre os dois escopos por pill, abrindo no vigente.
Cada linha carrega a marcação, derivada de `ref_ano`/`ref_mes` +
defasagem (`_marcar_vigencia_reconquista`, loaders):

| Coluna | Conteúdo |
|---|---|
| `apuracao_ref` → "Apuração" | `MM/AAAA` da apuração do lead (= ref + 1) |
| `vigencia` → "Vigência" | `Vigente` (a que os KPIs apuram) · `Próxima` (esteira do mês seguinte, a mesma da prévia) · `Histórico` · `Futura` · `Sem referência` (sem `dt_fim`) |

As duas colunas aparecem **nos dois escopos** e vão no CSV: lista
completa e recorte do mês nunca se confundem. Nenhum KPI lê
`clientes_todos`.

### KPI — conversão e faixa de prêmio (substitui a meta fixa)

Sem meta de 30%. O objetivo é o **% de conversão** sobre a base elegível
= `EFETIVADA / total ELEGIVEL` do mês de referência, mapeado numa faixa
de prêmio/deflator sobre o prêmio CNC (indicador — não calcula R$):

| % Conversão | Ajuste sobre prêmio CNC |
|---|---|
| 0 a 10% | −20% |
| 10,1 a 20% | −10% |
| 20,1 a 29,99% | 0 |
| 30 a 39,99% | +10% |
| ≥ 40% | +20% |

Fronteiras contínuas (limite superior inclusivo nas negativas):
`_faixa_premio_conversao` (loaders). PROMESSA é pipeline; SEM RECONQUISTA
é a trabalhar.

### Acelerador combinado — Reconquista + Cobrança Consignável (≥ 08/2026)

Vigente **a partir da apuração de agosto/2026**. Corte simples de data —
não há vigência por linha (nada de SCD2 como em `loja_regiao_vigencia`):
apuração < 08/2026 não tem acelerador combinado. Na prática o corte é
duplo e redundante de propósito: o gate de período no loader **e** a
ausência de faixas cadastradas para o período (sem faixa vigente ⇒
acelerador desligado, não erro).

Não confundir com
[KPI — conversão e faixa de prêmio](#kpi--conversão-e-faixa-de-prêmio-substitui-a-meta-fixa):
aquele é **percentual de conversão, por loja**; este é **contagem, por
consultor**. Os dois convivem.

**Escopo de premiação** — muda em relação ao histórico: até 07/2026 a
regra era apurada manualmente, fora do sistema, e alcançava público mais
amplo. A partir de 08/2026 o dashboard é a apuração oficial e o alcance é:

| Perfil | Premiado por esta regra? |
|---|---|
| `consultor` | Sim — atingimento individual |
| `supervisor` | Sim — 70% do prêmio de **cada** consultor da equipe (ver abaixo) |
| `gerente_comercial` / `gestor` / `admin` | Não — leitura gerencial, sem atingimento próprio |

**Contagem combinada**, por consultor, no mês de apuração:

```
total = EFETIVADA (Reconquista, base ELEGIVEL) + Cobrança Consignável
```

| `qtd_min` | `qtd_max` | Rótulo exibido |
|---|---|---|
| 0 | 2 | 0 a 2 |
| 3 | 5 | 3 a 5 |
| 6 | 8 | 6 a 8 |
| 9 | `NULL` | 9 ou mais |

- **9 exato entra na última faixa**: `qtd_max = NULL` = sem limite
  superior, sem lacuna entre 8 e 9. A tabela de origem do negócio dizia
  "Maior que 9"; o critério confirmado é **≥ 9** — o rótulo exibido não
  pode contradizer o critério.
- As faixas **não são hardcoded**: vêm da tabela
  `faixas_acelerador_reconquista`, configurável **por período**
  (`periodo_id`), mesmo padrão da [Pontuação](#pontuação)
  (`pontuacao` + `obter_pontuacao_periodo`), inclusive o fallback temporal
  — retrocede ao período anterior mais recente com faixas cadastradas.
  Mudar faixa de um mês para outro é edição de dado, **não deploy**.
  Contraste deliberado com `_faixa_premio_conversao`
  ([`src/dashboard/loaders.py:1917`](../../src/dashboard/loaders.py)),
  escada fixa em Python — não é o modelo a seguir aqui.
- **Assimetria de janela entre as duas parcelas** (esperado, não bug):
  EFETIVADA carrega a defasagem de 1 mês da Reconquista (apuração `M` =
  `dt_fim_relacionamento` em `M-1`); Cobrança Consignável conta pagamentos
  **do próprio mês `M`**.

**O dashboard exibe faixa, nunca prêmio.** Decisão de produto: só o
**rótulo** da faixa atingida (ex.: "3 a 5"). Nenhum valor de premiação em
R$ ou percentual aparece — prêmio/deflator é resolvido fora do dashboard.
Mesmo espírito do indicador de conversão (expõe o ajuste, nunca calcula
R$). Se um dia a tabela de faixas ganhar coluna de valor, ela não vai à UI
sem nova decisão.

### Cobrança Consignável — critério

Acelerador **novo e independente** da Reconquista: contagem de contratos
por consultor no mês de apuração. Critérios combinados por **AND**, sobre
o frame de contratos pagos (`v_contratos_dashboard`):

| Critério | Regra |
|---|---|
| Período | `status_pagamento_cliente = 'PAGO AO CLIENTE'` **e** `data_status_pagamento` dentro do mês/ano de apuração — **nunca** `data_cadastro` |
| `TIPO OPER.` | normalizado = `CONTRATO NOVO` (a base grava `Contrato Novo`) |
| `SUBTIPO` | normalizado = `NOVO`; `MARGEM COMPLEMENTAR` fica **explicitamente fora** (mesmo recorte do contador [Consignado (Novo/Refin)](#clt-e-consignado-novorefin-pagos)) |
| `categoria_codigo` | = `CONSIG_BMG` — é o que separa Consignado (INSS/público) de **CLT** (Consignado Privado e-Social): as duas linhas compartilham `TIPO OPER.`/`SUBTIPO` e só divergem aqui. Sem ele, CLT contaminaria a contagem |
| `BANCO` | normalizado ∈ {`BMG`, `BANCO BMG`} — mesma normalização da [flag "Somente BMG/Help"](#flag-somente-bmghelp), **sem** `HELP` |
| Valor | `valor_bruto <> valor` (`VLR BRUTO` ≠ `VLR BASE`), com tolerância de meio centavo |

> **Onde a regra mora:** desde a migration 067 o critério é a função SQL
> `fn_eh_cobranca_consignavel`, exposta como coluna
> `is_cobranca_consignavel` em `v_contratos_dashboard`. A tabela acima é
> **espelho documental** — alterar a regra é `CREATE OR REPLACE FUNCTION`
> numa migration nova, nunca reimplementar a máscara em Python. O loader
> aplica o filtro server-side (`.eq("is_cobranca_consignavel", True)`); o
> único resto em pandas é a reconferência de mês.
> A suíte de testes do critério é o **bloco de validação da própria
> migration** (seção 4) — o pytest não alcança SQL.

- Normalização em SQL = `upper(btrim(coalesce(x, '')))`, equivalente ao
  `.astype(str).str.strip().str.upper()` usado no resto do projeto (`_norm` /
  `_mask_banco`, [`src/dashboard/tabs/produtos.py`](../../src/dashboard/tabs/produtos.py)),
  pelo mesmo motivo de sempre: a base não é uniformemente maiúscula.
- **O filtro de período já vem satisfeito por construção** no frame mensal:
  `contratos.periodo_id` é derivado de `data_status_pagamento`, exposto
  como coluna `DATA` (mapa `_COLS_CONTRATOS_PAGOS`, loaders) — igual aos
  contadores de CLT/Consignado, não se re-filtra pagamento no DataFrame.
- A exceção `sub_status_banco = 'Liquidada'` dos
  [Seguros](#seguros-bmg-med--vida-familiar) **não contamina** esta
  contagem: essas linhas têm `TIPO OPER. ∈ {BMG MED, Seguro}` e nunca
  passam por `CONTRATO NOVO` (além de chegarem com `DATA` nula).
- **`HELP` fica de fora** — divergência deliberada em relação à flag
  "Somente BMG/Help": aqui o critério de negócio é BMG. Sem efeito prático
  hoje (`HELP` nunca ocorre como `BANCO` de consignado), mas o conjunto
  documentado é o que vale.
- `valor_bruto` (`VLR BRUTO`) é **coluna nova**. A view expõe
  `COALESCE(valor_bruto, valor)`: enquanto o ETL externo (`angry-man`) não
  persistir o campo, `valor_bruto = valor` ⇒ **Cobrança Consignável = 0**.
  Esse zero é o caso neutro documentado (mesmo espírito de
  `flag_elegibilidade` NULL ⇒ ELEGIVEL), **não** falha silenciosa: o dia
  em que o ETL mandar o valor real, o upsert por `contrato_id` corrige
  sozinho. Zero persistente após a carga do ETL é sinal de coluna não
  populada — investigar a origem, não a regra. O mesmo vale para o valor
  consolidado (abaixo): sem `valor_bruto`, `valor_consolidado = valor` e
  **nenhum número do dashboard muda**.

### Produção pelo VLR BRUTO (valor consolidado)

Consequência **financeira** da Cobrança Consignável, não apenas de
contagem: nessas operações o cliente usa parte do valor para quitar
débitos com o banco, então o `VLR BASE` não representa a venda. **A
produção considera o VLR BRUTO** — o valor cheio da operação.

`v_contratos_dashboard.valor_consolidado` (migration 067) é a coluna que
materializa isso:

```
valor_consolidado = GREATEST(valor_bruto, valor)  quando is_cobranca_consignavel
                  = valor                          nos demais casos
```

| Aspecto | Regra |
|---|---|
| Coluna `VALOR` do dashboard | vem de `valor_consolidado`. **Todo** KPI de produção, ranking, ticket médio, meta e gráfico lê essa coluna — nenhum deles precisou mudar |
| Pontuação | `pontos = VALOR × PTS` segue inalterado, logo **pontua sobre o consolidado**. Metas em pontos, meta diária e projeção acompanham |
| `VALOR_BASE` | o `VLR BASE` **cru**, só para auditoria/exibição. **Nunca somar como produção**: não recebe os zeramentos de `conta_valor = False` nem de emissão que o `VALOR` recebe na consolidação (mesma relação de `PONTOS` cru × `pontos` calculado) |
| Escopo | **somente contratos pagos**. Pipeline em análise (`v_contratos_em_analise`), cancelados (`v_contratos_cancelados`) e digitação diária (RPCs `obter_digitacao_diaria*`) seguem em `VLR BASE` |

- **Nunca reduz.** Se o `VLR BRUTO` vier **menor** que o `VLR BASE` (dado
  sujo na origem), o `GREATEST` mantém o `VLR BASE` — produção não cai por
  erro de ETL. A linha **continua** contando no contador, cujo critério é
  `|bruto − base| > 0,005` em qualquer direção. Invariante permanente:
  `valor_consolidado >= valor`.
- **Divergência conhecida com o fallback de categoria.**
  `_preencher_categoria_fallback` mapeia `TIPO_PRODUTO ∈ {CONSIG,
  CONSIG BMG}` → `CONSIG_BMG` quando `produtos.categoria_id` é NULL
  (migration 061); o SQL usa `cp.codigo` cru e não enxerga esse fallback.
  Uma linha assim **não recebe o uplift** — subnotifica, nunca
  superestima. Já era o comportamento do contador antes da 067 (o frame
  da Cobrança Consignável nunca aplicou o fallback), então a contagem não
  mudou. Medido pela query 6 do bloco de validação da migration; se der
  > 0, corrigir a **origem** (ETL), não a regra.

### Supervisor — 70% do prêmio de cada consultor

O supervisor recebe **70% do prêmio/deflator de cada consultor da sua
equipe, individualmente** — nunca um valor agregado único sobre a soma da
equipe. Consequência direta para a apuração e para a UI: a visão do
supervisor lista **um rótulo de faixa por consultor**, não uma faixa única
"do supervisor" nem uma contagem somada da equipe.

| Aspecto | Regra |
|---|---|
| Equipe do supervisor | Consultores lotados na(s) loja(s) do supervisor |
| Vínculo no schema | **Não existe FK supervisor→consultor**: `supervisores → lojas` (`carregar_supervisores()`, [`src/dashboard/loaders.py:1492`](../../src/dashboard/loaders.py), devolve `SUPERVISOR`/`LOJA`/`REGIAO`) cruzado com `consultores.loja_id` (`database/schema.sql`) |
| Supervisor multi-loja | Soma os consultores de todas as suas lojas (cada um continua com sua faixa própria) |
| Valor do 70% | Nunca exibido — o dashboard mostra faixa; o 70% define **o que** o supervisor enxerga (faixa por consultor) e quantas linhas a visão tem |

Produção do próprio supervisor não vira linha de consultor nesta visão
(vale a regra geral de [Exclusão de supervisores](#exclusão-de-supervisores)).

**A chave de junção das duas parcelas é o nome do consultor**, não um id:
EFETIVADA vem de `v_reconquista.consultor` (`COALESCE(consultores.nome,
reconquista.consultor_nome, '(Sem Consultor)')`, migration 030) e a
Cobrança Consignável vem de `CONSULTOR` no frame de contratos. Cliente
reconquistado sem consultor resolvido cai no bucket `(Sem Consultor)` —
que não premia ninguém e não deve ser redistribuído.

### Cards do bloco Reconquista (UI)

`render_cards_reconquista`
([`src/dashboard/ui/kpi_cards_reforma.py`](../../src/dashboard/ui/kpi_cards_reforma.py))
passa de 4 para 3 cards:

| Antes | Depois |
|---|---|
| 📋 Elegíveis do mês | *removido* |
| ✅ Efetivadas | ✅ Efetivadas |
| ⏳ Promessas | ⏳ Promessas |
| 🎯 Sem reconquista | **Cobrança Consignável** (contagem do período) |

Elegíveis e "sem reconquista" **continuam existindo no cálculo** (base da
conversão e fila a trabalhar) — saíram apenas do bloco de cards. O bloco de
prévia (`_render_previa_reconquista`, mesmo módulo, rótulo "Clientes na
esteira") **não** muda.

> **LGPD:** `nu_matricula` **não** é armazenada. `co_adesao` identifica o
> contrato, não a pessoa.
