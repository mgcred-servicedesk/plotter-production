-- =====================================================
-- Migracao 078: correcoes historicas do ledger supervisor_vigencia
--
-- Estagio 3 do rollout da 076. Depende da 076 (tabela + backfill) e da
-- 077 (fn_aplicar_mudanca_supervisor). NAO muda numero publicado
-- sozinha — quem le o ledger e a 079. Depois das duas aplicadas, os
-- numeros dos meses corrigidos mudam (detalhe abaixo).
--
-- A 076 deu a TODO supervisor atual uma linha aberta com piso
-- 2020-01-01 (decisao "congelar": reproduz exatamente o numero de
-- hoje). Esta migration corrige os casos em que o piso e sabidamente
-- falso — as promocoes informadas pelo usuario em 2026-08-18 — e
-- devolve ao ledger os ex-supervisores que a 063 apagou.
--
-- ANCORA (decidida em 2026-08-18): papel vigente no 1o DIA da
-- competencia vale para o mes inteiro. Consequencia caso a caso:
--   * promovido em 04/08/2026 => em 01/08 ainda era consultor, logo
--     AGOSTO fecha como consultor e SETEMBRO e o 1o mes como supervisor;
--   * promovida em 01/07/2026 => JULHO ja e o 1o mes como supervisora.
--
-- INDEPENDENTE DA ORDEM em relacao a correcao da foto. O usuario
-- corrigiu `supervisores` em 2026-08-18 (tirou a PAMELA, pos a EVILLYN
-- em HELP COPACABANA) ANTES desta migration — entao a 076 versiona a
-- EVILLYN com piso 2020-01-01, excluindo o passado dela por engano, e a
-- PAMELA fica sem linha nenhuma, devolvendo o passado dela aos rankings
-- (igual aos 5 ex-supervisores). Por isso cada caso abaixo tem CAMINHO
-- DUPLO: corrige a linha se ela existe, cria a linha se nao existe.
-- Vale nos dois sentidos — se a foto for revertida por um import antes
-- de esta migration rodar, o outro caminho assume. As unicas
-- divergencias possiveis sao datas dentro do proprio mes de agosto,
-- imateriais sob a ancora do dia 1o.
--
-- Impacto medido em 2026-08-18 (producao que volta a contar nas visoes
-- consultor-level: rankings, medias por consultor, headcount da loja):
--   LINDOMAR  1.137 contratos / R$ 1.488.195,64 / 15 competencias
--   TAMIRES   1.139 contratos / R$ 1.412.655,34 / 13 competencias
--   EVILLYN     928 contratos / R$ 1.294.156,68 / 15 competencias
--
-- E na direcao oposta — producao que volta a ser EXCLUIDA das visoes
-- consultor-level, porque a saida dela da foto (2026-08-18) devolveu o
-- passado de supervisora aos rankings:
--   PAMELA      492 contratos / R$ 565.500,76 / 11 competencias
--
-- Todos seguem contando no total da loja e no card Aceleradores, que
-- nunca excluiram supervisor (business-rules.md).
--
-- Executar no Supabase SQL Editor, depois da 076 e da 077.
-- =====================================================

BEGIN;

-- ===========================================
-- 1. Promocoes: corrigir o inicio da vigencia
--
-- Estas duas pessoas estao em `supervisores`, logo a 076 abriu vigencia
-- com piso 2020-01-01. A correcao NAO e abrir outra linha ('INICIO'
-- seria no-op por idempotencia) — e mover o inicio da linha aberta para
-- a data real da promocao.
--
-- O `SELECT fn_aplicar_mudanca_supervisor(...)` depois de cada UPDATE e
-- o caminho duplo do cabecalho: no-op quando a linha ja existe, abre a
-- vigencia (e insere na foto) se a pessoa tiver saido de `supervisores`
-- por algum import intermediario.
--
-- Idempotente: o predicado `vigencia_inicio = piso` faz a segunda
-- execucao nao mexer em nada.
-- ===========================================

