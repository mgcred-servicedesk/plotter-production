-- =====================================================
-- Migracao 129: fecha o buraco de 09/2025 no ledger de vigencia e faz a
--               guarda de origem reconhecer loja reinaugurada (PDV -> HELP)
-- Data: 2026-10-05
-- Depende de: 086/087 (ledger de vigencia), 105 (guarda de origem),
--             101 (materializacao da produtividade individual)
--
--
-- O BLOQUEIO QUE TROUXE ESTA MIGRATION
-- ------------------------------------
-- `fn_materializar_produtividade_individual(9, 2025)` falha fechado com
-- `unlinkedPaidOriginEvents = 744` (`overlappingEligibleDays = 0`).
-- 10/2025 tambem bloqueia (730): os mesmos contratos de origem em
-- setembro, pagos nas semanas de outubro.
--
--
-- CAUSA: O BACKFILL RODOU ANTES DE SETEMBRO/2025 EXISTIR
-- ------------------------------------------------------
-- O rebuild da 087 rodou em 2026-08-20 20:42, e a propria 087 registra:
-- "o periodo 09/2025 nao existe na base" (0 produtores na tabela de
-- efeito). Os 7.138 contratos do periodo 09/2025 so foram carregados em
-- 2026-10-05. Sem setembro, as regras da 087 produziram exatamente o
-- buraco medido:
--
--   * quem SAIU em setembro teve a janela fechada no fim do mes do
--     ultimo contrato CONHECIDO — 2025-09-01;
--   * quem ENTROU em setembro ganhou janela so a partir do 1o contrato
--     conhecido — 2025-10-01 em diante;
--   * quem nao produziu fora de setembro ficou sem janela nenhuma;
--   * transferencias de setembro viraram fronteira em 01/10.
--
-- Assinatura no ledger: 16 janelas fecham em 2025-09-01, nenhuma abre;
-- vigentes no dia 15 caem de 139 (08) para 127 (09) e saltam para 152
-- (10), com 14 aberturas em 2025-10-01.
--
--
-- CORRECAO 1 — LEDGER (724 dos 744 eventos)
-- -----------------------------------------
-- As fronteiras seguem as MESMAS regras da 087, agora com setembro a
-- vista — e o que um rebuild produziria hoje:
--   entrada       = data exata do 1o contrato;
--   transferencia = data exata do 1o contrato na loja nova;
--   saida         = fim do mes do ultimo contrato.
--
-- 25 linhas ajustadas, 3 criadas. `origem` das linhas ajustadas fica
-- como esta (so as datas mudam); as criadas sao BACKFILL_PRODUCAO, porque
-- sao inferencia de producao, nao declaracao — um rebuild as recriaria
-- identicas. Fatos confirmados pela operacao em 2026-10-05:
--
--   * JUAN VICTOR e RAYANE NUNES trocaram de loja entre si no periodo
--     (Mesquita <-> Queimados). A producao particiona sem ambiguidade:
--     Juan em Mesquita ate 30/08, Queimados desde 04/09; Rayane em
--     Queimados ate 03/09, Mesquita desde 04/09. Fronteira 2025-09-04.
--   * LETYCIA pertenceu as duas lojas de Alcantara, transferida de uma
--     para a outra: Carrefour ate 28/08, HELP ALCANTARA desde 01/09.
--   * PDV ENGENHO NOVO e PDV CAMPO GRANDE NOVA sao os nomes antigos de
--     HELP ENGENHO NOVO e HELP CAMPO GRANDE NOVA (reinauguracao sob a
--     marca Help). Para MARIA ARIANE, RAQUEL e LETICIA GOMES, a janela
--     PDV fecha em 01/09 e a HELP comeca em 01/09: setembro chegou
--     rotulado HELP, e `obter_produtividade_individual` so conta dia de
--     vinculo em loja ativa — com a janela PDV ate 01/10 elas teriam
--     setembro inteiro com ZERO dias no denominador.
--
--
-- CORRECAO 2 — GUARDA CIENTE DE SUCESSAO (os 20 restantes)
-- --------------------------------------------------------
-- O ETL rotula a loja pelo LOTE DE CARGA, nao pela data do contrato:
-- Engenho Novo veio HELP em 07/2025, PDV em 08/2025 e HELP em 09/2025;
-- o lote de 09 traz contratos digitados em 26-30/08 ja como HELP, e o de
-- 08 traz contratos de 23-31/07 como PDV. Nenhuma particao por data do
-- ledger cobre isso sem sobrepor janelas (o que acenderia
-- `overlappingEligibleDays`).
--
-- `lojas.sucessora_id` ja registra a reinauguracao. A guarda passa a
-- comparar a loja CANONICA dos dois lados (`coalesce(sucessora_id, id)`):
-- um contrato rotulado PDV dentro de uma janela HELP da mesma loja — ou
-- o inverso — tem vinculo de origem. So um nivel de sucessao: medido em
-- 2026-10-05, nenhuma sucessora tem sucessora.
--
-- Eventos resolvidos por esta correcao: LETICIA GOMES (5, HELP CGN em
-- 26-30/08), LAURA (1, HELP CGN em 29/08), RAQUEL (6, PDV EN em
-- 23-31/07), LINDOMAR (8, HELP BR SAO JOSE em 07/2025 sob janela
-- PDV BELFORD ROXO II, que tambem tem sucessora registrada).
--
--
-- EFEITO SIMULADO (2026-10-05, transacao com rollback)
-- ----------------------------------------------------
--   guarda          hoje   so guarda   guarda + ledger
--   06/2025           10          6                 6
--   07/2025           16         12                12
--   08/2025           34         10                10
--   09/2025          744        585                 0
--   10/2025          730        585                 0
--   11/2025            0          0                 0
--   08/2026            0          0                 0
--   09/2026            0          0                 0
--
--   pares de janelas sobrepostas: 0 antes, 0 depois.
--   overlappingEligibleDays 09/2025 e 10/2025: 0.
--
-- As competencias publicadas (08 e 09/2026) nao mudam.
--
-- Executar no Supabase SQL Editor.
-- =====================================================

