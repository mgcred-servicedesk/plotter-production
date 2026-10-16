-- =====================================================
-- Migracao 137: Reconquista V3 — Promessa Diaria
--
-- Adiciona:
--   - reconquista_promessa                  (tabela, por periodo)
--   - v_reconquista_promessa                (view de leitura)
--   - fn_importar_reconquista_promessa()    (RPC de import)
--
-- MOTIVACAO (decisao do usuario em 2026-10-16)
-- A partir da apuracao de 09/2026 o card "Promessas" da Reconquista
-- deixa de sair do export `reconquista` (028/029/053) e passa a ser a
-- contagem do arquivo "Promessa Diaria" do banco (`Promessa_diaria.xlsx`,
-- aba Export): uma linha por proposta (co_adesao = ADE) com a data da
-- promessa, o retorno do INSS e a flag de elegibilidade.
--
-- Promessas do mes = linhas com `elegivel = true` (PROMESSA e FDR E
-- PROMESSA contam; FDR = Fim De Relacionamento). E FLUXO: todas as
-- promessas feitas no mes, inclusive as que depois efetivaram.
-- `retorno_inss` NAO filtra a conta (so alimenta o insight do card).
-- Efetivadas seguem da Liga (127), sem mudanca; o badge "Efetivada
-- MM/AAAA" cruza co_adesao com v_reconquista_liga no consumidor.
--
-- PERIODO = MES DE dt_promessa, SEM DEFASAGEM
-- O arquivo cobre varios meses. O importador (angry-man, card
-- "Reconquista — Promessa Diaria", periodo obrigatorio) envia SO as
-- linhas com dt_promessa no mes do periodo escolhido e reporta as
-- demais como `descartadas`. A RPC confere de novo e RECUSA o lote se
-- alguma linha estiver fora do mes — nunca grava promessa no periodo
-- errado. Reimportar um mes substitui so aquele mes (DELETE + INSERT
-- na mesma transacao), como Liga (127) e Prestamista (134).
--
-- VALIDACAO ANTES DO DELETE — LOTE INTEIRO OU NADA
-- Toda recusa acontece ANTES de tocar o periodo, com RAISE EXCEPTION de
-- mensagem clara (o lote todo e abortado; o que ja estava gravado fica):
--   - periodo inexistente;
--   - payload vazio / nao-array / linha nao-objeto / chave fora da lista
--     fechada (ver secao 4);
--   - co_adesao ausente ou DUPLICADO no lote (lista ate 20 ADEs);
--   - dt_promessa ausente ou fora do mes do periodo (lista ate 20 ADEs);
--   - flag de elegibilidade vazia ou desconhecida (lista ate 20 ADEs).
-- Diferente da 127/134, NAO ha ON CONFLICT DO NOTHING: duplicata ja foi
-- barrada, e "ficar a primeira" esconderia um arquivo inconsistente.
-- Payload vazio tambem e recusado: com DELETE + INSERT ele apagaria o
-- periodo em silencio (ex.: import do mes errado); "nao importado" e um
-- estado explicito do dashboard, nao o resultado de um lote vazio.
--
-- ELEGIVEL DERIVADO NA RPC (nao no importador)
-- translate(upper(trim(flag)), 'ÍÃ', 'IA'):
--   'ELEGIVEL'     -> true   (ELEGÍVEL / ELEGIVEL)
--   'NAO ELEGIVEL' -> false  (NÃO ELEGÍVEL / NAO ELEGIVEL)
--   qualquer outro (inclusive vazio) -> lote RECUSADO.
-- Nao vale a regra do export (053) de flag NULL = ELEGIVEL: aqui a flag
-- e a conta, entao ausencia e erro, nao default. O texto bruto fica em
-- `flag_elegibilidade` para auditoria.
--
-- ATRIBUICAO (loja/consultor) VEM DO PROPRIO ARQUIVO
-- Identica a de fn_importar_reconquista_liga (127): loja por cod_bmg
-- (prefixo de `no_franquia`, extraido no importador) com sucessora
-- aplicada; consultor por nome completo + loja. Texto original guardado
-- (no_franquia/consultor_nome); a view cai nele quando a FK nao resolve.
-- Supervisor: guardamos o nome do arquivo (`supervisor_nome`) so como
-- informativo. O criterio de "promessa em nome de supervisor" e o
-- CADASTRO (carregar_supervisores + excluir_supervisores), no
-- consumidor — nao esta coluna.
--
-- LGPD / ESCOPO — O QUE NAO ENTRA
-- O arquivo traz nu_matricula (matricula do beneficiario), no_franqueado
-- e a cadeia de gerencia (no_gerente_executivo, no_gerente_regional,
-- no_gerente_canal_proprio, no_gerente_loja, no_coordenador_loja). Nada
-- disso e armazenado, nem aceito no payload: a RPC recusa chave fora da
-- lista fechada, entao um importador que "vaze" nu_matricula falha alto
-- em vez de a coluna ser descartada em silencio.
--
-- RLS — MESMO TRATAMENTO DA `reconquista_liga` (127)
-- Carteira de cliente (co_adesao): deny explicito para
-- anon/authenticated + REVOKE. Todo acesso e service_role (BYPASSRLS);
-- o recorte por perfil e client-side (_filtro_rls_reconquista), que
-- reaproveita as colunas texto loja/regiao/consultor — por isso a view
-- expoe os MESMOS nomes de v_reconquista_liga.
--
-- Depende de: periodos, lojas, regioes, consultores (schema base).
-- Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- 1. Tabela
-- ===========================================

