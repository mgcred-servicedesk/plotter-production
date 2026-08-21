-- =====================================================
-- Migracao 091: fn_headcount_ponderado
--               (R2 e R3 viram conta)
--
-- Fonte UNICA das regras de peso aprovadas em 2026-08-20. O Caderno
-- (092) e o dashboard (093) passam a consumir esta funcao em vez de
-- cada um reimplementar a regra — o erro que a 073 documentou, quando a
-- RPC contava 177 e o dashboard 114 sobre a MESMA fonte.
--
-- Nao muda numero publicado: nada chama esta funcao ainda.
--
--
-- AS REGRAS, NA FORMA EM QUE VIRAM SQL
-- -------------------------------------
--   R2  peso = dias_disponiveis / DU da competencia
--       * piso de 50% SO quando a reducao vem de fronteira INFERIDA;
--       * SEM piso quando vem de fato DECLARADO (afastamento, papel de
--         supervisor, ou janela de vinculo com origem ETL/MANUAL);
--       * ausencia que cobre o mes inteiro pesa 0 — o piso nunca
--         ressuscita quem teve zero dias;
--       * silencio (mes sem contrato, janela aberta) pesa 1,0 — nao ha
--         reducao nenhuma a aplicar.
--   R3  peso por loja = peso_pessoa x (dias na loja / dias da pessoa),
--       de modo que a soma entre lojas devolva UMA pessoa.
--
-- dias_disponiveis = dias uteis em que a pessoa (a) tinha vinculo com a
-- loja, (b) NAO estava afastada e (c) NAO era supervisora. Os tres
-- ledgers entram aqui, cada um respondendo a sua pergunta:
--
--   consultor_vigencia    -> em qual LOJA estava
--   consultor_afastamento -> se estava DISPONIVEL
--   supervisor_vigencia   -> em qual PAPEL estava
--
--
-- POR QUE O PISO DEPENDE DA PROCEDENCIA, E NAO DO TAMANHO
-- -------------------------------------------------------
-- O piso existe para limitar erro de ESTIMATIVA, nao para amortecer
-- fato. O mes de entrada e estimado — os dias de treinamento antes da
-- primeira venda nao deixam rastro, entao a fracao derivada da producao
-- subestima. Ja um retorno de licenca em 19/06 ou uma promocao em 15/07
-- sao datas EXATAS: aplicar piso ali apagaria informacao real.
--
-- O caso que forcou a distincao (ERICA, migrations 088/089):
--   06/2026 — volta como consultora em 19/06 -> 8 de 22 DU
--   07/2026 — vira supervisora em 15/07      -> 10 de 23 DU
-- Com piso, junho e julho empatariam em 0,50. Sem piso: 0,36 e 0,43.
--
--
-- SUPERVISOR SAI PROPORCIONAL, SEM PISO
-- --------------------------------------
-- Mudanca em relacao a ancora da 085 (papel vigente no ULTIMO DIA vale
-- o mes inteiro). Medido em 2026-08-20: 11 janelas de supervisor comecam
-- ou terminam no meio do mes. Sob a ancora, quem foi consultor ate o
-- dia 4 e supervisor no resto perde o mes inteiro — ou ganha, na
-- direcao oposta.
--
-- O custo hoje e pequeno (2 contratos da EVILLYN em 08/2026), mas a
-- correcao e gratuita: e a mesma intersecao de intervalos que o
-- afastamento ja exige. E sem piso, porque promocao tem data exata no
-- supervisor_vigencia.
--
-- A ancora da 085 CONTINUA valendo para o Caderno decidir quem e
-- supervisor numa listagem; o que muda e so o DENOMINADOR.
--
--
-- LIMITE CONHECIDO: FERIADOS SO DE 2026
-- --------------------------------------
-- `feriados` tem 13 linhas, todas de 2026. Nas competencias de 2025 o DU
-- sai sem feriado, entao fica 1 a 2 dias maior que o real. Efeito NULO
-- para quem trabalhou o mes inteiro (o feriado entra no numerador e no
-- denominador, e a razao segue 1,0); afeta so mes PARCIAL, subestimando
-- a fracao em ~5%. Carregar os feriados de 2025 corrige sem tocar nesta
-- funcao.
--
-- Executar no Supabase SQL Editor, depois da 090.
-- =====================================================