BEGIN;

LOCK TABLE public.consultor_vigencia IN SHARE ROW EXCLUSIVE MODE;

-- ===========================================
-- 1. Guarda de origem ciente de sucessao
-- ===========================================
CREATE OR REPLACE FUNCTION public.fn_contar_pagamentos_sem_vinculo_origem(p_mes integer, p_ano integer)
 RETURNS integer
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
WITH
periodo_base AS (
    SELECT
        make_date(p_ano, p_mes, 1) AS mes_inicio,
        (make_date(p_ano, p_mes, 1) + interval '1 month')::date AS mes_fim
),
periodo AS (
    SELECT
        pb.*,
        (pb.mes_fim - 1) AS ancora,
        ((pb.mes_fim - 1)
          - (extract(isodow FROM pb.mes_fim - 1)::integer % 7))::date
            AS semana_fim
    FROM periodo_base pb
),
parametros AS (
    SELECT p.*, (p.semana_fim - 55)::date AS semana_inicio
    FROM periodo p
),
supervisores AS (
    SELECT DISTINCT sv.nome_normalizado AS consultant_id
    FROM public.supervisor_vigencia sv
    CROSS JOIN parametros p
    WHERE sv.vigencia_inicio <= p.ancora
      AND (sv.vigencia_fim IS NULL OR sv.vigencia_fim > p.ancora)
),
eventos_pagos AS (
    SELECT
        v.id,
        v.data_cadastro::date AS data_origem,
        upper(regexp_replace(
            btrim(coalesce(v.consultor, '')),
            '[[:space:]]+', ' ', 'g'
        )) AS consultant_id,
        c.loja_id,
        -- 129: loja reinaugurada (PDV -> HELP) e a MESMA loja. O ETL
        -- rotula pelo lote de carga, nao pela data, entao a guarda
        -- compara a loja canonica dos dois lados.
        coalesce(lj.sucessora_id, c.loja_id) AS loja_canonica,
        CASE
            WHEN coalesce(v.conta_valor, true) = false THEN 0
            ELSE coalesce(v.valor_consolidado, 0)
        END::numeric AS paid_effective
    FROM public.v_contratos_dashboard v
    JOIN public.contratos c ON c.id = v.id
    LEFT JOIN public.lojas lj ON lj.id = c.loja_id
    LEFT JOIN public.periodos per ON per.id = v.periodo_id
    LEFT JOIN supervisores s
      ON s.consultant_id = upper(regexp_replace(
             btrim(coalesce(v.consultor, '')),
             '[[:space:]]+', ' ', 'g'
         ))
    CROSS JOIN parametros p
    WHERE s.consultant_id IS NULL
      AND upper(btrim(coalesce(v.loja, ''))) <> 'VAI E VEM'
      AND (
          (per.mes = p_mes AND per.ano = p_ano)
          OR v.data_status_pagamento::date
               BETWEEN p.semana_inicio AND p.semana_fim
      )
),
sem_vinculo AS (
    SELECT e.id
    FROM eventos_pagos e
    WHERE e.paid_effective > 0
      AND (
          e.data_origem IS NULL
          OR e.consultant_id = ''
          OR e.loja_id IS NULL
          OR NOT EXISTS (
              SELECT 1
              FROM public.consultor_vigencia cv
              JOIN public.lojas lcv ON lcv.id = cv.loja_id
              WHERE cv.nome_normalizado = e.consultant_id
                AND coalesce(lcv.sucessora_id, lcv.id) = e.loja_canonica
                AND e.data_origem >= cv.vigencia_inicio
                AND (cv.vigencia_fim IS NULL
                     OR e.data_origem < cv.vigencia_fim)
          )
      )
)
SELECT count(*)::integer FROM sem_vinculo;
$function$;

