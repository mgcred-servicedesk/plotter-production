# 2026-09-14 — Etapa 2 da revisão: separar consultas, transformações e apresentação

**Agente:** Claude Code
**Tipo:** refactor
**Arquivos tocados:** `src/dashboard/loaders.py`, `src/dashboard/rls.py`,
`src/dashboard/tabs/analiticos.py`, e os novos
`src/dashboard/kpis/{consolidacao,reconquista,seguros}.py`,
`src/dashboard/presets_gestao.py` + 3 arquivos de teste novos
**Commit(s):** `d890b13`, `b029ea9`, `b7db506`, `7d14754`, `eb2102e`
+ correções de SRP: `e3d0582` (normalização), `bb6d398` (acelerador)

## Objetivo

Etapa 2 do plano, critério declarado: **mesmos resultados e interfaces
públicas preservadas**. Item 4 da revisão — "responsabilidades voltaram
a se concentrar em módulos grandes: `loaders.py` tem 3.566 linhas,
reunindo consultas, cache, pontuação, Reconquista, autorização e
escrita de presets".

## O que foi feito

Cinco domínios, um commit cada (revisável e revertível sozinho):

| # | Domínio | Saiu de | Foi para |
|---|---|---|---|
| 1 | Seguros (união/dedup/classificação) | `tabs/analiticos.py` | `kpis/seguros.py` |
| 2 | Consolidação e pontuação | `loaders.py` | `kpis/consolidacao.py` |
| 3 | Reconquista e acelerador | `loaders.py` | `kpis/reconquista.py` |
| 4 | Presets (escrita) | `loaders.py` | `presets_gestao.py` |
| 5 | RLS da Reconquista | `loaders.py` | `rls.py` |

`loaders.py`: **3.583 → 2.755 linhas** (−828, já com as duas
correções de SRP abaixo). O que sobrou é o que o
nome promete: consultas, cache dual `_atual`/`_historico` e paginação.

## Decisões não óbvias

- **A rede de segurança não podia ser a suíte.** Medido antes de
  começar: `loaders.py` com 45% de cobertura e `analiticos.py` com
  18%. Testar depois não provaria que nada mudou. Por isso a técnica
  foi mover corpos **byte-idênticos** e provar isso mecanicamente:
  um script compara a AST normalizada (`ast.unparse`, sem docstring e
  sem decorators) de cada função entre o `HEAD` anterior e o destino.
  **23 funções provadas idênticas.** Só depois disso vieram os testes.

- **Onde a prova não bastava, a evidência foi statement a statement.**
  `_executar_consolidacao` não foi movida, foi **dividida**. A prova
  ali comparou as instruções: as 5 primeiras (carga) idênticas ao
  original, as 24 seguintes (transformação) idênticas, e
  `preencher_categoria_fallback` com os mesmos 11 statements.

- **`carregar_categorias` é injetado como callable, não como frame.**
  Importá-lo no módulo de domínio criaria ciclo. Carregá-lo
  ansiosamente na fachada acrescentaria **uma consulta ao Supabase por
  consolidação** no caso comum (nenhuma linha sem categoria) — o que
  importa no plano Nano. Callable preserva a laziness original, e o
  nome do parâmetro é igual ao da função que substituiu, o que manteve
  o corpo byte-idêntico de graça. Tem teste nos dois níveis.

- **Re-export em vez de atualizar call sites.** O critério da etapa é
  "interfaces públicas preservadas": `VIGENCIA_*`, as três funções de
  preset, as duas de RLS e `aplicar_nomes_display_produto` seguem
  importáveis de `loaders`. O `# noqa: F401` está acompanhado do
  motivo escrito ao lado — para o ruff é import sem uso; para quem
  importa `loaders`, é a fachada continuando a existir.

- **Presets foram junto com a escrita, não fatiados.** Nos outros
  domínios a fronteira é consulta × regra; nesse é **leitura ×
  escrita**. Fatiar não faria sentido: são 3 funções de IO e 2
  helpers, coesos. O módulo novo documenta o que sustenta a segurança
  (service_role tem BYPASSRLS, então o filtro por `usuario_id` dentro
  de cada query é o que impede mexer em preset alheio).

- **O que ficou para trás, e a correção do diagnóstico.** Classifiquei
  `_faixas_acelerador_por_qtd`, `_faixa_agregada_acelerador` e
  `_por_consultor_acelerador` como "orquestração, não regra pura" e as
  deixei em `loaders.py`. **A classificação estava errada** — corrigida
  no commit `bb6d398`, ver a seção de SRP abaixo. `_acelerador_no_escopo`
  esse sim ficou: depende do perfil logado e é gate de produto, não
  cálculo.

## O que a extração revelou

Regra que sai do lugar onde estava enterrada vira testável. Os três
domínios novos nasceram praticamente sem cobertura e fecharam assim:

| Módulo | Antes | Depois | Testes novos |
|---|---|---|---|
| `kpis/seguros.py` | 12% | **100%** | 22 |
| `kpis/consolidacao.py` | 38% (0% em `consolidar_pontuacao`) | **100%** | 29 |
| `kpis/reconquista.py` | 39% | **96%** | 59 |

`consolidar_pontuacao` é a função que decide **quanto cada contrato
pontua** e não era exercitada por nenhum teste — estava colada na
carga. Os testes fixam a ordem das regras (`conta_valor` zera VALOR
*antes* de `pontos = VALOR × PONTOS`; emissão zera os dois *depois*,
por cima da categoria) e o mapa de Portabilidade, inclusive a ausência
deliberada de `CONSIG_PRIV`.

