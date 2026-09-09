-- =====================================================
-- Migracao 116: diagnostico foto x ledger
-- Data: 2026-09-09
-- Depende de: 086/087 (consultor_vigencia), 076 (supervisor_vigencia),
--             092 (a CTE de dedup que esta funcao reproduz)
--
-- POR QUE DIAGNOSTICO E NAO BLOQUEIO
-- -----------------------------------
-- Em 2026-09-08 mediu-se a divergencia entre `consultores` (a foto) e a
-- janela aberta de `consultor_vigencia` (o ledger) sobre 123 ativos
-- nao-supervisores. Deu 5 divergencias, e a operacao julgou uma a uma:
--
--   JOYCE     foto certa (transferiu 01/09)          -> migration 109
--   HUGO      foto certa (promovido 01/09)           -> migration 110
--   MIZAEL    LEDGER certo (volta so em 04/09)       -> migration 111
--   CAROLINA  foto certa (trocou 03/09)              -> migration 112
--   THAIS     foto certa (trocou 03/09)              -> migration 112
--
-- A foto acertou 4 e errou 1, e NADA nos dados separa os casos: JOYCE
-- (erro de digitacao de filial) e HUGO (promocao legitima) tinham forma
-- identica — parou de vender em A, comecou em B no 1o dia util do mes.
-- Foi a operacao que decidiu, nao um sinal.
--
-- Logo, uma funcao que ESCOLHESSE um lado erraria ~20% das vezes, e
-- erraria escrevendo. Esta funcao so faz o numero aparecer, no espirito
-- da 095 (`desligados_com_janela_aberta`) e da 105
-- (`fn_contar_pagamentos_sem_vinculo_origem`): agir continua sendo ato
-- explicito.
--
--
-- O QUE ELA OLHA — cinco formas de falha, todas ja observadas
-- -----------------------------------------------------------
--   1. `divergencias`      — foto e ledger discordam da loja. E o caso
--                            das cinco pessoas acima.
--   2. `sem_janela_aberta` — ativo na foto sem nenhuma janela aberta.
--                            A 091 nao o conta no denominador: a pessoa
--                            some da media sem ter saido.
--   3. `multiplas_janelas` — mais de uma janela aberta. Permitido pelo
--                            indice (`uq_cv_consultor_loja_aberta` e por
--                            pessoa+LOJA), e legitimo em cobertura
--                            temporaria, mas em R3 reparte o peso da
--                            pessoa entre lojas: vale conferir se e
--                            intencional.
--   4. `cadastros_orfaos`  — linha de `consultores` que NAO vence o
--                            dedup e nao tem contrato nenhum. E o
--                            residuo da JOYCE em HELP ALCANTARA: inerte
--                            enquanto o `updated_at` do cadastro certo
--                            for maior, e pronto para receber producao
--                            no dia em que o ETL reconhecer o par
--                            (nome, loja) que ja existe.
--   5. `papel_sem_vinculo` — supervisao aberta numa loja e janela de
--                            consultor aberta em OUTRA. E a forma do
--                            caso HUGO: o ETL de contratos acertou a
--                            loja e ninguem registrou o papel.
--
-- Nenhuma das cinco e necessariamente um erro. Sao perguntas.
--
--
-- IDENTIDADE E DEDUP
-- ------------------
-- A CTE `foto` reproduz LITERALMENTE `consultores_mais_recentes` da 092
-- (`DISTINCT ON (nome_normalizado) ... ORDER BY updated_at DESC NULLS
-- LAST, id DESC`), que e o mesmo criterio de `_colapsar_cadastro_recente`
-- no dashboard. Um diagnostico que deduplicasse por outro criterio
-- acusaria divergencias que a tela nao mostra, e perderia as que mostra.
--
-- Nome de consultor nao e dado sensivel — `tipo` e `observacao` de
-- afastamento sao (089), e esta funcao nao toca em
-- `consultor_afastamento`.
--
-- Funcao de LEITURA: STABLE, sem escrita. Executar quando quiser, antes
-- e depois de qualquer carga.
--
-- Executar no Supabase SQL Editor, depois da 115.
-- =====================================================

