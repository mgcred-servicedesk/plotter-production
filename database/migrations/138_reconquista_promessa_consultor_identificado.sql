-- =====================================================
-- Migracao 138: Promessa Diaria — consultor_identificado na view
--
-- Altera:
--   - v_reconquista_promessa  (+ coluna consultor_identificado, no fim)
--
-- MOTIVACAO (decisao do usuario em 2026-10-16)
-- Promessa cujo consultor NAO e identificado no cadastro vai para o
-- SUPERVISOR vigente da loja (cadastro, na competencia) atuar: na
-- quebra por consultor ela aparece numa linha do supervisor, so com
-- esses leads — unica excecao a regra "supervisor fora das visoes por
-- pessoa". O lead continua pertencendo a loja do arquivo.
--
-- "Nao identificado" = a RPC (137) nao resolveu consultor_id: o nome do
-- arquivo nao casa (ILIKE, nome completo) com nenhum consultor da loja
-- da promessa (ou sem loja). A view de hoje NAO permite distinguir: a
-- coluna `consultor` faz COALESCE(con.nome, rp.consultor_nome), entao o
-- nome do arquivo aparece igual nos dois casos. Esta migration expoe o
-- fato como booleano; o consumidor nao precisa (nem deve) ver o id.
--
-- A resolucao e congelada no import: corrigir o cadastro de consultores
-- so muda a promessa depois de reimportar o periodo.
--
-- Coluna NOVA NO FIM da lista: CREATE OR REPLACE VIEW aceita adicionar
-- colunas ao final sem DROP (as demais mantem nome, tipo e ordem da
-- 137). security_invoker e o deny da tabela continuam valendo.
--
-- Depende de: 137_reconquista_promessa.sql.
-- Executar no Supabase SQL Editor.
-- =====================================================

CREATE OR REPLACE VIEW public.v_reconquista_promessa
    WITH (security_invoker = on)
AS
SELECT
    rp.co_adesao,
    p.ano                                                     AS ano,
    p.mes                                                     AS mes,
    rp.dt_promessa,
    rp.dt_retorno,
    rp.retorno_inss,
    rp.flag_elegibilidade,
    rp.elegivel,
    rp.status_mes_anterior,
    rp.status_cliente_atual,
    COALESCE(l.nome, rp.no_franquia, '(Nao Identificado)')    AS loja,
    reg.nome                                                  AS regiao,
    COALESCE(con.nome, rp.consultor_nome, '(Sem Consultor)')  AS consultor,
    rp.supervisor_nome                                        AS supervisor,
    rp.no_franquia,
    rp.cod_bmg,
    rp.consultor_nome,
    (rp.consultor_id IS NOT NULL)                             AS consultor_identificado
FROM public.reconquista_promessa rp
JOIN public.periodos p           ON p.id   = rp.periodo_id
LEFT JOIN public.lojas l         ON l.id   = rp.loja_id
LEFT JOIN public.regioes reg     ON reg.id = l.regiao_id
LEFT JOIN public.consultores con ON con.id = rp.consultor_id;

COMMENT ON VIEW public.v_reconquista_promessa IS
    'Promessa Diaria com loja/regiao/consultor rotulados e ano/mes do '
    'periodo. Fonte do card Promessas V3 (count elegivel, >= 09/2026) e '
    'do analitico "Promessa Diaria". consultor_identificado = false: o '
    'consultor do arquivo nao foi resolvido no cadastro (migration 138) '
    '— o lead vai para o supervisor vigente da loja na quebra por '
    'consultor.';

NOTIFY pgrst, 'reload schema';


-- =====================================================
-- VALIDACAO — rodar apos aplicar
--
-- 1) Coluna presente e no fim (esperado: ultima linha
--    consultor_identificado / boolean):
--
--    SELECT column_name, data_type
--    FROM information_schema.columns
--    WHERE table_schema = 'public' AND table_name = 'v_reconquista_promessa'
--    ORDER BY ordinal_position;
--
-- 2) Apos importar 09 e 10/2026 (esperado: 09 -> 3 false; 10 -> 1 false,
--    enquanto o cadastro da ERICA nao for corrigido e o mes reimportado):
--
--    SELECT ano, mes, consultor_identificado, count(*)
--    FROM public.v_reconquista_promessa
--    WHERE ano = 2026 AND mes IN (9, 10)
--    GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;
-- =====================================================
