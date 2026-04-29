-- =====================================================
-- Migracao 007: Índice para branch OR dos seguros
--              em v_contratos_dashboard
--
-- Problema: a view filtra contratos pagos OU seguros
-- liquidados (OR). O índice existente
-- idx_contratos_periodo_status_pag cobre apenas a
-- primeira branch (status_pagamento_cliente). A segunda
-- branch (sub_status_banco = 'Liquidada') não tem
-- índice que inclua periodo_id, forçando um path de
-- acesso separado na query e tornando o carregamento
-- mais lento conforme a tabela cresce.
--
-- Fix: índice parcial composto (periodo_id, sub_status_banco)
-- restrito a linhas já filtradas por sub_status_banco,
-- espelhando o padrão do índice da primeira branch.
--
-- Executar no Supabase SQL Editor.
-- =====================================================

CREATE INDEX IF NOT EXISTS idx_contratos_periodo_sub_status_liquidada
    ON contratos (periodo_id, sub_status_banco)
    WHERE sub_status_banco = 'Liquidada';

COMMENT ON INDEX idx_contratos_periodo_sub_status_liquidada IS
    'Cobre a branch OR dos seguros liquidados em '
    'v_contratos_dashboard quando filtrada por periodo_id '
    '(PostgREST). Complementa idx_contratos_periodo_status_pag.';
