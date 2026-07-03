-- =====================================================
-- Migracao 043: loja_regiao_vigencia
--               (versionamento temporal loja -> regiao)
--
-- Motivo:
-- A regiao de um contrato sempre foi DERIVADA do estado ATUAL da
-- loja (lojas.regiao_id) via LEFT JOIN nas views/RPCs. Quando uma
-- loja e remanejada para outra regiao (ex.: 2o semestre/2026), o
-- historico inteiro dela passa a aparecer na regiao NOVA, quebrando
-- comparacoes por regiao e o recorte RLS. Nao havia versionamento.
--
-- Esta migration introduz um ledger historico (SCD Type 2, na
-- granularidade de competencia) da relacao loja -> regiao:
--   * lojas.regiao_id PERMANECE como ponteiro do organograma ATUAL
--     (autoritativo para o acesso/RLS: "lojas do gerente hoje").
--   * loja_regiao_vigencia guarda a regiao vigente em cada janela de
--     tempo. A linha ABERTA (vigencia_fim IS NULL) espelha
--     lojas.regiao_id. A invariante e mantida pelo pipeline de
--     importacao (angry-man) a cada mudanca de regiao.
--
-- Leitura point-in-time: a regiao de um contrato = linha de vigencia
-- onde a data de referencia (competencia do periodo, ou data_cadastro
-- nas janelas por data) cai em [vigencia_inicio, vigencia_fim).
--
-- Estagio 1 do rollout (no-op observavel): apos o backfill, toda loja
-- tem UMA linha aberta com a regiao atual, entao a resolucao via
-- vigencia reproduz exatamente o comportamento de hoje. As views/RPCs
-- so passam a consumir a vigencia em migrations seguintes.
--
-- Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- 1. Tabela loja_regiao_vigencia
-- ===========================================

CREATE TABLE IF NOT EXISTS loja_regiao_vigencia (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    loja_id         UUID NOT NULL REFERENCES lojas (id)
                         ON DELETE CASCADE,
    regiao_id       UUID NOT NULL REFERENCES regioes (id)
                         ON DELETE CASCADE,
    vigencia_inicio DATE NOT NULL,
    vigencia_fim    DATE,   -- NULL = vigente (linha aberta)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- fim (quando definido) sempre depois do inicio
    CONSTRAINT chk_lrv_vigencia_ordem CHECK (
        vigencia_fim IS NULL OR vigencia_fim > vigencia_inicio
    )
);

COMMENT ON TABLE loja_regiao_vigencia IS
    'Ledger historico (SCD2) da relacao loja -> regiao por janela de '
    'tempo. A linha aberta (vigencia_fim IS NULL) espelha '
    'lojas.regiao_id (organograma atual). Usado para resolver a regiao '
    'point-in-time de contratos/metas sem reescrever o historico quando '
    'uma loja e remanejada de regiao.';

CREATE TRIGGER trg_lrv_updated_at
    BEFORE UPDATE ON loja_regiao_vigencia
    FOR EACH ROW
    EXECUTE FUNCTION atualizar_updated_at();


-- ===========================================
-- 2. Indices / invariantes
-- ===========================================

-- No maximo UMA linha aberta por loja (a regiao atual).
CREATE UNIQUE INDEX IF NOT EXISTS uq_lrv_loja_aberta
    ON loja_regiao_vigencia (loja_id)
    WHERE vigencia_fim IS NULL;

-- Resolucao por range (loja + janela de vigencia).
CREATE INDEX IF NOT EXISTS idx_lrv_loja_periodo
    ON loja_regiao_vigencia (loja_id, vigencia_inicio, vigencia_fim);


-- ===========================================
-- 3. Backfill: uma linha aberta por loja com a regiao atual
--
-- Piso de vigencia = 2020-01-01 (mesmo limite inferior de
-- periodos.ano), seguramente antes de qualquer contrato. Idempotente:
-- so insere para lojas que ainda nao tem nenhuma linha de vigencia.
-- ===========================================

INSERT INTO loja_regiao_vigencia (loja_id, regiao_id, vigencia_inicio)
SELECT l.id, l.regiao_id, DATE '2020-01-01'
FROM lojas l
WHERE l.regiao_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM loja_regiao_vigencia v WHERE v.loja_id = l.id
  );


-- ===========================================
-- 4. RLS + leitura: tabela-dimensao, legivel globalmente
--
-- Mesmo padrao de lojas/regioes/periodos (schema.sql: "tabelas de
-- referencia — leitura para todos"): RLS HABILITADA (exigencia do
-- Supabase p/ tabelas no schema public expostas via API) com policy
-- permissiva de SELECT. As views que fazem join aqui sao
-- security_invoker, entao o caller precisa poder ler estas linhas.
-- Sem policy de escrita: INSERT/UPDATE (backfill e angry-man) rodam
-- via service_role, que ignora RLS — identico a lojas/regioes hoje.
-- Nao carrega dado sensivel por usuario: e a base do recorte, nao o
-- recorte.
-- ===========================================

ALTER TABLE loja_regiao_vigencia ENABLE ROW LEVEL SECURITY;

CREATE POLICY pol_lrv_leitura
    ON loja_regiao_vigencia FOR SELECT USING (true);

GRANT SELECT ON loja_regiao_vigencia TO anon, authenticated;