-- LINDOMAR GLAUBER DA COSTA ALVES — HELP RIO COMPRIDO, 04/08/2026.
-- (Tem 4 cadastros 'Ativo (a)' em `consultores`, um por loja onde ja
-- passou; a dedup por updated_at do dashboard resolve p/ HELP RIO
-- COMPRIDO. Cadastro duplicado e problema separado, do roster.)
UPDATE public.supervisor_vigencia
   SET vigencia_inicio = DATE '2026-08-04'
 WHERE nome_normalizado = 'LINDOMAR GLAUBER DA COSTA ALVES'
   AND vigencia_fim IS NULL
   AND vigencia_inicio = DATE '2020-01-01';

SELECT public.fn_aplicar_mudanca_supervisor(
    'LINDOMAR GLAUBER DA COSTA ALVES', 'HELP RIO COMPRIDO',
    DATE '2026-08-04', 'INICIO');

-- TAMIRES MARQUES PAULOCINIO — PDV CAMPO GRANDE CF CASTRO, 01/07/2026.
-- Grafia: o usuario informou "TAMIRES MARQUES PAULOCINIO DA SILVA",
-- mas `supervisores`, `consultores` e os contratos gravam "TAMIRES
-- MARQUES PAULOCINIO" — usuario confirmou manter a grafia do banco
-- (2026-08-18). O ledger casa por nome normalizado: gravar o "DA SILVA"
-- faria a vigencia nunca encontrar a producao dela.
UPDATE public.supervisor_vigencia
   SET vigencia_inicio = DATE '2026-07-01'
 WHERE nome_normalizado = 'TAMIRES MARQUES PAULOCINIO'
   AND vigencia_fim IS NULL
   AND vigencia_inicio = DATE '2020-01-01';

SELECT public.fn_aplicar_mudanca_supervisor(
    'TAMIRES MARQUES PAULOCINIO', 'PDV CAMPO GRANDE CF CASTRO',
    DATE '2026-07-01', 'INICIO');


-- ===========================================
-- 2. EVILLYN DE OLIVEIRA ALVES — HELP COPACABANA, 04/08/2026
--
-- Estado verificado em 2026-08-18, DEPOIS de o usuario corrigir a foto:
-- ela ja esta em `supervisores` (HELP COPACABANA) e a PAMELA saiu. Logo
-- a 076 vai versiona-la no backfill com piso 2020-01-01 e quem resolve
-- e o caminho (a); o (b) fica de no-op. Antes da correcao da foto era o
-- contrario — os dois caminhos existem por isso.
--
-- Efeito da correcao da foto: desde 2026-08-18 ela E excluida — e
-- retroativamente, nas 15 competencias. E o proprio bug que esta
-- migration existe para consertar, so que recem-criado. Com o ledger,
-- a exclusao dela passa a valer de setembro/2026 em diante e os 928
-- contratos anteriores voltam para as visoes consultor-level.
--
-- Loja: existem DUAS lojas ativas com nome parecido — HELP COPACABANA
-- e HELP COPACABANA NOVA (supervisionada por RAIANE ALMEIDA SOUZA).
-- HELP COPACABANA e a informada pelo usuario e bate com o cadastro
-- dela, movido para la em 11/08/2026 — mesma data em que a PAMELA
-- (supervisora anterior de HELP COPACABANA) foi marcada 'Desligado
-- (a)'. A producao dela em agosto ainda sai em HELP COPACABANA NOVA,
-- de onde veio.
-- ===========================================

-- (a) Se a foto ja tiver sido corrigida ANTES da 076, ela entrou no
--     backfill com piso 2020-01-01 — move para a data real.
UPDATE public.supervisor_vigencia
   SET vigencia_inicio = DATE '2026-08-04'
 WHERE nome_normalizado = 'EVILLYN DE OLIVEIRA ALVES'
   AND vigencia_fim IS NULL
   AND vigencia_inicio = DATE '2020-01-01';

-- (b) Caminho normal: ainda nao ha linha — abre a vigencia e insere o
--     par na foto. No-op se (a) ja resolveu.
SELECT public.fn_aplicar_mudanca_supervisor(
    'EVILLYN DE OLIVEIRA ALVES', 'HELP COPACABANA',
    DATE '2026-08-04', 'INICIO');


