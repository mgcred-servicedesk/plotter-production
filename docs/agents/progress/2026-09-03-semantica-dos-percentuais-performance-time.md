# 2026-09-03 — Semântica dos percentuais da Performance do time

**Agente:** Claude Code
**Tipo:** bugfix + regra de negócio
**Arquivos tocados:** `src/dashboard/kpis/produtividade.py`,
`src/dashboard/kpis/gestao.py`, `src/dashboard/tabs/gestao_consultores.py`,
`tests/test_kpis_produtividade.py`, `tests/test_gestao_consultores.py`,
`tests/test_tabs_gestao_presets.py`, `docs/agents/business-rules.md`
**Commit(s):** (não commitado)

## Objetivo

O usuário pediu para revisar sob quais cálculos incidem as porcentagens da
gestão de performance do time e se elas são corretas para medir produtividade —
depois, corrigir tudo garantindo que o que aparece na tela seja verídico.

## Achados (todos medidos no banco, 08/2026 fechada e 09/2026 em curso)

1. **`% da loja` não era escala comparável entre lojas.** Com a pessoa dentro
   do próprio benchmark, o teto é `n_pessoas × 100%`. Medido em 09/2026,
   exatamente 100/200/300/400% nas lojas de 1/2/3/4 pessoas. São 48 lojas de 1
   a 4 e **84% do time em loja de até 3**; quem está sozinho marca 100% sempre.
2. **Índice ausente sumia do corte e ordenava como o melhor.** Loja inteira sem
   venda → benchmark 0 → `NaN`. O `<=` do slider descartava em silêncio e
   `na_position="last"` jogava essas pessoas para o fim de uma lista de piores.
   Duas pessoas em 09/2026 (HELP LARANJEIRAS).
3. **Critérios e Performance discordavam sobre o que é "a média".**
   `_resolver_limiar` usava média aritmética das produtividades individuais —
   a média de médias que o módulo proíbe. 08/2026: R$ 3.782,97 contra
   R$ 3.911,89/dia da razão das somas (−3,3%; −5,6% na região SANDRA).
4. **"Sem comparação possível" contava caso que não era lacuna.** 07→08/2026:
   das 18 lacunas, 3 estavam presentes nos dois meses — HELOISA (0 →
   R$ 918,78/dia) e MARCELLA (0 → R$ 3.056,38/dia), as duas maiores viradas do
   mês, arquivadas como ausência.
5. **Nada dizia que os percentuais são do escopo filtrado.** Filtrar uma loja
   fazia "% da região" deixar de ser a região; filtrar um consultor fazia tudo
   valer 100% por construção.

## O que foi feito

- **`% da carteira`** (nova coluna): a pessoa contra a razão das somas do
  escopo em tela — o **mesmo denominador do card "R$ por dia elegível"**.
  Único índice comparável entre lojas, e agora é o eixo do corte do slider.
- **`Na loja`** (nova coluna): posição por R$/dia dentro da própria loja
  ("2 de 3", empate divide a posição), sem teto e sem depender do tamanho do
  time. Linha sem dia elegível fica em branco.
- **`% da loja` e `% da região` mantidos com a fórmula atual**, com o teto e o
  tamanho de cada grupo declarados na tela.
- **Corte e ordenação** extraídos para `_recortar_e_ordenar` (função pura,
  testável): o corte guarda `NaN` explicitamente e a ordem crescente põe
  índice ausente no **topo**.
- **`_media_do_grupo` / `_media_por_regiao`** (`kpis/gestao.py`): razão das
  somas quando a métrica é razão (peso = dias elegíveis), média simples quando
  é soma. Identidade verificada contra o banco, global e por região.
- **`Situacao`** em `variacao_ultima_competencia`: SUBIU / CAIU / ESTAVEL /
  SAIU DE ZERO / ZERADO NOS DOIS / AUSENTE NO ANTERIOR / SEM DIA ELEGIVEL
  AGORA. A legenda da tendência passa a contar cada uma pelo que ela é.
- **Legenda e avisos**: `_legenda_percentuais` declara o tamanho real de cada
  grupo e o teto da loja; `_aviso_escopo_dos_percentuais` avisa quando o filtro
  colapsou a base; nota de amostra curta no mês em curso; nota de que Região é
  a **atual**, não a vigente no contrato.

## Decisões não óbvias

