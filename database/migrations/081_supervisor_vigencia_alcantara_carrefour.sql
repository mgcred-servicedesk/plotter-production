-- =====================================================
-- Migracao 081: correcao do caso HELP ALCANTARA CARREFOUR
--               + normalizacao do nome da ERICA
--
-- Depende de 076 (tabela), 077 (funcoes) e 078 (correcoes anteriores),
-- todas aplicadas em 2026-08-18.
--
-- Caso reportado pelo usuario e confirmado no banco: desligamento da
-- supervisora EMANUELE LIGIA DE AZEVEDO em 15/07/2026, sucedida por
-- ERICA CRISTINA MARINS DA SILVA. Nenhum dos dois estava registrado —
-- o caso nao constava da lista que originou a 078. Tres defeitos:
--
--   1. EMANUELE NAO TEM LINHA NO LEDGER. Saiu da planilha antes da 076,
--      entao o backfill nao a alcancou. Os 57 contratos dela (06/2025 a
--      05/2026, todos em HELP ALCANTARA CARREFOUR) contam como producao
--      de consultora nos meses em que ela era supervisora. Mesma
--      regressao da PAMELA e dos 5 ex-supervisores da 078.
--
--   2. ERICA com piso 2020-01-01, mas so assumiu em 15/07/2026 —
--      excluida retroativamente desde 2020. Bug de promocao, igual ao
--      LINDOMAR/TAMIRES/EVILLYN da 078.
--
--   3. GRAFIA DIVERGENTE, e este e o mais grave. `supervisores` e o
--      ledger gravam "ERICA CRISTINA MARINS DA SILVA ROSA"; `consultores`
--      e os contratos gravam "ERICA CRISTINA MARINS DA SILVA". Como o
--      match e por nome normalizado, a exclusao dela NUNCA funcionou —
--      nem antes do ledger, nem depois. Varredura das 47 vigencias
--      abertas: e o unico caso real. RAIANE ALMEIDA SOUZA tambem nao
--      casa, mas nao tem cadastro nem contrato — descasamento inerte.
--
-- Decisao do usuario (2026-08-18): o nome do banco e "ERICA CRISTINA
-- MARINS DA SILVA"; normatizar o registro com "ROSA" para essa forma.
--
-- Efeito no numero publicado:
--   * EMANUELE: 57 contratos saem das visoes consultor-level em
--     06/2025..05/2026. SEM efeito no headcount — ela esta
--     'Desligado (a)' no RH, logo fora do universo ativo.
--   * ERICA: passa a ser excluida a partir de 08/2026. NADA retroativo —
--     sob a ancora do dia 1o, em 01/07 ela ainda era consultora, entao
--     julho e o ultimo mes dela como consultora e os 8 contratos de
--     07/2026 seguem contando (correto).
--   * Caderno: nenhuma competencia FECHADA muda (ver validacao 4), logo
--     os snapshots da 080 nao precisam ser regerados.
--
-- Executar no Supabase SQL Editor.
-- =====================================================

BEGIN;

-- ===========================================
-- 1. Normalizar a grafia da ERICA
--
-- `supervisor_vigencia.nome_normalizado` e coluna GERADA a partir de
-- `nome`, entao atualizar `nome` ja reconstroi a chave de match. O
-- indice unico parcial (nome_normalizado, loja) so vale para linha
-- aberta e nao ha outra linha aberta dela nessa loja — sem conflito.
--
-- Idempotente: a segunda execucao nao encontra mais o nome antigo.
-- ===========================================

UPDATE public.supervisor_vigencia
   SET nome = 'ERICA CRISTINA MARINS DA SILVA'
 WHERE nome_normalizado = 'ERICA CRISTINA MARINS DA SILVA ROSA';

UPDATE public.supervisores
   SET nome = 'ERICA CRISTINA MARINS DA SILVA'
 WHERE upper(regexp_replace(btrim(nome), '[[:space:]]+', ' ', 'g'))
       = 'ERICA CRISTINA MARINS DA SILVA ROSA';


-- ===========================================
-- 2. ERICA: piso 2020-01-01 -> data real da promocao
-- ===========================================

UPDATE public.supervisor_vigencia
   SET vigencia_inicio = DATE '2026-07-15'
 WHERE nome_normalizado = 'ERICA CRISTINA MARINS DA SILVA'
   AND vigencia_fim IS NULL
   AND vigencia_inicio = DATE '2020-01-01';

