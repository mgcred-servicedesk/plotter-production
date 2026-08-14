-- =====================================================
-- Migracao 068: completa a 066 — `is_deflator` em
--               faixas_acelerador_reconquista e na RPC
--
-- POR QUE ESTA MIGRATION EXISTE
-- A 066 foi APLICADA no Supabase em 2026-08-11 (seed das 4
-- faixas de Ago/26) numa versao que ainda NAO tinha
-- `is_deflator`; o arquivo ganhou a coluna depois, no commit
-- b7b4dcd (2026-08-12), editado in-place. Resultado auditado
-- na base em 2026-08-14:
--
--   - faixas_acelerador_reconquista SEM a coluna is_deflator
--   - obter_faixa_acelerador_reconquista devolvendo apenas
--     {rotulo, is_fallback}
--
-- Consequencia no dashboard (bug silencioso, sem excecao):
-- `carregar_faixa_acelerador` (src/dashboard/loaders.py) faz
-- `bool(linhas[0].get("is_deflator"))` — chave ausente vira
-- None, que vira False. O alerta de faixa deflatora em
-- src/dashboard/ui/kpi_cards_reforma.py NUNCA dispara: a faixa
-- "0 a 2" deixa de ser sinalizada como desconto.
--
-- POR QUE NAO BASTA RE-EXECUTAR A 066
-- A 066 e idempotente na ESTRUTURA (ADD COLUMN IF NOT EXISTS,
-- DROP FUNCTION antes do CREATE), mas o seed usa
-- `ON CONFLICT (periodo_id, ordem) DO NOTHING` — e as 4 linhas
-- de Ago/26 JA EXISTEM. Re-executar criaria a coluna com
-- DEFAULT false e nao marcaria a faixa "0 a 2": o bug
-- continuaria, agora com a coluna presente e todo mundo em
-- false. E preciso um UPDATE explicito, que e o nucleo desta
-- migration.
--
-- POR QUE UMA MIGRATION NOVA, E NAO OUTRA EDICAO DA 066
-- Migration aplicada e imutavel (AGENTS.md / CLAUDE.md). Editar
-- a 066 de novo repetiria exatamente a causa do problema: o
-- arquivo passaria a descrever um estado que a base nunca teve,
-- e a proxima auditoria encontraria a mesma divergencia.
--
-- ESCOPO: so o que ficou faltando. Nao mexe em RLS/policy (ja
-- aplicadas pela 066 e inalteradas), nao re-seeda faixas, nao
-- toca em nada da 067.
--
-- GRANTS: a 066 nao define nenhum GRANT sobre esta RPC — ela
-- vive com o EXECUTE default de PUBLIC. O DROP/CREATE abaixo
-- recria nesse mesmo estado; nao ha grant a restaurar.
--
-- Executar no Supabase SQL Editor. Requer 066 aplicada.
-- =====================================================


-- ===========================================
-- 0. Pre-condicao: 066 aplicada
-- ===========================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name   = 'faixas_acelerador_reconquista'
    ) THEN
        RAISE EXCEPTION
            'Migration 066 nao aplicada (tabela '
            'faixas_acelerador_reconquista ausente). Aplique '
            '066_faixas_acelerador_reconquista.sql antes desta.';
    END IF;
END
$$;


-- ===========================================
-- 1. Coluna is_deflator
--
-- Identica a declaracao da 066 (o CREATE TABLE de la, e o
-- ALTER de idempotencia). IF NOT EXISTS: numa base que ja
-- tenha rodado a versao final da 066, este passo e no-op.
-- ===========================================

ALTER TABLE faixas_acelerador_reconquista
    ADD COLUMN IF NOT EXISTS is_deflator BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN faixas_acelerador_reconquista.is_deflator IS
    'TRUE na faixa que representa DESCONTO (deflator) sobre o '
    'premio total; FALSE nas faixas de premio positivo. Nao e '
    'valor: e a natureza da faixa, para a UI destacar a faixa '
    'negativa sem hardcodar o limiar (hoje "0 a 2"). Se os '
    'limites mudarem, basta mover a flag de linha — nenhum '
    'deploy de codigo.';


