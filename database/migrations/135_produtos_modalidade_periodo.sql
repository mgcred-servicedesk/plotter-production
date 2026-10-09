-- =====================================================
-- Migracao 135: modalidade (NORMAL/FLEX) da tabela comercial
--               versionada por mes
-- Data: 2026-10-09
-- Depende de: 130 (ultima que redefiniu v_contratos_dashboard),
--             133 (ultima fn_admin_import), 057 (wrappers *_json)
-- Par: 136 (Caderno passa a ler a modalidade versionada)
--
-- MOTIVACAO
-- `produtos` guarda UMA linha por tabela comercial (`tabela`, unica) e
-- o import faz upsert por `tabela`: `produtos.tipo_operacao`
-- ('NORMAL' | 'FLEX') e sempre o valor da ULTIMA planilha. A planilha
-- de tabelas passa a ser importada TODO MES (com periodo selecionado,
-- como a de pontuacao), e uma tabela pode trocar de modalidade de um
-- mes para o outro. Sem historico, a troca reclassifica
-- retroativamente toda a producao ja paga naquela tabela.
--
-- ATENCAO: `contratos.tipo_operacao` (Contrato Novo / Refin / BMG
-- MED...) e OUTRA coisa e NAO e tocada aqui.
--
-- REGRA (decisoes do usuario, 2026-10-09)
--   Mes de referencia da proposta = mes de `data_cadastro` (NAO o
--   periodo_id, que e a competencia do pagamento). Para a tabela da
--   proposta (contratos.produto_id):
--     1. versao da propria tabela no mes do cadastro;
--     2. senao, a versao mais recente dela ANTERIOR a esse mes;
--     3. senao, produtos.tipo_operacao (ultima importacao — os dados
--        atuais valem para todos os meses ja importados);
--     4. proposta sem produto_id -> 'SEM TABELA'.
--   `modalidade_fallback` = TRUE sempre que o valor NAO veio de uma
--   versao do mes exato do cadastro (casos 2, 3 e 4).
--   PTS/pontos da planilha de tabelas continuam ignorados.
--
-- COMPORTAMENTO NO DIA DA APLICACAO
-- A tabela nasce vazia: todo contrato cai no caso 3 e a modalidade e
-- exatamente upper(btrim(produtos.tipo_operacao)) — o mesmo valor que
-- o Caderno usa hoje. Medido em 2026-10-09 (simulacao com CTE vazia):
-- 165.248/165.248 contratos com produto iguais, 0 divergentes, 1 sem
-- produto -> 'SEM TABELA'.
--
-- DECISOES NAO OBVIAS
--   * Coluna `competencia` (1o dia do mes do periodo), preenchida por
--     trigger a partir de `periodos`. O angry-man NAO a envia. Existe
--     para que "ultima versao da tabela ate o mes X" seja UMA sonda no
--     indice (produto_id, competencia DESC) — `periodo_id` e uuid, nao
--     ordena, e buscar via join com periodos custaria O(meses
--     importados) por contrato, para sempre.
--   * v_contratos_dashboard NAO chama as funcoes: replica a mesma
--     regra como subquery escalar inline. Medido em 2026-10-09 sobre
--     ~99k contratos: uma funcao SQL com SET search_path (nao
--     inlinavel) custou ~825 ms; a subquery escalar equivalente,
--     ~27 ms. Funcao com subquery nunca e inlinada pelo Postgres
--     (hasSubLinks), com ou sem SET search_path — entao o SET fica
--     nas funcoes (padrao do repo, advisor limpo) e a view usa a
--     forma inline. Coluna nao selecionada nao entra no plano (EXPLAIN
--     identico ao atual, custo 4692.68 nos dois).
--     As funcoes sao a definicao canonica e sao usadas pelos wrappers
--     *_json (poucos milhares de linhas). A paridade view x funcao e o
--     item 3 da validacao abaixo.
--   * Wrappers *_json: as funcoes subjacentes (RETURNS TABLE) NAO
--     mudam — mudar o RETURNS TABLE exigiria DROP. O wrapper busca o
--     produto_id pela PK de contratos (LATERAL com OFFSET 0: nested
--     loop na ordem da funcao, sem hash/seq scan de contratos) e
--     acrescenta as duas chaves no fim de cada objeto. json_agg de um
--     registro preserva a ordem das colunas (to_jsonb reordenaria).
--
-- ALCANCE REAL DA RLS AQUI (mesmo caveat da 064/066)
-- O dashboard conecta com service_role (BYPASSRLS). A leitura e
-- ampla, identica a `produtos`/`pontuacao` (pol_*_leitura, SELECT
-- USING (true), sem policy de escrita): a tabela so guarda
-- tabela comercial x mes x NORMAL/FLEX — nenhum dado pessoal,
-- nenhum valor. NAO usar o padrao deny das 127/134: o angry-man le
-- esta tabela com a chave anon para descobrir o mes mais recente ja
-- importado; leitura vazia silenciosa faria todo mes parecer o mais
-- recente e um import de mes antigo sobrescreveria `produtos`.
-- Escrita so via fn_admin_import (SECURITY DEFINER, service_role).
--
-- Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- 1. Tabela
-- ===========================================

