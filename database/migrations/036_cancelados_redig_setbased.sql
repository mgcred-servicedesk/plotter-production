-- =====================================================
-- Migracao 036: redig set-based em obter_cancelados_classificados
--
-- Problema: a migration 034 ja trocou as 6 subconsultas EXISTS
-- de recuperacao por UM JOIN agregado (CTE `matches`, set-based)
-- e isso resolveu a maior parte do custo. Mas o CTE `redig`
-- continuou como um EXISTS CORRELACIONADO self-join sobre `canc`.
-- O comentario da 034 assumiu "canc e pequeno", porem a medicao
-- real no banco (periodo 6/2026) mostrou ~1.982 cancelados na
-- janela de 30 dias. Como a chave de match e `nome_norm`
-- (upper(trim(regexp_replace(...)))), calculada em runtime, nao
-- ha indice usavel: o EXISTS vira um nested-loop |canc| x |canc|
-- ~= 1.982^2 ~= 4M comparacoes. Somado ao custo de base, estoura
-- o statement_timeout do Supabase (erro 57014, timeout ~8,3s),
-- enquanto a RPC simples sem matching roda em ~3,0s.
--
-- Correcao: reescrever `redig` no MESMO padrao do CTE `matches`
-- da 034 — LEFT JOIN agregado set-based com bool_or — eliminando
-- o O(n^2). A janela de redigitacao (mesmo nome+categoria, ate 7
-- dias depois) e percorrida uma unica vez por linha, sob hash/
-- merge join em vez de nested-loop por linha.
--
-- Equivalencia semantica EXATA com a 034:
--   * is_redig(a) = (a.nome_norm <> '') AND existe b in canc com
--       b.nome_norm        = a.nome_norm
--       b.categoria_codigo = a.categoria_codigo
--       b.data_cadastro    > a.data_cadastro   (estrita, NAO >=)
--       b.data_cadastro   <= a.data_cadastro + INTERVAL '7 days'
--   * O LEFT JOIN preserva UMA linha por cancelado (inclusive os
--     de nome vazio): a guarda `a.nome_norm <> ''` esta na clausula
--     de juncao, entao linhas de nome vazio nao casam nenhum `b`
--     (bool_or -> false) e o conjunto resultante de `redig` continua
--     1:1 com `canc`, exatamente como o `FROM canc a` da 034. O
--     conjunto `(a.nome_norm <> '')` e mantido explicito no calculo
--     de is_redig para paridade literal com a 034.
--   * A desigualdade ESTRITA `>` (e nao `>=`) e preservada: um
--     cancelado nunca redigita a si mesmo nem casa empate de data.
--
-- canc, paga, matches, o SELECT final, a logica de classificacao
-- e as 3 flags (recuperada_outro / recuperada_outra_loja /
-- recuperada_outra_regiao) ficam IDENTICOS a 034 — so a FORMA do
-- CTE `redig` muda. Mesma assinatura e colunas de retorno, logo
-- CREATE OR REPLACE basta.
--
-- Rede de seguranca de timeout: o custo de base sobre ~2k
-- cancelados e real e irreduzivel, entao a funcao recebe
-- `SET statement_timeout = '15000'` na propria definicao (junto
-- de `SET search_path = ''`), dando folga sobre os ~3-8s
-- observados sem afrouxar o timeout global do projeto.
--
-- Migration 034 e imutavel e nao foi editada; esta a substitui
-- via CREATE OR REPLACE.
--
-- Executar no Supabase SQL Editor.
-- =====================================================

CREATE OR REPLACE FUNCTION obter_cancelados_classificados(
    p_mes INTEGER,
    p_ano INTEGER
)
RETURNS TABLE (
    id                        UUID,
    contrato_id               BIGINT,
    valor                     NUMERIC(15,2),
    prazo                     TEXT,
    valor_parcela             NUMERIC(15,2),
    tipo_operacao             TEXT,
    data_cadastro             DATE,
    status_banco              TEXT,
    data_status_banco         DATE,
    status_pagamento_cliente  TEXT,
    data_status_pagamento     DATE,
    banco                     TEXT,
    convenio                  TEXT,
    num_proposta              TEXT,
    sub_status_banco          TEXT,
    loja                      TEXT,
    regiao                    TEXT,
    consultor                 TEXT,
    produto                   TEXT,
    tipo_produto              TEXT,
    subtipo                   TEXT,
    categoria_codigo          TEXT,
    grupo_dashboard           TEXT,
    conta_valor               BOOLEAN,
    classificacao             TEXT,
    recuperada_outro          BOOLEAN,
    recuperada_outra_loja     BOOLEAN,
    recuperada_outra_regiao   BOOLEAN
)
LANGUAGE plpgsql
STABLE
SET search_path = ''
SET statement_timeout = '15000'
AS $$
DECLARE
    v_data_ref    DATE;
    v_data_inicio DATE;
    v_hoje        DATE := current_date;
