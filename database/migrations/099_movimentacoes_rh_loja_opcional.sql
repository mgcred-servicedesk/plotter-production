-- =====================================================
-- Migracao 099: loja deixa de ser obrigatoria no desligamento
--
-- A 097 exigia loja_id uuid valido em toda linha de desligamento, mas
-- nunca o usava: a identidade da pessoa e global por nome, como nos tres
-- ledgers (v. o UPDATE em consultor_vigencia mais abaixo). O efeito era
-- perder o desligamento por um campo que nao participa da operacao --
-- e o arquivo de RH e alimentado por e-mail, com a mesma loja escrita
-- de varias formas ("Help CG Calcadao" e "Help Campo Grande Calcadao",
-- "Help C.G. Estacao" e "Help CG Estacao") alem de lotacoes que nao sao
-- loja ("Digital", "nao especificada").
--
-- Agora loja_id ausente ou vazio e aceito. Quando vem preenchido segue
-- validado: uuid malformado continua LOJA_INVALIDA e uuid inexistente
-- continua LOJA_NAO_ENCONTRADA. Nao ha perda de checagem -- ha perda de
-- uma exigencia que nao correspondia a nenhum uso.
--
-- ASSINATURA INALTERADA (jsonb, jsonb, boolean): e CREATE OR REPLACE da
-- mesma funcao, nao sobrecarga. Nao exige redeploy da Edge Function nem
-- mudanca na whitelist do angry-man.
--
-- Depende de: 097. Executar depois da 098.
-- =====================================================