CREATE TABLE IF NOT EXISTS public.produtos_modalidade_periodo (
    produto_id  UUID NOT NULL
                    REFERENCES public.produtos (id)
                    ON DELETE CASCADE,
    periodo_id  UUID NOT NULL
                    REFERENCES public.periodos (id),
    modalidade  TEXT NOT NULL,
    competencia DATE NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT produtos_modalidade_periodo_pkey
        PRIMARY KEY (produto_id, periodo_id),
    CONSTRAINT chk_produtos_modalidade_periodo_modalidade
        CHECK (modalidade IN ('NORMAL', 'FLEX')),
    CONSTRAINT chk_produtos_modalidade_periodo_competencia
        CHECK (extract(day FROM competencia) = 1)
);

-- "Ultima versao da tabela ate o mes X" e "versao do mes exato":
-- uma sonda, index-only (INCLUDE modalidade).
CREATE INDEX IF NOT EXISTS idx_produtos_modalidade_periodo_produto_competencia
    ON public.produtos_modalidade_periodo (produto_id, competencia DESC)
    INCLUDE (modalidade);

-- DELETE por periodo_id do fn_admin_import (deleteWhere) e FK de
-- periodos — mesmo par de indices de pontuacao.
CREATE INDEX IF NOT EXISTS idx_produtos_modalidade_periodo_periodo_id
    ON public.produtos_modalidade_periodo (periodo_id);

COMMENT ON TABLE public.produtos_modalidade_periodo IS
    'Modalidade (NORMAL/FLEX) de cada tabela comercial por mes, da '
    'planilha de tabelas importada mensalmente (angry-man, via '
    'fn_admin_import). produtos.tipo_operacao segue sendo a ultima '
    'importacao. Consultar via fn_modalidade_tabela / '
    'fn_modalidade_tabela_fallback ou v_contratos_dashboard.modalidade.';
COMMENT ON COLUMN public.produtos_modalidade_periodo.modalidade IS
    'NORMAL ou FLEX (o importador normaliza para maiusculas).';
COMMENT ON COLUMN public.produtos_modalidade_periodo.competencia IS
    'Primeiro dia do mes do periodo_id. Preenchida SEMPRE pelo trigger '
    'trg_produtos_modalidade_periodo_competencia a partir de periodos '
    '(valor enviado pelo cliente e sobrescrito). Existe so para a busca '
    'ordenada por mes no indice.';


-- ===========================================
-- 2. Triggers
-- ===========================================

CREATE OR REPLACE FUNCTION public.fn_produtos_modalidade_periodo_competencia()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    SELECT make_date(p.ano, p.mes, 1)
      INTO NEW.competencia
      FROM public.periodos p
     WHERE p.id = NEW.periodo_id;

    -- Erro explicito em vez de "null value in column competencia".
    IF NEW.competencia IS NULL THEN
        RAISE EXCEPTION
            'produtos_modalidade_periodo: periodo_id % nao existe em periodos',
            NEW.periodo_id;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_produtos_modalidade_periodo_competencia
    ON public.produtos_modalidade_periodo;