BEGIN
    -- Data de referencia: hoje se periodo vigente,
    -- senao ultimo dia do mes selecionado (igual a RPC 003).
    IF p_mes = EXTRACT(MONTH FROM v_hoje)::INTEGER
       AND p_ano = EXTRACT(YEAR FROM v_hoje)::INTEGER
    THEN
        v_data_ref := v_hoje;
    ELSE
        v_data_ref := (make_date(p_ano, p_mes, 1)
                       + INTERVAL '1 month'
                       - INTERVAL '1 day')::DATE;
    END IF;

    v_data_inicio := v_data_ref - INTERVAL '30 days';

    RETURN QUERY
    WITH canc AS (
        -- Cancelados da janela; puxa o nome do base contratos
        -- apenas para o matching (nao sera retornado).
        SELECT
            v.id, v.contrato_id, v.valor, v.prazo, v.valor_parcela,
            v.tipo_operacao, v.data_cadastro, v.status_banco,
            v.data_status_banco, v.status_pagamento_cliente,
            v.data_status_pagamento, v.banco, v.convenio, v.num_proposta,
            v.sub_status_banco, v.loja, v.regiao, v.consultor, v.produto,
            v.tipo_produto, v.subtipo, v.categoria_codigo, v.grupo_dashboard,
            v.conta_valor,
            upper(trim(regexp_replace(
                coalesce(c.cliente, ''), '\s+', ' ', 'g'
            ))) AS nome_norm
        FROM public.v_contratos_cancelados v
        JOIN public.contratos c ON c.id = v.id
        WHERE v.data_cadastro >= v_data_inicio
          AND v.data_cadastro <= v_data_ref
    ),
    paga AS (
        -- Propostas pagas (mesmo nome+categoria) usadas para
        -- detectar recuperacao. Traz consultor/loja/regiao para
        -- distinguir recuperacao propria x por outro consultor,
        -- outra loja, outra regiao. Filtro de data limita o scan.
        SELECT
            upper(trim(regexp_replace(
                coalesce(c.cliente, ''), '\s+', ' ', 'g'
            ))) AS nome_norm,
            cp.codigo AS categoria_codigo,
            con.nome  AS consultor,
            l.nome    AS loja,
            r.nome    AS regiao,
            c.data_cadastro
        FROM public.contratos c
        JOIN public.produtos p            ON p.id  = c.produto_id
        JOIN public.categorias_produto cp ON cp.id = p.categoria_id
        LEFT JOIN public.consultores con  ON con.id = c.consultor_id
        LEFT JOIN public.lojas l          ON l.id  = c.loja_id
        LEFT JOIN public.regioes r        ON r.id  = l.regiao_id
        WHERE c.status_pagamento_cliente = 'PAGO AO CLIENTE'
          AND c.data_cadastro >= v_data_inicio
          AND c.data_cadastro <= v_data_ref + INTERVAL '7 days'
    ),
    redig AS (
        -- Superada por cancelamento posterior em <=7d (self-join
        -- sobre canc). Reescrito da forma EXISTS correlacionada da
        -- 034 (nested-loop O(|canc|^2)) para LEFT JOIN agregado
        -- set-based, mesmo padrao do CTE `matches`. A guarda de
        -- nome vazio fica na juncao: linhas com nome_norm = ''
        -- nao casam nenhum b -> bool_or = false, e o LEFT JOIN
        -- mantem UMA linha por cancelado (conjunto 1:1 com canc,
        -- como o `FROM canc a` da 034). Desigualdade ESTRITA `>`
        -- preservada: um cancelado nunca redigita a si mesmo.
        SELECT
            a.id,
            (a.nome_norm <> '' AND bool_or(b.id IS NOT NULL)) AS is_redig
        FROM canc a
        LEFT JOIN canc b
          ON a.nome_norm <> ''
         AND b.nome_norm        = a.nome_norm
         AND b.categoria_codigo = a.categoria_codigo
         AND b.data_cadastro    > a.data_cadastro
         AND b.data_cadastro   <= a.data_cadastro + INTERVAL '7 days'
        GROUP BY a.id, a.nome_norm
    ),
    matches AS (
        -- Uma unica passagem pela janela de pagas por cancelado:
        -- todas as flags de recuperacao derivam deste JOIN agregado,
        -- substituindo as 6 subconsultas EXISTS da migration 033.
        SELECT
            a.id,
            bool_or(g.consultor IS NOT DISTINCT FROM a.consultor)
                AS paga_propria,
            bool_or(g.consultor IS DISTINCT FROM a.consultor)
                AS paga_outro,
            bool_or(g.loja IS NOT DISTINCT FROM a.loja)
                AS paga_mesma_loja,
            bool_or(g.loja IS DISTINCT FROM a.loja)
                AS paga_outra_loja,
            bool_or(g.regiao IS NOT DISTINCT FROM a.regiao)
                AS paga_mesma_regiao,
            bool_or(g.regiao IS DISTINCT FROM a.regiao)
                AS paga_outra_regiao
        FROM canc a
        JOIN paga g
          ON g.nome_norm        = a.nome_norm
         AND g.categoria_codigo = a.categoria_codigo
         AND g.data_cadastro   >= a.data_cadastro
         AND g.data_cadastro   <= a.data_cadastro + INTERVAL '7 days'
        WHERE a.nome_norm <> ''
        GROUP BY a.id
    )
    SELECT
        f.id, f.contrato_id, f.valor, f.prazo, f.valor_parcela,
        f.tipo_operacao, f.data_cadastro, f.status_banco,
        f.data_status_banco, f.status_pagamento_cliente,
        f.data_status_pagamento, f.banco, f.convenio, f.num_proposta,
        f.sub_status_banco, f.loja, f.regiao, f.consultor, f.produto,
        f.tipo_produto, f.subtipo, f.categoria_codigo, f.grupo_dashboard,
        f.conta_valor,
        CASE
            WHEN rd.is_redig THEN 'redigitada'
            WHEN COALESCE(m.paga_propria, false)
              OR COALESCE(m.paga_outro, false) THEN 'recuperada'
            ELSE 'liquido'
        END AS classificacao,
        -- Oportunidade perdida por nivel: representante (nao
        -- redigitada) que NAO foi recuperado no proprio nivel, mas
        -- foi pago em OUTRO consultor / OUTRA loja / OUTRA regiao.
        (NOT rd.is_redig
            AND NOT COALESCE(m.paga_propria, false)
            AND COALESCE(m.paga_outro, false))
            AS recuperada_outro,
        (NOT rd.is_redig
            AND NOT COALESCE(m.paga_mesma_loja, false)
            AND COALESCE(m.paga_outra_loja, false))
            AS recuperada_outra_loja,
        (NOT rd.is_redig
            AND NOT COALESCE(m.paga_mesma_regiao, false)
            AND COALESCE(m.paga_outra_regiao, false))
            AS recuperada_outra_regiao
    FROM canc f
    JOIN redig rd        ON rd.id = f.id
    LEFT JOIN matches m  ON m.id  = f.id;
END;
$$;

COMMENT ON FUNCTION obter_cancelados_classificados(INTEGER, INTEGER) IS
    'Cancelados dos ultimos 30 dias classificados em '
    'redigitada / recuperada / liquido (matching por nome+categoria '
    'em janela de 7 dias). Marca tambem oportunidade perdida por nivel: '
    'recuperada_outro / recuperada_outra_loja / recuperada_outra_regiao '
    '(venda capturada por outro consultor / loja / regiao). '
    'O nome do cliente nao e exposto: so as flags saem no resultado. '
    'Migration 036: redig reescrito de EXISTS correlacionado para '
    'JOIN+bool_or set-based (elimina O(n^2) com canc ~= 2k); '
    'statement_timeout local de 15s como rede de seguranca.';

-- Acesso de execucao para os papeis do app. O dashboard le em
-- escopo completo e filtra por perfil client-side (aplicar_rls);
-- a classificacao e global de proposito (detecta cross-nivel).
GRANT EXECUTE ON FUNCTION obter_cancelados_classificados(INTEGER, INTEGER)
    TO anon, authenticated;
