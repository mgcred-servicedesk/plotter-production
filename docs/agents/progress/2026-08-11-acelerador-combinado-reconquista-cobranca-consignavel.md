# 2026-08-11/12 — Acelerador combinado (Reconquista + Cobrança Consignável): implementação completa

**Agente:** Claude Code (orquestração da feature; subagentes `data-layer-supabase`
e `streamlit-ui-specialist` em paralelo a partir do plano aprovado + edição
direta para follow-ups/bugfixes)
**Tipo:** feature (+ 2 bugfixes de follow-up)
**Arquivos tocados:** `database/migrations/065_contratos_valor_bruto.sql`,
`database/migrations/066_faixas_acelerador_reconquista.sql`,
`src/dashboard/loaders.py`, `src/dashboard/ui/kpi_cards_reforma.py`
**Commit(s):** —

## Objetivo

Implementar o acelerador combinado (Reconquista + Cobrança Consignável)
vigente a partir de 08/2026: quebra por consultor, contagem de Cobrança
Consignável, resolução de faixa/prêmio via tabela configurável no banco, e
as regras de visibilidade por perfil — depois fechar os bugs de universo de
consultores reportados em produção.

## O que foi feito

### 08/11 — Camada de dados (base)

- `_por_consultor_reconquista(clientes)` — espelho de `_por_loja_reconquista`
  agrupando por `consultor` (mesma base elegível, mesmos 3 estados).
- `carregar_cobranca_consignavel(mes, ano)` + `_fetch_*` + par de caches
  `_atual` (30min) / `_historico` (24h) — contratos que satisfazem
  `PAGO AO CLIENTE` ∧ `TIPO OPER. = CONTRATO NOVO` ∧ `SUBTIPO = NOVO` ∧
  `BANCO ∈ {BMG, BANCO BMG}` ∧ `|VLR BRUTO − VLR BASE| > 0,005`.
- `carregar_faixa_acelerador(qtd, mes, ano)` + `_fetch_*` + caches
  `_atual` (6h) / `_historico` (24h), e `_faixas_acelerador_por_qtd`
  (1 RPC por contagem **distinta**, não por consultor).
- `_por_consultor_acelerador(clientes, mes, ano)` — compõe tudo e aplica o
  gate; `carregar_reconquista` passa a devolver `por_consultor` e
  `totais["cobranca_consignavel"]` / `totais["acelerador_no_escopo"]`.

### 08/11 — Contagem visível a admin/gestor/gerente_comercial

Decisão do usuário após validar em produção: a **contagem** de Cobrança
Consignável (card do topo) deve valer para qualquer perfil a partir da
vigência, não só consultor/supervisor; a **faixa** e a tabela detalhada
continuam exclusivas de consultor/supervisor.

- Novo gate `_acelerador_vigente(mes, ano)` — só checa data, sem perfil.
- `_acelerador_no_escopo` (perfil + data) mantido como gate do
  **detalhado** (`por_consultor` + faixa), não mais da contagem.
- `totais["cobranca_consignavel"]` passa a ser calculado direto via
  `aplicar_rls(carregar_cobranca_consignavel(mes, ano))` contado (`len`),
  independente de perfil — RLS natural de cada perfil escopa o número.

### 08/11 — Faixa agregada vinda do banco (`is_deflator`)

- Migration 066 (**não aplicada** — editada in-place com autorização
  explícita do orquestrador, ainda não commitada): coluna `is_deflator
  BOOLEAN NOT NULL DEFAULT false`, seed `true` só na faixa "0 a 2", e
  `RETURNS TABLE` da RPC `obter_faixa_acelerador_reconquista` ganhando
  `is_deflator`.
- `loaders.py`: `_fetch_faixa_acelerador` propaga `is_deflator`; novo
  `_faixa_agregada_acelerador(totais, mes, ano)`; `carregar_reconquista`
  expõe `totais["faixa_agregada"]` e `totais["acelerador_perfil"]`.

### 08/11 — Barra-resumo restrita a perfil `consultor`

`render_cards_reconquista` passa a ler `totais["acelerador_perfil"]` e
`totais["faixa_agregada"]` e decidir em 3 vias: (1) `consultor` + faixa
presente → regime novo (número combinado + rótulo de deflator/prêmio
vindo de `is_deflator`); (2) `consultor` + faixa ausente (apuração
anterior a 08/2026) → regime antigo (% conversão); (3) qualquer outro
perfil → nenhuma barra renderiza, só cards/tabelas existentes. Markup
duplicado dos regimes 1/2 extraído para `_render_barra_reconquista`.

### 08/11 — Bugfix: vazamento de consultores inativos em `por_consultor`

Reportado pelo usuário (Supervisor, loja HELP ALCANTARA CARREFOUR,
08/2026): tabela mostrava consultores desligados.

- Causa: universo da tabela era **união** de `carregar_consultores_ativos()`
  ∪ nomes com produção em `rec`/`cobr` — não a restrição ao roster ativo.
  Um consultor desligado com cliente elegível de reconquista no período
  reaparecia via `rec`.
