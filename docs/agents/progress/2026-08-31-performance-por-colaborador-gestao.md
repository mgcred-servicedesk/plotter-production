# 2026-08-31 — Performance por colaborador na aba Gestão (sem migration)

**Agente:** Claude Code
**Tipo:** feature (data layer + regra de negócio + UI)
**Arquivos tocados:**
`src/dashboard/loaders.py`, `src/dashboard/kpis/produtividade.py` (novo),
`src/dashboard/kpis/gestao.py`, `src/dashboard/tabs/gestao_consultores.py`,
`src/dashboard/ui/charts.py`, `app.py`,
`tests/test_kpis_produtividade.py` (novo),
`tests/test_loaders_vinculos.py` (novo),
`tests/test_gestao_consultores.py`, `tests/test_tabs_gestao_presets.py`,
`docs/agents/business-rules.md`
**Commit(s):** —

## Objetivo

Adaptar o que já existe para mostrar a gestores e gerentes o nível de
performance de **cada colaborador** — pedido do usuário sobre o plano de
produtividade de 2026-08-31 (`...-plano-produtividade-gerencial-sem-afastamentos.md`).

## O achado que mudou o escopo

O plano do Codex é uma frente de **origem** (ST-00 → ST-11): nova migration,
snapshot individual privado, RPC de leitura, handoff ao Bereshit,
rematerialização. Nada disso é necessário para a visão gerencial:

- `consultor_vigencia` (086/087) já tem `GRANT SELECT` para
  `anon/authenticated` e policy de leitura aberta (086:351-357). O dashboard
  lê o ledger direto pelo PostgREST, como `carregar_supervisores` já faz com
  `supervisor_vigencia`.
- São **395 linhas** no ledger inteiro. Não há o que paginar nem RPC a criar.

**Zero migrations neste incremento.** A frente de origem continua valendo
para o contrato do Bereshit e para congelar snapshots; ela não bloqueia a
leitura gerencial.

## Decisões do usuário (revogam parte do plano)

1. **Visão nominal individual, com guarda-corpo** — revoga a decisão 6 e o
   item "ranking nominal no dashboard" do *Fora de escopo*. O argumento: a
   decisão 6 protegia contra decisão de RH sem cobertura de afastamento, não
   contra visibilidade — Rankings e Gestão **já** mostram consultor por nome
   com valor e meta. O que faltava era o denominador. Sem score automático e
   sem lista pré-montada de "piores"; o corte é do usuário, num slider.
2. **Mora na aba Gestão**, não em Evolução (que o plano indicava). Evolução é
   visível aos cinco perfis (`tab_evolucao: True` para todos); dado nominal
   ali exigiria um gate novo dentro da aba. `tab_gestao` já é
   admin/gestor/gerente_comercial.
3. **Escopo v1**: métrica + painel + tendência.

As sete decisões de produto do plano seguem valendo: `paidEffective /
consideredWorkingDays`, evento de pagamento, carteira atual, competências
fechadas na série, benchmark por razão das somas, e nenhuma leitura de
`consultor_afastamento`.

## O que foi feito

**`carregar_vinculos_consultores(mes, ano)`** (`loaders.py`): dias úteis
elegíveis por `(consultor, loja)`, com `BASE_DIAS = ELIGIBLE_LINK_DAYS` e
`COBERTURA_AFASTAMENTO = NONE` em toda linha. Reaplica os mesmos filtros de
`carregar_headcount_ponderado` (loja inativa, backoffice) e exclui supervisor
pela âncora da competência. Sem afastamento, sem piso de 50%, sem rateio —
as três diferenças deliberadas contra a 091, documentadas na docstring.

**`src/dashboard/kpis/produtividade.py`** (novo): funções puras —
`produtividade_por_consultor`, `benchmark_por` (razão das somas),
`produtividade_carteira`, `linhas_sem_vinculo`, `serie_por_consultor`,
`variacao_ultima_competencia`.

**Métrica `prod_dia` na tabela de critérios** (`kpis/gestao.py`): "R$/dia
elegível" entra como quinto eixo de métrica e herda **de graça** critérios,
limiares relativos (% da média do grupo/região, percentil), lacuna, presets e
export. A base "% da meta" é bloqueada — meta é mensal em R$, comparar com um
número por dia daria limiar ~20x maior.

