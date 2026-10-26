# 2026-10-26 — IPV do Prestamista por consultor para admin e gestor

**Agente:** Codex
**Tipo:** feature
**Arquivos tocados:** `src/dashboard/kpis/prestamista.py`,
`tests/test_tabs_analiticos_prestamista.py`, `docs/agents/business-rules.md`.

## Objetivo

Disponibilizar a tabela de IPV por consultor para os perfis admin e gestor,
que antes tinham apenas as quebras por região e loja.

## O que foi feito

- Acrescentada a aba Por consultor ao mapa compartilhado de quebras por perfil.
  O Dashboard e Analíticos > Prestamista reutilizam esse mapa; os Analíticos
  também oferecem a exportação CSV da nova tabela.
- Agrupamento por região, loja e consultor, com elegíveis, seguros, IPV e
  semáforo existentes. Sem elegíveis permanece sem percentual e sem cor.
- Mantidos o cálculo por somas, a origem dos dados, o recorte de acesso e as
  visões dos demais perfis. Não há migration nem ajuste no importador.
- 79 testes do Prestamista passaram, incluindo AppTest de ambas as telas para
  admin/gestor, totais reconciliados, nomes iguais em lojas diferentes,
  semáforo, ausência de elegíveis e botão de exportação.

## Decisões não óbvias

- Atribuição por região + loja + consultor evita juntar nomes iguais em
  unidades diferentes e preserva a origem das propostas.
- A consulta somente de leitura de outubro/2026 durante a investigação
  retornou 3.361 propostas, 1.015 elegíveis e 745 seguros (73,40%). Os 147
  grupos região/loja/consultor reconciliaram com o total. São uma fotografia
  da consulta, não valores fixos ou expectativa dos testes.
- Duas propostas elegíveis tinham consultor_id nulo, mas nome preservado;
  continuam no cálculo pelo nome do arquivo. Nenhum cadastro foi alterado.

## Validação e publicação

- Testes: `test_kpis_prestamista.py`, `test_loader_prestamista.py`,
  `test_tabs_analiticos_prestamista.py`, `test_ui_resumo_prestamista.py`.
- Implementação local; sem commit, push ou deploy nesta entrega.

## Referências

- [Regras do Prestamista](../business-rules.md#seguro-prestamista-cnc-ipv)
