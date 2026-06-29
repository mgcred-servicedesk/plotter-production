-- =====================================================
-- Migracao 039: coluna gerada cliente_norm + RPC
--               obter_cancelados_classificados sem regexp
--               em runtime
--
-- Problema (continuacao da 034/036):
-- A RPC obter_cancelados_classificados normaliza o nome do
-- cliente em RUNTIME — upper(trim(regexp_replace(
--   coalesce(c.cliente,''),'\s+',' ','g'))) — DUAS vezes:
--   * CTE `canc`: para cada cancelado da janela (~2k no 6/2026);
--   * CTE `paga`: para CADA contrato PAGO da janela de ~37 dias
--     (conjunto tipicamente bem maior que canc).
-- Mesmo apos a 036 ter eliminado o O(n^2) do `redig`, esse
-- custo de base (~3s, com statement_timeout de 15s como rede)
-- e dominado por recalcular o regexp por linha a cada chamada.
--
-- Por que NAO um indice funcional:
-- a normalizacao aparece na SELECT-list dos CTEs e os joins
-- de matching sao hash-join CTE<->CTE. O planner do PostgreSQL
-- NAO usa indice de expressao para evitar recomputar uma
-- expressao da SELECT-list nem para o join entre CTEs — logo
-- um indice funcional daria ganho ~zero aqui.
--
-- Correcao estrutural:
--   1. Coluna GERADA STORED `cliente_norm` em contratos. Como
--      upper/trim/regexp_replace/coalesce sao IMMUTABLE, o
--      Postgres aceita a expressao em GENERATED ALWAYS ... STORED.
--      O valor passa a ser materializado na escrita; a leitura
--      nao recalcula o regexp.
--   2. CREATE OR REPLACE da RPC trocando as DUAS expressoes de
--      normalizacao por `c.cliente_norm`. Todo o resto (canc,
--      paga, redig, matches, classificacao, flags) fica IDENTICO
--      a 036 — equivalencia semantica exata, pois cliente_norm
--      reproduz literalmente a mesma expressao.
--
-- ⚠️  ATENCAO / IMPACTO OPERACIONAL:
--   Adicionar uma coluna GERADA STORED REESCREVE a tabela
--   `contratos` inteira e adquire lock ACCESS EXCLUSIVE durante
--   a operacao — ESCRITAS FICAM BLOQUEADAS ate concluir
--   (segundos a minutos, conforme o tamanho da tabela).
--   Executar em JANELA DE BAIXO MOVIMENTO / FORA do horario do
--   ETL de importacao. Operacao unica e idempotente (IF NOT
--   EXISTS).
--
-- Migrations 034/036 sao imutaveis e nao foram editadas; esta
-- substitui a RPC via CREATE OR REPLACE.
--
-- Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- 1. Coluna gerada cliente_norm (STORED)
--    Mesma normalizacao usada pela RPC (036).
--    ⚠️ Reescreve a tabela contratos (lock ACCESS EXCLUSIVE).
-- ===========================================

ALTER TABLE public.contratos
    ADD COLUMN IF NOT EXISTS cliente_norm TEXT
    GENERATED ALWAYS AS (
        upper(trim(regexp_replace(
            coalesce(cliente, ''), '\s+', ' ', 'g'
        )))
    ) STORED;

COMMENT ON COLUMN public.contratos.cliente_norm IS
    'Nome do cliente normalizado (upper + trim + colapso de '
    'espacos) materializado na escrita. Usado como chave de '
    'matching em obter_cancelados_classificados (redigitada / '
    'recuperada), evitando recalcular o regexp por linha em '
    'tempo de query. Migration 039.';


