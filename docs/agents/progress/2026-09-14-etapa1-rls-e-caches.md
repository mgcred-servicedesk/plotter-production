# 2026-09-14 — Etapa 1 da revisão: RLS divergente + os dois mecanismos de cache

**Agente:** Claude Code
**Tipo:** bugfix
**Arquivos tocados:** `src/dashboard/rls.py`, `src/dashboard/loaders.py`,
`src/dashboard/kpis/gerais.py`, `src/dashboard/chat_ia/tools.py`,
`tests/test_rls_reconquista.py` (novo),
`tests/test_rls_cancelados.py`, `tests/test_loaders_cache_version.py`,
`tests/test_kpis_gerais.py`, `tests/test_app_helpers.py`,
`tests/test_chat_ia_tools.py`, `docs/agents/{rls,data-layer,architecture,ui-components}.md`
**Commit(s):** (a commitar)

## Objetivo

Fechar a Etapa 1 do plano de refatoração ("corrigir RLS e os dois
mecanismos de cache"), com o critério declarado: **os testes reproduzem
os problemas e passam depois das correções**. São os itens 1, 2 e 3 da
revisão externa.

## O que foi feito

### 1. Cache de KPIs servia número velho (alta)

`_chave_kpis` tinha seis componentes — período, perfil efetivo, escopo e
os dois filtros de UI —, **todos controlados pelo usuário**. Dado novo
chegando sozinho (fim do TTL de `consolidar_dados`: 30 min no mês
corrente; upload do angry-man; correção do ETL) não mexia em nenhum
deles, então as seis `obter_*_periodo` seguiam devolvendo o número da
carga anterior até alguém tocar num filtro.

Reprodução: `obter_kpis_gerais_periodo` com 1 linha de R$ 100 →
`total_vendas == 100`; chamada seguinte, mesmo perfil e mesma sidebar,
com 2 linhas somando R$ 200 → **100 de novo**.

Correção: 7º componente `revisao`, a impressão digital das entradas de
cada função (`_revisao_entradas` / `_revisao_frame`). Cada
`obter_*_periodo` passa **as suas** entradas, não as de todas — a chave
de uma não invalida o cache da outra à toa.

### 2. Duas implementações de RLS com comportamentos divergentes (alta)

`rls.aplicar_rls` negava acesso quando faltava informação; o recorte da
Reconquista (`loaders._filtro_rls_reconquista`) devolvia a base
**inteira** nos mesmos casos — tratava "não sei recortar" como "não
precisa recortar". Quatro portas abertas: perfil ausente, escopo vazio,
role desconhecido e coluna de escopo ausente no frame.

Correção em duas camadas:

- `rls.decidir_rls(colunas_por_perfil) -> DecisaoRls` — a decisão de quem
  vê o que passa a existir **uma vez**, com três estados e só três
  (global / recortar por coluna / negar). Usada por `aplicar_rls` e por
  `_filtro_rls_reconquista`.
- Cada adaptador nega quando a coluna de escopo não existe *naquele*
  frame — parte que a decisão central não tem como saber por ele.

Também fechados, na mesma passagem (fail-closed já era a regra
documentada; estes três pontos ainda não seguiam):
`aplicar_rls_metas`/`_supervisores` sem perfil autenticado,
`perfil["perfil"]` cru virando `KeyError` em vez de negação, e
`obter_regioes_permitidas`, que sem perfil devolvia a lista completa de
regiões da empresa.

### 3. `_cache_version` era ignorado pelo Streamlit (alta)

Argumento prefixado por `_` é excluído do hash da chave — mesmo passado
explicitamente pelo chamador. O versionamento declarado nunca
funcionou. Renomeado para `cache_version` nos quatro wrappers e nos
dois dispatchers; o teste-catraca ganhou casos que exercitam a
invalidação **real** (mesma versão reusa o fetch, versão diferente
refaz), em vez de só auditar a assinatura.

## Decisões não óbvias

- **Por que impressão digital dos frames, e não um token de revisão
  vindo do loader?** O token seria exato e O(1), mas exigiria mudar
  `DadosPeriodo`, os seis call sites em `app.py`, e ainda assim
  deixaria de fora `carregar_metas_produto_consultor`, que entra pelo
  caminho do consultor **fora** do gateway `carregar_periodo_dashboard`.
  A impressão digital é local e cobre automaticamente o que cada função
  de fato consome. Decisão do usuário, entre três opções apresentadas.

- **Por que não `pd.util.hash_pandas_object`?** Medido: 7,8 ms por
  frame a 20 mil linhas — as seis funções juntas pagariam ~230 ms por
  rerun, mais caro que o cálculo que o cache existe para evitar. A
  versão adotada (linhas + colunas + somas numéricas) custa ~0,4 ms no
  mesmo frame. **Premissa a validar:** o preço é uma colisão teórica —
  uma recarga que preserve contagem de linhas, nomes de coluna E todas
  as somas passa despercebida. Não conhecemos cenário real assim.

- **`NaN` vira a string `"nan"` na revisão.** `float('nan') !=
  float('nan')`: deixado cru, faria a chave nunca mais bater e o cache
  nunca mais acertar — o oposto do bug que estamos corrigindo. Tem
  teste próprio.

- **`revisao` é parâmetro obrigatório de `_chave_kpis`, sem default.**
  Uma `obter_*_periodo` nova que esqueça de passá-lo quebra na hora, em
  vez de nascer com cache silenciosamente velho.

- **O mapa `role → coluna` continua do chamador em `decidir_rls`.** O
  nome da coluna muda com o dataset (`LOJA` nos frames do dashboard,
  `loja` minúsculo na view de Reconquista); a regra de autorização não.
  Centralizar o mapa junto obrigaria a decisão central a conhecer o
  vocabulário de cada fonte.

- **Não mexemos na consultor→loja de `aplicar_rls_metas` /
  `aplicar_rls_supervisores`.** As duas derivam lojas de `df_dados`,
  regra genuinamente diferente das outras; usam a mesma disciplina
  fail-closed, mas não passam por `decidir_rls`. Unificá-las é assunto
  da Etapa 2.

- **Nenhuma mudança no tráfego com o Supabase** (pergunta do usuário,
  plano Nano). As `obter_*_periodo` não fazem query: operam sobre
  frames em memória. Uma invalidação a mais ali recalcula em pandas,
  não refaz fetch. O rename `cache_version` não muda a cardinalidade da
  chave (o dispatcher passa constante) — só um round de cache-miss no
  primeiro deploy, que um restart causaria de qualquer forma. O
  fail-closed filtra **depois** do fetch.

- **`test_chat_ia_tools::test_consultor_atingimento` quebrou pelo
  fail-closed** (o teste não loga perfil, e `aplicar_rls_metas` passou a
  devolver vazio). Neutralizado no namespace de `chat_ia.tools`, como
  manda o docstring daquele módulo — o teste mede o reshape do ranking,
  não o RLS, que tem cobertura própria.

- **O chat de IA passa a falhar alto quando o ranking de atingimento
  fica sem metas** (`tools._sem_metas`). Decisão do usuário. O bug que
  a quebra do teste expôs não era do teste: em produção,
  `calcular_ranking_*` sem metas não levanta — devolve **0% de
  atingimento para todo mundo**, e o modelo reportaria ao admin que a
  operação inteira está zerada. As duas causas conhecidas (não há metas
  no período; RLS fail-closed esvaziou o frame) têm a mesma resposta:
  não há base para calcular atingimento. `agent.py` marca o bloco com
  `is_error=True` a partir da chave `erro`, então o modelo vê a falha
  como falha. A trava é **só** do critério `atingimento`; `pontos`,
  `ticket_medio` e `media_du` não dependem de meta e seguem
  respondendo.

  Contexto que sustenta a escolha: o chat é Beta e **admin-only** —
  `tabs/chat_ia.py` barra os outros quatro perfis com "Em breve", ainda
  que a matriz de `permissions.py` marque a aba como visível para os
  cinco. Enquanto o PO humano desenha a feature, número errado com cara
  de certo custa mais que um "não consegui".

## Pendências / follow-ups

- [ ] **Mesmo bug de atualidade em
      `tabs/produtos.py::_carregar_mes_comparativo`** (não estava na
      revisão). O cache em `session_state` guarda o resultado de
      `consolidar_dados` sob uma chave sem revisão: enquanto ela não
      muda, o `consolidar_dados` nem chega a ser chamado de novo, então
      o fim do TTL do loader não tem efeito. Impacto baixo — os dois
      comparativos são meses **históricos** (TTL de 24h, dado
      praticamente estático); a exceção é o dia 1º, quando "mês
      anterior" ainda recebe pagamentos atrasados. Decidir se entra na
      Etapa 2.
- [ ] `ALLOWLIST_DIVIDA_CONHECIDA` segue com 25 wrappers sem
      `cache_version` (dívida documentada, fora do escopo desta etapa —
      pagá-la de uma vez invalidaria o cache de produção de 25 fontes
      simultaneamente).
- [ ] Etapa 2: separar consultas, transformações e apresentação por
      domínio, preservando as interfaces públicas.
- [ ] Etapa 3: consolidar critérios de produto repetidos, paginação
      (`consultores`/`vínculos`) e o `except` mudo de
      `shared/dias_uteis.py`. **A paginação aumenta o número de
      requisições ao Supabase** — medir antes de aplicar, dado o Nano.

## Referências

- Revisão externa de 09/2026, itens 1, 2 e 3 (etapa 1 de 3).
- Docs atualizados: [rls.md](../rls.md) (seção "Onde a decisão de
  autorização mora"), [data-layer.md](../data-layer.md)
  (`cache_version`), [architecture.md](../architecture.md) (7º
  componente da chave), [ui-components.md](../ui-components.md).
