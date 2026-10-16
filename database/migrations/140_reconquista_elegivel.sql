-- =====================================================
-- Migracao 140: Reconquista — Carteira Elegivel (Extrator de Elegiveis)
--
-- Adiciona:
--   - reconquista_elegivel                  (tabela, por periodo)
--   - v_reconquista_elegivel                (view de leitura)
--   - fn_importar_reconquista_elegivel()    (RPC de import)
--
-- MOTIVACAO (decisao do usuario em 2026-10-16)
-- O export antigo da Reconquista (`reconquista_YYYYMM.xlsx`, tabela
-- `reconquista`, 028/029/053) deixa de ser importado. A lista de
-- trabalho passa a ser o "Extrator de Elegiveis" do banco
-- (`Extrator_elegiveis.xlsx`, aba Export): FOTO da carteira elegivel de
-- um mes, uma linha por cliente (co_adesao = ADE), com prioridade de
-- atuacao, motivo de impedimento, saldo, bancos, regra de pagamento e o
-- link da jornada. E so ANALITICO (sub-aba "Carteira Elegivel"): nao
-- entra em card, apuracao nem acelerador. Primeiro arquivo: 10/2026.
--
-- PERIODO = anomes_referencia DO ARQUIVO
-- O arquivo traz `anomes_referencia` (YYYYMM) — um mes so. O importador
-- (angry-man, card "Reconquista — Carteira Elegivel", periodo
-- obrigatorio) recusa o arquivo se alguma linha for de outro mes, e a
-- RPC confere de novo. Reimportar substitui so o periodo (DELETE +
-- INSERT na mesma transacao), como Liga (127) e Promessa Diaria (137).
--
-- VALIDACAO ANTES DO DELETE — LOTE INTEIRO OU NADA (mesmo contrato da 137)
--   - periodo inexistente;
--   - payload vazio / nao-array / linha nao-objeto / chave fora da lista
--     fechada (ver secao 4);
--   - co_adesao ausente ou DUPLICADO no lote (lista ate 20 ADEs);
--   - anomes_referencia ausente ou diferente do periodo;
--   - flag de elegibilidade vazia ou desconhecida;
--   - flag de atuacao vazia ou desconhecida.
--
-- DERIVADOS NA RPC
--   elegivel         = translate(upper(trim(flag_elegibilidade)), 'ÍÃ', 'IA')
--                      'ELEGIVEL' -> true, 'NAO ELEGIVEL' -> false
--                      (mesma regra da 137; o arquivo hoje so traz
--                      ELEGIVEL, mas a flag e conta, nao default).
--   baixa_prioridade = regexp_replace(upper(trim(flag_atuacao)), '\s+', ' ')
--                      'BAIXA PRIORIDADE' -> true, 'PRIORIDADE' -> false.
--                      No primeiro arquivo, BAIXA PRIORIDADE <=> ter
--                      `de_motivo_impedido_operar` (311 de 311). Baixa
--                      prioridade CONTA como elegivel; a UI so a ordena
--                      abaixo das prioritarias (decisao do usuario).
-- Textos brutos ficam em `flag_elegibilidade` / `flag_atuacao`.
--
-- ATRIBUICAO (loja/consultor) VEM DO PROPRIO ARQUIVO
-- Identica a 127/137: loja por cod_bmg (prefixo de `no_franquia`) com
-- sucessora; consultor por nome completo + loja. A carteira pertence a
-- loja do ARQUIVO, mesmo quando o consultor esta cadastrado em outra
-- loja (carteira herdada da loja anterior). Consultor nao resolvido =>
-- `consultor_identificado = false` na view => no consumidor o lead vai
-- para o supervisor vigente da loja (regra da 138).
--
-- LINK DA JORNADA (`link_reconquista`)
-- Guardado e exibido por decisao do usuario (16/10/2026): e o que o
-- consultor usa para agir. E URL publica (quem tem o link acessa a
-- jornada do cliente) — mesmo nivel do `link_aceite` do export. O
-- consumidor so renderiza como link o que comeca com https://.
--
-- LGPD / ESCOPO — O QUE NAO ENTRA
-- nu_matricula, no_franqueado e a cadeia de gerencia
-- (no_gerente_executivo, no_gerente_regional, no_gerente_canal_proprio,
-- no_gerente_loja, no_coordenador_loja). A RPC recusa chave fora da
-- lista fechada.
--
-- RLS — MESMO TRATAMENTO DA 127/137
-- Deny explicito para anon/authenticated + REVOKE na tabela E na view.
-- Recorte por perfil client-side (_filtro_rls_reconquista) sobre as
-- colunas texto loja/regiao/consultor — mesmos nomes de
-- v_reconquista_promessa.
--
-- Depende de: periodos, lojas, regioes, consultores (schema base).
-- Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- 1. Tabela
-- ===========================================