CREATE TRIGGER trg_produtos_modalidade_periodo_competencia
    BEFORE INSERT OR UPDATE ON public.produtos_modalidade_periodo
    FOR EACH ROW
    EXECUTE FUNCTION public.fn_produtos_modalidade_periodo_competencia();

-- Mesmo trigger das demais tabelas da whitelist do fn_admin_import.
DROP TRIGGER IF EXISTS trg_produtos_modalidade_periodo_updated_at
    ON public.produtos_modalidade_periodo;
CREATE TRIGGER trg_produtos_modalidade_periodo_updated_at
    BEFORE UPDATE ON public.produtos_modalidade_periodo
    FOR EACH ROW
    EXECUTE FUNCTION public.atualizar_updated_at();


-- ===========================================
-- 3. RLS — leitura ampla (padrao produtos/pontuacao), sem escrita
-- ===========================================

ALTER TABLE public.produtos_modalidade_periodo ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS pol_produtos_modalidade_periodo_leitura
    ON public.produtos_modalidade_periodo;
CREATE POLICY pol_produtos_modalidade_periodo_leitura
    ON public.produtos_modalidade_periodo FOR SELECT
    USING (true);

-- Explicito (os default privileges do Supabase ja concedem): o
-- angry-man le com a chave anon. Escrita continua barrada pela RLS
-- (nenhuma policy de INSERT/UPDATE/DELETE) — so service_role /
-- fn_admin_import gravam.
GRANT SELECT ON public.produtos_modalidade_periodo TO anon, authenticated;


-- ===========================================
-- 4. Funcoes canonicas
-- ===========================================

CREATE OR REPLACE FUNCTION public.fn_modalidade_tabela(
    p_produto_id    UUID,
    p_data_cadastro DATE
)
RETURNS TEXT
LANGUAGE sql
STABLE
PARALLEL SAFE
SET search_path = ''
AS $$
    SELECT CASE
        WHEN p_produto_id IS NULL THEN 'SEM TABELA'
        ELSE coalesce(
            -- 1 e 2: versao do mes do cadastro ou a mais recente antes
            -- dele. data_cadastro NULL nao casa nada e cai no 3.
            (SELECT v.modalidade
               FROM public.produtos_modalidade_periodo v
              WHERE v.produto_id = p_produto_id
                AND v.competencia
                    <= date_trunc('month', p_data_cadastro::timestamp)::date
              ORDER BY v.competencia DESC
              LIMIT 1),
            -- 3: ultima importacao (mesma expressao do Caderno ate a 135).
            (SELECT upper(btrim(coalesce(p.tipo_operacao, '')))
               FROM public.produtos p
              WHERE p.id = p_produto_id)
        )
    END;
$$;

COMMENT ON FUNCTION public.fn_modalidade_tabela(UUID, DATE) IS
    'Modalidade (NORMAL/FLEX) da tabela comercial no mes de '
    'data_cadastro: versao do mes; senao a mais recente anterior; senao '
    'produtos.tipo_operacao; produto NULL -> ''SEM TABELA''. Espelhada '
    'inline em v_contratos_dashboard.modalidade (por custo) — mudar uma '
    'exige mudar a outra.';

CREATE OR REPLACE FUNCTION public.fn_modalidade_tabela_fallback(
    p_produto_id    UUID,
    p_data_cadastro DATE
)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
PARALLEL SAFE
SET search_path = ''
AS $$
    SELECT NOT EXISTS (
        SELECT 1
          FROM public.produtos_modalidade_periodo v
         WHERE v.produto_id = p_produto_id
           AND v.competencia
               = date_trunc('month', p_data_cadastro::timestamp)::date
    );
$$;