-- ===========================================
-- 2. Marcar a faixa deflatora nas linhas JA existentes
--
-- Este e o passo que a re-execucao da 066 nao faz (o seed dela
-- e DO NOTHING sobre linhas existentes).
--
-- Regra de negocio da 066: "so a primeira faixa e deflator
-- (desconto sobre o premio total); as demais sao premio
-- positivo" => a faixa de `ordem = 1` do periodo.
--
-- O `NOT EXISTS` restringe o UPDATE a periodos que ainda NAO
-- tem nenhuma faixa marcada. Duas propriedades que interessam:
--   a) IDEMPOTENTE — rodar duas vezes nao muda nada na segunda;
--   b) NAO SOBRESCREVE CONFIGURACAO DELIBERADA. A tabela e
--      descrita na 066 como "configuracao editavel por SQL, sem
--      deploy": se alguem ja tiver movido o deflator para outra
--      ordem num periodo, esta migration deixa esse periodo em
--      paz em vez de reverter a decisao.
-- Hoje isso alcanca exatamente as 4 linhas de Ago/26 (as unicas
-- existentes na auditoria de 2026-08-14), marcando "0 a 2".
-- ===========================================

UPDATE faixas_acelerador_reconquista f
SET is_deflator = true
WHERE f.ordem = 1
  AND NOT EXISTS (
      SELECT 1
      FROM faixas_acelerador_reconquista d
      WHERE d.periodo_id = f.periodo_id
        AND d.is_deflator
  );


-- ===========================================
-- 3. RPC obter_faixa_acelerador_reconquista
--
-- Corpo identico ao da 066 (secao 4) — a unica diferenca em
-- relacao ao que esta HOJE na base e o `is_deflator` no
-- RETURNS TABLE e na projecao final.
--
-- DROP antes do CREATE: CREATE OR REPLACE nao altera o tipo de
-- retorno de uma funcao existente, e a assinatura de retorno
-- muda de 2 para 3 colunas.
--
-- ATENCAO ao consumidor durante a janela do DROP: o dashboard
-- chama esta RPC em `carregar_faixa_acelerador`. Rodar a
-- migration inteira numa unica execucao (o SQL Editor envolve o
-- lote numa transacao) mantem a janela imperceptivel.
-- ===========================================

DROP FUNCTION IF EXISTS obter_faixa_acelerador_reconquista(
    INTEGER, INTEGER, INTEGER
);

CREATE OR REPLACE FUNCTION obter_faixa_acelerador_reconquista(
    p_qtd INTEGER,
    p_mes INTEGER,
    p_ano INTEGER
)
RETURNS TABLE (
    rotulo      TEXT,
    is_fallback BOOLEAN,
    is_deflator BOOLEAN
)
LANGUAGE plpgsql
STABLE
SET search_path = ''
AS $$
DECLARE
    v_periodo_id UUID;
    v_tem_dados  BOOLEAN;
    v_mes_busca  INTEGER := p_mes;
    v_ano_busca  INTEGER := p_ano;
    v_tentativas INTEGER := 0;
BEGIN
    -- Sem contagem nao ha faixa a resolver.
    IF p_qtd IS NULL THEN
        RETURN;
    END IF;

    -- Fallback temporal: retroceder ate achar periodo com pelo
    -- menos uma faixa cadastrada.
    LOOP
        SELECT p.id INTO v_periodo_id
        FROM public.periodos p
        WHERE p.mes = v_mes_busca AND p.ano = v_ano_busca;

        IF v_periodo_id IS NOT NULL THEN
            SELECT EXISTS(
                SELECT 1
                FROM public.faixas_acelerador_reconquista f
                WHERE f.periodo_id = v_periodo_id
            ) INTO v_tem_dados;

            EXIT WHEN v_tem_dados;
        END IF;

        v_tentativas := v_tentativas + 1;
        IF v_tentativas > 24 THEN
            RETURN;
        END IF;

        v_mes_busca := v_mes_busca - 1;
        IF v_mes_busca < 1 THEN
            v_mes_busca := 12;
            v_ano_busca := v_ano_busca - 1;
        END IF;
    END LOOP;

    RETURN QUERY
    SELECT
        f.rotulo,
        (v_mes_busca <> p_mes
         OR v_ano_busca <> p_ano)              AS is_fallback,
        f.is_deflator
    FROM public.faixas_acelerador_reconquista f
    WHERE f.periodo_id = v_periodo_id
      AND p_qtd BETWEEN f.qtd_min
                    AND COALESCE(f.qtd_max, 2147483647)
    ORDER BY f.ordem
    LIMIT 1;
END;
$$;