CREATE OR REPLACE FUNCTION public.fn_diag_vinculo_divergente()
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $fn$
WITH
foto AS (
    -- Copia fiel de `consultores_mais_recentes` (092). Ver cabecalho.
    SELECT DISTINCT ON (n.nome_normalizado)
        c.id,
        c.nome,
        c.loja_id,
        c.status,
        c.updated_at,
        n.nome_normalizado AS nn
    FROM public.consultores c
    CROSS JOIN LATERAL (
        SELECT upper(regexp_replace(
                   btrim(coalesce(c.nome, '')), '[[:space:]]+', ' ', 'g')
               ) AS nome_normalizado
    ) n
    WHERE n.nome_normalizado <> ''
    ORDER BY n.nome_normalizado, c.updated_at DESC NULLS LAST, c.id DESC
),
ativos AS (
    -- Mesmo predicado da 092: status vazio conta como ativo.
    SELECT * FROM foto
    WHERE btrim(coalesce(status, '')) = ''
       OR upper(btrim(status)) LIKE 'ATIVO%'
),
janelas AS (
    SELECT
        v.nome_normalizado AS nn,
        count(*)::integer  AS n_abertas,
        (array_agg(v.loja_id
                   ORDER BY v.vigencia_inicio DESC, v.id DESC))[1] AS loja_ledger,
        (array_agg(v.vigencia_inicio
                   ORDER BY v.vigencia_inicio DESC, v.id DESC))[1] AS desde,
        (array_agg(v.origem
                   ORDER BY v.vigencia_inicio DESC, v.id DESC))[1] AS origem
    FROM public.consultor_vigencia v
    WHERE v.vigencia_fim IS NULL
    GROUP BY 1
),
producao AS (
    -- Ultimo contrato da pessoa e a loja dele. E o unico fato objetivo
    -- disponivel para quem for julgar a divergencia: producao prova
    -- presenca. `data_cadastro`, nunca `data_status_pagamento` —
    -- pagamento arrasta depois da transferencia (105).
    SELECT DISTINCT ON (t.nn) t.nn, t.loja_id AS loja_ultimo, t.data_cadastro AS ultimo
    FROM (
        SELECT upper(regexp_replace(
                   btrim(cs.nome), '[[:space:]]+', ' ', 'g')) AS nn,
               ct.loja_id,
               ct.data_cadastro::date AS data_cadastro
        FROM public.contratos ct
        JOIN public.consultores cs ON cs.id = ct.consultor_id
        WHERE ct.data_cadastro IS NOT NULL
    ) t
    ORDER BY t.nn, t.data_cadastro DESC
),
supervisao AS (
    SELECT
        v.nome_normalizado AS nn,
        (array_agg(v.loja_id
                   ORDER BY v.vigencia_inicio DESC, v.id DESC))[1] AS loja_sup,
        (array_agg(v.vigencia_inicio
                   ORDER BY v.vigencia_inicio DESC, v.id DESC))[1] AS sup_desde
    FROM public.supervisor_vigencia v
    WHERE v.vigencia_fim IS NULL
    GROUP BY 1
)
SELECT jsonb_build_object(
    'gerado_em', now(),
    'ativos_avaliados', (SELECT count(*) FROM ativos),

    -- 1. Foto e ledger discordam da loja.
    'divergencias', (
        SELECT coalesce(jsonb_agg(jsonb_build_object(
                   'nome',            a.nome,
                   'loja_foto',       lf.nome,
                   'loja_ledger',     ll.nome,
                   'ledger_desde',    j.desde,
                   'ledger_origem',   j.origem,
                   'ultimo_contrato', p.ultimo,
                   'loja_ultimo_contrato', lu.nome,
                   'cadastro_atualizado_em', a.updated_at)
               ORDER BY a.nome), '[]'::jsonb)
        FROM ativos a
        JOIN janelas j        ON j.nn = a.nn AND j.n_abertas = 1
        LEFT JOIN producao p  ON p.nn = a.nn
        LEFT JOIN public.lojas lf ON lf.id = a.loja_id
        LEFT JOIN public.lojas ll ON ll.id = j.loja_ledger
        LEFT JOIN public.lojas lu ON lu.id = p.loja_ultimo
        WHERE a.loja_id IS DISTINCT FROM j.loja_ledger
    ),

    -- 2. Ativo na foto, invisivel para o denominador.
    'sem_janela_aberta', (
        SELECT coalesce(jsonb_agg(jsonb_build_object(
                   'nome',            a.nome,
                   'loja_foto',       lf.nome,
                   'status',          a.status,
                   'ultimo_contrato', p.ultimo)
               ORDER BY a.nome), '[]'::jsonb)
        FROM ativos a
        LEFT JOIN janelas j   ON j.nn = a.nn
        LEFT JOIN producao p  ON p.nn = a.nn
        LEFT JOIN public.lojas lf ON lf.id = a.loja_id
        WHERE j.nn IS NULL
    ),

    -- 3. Peso repartido entre lojas — legitimo, mas confira.
    'multiplas_janelas', (
        SELECT coalesce(jsonb_agg(jsonb_build_object(
                   'nome',     f.nome,
                   'abertas',  j.n_abertas,
                   'lojas',    (SELECT coalesce(jsonb_agg(l2.nome ORDER BY l2.nome),
                                                '[]'::jsonb)
                                FROM public.consultor_vigencia v2
                                LEFT JOIN public.lojas l2 ON l2.id = v2.loja_id
                                WHERE v2.nome_normalizado = j.nn
                                  AND v2.vigencia_fim IS NULL))
               ORDER BY f.nome), '[]'::jsonb)
        FROM janelas j
        JOIN foto f ON f.nn = j.nn
        WHERE j.n_abertas > 1
    ),

    -- 4. Residuo de cadastro pronto para receber producao fantasma.
    --    `tem_escopo_usuario` importa: usuario_escopos.consultor_id e
    --    ON DELETE CASCADE, entao remover a linha levaria o escopo junto
    --    (foi a guarda que a 109 precisou ter na etapa 6).
    'cadastros_orfaos', (
        SELECT coalesce(jsonb_agg(jsonb_build_object(
                   'nome',       c.nome,
                   'loja',       l.nome,
                   'status',     c.status,
                   'criado_em',  c.created_at,
                   'tem_escopo_usuario', EXISTS (
                       SELECT 1 FROM public.usuario_escopos ue
                       WHERE ue.consultor_id = c.id))
               ORDER BY c.nome), '[]'::jsonb)
        FROM public.consultores c
        LEFT JOIN public.lojas l ON l.id = c.loja_id
        WHERE NOT EXISTS (SELECT 1 FROM foto f WHERE f.id = c.id)
          AND NOT EXISTS (SELECT 1 FROM public.contratos ct
                          WHERE ct.consultor_id = c.id)
    ),

    -- 5. Supervisiona uma loja, tem vinculo de consultor em outra.
    'papel_sem_vinculo', (
        SELECT coalesce(jsonb_agg(jsonb_build_object(
                   'nome',            f.nome,
                   'loja_supervisao', ls.nome,
                   'supervisao_desde', s.sup_desde,
                   'loja_consultor',  lc.nome,
                   'consultor_desde', j.desde)
               ORDER BY f.nome), '[]'::jsonb)
        FROM supervisao s
        JOIN janelas j ON j.nn = s.nn AND j.n_abertas = 1
        JOIN foto f    ON f.nn = s.nn
        LEFT JOIN public.lojas ls ON ls.id = s.loja_sup
        LEFT JOIN public.lojas lc ON lc.id = j.loja_ledger
        WHERE s.loja_sup IS DISTINCT FROM j.loja_ledger
    )
);
$fn$;

