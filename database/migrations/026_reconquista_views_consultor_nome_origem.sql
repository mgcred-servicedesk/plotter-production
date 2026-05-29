-- ============================================================
-- Migracao 026: Views do Reconquista — usar consultor_nome_origem
-- e expor bloqueio operacional em Indiferentes
--
-- Decisoes desta entrega:
--   1. Analytics foca em loja/regiao (o lead pertence a loja).
--      v_reconquista_por_consultor deixa de ser usada e e
--      removida — simplifica manutencao.
--   2. v_reconquista_ultimo passa a expor consultor_nome_origem
--      (snapshot bruto do arquivo) alem do consultor_id.
--   3. v_reconquista_indiferentes:
--      - Nome do consultor via COALESCE(con.nome,
--        u.consultor_nome_origem, '(Sem Consultor)') — preserva
--        rastreabilidade quando FK nao casa (migracao 025).
--      - Expoe mot_ipd_operar do ULTIMO snapshot, para que o
--        gestor distinga indiferenca real de bloqueio
--        operacional (ex: contrato em DNA, banco recusou, etc).
--
-- Depende de: 024_reconquista_views_sucessora.sql,
--             025_reconquista_consultor_nome_origem.sql.
-- Executar no Supabase SQL Editor.
-- ============================================================

DROP VIEW IF EXISTS v_reconquista_indiferentes;
DROP VIEW IF EXISTS v_reconquista_por_consultor;
DROP VIEW IF EXISTS v_reconquista_por_loja;
DROP VIEW IF EXISTS v_reconquista_ultimo;


-- ============================================================
-- v_reconquista_ultimo
--
-- Ultimo snapshot por cliente (cod_ade) por maciça. Resolve
-- loja_id via sucessora. Expoe consultor_nome_origem para
-- COALESCE em views derivadas.
-- ============================================================

CREATE VIEW v_reconquista_ultimo
    WITH (security_invoker = on)
AS
SELECT DISTINCT ON (s.macica_id, s.cod_ade)
    s.macica_id,
    s.cod_ade,
    s.dat_envio                                  AS dat_ultimo_envio,
    COALESCE(l_orig.sucessora_id, s.loja_id)     AS loja_id,
    s.consultor_id,
    s.consultor_nome_origem,
    s.subproduto,
    s.saldo_contabil,
    s.dias_atraso,
    s.faixa_atraso,
    s.mot_ipd_operar,
    s.flag_cnc,
    s.flag_consignado,
    s.flag_cartao,
    s.flag_dna,
    s.flag_reconquista,
    s.flag_rl
FROM reconquista_snapshot s
LEFT JOIN lojas l_orig ON l_orig.id = s.loja_id
ORDER BY s.macica_id, s.cod_ade, s.dat_envio DESC;

COMMENT ON VIEW v_reconquista_ultimo IS
    'Ultimo snapshot por cliente (cod_ade) por maciça. '
    'loja_id resolvido via sucessora. consultor_nome_origem '
    'exposto para fallback de nome quando FK nao casa.';


-- ============================================================
-- v_reconquista_por_loja
--
-- KPIs agregados por loja. Inalterada em relacao a 024 — o
-- DROP/CREATE existe apenas pela dependencia em v_reconquista_ultimo.
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
    COALESCE(l.nome, '(Nao Identificado)')                          AS loja,
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
WHERE l.ativo = true OR l.id IS NULL
GROUP BY
    s.macica_id, m.codigo, m.descricao, m.meta_retencao,
    l.id, l.nome, r.nome;

COMMENT ON VIEW v_reconquista_por_loja IS
    'KPIs de reconquista por loja. loja_id resolvido via '
    'sucessora em v_reconquista_ultimo.';


-- ============================================================
-- v_reconquista_indiferentes
--
-- Clientes com 3+ aparicoes na mesma maciça sem conversao.
-- Granularidade por cod_ade. Expoe:
--   - consultor com COALESCE(FK, nome_origem, '(Sem Consultor)')
--   - mot_ipd_operar do ultimo snapshot (bloqueio operacional)
--
-- Implementacao: cruza v_reconquista_ultimo (campos do estado
-- mais recente: loja, consultor, mot_ipd_operar) com agregados
-- de reconquista_snapshot (aparicoes, saldo medio, datas).
-- ============================================================

CREATE VIEW v_reconquista_indiferentes
    WITH (security_invoker = on)
AS
SELECT
    u.macica_id,
    m.codigo                                                        AS macica,
    u.cod_ade,
    COALESCE(l.nome, '(Nao Identificado)')                          AS loja,
    r.nome                                                          AS regiao,
    COALESCE(con.nome, u.consultor_nome_origem, '(Sem Consultor)')  AS consultor,
    u.mot_ipd_operar,
    agg.aparicoes,
    agg.saldo_medio,
    agg.dias_atraso_medio,
    agg.primeira_aparicao,
    agg.ultima_aparicao
FROM v_reconquista_ultimo u
JOIN macicas m                ON m.id = u.macica_id
LEFT JOIN lojas l             ON l.id = u.loja_id
LEFT JOIN regioes r           ON r.id = l.regiao_id
LEFT JOIN consultores con     ON con.id = u.consultor_id
JOIN LATERAL (
    SELECT
        COUNT(DISTINCT s.dat_envio)                  AS aparicoes,
        ROUND(AVG(s.saldo_contabil), 2)              AS saldo_medio,
        ROUND(AVG(s.dias_atraso), 0)                 AS dias_atraso_medio,
        MIN(s.dat_envio)                             AS primeira_aparicao,
        MAX(s.dat_envio)                             AS ultima_aparicao,
        MAX(s.flag_reconquista)                      AS max_flag
    FROM reconquista_snapshot s
    WHERE s.macica_id = u.macica_id
      AND s.cod_ade   = u.cod_ade
) agg ON true
WHERE (l.ativo = true OR l.id IS NULL)
  AND agg.aparicoes >= 3
  AND agg.max_flag  = 0;

COMMENT ON VIEW v_reconquista_indiferentes IS
    'Clientes com 3+ aparicoes na mesma maciça que nunca '
    'converteram. Nome do consultor via COALESCE com '
    'consultor_nome_origem. Expoe mot_ipd_operar do ultimo '
    'snapshot para distinguir indiferenca de bloqueio '
    'operacional.';