CREATE OR REPLACE FUNCTION public.fn_movimentacoes_rh_import(
    p_afastamentos  jsonb,
    p_desligamentos jsonb,
    p_validar_apenas boolean DEFAULT true
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
SET statement_timeout = '120s'
AS $fn$
DECLARE
    v_pendencias       jsonb;
    v_afast_len        integer;
    v_desl_len         integer;
    v_afast_inseridos  integer := 0;
    v_afast_atualizados integer := 0;
    v_afast_inalterados integer := 0;
    v_afast_prod       integer := 0;
    v_desl_consultores integer := 0;
    v_desl_supervisores integer := 0;
    v_desl_cadastros   integer := 0;
    v_desl_afast       integer := 0;
    v_row              record;
    v_id               uuid;
    v_tipo_atual       text;
    v_inicio_atual     date;
    v_fim_atual        date;
BEGIN
    IF p_afastamentos IS NULL OR jsonb_typeof(p_afastamentos) <> 'array'
       OR p_desligamentos IS NULL OR jsonb_typeof(p_desligamentos) <> 'array' THEN
        RETURN jsonb_build_object(
            'aplicado', false,
            'validar_apenas', p_validar_apenas,
            'error', 'Os dois payloads devem ser arrays JSON.',
            'pendencias', jsonb_build_array(jsonb_build_object(
                'linha', 0, 'origem', 'ARQUIVO', 'codigo', 'PAYLOAD_INVALIDO')));
    END IF;

    v_afast_len := jsonb_array_length(p_afastamentos);
    v_desl_len := jsonb_array_length(p_desligamentos);

    IF v_afast_len + v_desl_len = 0 THEN
        RETURN jsonb_build_object(
            'aplicado', false,
            'validar_apenas', p_validar_apenas,
            'error', 'Nenhuma movimentacao valida recebida.',
            'pendencias', '[]'::jsonb);
    END IF;

    PERFORM pg_catalog.pg_advisory_xact_lock(20260831);

    CREATE TEMP TABLE mrh_pendencias (
        linha integer NOT NULL,
        origem text NOT NULL,
        codigo text NOT NULL
    ) ON COMMIT DROP;

    CREATE TEMP TABLE mrh_afast_raw ON COMMIT DROP AS
    SELECT
        CASE WHEN coalesce(e.value->>'linha', '') ~ '^[0-9]+$'
             THEN (e.value->>'linha')::integer
             ELSE e.ordinality::integer + 4 END AS linha,
        btrim(coalesce(e.value->>'nome', '')) AS nome,
        upper(regexp_replace(btrim(coalesce(e.value->>'nome', '')),
                             '[[:space:]]+', ' ', 'g')) AS nn,
        upper(btrim(coalesce(e.value->>'tipo', ''))) AS tipo,
        btrim(coalesce(e.value->>'data_inicio', '')) AS inicio_txt,
        btrim(coalesce(e.value->>'data_fim', '')) AS fim_txt
    FROM jsonb_array_elements(p_afastamentos) WITH ORDINALITY AS e(value, ordinality);

    CREATE TEMP TABLE mrh_desl_raw ON COMMIT DROP AS
    SELECT
        CASE WHEN coalesce(e.value->>'linha', '') ~ '^[0-9]+$'
             THEN (e.value->>'linha')::integer
             ELSE e.ordinality::integer + 4 END AS linha,
        btrim(coalesce(e.value->>'nome', '')) AS nome,
        upper(regexp_replace(btrim(coalesce(e.value->>'nome', '')),
                             '[[:space:]]+', ' ', 'g')) AS nn,
        btrim(coalesce(e.value->>'loja_id', '')) AS loja_txt,
        btrim(coalesce(e.value->>'data_desligamento', '')) AS desl_txt
    FROM jsonb_array_elements(p_desligamentos) WITH ORDINALITY AS e(value, ordinality);

    -- Validacao sintatica primeiro. As fases sao separadas para nenhuma
    -- expressao tentar converter texto malformado, mesmo se o otimizador
    -- reordenar predicados do WHERE.
    INSERT INTO mrh_pendencias
    SELECT linha, 'AFASTAMENTO',
           CASE
             WHEN nome = '' THEN 'NOME_AUSENTE'
             WHEN tipo NOT IN ('AFASTAMENTO_MEDICO', 'LICENCA_MATERNIDADE',
                               'LICENCA_NAO_REMUNERADA', 'FERIAS') THEN 'TIPO_INVALIDO'
             WHEN inicio_txt !~ '^\d{4}-\d{2}-\d{2}$' THEN 'DATA_INICIO_INVALIDA'
             ELSE 'DATA_FIM_INVALIDA'
           END
    FROM mrh_afast_raw
    WHERE nome = ''
       OR tipo NOT IN ('AFASTAMENTO_MEDICO', 'LICENCA_MATERNIDADE',
                       'LICENCA_NAO_REMUNERADA', 'FERIAS')
       OR inicio_txt !~ '^\d{4}-\d{2}-\d{2}$'
       OR (fim_txt <> '' AND fim_txt !~ '^\d{4}-\d{2}-\d{2}$');

    INSERT INTO mrh_pendencias
    SELECT linha, 'DESLIGAMENTO',
           CASE
             WHEN nome = '' THEN 'NOME_AUSENTE'
             WHEN loja_txt <> '' AND loja_txt !~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
               THEN 'LOJA_INVALIDA'
             ELSE 'DATA_DESLIGAMENTO_INVALIDA'
           END
    FROM mrh_desl_raw
    WHERE nome = ''
       OR (loja_txt <> '' AND loja_txt !~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
       OR desl_txt !~ '^\d{4}-\d{2}-\d{2}$';

    IF EXISTS (SELECT 1 FROM mrh_pendencias) THEN
        SELECT jsonb_agg(jsonb_build_object(
                   'linha', linha, 'origem', origem, 'codigo', codigo)
                   ORDER BY origem, linha)
          INTO v_pendencias
        FROM mrh_pendencias;
        RETURN jsonb_build_object(
            'aplicado', false, 'validar_apenas', p_validar_apenas,
            'error', 'Pendencias impedem a importacao.',
            'pendencias', v_pendencias);
    END IF;

    -- Componentes fora de faixa, ainda sem chamar to_date.
    INSERT INTO mrh_pendencias
    SELECT linha, 'AFASTAMENTO',
           CASE WHEN substring(inicio_txt, 1, 4)::integer NOT BETWEEN 1900 AND 2100
                  OR substring(inicio_txt, 6, 2)::integer NOT BETWEEN 1 AND 12
                  OR substring(inicio_txt, 9, 2)::integer NOT BETWEEN 1 AND 31
                THEN 'DATA_INICIO_INVALIDA' ELSE 'DATA_FIM_INVALIDA' END
    FROM mrh_afast_raw
    WHERE substring(inicio_txt, 1, 4)::integer NOT BETWEEN 1900 AND 2100
       OR substring(inicio_txt, 6, 2)::integer NOT BETWEEN 1 AND 12
       OR substring(inicio_txt, 9, 2)::integer NOT BETWEEN 1 AND 31
       OR (fim_txt <> '' AND (
           substring(fim_txt, 1, 4)::integer NOT BETWEEN 1900 AND 2100
        OR substring(fim_txt, 6, 2)::integer NOT BETWEEN 1 AND 12
        OR substring(fim_txt, 9, 2)::integer NOT BETWEEN 1 AND 31));

    INSERT INTO mrh_pendencias
    SELECT linha, 'DESLIGAMENTO', 'DATA_DESLIGAMENTO_INVALIDA'
    FROM mrh_desl_raw
    WHERE substring(desl_txt, 1, 4)::integer NOT BETWEEN 1900 AND 2100
       OR substring(desl_txt, 6, 2)::integer NOT BETWEEN 1 AND 12
       OR substring(desl_txt, 9, 2)::integer NOT BETWEEN 1 AND 31;

    IF EXISTS (SELECT 1 FROM mrh_pendencias) THEN
        SELECT jsonb_agg(jsonb_build_object(
                   'linha', linha, 'origem', origem, 'codigo', codigo)
                   ORDER BY origem, linha)
          INTO v_pendencias
        FROM mrh_pendencias;
        RETURN jsonb_build_object(
            'aplicado', false, 'validar_apenas', p_validar_apenas,
            'error', 'Pendencias impedem a importacao.',
            'pendencias', v_pendencias);
    END IF;

    -- Round-trip detecta 31/02 e similares; agora to_date recebe somente
    -- componentes numericos dentro das faixas basicas.
    INSERT INTO mrh_pendencias
    SELECT linha, 'AFASTAMENTO',
           CASE WHEN pg_catalog.to_char(pg_catalog.to_date(inicio_txt, 'YYYY-MM-DD'),
                                        'YYYY-MM-DD') <> inicio_txt
                THEN 'DATA_INICIO_INVALIDA'
                WHEN fim_txt <> '' AND pg_catalog.to_char(
                     pg_catalog.to_date(fim_txt, 'YYYY-MM-DD'), 'YYYY-MM-DD') <> fim_txt
                THEN 'DATA_FIM_INVALIDA'
                ELSE 'ORDEM_DATAS_INVALIDA' END
    FROM mrh_afast_raw
    WHERE pg_catalog.to_char(pg_catalog.to_date(inicio_txt, 'YYYY-MM-DD'),
                             'YYYY-MM-DD') <> inicio_txt
       OR (fim_txt <> '' AND pg_catalog.to_char(
           pg_catalog.to_date(fim_txt, 'YYYY-MM-DD'), 'YYYY-MM-DD') <> fim_txt)
       OR (fim_txt <> '' AND pg_catalog.to_date(fim_txt, 'YYYY-MM-DD')
                               <= pg_catalog.to_date(inicio_txt, 'YYYY-MM-DD'));

    INSERT INTO mrh_pendencias
    SELECT linha, 'DESLIGAMENTO', 'DATA_DESLIGAMENTO_INVALIDA'
    FROM mrh_desl_raw
    WHERE pg_catalog.to_char(pg_catalog.to_date(desl_txt, 'YYYY-MM-DD'),
                             'YYYY-MM-DD') <> desl_txt;

    IF EXISTS (SELECT 1 FROM mrh_pendencias) THEN
        SELECT jsonb_agg(jsonb_build_object(
                   'linha', linha, 'origem', origem, 'codigo', codigo)
                   ORDER BY origem, linha)
          INTO v_pendencias
        FROM mrh_pendencias;
        RETURN jsonb_build_object(
            'aplicado', false, 'validar_apenas', p_validar_apenas,
            'error', 'Pendencias impedem a importacao.',
            'pendencias', v_pendencias);
    END IF;

    CREATE TEMP TABLE mrh_afast ON COMMIT DROP AS
    SELECT linha, nome, nn, tipo,
           inicio_txt::date AS data_inicio,
           nullif(fim_txt, '')::date AS data_fim
    FROM mrh_afast_raw;

    CREATE TEMP TABLE mrh_desl ON COMMIT DROP AS
    SELECT linha, nome, nn, nullif(loja_txt, '')::uuid AS loja_id,
           desl_txt::date AS data_desligamento
    FROM mrh_desl_raw;

    INSERT INTO mrh_pendencias
    SELECT min(linha), 'AFASTAMENTO', 'PESSOA_DUPLICADA'
    FROM mrh_afast GROUP BY nn HAVING count(*) > 1;

    INSERT INTO mrh_pendencias
    SELECT min(linha), 'DESLIGAMENTO', 'PESSOA_DUPLICADA'
    FROM mrh_desl GROUP BY nn HAVING count(*) > 1;

    INSERT INTO mrh_pendencias
    SELECT a.linha, 'AFASTAMENTO', 'PESSOA_NAO_ENCONTRADA'
    FROM mrh_afast a
    WHERE NOT EXISTS (SELECT 1 FROM public.consultores c
                      WHERE upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g')) = a.nn)
      AND NOT EXISTS (SELECT 1 FROM public.supervisores s
                      WHERE upper(regexp_replace(btrim(s.nome), '[[:space:]]+', ' ', 'g')) = a.nn)
      AND NOT EXISTS (SELECT 1 FROM public.consultor_vigencia v WHERE v.nome_normalizado = a.nn)
      AND NOT EXISTS (SELECT 1 FROM public.supervisor_vigencia v WHERE v.nome_normalizado = a.nn);

    INSERT INTO mrh_pendencias
    SELECT d.linha, 'DESLIGAMENTO', 'PESSOA_NAO_ENCONTRADA'
    FROM mrh_desl d
    WHERE NOT EXISTS (SELECT 1 FROM public.consultores c
                      WHERE upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g')) = d.nn)
      AND NOT EXISTS (SELECT 1 FROM public.supervisores s
                      WHERE upper(regexp_replace(btrim(s.nome), '[[:space:]]+', ' ', 'g')) = d.nn)
      AND NOT EXISTS (SELECT 1 FROM public.consultor_vigencia v WHERE v.nome_normalizado = d.nn)
      AND NOT EXISTS (SELECT 1 FROM public.supervisor_vigencia v WHERE v.nome_normalizado = d.nn);

    INSERT INTO mrh_pendencias
    SELECT d.linha, 'DESLIGAMENTO', 'LOJA_NAO_ENCONTRADA'
    FROM mrh_desl d
    WHERE d.loja_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM public.lojas l WHERE l.id = d.loja_id);

    -- Correcao humana e fato posterior de producao vencem o arquivo.
    INSERT INTO mrh_pendencias
    SELECT DISTINCT a.linha, 'AFASTAMENTO', 'CORRECAO_MANUAL_EXISTENTE'
    FROM mrh_afast a JOIN public.consultor_afastamento ca
      ON ca.nome_normalizado = a.nn
     AND (ca.data_fim IS NULL OR ca.data_inicio = a.data_inicio)
    WHERE ca.origem = 'MANUAL';

    INSERT INTO mrh_pendencias
    SELECT DISTINCT d.linha, 'DESLIGAMENTO', 'CORRECAO_MANUAL_EXISTENTE'
    FROM mrh_desl d
    WHERE EXISTS (SELECT 1 FROM public.consultor_vigencia v
                  WHERE v.nome_normalizado = d.nn AND v.vigencia_fim IS NULL
                    AND v.origem = 'MANUAL')
       OR EXISTS (SELECT 1 FROM public.consultor_afastamento a
                  WHERE a.nome_normalizado = d.nn AND a.data_fim IS NULL
                    AND a.origem = 'MANUAL');

    INSERT INTO mrh_pendencias
    SELECT DISTINCT d.linha, 'DESLIGAMENTO', 'PRODUCAO_POSTERIOR_OU_IGUAL'
    FROM mrh_desl d
    JOIN public.consultores c
      ON upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g')) = d.nn
    JOIN public.contratos ct ON ct.consultor_id = c.id
    WHERE ct.data_cadastro::date >= d.data_desligamento;

    INSERT INTO mrh_pendencias
    SELECT DISTINCT d.linha, 'DESLIGAMENTO', 'JANELA_INCOMPATIVEL'
    FROM mrh_desl d
    WHERE EXISTS (SELECT 1 FROM public.consultor_vigencia v
                  WHERE v.nome_normalizado = d.nn AND v.vigencia_fim IS NULL
                    AND v.vigencia_inicio >= d.data_desligamento)
       OR EXISTS (SELECT 1 FROM public.supervisor_vigencia v
                  WHERE v.nome_normalizado = d.nn AND v.vigencia_fim IS NULL
                    AND v.vigencia_inicio >= d.data_desligamento)
       OR EXISTS (SELECT 1 FROM public.consultor_afastamento a
                  WHERE a.nome_normalizado = d.nn AND a.data_fim IS NULL
                    AND a.data_inicio >= d.data_desligamento);

    INSERT INTO mrh_pendencias
    SELECT DISTINCT d.linha, 'DESLIGAMENTO', 'ORDEM_MOVIMENTACOES_INVALIDA'
    FROM mrh_desl d JOIN mrh_afast a ON a.nn = d.nn
    WHERE a.data_inicio >= d.data_desligamento;

    IF EXISTS (SELECT 1 FROM mrh_pendencias) THEN
        SELECT jsonb_agg(jsonb_build_object(
                   'linha', linha, 'origem', origem, 'codigo', codigo)
                   ORDER BY origem, linha)
          INTO v_pendencias
        FROM (SELECT DISTINCT linha, origem, codigo FROM mrh_pendencias) p;
        RETURN jsonb_build_object(
            'aplicado', false, 'validar_apenas', p_validar_apenas,
            'error', 'Pendencias impedem a importacao.',
            'pendencias', v_pendencias,
            'afastamentos_recebidos', v_afast_len,
            'desligamentos_recebidos', v_desl_len);
    END IF;

    IF p_validar_apenas THEN
        RETURN jsonb_build_object(
            'aplicado', false, 'validar_apenas', true, 'error', NULL,
            'pendencias', '[]'::jsonb,
            'afastamentos_recebidos', v_afast_len,
            'desligamentos_recebidos', v_desl_len);
    END IF;

    -- Afastamentos: evento exato ja fechado por producao nao reabre.
    -- Isso torna a repeticao do mesmo arquivo um no-op real.
    FOR v_row IN SELECT * FROM mrh_afast ORDER BY linha LOOP
        v_id := NULL;
        SELECT a.id, a.tipo, a.data_inicio, a.data_fim
          INTO v_id, v_tipo_atual, v_inicio_atual, v_fim_atual
        FROM public.consultor_afastamento a
        WHERE a.nome_normalizado = v_row.nn
          AND a.data_inicio = v_row.data_inicio
        ORDER BY a.created_at, a.id
        LIMIT 1;

        IF v_id IS NULL THEN
            SELECT a.id, a.tipo, a.data_inicio, a.data_fim
              INTO v_id, v_tipo_atual, v_inicio_atual, v_fim_atual
            FROM public.consultor_afastamento a
            WHERE a.nome_normalizado = v_row.nn AND a.data_fim IS NULL
            LIMIT 1;
        END IF;

        IF v_id IS NULL THEN
            INSERT INTO public.consultor_afastamento
                (nome, tipo, data_inicio, data_fim, origem)
            VALUES (v_row.nome, v_row.tipo, v_row.data_inicio,
                    v_row.data_fim, 'ETL');
            v_afast_inseridos := v_afast_inseridos + 1;
        ELSIF v_tipo_atual IS DISTINCT FROM v_row.tipo
           OR (v_fim_atual IS NULL AND v_inicio_atual IS DISTINCT FROM v_row.data_inicio)
           OR (v_row.data_fim IS NOT NULL AND v_fim_atual IS DISTINCT FROM v_row.data_fim) THEN
            UPDATE public.consultor_afastamento
               SET nome = v_row.nome,
                   tipo = v_row.tipo,
                   data_inicio = v_row.data_inicio,
                   data_fim = coalesce(v_row.data_fim, data_fim),
                   origem = 'ETL'
             WHERE id = v_id;
            v_afast_atualizados := v_afast_atualizados + 1;
        ELSE
            v_afast_inalterados := v_afast_inalterados + 1;
        END IF;
    END LOOP;

    -- Desligamento encerra todos os papeis atuais da pessoa. A loja do
    -- arquivo e informativa e opcional (099): a identidade e global por
    -- nome, como nos tres ledgers existentes.
    UPDATE public.consultor_vigencia v
       SET vigencia_fim = d.data_desligamento, origem = 'ETL'
      FROM mrh_desl d
     WHERE v.nome_normalizado = d.nn AND v.vigencia_fim IS NULL
       AND v.vigencia_inicio < d.data_desligamento;
    GET DIAGNOSTICS v_desl_consultores = ROW_COUNT;

    UPDATE public.supervisor_vigencia v
       SET vigencia_fim = d.data_desligamento
      FROM mrh_desl d
     WHERE v.nome_normalizado = d.nn AND v.vigencia_fim IS NULL
       AND v.vigencia_inicio < d.data_desligamento;
    GET DIAGNOSTICS v_desl_supervisores = ROW_COUNT;

    UPDATE public.consultor_afastamento a
       SET data_fim = d.data_desligamento
      FROM mrh_desl d
     WHERE a.nome_normalizado = d.nn AND a.data_fim IS NULL
       AND a.data_inicio < d.data_desligamento;
    GET DIAGNOSTICS v_desl_afast = ROW_COUNT;

    UPDATE public.consultores c SET status = 'Desligado (a)'
    FROM mrh_desl d
    WHERE upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g')) = d.nn
      AND c.status IS DISTINCT FROM 'Desligado (a)';
    GET DIAGNOSTICS v_desl_cadastros = ROW_COUNT;

    DELETE FROM public.supervisores s USING mrh_desl d
    WHERE upper(regexp_replace(btrim(s.nome), '[[:space:]]+', ' ', 'g')) = d.nn;

    -- Producao somente fecha ausencia; nunca a cria.
    v_afast_prod := public.fn_fechar_afastamentos_por_producao();

    RETURN jsonb_build_object(
        'aplicado', true, 'validar_apenas', false, 'error', NULL,
        'pendencias', '[]'::jsonb,
        'afastamentos', jsonb_build_object(
            'recebidos', v_afast_len, 'inseridos', v_afast_inseridos,
            'atualizados', v_afast_atualizados,
            'inalterados', v_afast_inalterados,
            'fechados_por_producao', v_afast_prod),
        'desligamentos', jsonb_build_object(
            'recebidos', v_desl_len,
            'vigencias_consultor_fechadas', v_desl_consultores,
            'vigencias_supervisor_fechadas', v_desl_supervisores,
            'cadastros_consultor_atualizados', v_desl_cadastros,
            'afastamentos_fechados', v_desl_afast));
END;
$fn$;

COMMENT ON FUNCTION public.fn_movimentacoes_rh_import(jsonb, jsonb, boolean) IS
    'Importa afastamentos e desligamentos em uma transacao. Dry-run por '
    'padrao; validacao total antes da escrita; retorno somente agregado e '
    'pendencias por numero de linha, sem tipo/observacao/nome sensivel. '
    'loja_id no desligamento e opcional (099) e nao participa da '
    'identificacao da pessoa.';

REVOKE ALL ON FUNCTION public.fn_movimentacoes_rh_import(jsonb, jsonb, boolean)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_movimentacoes_rh_import(jsonb, jsonb, boolean)
    TO service_role;

-- Validacao operacional (nao aplicar dados reais junto com a migration):
-- SELECT public.fn_movimentacoes_rh_import('[]'::jsonb, '[]'::jsonb, true);
-- Esperado: recusado por nao haver movimentacoes.
--
-- Desligamento sem loja passa a validacao sintatica (a pendencia
-- esperada e PESSOA_NAO_ENCONTRADA, nao LOJA_INVALIDA):
-- SELECT public.fn_movimentacoes_rh_import('[]'::jsonb, jsonb_build_array(
--     jsonb_build_object('linha', 5, 'nome', 'NOME QUE NAO EXISTE',
--                        'data_desligamento', '2026-04-30')), true);
--
-- Loja malformada continua recusada com LOJA_INVALIDA:
-- SELECT public.fn_movimentacoes_rh_import('[]'::jsonb, jsonb_build_array(
--     jsonb_build_object('linha', 5, 'nome', 'X', 'loja_id', 'nao-e-uuid',
--                        'data_desligamento', '2026-04-30')), true);
-- O angry-man sempre chama primeiro com p_validar_apenas=true e somente
-- chama novamente com false quando `pendencias` esta vazio.
