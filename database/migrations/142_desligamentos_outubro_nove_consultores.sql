-- =====================================================
-- Migracao 142: desligamentos declarados de 10/2026 — nove consultores
-- Data: 2026-10-20
-- Depende de: 086/087 (consultor_vigencia), 105 (guarda de origem),
--             114 (versao vigente da fn_movimentacoes_rh_import),
--             126 (mesma forma: evento declarado, origem MANUAL)
--
-- Fato confirmado pela operacao (2026-10-20). A data e o ULTIMO DIA de
-- vinculo, inclusive (regra confirmada em 2026-09-11):
--
--   MATHEUS DUTRA DOS SANTOS DE OLIVEIRA          CAXIAS GUANABARA     01/10
--   INGRID DA SILVA RIBEIRO                       SANTA CRUZ PREZUNIC  02/10
--   LUIZ FELIPE FERNANDES SILVA                   CASCADURA            06/10
--   BRUNO VINICIUS MARTINS DA SILVA               PRACA SECA           06/10
--   PEDRO GABRIEL TEIXEIRA GOMES                  PAVUNA               09/10
--   PRISCILA MARCIANA TRANCOSO CORREA DOS SANTOS  CAXIAS CENTRO        13/10
--   DAYENE DA SILVA DOS SANTOS                    PADRE MIGUEL         14/10
--   AGNALDO JOSE DE MORAIS JUNIOR                 TAQUARA              14/10
--   LUIZA DA SILVA CEDRO                          MADUREIRA            20/10
--
--
-- POR QUE MIGRATION E NAO O ARQUIVO DE RH
-- ---------------------------------------
-- 1. O arquivo foi RECUSADO inteiro (tudo-ou-nada, 114): MATHEUS, BRUNO e
--    PRISCILA tem janela aberta com origem MANUAL — correcoes de 02/09 e
--    09/09 — e a guarda CORRECAO_MANUAL_EXISTENTE impede a carga de
--    sobrescreve-las. A guarda esta certa; quem fecha MANUAL e ato
--    explicito.
--
-- 2. Para os outros seis, a RPC grava o fim ERRADO. `data_efetiva` na 114
--    e a propria data do arquivo (ou ultima_producao + 1, se maior). Como
--    `vigencia_fim` e EXCLUSIVO (091: d.dia < v.vigencia_fim), o ultimo
--    dia trabalhado sairia do denominador. A regra confirmada pede o DIA
--    SEGUINTE. docs/headcount.md do angry-man proibe compensar enviando
--    data artificial a RPC antiga — entao a correcao vem por aqui, com a
--    data real, ate o contrato da RPC ser atualizado (FOLLOW-UP).
--
--
-- O QUE ESTA MIGRATION ESCREVE — OS MESMOS EFEITOS DA 114
-- -------------------------------------------------------
--   * consultor_vigencia: fecha TODAS as janelas abertas da pessoa em
--     (desligamento + 1), origem 'MANUAL' — a data foi declarada pela
--     operacao, e MANUAL a protege do rebuild do backfill (087).
--   * consultores: status 'Desligado (a)' em TODAS as linhas da pessoa,
--     inclusive a da loja anterior das transferidas (INGRID, DAYENE,
--     LUIZA). Mesmo UPDATE da 114.
--   * consultor_afastamento e supervisores: nenhum dos nove tem
--     afastamento aberto nem supervisao (medido 2026-10-20). As guardas
--     abortam se isso mudar, em vez de escrever nesses ledgers.
--
-- Medido em 2026-10-20: nenhum dos nove tem contrato a partir do dia
-- seguinte ao desligamento. A guarda 4 aborta se aparecer algum — ai a
-- data declarada contradiz a producao e a operacao precisa decidir.
--
--
-- EFEITO NUMERICO — LER ANTES DE APLICAR
-- --------------------------------------
-- So 10/2026: todas as janelas fecham entre 02/10 e 21/10. Os nove deixam
-- de pesar nos dias uteis de outubro posteriores ao desligamento, e
-- `origem = 'MANUAL'` conta como reducao DECLARADA na 091 (fracao pura,
-- sem o piso de 50%). 09/2026 NAO e tocada por esta migration: o fim
-- mais cedo e 02/10.
--
-- ATENCAO: a carga de HC de 2026-10-20 (feita antes desta migration)
-- abriu janelas de JESSICA BARBOSA DE OLIVEIRA e BEATRIZ DA SILVA NEVES
-- desde 28/09 e de LUIZ FELIPE desde 22/09 — isso ja mudou 09/2026.
--
-- Executar no Supabase SQL Editor.
-- =====================================================

BEGIN;

LOCK TABLE public.consultor_vigencia IN SHARE ROW EXCLUSIVE MODE;

CREATE TEMP TABLE m142_desl (
    nn       TEXT PRIMARY KEY,
    loja     TEXT NOT NULL,
    deslig   DATE NOT NULL,
    fim      DATE GENERATED ALWAYS AS (deslig + 1) STORED
) ON COMMIT DROP;