-- ===========================================
-- 2. RPC obter_cancelados_classificados — reescrita
--    Unica mudanca vs 036: as duas expressoes de
--    normalizacao viram `c.cliente_norm`.
-- ===========================================

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
    recuperada_outro          BOOLEAN,
    recuperada_outra_loja     BOOLEAN,
    recuperada_outra_regiao   BOOLEAN
)
LANGUAGE plpgsql
STABLE
SET search_path = ''
SET statement_timeout = '15000'
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
        -- Cancelados da janela; puxa o nome normalizado do base
        -- contratos apenas para o matching (nao sera retornado).
        SELECT
            v.id, v.contrato_id, v.valor, v.prazo, v.valor_parcela,
            v.tipo_operacao, v.data_cadastro, v.status_banco,
            v.data_status_banco, v.status_pagamento_cliente,
            v.data_status_pagamento, v.banco, v.convenio, v.num_proposta,
            v.sub_status_banco, v.loja, v.regiao, v.consultor, v.produto,
            v.tipo_produto, v.subtipo, v.categoria_codigo, v.grupo_dashboard,
            v.conta_valor,
            c.cliente_norm AS nome_norm
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
            c.cliente_norm AS nome_norm,
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
    redig AS (
        -- Superada por cancelamento posterior em <=7d (self-join
        -- sobre canc). LEFT JOIN agregado set-based (036). A guarda
        -- de nome vazio fica na juncao: linhas com nome_norm = ''
        -- nao casam nenhum b -> bool_or = false, e o LEFT JOIN
        -- mantem UMA linha por cancelado. Desigualdade ESTRITA `>`.
        SELECT
            a.id,
            (a.nome_norm <> '' AND bool_or(b.id IS NOT NULL)) AS is_redig
        FROM canc a
        LEFT JOIN canc b
          ON a.nome_norm <> ''
         AND b.nome_norm        = a.nome_norm
         AND b.categoria_codigo = a.categoria_codigo
         AND b.data_cadastro    > a.data_cadastro
         AND b.data_cadastro   <= a.data_cadastro + INTERVAL '7 days'
        GROUP BY a.id, a.nome_norm
    ),
    matches AS (
        -- Uma unica passagem pela janela de pagas por cancelado:
        -- todas as flags de recuperacao derivam deste JOIN agregado.
        SELECT
            a.id,
            bool_or(g.consultor IS NOT DISTINCT FROM a.consultor)
                AS paga_propria,
            bool_or(g.consultor IS DISTINCT FROM a.consultor)
                AS paga_outro,
            bool_or(g.loja IS NOT DISTINCT FROM a.loja)
                AS paga_mesma_loja,
            bool_or(g.loja IS DISTINCT FROM a.loja)
                AS paga_outra_loja,
            bool_or(g.regiao IS NOT DISTINCT FROM a.regiao)
                AS paga_mesma_regiao,
            bool_or(g.regiao IS DISTINCT FROM a.regiao)
                AS paga_outra_regiao
        FROM canc a
        JOIN paga g
          ON g.nome_norm        = a.nome_norm
         AND g.categoria_codigo = a.categoria_codigo
         AND g.data_cadastro   >= a.data_cadastro
         AND g.data_cadastro   <= a.data_cadastro + INTERVAL '7 days'
        WHERE a.nome_norm <> ''
        GROUP BY a.id
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
            WHEN rd.is_redig THEN 'redigitada'
            WHEN COALESCE(m.paga_propria, false)
              OR COALESCE(m.paga_outro, false) THEN 'recuperada'
            ELSE 'liquido'
        END AS classificacao,
        -- Oportunidade perdida por nivel: representante (nao
        -- redigitada) que NAO foi recuperado no proprio nivel, mas
        -- foi pago em OUTRO consultor / OUTRA loja / OUTRA regiao.
        (NOT rd.is_redig
            AND NOT COALESCE(m.paga_propria, false)
            AND COALESCE(m.paga_outro, false))
            AS recuperada_outro,
        (NOT rd.is_redig
            AND NOT COALESCE(m.paga_mesma_loja, false)
            AND COALESCE(m.paga_outra_loja, false))
            AS recuperada_outra_loja,
        (NOT rd.is_redig
            AND NOT COALESCE(m.paga_mesma_regiao, false)
            AND COALESCE(m.paga_outra_regiao, false))
            AS recuperada_outra_regiao
    FROM canc f
    JOIN redig rd        ON rd.id = f.id
    LEFT JOIN matches m  ON m.id  = f.id;
END;
$$;

COMMENT ON FUNCTION obter_cancelados_classificados(INTEGER, INTEGER) IS
    'Cancelados dos ultimos 30 dias classificados em '
    'redigitada / recuperada / liquido (matching por nome+categoria '
    'em janela de 7 dias). Marca tambem oportunidade perdida por nivel: '
    'recuperada_outro / recuperada_outra_loja / recuperada_outra_regiao. '
    'O nome do cliente nao e exposto: so as flags saem no resultado. '
    'Migration 039: matching passa a usar contratos.cliente_norm '
    '(coluna gerada STORED) em vez de recalcular o regexp por linha '
    'em runtime — mesma semantica da 036, sem o custo de normalizacao.';

-- Acesso de execucao para os papeis do app (preserva GRANT da 036).
GRANT EXECUTE ON FUNCTION obter_cancelados_classificados(INTEGER, INTEGER)
    TO anon, authenticated;


-- ===========================================
-- 3. Validacao de performance (EXPLAIN ANALYZE)
--
-- Rodar no Supabase SQL Editor. Substitua (6, 2026) pelo
-- periodo com mais volume de cancelados que voce quiser medir.
--
-- Passo A — ANTES de aplicar a secao 1/2 desta migration
--   (estado atual = RPC 036 com regexp em runtime):
--
--     EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
--     SELECT * FROM obter_cancelados_classificados(6, 2026);
--
--   Anote: "Execution Time", e o custo dos nodes que computam
--   regexp_replace sobre contratos (Seq/Index Scan em contratos
--   nos CTEs canc e paga).
--
-- Passo B — DEPOIS de aplicar as secoes 1 e 2:
--
--     EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
--     SELECT * FROM obter_cancelados_classificados(6, 2026);
--
--   Esperado: desaparecem os calculos de regexp_replace nos
--   scans (a coluna ja vem materializada); "Execution Time"
--   menor, com folga maior sobre o statement_timeout de 15s.
--
-- Sanidade (equivalencia de resultado antes x depois):
--
--     SELECT classificacao, count(*)
--     FROM obter_cancelados_classificados(6, 2026)
--     GROUP BY classificacao
--     ORDER BY classificacao;
--
--   As contagens devem ser IDENTICAS antes e depois (a
--   normalizacao e a mesma expressao).
-- ===========================================
