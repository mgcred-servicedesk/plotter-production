-- =====================================================
-- Migracao 089: consultor_afastamento
--               (ledger de ausencia + fechamento por digitacao)
--
-- Fecha a lacuna diagnosticada em 2026-08-20: nenhum ponto do sistema
-- distingue "ativo presente que vendeu zero" de "ativo afastado". As
-- medias escondem os dois (ambos ausentes do denominador, porque o
-- denominador vem da producao) e o cadastro conta os dois (ambos
-- presentes). O unico caso que funciona hoje e acidental: uma pessoa
-- em que o RH digitou 'Licenciado (a)' na coluna STATUS.
--
-- Fonte do sinal: o RH JA informa afastamento, na coluna `Obs` de
-- HC_Colaboradores.xlsx (2 licencas maternidade, 1 afastamento medico,
-- 1 licenca medica em 2026-08-20). O ETL descarta — `consultores` so
-- tem (nome, loja_id, status). Esta migration cria o destino.
--
--
-- POR QUE TABELA SEPARADA, E NAO UMA COLUNA EM consultor_vigencia
-- ---------------------------------------------------------------
-- Vinculo e ausencia sao ORTOGONAIS: a pessoa continua vinculada a
-- loja enquanto afastada (a ERICA seguiu sendo de HELP ALCANTARA os 5
-- meses de licenca; o cadastro dela dizia 'Licenciado (a)' NAQUELA
-- loja). Sobrepor as duas dimensoes na mesma tabela quebraria a
-- invariante que a 086 verifica — janelas de vinculo nao podem se
-- sobrepor, e uma pessoa afastada teria duas linhas simultaneas.
--
-- Tres ledgers ortogonais, um por pergunta:
--   consultor_vigencia   -> em qual LOJA a pessoa estava
--   supervisor_vigencia  -> em qual PAPEL ela estava
--   consultor_afastamento-> se ela estava DISPONIVEL
--
-- Por isso esta tabela NAO tem loja_id: afastamento e da pessoa. A
-- loja sai do cruzamento com consultor_vigencia, na 090.
--
--
-- A ASSIMETRIA, AGORA EM CODIGO
-- ------------------------------
-- "Producao prova presenca; a falta dela nao prova ausencia."
-- Medido em 2026-08-20: a cobertura de dias com digitacao e 82%
-- (mediana) em meses de regime, mas 21% dos meses de regime ficam
-- abaixo de 25% — silencio nao serve para inferir ausencia.
--
-- Consequencia pratica, e o motivo de fn_fechar_afastamentos_por_producao
-- existir: o RH acerta o INICIO e erra o FIM. Verificado nos 4 nomes
-- marcados na planilha — ERICA seguia 'Licenciado (a)' meses depois de
-- ter voltado; ANA LETICIA seguia com "Afastamento medico" na Obs sendo
-- a maior produtora da base desde marco. Ninguem volta na planilha para
-- limpar.
--
-- Entao: o RH declara a abertura, e a DIGITACAO fecha sozinha. A data
-- de retorno nunca precisa ser informada.
--
--
-- PRIVACIDADE — E AQUI ESTA TABELA DIFERE DAS OUTRAS DUAS
-- --------------------------------------------------------
-- 076 e 086 liberam SELECT para anon/authenticated porque guardam
-- estrutura organizacional. Esta guarda MOTIVO DE AFASTAMENTO, que e
-- dado pessoal sensivel (saude, gravidez). O projeto usa UMA chave
-- Supabase compartilhada: o que anon le, qualquer portador da chave le.
--
-- Decisao: NENHUM grant para anon/authenticated. RLS habilitada e sem
-- policy de leitura — fail-closed. O acesso acontece por RPC
-- SECURITY DEFINER (fn_headcount_ponderado, na 090), que devolve PESO
-- agregado e NUNCA o tipo nem o nome do afastado. O dashboard precisa
-- saber que a pessoa pesa 0 naquele mes; nao precisa saber por que.
--
-- Executar no Supabase SQL Editor, depois da 088.
-- =====================================================


-- ===========================================
-- 1. Tabela
--
-- Chave de identidade = nome normalizado, como 076/086. Coluna GERADA,
-- entao nome e nome_normalizado nunca divergem.
-- ===========================================