**Sub-visão "Performance do time"** (`tabs/gestao_consultores.py`): a aba
ganhou sub-navegação em `st.pills` (Critérios | Performance). O painel traz
cards da carteira, tabela nominal (produção, dias, R$/dia, % da loja, % da
região), benchmark por loja, diagnóstico de produção sem vínculo, export CSV
e a série das competências fechadas (`criar_grafico_produtividade`), carregada
sob demanda por toggle — cada competência é uma leitura a mais no Supabase.

**45 testes novos**; suíte em 659 passando, `ruff` limpo.

## Verificação ponta a ponta (banco real)

Denominador individual × `weightedHeadcount` que os cards usam:

| Competência | Σ fração-pessoa | peso dos cards | gap |
|---|---|---|---|
| 06/2026 | 123,7143 | 122,8573 | +0,86 |
| 07/2026 | 112,5217 | 112,4782 | +0,04 |
| 08/2026 | 114,9524 | 114,3333 | +0,62 |

O gap é exatamente o que esta base **não** aplica: afastamento e piso de 50%.

Numerador contra `producao_consultores`: R$ 10.011.092,38 (individual) vs
R$ 10.012.897,32 (cards) em 07/2026. A diferença de R$ 1.804,94 **não é erro
desta feature** — ver o achado abaixo.

Produtividade da rede 07/2026: R$ 3.868,27/dia (individual) contra
R$ 3.870,47/dia do card (0,06%), diferença que vem do denominador.

O caso de uso, medido: TACILA DE LIMA GUIMARAES produziu R$ 20.103 em
**10 dias** — R$ 2.010/dia, **118% da média da própria loja**. Pela leitura
de valor absoluto ela estava no fim da lista.

## Achado: `excluir_supervisores` casa grafia EXATA

`kpis/gerais.py:43-55` usa `df["CONSULTOR"].isin(df_sup["SUPERVISOR"])`.
`supervisor_vigencia` grava `DJANE MARIA PEREIRA DOS SANTOS` (upper) e a
produção chega como `Djane Maria Pereira dos Santos` — o `isin` não casa e a
supervisora **atravessa o corte**, entrando em rankings, na aba Gestão como
consultora e no numerador `producao_consultores`:

| Competência | Produção de supervisor que escapa |
|---|---|
| 06/2026 | R$ 3.713,04 |
| 07/2026 | R$ 1.804,94 |
| 08/2026 | R$ 3.259,26 |

Uma pessoa, três meses. É a mesma classe de defeito do progress de hoje
(população misturada), do outro lado do nome.

**Não corrigido na origem** — mexer em `excluir_supervisores` muda número
publicado em rankings, médias e cards, e é decisão do usuário (tier
"perguntar primeiro"). `kpis/produtividade.py` se protege com
`_sem_supervisores`, que chama o corte compartilhado e acrescenta o
casamento normalizado; se a origem for corrigida, a rede vira no-op.

## Decisões não óbvias

- **Dias da pessoa vão para a loja de MAIOR permanência**, junto com o
  dinheiro dela. Atribuir dias por segmento e produção por loja de
  identificação criaria loja com os dias de uma pessoa e a produção de outra.
  Numerador e denominador seguem a mesma regra de atribuição; qualquer
  distorção de transferência é idêntica dos dois lados (5 pessoas em 07/2026).
- **Produção sem vínculo é `NaN`, nunca 0.** Zero é afirmação sobre a pessoa;
  o furo está no ledger. Essas linhas saem dos dois lados de todo benchmark e
  viram diagnóstico nominal — nunca recebem denominador emprestado.
- **Elegível sem venda fica na tabela.** Removê-lo faria a média da loja subir
  no mês em que mais gente deixou de vender — a mesma patologia que o
  denominador ponderado corrigiu em 2026-08-25.
- **A série exclui o mês corrente** e não liga pontos sobre lacuna
  (`connectgaps=False`).
- **Aviso da base é `st.warning`, não `caption`.** A leitura errada
  ("fulano trabalha pouco") é o risco central desta base, e ela não tem como
  se defender sozinha na tela.

## Follow-ups

1. Decidir sobre `excluir_supervisores` (normalizar na origem muda números
   publicados).
2. `peso_headcount_escopo` devolve `None` quando há um consultor selecionado
   na sidebar, porque "não existe peso por pessoa" (`gerais.py:85-89`). Agora
   existe: `carregar_vinculos_consultores` poderia sustentar o card também
   nesse filtro.
3. A frente de origem do plano (ST-00 → ST-11) segue de pé para o contrato do
   Bereshit e para congelar snapshots por competência. Esta entrega não a
   substitui — calcula ao vivo, sem congelamento.
