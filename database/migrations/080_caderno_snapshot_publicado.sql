-- =====================================================
-- Migracao 080: Caderno materializado (meses fechados)
--
-- Problema: `obter_caderno_fechamento` leva ~4s morna e ESTOURA o
-- statement_timeout na chamada fria. O bereshit (consumidor do Caderno)
-- ja convive com isso — tem retry com backoff para o codigo 57014 em
-- src/data/report.ts. Medindo por competencia o tempo e praticamente
-- PLANO (4,3s jan / 3,6s jun / 4,3s ago em 2026-08-18), ou seja, custo
-- fixo: nao adianta reduzir a janela da serie.
--
-- Decisao do usuario (2026-08-18): o Caderno serve **somente meses
-- fechados**; o mes vigente ganha projecao, registrada como feature no
-- bereshit (docs/PLANO_EVOLUCAO_UI_UX.md, Fase 7). Isso torna a
-- materializacao a saida natural: relatorio de fechamento de mes fechado
-- nao muda a cada leitura — calcula uma vez, guarda o JSONB, serve de
-- tabela.
--
-- Por que isso cabe no Nano SEM subir de plano: `statement_timeout` e
-- configuravel POR FUNCAO (clausula SET, mesmo mecanismo que a 054 usou
-- para work_mem no authenticator). A funcao de materializacao roda com
-- folga; a de leitura e um SELECT por chave primaria, na casa do
-- milissegundo. O custo de 4s sai do caminho do usuario e passa a
-- acontecer uma vez por competencia.
--
-- O que NAO muda: `obter_caderno_fechamento` continua existindo e sendo
-- a unica fonte do calculo — esta migration nao duplica regra de
-- negocio, so guarda o resultado dela.
--
-- ATENCAO: o snapshot congela o payload no momento da geracao. Correcao
-- retroativa no ledger de supervisores (ou qualquer migration que mude
-- o calculo) exige RE-materializar as competencias afetadas, senao o
-- Caderno publicado fica defasado. Ver secao 5.
--
-- Executar no Supabase SQL Editor, depois da 079.
-- =====================================================


-- ===========================================
-- 1. Tabela de snapshots
-- ===========================================

CREATE TABLE IF NOT EXISTS caderno_fechamento_snapshot (
    ano        SMALLINT NOT NULL,
    mes        SMALLINT NOT NULL,
    payload    JSONB NOT NULL,
    gerado_em  TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (ano, mes),
    CONSTRAINT chk_cfs_mes CHECK (mes BETWEEN 1 AND 12),
    CONSTRAINT chk_cfs_ano CHECK (ano BETWEEN 2020 AND 2100)
);

COMMENT ON TABLE caderno_fechamento_snapshot IS
    'Caderno de Fechamento materializado por competencia FECHADA. '
    'payload = saida integral de obter_caderno_fechamento(mes, ano) no '
    'momento da geracao. Existe para tirar os ~4s do calculo do caminho '
    'de leitura (statement_timeout do Nano). Nao contem regra de negocio: '
    'e cache de resultado, e a fonte segue sendo a RPC.';

COMMENT ON COLUMN caderno_fechamento_snapshot.gerado_em IS
    'Quando o payload foi calculado. O bereshit pode exibir como "ultima '
    'atualizacao" — item ja previsto no plano de UI/UX daquele projeto.';


-- ===========================================
-- 2. Materializacao (escrita)
--
-- statement_timeout elevado NA FUNCAO: e o que permite o calculo de ~4s
-- (ou mais, em competencia pesada) rodar sem esbarrar no limite que
-- derruba a chamada direta via PostgREST.
--
-- Guarda: so competencia FECHADA. Mes vigente e futuro sao recusados
-- com mensagem — o bereshit cobre o mes corrente com projecao.
-- ===========================================