CREATE TABLE IF NOT EXISTS consultor_afastamento (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome             TEXT NOT NULL,
    nome_normalizado TEXT GENERATED ALWAYS AS (
                         upper(regexp_replace(
                             btrim(nome), '[[:space:]]+', ' ', 'g'))
                     ) STORED,
    tipo             TEXT NOT NULL,
    data_inicio      DATE NOT NULL,
    data_fim         DATE,   -- NULL = afastamento EM CURSO
    origem           TEXT NOT NULL DEFAULT 'ETL',
    observacao       TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_ca_ordem CHECK (
        data_fim IS NULL OR data_fim > data_inicio
    ),
    CONSTRAINT chk_ca_nome_nao_vazio CHECK (btrim(nome) <> ''),
    -- Vocabulario FECHADO (aprovado 2026-08-20). Texto livre e como a
    -- coluna `Obs` chegou ao estado atual: 4 grafias para 3 conceitos,
    -- 2 delas desatualizadas.
    CONSTRAINT chk_ca_tipo CHECK (
        tipo IN ('AFASTAMENTO_MEDICO', 'LICENCA_MATERNIDADE',
                 'LICENCA_NAO_REMUNERADA', 'FERIAS')
    ),
    CONSTRAINT chk_ca_origem CHECK (origem IN ('ETL', 'MANUAL'))
);

COMMENT ON TABLE consultor_afastamento IS
    'Ledger de ausencia (SCD2) por pessoa. Responde "estava DISPONIVEL na '
    'competencia C" — ortogonal a consultor_vigencia (qual loja) e a '
    'supervisor_vigencia (qual papel). Sem loja_id de proposito: '
    'afastamento e da pessoa. CONTEM DADO PESSOAL SENSIVEL: sem grant '
    'para anon/authenticated, leitura so por RPC SECURITY DEFINER que '
    'devolve peso agregado.';

COMMENT ON COLUMN consultor_afastamento.data_fim IS
    'NULL = em curso. O RH nao precisa informar retorno: '
    'fn_fechar_afastamentos_por_producao fecha na data do primeiro '
    'contrato digitado apos data_inicio.';

DROP TRIGGER IF EXISTS trg_ca_updated_at ON consultor_afastamento;
CREATE TRIGGER trg_ca_updated_at
    BEFORE UPDATE ON consultor_afastamento
    FOR EACH ROW
    EXECUTE FUNCTION atualizar_updated_at();


-- ===========================================
-- 2. Invariantes
--
-- No maximo UM afastamento aberto por pessoa (diferente de 076/086,
-- que travam por pessoa+loja — aqui nao ha loja). Nada impede
-- afastamentos fechados sucessivos: ferias em marco e licenca em
-- agosto sao duas linhas.
-- ===========================================

CREATE UNIQUE INDEX IF NOT EXISTS uq_ca_pessoa_aberta
    ON consultor_afastamento (nome_normalizado)
    WHERE data_fim IS NULL;

CREATE INDEX IF NOT EXISTS idx_ca_pessoa_periodo
    ON consultor_afastamento (nome_normalizado, data_inicio, data_fim);


-- ===========================================
-- 3. fn_registrar_afastamento
--
-- Operacao atomica para o ETL e para correcao manual. Reabrir um
-- afastamento em curso com a mesma data e no-op; com data diferente,
-- corrige a data. Padrao da 077 (fn_aplicar_mudanca_supervisor).
-- ===========================================

CREATE OR REPLACE FUNCTION public.fn_registrar_afastamento(
    p_nome   TEXT,
    p_tipo   TEXT,
    p_inicio DATE,
    p_fim    DATE DEFAULT NULL,
    p_origem TEXT DEFAULT 'ETL'
)
RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_nn TEXT;
    v_id UUID;
BEGIN
    v_nn := upper(regexp_replace(btrim(coalesce(p_nome, '')),
                                 '[[:space:]]+', ' ', 'g'));
    IF v_nn = '' THEN
        RAISE EXCEPTION 'nome vazio';
    END IF;

    SELECT id INTO v_id
    FROM consultor_afastamento
    WHERE nome_normalizado = v_nn
      AND data_fim IS NULL;

    IF v_id IS NULL THEN
        INSERT INTO consultor_afastamento (nome, tipo, data_inicio, data_fim, origem)
        VALUES (btrim(p_nome), p_tipo, p_inicio, p_fim, p_origem);
        RETURN 'ABERTO';
    END IF;

    -- Ja existe janela aberta: fechar (se veio p_fim) ou corrigir inicio.
    UPDATE consultor_afastamento
    SET data_fim    = coalesce(p_fim, data_fim),
        data_inicio = p_inicio,
        tipo        = p_tipo,
        origem      = p_origem
    WHERE id = v_id;

    RETURN CASE WHEN p_fim IS NOT NULL THEN 'FECHADO' ELSE 'ATUALIZADO' END;
END;
$$;

