-- =====================================================
-- Migracao 033: oportunidade perdida por loja e regiao
--
-- Estende obter_cancelados_classificados (migration 032) com
-- duas colunas de oportunidade perdida por nivel de perfil:
--   * recuperada_outra_loja   -> venda capturada em OUTRA loja
--                                (escopo supervisor)
--   * recuperada_outra_regiao -> venda capturada em OUTRA regiao
--                                (escopo gerente)
-- alem da ja existente:
--   * recuperada_outro        -> capturada por OUTRO consultor
--                                (escopo consultor)
--
-- Semantica: uma venda recapturada DENTRO do proprio nivel nao e
-- perda (ex.: outro consultor da mesma loja nao e perda da loja).
-- Por isso cada nivel exige NAO ter sido recuperada no proprio
-- nivel E ter sido paga fora dele, em <=7 dias.
--
-- Como o tipo de retorno muda (novas colunas no RETURNS TABLE),
-- CREATE OR REPLACE nao basta — e preciso DROP FUNCTION antes
-- (Postgres: "cannot change return type of existing function").
-- A 032 ja foi aplicada e permanece imutavel; esta migration a
-- substitui de forma versionada.
--
-- Executar no Supabase SQL Editor.
-- =====================================================

DROP FUNCTION IF EXISTS obter_cancelados_classificados(INTEGER, INTEGER);

CREATE FUNCTION obter_cancelados_classificados(
    p_mes INTEGER,
    p_ano INTEGER
)
RETURNS TABLE (
    id                        UUID,
    contrato_id               BIGINT,
    valor                     NUMERIC(15,2),
    prazo                     TEXT,
    valor_parcela             NUMERIC(15,2),
    tipo_operacao             TEXT,
    data_cadastro             DATE,
    status_banco              TEXT,
    data_status_banco         DATE,
    status_pagamento_cliente  TEXT,
    data_status_pagamento     DATE,
    banco                     TEXT,
    convenio                  TEXT,
    num_proposta              TEXT,
    sub_status_banco          TEXT,
    loja                      TEXT,
    regiao                    TEXT,
    consultor                 TEXT,
    produto                   TEXT,
    tipo_produto              TEXT,
    subtipo                   TEXT,
    categoria_codigo          TEXT,
    grupo_dashboard           TEXT,
    conta_valor               BOOLEAN,
    classificacao             TEXT,
    recuperada_outro          BOOLEAN,
    recuperada_outra_loja     BOOLEAN,
    recuperada_outra_regiao   BOOLEAN
)
LANGUAGE plpgsql
STABLE
SET search_path = ''
AS $$
DECLARE
    v_data_ref    DATE;
    v_data_inicio DATE;
    v_hoje        DATE := current_date;
