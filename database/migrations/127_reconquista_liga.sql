-- =====================================================
-- Migracao 127: Reconquista — apuracao oficial da LIGA
--
-- Adiciona:
--   - reconquista_liga                      (tabela, por periodo)
--   - v_reconquista_liga                    (view de leitura)
--   - fn_importar_reconquista_liga()        (RPC de import)
--
-- MOTIVACAO (decisao do usuario em 2026-10-02)
-- A partir da apuracao de 09/2026 o indicador de Reconquista deixa de
-- sair do export `reconquista_YYYYMM.xlsx` (status EFETIVADA, com
-- defasagem de 1 mes por dt_fim_relacionamento) e passa a ser a
-- contagem que o BANCO contabiliza — o arquivo da "liga"
-- (`Reconquista_<Mes>_Liga.xlsx`): uma linha por proposta (Adesao) com
-- `Qtde Reconquista Relacionamento` 1 (contabilizada) ou 0 (nao).
--
-- O export antigo segue sendo importado (028/029/053), mas vira SO
-- analitico. Os dois nao se cruzam em nenhum KPI: no arquivo de
-- 09/2026, 36 das 118 propostas contabilizadas nem existem no export,
-- e as 82 que existem tem dt_fim espalhado de 03 a 08/2026 — a liga
-- conta pelo mes da reconquista (macica), nao pelo fim de
-- relacionamento.
--
-- POR PERIODO, NAO TRUNCATE
-- Ao contrario da `reconquista` (foto unica, truncada a cada carga),
-- cada arquivo da liga e a apuracao de UM mes, escolhido no importador
-- (angry-man, card com periodo obrigatorio — mesmo fluxo de Metas e
-- Pontuacao). Reimportar um mes substitui so aquele mes; os anteriores
-- ficam. Vigencia por `periodo_id`, mesmo padrao de `pontuacao` (013) e
-- `faixas_acelerador_reconquista` (066).
--
-- LINHAS COM QTDE 0 SAO GUARDADAS
-- Decisao do usuario: o analitico "Liga" lista as duas, com filtro em
-- "contabilizada". A conta usa so `qtde = 1`. Por isso `qtde` e coluna,
-- nao filtro de import.
--
-- ATRIBUICAO (loja/consultor) VEM DO PROPRIO ARQUIVO DA LIGA
-- Nao do export: ha propostas que so existem na liga, e quando as duas
-- fontes divergem o premio segue quem o banco contabilizou. Resolucao
-- identica a de fn_importar_reconquista (053): loja por cod_bmg (prefixo
-- de `Franquia`) com sucessora aplicada; consultor por nome completo +
-- loja. O texto original fica guardado (no_franquia/consultor_nome) e a
-- view cai nele quando a FK nao resolve.
--
-- RLS — MESMO TRATAMENTO DA `reconquista` (093)
-- Carteira de cliente (co_adesao), nao estrutura organizacional: deny
-- explicito para anon/authenticated + REVOKE. Todo acesso e service_role
-- (BYPASSRLS); o recorte por perfil e client-side
-- (_filtro_rls_reconquista), que reaproveita as colunas texto
-- loja/regiao/consultor da view — por isso ela expoe os MESMOS nomes de
-- v_reconquista.
--
-- Depende de: periodos, lojas, regioes, consultores (schema base).
-- Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- 1. Tabela
-- ===========================================

CREATE TABLE IF NOT EXISTS public.reconquista_liga (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    periodo_id       UUID NOT NULL
                         REFERENCES public.periodos (id)
                         ON DELETE CASCADE,
    co_adesao        BIGINT  NOT NULL,
    qtde             INTEGER NOT NULL,
    data_reconquista DATE,

    -- Origem (texto bruto do arquivo + FK resolvida no import)
    no_franquia      TEXT,
    cod_bmg          INTEGER,
    loja_id          UUID REFERENCES public.lojas (id)       ON DELETE SET NULL,
    consultor_nome   TEXT,
    consultor_id     UUID REFERENCES public.consultores (id) ON DELETE SET NULL,

    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_reconquista_liga_periodo_adesao
        UNIQUE (periodo_id, co_adesao),
    CONSTRAINT chk_reconquista_liga_qtde
        CHECK (qtde IN (0, 1))
);

