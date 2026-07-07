# 2026-07-07 — Rankings: lojas e consultores sem produção (visão de controle)

**Agente:** Claude Code
**Tipo:** feature
**Arquivos tocados:** `src/dashboard/kpis/rankings.py`,
`src/dashboard/loaders.py`, `src/dashboard/tabs/rankings.py`, `app.py`,
`tests/test_kpis_rankings.py`, `tests/test_loaders.py`

## Objetivo

A aba Rankings listava apenas lojas/consultores **com** produção
(todos os rankings nascem de `groupby` sobre contratos com
`VALOR > 0`). Requisito: expor também quem NÃO produziu no período,
para controle de Gerentes Comerciais e Gestores. Na data da entrega
havia 99 consultores ativos sem produção invisíveis no dashboard.

## O que foi feito

- **Universos** (loaders): `carregar_universo_lojas(mes, ano)` — mês
  corrente usa lojas ATIVAS (`REGIAO := REGIAO_ATUAL`); histórico usa
  lojas com meta no período (proxy point-in-time já aceito em
  `_fetch_metas`). `carregar_consultores_ativos()` — cadastro ativo
  com loja-base ativa, `[CONSULTOR, LOJA, REGIAO, REGIAO_ATUAL]`,
  TTL 24h, global (recorte client-side via `aplicar_rls`).
- **KPI**: parâmetro opcional `df_universo` em
  `calcular_ranking_lojas/consultores/pontos` — entidades do universo
  ausentes entram zeradas (Qtd/Valor/Pontos/Atingimento/Ticket = 0) no
  fim do ranking (ordenação estável + zerados alfabéticos). Nova
  `listar_sem_producao(df, df_universo, tipo, df_supervisores)` para o
  bloco de controle. Match cadastro × produção por nome normalizado
  (trim + upper).
- **UI** (sub-abas Lojas, Consultores e Regiões):
  - Visões globais Top N: expander **"⚠ Sem produção no período (N)"**
    abaixo do par de rankings, com export CSV (Top N intacto — os
    zerados ficariam cortados dentro dele).
  - Visões por região (listas completas): zerados entram **no** ranking
    com posição; regiões só com zerados agora aparecem no
    seletor/expanders (união produção ∪ universo); `top_n` dessas
    visões passou de `len(df_reg)` para `_SEM_LIMITE` (o proxy por
    contagem de linhas estourava com o universo).
  - Flag "Somente dados da região" recorta também os universos
    (`_filtrar_somente_regiao` agora retorna `(df, regioes)`).
  - **Por Produto** (follow-up do usuário na mesma sessão): dentro do
    expander de cada produto, abaixo do ranking pinned, lista
    "⚠ Sem produção em <produto>: N" com quem não vendeu AQUELE
    `grupo_dashboard` (mesmo critério VALOR > 0 recortado pelo grupo),
    com export CSV. Sem expander aninhado (Streamlit não permite) —
    caption + tabela direto (`_render_sem_producao_produto`).
- **Visibilidade**: só `admin`/`gestor`/`gerente_comercial`
  (`_PERFIS_CONTROLE`); demais perfis têm os universos zerados no
  início do render (fail-closed). Gerente enxerga só sua região:
  `app.py` aplica `aplicar_rls` (por `REGIAO_ATUAL`) nos universos
  antes de passar à aba.
- **Testes**: +13 em `test_kpis_rankings.py` (universo zerado,
  exclusão de supervisor, normalização, região toda zerada, corte do
  Top N) e +3 em `test_loaders.py` (`carregar_universo_lojas` com
  fontes monkeypatched). Suíte completa: 238 passed.

## Decisões não óbvias

- **"Sem produção" = ausente do ranking (nenhum contrato `VALOR > 0`)**
  — espelha o critério dos rankings; quem só emitiu (valor zerado na
  consolidação) conta como sem produção. Evita zona cega: toda entidade
  ativa está ou no ranking ou na lista. Decisão validada com o usuário.
- **Bloco separado no Top N, inline nas listas completas** — zerados
  dentro do Top N ficariam cortados (ficam no fim); decisão validada
  com o usuário, junto com visibilidade e escopo de sub-abas.
- **Por Produto entrou; Por Aceleradores segue fora** — a decisão
  inicial deixava ambos fora, mas o usuário reverteu para Por Produto
  no follow-up ("zerados em produção de determinados produtos").
  Aceleradores continuam sem lista de zerados: o critério lá é por
  flag booleana (`is_bmg_med` etc.), não `VALOR > 0` — se for
  desejado, precisa de critério próprio por máscara, não do
  `listar_sem_producao` atual.
- **Matching por nome é confiável**: validado com dados reais
  (jul/2026) — 110/110 consultores da produção têm match exato no
  cadastro (nomes vêm da mesma FK). Normalização trim+upper é cinto de
  segurança.
- **Consultores sem vigência temporal**: o cadastro não tem ledger
  (diferente de `loja_regiao_vigencia`) — em meses históricos o
  universo de consultores reflete o organograma de HOJE. Limitação
  aceita e documentada na docstring do loader.
- **Status do cadastro**: valores reais são `Ativo (a)`,
  `Desligado (a)`, `Licença Maternidade`, `Licenciado (a)`; o filtro
  `"ativo" in status.lower()` (mesmo de `carregar_consultores_cadastro`)
  mantém só `Ativo (a)` — licenças NÃO aparecem como "sem produção".
- **Supervisores excluídos do universo consultor** (regra de negócio
  "supervisores não aparecem em análises consultor-level"), aplicado
  via `excluir_supervisores` tanto no ranking quanto na lista.

## Pendências / follow-ups

- [ ] Validar visualmente com perfis reais (gerente comercial deve ver
      só sua região no bloco; supervisor/consultor não devem ver o
      bloco).
- [ ] Avaliar vigência temporal para consultores (ledger análogo a
      `loja_regiao_vigencia`) se o histórico de "sem produção" por mês
      passado se mostrar relevante.

## Patterns criados ou atualizados

- (nenhum)

## Referências

- Decisões de produto confirmadas pelo usuário em 2026-07-07 (exibição,
  visibilidade, definição de sem produção, escopo de sub-abas).
- Precedente do universo de lojas ativas: filtro de lojas do gerente em
  `app.py` (`aplicar_rls(carregar_lojas_ativas())`).