-- Fallback (caminho duplo da 078): se um import intermediario tiver
-- removido e recriado a linha, garante que ela exista com a loja certa.
SELECT public.fn_aplicar_mudanca_supervisor(
    'ERICA CRISTINA MARINS DA SILVA', 'HELP ALCANTARA CARREFOUR',
    DATE '2026-07-15', 'INICIO');


-- ===========================================
-- 3. EMANUELE: linha ja fechada [2020-01-01, 2026-07-15)
--
-- Ela nao esta em `supervisores` (saiu na planilha), entao nao ha
-- vigencia aberta para fechar — entra direto como linha fechada, igual
-- aos 5 ex-supervisores da 078. Aqui, ao contrario daqueles, a loja E
-- conhecida: HELP ALCANTARA CARREFOUR, confirmada pelo cadastro e por
-- 100% da producao dela.
--
-- A data de fim casa com o inicio da ERICA: a cadeira nao fica vaga.
-- ===========================================

INSERT INTO public.supervisor_vigencia
    (nome, loja_id, vigencia_inicio, vigencia_fim)
SELECT 'EMANUELE LIGIA DE AZEVEDO', l.id,
       DATE '2020-01-01', DATE '2026-07-15'
FROM public.lojas l
WHERE l.nome = 'HELP ALCANTARA CARREFOUR'
  AND NOT EXISTS (
      SELECT 1 FROM public.supervisor_vigencia v
      WHERE v.nome_normalizado = 'EMANUELE LIGIA DE AZEVEDO'
  );

COMMIT;


-- ===========================================
-- ATENCAO — correcao na origem OBRIGATORIA
--
-- `configuracao/Supervisores.xlsx` (angry-man) precisa gravar
-- "ERICA CRISTINA MARINS DA SILVA", SEM o "ROSA".
--
-- Enquanto nao for corrigida, o proximo import faz PIOR que reverter:
-- com a 077 aplicada, o par (ERICA...ROSA, ALCANTARA CARREFOUR) e visto
-- como NOVO (nao ha vigencia aberta com esse nome depois da secao 1) e
-- abre vigencia em current_date, enquanto o par correto e visto como
-- AUSENTE e tem a vigencia FECHADA. O resultado e a linha orfa de volta
-- e a vigencia certa encerrada — os dois defeitos ao mesmo tempo.
-- ===========================================


-- ===========================================
-- Validacao (apos executar)
-- ===========================================
-- 1) Nenhum supervisor com nome que nao casa com cadastro/contratos:
--
--    SELECT v.nome
--    FROM supervisor_vigencia v
--    WHERE v.vigencia_fim IS NULL
--      AND NOT EXISTS (
--          SELECT 1 FROM consultores c
--          WHERE upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g'))
--                = v.nome_normalizado);
--    -- Esperado: so RAIANE ALMEIDA SOUZA (inerte — sem cadastro e sem
--    --           contrato; se aparecer outro nome, e um caso novo).
--
-- 2) As duas vigencias do Alcantara Carrefour, sem lacuna nem
--    sobreposicao:
--
--    SELECT v.nome, v.vigencia_inicio, v.vigencia_fim
--    FROM supervisor_vigencia v
--    JOIN lojas l ON l.id = v.loja_id
--    WHERE l.nome = 'HELP ALCANTARA CARREFOUR'
--    ORDER BY v.vigencia_inicio;
--    -- Esperado:
--    --   EMANUELE LIGIA DE AZEVEDO       2020-01-01 -> 2026-07-15
--    --   ERICA CRISTINA MARINS DA SILVA  2026-07-15 -> aberta
--
-- 3) Invariante da 077 (foto == linhas abertas) intacta:
--
--    SELECT
--      (SELECT count(*) FROM supervisor_vigencia WHERE vigencia_fim IS NULL)
--        AS abertas,
--      (SELECT count(*) FROM supervisores) AS foto;
--    -- Esperado: iguais (47 — a 081 nao cria nem remove supervisor
--    --           atual, so renomeia um e fecha uma saida antiga).
--
-- 4) Snapshots da 080 seguem validos (nenhuma competencia fechada muda):
--
--    SELECT obter_caderno_publicado(6, 2026)
--         = obter_caderno_fechamento(6, 2026) AS junho_ok,
--           obter_caderno_publicado(7, 2026)
--         = obter_caderno_fechamento(7, 2026) AS julho_ok;
--    -- Esperado: true, true. Se der false, re-materializar:
--    --   SELECT fn_materializar_caderno(mes, ano) ...
--    -- (EMANUELE esta 'Desligado (a)' => fora do universo ativo, e a
--    --  ERICA so vira supervisora em 08/2026, que ainda nao fechou.)
-- =====================================================
