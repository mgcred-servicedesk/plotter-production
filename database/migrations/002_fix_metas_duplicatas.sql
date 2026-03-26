-- =====================================================
-- Migração 002: Corrigir duplicatas na tabela metas
--
-- Problema: a constraint UNIQUE com nivel NULL não
-- impede duplicatas no PostgreSQL (NULL ≠ NULL).
-- O import criou 2 registros por (loja, produto)
-- quando nivel IS NULL, dobrando as metas no dashboard.
--
-- Solução:
-- 1. Remover registros duplicados (manter o mais antigo)
-- 2. Criar índice UNIQUE parcial para nivel IS NULL
--    (compatível com PG < 15, sem NULLS NOT DISTINCT)
--
-- Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- 1. Verificar duplicatas antes da limpeza
-- ===========================================

-- Contagem de duplicatas (apenas visualização)
SELECT
    periodo_id, loja_id, produto, escopo,
    COUNT(*) AS total
FROM metas
WHERE nivel IS NULL
GROUP BY periodo_id, loja_id, produto, escopo
HAVING COUNT(*) > 1
ORDER BY total DESC;


-- ===========================================
-- 2. Remover duplicatas (manter o mais antigo)
-- ===========================================

DELETE FROM metas
WHERE id IN (
    SELECT id
    FROM (
        SELECT
            id,
            ROW_NUMBER() OVER (
                PARTITION BY periodo_id, loja_id,
                             produto, escopo
                ORDER BY created_at ASC, id ASC
            ) AS rn
        FROM metas
        WHERE nivel IS NULL
    ) sub
    WHERE rn > 1
);


-- ===========================================
-- 3. Índice UNIQUE parcial para nivel IS NULL
--    Impede duplicatas futuras sem precisar de
--    NULLS NOT DISTINCT (compatível com PG < 15)
-- ===========================================

CREATE UNIQUE INDEX IF NOT EXISTS
    uq_metas_periodo_loja_prod_esc_nivel_null
ON metas (periodo_id, loja_id, produto, escopo)
WHERE nivel IS NULL;


-- ===========================================
-- 4. Verificar resultado
-- ===========================================

-- Deve retornar 0 linhas
SELECT
    periodo_id, loja_id, produto, escopo,
    COUNT(*) AS total
FROM metas
WHERE nivel IS NULL
GROUP BY periodo_id, loja_id, produto, escopo
HAVING COUNT(*) > 1;