- **Leave-one-out por loja foi medido e DESCARTADO.** É semanticamente exato
  ("100% = igual aos colegas") mas com o colega no denominador o índice explode:
  máximo de **30.690%** e desvio-padrão de **4.459** nas lojas de duas pessoas
  em 08/2026. Trocamos a escala quebrada por uma escala boa (`% da carteira`)
  mais uma leitura sem escala (`Na loja`).
- **`% da loja` NÃO foi removida.** O sinal dela é exato — estar acima do grupo
  com a pessoa dentro é algebricamente idêntico a estar acima dos colegas sem
  ela (0 de 122 trocam de lado no leave-one-out) — e ela carrega informação que
  os outros índices não têm (Spearman 0,80 contra R$/dia). O defeito era ler
  como escala de rede; a correção é declarar o teto, não apagar a coluna.
- **O corte migrou para `% da carteira`.** Um corte único sobre `% da loja`
  mede coisa diferente em cada loja. Efeito colateral bom: `% da carteira` não
  fica `NaN` quando a loja não vende (só se a rede inteira não vender), então
  as duas pessoas do achado 2 aparecem com **0,0%** no topo da lista em vez de
  sumirem.
- **Teto do slider virou 400 e é sentinela de "sem filtro".** Nenhum teto fixo
  cobre o mês em curso (máximo medido: 719% no 2º dia útil de 09/2026), então o
  topo desliga o filtro em vez de fingir que existe limite.
- **Ticket médio e share continuam na média simples.** São razões também, mas
  o projeto não publica em lugar nenhum uma média de grupo para elas — não há
  contradição declarada a corrigir, e mexer mudaria número já em uso nos
  Critérios. Ver follow-up 1.
- **Critérios e Performance não têm de bater em VALOR.** O `Total` dos
  Critérios soma só os produtos selecionados e a população depende de "incluir
  zerados". O que tinha de ser igual — e agora é — é a *definição* de média.

## Verificação ponta a ponta (banco real)

| Checagem | 08/2026 | 09/2026 |
|---|---|---|
| `% da carteira` == `prod_dia / card × 100` | ✅ | ✅ |
| média ponderada de `% da carteira` | 100,00% | 100,00% |
| `Na loja` coerente com a ordem de R$/dia | 48/48 lojas | 48/48 lojas |
| linhas violando o teto `n×100` em `% da loja` | 0 | 0 |
| órfãs na tabela | 0 | 0 |

- Identidade da razão das somas em `_media_do_grupo`: R$ 3.575,003396/dia
  esperado e obtido; as 5 regiões batem casa decimal a casa decimal.
- 07→08/2026, situações: 55 CAIU, 49 SUBIU, 15 AUSENTE NO ANTERIOR,
  2 SAIU DE ZERO, 1 ZERADO NOS DOIS (antes: "49 subiram, 55 caíram, 18 sem
  comparação").
- Os 3 testes novos de `_media_do_grupo` foram rodados contra a implementação
  ANTIGA reinstalada em runtime: os 3 falham. São guardas reais, não tautologia.

**702 testes passando** (21 novos; 681 antes), `ruff` limpo.

## Pendências / follow-ups

- [ ] Ticket médio e share nos Critérios seguem na média aritmética. Alinhar
      muda número publicado — decisão do usuário.
- [ ] `variacao_ultima_competencia` casa o mês anterior pelo nome de EXIBIÇÃO
      (`set_index(COL_CONSULTOR)`), não pela chave normalizada. Colisão de
      grafia levanta `InvalidIndexError` (falha alto, não silenciosa), mas
      destoa do resto do módulo.
- [ ] O numerador é R$ pago: `% da loja` mistura produtividade com mix de
      produto e ticket. Um segundo eixo em quantidade ou pontos mediria
      *throughput*, que é o que "produtividade" costuma significar.
- [ ] A base continua sendo **vínculo, não presença** (férias e afastamento não
      descem). É a maior distorção individual e segue avisada em `st.warning`.

## Referências

- Achados originais desta sessão, com os números que motivaram cada correção.
- Entrada anterior: [2026-09-02-denominador-parcial-r-por-dia-elegivel.md](2026-09-02-denominador-parcial-r-por-dia-elegivel.md)
- Regra atualizada: [business-rules.md](../business-rules.md) — "Produtividade
  por dia elegível (individual)"
