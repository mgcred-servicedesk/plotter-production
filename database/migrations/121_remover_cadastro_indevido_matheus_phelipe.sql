-- =====================================================
-- Migracao 121: remocao do cadastro indevido de
--               MATHEUS PHELIPE BANDEIRA DA SILVA
-- Data: 2026-09-23
-- Depende de: 086/087 (consultor_vigencia), 091 (headcount ponderado)
--
-- Fato declarado pela operacao (2026-09-23):
--   A pessoa NAO e membro da rede ha muito tempo. O cadastro de
--   20/08/2026 e importacao indevida — nunca houve vinculo nessa
--   competencia. Nao e desligamento: e registro que nao deveria existir.
--
-- Por isso a acao e DELETE e nao fechamento de janela. Fechar
-- (`vigencia_fim`) afirmaria "esteve na loja de 20/08 ate X" e manteria
-- peso no denominador de 08/2026 — exatamente o que a operacao nega.
-- O CHECK `chk_cv_vigencia_ordem` (fim > inicio) torna impossivel
-- fechar com janela de duracao zero, o que confirma que o caminho para
-- "nunca existiu" e a remocao da linha.
--
--
-- COMO O CASO APARECEU (confirmado pela operacao, 2026-09-23)
-- -----------------------------------------------------------
-- O extrator do banco mandou uma ADE ERRADA na relacao de producao, e
-- junto veio um CONTRATO ANTIGO — da epoca em que a pessoa ainda era da
-- rede. O ETL de contratos gravou essa linha e, ao faze-lo, CRIOU o
-- cadastro: `uq_consultores_nome_loja` e (nome, loja_id), entao um par
-- inedito INSERE em vez de reconhecer que aquela pessoa ja nao esta na
-- rede. Mesma mecanica das migrations 109 (JOYCE) e 118 (LIVIA) — muda
-- so o veredito da operacao.
--
-- A sequencia esta nos timestamps, e ela explica por que hoje nao ha
-- contrato nenhum apontando para ele:
--
--   20/08 15:22  ETL grava a linha da ADE errada -> cadastro CRIADO
--   (depois)     a ADE e corrigida na origem; a linha sai de `contratos`
--   20/08 20:42  a 086 roda o backfill e o cadastro, agora SEM producao,
--                recebe janela de PISO — `BACKFILL_PISO`
--   desde entao  ele pesa no denominador da loja sem numerador algum
--
-- Medido em 2026-09-23: ZERO contratos gravados (`created_at`) na janela
-- 15:00-15:40 de 20/08, e ZERO contratos com `data_cadastro` anterior a
-- 01/08/2026 gravados naquele dia. A linha que criou o cadastro nao
-- existe mais — a correcao do lado da producao JA ACONTECEU. O que ficou
-- para tras foi o cadastro e, cinco horas depois, o peso que a 086 deu
-- a ele.
--
-- E por isso que ele e a unica `BACKFILL_PISO` do ledger: o piso so da
-- janela a cadastro SEM producao, e ele era o unico cadastro orfao
-- existente no instante exato em que a 086 rodou.
--
--
-- O QUE ISSO DESCARTA
-- --------------------
-- A planilha `HC_Colaboradores` NAO e a origem e nao precisa ser
-- mexida — `fn_headcount_replace` (095) nunca viu esse nome. O risco de
-- recriacao tambem nao vem de la: vem do extrator repetir a ADE errada.
-- Se repetir, o cadastro volta pelo mesmo caminho e a 116 passa a
-- acusa-lo em `sem_janela_aberta` (cadastro novo, sem janela) — que e o
-- detector certo para vigiar isso, sem precisar de guarda nova.
--
--
-- O QUE FOI MEDIDO (2026-09-23, leitura pura)
-- --------------------------------------------
--   consultores            1 linha  c92ffcdb-93e1-4b68-b988-01c0082a6df9
--                          status 'Ativo (a)', created_at 2026-08-20
--                          loja HELP SANTA CRUZ PREZUNIC (49911), reg. ROBSON
--   consultor_vigencia     1 janela ABERTA desde 2026-08-20
--                          origem 'BACKFILL_PISO'
--   producao (qualquer status, qualquer mes)   ZERO
--
-- A janela e a UNICA 'BACKFILL_PISO' do ledger inteiro (1 de 415:
-- 251 BACKFILL_PRODUCAO, 121 BACKFILL_CENSURADO, 37 MANUAL, 5 ETL).
-- A 095 ja media esse mesmo 1 em 2026-08-25. O piso da 086 existe para
-- dar janela a quem tem cadastro sem producao — foi o que capturou este
-- cadastro indevido e o transformou em peso.
--
--
-- CASCATA — VERIFICADA UMA A UMA, NAO ASSUMIDA
-- ---------------------------------------------
-- FKs que apontam para `consultores(id)`, com as linhas dele medidas:
--
--   contratos.consultor_id        ON DELETE SET NULL      0 linhas
--   reconquista.consultor_id      ON DELETE SET NULL      0 linhas
--   usuario_escopos.consultor_id  ON DELETE CASCADE       0 linhas
--   reconquista_snapshot          (tabela nao existe — 031 dropou a v1)
--
-- TOTAL afetado por cascata de FK: ZERO. Nenhum DELETE em cadeia,
-- nenhum SET NULL, nenhuma producao orfanada. E o unico motivo pelo
-- qual o DELETE e aceitavel aqui: nao ha historico a preservar.
--
-- Ligadas por NOME (sem FK — NAO cascateiam, precisam de DELETE
-- explicito, e e por isso que esta migration tem dois statements):
--
--   consultor_vigencia      1 linha   <-- ORFA se so `consultores` for apagado
--   consultor_afastamento   0
--   supervisor_vigencia     0
--   supervisores            0
--   reconquista.consultor_nome  0
--
-- Apagar so `consultores` deixaria a janela aberta para tras, e como
-- `fn_headcount_ponderado` (091) le SO o ledger e NUNCA
-- `consultores.status`, o peso continuaria inteiro. O sintoma some da
-- tela de cadastro e permanece no numero. Os dois DELETEs sao um so ato.
--
--
-- EFEITO NUMERICO — LER ANTES DE APLICAR
-- ---------------------------------------
-- Medido em 2026-09-23. Agosto e setembro tem 21 DU. A loja tem 3
-- cabecas, das quais so 2 produzem; ele pesa sem numerador.
--
--   08/2026  producao da loja R$ 205.691,72 (117 contratos)
--     peso dele          0,3810  (8 DU — entrou 20/08)
--     peso da loja       2,4524 -> 2,0714     cabecas 3 -> 2
--     produtiv./dia-cab  R$ 3.993,98 -> R$ 4.728,50   (+18,4%)
--     peso da REDE       116,4761 -> 116,0951
--
--   09/2026  producao da loja R$ 102.672,06 (112 contratos, mes em curso)
--     peso dele          1,0000  (21 DU)
--     peso da loja       3,0000 -> 2,0000     cabecas 3 -> 2
--     produtiv./dia-cab  R$ 1.629,72 -> R$ 2.444,57   (+50,0%)
--     peso da REDE       121,7618 -> 120,7618
--
-- A produtividade SOBE porque sai um divisor que nunca teve numerador.
-- E a correcao pretendida — mas 08/2026 e competencia JA PUBLICADA, e
-- +18,4% numa loja de mes fechado e mudanca visivel. Ver a secao de
-- rematerializacao: sem ela, dashboard e Caderno passam a DISCORDAR.
--
--
-- DIVERGENCIA DE SUPERFICIE ATE REMATERIALIZAR
-- ---------------------------------------------
-- Este repo (`carregar_headcount_ponderado`, TTL 30min) chama
-- `fn_headcount_ponderado` AO VIVO, inclusive para meses historicos:
-- 08/2026 muda sozinho ~30min apos o DELETE.
--
-- O Caderno (bereshit) le `caderno_fechamento_snapshot`, JSONB
-- CONGELADO em 2026-09-02; e `produtividade_individual_snapshot`
-- 08/2026 contem o nome dele em 6 lugares (1 mensal + 2 semanais,
-- todos com paidEffective 0). Nenhum snapshot muda com este DELETE —
-- o aviso da 080 vale literalmente aqui.
--
-- Entao, entre aplicar e rematerializar, as duas superficies mostram
-- numeros diferentes para 08/2026. A rematerializacao nao e opcional
-- nem cosmetica: e o que fecha a migration.
-- =====================================================