CREATE TABLE IF NOT EXISTS public.reconquista_promessa (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    periodo_id            UUID NOT NULL
                              REFERENCES public.periodos (id)
                              ON DELETE CASCADE,
    co_adesao             BIGINT  NOT NULL,
    dt_promessa           DATE    NOT NULL,
    dt_retorno            DATE,
    retorno_inss          TEXT,
    flag_elegibilidade    TEXT    NOT NULL,
    elegivel              BOOLEAN NOT NULL,
    status_mes_anterior   TEXT,
    status_cliente_atual  TEXT,

    -- Origem (texto bruto do arquivo + FK resolvida no import)
    no_franquia           TEXT,
    cod_bmg               INTEGER,
    loja_id               UUID REFERENCES public.lojas (id)       ON DELETE SET NULL,
    supervisor_nome       TEXT,
    consultor_nome        TEXT,
    consultor_id          UUID REFERENCES public.consultores (id) ON DELETE SET NULL,

    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_reconquista_promessa_periodo_adesao
        UNIQUE (periodo_id, co_adesao)
);

COMMENT ON TABLE public.reconquista_promessa IS
    'Promessa Diaria da Reconquista (arquivo do banco, aba Export), uma '
    'linha por proposta (co_adesao = ADE) por periodo; periodo = mes de '
    'dt_promessa, sem defasagem. Fonte do card Promessas a partir de '
    '09/2026: count(elegivel) do periodo. Reimport substitui so o '
    'periodo (fn_importar_reconquista_promessa). Sem nu_matricula (LGPD), '
    'sem franqueado e sem cadeia de gerencia.';

COMMENT ON COLUMN public.reconquista_promessa.co_adesao IS
    'ADE da proposta. Unica por periodo: duplicata no arquivo recusa o '
    'import inteiro. Cruza com v_reconquista_liga.co_adesao para o badge '
    '"Efetivada MM/AAAA" (no consumidor).';

COMMENT ON COLUMN public.reconquista_promessa.dt_promessa IS
    'Data da promessa. Define o periodo: a RPC recusa linha cujo mes '
    'difira do periodo do import.';

COMMENT ON COLUMN public.reconquista_promessa.retorno_inss IS
    'Retorno do INSS (texto do arquivo). NULL = pendente. Nao filtra a '
    'contagem de promessas; so alimenta o insight do card.';

COMMENT ON COLUMN public.reconquista_promessa.flag_elegibilidade IS
    'Flag de elegibilidade como veio no arquivo (texto bruto, para '
    'auditoria). A conta usa `elegivel`, derivado dela na RPC.';