-- ===========================================
-- 2. Ledger: fronteiras de 09/2025
-- ===========================================
DO $$
DECLARE
    v_r       record;
    v_antigo  integer;
    v_novo    integer;
    v_feitos  integer := 0;
    v_n       integer;
BEGIN
    -- So um nivel de sucessao e suportado pela guarda.
    SELECT count(*) INTO v_n
      FROM public.lojas a
      JOIN public.lojas b ON b.id = a.sucessora_id
     WHERE b.sucessora_id IS NOT NULL;
    IF v_n > 0 THEN
        RAISE EXCEPTION 'Migration 129: % loja(s) com sucessao encadeada', v_n;
    END IF;

    CREATE TEMP TABLE m129_ajuste (
        nn text, loja text,
        ini_atual date, fim_atual date,
        ini_novo date, fim_novo date
    ) ON COMMIT DROP;

    INSERT INTO m129_ajuste VALUES
      ('ALINE MACHADO DE LIMA',            'HELP BONSUCESSO',             '2025-10-01', '2026-02-01', '2025-09-02', '2026-02-01'),
      ('ANDREA DA SILVA CARDOSO',          'HELP BELFORD ROXO',           '2025-07-02', '2025-09-01', '2025-07-02', '2025-10-01'),
      ('CAROLINE INDAYA TAVARES SILVA',    'HELP MADUREIRA',              '2025-10-01', '2025-12-01', '2025-09-01', '2025-12-01'),
      ('DANILO ALBERTO FRANCA DOS ANJOS',  'HELP CIDADE DE DEUS',         '2025-04-01', '2025-09-01', '2025-04-01', '2025-10-01'),
      ('GUSTAVO DA SILVA COSTA SANTIAGO',  'HELP PENHA',                  '2025-08-01', '2025-09-01', '2025-08-01', '2025-10-01'),
      ('JUAN VICTOR DOS SANTOS SILVA',     'HELP MESQUITA',               '2025-08-01', '2025-10-01', '2025-08-01', '2025-09-04'),
      ('JUAN VICTOR DOS SANTOS SILVA',     'HELP QUEIMADOS',              '2025-10-01', NULL,         '2025-09-04', NULL),
      ('LARISSA SANTOS ALVES',             'HELP LARGO DA SEGUNDA FEIRA', '2025-10-01', '2026-03-02', '2025-09-04', '2026-03-02'),
      ('LETICIA DA SILVA GOMES',           'PDV CAMPO GRANDE NOVA',       '2025-08-01', '2025-10-02', '2025-08-01', '2025-09-01'),
      ('LETICIA DA SILVA GOMES',           'HELP CAMPO GRANDE NOVA',      '2025-10-02', '2026-09-02', '2025-09-01', '2026-09-02'),
      ('LETYCIA DA SILVA CAMPOS CRELIER',  'HELP ALCANTARA CARREFOUR',    '2025-03-01', '2025-10-01', '2025-03-01', '2025-09-01'),
      ('LETYCIA DA SILVA CAMPOS CRELIER',  'HELP ALCANTARA',              '2025-10-01', '2026-07-09', '2025-09-01', '2026-07-09'),
      ('LIDIANE TEODORO DO NASCIMENTO',    'HELP MAGE',                   '2025-10-01', '2025-10-28', '2025-08-30', '2025-10-28'),
      ('LUCAS DE MOURA LIRA',              'HELP CAXIAS GUANABARA',       '2025-10-01', '2025-11-01', '2025-09-19', '2025-11-01'),
      ('MARIA ARIANE AGAPITO CORDEIRO',    'PDV ENGENHO NOVO',            '2025-08-01', '2025-10-01', '2025-08-01', '2025-09-01'),
      ('MARIA ARIANE AGAPITO CORDEIRO',    'HELP ENGENHO NOVO',           '2025-10-01', NULL,         '2025-09-01', NULL),
      ('PRISCILA DE LIMA RIBEIRO',         'HELP BONSUCESSO',             '2025-07-23', '2025-09-01', '2025-07-23', '2025-10-01'),
      ('RAQUEL VERAS SILVA',               'PDV ENGENHO NOVO',            '2025-08-01', '2025-10-01', '2025-08-01', '2025-09-01'),
      ('RAQUEL VERAS SILVA',               'HELP ENGENHO NOVO',           '2025-10-01', NULL,         '2025-09-01', NULL),
      ('RAYANE DA SILVA AURELIANO',        'HELP SAO JOAO DE MERITI',     '2025-08-06', '2025-09-01', '2025-08-06', '2025-10-01'),
      ('RAYANE NUNES TEIXEIRA',            'HELP QUEIMADOS',              '2025-08-22', '2025-10-01', '2025-08-22', '2025-09-04'),
      ('RAYANE NUNES TEIXEIRA',            'HELP MESQUITA',               '2025-10-01', '2025-11-01', '2025-09-04', '2025-11-01'),
      ('RAYANE VELOSO DA SILVA',           'HELP TIJUCA ALMIRANTE',       '2025-10-01', '2026-02-01', '2025-09-01', '2026-02-01'),
      ('REBECCA EDUARDA JUSTINO DA SILVA', 'HELP MEIER',                  '2025-10-06', '2025-11-01', '2025-09-08', '2025-11-01'),
      ('THAYANE DE MELO PEDREIRA',         'HELP VICENTE DE CARVALHO',    '2025-08-04', '2025-09-01', '2025-08-04', '2025-10-01');

    -- Cada ajuste casa exatamente uma linha no estado ANTIGO (aplica) ou
    -- no estado NOVO (ja aplicado: no-op). Qualquer outra coisa aborta.
    FOR v_r IN SELECT * FROM m129_ajuste LOOP
        SELECT count(*) INTO v_antigo
          FROM public.consultor_vigencia cv
          JOIN public.lojas l ON l.id = cv.loja_id
         WHERE cv.nome_normalizado = v_r.nn AND l.nome = v_r.loja
           AND cv.vigencia_inicio = v_r.ini_atual
           AND cv.vigencia_fim IS NOT DISTINCT FROM v_r.fim_atual;

        SELECT count(*) INTO v_novo
          FROM public.consultor_vigencia cv
          JOIN public.lojas l ON l.id = cv.loja_id
         WHERE cv.nome_normalizado = v_r.nn AND l.nome = v_r.loja
           AND cv.vigencia_inicio = v_r.ini_novo
           AND cv.vigencia_fim IS NOT DISTINCT FROM v_r.fim_novo;

        IF v_antigo = 1 AND v_novo = 0 THEN
            UPDATE public.consultor_vigencia cv
               SET vigencia_inicio = v_r.ini_novo,
                   vigencia_fim    = v_r.fim_novo
              FROM public.lojas l
             WHERE l.id = cv.loja_id
               AND cv.nome_normalizado = v_r.nn AND l.nome = v_r.loja
               AND cv.vigencia_inicio = v_r.ini_atual
               AND cv.vigencia_fim IS NOT DISTINCT FROM v_r.fim_atual;
            v_feitos := v_feitos + 1;
        ELSIF NOT (v_antigo = 0 AND v_novo = 1) THEN
            RAISE EXCEPTION
                'Migration 129: estado inesperado para % / % (antigo=%, novo=%)',
                v_r.nn, v_r.loja, v_antigo, v_novo;
        END IF;
    END LOOP;

    -- Producao exclusivamente em 09/2025, sem janela nenhuma.
    INSERT INTO public.consultor_vigencia
        (nome, loja_id, vigencia_inicio, vigencia_fim, origem)
    SELECT x.nome, l.id, x.ini, x.fim, 'BACKFILL_PRODUCAO'
      FROM (VALUES
        ('DAIANA ROSE DA COSTA MATTOS',  'HELP BELFORD ROXO',          date '2025-09-03', date '2025-10-01'),
        ('JULIANA DE JESUS FARIA',       'HELP BELFORD ROXO SAO JOSE', date '2025-09-10', date '2025-10-01'),
        ('SINTHIA APARECIDA DOS SANTOS', 'HELP ABOLICAO',              date '2025-09-01', date '2025-10-01')
      ) x(nome, loja, ini, fim)
      JOIN public.lojas l ON l.nome = x.loja
     WHERE NOT EXISTS (
         SELECT 1 FROM public.consultor_vigencia cv
          WHERE cv.nome_normalizado =
                upper(regexp_replace(btrim(x.nome), '[[:space:]]+', ' ', 'g'))
            AND cv.loja_id = l.id
            AND cv.vigencia_inicio = x.ini);
    GET DIAGNOSTICS v_n = ROW_COUNT;

    RAISE NOTICE 'Migration 129: % janelas ajustadas, % criadas', v_feitos, v_n;

    -- ---- Pos-condicoes ----
    SELECT count(*) INTO v_n
      FROM public.consultor_vigencia a
      JOIN public.consultor_vigencia b
        ON a.nome_normalizado = b.nome_normalizado AND a.id < b.id
       AND a.vigencia_inicio < coalesce(b.vigencia_fim, 'infinity')
       AND b.vigencia_inicio < coalesce(a.vigencia_fim, 'infinity');
    IF v_n > 0 THEN
        RAISE EXCEPTION 'Migration 129: pos-condicao falhou — % pares de janelas sobrepostas', v_n;
    END IF;

    v_n := public.fn_contar_pagamentos_sem_vinculo_origem(9, 2025);
    IF v_n <> 0 THEN
        RAISE EXCEPTION 'Migration 129: pos-condicao falhou — guarda 09/2025 = %', v_n;
    END IF;

    v_n := public.fn_contar_pagamentos_sem_vinculo_origem(10, 2025);
    IF v_n <> 0 THEN
        RAISE EXCEPTION 'Migration 129: pos-condicao falhou — guarda 10/2025 = %', v_n;
    END IF;