CREATE TABLE IF NOT EXISTS public.reconquista_elegivel (
    id                         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    periodo_id                 UUID NOT NULL
                                   REFERENCES public.periodos (id)
                                   ON DELETE CASCADE,
    co_adesao                  BIGINT  NOT NULL,
    flag_elegibilidade         TEXT    NOT NULL,
    elegivel                   BOOLEAN NOT NULL,
    flag_atuacao               TEXT    NOT NULL,
    baixa_prioridade           BOOLEAN NOT NULL,
    motivo_impedido_operar     TEXT,
    status_cliente_anterior    TEXT,
    status_cliente_atual       TEXT,
    flag_promessa_sem_retorno  TEXT,
    saldo_carteira             NUMERIC(15, 2),
    banco_origem               TEXT,
    banco_destino              TEXT,
    banco_saldo_residual       TEXT,
    regra_pagamento            TEXT,
    link_reconquista           TEXT,

    -- Origem (texto bruto do arquivo + FK resolvida no import)
    no_franquia                TEXT,
    cod_bmg                    INTEGER,
    loja_id                    UUID REFERENCES public.lojas (id)       ON DELETE SET NULL,
    supervisor_nome            TEXT,
    consultor_nome             TEXT,
    consultor_id               UUID REFERENCES public.consultores (id) ON DELETE SET NULL,

    created_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_reconquista_elegivel_periodo_adesao
        UNIQUE (periodo_id, co_adesao)
);

COMMENT ON TABLE public.reconquista_elegivel IS
    'Carteira Elegivel da Reconquista (Extrator de Elegiveis do banco, aba '
    'Export): foto mensal, uma linha por cliente (co_adesao = ADE) por '
    'periodo; periodo = anomes_referencia do arquivo. So analitico (sub-aba '
    '"Carteira Elegivel", >= 10/2026). Reimport substitui so o periodo '
    '(fn_importar_reconquista_elegivel). Sem nu_matricula (LGPD), sem '
    'franqueado e sem cadeia de gerencia.';

COMMENT ON COLUMN public.reconquista_elegivel.co_adesao IS
    'ADE do cliente. Unica por periodo: duplicata no arquivo recusa o '
    'import inteiro.';

COMMENT ON COLUMN public.reconquista_elegivel.elegivel IS
    'Derivado na RPC: translate(upper(trim(flag)), ''ÍÃ'', ''IA'') = '
    '''ELEGIVEL'' -> true; = ''NAO ELEGIVEL'' -> false; outro valor recusa '
    'o import.';

COMMENT ON COLUMN public.reconquista_elegivel.baixa_prioridade IS
    'Derivado na RPC de flag_atuacao: ''BAIXA PRIORIDADE'' -> true; '
    '''PRIORIDADE'' -> false; outro valor recusa o import. Conta como '
    'elegivel; a UI ordena abaixo das prioritarias.';

COMMENT ON COLUMN public.reconquista_elegivel.link_reconquista IS
    'URL publica da jornada do cliente (Reconquista Facil). Guardada por '
    'decisao do usuario (16/10/2026). O consumidor so exibe como link o que '
    'comeca com https://.';

COMMENT ON COLUMN public.reconquista_elegivel.supervisor_nome IS
    'Supervisor como veio no arquivo — so informativo. O destino do lead '
    'sem consultor identificado e o supervisor do CADASTRO '
    '(carregar_supervisores), nao esta coluna.';

CREATE INDEX IF NOT EXISTS idx_reconquista_elegivel_periodo
    ON public.reconquista_elegivel (periodo_id);