INSERT INTO m142_desl (nn, loja, deslig) VALUES
    ('MATHEUS DUTRA DOS SANTOS DE OLIVEIRA',         'HELP CAXIAS GUANABARA',    DATE '2026-10-01'),
    ('INGRID DA SILVA RIBEIRO',                      'HELP SANTA CRUZ PREZUNIC', DATE '2026-10-02'),
    ('LUIZ FELIPE FERNANDES SILVA',                  'HELP CASCADURA',           DATE '2026-10-06'),
    ('BRUNO VINICIUS MARTINS DA SILVA',              'HELP PRACA SECA',          DATE '2026-10-06'),
    ('PEDRO GABRIEL TEIXEIRA GOMES',                 'HELP PAVUNA',              DATE '2026-10-09'),
    ('PRISCILA MARCIANA TRANCOSO CORREA DOS SANTOS', 'HELP CAXIAS CENTRO',       DATE '2026-10-13'),
    ('DAYENE DA SILVA DOS SANTOS',                   'HELP PADRE MIGUEL',        DATE '2026-10-14'),
    ('AGNALDO JOSE DE MORAIS JUNIOR',                'HELP TAQUARA',             DATE '2026-10-14'),
    ('LUIZA DA SILVA CEDRO',                         'HELP MADUREIRA',           DATE '2026-10-20');

DO $$
DECLARE
    v_qtd   INTEGER;
    v_nomes TEXT;
