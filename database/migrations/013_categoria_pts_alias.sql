-- =====================================================
-- Migracao 013: Alias de pontuacao por categoria
--
-- Problema (ver progress/2026-05-12-dashboard-pontuacao.md):
-- A regra de negocio (Tabelas.xlsx, coluna PRODUTO PTS)
-- diz que algumas categorias DEVEM buscar a pontuacao
-- atraves de outra categoria. Exemplos:
--   - SAQUE / SAQUE_BENEFICIO -> CARTAO (PTS=2,5)
--   - SUPER_CONTA -> CNC (PTS=5,0)
--
-- Hoje a tabela `pontuacao` exige uma linha por categoria
-- e por periodo. Toda virada de mes alguem precisa lembrar
-- de inserir as linhas espelhadas. Em 05/2026 isso nao foi
-- feito para SAQUE/SAQUE_BENEFICIO/SUPER_CONTA, causando
-- pontos=0 para 294 contratos (~2,1M pts faltando).
--
-- Solucao estrutural:
--   1. Coluna `categoria_pts_id` (FK opcional para si mesma)
--      em `categorias_produto`. Quando preenchida, indica
--      "use a pontuacao da categoria X para esta".
--   2. RPC `obter_pontuacao_periodo` reescrita para seguir
--      o alias via LEFT JOIN. Preserva o fallback temporal
--      (whole-period) existente.
--
-- Aliases definidos (Tabelas.xlsx, coluna PRODUTO PTS):
--   - SAQUE            -> CARTAO
--   - SAQUE_BENEFICIO  -> CARTAO
--   - SUPER_CONTA      -> CNC
--
-- PORTABILIDADE FICA SEM ALIAS: em Tabelas.xlsx ela aponta
-- para 4 alvos distintos (CONSIG / CONSIG BMG / CONSIG C6
-- / CONSIG Itau) com PTS diferentes (0,5 vs 1,0).
-- Granularidade Tabela > Categoria. Mantemos lookup direto;
-- o operacional continua inserindo a linha por mes.
--
-- Reversao: drop column + restaurar RPC anterior do
-- schema.sql (linhas 484-563 antes desta migracao).
--
-- Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- 1. Nova coluna categoria_pts_id (alias)
-- ===========================================

ALTER TABLE public.categorias_produto
    ADD COLUMN IF NOT EXISTS categoria_pts_id UUID NULL
        REFERENCES public.categorias_produto (id);

COMMENT ON COLUMN public.categorias_produto.categoria_pts_id IS
    'Alias para lookup de pontuacao. Quando preenchido, '
    'a RPC obter_pontuacao_periodo retorna a pontuacao da '
    'categoria referenciada em vez de procurar uma entrada '
    'direta para esta categoria no periodo. Permite '
    'compartilhar PTS entre categorias relacionadas '
    '(ex: SAQUE -> CARTAO, SUPER_CONTA -> CNC, conforme '
    'Tabelas.xlsx coluna PRODUTO PTS). NULL = lookup direto '
    '(comportamento padrao). O flag conta_pontuacao do '
    'contrato continua sendo o da propria categoria (nao '
    'herda do alias).';

-- Indice ajuda o LEFT JOIN da RPC.
CREATE INDEX IF NOT EXISTS idx_categorias_produto_pts_id
    ON public.categorias_produto (categoria_pts_id);


-- ===========================================
-- 2. Backfill dos aliases
-- ===========================================

UPDATE public.categorias_produto AS dest
SET categoria_pts_id = src.id
FROM public.categorias_produto AS src
WHERE dest.codigo = 'SAQUE'
  AND src.codigo  = 'CARTAO'
  AND dest.categoria_pts_id IS DISTINCT FROM src.id;

UPDATE public.categorias_produto AS dest
SET categoria_pts_id = src.id
FROM public.categorias_produto AS src
WHERE dest.codigo = 'SAQUE_BENEFICIO'
  AND src.codigo  = 'CARTAO'
  AND dest.categoria_pts_id IS DISTINCT FROM src.id;

UPDATE public.categorias_produto AS dest
SET categoria_pts_id = src.id
FROM public.categorias_produto AS src
WHERE dest.codigo = 'SUPER_CONTA'
  AND src.codigo  = 'CNC'
  AND dest.categoria_pts_id IS DISTINCT FROM src.id;


