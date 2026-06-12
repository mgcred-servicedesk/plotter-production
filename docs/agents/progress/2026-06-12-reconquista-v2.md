# 2026-06-12 — Reconquista v2 (novo layout + regras por status)

**Agente:** Claude Code
**Tipo:** feature / refactor
**Arquivos tocados:** `database/migrations/028..030`, `scripts/importar_reconquista.py`, `src/dashboard/loaders.py`, `src/dashboard/ui/kpi_cards_reforma.py`, `src/dashboard/tabs/analiticos.py`, `docs/agents/business-rules.md`
**Commit(s):** (pendente)

## Objetivo

Trocar a apuração do Reconquista. A fonte passa a ser o export
`reconquista.xlsx` (aba `Export`), 1 linha por cliente, já classificado
em `de_status_reconquista` (EFETIVADA / PROMESSA / SEM RECONQUISTA).
Truncar a base e realimentar conforme o novo layout.

## O que foi feito

- **Tabela nova `reconquista`** (migration 028), 1 linha por `co_adesao`,
  com `status`, datas (dt_fim_relacionamento, dt_macica, dt_dna,
  dt_producao), origem/hierarquia e `link_aceite`. `nu_matricula` **não**
  é armazenada (LGPD).
- **RPC `fn_importar_reconquista(p_rows JSONB)`** (migration 029):
  `TRUNCATE` + resolve `loja_id` (cod_bmg + sucessora) e `consultor_id`
  (nome completo + loja) + `INSERT`, atômico.
- **View `v_reconquista`** (migration 030): detalhe por cliente com
  loja/região/consultor rotulados e `ref_ano`/`ref_mes` (de
  dt_fim_relacionamento). KPIs e quebra por loja são derivados no loader.
- **Script `scripts/importar_reconquista.py`**: lê o xlsx, monta o payload
  e chama a RPC. Valida a quebra mensal antes de enviar.
- **Loader** `carregar_reconquista(mes, ano)` reescrito: aplica a
  **defasagem de 1 mês**, RLS por perfil e deriva totais + por_loja.
- **Cards** minimalistas: Clientes do mês / Efetivadas (taxa vs meta 30%)
  / Promessas / Sem reconquista.
- **Analítico**: abas Por Loja + Detalhamento (com link de aceite).
  Aba "Resistentes" removida (não há mais snapshots/aparições).

## Regras (validadas 100% contra o arquivo, 1621/1621)

- **EFETIVADA** ⟺ `dt_macica > dt_fim_relacionamento`.
- **PROMESSA** ⟺ (`dt_dna > dt_fim_relacionamento` **ou**
  `dt_producao > dt_fim_relacionamento`, exceto antecipação) e não-efetivada.
- **SEM RECONQUISTA** ⟺ caso contrário.
- **Apuração mensal por `dt_fim_relacionamento`** com **defasagem de 1 mês**:
  o mês de apuração M exibe os contratos com `dt_fim` em M-1.
  Ex.: apuração Jun/2026 → dt_fim Mai/2026 (0/33/288). Apuração Mai → Abr
  (36/23/249).
- **Meta = 30%** (taxa = EFETIVADA / total).

## Decisões não óbvias

- **Confiar em `de_status_reconquista` do arquivo** em vez de recalcular
  no banco — as regras de data reproduzem a coluna com 100% de match; o
  banco é a fonte. As datas ficam guardadas para auditoria/recálculo.
- **Tabela nova em vez de truncar `reconquista_snapshot`** — o modelo v1
  (snapshots por envio + flags + maciças) não mapeia no novo (1 linha,
  3 estados). Tabela limpa evita ALTER/mistura de modelos.
- **Defasagem aplicada no loader** (não na view) — a view expõe o mês real
  de `dt_fim`; o loader mapeia mês de apuração → mês anterior. Mantém a
  view reutilizável.
- **KPIs/por_loja derivados em pandas** (≤1621 linhas) a partir de
  `v_reconquista` — cards e tabela vêm da mesma fonte (consistência) e
  evita uma 2ª view agregada.
- **EFETIVADA "zerada" em Mai (apuração Jun) é esperado** — depende de
  `dt_macica > dt_fim`; quando a maciça desses contratos virar (novo
  `dt_macica` no próximo export), eles migram para EFETIVADA.

## Pendências / follow-ups

- [x] **Migrations 028/029/030** aplicadas no Supabase (pelo dono).
- [x] Carga rodada (`scripts/importar_reconquista.py`): 1621 inseridos,
      0 sem_loja, 122 sem_consultor. Validado vs BI (Abr 36/23/249,
      Mai 0/33/288).
- [x] `docs/RECONQUISTA_MIGRATION.md` marcado como histórico (v1).
- [x] Spec do ETL v2 (contrato arquivo→RPC): `docs/RECONQUISTA_V2_ETL.md`.
- [ ] **Aplicar `031_reconquista_drop_v1.sql`** (DESTRUTIVO — remove
      `macicas`, `reconquista_snapshot` ~6410 linhas, views/RPCs v1).
      Criada, **não aplicada**. `lojas.sucessora_id`/`ativo` mantidos
      (sucessora_id é usado pela RPC v2).
- [ ] **sem_consultor (122 linhas / 67 nomes)**: 18 nomes casariam
      ignorando acento/caixa (arquivo sem acento vs cadastro com acento) —
      recuperáveis com `unaccent` no match (exige extensão + migration 032,
      a confirmar). 49 nomes são ausências reais do cadastro
      (conciliação operacional). `consultor_nome` bruto fica persistido.
- [ ] ETL recorrente no `angry-man`: portar o contrato de
      `docs/RECONQUISTA_V2_ETL.md`.

## Referências

- Docs consultados: [business-rules.md](../business-rules.md),
  [data-layer.md](../data-layer.md), [rls.md](../rls.md)
- Fonte: `reconquista.xlsx` (aba `Export`, 22 colunas)