COMMENT ON FUNCTION public.fn_modalidade_tabela_fallback(UUID, DATE) IS
    'TRUE quando fn_modalidade_tabela NAO veio de uma versao do mes exato '
    'do cadastro (versao anterior, produtos.tipo_operacao ou SEM TABELA). '
    'Nunca NULL. Espelhada inline em '
    'v_contratos_dashboard.modalidade_fallback.';

GRANT EXECUTE ON FUNCTION public.fn_modalidade_tabela(UUID, DATE)
    TO anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_modalidade_tabela_fallback(UUID, DATE)
    TO anon, authenticated;


-- ===========================================
-- 5. v_contratos_dashboard
--    Base: migration 130 (conferida contra pg_get_viewdef e os tipos
--    de pg_attribute em 2026-10-09). Identica, mais DUAS colunas no
--    FIM: modalidade, modalidade_fallback. Nenhuma coluna existente
--    muda de nome, tipo ou ordem.
-- ===========================================

CREATE OR REPLACE VIEW v_contratos_dashboard AS
SELECT
    c.id,
    c.contrato_id,
    c.valor,
    c.prazo,
    c.valor_parcela,
    c.tipo_operacao,
    c.data_cadastro,
    c.status_banco,
    c.data_status_banco,
    c.status_pagamento_cliente,
    c.data_status_pagamento,
    c.banco,
    c.convenio,
    c.num_proposta,
    c.sub_status_banco,
    c.periodo_id,
    l.nome        AS loja,
    r.nome        AS regiao,        -- vigente na COMPETENCIA do pagamento
    con.nome      AS consultor,
    p.tabela      AS produto,
    p.tipo        AS tipo_produto,
    p.subtipo,
    cp.codigo     AS categoria_codigo,
    cp.grupo_dashboard,
    cp.grupo_meta,
    cp.conta_valor,
    cp.conta_pontuacao,
    c.created_at,
    r_atual.nome  AS regiao_atual,   -- organograma atual (RLS)
    COALESCE(c.valor_bruto,   c.valor) AS valor_bruto,
    COALESCE(c.valor_liquido, c.valor) AS valor_liquido,
    -- 130: criterio misto — sinal de valor (>= 08/2026) OU tabela
    -- dedicada do banco.
    (public.fn_eh_cobranca_consignavel_por_valor(
         c.tipo_operacao, p.subtipo, cp.codigo, c.banco,
         c.valor, c.valor_bruto, c.data_status_pagamento)
     OR public.fn_eh_tabela_cobranca_consignavel(p.tabela)
    ) AS is_cobranca_consignavel,
    -- 130: uplift SO pelo sinal de valor. Tabela dedicada (inclusive
    -- REFIN) produz no VLR BASE.
    (CASE
        WHEN public.fn_eh_cobranca_consignavel_por_valor(
                c.tipo_operacao, p.subtipo, cp.codigo, c.banco,
                c.valor, c.valor_bruto, c.data_status_pagamento)
        THEN GREATEST(COALESCE(c.valor_bruto, c.valor), c.valor)
        ELSE c.valor
     END)::NUMERIC(15,2) AS valor_consolidado,
    -- 135: espelho INLINE de fn_modalidade_tabela (subquery escalar, so
    -- avaliada quando a coluna e selecionada). `p` ja e o produto da
    -- proposta, entao o passo 3 dispensa nova busca.
    (CASE
        WHEN c.produto_id IS NULL THEN 'SEM TABELA'
        ELSE COALESCE(
            (SELECT pmp.modalidade
               FROM public.produtos_modalidade_periodo pmp
              WHERE pmp.produto_id = c.produto_id
                AND pmp.competencia
                    <= date_trunc('month', c.data_cadastro::timestamp)::date
              ORDER BY pmp.competencia DESC
              LIMIT 1),
            upper(btrim(COALESCE(p.tipo_operacao, '')))
        )
     END) AS modalidade,
    -- 135: espelho INLINE de fn_modalidade_tabela_fallback.
    (NOT EXISTS (
        SELECT 1
          FROM public.produtos_modalidade_periodo pmp
         WHERE pmp.produto_id = c.produto_id
           AND pmp.competencia
               = date_trunc('month', c.data_cadastro::timestamp)::date
    )) AS modalidade_fallback