COMMENT ON TABLE public.reconquista_liga IS
    'Apuracao oficial da Reconquista contabilizada pelo banco (arquivo '
    '"liga"), uma linha por proposta por periodo. Fonte dos KPIs de '
    'Reconquista a partir de 09/2026: efetivadas = count(qtde = 1) do '
    'periodo selecionado, sem defasagem. Reimport substitui so o periodo '
    '(fn_importar_reconquista_liga). O export `reconquista` segue como '
    'analitico apenas.';

COMMENT ON COLUMN public.reconquista_liga.qtde IS
    '"Qtde Reconquista Relacionamento" do arquivo: 1 = contabilizada '
    'pelo banco (entra na conta), 0 = listada e nao contabilizada '
    '(fica so no analitico).';

COMMENT ON COLUMN public.reconquista_liga.data_reconquista IS
    '"Data Reconquista" do arquivo. No primeiro arquivo (09/2026) todas '
    'as linhas trazem a mesma data (16/09) — parece data de extracao, '
    'nao da reconquista de cada proposta. Informativa: o periodo da '
    'apuracao e `periodo_id`, escolhido no import.';

CREATE INDEX IF NOT EXISTS idx_reconquista_liga_periodo
    ON public.reconquista_liga (periodo_id);


-- ===========================================
-- 2. RLS — deny explicito (mesmo racional da 093)
-- ===========================================

ALTER TABLE public.reconquista_liga ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS pol_reconquista_liga_deny ON public.reconquista_liga;

CREATE POLICY pol_reconquista_liga_deny
    ON public.reconquista_liga
    FOR ALL
    TO anon, authenticated
    USING (false)
    WITH CHECK (false);

COMMENT ON POLICY pol_reconquista_liga_deny ON public.reconquista_liga IS
    'Deny explicito. Carteira de cliente (co_adesao) — mesmo tratamento '
    'de pol_reconquista_deny (093). Todo acesso e por service_role; o '
    'recorte por perfil e client-side (_filtro_rls_reconquista).';

REVOKE ALL ON public.reconquista_liga FROM anon, authenticated;


-- ===========================================
-- 3. View de leitura
--
-- Nomes de loja/regiao/consultor IGUAIS aos de v_reconquista: o
-- recorte client-side por perfil e o mesmo para as duas.
-- ===========================================

CREATE OR REPLACE VIEW public.v_reconquista_liga
    WITH (security_invoker = on)
AS
SELECT
    rl.co_adesao,
    p.ano                                                     AS ano,
    p.mes                                                     AS mes,
    rl.qtde,
    rl.data_reconquista,
    COALESCE(l.nome, rl.no_franquia, '(Nao Identificado)')    AS loja,
    reg.nome                                                  AS regiao,
    COALESCE(con.nome, rl.consultor_nome, '(Sem Consultor)')  AS consultor,
    rl.no_franquia,
    rl.consultor_nome
FROM public.reconquista_liga rl
JOIN public.periodos p          ON p.id   = rl.periodo_id
LEFT JOIN public.lojas l        ON l.id   = rl.loja_id
LEFT JOIN public.regioes reg    ON reg.id = l.regiao_id
LEFT JOIN public.consultores con ON con.id = rl.consultor_id;

COMMENT ON VIEW public.v_reconquista_liga IS
    'Liga (apuracao oficial do banco) com loja/regiao/consultor '
    'rotulados e ano/mes do periodo. Fonte dos KPIs de Reconquista a '
    'partir de 09/2026 (count qtde = 1) e do analitico "Liga".';


-- ===========================================
-- 4. RPC de import — substitui SO o periodo
--
-- DELETE do periodo + INSERT na mesma transacao: reimportar o mes e
-- idempotente e nao toca os demais. Payload: lista de
--   {co_adesao, qtde, data_reconquista, no_franquia, cod_bmg,
--    consultor_nome}
-- (o parse do xlsx — rodape "Total"/"Filtros aplicados" incluso — e do
-- importador; aqui so se resolve FK e grava).
--
-- Adesao repetida no mesmo arquivo: fica a primeira (ON CONFLICT DO
-- NOTHING), como em fn_importar_reconquista; `inseridos` < linhas
-- enviadas denuncia o caso no log do importador.
-- ===========================================