COMMENT ON FUNCTION public.fn_registrar_afastamento(TEXT, TEXT, DATE, DATE, TEXT) IS
    'Abre, corrige ou fecha o afastamento em curso de uma pessoa. '
    'SECURITY DEFINER; EXECUTE so para service_role.';

REVOKE ALL ON FUNCTION public.fn_registrar_afastamento(TEXT, TEXT, DATE, DATE, TEXT)
    FROM PUBLIC;
REVOKE ALL ON FUNCTION public.fn_registrar_afastamento(TEXT, TEXT, DATE, DATE, TEXT)
    FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_registrar_afastamento(TEXT, TEXT, DATE, DATE, TEXT)
    TO service_role;


-- ===========================================
-- 4. fn_fechar_afastamentos_por_producao
--
-- O CORACAO DO DESENHO. Producao so pode FECHAR ausencia, nunca abrir:
-- um contrato digitado prova que a pessoa estava trabalhando naquele
-- dia; a falta de contratos nao prova nada.
--
-- Fecha cada janela aberta na data do PRIMEIRO contrato posterior ao
-- inicio dela. Idempotente: rodar de novo nao mexe no que ja fechou.
-- Chamar depois de cada carga do ETL de contratos.
--
-- Limite conhecido: se o backoffice digitar um contrato em nome de
-- quem esta afastado, a janela fecha indevidamente. O ETL reabre com
-- fn_registrar_afastamento — por isso ela aceita corrigir data_inicio
-- de janela existente.
-- ===========================================

