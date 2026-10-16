# 2026-10-16 — Troca de supervisão HELP ALCANTARA ↔ CARREFOUR (01/09/2026)

**Agente:** Claude Code
**Tipo:** bugfix (dado de cadastro)
**Arquivos tocados:** `database/migrations/139_supervisor_vigencia_troca_alcantara_carrefour.sql`, `docs/agents/business-rules.md`
**Commit(s):** — (não commitado)

## Objetivo

O usuário informou que ERICA CRISTINA MARINS DA SILVA e MARIANA DE
OLIVEIRA RODRIGUES trocaram de loja como supervisoras em 01/09/2026
(ERICA → HELP ALCANTARA, MARIANA → HELP ALCANTARA CARREFOUR).

## O que foi feito

- Migration 139 (não aplicada): dois `fn_aplicar_mudanca_supervisor(...,
  DATE '2026-09-01', 'REMANEJAMENTO')` + `origem = 'MANUAL'` nas janelas
  novas, numa transação. Bloco de validação no fim.
- business-rules § Promessa Diária: caso ERICA reescrito.

## Decisões não óbvias

- **Corrige [2026-10-16d](2026-10-16d-promessa-lead-sem-consultor-supervisor.md):**
  lá ficou pendente "nome com ROSA em supervisores e consultores" — isso
  contraria a decisão do usuário de 18/08/2026 (migration 081: nome oficial
  SEM "ROSA", porque é o dos contratos/consultores). Fica sem "ROSA".
- **Migration e não planilha:** `fn_supervisores_replace` data o evento em
  `current_date`; setembro ficaria invertido.
- **MANUAL:** doutrina 113/117 — a planilha não desfaz correção humana.
  Custo: encerrar essas janelas depois exige REBAIXAMENTO/FIM explícito.
- **Sem efeito em ranking/média de consultor:** as duas são supervisoras
  antes e depois e a exclusão é por nome. Muda o mapa supervisor→loja a
  partir de 09/2026.

## Pendências / follow-ups

- [ ] Usuário aplica a 139 (SQL Editor) e roda a validação.
- [ ] Usuário atualiza `configuracao/Supervisores.xlsx` no angry-man
      (ERICA em HELP ALCANTARA, MARIANA em CARREFOUR, ERICA sem "ROSA")
      antes do próximo import da planilha.
- [ ] Conferir o Caderno 09/2026 (validação 3) antes de decidir
      rematerializar.

## Referências

- Migrations 077, 078, 081, 113, 117.
