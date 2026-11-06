-- Migration 147: vinculos declarados para o fechamento de outubro/2026.
-- Declaracoes da operacao em 04/11/2026:
--   Transferencias de Alessandra, Vitoria e Roberta em 01/10/2026.
--   Dalila admitida em 22/09/2026; Leticia em 21/09/2026.
--   Heloina: licenca desde 01/05/2026; ultimo dia de vinculo 03/11/2026.
-- Dependencias: 086, 089, 105, 129 e 144.
-- Executar TODO o arquivo no SQL Editor. Nao rematerializa nem publica.
-- Transacao unica; divergencia inesperada cancela todas as alteracoes.
-- Reexecucao aceita apenas o mesmo estado final, sem duplicar janelas.
--
-- ATENCAO: os contratos de setembro nas lojas novas de Alessandra/Vitoria
-- e o caso de VICTOR FELIPE TRAJANO COSTA continuam sujeitos a apuracao.
-- Nao antecipar transferencias nem mudar contratos para zerar a guarda.
--
-- Heloina: tipo LICENCA_MATERNIDADE vem do cadastro atual de Bonsucesso.
-- Conforme a 089, a primeira digitacao posterior fecha o afastamento.
-- Medido em 04/11: primeiro contrato em 20/10/2026. Esta migration confere
-- esse fato antes de registrar [01/05, 20/10). Nao presume licenca ate
-- novembro. O vinculo inclui 03/11: fim exclusivo em 04/11/2026 (142).
-- O afastamento afeta o HC ponderado; produtividade individual continua
-- usando dias de vinculo, sem descontar afastamentos (regra vigente).

BEGIN;

LOCK TABLE public.consultor_vigencia, public.consultor_afastamento,
           public.consultores IN SHARE ROW EXCLUSIVE MODE;
-- Estabiliza a prova de retorno e impede carga concorrente durante a correcao.
LOCK TABLE public.contratos IN SHARE MODE;

CREATE TEMP TABLE m147_transferencias (
    nome text PRIMARY KEY,
    loja_anterior text NOT NULL,
    loja_atual text NOT NULL,
    inicio_anterior date NOT NULL,
    transferencia date NOT NULL
) ON COMMIT DROP;
INSERT INTO m147_transferencias VALUES
    ('ALESSANDRA BRANDAO LUIZ', 'HELP SANTA CRUZ DA SERRA',
     'HELP MAGE', DATE '2026-07-22', DATE '2026-10-01'),
    ('VITORIA SOUZA DE OLIVEIRA', 'HELP MAGE',
     'HELP CAXIAS GUANABARA', DATE '2026-03-20', DATE '2026-10-01'),
    ('ROBERTA DE MORAES FERREIRA LESSA', 'HELP MEIER',
     'HELP BELFORD ROXO', DATE '2026-07-17', DATE '2026-10-01');

CREATE TEMP TABLE m147_admissoes (
    nome text PRIMARY KEY,
    loja text NOT NULL,
    admissao date NOT NULL
) ON COMMIT DROP;
INSERT INTO m147_admissoes VALUES
    ('DALILA ZAIRA DE OLIVEIRA DA SILVA FERNANDES',
     'HELP CAMPO GRANDE NOVA', DATE '2026-09-22'),
    ('LETICIA PEREIRA FAGUNDES LAUDELINO',
     'HELP CAMPO GRANDE CALCADAO', DATE '2026-09-21');

DO $migration$
DECLARE
    r record;
    old_store uuid;
    new_store uuid;
    target_id uuid;
    row_count integer;
    return_date date;
    heloina constant text := 'HELOINA DE AQUINO';