**Lacuna encontrada — e corrigida em seguida (`e3d0582`):**
`_norm_texto` fazia apenas `strip + upper`, sem dobrar acento, então o
merge de produção por nome não casava `JOÃO` com `JOAO` e a pessoa
aparecia zerada no acelerador. Ver a seção "Duas correções de SRP"
abaixo.

## Duas correções de SRP, depois da etapa

A revisão da própria Etapa 2 (a pedido do usuário) expôs duas
responsabilidades sem dono. As duas seguem o mesmo padrão: quando uma
responsabilidade não tem lugar, ela é reimplementada onde faz falta —
e os clones divergem ou carregam o mesmo bug.

### 1. Normalização de texto (`e3d0582`)

`JOÃO DA SILVA` e `JOAO DA SILVA` não casavam no merge de produção. A
correção óbvia — dobrar acento no normalizador — **quebraria a aba de
Produtos**: a config tem literais acentuados (`"CARTÃO BENEFICIO"`,
`"Venda Pré-Adesão"`) e comparação contra constante do código só
funciona se nenhum lado dobrar.

São duas responsabilidades com a mesma implementação, e por isso foram
confundidas. Agora têm nome e dono em `src/shared/texto.py`:

| Função | Compara | Dobra acento? | Por quê |
|---|---|---|---|
| `normalizar_nome` | pessoas, entre fontes do banco | **sim** | os dois lados são dado digitado por gente diferente; acento é ruído |
| `normalizar_rotulo` | rótulo de dado × constante do código | **não** | dobrar só de um lado faz a linha sumir da contagem, em silêncio |

Estava reimplementada em **5 lugares**, todos com o mesmo bug. Os
quatro primeiros passam a delegar. O inline de `_excluir_sup`
**precisava** mudar junto: com `supervisores_norm` dobrando e a
comparação não, supervisor acentuado deixaria de ser excluído e
voltaria a aparecer como consultor.

Detalhe que custou duas tentativas: a dobra usa NFKD + `replace` do
bloco de diacríticos combinantes, e **não** o ida-e-volta por ASCII —
este quebra em série toda nula (chega como `float`, e `.str` levanta
`AttributeError`). E o regex precisa de string **não-crua**: as colunas
são Arrow-backed e vão para o RE2 do pyarrow, que não entende escape
`\u`. Os dois casos têm teste.

### 2. Acelerador: a carga volta ao orquestrador (`bb6d398`)

`aplicar_rls(carregar_cobranca_consignavel(mes, ano))` acontecia **duas
vezes por render** — uma dentro de `_por_consultor_acelerador` e outra
em `carregar_reconquista`, que a chama. O gate idem. Não custava query
(o `st.cache_data` absorve), mas era duplicação que só existia porque
as duas funções achavam que a carga era responsabilidade delas.

**A pergunta que destravou:** mover as funções exigiria mudar a
responsabilidade de quem as invoca? Não — e é o contrário.
`carregar_reconquista` já era o orquestrador: já carregava, já aplicava
RLS, já montava o dict. A responsabilidade dele tinha **vazado para
baixo**, e a duplicação era o preço. Consolidar reduz de dois lugares
que carregam para um.

As três foram para `kpis/reconquista.py` recebendo frames e um
`resolver_faixas` injetado. O gate ficou com o chamador, que é quem
conhece o usuário logado. Call site único, então nenhuma interface
pública mudou. Prova por AST: as duas funções de faixa com corpo
idêntico; em `montar_acelerador_por_consultor`, o diff é exatamente
gate + 3 cargas + RLS saindo, sem uma linha de regra tocada.

**Lição para a próxima etapa:** "chama um loader" não é o mesmo que "é
orquestração". Foi esse atalho que me fez classificar errado na
primeira passagem.

## Pendências / follow-ups

- [x] ~~Decidir sobre a normalização de acento~~ — feito em `e3d0582`.
- [x] ~~Trazer `_por_consultor_acelerador` e as duas funções de faixa
      para `kpis/reconquista.py`~~ — feito em `bb6d398`.
- [ ] Varrer o resto do codebase atrás de outras comparações de nome
      de pessoa que ainda usem `strip + upper` inline. As 5 conhecidas
      foram tratadas; a busca foi por `CONSULTOR`/`SUPERVISOR` e pode
      ter deixado passar comparação com outro nome de coluna.
- [ ] `tabs/analiticos.py` ainda tem 1.400 linhas e 19% de cobertura.
      A Etapa 2 tirou dali só o que a revisão nomeou (seguros); os
      `_render_*` restantes são UI de verdade, mas
      `_render_reconquista_detalhamento` tem 191 linhas e
      provavelmente esconde regra.
- [ ] Etapa 3: consolidar critérios de produto repetidos entre
      `kpis/gerais.py`, `kpis/produtos.py` e `tabs/produtos.py`;
      paginação de `consultores`/`vínculos`; `except` mudo de
      `shared/dias_uteis.py`. **A paginação aumenta o número de
      requisições ao Supabase** — medir antes, dado o Nano.
- [ ] Da Etapa 1, ainda aberto: mesmo bug de atualidade em
      `tabs/produtos.py::_carregar_mes_comparativo`.

## Referências

- Revisão externa de 09/2026, item 4 (etapa 2 de 3).
- Etapa 1: [2026-09-14-etapa1-rls-e-caches.md](2026-09-14-etapa1-rls-e-caches.md)
- Docs atualizados: [architecture.md](../architecture.md) (mapa de módulos).
