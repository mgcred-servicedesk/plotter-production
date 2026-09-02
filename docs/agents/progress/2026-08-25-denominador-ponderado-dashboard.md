# 2026-08-25 — Dashboard passa a dividir pelo headcount ponderado

**Agente:** Claude Code
**Tipo:** feature (regra de negócio + data layer + UI)
**Arquivos tocados:**
`src/dashboard/loaders.py`, `src/dashboard/kpis/gerais.py`,
`src/dashboard/kpis/pontuacao.py`,
`src/dashboard/pages/dashboard_pontuacao.py`, `app.py`,
`src/dashboard/formatters.py`, `src/dashboard/ui/kpi_cards.py`,
`src/dashboard/ui/kpi_cards_reforma.py`,
`src/dashboard/ui/kpi_cards_pontuacao.py`,
`tests/test_kpis_gerais.py`, `docs/HEADCOUNT_ETL.md`;
no `angry-man`: `docs/headcount.md`
**Commit(s):** —

## Objetivo

Fechar a pendência que o usuário chamou de centro do problema: dashboard e
Caderno não argumentavam com os mesmos dados. O Caderno já dividia por
`weightedHeadcount` (migration 092); o dashboard continuava dividindo por
quem produziu no período.

## O achado que mudou o enquadramento

A diferença de tamanho é pequena — em 07/2026, ~113 produtores contra peso
112,4782 — e foi por isso que passou tanto tempo sem ser vista. O problema
é a **direção**:

> Excluir quem não vendeu faz a média do dashboard **subir** exatamente no
> mês em que mais gente não vendeu, enquanto a do Caderno **desce**.

Os dois números se moviam em sentidos opostos. Nenhuma reconciliação era
possível enquanto o denominador viesse da produção, e não do quadro.

## O que foi feito

- **`carregar_headcount_ponderado(mes, ano)`** (`loaders.py`): lê
  `fn_headcount_ponderado` (091) e devolve `[LOJA, PESO, CABECAS,
  DU_COMPETENCIA, REGIAO, REGIAO_ATUAL]`. Reaplica os **mesmos dois
  filtros** que a 092 reaplica sobre a 091 — loja inativa e backoffice —
  porque a 091 responde "quem estava onde", não "o que entra na média".
  REGIAO vem da região atual da loja, para passar pelo mesmo `aplicar_rls`.
- **`peso_headcount_escopo`** (`gerais.py`): soma o peso do escopo já
  recortado, ou `None` quando não há denominador confiável.
- **Denominador trocado** em `calcular_medias_du_por_nivel` e
  `calcular_medias_pontos_por_nivel`. Retorno ganhou `peso_consultores` e
  `denominador_consultores` (`"peso"` | `"produtores"`).
- **Cards** (vendas, pontuação e o card compacto) passam a dividir pelo
  peso e a rotular o rodapé com `112,5 gente-mês · 113 produziram`.
- **14 testes novos**; suíte em 609 passando, `ruff` limpo.

## Verificação ponta a ponta

Com o banco real, 07/2026: o peso somado pelo loader dá **112,4782** —
idêntico, até a quarta casa, ao `weightedHeadcount` que o Caderno publica.
Dois caminhos independentes (loader Python e SQL da 092) chegando ao mesmo
número é a evidência de que os filtros foram replicados corretamente.

Média DU por consultor em 07/2026: R$ 3.852,60 (antes) → R$ 3.870,47
(agora). O deslocamento é pequeno **neste mês** porque produtores e peso
quase coincidiram; o ganho é estrutural.

## Decisões não óbvias

- **O escopo vem do FILTRO, nunca da produção.** Loja dentro do escopo
  continua no denominador mesmo sem contrato no período. É o princípio que
  `aplicar_rls_metas` já seguia ("não usa a presença de contratos como
  proxy de escopo"), e usar contrato como proxy reintroduziria exatamente
  o viés que a mudança corrige.

- **Produtores viram diagnóstico, não somem.** Decisão do usuário, e é o
  mesmo movimento que a 092 fez do outro lado: a contagem antiga virou
  `countedInRegistry`. Ver a diferença entre os dois números é o que expõe
  a patologia; escondê-la seria repetir o erro em outra direção.

- **Consultor selecionado cai no denominador antigo.** A 091 agrega por
  LOJA e não existe peso por pessoa. Restringir a uma pessoa deixaria o
  denominador da loja inteira contra a produção de uma só — pior que o
  problema original. `peso_headcount_escopo` devolve `None` e o card diz
  qual denominador usou.

- **Mês corrente usa o peso da competência inteira.** A 091 calcula sobre
  os DU cheios do mês; a divisão por `du_decorridos` continua separada.
  Quem saiu no meio já entra com peso parcial, e quem está com janela
  aberta pesa 1,0 de qualquer forma. Peso pro-rata do decorrido seria
  outro cálculo — não foi feito.

- **`peso_headcount` entra por parâmetro, não por query.** As funções de
  KPI não consultam o banco (convenção do projeto, e `loaders.py` já
  importa de `kpis/gerais.py` — o caminho inverso seria import circular).
  Quem carrega e recorta é o `app.py`.

- **`carregar_consultores_ativos()` não foi tocada.** Ela responde outra
  pergunta — "quem existe no cadastro hoje", usada para listar quem não
  produziu e para os filtros da sidebar. Deixou de ser denominador de
  média, mas continua correta no papel dela.

## Pendências / follow-ups

- [ ] **Rematerializar as 14 competências** depois que o bereshit passar a
      ler `weightedHeadcount` — o passo 3 da ordem de chamada.
- [ ] Migration **095** segue pendente de aplicação (ver
      [progress do mesmo dia](2026-08-25-headcount-guardas-cadastro.md)).
- [ ] **Peso por pessoa** não existe. Se o filtro de consultor precisar do
      denominador ponderado, é uma extensão da 091 — decisão à parte.
- [ ] Conferir os cards em tela: a verificação foi numérica (loader + KPIs
      + testes), não visual.

## Referências

- [HEADCOUNT_ETL.md §7](../../HEADCOUNT_ETL.md) — o lado Python
- [progress/2026-08-25-headcount-guardas-cadastro.md](2026-08-25-headcount-guardas-cadastro.md)
- [progress/2026-08-21-caderno-headcount-ponderado.md](2026-08-21-caderno-headcount-ponderado.md)
- Migrations: 091 (peso), 092 (Caderno)
