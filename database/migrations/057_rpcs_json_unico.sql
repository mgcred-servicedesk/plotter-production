-- =====================================================
-- Migracao 057: variantes _json das RPCs paginadas (json_agg unico)
--
-- Contexto (continuacao do Disk IO Budget; ver 054/056 e
-- docs/agents/progress/2026-07-08-disk-io-*.md):
--
-- O dashboard paginava as RPCs obter_contratos_em_analise,
-- obter_digitacao_diaria_detalhe e obter_cancelados_classificados com
-- .range() (Range header). Para funcao, o PostgREST NAO empurra o
-- limit/offset para dentro: ele REEXECUTA a funcao inteira e fatia o
-- resultado — cada pagina paga o custo total. obter_cancelados_
-- classificados custa ~2,6 s e ~14 GB de trafego logico de buffers POR
-- execucao (pg_stat_statements): um mes com >1000 cancelados paga isso
-- N vezes.
--
-- Correcao: wrappers *_json que agregam o resultado da funcao original
-- em um JSON unico. Uma execucao por chamada; o PostgREST devolve uma
-- linha so (sem Content-Range — paginacao deixa de existir). Payload
-- unico maior e aceitavel: resultsets de poucos milhares de linhas.
--
-- Decisoes:
--   * Wrappers ADITIVOS (funcoes novas), nao CREATE OR REPLACE das
--     originais: mudar o tipo de retorno exigiria DROP (quebra atomica
--     de contrato entre migration e deploy do app) e as originais
--     continuam uteis para debug no SQL Editor.
--   * COALESCE('[]') — json_agg de zero linhas devolve NULL; sem o
--     COALESCE, resp.data viraria None no cliente em mes vazio.
--   * O SET statement_timeout='15000' da 052 continua valendo: e
--     function-level e se aplica durante a chamada interna.
--   * Se a RPC nova der 404 logo apos criar (schema cache do
--     PostgREST), rodar: NOTIFY pgrst, 'reload schema';
--
-- Executar no Supabase SQL Editor ANTES de deployar o app que consome
-- as *_json (loaders.py). Requer 046/048/052 aplicadas.
-- =====================================================

CREATE OR REPLACE FUNCTION obter_contratos_em_analise_json(
    p_mes INTEGER,
    p_ano INTEGER
)
RETURNS JSON
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
    SELECT COALESCE(json_agg(t), '[]'::json)
    FROM public.obter_contratos_em_analise(p_mes, p_ano) t;
$$;

CREATE OR REPLACE FUNCTION obter_digitacao_diaria_detalhe_json(
    p_mes INTEGER,
    p_ano INTEGER,
    p_dias_recentes INTEGER DEFAULT NULL
)
RETURNS JSON
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
    SELECT COALESCE(json_agg(t), '[]'::json)
    FROM public.obter_digitacao_diaria_detalhe(
        p_mes, p_ano, p_dias_recentes
    ) t;
$$;

CREATE OR REPLACE FUNCTION obter_cancelados_classificados_json(
    p_mes INTEGER,
    p_ano INTEGER
)
RETURNS JSON
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
    SELECT COALESCE(json_agg(t), '[]'::json)
    FROM public.obter_cancelados_classificados(p_mes, p_ano) t;
$$;

-- Acesso de execucao para os papeis do app (mesmo padrao da 052).
GRANT EXECUTE ON FUNCTION obter_contratos_em_analise_json(INTEGER, INTEGER)
    TO anon, authenticated;
GRANT EXECUTE ON FUNCTION
    obter_digitacao_diaria_detalhe_json(INTEGER, INTEGER, INTEGER)
    TO anon, authenticated;
GRANT EXECUTE ON FUNCTION
    obter_cancelados_classificados_json(INTEGER, INTEGER)
    TO anon, authenticated;


-- ===========================================
-- Verificacao (paridade com as originais):
--
--   SELECT json_array_length(obter_contratos_em_analise_json(7, 2026));
--   SELECT count(*) FROM obter_contratos_em_analise(7, 2026);
--   -- devem ser iguais (idem para as outras duas)
--
--   SELECT json_array_length(obter_cancelados_classificados_json(7, 2026));
--   SELECT count(*) FROM obter_cancelados_classificados(7, 2026);
--
-- Pos-deploy (48h), atribuicao por query:
--
--   SELECT LEFT(query, 90), calls, ROUND(mean_exec_time::numeric, 1)
--   FROM extensions.pg_stat_statements
--   WHERE query ILIKE '%cancelados%' ORDER BY calls DESC;
--   -- esperado: 1 execucao por cache-miss (nao mais N paginas)
--
-- Reversao:
--   DROP FUNCTION IF EXISTS obter_contratos_em_analise_json(INTEGER, INTEGER);
--   DROP FUNCTION IF EXISTS
--       obter_digitacao_diaria_detalhe_json(INTEGER, INTEGER, INTEGER);
--   DROP FUNCTION IF EXISTS
--       obter_cancelados_classificados_json(INTEGER, INTEGER);
-- ===========================================