END
$$;

COMMIT;

-- =====================================================
-- DEPOIS DE APLICAR
-- =====================================================
--   SELECT public.fn_materializar_produtividade_individual(9, 2025);
--   SELECT public.fn_materializar_produtividade_individual(10, 2025);
-- (ou o fluxo de rematerializacao do Caderno, que chama a mesma guarda)
--
--
-- =====================================================
-- FOLLOW-UPS QUE NAO SAO DESTA MIGRATION
-- =====================================================
--
-- [ ] 06, 07 e 08/2025 seguem com residuo (6 / 12 / 10). Nao bloqueiam
--     nada publicado hoje, mas bloqueiam a produtividade individual
--     dessas competencias quando for materializada.
--
-- [ ] `obter_produtividade_individual` filtra `coalesce(l.ativo, true)`
--     no denominador. Lojas reinauguradas estao `ativo = false`, entao
--     as janelas PDV de 08/2025 (Engenho Novo, Campo Grande Nova) somam
--     ZERO dias. Afeta a produtividade individual de 08/2025, nao a de
--     09/2025. Mesma loja canonica resolveria tambem ali.
--
-- [ ] Carga retroativa depois de backfill e o mecanismo: qualquer periodo
--     carregado apos 2026-08-20 nao tem fronteira no ledger. Vale um
--     alerta (periodo com contratos e 0 aberturas/fechamentos no dia 1)
--     antes da proxima carga historica.
