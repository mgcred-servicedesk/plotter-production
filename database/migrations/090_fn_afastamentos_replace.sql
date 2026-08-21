-- =====================================================
-- Migracao 090: fn_afastamentos_replace
--               (carga de afastamentos por upload de arquivo)
--
-- A 089 criou o ledger e fn_registrar_afastamento, que trata UMA pessoa
-- por chamada. A partir de 2026-08-20 o RH passa a comunicar as datas
-- por upload de arquivo, entao falta a porta de entrada em lote — o
-- equivalente de fn_supervisores_replace (077) para esta dimensao.
--
--
-- DOIS MODOS (decisao do usuario, 2026-08-20)
-- --------------------------------------------
--   SNAPSHOT (padrao) — o arquivo e a FOTO de quem esta afastado hoje.
--       Quem esta no arquivo tem janela aberta/corrigida; quem SUMIU do
--       arquivo retornou, e a janela dele FECHA.
--   UPSERT — o arquivo e uma correcao pontual. So mexe nas linhas
--       enviadas; ausencia nao fecha nada.
--
-- Por que SNAPSHOT e o padrao: o RH acerta o INICIO e erra o FIM. Foi
-- medido nos 4 nomes marcados na planilha — ERICA seguia 'Licenciado
-- (a)' meses depois de voltar; ANA LETICIA seguia com "Afastamento
-- medico" sendo a maior produtora da base. Ninguem volta na planilha
-- para limpar. Com SNAPSHOT ninguem precisa: a pessoa sai do arquivo
-- seguinte e a janela fecha sozinha.
--
-- A direcao do erro justifica a escolha. Afastamento aberto indevido
-- pesa 0, encolhe o denominador e INFLA a produtividade — e o erro
-- perigoso. SNAPSHOT ataca exatamente esse; UPSERT o deixaria vivo.
--
--
-- SNAPSHOT VAZIO E RECUSADO
-- --------------------------
-- Um arquivo vazio ou quebrado em modo SNAPSHOT fecharia TODAS as
-- janelas de uma vez, inflando denominador em silencio. A 077 se
-- protege disso com minimo de 30 linhas; aqui nao da — zero afastados e
-- um estado legitimo da empresa.
--
-- Solucao: SNAPSHOT exige pelo menos 1 linha. Fechar todo mundo passa a
-- ser ato EXPLICITO — UPSERT com data_fim preenchida, uma linha por
-- pessoa. O caminho perigoso deixa de ser alcancavel por acidente.
--
--
-- ORDEM DE FECHAMENTO NO SNAPSHOT (importa)
-- ------------------------------------------
--   1o. fn_fechar_afastamentos_por_producao — quem digitou contrato
--       fecha na DATA EXATA do contrato;
--   2o. quem sumiu do arquivo e nao tem producao fecha em current_date.
--
-- Invertida, a ordem perderia a data exata: current_date sobrescreveria
-- o retorno comprovado. Por isso o passo 1 esta DENTRO desta funcao e
-- nao depende de o ETL lembrar de chamar.
--
-- Executar no Supabase SQL Editor, depois da 089.
-- =====================================================


-- ===========================================
-- 1. fn_afastamentos_replace
--
-- ATENCAO para quem for evoluir: NAO criar sobrecarga desta funcao.
-- CREATE OR REPLACE casa por ASSINATURA — uma segunda versao com
-- numero diferente de argumentos vira funcao NOVA, e a chamada de 1
-- argumento do angry-man passa a dar "function is not unique". E a
-- licao registrada no cabecalho da 077. Para mudar o contrato, altere
-- ESTA assinatura e faca o redeploy do angry-man junto.
-- ===========================================