COMMENT ON FUNCTION public.fn_diag_vinculo_divergente() IS
    'Diagnostico read-only entre a foto (`consultores`, deduplicada pelo '
    'mesmo criterio da 092) e os ledgers de vinculo e papel. Devolve cinco '
    'listas: divergencia de loja foto x ledger, ativo sem janela aberta, '
    'multiplas janelas abertas, cadastro orfao sem contrato, e supervisao '
    'aberta em loja diferente do vinculo de consultor. NAO decide nem '
    'escreve: em 2026-09-08 a foto acertou 4 das 5 divergencias e nada nos '
    'dados separava os casos — so a operacao. Agir e ato explicito.';

REVOKE ALL ON FUNCTION public.fn_diag_vinculo_divergente() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.fn_diag_vinculo_divergente() FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_diag_vinculo_divergente() TO service_role;


-- =====================================================
-- Verificacao operacional depois da aplicacao
-- =====================================================
--
-- 1) Rodar e comparar com a linha de base abaixo:
--
--    SELECT public.fn_diag_vinculo_divergente();
--
--    MEDIDO EM 2026-09-09 (por reimplementacao da mesma logica em Python
--    contra o banco real, antes de aplicar esta migration). 437 linhas em
--    `consultores`, 336 pessoas depois do dedup, 175 ativas:
--
--      divergencias        1   LIVIA GOMES DE SANT ANNA
--      sem_janela_aberta   5   BRUNO, GISELLE, MARIA LUISA, MATHEUS, STEPHANIA
--      multiplas_janelas   0
--      cadastros_orfaos    2   LETICIA MAESSE, RENATA BUAS
--      papel_sem_vinculo   0
--
--    As 5 pessoas divergentes medidas em 08/09 sairam da lista: as
--    migrations 109-112 as corrigiram e foram aplicadas. `papel_sem_vinculo`
--    zerou porque a 110 abriu a janela de consultor do HUGO em MADUREIRA
--    junto com a supervisao. E (JOYCE, HELP ALCANTARA) sumiu de
--    `cadastros_orfaos` pela etapa 6 da 109.
--
--    O QUE ENTROU NO LUGAR, em um unico dia, e o argumento desta funcao:
--
--    * LIVIA — cadastro (LIVIA, HELP PENHA) CRIADO EM 2026-09-09 pelo ETL
--      de contratos, exatamente a forma do caso JOYCE. Ledger diz
--      BONSUCESSO desde 12/05 (BACKFILL_PRODUCAO); 09/2026 esta partido em
--      5 contratos BONSUCESSO e 5 PENHA. Nao ha desempate: a regra da
--      "loja dominante do mes" (087) empata, como empatava na CAROLINA
--      (112). So a operacao decide.
--
--    * Os 5 sem janela nao tem janela NENHUMA, nem fechada — cadastros
--      criados em 08 e 09/09, produzindo so em 09/2026. Sao admissoes
--      novas. Como a 091 le so o ledger, cada um esta no NUMERADOR (a
--      producao conta) e fora do DENOMINADOR (peso zero): a media da loja
--      sobe por gente que existe e nao e contada. E o caso que
--      `acao_adm = 'criar_janela'` da 095 resolve — mas o HC_Colaboradores
--      nunca foi importado, entao nada abre a janela deles.
--
--    * MIZAEL nao aparece em `divergencias` e vale a nota: o cadastro dele
--      em HELP RIO COMPRIDO e residuo de 13/08 e o ledger so voltou a RIO
--      COMPRIDO em 04/09 (111). Os dois concordam HOJE por coincidencia,
--      nao porque o cadastro tenha sido corrigido.
--
-- 2) Leitura de cada lista, para quem for julgar:
--
--    * `divergencias` — compare `loja_ultimo_contrato` com as duas. Onde
--      a pessoa esta vendendo AGORA e o melhor indicio, mas nao decide:
--      o caso JOYCE tinha producao na loja errada.
--    * `sem_janela_aberta` — se `ultimo_contrato` for antigo, e provavel
--      desligamento nao informado; se for recente, e admissao que nao
--      chegou ao ledger.
--    * `cadastros_orfaos` com `tem_escopo_usuario = true` NAO pode ser
--      apagado sem antes tratar `usuario_escopos` (ON DELETE CASCADE).
--
-- 3) Custo: a funcao varre `contratos` inteira uma vez (CTE `producao`).
--    Em Nano isso nao e gratuito — rodar sob demanda, nao em loop de UI.
