# 2026-09-11 — Pontuação: meta inexistente vira travessão, nunca "Atingida"

## Contexto

A loja DIGITAL não tem meta cadastrada em nenhum escopo (nem LOJA, nem
CONSULTOR). É lacuna de cadastro conhecida e aceita. Depois que o
dashboard passou a usar metas **individuais** de consultor, os
consultores do DIGITAL passaram a cair legitimamente no caso
`meta = 0`.

O dashboard de **Vendas** (`ui/kpi_cards_reforma.py`) já tratava isso:
valor `—` em `var(--mg-text-muted)` + subtexto "Sem meta definida". O
dashboard de **Pontuação** não tinha ramo nenhum para meta zero.

## O defeito

`gap = max(0, meta - realizado)` zera em **dois** casos diferentes:

1. a meta foi batida;
2. não existe meta cadastrada.

Todo o código de Pontuação decidia pelo gap, então o caso (2) caía no
ramo de sucesso e o card exibia **"✓ Prata Atingida"** com "+0 pts
acima" — afirmando atingimento onde não há meta, em verde.

## Decisão

**A distinção é por valor da meta, nunca por nome de loja.**

- `meta > 0 and gap <= 0` ⇒ meta batida ⇒ mantém o "✓ ... Atingida";
- `meta <= 0` ⇒ não há meta ⇒ travessão + "Sem meta definida".

Nenhum `if loja == "DIGITAL"` em lugar nenhum: DIGITAL é só o caso que
expôs o problema. Amanhã é qualquer loja/competência sem cadastro.

## Superfícies alteradas

- `ui/kpi_cards_pontuacao.py :: render_kpis_principais_pts` — ramo de
  meta inexistente nos cards "📊 % Meta Prata" e "🎯 Falta para Prata".
- `ui/kpi_cards_pontuacao.py :: render_bloco_media_projecao_pts` —
  `msg_desvio` passa a distinguir "Sem meta definida" / "Prata
  atingida" / "Período encerrado — Prata não atingida" / desvio do
  ritmo (espelha `kpi_cards_reforma`); "Necessário p/ Prata" e os
  percentuais de "Projeção Fim" viram `—` / são suprimidos sem meta.
- `ui/prioridades_pontuacao.py` — badge "Sem meta" (cor neutra), textos
  Prata/Ouro e "Ação Recomendada" deixam de dizer "já atingida".
- `pages/dashboard_pontuacao.py` — repassa `meta_prata`/`meta_ouro` ao
  `render_prioridades_pontuacao`.

## Por que `prioridades_pontuacao` precisou de parâmetro novo

Os dicts de `calcular_prioridades_pontuacao` carregam `gap_prata` /
`gap_ouro`, mas **não** `meta_prata` / `meta_ouro` — então era
impossível separar os dois casos dentro da UI. `meta_prata` e
`meta_ouro` entraram como kwargs opcionais (default `0.0`) em
`render_prioridades_pontuacao`, `_render_lista` e
`_html_card_produto_pts`. Assinatura retrocompatível.

**Divergência doc × código (follow-up, não corrigida aqui):** a
docstring de `calcular_prioridades_pontuacao`
(`kpis/pontuacao.py`, ~linha 291) anuncia ``meta_prata``, ``meta_ouro``
como chaves do dict de retorno. O dict retornado não as inclui. Ou a
docstring desce, ou as chaves sobem — se subirem, o kwarg da UI pode
ser removido depois.

## Fora de escopo (auditado, não alterado)

- **Tabela de ranking de consultores**: a coluna de atingimento
  continua numérica (0%) porque virar texto afetaria ordenação e
  export. `tabs/rankings.py` já emite caption
  "⚠ Sem meta individual (escopo CONSULTOR) — atingimento 0% para
  consultores de: …", então o caso está sinalizado ao usuário.
- `ui/kpi_cards_reforma.py` (Vendas) — já é o padrão canônico.

## Validação

`.venv/bin/ruff check src/ app.py` limpo; `pytest tests/` 757 passed.
Render headless (AppTest + chamada direta com `kpis` sintéticos) nos
três estados: meta real abaixo, meta real batida (verde sobrevive),
meta zero (travessão nos dois cards).