FROM contratos c
LEFT JOIN lojas l              ON l.id  = c.loja_id
LEFT JOIN periodos per         ON per.id = c.periodo_id
LEFT JOIN LATERAL (
    SELECT vig.regiao_id
    FROM loja_regiao_vigencia vig
    WHERE vig.loja_id = c.loja_id
      AND COALESCE(make_date(per.ano, per.mes, 1), c.data_cadastro)
              >= vig.vigencia_inicio
      AND (vig.vigencia_fim IS NULL
           OR COALESCE(make_date(per.ano, per.mes, 1), c.data_cadastro)
              < vig.vigencia_fim)
    ORDER BY vig.vigencia_inicio DESC
    LIMIT 1
) rv ON true
LEFT JOIN regioes r            ON r.id  = COALESCE(rv.regiao_id, l.regiao_id)
LEFT JOIN regioes r_atual      ON r_atual.id = l.regiao_id
LEFT JOIN consultores con      ON con.id = c.consultor_id
LEFT JOIN produtos p           ON p.id  = c.produto_id
LEFT JOIN categorias_produto cp ON cp.id = p.categoria_id
WHERE
    c.status_pagamento_cliente = 'PAGO AO CLIENTE'
    OR
    (c.sub_status_banco = 'Liquidada'
     AND c.tipo_operacao IN ('BMG MED', 'Seguro'));

ALTER VIEW public.v_contratos_dashboard
    SET (security_invoker = on);

COMMENT ON COLUMN v_contratos_dashboard.modalidade IS
    'NORMAL/FLEX da tabela comercial no MES DE data_cadastro '
    '(produtos_modalidade_periodo: mes exato -> versao anterior -> '
    'produtos.tipo_operacao); ''SEM TABELA'' sem produto. Mesma regra de '
    'fn_modalidade_tabela. Nao reimplementar no consumidor.';

COMMENT ON COLUMN v_contratos_dashboard.modalidade_fallback IS
    'TRUE quando `modalidade` nao veio de versao do mes exato do '
    'cadastro. Nunca NULL. Mesma regra de fn_modalidade_tabela_fallback.';


-- ===========================================
-- 6. Wrappers *_json dos Analiticos (base: 057)
--    Mesma assinatura e RETURNS JSON; cada objeto ganha, no fim,
--    `modalidade` e `modalidade_fallback`. As funcoes RETURNS TABLE
--    subjacentes nao mudam.
-- ===========================================

CREATE OR REPLACE FUNCTION public.obter_contratos_em_analise_json(
    p_mes INTEGER,
    p_ano INTEGER
)
RETURNS JSON
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
    SELECT COALESCE(json_agg(x), '[]'::json)
    FROM (
        SELECT
            t.*,
            public.fn_modalidade_tabela(k.produto_id, t.data_cadastro)
                AS modalidade,
            public.fn_modalidade_tabela_fallback(k.produto_id, t.data_cadastro)
                AS modalidade_fallback
        FROM public.obter_contratos_em_analise(p_mes, p_ano) t
        LEFT JOIN LATERAL (
            -- PK por linha, na ordem da funcao (OFFSET 0 impede o
            -- pull-up e, com ele, um hash join com seq scan).
            SELECT c.produto_id
              FROM public.contratos c
             WHERE c.id = t.id
            OFFSET 0
        ) k ON true
    ) x;
$$;

CREATE OR REPLACE FUNCTION public.obter_cancelados_classificados_json(
    p_mes INTEGER,
    p_ano INTEGER
)
RETURNS JSON
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
    SELECT COALESCE(json_agg(x), '[]'::json)
    FROM (
        SELECT
            t.*,
            public.fn_modalidade_tabela(k.produto_id, t.data_cadastro)
                AS modalidade,
            public.fn_modalidade_tabela_fallback(k.produto_id, t.data_cadastro)
                AS modalidade_fallback
        FROM public.obter_cancelados_classificados(p_mes, p_ano) t
        LEFT JOIN LATERAL (
            SELECT c.produto_id
              FROM public.contratos c
             WHERE c.id = t.id
            OFFSET 0
        ) k ON true
    ) x;
