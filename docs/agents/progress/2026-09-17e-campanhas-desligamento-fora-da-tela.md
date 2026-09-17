# 2026-09-17 — Campanhas: desligamento não aparece na tela

**Agente:** Claude Code
**Tipo:** ajuste de UI

> Revoga a legenda de contagem descrita em
> [2026-09-17c](2026-09-17c-campanhas-desligados-fora-do-ranking.md)
> ("A tela diz quantos saíram").

## Decisão (usuário, 17/09/2026)

> "essa é uma regra interna, não deve aparecer em tela (menção a
> desligamento)"

O filtro de desligados continua igual; só a legenda
"N consultor(es) desligado(s) fora do ranking" saiu. `excluir_desligados`
ainda devolve a contagem (auditoria/teste), sem uso na página.

`test_tela_nao_menciona_desligamento` varre caption/info/warning/
markdown/write do painel nos dois rankings; sabotagem (legenda de volta)
pega. Suíte: 1306 passam.
