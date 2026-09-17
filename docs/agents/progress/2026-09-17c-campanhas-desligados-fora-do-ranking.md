# 2026-09-17 — Campanhas: desligados fora do ranking de consultores

**Agente:** Claude Code
**Tipo:** feature
**Arquivos tocados:** `src/dashboard/loaders.py`,
`src/dashboard/kpis/campanha.py`, `src/dashboard/pages/campanhas.py`,
`tests/test_kpis_campanha.py`, `tests/test_loaders_paginacao_cadastro.py`

> Continua [2026-09-17b](2026-09-17b-campanhas-destaque-do-escopo.md).

## Pedido

Não listar consultores desligados no ranking da campanha.

## Medição antes de filtrar (17/09/2026)

134 consultores no ranking; 17 sem cadastro ativo, R$ 915 mil. **Todos
os 17** têm status `Desligado (a)` no registro mais recente — nenhum
saiu por grafia divergente. Nenhum estava entre os 16 primeiros. Depois
do filtro: 117 linhas.

## Decisões não óbvias

- **Recorte por DESLIGADO, não por ATIVO.** `carregar_consultores_ativos`
  (o universo de vendas) exclui qualquer status que não comece com
  "Ativo" — inclusive `Licença Maternidade`, que existe no cadastro.
  Numa campanha com prêmio, tirar do ranking quem está de licença seria
  uma decisão de premiação (e trabalhista) que ninguém tomou. Loader
  novo, `carregar_consultores_desligados`, com o mesmo colapso de
  duplicados e paginação por `id`. Não filtra loja ativa.
- **Antes do ranking, não depois.** Posições recalculadas: desligado não
  ocupa vaga de premiação.
- **Ranking de lojas e totais intactos.** A produção foi feita na loja e
  continua dela; termômetro, famílias e condições seguem somando tudo.
- **A tela diz quantos saíram** ("N consultor(es) desligado(s) fora do
  ranking"), para o filtro não parecer bug.

## Premissa a validar

Desligado **no meio da campanha** perde a posição, mesmo tendo produzido
enquanto estava ativo. É o que o pedido diz; se o regulamento previr
premiar quem produziu no período, a regra muda.

## Verificação

`TestDesligadosForaDoRanking` (7, + os 7 de RLS herdados) e
`TestConsultoresDesligados` (4, loader). Três sabotagens pegas: licença
tratada como desligado, filtro não aplicado, remoção depois do ranking.
Suíte: 1305 passam.