BEGIN
    -- ---- 1. Cada pessoa tem EXATAMENTE UMA janela aberta, na loja declarada ----
    -- Quem ja foi fechado (reexecucao) ou tem duas abertas para aqui: o
    -- primeiro caso e no-op tratado abaixo, o segundo precisa de decisao.
    SELECT string_agg(d.nn, ', ' ORDER BY d.nn)
      INTO v_nomes
      FROM m142_desl d
     WHERE (SELECT count(*) FROM public.consultor_vigencia v
             WHERE v.nome_normalizado = d.nn AND v.vigencia_fim IS NULL) > 1
        OR EXISTS (SELECT 1 FROM public.consultor_vigencia v
                     JOIN public.lojas l ON l.id = v.loja_id
                    WHERE v.nome_normalizado = d.nn AND v.vigencia_fim IS NULL
                      AND upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g')) <> d.loja);

    IF v_nomes IS NOT NULL THEN
        RAISE EXCEPTION
            'Migration 142: janela aberta em loja diferente da declarada, ou mais de uma aberta: %',
            v_nomes;
    END IF;

    -- ---- 2. A janela comeca antes do fim (senao o fechamento a inverteria) ----
    SELECT string_agg(d.nn, ', ' ORDER BY d.nn)
      INTO v_nomes
      FROM m142_desl d
      JOIN public.consultor_vigencia v
        ON v.nome_normalizado = d.nn AND v.vigencia_fim IS NULL
     WHERE v.vigencia_inicio >= d.fim;

    IF v_nomes IS NOT NULL THEN
        RAISE EXCEPTION
            'Migration 142: janela aberta comeca depois do desligamento: %', v_nomes;
    END IF;

    -- ---- 3. Nenhum afastamento aberto nem supervisao ----
    -- A 114 fecharia esses ledgers tambem. Hoje nao ha o que fechar; se
    -- passar a haver, o caso precisa ser olhado, nao fechado as cegas.
    SELECT string_agg(d.nn, ', ' ORDER BY d.nn)
      INTO v_nomes
      FROM m142_desl d
     WHERE EXISTS (SELECT 1 FROM public.consultor_afastamento a
                    WHERE a.nome_normalizado = d.nn AND a.data_fim IS NULL)
        OR EXISTS (SELECT 1 FROM public.supervisor_vigencia s
                    WHERE s.nome_normalizado = d.nn AND s.vigencia_fim IS NULL)
        OR EXISTS (SELECT 1 FROM public.supervisores s
                    WHERE upper(regexp_replace(btrim(s.nome), '[[:space:]]+', ' ', 'g')) = d.nn);

    IF v_nomes IS NOT NULL THEN
        RAISE EXCEPTION
            'Migration 142: afastamento aberto ou supervisao para: % — decidir antes', v_nomes;
    END IF;

    -- ---- 4. A data declarada nao desmente a producao ----
    -- Filtro de data em contratos: a janela de outubro em diante.
    SELECT string_agg(DISTINCT d.nn, ', ')
      INTO v_nomes
      FROM m142_desl d
      JOIN public.consultores cs
        ON upper(regexp_replace(btrim(cs.nome), '[[:space:]]+', ' ', 'g')) = d.nn
      JOIN public.contratos ct ON ct.consultor_id = cs.id
     WHERE ct.data_cadastro >= DATE '2026-10-01'
       AND ct.data_cadastro >= d.fim;

    IF v_nomes IS NOT NULL THEN
        RAISE EXCEPTION
            'Migration 142: contrato no dia seguinte ao desligamento ou depois: % — a data contradiz a producao',
            v_nomes;
    END IF;

    -- ---- 5. Fecha as janelas ----
    UPDATE public.consultor_vigencia v
       SET vigencia_fim = d.fim,
           origem       = 'MANUAL'
      FROM m142_desl d
     WHERE v.nome_normalizado = d.nn
       AND v.vigencia_fim IS NULL;
    GET DIAGNOSTICS v_qtd = ROW_COUNT;

    -- 9 na primeira aplicacao; 0 numa reexecucao (todas ja fechadas).
    IF v_qtd NOT IN (0, 9) THEN
        RAISE EXCEPTION
            'Migration 142: % janela(s) fechada(s) — esperado 9 (ou 0 em reexecucao)', v_qtd;
    END IF;

    -- ---- 6. Foto: todas as linhas da pessoa, como a 114 ----
    UPDATE public.consultores c
       SET status = 'Desligado (a)'
      FROM m142_desl d
     WHERE upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g')) = d.nn
       AND c.status IS DISTINCT FROM 'Desligado (a)';

    -- ---- 7. Pos-condicoes ----
    -- Nenhuma janela aberta para os nove.
    SELECT count(*)::integer INTO v_qtd
      FROM public.consultor_vigencia v
      JOIN m142_desl d ON d.nn = v.nome_normalizado
     WHERE v.vigencia_fim IS NULL;

    IF v_qtd <> 0 THEN
        RAISE EXCEPTION 'Migration 142: pos-condicao falhou — % janela(s) ainda aberta(s)', v_qtd;
    END IF;

    -- Cada um tem exatamente uma janela terminando no dia seguinte, na loja declarada.
    SELECT string_agg(d.nn, ', ' ORDER BY d.nn)
      INTO v_nomes
      FROM m142_desl d
     WHERE (SELECT count(*)
              FROM public.consultor_vigencia v
              JOIN public.lojas l ON l.id = v.loja_id
             WHERE v.nome_normalizado = d.nn
               AND v.vigencia_fim = d.fim
               AND v.origem = 'MANUAL'
               AND upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g')) = d.loja) <> 1;

    IF v_nomes IS NOT NULL THEN
        RAISE EXCEPTION
            'Migration 142: pos-condicao falhou — janela final ausente ou fora da regra: %', v_nomes;
    END IF;

    -- Foto coerente: nenhuma linha ativa restante.
    SELECT count(*)::integer INTO v_qtd
      FROM public.consultores c
      JOIN m142_desl d
        ON upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g')) = d.nn
     WHERE c.status IS DISTINCT FROM 'Desligado (a)';

    IF v_qtd <> 0 THEN
        RAISE EXCEPTION 'Migration 142: pos-condicao falhou — % cadastro(s) ainda nao desligado(s)', v_qtd;
    END IF;
END
$$;

COMMIT;


-- =====================================================
-- Verificacao operacional depois da aplicacao
-- =====================================================
--
-- 1) As nove janelas:
--
--    SELECT v.nome_normalizado, l.nome, v.vigencia_inicio, v.vigencia_fim, v.origem
--      FROM consultor_vigencia v
--      JOIN lojas l ON l.id = v.loja_id
--     WHERE v.nome_normalizado IN (
--         'MATHEUS DUTRA DOS SANTOS DE OLIVEIRA', 'INGRID DA SILVA RIBEIRO',
--         'LUIZ FELIPE FERNANDES SILVA', 'BRUNO VINICIUS MARTINS DA SILVA',
--         'PEDRO GABRIEL TEIXEIRA GOMES',
--         'PRISCILA MARCIANA TRANCOSO CORREA DOS SANTOS',
--         'DAYENE DA SILVA DOS SANTOS', 'AGNALDO JOSE DE MORAIS JUNIOR',
--         'LUIZA DA SILVA CEDRO')
--     ORDER BY 1, 3;
--
--    -- esperado: fim = desligamento + 1 (02/10, 03/10, 07/10, 07/10,
--    -- 10/10, 14/10, 15/10, 15/10, 21/10), origem MANUAL. As janelas
--    -- antigas de INGRID, DAYENE e LUIZA ficam como estavam.
--
-- 2) O detector nao acusa nenhum deles:
--
--    SELECT fn_diag_vinculo_divergente();
--
-- 3) Rematerializar o Caderno:
--
--    SELECT fn_materializar_caderno(9, 2026);   -- carga de HC de 20/10
--    SELECT fn_materializar_caderno(10, 2026);  -- esta migration
--
--
-- =====================================================
-- FOLLOW-UP
-- =====================================================
--
-- [ ] `fn_movimentacoes_rh_import` (114) grava `data_efetiva` = data do
--     arquivo. Pela regra de 2026-09-11 deveria ser data + 1. Enquanto o
--     contrato nao mudar (junto com os consumidores no angry-man), todo
--     desligamento pelo arquivo perde o ultimo dia trabalhado — e esta e a
--     SEGUNDA vez que a correcao sai por migration (a primeira foi a
--     lista de 13 marcada MANUAL em setembro).
