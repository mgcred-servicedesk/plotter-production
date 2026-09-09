-- =====================================================
-- Migracao 120: data impossivel vira pendencia, nao excecao
-- Data: 2026-09-09
-- Depende de: 114 (versao vigente da fn_movimentacoes_rh_import),
--             117 (fn_movimentacoes_replace)
--
-- O DEFEITO, MEDIDO
-- -----------------
-- As duas funcoes validavam data em tres fases para nunca entregar texto
-- malformado a uma conversao. A terceira fase era um round-trip:
--
--     to_char(to_date(t, 'YYYY-MM-DD'), 'YYYY-MM-DD') <> t
--
-- escrito para pegar 2026-02-31, que passa pelo regex e passa pela faixa
-- de componentes (dia 31 esta entre 1 e 31). A ideia era que `to_date`
-- normalizasse 31/02 para 03/03 e o texto deixasse de bater.
--
-- Ele nao normaliza. Nesta versao do PostgreSQL `to_date` LANCA para
-- valor fora de faixa, entao a comparacao nunca chega a acontecer e a
-- excecao sobe pela funcao inteira. Medido em 2026-09-09 contra o banco,
-- por chamada direta em dry-run:
--
--   fn_movimentacoes_rh_import  afastamento  2026-02-31  -> 22008
--   fn_movimentacoes_rh_import  desligamento 2026-04-31  -> 22008
--   fn_movimentacoes_rh_import  desligamento 2026-02-29  -> 22008
--   fn_movimentacoes_replace    transferencia 2026-02-31 -> 22008
--
-- `22008 date/time field value out of range`. O envelope de pendencias
-- nunca e devolvido: o dry-run inteiro morre.
--
-- POR QUE ISSO IMPORTA MAIS DO QUE PARECE
-- ----------------------------------------
-- O contrato das duas portas e "validacao total antes de qualquer
-- escrita, pendencia por numero de linha". Uma data impossivel quebra
-- exatamente esse contrato: em vez de "linha 12: data de desligamento
-- invalida", quem importa recebe um erro opaco de banco, sem linha e sem
-- causa. E o arquivo de RH e digitado a mao a partir de e-mails — 31/04 e
-- erro de digitacao comum, nao caso de laboratorio.
--
-- Nada e escrito errado por causa disso: a transacao aborta. O defeito e
-- de diagnostico, e o custo e o tempo de descobrir qual linha da planilha
-- causou.
--
--
-- A CORRECAO
-- ----------
-- Comparar o dia com o ULTIMO DIA REAL DO MES, sem chamar `to_date`
-- nenhuma vez:
--
--     substring(t, 9, 2)::integer > extract(day FROM (
--         make_date(ano, mes, 1) + interval '1 month' - interval '1 day'))
--
-- `make_date(ano, mes, 1)` e seguro porque ano e mes JA passaram pela
-- checagem de faixa do bloco anterior, e o dia 1 existe em todo mes.
-- Somar um mes e voltar um dia da 28 ou 29 em fevereiro conforme o ano,
-- 30 em abril, 31 em janeiro — sem tabela de meses codificada.
--
-- Depois dessa checagem a data e integralmente valida, entao o `::date`
-- que vem adiante nao pode falhar. Na fn_movimentacoes_rh_import a
-- comparacao de ORDEM (`fim <= inicio`) foi separada num bloco proprio,
-- DEPOIS do portao de pendencias — antes ela dividia o mesmo INSERT com o
-- round-trip, e era por isso que uma data impossivel a alcancava.
--
-- ASSINATURAS INALTERADAS nas duas funcoes: CREATE OR REPLACE, sem DROP,
-- sem redeploy da Edge Function, sem mudanca na whitelist.
--
-- NENHUM DADO MUDA. As duas funcoes so passam a recusar melhor o que ja
-- recusavam — o que antes abortava com erro de banco agora volta como
-- pendencia de linha. Carga que ja funcionava continua identica.
--
-- Executar no Supabase SQL Editor, depois da 119.
-- =====================================================


