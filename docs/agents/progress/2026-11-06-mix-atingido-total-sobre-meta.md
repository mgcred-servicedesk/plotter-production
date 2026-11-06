# 2026-11-06 — "% Mix Atingido": total ÷ meta no card e no Resumo

**Agente:** Claude Code
**Tipo:** feature
**Arquivos tocados:** `src/dashboard/ui/kpi_cards_reforma.py`, `src/dashboard/ui/resumo_executivo.py`, `tests/test_regra_mix.py`, `docs/agents/business-rules.md`, `docs/agents/ui-components.md`
**Commit(s):** —

## Objetivo

O card "📊 % Meta Atingida" mostrava o % pela regra do MIX (ponderado:
`(meta_mix − falta) ÷ meta_mix`). O usuário pediu a volta ao modo
anterior — total vendido ÷ meta MIX — com o nome "% Mix Atingido",
mantendo a conta ponderada no "Para Onde Estamos Indo".

## O que foi feito

- Card (`render_kpis_principais`): % grande = `kpis["perc_ating_valor"]`
  (total ÷ meta MIX); "Projeção:" = `projecao ÷ meta_mix`; rótulo
  "📊 % Mix Atingido" (também no estado sem meta); saiu o rodapé "Total
  vendido: X% da meta MIX", que passaria a repetir o número grande.
- Resumo Executivo: status "X% do MIX atingido (R$)" e "Proj. MIX" com
  as mesmas contas do card.
- Mantido pela regra: card "🎯 Falta para Meta" (falta, "✓ Meta
  Atingida", o que falta por produto), "Para Onde Estamos Indo"
  (necessário, projeção e ritmo por produto), Meta Diária do consultor
  e, no Resumo, o ✅ (só atingida), "Faltam"/"Gap", a linha do que falta
  por produto e a pill 🔥 de ritmo por produto.
- Testes: 4 testes que travavam o modo ponderado no card/Resumo foram
  trocados; novos travam o rótulo e a convivência na mesma tela (card
  total × "Para Onde" ponderado). Sabotagem: contra o código anterior
  caem 7; contra o novo, os antigos caíam 4.

## Decisões não óbvias

- **Respostas do usuário (2026-11-06):** projeção do card volta a total
  ÷ meta; Resumo alinhado ao card mantendo o que falta por produto;
  "Falta para Meta" segue a regra — "atingimento em valor do total MIX
  não significa que atingiu a meta, e por isso criei essa ponderação".
- **A cor do % segue o total.** Consultor com o total a 114% e CLT
  pendente vê o % em verde ao lado de "Falta para Meta" pendente. É a
  leitura pedida: volume no card, veredito ao lado.
- **Texto do Resumo trocado de "da meta MIX atingida" para "do MIX
  atingido"**, alinhado ao nome do card: com o % do total, "114% da meta
  MIX atingida" ao lado de ⚠️ pendente se lia como contradição.
- `avaliar_regra_mix(...)["perc"]` continua calculado e exibido na
  coluna "Atingimento MIX %" da Performance do time (aba Gestão), que
  não fez parte do pedido.

## Pendências / follow-ups

- [ ] Perguntar se a coluna "Atingimento MIX %" da Performance do time
      deve seguir o card (total ÷ meta) ou ficar ponderada.

## Patterns criados ou atualizados

- Nenhum.

## Referências

- Docs: [business-rules.md](../business-rules.md#regra-do-mix--meta-atingida-exige-cada-produto-102026),
  [ui-components.md](../ui-components.md)
- Entrada anterior: [2026-10-16b-regra-mix-meta-por-produto.md](2026-10-16b-regra-mix-meta-por-produto.md)
