# 2026-08-31 — Numerador dos cards de média por consultor entra na mesma população do peso

**Agente:** Claude Code
**Tipo:** bugfix (regras de negócio + UI)
**Arquivos tocados:** `src/dashboard/kpis/gerais.py`,
`src/dashboard/kpis/pontuacao.py`, `src/dashboard/ui/kpi_cards_reforma.py`,
`src/dashboard/ui/kpi_cards_pontuacao.py`, `tests/test_kpis_gerais.py`,
`tests/test_kpis_pontuacao.py`
**Commit(s):** —

## Objetivo

Revisar a contagem de consultores ativos usada como denominador das médias e
corrigir o que a revisão encontrasse. O usuário confirmou o **gente-mês** como
base.

## O achado

A troca do denominador (progress de 2026-08-25) estava correta e reproduz o
`weightedHeadcount` até a quarta casa. O defeito estava do **outro lado da
divisão**: o numerador.

`kpis["total_vendas"]` é `df["VALOR"].sum()` — inclui supervisor e `VAI E VEM`,
regra deliberada desde 2026-08-10. O `peso` da 091 **exclui os dois por
construção**. Os cards de "Média por Consultor" dividiam um pelo outro.

É literalmente o defeito descrito na primeira frase do cabeçalho da migration
**096** (*"`productivity` divide producao que INCLUI supervisor por capacidade
que o EXCLUI"*), que ela corrige no Caderno criando `paidByConsultants`. A 096
consertou o lado SQL; o dashboard havia reintroduzido o mesmo erro no Python.

Medido contra o banco:

| Competência | Exibido antes | Correto | Erro |
|---|---|---|---|
| 06/2026 | R$ 60.272,67 | R$ 59.806,48 | +0,78% |
| 07/2026 | R$ 90.182,05 | R$ 89.020,78 | +1,30% |
| 08/2026 | R$ 81.508,26 | R$ 80.072,33 | +1,79% |

Os 1,30% de 07/2026 são exatamente o número que o cabeçalho da 096 diz ter
retirado da medição por contaminação. E crescia mês a mês.

**Sintoma visível:** dentro do *mesmo card*, o número grande e a linha
"Projeção fim do mês" usavam numeradores diferentes — `media_du_consultor` já
somava sobre `df_sem_sup`. Em 08/2026 o card mostrava R$ 81.508 no topo e
R$ 80.072 de projeção logo abaixo, num mês que fechava naquele dia.

## O que foi feito

- **`producao_consultores`** no retorno de `calcular_medias_du_por_nivel` e
  **`pontos_consultores`** no de `calcular_medias_pontos_por_nivel`: a soma
  sobre `df_sem_sup` que as duas funções já calculavam e descartavam. É o
  análogo exato do `paidByConsultants` da 096.
- Os dois cards de "Média por Consultor" (valor e pontos) passam a usar esse
  numerador.
- **9 testes novos**; suíte em 614 passando, `ruff` limpo.

## Verificação ponta a ponta

Com o banco real, 06–08/2026: `(producao_consultores / peso) / DU` agora bate
com `media_du_consultor` até 1e-6, e nos meses fechados o topo do card e a
projeção convergem para o mesmo valor — que era o teste que falhava antes.

## Decisões não óbvias

- **A correção vale nos DOIS caminhos do denominador**, não só no ponderado.
  O fallback por produtores tinha a mesma mistura de populações. Deixar só um
  lado corrigido faria o card calcular a manchete de dois jeitos dependendo de
  um branch — pior de raciocinar que o bug original. `business-rules.md`
  ("Exclusão de supervisores") manda excluir supervisor de **toda** média por
  consultor, sem ressalva quanto ao denominador.

- **Média por LOJA ficou como estava.** Ali somar supervisor é a regra correta
  (`business-rules.md`: produção de supervisor entra anônima e somada no total
  da loja). Não é a mesma pergunta que a média por consultor.

- **Meta, gap e projeção da rede seguem com `total_vendas` cheio.** Auditei os
  outros usos de `total_vendas`/`total_pontos`: são comparações contra meta,
  onde incluir supervisor é a regra de 2026-08-10. Só os dois cards de média
  por consultor estavam errados.

- **Premissa do usuário corrigida antes de implementar.** A justificativa dada
  foi que o gente-mês "considera consultores ativos que realmente produziram".
  Ele faz o oposto: conta todo mundo com vínculo, **inclusive quem vendeu
  zero**, fracionado pelo tempo ativo (R2 da 091). Excluir os zerados era o
  denominador antigo, e é o viés que a mudança de 25/ago removeu. A metade
  sobre fracionar pelo tempo ativo está certa, e é o que torna o gente-mês a
  base correta.

## Pendências / follow-ups

- [ ] **Migration 096 ainda não aplicada.** Enquanto isso, numerador e
      denominador ainda discordam sobre *quem é supervisor*: o numerador usa a
      âncora do último dia (085), o peso conta dias proporcionais (091).
      São 0,4348 pessoa (0,38%) em 07/2026, pela medição da própria 096 — que
      é exatamente o que ela alinha. O Python foi entregue antes da migration
      que o torna consistente.
- [ ] **`num_lojas` ficou com o viés que `num_consultores` perdeu**
      (`gerais.py`): ainda conta lojas *que produziram*. Verificado em 06, 07 e
      08/2026 — 48 = 48 nos três meses, então hoje é inócuo. Assimetria
      latente; o frame de headcount já traz a contagem de escopo pronta.
- [ ] **`carregar_consultores_ativos()` devolve 169 pessoas, das quais 47 são
      supervisores.** Não é bug — todos os consumidores chamam
      `excluir_supervisores` no ponto de uso, e o padrão está documentado em
      `loaders.py`. Mas o nome e a docstring da função não avisam. Vale uma
      linha na docstring antes que o próximo consumidor tropece.
- [ ] Conferir os cards em tela: a verificação foi numérica, não visual.

## Referências

- [progress/2026-08-25-denominador-ponderado-dashboard.md](2026-08-25-denominador-ponderado-dashboard.md) — a troca do denominador
- [business-rules.md](../business-rules.md) — "Exclusão de supervisores", "Lojas de backoffice"
- Migrations: 091 (peso), 092 (Caderno), 096 (população única no SQL)
