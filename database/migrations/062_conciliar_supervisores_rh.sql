-- =====================================================
-- Migracao 062: conciliar `supervisores` com o roster do RH
-- (rodizio de supervisores nao refletido na tabela)
--
-- Contexto (ver progress doc 2026-07-09-supervisor-como-
-- consultor-exclusao-global.md): o rodizio recente de
-- supervisores entre lojas atualizou o roster do RH (tabela
-- `consultores`, via ETL) mas NAO a tabela `supervisores`.
-- Estado verificado no banco em 2026-07-09 — registro atual
-- vs loja real (RH + contratos digitados em jul):
--
--   CRISTINA DE ARAUJO RIBEIRO PEREIRA:
--       HELP CAMPO GRANDE CALCADAO -> HELP BANGU
--   ISABELE DA SILVA TRINDADE DE SOUZA:
--       HELP BANGU -> HELP SANTA CRUZ PREZUNIC
--   TAMIRIS DA CONCEICAO ARRUDA:
--       HELP SANTA CRUZ PREZUNIC -> HELP CAMPO GRANDE CALCADAO
--   LUCIANA DE OLIVEIRA SOUZA:
--       HELP LARGO DA SEGUNDA FEIRA -> HELP RIO COMPRIDO
--   TIAGO FELIPE RIBEIRO:
--       HELP RIO COMPRIDO -> HELP LARGO DA SEGUNDA FEIRA
--   MONICA OLIVEIRA DOS SANTOS DA HORA:
--       duplicada (HELP PAVUNA correta + HELP VILAR DOS TELES
--       resto) -> remover so a linha de VILAR DOS TELES
--
-- Por que DELETE + INSERT (e nao UPDATE): o import do angry-man
-- (importSupervisores, configuracao/Supervisores.xlsx) faz upsert
-- com onConflict (nome, loja_id) e NUNCA remove o par antigo
-- quando alguem troca de loja — foi assim que a MONICA duplicou.
-- Se a planilha for corrigida e importada antes desta migration,
-- o par novo ja existira; um UPDATE do par antigo violaria
-- uq_supervisores_nome_loja. DELETE do par antigo + INSERT ... ON
-- CONFLICT DO NOTHING e idempotente e funciona em qualquer ordem.
--
-- ATENCAO — correcao na origem obrigatoria: enquanto
-- configuracao/Supervisores.xlsx (repo angry-man) listar as lojas
-- antigas, o proximo import RE-INSERE os pares antigos e recria a
-- divergencia. Corrigir a planilha ANTES do proximo import.
-- regiao_id segue a regiao ATUAL da loja de destino.
-- =====================================================

BEGIN;

-- ── CRISTINA: CAMPO GRANDE CALCADAO -> BANGU ──
DELETE FROM public.supervisores s
USING public.lojas l
WHERE s.nome = 'CRISTINA DE ARAUJO RIBEIRO PEREIRA'
  AND s.loja_id = l.id
  AND l.nome = 'HELP CAMPO GRANDE CALCADAO';

INSERT INTO public.supervisores (nome, loja_id, regiao_id)
SELECT 'CRISTINA DE ARAUJO RIBEIRO PEREIRA', l.id, l.regiao_id
FROM public.lojas l
WHERE l.nome = 'HELP BANGU'
ON CONFLICT (nome, loja_id) DO NOTHING;

-- ── ISABELE: BANGU -> SANTA CRUZ PREZUNIC ──
DELETE FROM public.supervisores s
USING public.lojas l
WHERE s.nome = 'ISABELE DA SILVA TRINDADE DE SOUZA'
  AND s.loja_id = l.id
  AND l.nome = 'HELP BANGU';

INSERT INTO public.supervisores (nome, loja_id, regiao_id)
SELECT 'ISABELE DA SILVA TRINDADE DE SOUZA', l.id, l.regiao_id
FROM public.lojas l
WHERE l.nome = 'HELP SANTA CRUZ PREZUNIC'
ON CONFLICT (nome, loja_id) DO NOTHING;

