-- =====================================================
-- Migracao 005: Tabela de feriados
--
-- Objetivo: centralizar feriados no banco para calculo
-- de dias uteis com integridade e idempotencia.
-- Substitui a variavel HOLIDAYS do .env.
--
-- Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- 1. Tabela feriados
-- ===========================================

CREATE TABLE IF NOT EXISTS feriados (
    id SERIAL PRIMARY KEY,
    data DATE NOT NULL UNIQUE,
    descricao TEXT NOT NULL,
    tipo TEXT NOT NULL DEFAULT 'nacional'
        CHECK (tipo IN (
            'nacional',
            'estadual',
            'municipal',
            'ponto_facultativo'
        )),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_feriados_ano_mes
    ON feriados (
        EXTRACT(YEAR FROM data),
        EXTRACT(MONTH FROM data)
    );


-- ===========================================
-- 2. Dados iniciais — feriados nacionais e
--    estaduais de 2026 (apenas dias uteis)
-- ===========================================

INSERT INTO feriados (data, descricao, tipo) VALUES
    ('2026-01-01', 'Confraternizacao Universal',  'nacional'),
    ('2026-02-16', 'Carnaval (segunda-feira)',     'nacional'),
    ('2026-02-17', 'Carnaval (terca-feira)',       'nacional'),
    ('2026-04-03', 'Sexta-feira Santa',            'nacional'),
    ('2026-04-21', 'Tiradentes',                   'nacional'),
    ('2026-04-23', 'Sao Jorge',                    'estadual'),
    ('2026-05-01', 'Dia do Trabalho',              'nacional'),
    ('2026-06-04', 'Corpus Christi',               'nacional'),
    ('2026-09-07', 'Independencia do Brasil',      'nacional'),
    ('2026-10-12', 'Nossa Senhora Aparecida',      'nacional'),
    ('2026-11-02', 'Finados',                      'nacional'),
    ('2026-11-20', 'Consciencia Negra',            'nacional'),
    ('2026-12-25', 'Natal',                        'nacional')
ON CONFLICT (data) DO NOTHING;
