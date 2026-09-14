# 2026-09-14 — Etapa 3 da revisão: critérios, paginação e tratamento de falhas

**Agente:** Claude Code
**Tipo:** bugfix + refactor
**Arquivos tocados:** `src/shared/dias_uteis.py`, `src/dashboard/loaders.py`,
`src/dashboard/kpis/produtos.py`, `app.py`, `tests/conftest.py`
+ 3 arquivos de teste novos, `docs/agents/{data-layer,business-rules}.md`
**Commit(s):** `bfffd6b` (feriados), `078032d` (paginação), `5dc298e` (critérios)

## Objetivo

Etapa 3 do plano, critério declarado: **comportamentos compartilhados
testados e documentação alinhada**. Itens 5 e 6 da revisão, mais a
parte do item 4 sobre critérios de produto repetidos.

## O que foi feito

### Item 5 — falha de consulta virava "nenhum feriado" por 24h

`carregar_feriados_supabase` capturava qualquer exceção e devolvia
`set()` — **de dentro da função cacheada**. Uma indisponibilidade de 1
segundo virava "nenhum feriado neste mês" pelo TTL inteiro, sem erro na
tela: sem feriados o `total_du` infla, a meta diária cai e a projeção
sobe.

Agora são estados distintos: `set()` = nenhum feriado (cacheável);
`FeriadosIndisponiveis` = a consulta falhou.

### Item 6 — leitura sem paginação truncava em silêncio

`carregar_consultores_ativos` e `_fetch_vinculos_consultores` liam a
tabela inteira num `.execute()`. Passando do teto da API, pessoas
sumiriam do universo de ativos e dias elegíveis do denominador de
produtividade — sem erro, só médias mais altas.

### Item 4 (parte) — uma definição de acelerador, duas superfícies

"O que é um BMG Med / Vida Familiar / Emissão / Super Conta" estava
escrito duas vezes, com o mesmo texto, em `kpis/gerais.py` e
`kpis/produtos.py`. `kpis/produtos.py` passa a delegar.

## Decisões não óbvias

- **Verifiquei a premissa do fix de feriados antes de escrevê-lo.** O
  plano inteiro depende de `st.cache_data` **não** guardar exceção.
  Testei: exceção não é cacheada, e o sucesso seguinte é cacheado
  normalmente. Então deixar o erro subir já resolve "impedir que a
  falha seja armazenada como sucesso" — o próximo rerun tenta de novo.
  Se a premissa fosse falsa, o desenho teria de ser outro.

- **Feriados falham "alto e macio".** `carregar_feriados` continua
  devolvendo `set()` — derrubar o dashboard por causa do calendário
  seria pior —, mas registra: log de erro + marca em
  `periodos_com_feriados_indisponiveis()`, e o `app.py` avisa
  explicando o efeito nos números. Mesma régua da decisão do chat IA:
  número errado sem sinal é pior que número com ressalva.

- **Sucesso posterior apaga a marca.** Sem isso o aviso ficaria na tela
  pelo resto da sessão depois de o Supabase voltar, e o usuário passaria
  a desconfiar de número que já está certo.

- **Paginar não custa request a mais no volume de hoje.**
  `_paginar_keyset` encerra quando a página volta incompleta, então com
  ~112 consultores e ~400 linhas no ledger é **uma** requisição, igual
  à leitura única de antes. O request extra só aparece com mais de uma
  página — o caso em que hoje se perdia dado. Dois testes **medem
  páginas servidas**, não só o resultado, porque é isso que importa no
  plano Nano.

- **Paginação por `id` (PK), nunca por `nome`.** O loader de
  consultores existe justamente porque a tabela TEM nomes duplicados
  (desligamento em linha nova). Chave repetida pula linhas na virada da
  página. A ordem do servidor deixou de ser por nome, o que não muda a
  saída: `_colapsar_cadastro_recente` reduz por nome normalizado
  (max `updated_at`, independente de ordem) e devolve ordenado. Tem
  teste com as duas linhas da mesma pessoa em páginas diferentes.

