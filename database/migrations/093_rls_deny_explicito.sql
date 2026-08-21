-- =====================================================
-- Migracao 093: RLS deny explicito em consultor_afastamento
--               e reconquista (lint 0008_rls_enabled_no_policy)
--
-- NOTA DE NUMERACAO: o "093" citado no cabecalho da 091 e nos
-- follow-ups de progress/ e um PASSO Python (carregar_consultores_ativos
-- com coluna PESO) — nao gera arquivo .sql. Este numero estava livre em
-- database/migrations/ e nao ha conflito.
--
--
-- O QUE O AVISO E, E O QUE ELE NAO E
-- -----------------------------------
-- O advisor do Supabase reporta, em nivel INFO:
--
--   Table `public.consultor_afastamento` has RLS enabled, but no
--   policies exist
--   Table `public.reconquista` has RLS enabled, but no policies exist
--
-- Isso NAO e vulnerabilidade. RLS ligado sem policy nenhuma e o estado
-- mais restritivo que existe: nega tudo para qualquer role que nao faca
-- bypass. O linter avisa porque a causa COMUM do padrao e esquecimento
-- — alguem liga o RLS, esquece a policy, e a tabela fica muda para a
-- aplicacao sem ninguem entender por que.
--
-- Aqui os dois casos sao de naturezas opostas, e esta migration trata
-- cada um pelo que ele e.
--
--
-- CASO 1 — consultor_afastamento: intencional desde a 089
-- --------------------------------------------------------
-- A 089 liga RLS e revoga anon/authenticated de proposito. O cabecalho
-- dela explica: 076 e 086 liberam SELECT porque guardam ESTRUTURA
-- ORGANIZACIONAL; esta guarda MOTIVO DE AFASTAMENTO, que e dado pessoal
-- sensivel (saude, gravidez). Com UMA chave Supabase compartilhada, o
-- que anon le qualquer portador da chave le. A 090 expoe so o peso
-- agregado — nunca o motivo.
--
-- Nada muda no comportamento. O que esta migration acrescenta e a
-- INTENCAO no catalogo: uma policy nomeada USING (false) diz "fechado
-- de proposito", que o par (RLS ligado, zero policies) nao consegue
-- dizer nem para o linter nem para quem ler o schema daqui a um ano.
--
--
-- CASO 2 — reconquista: drift entre banco e migrations
-- -----------------------------------------------------
-- Este e o achado que motiva o arquivo. A 028 cria a tabela
-- `reconquista` com ZERO linhas de RLS ou GRANT, e nenhuma migration
-- posterior liga RLS nela. Mas o banco tem RLS ligado — ou seja, foi
-- ligado FORA do fluxo de migrations (botao do Studio). Consequencia:
-- aplicar database/migrations/ do zero produz um banco diferente do de
-- producao, que e exatamente a garantia que o diretorio existe para dar.
--
-- Efeito silencioso number 2: a 030 declara
-- `v_reconquista WITH (security_invoker = on)` justamente para
-- "respeitar as policies de quem consulta". Sem policy na tabela base,
-- essa view devolve ZERO LINHAS para qualquer role sem bypass — o
-- design declarado no cabecalho da 030 e hoje letra morta. Ninguem
-- percebeu porque a chave do .env e service_role (BYPASSRLS) e o recorte
-- real por perfil e client-side (_filtrar_rls_reconquista, loaders.py).
--
-- POR QUE FECHAR, E NAO ABRIR (decisao do usuario em 2026-08-21)
-- --------------------------------------------------------------
-- Abrir com USING (true) + GRANT, no padrao 076/086, faria a
-- security_invoker da view voltar a funcionar. Foi descartado: 076/086
-- guardam estrutura organizacional, e `reconquista` guarda CARTEIRA DE
-- CLIENTE — co_adesao, saldo_contabil, link_aceite. Enquanto a chave for
-- unica e compartilhada, liberar anon e liberar para todo portador.
--
-- Replicar pol_contratos_select (011) por perfil tambem foi descartado
-- por ora: custo alto e beneficio zero enquanto todo acesso for
-- service_role, que ignora policy. Fica registrado como o caminho a
-- seguir SE o projeto sair da chave unica — nesse dia, esta policy deny
-- e o ponto exato a substituir.
--
--
-- O QUE MUDA NA PRATICA
-- ----------------------
-- Nada, para o dashboard: `service_role` tem BYPASSRLS e nunca avalia
-- policy. O que muda e (a) os dois avisos do advisor somem, (b) o
-- estado do banco passa a ser reproduzivel a partir das migrations, e
-- (c) a intencao fica escrita onde o proximo leitor procura.
--
-- Depende de: 028 (reconquista), 089 (consultor_afastamento).
-- Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- 0. Guarda — as duas tabelas precisam existir
-- ===========================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'reconquista'
    ) THEN
        RAISE EXCEPTION
            'Tabela public.reconquista ausente. Aplique '
            '028_reconquista_v2_tabela.sql antes desta.';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'consultor_afastamento'
    ) THEN
        RAISE EXCEPTION
            'Tabela public.consultor_afastamento ausente. Aplique '
            '089_consultor_afastamento.sql antes desta.';
    END IF;
