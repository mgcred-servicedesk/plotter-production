# 2026-07-03 — Reconquista: elegibilidade + faixa de prêmio (sem meta)

**Agente:** Claude Code
**Tipo:** feature (regra de negócio / data-layer / UI)
**Arquivos tocados:** `database/migrations/053_reconquista_flag_elegibilidade.sql`,
`src/dashboard/loaders.py`, `src/dashboard/ui/kpi_cards_reforma.py`,
`src/dashboard/tabs/analiticos.py`, `scripts/importar_reconquista.py`,
`docs/RECONQUISTA_V2_ETL.md`, `docs/agents/business-rules.md`
**Commit(s):** (não commitado)

## Objetivo

O arquivo de Reconquista ganhou a coluna `flag_elegibilidade`
(ELEGIVEL / NAO ELEGIVEL). A apuração passa a contar **só ELEGIVEL**
(mantendo todos os clientes nos analíticos), a **meta de 30% sai** e o
objetivo vira o **% de conversão**, mapeado numa faixa de prêmio/deflator
sobre o prêmio CNC.

## O que foi feito

- **053** — `ALTER TABLE reconquista ADD COLUMN flag_elegibilidade`
  (CHECK ELEGIVEL/NAO ELEGIVEL, nullable); `CREATE OR REPLACE VIEW
  v_reconquista` expõe a coluna (ao final); `CREATE OR REPLACE
  fn_importar_reconquista` persiste a flag (opcional → NULL).
- **loaders.py** — `_mask_elegivel` (NULL/sem flag ⇒ ELEGIVEL);
  `_faixa_premio_conversao` (mapeia % → ajuste/rótulo/cor);
  `_totais_reconquista` agora computa **conversão = EFETIVADA/elegíveis**
  + `total_geral`/`nao_elegivel` + `faixa`; `_por_loja_reconquista`
  restrito a elegíveis (`conversao_pct` + `faixa`); `carregar_reconquista`
  sem `meta`; removido `_RECONQUISTA_META`.
- **kpi_cards_reforma.py** — card de Reconquista sem meta; faixa de
  prêmio como banner (conversão % + rótulo colorido); "Clientes do mês"
  → "Elegíveis do mês" (com contexto de não elegíveis). Removidos imports
  órfãos `math` e `get_status_color` (top-level; usa o import local).
- **analiticos.py** — detalhamento com **todos** os clientes + coluna
  "Elegível" + filtro de Elegibilidade; por-loja com Conversão %/Faixa;
  caption com elegíveis + conversão.
- **ETL** — `scripts/importar_reconquista.py` envia `flag_elegibilidade`
  (via `getattr`, tolera arquivo antigo); doc de contrato atualizada.

Validação: faixas conferidas nas fronteiras (10→−20, 20→−10, 20,1→0,
30→+10, 40→+20); elegibilidade exclui NAO ELEGIVEL da conversão e mantém
no `total_geral`. 212 testes verdes, ruff limpo.

## Decisões não óbvias

- **NULL / sem flag ⇒ ELEGIVEL** (decisão do usuário) — interim até o
  arquivo com a flag ser importado; antes disso `v_reconquista` nem tem a
  coluna e `_mask_elegivel` retorna tudo-True (no-op, backward-compat).
- **Prêmio CNC = indicador, não R$** (decisão do usuário) — mostra só a
  faixa/ajuste (ex.: "+10% sobre prêmio CNC"); o valor monetário é apurado
  fora (folha/comissão).
- **Fronteiras contínuas** resolvem os micro-gaps da tabela (29,99/30 e
  39,99/40); limite superior inclusivo nas faixas negativas (20% ⇒ −10%).
- **Conversão restrita a elegíveis** nos dois lados (num. e den.); um
  EFETIVADA que seja NAO ELEGIVEL não entra.

## Pendências / follow-ups

- [ ] Aplicar **053** no Supabase e importar o arquivo novo (com a flag).
- [ ] **angry-man** (ETL recorrente) precisa enviar `flag_elegibilidade`
  no import de reconquista — mesmo contrato do script local. Fica junto
  do trabalho pendente do angry-man.

## Referências

- Base: [028](../../../database/migrations/028_reconquista_v2_tabela.sql),
  [029](../../../database/migrations/029_reconquista_v2_rpc_import.sql),
  [030](../../../database/migrations/030_reconquista_v2_view.sql)
- Docs: [business-rules.md](../business-rules.md#reconquista-v2),
  [RECONQUISTA_V2_ETL.md](../../RECONQUISTA_V2_ETL.md)