-- ===========================================
-- 1. fn_movimentacoes_rh_import (afastamentos e desligamentos)
-- ===========================================

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

    -- MUDANCA 120 — o dia contra o ULTIMO DIA DO MES, sem to_date.
    --
    -- Aqui ficava um round-trip `to_char(to_date(t)) <> t`, escrito para
    -- pegar 31/02. Ele NAO pega: nesta versao do PostgreSQL `to_date`
    -- LANCA em vez de normalizar, entao a comparacao nunca acontece e a
    -- excecao escapa da funcao. Medido em 2026-09-09 contra o banco:
    -- 31/02, 31/04 e 29/02 de ano nao bissexto devolviam
    -- `22008 date/time field value out of range` em vez de pendencia.
    --
    -- O efeito pratico e ruim justamente onde este arquivo vive: o RH e
    -- digitado a mao a partir de e-mails, onde 31/04 acontece, e quem
    -- importa via um erro opaco de banco em vez de "linha 12: data
    -- invalida".
    --
    -- A checagem nova nao chama to_date nenhuma vez. `make_date(y, m, 1)`
    -- e seguro porque ano e mes JA passaram pela faixa no bloco anterior,
    -- e o dia 1 existe em todo mes. Somar um mes e voltar um dia da o
    -- ultimo dia real — 28 ou 29 em fevereiro, conforme o ano.
    INSERT INTO mrh_pendencias
    SELECT linha, 'AFASTAMENTO',
           CASE WHEN substring(inicio_txt, 9, 2)::integer > pg_catalog.date_part('day',
                         pg_catalog.make_date(
                             substring(inicio_txt, 1, 4)::integer,
                             substring(inicio_txt, 6, 2)::integer, 1)
                             + interval '1 month' - interval '1 day')
                THEN 'DATA_INICIO_INVALIDA'
                ELSE 'DATA_FIM_INVALIDA' END
    FROM mrh_afast_raw
    WHERE substring(inicio_txt, 9, 2)::integer > pg_catalog.date_part('day',
              pg_catalog.make_date(
                  substring(inicio_txt, 1, 4)::integer,
                  substring(inicio_txt, 6, 2)::integer, 1)
                  + interval '1 month' - interval '1 day')
       OR (fim_txt <> '' AND substring(fim_txt, 9, 2)::integer > pg_catalog.date_part('day',
              pg_catalog.make_date(
                  substring(fim_txt, 1, 4)::integer,
                  substring(fim_txt, 6, 2)::integer, 1)
                  + interval '1 month' - interval '1 day'));

    INSERT INTO mrh_pendencias
    SELECT linha, 'DESLIGAMENTO', 'DATA_DESLIGAMENTO_INVALIDA'
    FROM mrh_desl_raw
    WHERE substring(desl_txt, 9, 2)::integer > pg_catalog.date_part('day',
              pg_catalog.make_date(
                  substring(desl_txt, 1, 4)::integer,
                  substring(desl_txt, 6, 2)::integer, 1)
                  + interval '1 month' - interval '1 day');

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

    -- Ordem das datas. Separada da validade e DEPOIS do portao acima:
    -- so agora o cast `::date` e seguro para as duas pontas. Antes da
    -- 120 esta comparacao dividia o mesmo INSERT com o round-trip, e era
    -- por isso que uma data impossivel a alcancava.
    INSERT INTO mrh_pendencias
    SELECT linha, 'AFASTAMENTO', 'ORDEM_DATAS_INVALIDA'
    FROM mrh_afast_raw
    WHERE fim_txt <> '' AND fim_txt::date <= inicio_txt::date;

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


-- ===========================================
-- 2. fn_movimentacoes_replace (transferencia e cargo)
-- ===========================================

