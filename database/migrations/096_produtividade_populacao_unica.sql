-- =====================================================
-- Migracao 096: uma populacao so no numerador e no denominador
--               (CREATE OR REPLACE de fn_headcount_ponderado + de
--                obter_caderno_fechamento — MESMAS assinaturas)
--
-- AS DUAS FUNCOES NUM ARQUIVO SO, DE PROPOSITO. Elas formam um par:
-- uma calcula o denominador da produtividade, a outra o numerador.
-- Aplicar so uma deixaria o Caderno PIOR do que esta hoje — corrigido
-- de um lado e nao do outro. Nao separar em 096/097.
--
-- Depende de: 085 (ancora de competencia), 091 (peso), 092 (Caderno).
-- Executar no Supabase SQL Editor. Independente da 095: ela toca
-- fn_headcount_replace, que nao aparece aqui.
--
--
-- O DEFEITO, EM UMA FRASE
-- ------------------------
-- `productivity` divide producao que INCLUI supervisor por capacidade
-- que o EXCLUI. Media por consultor calculada sobre duas populacoes
-- diferentes.
--
-- A regra do projeto e explicita — docs/agents/business-rules.md,
-- "Exclusao de supervisores":
--
--   "Aplicar ANTES de rankings, contagens de consultores e MEDIAS POR
--    CONSULTOR."
--
-- E a excecao aberta em 2026-08-10 devolveu supervisor ao TOTAL, com o
-- cuidado de dizer que ele "continua nunca virando linha de consultor
-- em ranking, esqueleto ou MEDIA". `productivity` e media por
-- consultor. Estava fora da regra.
--
--
-- TAMANHO REAL — MEDICAO REVISADA EM 2026-08-26
-- ----------------------------------------------
-- A primeira medicao atribuiu a este defeito 1,30% da produtividade da
-- rede. Estava CONTAMINADA e o numero foi retirado: 98,8% daquela
-- "producao de supervisor" vinha de gente com a data de promocao errada
-- no ledger (o piso 2020-01-01 que a 076 deu a todo supervisor atual),
-- nao de supervisor de verdade.
--
-- Separando as duas causas em 07/2026:
--
--   producao atribuida a supervisor       R$ 130.617,59
--     de janela com piso 2020-01-01       R$ 128.991,16   98,8%
--     de janela com data REAL (este bug)  R$   1.626,43    1,2%
--
--   efeito real na produtividade da rede:  R$ 14,46/pessoa  (0,02%)
--
-- Esta migration corrige um defeito REAL de regra, mas hoje quase sem
-- efeito numerico. Ela existe para que o defeito nao volte a crescer
-- quando um supervisor legitimo vender muito — NAO para consertar os
-- numeros de hoje, que dependem das DATAS.
--
--
-- A ORDEM IMPORTA: DATAS ANTES OU JUNTO
-- --------------------------------------
-- Aplicar so esta migration sobre datas erradas produz um numero
-- DIFERENTE, tambem errado, e obriga a rematerializar duas vezes.
--
-- Medido em HELP PRACA SECA, 07/2026. A loja teve duas pessoas
-- produzindo; o supervisor real (WESLEY) nao vendeu nada, e a segunda
-- maior produtora estava marcada como supervisora desde 2020 por causa
-- do piso — quando so foi promovida em 04/08/2026, para OUTRA loja:
--
--   publicado hoje            peso 1,00    R$ 163.780,34
--   so esta migration         peso 1,00    R$  86.578,34
--   com a data corrigida      peso 2,00    R$  81.890,17   <- correto
--
-- O numero publicado e exatamente o DOBRO do certo: credita a producao
-- de duas pessoas a capacidade de uma. E a correcao de lógica sozinha
-- erra na direcao oposta, jogando fora a producao dela em vez de somar
-- a capacidade.
--
--
-- MUDANCA 1 — fn_headcount_ponderado: papel por COMPETENCIA
-- ----------------------------------------------------------
-- A 085 decidiu (18/ago) que o papel vigente no ULTIMO DIA vale o mes
-- inteiro — "quem fechou o mes responde por ele" — e o cabecalho dela
-- registra que os 8 contratos de ERICA sairiam das visoes
-- consultor-level. A 091 (20/ago) conta DIAS. As duas decisoes sao
-- recentes e corretas isoladamente, mas se multiplicam na mesma
-- metrica, e o resultado e assimetrico nos dois sentidos:
--
--   ERICA    virou supervisora em 15/07 -> producao removida INTEIRA,
--            ~0,43 pessoa ainda no denominador.
--   EMANUELE saiu da supervisao em 15/07 -> nao e supervisora pela
--            ancora, producao conta INTEIRA, mas a 091 so lhe dava os
--            dias de 15 a 31.
--
-- Decisao do usuario (2026-08-26): alinhar a 091 a ancora da 085. Quem
-- responde pela competencia como supervisor nao entra no denominador de
-- consultores dela — peso zero no mes inteiro. Uma populacao so, por
-- construcao, e os dois desvios acima somem juntos.
--
-- Custo medido replicando a 091 em Python para 07/2026:
--
--   ancora DIA (hoje)  peso 113,9565   118 cabecas
--   ancora MES (096)   peso 113,5217   117 cabecas
--
-- 0,4348 pessoa, 0,38% do denominador. (Os valores acima sao pre-filtro
-- de loja; com os filtros do Caderno o peso publicado e 112,4782.)
--
-- O predicado usado e IDENTICO ao de `supervisores_normalizados` na
-- obter_caderno_fechamento e ao de `carregar_supervisores` no
-- dashboard. Uma regra, tres superficies.
--
--
-- MUDANCA 2 — obter_caderno_fechamento: numerador sem supervisor
-- ---------------------------------------------------------------
-- Nova CTE `pago_consultores` e a produtividade passa a dividi-la pelo
-- peso. `paidEffective` NAO muda: continua sendo o total com supervisor,
-- que e a regra de 2026-08-10.
--
-- Como os dois passam a divergir dentro da mesma linha, a produtividade
-- expoe o proprio numerador em **`paidByConsultants`**. Sem isso, quem
-- dividisse `paidEffective / weightedHeadcount` a mao nao fecharia — e
-- foi exatamente esse tipo de armadilha que o contrato de ETL ja tinha
-- alertado no §6.
--
-- Campo NOVO, nada removido nem renomeado. O bereshit ignora chave
-- desconhecida, entao a versao atual dele continua funcionando; so o
-- `networkAverage`, que ele soma de `paidEffective`, permanece com o
-- vies ate ele passar a preferir `paidByConsultants`.
--
--
-- ORDEM DE APLICACAO — IMPORTANTE
-- --------------------------------
--   0. corrigir as datas de `supervisor_vigencia` (piso 2020-01-01) —
--      ver a revisao de 2026-08-26; sem isso os numeros seguem
--      dominados pelo erro de data e a rematerializacao vira dupla;
--   1. esta migration (as duas funcoes, mesma transacao logica);
--   2. o `Numeros_venda` (Python) ja divide pelo peso desde 25/08 —
--      nenhuma mudanca necessaria;
--   3. o bereshit, para o `networkAverage` usar `paidByConsultants`;
--   4. REMATERIALIZAR as competencias — o Caderno e CONGELADO (080),
--      entao nenhum snapshot muda sozinho:
--
--        SELECT fn_materializar_caderno(m, a);  -- para cada competencia
--
-- Sem o passo 4 o relatorio publicado continua com os numeros antigos e
-- a correcao nao chega a ninguem.
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
    -- ANCORA DE COMPETENCIA (096), nao mais por DIA.
    --
    -- Ate a 095 esta CTE devolvia (pessoa, dia) e o papel reduzia o peso
    -- proporcionalmente. Isso discordava da 085, que ancora o papel no
    -- ULTIMO DIA da competencia e vale o mes inteiro: quem virou
    -- supervisor no meio do mes tinha a producao removida INTEIRA das
    -- visoes consultor-level e mesmo assim contribuia com peso parcial
    -- no denominador. Numerador e denominador contavam populacoes
    -- diferentes.
    --
    -- Predicado IDENTICO ao de `supervisores_normalizados` na
    -- obter_caderno_fechamento (085/092) — e o mesmo `carregar_supervisores`
    -- do dashboard. Uma regra so, tres superficies.
    --
    -- Janela meio-aberta [inicio, fim): quem encerra exatamente no ultimo
    -- dia NAO o cobre, e a competencia fica com o sucessor.
    SELECT DISTINCT s.nome_normalizado AS nn
    FROM public.supervisor_vigencia s
    CROSS JOIN per
    WHERE s.vigencia_inicio <= (per.fim - 1)
      AND (s.vigencia_fim IS NULL OR s.vigencia_fim > (per.fim - 1))
),
disp AS (
    -- dias DISPONIVEIS por (pessoa, loja)
    SELECT v.nn, v.loja_id, count(*)::integer AS dias
    FROM vinc v
    WHERE NOT EXISTS (SELECT 1 FROM afast a WHERE a.nn = v.nn AND a.dia = v.dia)
      -- Supervisor pela ancora nao tem NENHUM dia disponivel na
      -- competencia: ele nao e consultor daquele mes, e nao de parte
      -- dele. Com zero dias a pessoa cai fora de `pessoa` e nunca
      -- alcanca `peso_pessoa`.
      AND NOT EXISTS (SELECT 1 FROM sup   s WHERE s.nn = v.nn)
    GROUP BY 1, 2
),
declarado AS (
    -- Reducao com PROCEDENCIA: nao leva piso.
    -- `sup` saiu desta uniao na 096 e a remocao e deliberada: com a
    -- ancora de competencia, supervisor tem zero dias disponiveis e
    -- nunca chega a `peso_pessoa`. O ramo virou inalcancavel, e deixa-lo
    -- sugeriria uma reducao parcial que nao existe mais.
    SELECT DISTINCT nn FROM (
        SELECT nn FROM vinc WHERE origem IN ('ETL', 'MANUAL')
        UNION ALL SELECT nn FROM afast
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
    'supervisor_vigencia (papel). O PAPEL vale por COMPETENCIA, nao por dia '
    '(096): quem era supervisor no ULTIMO dia do mes tem peso ZERO no mes '
    'inteiro, mesma ancora da 085 e de carregar_supervisores — numerador e '
    'denominador da produtividade contam a mesma populacao. `peso` e o '
    'denominador de produtividade; `cabecas` e a contagem inteira, para '
    'auditoria.';

-- Leitura agregada: nao expoe motivo de afastamento, so o peso.
-- Por isso pode ser concedida a anon (ver 089, secao de privacidade).
REVOKE ALL ON FUNCTION public.fn_headcount_ponderado(integer, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.fn_headcount_ponderado(integer, integer)
    TO anon, authenticated, service_role;


CREATE OR REPLACE FUNCTION public.obter_caderno_fechamento(
    p_mes integer,
    p_ano integer
)
RETURNS jsonb
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
WITH
lojas_backoffice AS (
    -- Fonte unica do literal: um novo ponto de backoffice entra aqui e
    -- passa a valer para todos os eixos comparativos de uma vez.
    SELECT unnest(ARRAY['VAI E VEM']) AS nome
),
periodos_ano AS (
    SELECT id, mes, ano, referencia
    FROM public.periodos
    WHERE ano = p_ano
      AND mes BETWEEN 1 AND p_mes
),
periodo AS (
    SELECT *
    FROM periodos_ano
    WHERE mes = p_mes
),
pontos_categoria_ano AS (
    SELECT
        per.id AS periodo_id,
        pc.categoria_codigo,
        pc.pontos
    FROM periodos_ano per
    CROSS JOIN LATERAL public.obter_pontuacao_periodo(per.mes, per.ano) pc
),
contratos_canonicos AS (
    SELECT
        v.*,
        per.mes AS competencia_mes,
        per.ano AS competencia_ano,
        upper(btrim(coalesce(prod.tipo_operacao, ''))) AS modalidade_tabela,
        coalesce(
            v.categoria_codigo,
            CASE upper(btrim(coalesce(v.tipo_produto, '')))
                WHEN 'CNC' THEN 'CNC'
                WHEN 'CNC 13º' THEN 'CNC_13'
                WHEN 'CNC 13' THEN 'CNC_13'
                WHEN 'CNC ANT' THEN 'ANT_BENEF'
                WHEN 'ANT. DE BENEF.' THEN 'ANT_BENEF'
                WHEN 'SAQUE' THEN 'SAQUE'
                WHEN 'SAQUE BENEFICIO' THEN 'SAQUE_BENEFICIO'
                WHEN 'CONSIG' THEN 'CONSIG_BMG'
                WHEN 'CONSIG BMG' THEN 'CONSIG_BMG'
                WHEN 'CONSIG PRIV' THEN 'CONSIG_PRIV'
                WHEN 'CLT' THEN 'CONSIG_PRIV'
                WHEN 'CONSIG ITAU' THEN 'CONSIG_ITAU'
                WHEN 'CONSIG C6' THEN 'CONSIG_C6'
                WHEN 'FGTS' THEN 'FGTS'
                WHEN 'EMISSAO' THEN 'CARTAO'
                WHEN 'EMISSAO CB' THEN 'CARTAO'
                WHEN 'EMISSAO CC' THEN 'CARTAO'
                WHEN 'PORTABILIDADE' THEN 'PORTABILIDADE'
            END
        ) AS categoria_canonica
    FROM public.v_contratos_dashboard v
    JOIN periodos_ano per ON per.id = v.periodo_id
    LEFT JOIN public.produtos prod ON prod.tabela = v.produto
),
contratos_classificados AS (
    SELECT
        v.contrato_id,
        v.periodo_id,
        v.competencia_mes,
        v.competencia_ano,
        v.loja,
        v.regiao,
        v.regiao_atual,
        v.consultor,
        v.categoria_canonica AS categoria_codigo,
        v.banco,
        v.subtipo,
        v.prazo,
        v.modalidade_tabela,
        CASE
            WHEN coalesce(v.conta_valor, true) = false THEN 0
            ELSE coalesce(v.valor_consolidado, 0)
        END::numeric AS valor_pago,
        CASE
            WHEN v.categoria_canonica = 'PORTABILIDADE' THEN
                CASE upper(btrim(coalesce(v.banco, '')))
                    WHEN 'BMG' THEN 'CONSIG_BMG'
                    WHEN 'BANCO BMG' THEN 'CONSIG_BMG'
                    WHEN 'C6 BANK' THEN 'CONSIG_C6'
                    WHEN 'C6' THEN 'CONSIG_C6'
                    WHEN 'BANCO C6' THEN 'CONSIG_C6'
                    WHEN 'ITAU' THEN 'CONSIG_ITAU'
                    WHEN 'ITAÚ' THEN 'CONSIG_ITAU'
                    WHEN 'BANCO ITAU' THEN 'CONSIG_ITAU'
                    WHEN 'BANCO ITAÚ' THEN 'CONSIG_ITAU'
                END
            ELSE v.categoria_canonica
        END AS categoria_pontos,
        CASE
            WHEN v.modalidade_tabela = 'FLEX' THEN 'FLEX'
            WHEN v.categoria_canonica IN ('CONSIG_BMG', 'CONSIG_ITAU', 'CONSIG_C6')
             AND upper(btrim(coalesce(v.subtipo, ''))) = 'NOVO'
             AND nullif(regexp_replace(coalesce(v.prazo, ''), '[^0-9]', '', 'g'), '')::integer < 96
                THEN 'FLEX'
            WHEN v.modalidade_tabela = 'NORMAL' THEN 'NORMAL'
            ELSE 'DESCONHECIDA'
        END AS classificacao_validade,
        CASE
            WHEN v.categoria_canonica IN ('CNC', 'CNC_13', 'SUPER_CONTA') THEN 'CNC'
            WHEN v.categoria_canonica = 'FGTS' THEN 'FGTS'
            WHEN v.categoria_canonica IN ('SAQUE', 'SAQUE_BENEFICIO') THEN 'SAQUE'
            WHEN v.categoria_canonica = 'CONSIG_PRIV' THEN 'CLT'
            WHEN v.categoria_canonica = 'ANT_BENEF' THEN 'ANTECIP_BENEFICIO'
            WHEN v.categoria_canonica IN ('CONSIG_BMG', 'CONSIG_ITAU', 'CONSIG_C6', 'PORTABILIDADE') THEN 'CONSIGNADO'
        END AS grupo_mix,
        coalesce(v.conta_pontuacao, true) AS conta_pontuacao
    FROM contratos_canonicos v
),
base_ano AS (
    SELECT
        c.*,
        coalesce(pc.pontos, 0)::numeric AS multiplicador_pontos,
        CASE WHEN c.conta_pontuacao
             THEN c.valor_pago * coalesce(pc.pontos, 0)
             ELSE 0 END::numeric AS pontos_efetivos,
        CASE WHEN c.classificacao_validade = 'NORMAL'
             THEN c.valor_pago ELSE 0 END::numeric AS valor_valido,
        CASE WHEN c.classificacao_validade = 'FLEX'
             THEN c.valor_pago ELSE 0 END::numeric AS valor_flex
    FROM contratos_classificados c
    LEFT JOIN pontos_categoria_ano pc
      ON pc.periodo_id = c.periodo_id
     AND pc.categoria_codigo = c.categoria_pontos
),
base AS (
    SELECT *
    FROM base_ano
    WHERE competencia_mes = p_mes
),
metas_ano AS (
    SELECT
        per.mes AS competencia_mes,
        per.ano AS competencia_ano,
        m.loja,
        m.regiao,
        m.nivel,
        m.valor
    FROM periodos_ano per
    CROSS JOIN LATERAL public.obter_metas_geral_loja(per.mes, per.ano) m
),
metas_loja AS (
    SELECT
        loja,
        max(regiao) AS regiao,
        sum(valor) FILTER (WHERE nivel = 'PRATA')::numeric AS meta_prata,
        sum(valor) FILTER (WHERE nivel = 'OURO')::numeric AS meta_ouro
    FROM metas_ano
    WHERE competencia_mes = p_mes
    GROUP BY loja
),
lojas AS (
    SELECT
        coalesce(b.loja, m.loja) AS loja,
        coalesce(max(b.regiao), max(m.regiao), '') AS regiao,
        coalesce(sum(b.valor_pago), 0)::numeric AS pago,
        coalesce(sum(b.valor_valido), 0)::numeric AS valido,
        coalesce(sum(b.pontos_efetivos), 0)::numeric AS pontos,
        coalesce(max(m.meta_prata), 0)::numeric AS meta_prata,
        coalesce(max(m.meta_ouro), 0)::numeric AS meta_ouro
    FROM base b
    FULL JOIN metas_loja m ON m.loja = b.loja
    WHERE upper(btrim(coalesce(b.loja, m.loja, '')))
          NOT IN (SELECT nome FROM lojas_backoffice)
    GROUP BY coalesce(b.loja, m.loja)
),
ranking AS (
    SELECT
        row_number() OVER (
            ORDER BY CASE WHEN meta_prata > 0 THEN pontos / meta_prata ELSE 0 END DESC,
                     pontos DESC, loja
        ) AS position,
        loja AS store,
        regiao AS manager,
        pago AS "paidEffective",
        valido AS "validProduction",
        pontos AS "effectivePoints",
        meta_prata AS "silverGoal",
        meta_ouro AS "goldGoal",
        CASE WHEN meta_prata > 0 THEN pontos / meta_prata ELSE 0 END AS "silverAchievement",
        CASE WHEN meta_ouro > 0 THEN pontos / meta_ouro ELSE 0 END AS "goldAchievement"
    FROM lojas
),
pontos_mensais_loja AS (
    SELECT
        competencia_mes,
        loja,
        regiao,
        sum(pontos_efetivos)::numeric AS pontos
    FROM base_ano
    WHERE loja IS NOT NULL
      AND upper(btrim(loja)) NOT IN (SELECT nome FROM lojas_backoffice)
    GROUP BY competencia_mes, loja, regiao
),
metas_mensais_loja AS (
    SELECT
        competencia_mes,
        loja,
        regiao,
        coalesce(sum(valor) FILTER (WHERE nivel = 'PRATA'), 0)::numeric AS meta_prata,
        coalesce(sum(valor) FILTER (WHERE nivel = 'OURO'), 0)::numeric AS meta_ouro
    FROM metas_ano
    WHERE upper(btrim(coalesce(loja, '')))
          NOT IN (SELECT nome FROM lojas_backoffice)
    GROUP BY competencia_mes, loja, regiao
),
desempenho_mensal_base AS (
    SELECT
        coalesce(p.competencia_mes, m.competencia_mes) AS competencia_mes,
        coalesce(p.loja, m.loja) AS loja,
        coalesce(p.regiao, m.regiao, '') AS regiao,
        coalesce(p.pontos, 0)::numeric AS pontos,
        coalesce(m.meta_prata, 0)::numeric AS meta_prata,
        coalesce(m.meta_ouro, 0)::numeric AS meta_ouro
    FROM pontos_mensais_loja p
    FULL JOIN metas_mensais_loja m
      ON m.competencia_mes = p.competencia_mes
     AND m.loja = p.loja
     AND m.regiao = p.regiao
),
desempenho_mensal AS (
    SELECT
        competencia_mes AS month,
        loja AS store,
        regiao AS manager,
        pontos AS "effectivePoints",
        meta_prata AS "silverGoal",
        meta_ouro AS "goldGoal",
        CASE WHEN meta_prata > 0 THEN pontos / meta_prata ELSE 0 END AS "silverAchievement",
        CASE WHEN meta_ouro > 0 THEN pontos / meta_ouro ELSE 0 END AS "goldAchievement",
        CASE
            WHEN meta_ouro > 0 AND pontos >= meta_ouro THEN 'OURO'
            WHEN meta_prata > 0 AND pontos >= meta_prata THEN 'PRATA'
            WHEN meta_prata = 0 AND meta_ouro = 0 THEN 'SEM_META'
            ELSE 'ABAIXO'
        END AS level
    FROM desempenho_mensal_base
),
consultores_mais_recentes AS (
    SELECT DISTINCT ON (n.nome_normalizado)
        c.id,
        c.nome,
        c.loja_id,
        c.status,
        c.updated_at,
        n.nome_normalizado
    FROM public.consultores c
    CROSS JOIN LATERAL (
        SELECT upper(
            regexp_replace(btrim(coalesce(c.nome, '')), '[[:space:]]+', ' ', 'g')
        ) AS nome_normalizado
    ) n
    WHERE n.nome_normalizado <> ''
    ORDER BY n.nome_normalizado, c.updated_at DESC NULLS LAST, c.id DESC
),
competencia_ancora AS (
    -- Ancora de leitura REVISADA em 2026-08-18 (ver cabecalho): o papel
    -- vigente no ULTIMO DIA da competencia vale para o mes inteiro —
    -- quem fechou o mes responde por ele. Continua sendo UMA regra so
    -- para producao e headcount, entao nenhum mes fica com a pessoa
    -- dentro do ranking e fora do denominador ao mesmo tempo.
    --
    -- Janela meio-aberta [inicio, fim): quem encerra exatamente no
    -- ultimo dia do mes NAO cobre esse dia, entao o mes pertence ao
    -- sucessor. E a mesma convencao usada em todo o ledger.
    SELECT (make_date(p_ano, p_mes, 1)
            + INTERVAL '1 month - 1 day')::date AS dia
),
supervisores_normalizados AS (
    -- POINT-IN-TIME (076/077/078/084): quem era supervisor NA COMPETENCIA,
    -- nao quem e supervisor hoje. Antes desta versao a foto do presente
    -- filtrava toda a historia, entao uma promocao apagava
    -- retroativamente os meses em que a pessoa vendia como consultora e
    -- uma saida da supervisao devolvia os meses em que ela supervisionava.
    SELECT DISTINCT v.nome_normalizado
    FROM public.supervisor_vigencia v
    CROSS JOIN competencia_ancora a
    WHERE v.vigencia_inicio <= a.dia
      AND (v.vigencia_fim IS NULL OR v.vigencia_fim > a.dia)
),
pago_consultores AS (
    -- Producao que entra na PRODUTIVIDADE — sem supervisor.
    --
    -- Ate a 095 a produtividade era `pago / peso`, com `pago` incluindo a
    -- producao de quem era supervisor e `peso` excluindo a capacidade
    -- dele. Media por consultor calculada sobre populacoes diferentes.
    --
    -- A regra do projeto e explicita (docs/agents/business-rules.md,
    -- "Exclusao de supervisores"): aplicar ANTES de rankings, contagens
    -- de consultores e MEDIAS POR CONSULTOR. A excecao de 2026-08-10
    -- devolveu supervisor ao TOTAL — e so ao total; media nunca.
    --
    -- Medido em 07/2026 antes da correcao: R$ 130.617,59 (1,29% do pago)
    -- vinham de 17 supervisores, dos quais 16 supervisionaram o mes
    -- inteiro e pesavam ZERO no denominador. Na rede isso inflava a
    -- produtividade em 1,30%; em HELP PRACA SECA, que tem peso 1,00 e
    -- recebeu R$ 77.202 de uma supervisora, inflava 89,2% — e
    -- `productivity` e o que ORDENA o ranking publicado.
    --
    -- `paidEffective` continua sendo o total COM supervisor: e a regra
    -- de 2026-08-10 e nao muda aqui. Por isso a produtividade passa a
    -- expor o proprio numerador (`paidByConsultants`), senao quem
    -- dividir `paidEffective / weightedHeadcount` a mao continua sem
    -- fechar — exatamente a armadilha que o contrato de ETL ja alertou.
    SELECT
        b.loja,
        coalesce(sum(b.valor_pago), 0)::numeric AS pago
    FROM base b
    LEFT JOIN supervisores_normalizados s
      ON s.nome_normalizado = upper(regexp_replace(
             btrim(coalesce(b.consultor, '')), '[[:space:]]+', ' ', 'g'))
    WHERE s.nome_normalizado IS NULL
      AND upper(btrim(coalesce(b.loja, '')))
          NOT IN (SELECT nome FROM lojas_backoffice)
    GROUP BY b.loja
),
consultores_ativos AS (
    -- Status vazio conta como ativo (linhas legadas sem status); match por
    -- prefixo para "Inativo (a)" nunca entrar. Mesma regra do dashboard.
    SELECT c.*
    FROM consultores_mais_recentes c
    WHERE btrim(coalesce(c.status, '')) = ''
       OR upper(btrim(c.status)) LIKE 'ATIVO%'
),
consultores_classificados AS (
    -- As quatro categorias abaixo particionam o cadastro ativo: cada
    -- consultor cai em exatamente uma, e so a ultima entra no headcount.
    SELECT
        l.nome AS loja,
        (s.nome_normalizado IS NOT NULL) AS eh_supervisor,
        (l.id IS NOT NULL AND coalesce(l.ativo, true)) AS tem_loja_ativa,
        (upper(btrim(coalesce(l.nome, '')))
             IN (SELECT nome FROM lojas_backoffice)) AS eh_backoffice
    FROM consultores_ativos c
    LEFT JOIN public.lojas l ON l.id = c.loja_id
    LEFT JOIN supervisores_normalizados s
      ON s.nome_normalizado = c.nome_normalizado
),
headcount_loja AS (
    SELECT
        loja,
        count(*)::integer AS total
    FROM consultores_classificados
    WHERE NOT eh_supervisor
      AND tem_loja_ativa
      AND NOT eh_backoffice
    GROUP BY loja
),
headcount_diagnostico AS (
    SELECT
        count(*)::integer AS ativos_cadastro,
        count(*) FILTER (WHERE eh_supervisor)::integer AS supervisores,
        count(*) FILTER (
            WHERE NOT eh_supervisor AND NOT tem_loja_ativa
        )::integer AS sem_loja_ativa,
        count(*) FILTER (
            WHERE NOT eh_supervisor AND tem_loja_ativa AND eh_backoffice
        )::integer AS backoffice
    FROM consultores_classificados
),
headcount_ponderado AS (
    -- FONTE DO NUMERO PUBLICADO (091). `cabecas` e a contagem inteira
    -- point-in-time; `peso` e o gente-mes que divide o pago.
    --
    -- A 091 devolve TODA loja com vinculo, inclusive backoffice e loja
    -- inativa — ela responde "quem estava onde", nao "o que entra no
    -- Caderno". Os dois filtros que o headcount do cadastro ja aplicava
    -- (`tem_loja_ativa`, `NOT eh_backoffice`) sao reaplicados aqui.
    SELECT
        h.loja,
        h.peso,
        h.cabecas
    FROM public.fn_headcount_ponderado(p_mes, p_ano) h
    JOIN public.lojas l ON l.id = h.loja_id
    WHERE coalesce(l.ativo, true)
      AND upper(btrim(coalesce(h.loja, '')))
          NOT IN (SELECT nome FROM lojas_backoffice)
),
headcount AS (
    SELECT
        coalesce(sum(cabecas), 0)::integer AS total,
        coalesce(sum(peso), 0)::numeric    AS peso_total
    FROM headcount_ponderado
),
headcount_cadastro AS (
    -- O antigo `activeConsultants` (cadastro de HOJE). Deixa de ser o
    -- numero publicado e vira linha de auditoria em
    -- headcountDiagnostics.countedInRegistry, onde a identidade da 075
    -- continua fechando.
    SELECT coalesce(sum(total), 0)::integer AS total
    FROM headcount_loja
),
produtividade_base AS (
    SELECT
        l.loja,
        l.regiao,
        l.pago,
        coalesce(h.cabecas, 0)::integer AS ativos,
        coalesce(h.peso, 0)::numeric    AS peso,
        coalesce(pc.pago, 0)::numeric   AS pago_consultores,
        -- Denominador PONDERADO (R2/R3). Peso 0 devolve 0, mesmo idioma
        -- que a 085 usava para ativos 0: loja sem ninguem no ledger nao
        -- tem produtividade definida, e inventar uma seria pior.
        --
        -- Numerador SEM supervisor (096): mesma populacao do denominador.
        CASE WHEN coalesce(h.peso, 0) > 0
             THEN coalesce(pc.pago, 0) / h.peso
             ELSE 0 END::numeric AS produtividade
    FROM lojas l
    LEFT JOIN headcount_ponderado h ON h.loja = l.loja
    LEFT JOIN pago_consultores    pc ON pc.loja = l.loja
    -- `lojas` ja exclui o backoffice; filtro redundante removido aqui.
),
produtividade AS (
    SELECT
        row_number() OVER (ORDER BY produtividade DESC, pago DESC, loja) AS position,
        loja AS store,
        regiao AS manager,
        pago AS "paidEffective",
        pago_consultores AS "paidByConsultants",
        ativos AS "activeConsultants",
        peso AS "weightedHeadcount",
        produtividade AS productivity
    FROM produtividade_base
),
resumo AS (
    SELECT
        coalesce(sum(valor_pago), 0)::numeric AS pago,
        coalesce(sum(valor_valido), 0)::numeric AS valido,
        coalesce(sum(valor_flex), 0)::numeric AS flex,
        coalesce(sum(pontos_efetivos), 0)::numeric AS pontos,
        count(*) FILTER (WHERE classificacao_validade = 'DESCONHECIDA')::integer AS desconhecidos
    FROM base
),
backoffice AS (
    SELECT
        coalesce(sum(valor_pago), 0)::numeric AS pago,
        coalesce(sum(valor_valido), 0)::numeric AS valido
    FROM base
    WHERE upper(btrim(coalesce(loja, ''))) IN (SELECT nome FROM lojas_backoffice)
),
mix AS (
    SELECT
        grupo_mix AS product,
        sum(valor_pago)::numeric AS "paidEffective",
        CASE WHEN sum(sum(valor_pago)) OVER () > 0
             THEN sum(valor_pago) / sum(sum(valor_pago)) OVER ()
             ELSE 0 END::numeric AS share
    FROM base
    WHERE grupo_mix IS NOT NULL
    GROUP BY grupo_mix
),
produto_lojas AS (
    SELECT
        grupo_mix AS product,
        loja AS store,
        max(regiao) AS manager,
        sum(valor_pago)::numeric AS "paidEffective",
        sum(valor_valido)::numeric AS "validProduction",
        sum(pontos_efetivos)::numeric AS "effectivePoints"
    FROM base
    WHERE grupo_mix IS NOT NULL
      AND loja IS NOT NULL
      AND upper(btrim(loja)) NOT IN (SELECT nome FROM lojas_backoffice)
    GROUP BY grupo_mix, loja
),
produto_ranking AS (
    SELECT
        product,
        row_number() OVER (PARTITION BY product ORDER BY "paidEffective" DESC, store) AS position,
        store,
        manager,
        "paidEffective",
        "validProduction",
        "effectivePoints"
    FROM produto_lojas
)
SELECT jsonb_build_object(
    'competence', jsonb_build_object('month', p_mes, 'year', p_ano, 'label', max(per.referencia)),
    'summary', jsonb_build_object(
        'paidEffective', max(r.pago),
        'validProduction', max(r.valido),
        'flexProduction', max(r.flex),
        'effectivePoints', max(r.pontos),
        'silverGoal', coalesce((SELECT sum(meta_prata) FROM lojas), 0),
        'storeCount', (SELECT count(*) FROM lojas),
        'activeConsultants', max(h.total),
        'weightedHeadcount', max(h.peso_total),
        'unknownClassificationCount', max(r.desconhecidos),
        'backoffice', jsonb_build_object(
            'paidEffective', max(bo.pago),
            'validProduction', max(bo.valido)
        ),
        'headcountDiagnostics', jsonb_build_object(
            'activeRegistered', max(hd.ativos_cadastro),
            'supervisorsExcluded', max(hd.supervisores),
            'withoutActiveStore', max(hd.sem_loja_ativa),
            'backofficeExcluded', max(hd.backoffice),
            'countedInRegistry', max(hcad.total)
        )
    ),
    'ranking', coalesce((SELECT jsonb_agg(to_jsonb(rk) ORDER BY rk.position) FROM ranking rk), '[]'::jsonb),
    'monthlyPoints', coalesce((
        SELECT jsonb_agg(to_jsonb(dm) ORDER BY dm.month, dm.manager, dm.store)
        FROM desempenho_mensal dm
    ), '[]'::jsonb),
    'productivity', coalesce((
        SELECT jsonb_agg(to_jsonb(prd) ORDER BY prd.position)
        FROM produtividade prd
    ), '[]'::jsonb),
    'mix', coalesce((SELECT jsonb_agg(to_jsonb(mx) ORDER BY mx."paidEffective" DESC) FROM mix mx), '[]'::jsonb),
    'productRanking', coalesce((
        SELECT jsonb_agg(to_jsonb(pr) ORDER BY pr.product, pr.position)
        FROM produto_ranking pr
    ), '[]'::jsonb)
)
FROM periodo per
CROSS JOIN resumo r
CROSS JOIN headcount h
CROSS JOIN backoffice bo
CROSS JOIN headcount_diagnostico hd
CROSS JOIN headcount_cadastro hcad;
$$;
