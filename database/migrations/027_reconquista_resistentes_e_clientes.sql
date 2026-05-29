-- ============================================================
-- Migracao 027: Reconquista — renomear Indiferentes para
-- Resistentes e adicionar view analitica por cliente
--
-- Mudancas:
--   1. v_reconquista_ultimo passa a expor todas as colunas do
--      snapshot (banco_origem/destino, tipo_pgto, tipo_conta,
--      regra_pgto, dat_fim_relac, qtd_fdr, link). Necessario
--      para alimentar v_reconquista_clientes sem joins extras.
--   2. v_reconquista_indiferentes é REMOVIDA. v_reconquista_resistentes
--      assume o mesmo papel — clientes com 3+ aparicoes sem
--      conversao. Mesmo filtro, nome mais descritivo do
--      comportamento (resistem a oferta).
--   3. NOVA v_reconquista_clientes — listagem analitica
--      completa, 1 linha por cliente (cod_ade) com o ultimo
--      estado + agregados de aparicoes. Inclui colunas
--      derivadas `status` (Reconquistado/Pendente) e
--      `tipo_conversao` (CNC/Consignado/Cartao/DNA com
--      prioridade CNC > Consignado > Cartao > DNA).
--
-- Depende de: 026_reconquista_views_consultor_nome_origem.sql.
-- Executar no Supabase SQL Editor.
-- ============================================================

DROP VIEW IF EXISTS v_reconquista_clientes;
DROP VIEW IF EXISTS v_reconquista_resistentes;
DROP VIEW IF EXISTS v_reconquista_indiferentes;
DROP VIEW IF EXISTS v_reconquista_por_loja;
DROP VIEW IF EXISTS v_reconquista_ultimo;


-- ============================================================
-- v_reconquista_ultimo
--
-- Ultimo snapshot por cliente (cod_ade) por maciça. Resolve
-- loja_id via sucessora. Agora expoe TODAS as colunas do
-- snapshot (necessario para v_reconquista_clientes).
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
    s.flag_rl,
    s.tipo_pgto,
    s.tipo_conta,
    s.regra_pgto,
    s.dat_fim_relac,
    s.banco_origem,
    s.banco_destino,
    s.qtd_fdr,
    s.link
FROM reconquista_snapshot s
LEFT JOIN lojas l_orig ON l_orig.id = s.loja_id
ORDER BY s.macica_id, s.cod_ade, s.dat_envio DESC;

COMMENT ON VIEW v_reconquista_ultimo IS
    'Ultimo snapshot por cliente (cod_ade) por maciça. '
    'loja_id resolvido via sucessora. Expoe todas as colunas '
    'do snapshot para alimentar a listagem analitica.';


-- ============================================================
-- v_reconquista_por_loja
--
-- KPIs agregados por loja. Inalterada em comportamento — apenas
-- recriada por dependencia em v_reconquista_ultimo.
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
-- v_reconquista_resistentes
--
-- Antes "v_reconquista_indiferentes". Mesmo filtro (3+ aparicoes
-- sem conversao). Nome novo descreve o comportamento — sao
-- clientes que resistem a oferta de reconquista.
-- ============================================================

CREATE VIEW v_reconquista_resistentes
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

COMMENT ON VIEW v_reconquista_resistentes IS
    'Clientes com 3+ aparicoes na mesma maciça que nunca '
    'converteram — alvo prioritario de acao. Nome anterior: '
    'v_reconquista_indiferentes.';


-- ============================================================
-- v_reconquista_clientes
--
-- Listagem analitica completa: 1 linha por cliente (cod_ade)
-- com o ultimo estado + agregados de aparicoes. Inclui colunas
-- derivadas para facilitar leitura/filtro:
--   - status: Reconquistado se flag_reconquista=1, senao Pendente
--   - tipo_conversao: qual flag esta em 1, com prioridade
--     CNC > Consignado > Cartao > DNA (CNC e fato contabil
--     irreversivel; DNA e estado de processo reversivel).
-- ============================================================

CREATE VIEW v_reconquista_clientes
    WITH (security_invoker = on)
AS
SELECT
    u.macica_id,
    m.codigo                                                        AS macica,
    u.cod_ade,
    COALESCE(l.nome, '(Nao Identificado)')                          AS loja,
    r.nome                                                          AS regiao,
    COALESCE(con.nome, u.consultor_nome_origem, '(Sem Consultor)')  AS consultor,
    u.subproduto,
    u.saldo_contabil,
    u.dias_atraso,
    u.faixa_atraso,
    u.flag_reconquista,
    CASE
        WHEN u.flag_reconquista = 1 THEN 'Reconquistado'
        ELSE 'Pendente'
    END                                                             AS status,
    CASE
        WHEN u.flag_cnc        = 1 THEN 'CNC'
        WHEN u.flag_consignado = 1 THEN 'Consignado'
        WHEN u.flag_cartao     = 1 THEN 'Cartao'
        WHEN u.flag_dna        = 1 THEN 'DNA'
        ELSE NULL
    END                                                             AS tipo_conversao,
    u.mot_ipd_operar,
    u.banco_origem,
    u.banco_destino,
    u.tipo_pgto,
    u.tipo_conta,
    u.dat_ultimo_envio,
    agg.aparicoes,
    agg.primeira_aparicao,
    agg.ultima_aparicao
FROM v_reconquista_ultimo u
JOIN macicas m                ON m.id = u.macica_id
LEFT JOIN lojas l             ON l.id = u.loja_id
LEFT JOIN regioes r           ON r.id = l.regiao_id
LEFT JOIN consultores con     ON con.id = u.consultor_id
JOIN LATERAL (
    SELECT
        COUNT(DISTINCT s.dat_envio) AS aparicoes,
        MIN(s.dat_envio)            AS primeira_aparicao,
        MAX(s.dat_envio)            AS ultima_aparicao
    FROM reconquista_snapshot s
    WHERE s.macica_id = u.macica_id
      AND s.cod_ade   = u.cod_ade
) agg ON true
WHERE l.ativo = true OR l.id IS NULL;

COMMENT ON VIEW v_reconquista_clientes IS
    'Listagem analitica por cliente (cod_ade): ultimo estado + '
    'agregados de aparicoes. Inclui colunas derivadas status e '
    'tipo_conversao (prioridade CNC > Consignado > Cartao > DNA).';
