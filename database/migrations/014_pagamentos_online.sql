-- =====================================================
-- Migracao 014: Pagamentos Online (extrator DNA)
--
-- Contexto:
-- Hoje a base do dashboard recebe os contratos pagos
-- apenas D+1 (via angry-man -> tabela contratos). Para
-- ter uma estimativa do dia em andamento, o angry-man
-- passa a importar tambem o extrator DNA
-- (`relatorio-completo-acompanhamento-propostas.csv`).
-- Fase inicial: upload manual no angry-man, varias vezes
-- ao dia. Fase futura: cron horario.
--
-- O que esta migracao introduz:
--   1. Coluna `codigo_dna` em `lojas` — vincula o codigo
--      da loja no extrator DNA com a loja interna.
--   2. Tabela `pagamentos_online` — destino dos uploads.
--      Cada upload e um DELETE+INSERT atomico (transacao)
--      no angry-man.
--   3. View `v_pagamentos_online_efetivo` — aplica a
--      regra "pago online" e o calculo de valor_producao,
--      e ja remove ADEs que ja entraram no consolidado.
--
-- Fora desta migracao (responsabilidade do angry-man):
--   - Upload do CSV DNA e do `Codigo Lojas Help.xlsx`.
--   - Filtro `Grupo Produto IN (...)` antes do INSERT.
--   - DELETE+INSERT atomico (BEGIN; DELETE; INSERT; COMMIT;)
--     a cada upload, com advisory lock e pre-validacao de
--     linhas minimas. Ver INTEGRACAO_PAGAMENTOS_ONLINE.md §4.1.
--   - Limpeza de fim de dia (DELETE manual ou cron 23:59)
--     para zerar a tabela antes do primeiro upload de D+1.
--     Ver INTEGRACAO_PAGAMENTOS_ONLINE.md §4.3.
--   - UPSERT em `lojas.codigo_dna` a partir do Excel.
--
-- Doc do contrato CSV -> tabela: ver
--   database/INTEGRACAO_PAGAMENTOS_ONLINE.md
--
-- Reversao:
--   DROP VIEW v_pagamentos_online_efetivo;
--   DROP TABLE pagamentos_online;
--   ALTER TABLE lojas DROP COLUMN codigo_dna;
--
-- Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- 1. lojas.codigo_dna
--
-- O codigo do extrator DNA (coluna `Loja`, ex: '49819')
-- bate 1:1 com o `CÓDIGO` do `Codigo Lojas Help.xlsx`.
-- Modelamos como coluna nova em `lojas`, em vez de
-- tabela bridge separada — assim mantemos a `lojas`
-- como single source of truth e antecipamos a adequacao
-- para o cenario futuro de API DNA online.
-- ===========================================

ALTER TABLE public.lojas
    ADD COLUMN IF NOT EXISTS codigo_dna TEXT;

ALTER TABLE public.lojas
    ADD CONSTRAINT uq_lojas_codigo_dna UNIQUE (codigo_dna);

CREATE INDEX IF NOT EXISTS idx_lojas_codigo_dna
    ON public.lojas (codigo_dna);

COMMENT ON COLUMN public.lojas.codigo_dna IS
    'Codigo da loja no extrator DNA (coluna `Loja` do '
    'relatorio-completo-acompanhamento-propostas.csv). '
    'Bate 1:1 com a coluna `CÓDIGO` do `Codigo Lojas '
    'Help.xlsx`. Populado/atualizado pelo angry-man via '
    'UPSERT (chave: lojas.nome <-> LOJA do Excel). '
    'NULL quando a loja nao tem cadastro DNA correspondente.';


-- ===========================================
-- 2. Tabela pagamentos_online
--
-- Destino do extrator DNA. PK = `proposta` (= ADE / Nº
-- PROP / num_proposta em contratos). Substituicao
-- integral a cada upload (DELETE+INSERT atomico); nao
-- mantemos historico de transicoes.
--
-- Colunas Status / Situacao / Agrupamento ficam na
-- tabela (e nao apenas filtro de ingestao) para permitir
-- que a regra "pago online" evolua na view sem mudar
-- o ingestor.
--
-- Filtro de `grupo_produto` (apenas Antecipacao em
-- Conta e Credito na Conta) e responsabilidade do
-- angry-man — ja chega filtrado aqui.
-- ===========================================

