# 2026-09-23 — Analítico de Reconquista passa a rodar no eixo do fim de relacionamento

**Agente:** Claude Code
**Tipo:** feature
**Arquivos tocados:** `src/dashboard/kpis/reconquista.py`,
`src/dashboard/loaders.py`, `src/dashboard/tabs/analiticos.py`,
`tests/test_loaders.py`, `tests/test_kpis_reconquista.py`,
`tests/test_tabs_analiticos.py`, `docs/agents/business-rules.md`,
`docs/agents/ui-components.md`
**Commit(s):** (pendente)

## Objetivo

O analítico de Reconquista abria na apuração vigente da campanha —
defasada em 1 mês (Setembro mostrava quem encerrou em Agosto). O pedido:
mostrar o **fim de relacionamento do mês selecionado** (Agosto mostra
Agosto), mantendo a flexibilidade de consultar os meses anteriores, sem
tocar em cards/KPIs. Em 3 rodadas: primeiro o Detalhamento, depois os
labels, e por fim o **Por Loja** — que tinha ficado para trás em
08/2026 (visto em tela pelo usuário).

## O que foi feito

- `_marcar_vigencia_reconquista` passou a derivar também `ref_key` e
  `ref_label` (o mês de `dt_fim_relacionamento`), ao lado de
  `apuracao_key`/`apuracao_ref`. Helper vetorizado `_rotulo_mes`
  substitui a construção inline do rótulo (agora usada pelos dois eixos).
- Detalhamento passou a recortar/ordenar/destacar/filtrar por `ref_label`:
  pill `Fim de relacionamento · MM/AAAA` (padrão) × `Todos os meses ·
  <cobertura>`, multiselect "Fim de Relacionamento" no escopo completo,
  coluna "Mês Fim Relac." na tabela e no CSV.
- **Por Loja** (3ª passada) passou a ler `por_loja_mes`, nova chave do
  loader = `_por_loja_reconquista(clientes_prox)` — mesmo frame cacheado
  e RLS'd da prévia, sem fetch novo. Ganhou caption avisando que
  conversão/faixa ali são prévia da esteira.
- **Dois defeitos de formatação** na mesma tabela, visíveis na tela:
  "Conversão %" saía crua (`58.800000`) porque não casa nenhuma keyword
  de `_classificar_coluna` — agora vai explícita em `colunas_percentual`;
  e "Saldo Medio" imprimia `None` porque `mean()` de coluna `object`
  toda nula devolve `None` (não NaN) — `_coagir_numerico` resolve nas
  duas quebras (loja e consultor).
- **Labels** revistos (2ª passada, a pedido): a sub-nav da Reconquista
  carrega o período de cada eixo (`Por Loja · 08/2026`, `Detalhamento ·
  09/2026` — sempre o mês de `dt_fim`), o caption do topo declara "KPIs e
  Por Loja" e o aviso de apuração vazia diz que o Detalhamento segue
  listando o mês selecionado.
- `dt_fim_relacionamento` virou "Dt Fim Relac." na tabela — desambigua da
  coluna de mês e fica coerente com as irmãs "Dt Maciça"/"Dt DNA".
- Testes: `ref_label`/`ref_key` em `TestMarcarVigenciaReconquista`;
  `TestRenderReconquistaDetalhamento` reescrito para provar o eixo novo.

## Decisões não óbvias

- **O analítico inteiro mudou de eixo; os KPIs não.** Cards, conversão,
  faixa de prêmio e acelerador seguem na apuração defasada — o número
  que define prêmio/deflator não podia se mexer. Efeito colateral aceito
  e documentado: com Setembro selecionado, Por Loja e Detalhamento
  mostram `dt_fim` 09/2026 e os cards acima, 08/2026; os captions
  declaram os dois eixos para ninguém ler como divergência.
- **`por_loja` (apuração) ficou sem consumidor na UI.** Mantido no dict
  de `carregar_reconquista` — remover é decisão do usuário (CLAUDE.md,
  exclusão de código). Custo: um groupby pequeno por render.
- **A faixa de prêmio continua na tabela do Por Loja**, mesmo sendo
  prévia. Tirar seria esconder informação; o caption diz que o prêmio
  sai da apuração. Se em produção a leitura confundir, a alternativa é
  renomear a coluna ou omiti-la só no mês corrente.
- **Colunas Apuração/Vigência ficaram nos dois escopos**, mesmo com
  "Vigência = Próxima" constante no escopo padrão (todo lead do mês
  selecionado é apurado no mês seguinte). Constante ali é informação, não
  ruído: é o que amarra a linha ao mês de prêmio dela.
- **`ref_*` derivado no domínio, não na UI** — a defasagem já é regra de
  negócio (`kpis/reconquista.py`); a tab só escolhe por qual eixo filtra.
- **Valor do pill mudou** (`"Vigente"` → `"Mês selecionado"`, `"Todas"`
  → `"Todos"`) junto com a semântica, para código e tela não divergirem;
  a key `rec_det_escopo` foi mantida. O multiselect trocou de key
  (`rec_det_apuracao` → `rec_det_ref_mes`) porque mudou de dimensão.
- **A palavra "vigente" saiu do escopo do Detalhamento.** O rótulo
  inicial era "Mês vigente", que contradizia a coluna `Vigência` — nela
  todo lead do mês selecionado aparece como `Próxima` (será apurado no
  mês seguinte). O escopo passou a nomear o eixo que filtra ("Fim de
  relacionamento"), igual ao multiselect. A coluna `Vigência` ficou:
  constante no recorte padrão, mas é ela que amarra o lead ao mês de
  prêmio.
- **Acentuação dos labels NÃO foi mexida.** "Regiao", "Ticket Medio",
  "Em Analise" e afins são convenção do dashboard inteiro (`app.py`,
  `tabs/em_analise.py`, tabelas de gestão — com testes assertando
  `tabela["Regiao"]`), não defeito do Analíticos. Corrigir só nesta aba
  deixaria a tela inconsistente com as vizinhas; é decisão global e
  cabe ao usuário.
- **Sabotagem antes de fechar**: trocando o recorte de volta para
  `apuracao_ref`, `test_escopo_vigente_lista_o_fim_de_relacionamento_do_mes`
  falha — o teste prova o mecanismo, não a aparência.

## Pendências / follow-ups

- [ ] Decidir se `por_loja` (eixo de apuração) sai do dict do loader —
      hoje sem consumidor.
- [x] `_classificar_coluna` (components/tables.py) não reconhece
      "Conversão %" — verificado: a coluna só existe nesta tabela, então
      não há outra tela saindo crua pelo mesmo motivo.
