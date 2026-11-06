-- Migration 148: loja de origem pela data de digitacao, antes da transferencia.
-- Data: 04/11/2026. Depende de 105, 129, 144 e das transferencias em 01/10.
-- Decisao da operacao: digitacao anterior a 01/10 pertence a loja anterior.
-- Alessandra: seis contratos de setembro -> HELP SANTA CRUZ DA SERRA.
-- Vitoria: um contrato de setembro -> HELP MAGE.
-- Corrige loja_id E consultor_id (cadastro da mesma pessoa na loja anterior).
-- Pagamento e competencia permanecem em outubro. Valores e demais dados
-- dos contratos sao comparados antes/depois. Nao altera vinculos.
--
-- Aplicar TODO o arquivo no SQL Editor, depois da 147. Nao publica nem
-- rematerializa automaticamente. Aceita reexecucao sem duplicar/retocar.
-- Em 04/11, apos a carga do HC (Dalila/Leticia): 10 eventos; a 147 resolve
-- os 3 da Heloina e a 148 resolve os outros 7.
-- Movimentacao em outubro: Mage -21.787,04 +4.910,06; Santa Cruz da Serra
-- +21.787,04; Caxias Guanabara -4.910,06. Total da rede preservado.
-- IMPORTANTE: corrigir tambem a atribuicao na origem/extrator. Reimportacao
-- que mantenha a loja nova nesses contratos pode desfazer esta correcao.

BEGIN;
LOCK TABLE public.contratos IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.lojas, public.consultores, public.consultor_vigencia,
           public.periodos IN SHARE MODE;

CREATE TEMP TABLE m148_origem (
    contrato bigint PRIMARY KEY,
    ade text NOT NULL,
    digitacao date NOT NULL,
    pessoa text NOT NULL,
    loja_errada text NOT NULL,
    loja_origem text NOT NULL
) ON COMMIT DROP;
INSERT INTO m148_origem VALUES
    (3005011, '979002321', DATE '2026-09-16', 'ALESSANDRA BRANDAO LUIZ', 'HELP MAGE', 'HELP SANTA CRUZ DA SERRA'),
    (3005005, '979002067', DATE '2026-09-16', 'ALESSANDRA BRANDAO LUIZ', 'HELP MAGE', 'HELP SANTA CRUZ DA SERRA'),
    (3008434, '103947105', DATE '2026-09-25', 'ALESSANDRA BRANDAO LUIZ', 'HELP MAGE', 'HELP SANTA CRUZ DA SERRA'),
    (3008435, '103947104', DATE '2026-09-25', 'ALESSANDRA BRANDAO LUIZ', 'HELP MAGE', 'HELP SANTA CRUZ DA SERRA'),
    (3009606, '103967346', DATE '2026-09-29', 'ALESSANDRA BRANDAO LUIZ', 'HELP MAGE', 'HELP SANTA CRUZ DA SERRA'),
    (3009607, '103967347', DATE '2026-09-29', 'ALESSANDRA BRANDAO LUIZ', 'HELP MAGE', 'HELP SANTA CRUZ DA SERRA'),
    (3007254, '979098895', DATE '2026-09-22', 'VITORIA SOUZA DE OLIVEIRA', 'HELP CAXIAS GUANABARA', 'HELP MAGE');

DO $migration$
DECLARE
    r record;
    n integer;
    old_store uuid;
    target_store uuid;
    old_consultant uuid;
    target_consultant uuid;
    target_contract uuid;
    target_period_id uuid;
    before_data jsonb;
    after_data jsonb;
    before_value numeric;
    after_value numeric;
