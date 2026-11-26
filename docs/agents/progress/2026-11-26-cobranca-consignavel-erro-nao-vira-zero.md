# 2026-11-26 — Cobrança Consignável: erro de leitura não vira zero

**Agente:** Claude Code
**Tipo:** bugfix
**Arquivos tocados:** `src/dashboard/loaders.py`, `src/dashboard/kpis/reconquista.py`, `src/dashboard/ui/kpi_cards_reforma.py`, `src/dashboard/tabs/analiticos.py`, `tests/test_loaders_cobranca_consignavel.py`, `tests/test_loader_reconquista_liga.py`, `tests/test_cards_reconquista_liga.py`, `docs/agents/business-rules.md`
**Commit(s):** —

## Objetivo

Revisão da Cobrança Consignável. A regra em SQL (migration 130) está
correta, mas o loader transformava qualquer falha de leitura em
"Cobrança Consignável = 0" e guardava esse zero no cache.

## O que foi feito

- `_fetch_cobranca_consignavel` não captura mais a exceção: a falha sobe
  (o `_paginar_keyset` já retenta o 57014) e o `st.cache_data` não a guarda.
- `carregar_reconquista` transforma a falha em
  `totais["consignavel_status"] = CONSIGNAVEL_ERRO`, com
  `cobranca_consignavel = None`, sem `por_consultor` e sem `faixa_agregada`.
  Esse é o mesmo desenho de `LIGA_ERRO` e `PROMESSA_ERRO`.
- O card mostra "—" e um `st.error`. A sub-aba de Analíticos avisa a falha
  em vez de dizer "nenhuma proposta". Para consultor em 08/2026, a barra
  antiga de conversão não aparece com o erro.
- A docstring da busca foi atualizada para o critério da migration 130
  (tabela + REFIN + corte em 08/2026).
- Testes: o teste antigo fixava o vazio na falha e foi trocado por um que
  exige a exceção. Entraram 4 testes de orquestração e 3 de card. Cada
  parte da correção foi desfeita de propósito, e algum teste quebrou em
  todos os casos.

## Decisões não óbvias

- **Status em vez de deixar a exceção subir até o `app.py`.** Lá a
  exceção descarta a Reconquista inteira (`dados_reconquista = None`), e
  liga e promessas sumiriam junto (decisão do usuário, 26/11/2026).
- **`aplicar_rls` fica fora do `try`.** Uma falha do RLS não é "erro de
  leitura" e continua sendo tratada como antes.
- **Sem estado "não importada".** O frame sai de `v_contratos_dashboard`,
  então mês sem proposta é zero legítimo.

## Pendências / follow-ups

- [ ] `_fetch_faixa_acelerador` ainda captura a falha e devolve rótulo
      vazio, também cacheado (6h/24h). O efeito é "sem faixa", e não uma
      faixa errada, mas o motivo citado (migration 066 não aplicada) está
      obsoleto.
- [ ] O subtítulo do card ("Contrato Novo · BMG · propostas pagas") não
      menciona o REFIN, que conta desde a migration 130.
- [ ] Confirmar com o negócio: 3 contratos de `COBRANÇA CONSIGNAVEL - NOVO`
      em 10/2026 vieram com bruto ≠ base e entraram pelo VLR BRUTO
      (+R$ 13.302,26). A migration 130 supunha bruto = base nessas tabelas.
- [ ] Confirmar com o negócio: 11/2026 tem só 1 contrato pago até 25/11.
      O último cadastro nas tabelas da modalidade foi em 09/11, e desde
      15/10 não surgiu tabela com nome parecido.

## Referências

- Docs consultados: [business-rules.md](../business-rules.md) § "Cobrança Consignável — critério"
