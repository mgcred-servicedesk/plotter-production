# 2026-05-15 — Plano: Meta Capped (Realizado Elegível) nos cards principais

**Agente:** Claude Code (Opus 4.7)
**Tipo:** research / plano de feature (aguardando aprovação para implementar)
**Arquivos previstos:** `app.py`, `src/dashboard/kpis/gerais.py` (e leitores: `src/dashboard/ui/kpi_cards_reforma.py`, `src/dashboard/ui/resumo_executivo.py`, `src/dashboard/ui/prioridades_acao.py`)
**Commit(s):** — (nenhum; este documento é apenas plano)
**Status:** PLANEJADO — implementar somente após aprovação explícita do usuário.

## Objetivo

Trocar o cálculo dos KPIs **% Meta Atingida**, **% Projeção** e **Falta para Meta** (cards principais do dashboard) de uma comparação "soma de realizado ÷ soma de metas" para uma comparação **Realizado Elegível ÷ Meta Total**, onde o realizado de cada produto é **limitado (capped) à própria meta** antes de somar.

Motivação: hoje, um único produto com forte superávit pode "cobrir" o déficit dos demais e induzir a leitura de meta batida no agregado, mesmo com outros produtos zerados. O capping por produto elimina essa distorção.

## Contexto / problema

- O dashboard exibe três cards principais (em `render_kpis_principais` de [src/dashboard/ui/kpi_cards_reforma.py:43-134](../../../src/dashboard/ui/kpi_cards_reforma.py#L43-L134)):
  - 💰 **Pagos** — total bruto realizado + projeção em R$.
  - 📊 **% Meta Atingida** — `perc_ating_valor` = `total_vendas / meta_mix * 100`.
  - 🎯 **Falta para Meta** — `gap_valor` = `max(0, meta_mix - total_vendas)`; e meta diária restante = `gap_valor / du_restantes`.
- `perc_ating_valor` e `gap_valor` são calculados em [app.py:1074-1084](../../../app.py#L1074-L1084), usando `total_vendas` (faturamento bruto) e `meta_mix` (soma das metas por produto, vinda de `calcular_kpis_gerais` em [src/dashboard/kpis/gerais.py:97-112](../../../src/dashboard/kpis/gerais.py#L97-L112)).
- Como `total_vendas` é a soma bruta de todos os produtos (inclusive superávit), o numerador pode ultrapassar uma meta individual sem que isso signifique cumprimento global.

### Exemplo numérico (consultora, 9º DU de 20)

| Produto         | Realizado    | Meta         | Realizado Capped |
|-----------------|-------------:|-------------:|-----------------:|
| CNC             | 13.569,48    | 35.000,00    | 13.569,48        |
| CLT             | 0,00         | 12.000,00    | 0,00             |
| SAQUE           | (excluído — sem meta) | —    | —                |
| Consignado      | 42.899,64    | 69.000,00    | 42.899,64        |
| FGTS/Ant.Ben.   | 2.864,02     | 7.000,00     | 2.864,02         |
| **Total elegível** | —          | **123.000,00** | **59.333,14**    |

- **% Meta Atingida (capped):** 59.333,14 / 123.000,00 = **48,24%**
- **Gap (capped):** 123.000,00 − 59.333,14 = **R$ 63.666,86**
- **Meta diária restante:** 63.666,86 / (20 − 9) = **R$ 5.787,90/DU**

Teste do caso problemático — se Consignado fosse R$ 80.000 (estouro de R$ 11.000):
- Realizado bruto total = 96.433,50 (≈78% se calculado pelo método antigo).
- Realizado capped = 13.569,48 + 0 + 69.000,00 + 2.864,02 = **85.433,50 → 69,46%**. ✅ Sem indução de meta batida.

## Modelo conceitual

**Realizado Elegível por produto** = `min(realizado_produto, meta_produto)` para todo produto **com meta cadastrada > 0**.

- Produtos sem meta (ex.: SAQUE hoje) ficam **fora do numerador e do denominador** do %. Continuam somando normalmente no card de Pagos (faturamento bruto).
- A **Meta Total Elegível** é a soma das metas dos produtos que têm meta cadastrada — equivalente ao `meta_mix` atual, mas com o entendimento explícito de que produtos sem meta não contribuem.
- A **Projeção capped** também precisa ser construída produto a produto: projetar realizado por produto pelo ritmo atual → aplicar `min(projecao_produto, meta_produto)` → somar → dividir pela meta total elegível.

## Decisões já tomadas (validadas com o usuário em 2026-05-15)

1. **Card de Pagos (R$):** continua mostrando faturamento **bruto** (com superávit) e projeção bruta. O capping só alimenta os cards de **% Meta** e **Falta**.
2. **SAQUE / produto sem meta:** fora do cálculo de % Meta e Falta. No card de Pagos, soma normalmente.
3. **Projeção do % Meta:** capping aplicado por produto **antes** de somar a projeção, espelhando a regra do realizado.
4. **Produto novo sem meta cadastrada:** segue a mesma regra do SAQUE (excluído do % Meta e Falta) até que receba meta.
5. **"Quanto falta":** mantém um único valor agregado no card. A responsabilidade de "onde focar" continua nos cards por produto/mix existentes (não duplicar detalhamento aqui).

## Mudanças propostas (mapa de implementação)

### 1. Núcleo do cálculo — `src/dashboard/kpis/gerais.py`

Em `calcular_kpis_gerais`, calcular três novos campos:

- `realizado_elegivel` — soma de `min(realizado_produto, meta_produto)` para produtos com meta > 0.
- `meta_elegivel` — soma das metas dos produtos com meta > 0 (efetivamente o `meta_mix` atual, mas com o filtro `meta > 0` explícito; manter `meta_mix` como alias para não quebrar leitores).
- `projecao_elegivel` — soma de `min(projecao_produto, meta_produto)`, com `projecao_produto = (realizado_produto / du_decorridos) * du_total`.

Implementação prática:
- Hoje `meta_mix` é montado em [src/dashboard/kpis/gerais.py:97-112](../../../src/dashboard/kpis/gerais.py#L97-L112) a partir de `df_metas_produto`. O realizado por produto precisa vir de um agrupamento de `df` pelas mesmas colunas/categorias de produto que as metas usam — verificar como `prioridades_acao.py` faz (já agrupa por produto em [src/dashboard/ui/prioridades_acao.py:89-126](../../../src/dashboard/ui/prioridades_acao.py#L89-L126), provavelmente reutilizável).
- Atenção: a granularidade do agrupamento precisa **bater 1-pra-1** com a granularidade das metas (ex.: a coluna PRODUTO no `df` precisa mapear para as colunas CNC/CLT/SAQUE/CONSIGNADO/FGTS_ANT_BEN_CNC13 das metas). Validar antes de codar — pode haver um normalizador já existente.

### 2. Substituir o cálculo de % e gap — `app.py:1074-1084`

Trocar:

```python
meta_global_valor = float(kpis.get("meta_mix", 0) or 0)
total_vendas_valor = float(kpis.get("total_vendas", 0) or 0)
kpis["perc_ating_valor"] = (total_vendas_valor / meta_global_valor * 100) if ...
kpis["gap_valor"] = max(0, meta_global_valor - total_vendas_valor)
```

Por:

```python
meta_elegivel = float(kpis.get("meta_elegivel", 0) or 0)
realizado_elegivel = float(kpis.get("realizado_elegivel", 0) or 0)
projecao_elegivel = float(kpis.get("projecao_elegivel", 0) or 0)
kpis["perc_ating_valor"] = (realizado_elegivel / meta_elegivel * 100) if meta_elegivel > 0 else 0
kpis["gap_valor"] = max(0, meta_elegivel - realizado_elegivel)
kpis["perc_proj_valor"] = (projecao_elegivel / meta_elegivel * 100) if meta_elegivel > 0 else 0
```

`total_vendas` permanece como está (alimenta o card Pagos bruto).

### 3. Card % Meta — `src/dashboard/ui/kpi_cards_reforma.py:70-104`

- Linha 75: `perc_proj = (projecao / meta_mix * 100) ...` → usar `kpis["perc_proj_valor"]` (capped) em vez de recalcular a partir da `projecao` bruta.
- Linha 102: o sub-rótulo "MIX: {meta_mix_fmt}" pode continuar mostrando a meta total elegível (sem mudança visual de copy, mas vale revisar o texto para deixar explícito se desejado — sugestão: manter como está para não introduzir mudança de UX além do necessário).

### 4. Card Falta — `src/dashboard/ui/kpi_cards_reforma.py:106-127`

- `gap` já lê `kpis["gap_valor"]` — passa a refletir o cálculo capped automaticamente.
- Linha 108: `gap_por_dia = gap / du_restantes` permanece — mas agora o gap é honesto.

### 5. Resumo executivo e prioridades — leitores existentes

- [src/dashboard/ui/resumo_executivo.py:131-133](../../../src/dashboard/ui/resumo_executivo.py#L131-L133) já lê `perc_ating_valor` e `gap_valor` — passa a refletir o novo cálculo automaticamente, sem alteração.
- [src/dashboard/ui/prioridades_acao.py](../../../src/dashboard/ui/prioridades_acao.py) usa `gap_valor` em vários pontos (linhas 835, 866, 985, 1239, 1262, 1643). **Revisar caso a caso** se o gap capped continua semanticamente coerente nesses lugares — provavelmente sim, mas precisa ler o uso em contexto. Em particular:
  - `prioridades_acao.py:101` já calcula `gap_valor = max(0, meta_total - valor_atual)` **por produto** (não global). Esse cálculo por produto **já é naturalmente capped** quando agregado → não precisa de mudança. Apenas o agregado global muda.

### 6. Testes

- Adicionar caso de teste em `tests/` cobrindo:
  - Cenário do exemplo acima (sem estouro): % capped == % bruto.
  - Cenário com estouro em 1 produto: % capped < % bruto.
  - Cenário com produto sem meta: produto fica fora do denominador.
  - Cenário com `meta_elegivel == 0`: % retorna 0 e gap retorna 0 (não estourar divisão).

## Casos de borda / pontos de atenção

- **Granularidade do agrupamento de realizado por produto**: o `df` de vendas e o `df_metas_produto` precisam usar o mesmo dicionário de produtos. Verificar antes se há divergência (ex.: vendas tem "FGTS" e "ANT.BEN." separados, mas a meta é "FGTS_ANT_BEN_CNC13" combinado). Já existe lógica de combinação em `_MIX_COMPONENTES` ([gerais.py:94-96](../../../src/dashboard/kpis/gerais.py#L94-L96)) — reaproveitar.
- **Escopo de filtros (perfil/RLS):** o cálculo do realizado elegível precisa respeitar os mesmos filtros aplicados a `df_f` (filtro de UI + RLS). Como o cálculo entra após os filtros já estarem aplicados (mesmo lugar do `total_vendas`), isso é automático — mas vale confirmar no teste.
- **Cache de KPIs:** `st.session_state["_kpis_cache"]` ([app.py:1149-1158](../../../app.py#L1149-L1158)) precisa ser invalidado se a chave de cache `chave_kpis` não incluir variáveis relevantes — provavelmente não há mudança, mas conferir.
- **Compatibilidade do nome `meta_mix`:** muitos consumidores leem `kpis["meta_mix"]`. Manter `meta_mix` como alias de `meta_elegivel` (mesmo valor) para evitar refactor amplo.
- **Diferença `meta_elegivel` vs `meta_mix` atual:** se hoje `meta_mix` já soma apenas produtos com meta > 0 (na prática, produto sem meta tem coluna ausente ou valor 0), então `meta_elegivel == meta_mix` numericamente. A novidade é só no numerador (realizado capped) e na projeção capped. Confirmar isso na implementação.

## Pendências / follow-ups

- [ ] Validar com o usuário se a granularidade do mapeamento produto-meta tem 1-pra-1 ou se precisa de tabela de aliasing (similar ao alias de categoria de pontos em [progress/2026-05-12-categoria-pts-alias.md](2026-05-12-categoria-pts-alias.md)).
- [ ] Decidir copy do sub-rótulo do card de % Meta — manter "MIX: R$ X" ou trocar por "Meta elegível: R$ X" para deixar a regra explícita ao usuário final.
- [ ] Confirmar se o cancelamento (`kpis_cancel`) deve impactar o realizado elegível (subtrair cancelados antes do cap?). Hoje `total_vendas` já vem líquido dos filtros aplicados — verificar.
- [ ] Implementação propriamente dita, após aprovação.

## Patterns criados ou atualizados

- Não cria pattern novo. Se aprovado e implementado, considerar abrir `docs/agents/patterns/meta-capped.md` resumindo a regra para reuso futuro (ex.: cards por região/loja que também agregam metas heterogêneas).

## Referências

- Conversa: 2026-05-15, mensagem do usuário descrevendo problema e propondo "Realizado Elegível (Capped)".
- Docs consultados: [docs/agents/business-rules.md](../business-rules.md) (regras de meta) e [docs/agents/ui-components.md](../ui-components.md) (cards e KPIs).
- Código-âncora:
  - [app.py:1074-1084](../../../app.py#L1074-L1084) — ponto de cálculo de `perc_ating_valor` e `gap_valor`.
  - [src/dashboard/kpis/gerais.py:97-112](../../../src/dashboard/kpis/gerais.py#L97-L112) — montagem de `meta_mix`.
  - [src/dashboard/ui/kpi_cards_reforma.py:43-134](../../../src/dashboard/ui/kpi_cards_reforma.py#L43-L134) — renderização dos 3 cards principais.