-- ===========================================
-- 1. Guarda: aborta se o estado nao for o medido
-- ===========================================
-- Numero errado e pior que falha explicita. Se entre a medicao e a
-- aplicacao aparecer producao, contrato ou escopo, esta migration NAO
-- pode apagar nada — o caso deixou de ser "cadastro indevido".

DO $$
DECLARE
    v_id          uuid;
    v_contratos   integer;
    v_reconquista integer;
    v_escopos     integer;
    v_janelas     integer;
BEGIN
    SELECT id INTO v_id
      FROM public.consultores
     WHERE upper(regexp_replace(btrim(nome), '[[:space:]]+', ' ', 'g'))
           = 'MATHEUS PHELIPE BANDEIRA DA SILVA';

    IF v_id IS NULL THEN
        RAISE EXCEPTION
            'Cadastro nao encontrado — ja removido ou nome mudou. '
            'Nada a fazer; revise antes de reaplicar.';
    END IF;

    IF v_id <> 'c92ffcdb-93e1-4b68-b988-01c0082a6df9'::uuid THEN
        RAISE EXCEPTION
            'id divergente do medido (esperado c92ffcdb-..., veio %). '
            'Cadastro foi recriado: remedir antes de apagar.', v_id;
    END IF;

    SELECT count(*) INTO v_contratos
      FROM public.contratos WHERE consultor_id = v_id;
    SELECT count(*) INTO v_reconquista
      FROM public.reconquista WHERE consultor_id = v_id;
    SELECT count(*) INTO v_escopos
      FROM public.usuario_escopos WHERE consultor_id = v_id;

    IF v_contratos > 0 OR v_reconquista > 0 OR v_escopos > 0 THEN
        RAISE EXCEPTION
            'ABORTADO: a pessoa tem vinculo (contratos=%, reconquista=%, '
            'escopos=%). O caso nao e mais cadastro indevido — o certo '
            'passa a ser FECHAR a janela, nao apagar.',
            v_contratos, v_reconquista, v_escopos;
    END IF;

    SELECT count(*) INTO v_janelas
      FROM public.consultor_vigencia
     WHERE nome_normalizado = 'MATHEUS PHELIPE BANDEIRA DA SILVA';

    IF v_janelas <> 1 THEN
        RAISE EXCEPTION
            'ABORTADO: esperava 1 janela em consultor_vigencia, achou %. '
            'Estado divergente do medido em 2026-09-23.', v_janelas;
    END IF;

    RAISE NOTICE 'Guardas OK: id=%, sem producao, 1 janela.', v_id;