CREATE OR REPLACE FUNCTION public.fn_materializar_caderno(
    p_mes integer,
    p_ano integer
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET statement_timeout = '180s'
AS $$
DECLARE
    v_payload      jsonb;
    v_competencia  date;
    v_mes_corrente date := date_trunc('month', current_date)::date;
BEGIN
    IF p_mes IS NULL OR p_mes NOT BETWEEN 1 AND 12
       OR p_ano IS NULL OR p_ano NOT BETWEEN 2020 AND 2100 THEN
        RETURN jsonb_build_object(
            'error', format('Competencia invalida: %s/%s', p_mes, p_ano));
    END IF;

    v_competencia := make_date(p_ano, p_mes, 1);

    IF v_competencia >= v_mes_corrente THEN
        RETURN jsonb_build_object(
            'error', format(
                'Competencia %s/%s ainda nao fechou — o Caderno so '
                'materializa mes fechado (o mes vigente e coberto por '
                'projecao no bereshit).', p_mes, p_ano));
    END IF;

    SELECT public.obter_caderno_fechamento(p_mes, p_ano) INTO v_payload;

    -- Competencia sem linha em `periodos`: a RPC devolve NULL (o SELECT
    -- final faz FROM periodo). Materializar NULL publicaria um Caderno
    -- vazio como se fosse valido.
    IF v_payload IS NULL THEN
        RETURN jsonb_build_object(
            'error', format(
                'Sem periodo cadastrado para %s/%s — nada a materializar.',
                p_mes, p_ano));
    END IF;

    INSERT INTO caderno_fechamento_snapshot (ano, mes, payload)
    VALUES (p_ano, p_mes, v_payload)
    ON CONFLICT (ano, mes) DO UPDATE
        SET payload = EXCLUDED.payload,
            gerado_em = now();

    RETURN jsonb_build_object(
        'mes', p_mes,
        'ano', p_ano,
        'bytes', pg_column_size(v_payload),
        'gerado_em', now(),
        'error', NULL
    );
END;
$$;

COMMENT ON FUNCTION public.fn_materializar_caderno(integer, integer) IS
    'Calcula obter_caderno_fechamento(mes, ano) e guarda em '
    'caderno_fechamento_snapshot (upsert). So competencia FECHADA. '
    'statement_timeout de 180s na propria funcao — e por isso que o '
    'calculo de ~4s cabe aqui e nao no caminho de leitura. Escrita: '
    'EXECUTE so para service_role.';

REVOKE ALL ON FUNCTION public.fn_materializar_caderno(integer, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.fn_materializar_caderno(integer, integer) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_materializar_caderno(integer, integer) TO service_role;


-- ===========================================
-- 3. Leitura (o que o bereshit passa a chamar)
--
-- SELECT por chave primaria: milissegundos, sem risco de timeout. Devolve
-- NULL quando a competencia nao foi publicada — deliberadamente NAO cai
-- de volta no calculo, senao o timeout voltaria de forma imprevisivel.
-- Competencia nao publicada e um estado que o consumidor deve mostrar,
-- nao um erro para reprocessar.
--
-- Mesmos grants de obter_caderno_fechamento (075): a exposicao nao muda.
-- ===========================================

CREATE OR REPLACE FUNCTION public.obter_caderno_publicado(
    p_mes integer,
    p_ano integer
)
RETURNS jsonb
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
    SELECT s.payload
    FROM public.caderno_fechamento_snapshot s
    WHERE s.ano = p_ano AND s.mes = p_mes;
$$;

COMMENT ON FUNCTION public.obter_caderno_publicado(integer, integer) IS
    'Devolve o Caderno JA materializado da competencia (leitura por PK, '
    'milissegundos). NULL = competencia nao publicada; nao recalcula de '
    'proposito. Substitui obter_caderno_fechamento no caminho de leitura '
    'do bereshit, que assim deixa de depender do retry de 57014.';

REVOKE ALL ON FUNCTION public.obter_caderno_publicado(integer, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.obter_caderno_publicado(integer, integer)
    TO anon, authenticated, service_role;


-- ===========================================
-- 4. RLS: mesma exposicao do calculo que ela guarda
-- ===========================================

ALTER TABLE caderno_fechamento_snapshot ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS pol_cfs_leitura ON caderno_fechamento_snapshot;
CREATE POLICY pol_cfs_leitura
    ON caderno_fechamento_snapshot FOR SELECT USING (true);

GRANT SELECT ON caderno_fechamento_snapshot TO anon, authenticated;


-- ===========================================
-- 5. Backfill: materializa toda competencia FECHADA
--
-- Roda no SQL Editor (role owner), onde o timeout nao aperta. Sao ~4s
-- por competencia; com 14 fechadas em 2026-08-18, espere ~1min.
--
-- Idempotente: reexecutar re-materializa (upsert) — e e exatamente isso
-- que se deve fazer depois de QUALQUER correcao retroativa (ledger de
-- supervisores, migration que mude o calculo). O snapshot congela o
-- resultado; sem re-materializar, o Caderno publicado fica defasado.
-- ===========================================

SELECT p.mes, p.ano, public.fn_materializar_caderno(p.mes, p.ano) AS resultado
FROM public.periodos p
WHERE make_date(p.ano, p.mes, 1) < date_trunc('month', current_date)::date
ORDER BY p.ano, p.mes;


-- ===========================================
-- Validacao pos-migracao
-- ===========================================
-- 1) Toda competencia fechada publicada, e nenhuma vazia:
--
--    SELECT ano, mes, gerado_em, pg_column_size(payload) AS bytes
--    FROM caderno_fechamento_snapshot ORDER BY ano, mes;
--    -- Esperado: 1 linha por periodo fechado, bytes > 0.
--
-- 2) O payload publicado bate com o calculado na hora:
--
--    SELECT obter_caderno_publicado(6, 2026)
--         = obter_caderno_fechamento(6, 2026) AS identico;
--    -- Esperado: true.
--
-- 3) Leitura instantanea (o ponto da migration):
--
--    EXPLAIN ANALYZE SELECT obter_caderno_publicado(6, 2026);
--    -- Esperado: Index Scan / execution time na casa de 1ms.
--
-- 4) Guarda do mes vigente:
--
--    SELECT fn_materializar_caderno(
--        EXTRACT(MONTH FROM current_date)::int,
--        EXTRACT(YEAR FROM current_date)::int);
--    -- Esperado: { "error": "Competencia ... ainda nao fechou ..." }
-- =====================================================
