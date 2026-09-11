# 2026-09-10 — Heatmap regional: critério de ranking passa a olhar a meta, não o atingimento

**Agente:** Claude Code
**Tipo:** bugfix
**Arquivos tocados:** `src/dashboard/kpis/regioes.py`, `src/dashboard/ui/charts.py`, `src/dashboard/tabs/produtos.py`, `tests/test_kpis_regioes.py`
**Commit(s):** (pendente)

## Objetivo

Auditar o Mapa de Calor (Ranking Região × Produto) quanto ao ranqueamento por
atingimento de meta e ao fallback por volume de produção quando não há meta
cadastrada.

## O que foi feito

- `calcular_heatmap_regiao_produto` passou a decidir o critério pela **meta
  cadastrada** (`df_meta[col].sum() > 0`) em vez do atingimento realizado
  (`df_ating[col].sum() == 0`).
- `% atingimento` sem meta virou `NaN` (antes `0`), separando "não tem alvo"
  de "tem alvo e não produziu".
- Célula sem base de comparação virou `NaN` no ranking (= "sem posição"):
  região sem meta numa coluna com meta; região sem produção numa coluna
  ranqueada por volume; coluna inteira quando ninguém produziu.
- `criar_heatmap_regiao_produto` pinta a célula sem posição com fundo neutro
  (`grid_zero`) + anotação `—`, e o hover explicita o critério de cada célula
  (atingimento, volume, ou o motivo da ausência de posição).
- Subtítulo do card passou a declarar os dois critérios e o significado do `—`.
- Quatro testes novos em `TestCalcularHeatmapRegiaoProduto` cobrindo: sem meta
  em nenhuma região, sem meta e sem produção, meta cadastrada sem produção,
  e meta parcial.

## Bugs corrigidos (verificados com dados reais)

- **08/2026, SAQUE**: sem meta e sem nenhum contrato no mês, `rank` sobre a
  coluna toda-zero devolvia `1` para todas as regiões — as 4 apareciam "1º" em
  verde. Agora aparecem `—`.
- **09/2026, SAQUE**: GLENDA (R$ 1.891) 1º e as outras três, com R$ 0,
  empatadas em "2º" no meio da escala com hover "Atingimento: 0,0%". Agora só
  GLENDA tem posição (hover: ranking por volume), as demais `—`.
- **Meta parcial**: região sem meta do produto herdava 0% e ia para o último
  lugar mesmo com o maior volume. Hoje isso não aparecia porque a única região
  sem metas (ALEXANDRE) está hardcoded fora do heatmap
  (`_REGIOES_EXCLUIR_HM`) — qualquer região nova cairia no buraco.
- **Meta cadastrada sem produção** (início de mês): o gatilho antigo, por ser
  baseado no atingimento, trocava silenciosamente para volume e, com volume
  zero, pintava todas as regiões como 1º.

## Decisões não óbvias

- **Por que `NaN` em vez de manter o último lugar?** Posição só existe onde
  houve disputa. Região sem meta não disputou o critério de atingimento; região
  sem produção não disputou o de volume. Dar-lhe um lugar é inventar
  informação — e era exatamente isso que fazia "0%" virar vice ou primeiro.
- **Por que o critério olha a meta e não o realizado?** O realizado é zero por
  dois motivos distintos (sem alvo / com alvo e sem venda) e o gatilho antigo
  não distinguia. A meta é a propriedade estável da coluna.
- **Por que não mudar a aridade do retorno da função?** O contrato
  `(df_ranking, df_ating)` foi preservado; o critério de cada célula é
  derivável do par (`ating` `NaN` → ranking veio de volume). Consequência: o
  hover da coluna por volume não mostra o R$ produzido — para isso a matriz de
  volume precisaria chegar ao gráfico.
- **Empate legítimo continua empatando** (`method="min"`): duas regiões com o
  mesmo atingimento dividem a posição.

## Pendências / follow-ups

- [ ] Metas por produto trazem `REGIAO` = região **atual** da loja
      (`_fetch_metas_produto`, via `lojas.regioes`), enquanto o realizado usa
      região point-in-time. `_fetch_metas` (META_PRATA) já faz point-in-time via
      `loja_regiao_vigencia`. Verificado 06–09/2026: nenhuma loja mudou de
      região, então hoje não diverge — na próxima transferência, numerador e
      denominador do heatmap caem em regiões diferentes.
- [ ] Exclusão de ALEXANDRE do heatmap é uma constante hardcoded
      (`_REGIOES_EXCLUIR_HM`); com o `—` implementado, avaliar se a região
      ainda precisa ficar de fora.
- [ ] Hover da coluna ranqueada por volume não mostra o R$ produzido.

## Referências

- Docs consultados: [business-rules.md](../business-rules.md),
  [ui-components.md](../ui-components.md)