CREATE OR REPLACE FUNCTION public.fn_importar_reconquista_liga(
    p_periodo_id UUID,
    p_rows       JSONB
)
RETURNS TABLE (
    removidos     INTEGER,
    inseridos     INTEGER,
    contabilizadas INTEGER,
    sem_loja      INTEGER,
    sem_consultor INTEGER
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_removidos      INTEGER := 0;
    v_inseridos      INTEGER := 0;
    v_contabilizadas INTEGER := 0;
    v_sem_loja       INTEGER := 0;
    v_sem_consultor  INTEGER := 0;
    v_row            JSONB;
    v_loja_id        UUID;
    v_consultor_id   UUID;
    v_consultor_nm   TEXT;
    v_qtde           INTEGER;
    v_affected       INTEGER;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM public.periodos WHERE id = p_periodo_id) THEN
        RAISE EXCEPTION 'Periodo % inexistente.', p_periodo_id;
    END IF;

    DELETE FROM public.reconquista_liga WHERE periodo_id = p_periodo_id;
    GET DIAGNOSTICS v_removidos = ROW_COUNT;

    FOR v_row IN SELECT * FROM jsonb_array_elements(p_rows)
    LOOP
        -- Loja: cod_bmg ja com sucessora aplicada (mesmo criterio da 053)
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

        -- Consultor: nome completo + loja (mesmo criterio da 053)
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

        v_qtde := (v_row->>'qtde')::INTEGER;

        INSERT INTO public.reconquista_liga (
            periodo_id, co_adesao, qtde, data_reconquista,
            no_franquia, cod_bmg, loja_id,
            consultor_nome, consultor_id
        )
        VALUES (
            p_periodo_id,
            (v_row->>'co_adesao')::BIGINT,
            v_qtde,
            (v_row->>'data_reconquista')::DATE,
            NULLIF(TRIM(v_row->>'no_franquia'), ''),
            (v_row->>'cod_bmg')::INTEGER,
            v_loja_id,
            v_consultor_nm,
            v_consultor_id
        )
        ON CONFLICT (periodo_id, co_adesao) DO NOTHING;

        GET DIAGNOSTICS v_affected = ROW_COUNT;
        v_inseridos := v_inseridos + v_affected;
        IF v_affected > 0 AND v_qtde = 1 THEN
            v_contabilizadas := v_contabilizadas + 1;
        END IF;
    END LOOP;

    RETURN QUERY SELECT
        v_removidos, v_inseridos, v_contabilizadas,
        v_sem_loja, v_sem_consultor;
END;
$$;

COMMENT ON FUNCTION public.fn_importar_reconquista_liga(UUID, JSONB) IS
    'Liga da Reconquista: DELETE do periodo + carga em lote, na mesma '
    'transacao. Resolve loja_id (cod_bmg + sucessora) e consultor_id '
    '(nome completo + loja). Retorna (removidos, inseridos, '
    'contabilizadas, sem_loja, sem_consultor) para o log do importador.';

-- Mesmo fechamento da 058: so service_role (angry-man via Edge Function
-- reconquista-rpc no web, IPC service_role no Electron).
REVOKE EXECUTE ON FUNCTION public.fn_importar_reconquista_liga(UUID, JSONB)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_importar_reconquista_liga(UUID, JSONB)
    TO service_role;


-- =====================================================
-- VALIDACAO — rodar apos aplicar e importar a liga de 09/2026
--
-- 1) Contagem do arquivo (esperado: 176 linhas, 118 contabilizadas):
--
--    SELECT count(*) AS linhas, count(*) FILTER (WHERE qtde = 1) AS contab
--    FROM public.v_reconquista_liga WHERE ano = 2026 AND mes = 9;
--
-- 2) Atribuicao — quantas nao resolveram loja/consultor
--    (cai no texto original na view; idealmente 0 sem loja):
--
--    SELECT count(*) FILTER (WHERE loja_id IS NULL)      AS sem_loja,
--           count(*) FILTER (WHERE consultor_id IS NULL) AS sem_consultor
--    FROM public.reconquista_liga rl
--    JOIN public.periodos p ON p.id = rl.periodo_id
--    WHERE p.ano = 2026 AND p.mes = 9;
--
-- 3) Deny — sem grant residual para anon/authenticated (esperado: 0):
--
--    SELECT grantee, privilege_type
--    FROM information_schema.role_table_grants
--    WHERE table_name = 'reconquista_liga'
--      AND grantee IN ('anon', 'authenticated');
-- =====================================================
