-- =====================================================
-- Migracao 134: Seguro Prestamista CNC — IPV
--
-- Adiciona:
--   - prestamista_cnc                   (tabela, por periodo)
--   - v_prestamista_cnc                 (view de leitura)
--   - fn_importar_prestamista_cnc()     (RPC de import)
--   - prestamista_cnc_meta              (meta do IPV por periodo)
--   - obter_meta_prestamista_cnc()      (lookup com fallback)
--   - seed da meta de 10/2026 (80%, alerta 60%)
--
-- MOTIVACAO (pedido do usuario em 2026-10-08)
-- Novo acompanhamento do seguro Prestamista do CNC. O indicador e o
-- IPV = Qtd Seguro / Qtd Elegivel, meta de 80%. Fonte: export do BI do
-- banco (`Prestamista_CNC.xlsx`, aba Export, filtro "Prst CNC" + mes),
-- uma linha por proposta (Adesao) com:
--   Qtd Contrato  0/1 (informativa)
--   Qtd Elegivel  0/1 — denominador
--   Qtd Seguro    0/1 — numerador (no arquivo de 10/2026, so a apolice
--                 "Aprovado" vem com 1; "Aguardando Envio de
--                 Arrecadacao" e elegivel com seguro 0)
--   Status Apolice (informativo)
--
-- IPV = SUM(qtd_seguro) / SUM(qtd_elegivel) — a mesma conta do BI (o
-- rodape do arquivo de 10/2026 traz 93 / 231 = 40,26%). Seguro em
-- proposta nao elegivel, se um dia aparecer, entra no numerador como
-- no BI; nao filtramos para o numero bater com a fonte.
--
-- POR PERIODO, NAO TRUNCATE (decisao do usuario)
-- O arquivo e o acumulado do mes ate a extracao. Cada import grava UM
-- periodo, escolhido no angry-man; reimportar substitui so aquele
-- periodo e os anteriores ficam (mesmo fluxo da Liga, migration 127).
--
-- ATRIBUICAO (loja/consultor) VEM DO PROPRIO ARQUIVO
-- Identica a de fn_importar_reconquista_liga (127): loja por cod_bmg
-- (prefixo de `Franquia`) com sucessora aplicada; consultor por nome
-- completo + loja. O texto original fica guardado e a view cai nele
-- quando a FK nao resolve. Conferido no arquivo de 10/2026: 48/48
-- franquias resolvem (todas ativas), 110/113 consultores resolvem.
-- `Adesao` e o num_proposta de `contratos` — nao e usado para cruzar:
-- o arquivo ja traz loja e consultor, e a fonte da conta e o banco.
--
-- META CONFIGURAVEL POR PERIODO (decisao do usuario)
-- `prestamista_cnc_meta` guarda meta_ipv (verde a partir dela) e
-- faixa_alerta (amarelo a partir dela; vermelho abaixo). Lookup com
-- fallback temporal: periodo sem meta usa a do periodo anterior mais
-- recente que tenha (espirito de obter_pontuacao_periodo, 013, e
-- obter_faixa_acelerador_reconquista, 066). Antes do primeiro periodo
-- cadastrado nao ha meta — o consumidor exibe o IPV sem semaforo.
--
-- RLS
-- prestamista_cnc: carteira de cliente (Adesao) — deny explicito para
-- anon/authenticated + REVOKE, mesmo tratamento de reconquista_liga.
-- Recorte por perfil e client-side (_filtro_rls_reconquista), por isso
-- a view expoe os MESMOS nomes regiao/loja/consultor de
-- v_reconquista_liga.
-- prestamista_cnc_meta: so limiar percentual, sem dado pessoal —
-- leitura ampla, como pontuacao e faixas_acelerador_reconquista.
--
-- Depende de: periodos, lojas, regioes, consultores (schema base).
-- Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- 1. Tabela de propostas
-- ===========================================

CREATE TABLE IF NOT EXISTS public.prestamista_cnc (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    periodo_id      UUID NOT NULL
                        REFERENCES public.periodos (id)
                        ON DELETE CASCADE,
    co_adesao       BIGINT  NOT NULL,
    qtd_contrato    INTEGER NOT NULL,
    qtd_elegivel    INTEGER NOT NULL,
    qtd_seguro      INTEGER NOT NULL,
    status_apolice  TEXT,

    -- Origem (texto bruto do arquivo + FK resolvida no import)
    no_franquia     TEXT,
    cod_bmg         INTEGER,
    loja_id         UUID REFERENCES public.lojas (id)       ON DELETE SET NULL,
    consultor_nome  TEXT,
    consultor_id    UUID REFERENCES public.consultores (id) ON DELETE SET NULL,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_prestamista_cnc_periodo_adesao
        UNIQUE (periodo_id, co_adesao),
    CONSTRAINT chk_prestamista_cnc_contrato CHECK (qtd_contrato IN (0, 1)),
    CONSTRAINT chk_prestamista_cnc_elegivel CHECK (qtd_elegivel IN (0, 1)),
    CONSTRAINT chk_prestamista_cnc_seguro   CHECK (qtd_seguro   IN (0, 1))
);

COMMENT ON TABLE public.prestamista_cnc IS
    'Seguro Prestamista CNC: export do BI do banco, uma linha por '
    'proposta (Adesao) por periodo. IPV = SUM(qtd_seguro) / '
    'SUM(qtd_elegivel), meta em prestamista_cnc_meta. Reimport '
    'substitui so o periodo (fn_importar_prestamista_cnc).';

COMMENT ON COLUMN public.prestamista_cnc.qtd_elegivel IS
    '"Qtd Elegivel" do arquivo: 1 = elegivel ao seguro (denominador '
    'do IPV), 0 = nao elegivel.';

COMMENT ON COLUMN public.prestamista_cnc.qtd_seguro IS
    '"Qtd Seguro" do arquivo: 1 = seguro ativo (numerador do IPV). '
    'Em 10/2026 so a apolice "Aprovado" vem com 1.';

COMMENT ON COLUMN public.prestamista_cnc.co_adesao IS
    '"Adesao" do arquivo — corresponde a contratos.num_proposta. '
    'Nao e usada para cruzar: loja/consultor vem do proprio arquivo.';

CREATE INDEX IF NOT EXISTS idx_prestamista_cnc_periodo
    ON public.prestamista_cnc (periodo_id);


-- ===========================================
-- 2. RLS — deny explicito (mesmo racional da 093/127)
-- ===========================================

ALTER TABLE public.prestamista_cnc ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS pol_prestamista_cnc_deny ON public.prestamista_cnc;

CREATE POLICY pol_prestamista_cnc_deny
    ON public.prestamista_cnc
    FOR ALL
    TO anon, authenticated
    USING (false)
    WITH CHECK (false);

COMMENT ON POLICY pol_prestamista_cnc_deny ON public.prestamista_cnc IS
    'Deny explicito. Carteira de cliente (Adesao) — mesmo tratamento '
    'de pol_reconquista_liga_deny (127). Todo acesso e por '
    'service_role; o recorte por perfil e client-side '
    '(_filtro_rls_reconquista).';

REVOKE ALL ON public.prestamista_cnc FROM anon, authenticated;


-- ===========================================
-- 3. View de leitura
--
-- Nomes de loja/regiao/consultor IGUAIS aos de v_reconquista_liga: o
-- recorte client-side por perfil e o mesmo. Regiao = a ATUAL da loja
-- (lojas.regiao_id), como na liga.
-- ===========================================

CREATE OR REPLACE VIEW public.v_prestamista_cnc
    WITH (security_invoker = on)
AS
SELECT
    pc.co_adesao,
    p.ano                                                     AS ano,
    p.mes                                                     AS mes,
    pc.qtd_contrato,
    pc.qtd_elegivel,
    pc.qtd_seguro,
    pc.status_apolice,
    COALESCE(l.nome, pc.no_franquia, '(Nao Identificado)')    AS loja,
    reg.nome                                                  AS regiao,
    COALESCE(con.nome, pc.consultor_nome, '(Sem Consultor)')  AS consultor,
    pc.no_franquia,
    pc.consultor_nome
FROM public.prestamista_cnc pc
JOIN public.periodos p           ON p.id   = pc.periodo_id
LEFT JOIN public.lojas l         ON l.id   = pc.loja_id
LEFT JOIN public.regioes reg     ON reg.id = l.regiao_id
LEFT JOIN public.consultores con ON con.id = pc.consultor_id;

COMMENT ON VIEW public.v_prestamista_cnc IS
    'Prestamista CNC com loja/regiao/consultor rotulados e ano/mes do '
    'periodo. Fonte do IPV do dashboard.';


-- ===========================================
-- 4. RPC de import — substitui SO o periodo
--
-- DELETE do periodo + INSERT em lote na mesma transacao. Payload:
-- lista de
--   {co_adesao, qtd_contrato, qtd_elegivel, qtd_seguro,
--    status_apolice, no_franquia, cod_bmg, consultor_nome}
-- (parse do xlsx — rodape "Total"/"Filtros aplicados" incluso — e do
-- importador). Set-based em vez do loop da 127: o arquivo tem ~1000
-- linhas, e no Nano cada round-trip de PL/pgSQL conta.
--
-- Adesao repetida no mesmo arquivo: fica uma (ON CONFLICT DO NOTHING);
-- `inseridos` < linhas enviadas denuncia o caso no log do importador.
-- ===========================================

CREATE OR REPLACE FUNCTION public.fn_importar_prestamista_cnc(
    p_periodo_id UUID,
    p_rows       JSONB
)
RETURNS TABLE (
    removidos     INTEGER,
    inseridos     INTEGER,
    elegiveis     INTEGER,
    seguros       INTEGER,
    sem_loja      INTEGER,
    sem_consultor INTEGER
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_removidos INTEGER := 0;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM public.periodos WHERE id = p_periodo_id) THEN
        RAISE EXCEPTION 'Periodo % inexistente.', p_periodo_id;
    END IF;

    DELETE FROM public.prestamista_cnc WHERE periodo_id = p_periodo_id;
    GET DIAGNOSTICS v_removidos = ROW_COUNT;

    RETURN QUERY
    WITH src AS (
        SELECT
            r.co_adesao,
            r.qtd_contrato,
            r.qtd_elegivel,
            r.qtd_seguro,
            NULLIF(TRIM(r.status_apolice), '') AS status_apolice,
            NULLIF(TRIM(r.no_franquia), '')    AS no_franquia,
            r.cod_bmg,
            NULLIF(TRIM(r.consultor_nome), '') AS consultor_nome
        FROM jsonb_to_recordset(p_rows) AS r (
            co_adesao      BIGINT,
            qtd_contrato   INTEGER,
            qtd_elegivel   INTEGER,
            qtd_seguro     INTEGER,
            status_apolice TEXT,
            no_franquia    TEXT,
            cod_bmg        INTEGER,
            consultor_nome TEXT
        )
    ),
    resolvido AS (
        SELECT s.*, lj.loja_id, cs.consultor_id
        FROM src s
        -- Loja: cod_bmg ja com sucessora aplicada (criterio da 053/127)
        LEFT JOIN LATERAL (
            SELECT COALESCE(l.sucessora_id, l.id) AS loja_id
            FROM public.lojas l
            WHERE l.cod_bmg = s.cod_bmg
            LIMIT 1
        ) lj ON true
        -- Consultor: nome completo + loja (criterio da 053/127)
        LEFT JOIN LATERAL (
            SELECT c.id AS consultor_id
            FROM public.consultores c
            WHERE s.consultor_nome IS NOT NULL
              AND c.nome ILIKE s.consultor_nome
              AND (c.loja_id = lj.loja_id OR c.loja_id IS NULL)
            ORDER BY CASE WHEN c.loja_id = lj.loja_id THEN 0 ELSE 1 END, c.nome
            LIMIT 1
        ) cs ON true
    ),
    ins AS (
        INSERT INTO public.prestamista_cnc (
            periodo_id, co_adesao, qtd_contrato, qtd_elegivel, qtd_seguro,
            status_apolice, no_franquia, cod_bmg, loja_id,
            consultor_nome, consultor_id
        )
        SELECT
            p_periodo_id, r.co_adesao, r.qtd_contrato, r.qtd_elegivel,
            r.qtd_seguro, r.status_apolice, r.no_franquia, r.cod_bmg,
            r.loja_id, r.consultor_nome, r.consultor_id
        FROM resolvido r
        ON CONFLICT (periodo_id, co_adesao) DO NOTHING
        RETURNING qtd_elegivel, qtd_seguro, loja_id, consultor_id
    )
    SELECT
        v_removidos,
        count(*)::INTEGER,
        COALESCE(sum(i.qtd_elegivel), 0)::INTEGER,
        COALESCE(sum(i.qtd_seguro), 0)::INTEGER,
        (count(*) FILTER (WHERE i.loja_id IS NULL))::INTEGER,
        (count(*) FILTER (WHERE i.consultor_id IS NULL))::INTEGER
    FROM ins i;
END;
$$;

COMMENT ON FUNCTION public.fn_importar_prestamista_cnc(UUID, JSONB) IS
    'Prestamista CNC: DELETE do periodo + carga em lote, na mesma '
    'transacao. Resolve loja_id (cod_bmg + sucessora) e consultor_id '
    '(nome completo + loja). Retorna (removidos, inseridos, elegiveis, '
    'seguros, sem_loja, sem_consultor) para o log do importador.';

-- Mesmo fechamento da 127: so service_role (angry-man via Edge
-- Function reconquista-rpc).
REVOKE EXECUTE ON FUNCTION public.fn_importar_prestamista_cnc(UUID, JSONB)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_importar_prestamista_cnc(UUID, JSONB)
    TO service_role;


-- ===========================================
-- 5. Meta do IPV por periodo
-- ===========================================

CREATE TABLE IF NOT EXISTS public.prestamista_cnc_meta (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    periodo_id    UUID NOT NULL
                      REFERENCES public.periodos (id)
                      ON DELETE CASCADE,
    meta_ipv      NUMERIC(5, 4) NOT NULL,
    faixa_alerta  NUMERIC(5, 4) NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_prestamista_cnc_meta_periodo UNIQUE (periodo_id),
    CONSTRAINT chk_prestamista_cnc_meta_ipv
        CHECK (meta_ipv > 0 AND meta_ipv <= 1),
    CONSTRAINT chk_prestamista_cnc_meta_alerta
        CHECK (faixa_alerta >= 0 AND faixa_alerta <= meta_ipv)
);

COMMENT ON TABLE public.prestamista_cnc_meta IS
    'Meta do IPV do Prestamista CNC por periodo, editavel por SQL sem '
    'deploy. Semaforo: verde >= meta_ipv; amarelo >= faixa_alerta; '
    'vermelho abaixo. Periodo sem linha usa o anterior mais recente '
    '(obter_meta_prestamista_cnc).';

COMMENT ON COLUMN public.prestamista_cnc_meta.meta_ipv IS
    'Meta do IPV em fracao (0.80 = 80%). Limite INCLUSIVO do verde.';

COMMENT ON COLUMN public.prestamista_cnc_meta.faixa_alerta IS
    'Limite INCLUSIVO do amarelo, em fracao (0.60 = 60%). Abaixo dele, '
    'vermelho.';

ALTER TABLE public.prestamista_cnc_meta ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS pol_prestamista_cnc_meta_leitura
    ON public.prestamista_cnc_meta;

CREATE POLICY pol_prestamista_cnc_meta_leitura
    ON public.prestamista_cnc_meta FOR SELECT
    USING (true);

-- Seed: meta vigente a partir de 10/2026. Idempotente e nao
-- sobrescreve ajuste manual.
INSERT INTO public.periodos (mes, ano, referencia)
VALUES (10, 2026, '10/2026')
ON CONFLICT (mes, ano) DO NOTHING;

INSERT INTO public.prestamista_cnc_meta (periodo_id, meta_ipv, faixa_alerta)
SELECT p.id, 0.80, 0.60
FROM public.periodos p
WHERE p.mes = 10 AND p.ano = 2026
ON CONFLICT ON CONSTRAINT uq_prestamista_cnc_meta_periodo DO NOTHING;


-- ===========================================
-- 6. Lookup da meta com fallback temporal
--
-- Periodo mais recente <= (p_ano, p_mes) que tenha meta. Zero linhas
-- antes do primeiro periodo cadastrado — o consumidor NAO inventa
-- meta default (exibe o IPV sem semaforo).
-- ===========================================

CREATE OR REPLACE FUNCTION public.obter_meta_prestamista_cnc(
    p_mes INTEGER,
    p_ano INTEGER
)
RETURNS TABLE (
    meta_ipv     NUMERIC,
    faixa_alerta NUMERIC,
    is_fallback  BOOLEAN
)
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
    SELECT
        m.meta_ipv,
        m.faixa_alerta,
        (p.mes <> p_mes OR p.ano <> p_ano) AS is_fallback
    FROM public.prestamista_cnc_meta m
    JOIN public.periodos p ON p.id = m.periodo_id
    WHERE (p.ano, p.mes) <= (p_ano, p_mes)
    ORDER BY p.ano DESC, p.mes DESC
    LIMIT 1;
$$;

COMMENT ON FUNCTION public.obter_meta_prestamista_cnc(INTEGER, INTEGER) IS
    'Meta do IPV do Prestamista CNC para (mes, ano): a do proprio '
    'periodo ou, sem ela, a do anterior mais recente (is_fallback). '
    'Zero linhas antes do primeiro periodo com meta.';

NOTIFY pgrst, 'reload schema';


-- =====================================================
-- VALIDACAO — rodar apos aplicar e importar 10/2026
--
-- 1) Conta do arquivo (esperado em Prestamista_CNC.xlsx de 08/10:
--    950 linhas, 231 elegiveis, 93 seguros, IPV 0,4026):
--
--    SELECT count(*), sum(qtd_elegivel), sum(qtd_seguro),
--           round(sum(qtd_seguro)::numeric / NULLIF(sum(qtd_elegivel), 0), 4)
--    FROM public.v_prestamista_cnc WHERE ano = 2026 AND mes = 10;
--
-- 2) Atribuicao (esperado: 0 sem loja, 3 sem consultor):
--
--    SELECT count(*) FILTER (WHERE loja_id IS NULL)      AS sem_loja,
--           count(*) FILTER (WHERE consultor_id IS NULL) AS sem_consultor
--    FROM public.prestamista_cnc pc
--    JOIN public.periodos p ON p.id = pc.periodo_id
--    WHERE p.ano = 2026 AND p.mes = 10;
--
-- 3) Meta (esperado: 0.80 / 0.60 / false; e 11/2026 -> fallback true):
--
--    SELECT * FROM public.obter_meta_prestamista_cnc(10, 2026);
--    SELECT * FROM public.obter_meta_prestamista_cnc(11, 2026);
--    SELECT * FROM public.obter_meta_prestamista_cnc(9, 2026);  -- 0 linhas
--
-- 4) Deny — sem grant residual para anon/authenticated (esperado: 0):
--
--    SELECT grantee, privilege_type
--    FROM information_schema.role_table_grants
--    WHERE table_name = 'prestamista_cnc'
--      AND grantee IN ('anon', 'authenticated');
-- =====================================================