BEGIN
    -- Data de referencia: hoje se periodo vigente,
    -- senao ultimo dia do mes selecionado (igual a RPC 003).
    IF p_mes = EXTRACT(MONTH FROM v_hoje)::INTEGER
       AND p_ano = EXTRACT(YEAR FROM v_hoje)::INTEGER
    THEN
        v_data_ref := v_hoje;
    ELSE
        v_data_ref := (make_date(p_ano, p_mes, 1)
                       + INTERVAL '1 month'
                       - INTERVAL '1 day')::DATE;
    END IF;

    v_data_inicio := v_data_ref - INTERVAL '30 days';

    RETURN QUERY
    WITH canc AS (
        -- Cancelados da janela; puxa o nome do base contratos
        -- apenas para o matching (nao sera retornado).
        SELECT
            v.id, v.contrato_id, v.valor, v.prazo, v.valor_parcela,
            v.tipo_operacao, v.data_cadastro, v.status_banco,
            v.data_status_banco, v.status_pagamento_cliente,
            v.data_status_pagamento, v.banco, v.convenio, v.num_proposta,
            v.sub_status_banco, v.loja, v.regiao, v.consultor, v.produto,
            v.tipo_produto, v.subtipo, v.categoria_codigo, v.grupo_dashboard,
            v.conta_valor,
            upper(trim(regexp_replace(
                coalesce(c.cliente, ''), '\s+', ' ', 'g'
            ))) AS nome_norm
        FROM public.v_contratos_cancelados v
        JOIN public.contratos c ON c.id = v.id
        WHERE v.data_cadastro >= v_data_inicio
          AND v.data_cadastro <= v_data_ref
    ),
    paga AS (
        -- Propostas pagas (mesmo nome+categoria) usadas para
        -- detectar recuperacao. Traz consultor/loja/regiao para
        -- distinguir recuperacao propria x por outro consultor,
        -- outra loja, outra regiao. Filtro de data limita o scan.
        SELECT
            upper(trim(regexp_replace(
                coalesce(c.cliente, ''), '\s+', ' ', 'g'
            ))) AS nome_norm,
            cp.codigo AS categoria_codigo,
            con.nome  AS consultor,
            l.nome    AS loja,
            r.nome    AS regiao,
            c.data_cadastro
        FROM public.contratos c
        JOIN public.produtos p            ON p.id  = c.produto_id
        JOIN public.categorias_produto cp ON cp.id = p.categoria_id
        LEFT JOIN public.consultores con  ON con.id = c.consultor_id
        LEFT JOIN public.lojas l          ON l.id  = c.loja_id
        LEFT JOIN public.regioes r        ON r.id  = l.regiao_id
        WHERE c.status_pagamento_cliente = 'PAGO AO CLIENTE'
          AND c.data_cadastro >= v_data_inicio
          AND c.data_cadastro <= v_data_ref + INTERVAL '7 days'
    ),
    flags AS (
        SELECT
            a.*,
            -- stage 1: superada por cancelamento posterior em <=7d
            (a.nome_norm <> '' AND EXISTS (
                SELECT 1 FROM canc b
                WHERE b.nome_norm = a.nome_norm
                  AND b.categoria_codigo = a.categoria_codigo
                  AND b.data_cadastro > a.data_cadastro
                  AND b.data_cadastro <= a.data_cadastro + INTERVAL '7 days'
            )) AS is_redig,
            -- paga pelo PROPRIO consultor em <=7d apos
            (a.nome_norm <> '' AND EXISTS (
                SELECT 1 FROM paga g
                WHERE g.nome_norm = a.nome_norm
                  AND g.categoria_codigo = a.categoria_codigo
                  AND g.consultor IS NOT DISTINCT FROM a.consultor
                  AND g.data_cadastro >= a.data_cadastro
                  AND g.data_cadastro <= a.data_cadastro + INTERVAL '7 days'
            )) AS paga_propria,
            -- paga por OUTRO consultor em <=7d apos (venda capturada)
            (a.nome_norm <> '' AND EXISTS (
                SELECT 1 FROM paga g
                WHERE g.nome_norm = a.nome_norm
                  AND g.categoria_codigo = a.categoria_codigo
                  AND g.consultor IS DISTINCT FROM a.consultor
                  AND g.data_cadastro >= a.data_cadastro
                  AND g.data_cadastro <= a.data_cadastro + INTERVAL '7 days'
            )) AS paga_outro,
            -- paga na MESMA loja em <=7d apos
            (a.nome_norm <> '' AND EXISTS (
                SELECT 1 FROM paga g
                WHERE g.nome_norm = a.nome_norm
                  AND g.categoria_codigo = a.categoria_codigo
                  AND g.loja IS NOT DISTINCT FROM a.loja
                  AND g.data_cadastro >= a.data_cadastro
                  AND g.data_cadastro <= a.data_cadastro + INTERVAL '7 days'
            )) AS paga_mesma_loja,
            -- paga em OUTRA loja em <=7d apos
            (a.nome_norm <> '' AND EXISTS (
                SELECT 1 FROM paga g
                WHERE g.nome_norm = a.nome_norm
                  AND g.categoria_codigo = a.categoria_codigo
                  AND g.loja IS DISTINCT FROM a.loja
                  AND g.data_cadastro >= a.data_cadastro
                  AND g.data_cadastro <= a.data_cadastro + INTERVAL '7 days'
            )) AS paga_outra_loja,
            -- paga na MESMA regiao em <=7d apos
            (a.nome_norm <> '' AND EXISTS (
                SELECT 1 FROM paga g
                WHERE g.nome_norm = a.nome_norm
                  AND g.categoria_codigo = a.categoria_codigo
                  AND g.regiao IS NOT DISTINCT FROM a.regiao
                  AND g.data_cadastro >= a.data_cadastro
                  AND g.data_cadastro <= a.data_cadastro + INTERVAL '7 days'
            )) AS paga_mesma_regiao,
            -- paga em OUTRA regiao em <=7d apos
            (a.nome_norm <> '' AND EXISTS (
                SELECT 1 FROM paga g
                WHERE g.nome_norm = a.nome_norm
                  AND g.categoria_codigo = a.categoria_codigo
                  AND g.regiao IS DISTINCT FROM a.regiao
                  AND g.data_cadastro >= a.data_cadastro
                  AND g.data_cadastro <= a.data_cadastro + INTERVAL '7 days'
            )) AS paga_outra_regiao
        FROM canc a
    )
    SELECT
        f.id, f.contrato_id, f.valor, f.prazo, f.valor_parcela,
        f.tipo_operacao, f.data_cadastro, f.status_banco,
        f.data_status_banco, f.status_pagamento_cliente,
        f.data_status_pagamento, f.banco, f.convenio, f.num_proposta,
        f.sub_status_banco, f.loja, f.regiao, f.consultor, f.produto,
        f.tipo_produto, f.subtipo, f.categoria_codigo, f.grupo_dashboard,
        f.conta_valor,
        CASE
            WHEN f.is_redig THEN 'redigitada'
            WHEN f.paga_propria OR f.paga_outro THEN 'recuperada'
            ELSE 'liquido'
        END AS classificacao,
        -- Oportunidade perdida por nivel: representante (nao
        -- redigitada) que NAO foi recuperado no proprio nivel, mas
        -- foi pago em OUTRO consultor / OUTRA loja / OUTRA regiao.
        (NOT f.is_redig AND NOT f.paga_propria AND f.paga_outro)
            AS recuperada_outro,
        (NOT f.is_redig AND NOT f.paga_mesma_loja AND f.paga_outra_loja)
            AS recuperada_outra_loja,
        (NOT f.is_redig AND NOT f.paga_mesma_regiao AND f.paga_outra_regiao)
            AS recuperada_outra_regiao
    FROM flags f;
END;
$$;

COMMENT ON FUNCTION obter_cancelados_classificados(INTEGER, INTEGER) IS
    'Cancelados dos ultimos 30 dias classificados em '
    'redigitada / recuperada / liquido (matching por nome+categoria '
    'em janela de 7 dias). Marca tambem oportunidade perdida por nivel: '
    'recuperada_outro / recuperada_outra_loja / recuperada_outra_regiao '
    '(venda capturada por outro consultor / loja / regiao). '
    'O nome do cliente nao e exposto: so as flags saem no resultado.';

-- Acesso de execucao para os papeis do app. O dashboard le em
-- escopo completo e filtra por perfil client-side (aplicar_rls);
-- a classificacao e global de proposito (detecta cross-nivel).
GRANT EXECUTE ON FUNCTION obter_cancelados_classificados(INTEGER, INTEGER)
    TO anon, authenticated;
