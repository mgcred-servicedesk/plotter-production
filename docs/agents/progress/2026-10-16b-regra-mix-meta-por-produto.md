# 2026-10-16 — Regra do MIX: "meta atingida" exige cada produto

**Agente:** Claude Code
**Tipo:** feature
**Arquivos tocados:** `src/dashboard/kpis/gerais.py`, `src/dashboard/ui/kpi_cards_reforma.py`, `src/dashboard/ui/prioridades_acao.py`, `tests/test_regra_mix.py`, `docs/agents/business-rules.md`
**Commit(s):** —

## Objetivo

O quadro de vendas só pode dizer que a meta foi batida se o total do MIX
e o mínimo de cada produto forem atingidos; se algum produto já bateu,
avisar quanto falta nos demais.

## O que foi feito

- `avaliar_regra_mix` (`kpis/gerais.py`): função pura, fonte única da
  regra (atingida / parcial / pendentes / falta).
- `mensagem_regra_mix` + `texto_faltas_mix` (`ui/kpi_cards_reforma.py`):
  texto do estado parcial, reusado pelo card do consultor.
- Aplicado em: card "🎯 Falta para Meta" (`render_kpis_principais`),
  bloco "Para Onde Estamos Indo" (`render_bloco_media_projecao`) e Meta
  Diária do consultor (`calcular_planejamento_consultor` +
  `_render_planejamento_consultor_coluna`).
- 15 testes em `tests/test_regra_mix.py` (unit + AppTest), sabotados:
  voltando à regra antiga (só total) caem 5.
- Dados reais 10/2026 (dia 16): 6 consultores com total batido e
  produto pendente deixam de ler "meta atingida".

## Decisões não óbvias

- **Respostas do usuário:** mínimo = 100% da meta do produto; atingida =
  total MIX **e** cada produto; os três quadros.
- **"Card Mix Geral" da pergunta era código morto.** `criar_cards_metas_produto`
  (`ui/kpi_cards.py`) só é reexportado pelo `app.py`, não é chamado. O
  quadro visível que dizia "✓ Meta Atingida" é o hero "Falta para Meta"
  — foi nele que a regra entrou. O código morto não foi tocado nem
  removido (sinalizado ao usuário).
- **Falta = max(falta no total, soma das faltas por produto)** — o
  excedente de um produto não cobre a falta de outro. Muda o valor do
  "Falta para Meta" e o "Necessário/dia" mesmo antes de algum produto
  bater, sempre que um produto passa da meta e outro não.
- **`kpis["gap_valor"]` não mudou** (Resumo Executivo segue no total);
  a regra é aplicada na renderização dos três quadros pedidos.
- **"+X acima"** do card atingido passou a usar `total - meta_mix`: o
  `gap_valor` é `max(0, …)`, então o texto antigo mostrava sempre +R$ 0.
- **`$` vira `&#36;`** no texto das faltas: duas moedas na mesma linha
  viram LaTeX no markdown do Streamlit.

## Pendências / follow-ups

- [ ] `criar_cards_metas_produto` / `_card_meta_produto` / `_calcular_mix`
  (`ui/kpi_cards.py`) parecem não usados — confirmar com o usuário antes
  de remover.
- [ ] "Fecharemos X% acima da meta" (bloco Para Onde) segue a projeção do
  total; com produto pendente pode soar contraditório.

## Referências

- Docs consultados: [business-rules.md](../business-rules.md#regra-do-mix--meta-atingida-exige-cada-produto-102026)

## Atualização — 2026-10-16 (% Meta Atingida pela regra)

- Usuário escolheu o card **📊 % Meta Atingida** e o percentual **pela
  regra** (excedente não compensa): `avaliar_regra_mix` ganhou `perc` =
  `(meta_mix − falta) / meta_mix`; atingida, o % real do total.
- Rodapé do card mostra "Total vendido: X% da meta MIX" enquanto a regra
  não fecha, para o número antigo não sumir sem explicação.
- **Decisão minha, a validar:** atingida, o card mostra o % do total
  (pode passar de 100%) em vez de travar em 100% — não há falta a
  compensar e o excedente fica visível.
- Dados 10/2026: empresa 45,0% (igual nos dois cálculos); Stella 100,8%
  → 79,4%; Rosiane 103,1% → 76,1%.
- +5 testes (20 em `test_regra_mix.py`); sabotagem (card voltando ao
  `perc_ating_valor`) derruba o teste do card.
- Resumo Executivo ("✅ Meta MIX atingida" pelo total) **não** foi
  alterado — usuário escolheu só o card.

## Atualização — 2026-10-16 (Resumo Executivo)

- Usuário pediu para alinhar o **Resumo Executivo**: status "✅ Meta MIX
  atingida" só com `regra["atingida"]`; % do status, "Faltam", "Gap" e
  ritmo necessário passam a usar `regra["perc"]` / `regra["falta"]`; no
  estado parcial o subtítulo ganha `mensagem_regra_mix`. Pendência de
  contradição card × resumo **resolvida**.
- +2 testes (22 em `test_regra_mix.py`, `st.html` capturado via
  monkeypatch); sabotagem (voltar ao `perc_ating_valor`/`gap_valor`)
  derruba o teste do estado parcial.

## Atualização — 2026-10-16 (projeção pela regra)

- Caso que motivou: Bruna Moulaz (HELP ABOLICAO) — Consignado 161% fazia
  o total ler 106% e a projeção 202–247%, com CNC/CLT/FGTS abaixo.
- Usuário aprovou projetar **cada produto** com a mesma regra:
  `projetar_regra_mix` (`kpis/gerais.py`) = `avaliar_regra_mix` sobre a
  `projecao` de cada produto (a mesma dos cards por produto).
- Aplicado em: "Projeção:" (card % Meta Atingida), "Projeção Fim" e
  "Fecharemos…" (Para Onde), "Proj. MIX" (Resumo).
- **Ritmo:** produto projetado abaixo da meta ⇔ ritmo abaixo da meta
  diária restante. A frase "X% acima do necessário" (Para Onde) e a pill
  🔥 (Resumo) passam a listar esses produtos quando existem — o ritmo
  total escondia o produto atrasado.
- **Decisão:** valor em R$ da projeção (card Pagos, "Projeção Fim") segue
  sendo a venda total prevista; só o % e as frases seguem a regra.
- Dados 10/2026 (Bruna): projeção 202,3% → 87,1%; ritmo abaixo em CLT e
  FGTS/Ant./13º (CNC projeta R$ 41,5K ≥ R$ 35K).
- +5 testes (27 em `test_regra_mix.py`); sabotagem (projeção só pelo
  total) derruba 4. Pendência "Fecharemos X% acima" **resolvida**.
- Observação: o Streamlit local (PID 8179, iniciado 10:18) não recarregou
  `resumo_executivo.py` — usuário viu o Resumo antigo; reiniciar o app.
