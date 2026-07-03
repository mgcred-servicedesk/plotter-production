-- ============================================================
-- Migracao 053: Reconquista — coluna flag_elegibilidade
--
-- Contexto: o arquivo de Reconquista ganhou a coluna
-- `flag_elegibilidade` (ELEGIVEL / NAO ELEGIVEL). A apuracao
-- (conversao = EFETIVADA / total) passa a contar SOMENTE os
-- clientes ELEGIVEL; os NAO ELEGIVEL continuam visiveis nos
-- analiticos (detalhe por cliente), apenas fora da conta.
--
-- Interim (decisao 2026-07-03): enquanto o arquivo novo nao for
-- importado, os registros ficam com flag NULL. O dashboard trata
-- NULL como ELEGIVEL (nao zera a apuracao ate a flag real chegar).
-- Por isso a coluna e NULLABLE, sem default forcado.
--
-- Alteracoes (todas versionadas / idempotentes):
--   1. ALTER TABLE reconquista ADD COLUMN flag_elegibilidade TEXT
--      (CHECK aceita NULL + os dois valores canonicos).
--   2. CREATE OR REPLACE VIEW v_reconquista — expoe a coluna nova
--      (ao FINAL, como exige CREATE OR REPLACE VIEW).
--   3. CREATE OR REPLACE FUNCTION fn_importar_reconquista — passa a
--      persistir p_rows->>'flag_elegibilidade' (opcional; ausente
--      => NULL). RETURNS TABLE inalterado -> sem DROP.
--
-- Depende de: 028 (tabela), 029 (RPC), 030 (view).
-- Executar no Supabase SQL Editor.
-- ============================================================

-- ---------------------------------------------------------------
-- 1. Coluna na tabela base
-- ---------------------------------------------------------------
ALTER TABLE reconquista
    ADD COLUMN IF NOT EXISTS flag_elegibilidade TEXT;

ALTER TABLE reconquista
    DROP CONSTRAINT IF EXISTS chk_reconquista_elegibilidade;
ALTER TABLE reconquista
    ADD CONSTRAINT chk_reconquista_elegibilidade
    CHECK (flag_elegibilidade IN ('ELEGIVEL', 'NAO ELEGIVEL'));

COMMENT ON COLUMN reconquista.flag_elegibilidade IS
    'Elegibilidade do cliente para a apuracao/premio (ELEGIVEL / '
    'NAO ELEGIVEL). Somente ELEGIVEL entram na conversao; NAO '
    'ELEGIVEL seguem visiveis nos analiticos. NULL (sem flag no '
    'arquivo) e tratado como ELEGIVEL pelo dashboard.';

-- ---------------------------------------------------------------
-- 2. View de leitura — expoe a coluna nova ao final
-- ---------------------------------------------------------------
CREATE OR REPLACE VIEW v_reconquista
    WITH (security_invoker = on)
AS
SELECT
    r.co_adesao,
    r.status,
    r.dt_fim_relacionamento,
    EXTRACT(YEAR  FROM r.dt_fim_relacionamento)::INTEGER  AS ref_ano,
    EXTRACT(MONTH FROM r.dt_fim_relacionamento)::INTEGER  AS ref_mes,
    r.dt_macica,
    r.dt_dna,
    r.dt_producao,
    r.subproduto,
    COALESCE(l.nome, '(Nao Identificado)')                AS loja,
    reg.nome                                              AS regiao,
    COALESCE(con.nome, r.consultor_nome, '(Sem Consultor)') AS consultor,
    r.gerente_regional,
    r.gerente_loja,
    r.coordenador_loja,
    r.banco_origem,
    r.banco_destino,
    r.saldo_contabil,
    r.dias_atraso,
    r.faixa_atraso,
    r.tipo_pagamento,
    r.qt_fim_relacionamento,
    r.link_aceite,
    r.flag_elegibilidade
FROM reconquista r
LEFT JOIN lojas l         ON l.id   = r.loja_id
LEFT JOIN regioes reg     ON reg.id = l.regiao_id
LEFT JOIN consultores con ON con.id = r.consultor_id;

COMMENT ON VIEW v_reconquista IS
    'Reconquista v2: detalhe por cliente com loja/regiao/consultor '
    'rotulados e ref_ano/ref_mes (de dt_fim_relacionamento). Expoe '
    'flag_elegibilidade (a apuracao/conversao no dashboard conta so '
    'ELEGIVEL; NULL = ELEGIVEL). KPIs e quebra por loja agregados no '
    'loader. Defasagem de 1 mes aplicada no loader.';