CREATE OR REPLACE FUNCTION public.fn_movimentacoes_replace(
    p_movimentos     jsonb,
    p_validar_apenas boolean DEFAULT true
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
SET statement_timeout = '120s'
AS $fn$
DECLARE
    v_len            integer;
    v_pendencias     jsonb;
    v_divergencias   jsonb;
    v_cv_fechadas    integer := 0;
    v_cv_abertas     integer := 0;
    v_sv_fechadas    integer := 0;
    v_sv_abertas     integer := 0;
    v_sv_sucessao    integer := 0;
    v_foto_ins       integer := 0;
    v_foto_del       integer := 0;
    v_row            record;
    v_loja_atual     uuid;
    v_n              integer;
BEGIN
    IF p_movimentos IS NULL OR jsonb_typeof(p_movimentos) <> 'array' THEN
        RETURN jsonb_build_object(
            'aplicado', false, 'validar_apenas', p_validar_apenas,
            'error', 'O payload deve ser um array JSON.',
            'pendencias', jsonb_build_array(jsonb_build_object(
                'linha', 0, 'codigo', 'PAYLOAD_INVALIDO')));
    END IF;

    v_len := jsonb_array_length(p_movimentos);

    IF v_len = 0 THEN
        RETURN jsonb_build_object(
            'aplicado', false, 'validar_apenas', p_validar_apenas,
            'error', 'Nenhuma movimentacao recebida.',
            'pendencias', '[]'::jsonb);
    END IF;

    -- Serializa contra outra carga de movimentacao. Chave diferente da
    -- 097 (20260831) de proposito: as duas funcoes tocam os mesmos
    -- ledgers e nao podem correr juntas.
    PERFORM pg_catalog.pg_advisory_xact_lock(20260909);

    -- `ON COMMIT DROP` so libera o nome no COMMIT: duas chamadas na MESMA
    -- transacao (dry-run e aplicacao juntos, por exemplo) falhariam com
    -- "relation already exists" antes de validar nada. Guarda igual a da
    -- 095 para `hc_plan`.
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_class c
        WHERE c.relname = 'mv_pendencias'
          AND c.relnamespace = pg_catalog.pg_my_temp_schema()
    ) THEN
        DROP TABLE pg_temp.mv_pendencias;
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_class c
        WHERE c.relname = 'mv_raw'
          AND c.relnamespace = pg_catalog.pg_my_temp_schema()
    ) THEN
        DROP TABLE pg_temp.mv_raw;
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_class c
        WHERE c.relname = 'mv'
          AND c.relnamespace = pg_catalog.pg_my_temp_schema()
    ) THEN
        DROP TABLE pg_temp.mv;
    END IF;

    CREATE TEMP TABLE mv_pendencias (
        linha  integer NOT NULL,
        codigo text    NOT NULL
    ) ON COMMIT DROP;

    CREATE TEMP TABLE mv_raw ON COMMIT DROP AS
    SELECT
        CASE WHEN coalesce(e.value->>'linha', '') ~ '^[0-9]+$'
             THEN (e.value->>'linha')::integer
             ELSE e.ordinality::integer + 1 END           AS linha,
        btrim(coalesce(e.value->>'nome', ''))             AS nome,
        upper(regexp_replace(btrim(coalesce(e.value->>'nome', '')),
                             '[[:space:]]+', ' ', 'g'))   AS nn,
        upper(btrim(coalesce(e.value->>'tipo', '')))      AS tipo,
        btrim(coalesce(e.value->>'loja_destino', ''))     AS destino_txt,
        btrim(coalesce(e.value->>'data_efetiva', ''))     AS data_txt
    FROM jsonb_array_elements(p_movimentos)
         WITH ORDINALITY AS e(value, ordinality);

    -- ---- Fase 1: sintaxe ----
    -- Separada das demais para que NENHUMA expressao tente converter
    -- texto malformado, mesmo se o otimizador reordenar predicados.
    -- Mesmo cuidado (e mesmo motivo) da 097.
    INSERT INTO mv_pendencias
    SELECT linha,
           CASE
             WHEN nome = '' THEN 'NOME_AUSENTE'
             WHEN tipo NOT IN ('TRANSFERENCIA', 'PROMOCAO', 'REBAIXAMENTO')
               THEN 'TIPO_INVALIDO'
             WHEN data_txt !~ '^\d{4}-\d{2}-\d{2}$' THEN 'DATA_INVALIDA'
             ELSE 'LOJA_INVALIDA'
           END
    FROM mv_raw
    WHERE nome = ''
       OR tipo NOT IN ('TRANSFERENCIA', 'PROMOCAO', 'REBAIXAMENTO')
       OR data_txt !~ '^\d{4}-\d{2}-\d{2}$'
       -- destino e obrigatorio em TRANSFERENCIA e PROMOCAO; opcional em
       -- REBAIXAMENTO (vazio = mantem a loja de consultor onde esta).
       OR (tipo IN ('TRANSFERENCIA', 'PROMOCAO') AND destino_txt = '')
       OR (destino_txt <> '' AND destino_txt !~
           '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$');

    IF EXISTS (SELECT 1 FROM mv_pendencias) THEN
        SELECT jsonb_agg(jsonb_build_object('linha', linha, 'codigo', codigo)
                         ORDER BY linha)
          INTO v_pendencias FROM mv_pendencias;
        RETURN jsonb_build_object(
            'aplicado', false, 'validar_apenas', p_validar_apenas,
            'error', 'Pendencias impedem a importacao.',
            'pendencias', v_pendencias, 'recebidas', v_len);
    END IF;

    -- Componentes fora de faixa, ainda sem chamar to_date.
    INSERT INTO mv_pendencias
    SELECT linha, 'DATA_INVALIDA' FROM mv_raw
    WHERE substring(data_txt, 1, 4)::integer NOT BETWEEN 1900 AND 2100
       OR substring(data_txt, 6, 2)::integer NOT BETWEEN 1 AND 12
       OR substring(data_txt, 9, 2)::integer NOT BETWEEN 1 AND 31;

    IF EXISTS (SELECT 1 FROM mv_pendencias) THEN
        SELECT jsonb_agg(jsonb_build_object('linha', linha, 'codigo', codigo)
                         ORDER BY linha)
          INTO v_pendencias FROM mv_pendencias;
        RETURN jsonb_build_object(
            'aplicado', false, 'validar_apenas', p_validar_apenas,
            'error', 'Pendencias impedem a importacao.',
            'pendencias', v_pendencias, 'recebidas', v_len);
    END IF;

    -- MUDANCA 120 — o dia contra o ULTIMO DIA DO MES, sem to_date.
    -- Mesmo defeito e mesma correcao de fn_movimentacoes_rh_import: o
    -- round-trip que estava aqui herdou o desenho da 097 e herdou junto
    -- o furo. Nesta versao do PostgreSQL `to_date` LANCA em vez de
    -- normalizar, entao 2026-02-31 escapava como excecao 22008 em vez de
    -- virar pendencia DATA_INVALIDA. Medido em 2026-09-09.
    --
    -- `make_date(y, m, 1)` e seguro: ano e mes ja passaram pela faixa no
    -- bloco anterior, e o dia 1 existe em todo mes.
    INSERT INTO mv_pendencias
    SELECT linha, 'DATA_INVALIDA' FROM mv_raw
    WHERE substring(data_txt, 9, 2)::integer > pg_catalog.date_part('day',
              pg_catalog.make_date(
                  substring(data_txt, 1, 4)::integer,
                  substring(data_txt, 6, 2)::integer, 1)
                  + interval '1 month' - interval '1 day');

    IF EXISTS (SELECT 1 FROM mv_pendencias) THEN
        SELECT jsonb_agg(jsonb_build_object('linha', linha, 'codigo', codigo)
                         ORDER BY linha)
          INTO v_pendencias FROM mv_pendencias;
        RETURN jsonb_build_object(
            'aplicado', false, 'validar_apenas', p_validar_apenas,
            'error', 'Pendencias impedem a importacao.',
            'pendencias', v_pendencias, 'recebidas', v_len);
    END IF;

    -- ---- Fase 2: semantica ----
    -- `mv` ja tem os tipos convertidos e a loja atual de cada pessoa
    -- resolvida uma vez so, para as validacoes e a aplicacao usarem a
    -- MESMA leitura. Reconsultar na aplicacao abriria janela para o
    -- estado mudar entre validar e escrever.
    CREATE TEMP TABLE mv ON COMMIT DROP AS
    SELECT
        r.linha, r.nome, r.nn, r.tipo,
        nullif(r.destino_txt, '')::uuid AS loja_destino,
        r.data_txt::date                AS data_efetiva,
        cv.id       AS cv_id,
        cv.loja_id  AS cv_loja,
        cv.vigencia_inicio AS cv_inicio,
        cv.origem   AS cv_origem,
        cv.n_abertas,
        sv.id       AS sv_id,
        sv.loja_id  AS sv_loja,
        sv.vigencia_inicio AS sv_inicio,
        sv.origem   AS sv_origem
    FROM mv_raw r
    LEFT JOIN LATERAL (
        -- A janela de consultor aberta mais recente. `n_abertas` conta
        -- todas: mais de uma e cobertura temporaria (103/111) e a funcao
        -- nao adivinha qual fechar.
        SELECT v.id, v.loja_id, v.vigencia_inicio, v.origem,
               count(*) OVER ()::integer AS n_abertas
        FROM public.consultor_vigencia v
        WHERE v.nome_normalizado = r.nn AND v.vigencia_fim IS NULL
        ORDER BY v.vigencia_inicio DESC, v.id DESC
        LIMIT 1
    ) cv ON true
    LEFT JOIN LATERAL (
        SELECT v.id, v.loja_id, v.vigencia_inicio, v.origem
        FROM public.supervisor_vigencia v
        WHERE v.nome_normalizado = r.nn AND v.vigencia_fim IS NULL
        ORDER BY v.vigencia_inicio DESC, v.id DESC
        LIMIT 1
    ) sv ON true;

    -- A mesma pessoa duas vezes na mesma carga: a segunda linha leria um
    -- estado que a primeira ja mudou, e `mv` foi resolvida ANTES de
    -- qualquer escrita. Duas movimentacoes da mesma pessoa exigem duas
    -- cargas, em ordem.
    INSERT INTO mv_pendencias
    SELECT min(linha), 'PESSOA_DUPLICADA'
    FROM mv GROUP BY nn HAVING count(*) > 1;

    INSERT INTO mv_pendencias
    SELECT m.linha, 'PESSOA_NAO_ENCONTRADA'
    FROM mv m
    WHERE NOT EXISTS (SELECT 1 FROM public.consultores c
                      WHERE upper(regexp_replace(btrim(c.nome),
                            '[[:space:]]+', ' ', 'g')) = m.nn)
      AND NOT EXISTS (SELECT 1 FROM public.supervisores s
                      WHERE upper(regexp_replace(btrim(s.nome),
                            '[[:space:]]+', ' ', 'g')) = m.nn)
      AND NOT EXISTS (SELECT 1 FROM public.consultor_vigencia v
                      WHERE v.nome_normalizado = m.nn)
      AND NOT EXISTS (SELECT 1 FROM public.supervisor_vigencia v
                      WHERE v.nome_normalizado = m.nn);

    INSERT INTO mv_pendencias
    SELECT m.linha, 'LOJA_NAO_ENCONTRADA'
    FROM mv m
    WHERE m.loja_destino IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM public.lojas l WHERE l.id = m.loja_destino);

    -- TRANSFERENCIA e PROMOCAO precisam de janela de consultor para
    -- fechar. Sem ela nao ha de onde transferir, e ABRIR sozinho
    -- inventaria um vinculo cuja data de inicio ninguem declarou.
    INSERT INTO mv_pendencias
    SELECT m.linha, 'SEM_JANELA_ABERTA'
    FROM mv m
    WHERE m.tipo IN ('TRANSFERENCIA', 'PROMOCAO') AND m.cv_id IS NULL;

    INSERT INTO mv_pendencias
    SELECT m.linha, 'SEM_SUPERVISAO_ABERTA'
    FROM mv m
    WHERE m.tipo = 'REBAIXAMENTO' AND m.sv_id IS NULL;

    -- Mais de uma janela aberta e cobertura temporaria. Qual fechar nao
    -- se deduz: para e pede decisao humana.
    INSERT INTO mv_pendencias
    SELECT m.linha, 'MULTIPLAS_JANELAS_ABERTAS'
    FROM mv m
    WHERE m.tipo IN ('TRANSFERENCIA', 'PROMOCAO')
      AND coalesce(m.n_abertas, 0) > 1;

    -- Transferir para a loja onde a pessoa ja esta e no-op disfarcado:
    -- fecharia e reabriria a mesma janela, quebrando o historico em duas
    -- sem que nada tenha mudado.
    INSERT INTO mv_pendencias
    SELECT m.linha, 'DESTINO_IGUAL_ORIGEM'
    FROM mv m
    WHERE m.tipo = 'TRANSFERENCIA' AND m.loja_destino = m.cv_loja;

    INSERT INTO mv_pendencias
    SELECT m.linha, 'JA_SUPERVISIONA_DESTINO'
    FROM mv m
    WHERE m.tipo = 'PROMOCAO' AND m.sv_id IS NOT NULL
      AND m.sv_loja = m.loja_destino;

    -- Fechar em data <= inicio violaria chk_cv_vigencia_ordem /
    -- chk_sv_vigencia_ordem. Recusa antes de tentar.
    INSERT INTO mv_pendencias
    SELECT m.linha, 'JANELA_INCOMPATIVEL'
    FROM mv m
    WHERE (m.tipo IN ('TRANSFERENCIA', 'PROMOCAO')
           AND m.cv_inicio IS NOT NULL AND m.data_efetiva <= m.cv_inicio)
       OR (m.tipo IN ('PROMOCAO', 'REBAIXAMENTO')
           AND m.sv_inicio IS NOT NULL AND m.data_efetiva <= m.sv_inicio);

    -- Correcao humana anterior nao se desfaz por carga. Vale tambem aqui:
    -- esta funcao escreve MANUAL, mas uma linha errada dela nao pode
    -- passar por cima de outra correcao MANUAL sem que alguem veja.
    -- Reaplicar de proposito exige corrigir a janela antes.
    INSERT INTO mv_pendencias
    SELECT m.linha, 'CORRECAO_MANUAL_EXISTENTE'
    FROM mv m
    WHERE (m.tipo IN ('TRANSFERENCIA', 'PROMOCAO') AND m.cv_origem = 'MANUAL'
           AND m.cv_inicio = m.data_efetiva)
       OR (m.tipo IN ('PROMOCAO', 'REBAIXAMENTO') AND m.sv_origem = 'MANUAL'
           AND m.sv_inicio = m.data_efetiva);

    IF EXISTS (SELECT 1 FROM mv_pendencias) THEN
        SELECT jsonb_agg(jsonb_build_object('linha', linha, 'codigo', codigo)
                         ORDER BY linha)
          INTO v_pendencias
        FROM (SELECT DISTINCT linha, codigo FROM mv_pendencias) p;
        RETURN jsonb_build_object(
            'aplicado', false, 'validar_apenas', p_validar_apenas,
            'error', 'Pendencias impedem a importacao.',
            'pendencias', v_pendencias, 'recebidas', v_len);
    END IF;

    -- ---- Divergencias: producao do lado errado da fronteira ----
    -- REPORTA, nao bloqueia. Ver cabecalho: uma guarda estrita teria
    -- recusado a transferencia da CAROLINA por 1 contrato avulso.
    SELECT jsonb_agg(d ORDER BY linha, d->>'codigo') INTO v_divergencias
    FROM (
        SELECT m.linha,
               jsonb_build_object(
                   'linha', m.linha,
                   'codigo', 'PRODUCAO_NA_ORIGEM_APOS_CORTE',
                   'contratos', count(*)::integer,
                   'ultimo', max(ct.data_cadastro::date)) AS d
        FROM mv m
        JOIN public.consultores cs
          ON upper(regexp_replace(btrim(cs.nome),
                   '[[:space:]]+', ' ', 'g')) = m.nn
        JOIN public.contratos ct ON ct.consultor_id = cs.id
        WHERE m.tipo IN ('TRANSFERENCIA', 'PROMOCAO')
          AND ct.loja_id = m.cv_loja
          AND ct.data_cadastro >= m.data_efetiva
        GROUP BY m.linha

        UNION ALL

        SELECT m.linha,
               jsonb_build_object(
                   'linha', m.linha,
                   'codigo', 'PRODUCAO_NO_DESTINO_ANTES_DO_CORTE',
                   'contratos', count(*)::integer,
                   'primeiro', min(ct.data_cadastro::date)) AS d
        FROM mv m
        JOIN public.consultores cs
          ON upper(regexp_replace(btrim(cs.nome),
                   '[[:space:]]+', ' ', 'g')) = m.nn
        JOIN public.contratos ct ON ct.consultor_id = cs.id
        WHERE m.tipo IN ('TRANSFERENCIA', 'PROMOCAO')
          AND ct.loja_id = m.loja_destino
          AND ct.data_cadastro < m.data_efetiva
        GROUP BY m.linha
    ) t;

    IF p_validar_apenas THEN
        RETURN jsonb_build_object(
            'aplicado', false, 'validar_apenas', true, 'error', NULL,
            'pendencias', '[]'::jsonb,
            'divergencias', coalesce(v_divergencias, '[]'::jsonb),
            'recebidas', v_len);
    END IF;

    -- ---- Fase 3: aplicacao ----
    -- Linha a linha e em ordem, porque PROMOCAO faz quatro escritas
    -- interdependentes e a sucessao do antecessor depende da data desta
    -- pessoa. Volume esperado: unidades por carga.
    FOR v_row IN SELECT * FROM mv ORDER BY linha LOOP

        -- (1) Consultor: fecha a janela atual e abre na loja nova.
        --     REBAIXAMENTO so entra aqui se `loja_destino` vier e for
        --     diferente da atual — rebaixar nao move de loja por si.
        v_loja_atual := v_row.cv_loja;

        IF v_row.tipo IN ('TRANSFERENCIA', 'PROMOCAO')
           OR (v_row.tipo = 'REBAIXAMENTO'
               AND v_row.loja_destino IS NOT NULL
               AND v_row.loja_destino IS DISTINCT FROM v_loja_atual
               AND v_row.cv_id IS NOT NULL) THEN

            -- PROMOCAO para a loja onde a pessoa JA e consultora nao
            -- mexe no vinculo: so o papel muda.
            IF v_row.loja_destino IS DISTINCT FROM v_loja_atual THEN
                UPDATE public.consultor_vigencia
                   SET vigencia_fim = v_row.data_efetiva,
                       origem       = 'MANUAL'
                 WHERE id = v_row.cv_id;
                v_cv_fechadas := v_cv_fechadas + 1;

                -- `uq_cv_consultor_loja_aberta` impede duas abertas para
                -- a mesma (pessoa, loja). Se ja houver uma na loja de
                -- destino — retorno a uma loja anterior sem ter fechado
                -- la — o INSERT violaria o indice; o NOT EXISTS torna o
                -- caso um no-op em vez de abortar a carga inteira.
                INSERT INTO public.consultor_vigencia
                    (nome, loja_id, vigencia_inicio, vigencia_fim, origem)
                SELECT v_row.nome, v_row.loja_destino, v_row.data_efetiva,
                       NULL, 'MANUAL'
                WHERE NOT EXISTS (
                    SELECT 1 FROM public.consultor_vigencia w
                    WHERE w.nome_normalizado = v_row.nn
                      AND w.loja_id = v_row.loja_destino
                      AND w.vigencia_fim IS NULL);
                -- ROW_COUNT, nao `+ 1`: o NOT EXISTS acima pode nao ter
                -- inserido nada, e o envelope tem de dizer o que
                -- aconteceu, nao o que se pretendia.
                GET DIAGNOSTICS v_n = ROW_COUNT;
                v_cv_abertas := v_cv_abertas + v_n;
            END IF;
        END IF;

        -- (2) Supervisao.
        IF v_row.tipo = 'PROMOCAO' THEN
            -- Fecha a supervisao anterior DA PESSOA, se houver (mudanca
            -- de loja supervisionada).
            IF v_row.sv_id IS NOT NULL THEN
                UPDATE public.supervisor_vigencia
                   SET vigencia_fim = v_row.data_efetiva,
                       origem       = 'MANUAL'
                 WHERE id = v_row.sv_id;
                v_sv_fechadas := v_sv_fechadas + 1;
            END IF;

            -- Sucessao: o antecessor da loja de destino fecha na data do
            -- sucessor. A cadeira nao fica vaga nem com dois ocupantes —
            -- mesma regra da 082, e o que a 110 fez a mao para BARBARA.
            -- `vigencia_inicio < data` evita violar chk_sv_vigencia_ordem
            -- quando o antecessor comecou no mesmo dia ou depois.
            UPDATE public.supervisor_vigencia v
               SET vigencia_fim = v_row.data_efetiva,
                   origem       = 'MANUAL'
             WHERE v.loja_id = v_row.loja_destino
               AND v.vigencia_fim IS NULL
               AND v.nome_normalizado <> v_row.nn
               AND v.vigencia_inicio < v_row.data_efetiva;
            GET DIAGNOSTICS v_sv_sucessao = ROW_COUNT;
            v_sv_fechadas := v_sv_fechadas + v_sv_sucessao;

            DELETE FROM public.supervisores s
             WHERE s.loja_id = v_row.loja_destino
               AND upper(regexp_replace(btrim(s.nome),
                         '[[:space:]]+', ' ', 'g')) <> v_row.nn;
            -- Acumula: `GET DIAGNOSTICS` sobrescreve, e o loop passa por
            -- varias linhas. Somar e o que faz o envelope descrever a
            -- carga inteira em vez da ultima iteracao.
            GET DIAGNOSTICS v_n = ROW_COUNT;
            v_foto_del := v_foto_del + v_n;

            INSERT INTO public.supervisor_vigencia
                (nome, loja_id, vigencia_inicio, vigencia_fim, origem)
            SELECT v_row.nome, v_row.loja_destino, v_row.data_efetiva,
                   NULL, 'MANUAL'
            WHERE NOT EXISTS (
                SELECT 1 FROM public.supervisor_vigencia w
                WHERE w.nome_normalizado = v_row.nn
                  AND w.loja_id = v_row.loja_destino
                  AND w.vigencia_fim IS NULL);
            GET DIAGNOSTICS v_n = ROW_COUNT;
            v_sv_abertas := v_sv_abertas + v_n;

            INSERT INTO public.supervisores (nome, loja_id, regiao_id)
            SELECT v_row.nome, v_row.loja_destino, l.regiao_id
            FROM public.lojas l WHERE l.id = v_row.loja_destino
            ON CONFLICT (nome, loja_id) DO NOTHING;
            GET DIAGNOSTICS v_n = ROW_COUNT;
            v_foto_ins := v_foto_ins + v_n;

        ELSIF v_row.tipo = 'REBAIXAMENTO' THEN
            UPDATE public.supervisor_vigencia
               SET vigencia_fim = v_row.data_efetiva,
                   origem       = 'MANUAL'
             WHERE id = v_row.sv_id;
            v_sv_fechadas := v_sv_fechadas + 1;

            -- Sai da foto de supervisores. A janela de consultor
            -- permanece: a pessoa volta a ser contada no denominador da
            -- loja, que e justamente o efeito do rebaixamento.
            DELETE FROM public.supervisores s
             WHERE upper(regexp_replace(btrim(s.nome),
                         '[[:space:]]+', ' ', 'g')) = v_row.nn
               AND s.loja_id IS NOT DISTINCT FROM v_row.sv_loja;
            GET DIAGNOSTICS v_n = ROW_COUNT;
            v_foto_del := v_foto_del + v_n;
        END IF;
    END LOOP;

    RETURN jsonb_build_object(
        'aplicado', true, 'validar_apenas', false, 'error', NULL,
        'pendencias', '[]'::jsonb,
        'divergencias', coalesce(v_divergencias, '[]'::jsonb),
        'recebidas', v_len,
        'consultor_vigencia', jsonb_build_object(
            'fechadas', v_cv_fechadas, 'abertas', v_cv_abertas),
        'supervisor_vigencia', jsonb_build_object(
            'fechadas', v_sv_fechadas, 'abertas', v_sv_abertas),
        'foto_supervisores', jsonb_build_object(
            'inseridos', v_foto_ins, 'removidos', v_foto_del));
