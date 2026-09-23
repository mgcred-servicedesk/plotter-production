# 2026-09-23 — Ranking truncava em silêncio e o modelo estimava a cobertura

**Agente:** Claude Code
**Tipo:** bugfix
**Arquivos tocados:** `src/dashboard/chat_ia/tools.py`,
`src/dashboard/chat_ia/agent.py`, `tests/test_chat_ia_tools.py`

## Objetivo

No uso real da aba, o assistente montou uma tabela somando quatro
rankings diferentes e concluiu *"cerca de 19 lojas nunca aparecem em
nenhum top 25"* — número que nenhuma tool produziu.

## Diagnóstico

Assimetria entre os retornos das tools:

- `comparar_entidades` devolvia `total_comparadas` (total **antes** do
  corte) — daí o "49 lojas" legítimo da resposta.
- `ranking_periodo` devolvia **só `resultados`**. Um top 25 de 49 era
  indistinguível de "existem só estas 25".

Sem saber a cobertura, o modelo preencheu a lacuna com aritmética
própria — exatamente o que o `SYSTEM_PROMPT` proíbe. O design da tool
empurrou para lá.

## O que foi feito

- `ranking_periodo` passa `_TOP_N_SEM_CORTE` às funções de
  `kpis/rankings.py`, lê `total_disponivel = len(ranking)` e **só então**
  corta com `.head(limite)`. Retorno ganhou `total_disponivel` e
  `truncado`.
- `comparar_entidades` e `listar_sem_producao` ganharam `truncado`
  (ambos já informavam o total).
- `_LIMITE_MAXIMO`: 25 -> 50.
- Descrições das tools e `SYSTEM_PROMPT` instruem a citar o total da
  própria tool e a **nunca** deduzir cobertura cruzando chamadas.
- 4 testes novos; 3 existentes passaram a referenciar `_LIMITE_MAXIMO`
  em vez de fixar 25.

## Decisões não óbvias

- **Cortar em `tools.py`, não mexer em `kpis/rankings.py`** — `_rankear`
  ([rankings.py:125](../../../src/dashboard/kpis/rankings.py#L125)) já
  monta o ranking inteiro e só depois faz `.head(top_n)`. Pedir o
  ranking completo e cortar aqui **não custa query nem cálculo extra**, e
  não toca a camada de KPI usada por outras abas.
- **`_LIMITE_MAXIMO` não protege o banco** — rankings e comparativos são
  pandas puro sobre frames já carregados (`rankings.py` e
  `comparativos.py` não importam Supabase). O teto existe porque cada
  linha vira token e concorre com o `MAX_TOKENS` de saída do agent.
  Medido: 25 -> 50 linhas custa ~+625 tokens de entrada (~$0,0001 por
  chamada). Impacto no plano Nano do Supabase: **nenhum**.
- **50 e não 100** — 50 linhas em tabela markdown já consomem ~1.000 dos
  2.048 tokens de saída; acima disso a resposta trunca no meio.
- **Corrigir isso tende a reduzir rodadas de tool-use**, não aumentar: o
  truncamento silencioso é que fazia o modelo encadear ranking atrás de
  ranking tentando cercar a cobertura.

## Validação

- E2E real (OpenRouter, 62 lojas sintéticas, Supabase blindado no teste):
  o modelo respondeu *"o ranking completo tem 62 lojas, e aqui foram
  exibidas só as 10 primeiras"* — total vindo da tool, sem estimativa
  própria.
- Sabotagens: total lido após o corte (2 falhas), `truncado` fixo em
  `False` (3 falhas).
- `1328 testes` passando; `ruff check` limpo.

## Pendências / follow-ups

- [ ] **Não há tool que filtre por faixa de valor.** "Todas as lojas
      abaixo de R$ 150 mil" continua sem resposta possível — não é
      questão de limite, e sim de tool inexistente. Se a pergunta for
      recorrente no uso real, criar a tool em vez de subir o teto de novo.
- [ ] Avaliar se `comparar_entidades` deveria expor faixas de valor pelo
      mesmo motivo.

## Referências

- Progresso anterior:
  [2026-09-23b-chat-ia-429-mascarado-pelo-fallback.md](2026-09-23b-chat-ia-429-mascarado-pelo-fallback.md)
