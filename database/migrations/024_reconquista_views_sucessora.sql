-- ============================================================
-- Migracao 024: Reconquista — views resolvem sucessora e
-- filtram lojas inativas
--
-- Aplica a estrategia (b) acordada:
--   - v_reconquista_ultimo resolve `loja_id` via
--     `COALESCE(l.sucessora_id, l.id)`. Snapshots de uma
--     loja PDV cuja sucessao foi cadastrada aparecem
--     automaticamente sob a HELP herdeira, sem necessidade
--     de re-importar arquivos antigos.
--   - Views agregadas por loja/consultor:
--     * LEFT JOIN com lojas
--     * filtro defensivo `WHERE l.ativo = true OR l.id IS NULL`
--       (snapshots sem loja viram bucket "(Nao Identificado)";
--        lojas inativas sem sucessora ficam de fora)
--     * COALESCE(l.nome, '(Nao Identificado)') no label.
--
-- Depende de: 019_reconquista_views.sql, 021_lojas_sucessao.sql.
-- Executar no Supabase SQL Editor.
-- ============================================================

DROP VIEW IF EXISTS v_reconquista_indiferentes;
DROP VIEW IF EXISTS v_reconquista_por_consultor;
DROP VIEW IF EXISTS v_reconquista_por_loja;
DROP VIEW IF EXISTS v_reconquista_ultimo;


-- ============================================================
-- v_reconquista_ultimo
--
-- Ultimo snapshot por cliente (cod_ade) por maciça.
-- Resolve loja_id via sucessora — se a loja original tem
-- sucessora_id, expoe a sucessora. Caso contrario, expoe a
-- propria loja_id (incluindo NULL quando o lookup do import
-- falhou).
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
    'loja_id ja vem resolvido para a sucessora quando aplicavel '
    '(COALESCE(sucessora_id, loja_id)).';


-- ============================================================
-- v_reconquista_por_loja
--
-- KPIs agregados por loja. Esconde lojas inativas que nao
-- tiveram sucessora resolvida; expoe snapshots sem loja como
-- bucket "(Nao Identificado)".
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
    'KPIs de reconquista por loja. loja_id vem ja resolvido '
    'pela sucessora via v_reconquista_ultimo. Esconde lojas '
    'inativas sem sucessora; bucket "(Nao Identificado)" para '
    'snapshots sem loja resolvida.';


-- ============================================================
-- v_reconquista_por_consultor
--
-- KPIs por consultor. A loja exibida vem da loja_id do
-- consultor (consultores.loja_id), resolvida via sucessora.
-- Esconde consultores cuja loja-base seja inativa sem
-- sucessora.
-- ============================================================

CREATE VIEW v_reconquista_por_consultor
    WITH (security_invoker = on)
AS
SELECT
    s.macica_id,
    m.codigo                                                        AS macica,
    m.meta_retencao,
    COALESCE(l.nome, '(Nao Identificado)')                          AS loja,
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
JOIN macicas m                ON m.id = s.macica_id
LEFT JOIN consultores con     ON con.id = s.consultor_id
LEFT JOIN lojas l_orig        ON l_orig.id = con.loja_id
LEFT JOIN lojas l             ON l.id = COALESCE(l_orig.sucessora_id, l_orig.id)
LEFT JOIN regioes r           ON r.id = l.regiao_id
WHERE l.ativo = true OR l.id IS NULL
GROUP BY
    s.macica_id, m.codigo, m.meta_retencao,
    l.nome, r.nome, con.nome;

COMMENT ON VIEW v_reconquista_por_consultor IS
    'KPIs de reconquista por consultor. A loja-base do '
    'consultor e resolvida via sucessora. Esconde consultores '
    'de lojas inativas sem sucessora.';


-- ============================================================
-- v_reconquista_indiferentes
--
-- Clientes com 3+ aparicoes na mesma maciça sem conversao.
-- Loja resolvida via sucessora.
-- ============================================================

CREATE VIEW v_reconquista_indiferentes
    WITH (security_invoker = on)
AS
SELECT
    s.macica_id,
    m.codigo                                                        AS macica,
    s.cod_ade,
    COALESCE(l.nome, '(Nao Identificado)')                          AS loja,
    r.nome                                                          AS regiao,
    con.nome                                                        AS consultor,
    COUNT(DISTINCT s.dat_envio)                                     AS aparicoes,
    ROUND(AVG(s.saldo_contabil), 2)                                 AS saldo_medio,
    ROUND(AVG(s.dias_atraso), 0)                                    AS dias_atraso_medio,
    MIN(s.dat_envio)                                                AS primeira_aparicao,
    MAX(s.dat_envio)                                                AS ultima_aparicao
FROM reconquista_snapshot s
JOIN macicas m                ON m.id = s.macica_id
LEFT JOIN lojas l_orig        ON l_orig.id = s.loja_id
LEFT JOIN lojas l             ON l.id = COALESCE(l_orig.sucessora_id, l_orig.id)
LEFT JOIN regioes r           ON r.id = l.regiao_id
LEFT JOIN consultores con     ON con.id = s.consultor_id
WHERE l.ativo = true OR l.id IS NULL
GROUP BY s.macica_id, m.codigo, s.cod_ade, l.nome, r.nome, con.nome
HAVING COUNT(DISTINCT s.dat_envio) >= 3
   AND MAX(s.flag_reconquista) = 0;

COMMENT ON VIEW v_reconquista_indiferentes IS
    'Clientes que aparecem 3+ vezes na mesma maciça sem '
    'converterem. Loja resolvida via sucessora; bucket '
    '"(Nao Identificado)" para snapshots sem loja.';