- **Super Conta: uma divergência real desapareceu na junção.**
  `mascaras_aceleradores` prefere a flag canônica `is_super_conta`
  (derivada em `kpis/consolidacao.py`) e só cai para o `SUBTIPO` quando
  o frame não a traz. Em `kpis/produtos.py` o `SUBTIPO` era a ÚNICA
  fonte — mesmo resultado hoje, porque a derivação é idêntica, mas
  deixaria de ser no dia em que a regra mudar na consolidação. Tem
  teste com flag e SUBTIPO em desacordo.

## Por que a suíte não pegava a paginação

Os duplos de Supabase ignoravam `.order`/`.limit`/`.gt` e devolviam
tudo num `.execute()`: **um loader sem paginação passava exatamente
como um paginado**. `ClienteFakePaginado` (conftest) honra o contrato
do keyset e conta páginas servidas. Sabotei o código de volta para
confirmar que os testes novos falham sem a correção: 6 de 11 quebram.

É o mesmo padrão da Etapa 1 (teste que auditava assinatura sem
exercitar invalidação) e da Etapa 2 (regra enterrada no renderer, sem
cobertura): **o teste precisa exercitar o mecanismo, não a aparência
dele.**

## Escopo estendido, e o que ficou de fora

A varredura por leitores sem paginação achou 7 além dos 2 que a revisão
nomeou. **Dois foram corrigidos junto**, por serem o mesmo defeito na
mesma forma:

- `carregar_consultores_cadastro` — MESMA tabela `consultores` que
  acabou de ser paginada ao lado;
- `carregar_supervisores` — ledger `supervisor_vigencia`, mesmo formato
  do `consultor_vigencia`. Truncar ali tira supervisor da lista de
  **exclusão**: ele volta a contar como consultor e infla o
  denominador das médias.

**Os 5 restantes ficaram de fora, deliberadamente:**

| Loader | Por que não |
|---|---|
| `carregar_categorias` | tabela de referência, dezenas de linhas |
| `carregar_lojas_ativas` / `carregar_lojas_regioes` | idem |
| `_fetch_metas_produto` / `_fetch_metas_consultor` | já filtrados por competência |

`carregar_periodo` / `carregar_ultimo_periodo` têm `.limit()`
deliberado (top-N), não são leitura de tabela.

## Pendências / follow-ups

- [ ] Os 5 loaders acima, se algum crescer. `_fetch_metas_consultor` é
      o mais provável (uma linha por consultor × competência).
- [ ] Terceira superfície de critérios: `_PRODUTOS_QTD` +
      `_mask_subtab` (`tabs/produtos.py`). É config declarativa com
      critérios mais granulares (digitação, subtipos, exclusões por
      tipo de operação) que alimentam as sub-abas — **não** são as
      mesmas 4 máscaras. Unificar seria redesenho, não consolidação.
- [ ] `limpar_cache_feriados` faz `st.cache_data.clear()`, que limpa
      **todos** os caches do app, e tem uma linha morta
      (`__wrapped__ = None`). Funciona, mas é bala de canhão: o CRUD de
      um feriado derruba o cache de contratos, metas e tudo mais.
      Encontrado ao mexer no módulo; fora do escopo da etapa.
- [ ] Da Etapa 1: mesmo bug de atualidade em
      `tabs/produtos.py::_carregar_mes_comparativo`.
- [ ] Da Etapa 2: varrer o resto do codebase atrás de comparações de
      nome de pessoa com `strip + upper` inline.

## Referências

- Revisão externa de 09/2026, itens 4 (parte), 5 e 6 — etapa 3 de 3.
- Etapa 1: [2026-09-14-etapa1-rls-e-caches.md](2026-09-14-etapa1-rls-e-caches.md)
- Etapa 2: [2026-09-14b-etapa2-separacao-por-dominio.md](2026-09-14b-etapa2-separacao-por-dominio.md)
- Docs atualizados: [data-layer.md](../data-layer.md) (custo da
  paginação, `ClienteFakePaginado`, ausência × falha de feriados),
  [business-rules.md](../business-rules.md) (onde cada critério mora).