$$;


-- ===========================================
-- 7. fn_admin_import — whitelist
--    IDENTICA a 133 (conferida contra pg_get_functiondef em
--    2026-10-09), so com 'produtos_modalidade_periodo' no v_allowed.
--
--    Fluxos suportados para a tabela nova:
--      * upsert: p_on_conflict = 'produto_id,periodo_id' -> ON CONFLICT
--        (produto_id, periodo_id) DO UPDATE (casa a PK composta);
--      * delete+insert: p_delete_where = {"periodo_id": "<uuid>"} ->
--        DELETE ... WHERE periodo_id = '<uuid>' e INSERT ... ON CONFLICT
--        DO NOTHING, na mesma chamada (mesma transacao). p_on_conflict
--        e ignorado nesse modo. ATENCAO: o DELETE roda a CADA chamada —
--        importador que mande o mes em varios lotes com deleteWhere em
--        todos apaga os lotes anteriores (deleteWhere so no primeiro).
--    `competencia` nao precisa vir no payload (trigger); `updated_at`
--    e bumpado pelo trigger no DO UPDATE.
-- ===========================================

CREATE OR REPLACE FUNCTION public.fn_admin_import(
    p_table text,
    p_data jsonb,
    p_on_conflict text DEFAULT NULL::text,
    p_delete_where jsonb DEFAULT NULL::jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
    v_count         integer := 0;
    v_insert_cols   text;
    v_update_cols   text;
    v_conflict_cols text;
    v_delete_where  text;
    v_sql           text;
    v_cmp_atual     text;
    v_cmp_novo      text;
    v_update_where  text := '';
    v_allowed       text[] := ARRAY[
        'regioes','lojas','consultores','supervisores',
        'periodos','produtos','contratos','metas','pontuacao',
        'produtos_modalidade_periodo'
    ];
BEGIN
    -- 1. Validar tabela (whitelist contra SQL injection)
    IF NOT (p_table = ANY(v_allowed)) THEN
        RETURN jsonb_build_object(
            'count', 0,
            'error', format('Tabela nao permitida: %s', p_table)
        );
    END IF;

    IF p_data IS NULL OR jsonb_array_length(p_data) = 0 THEN
        RETURN jsonb_build_object('count', 0, 'error', NULL);
    END IF;

    -- 2. DELETE antes do insert quando p_delete_where for informado.
    -- Constrói WHERE col = 'val' para cada chave do JSONB.
    -- %I faz quoting seguro do identificador; %L do literal.
    IF p_delete_where IS NOT NULL
       AND jsonb_typeof(p_delete_where) = 'object'
    THEN
        SELECT string_agg(format('%I = %L', key, value), ' AND ')
        INTO v_delete_where
        FROM jsonb_each_text(p_delete_where);

        IF v_delete_where IS NOT NULL THEN
            v_sql := format('DELETE FROM %I WHERE %s', p_table, v_delete_where);
            EXECUTE v_sql;
        END IF;
    END IF;

    -- 3. Construir lista de colunas de conflito com quoting seguro por coluna.
    -- Ignorado quando p_delete_where foi usado (insert simples após delete).
    IF p_on_conflict IS NOT NULL AND p_delete_where IS NULL THEN
        SELECT string_agg(format('%I', trim(col)), ', ')
        INTO v_conflict_cols
        FROM unnest(string_to_array(p_on_conflict, ',')) AS col
        WHERE trim(col) != '';
    END IF;

    -- 4. Colunas do JSONB que existem na tabela destino
    SELECT
        string_agg(format('%I', c.column_name), ', ' ORDER BY c.ordinal_position),
        string_agg(
            CASE WHEN c.column_name NOT IN ('id', 'created_at')
                THEN format('%I = EXCLUDED.%I', c.column_name, c.column_name)
            END,
            ', ' ORDER BY c.ordinal_position
        ),
        -- Mesmas colunas do SET, para o filtro de linha inalterada.
        string_agg(
            CASE WHEN c.column_name NOT IN ('id', 'created_at')
                THEN format('%I.%I', p_table, c.column_name)
            END,
            ', ' ORDER BY c.ordinal_position
        ),
        string_agg(
            CASE WHEN c.column_name NOT IN ('id', 'created_at')
                THEN format('EXCLUDED.%I', c.column_name)
            END,
            ', ' ORDER BY c.ordinal_position
        )
    INTO v_insert_cols, v_update_cols, v_cmp_atual, v_cmp_novo
    FROM information_schema.columns c
    WHERE c.table_schema = 'public'
      AND c.table_name   = p_table
      AND c.column_name IN (
          SELECT jsonb_object_keys(p_data -> 0)
      );

    -- Remover NULLs residuais do string_agg (colunas excluidas)
    v_update_cols := array_to_string(
        array_remove(
            string_to_array(v_update_cols, ', '),
            NULL
        ),
        ', '
    );

    IF v_insert_cols IS NULL THEN
        RETURN jsonb_build_object(
            'count', 0,
            'error', 'Nenhuma coluna valida encontrada no payload'
        );
    END IF;

    -- Migration 133: em contratos, nao reescrever linha identica
    -- (UPDATE non-HOT mantem os 14 indices). Outras tabelas tem
    -- trigger de updated_at — ficam como estavam.
    IF p_table = 'contratos' AND v_cmp_atual IS NOT NULL THEN
        v_update_where := format(
            ' WHERE (%s) IS DISTINCT FROM (%s)', v_cmp_atual, v_cmp_novo
        );
    END IF;

    -- 5. Montar e executar SQL dinamico
    IF v_conflict_cols IS NOT NULL AND v_update_cols IS NOT NULL
       AND v_update_cols != '' THEN
        -- Upsert normal: ON CONFLICT (...) DO UPDATE
        v_sql := format(
            'WITH ins AS (
                INSERT INTO %I (%s)
                SELECT %s
                FROM jsonb_populate_recordset(null::%I, $1)
                ON CONFLICT (%s) DO UPDATE SET %s%s
                RETURNING 1
            ) SELECT count(*) FROM ins',
            p_table, v_insert_cols,
            v_insert_cols,
            p_table, v_conflict_cols, v_update_cols, v_update_where
        );
    ELSIF p_delete_where IS NOT NULL THEN
        -- Insert após delete: ON CONFLICT DO NOTHING para linhas
        -- duplicadas dentro do próprio arquivo (segurança extra).
        v_sql := format(
            'WITH ins AS (
                INSERT INTO %I (%s)
                SELECT %s
                FROM jsonb_populate_recordset(null::%I, $1)
                ON CONFLICT DO NOTHING
                RETURNING 1
            ) SELECT count(*) FROM ins',
            p_table, v_insert_cols,
            v_insert_cols,
            p_table
        );
    ELSE
        -- Insert simples sem tratamento de conflito
        v_sql := format(
            'WITH ins AS (
                INSERT INTO %I (%s)
                SELECT %s
                FROM jsonb_populate_recordset(null::%I, $1)
                RETURNING 1
            ) SELECT count(*) FROM ins',
            p_table, v_insert_cols,
            v_insert_cols,
            p_table
        );
    END IF;

    EXECUTE v_sql INTO v_count USING p_data;

    -- Com o filtro, RETURNING so conta as linhas tocadas. 'count'
    -- continua sendo o lote processado (contrato com o app);
    -- 'alterados' expoe o que de fato foi gravado.
    IF v_update_where != '' AND v_sql LIKE '%DO UPDATE%' THEN
        RETURN jsonb_build_object(
            'count', jsonb_array_length(p_data),
            'alterados', v_count,
            'error', NULL
        );
    END IF;

    RETURN jsonb_build_object('count', v_count, 'error', NULL);