BEGIN
    -- Nao converter pessoa com outro papel sem decisao explicita.
    IF EXISTS (
        SELECT 1 FROM public.supervisor_vigencia s
        WHERE s.nome_normalizado IN (
            SELECT nome FROM m147_transferencias
            UNION ALL SELECT nome FROM m147_admissoes
            UNION ALL SELECT heloina
        ) AND (s.vigencia_fim IS NULL OR s.vigencia_fim > DATE '2026-09-01')
    ) THEN
        RAISE EXCEPTION '147: supervisao inesperada para uma das seis pessoas';
    END IF;

    FOR r IN SELECT * FROM m147_transferencias ORDER BY nome LOOP
        SELECT count(*), (array_agg(l.id))[1] INTO row_count, old_store
        FROM public.lojas l WHERE l.nome = r.loja_anterior;
        IF row_count <> 1 THEN
            RAISE EXCEPTION '147: loja anterior ausente/ambigua: %', r.loja_anterior;
        END IF;
        SELECT count(*), (array_agg(l.id))[1] INTO row_count, new_store
        FROM public.lojas l WHERE l.nome = r.loja_atual;
        IF row_count <> 1 THEN
            RAISE EXCEPTION '147: loja atual ausente/ambigua: %', r.loja_atual;
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM public.consultores c
            WHERE public.fn_normalizar_nome(c.nome) = r.nome
              AND c.loja_id = new_store
        ) THEN
            RAISE EXCEPTION '147: cadastro da pessoa ausente na loja atual: %', r.nome;
        END IF;

        -- Aceita o estado anterior OU a transferencia ja registrada.
        SELECT count(*), (array_agg(v.id))[1] INTO row_count, target_id
        FROM public.consultor_vigencia v
        WHERE v.nome_normalizado = r.nome AND v.loja_id = old_store
          AND v.vigencia_inicio = r.inicio_anterior
          AND (v.vigencia_fim IS NULL OR v.vigencia_fim = r.transferencia);
        IF row_count <> 1 THEN
            RAISE EXCEPTION '147: janela anterior inesperada: %', r.nome;
        END IF;
        IF EXISTS (
            SELECT 1 FROM public.consultor_vigencia v
            WHERE v.nome_normalizado = r.nome AND v.id <> target_id
              AND (v.loja_id = new_store
                       AND v.vigencia_inicio = r.transferencia
                       AND v.vigencia_fim IS NULL AND v.origem = 'MANUAL') IS NOT TRUE
        ) THEN
            RAISE EXCEPTION '147: janela adicional nao prevista: %', r.nome;
        END IF;
        UPDATE public.consultor_vigencia
        SET vigencia_fim = r.transferencia, origem = 'MANUAL'
        WHERE id = target_id
          AND (vigencia_fim IS DISTINCT FROM r.transferencia
               OR origem IS DISTINCT FROM 'MANUAL');
        IF NOT EXISTS (
            SELECT 1 FROM public.consultor_vigencia v
            WHERE v.nome_normalizado = r.nome AND v.loja_id = new_store
              AND v.vigencia_inicio = r.transferencia
              AND v.vigencia_fim IS NULL AND v.origem = 'MANUAL'
        ) THEN
            INSERT INTO public.consultor_vigencia
                (nome, loja_id, vigencia_inicio, vigencia_fim, origem)
            VALUES (r.nome, new_store, r.transferencia, NULL, 'MANUAL');
        END IF;
    END LOOP;

    FOR r IN SELECT * FROM m147_admissoes ORDER BY nome LOOP
        SELECT count(*), (array_agg(l.id))[1] INTO row_count, new_store
        FROM public.lojas l WHERE l.nome = r.loja;
        IF row_count <> 1 THEN
            RAISE EXCEPTION '147: loja de admissao ausente/ambigua: %', r.loja;
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM public.consultores c
            WHERE public.fn_normalizar_nome(c.nome) = r.nome AND c.loja_id = new_store
        ) THEN
            RAISE EXCEPTION '147: cadastro de admissao ausente: %', r.nome;
        END IF;
        -- A carga do HC pode ter criado a janela declarada (origem ETL);
        -- aceita sem converter para MANUAL, que travaria o desligamento.
        IF EXISTS (
            SELECT 1 FROM public.consultor_vigencia v
            WHERE v.nome_normalizado = r.nome
              AND (v.loja_id = new_store AND v.vigencia_inicio = r.admissao
                       AND v.vigencia_fim IS NULL
                       AND v.origem IN ('MANUAL', 'ETL')) IS NOT TRUE
        ) THEN
            RAISE EXCEPTION '147: admissao tem janela diferente da declarada: %', r.nome;
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM public.consultor_vigencia v WHERE v.nome_normalizado = r.nome
        ) THEN
            INSERT INTO public.consultor_vigencia
                (nome, loja_id, vigencia_inicio, vigencia_fim, origem)
            VALUES (r.nome, new_store, r.admissao, NULL, 'MANUAL');
        END IF;
    END LOOP;

    SELECT count(*), (array_agg(l.id))[1] INTO row_count, new_store
    FROM public.lojas l WHERE l.nome = 'HELP BONSUCESSO';
    IF row_count <> 1 THEN
        RAISE EXCEPTION '147: loja HELP BONSUCESSO ausente/ambigua';
    END IF;
    SELECT count(*), (array_agg(v.id))[1] INTO row_count, target_id
    FROM public.consultor_vigencia v
    WHERE v.nome_normalizado = heloina AND v.loja_id = new_store
      AND v.vigencia_inicio = DATE '2026-01-09'
      AND v.vigencia_fim IN (DATE '2026-05-01', DATE '2026-11-04');
    IF row_count <> 1 THEN
        RAISE EXCEPTION '147: janela da Heloina diferente da conferida';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.consultores c
        WHERE public.fn_normalizar_nome(c.nome) = heloina AND c.loja_id = new_store
          AND c.status IN ('Licença Maternidade', 'Desligado (a)')
    ) THEN
        RAISE EXCEPTION '147: cadastro da Heloina nao confirma licenca/estado reaplicado';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.contratos ct
        JOIN public.consultores c ON c.id = ct.consultor_id
        WHERE public.fn_normalizar_nome(c.nome) = heloina
          AND ct.data_cadastro >= DATE '2026-11-04'
    ) THEN
        RAISE EXCEPTION '147: Heloina tem contrato posterior ao desligamento declarado';
    END IF;
    SELECT min(ct.data_cadastro::date) INTO return_date
    FROM public.contratos ct
    JOIN public.consultores c ON c.id = ct.consultor_id
    WHERE public.fn_normalizar_nome(c.nome) = heloina
      AND ct.data_cadastro >= DATE '2026-05-02'
      AND ct.data_cadastro < DATE '2026-11-04';
    IF return_date IS DISTINCT FROM DATE '2026-10-20' THEN
        RAISE EXCEPTION '147: primeira digitacao da Heloina mudou: %; revisar retorno', return_date;
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.consultor_afastamento a
        WHERE a.nome_normalizado = heloina
          AND (a.tipo = 'LICENCA_MATERNIDADE'
                   AND a.data_inicio = DATE '2026-05-01'
                   AND a.data_fim = return_date AND a.origem = 'MANUAL') IS NOT TRUE
    ) THEN
        RAISE EXCEPTION '147: Heloina tem afastamento diferente do estado esperado';
    END IF;
    UPDATE public.consultor_vigencia
    SET vigencia_fim = DATE '2026-11-04', origem = 'MANUAL'
    WHERE id = target_id
      AND (vigencia_fim IS DISTINCT FROM DATE '2026-11-04'
           OR origem IS DISTINCT FROM 'MANUAL');
    IF NOT EXISTS (
        SELECT 1 FROM public.consultor_afastamento a WHERE a.nome_normalizado = heloina
    ) THEN
        INSERT INTO public.consultor_afastamento
            (nome, tipo, data_inicio, data_fim, origem, observacao)
        VALUES (heloina, 'LICENCA_MATERNIDADE', DATE '2026-05-01', return_date,
                'MANUAL', '147: inicio declarado; fim pela primeira digitacao (regra 089).');
    END IF;
    UPDATE public.consultores c SET status = 'Desligado (a)'
    WHERE public.fn_normalizar_nome(c.nome) = heloina
      AND c.status IS DISTINCT FROM 'Desligado (a)';

    -- Pos-condicao global: nenhuma sobreposicao para as pessoas corrigidas.
    IF EXISTS (
        SELECT 1 FROM public.consultor_vigencia a
        JOIN public.consultor_vigencia b
          ON b.nome_normalizado = a.nome_normalizado AND b.id > a.id
        WHERE a.nome_normalizado IN (
            SELECT nome FROM m147_transferencias
            UNION ALL SELECT nome FROM m147_admissoes
            UNION ALL SELECT heloina
        )
          AND a.vigencia_inicio < coalesce(b.vigencia_fim, 'infinity'::date)
          AND b.vigencia_inicio < coalesce(a.vigencia_fim, 'infinity'::date)
    ) THEN
        RAISE EXCEPTION '147: sobreposicao de vinculos; nenhuma correcao sera aplicada';
    END IF;
    RAISE NOTICE '147: correcoes concluidas; conferir pendencias antes de rematerializar.';
END
$migration$;

COMMIT;

-- Somente leitura. Nao exige zero: Victor e os cadastros anteriores as
-- transferencias de 01/10 ainda precisam de verificacao pela operacao.
SELECT public.fn_contar_pagamentos_sem_vinculo_origem(10, 2026)
       AS eventos_origem_ainda_pendentes_outubro;
-- A extensao do vinculo e as admissoes tambem podem alterar competencias
-- anteriores. Revisar 05..09/2026 antes de republicar qualquer historico.
-- Depois de resolver as pendencias, executar SEPARADAMENTE:
-- SELECT public.fn_materializar_caderno(10, 2026);