END;
$$;


-- ===========================================
-- 1. consultor_afastamento — formaliza a 089
--
-- ENABLE e REVOKE sao idempotentes e ja vieram da 089; repetidos aqui
-- para que este arquivo descreva o estado final sozinho.
-- ===========================================

ALTER TABLE public.consultor_afastamento ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS pol_consultor_afastamento_deny ON public.consultor_afastamento;

CREATE POLICY pol_consultor_afastamento_deny
    ON public.consultor_afastamento
    FOR ALL
    TO anon, authenticated
    USING (false)
    WITH CHECK (false);

COMMENT ON POLICY pol_consultor_afastamento_deny ON public.consultor_afastamento IS
    'Deny explicito. A tabela guarda motivo de afastamento (dado pessoal '
    'sensivel) e o projeto usa uma chave Supabase compartilhada — o que '
    'anon le, qualquer portador da chave le. Acesso apenas por '
    'service_role; o peso agregado sai pela fn_afastamentos (090). '
    'Fechado de PROPOSITO, nao por policy esquecida.';

REVOKE ALL ON public.consultor_afastamento FROM anon, authenticated;


-- ===========================================
-- 2. reconquista — registra em migration o RLS
--    que hoje so existe no banco
-- ===========================================

ALTER TABLE public.reconquista ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS pol_reconquista_deny ON public.reconquista;

CREATE POLICY pol_reconquista_deny
    ON public.reconquista
    FOR ALL
    TO anon, authenticated
    USING (false)
    WITH CHECK (false);

COMMENT ON POLICY pol_reconquista_deny ON public.reconquista IS
    'Deny explicito. Carteira de cliente (co_adesao, saldo_contabil, '
    'link_aceite) — nao estrutura organizacional, logo NAO segue o padrao '
    'aberto de 076/086. Todo acesso e por service_role (BYPASSRLS); o '
    'recorte por perfil e client-side (_filtrar_rls_reconquista). Se o '
    'projeto sair da chave unica, esta policy e o ponto a substituir por '
    'uma no padrao pol_contratos_select (011).';

-- A 028 nunca revogou os grants default do schema public; se anon ainda
-- os carrega, some com eles. Nao afeta v_reconquista: a view e
-- security_invoker e quem a consulta e service_role, com grants proprios.
REVOKE ALL ON public.reconquista FROM anon, authenticated;


-- =====================================================
-- VALIDACAO — rodar apos aplicar
--
-- 1) Os dois avisos do advisor devem sumir. Confirmacao direta no
--    catalogo (esperado: 1 linha por tabela, com a policy nomeada):
--
--    SELECT c.relname, c.relrowsecurity AS rls_ligado, p.polname
--    FROM pg_class c
--    LEFT JOIN pg_policy p ON p.polrelid = c.oid
--    WHERE c.relname IN ('reconquista', 'consultor_afastamento');
--
-- 2) Nenhum grant residual para anon/authenticated (esperado: 0 linhas):
--
--    SELECT grantee, table_name, privilege_type
--    FROM information_schema.role_table_grants
--    WHERE table_name IN ('reconquista', 'consultor_afastamento')
--      AND grantee IN ('anon', 'authenticated');
--
-- 3) O dashboard nao pode mudar. service_role continua lendo tudo
--    (esperado: a mesma contagem de antes da migration):
--
--    SELECT count(*) FROM public.reconquista;
--    SELECT count(*) FROM public.v_reconquista;
--
-- 4) Sanidade do deny — simulando anon (esperado: erro de permissao,
--    NAO um resultado vazio; o REVOKE barra antes da policy):
--
--    SET LOCAL ROLE anon;
--    SELECT count(*) FROM public.reconquista;  -- permission denied
--    RESET ROLE;
-- =====================================================