-- ===========================================
-- 2. RLS — deny explicito (mesmo racional da 127/137)
-- ===========================================

ALTER TABLE public.reconquista_elegivel ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS pol_reconquista_elegivel_deny ON public.reconquista_elegivel;

CREATE POLICY pol_reconquista_elegivel_deny
    ON public.reconquista_elegivel
    FOR ALL
    TO anon, authenticated
    USING (false)
    WITH CHECK (false);

COMMENT ON POLICY pol_reconquista_elegivel_deny ON public.reconquista_elegivel IS
    'Deny explicito. Carteira de cliente (co_adesao) — mesmo tratamento '
    'de pol_reconquista_promessa_deny (137). Todo acesso e por service_role; '
    'o recorte por perfil e client-side (_filtro_rls_reconquista).';

REVOKE ALL ON public.reconquista_elegivel FROM anon, authenticated;


-- ===========================================
-- 3. View de leitura
--
-- Nomes de loja/regiao/consultor IGUAIS aos de v_reconquista_promessa;
-- `consultor_identificado` com a mesma semantica da 138.
-- ===========================================

CREATE OR REPLACE VIEW public.v_reconquista_elegivel
    WITH (security_invoker = on)
AS
SELECT
    re.co_adesao,
    p.ano                                                     AS ano,
    p.mes                                                     AS mes,
    re.flag_elegibilidade,
    re.elegivel,
    re.flag_atuacao,
    re.baixa_prioridade,
    re.motivo_impedido_operar,
    re.status_cliente_anterior,
    re.status_cliente_atual,
    re.flag_promessa_sem_retorno,
    re.saldo_carteira,
    re.banco_origem,
    re.banco_destino,
    re.banco_saldo_residual,
    re.regra_pagamento,
    re.link_reconquista,
    COALESCE(l.nome, re.no_franquia, '(Nao Identificado)')    AS loja,
    reg.nome                                                  AS regiao,
    COALESCE(con.nome, re.consultor_nome, '(Sem Consultor)')  AS consultor,
    re.supervisor_nome                                        AS supervisor,
    re.no_franquia,
    re.cod_bmg,
    re.consultor_nome,
    (re.consultor_id IS NOT NULL)                             AS consultor_identificado
FROM public.reconquista_elegivel re
JOIN public.periodos p           ON p.id   = re.periodo_id
LEFT JOIN public.lojas l         ON l.id   = re.loja_id
LEFT JOIN public.regioes reg     ON reg.id = l.regiao_id
LEFT JOIN public.consultores con ON con.id = re.consultor_id;

COMMENT ON VIEW public.v_reconquista_elegivel IS
    'Carteira Elegivel com loja/regiao/consultor rotulados e ano/mes do '
    'periodo. Fonte do analitico "Carteira Elegivel" (>= 10/2026).';

-- View nova ja nasce sem o grant padrao do Supabase para anon/authenticated
-- (a tabela-base ja nega via security_invoker; isto e defesa em camada).
REVOKE ALL ON public.v_reconquista_elegivel FROM anon, authenticated;


-- ===========================================
-- 4. RPC de import — valida tudo, depois substitui SO o periodo
--
-- Payload: lista de objetos com a lista FECHADA de chaves
--   {co_adesao (int), anomes_referencia (int YYYYMM),
--    flag_elegibilidade, flag_atuacao (texto bruto),
--    motivo_impedido_operar, status_cliente_anterior,
--    status_cliente_atual, flag_promessa_sem_retorno,
--    saldo_carteira (numero|null), banco_origem, banco_destino,
--    banco_saldo_residual, regra_pagamento, link_reconquista,
--    no_franquia, cod_bmg (int|null), supervisor_nome, consultor_nome}
-- Parse do xlsx (aba Export, rodape do BI) e do importador.
-- ===========================================

