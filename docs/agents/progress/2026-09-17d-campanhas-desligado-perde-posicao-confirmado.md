# 2026-09-17 — Campanhas: regra do desligado confirmada

**Agente:** Claude Code
**Tipo:** decisão (sem mudança de código)

> Fecha a premissa aberta em
> [2026-09-17c](2026-09-17c-campanhas-desligados-fora-do-ranking.md).

## Regra (usuário, 17/09/2026)

> "se houver mudança de status de Ativo para Desligado o vendedor é
> removido da listagem e sua posição será ocupada pelo próximo vendedor
> ativo"

Vale também para quem foi desligado no meio da campanha, com produção
anterior. É o comportamento implementado em `1626b3c`, travado por
`test_posicoes_sao_recalculadas` e `test_desligamento_mais_recente_vence`.

## Tempo de reflexo

A mudança de status chega pelo upload de cadastro (angry-man). O
dashboard a enxerga em até **30 min** (TTL de
`carregar_consultores_desligados`), ou na hora com "Atualizar Dados".