-- ===========================================
-- 3. PAMELA CRISTINA MOREIRA DE PAIVA — fim em 04/08/2026
--
-- Sucedida pela EVILLYN em HELP COPACABANA e marcada 'Desligado (a)'
-- no RH em 11/08/2026. O usuario ja a removeu de `supervisores` em
-- 2026-08-18, entao aqui quem resolve e o caminho (b): sem ele, ela nao
-- teria linha nenhuma no ledger e os 492 contratos dela voltariam a
-- contar como producao de consultor.
--
-- A data exata e IMATERIAL para qualquer numero publicado: sob a
-- ancora do dia 1o, 04/08 e 11/08 caem os dois em agosto, e ela nao
-- tem producao depois de 05/2026. Escolhido 04/08 = a passagem de
-- bastao, que mantem a cadeira de HELP COPACABANA ocupada sem lacuna.
-- ===========================================

-- (a) Caminho normal: linha aberta vinda do backfill da 076 — fecha e
--     tira o par da foto. Se ela nao tiver linha aberta, e no-op (nao
--     levanta excecao).
SELECT public.fn_aplicar_mudanca_supervisor(
    'PAMELA CRISTINA MOREIRA DE PAIVA', 'HELP COPACABANA',
    DATE '2026-08-04', 'FIM');

-- (b) Se a foto ja tiver sido corrigida ANTES da 076, ela nunca entrou
--     no ledger e (a) nao teve o que fechar — sem esta linha, os 492
--     contratos dela (05/2025..05/2026) voltariam a contar como
--     producao de consultor, a mesma regressao dos 5 ex-supervisores.
INSERT INTO public.supervisor_vigencia
    (nome, loja_id, vigencia_inicio, vigencia_fim)
SELECT 'PAMELA CRISTINA MOREIRA DE PAIVA', l.id,
       DATE '2020-01-01', DATE '2026-08-04'
FROM public.lojas l
WHERE l.nome = 'HELP COPACABANA'
  AND NOT EXISTS (
      SELECT 1 FROM public.supervisor_vigencia v
      WHERE v.nome_normalizado = 'PAMELA CRISTINA MOREIRA DE PAIVA'
  );