-- ── TAMIRIS: SANTA CRUZ PREZUNIC -> CAMPO GRANDE CALCADAO ──
DELETE FROM public.supervisores s
USING public.lojas l
WHERE s.nome = 'TAMIRIS DA CONCEICAO ARRUDA'
  AND s.loja_id = l.id
  AND l.nome = 'HELP SANTA CRUZ PREZUNIC';

INSERT INTO public.supervisores (nome, loja_id, regiao_id)
SELECT 'TAMIRIS DA CONCEICAO ARRUDA', l.id, l.regiao_id
FROM public.lojas l
WHERE l.nome = 'HELP CAMPO GRANDE CALCADAO'
ON CONFLICT (nome, loja_id) DO NOTHING;

-- ── LUCIANA: LARGO DA SEGUNDA FEIRA -> RIO COMPRIDO ──
DELETE FROM public.supervisores s
USING public.lojas l
WHERE s.nome = 'LUCIANA DE OLIVEIRA SOUZA'
  AND s.loja_id = l.id
  AND l.nome = 'HELP LARGO DA SEGUNDA FEIRA';

INSERT INTO public.supervisores (nome, loja_id, regiao_id)
SELECT 'LUCIANA DE OLIVEIRA SOUZA', l.id, l.regiao_id
FROM public.lojas l
WHERE l.nome = 'HELP RIO COMPRIDO'
ON CONFLICT (nome, loja_id) DO NOTHING;

-- ── TIAGO: RIO COMPRIDO -> LARGO DA SEGUNDA FEIRA ──
DELETE FROM public.supervisores s
USING public.lojas l
WHERE s.nome = 'TIAGO FELIPE RIBEIRO'
  AND s.loja_id = l.id
  AND l.nome = 'HELP RIO COMPRIDO';

INSERT INTO public.supervisores (nome, loja_id, regiao_id)
SELECT 'TIAGO FELIPE RIBEIRO', l.id, l.regiao_id
FROM public.lojas l
WHERE l.nome = 'HELP LARGO DA SEGUNDA FEIRA'
ON CONFLICT (nome, loja_id) DO NOTHING;

-- ── MONICA: remover duplicata (VILAR DOS TELES); PAVUNA fica ──
DELETE FROM public.supervisores s
USING public.lojas l
WHERE s.nome = 'MONICA OLIVEIRA DOS SANTOS DA HORA'
  AND s.loja_id = l.id
  AND l.nome = 'HELP VILAR DOS TELES';

COMMIT;


-- ===========================================
-- Verificacao (apos executar)
-- ===========================================
-- SELECT s.nome, l.nome AS loja, r.nome AS regiao
-- FROM supervisores s
-- JOIN lojas l ON l.id = s.loja_id
-- LEFT JOIN regioes r ON r.id = s.regiao_id
-- WHERE s.nome IN (
--     'CRISTINA DE ARAUJO RIBEIRO PEREIRA',
--     'ISABELE DA SILVA TRINDADE DE SOUZA',
--     'TAMIRIS DA CONCEICAO ARRUDA',
--     'LUCIANA DE OLIVEIRA SOUZA',
--     'TIAGO FELIPE RIBEIRO',
--     'MONICA OLIVEIRA DOS SANTOS DA HORA')
-- ORDER BY s.nome;
-- Esperado (1 linha por nome, 6 no total):
--   CRISTINA -> HELP BANGU (GLENDA)
--   ISABELE  -> HELP SANTA CRUZ PREZUNIC (ROBSON)
--   LUCIANA  -> HELP RIO COMPRIDO (SANDRA)
--   MONICA   -> HELP PAVUNA (SANDRA)
--   TAMIRIS  -> HELP CAMPO GRANDE CALCADAO (ROBSON)
--   TIAGO    -> HELP LARGO DA SEGUNDA FEIRA (ROBSON)
--
-- Nenhum nome duplicado na tabela inteira:
-- SELECT nome, COUNT(*) FROM supervisores
-- GROUP BY nome HAVING COUNT(*) > 1;
-- Esperado: 0 linhas.
--
-- Reversao (volta ao estado divergente pre-062 — improvavel):
--   repetir o padrao DELETE/INSERT com as lojas invertidas.
-- =====================================================
