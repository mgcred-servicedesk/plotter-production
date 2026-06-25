-- =====================================================
-- Migracao 032: RPC obter_cancelados_classificados
--
-- Objetivo: conter a inflacao do KPI de cancelados causada
-- por REDIGITACOES (mesma proposta redigitada varias vezes)
-- e por canceladas que foram redigitadas e PAGAS depois.
--
-- A RPC classifica cada cancelado (status_banco = 'CANCELADO')
-- em uma de tres classes, fazendo o matching pelo NOME do
-- cliente (homonimos = risco aceito). O nome (`contratos.cliente`)
-- e lido por join interno e NUNCA sai no resultado: so sai a
-- coluna `classificacao`. Isso preserva a postura de seguranca
-- do projeto (CPF nao e armazenado; nome nao trafega ao app).
--
-- Classes (janela de 7 dias, "mesmo produto" = categoria_codigo):
--   * redigitada  -> existe outro cancelamento do mesmo
--                    nome+categoria com data_cadastro POSTERIOR
--                    em ate 7 dias (foi superada). Sai da conta.
--   * recuperada  -> nao redigitada, mas existe proposta PAGA
--                    do mesmo nome+categoria com data_cadastro
--                    entre o cancelamento e +7 dias. Sai da conta.
--   * liquido     -> representante final do cluster sem paga em
--                    7 dias. CONTA como cancelamento real.
--
-- Coluna extra `recuperada_outro` (BOOLEAN): TRUE quando o
-- representante NAO foi recuperado pelo proprio consultor, mas a
-- venda foi paga por OUTRO consultor em <=7 dias (oportunidade
-- perdida). Subconjunto de `recuperada`; nao altera a contagem de
-- liquidos — alimenta a secao "Oportunidades perdidas". O nome de
-- quem capturou NAO e exposto (so o flag e o valor).
--
-- NOTA: a extensao por loja/regiao (supervisor/gerente) esta na
-- migration 033 (DROP + CREATE, pois o tipo de retorno muda).
--
-- Segue o mesmo padrao (datas de 30 dias, SECURITY INVOKER,
-- search_path vazio) da RPC obter_contratos_cancelados
-- (migration 003). A RPC antiga permanece intocada.
--
-- Executar no Supabase SQL Editor.
-- =====================================================

CREATE OR REPLACE FUNCTION obter_cancelados_classificados(
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
    recuperada_outro          BOOLEAN
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
        -- detectar recuperacao. Traz o consultor para distinguir
        -- recuperacao propria x por outro consultor. Filtro de
        -- data limita o scan.
        SELECT
            upper(trim(regexp_replace(
                coalesce(c.cliente, ''), '\s+', ' ', 'g'
            ))) AS nome_norm,
            cp.codigo AS categoria_codigo,
            con.nome  AS consultor,
            c.data_cadastro
        FROM public.contratos c
        JOIN public.produtos p            ON p.id  = c.produto_id
        JOIN public.categorias_produto cp ON cp.id = p.categoria_id
        LEFT JOIN public.consultores con  ON con.id = c.consultor_id
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
            )) AS paga_outro
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
        -- Oportunidade perdida: representante (nao redigitada) que o
        -- PROPRIO consultor nao recuperou, mas OUTRO consultor pagou.
        (NOT f.is_redig AND NOT f.paga_propria AND f.paga_outro)
            AS recuperada_outro
    FROM flags f;
END;
$$;

COMMENT ON FUNCTION obter_cancelados_classificados(INTEGER, INTEGER) IS
    'Cancelados dos ultimos 30 dias classificados em '
    'redigitada / recuperada / liquido (matching por nome+categoria '
    'em janela de 7 dias). Tambem marca recuperada_outro = TRUE quando '
    'a venda foi capturada por OUTRO consultor (oportunidade perdida). '
    'O nome do cliente nao e exposto: so a classificacao sai no resultado.';

-- Acesso de execucao para os papeis do app. O dashboard le em
-- escopo completo e filtra por perfil client-side (aplicar_rls);
-- a classificacao e global de proposito (detecta cross-consultor).
GRANT EXECUTE ON FUNCTION obter_cancelados_classificados(INTEGER, INTEGER)
    TO anon, authenticated;

-- Nota de performance: se o scan ficar lento, avaliar indice
-- funcional sobre o nome normalizado, p.ex.:
--   CREATE INDEX idx_contratos_cliente_norm
--     ON contratos (upper(trim(regexp_replace(coalesce(cliente,''),'\s+',' ','g'))));
-- Nao criado aqui para nao introduzir objeto de infra sem alinhamento.
