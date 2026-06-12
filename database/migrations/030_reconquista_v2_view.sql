-- ============================================================
-- Migracao 030: Reconquista v2 — view de leitura `v_reconquista`
--
-- View unica, detalhada (1 linha por cliente) com loja/regiao/
-- consultor resolvidos e o periodo de referencia derivado de
-- dt_fim_relacionamento (ref_ano/ref_mes).
--
-- O dashboard:
--   * filtra ref_ano/ref_mes pelo MES ANTERIOR ao selecionado
--     (defasagem de 1 mes — aplicada no loader);
--   * deriva os KPIs (EFETIVADA/PROMESSA/SEM RECONQUISTA + taxa)
--     e a quebra por loja agregando esta view em pandas.
--
-- security_invoker = on: respeita as policies de quem consulta.
-- loja_id ja vem resolvido para a sucessora no import (028/029),
-- entao a view NAO re-resolve sucessora — apenas rotula.
--
-- Nomes novos: NAO altera as views v1 (v_reconquista_ultimo,
-- v_reconquista_por_loja, v_reconquista_clientes, _resistentes),
-- que seguem sinalizadas para deprecacao.
--
-- Depende de: 028_reconquista_v2_tabela.sql.
-- Executar no Supabase SQL Editor.
-- ============================================================

CREATE OR REPLACE VIEW v_reconquista
    WITH (security_invoker = on)
AS
SELECT
    r.co_adesao,
    r.status,
    r.dt_fim_relacionamento,
    EXTRACT(YEAR  FROM r.dt_fim_relacionamento)::INTEGER  AS ref_ano,
    EXTRACT(MONTH FROM r.dt_fim_relacionamento)::INTEGER  AS ref_mes,
    r.dt_macica,
    r.dt_dna,
    r.dt_producao,
    r.subproduto,
    COALESCE(l.nome, '(Nao Identificado)')                AS loja,
    reg.nome                                              AS regiao,
    COALESCE(con.nome, r.consultor_nome, '(Sem Consultor)') AS consultor,
    r.gerente_regional,
    r.gerente_loja,
    r.coordenador_loja,
    r.banco_origem,
    r.banco_destino,
    r.saldo_contabil,
    r.dias_atraso,
    r.faixa_atraso,
    r.tipo_pagamento,
    r.qt_fim_relacionamento,
    r.link_aceite
FROM reconquista r
LEFT JOIN lojas l         ON l.id   = r.loja_id
LEFT JOIN regioes reg     ON reg.id = l.regiao_id
LEFT JOIN consultores con ON con.id = r.consultor_id;

COMMENT ON VIEW v_reconquista IS
    'Reconquista v2: detalhe por cliente com loja/regiao/consultor '
    'rotulados e ref_ano/ref_mes (de dt_fim_relacionamento). Fonte '
    'unica do dashboard; KPIs e quebra por loja sao agregados no '
    'loader. Defasagem de 1 mes aplicada no loader.';
