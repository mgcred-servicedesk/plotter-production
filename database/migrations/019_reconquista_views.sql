-- ============================================================
-- Migracao 019: Views e funcao de exibicao do Reconquista
--
-- Depende de: 018_reconquista_tables.sql
--
-- Adiciona:
--   - fn_macica_ativa(p_mes, p_ano)
--   - v_reconquista_ultimo          (DISTINCT ON do snapshot mais recente)
--   - v_reconquista_por_loja        (KPIs por loja)
--   - v_reconquista_por_consultor   (KPIs por consultor)
--   - v_reconquista_indiferentes    (3+ aparicoes sem conversao)
--
-- Todas as views usam security_invoker = on para herdar o
-- RLS de reconquista_snapshot definido na migracao 018.
--
-- Executar no Supabase SQL Editor.
-- ============================================================


-- ============================================================
-- fn_macica_ativa
--
-- Retorna a maciça a ser exibida para um dado mês/ano.
-- Regra: a maciça muda aprox no dia 20. Quando o mês solicitado
-- nao tem maciça propria, exibe a anterior mais recente.
-- ============================================================

CREATE OR REPLACE FUNCTION fn_macica_ativa(
    p_mes INTEGER,
    p_ano INTEGER
)
RETURNS TABLE (
    id                 UUID,
    codigo             TEXT,
    descricao          TEXT,
    dat_primeiro_envio DATE,
    dat_ultimo_envio   DATE,
    meta_retencao      NUMERIC
)
LANGUAGE SQL
STABLE
SET search_path = ''
AS $$
    SELECT
        m.id,
        m.codigo,
        m.descricao,
        m.dat_primeiro_envio,
        m.dat_ultimo_envio,
        m.meta_retencao
    FROM public.macicas m
    WHERE m.ativo = true
      AND m.dat_primeiro_envio <=
          (make_date(p_ano, p_mes, 1) + INTERVAL '1 month - 1 day')::date
    ORDER BY m.dat_primeiro_envio DESC
    LIMIT 1;
$$;

COMMENT ON FUNCTION fn_macica_ativa(INTEGER, INTEGER) IS
    'Retorna a maciça de reconquista a ser exibida para o mês/ano '
    'solicitado. Se não há maciça para o mês corrente, retorna a '
    'última disponível (fallback para mês anterior).';


-- ============================================================
-- v_reconquista_ultimo
--
-- Ultimo snapshot por cliente (cod_ade) por maciça.
-- Base para os KPIs do dashboard.
-- ============================================================

DROP VIEW IF EXISTS v_reconquista_indiferentes;
DROP VIEW IF EXISTS v_reconquista_por_consultor;
DROP VIEW IF EXISTS v_reconquista_por_loja;
DROP VIEW IF EXISTS v_reconquista_ultimo;

CREATE VIEW v_reconquista_ultimo
    WITH (security_invoker = on)
AS
SELECT DISTINCT ON (macica_id, cod_ade)
    macica_id,
    cod_ade,
    dat_envio AS dat_ultimo_envio,
    loja_id,
    consultor_id,
    subproduto,
    saldo_contabil,
    dias_atraso,
    faixa_atraso,
    mot_ipd_operar,
    flag_cnc,
    flag_consignado,
    flag_cartao,
    flag_dna,
    flag_reconquista,
    flag_rl
FROM reconquista_snapshot
ORDER BY macica_id, cod_ade, dat_envio DESC;

COMMENT ON VIEW v_reconquista_ultimo IS
    'Ultimo snapshot por cliente (cod_ade) por maciça. '
    'Representa o estado mais atual de cada cliente na campanha.';


-- ============================================================
-- v_reconquista_por_loja
-- KPIs agregados por loja, baseado em v_reconquista_ultimo.
-- ============================================================

CREATE VIEW v_reconquista_por_loja
    WITH (security_invoker = on)