COMMENT ON FUNCTION obter_faixa_acelerador_reconquista(INTEGER, INTEGER, INTEGER) IS
    'Resolve a faixa do acelerador combinado (reconquistas '
    'EFETIVADAS + Cobranca Consignavel) para uma contagem e um '
    'periodo. Fallback temporal identico ao de '
    'obter_pontuacao_periodo: se o periodo pedido nao tem faixas '
    'cadastradas, retrocede ate 24 meses e sinaliza '
    'is_fallback=true. Retorna 0 linhas quando nao ha faixa '
    'aplicavel (periodo anterior a vigencia da regra, p_qtd NULL '
    'ou contagem fora das faixas) — o consumidor NAO deve '
    'assumir faixa default. Devolve rotulo + is_deflator (natureza '
    'da faixa): o VALOR do premio/deflator nao existe nesta tabela '
    'e nao e exibido pelo dashboard.';


-- ===========================================
-- 4. Validacao pos-migracao
-- ===========================================
-- 1) A coluna existe e a faixa deflatora esta marcada — este e o
--    estado que a 066 pretendia e a base nao tinha:
--
--   SELECT p.referencia, f.ordem, f.qtd_min, f.qtd_max, f.rotulo,
--          f.is_deflator
--   FROM faixas_acelerador_reconquista f
--   JOIN periodos p ON p.id = f.periodo_id
--   ORDER BY p.ano, p.mes, f.ordem;
--   -- Esperado (Ago/26): is_deflator = true SO na ordem 1
--   --                    ("0 a 2"); false nas ordens 2, 3 e 4.
--
-- 2) Exatamente um deflator por periodo (invariante):
--
--   SELECT p.referencia,
--          count(*) FILTER (WHERE f.is_deflator) AS deflatores
--   FROM faixas_acelerador_reconquista f
--   JOIN periodos p ON p.id = f.periodo_id
--   GROUP BY p.referencia, p.ano, p.mes
--   ORDER BY p.ano, p.mes;
--   -- Esperado: deflatores = 1 em todo periodo. Zero indica
--   -- periodo seeded sem a flag (rodar de novo a secao 2);
--   -- 2+ indica configuracao manual conflitante.
--
-- 3) A RPC devolve as TRES colunas (era o que faltava):
--
--   SELECT * FROM obter_faixa_acelerador_reconquista(1, 8, 2026);
--   -- Esperado: rotulo = "0 a 2", is_fallback = false,
--   --           is_deflator = TRUE
--
-- 4) Flag vinda da RPC ao longo das faixas (o dashboard le daqui,
--    nao hardcoda o limiar):
--
--   SELECT q, (SELECT is_deflator
--              FROM obter_faixa_acelerador_reconquista(q, 8, 2026))
--   FROM generate_series(0, 12) AS q;
--   -- Esperado: true para 0,1,2; false do 3 em diante
--
-- 5) Nao houve regressao nas bordas de faixa (comportamento que
--    JA funcionava antes desta migration — tem que continuar):
--
--   SELECT q, (SELECT rotulo
--              FROM obter_faixa_acelerador_reconquista(q, 8, 2026))
--   FROM generate_series(0, 12) AS q;
--   -- Esperado: 0-2 -> "0 a 2"; 3-5 -> "3 a 5"; 6-8 -> "6 a 8";
--   --           9,10,11,12 -> "9 ou mais"
--
-- 6) Fallback temporal e vigencia (idem — sem regressao):
--
--   SELECT * FROM obter_faixa_acelerador_reconquista(4, 9, 2026);
--   -- Esperado: "3 a 5", is_fallback = true, is_deflator = false
--
--   SELECT count(*) FROM obter_faixa_acelerador_reconquista(4, 7, 2026);
--   -- Esperado: 0 linhas (antes da vigencia da regra)
--
-- 7) RLS intacta (a 068 nao toca em policy; e conferencia):
--
--   SELECT relrowsecurity FROM pg_class
--   WHERE relname = 'faixas_acelerador_reconquista';   -- true
--
--   SELECT policyname, cmd FROM pg_policies
--   WHERE tablename = 'faixas_acelerador_reconquista';
--   -- Esperado: apenas pol_faixas_acel_reconq_leitura / SELECT
--
-- 8) Conferencia no dashboard, depois de limpar o cache:
--    um consultor/supervisor com total do acelerador entre 0 e 2
--    passa a exibir o alerta de faixa deflatora (que ate agora
--    nunca aparecia).