EXCEPTION WHEN OTHERS THEN
    RETURN jsonb_build_object('count', 0, 'error', SQLERRM);
END;
$function$;

NOTIFY pgrst, 'reload schema';


-- ===========================================
-- 8. Validacao pos-migracao
-- ===========================================
-- 1) Tabela vazia => modalidade == produtos.tipo_operacao em TODO
--    contrato pago (medido por simulacao em 2026-10-09: 125.191 linhas
--    na view, 0 divergentes):
--
--   SELECT count(*) FILTER (WHERE v.modalidade IS DISTINCT FROM
--                              upper(btrim(p.tipo_operacao))) AS divergentes,
--          count(*) FILTER (WHERE NOT v.modalidade_fallback)  AS exatos
--   FROM v_contratos_dashboard v
--   JOIN contratos c ON c.id = v.id
--   LEFT JOIN produtos p ON p.id = c.produto_id;
--   -- Esperado (tabela vazia): 0, 0
--
--   SELECT fn_modalidade_tabela(NULL, current_date),
--          fn_modalidade_tabela_fallback(NULL, current_date);
--   -- Esperado: SEM TABELA, t
--
-- 2) Fallback (rodar em transacao com ROLLBACK; :pid = um produto
--    NORMAL qualquer):
--
--   BEGIN;
--   INSERT INTO produtos_modalidade_periodo (produto_id, periodo_id, modalidade)
--   SELECT :pid, per.id, 'FLEX' FROM periodos per
--    WHERE (per.mes, per.ano) IN ((7, 2026), (10, 2026));
--   SELECT fn_modalidade_tabela(:pid, '2026-10-15'), fn_modalidade_tabela_fallback(:pid, '2026-10-15'),  -- FLEX, f
--          fn_modalidade_tabela(:pid, '2026-09-03'), fn_modalidade_tabela_fallback(:pid, '2026-09-03'),  -- FLEX, t
--          fn_modalidade_tabela(:pid, '2026-06-30'), fn_modalidade_tabela_fallback(:pid, '2026-06-30');  -- NORMAL, t
--   SELECT competencia FROM produtos_modalidade_periodo WHERE produto_id = :pid;
--   -- Esperado: 2026-07-01, 2026-10-01 (trigger)
--   ROLLBACK;
--
-- 3) Paridade view x funcao (deve ser 0 sempre, com ou sem versoes):
--
--   SELECT count(*) FROM v_contratos_dashboard v JOIN contratos c ON c.id = v.id
--   WHERE v.modalidade IS DISTINCT FROM fn_modalidade_tabela(c.produto_id, c.data_cadastro)
--      OR v.modalidade_fallback IS DISTINCT FROM
--         fn_modalidade_tabela_fallback(c.produto_id, c.data_cadastro);
--
-- 4) Custo: SELECT sem as colunas novas tem o MESMO plano de antes
--    (em 2026-10-09: custo 4692.68):
--
--   EXPLAIN SELECT contrato_id, loja, valor_consolidado
--   FROM v_contratos_dashboard WHERE data_status_pagamento >= '2026-10-01';
--
-- 5) Wrappers: mesma contagem de antes e as duas chaves no fim:
--
--   SELECT json_array_length(obter_contratos_em_analise_json(10, 2026)),
--          (SELECT count(*) FROM obter_contratos_em_analise(10, 2026));
--   SELECT json_object_keys(obter_cancelados_classificados_json(10, 2026) -> 0);
--
-- 6) fn_admin_import aceita a tabela (ROLLBACK):
--
--   BEGIN;
--   SELECT fn_admin_import('produtos_modalidade_periodo',
--       (SELECT jsonb_agg(jsonb_build_object('produto_id', p.id,
--               'periodo_id', per.id, 'modalidade', upper(btrim(p.tipo_operacao))))
--          FROM produtos p CROSS JOIN periodos per
--         WHERE per.mes = 10 AND per.ano = 2026),
--       'produto_id,periodo_id', NULL);
--   -- Esperado: {"count": 1016, "error": null}
--   ROLLBACK;
--
-- Reversao (so se nada consumir as colunas/chaves novas): CREATE OR
-- REPLACE nao remove coluna de view — exige DROP VIEW + recriar a 130.