BEGIN
    SELECT count(*), (array_agg(p.id))[1] INTO n, target_period_id
    FROM public.periodos p WHERE p.ano = 2026 AND p.mes = 10;
    IF n <> 1 THEN
        RAISE EXCEPTION '148: competencia 10/2026 ausente ou ambigua';
    END IF;

    FOR r IN SELECT * FROM m148_origem ORDER BY contrato LOOP
        SELECT count(*), (array_agg(l.id))[1] INTO n, old_store
        FROM public.lojas l WHERE l.nome = r.loja_errada;
        IF n <> 1 THEN
            RAISE EXCEPTION '148: loja atual ausente/ambigua: %', r.loja_errada;
        END IF;
        SELECT count(*), (array_agg(l.id))[1] INTO n, target_store
        FROM public.lojas l WHERE l.nome = r.loja_origem;
        IF n <> 1 THEN
            RAISE EXCEPTION '148: loja de origem ausente/ambigua: %', r.loja_origem;
        END IF;
        SELECT count(*), (array_agg(c.id))[1] INTO n, old_consultant
        FROM public.consultores c
        WHERE public.fn_normalizar_nome(c.nome) = r.pessoa AND c.loja_id = old_store;
        IF n <> 1 THEN
            RAISE EXCEPTION '148: cadastro atual ausente/ambiguo: %', r.pessoa;
        END IF;
        SELECT count(*), (array_agg(c.id))[1] INTO n, target_consultant
        FROM public.consultores c
        WHERE public.fn_normalizar_nome(c.nome) = r.pessoa AND c.loja_id = target_store;
        IF n <> 1 THEN
            RAISE EXCEPTION '148: cadastro de origem ausente/ambiguo: %', r.pessoa;
        END IF;

        -- A loja anterior precisa cobrir a data EXATA da digitacao.
        SELECT count(*) INTO n FROM public.consultor_vigencia v
        WHERE v.nome_normalizado = r.pessoa AND v.loja_id = target_store
          AND r.digitacao >= v.vigencia_inicio
          AND (v.vigencia_fim IS NULL OR r.digitacao < v.vigencia_fim);
        IF n <> 1 THEN
            RAISE EXCEPTION '148: vinculo de origem ausente/ambiguo no contrato %', r.contrato;
        END IF;
        -- E a transferencia declarada continua em 01/10.
        IF NOT EXISTS (
            SELECT 1 FROM public.consultor_vigencia v
            WHERE v.nome_normalizado = r.pessoa AND v.loja_id = old_store
              AND v.vigencia_inicio = DATE '2026-10-01'
        ) THEN
            RAISE EXCEPTION '148: transferencia de % em 01/10 nao encontrada', r.pessoa;
        END IF;

        SELECT count(*), (array_agg(c.id))[1] INTO n, target_contract
        FROM public.contratos c
        WHERE c.contrato_id = r.contrato AND c.num_proposta = r.ade
          AND c.data_cadastro = r.digitacao AND c.periodo_id = target_period_id
          AND ((c.loja_id = old_store AND c.consultor_id = old_consultant)
            OR (c.loja_id = target_store AND c.consultor_id = target_consultant));
        IF n <> 1 THEN
            RAISE EXCEPTION '148: contrato % / ADE % diverge do estado conferido', r.contrato, r.ade;
        END IF;
        SELECT to_jsonb(c) - 'loja_id' - 'consultor_id' - 'updated_at'
        INTO before_data FROM public.contratos c WHERE c.id = target_contract;
        SELECT count(*), sum(v.valor_consolidado) INTO n, before_value
        FROM public.v_contratos_dashboard v WHERE v.id = target_contract;
        IF n <> 1 OR before_value IS NULL THEN
            RAISE EXCEPTION '148: contrato % ausente/ambiguo na view de pagamentos', r.contrato;
        END IF;

        UPDATE public.contratos c
        SET loja_id = target_store, consultor_id = target_consultant
        WHERE c.id = target_contract AND c.loja_id = old_store
          AND c.consultor_id = old_consultant;

        SELECT to_jsonb(c) - 'loja_id' - 'consultor_id' - 'updated_at'
        INTO after_data FROM public.contratos c
        WHERE c.id = target_contract AND c.loja_id = target_store
          AND c.consultor_id = target_consultant;
        IF after_data IS DISTINCT FROM before_data THEN
            RAISE EXCEPTION '148: dados adicionais do contrato % mudaram; rollback', r.contrato;
        END IF;
        SELECT count(*), sum(v.valor_consolidado) INTO n, after_value
        FROM public.v_contratos_dashboard v
        WHERE v.id = target_contract AND v.loja = r.loja_origem
          AND public.fn_normalizar_nome(v.consultor) = r.pessoa;
        IF n <> 1 OR after_value IS DISTINCT FROM before_value THEN
            RAISE EXCEPTION '148: view/valor divergiu apos corrigir contrato %; rollback', r.contrato;
        END IF;
    END LOOP;
    RAISE NOTICE '148: sete contratos conferidos na loja de origem pela digitacao.';
END
$migration$;
COMMIT;

-- Verificacao somente leitura. Esperado: zero se a 147 tambem foi aplicada
-- e nenhum outro dado mudou desde a apuracao dos 35 eventos.
SELECT public.fn_contar_pagamentos_sem_vinculo_origem(10, 2026)
       AS eventos_origem_ainda_pendentes_outubro;
-- Se zero, rematerializar pelo angry-man; ainda serao validadas a ausencia
-- de sobreposicoes e a conciliacao. A guarda de origem e apenas uma etapa.
