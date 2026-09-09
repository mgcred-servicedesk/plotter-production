-- =====================================================
-- Migracao 114: o import de RH passa a respeitar o ledger de supervisor
-- Data: 2026-09-09
-- Depende de: 113 (supervisor_vigencia.origem), 100 (versao vigente da
--             fn_movimentacoes_rh_import)
--
-- O BURACO
-- --------
-- Desde a 097 esta funcao CONSULTA dois ledgers na guarda de correcao
-- humana (`CORRECAO_MANUAL_EXISTENTE`: consultor_vigencia e
-- consultor_afastamento) e ESCREVE em tres — o `UPDATE` de
-- supervisor_vigencia nao tinha condicao nenhuma. Nao era descuido de
-- quem escreveu a 097: a coluna `origem` nao existia naquela tabela, e
-- sem ela nao havia o que consultar. A 113 criou a coluna; esta migration
-- e a metade que faltava.
--
-- Efeito concreto enquanto o buraco existir: a promocao do HUGO
-- (migration 110, aplicada em 2026-09-08 — supervisao de HELP MADUREIRA
-- desde 01/09) e desfeita por qualquer arquivo de RH que traga o nome
-- dele numa linha de desligamento. Silenciosamente: sem pendencia, sem
-- divergencia, sem linha no envelope.
--
--
-- AS DUAS MUDANCAS, NENHUMA NA ASSINATURA
-- ----------------------------------------
--   1. `CORRECAO_MANUAL_EXISTENTE` ganha o terceiro EXISTS, sobre
--      supervisor_vigencia com origem = 'MANUAL'. A linha vira pendencia
--      e — como toda pendencia nesta funcao — para a carga inteira, que
--      e o comportamento tudo-ou-nada ja documentado no §4.4 do
--      docs/HEADCOUNT_ETL.md.
--
--   2. O `UPDATE` de supervisor_vigencia carimba `origem`, pela mesma
--      regra que a 100 aplicou ao consultor: a procedencia diz de onde
--      veio a DATA. Fechou na data do arquivo, 'ETL'; fechou na data
--      derivada do ultimo contrato, 'BACKFILL_PRODUCAO'.
--
-- Por que a linha 1 nao muda numero nenhum hoje: depois da 113 TODAS as
-- 59 linhas de supervisor_vigencia sao 'LEGADO', nenhuma e 'MANUAL', e o
-- EXISTS novo nao casa com nada. A guarda comeca a valer sobre o que for
-- escrito daqui pra frente — que e exatamente a decisao do usuario em
-- 2026-09-09 (sem backfill de procedencia).
--
-- ASSINATURA INALTERADA (jsonb, jsonb, boolean): e CREATE OR REPLACE da
-- mesma funcao, nao sobrecarga. Sem redeploy da Edge Function, sem
-- mudanca na whitelist do angry-man.
--
-- Executar no Supabase SQL Editor, depois da 113.
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
    v_desl_producao    integer := 0;
    v_divergencias     jsonb;
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

    -- `data_efetiva` e a data que vai para os ledgers. Ela so diverge da
    -- data do arquivo quando ha producao em ou depois dela: nesse caso o
    -- corte e o dia SEGUINTE ao ultimo contrato, porque vigencia_fim e
    -- exclusivo e o dia do ultimo contrato foi trabalhado.
    CREATE TEMP TABLE mrh_desl ON COMMIT DROP AS
    SELECT r.linha, r.nome, r.nn, nullif(r.loja_txt, '')::uuid AS loja_id,
           r.desl_txt::date AS data_desligamento,
           p.ultima_producao,
           CASE WHEN p.ultima_producao IS NULL THEN r.desl_txt::date
                ELSE greatest(r.desl_txt::date, p.ultima_producao + 1)
           END AS data_efetiva,
           CASE WHEN p.ultima_producao IS NULL THEN 0
                ELSE (p.ultima_producao - r.desl_txt::date)
           END AS dias_apos
    FROM mrh_desl_raw r
    LEFT JOIN LATERAL (
        -- Filtro de data obrigatorio em `contratos`; a propria condicao
        -- da regra ja o fornece.
        SELECT max(ct.data_cadastro::date) AS ultima_producao
        FROM public.consultores c
        JOIN public.contratos ct ON ct.consultor_id = c.id
        WHERE upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g')) = r.nn
          AND ct.data_cadastro::date >= r.desl_txt::date
    ) p ON true;

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
                    AND a.origem = 'MANUAL')
       -- MUDANCA 114: o terceiro ledger entra na guarda. Ate aqui a
       -- funcao consultava dois ledgers e ESCREVIA em tres — o UPDATE
       -- de supervisor_vigencia, mais abaixo, nao tinha condicao
       -- nenhuma. Uma promocao registrada a mao (110) era desfeita por
       -- um desligamento vindo do arquivo, sem aparecer em pendencia
       -- nem em divergencia.
       OR EXISTS (SELECT 1 FROM public.supervisor_vigencia v
                  WHERE v.nome_normalizado = d.nn AND v.vigencia_fim IS NULL
                    AND v.origem = 'MANUAL');

    -- Ate 30 dias a janela fecha pela producao e a linha e reportada como
    -- divergencia. Acima disso nao ha aviso previo que explique, e a
    -- carga para.
    INSERT INTO mrh_pendencias
    SELECT d.linha, 'DESLIGAMENTO', 'PRODUCAO_POSTERIOR_OU_IGUAL'
    FROM mrh_desl d
    WHERE d.dias_apos > 30;

    INSERT INTO mrh_pendencias
    SELECT DISTINCT d.linha, 'DESLIGAMENTO', 'JANELA_INCOMPATIVEL'
    FROM mrh_desl d
    WHERE EXISTS (SELECT 1 FROM public.consultor_vigencia v
                  WHERE v.nome_normalizado = d.nn AND v.vigencia_fim IS NULL
                    AND v.vigencia_inicio >= d.data_efetiva)
       OR EXISTS (SELECT 1 FROM public.supervisor_vigencia v
                  WHERE v.nome_normalizado = d.nn AND v.vigencia_fim IS NULL
                    AND v.vigencia_inicio >= d.data_efetiva)
       OR EXISTS (SELECT 1 FROM public.consultor_afastamento a
                  WHERE a.nome_normalizado = d.nn AND a.data_fim IS NULL
                    AND a.data_inicio >= d.data_efetiva);

    INSERT INTO mrh_pendencias
    SELECT DISTINCT d.linha, 'DESLIGAMENTO', 'ORDEM_MOVIMENTACOES_INVALIDA'
    FROM mrh_desl d JOIN mrh_afast a ON a.nn = d.nn
    WHERE a.data_inicio >= d.data_efetiva;

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

    -- Sem nome: o envelope e agregado por desenho e pode ser logado
    -- inteiro. A linha da planilha basta para a conferencia.
    SELECT count(*), jsonb_agg(jsonb_build_object(
               'linha', linha, 'codigo', 'FECHADO_POR_PRODUCAO',
               'dias', dias_apos, 'data_arquivo', data_desligamento,
               'data_aplicada', data_efetiva) ORDER BY linha)
      INTO v_desl_producao, v_divergencias
    FROM mrh_desl WHERE ultima_producao IS NOT NULL;

    IF p_validar_apenas THEN
        RETURN jsonb_build_object(
            'aplicado', false, 'validar_apenas', true, 'error', NULL,
            'pendencias', '[]'::jsonb,
            'divergencias', coalesce(v_divergencias, '[]'::jsonb),
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
       SET vigencia_fim = d.data_efetiva,
           -- A origem diz de onde veio a DATA, nao de onde veio o evento.
           origem = CASE WHEN d.ultima_producao IS NULL THEN 'ETL'
                         ELSE 'BACKFILL_PRODUCAO' END
      FROM mrh_desl d
     WHERE v.nome_normalizado = d.nn AND v.vigencia_fim IS NULL
       AND v.vigencia_inicio < d.data_efetiva;
    GET DIAGNOSTICS v_desl_consultores = ROW_COUNT;

    -- Mesma regra de procedencia do consultor logo acima: a origem diz
    -- de onde veio a DATA. `origem <> 'MANUAL'` e redundante com a
    -- pendencia (a linha inteira ja teria parado a carga) e fica como
    -- rede: se um dia a pendencia virar aviso, o UPDATE nao passa a
    -- apagar correcao humana em silencio por conta disso.
    UPDATE public.supervisor_vigencia v
       SET vigencia_fim = d.data_efetiva,
           origem = CASE WHEN d.ultima_producao IS NULL THEN 'ETL'
                         ELSE 'BACKFILL_PRODUCAO' END
      FROM mrh_desl d
     WHERE v.nome_normalizado = d.nn AND v.vigencia_fim IS NULL
       AND v.vigencia_inicio < d.data_efetiva
       AND v.origem <> 'MANUAL';
    GET DIAGNOSTICS v_desl_supervisores = ROW_COUNT;

    UPDATE public.consultor_afastamento a
       SET data_fim = d.data_efetiva
      FROM mrh_desl d
     WHERE a.nome_normalizado = d.nn AND a.data_fim IS NULL
       AND a.data_inicio < d.data_efetiva;
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
        'divergencias', coalesce(v_divergencias, '[]'::jsonb),
        'desligamentos', jsonb_build_object(
            'recebidos', v_desl_len,
            'fechados_por_producao', v_desl_producao,
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
    'identificacao da pessoa. Havendo producao em ou depois da data do '
    'desligamento, a vigencia fecha no dia seguinte ao ultimo contrato e '
    'a linha sai em `divergencias`; acima de 30 dias vira pendencia (100). '
    'A guarda CORRECAO_MANUAL_EXISTENTE cobre os TRES ledgers, incluindo '
    'supervisor_vigencia, e o fechamento de supervisor carimba origem '
    '(114).';

REVOKE ALL ON FUNCTION public.fn_movimentacoes_rh_import(jsonb, jsonb, boolean)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_movimentacoes_rh_import(jsonb, jsonb, boolean)
    TO service_role;



-- =====================================================
-- Verificacao operacional depois da aplicacao
-- =====================================================
--
-- 1) A guarda enxerga o terceiro ledger. Em ambiente de teste, marque uma
--    supervisao aberta como MANUAL e mande a pessoa num desligamento com
--    p_validar_apenas = true:
--
--    -- UPDATE supervisor_vigencia SET origem = 'MANUAL' WHERE id = '<uuid>';
--    -- SELECT public.fn_movimentacoes_rh_import(
--    --     '[]'::jsonb,
--    --     jsonb_build_array(jsonb_build_object(
--    --         'linha', 5, 'nome', '<NOME>',
--    --         'data_desligamento', '2026-10-01')),
--    --     true);
--    --
--    -- esperado: aplicado=false e pendencias contendo
--    --   {"linha":5,"origem":"DESLIGAMENTO","codigo":"CORRECAO_MANUAL_EXISTENTE"}
--    -- ANTES desta migration o mesmo payload passava e o UPDATE fechava
--    -- a janela.
--
-- 2) O carimbo de procedencia:
--
--    SELECT origem, count(*) FROM supervisor_vigencia GROUP BY origem;
--    -- antes da primeira carga pos-114: so LEGADO
--    -- depois de uma carga com desligamento: aparecem ETL e/ou
--    --   BACKFILL_PRODUCAO nas janelas que ela fechou
--
-- 3) Nada mudou para quem nao tem correcao manual — a contagem de
--    supervisores fechados no envelope segue igual para o mesmo arquivo:
--
--    -- SELECT public.fn_movimentacoes_rh_import(<afast>, <desl>, true);
--    -- comparar `desligamentos.vigencias_supervisor_fechadas` com a
--    -- execucao anterior a esta migration: mesmo numero.