END;
$fn$;

COMMENT ON FUNCTION public.fn_movimentacoes_replace(jsonb, boolean) IS
    'Porta de eventos datados para TRANSFERENCIA, PROMOCAO e REBAIXAMENTO '
    '— as movimentacoes que nenhuma das quatro portas de RH registrava e '
    'que exigiam migration a mao (109, 110, 111, 112). Dry-run por padrao; '
    'validacao total antes da escrita; pendencia por numero de linha. '
    'Escreve origem = MANUAL de proposito: e o que imuniza o registro '
    'contra o rebuild do backfill (087) e contra o fechamento por ausencia '
    'de fn_supervisores_replace (082). Producao do lado errado da fronteira '
    'sai em `divergencias` e NAO bloqueia. SECURITY DEFINER; EXECUTE so '
    'para service_role.';

REVOKE ALL ON FUNCTION public.fn_movimentacoes_replace(jsonb, boolean)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_movimentacoes_replace(jsonb, boolean)
    TO service_role;


-- =====================================================
-- Verificacao operacional depois da aplicacao
-- =====================================================
--
-- 1) As quatro chamadas que hoje explodem devem devolver ENVELOPE com
--    pendencia, nao excecao:
--
--    SELECT public.fn_movimentacoes_rh_import(
--        jsonb_build_array(jsonb_build_object(
--            'linha', 5, 'nome', 'X', 'tipo', 'AFASTAMENTO_MEDICO',
--            'data_inicio', '2026-02-31')),
--        '[]'::jsonb, true);
--    -- esperado: {"aplicado": false, "pendencias":
--    --            [{"linha":5,"origem":"AFASTAMENTO","codigo":"DATA_INICIO_INVALIDA"}]}
--
--    SELECT public.fn_movimentacoes_rh_import('[]'::jsonb,
--        jsonb_build_array(jsonb_build_object(
--            'linha', 5, 'nome', 'X', 'data_desligamento', '2026-04-31')), true);
--    -- esperado: pendencia DATA_DESLIGAMENTO_INVALIDA na linha 5
--
--    SELECT public.fn_movimentacoes_rh_import('[]'::jsonb,
--        jsonb_build_array(jsonb_build_object(
--            'linha', 5, 'nome', 'X', 'data_desligamento', '2026-02-29')), true);
--    -- esperado: pendencia DATA_DESLIGAMENTO_INVALIDA (2026 nao e bissexto)
--
--    SELECT public.fn_movimentacoes_replace(jsonb_build_array(
--        jsonb_build_object('linha', 2, 'tipo', 'TRANSFERENCIA',
--            'nome', 'X', 'loja_destino', gen_random_uuid()::text,
--            'data_efetiva', '2026-02-31')), true);
--    -- esperado: pendencia DATA_INVALIDA na linha 2
--
-- 2) Ano BISSEXTO continua passando — a correcao nao pode ser um teto
--    fixo de 28 para fevereiro:
--
--    SELECT public.fn_movimentacoes_rh_import('[]'::jsonb,
--        jsonb_build_array(jsonb_build_object(
--            'linha', 5, 'nome', 'X', 'data_desligamento', '2028-02-29')), true);
--    -- esperado: NENHUMA pendencia de data (2028 e bissexto). A linha
--    -- ainda pode cair em PESSOA_NAO_ENCONTRADA, que e outro assunto.
--
-- 3) A ordem das datas continua sendo verificada:
--
--    SELECT public.fn_movimentacoes_rh_import(
--        jsonb_build_array(jsonb_build_object(
--            'linha', 5, 'nome', 'X', 'tipo', 'AFASTAMENTO_MEDICO',
--            'data_inicio', '2026-03-10', 'data_fim', '2026-03-01')),
--        '[]'::jsonb, true);
--    -- esperado: pendencia ORDEM_DATAS_INVALIDA na linha 5
--
-- 4) Carga valida segue funcionando igual — comparar o envelope de um
--    dry-run do arquivo real com o de antes da migration: mesmos numeros.