-- ===========================================
-- 3. RPC obter_pontuacao_periodo — reescrita
--
-- Mudancas em relacao a versao anterior:
--   - Driver passa a ser categorias_produto (todas as
--     categorias ativas), nao a tabela pontuacao.
--   - LEFT JOIN duplo:
--       a) pt_direta: entrada direta para essa categoria
--       b) pt_alias:  entrada da categoria apontada por
--                     categoria_pts_id (se houver)
--   - COALESCE(pt_direta, pt_alias):
--       prioridade da linha direta. Isso permite ao
--       operacional sobrescrever o alias para um periodo
--       especifico (ex: cadastrar SAQUE com pts diferente
--       de CARTAO num mes pontual).
--   - Linhas retornadas: apenas categorias que tem
--     pontos via direta OU alias no periodo escolhido.
--   - is_fallback continua sinalizando apenas o fallback
--     TEMPORAL (periodo anterior). Alias nao e fallback.
-- ===========================================

CREATE OR REPLACE FUNCTION obter_pontuacao_periodo(
    p_mes INTEGER,
    p_ano INTEGER
)
RETURNS TABLE (
    categoria_id     UUID,
    categoria_codigo TEXT,
    categoria_nome   TEXT,
    pontos           NUMERIC(10,4),
    producao         INTEGER,
    periodo_origem   TEXT,
    is_fallback      BOOLEAN
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
    -- Fallback temporal: retroceder ate achar periodo
    -- com pelo menos uma linha em pontuacao (qualquer
    -- categoria). Mesmo comportamento da versao anterior.
    LOOP
        SELECT p.id INTO v_periodo_id
        FROM public.periodos p
        WHERE p.mes = v_mes_busca AND p.ano = v_ano_busca;

        IF v_periodo_id IS NOT NULL THEN
            SELECT EXISTS(
                SELECT 1
                FROM public.pontuacao pt
                WHERE pt.periodo_id = v_periodo_id
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
        cp.id                                  AS categoria_id,
        cp.codigo                              AS categoria_codigo,
        cp.nome                                AS categoria_nome,
        COALESCE(pt_direta.pontos,
                 pt_alias.pontos)              AS pontos,
        COALESCE(pt_direta.producao,
                 pt_alias.producao)            AS producao,
        per.referencia                         AS periodo_origem,
        (v_mes_busca <> p_mes
         OR v_ano_busca <> p_ano)              AS is_fallback
    FROM public.categorias_produto cp
    LEFT JOIN public.pontuacao pt_direta
        ON pt_direta.categoria_id = cp.id
       AND pt_direta.periodo_id  = v_periodo_id
    LEFT JOIN public.pontuacao pt_alias
        ON pt_alias.categoria_id = cp.categoria_pts_id
       AND pt_alias.periodo_id   = v_periodo_id
    JOIN public.periodos per
        ON per.id = v_periodo_id
    WHERE cp.ativo = TRUE
      AND COALESCE(pt_direta.pontos, pt_alias.pontos) IS NOT NULL;
END;
$$;

COMMENT ON FUNCTION obter_pontuacao_periodo(INTEGER, INTEGER) IS
    'Retorna pontuacao efetiva por categoria para um '
    'periodo. Aplica dois mecanismos de fallback: '
    '(a) temporal — se o periodo solicitado nao tem '
    'nenhuma linha em pontuacao, retrocede ate 24 meses '
    'buscando o ultimo periodo com dados; '
    '(b) alias — categorias com categoria_pts_id '
    'preenchido herdam a pontuacao da categoria '
    'referenciada (ex: SAQUE usa pts de CARTAO). '
    'A entrada direta tem prioridade sobre o alias, '
    'permitindo overrides pontuais por periodo. '
    'is_fallback=true sinaliza apenas o fallback '
    'temporal — alias nao e fallback.';


-- ===========================================
-- 4. Validacao pos-migracao (opcional)
-- ===========================================
-- Executar em sequencia para conferir:
--
--   -- Os 3 aliases foram aplicados:
--   SELECT codigo, categoria_pts_id IS NOT NULL AS tem_alias
--   FROM categorias_produto
--   WHERE codigo IN ('SAQUE','SAQUE_BENEFICIO','SUPER_CONTA')
--   ORDER BY codigo;
--
--   -- A RPC agora retorna as 3 categorias para 05/2026
--   -- mesmo sem entradas diretas:
--   SELECT categoria_codigo, pontos, is_fallback
--   FROM obter_pontuacao_periodo(5, 2026)
--   WHERE categoria_codigo IN ('SAQUE','SAQUE_BENEFICIO','SUPER_CONTA')
--   ORDER BY categoria_codigo;
--   -- Esperado:
--   --   SAQUE              | 2.5  | false
--   --   SAQUE_BENEFICIO    | 2.5  | false
--   --   SUPER_CONTA        | 5.0  | false