COMMENT ON COLUMN public.reconquista_promessa.elegivel IS
    'Derivado na RPC: translate(upper(trim(flag)), ''ÍÃ'', ''IA'') = '
    '''ELEGIVEL'' -> true; = ''NAO ELEGIVEL'' -> false; outro valor '
    'recusa o import. Promessas do mes = count(*) FILTER (elegivel).';

COMMENT ON COLUMN public.reconquista_promessa.supervisor_nome IS
    'Supervisor como veio no arquivo — so informativo. O criterio de '
    'exclusao de supervisor nas visoes por pessoa e o cadastro '
    '(carregar_supervisores), nao esta coluna.';

CREATE INDEX IF NOT EXISTS idx_reconquista_promessa_periodo
    ON public.reconquista_promessa (periodo_id);


-- ===========================================
-- 2. RLS — deny explicito (mesmo racional da 093/127)
-- ===========================================

ALTER TABLE public.reconquista_promessa ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS pol_reconquista_promessa_deny ON public.reconquista_promessa;

CREATE POLICY pol_reconquista_promessa_deny
    ON public.reconquista_promessa
    FOR ALL
    TO anon, authenticated
    USING (false)
    WITH CHECK (false);

COMMENT ON POLICY pol_reconquista_promessa_deny ON public.reconquista_promessa IS
    'Deny explicito. Carteira de cliente (co_adesao) — mesmo tratamento '
    'de pol_reconquista_liga_deny (127). Todo acesso e por service_role; '
    'o recorte por perfil e client-side (_filtro_rls_reconquista).';

REVOKE ALL ON public.reconquista_promessa FROM anon, authenticated;


-- ===========================================
-- 3. View de leitura
--
-- Nomes de loja/regiao/consultor IGUAIS aos de v_reconquista_liga: o
-- recorte client-side por perfil e o mesmo. Regiao = a ATUAL da loja
-- (lojas.regiao_id), como na liga.
-- ===========================================

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
    rp.consultor_nome
FROM public.reconquista_promessa rp
JOIN public.periodos p           ON p.id   = rp.periodo_id
LEFT JOIN public.lojas l         ON l.id   = rp.loja_id
LEFT JOIN public.regioes reg     ON reg.id = l.regiao_id
LEFT JOIN public.consultores con ON con.id = rp.consultor_id;

COMMENT ON VIEW public.v_reconquista_promessa IS
    'Promessa Diaria com loja/regiao/consultor rotulados e ano/mes do '
    'periodo. Fonte do card Promessas V3 (count elegivel, >= 09/2026) e '
    'do analitico "Promessa Diaria".';


-- ===========================================
-- 4. RPC de import — valida tudo, depois substitui SO o periodo
--
-- Payload: lista de objetos com a lista FECHADA de chaves
--   {co_adesao (int), dt_promessa ('YYYY-MM-DD'),
--    dt_retorno ('YYYY-MM-DD'|null), retorno_inss (text|null),
--    flag_elegibilidade (text bruto), status_mes_anterior,
--    status_cliente_atual, no_franquia, cod_bmg (int|null),
--    supervisor_nome, consultor_nome}
-- Chave fora da lista recusa o lote (barreira contra nu_matricula e
-- cadeia de gerencia). Parse do xlsx — aba Export, linhas sem
-- co_adesao, rodape "Filtros aplicados", filtro pelo mes — e do
-- importador; aqui se valida, resolve FK e grava.
--
-- Set-based (como a 134). Ordem: validacoes -> DELETE -> INSERT, tudo
-- na mesma transacao da chamada.
-- ===========================================

CREATE OR REPLACE FUNCTION public.fn_importar_reconquista_promessa(
    p_periodo_id UUID,
    p_rows       JSONB
)
RETURNS TABLE (
    removidos     INTEGER,
    inseridos     INTEGER,
    elegiveis     INTEGER,
    sem_loja      INTEGER,
    sem_consultor INTEGER
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_ano        INTEGER;
    v_mes        INTEGER;
    v_ref        TEXT;
    v_removidos  INTEGER := 0;
    v_qtd        INTEGER;
    v_lista      TEXT;
    v_valores    TEXT;
BEGIN
    -- ---------------------------------------
    -- Periodo
    -- ---------------------------------------
    SELECT p.ano, p.mes INTO v_ano, v_mes
    FROM public.periodos p
    WHERE p.id = p_periodo_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Periodo % inexistente.', p_periodo_id;
    END IF;

    v_ref := lpad(v_mes::TEXT, 2, '0') || '/' || v_ano;

    -- ---------------------------------------
    -- Forma do payload
    -- ---------------------------------------
    IF p_rows IS NULL OR jsonb_typeof(p_rows) <> 'array' THEN
        RAISE EXCEPTION '%', 'Payload invalido: esperado um array JSON de '
            || 'linhas. Nada foi gravado.';
    END IF;

    IF jsonb_array_length(p_rows) = 0 THEN
        RAISE EXCEPTION '%', format(
            'Nenhuma promessa para %s no lote. Nada foi gravado nem removido '
            || '(confira o periodo escolhido e o arquivo).', v_ref);
    END IF;

    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_rows) e
        WHERE jsonb_typeof(e) <> 'object'
    ) THEN
        RAISE EXCEPTION '%', 'Payload invalido: toda linha deve ser um '
            || 'objeto JSON. Nada foi gravado.';
    END IF;

    -- Lista FECHADA de chaves: barra nu_matricula / franqueado / gerencia
    SELECT string_agg(DISTINCT k, ', ' ORDER BY k) INTO v_lista
    FROM jsonb_array_elements(p_rows) e,
         LATERAL jsonb_object_keys(e) k
    WHERE k <> ALL (ARRAY[
        'co_adesao', 'dt_promessa', 'dt_retorno', 'retorno_inss',
        'flag_elegibilidade', 'status_mes_anterior', 'status_cliente_atual',
        'no_franquia', 'cod_bmg', 'supervisor_nome', 'consultor_nome'
    ]);

    IF v_lista IS NOT NULL THEN
        RAISE EXCEPTION '%', format(
            'Payload com chave(s) nao permitida(s): %s. A Promessa Diaria nao '
            || 'aceita nu_matricula, franqueado nem cadeia de gerencia. Nada '
            || 'foi gravado.', v_lista);
    END IF;

    -- ---------------------------------------
    -- co_adesao ausente
    -- ---------------------------------------
    SELECT count(*) INTO v_qtd
    FROM jsonb_array_elements(p_rows) e
    WHERE NULLIF(TRIM(e->>'co_adesao'), '') IS NULL;

    IF v_qtd > 0 THEN
        RAISE EXCEPTION '%', format(
            'Import bloqueado: %s linha(s) sem co_adesao (ADE). Nada foi '
            || 'gravado.', v_qtd);
    END IF;

    -- ---------------------------------------
    -- co_adesao duplicado (lista ate 20 ADEs)
    -- ---------------------------------------
    SELECT count(*),
           string_agg(d.ade::TEXT, ', ' ORDER BY d.ade) FILTER (WHERE d.rn <= 20)
      INTO v_qtd, v_lista
    FROM (
        SELECT x.ade, row_number() OVER (ORDER BY x.ade) AS rn
        FROM (
            SELECT (e->>'co_adesao')::BIGINT AS ade
            FROM jsonb_array_elements(p_rows) e
        ) x
        GROUP BY x.ade
        HAVING count(*) > 1
    ) d;

    IF v_qtd > 0 THEN
        RAISE EXCEPTION '%', format(
            'Import bloqueado: %s ADE(s) duplicada(s) no arquivo para %s: %s%s. '
            || 'Nada foi gravado.',
            v_qtd, v_ref, v_lista,
            CASE WHEN v_qtd > 20 THEN format(' (e mais %s)', v_qtd - 20) ELSE '' END);
    END IF;

    -- ---------------------------------------
    -- dt_promessa ausente ou fora do mes do periodo (lista ate 20 ADEs)
    -- ---------------------------------------
    SELECT count(*),
           string_agg(
               f.ade::TEXT || ' ('
               || COALESCE(to_char(f.dt, 'DD/MM/YYYY'), 'sem data') || ')',
               ', ' ORDER BY f.ade
           ) FILTER (WHERE f.rn <= 20)
      INTO v_qtd, v_lista
    FROM (
        SELECT x.ade, x.dt, row_number() OVER (ORDER BY x.ade) AS rn
        FROM (
            SELECT (e->>'co_adesao')::BIGINT AS ade,
                   (NULLIF(TRIM(e->>'dt_promessa'), ''))::DATE AS dt
            FROM jsonb_array_elements(p_rows) e
        ) x
        WHERE x.dt IS NULL
           OR date_trunc('month', x.dt)::DATE <> make_date(v_ano, v_mes, 1)
    ) f;

    IF v_qtd > 0 THEN
        RAISE EXCEPTION '%', format(
            'Import bloqueado: %s linha(s) com dt_promessa ausente ou fora de '
            || '%s: %s%s. Nada foi gravado.',
            v_qtd, v_ref, v_lista,
            CASE WHEN v_qtd > 20 THEN format(' (e mais %s)', v_qtd - 20) ELSE '' END);
    END IF;

    -- ---------------------------------------
    -- Flag vazia/desconhecida (lista ate 20 ADEs + valores vistos)
    -- Normalizacao IDENTICA a do INSERT abaixo.
    -- ---------------------------------------
    SELECT count(*),
           string_agg(f.ade::TEXT, ', ' ORDER BY f.ade) FILTER (WHERE f.rn <= 20),
           string_agg(DISTINCT COALESCE('"' || f.flag || '"', 'nula'), ', ')
      INTO v_qtd, v_lista, v_valores
    FROM (
        SELECT x.ade, x.flag, row_number() OVER (ORDER BY x.ade) AS rn
        FROM (
            SELECT (e->>'co_adesao')::BIGINT AS ade,
                   e->>'flag_elegibilidade' AS flag
            FROM jsonb_array_elements(p_rows) e
        ) x
        WHERE translate(upper(trim(x.flag)), 'ÍÃ', 'IA') IS NULL
           OR translate(upper(trim(x.flag)), 'ÍÃ', 'IA')
                  NOT IN ('ELEGIVEL', 'NAO ELEGIVEL')
    ) f;

    IF v_qtd > 0 THEN
        RAISE EXCEPTION '%', format(
            'Import bloqueado: %s linha(s) com flag de elegibilidade vazia ou '
            || 'desconhecida (valores: %s). ADEs: %s%s. Esperado ELEGIVEL ou '
            || 'NAO ELEGIVEL. Nada foi gravado.',
            v_qtd, v_valores, v_lista,
            CASE WHEN v_qtd > 20 THEN format(' (e mais %s)', v_qtd - 20) ELSE '' END);
    END IF;

    -- ---------------------------------------
    -- Lote valido: substitui o periodo
    -- ---------------------------------------
    DELETE FROM public.reconquista_promessa WHERE periodo_id = p_periodo_id;
    GET DIAGNOSTICS v_removidos = ROW_COUNT;

    RETURN QUERY
    WITH src AS (
        SELECT
            r.co_adesao,
            r.dt_promessa,
            (NULLIF(TRIM(r.dt_retorno), ''))::DATE                  AS dt_retorno,
            NULLIF(TRIM(r.retorno_inss), '')                         AS retorno_inss,
            r.flag_elegibilidade,
            translate(upper(trim(r.flag_elegibilidade)), 'ÍÃ', 'IA') AS flag_norm,
            NULLIF(TRIM(r.status_mes_anterior), '')                  AS status_mes_anterior,
            NULLIF(TRIM(r.status_cliente_atual), '')                 AS status_cliente_atual,
            NULLIF(TRIM(r.no_franquia), '')                          AS no_franquia,
            r.cod_bmg,
            NULLIF(TRIM(r.supervisor_nome), '')                      AS supervisor_nome,
            NULLIF(TRIM(r.consultor_nome), '')                       AS consultor_nome
        FROM jsonb_to_recordset(p_rows) AS r (
            co_adesao             BIGINT,
            dt_promessa           DATE,
            dt_retorno            TEXT,  -- '' tolerado -> NULL
            retorno_inss          TEXT,
            flag_elegibilidade    TEXT,
            status_mes_anterior   TEXT,
            status_cliente_atual  TEXT,
            no_franquia           TEXT,
            cod_bmg               INTEGER,
            supervisor_nome       TEXT,
            consultor_nome        TEXT
        )
    ),
    resolvido AS (
        SELECT s.*, lj.loja_id, cs.consultor_id
        FROM src s
        -- Loja: cod_bmg ja com sucessora aplicada (criterio da 053/127)
        LEFT JOIN LATERAL (
            SELECT COALESCE(l.sucessora_id, l.id) AS loja_id
            FROM public.lojas l
            WHERE l.cod_bmg = s.cod_bmg
            LIMIT 1
        ) lj ON true
        -- Consultor: nome completo + loja (criterio da 053/127)
        LEFT JOIN LATERAL (
            SELECT c.id AS consultor_id
            FROM public.consultores c
            WHERE s.consultor_nome IS NOT NULL
              AND c.nome ILIKE s.consultor_nome
              AND (c.loja_id = lj.loja_id OR c.loja_id IS NULL)
            ORDER BY CASE WHEN c.loja_id = lj.loja_id THEN 0 ELSE 1 END, c.nome
            LIMIT 1
        ) cs ON true
    ),
    ins AS (
        INSERT INTO public.reconquista_promessa (
            periodo_id, co_adesao, dt_promessa, dt_retorno, retorno_inss,
            flag_elegibilidade, elegivel,
            status_mes_anterior, status_cliente_atual,
            no_franquia, cod_bmg, loja_id,
            supervisor_nome, consultor_nome, consultor_id
        )
        SELECT
            p_periodo_id, r.co_adesao, r.dt_promessa, r.dt_retorno,
            r.retorno_inss,
            r.flag_elegibilidade, (r.flag_norm = 'ELEGIVEL'),
            r.status_mes_anterior, r.status_cliente_atual,
            r.no_franquia, r.cod_bmg, r.loja_id,
            r.supervisor_nome, r.consultor_nome, r.consultor_id
        FROM resolvido r
        RETURNING elegivel, loja_id, consultor_id
    )
    SELECT
        v_removidos,
        count(*)::INTEGER,
        (count(*) FILTER (WHERE i.elegivel))::INTEGER,
        (count(*) FILTER (WHERE i.loja_id IS NULL))::INTEGER,
        (count(*) FILTER (WHERE i.consultor_id IS NULL))::INTEGER
    FROM ins i;
END;
$$;

COMMENT ON FUNCTION public.fn_importar_reconquista_promessa(UUID, JSONB) IS
    'Promessa Diaria da Reconquista: valida o lote inteiro (chaves '
    'permitidas, ADE unica, dt_promessa no mes do periodo, flag '
    'ELEGIVEL/NAO ELEGIVEL) e so entao faz DELETE do periodo + INSERT, '
    'na mesma transacao. Deriva `elegivel` da flag; resolve loja_id '
    '(cod_bmg + sucessora) e consultor_id (nome completo + loja). Retorna '
    '(removidos, inseridos, elegiveis, sem_loja, sem_consultor) para o '
    'log do importador.';

-- Mesmo fechamento da 127/134: so service_role (angry-man via Edge
-- Function reconquista-rpc no web, IPC service_role no Electron).
REVOKE EXECUTE ON FUNCTION public.fn_importar_reconquista_promessa(UUID, JSONB)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_importar_reconquista_promessa(UUID, JSONB)
    TO service_role;

NOTIFY pgrst, 'reload schema';


-- =====================================================
-- VALIDACAO — rodar apos aplicar e importar 09/2026 e 10/2026
-- (arquivo Promessa_diaria.xlsx atual, 216 linhas de dado)
--
-- Esperado no log do importador:
--   09/2026: enviadas/inseridas 161, elegiveis 153, descartadas 55,
--            sem_loja 0, sem_consultor 3
--   10/2026: enviadas/inseridas  55, elegiveis  42, descartadas 161,
--            sem_loja 0, sem_consultor 1
--
-- 1) Contagem por periodo (esperado: 09 -> 161 / 153; 10 -> 55 / 42):
--
--    SELECT ano, mes, count(*) AS linhas,
--           count(*) FILTER (WHERE elegivel) AS elegiveis
--    FROM public.v_reconquista_promessa
--    WHERE ano = 2026 AND mes IN (9, 10)
--    GROUP BY ano, mes ORDER BY mes;
--
-- 2) Atribuicao (esperado: 09 -> sem_loja 0, sem_consultor 3;
--                          10 -> sem_loja 0, sem_consultor 1):
--
--    SELECT p.mes,
--           count(*) FILTER (WHERE rp.loja_id IS NULL)      AS sem_loja,
--           count(*) FILTER (WHERE rp.consultor_id IS NULL) AS sem_consultor
--    FROM public.reconquista_promessa rp
--    JOIN public.periodos p ON p.id = rp.periodo_id
--    WHERE p.ano = 2026 AND p.mes IN (9, 10)
--    GROUP BY p.mes ORDER BY p.mes;
--
-- 3) Quem nao resolveu consultor (esperado: 4361404 LETICIA VIEIRA
--    GOMES @50151; 5856610 e 5004753 LETICIA GONCALVES DA COSTA @49889
--    — em 09; 9797582 ERICA CRISTINA MARINS DA SILVA ROSA @49820 — em 10):
--
--    SELECT p.mes, rp.co_adesao, rp.consultor_nome, rp.cod_bmg
--    FROM public.reconquista_promessa rp
--    JOIN public.periodos p ON p.id = rp.periodo_id
--    WHERE p.ano = 2026 AND p.mes IN (9, 10) AND rp.consultor_id IS NULL
--    ORDER BY p.mes, rp.co_adesao;
--
-- 4) Flag -> elegivel (esperado: so pares ELEGIVEL/true e
--    NAO ELEGIVEL/false, com e sem acento):
--
--    SELECT flag_elegibilidade, elegivel, count(*)
--    FROM public.reconquista_promessa
--    GROUP BY 1, 2 ORDER BY 1, 2;
--
-- 5) Deny — sem grant residual para anon/authenticated (esperado: 0
--    linhas na tabela; false/false na RPC):
--
--    SELECT grantee, privilege_type
--    FROM information_schema.role_table_grants
--    WHERE table_name IN ('reconquista_promessa', 'v_reconquista_promessa')
--      AND grantee IN ('anon', 'authenticated');
--
--    SELECT has_function_privilege('anon',
--               'public.fn_importar_reconquista_promessa(uuid, jsonb)', 'EXECUTE') AS anon_exec,
--           has_function_privilege('authenticated',
--               'public.fn_importar_reconquista_promessa(uuid, jsonb)', 'EXECUTE') AS auth_exec;
--
-- 6) LGPD — nenhuma coluna proibida (esperado: 0 linhas):
--
--    SELECT column_name
--    FROM information_schema.columns
--    WHERE table_schema = 'public'
--      AND table_name IN ('reconquista_promessa', 'v_reconquista_promessa')
--      AND column_name IN ('nu_matricula', 'no_franqueado',
--                          'no_gerente_executivo', 'no_gerente_regional',
--                          'no_gerente_canal_proprio', 'no_gerente_loja',
--                          'no_coordenador_loja');
--
-- 7) Recusas (smoke test, NAO grava — tudo em ROLLBACK; cada SELECT
--    deve falhar com a mensagem indicada, sem apagar o periodo):
--
--    BEGIN;
--    -- duplicata -> "ADE(s) duplicada(s) ... 1"
--    SELECT * FROM public.fn_importar_reconquista_promessa(
--        (SELECT id FROM public.periodos WHERE ano = 2026 AND mes = 10),
--        '[{"co_adesao":1,"dt_promessa":"2026-10-01","flag_elegibilidade":"ELEGÍVEL"},
--          {"co_adesao":1,"dt_promessa":"2026-10-02","flag_elegibilidade":"ELEGÍVEL"}]');
--    ROLLBACK;
--    -- Repetir com: dt_promessa "2026-09-30" (fora do mes),
--    -- flag_elegibilidade "" ou "TALVEZ" (flag desconhecida),
--    -- chave extra "nu_matricula" (chave nao permitida), e '[]' (vazio).
-- =====================================================