-- ===========================================
-- 4. Os 5 ex-supervisores apagados pela 063
--
-- O progress doc 2026-07-08 mandava explicitamente NAO deletar estas
-- linhas ("mantê-los é necessário p/ excluir a produção histórica
-- deles"); o replace-style da 063, uma semana depois, tornou o DELETE
-- o mecanismo. Resultado: 86 contratos entre 05/2025 e 03/2026
-- voltaram a contar como producao de consultor. Entram aqui como
-- linhas JA FECHADAS.
--
-- Loja: so a TALITA tem loja identificada — usuario informou em
-- 2026-08-18 que ela veio do backoffice e por ultimo exercia o papel de
-- supervisora do DIGITAL ate ser desligada (bate com o cadastro dela:
-- VAI E VEM 'Ativo (a)' antigo, DIGITAL 'Desligado (a)' em 11/08). Note
-- que DIGITAL nao e backoffice para efeito de metrica — VAI E VEM esta
-- fora das medias, DIGITAL conta (business-rules.md).
--
-- Os outros 4 ficam com loja_id NULL de proposito: cada um tem DOIS
-- cadastros em `consultores` apontando lojas diferentes e
-- `supervisores` nao os tem mais — nao ha evidencia de qual loja
-- supervisionavam. A exclusao historica e POR NOME, entao a loja nao
-- muda nenhum resultado; inferi-la do cadastro conflitante seria
-- fabricar dado. A loja so importa na visao de equipe/70%, que le o
-- presente e nao enxerga linha fechada.
--
-- Data de fim 2026-07-01 = a planilha de supervisores de 2026-07-08 em
-- que o usuario confirmou os desligamentos. IMATERIAL: os cinco estao
-- 'Desligado (a)' no RH (fora do headcount) e nenhum tem producao
-- depois de 03/2026 — qualquer data a partir de 2026-04-01 produz
-- numeros identicos.
--
-- Idempotente via NOT EXISTS.
-- ===========================================

INSERT INTO public.supervisor_vigencia (nome, loja_id, vigencia_inicio, vigencia_fim)
SELECT n.nome, l.id, DATE '2020-01-01', DATE '2026-07-01'
FROM (VALUES
    ('ALANA SOUZA DO NASCIMENTO',   NULL::text),
    ('LEONARDO MEYER ROLY',         NULL),
    ('MICHELE TINOCO DA CONCEICAO', NULL),
    ('TALITA PINTO DA SILVA',       'DIGITAL'),
    ('THAIS REBELLO DE ALMEIDA',    NULL)
) AS n(nome, loja_nome)
LEFT JOIN public.lojas l ON l.nome = n.loja_nome
WHERE NOT EXISTS (
    SELECT 1 FROM public.supervisor_vigencia v
    WHERE v.nome_normalizado = upper(regexp_replace(
              btrim(n.nome), '[[:space:]]+', ' ', 'g'))
);

COMMIT;


-- ===========================================
-- ATENCAO — correcao na origem OBRIGATORIA
--
-- Mesma licao da 062: `supervisores` e reescrita por inteiro a cada
-- import da planilha. Enquanto configuracao/Supervisores.xlsx
-- (angry-man) NAO listar a EVILLYN em HELP COPACABANA e AINDA listar a
-- PAMELA, o proximo import desfaz a secao 2 e a 3 desta migration —
-- e agora, com a 077, o desfazimento tambem FECHA a vigencia da
-- EVILLYN e REABRE a da PAMELA.
--
-- Corrigir a planilha ANTES do proximo import:
--   - trocar PAMELA CRISTINA MOREIRA DE PAIVA por
--     EVILLYN DE OLIVEIRA ALVES na linha de HELP COPACABANA.
-- ===========================================


-- ===========================================
-- Verificacao (apos executar)
-- ===========================================
-- 1) As tres promocoes com a data real (e nenhum piso sobrando nelas):
--
--    SELECT nome, vigencia_inicio, vigencia_fim
--    FROM supervisor_vigencia
--    WHERE nome_normalizado IN (
--        'LINDOMAR GLAUBER DA COSTA ALVES',
--        'TAMIRES MARQUES PAULOCINIO',
--        'EVILLYN DE OLIVEIRA ALVES')
--    ORDER BY nome;
--    -- Esperado: 3 linhas abertas, inicios 2026-08-04 / 2026-07-01 /
--    --           2026-08-04.
--
-- 2) PAMELA fechada e fora da foto:
--
--    SELECT vigencia_inicio, vigencia_fim FROM supervisor_vigencia
--    WHERE nome_normalizado = 'PAMELA CRISTINA MOREIRA DE PAIVA';
--    -- Esperado: 1 linha [2020-01-01, 2026-08-04)
--    SELECT count(*) FROM supervisores
--    WHERE nome = 'PAMELA CRISTINA MOREIRA DE PAIVA';   -- Esperado: 0
--
-- 3) Os 5 ex-supervisores de volta, fechados:
--
--    SELECT nome, vigencia_inicio, vigencia_fim, loja_id
--    FROM supervisor_vigencia v
--    LEFT JOIN lojas l ON l.id = v.loja_id
--    WHERE v.vigencia_fim = DATE '2026-07-01' ORDER BY v.nome;
--    -- Esperado: 5 linhas — TALITA em DIGITAL, as outras 4 sem loja.
--
-- 4) Invariante da 077 (foto == linhas abertas) continua de pe:
--
--    SELECT
--      (SELECT count(*) FROM supervisor_vigencia WHERE vigencia_fim IS NULL)
--        AS abertas,
--      (SELECT count(*) FROM supervisores) AS foto;
--    -- Esperado: iguais — 47, a foto ja corrigida pelo usuario em
--    --           2026-08-18 (EVILLYN dentro, PAMELA fora).
--
-- 5) Leitura point-in-time em 06/2026 — os tres promovidos NAO devem
--    aparecer como supervisores:
--
--    SELECT count(*) FROM supervisor_vigencia
--    WHERE vigencia_inicio <= DATE '2026-06-01'
--      AND (vigencia_fim IS NULL OR vigencia_fim > DATE '2026-06-01')
--      AND nome_normalizado IN (
--          'LINDOMAR GLAUBER DA COSTA ALVES',
--          'TAMIRES MARQUES PAULOCINIO',
--          'EVILLYN DE OLIVEIRA ALVES');
--    -- Esperado: 0.
-- =====================================================