CREATE OR REPLACE FUNCTION public.fn_headcount_ponderado(
    p_mes integer,
    p_ano integer
)
RETURNS TABLE (
    loja_id        uuid,
    loja           text,
    peso           numeric,
    cabecas        integer,
    du_competencia integer
)
LANGUAGE sql
STABLE
SET search_path = ''
AS $fn$
WITH
per AS (
    SELECT make_date(p_ano, p_mes, 1) AS ini,
           (make_date(p_ano, p_mes, 1) + INTERVAL '1 month')::date AS fim
),
dias_uteis AS (
    -- Seg-sex menos feriados. Mesma definicao de src/shared/dias_uteis.py,
    -- para dashboard e Caderno nunca discordarem sobre o denominador.
    SELECT g::date AS dia
    FROM per, generate_series(per.ini, per.fim - 1, INTERVAL '1 day') g
    WHERE extract(isodow FROM g) < 6
      AND NOT EXISTS (
          SELECT 1 FROM public.feriados f WHERE f.data = g::date)
),
du AS (SELECT count(*)::integer AS total FROM dias_uteis),
vinc AS (
    -- Um dia so pode cair em UMA janela de vinculo: a invariante de
    -- nao-sobreposicao (087, check 4) garante isso.
    SELECT v.nome_normalizado AS nn, v.loja_id, d.dia, v.origem
    FROM public.consultor_vigencia v
    JOIN dias_uteis d
      ON d.dia >= v.vigencia_inicio
     AND (v.vigencia_fim IS NULL OR d.dia < v.vigencia_fim)
),
afast AS (
    SELECT DISTINCT a.nome_normalizado AS nn, d.dia
    FROM public.consultor_afastamento a
    JOIN dias_uteis d
      ON d.dia >= a.data_inicio
     AND (a.data_fim IS NULL OR d.dia < a.data_fim)
),
sup AS (
    SELECT DISTINCT s.nome_normalizado AS nn, d.dia
    FROM public.supervisor_vigencia s
    JOIN dias_uteis d
      ON d.dia >= s.vigencia_inicio
     AND (s.vigencia_fim IS NULL OR d.dia < s.vigencia_fim)
),
disp AS (
    -- dias DISPONIVEIS por (pessoa, loja)
    SELECT v.nn, v.loja_id, count(*)::integer AS dias
    FROM vinc v
    WHERE NOT EXISTS (SELECT 1 FROM afast a WHERE a.nn = v.nn AND a.dia = v.dia)
      AND NOT EXISTS (SELECT 1 FROM sup   s WHERE s.nn = v.nn AND s.dia = v.dia)
    GROUP BY 1, 2
),
declarado AS (
    -- Reducao com PROCEDENCIA: nao leva piso.
    SELECT DISTINCT nn FROM (
        SELECT nn FROM vinc WHERE origem IN ('ETL', 'MANUAL')
        UNION ALL SELECT nn FROM afast
        UNION ALL SELECT nn FROM sup
    ) x
),
pessoa AS (
    SELECT nn, sum(dias)::integer AS dias_pessoa
    FROM disp GROUP BY 1
),
peso_pessoa AS (
    SELECT
        p.nn,
        p.dias_pessoa,
        CASE
            WHEN p.dias_pessoa = 0            THEN 0::numeric
            WHEN p.dias_pessoa >= du.total    THEN 1::numeric
            -- reducao declarada -> fracao pura
            WHEN d.nn IS NOT NULL
                THEN p.dias_pessoa::numeric / du.total
            -- reducao inferida -> piso de 50%
            ELSE greatest(0.5, p.dias_pessoa::numeric / du.total)
        END AS frac
    FROM pessoa p
    CROSS JOIN du
    LEFT JOIN declarado d ON d.nn = p.nn
)
SELECT
    disp.loja_id,
    l.nome AS loja,
    round(sum(pp.frac * disp.dias::numeric / pp.dias_pessoa), 4) AS peso,
    count(DISTINCT disp.nn)::integer AS cabecas,
    max(du.total)::integer AS du_competencia
FROM disp
JOIN peso_pessoa pp ON pp.nn = disp.nn
JOIN public.lojas l ON l.id = disp.loja_id
CROSS JOIN du
WHERE pp.dias_pessoa > 0
GROUP BY disp.loja_id, l.nome
ORDER BY l.nome;
$fn$;

COMMENT ON FUNCTION public.fn_headcount_ponderado(integer, integer) IS
    'Headcount PONDERADO por loja na competencia. Fonte unica das regras R2 '
    '(peso = dias disponiveis / DU, piso de 50% so em reducao INFERIDA) e R3 '
    '(rateio por loja proporcional aos dias). Cruza os tres ledgers: '
    'consultor_vigencia (loja), consultor_afastamento (disponibilidade) e '
    'supervisor_vigencia (papel). `peso` e o denominador de produtividade; '
    '`cabecas` e a contagem inteira, para auditoria.';