CREATE OR REPLACE FUNCTION public.fn_fechar_afastamentos_por_producao(
    p_ate DATE DEFAULT current_date
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_fechados integer;
BEGIN
    WITH retorno AS (
        SELECT
            a.id,
            min(ct.data_cadastro::date) AS dia_retorno
        FROM consultor_afastamento a
        JOIN consultores cs
          ON upper(regexp_replace(btrim(coalesce(cs.nome, '')),
                                  '[[:space:]]+', ' ', 'g')) = a.nome_normalizado
        JOIN contratos ct
          ON ct.consultor_id = cs.id
        WHERE a.data_fim IS NULL
          AND ct.data_cadastro::date > a.data_inicio
          AND ct.data_cadastro::date <= p_ate
        GROUP BY a.id
    )
    UPDATE consultor_afastamento a
    SET data_fim = r.dia_retorno
    FROM retorno r
    WHERE a.id = r.id;

    GET DIAGNOSTICS v_fechados = ROW_COUNT;
    RETURN v_fechados;
END;
$$;

COMMENT ON FUNCTION public.fn_fechar_afastamentos_por_producao(DATE) IS
    'Fecha afastamentos em curso na data do primeiro contrato digitado '
    'depois do inicio. Producao FECHA ausencia, nunca abre. Rodar apos '
    'cada carga de contratos. SECURITY DEFINER; service_role.';

REVOKE ALL ON FUNCTION public.fn_fechar_afastamentos_por_producao(DATE) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.fn_fechar_afastamentos_por_producao(DATE)
    FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_fechar_afastamentos_por_producao(DATE)
    TO service_role;


-- ===========================================
-- 5. RLS — fail-closed, sem policy de leitura
--
-- Diferente da 076/086 de proposito (ver cabecalho). Sem GRANT para
-- anon/authenticated e sem policy: quem nao e service_role/owner nao
-- le nada. A 090 expoe apenas o peso agregado.
-- ===========================================

ALTER TABLE consultor_afastamento ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON consultor_afastamento FROM anon, authenticated;


-- ===========================================
-- 6. Seed: o unico caso com data confirmada
--
-- ERICA CRISTINA MARINS DA SILVA — supervisora de HELP ALCANTARA,
-- afastada, retorna como consultora de HELP ALCANTARA CARREFOUR em
-- 19/06/2026 (ver 088 para a linha do tempo completa).
--
-- Inicio 12/01/2026: data ESTIMADA, informada pelo usuario em
-- 2026-08-20 para deixar linear a sucessao da loja (MARIANA assume em
-- 13/01). A data exata nao existe no RH. Consistente com o dado: o
-- ultimo contrato dela e de 27/11/2025, e producao zero em dez/2025 e
-- jan/2026 nao contradiz presenca — ela era SUPERVISORA, e supervisor
-- nesta base produz de 1 a 22 contratos/mes.
--
-- Fim 19/06/2026: data informada, o retorno como consultora. Nao
-- depende da fn_fechar_* porque ela produziu zero entre o retorno e a
-- promocao — este e exatamente o caso que a producao NAO enxerga (o
-- primeiro contrato dela em CARREFOUR e de 20/07, cinco dias depois de
-- ja ter virado supervisora).
--
-- TIPO: registrado como AFASTAMENTO_MEDICO, seguindo a descricao do
-- usuario ("entrou em licenca medica"). A planilha do RH registra
-- 'Licenca maternidade' na Obs e 'Licenciado (a)' no STATUS. A
-- divergencia NAO afeta calculo nenhum (todo tipo pesa 0), mas precisa
-- ser reconciliada na fonte. Ver pendencia no bloco final.
-- ===========================================

INSERT INTO consultor_afastamento (nome, tipo, data_inicio, data_fim, origem, observacao)
SELECT
    'ERICA CRISTINA MARINS DA SILVA',
    'AFASTAMENTO_MEDICO',
    DATE '2026-01-12',
    DATE '2026-06-19',
    'MANUAL',
    'Inicio estimado (usuario, 2026-08-20) para linearizar a sucessao de '
    'HELP ALCANTARA; MARIANA assume em 13/01/2026. Tipo diverge da Obs do '
    'RH (Licenca maternidade) — reconciliar na fonte.'
WHERE NOT EXISTS (
    SELECT 1 FROM consultor_afastamento
    WHERE nome_normalizado = 'ERICA CRISTINA MARINS DA SILVA'
      AND data_inicio = DATE '2026-01-12'
);


-- ===========================================
-- Verificacao (apos executar)
-- ===========================================
-- 1) A tabela nasceu fechada para o portador da chave anon:
--
--    SELECT grantee, privilege_type
--    FROM information_schema.role_table_grants
--    WHERE table_name = 'consultor_afastamento';
--    -- Esperado: NENHUMA linha para anon nem authenticated.
--
-- 2) O seed entrou:
--
--    SELECT nome, tipo, data_inicio, data_fim, origem
--    FROM consultor_afastamento;
--    -- Esperado: 1 linha — ERICA, 2026-01-12 a 2026-06-19, MANUAL.
--
-- 3) O fechamento por producao e no-op agora (a unica janela ja esta
--    fechada) — prova que a funcao nao inventa fechamento:
--
--    SELECT fn_fechar_afastamentos_por_producao();
--    -- Esperado: 0.
--
-- 4) Teste do mecanismo, em transacao descartavel:
--
--    BEGIN;
--      SELECT fn_registrar_afastamento(
--          'ANNA CLARA CORREA DE SOUZA SCHARTH', 'AFASTAMENTO_MEDICO',
--          DATE '2026-01-01');                    -- abre em curso
--      SELECT count(*) FROM consultor_afastamento WHERE data_fim IS NULL;
--      -- Esperado: 1.
--      SELECT fn_fechar_afastamentos_por_producao();
--      -- Esperado: 0 — o ultimo contrato dela e de 18/08/2025, anterior
--      -- ao inicio da janela, entao nada prova retorno e ela CONTINUA
--      -- aberta. E a assimetria funcionando: silencio nao fecha nem
--      -- abre. (Nome usado so como fixture; ela esta desligada.)
--    ROLLBACK;
--
-- 5) Invariante: no maximo um afastamento aberto por pessoa:
--
--    SELECT nome_normalizado, count(*)
--    FROM consultor_afastamento WHERE data_fim IS NULL
--    GROUP BY 1 HAVING count(*) > 1;
--    -- Esperado: 0 linhas (garantido por uq_ca_pessoa_aberta).
--
--
-- PENDENCIAS ABERTAS APOS ESTA MIGRATION
-- ---------------------------------------
-- (a) ANNA CLARA CORREA DE SOUZA SCHARTH — desligada em 04/05/2026
--     (usuario, 2026-08-20). O BANCO ja a tem como 'Desligado (a)':
--     ela nao contamina denominador nenhum. Quem diz 'Ativo (a)' e a
--     copia local de HC_Colaboradores.xlsx, que esta desatualizada.
--     Pendencia REAL e outra: o vinculo dela em consultor_vigencia
--     fecha em 2025-09-01 (fim do mes do ultimo contrato, 18/08/2025),
--     mas ela seguiu na folha ate 04/05/2026. Sob R2 o numero so muda
--     se ela estava TRABALHANDO nesses 8 meses; se estava afastada,
--     peso 0 nos dois casos. Falta essa informacao.
-- (b) O ETL do angry-man ainda nao le a coluna Obs. Enquanto nao ler,
--     esta tabela so recebe entrada MANUAL.
-- (c) O tipo do afastamento da ERICA diverge entre a descricao do
--     usuario e a planilha do RH.
-- =====================================================
