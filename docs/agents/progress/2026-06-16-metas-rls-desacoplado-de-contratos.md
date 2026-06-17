# 2026-06-16 — Total de metas desacoplado da presença de contratos

**Agente:** Claude Code
**Tipo:** bugfix
**Arquivos tocados:** `src/dashboard/rls.py`, `src/dashboard/loaders.py`, `app.py`
**Commit(s):** (não commitado)

## Objetivo

O total global de metas (ex.: Prata e CNC de junho/2026) não batia com o
banco. A loja HELP PAVUNA (recém-aberta, com metas mas sem nenhum contrato
no período) não aparecia no total.

## O que foi feito

- `aplicar_rls_metas` agora é **ciente do perfil** (espelha `aplicar_rls`):
  - `admin`/`gestor` → metas sem filtro;
  - `gerente_comercial` → filtra por `REGIAO`;
  - `supervisor` → filtra por `LOJA`;
  - `consultor` → mantém aproximação por lojas onde tem contratos.
  Antes a função ignorava o perfil e sempre interseccionava as metas com as
  lojas presentes nos contratos — derrubando lojas com meta e zero contrato.
- `_fetch_metas` e `_fetch_metas_produto` passaram a:
  - trazer a coluna `REGIAO` (via `lojas!inner(nome, regioes(nome))`),
    necessária para o filtro RLS por região sem depender de contratos;
  - no **mês corrente**, contar apenas lojas `ativo = true`
    (`.eq("lojas.ativo", True)`). No histórico, preservam todas as lojas que
    tinham meta (decisão do usuário).
- Novo helper `_filtrar_metas_ui` em `app.py` separa o **filtro granular da
  sidebar** (loja/consultor) do RLS de perfil. Antes `aplicar_rls_metas` era
  reutilizada para os dois papéis; com a versão ciente de perfil isso quebraria
  o filtro da sidebar para admin/gestor.

## Decisões não óbvias

- **Filtro `ativo` só no mês corrente** — filtrar pelo `ativo` atual no
  histórico apagaria retroativamente metas de lojas que fecharam depois.
  Decisão explícita do usuário: histórico mantém todas; mês corrente só ativas.
- **RLS de metas via escopo de perfil, não via contratos** — usar "lojas com
  contrato" como proxy do escopo era a origem do bug. Loja ativa no escopo deve
  contar a meta mesmo sem vendas (ex.: loja inaugurada ontem).
- **Coluna `REGIAO` nas metas é segura para os totais** — os KPIs globais somam
  colunas nomeadas (`META_PRATA`, `CNC`, ...) em `kpis/gerais.py`, não somam o
  DataFrame inteiro; a coluna string não entra em nenhuma soma.
- Caso inverso confirmado: **DIGITAL** é ativa, tem contratos e **nenhuma meta**
  → continua na produção com meta 0 (não é afetada; metas só listam lojas com
  meta cadastrada).

## Pendências / follow-ups

- [ ] `aplicar_rls_supervisores` continua sendo reutilizada no filtro de UI
      (`app.py` ~L980); para admin/gestor ela não estreita por loja selecionada.
      Não tocado (fora do escopo de metas) — avaliar se é o comportamento desejado.

## Referências

- Docs consultados: [docs/agents/data-layer.md](../data-layer.md),
  [docs/agents/rls.md](../rls.md)