-- Leitura agregada: nao expoe motivo de afastamento, so o peso.
-- Por isso pode ser concedida a anon (ver 089, secao de privacidade).
REVOKE ALL ON FUNCTION public.fn_headcount_ponderado(integer, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.fn_headcount_ponderado(integer, integer)
    TO anon, authenticated, service_role;


-- ===========================================
-- Verificacao (apos executar)
-- ===========================================
-- 1) DU bate com o calendario:
--
--    SELECT DISTINCT du_competencia FROM fn_headcount_ponderado(7, 2026);
--    -- Esperado: 23 (julho/2026, seg-sex, sem feriado na tabela).
--    SELECT DISTINCT du_competencia FROM fn_headcount_ponderado(6, 2026);
--    -- Esperado: 21 (junho/2026 tem Corpus Christi em 04/06).
--
-- 2) INVARIANTE — peso <= cabecas em toda loja (ninguem pesa mais que 1):
--
--    SELECT loja, peso, cabecas FROM fn_headcount_ponderado(7, 2026)
--    WHERE peso > cabecas;
--    -- Esperado: 0 linhas.
--
-- 3) INVARIANTE — soma dos pesos de UMA pessoa nunca passa de 1.
--    (R3: o rateio entre lojas reparte, nao multiplica.)
--    Checagem indireta: o total ponderado nunca supera o total de cabecas.
--
--    SELECT sum(peso) AS peso_total, sum(cabecas) AS cabecas_total
--    FROM fn_headcount_ponderado(7, 2026);
--    -- Esperado: peso_total <= cabecas_total.
--
-- 4) O CASO ERICA — a prova de que o piso ficou onde devia.
--    Valores simulados sobre o banco pos-088/089 em 2026-08-20:
--
--    SELECT loja, peso, cabecas FROM fn_headcount_ponderado(6, 2026)
--    WHERE loja = 'HELP ALCANTARA CARREFOUR';
--    -- Esperado: peso 2.3810, cabecas 3. Decomposicao:
--    --   DOMINIQUE  21/21 = 1.0000
--    --   LUDHIMILLA 21/21 = 1.0000
--    --   ERICA       8/21 = 0.3810  <- volta em 19/06
--    -- 0.3810 e NAO 0.5000: a data e declarada (vinculo origem MANUAL),
--    -- entao a fracao vale pura. Com piso, junho e julho empatariam.
--
--    SELECT loja, peso, cabecas FROM fn_headcount_ponderado(7, 2026)
--    WHERE loja = 'HELP ALCANTARA CARREFOUR';
--    -- Esperado: peso 3.3043, cabecas 4. Decomposicao:
--    --   DOMINIQUE  23/23 = 1.0000
--    --   LUDHIMILLA 23/23 = 1.0000
--    --   THIAGO     20/23 = 0.8696
--    --   ERICA      10/23 = 0.4348  <- vira supervisora em 15/07
--
-- 4b) Os TRES ledgers compondo na mesma pessoa. Entre 02 e 05/2026 a
--     ERICA tem vinculo com HELP ALCANTARA mas esta afastada, entao
--     contribui ZERO:
--
--    SELECT loja, peso FROM fn_headcount_ponderado(3, 2026)
--    WHERE loja = 'HELP ALCANTARA';
--    -- Esperado: o peso NAO inclui a ERICA. Era o bloqueador que a 088
--    -- registrou e que a 089 resolveu.
--
-- 5) O peso VARIA entre competencias (nao virou outro numero achatado).
--    Simulado em 2026-08-20, sem os filtros do Caderno (backoffice e
--    loja inativa entram aqui; a 092 e que os aplica):
--
--    SELECT sum(peso), sum(cabecas), max(du_competencia)
--    FROM fn_headcount_ponderado(7, 2026);
--
--    comp      DU   peso    cabecas   delta
--    05/2025   22   102,00      103    -1,00  (-1,0%)
--    12/2025   23   125,93      132    -6,07  (-4,6%)
--    03/2026   22   124,50      130    -5,50  (-4,2%)
--    06/2026   21   125,86      136   -10,14  (-7,5%)
--    07/2026   23   116,30      124    -7,70  (-6,2%)
--
--    O peso e SEMPRE menor que a contagem inteira — entrada, saida,
--    transferencia, afastamento e troca de papel so podem tirar dia.
--    Denominador menor => produtividade MAIOR. O efeito total sobre o
--    numero publicado hoje combina isto com a troca de cadastro-de-hoje
--    por leitura point-in-time, que anda na direcao oposta.
--
-- 6) Comparacao com a contagem inteira — de quanto o denominador muda:
--
--    SELECT loja, cabecas, peso, round(peso - cabecas, 2) AS delta
--    FROM fn_headcount_ponderado(7, 2026)
--    ORDER BY delta LIMIT 10;
--    -- Esperado: delta <= 0 sempre; as lojas mais negativas sao as que
--    -- tiveram entrada, saida, transferencia ou afastamento no mes.
-- =====================================================
