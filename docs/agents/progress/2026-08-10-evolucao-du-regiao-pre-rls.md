# 2026-08-10 — Comparativo regional de Evolução Média DU ignora RLS de propósito

**Agente:** Claude Code
**Tipo:** bugfix
**Arquivos tocados:** `src/dashboard/tabs/produtos.py`
**Commit(s):** (não commitado ainda)

## Objetivo

Usuário reportou: no quadro "Evolução Média DU por Região" (aba Produtos →
Comparativo Regional), a visão global funciona, mas ao visualizar como
Gerente Comercial o RLS quebra o sentido comparativo entre regionais.
Pedido explícito: manter esse quadro ignorando o RLS, propositalmente —
é estímulo para cada regional se comparar com o resto da rede, não só
com o próprio mês anterior.

## O que foi feito

- `_carregar_mes_comparativo` agora também cacheia um snapshot
  **pré-RLS** do mês de comparação (`<prefixo>_cache_full`), no mesmo
  espírito do `df_full` que o mês atual já tinha (padrão existente em
  `app.py` / `obter_medias_organizacao_periodo`).
- Nova função `_mes_comparativo_full(prefixo)` para ler esse cache.
- `limpar_cache_comparativos` passa a limpar também a nova chave.
- O `calcular_evolucao_media_du(...)` dentro do bloco `pode_heatmap`
  passou a receber `_mes_comparativo_full(_PREFIXO_MES_ANT)` em vez de
  `df_ant` (que é pós-RLS) para a coluna "Mês Anterior".

## Decisões não óbvias

- **Causa raiz real:** não era falta de bypass de RLS — o "Mês Atual"
  (`df_full`) já era pré-RLS. O problema estava só no "Mês Anterior"
  (`df_ant`), carregado por `_carregar_mes_comparativo`, que sempre
  aplicava `aplicar_rls`. Para um perfil `gerente_comercial`, isso
  zerava (não apenas ocultava) o "Mês Anterior" de toda região que não
  fosse a dele — `calcular_evolucao_media_du` faz
  `serie_ant.get(regiao, 0)`, então região ausente vira R$0 / 0% de
  evolução, não um erro visível.
- **Por que não tornar `df_ant` sempre pré-RLS?** — esse mesmo frame
  alimenta o gráfico "Análise Completa de Produtos" (`criar_grafico_produtos`,
  mais abaixo na aba), que precisa continuar respeitando o escopo do
  perfil. Só o bloco `pode_heatmap` (Comparativo Regional) precisa da
  versão organização-inteira.
- **Por que reaproveitar o cache em vez de nova query?** — `consolidar_dados`
  já é chamado uma vez por `_carregar_mes_comparativo`; o frame pré-RLS é
  só uma referência anterior ao `aplicar_rls`, sem custo adicional de
  Supabase.
- **Escopo do bypass:** só agregados por região chegam à tela a partir
  desse frame (soma de `VALOR` por `REGIAO` / dias úteis) — nenhuma
  linha crua, mesma garantia documentada em
  `obter_medias_organizacao_periodo` (`src/dashboard/kpis/gerais.py`).

## Pendências / follow-ups

Nenhuma. Mudança testada (`pytest tests/` completo, 463 passed) e
`ruff check` limpo.

## Referências

- Docs consultados: [docs/agents/rls.md](../rls.md)
