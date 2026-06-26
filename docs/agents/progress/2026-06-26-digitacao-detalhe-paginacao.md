# 2026-06-26 — "Digitação do Último Dia" parava em 15/06 (truncamento PostgREST)

**Agente:** Devin
**Tipo:** bugfix
**Arquivos tocados:** `src/dashboard/loaders.py`
**Commit(s):** (ainda não commitado)

## Objetivo

No detalhe do card "Em Análise", o quadro "Digitação do Último Dia"
mostrava `15/06/2026` com apenas 2 regiões (ALEXANDRE, GLENDA). O esperado
era a última data digitada (`25/06/2026`) com todas as regiões. A série
"Últimos 7 Dias (Digitação)" já estava correta.

## O que foi feito

- `_fetch_digitacao_diaria_detalhe` passou a **paginar** a RPC
  `obter_digitacao_diaria_detalhe` com `.range(offset, offset+_PAGE_SIZE-1)`,
  mesmo padrão de `_fetch_contratos_cancelados`.
- Validado contra o Supabase real (junho/2026): antes 1000 linhas / max
  15/06; depois 2017 linhas / max 25/06, todas as 5 regiões, e o Total do
  pivot do dia (R$ 392.864,73) bate com o agregado de `obter_digitacao_diaria`.

## Decisões não óbvias

- **Causa raiz = limite default de 1000 linhas do PostgREST**, não a migração.
  O agregado diário (035) tem ≤31 linhas e nunca é cortado; o detalhe
  (037/038) na granularidade dia × região × loja × produto passa de 1000
  linhas no mês. Como a RPC ordena por `data_cadastro` ASC, o corte caía
  exatamente em 15/06 e os dias/regiões posteriores sumiam silenciosamente.
- Por isso o sintoma enganava: parecia problema de migração/RLS, mas migração
  e RLS estavam corretas. A correção é só no loader (paginação), seguindo
  convenção já existente — sem tocar SQL nem UI.

## Pendências / follow-ups

- Nenhuma. Demais loaders de nível-contrato já paginam.

## Referências

- Docs consultados: [docs/agents/data-layer.md](../data-layer.md),
  [progress/2026-06-26-digitacao-ultimo-dia-detalhe.md](2026-06-26-digitacao-ultimo-dia-detalhe.md)