END $$;


-- ===========================================
-- 2. Ledger primeiro (e o que move o numero)
-- ===========================================
-- Sem FK para `consultores`: o match e por nome normalizado, e esta
-- linha NAO sai junto com o cadastro. Apagar o ledger antes garante
-- que uma interrupcao entre os dois statements deixe o estado no lado
-- seguro (cadastro sem janela = peso zero, detectavel pela 116 em
-- `sem_janela_aberta`), e nao no lado que mente no numero.

DELETE FROM public.consultor_vigencia
 WHERE nome_normalizado = 'MATHEUS PHELIPE BANDEIRA DA SILVA';


-- ===========================================
-- 3. Cadastro (a foto)
-- ===========================================

DELETE FROM public.consultores
 WHERE id = 'c92ffcdb-93e1-4b68-b988-01c0082a6df9'::uuid;


-- ===========================================
-- 4. Verificacao — rodar DEPOIS, no mesmo editor
-- ===========================================
--
-- 1) Sumiu das duas tabelas (esperado: 0 e 0):
--
--    SELECT count(*) FROM consultores
--     WHERE nome ILIKE '%BANDEIRA DA SILVA%';
--    SELECT count(*) FROM consultor_vigencia
--     WHERE nome_normalizado = 'MATHEUS PHELIPE BANDEIRA DA SILVA';
--
-- 2) O peso caiu exatamente o previsto:
--
--    SELECT * FROM fn_headcount_ponderado(8, 2026)
--     WHERE loja = 'HELP SANTA CRUZ PREZUNIC';
--    -- esperado: peso 2,0714  cabecas 2   (era 2,4524 / 3)
--
--    SELECT * FROM fn_headcount_ponderado(9, 2026)
--     WHERE loja = 'HELP SANTA CRUZ PREZUNIC';
--    -- esperado: peso 2,0000  cabecas 2   (era 3,0000 / 3)
--
-- 3) Nao sobrou orfao nem divergencia nova (116):
--
--    SELECT fn_diag_vinculo_divergente();
--    -- ele nao aparecia em lista nenhuma ANTES (medido 2026-09-23);
--    -- tambem nao pode aparecer depois. As contagens das outras listas
--    -- (3 divergencias, 4 cadastros_orfaos) devem ficar INALTERADAS.
--
-- 4) A producao da loja nao se moveu — so o denominador:
--
--    SELECT count(*), sum(valor_consolidado)
--      FROM v_contratos_dashboard
--     WHERE loja = 'HELP SANTA CRUZ PREZUNIC'
--       AND periodo_id = (SELECT id FROM periodos WHERE mes = 8 AND ano = 2026);
--    -- esperado INALTERADO: 117 contratos, R$ 205.691,72
--
--
-- ===========================================
-- 5. Rematerializacao — OBRIGATORIA
-- ===========================================
-- Enquanto nao rodar, o Caderno publicado de 08/2026 segue com o peso
-- antigo e discorda do dashboard deste repo (que recalcula ao vivo).
--
--    SELECT fn_materializar_caderno(8, 2026);
--    SELECT fn_materializar_caderno(9, 2026);
--
-- O snapshot de produtividade individual de 08/2026 tambem carrega o
-- nome dele em 6 lugares. Regerar por esse caminho (ou aceitar, de
-- forma declarada, que o snapshot publicado e uma foto de 02/09) — mas
-- decidir, nao deixar por omissao.