CREATE OR REPLACE FUNCTION public.fn_importar_reconquista_elegivel(
    p_periodo_id UUID,
    p_rows       JSONB
)
RETURNS TABLE (
    removidos         INTEGER,
    inseridos         INTEGER,
    elegiveis         INTEGER,
    baixa_prioridade  INTEGER,
    sem_loja          INTEGER,
    sem_consultor     INTEGER
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
            'Nenhum cliente elegivel para %s no lote. Nada foi gravado nem '
            || 'removido (confira o periodo escolhido e o arquivo).', v_ref);
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
        'co_adesao', 'anomes_referencia',
        'flag_elegibilidade', 'flag_atuacao', 'motivo_impedido_operar',
        'status_cliente_anterior', 'status_cliente_atual',
        'flag_promessa_sem_retorno', 'saldo_carteira',
        'banco_origem', 'banco_destino', 'banco_saldo_residual',
        'regra_pagamento', 'link_reconquista',
        'no_franquia', 'cod_bmg', 'supervisor_nome', 'consultor_nome'
    ]);

    IF v_lista IS NOT NULL THEN
        RAISE EXCEPTION '%', format(
            'Payload com chave(s) nao permitida(s): %s. A Carteira Elegivel '
            || 'nao aceita nu_matricula, franqueado nem cadeia de gerencia. '
            || 'Nada foi gravado.', v_lista);
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
    -- anomes_referencia ausente ou diferente do periodo
    -- ---------------------------------------
    SELECT count(*),
           string_agg(DISTINCT COALESCE(NULLIF(TRIM(e->>'anomes_referencia'), ''),
                                        'vazio'), ', ')
      INTO v_qtd, v_valores
    FROM jsonb_array_elements(p_rows) e
    WHERE NULLIF(TRIM(e->>'anomes_referencia'), '') IS NULL
       OR TRIM(e->>'anomes_referencia') <> (v_ano * 100 + v_mes)::TEXT;

    IF v_qtd > 0 THEN
        RAISE EXCEPTION '%', format(
            'Import bloqueado: %s linha(s) com anomes_referencia ausente ou '
            || 'diferente de %s (valores: %s). Nada foi gravado.',
            v_qtd, (v_ano * 100 + v_mes)::TEXT, v_valores);
    END IF;

    -- ---------------------------------------
    -- Flag de elegibilidade vazia/desconhecida
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
    -- Flag de atuacao vazia/desconhecida
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
                   e->>'flag_atuacao' AS flag
            FROM jsonb_array_elements(p_rows) e
        ) x
        WHERE regexp_replace(upper(trim(x.flag)), '\s+', ' ', 'g') IS NULL
           OR regexp_replace(upper(trim(x.flag)), '\s+', ' ', 'g')
                  NOT IN ('PRIORIDADE', 'BAIXA PRIORIDADE')
    ) f;

    IF v_qtd > 0 THEN
        RAISE EXCEPTION '%', format(
            'Import bloqueado: %s linha(s) com flag de atuacao vazia ou '
            || 'desconhecida (valores: %s). ADEs: %s%s. Esperado PRIORIDADE ou '
            || 'BAIXA PRIORIDADE. Nada foi gravado.',
            v_qtd, v_valores, v_lista,
            CASE WHEN v_qtd > 20 THEN format(' (e mais %s)', v_qtd - 20) ELSE '' END);
    END IF;

    -- ---------------------------------------
    -- Lote valido: substitui o periodo
    -- ---------------------------------------
    DELETE FROM public.reconquista_elegivel WHERE periodo_id = p_periodo_id;
    GET DIAGNOSTICS v_removidos = ROW_COUNT;

    RETURN QUERY
    WITH src AS (
        SELECT
            r.co_adesao,
            r.flag_elegibilidade,
            translate(upper(trim(r.flag_elegibilidade)), 'ÍÃ', 'IA')  AS flag_eleg_norm,
            r.flag_atuacao,
            regexp_replace(upper(trim(r.flag_atuacao)), '\s+', ' ', 'g') AS flag_atu_norm,
            NULLIF(TRIM(r.motivo_impedido_operar), '')                AS motivo_impedido_operar,
            NULLIF(TRIM(r.status_cliente_anterior), '')               AS status_cliente_anterior,
            NULLIF(TRIM(r.status_cliente_atual), '')                  AS status_cliente_atual,
            NULLIF(TRIM(r.flag_promessa_sem_retorno), '')             AS flag_promessa_sem_retorno,
            r.saldo_carteira,
            NULLIF(TRIM(r.banco_origem), '')                          AS banco_origem,
            NULLIF(TRIM(r.banco_destino), '')                         AS banco_destino,
            NULLIF(TRIM(r.banco_saldo_residual), '')                  AS banco_saldo_residual,
            NULLIF(TRIM(r.regra_pagamento), '')                       AS regra_pagamento,
            NULLIF(TRIM(r.link_reconquista), '')                      AS link_reconquista,
            NULLIF(TRIM(r.no_franquia), '')                           AS no_franquia,
            r.cod_bmg,
            NULLIF(TRIM(r.supervisor_nome), '')                       AS supervisor_nome,
            NULLIF(TRIM(r.consultor_nome), '')                        AS consultor_nome
        FROM jsonb_to_recordset(p_rows) AS r (
            co_adesao                  BIGINT,
            flag_elegibilidade         TEXT,
            flag_atuacao               TEXT,
            motivo_impedido_operar     TEXT,
            status_cliente_anterior    TEXT,
            status_cliente_atual       TEXT,
            flag_promessa_sem_retorno  TEXT,
            saldo_carteira             NUMERIC(15, 2),
            banco_origem               TEXT,
            banco_destino              TEXT,
            banco_saldo_residual       TEXT,
            regra_pagamento            TEXT,
            link_reconquista           TEXT,
            no_franquia                TEXT,
            cod_bmg                    INTEGER,
            supervisor_nome            TEXT,
            consultor_nome             TEXT
        )
    ),
    resolvido AS (
        SELECT s.*, lj.loja_id, cs.consultor_id
        FROM src s
        -- Loja: cod_bmg ja com sucessora aplicada (criterio da 053/127/137)
        LEFT JOIN LATERAL (
            SELECT COALESCE(l.sucessora_id, l.id) AS loja_id
            FROM public.lojas l
            WHERE l.cod_bmg = s.cod_bmg
            LIMIT 1
        ) lj ON true
        -- Consultor: nome completo + loja (criterio da 053/127/137)
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
        INSERT INTO public.reconquista_elegivel (
            periodo_id, co_adesao,
            flag_elegibilidade, elegivel, flag_atuacao, baixa_prioridade,
            motivo_impedido_operar, status_cliente_anterior,
            status_cliente_atual, flag_promessa_sem_retorno, saldo_carteira,
            banco_origem, banco_destino, banco_saldo_residual,
            regra_pagamento, link_reconquista,
            no_franquia, cod_bmg, loja_id,
            supervisor_nome, consultor_nome, consultor_id
        )
        SELECT
            p_periodo_id, r.co_adesao,
            r.flag_elegibilidade, (r.flag_eleg_norm = 'ELEGIVEL'),
            r.flag_atuacao, (r.flag_atu_norm = 'BAIXA PRIORIDADE'),
            r.motivo_impedido_operar, r.status_cliente_anterior,
            r.status_cliente_atual, r.flag_promessa_sem_retorno,
            r.saldo_carteira,
            r.banco_origem, r.banco_destino, r.banco_saldo_residual,
            r.regra_pagamento, r.link_reconquista,
            r.no_franquia, r.cod_bmg, r.loja_id,
            r.supervisor_nome, r.consultor_nome, r.consultor_id
        FROM resolvido r
        RETURNING elegivel, baixa_prioridade, loja_id, consultor_id
    )
    SELECT
        v_removidos,
        count(*)::INTEGER,
        (count(*) FILTER (WHERE i.elegivel))::INTEGER,
        (count(*) FILTER (WHERE i.baixa_prioridade))::INTEGER,
        (count(*) FILTER (WHERE i.loja_id IS NULL))::INTEGER,
        (count(*) FILTER (WHERE i.consultor_id IS NULL))::INTEGER
    FROM ins i;