-- ---------------------------------------------------------------
-- 3. RPC de importacao — persiste a flag (opcional -> NULL)
-- ---------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_importar_reconquista(
    p_rows JSONB
)
RETURNS TABLE (
    inseridos     INTEGER,
    sem_loja      INTEGER,
    sem_consultor INTEGER
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_inseridos     INTEGER := 0;
    v_sem_loja      INTEGER := 0;
    v_sem_consultor INTEGER := 0;
    v_row           JSONB;
    v_loja_id       UUID;
    v_consultor_id  UUID;
    v_consultor_nm  TEXT;
    v_affected      INTEGER;
BEGIN
    TRUNCATE TABLE public.reconquista;

    FOR v_row IN SELECT * FROM jsonb_array_elements(p_rows)
    LOOP
        -- Loja: resolve pelo cod_bmg ja com sucessora aplicada
        v_loja_id := NULL;
        IF (v_row->>'cod_bmg') IS NOT NULL THEN
            SELECT COALESCE(l.sucessora_id, l.id) INTO v_loja_id
            FROM public.lojas l
            WHERE l.cod_bmg = (v_row->>'cod_bmg')::INTEGER
            LIMIT 1;
        END IF;

        IF v_loja_id IS NULL THEN
            v_sem_loja := v_sem_loja + 1;
        END IF;

        -- Consultor: nome completo (novo layout) + loja
        v_consultor_id := NULL;
        v_consultor_nm := NULLIF(TRIM(v_row->>'consultor_nome'), '');
        IF v_consultor_nm IS NOT NULL THEN
            SELECT c.id INTO v_consultor_id
            FROM public.consultores c
            WHERE c.nome ILIKE v_consultor_nm
              AND (c.loja_id = v_loja_id OR c.loja_id IS NULL)
            ORDER BY CASE WHEN c.loja_id = v_loja_id THEN 0 ELSE 1 END, c.nome
            LIMIT 1;
        END IF;

        IF v_consultor_id IS NULL THEN
            v_sem_consultor := v_sem_consultor + 1;
        END IF;

        INSERT INTO public.reconquista (
            co_adesao, status,
            dt_fim_relacionamento, dt_macica, dt_dna, dt_producao,
            subproduto,
            no_franquia, cod_bmg, loja_id,
            consultor_nome, consultor_id,
            gerente_regional, gerente_loja, coordenador_loja,
            banco_origem, banco_destino, saldo_contabil,
            dias_atraso, faixa_atraso, tipo_pagamento,
            qt_fim_relacionamento, link_aceite,
            flag_elegibilidade
        )
        VALUES (
            (v_row->>'co_adesao')::BIGINT,
            v_row->>'status',
            (v_row->>'dt_fim_relacionamento')::DATE,
            (v_row->>'dt_macica')::DATE,
            (v_row->>'dt_dna')::DATE,
            (v_row->>'dt_producao')::DATE,
            v_row->>'subproduto',
            v_row->>'no_franquia',
            (v_row->>'cod_bmg')::INTEGER,
            v_loja_id,
            v_consultor_nm,
            v_consultor_id,
            v_row->>'gerente_regional',
            v_row->>'gerente_loja',
            v_row->>'coordenador_loja',
            v_row->>'banco_origem',
            v_row->>'banco_destino',
            (v_row->>'saldo_contabil')::NUMERIC,
            (v_row->>'dias_atraso')::INTEGER,
            v_row->>'faixa_atraso',
            v_row->>'tipo_pagamento',
            (v_row->>'qt_fim_relacionamento')::INTEGER,
            v_row->>'link_aceite',
            NULLIF(TRIM(v_row->>'flag_elegibilidade'), '')
        )
        ON CONFLICT (co_adesao) DO NOTHING;

        GET DIAGNOSTICS v_affected = ROW_COUNT;
        v_inseridos := v_inseridos + v_affected;
    END LOOP;

    RETURN QUERY SELECT v_inseridos, v_sem_loja, v_sem_consultor;
END;
$$;

COMMENT ON FUNCTION fn_importar_reconquista(JSONB) IS
    'Reconquista v2: TRUNCATE + carga em lote da tabela reconquista. '
    'Resolve loja_id (cod_bmg + sucessora) e consultor_id (nome '
    'completo + loja) e persiste flag_elegibilidade (opcional -> NULL). '
    'Atomica (truncate+insert na mesma transacao). Retorna '
    '(inseridos, sem_loja, sem_consultor) para logging.';

-- Apenas service_role/admin importam (preserva REVOKE da 029)
REVOKE ALL ON FUNCTION fn_importar_reconquista(JSONB) FROM PUBLIC;
