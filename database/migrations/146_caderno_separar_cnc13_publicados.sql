-- =====================================================
-- Migracao 146: separa o CNC 13o nos Cadernos ja publicados
-- Data: 2026-10-29
-- Depende de: 145 (CNC_13 em grupo proprio em obter_caderno_fechamento)
--
-- PROBLEMA
-- A 145 so vale para o que for publicado depois dela. Os 17 Cadernos
-- publicados (05/2025 a 09/2026) seguem congelados com o CNC 13o somado
-- ao CNC, e o negocio nao quer ler os dois juntos (decisao do usuario,
-- 2026-10-29). O 13o teve producao em 05/2025 (R$ 46.330), 02/2026
-- (R$ 176.696), 03/2026 (R$ 1.268.033, 24,1% do CNC) e 04/2026
-- (R$ 445.128).
--
-- POR QUE NAO REPUBLICAR
-- fn_materializar_caderno recalcula o Caderno inteiro: alem de separar o
-- 13o, moveria a produtividade por loja congelada (correcoes de vigencia
-- 109-129) e a producao valida de lojas cuja tabela mudou de modalidade
-- depois da publicacao (06, 07 e 09/2026). E recusaria 03 e 04/2026, que
-- ainda tem pagamentos sem vinculo de origem (10 e 16). A republicacao
-- continua sendo a Fase 8 do Bereshit, com decisao propria.
--
-- O QUE FAZ
-- fn_separar_cnc13_snapshot(mes, ano) troca SO o grupo CNC de mix e
-- productRanking pelo CNC e CNC_13 do calculo atual, e apenas depois de
-- provar que os dois somados dao exatamente o CNC publicado — no total do
-- MIX e loja a loja, em pago, producao valida, pontos e gerente. Se nao
-- der, recusa o mes (RAISE) e nada muda nele. Todo o resto do payload —
-- summary, ranking, monthlyPoints, productivity, os demais grupos do MIX e
-- os demais rankings por produto — fica exatamente como publicado.
-- gerado_em tambem fica: os numeros continuam sendo os daquela publicacao.
--
-- O payload recebe contractVersion = 'v1.10' (a forma da 145) e
-- mixRevision, que registra que so o MIX foi revisado, quando e por qual
-- migration. O snapshot nominal (produtividade_individual_snapshot) nao
-- tem MIX e nao e tocado.
--
-- Antes de trocar, o payload anterior vai para
-- caderno_fechamento_snapshot_revisao: e o primeiro registro de revisao do
-- Caderno, que o contrato funcional pedia e nao existia
-- (fn_materializar_caderno segue sobrescrevendo sem arquivar).
--
-- CONFERIDO EM 2026-10-29 (consulta so leitura contra o calculo atual)
--   Nos 17 meses, CNC + CNC_13 atuais = CNC publicado no MIX e em todas as
--   lojas do productRanking (pago, producao valida, pontos e gerente). Os
--   demais grupos do MIX tambem batem. As unicas diferencas do
--   productRanking estao em CONSIGNADO (producao valida de 1, 2 e 11 lojas
--   em 06, 07 e 09/2026) — e esta migration nao toca nelas.
--
-- ORDEM (obrigatoria)
--   1. Bereshit com suporte a CNC_13 publicado em producao (commit
--      5d4ed88 em diante). O parser anterior descarta o grupo desconhecido:
--      sem o deploy, os meses separados perdem a linha do 13o e 05/2025 e
--      02-04/2026 somem da serie do MIX.
--   2. Esta migration. Cada chamada recalcula a competencia (~5-7 s); sao
--      17, uma por instrucao.
--
-- Reversao: ver o fim do arquivo.
--
-- Executar no Supabase SQL Editor, DEPOIS do deploy do Bereshit.
-- =====================================================

-- ===========================================
-- 1. Revisoes arquivadas do Caderno
-- ===========================================

CREATE TABLE IF NOT EXISTS public.caderno_fechamento_snapshot_revisao (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ano          SMALLINT    NOT NULL,
    mes          SMALLINT    NOT NULL,
    -- payload e gerado_em como estavam ANTES da revisao.
    payload      JSONB       NOT NULL,
    gerado_em    TIMESTAMPTZ,
    arquivado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    motivo       TEXT        NOT NULL CHECK (btrim(motivo) <> '')
);

