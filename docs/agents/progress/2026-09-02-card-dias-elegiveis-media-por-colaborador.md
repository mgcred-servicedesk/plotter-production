# 2026-09-02 — Card "Dias elegíveis" vira média por colaborador

**Agente:** Claude Code
**Tipo:** bugfix (leitura de KPI)
**Arquivos tocados:** `src/dashboard/tabs/gestao_consultores.py`,
`src/dashboard/kpis/produtividade.py`, `tests/test_kpis_produtividade.py`,
`tests/test_tabs_gestao_presets.py`
**Commit(s):** (não commitado)

## Objetivo

O usuário apontou que o card "Dias elegíveis" no topo de **Performance do
time** mostra uma informação que não se lê como KPI.

## O que foi feito

- Diagnóstico: o card exibia `sum(Dias elegiveis)` de todo o escopo —
  **dias-colaborador** (~112 pessoas × ~21 DU ≈ 2.352) sob o rótulo
  "Dias elegíveis", num mês que tem 21 dias úteis. Era o denominador do
  card vizinho (R$/dia elegível) posando de indicador, sem referência
  para dizer se o número era alto ou baixo.
- `produtividade_carteira` passou a devolver `dias_por_colaborador`
  (= `dias / colaboradores`). `dias` continua no dict, como base
  auditável.
- O card virou **"Dias por colaborador"**: média em decimal, delta
  `"de N DU na competência"` e `help` com a composição
  (`X dias-colaborador = N pessoas × dias de cada uma`).
- Novo helper `_du_competencia(df_vinculos)` lê `DU_COMPETENCIA` — a
  coluna que o loader de vínculos já publicava e a UI ignorava.

## Decisões não óbvias

- **Por que média por pessoa e não cobertura em %?** — a média fica na
  mesma unidade do que a sub-visão promete corrigir ("quem entrou dia 20
  teve menos dias"): 20,4 de 21 DU se lê direto. O percentual exigiria
  o teto mentalmente. Opção oferecida ao usuário e descartada por ele.
- **O total não foi apagado, foi rebaixado** — sai do card, fica no
  `help`. Ele é o denominador do R$/dia ao lado; sumir com ele quebraria
  a auditoria da razão das somas.
- **DU vem de `df_vinculos`, não recalculado na UI** — `DU_COMPETENCIA`
  já é constante por linha vinda de `_fetch_vinculos_consultores`.
  Recalcular na aba criaria uma segunda fonte para "quantos DU tem o
  mês", que o projeto mantém única (`src/shared/dias_uteis.py` e 091).
- **Sem DU, o card não some** — `_du_competencia` devolve `None` e o
  delta cai para "media do escopo". A média não depende da referência.

## Pendências / follow-ups

- [ ] Nenhuma. A base continua sendo dias de VÍNCULO (sem desconto de
      afastamento) — o aviso permanente de `_aviso_base_elegivel` cobre
      isso e não foi tocado.

## Referências

- Docs consultados: [docs/agents/ui-components.md](../ui-components.md),
  [docs/agents/business-rules.md](../business-rules.md)
- Contexto anterior: [2026-09-01-produtividade-individual-v2-implementacao.md](2026-09-01-produtividade-individual-v2-implementacao.md)