AS
SELECT
    s.macica_id,
    m.codigo                                                        AS macica,
    m.descricao,
    m.meta_retencao,
    l.id                                                            AS loja_id,
    l.nome                                                          AS loja,
    r.nome                                                          AS regiao,
    COUNT(*)                                                        AS total_clientes,
    SUM(s.flag_reconquista)                                         AS reconquistados,
    ROUND(
        SUM(s.flag_reconquista) * 100.0 / NULLIF(COUNT(*), 0), 1
    )                                                               AS taxa_pct,
    ROUND(
        SUM(s.flag_reconquista) * 100.0 / NULLIF(COUNT(*), 0)
        - m.meta_retencao, 1
    )                                                               AS gap_pp,
    ROUND(AVG(s.saldo_contabil), 2)                                 AS saldo_medio,
    ROUND(AVG(s.dias_atraso), 0)                                    AS dias_atraso_medio
FROM v_reconquista_ultimo s
JOIN macicas m            ON m.id = s.macica_id
LEFT JOIN lojas l         ON l.id = s.loja_id
LEFT JOIN regioes r       ON r.id = l.regiao_id
GROUP BY
    s.macica_id, m.codigo, m.descricao, m.meta_retencao,
    l.id, l.nome, r.nome;

COMMENT ON VIEW v_reconquista_por_loja IS
    'KPIs de reconquista por loja. Baseado no ultimo snapshot '
    'de cada cliente por maciça.';


-- ============================================================
-- v_reconquista_por_consultor
-- KPIs agregados por consultor.
-- ============================================================

CREATE VIEW v_reconquista_por_consultor
    WITH (security_invoker = on)
AS
SELECT
    s.macica_id,
    m.codigo                                                        AS macica,
    m.meta_retencao,
    l.nome                                                          AS loja,
    r.nome                                                          AS regiao,
    con.nome                                                        AS consultor,
    COUNT(*)                                                        AS total_clientes,
    SUM(s.flag_reconquista)                                         AS reconquistados,
    ROUND(
        SUM(s.flag_reconquista) * 100.0 / NULLIF(COUNT(*), 0), 1
    )                                                               AS taxa_pct,
    ROUND(
        SUM(s.flag_reconquista) * 100.0 / NULLIF(COUNT(*), 0)
        - m.meta_retencao, 1
    )                                                               AS gap_pp
FROM v_reconquista_ultimo s
JOIN macicas m               ON m.id = s.macica_id
LEFT JOIN consultores con    ON con.id = s.consultor_id
LEFT JOIN lojas l            ON l.id = con.loja_id
LEFT JOIN regioes r          ON r.id = l.regiao_id
GROUP BY
    s.macica_id, m.codigo, m.meta_retencao,
    l.nome, r.nome, con.nome;

COMMENT ON VIEW v_reconquista_por_consultor IS
    'KPIs de reconquista por consultor. Baseado no ultimo snapshot '
    'de cada cliente por maciça.';


-- ============================================================
-- v_reconquista_indiferentes
-- Clientes com 3+ aparicoes na mesma maciça sem conversao.
-- ============================================================

CREATE VIEW v_reconquista_indiferentes
    WITH (security_invoker = on)
AS
SELECT
    s.macica_id,
    m.codigo                                                        AS macica,
    s.cod_ade,
    l.nome                                                          AS loja,
    r.nome                                                          AS regiao,
    con.nome                                                        AS consultor,
    COUNT(DISTINCT s.dat_envio)                                     AS aparicoes,
    ROUND(AVG(s.saldo_contabil), 2)                                 AS saldo_medio,
    ROUND(AVG(s.dias_atraso), 0)                                    AS dias_atraso_medio,
    MIN(s.dat_envio)                                                AS primeira_aparicao,
    MAX(s.dat_envio)                                                AS ultima_aparicao
FROM reconquista_snapshot s
JOIN macicas m              ON m.id = s.macica_id
LEFT JOIN lojas l           ON l.id = s.loja_id
LEFT JOIN regioes r         ON r.id = l.regiao_id
LEFT JOIN consultores con   ON con.id = s.consultor_id
GROUP BY s.macica_id, m.codigo, s.cod_ade, l.nome, r.nome, con.nome
HAVING COUNT(DISTINCT s.dat_envio) >= 3
   AND MAX(s.flag_reconquista) = 0;

COMMENT ON VIEW v_reconquista_indiferentes IS
    'Clientes que aparecem 3+ vezes na mesma maciça sem nunca '
    'converterem. Distinguir indiferenca de bloqueio operacional '
    '(mot_ipd_operar preenchido).';
