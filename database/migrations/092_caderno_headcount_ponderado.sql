-- =====================================================
-- Migracao 092: o Caderno passa a ler o headcount do LEDGER
--               (point-in-time) e a produtividade passa a
--               ser dividida pelo PESO
--
-- Substitui as CTEs de headcount e produtividade da 085. O resto da
-- funcao — producao, metas, ranking, serie mensal, MIX, produto — e
-- byte-identico.
--
-- Esta e a migration que QUEBRA CONTRATO com o bereshit: `productivity`
-- muda de patamar e `weightedHeadcount` nasce. Ver "Deploy coordenado".
--
--
-- O QUE ESTAVA ERRADO
-- --------------------
-- Ate a 085 o headcount do Caderno vinha do CADASTRO DE HOJE: contava
-- quem esta ativo agora e projetava esse numero para tras, sobre todas
-- as competencias. Medido em 2026-08-21, comparando o que a funcao
-- devolvia com o que os ledgers dizem:
--
--   competencia   cadastro(hoje)   cabecas(ledger)   peso
--   07/2025            124               108         101,57
--   12/2025            124               130         123,93
--   02/2026            124               118         115,39
--   03/2026            124               128         122,50
--   06/2026            124               134         123,86
--   07/2026            122               122         114,30
--
-- O cadastro devolve 124 FIXO em quase toda competencia — nao porque o
-- quadro ficou estavel, mas porque so existe UMA foto e ela e a de hoje.
-- Consequencia pratica ja observada (progress de 2026-08-20): toda carga
-- de RH reescrevia as 14 competencias publicadas ao vivo, e o snapshot
-- congelado divergia da funcao sem que nada de negocio tivesse mudado.
--
--
-- O QUE MUDA
-- -----------
--   summary.activeConsultants   cadastro de hoje  ->  `cabecas` da 091
--                               (point-in-time; inteiro, como antes)
--   summary.weightedHeadcount   NOVO — soma dos pesos da 091
--   productivity[].activeConsultants   idem, por loja
--   productivity[].weightedHeadcount   NOVO, por loja
--   productivity[].productivity        pago/ativos -> pago/PESO
--
-- `activeConsultants` continua INTEIRO e continua respondendo "quantas
-- pessoas"; o que muda e a foto de onde ele sai. Quem responde "quanto
-- de gente-mes a loja teve" agora e `weightedHeadcount`, e e ele que
-- divide o pago.
--
-- Decisao do usuario em 2026-08-21, com os numeros da tabela acima na
-- mao: o inteiro publicado passa a ser point-in-time. A alternativa —
-- manter o cadastro e publicar os dois — deixaria o Caderno com dois
-- inteiros que discordam entre si e nao resolveria o drift.
--
--
-- A IDENTIDADE DO headcountDiagnostics MUDA DE SIGNIFICADO
-- ---------------------------------------------------------
-- Ate a 085 valia:
--   activeRegistered = activeConsultants + supervisorsExcluded
--                      + withoutActiveStore + backofficeExcluded
--
-- Com `activeConsultants` vindo do ledger, essa soma DEIXA de fechar —
-- os dois lados passam a falar de fotos diferentes. Para nao perder a
-- auditoria, o antigo numero entra no proprio bloco de diagnostico como
-- `countedInRegistry`, e a identidade continua valendo LA DENTRO:
--
--   activeRegistered = countedInRegistry + supervisorsExcluded
--                      + withoutActiveStore + backofficeExcluded
--
-- Ler `countedInRegistry` <> `activeConsultants` nao e defeito: e a
-- distancia entre o cadastro de hoje e o quadro daquele mes, agora
-- visivel em vez de silenciosa.
--
--
-- POR QUE O PESO E NAO AS CABECAS NO DENOMINADOR
-- -----------------------------------------------
-- Regra R2/R3, aprovada em 2026-08-20 e implementada na 091: quem
-- trabalhou meio mes conta meio. Dividir por cabecas trata quem entrou
-- dia 20 igual a quem estava desde o dia 1o e PUNE a loja que recebeu
-- gente nova no fim do mes. O peso e sempre <= cabecas, entao a
-- produtividade publicada SOBE em relacao a 085 — nao e melhora de
-- resultado, e correcao de denominador.
--
-- Backoffice (VAI E VEM) e loja inativa ficam de fora do peso, como ja
-- ficavam do headcount — a 091 nao filtra nenhum dos dois, entao o
-- filtro e feito aqui, no leitor.
--
-- Loja com peso 0 e pago > 0 devolve produtividade 0, mesmo idioma que
-- a 085 ja usava para ativos 0. Medido: 1 loja em 07/2025 (PDV BELFORD
-- ROXO II, sem nenhuma linha no ledger) contra 2 no criterio antigo.
--
--
-- DEPLOY COORDENADO — OBRIGATORIO
-- --------------------------------
-- Entre esta migration entrar e o bereshit ler `weightedHeadcount`, o
-- relatorio fica internamente inconsistente: headcount inteiro ao lado
-- de produtividade calculada sobre o peso. Tem de sair na MESMA janela:
--
--   1. aplicar esta migration;
--   2. subir o bereshit lendo `weightedHeadcount`;
--   3. rematerializar as 14 competencias (bloco no fim do arquivo).
--
-- A rematerializacao estava SEGURA desde a 088 esperando por esta
-- migration (ver progress de 2026-08-20): rematerializar antes so
-- recongelaria o cadastro do dia.
--
-- AVISAR AS LOJAS ANTES: trocar o denominador derruba todas as medias
-- publicadas. E mudanca de patamar, nao refinamento.
--
-- Executar no Supabase SQL Editor, depois da 091.
-- =====================================================

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
        -- Denominador PONDERADO (R2/R3). Peso 0 devolve 0, mesmo idioma
        -- que a 085 usava para ativos 0: loja sem ninguem no ledger nao
        -- tem produtividade definida, e inventar uma seria pior.
        CASE WHEN coalesce(h.peso, 0) > 0
             THEN l.pago / h.peso
             ELSE 0 END::numeric AS produtividade
    FROM lojas l
    LEFT JOIN headcount_ponderado h ON h.loja = l.loja
    -- `lojas` ja exclui o backoffice; filtro redundante removido aqui.
),
produtividade AS (
    SELECT
        row_number() OVER (ORDER BY produtividade DESC, pago DESC, loja) AS position,
        loja AS store,
        regiao AS manager,
        pago AS "paidEffective",
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

COMMENT ON FUNCTION public.obter_caderno_fechamento(integer, integer) IS
    'Contrato agregado v1.7 do Caderno de Fechamento. Headcount e '
    'produtividade vem do LEDGER (fn_headcount_ponderado, 091), nao mais do '
    'cadastro de hoje: summary.activeConsultants e '
    'productivity[].activeConsultants sao a contagem inteira POINT-IN-TIME da '
    'competencia, summary.weightedHeadcount e productivity[].weightedHeadcount '
    'trazem o gente-mes ponderado (R2: dias disponiveis / DU, piso de 50% so em '
    'reducao inferida; R3: rateio por loja), e productivity[].productivity e '
    'PAGO dividido pelo PESO. Backoffice e loja inativa ficam fora do peso. '
    'summary.headcountDiagnostics decompoe o CADASTRO ativo (foto de hoje) em '
    'countedInRegistry, supervisores, sem loja ativa e backoffice — a soma '
    'fecha contra activeRegistered, NAO contra activeConsultants, que vem de '
    'outra foto. Serie mensal de pontos/metas com regiao historica por '
    'competencia e niveis Prata/Ouro. Supervisor da competencia sai pelo papel '
    'vigente no ULTIMO dia do mes (085). VAI E VEM, ponto de backoffice, fica '
    'fora de ranking, contagem de lojas, serie mensal, rankings por produto, '
    'produtividade e headcount, mas segue somado em paidEffective, '
    'validProduction e MIX; o montante vai em summary.backoffice.';

REVOKE ALL ON FUNCTION public.obter_caderno_fechamento(integer, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.obter_caderno_fechamento(integer, integer) TO anon, authenticated;


-- ===========================================
-- Validacao pos-migracao
-- ===========================================
-- Valores medidos em 2026-08-21 contra o banco pos-091, simulando o
-- resultado desta funcao antes de escreve-la. Se algum divergir, a
-- migration NAO fez o que este cabecalho descreve.
--
-- 1) O inteiro publicado deixa de ser 124 fixo e passa a variar:
--
--    SELECT (obter_caderno_fechamento(m, a) -> 'summary' ->> 'activeConsultants')::int
--    FROM (VALUES (7,2025),(12,2025),(2,2026),(3,2026),(6,2026),(7,2026)) v(m,a);
--    -- Esperado, na ordem: 108, 130, 118, 128, 134, 122.
--    -- (Antes desta migration: 124,124,124,124,124,122.)
--
-- 2) O peso nasce e e sempre <= o inteiro:
--
--    SELECT obter_caderno_fechamento(7, 2026) -> 'summary' ->> 'weightedHeadcount';
--    -- Esperado: 114.3043
--    SELECT obter_caderno_fechamento(6, 2026) -> 'summary' ->> 'weightedHeadcount';
--    -- Esperado: 123.8573
--    SELECT obter_caderno_fechamento(7, 2025) -> 'summary' ->> 'weightedHeadcount';
--    -- Esperado: 101.5652
--
-- 3) INVARIANTE — nenhuma loja pesa mais do que tem de cabecas:
--
--    SELECT p ->> 'store'
--    FROM jsonb_array_elements(
--             obter_caderno_fechamento(7, 2026) -> 'productivity') p
--    WHERE (p ->> 'weightedHeadcount')::numeric > (p ->> 'activeConsultants')::numeric;
--    -- Esperado: 0 linhas. Idem para qualquer competencia.
--
-- 4) INVARIANTE — a soma das lojas fecha com o summary:
--
--    SELECT (obter_caderno_fechamento(7, 2026) -> 'summary' ->> 'weightedHeadcount')::numeric
--         - (SELECT sum((p ->> 'weightedHeadcount')::numeric)
--            FROM jsonb_array_elements(
--                     obter_caderno_fechamento(7, 2026) -> 'productivity') p) AS diff;
--    -- Esperado: 0. Vale porque `lojas` (producao+metas) e
--    -- `headcount_ponderado` (ledger) cobrem o mesmo conjunto quando
--    -- toda loja com vinculo tem producao ou meta. Se der <> 0, existe
--    -- loja com gente e sem nenhuma das duas — investigar, nao ajustar.
--
-- 5) O caso ERICA atravessa a 091 ate o Caderno sem se perder:
--
--    SELECT p ->> 'activeConsultants', p ->> 'weightedHeadcount'
--    FROM jsonb_array_elements(
--             obter_caderno_fechamento(6, 2026) -> 'productivity') p
--    WHERE p ->> 'store' = 'HELP ALCANTARA CARREFOUR';
--    -- Esperado: 3 e 2.3810 (volta de licenca em 19/06, data declarada,
--    -- fracao pura 8/21 sem piso).
--
-- 6) A identidade do diagnostico fecha DENTRO do bloco (e nao contra
--    activeConsultants, que agora vem de outra foto):
--
--    WITH d AS (SELECT obter_caderno_fechamento(7, 2026)
--                      -> 'summary' -> 'headcountDiagnostics' AS j)
--    SELECT (j ->> 'activeRegistered')::int
--         - (j ->> 'countedInRegistry')::int
--         - (j ->> 'supervisorsExcluded')::int
--         - (j ->> 'withoutActiveStore')::int
--         - (j ->> 'backofficeExcluded')::int AS deve_ser_zero
--    FROM d;
--    -- Esperado: 0.
--
-- 7) Producao NAO se mexeu — a migration so toca denominador:
--
--    SELECT obter_caderno_fechamento(7, 2026) -> 'summary' ->> 'paidEffective';
--    -- Esperado: identico ao snapshot publicado de 07/2026.
--
--
-- ===========================================
-- Rematerializacao — SO no deploy coordenado
-- ===========================================
-- NAO rodar antes de o bereshit estar lendo `weightedHeadcount`. Entre
-- os dois passos o relatorio publicado fica inconsistente consigo mesmo.
--
-- As 14 competencias de uma vez (a 088 mandava 6, pelo eixo de producao;
-- o eixo de HEADCOUNT muda TODAS — correcao registrada no progress de
-- 2026-08-20):
--
--    SELECT s.mes, s.ano, fn_materializar_caderno(s.mes, s.ano)
--    FROM caderno_fechamento_snapshot s
--    ORDER BY s.ano, s.mes;
--
--    -- Conferencia: publicado == ao vivo em todas.
--    SELECT s.mes, s.ano,
--           obter_caderno_publicado(s.mes, s.ano)
--         = obter_caderno_fechamento(s.mes, s.ano) AS igual
--    FROM caderno_fechamento_snapshot s
--    ORDER BY s.ano, s.mes;
--    -- Esperado: igual = true em todas as 14.
-- =====================================================