- Corrigido: universo passa a ser **só** o roster ativo; `rec`/`cobr`
  apenas enriquecem contagem de quem já está no universo, nunca adicionam
  linha nova.

### 08/11 — Fechamento de decisões (rótulo + assimetria de janela)

- Rótulo divergente da última faixa reconciliado: migration 066 tinha
  "Maior que 9" (literal da tabela original), business-rules.md tinha
  "9 ou mais" (semanticamente correto, já que 9 exato entra na faixa) —
  migration atualizada para "9 ou mais" em todas as ocorrências.
- **Assimetria de janela confirmada como intencional pelo usuário**: a
  Reconquista mantém a defasagem de 1 mês (`dt_fim_relacionamento`); a
  Cobrança Consignável conta só o mês da própria apuração
  (`data_status_pagamento`), sem defasagem. Não é bug.

### 08/12 — Bugfix: supervisor listado como consultor da própria equipe

Reportado pelo usuário (perfil Supervisor): tabela lista o próprio
supervisor como consultor da equipe.

- Causa: `aplicar_rls` para `supervisor` filtra só por LOJA
  (`src/dashboard/rls.py:86`), sem distinção de papel; o cadastro de
  `consultores` (RH) duplica a maioria dos supervisores como consultor
  ativo da própria loja (47 de 52 — esperado, ver progress
  `2026-07-09-supervisor-como-consultor-exclusao-global.md`). A regra já
  estava documentada em `business-rules.md:597-598` mas não implementada
  na feature nova.
- Fix: `universo = excluir_supervisores(universo, carregar_supervisores())`
  logo após montar o universo, antes do merge com `rec`/`cobr`.
- **Refinamento pedido pelo usuário**: excluir só o nome zerado do
  esqueleto, não a produção real. Novo helper `_juntar_producao` fatora o
  merge nomes×rec×cobr; produção de supervisor isolada em `bloco_sup` —
  só vira linha se `efetivadas + cobranca_consignavel > 0`, rotulada
  `"<nome> (Supervisor)"` (padrão de `tabs/produtos.py`), anexada
  **depois** do sort dos consultores reais.

## Decisões não óbvias

- **Threshold do deflator não é mais hardcoded.** Antes: `acelerador <= 2`
  em Python. Agora: `faixa_agregada["is_deflator"]`, resolvido pela RPC
  contra a tabela configurável — se a faixa negativa mudar no banco, a
  barra acompanha sozinha.
- **`DROP FUNCTION` antes do `CREATE OR REPLACE`** na 066: `CREATE OR
  REPLACE` não altera tipo de retorno de função existente. Mesma razão
  para `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` ao lado do `CREATE
  TABLE IF NOT EXISTS`.
- **`acelerador_no_escopo` continua `True` para supervisor.** A restrição
  "só consultor" na barra-resumo é de **apresentação** (soma da equipe,
  prêmio é por consultor individual); a contagem e a tabela
  `por_consultor` seguem valendo para os dois perfis.
- **`faixa_agregada = None` quando não há faixa**, nunca uma faixa
  default — mesmo contrato de "sem linha = recurso desligado" da RPC.
- **Por que a contagem não deriva mais de `por_consultor`**: os dois
  passaram a ter gates diferentes (`por_consultor` vazio por design para
  admin/gestor/gerente_comercial); somar a partir dele sempre daria 0
  pra esses perfis. Para consultor/supervisor os dois ainda batem, porque
  derivam do mesmo `aplicar_rls(carregar_cobranca_consignavel(...))`.
- **Por que o vazamento de inativos não era bug de cache/RLS**:
  `carregar_consultores_ativos` já excluía a consultora desligada
  corretamente — o bug estava na composição do universo da tabela
  (lógica de merge), não na fonte de "ativos". "Atualizar dados" não
  resolvia porque os dados já estavam certos.
- **Trade-off aceito no fix de inativos**: consultor ativo cujo nome só
  aparece em `rec`/`cobr` (nunca no roster, ex.: cadastro atrasado em
  relação ao upload do angry-man) deixa de aparecer na tabela. Julgado
  correto — fonte de verdade de "quem é ativo" é o cadastro, não "quem
  produziu" ([[project_universo_consultores_vai_e_vem]]).
