# 2026-07-07 — Higienizar FGTS_ANT_BEN_CNC13 nos insights de ação

**Agente:** Claude Code (Fable 5)
**Tipo:** fix (display)
**Arquivos tocados:** `src/dashboard/ui/prioridades_acao.py`

## Objetivo

O código bruto `FGTS_ANT_BEN_CNC13` aparecia em "Onde Agir Agora
(Prioridades)" e "Ações Recomendadas para Hoje". Exibir como
`FGTS/Ant.Ben./13º` (convenção já usada nos módulos de pontuação).

## O que foi feito

`prioridades_acao.py` ganhou `_NOMES_MIX` + helper `_nome_produto`
(mesma convenção de `prioridades_pontuacao._NOMES_MIX`,
`kpi_cards_pontuacao`, `kpi_cards_reforma`), aplicados em 4 pontos de
renderização: título do card de produto (`_html_card_produto`), card
"Pipeline em Análise" do consultor, e as duas ações recomendadas
("Focar em …" e "Acionar pipeline de …").

## Decisões não óbvias

- **Duas taxonomias de código convivem no app**: as chaves de
  `PRODUTOS_DASHBOARD` (`produto_display`: CNC, CLT, SAQUE,
  CONSIGNADO, FGTS_ANT_BEN_CNC13) e o `grupo_dashboard` do banco
  (que usa `PACK` para o mesmo mix — já humanizado em `app.py` via
  `NOMES_DISPLAY_PRODUTO` de `settings.py`, para
  "FGTS/Ant. Ben./CNC 13o"). O vazamento era só do primeiro grupo.
- **Mapeamento aplicado somente na renderização**: os dicts de
  prioridades/pipeline mantêm a chave canônica porque
  `calcular_prioridades_produto` casa `analise_map` por essa chave.
- **Efeito colateral aceito**: SAQUE/CONSIGNADO nos mesmos pontos
  passam a exibir "Saque"/"Consignado" (alinhado ao resto do
  dashboard).
- **Follow-up opcional (não feito)**: existem duas variantes do
  rótulo no app — "FGTS/Ant.Ben./13º" (pontuação + agora insights) e
  "FGTS/Ant. Ben./CNC 13o" (`settings.NOMES_DISPLAY_PRODUTO`, usado
  em produtos_baixa_perf/regioes). Unificar exigiria mudar o valor em
  `settings.py`, propagando para outras telas — decisão do usuário.
