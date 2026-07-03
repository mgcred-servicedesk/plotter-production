-- =====================================================
-- Migracao 050: aplicacao do remanejamento de regioes H2/2026
--
-- Estagio 3 (dados). Move 23 lojas HELP para 4 regionais (nomeadas
-- pelos gerentes: GLENDA, JACQUELINE, ROBSON, SANDRA) com vigencia a
-- partir de 2026-07-01, usando fn_aplicar_remanejamento_regiao (049).
-- A partir dessa data o historico >= jul/2026 dessas lojas conta na
-- regiao nova; <= jun/2026 permanece na regiao antiga (point-in-time).
--
-- Propriedades:
--   * ATOMICO: tudo roda dentro de um bloco DO (1 transacao). Se
--     qualquer loja falhar, NADA e aplicado.
--   * PRE-VALIDADO: antes de mutar, confere que todos os nomes de loja
--     existem em lojas.nome; se faltar algum, aborta listando quais
--     (nomes tem de bater EXATAMENTE — acentos/pontuacao inclusos).
--   * IDEMPOTENTE: reexecutar e seguro (a RPC 049 e no-op p/ loja que
--     ja esta na regiao nova; o INSERT de regioes usa ON CONFLICT).
--
-- Regioes destino sao CRIADAS se ainda nao existirem.
--
-- Executar no Supabase SQL Editor. Requer 043-049 aplicadas.
-- =====================================================

DO $$
DECLARE
    v_data_efetiva DATE := DATE '2026-07-01';
    v_faltando     TEXT;
    r              RECORD;
    v_msg          TEXT;
BEGIN
    -- Pares loja -> regiao nova (de->para informado pelo negocio).
    CREATE TEMP TABLE _remanejo (loja TEXT, regiao TEXT) ON COMMIT DROP;
    INSERT INTO _remanejo (loja, regiao) VALUES
        ('HELP PADRE MIGUEL',            'GLENDA'),
        ('HELP BELFORD ROXO',            'GLENDA'),
        ('HELP BANGU',                   'GLENDA'),
        ('HELP CASCADURA',               'GLENDA'),
        ('HELP MADUREIRA',               'GLENDA'),
        ('HELP PRACA SECA',              'GLENDA'),
        ('HELP BELFORD ROXO SAO JOSE',   'GLENDA'),
        ('HELP CAXIAS CENTRO',           'JACQUELINE'),
        ('HELP CAXIAS GUANABARA',        'JACQUELINE'),
        ('HELP CAXIAS NILO PECANHA',     'JACQUELINE'),
        ('HELP CAXIAS PRES. VARGAS',     'JACQUELINE'),
        ('HELP TIJUCA ALMIRANTE',        'ROBSON'),
        ('HELP ENGENHO NOVO',            'ROBSON'),
        ('HELP LARGO DA SEGUNDA FEIRA',  'ROBSON'),
        ('HELP SÃO CRISTOVÃO',           'ROBSON'),
        ('HELP VILA ISABEL',             'ROBSON'),
        ('HELP BONSUCESSO',              'SANDRA'),
        ('HELP COPACABANA',              'SANDRA'),
        ('HELP PENHA',                   'SANDRA'),
        ('HELP LARANJEIRAS',             'SANDRA'),
        ('HELP RAMOS',                   'SANDRA'),
        ('HELP RIO COMPRIDO',            'SANDRA'),
        ('HELP COPACABANA NOVA',         'SANDRA');

    -- Garante as regioes destino (cria se novas).
    INSERT INTO public.regioes (nome)
    SELECT DISTINCT regiao FROM _remanejo
    ON CONFLICT (nome) DO NOTHING;

    -- Pre-validacao: todas as lojas existem? (aborta com a lista dos
    -- nomes que nao batem, ANTES de qualquer mutacao de vigencia).
    SELECT string_agg(x.loja, ' | ' ORDER BY x.loja) INTO v_faltando
    FROM _remanejo x
    WHERE NOT EXISTS (
        SELECT 1 FROM public.lojas l WHERE l.nome = x.loja
    );
    IF v_faltando IS NOT NULL THEN
        RAISE EXCEPTION
            'Lojas nao encontradas (corrigir nomes p/ bater com lojas.nome): %',
            v_faltando;
    END IF;

    -- Aplica loja a loja (atomico dentro do DO).
    FOR r IN SELECT loja, regiao FROM _remanejo LOOP
        v_msg := public.fn_aplicar_remanejamento_regiao(
            r.loja, r.regiao, v_data_efetiva
        );
        RAISE NOTICE '%', v_msg;
    END LOOP;
END $$;


-- ===========================================
-- Verificacao (rodar apos o bloco acima) — deve mostrar, por loja
-- remanejada, a linha ANTIGA fechada (vigencia_fim = 2026-07-01) e a
-- NOVA aberta (vigencia_inicio = 2026-07-01, vigencia_fim NULL).
-- ===========================================
--
--   SELECT l.nome AS loja, r.nome AS regiao,
--          v.vigencia_inicio, v.vigencia_fim
--   FROM loja_regiao_vigencia v
--   JOIN lojas l   ON l.id = v.loja_id
--   JOIN regioes r ON r.id = v.regiao_id
--   WHERE l.nome LIKE 'HELP %'
--   ORDER BY l.nome, v.vigencia_inicio;
--
-- E conferir que lojas.regiao_id (atual) aponta p/ a regiao nova:
--
--   SELECT l.nome, r.nome AS regiao_atual
--   FROM lojas l JOIN regioes r ON r.id = l.regiao_id
--   WHERE l.nome LIKE 'HELP %' ORDER BY r.nome, l.nome;
-- ===========================================
