# 2026-09-14 — Etapa 2 da revisão: separar consultas, transformações e apresentação

**Agente:** Claude Code
**Tipo:** refactor
**Arquivos tocados:** `src/dashboard/loaders.py`, `src/dashboard/rls.py`,
`src/dashboard/tabs/analiticos.py`, e os novos
`src/dashboard/kpis/{consolidacao,reconquista,seguros}.py`,
`src/dashboard/presets_gestao.py` + 3 arquivos de teste novos
**Commit(s):** `d890b13`, `b029ea9`, `b7db506`, `7d14754`

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

`loaders.py`: **3.583 → 2.884 linhas** (−699). O que sobrou é o que o
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

- **O que deliberadamente NÃO saiu de `loaders.py`:**
  `_faixas_acelerador_por_qtd`, `_faixa_agregada_acelerador` e
  `_por_consultor_acelerador` chamam loaders (faixas, cobrança
  consignável, consultores ativos, supervisores). São **orquestração**,
  não regra pura, e trazê-las exigiria injetar cinco loaders —
  mudança de assinatura que contraria o critério da etapa.
  `_acelerador_no_escopo` também ficou: depende do perfil logado e é
  gate de produto. Registrado no topo de `kpis/reconquista.py`.

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

**Lacuna encontrada (não corrigida — decisão do usuário):**
`_norm_texto` faz apenas `strip + upper`, sem dobrar acento. O merge
de produção por nome em `_juntar_producao` portanto **não casa** `JOÃO`
com `JOAO`: a produção da pessoa cai para zero silenciosamente (ela
aparece zerada, não some do universo). A docstring da própria função
sugere o contrário — "as fontes podem vir com grafia levemente
diferente do cadastro". Os testes que fixam isso têm `_NAO_` no nome,
para que mudar seja uma decisão consciente. Se mudar, `_norm` de
`tabs/produtos.py` — que `_norm_texto` declara replicar — precisa da
mesma decisão, senão as duas camadas divergem.

## Pendências / follow-ups

- [ ] **Decidir sobre a normalização de acento** em `_norm_texto` /
      `_norm`. Impacto: consultor com acento divergente entre cadastro
      e fonte de produção aparece com produção zerada no acelerador.
- [ ] Trazer `_por_consultor_acelerador` e as duas funções de faixa
      para `kpis/reconquista.py`, injetando os loaders. Fica para uma
      passagem que possa mudar assinatura.
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