- **Período da Cobrança Consignável é `(mes, ano)` da apuração**, sem a
  defasagem da reconquista — confirmado intencional (ver "Fechamento de
  decisões" acima).
- **Filtro server-side por `periodo_id`, não por range de data** —
  índices de data foram reduzidos nas migrations 055/060 (compute Nano).
  Mês reconferido no frame (`DATA.dt.month/year`) como defesa contra erro
  do ETL no `periodo_id`.
- **`_norm_texto` replicado em vez de importar de `tabs/produtos.py`** —
  camada de dados não depende de UI (`architecture.md`). Conjunto de
  bancos aqui é mais estreito que a flag "BMG/Help" de Produtos: HELP não
  entra.
- **Comparação por tolerância (0,005)** entre VLR BRUTO e VLR BASE evita
  ruído de float; `valor_bruto` ausente neutralizado com `fillna(VALOR)`
  (mesmo efeito do `COALESCE` da view 065, defesa se a migration ainda
  não estiver aplicada).
- **RLS fora do cache** — `carregar_cobranca_consignavel` devolve dados
  globais; `aplicar_rls` só em `_por_consultor_acelerador`. Cachear
  pós-RLS envenenaria a chave entre perfis.
- **Equipe do supervisor derivada do escopo do perfil** (fail-closed do
  RLS), não de `carregar_supervisores()` (cadastro de RH, pode ser mais
  largo que o escopo concedido — seria vazamento).
- **Falha de RPC/coluna ausente degrada com `logger.exception`**
  (migrations 065/066 ainda não aplicadas) — aba renderiza com contagem
  0/rótulo vazio, erro fica no log. Não é o padrão dos demais `_fetch_*`
  (que propagam); restrito a estes dois pontos.
- **Import direto de `excluir_supervisores` em vez de replicar**: a regra
  "camada de dados não depende de UI" é sobre `tabs/` (UI), não sobre
  `kpis/` — `loaders.py` já importa de `kpis/gerais.py` e
  `kpis/detalhes_cards.py`, sem risco de import circular.
- **Card agregado não é afetado pela exclusão de supervisor** —
  `totais["cobranca_consignavel"]` continua somando direto sobre RLS, sem
  passar por `universo`/`excluir_supervisores`: se o supervisor tiver
  contrato em nome próprio, ainda conta no total agregado (consistente
  com "Produção de supervisor — conta pro total, marcada, fora do
  ranking" em business-rules.md).

## Verificação

Cada etapa foi verificada com `.venv/bin/ruff check` limpo (nos arquivos
tocados e `src/ app.py`) e `.venv/bin/python -m pytest tests/` — 483
passed, mantido estável ao longo de toda a feature. Simulações manuais
específicas:

- 3 regimes da barra-resumo (consultor+deflator, consultor+faixa
  positiva, consultor fora da vigência, supervisor) via inspeção de
  `st.markdown` renderizado.
- 5 perfis (`gestor`/`admin`, `gerente_comercial`, `supervisor`,
  `consultor`) para agosto/2026 confirmando contagem e escopo da tabela
  detalhada.
- Vazamento de inativos: tabela passou de 6 para 5 linhas na loja HELP
  ALCANTARA CARREFOUR, consultora desligada removida.
- Supervisor como consultor: consultor real sem produção aparece com 0;
  supervisor sem produção não aparece; supervisor com produção aparece
  como última linha rotulada, fora do sort.

## Pendências / follow-ups

- [ ] Aplicar as migrations 065/066 no Supabase (ainda não executado —
      até lá, Cobrança Consignável fica em 0/vazio por design, não é bug).
- [ ] Testes automatizados em `tests/test_loaders.py`/`test_ui_cards.py`
      para: os 5 perfis, consultor desligado com produção, supervisor
      duplicado como consultor, os 3 regimes da barra-resumo. Só houve
      simulação manual até aqui.
- [ ] `angry-man` precisa popular `valor_bruto`/`valor_liquido`
      (`HEADER_MAP` em `src/services/import-contratos.ts`, outro
      repositório) — sem isso a contagem é estruturalmente 0.
- [ ] Validar com o usuário: perfis fora do gate (`admin`/`gestor`/
      `gerente_comercial`) continuam com `cobranca_consignavel = 0` nos
      cards da tabela detalhada (não a barra) — ainda não perguntado
      explicitamente.
- [ ] Sinalizado, não corrigido: `business-rules.md:400-402` documenta
      que consultores do Vai e Vem não devem entrar nos "aceleradores por
      consultor" — `_por_consultor_acelerador` não filtra
      `LOJAS_BACKOFFICE` hoje. Mesma categoria de gap (regra documentada,
      não implementada nesta feature).

## Patterns criados ou atualizados

- Nenhum novo pattern formal. Reuso confirmado de padrões existentes:
  rótulo `"<nome> (Supervisor)"` de `tabs/produtos.py` e
  `excluir_supervisores` de `src/dashboard/kpis/gerais.py`.

## Referências

- Plano aprovado: `~/.claude/plans/para-o-m-s-de-toasty-canyon.md`
- Docs consultados: [data-layer.md](../data-layer.md), [rls.md](../rls.md),
  [architecture.md](../architecture.md),
  [business-rules.md](../business-rules.md),
  [rpi-workflow.md](../rpi-workflow.md)
- Progress relacionado (pré-existente):
  `2026-07-09-supervisor-como-consultor-exclusao-global.md`
- Memória: [[project_universo_consultores_vai_e_vem]]

_Esta entrada consolida 7 progress separados da mesma feature
(2026-08-11 a 2026-08-12), compactados antes do primeiro commit para
reduzir redundância entre pendências repetidas._