CREATE OR REPLACE FUNCTION public.fn_afastamentos_replace(
    p_rows jsonb,
    p_modo text DEFAULT 'SNAPSHOT'
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $fn$
DECLARE
    v_modo        text;
    v_len         integer;
    v_invalidas   jsonb;
    v_row         jsonb;
    v_nome        text;
    v_nn          text;
    v_tipo        text;
    v_inicio      date;
    v_fim         date;
    v_obs         text;
    v_id          uuid;
    v_ins         integer := 0;
    v_upd         integer := 0;
    v_fech_prod   integer := 0;
    v_fech_aus    integer := 0;
    v_abertos_ini integer;
BEGIN
    v_modo := upper(btrim(coalesce(p_modo, 'SNAPSHOT')));

    IF v_modo NOT IN ('SNAPSHOT', 'UPSERT') THEN
        RETURN jsonb_build_object(
            'count', 0,
            'error', format('Modo invalido: %s. Use SNAPSHOT ou UPSERT.', p_modo));
    END IF;

    IF p_rows IS NULL OR jsonb_typeof(p_rows) <> 'array' THEN
        RETURN jsonb_build_object(
            'count', 0,
            'error', 'Payload ausente ou nao e um array JSON.');
    END IF;

    v_len := jsonb_array_length(p_rows);

    IF v_modo = 'SNAPSHOT' AND v_len = 0 THEN
        RETURN jsonb_build_object(
            'count', 0,
            'error', 'SNAPSHOT vazio recusado: fecharia todas as janelas '
                     'abertas de uma vez. Para encerrar afastamentos, use '
                     'modo UPSERT com data_fim preenchida por pessoa.');
    END IF;

    -- Serializa cargas concorrentes (mesmo padrao da 077).
    PERFORM pg_advisory_xact_lock(20260820);

    -- ---- validacao TOTAL antes de aplicar QUALQUER linha ----
    SELECT jsonb_agg(r) INTO v_invalidas
    FROM jsonb_array_elements(p_rows) r
    WHERE btrim(coalesce(r->>'nome', '')) = ''
       OR upper(btrim(coalesce(r->>'tipo', ''))) NOT IN (
              'AFASTAMENTO_MEDICO', 'LICENCA_MATERNIDADE',
              'LICENCA_NAO_REMUNERADA', 'FERIAS')
       OR coalesce(r->>'data_inicio', '') !~ '^\d{4}-\d{2}-\d{2}$'
       OR (coalesce(r->>'data_fim', '') <> ''
           AND r->>'data_fim' !~ '^\d{4}-\d{2}-\d{2}$');

    IF v_invalidas IS NOT NULL THEN
        RETURN jsonb_build_object(
            'count', 0,
            'error', 'Linhas invalidas — nada foi aplicado.',
            'invalidas', v_invalidas);
    END IF;

    SELECT count(*) INTO v_abertos_ini
    FROM consultor_afastamento WHERE data_fim IS NULL;

    -- ---- aplica linha a linha ----
    -- Volume e de dezenas, nao de milhares: laco explicito vale mais que
    -- DML em lote pela clareza da resolucao de identidade abaixo.
    FOR v_row IN SELECT * FROM jsonb_array_elements(p_rows) LOOP
        v_nome   := btrim(v_row->>'nome');
        v_nn     := upper(regexp_replace(v_nome, '[[:space:]]+', ' ', 'g'));
        v_tipo   := upper(btrim(v_row->>'tipo'));
        v_inicio := (v_row->>'data_inicio')::date;
        v_fim    := nullif(btrim(coalesce(v_row->>'data_fim', '')), '')::date;
        v_obs    := nullif(btrim(coalesce(v_row->>'observacao', '')), '');

        -- Resolucao de identidade, nesta ordem:
        --   1. mesma pessoa e mesmo data_inicio  -> e a MESMA janela;
        --   2. senao, a janela ABERTA da pessoa  -> e o caso "corrigir
        --      informacao equivocada" (inclusive data_inicio errada);
        --   3. senao, e afastamento novo.
        SELECT id INTO v_id
        FROM consultor_afastamento
        WHERE nome_normalizado = v_nn AND data_inicio = v_inicio;

        IF v_id IS NULL THEN
            SELECT id INTO v_id
            FROM consultor_afastamento
            WHERE nome_normalizado = v_nn AND data_fim IS NULL;
        END IF;

        IF v_id IS NULL THEN
            INSERT INTO consultor_afastamento
                (nome, tipo, data_inicio, data_fim, origem, observacao)
            VALUES (v_nome, v_tipo, v_inicio, v_fim, 'ETL', v_obs);
            v_ins := v_ins + 1;
        ELSE
            UPDATE consultor_afastamento
            SET nome        = v_nome,
                tipo        = v_tipo,
                data_inicio = v_inicio,
                data_fim    = v_fim,
                origem      = 'ETL',
                observacao  = coalesce(v_obs, observacao)
            WHERE id = v_id;
            v_upd := v_upd + 1;
        END IF;
    END LOOP;

    -- ---- fechamento (so no SNAPSHOT) ----
    IF v_modo = 'SNAPSHOT' THEN
        -- 1o: producao fecha com data exata (ver cabecalho).
        v_fech_prod := public.fn_fechar_afastamentos_por_producao();

        -- 2o: sumiu do arquivo e nao tem producao que prove o dia.
        -- O filtro data_inicio < current_date respeita chk_ca_ordem:
        -- janela aberta HOJE nao pode fechar HOJE.
        UPDATE consultor_afastamento a
        SET data_fim = current_date
        WHERE a.data_fim IS NULL
          AND a.data_inicio < current_date
          AND NOT EXISTS (
              SELECT 1 FROM jsonb_array_elements(p_rows) r
              WHERE upper(regexp_replace(
                        btrim(coalesce(r->>'nome', '')),
                        '[[:space:]]+', ' ', 'g')) = a.nome_normalizado);
        GET DIAGNOSTICS v_fech_aus = ROW_COUNT;
    END IF;

    RETURN jsonb_build_object(
        'modo',                  v_modo,
        'count',                 v_len,
        'inseridos',             v_ins,
        'atualizados',           v_upd,
        'fechados_por_producao', v_fech_prod,
        'fechados_por_ausencia', v_fech_aus,
        'abertos_antes',         v_abertos_ini,
        'abertos_depois', (SELECT count(*) FROM consultor_afastamento
                           WHERE data_fim IS NULL));
END;
$fn$;

COMMENT ON FUNCTION public.fn_afastamentos_replace(jsonb, text) IS
    'Carga de afastamentos por upload. SNAPSHOT (padrao): o arquivo e a foto '
    'de quem esta afastado; ausencia fecha a janela. UPSERT: correcao '
    'pontual, ausencia nao fecha nada. SNAPSHOT vazio e recusado. '
    'SECURITY DEFINER; EXECUTE so para service_role. NAO criar sobrecarga '
    '(ver 077).';

REVOKE ALL ON FUNCTION public.fn_afastamentos_replace(jsonb, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.fn_afastamentos_replace(jsonb, text)
    FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_afastamentos_replace(jsonb, text)
    TO service_role;


-- ===========================================
-- Verificacao (apos executar)
-- ===========================================
-- 1) Modo invalido e payload torto sao recusados sem aplicar nada:
--
--    SELECT fn_afastamentos_replace('[]'::jsonb, 'XPTO');
--    -- Esperado: {"count":0,"error":"Modo invalido: XPTO..."}
--    SELECT fn_afastamentos_replace('{}'::jsonb);
--    -- Esperado: {"count":0,"error":"Payload ausente ou nao e um array JSON."}
--    SELECT fn_afastamentos_replace('[]'::jsonb);
--    -- Esperado: {"count":0,"error":"SNAPSHOT vazio recusado..."}
--
-- 2) Tipo fora do vocabulario derruba a carga INTEIRA (nada parcial):
--
--    SELECT fn_afastamentos_replace(
--      '[{"nome":"FULANO","tipo":"FERIAS","data_inicio":"2026-08-01"},
--        {"nome":"CICLANO","tipo":"LICENCA_X","data_inicio":"2026-08-01"}]'::jsonb);
--    -- Esperado: count 0, chave "invalidas" com a linha do CICLANO,
--    -- e FULANO NAO inserido.
--
-- 3) Ciclo completo, em transacao descartavel:
--
--    BEGIN;
--      -- entra um afastado
--      SELECT fn_afastamentos_replace(
--        '[{"nome":"TESTE DA SILVA","tipo":"FERIAS",
--           "data_inicio":"2026-08-01"}]'::jsonb);
--      -- Esperado: inseridos 1, abertos_depois = abertos_antes + 1.
--
--      -- proximo arquivo sem ele = voltou
--      SELECT fn_afastamentos_replace(
--        '[{"nome":"OUTRO NOME","tipo":"FERIAS",
--           "data_inicio":"2026-08-05"}]'::jsonb);
--      -- Esperado: fechados_por_ausencia >= 1 e a janela do TESTE DA
--      -- SILVA com data_fim = current_date.
--    ROLLBACK;
--
-- 4) UPSERT corrige data_inicio errada SEM abrir janela nova:
--
--    BEGIN;
--      SELECT fn_afastamentos_replace(
--        '[{"nome":"TESTE DA SILVA","tipo":"FERIAS",
--           "data_inicio":"2026-08-01"}]'::jsonb, 'UPSERT');
--      SELECT fn_afastamentos_replace(
--        '[{"nome":"TESTE DA SILVA","tipo":"FERIAS",
--           "data_inicio":"2026-07-15"}]'::jsonb, 'UPSERT');
--      SELECT count(*) FROM consultor_afastamento
--      WHERE nome_normalizado = 'TESTE DA SILVA';
--      -- Esperado: 1 (regra 2 da resolucao de identidade — a janela
--      -- aberta foi corrigida, nao duplicada).
--    ROLLBACK;
--
-- 5) UPSERT nunca fecha por ausencia:
--
--    SELECT fn_afastamentos_replace('[]'::jsonb, 'UPSERT');
--    -- Esperado: count 0, fechados_por_ausencia 0, abertos_depois
--    -- igual a abertos_antes. (Vazio e aceito em UPSERT — e no-op.)
-- =====================================================
