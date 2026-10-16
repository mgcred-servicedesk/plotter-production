-- =====================================================
-- Migracao 139: troca de supervisao HELP ALCANTARA <-> HELP ALCANTARA
--               CARREFOUR em 01/09/2026
--
-- Depende de 076/077 (ledger + fn_aplicar_mudanca_supervisor), 081
-- (normalizacao do nome da ERICA) e 113 (supervisor_vigencia.origem).
--
-- Caso reportado pelo usuario em 2026-10-16, ao analisar a Promessa
-- Diaria: em 01/09/2026 as duas supervisoras TROCARAM de loja.
--
--   ERICA CRISTINA MARINS DA SILVA   CARREFOUR -> HELP ALCANTARA
--   MARIANA DE OLIVEIRA RODRIGUES    HELP ALCANTARA -> CARREFOUR
--
-- O ledger nao registrou a troca: ERICA segue aberta em CARREFOUR desde
-- 15/07/2026 (081) e MARIANA aberta em HELP ALCANTARA desde 13/01/2026.
-- O arquivo do banco (Promessa_diaria.xlsx, set-out/2026) ja traz
-- ERICA como supervisora de 49820 (HELP ALCANTARA) e MARIANA de 56436
-- (CARREFOUR), o que bate com o relato do usuario.
--
-- POR QUE MIGRATION E NAO A PLANILHA
-- A planilha (fn_supervisores_replace) data o evento em current_date:
-- a troca entraria em 16/10 e setembro ficaria com as lojas invertidas.
-- Correcao com data real e trabalho da fn_aplicar_mudanca_supervisor
-- (REMANEJAMENTO = fecha a vigencia aberta e abre a nova na mesma data,
-- ledger e foto `supervisores` em sincronia), como 078 e 081.
--
-- NOME: mantem "ERICA CRISTINA MARINS DA SILVA", SEM "ROSA" — decisao do
-- usuario de 2026-08-18 (081). O arquivo da Promessa Diaria usa o nome
-- com "ROSA"; a promessa dela fica "sem consultor identificado" e vai
-- para o supervisor vigente de HELP ALCANTARA — ela mesma, apos esta
-- migration.
--
-- ORIGEM 'MANUAL' (doutrina da 113/117): correcao humana nao se desfaz
-- por carga. As duas janelas novas ficam imunes ao fechamento por
-- ausencia da planilha. Custo declarado: encerrar essas supervisoes no
-- futuro e ato explicito (REBAIXAMENTO na fn_movimentacoes_replace ou
-- fn_aplicar_mudanca_supervisor(..., 'FIM')).
--
-- CORRECAO NA ORIGEM OBRIGATORIA: `configuracao/Supervisores.xlsx`
-- (angry-man) precisa listar ERICA em HELP ALCANTARA e MARIANA em HELP
-- ALCANTARA CARREFOUR (ERICA sem "ROSA"). Com a planilha antiga, o
-- proximo import abre de novo os pares velhos em current_date.
--
-- Efeito no numero publicado: as duas continuam supervisoras antes e
-- depois (so muda a loja), e a exclusao de supervisor e por NOME —
-- rankings/medias de consultor nao mudam. Muda o mapa supervisor->loja
-- a partir de 09/2026 (quem supervisiona qual loja; destino dos leads
-- "sem consultor identificado" da Promessa Diaria). Validacao 3 confere
-- o Caderno de 09/2026.
--
-- Executar no Supabase SQL Editor.
-- =====================================================

BEGIN;

SELECT public.fn_aplicar_mudanca_supervisor(
    'ERICA CRISTINA MARINS DA SILVA', 'HELP ALCANTARA',
    DATE '2026-09-01', 'REMANEJAMENTO');

SELECT public.fn_aplicar_mudanca_supervisor(
    'MARIANA DE OLIVEIRA RODRIGUES', 'HELP ALCANTARA CARREFOUR',
    DATE '2026-09-01', 'REMANEJAMENTO');

UPDATE public.supervisor_vigencia v
   SET origem = 'MANUAL'
  FROM public.lojas l
 WHERE l.id = v.loja_id
   AND v.vigencia_inicio = DATE '2026-09-01'
   AND v.vigencia_fim IS NULL
   AND (
        (v.nome_normalizado = 'ERICA CRISTINA MARINS DA SILVA'
         AND l.nome = 'HELP ALCANTARA')
     OR (v.nome_normalizado = 'MARIANA DE OLIVEIRA RODRIGUES'
         AND l.nome = 'HELP ALCANTARA CARREFOUR')
   );

COMMIT;


-- =====================================================
-- VALIDACAO — rodar apos aplicar
--
-- 1) Ledger (esperado:
--    ERICA    CARREFOUR  2026-07-15 -> 2026-09-01
--    ERICA    ALCANTARA  2026-09-01 -> aberta  MANUAL
--    MARIANA  ALCANTARA  2026-01-13 -> 2026-09-01
--    MARIANA  CARREFOUR  2026-09-01 -> aberta  MANUAL
--    + a linha antiga ERICA ALCANTARA 2020-01-01 -> 2026-01-13):
--
--    SELECT v.nome, l.nome AS loja, v.vigencia_inicio, v.vigencia_fim, v.origem
--    FROM public.supervisor_vigencia v
--    JOIN public.lojas l ON l.id = v.loja_id
--    WHERE v.nome_normalizado IN ('ERICA CRISTINA MARINS DA SILVA',
--                                 'MARIANA DE OLIVEIRA RODRIGUES')
--    ORDER BY v.nome, v.vigencia_inicio;
--
-- 2) Foto `supervisores` (esperado: ERICA -> HELP ALCANTARA;
--    MARIANA -> HELP ALCANTARA CARREFOUR; uma linha cada):
--
--    SELECT s.nome, l.nome AS loja
--    FROM public.supervisores s JOIN public.lojas l ON l.id = s.loja_id
--    WHERE s.nome IN ('ERICA CRISTINA MARINS DA SILVA',
--                     'MARIANA DE OLIVEIRA RODRIGUES');
--
-- 3) Caderno 09/2026: as duas continuam excluidas como supervisoras
--    (exclusao por nome) — conferir que o universo de consultores das
--    duas lojas nao mudou comparando com o snapshot publicado antes de
--    decidir rematerializar (fn_materializar_caderno(9, 2026)).
-- =====================================================