END;
$$;

COMMENT ON FUNCTION public.fn_importar_reconquista_elegivel(UUID, JSONB) IS
    'Carteira Elegivel da Reconquista: valida o lote inteiro (chaves '
    'permitidas, ADE unica, anomes_referencia = periodo, flag de '
    'elegibilidade e de atuacao conhecidas) e so entao faz DELETE do periodo '
    '+ INSERT, na mesma transacao. Deriva `elegivel` e `baixa_prioridade`; '
    'resolve loja_id (cod_bmg + sucessora) e consultor_id (nome completo + '
    'loja). Retorna (removidos, inseridos, elegiveis, baixa_prioridade, '
    'sem_loja, sem_consultor) para o log do importador.';

-- Mesmo fechamento da 127/134/137: so service_role (angry-man via Edge
-- Function reconquista-rpc no web, IPC service_role no Electron).
REVOKE EXECUTE ON FUNCTION public.fn_importar_reconquista_elegivel(UUID, JSONB)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_importar_reconquista_elegivel(UUID, JSONB)
    TO service_role;

NOTIFY pgrst, 'reload schema';


-- =====================================================
-- VALIDACAO — rodar apos aplicar e importar 10/2026
-- (arquivo Extrator_elegiveis.xlsx de 16/10/2026: 2926 linhas de dado +
-- 3 de rodape do BI)
--
-- Esperado no log do importador:
--   10/2026: enviadas/inseridas 2926, elegiveis 2926, baixa_prioridade 311,
--            sem_loja 0, sem_consultor 137 (numero do cadastro de
--            16/10/2026 — cai conforme o apontamento for corrigido)
--
-- 1) Contagem (esperado: 2926 / 2926 / 311; saldo 12979803.45):
--
--    SELECT count(*) AS linhas,
--           count(*) FILTER (WHERE elegivel) AS elegiveis,
--           count(*) FILTER (WHERE baixa_prioridade) AS baixa_prioridade,
--           sum(saldo_carteira) AS saldo
--    FROM public.v_reconquista_elegivel
--    WHERE ano = 2026 AND mes = 10;
--
-- 2) Baixa prioridade <=> motivo de impedimento (esperado: so os pares
--    false/false 2615 e true/true 311):
--
--    SELECT baixa_prioridade, motivo_impedido_operar IS NOT NULL AS impedido,
--           count(*)
--    FROM public.reconquista_elegivel GROUP BY 1, 2 ORDER BY 1, 2;
--
-- 3) Deny — sem grant residual para anon/authenticated (esperado: 0
--    linhas; false/false na RPC):
--
--    SELECT table_name, grantee, privilege_type
--    FROM information_schema.role_table_grants
--    WHERE table_name IN ('reconquista_elegivel', 'v_reconquista_elegivel')
--      AND grantee IN ('anon', 'authenticated');
--
--    SELECT has_function_privilege('anon',
--               'public.fn_importar_reconquista_elegivel(uuid, jsonb)', 'EXECUTE') AS anon_exec,
--           has_function_privilege('authenticated',
--               'public.fn_importar_reconquista_elegivel(uuid, jsonb)', 'EXECUTE') AS auth_exec;
--
-- 4) LGPD — nenhuma coluna proibida (esperado: 0 linhas):
--
--    SELECT column_name
--    FROM information_schema.columns
--    WHERE table_schema = 'public'
--      AND table_name IN ('reconquista_elegivel', 'v_reconquista_elegivel')
--      AND column_name IN ('nu_matricula', 'no_franqueado',
--                          'no_gerente_executivo', 'no_gerente_regional',
--                          'no_gerente_canal_proprio', 'no_gerente_loja',
--                          'no_coordenador_loja');
--
-- 5) Recusas (smoke test, NAO grava — cada bloco em ROLLBACK; deve falhar
--    com a mensagem indicada):
--
--    BEGIN;
--    -- anomes errado -> "anomes_referencia ausente ou diferente de 202610"
--    SELECT * FROM public.fn_importar_reconquista_elegivel(
--        (SELECT id FROM public.periodos WHERE ano = 2026 AND mes = 10),
--        '[{"co_adesao":1,"anomes_referencia":202609,
--           "flag_elegibilidade":"ELEGÍVEL","flag_atuacao":"PRIORIDADE"}]');
--    ROLLBACK;
--    -- Repetir com: ADE duplicada; flag_atuacao "URGENTE" ou ausente;
--    -- flag_elegibilidade "TALVEZ"; chave extra "nu_matricula"; e '[]'.
-- =====================================================
