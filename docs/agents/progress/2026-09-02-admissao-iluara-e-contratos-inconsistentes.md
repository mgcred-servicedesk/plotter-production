# 2026-09-02 — Admissão de Iluara e contratos inconsistentes

**Agente:** Codex
**Tipo:** fix / diagnóstico de dados
**Arquivo desta frente:** `database/migrations/104_vigencia_admissao_iluara.sql`
**Commit(s):** —

## Fato confirmado

Iluara Borges Cabral foi admitida na Help Cascadura em 25/08/2026. A migration
104 registra essa vigência como correção `MANUAL`, sem antecipá-la a partir de
produção.

## Divergência encontrada

A operação informou que Iluara digitou somente um contrato, em 31/08/2026. A
tabela bruta confirma esse registro (`contrato_id = 2999022`), ainda não pago.
Entretanto, 17 contratos cadastrados e pagos em 18/08/2026 apontam para o UUID
do cadastro de Iluara e somam R$ 14.221,48.

O cadastro de Iluara foi criado em 01/09, enquanto as 17 linhas de contratos
foram inseridas em 19/08. Isso é compatível com reimportação posterior dos
mesmos `contrato_id`, que preservou `created_at` mas atualizou `consultor_id`
segundo a planilha mais recente. `contratos_pagos` não preserva uma identidade
anterior: contém o mesmo UUID atual.

## Decisão segura

A vigência não será antecipada para encobrir os 17 contratos. Antes de
rematerializar, eles precisam ser reimportados com o vendedor correto ou
corrigidos por uma relação explícita `contrato_id -> consultor`. O responsável
não será inferido apenas por pertencer à loja.
