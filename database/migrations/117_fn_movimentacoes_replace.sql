-- =====================================================
-- Migracao 117: porta de eventos datados para transferencia e cargo
-- Data: 2026-09-09
-- Depende de: 086/087 (consultor_vigencia), 076 (supervisor_vigencia),
--             113 (supervisor_vigencia.origem — a guarda que protege o
--             que esta funcao escreve)
--
-- A LACUNA QUE ESTA FUNCAO FECHA
-- -------------------------------
-- Nenhuma das quatro portas de RH registra MUDANCA DE LOJA. A
-- `fn_headcount_replace` (095) escreve tres coisas em `consultor_vigencia`
-- — recua o inicio da PRIMEIRA janela (admissao), cria janela para quem
-- nao tem nenhuma, e fecha TODAS as janelas (desligamento). Pessoa que
-- aparece no arquivo sob loja nova, tendo janela aberta na antiga, cai em
-- `acao_adm = 'sem_data'`: o upsert cria a segunda linha em `consultores`
-- e o ledger nao se mexe. A foto anda, o ledger fica.
--
-- Cargo tem meia porta. `fn_supervisores_replace` registra quem
-- supervisiona qual loja e nada mais. A promocao do HUGO (110) exigiu
-- QUATRO escritas — fechar consultor em BANGU, abrir consultor em
-- MADUREIRA, fechar a supervisao da BARBARA, abrir a dele — e so uma
-- delas tinha canal de upload. Rebaixamento nao tinha canal nenhum.
--
-- Consequencia medida: as migrations 109, 111 e 112 sao transferencias
-- escritas a mao, e a 110 e uma promocao. Em 2026-09-09 o detector (116)
-- achou LIVIA GOMES DE SANT ANNA com a MESMA forma — cadastro em HELP
-- PENHA criado no dia pelo ETL de contratos, ledger ainda em BONSUCESSO,
-- setembro partido 5 a 5 entre as duas lojas. Uma migration por
-- movimentacao nao acompanha o ritmo da operacao.
--
--
-- POR QUE UMA FUNCAO NOVA, E NAO UM PARAMETRO NA 100
-- ---------------------------------------------------
-- A 082 ja documenta a armadilha: `CREATE OR REPLACE` casa por
-- assinatura, entao um parametro novo com DEFAULT cria uma SEGUNDA
-- funcao e a chamada de 3 argumentos do angry-man fica ambigua. Nome
-- novo evita isso e deixa `fn_movimentacoes_rh_import` intacta para o
-- arquivo historico de e-mails, que continua tendo o formato dela.
--
-- Custo declarado: RPC nova = 2 registros na whitelist + redeploy da
-- Edge Function (topologia cross-repo).
--
--
-- POR QUE ESCREVE 'MANUAL' E NAO 'ETL'
-- -------------------------------------
-- Esta nao e uma carga em massa de arquivo: e a operacao declarando um
-- evento por vez, que e exatamente o que as 109-112 fazem. E 'MANUAL' e
-- o que IMUNIZA o registro:
--
--   * o rebuild do backfill (087) apaga so `origem LIKE 'BACKFILL%'`. Sem
--     MANUAL, um rebuild leria os contratos e reescreveria a fronteira —
--     e no caso da LIVIA a regra da "loja dominante do mes" EMPATA (5 a
--     5), entao reescreveria errado;
--   * `fn_supervisores_replace` fecha por AUSENCIA na planilha (082).
--     Uma promocao gravada como 'ETL' seria desfeita pelo primeiro import
--     em que a Supervisores.xlsx ainda nao listasse a pessoa — que e o
--     modo de falha normal dela. A guarda da 113 so protege 'MANUAL';
--   * a 095 e a 114 recusam sobrescrever janela MANUAL, entao nem o HC
--     nem o arquivo de RH desfazem o que entrar por aqui.
--
-- O custo do outro lado, declarado: supervisao MANUAL nao fecha por
-- planilha. Encerrar passa a ser ato explicito — `REBAIXAMENTO` nesta
-- funcao, ou `fn_aplicar_mudanca_supervisor(..., 'FIM')`.
--
--
-- PRODUCAO CONTRADIZENDO A DATA: REPORTA, NAO BLOQUEIA
-- -----------------------------------------------------
-- A 109 exigia fronteira limpa (zero contratos do lado errado) e abortava
-- se nao houvesse. Como pre-condicao de UMA migration para UMA pessoa,
-- funciona. Como regra geral, nao: a CAROLINA (112) tinha 1 contrato
-- avulso em PAVUNA no proprio dia da virada contra 6 em MESQUITA, e uma
-- guarda estrita teria recusado a transferencia inteira por causa dele.
-- E o mesmo erro que a 100 corrigiu do outro lado — 6 desligamentos
-- bloqueando os outros 25.
--
-- Entao a producao do lado errado da fronteira sai em `divergencias`,
-- com a contagem exata, e a movimentacao se aplica. Declarado vence
-- inferido; quem le o envelope ve o tamanho do residuo e julga.
--
--
-- TRES TIPOS, E O QUE CADA UM ESCREVE
-- ------------------------------------
--   TRANSFERENCIA  fecha consultor_vigencia (loja atual) em data_efetiva
--                  abre  consultor_vigencia (loja_destino) em data_efetiva
--
--   PROMOCAO       o caso HUGO, quatro escritas:
--                  fecha consultor_vigencia (loja atual)
--                  abre  consultor_vigencia (loja_destino)
--                  fecha supervisor_vigencia do ANTECESSOR da loja_destino
--                  abre  supervisor_vigencia da pessoa (loja_destino)
--                  + insere em `supervisores` (a foto)
--
--   REBAIXAMENTO   o caso BARBARA:
--                  fecha supervisor_vigencia aberta
--                  remove de `supervisores` (a foto)
--                  MANTEM a janela de consultor (move so se loja_destino
--                  vier preenchida e for diferente da atual)
--
-- Supervisor NAO perde a janela de consultor neste modelo — medido em
-- 2026-09-08: as 47 janelas de supervisao abertas pertencem a 47 pessoas
-- e todas as 47 tem `consultor_vigencia` aberta. A exclusao dos rankings
-- acontece na LEITURA (`_fetch_vinculos_consultores` filtra por
-- `carregar_supervisores`), nunca pela ausencia da janela. Por isso
-- PROMOCAO abre a janela de consultor na loja nova em vez de so fechar a
-- antiga.
--
-- Janela meio-aberta [inicio, fim), como em toda a 086/087: fechar em D
-- faz o ultimo dia coberto ser D-1 e a loja nova comecar em D. Emenda sem
-- vago nem sobreposicao.
--
-- Dry-run por padrao e tudo-ou-nada, como a 097: qualquer pendencia
-- impede toda escrita. O envelope e agregado e traz pendencia por numero
-- de linha.
--
-- Executar no Supabase SQL Editor, depois da 116.
-- =====================================================

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

    -- Round-trip pega 31/02 e similares.
    INSERT INTO mv_pendencias
    SELECT linha, 'DATA_INVALIDA' FROM mv_raw
    WHERE pg_catalog.to_char(
              pg_catalog.to_date(data_txt, 'YYYY-MM-DD'), 'YYYY-MM-DD')
          <> data_txt;

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
-- 1) Dry-run com payload vazio e com tipo invalido — nada deve escrever:
--
--    SELECT public.fn_movimentacoes_replace('[]'::jsonb, true);
--    -- esperado: aplicado=false, "Nenhuma movimentacao recebida."
--
--    SELECT public.fn_movimentacoes_replace(jsonb_build_array(
--        jsonb_build_object('linha', 2, 'tipo', 'DEMISSAO',
--                           'nome', 'X', 'data_efetiva', '2026-10-01')), true);
--    -- esperado: pendencia TIPO_INVALIDO na linha 2
--
-- 2) O caso LIVIA, que e o motivo desta funcao existir. Dry-run primeiro
--    (NAO aplicar sem o veredito da operacao sobre a data):
--
--    SELECT public.fn_movimentacoes_replace(jsonb_build_array(
--        jsonb_build_object(
--            'linha', 2,
--            'tipo', 'TRANSFERENCIA',
--            'nome', 'LIVIA GOMES DE SANT ANNA',
--            'loja_destino', (SELECT id FROM lojas WHERE nome = 'HELP PENHA'),
--            'data_efetiva', '2026-09-01')), true);
--
--    -- esperado: sem pendencias, e `divergencias` mostrando os contratos
--    -- dela em BONSUCESSO a partir de 01/09 (eram 5 em 2026-09-09). E o
--    -- numero que a operacao precisa ver antes de confirmar a data.
--
-- 3) Depois de aplicar qualquer movimentacao, a emenda tem de ficar sem
--    vago nem sobreposicao:
--
--    SELECT count(*) FROM (
--        SELECT v.vigencia_inicio,
--               lag(v.vigencia_fim) OVER (PARTITION BY v.nome_normalizado
--                                         ORDER BY v.vigencia_inicio) AS fim_ant
--        FROM consultor_vigencia v
--    ) t WHERE t.fim_ant IS NOT NULL AND t.vigencia_inicio <> t.fim_ant;
--    -- esperado: o mesmo numero de antes da carga (a base tem emendas
--    -- historicas de backfill; o que nao pode e AUMENTAR).
--
-- 4) A cadeira de supervisao nunca com dois ocupantes:
--
--    SELECT loja_id, count(*) FROM supervisor_vigencia
--     WHERE vigencia_fim IS NULL AND loja_id IS NOT NULL
--     GROUP BY loja_id HAVING count(*) > 1;
--    -- esperado: zero linhas
--
-- 5) Rematerializar o Caderno das competencias afetadas — uma janela
--    atravessa varias:
--
--    SELECT public.fn_materializar_caderno(<mes>, <ano>);
--
--
-- LIMITES CONHECIDOS
-- ------------------
-- 1) Duas movimentacoes da MESMA pessoa na mesma carga sao recusadas
--    (PESSOA_DUPLICADA). `mv` resolve o estado de todos ANTES de
--    escrever, entao a segunda linha leria uma foto ja vencida. Duas
--    movimentacoes exigem duas cargas, em ordem cronologica. Nao e comum
--    — a CAROLINA e a THAIS (112) sao duas PESSOAS numa carga, o que
--    funciona.
--
-- 2) ESTA FUNCAO NAO MEXE EM `consultores` (a foto). Ela escreve os
--    ledgers e, no caso do papel, tambem `supervisores` — que e foto mas
--    e mantida pela mesma porta desde a 077, entao deixa-la de fora
--    partiria a promocao ao meio.
--
--    `consultores` fica de fora de proposito. `uq_consultores_nome_loja`
--    e (nome, loja_id): "mover" a pessoa seria UPDATE do loja_id, que
--    colide quando ja existe linha para a loja de destino, ou INSERT, que
--    cria mais uma duplicata para o dedup por `updated_at` resolver. A
--    109 mostrou o tamanho do problema — FK ON DELETE SET NULL em
--    `contratos`, ON DELETE CASCADE em `usuario_escopos` — e limpar
--    cadastro exige instrucao explicita, nunca efeito colateral de uma
--    carga. Foto e ledger tem portas separadas: `fn_headcount_replace`
--    (HC_Colaboradores) e o ETL de contratos cuidam de `consultores`.
--
--    Consequencia pratica: uma transferencia declarada ANTES de a pessoa
--    produzir na loja nova deixa foto e ledger discordando ate o ETL
--    criar o cadastro. O detector (116) vai reportar essa divergencia — e
--    esta certo em reportar. Nesse caso o ledger e que esta correto.