CREATE INDEX IF NOT EXISTS idx_cfsr_competencia
    ON public.caderno_fechamento_snapshot_revisao (ano, mes, arquivado_em);

COMMENT ON TABLE public.caderno_fechamento_snapshot_revisao IS
    'Payloads de caderno_fechamento_snapshot substituidos por revisao '
    'deliberada (146 em diante). Uma linha por revisao, com o payload e o '
    'gerado_em de antes. Sem leitura publica: RLS sem policy.';

ALTER TABLE public.caderno_fechamento_snapshot_revisao ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.caderno_fechamento_snapshot_revisao FROM anon, authenticated;

-- ===========================================
-- 2. Separacao do CNC 13o num snapshot
-- ===========================================

CREATE OR REPLACE FUNCTION public.fn_separar_cnc13_snapshot(
    p_mes integer,
    p_ano integer
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path = ''
SET statement_timeout = '180s'
AS $$
DECLARE
    v_competencia text := lpad(p_mes::text, 2, '0') || '/' || p_ano;
    v_publicado   jsonb;
    v_gerado_em   timestamptz;
    v_vivo        jsonb;
    v_total       numeric;
    v_cnc_pub     numeric;
    v_cnc_vivo    numeric;
    v_cnc13_vivo  numeric;
    v_lojas       integer;
    v_mix         jsonb;
    v_ranking     jsonb;
BEGIN
    SELECT s.payload, s.gerado_em
      INTO v_publicado, v_gerado_em
      FROM public.caderno_fechamento_snapshot s
     WHERE s.ano = p_ano AND s.mes = p_mes
       FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Caderno % nao publicado.', v_competencia;
    END IF;
    -- Idempotente: publicado ja na 145 ou ja separado aqui.
    IF v_publicado ? 'contractVersion' THEN
        RETURN jsonb_build_object(
            'competencia', v_competencia,
            'status', 'JA_SEPARADO',
            'contractVersion', v_publicado ->> 'contractVersion');
    END IF;

    v_vivo := public.obter_caderno_fechamento(p_mes, p_ano);

    SELECT coalesce(sum((x ->> 'paidEffective')::numeric), 0),
           coalesce(sum((x ->> 'paidEffective')::numeric)
                    FILTER (WHERE x ->> 'product' = 'CNC'), 0)
      INTO v_total, v_cnc_pub
      FROM jsonb_array_elements(v_publicado -> 'mix') x;

    SELECT coalesce(sum((x ->> 'paidEffective')::numeric)
                    FILTER (WHERE x ->> 'product' = 'CNC'), 0),
           coalesce(sum((x ->> 'paidEffective')::numeric)
                    FILTER (WHERE x ->> 'product' = 'CNC_13'), 0)
      INTO v_cnc_vivo, v_cnc13_vivo
      FROM jsonb_array_elements(v_vivo -> 'mix') x;

    IF abs(v_cnc_pub - (v_cnc_vivo + v_cnc13_vivo)) > 0.01 THEN
        RAISE EXCEPTION
            'Caderno %: CNC publicado (%) difere de CNC + CNC 13o atuais (% + %). '
            'Separar moveria outros numeros; a competencia precisa ser republicada.',
            v_competencia, v_cnc_pub, v_cnc_vivo, v_cnc13_vivo;
    END IF;

    -- Loja a loja: o CNC publicado tem de ser o CNC + CNC 13o de agora, nos
    -- tres valores e no gerente historico.
    SELECT count(*)
      INTO v_lojas
      FROM (
            SELECT x ->> 'store'   AS loja,
                   x ->> 'manager' AS gerente,
                   (x ->> 'paidEffective')::numeric   AS pago,
                   (x ->> 'validProduction')::numeric AS valido,
                   (x ->> 'effectivePoints')::numeric AS pontos
              FROM jsonb_array_elements(v_publicado -> 'productRanking') x
             WHERE x ->> 'product' = 'CNC'
           ) pub
      FULL JOIN (
            SELECT x ->> 'store'        AS loja,
                   max(x ->> 'manager') AS gerente,
                   sum((x ->> 'paidEffective')::numeric)   AS pago,
                   sum((x ->> 'validProduction')::numeric) AS valido,
                   sum((x ->> 'effectivePoints')::numeric) AS pontos
              FROM jsonb_array_elements(v_vivo -> 'productRanking') x
             WHERE x ->> 'product' IN ('CNC', 'CNC_13')
             GROUP BY x ->> 'store'
           ) vivo USING (loja)
     WHERE abs(coalesce(pub.pago, 0)   - coalesce(vivo.pago, 0))   > 0.01
        OR abs(coalesce(pub.valido, 0) - coalesce(vivo.valido, 0)) > 0.01
        OR abs(coalesce(pub.pontos, 0) - coalesce(vivo.pontos, 0)) > 0.01
        OR pub.gerente IS DISTINCT FROM vivo.gerente;
    IF v_lojas > 0 THEN
        RAISE EXCEPTION
            'Caderno %: % loja(s) com CNC publicado diferente de CNC + CNC 13o atuais. '
            'Separar moveria outros numeros; a competencia precisa ser republicada.',
            v_competencia, v_lojas;
    END IF;

    -- MIX: demais grupos como publicados; CNC e CNC_13 do calculo atual,
    -- com a participacao sobre o total PUBLICADO (que nao muda).
    SELECT coalesce(jsonb_agg(t.linha ORDER BY (t.linha ->> 'paidEffective')::numeric DESC), '[]'::jsonb)
      INTO v_mix
      FROM (
            SELECT x AS linha
              FROM jsonb_array_elements(v_publicado -> 'mix') x
             WHERE x ->> 'product' <> 'CNC'
            UNION ALL
            SELECT jsonb_build_object(
                       'product', x ->> 'product',
                       'paidEffective', (x ->> 'paidEffective')::numeric,
                       'share', CASE WHEN v_total > 0
                                     THEN (x ->> 'paidEffective')::numeric / v_total
                                     ELSE 0 END)
              FROM jsonb_array_elements(v_vivo -> 'mix') x
             WHERE x ->> 'product' IN ('CNC', 'CNC_13')
           ) t;

    -- Ranking por produto: demais produtos como publicados; CNC e CNC_13
    -- do calculo atual, que a conferencia acima provou somar o publicado.
    SELECT coalesce(jsonb_agg(t.linha ORDER BY t.linha ->> 'product', (t.linha ->> 'position')::integer), '[]'::jsonb)
      INTO v_ranking
      FROM (
            SELECT x AS linha
              FROM jsonb_array_elements(v_publicado -> 'productRanking') x
             WHERE x ->> 'product' <> 'CNC'
            UNION ALL
            SELECT x
              FROM jsonb_array_elements(v_vivo -> 'productRanking') x
             WHERE x ->> 'product' IN ('CNC', 'CNC_13')
           ) t;

    INSERT INTO public.caderno_fechamento_snapshot_revisao
        (ano, mes, payload, gerado_em, motivo)
    VALUES
        (p_ano, p_mes, v_publicado, v_gerado_em,
         'Migration 146: CNC 13o separado do CNC no mix e no productRanking');

    UPDATE public.caderno_fechamento_snapshot s
       SET payload = v_publicado || jsonb_build_object(
               'contractVersion', 'v1.10',
               'mix', v_mix,
               'productRanking', v_ranking,
               'mixRevision', jsonb_build_object(
                   'migration', 146,
                   'revisedAt', now(),
                   'change', 'CNC_13 separado do CNC em mix e productRanking; '
                             'demais numeros preservados como publicados'))
     WHERE s.ano = p_ano AND s.mes = p_mes;

    RETURN jsonb_build_object(
        'competencia', v_competencia,
        'status', 'SEPARADO',
        'cnc', v_cnc_vivo,
        'cnc13', v_cnc13_vivo);
END;
$$;

COMMENT ON FUNCTION public.fn_separar_cnc13_snapshot(integer, integer) IS
    'Separa o CNC 13o do CNC em mix e productRanking de um Caderno publicado '
    'antes da 145, sem mover nenhum outro numero: so troca se CNC + CNC_13 '
    'atuais = CNC publicado no total e loja a loja. Arquiva o payload anterior '
    'em caderno_fechamento_snapshot_revisao. Idempotente.';

REVOKE ALL ON FUNCTION public.fn_separar_cnc13_snapshot(integer, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.fn_separar_cnc13_snapshot(integer, integer) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_separar_cnc13_snapshot(integer, integer) TO service_role;

-- ===========================================
-- 3. Os 17 Cadernos publicados — um por instrucao
-- ===========================================
-- Os quatro com producao de 13o primeiro; os demais nao mudam de valor,
-- so passam a declarar a composicao separada (CNC 13o = 0).

SELECT public.fn_separar_cnc13_snapshot(3, 2026);
SELECT public.fn_separar_cnc13_snapshot(4, 2026);
SELECT public.fn_separar_cnc13_snapshot(2, 2026);
SELECT public.fn_separar_cnc13_snapshot(5, 2025);
SELECT public.fn_separar_cnc13_snapshot(6, 2025);
SELECT public.fn_separar_cnc13_snapshot(7, 2025);
SELECT public.fn_separar_cnc13_snapshot(8, 2025);
SELECT public.fn_separar_cnc13_snapshot(9, 2025);
SELECT public.fn_separar_cnc13_snapshot(10, 2025);
SELECT public.fn_separar_cnc13_snapshot(11, 2025);
SELECT public.fn_separar_cnc13_snapshot(12, 2025);
SELECT public.fn_separar_cnc13_snapshot(1, 2026);
SELECT public.fn_separar_cnc13_snapshot(5, 2026);
SELECT public.fn_separar_cnc13_snapshot(6, 2026);
SELECT public.fn_separar_cnc13_snapshot(7, 2026);
SELECT public.fn_separar_cnc13_snapshot(8, 2026);
SELECT public.fn_separar_cnc13_snapshot(9, 2026);


-- ===========================================
-- Verificacao — rodar DEPOIS
-- ===========================================
--
-- 1) Todos separados:
--
--    SELECT ano, mes, payload ->> 'contractVersion' AS versao
--      FROM public.caderno_fechamento_snapshot ORDER BY ano, mes;
--    -- Esperado: v1.10 em todas as linhas.
--
-- 2) CNC + CNC_13 de agora = CNC arquivado, mes a mes:
--
--    SELECT s.ano, s.mes,
--           (SELECT sum((x ->> 'paidEffective')::numeric)
--              FROM jsonb_array_elements(s.payload -> 'mix') x
--             WHERE x ->> 'product' IN ('CNC', 'CNC_13'))      AS agora,
--           (SELECT (x ->> 'paidEffective')::numeric
--              FROM jsonb_array_elements(r.payload -> 'mix') x
--             WHERE x ->> 'product' = 'CNC')                     AS antes
--      FROM public.caderno_fechamento_snapshot s
--      JOIN public.caderno_fechamento_snapshot_revisao r USING (ano, mes)
--     ORDER BY 1, 2;
--    -- Esperado: agora = antes nas 17 linhas.
--
-- 3) Nada fora do MIX se moveu:
--
--    SELECT s.ano, s.mes,
--           md5((s.payload - 'mix' - 'productRanking' - 'contractVersion' - 'mixRevision')::text)
--         = md5((r.payload - 'mix' - 'productRanking')::text) AS resto_intacto
--      FROM public.caderno_fechamento_snapshot s
--      JOIN public.caderno_fechamento_snapshot_revisao r USING (ano, mes)
--     ORDER BY 1, 2;
--    -- Esperado: t nas 17 linhas.
--
-- ===========================================
-- Reversao (se precisar)
-- ===========================================
--
--    UPDATE public.caderno_fechamento_snapshot s
--       SET payload = r.payload
--      FROM public.caderno_fechamento_snapshot_revisao r
--     WHERE r.ano = s.ano AND r.mes = s.mes
--       AND r.motivo LIKE 'Migration 146:%';
