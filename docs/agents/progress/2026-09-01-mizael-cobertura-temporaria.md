# 2026-09-01 — Cobertura temporária de Mizael em Rio Comprido

**Agente:** Codex
**Tipo:** fix
**Arquivos desta frente:**
`database/migrations/103_mizael_cobertura_temporaria_rio_comprido.sql`
**Commit(s):** —

## Confirmação da operação

Mizael Barbosa Neto pertence à Help Laranjeiras, começou a cobertura temporária
na Help Rio Comprido em 11/08/2026 e retornou a Laranjeiras em 25/08/2026.

## Implementado

A migration 103 representa o período com três janelas consecutivas e sem
sobreposição:

1. Laranjeiras até 10/08;
2. Rio Comprido de 11/08 a 24/08;
3. Laranjeiras novamente desde 25/08.

A correção também substitui a janela inferida que mantinha Rio Comprido aberto
desde 01/09. Todas as linhas afetadas passam a ter origem `MANUAL`. A migração
é reaplicável e aborta se encontrar um histórico adicional incompatível.

## Próximo passo

Aplicar as migrations 101, 102 e 103, materializar a competência 08/2026 e
validar a conciliação nominal no Bereshit.