CREATE TABLE IF NOT EXISTS public.pagamentos_online (
    proposta                TEXT PRIMARY KEY,
    data_implantacao        DATE NOT NULL,
    data_status             DATE NOT NULL,
    cliente                 TEXT NOT NULL,
    grupo_produto           TEXT NOT NULL,
    produto                 TEXT NOT NULL,
    loja_codigo             TEXT NOT NULL,
    usuario_nome            TEXT,
    status                  TEXT NOT NULL,
    situacao                TEXT NOT NULL,
    agrupamento             TEXT NOT NULL,
    valor_liquido_digitado  NUMERIC(12,2),
    valor_liquido_aprovado  NUMERIC(12,2),
    valor_seguro_aprovado   NUMERIC(12,2),
    imported_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pagamentos_online_loja
    ON public.pagamentos_online (loja_codigo);

CREATE INDEX IF NOT EXISTS idx_pagamentos_online_data_status
    ON public.pagamentos_online (data_status);

CREATE INDEX IF NOT EXISTS idx_pagamentos_online_triplo
    ON public.pagamentos_online (status, situacao, agrupamento);

COMMENT ON TABLE public.pagamentos_online IS
    'Estimativa de pagamentos do dia a partir do extrator DNA. '
    'Cada upload no angry-man substitui o conteudo via '
    'DELETE+INSERT atomico. Limpeza de fim de dia (DELETE) '
    'zera a tabela antes do primeiro upload de D+1. Conteudo '
    'descartavel — fonte da verdade e `contratos` apos '
    'consolidacao D+1.';

COMMENT ON COLUMN public.pagamentos_online.proposta IS
    'Numero da proposta (= ADE / Nº PROP / contratos.num_proposta). '
    'PK do extrator DNA.';

COMMENT ON COLUMN public.pagamentos_online.loja_codigo IS
    'Codigo DNA da loja. Referencia `lojas.codigo_dna` '
    'logicamente (nao FK fisico para nao bloquear ingestao '
    'caso uma loja nova ainda nao tenha sido espelhada).';

COMMENT ON COLUMN public.pagamentos_online.imported_at IS
    'Timestamp da ingestao. Usado pela aba para mostrar '
    '"atualizado ha X min".';


-- ===========================================
-- 3. View v_pagamentos_online_efetivo
--
-- Aplica:
--   (a) Regra "pago online" — triplo filtro
--       Status='Concluída' AND Situacao='Concluída'
--       AND Agrupamento='Paga'.
--   (b) Dedup vs consolidado — exclui propostas que
--       ja figuram em `contratos` como PAGO AO CLIENTE.
--       Cobre o caso em que uma ADE aparece no extrator
--       DNA do dia mas o angry-man ja consolidou ela
--       em ciclo anterior (peculiaridade conhecida).
--   (c) Calculo de `valor_producao`:
--       - se valor_liquido_aprovado = 0/NULL -> usa
--         valor_liquido_digitado
--       - caso contrario -> valor_liquido_aprovado +
--         valor_seguro_aprovado
--
-- Convencao do projeto: SECURITY INVOKER (a view roda
-- com permissoes do usuario chamador, RLS de
-- `pagamentos_online` se aplica). Ver migracao 004.
-- ===========================================

CREATE OR REPLACE VIEW public.v_pagamentos_online_efetivo
WITH (security_invoker = on)
AS
SELECT
    p.proposta,
    p.data_implantacao,
    p.data_status,
    p.cliente,
    p.grupo_produto,
    p.produto,
    p.loja_codigo,
    l.id            AS loja_id,
    l.nome          AS loja_nome,
    l.regiao_id,
    p.usuario_nome,
    p.valor_liquido_digitado,
    p.valor_liquido_aprovado,
    p.valor_seguro_aprovado,
    CASE
        WHEN COALESCE(p.valor_liquido_aprovado, 0) = 0
            THEN COALESCE(p.valor_liquido_digitado, 0)
        ELSE COALESCE(p.valor_liquido_aprovado, 0)
             + COALESCE(p.valor_seguro_aprovado, 0)
    END             AS valor_producao,
    p.imported_at
FROM public.pagamentos_online p
LEFT JOIN public.lojas l
    ON l.codigo_dna = p.loja_codigo
WHERE p.status      = 'Concluída'
  AND p.situacao    = 'Concluída'
  AND p.agrupamento = 'Paga'
  AND NOT EXISTS (
      SELECT 1 FROM public.contratos c
      WHERE c.num_proposta = p.proposta
        AND c.status_pagamento_cliente = 'PAGO AO CLIENTE'
  );

COMMENT ON VIEW public.v_pagamentos_online_efetivo IS
    'Propostas pagas "online" (estimativa do dia) com '
    'valor_producao calculado e exclusao das ADEs que '
    'ja entraram no consolidado (contratos). Esta e a '
    'view consumida pela aba Pagamentos Online do '
    'dashboard. security_invoker=on (RLS de '
    'pagamentos_online se aplica).';


-- ===========================================
-- 4. RLS de pagamentos_online
--
-- Padrao: igual `contratos`. Mas como o produto desta
-- feature so e exibido para admin e gestor, somente
-- esses dois perfis recebem SELECT explicito. Demais
-- perfis ficam bloqueados por ausencia de policy
-- (fail-closed do RLS).
-- ===========================================

ALTER TABLE public.pagamentos_online ENABLE ROW LEVEL SECURITY;

CREATE POLICY pol_pagamentos_online_admin
    ON public.pagamentos_online FOR ALL
    USING (obter_perfil_atual() = 'admin');

CREATE POLICY pol_pagamentos_online_gestor
    ON public.pagamentos_online FOR SELECT
    USING (obter_perfil_atual() = 'gestor');


-- ===========================================
-- 5. Validacao pos-migracao (opcional)
-- ===========================================
-- Executar em sequencia para conferir:
--
--   -- Coluna criada e indice ok:
--   SELECT column_name, data_type, is_nullable
--   FROM information_schema.columns
--   WHERE table_name='lojas' AND column_name='codigo_dna';
--
--   -- Tabela e view criadas:
--   SELECT to_regclass('public.pagamentos_online'),
--          to_regclass('public.v_pagamentos_online_efetivo');
--
--   -- Smoke test (apos seed da coluna codigo_dna e
--   -- insert manual de uma proposta paga online):
--   SELECT proposta, loja_nome, valor_producao
--   FROM v_pagamentos_online_efetivo
--   LIMIT 5;
--
--   -- Conferir que dedup funciona:
--   --   1. Inserir em pagamentos_online uma proposta
--   --      cuja num_proposta ja exista em contratos
--   --      como 'PAGO AO CLIENTE'.
--   --   2. A view NAO deve retornar essa proposta.
