-- =====================================================
-- Migracao 102: vigencias confirmadas do piloto de produtividade
-- Data: 2026-09-01
-- Depende de: 087 (consultor_vigencia diaria)
--
-- Registra duas admissoes confirmadas pela operacao para que o piloto de
-- 08/2026 nao derive data de vinculo a partir da primeira producao paga.
--
-- Mizael Barbosa Neto nao entra nesta migracao: a cobertura temporaria em
-- Rio Comprido precisa dos dias exatos para repartir, sem sobreposicao, a
-- vigencia cuja loja de origem e Laranjeiras.
-- =====================================================

BEGIN;

LOCK TABLE public.consultor_vigencia IN SHARE ROW EXCLUSIVE MODE;

DO $$
DECLARE
    v_lojas_invalidas TEXT;
    v_conflitos TEXT;
BEGIN
    WITH correcoes(nome, loja, admissao) AS (
        VALUES
            ('KASSIANE FONSECA FELICIO', 'HELP LARANJEIRAS', DATE '2026-08-25'),
            ('PRISCILA MARCIANA TRANCOSO CORREA DOS SANTOS',
             'HELP CAXIAS CENTRO', DATE '2026-08-11')
    ),
    resolucao AS (
        SELECT
            c.loja,
            count(l.id) AS quantidade
        FROM correcoes c
        LEFT JOIN public.lojas l
          ON upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g')) =
             upper(regexp_replace(btrim(c.loja), '[[:space:]]+', ' ', 'g'))
        GROUP BY c.loja
    )
    SELECT string_agg(format('%s (%s correspondencias)', loja, quantidade), ', ')
      INTO v_lojas_invalidas
      FROM resolucao
     WHERE quantidade <> 1;

    IF v_lojas_invalidas IS NOT NULL THEN
        RAISE EXCEPTION
            'Migration 102: loja ausente ou ambigua: %', v_lojas_invalidas;
    END IF;

    -- Uma linha aberta na loja correta, iniciada na admissao ou depois dela,
    -- pode ser antecipada com seguranca. Qualquer outro vinculo que alcance o
    -- periodo posterior a admissao exige revisao humana e aborta a migracao.
    WITH correcoes(nome, loja, admissao) AS (
        VALUES
            ('KASSIANE FONSECA FELICIO', 'HELP LARANJEIRAS', DATE '2026-08-25'),
            ('PRISCILA MARCIANA TRANCOSO CORREA DOS SANTOS',
             'HELP CAXIAS CENTRO', DATE '2026-08-11')
    ),
    resolvidas AS (
        SELECT
            c.*,
            l.id AS loja_id,
            upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g')) AS nn
        FROM correcoes c
        JOIN public.lojas l
          ON upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g')) =
             upper(regexp_replace(btrim(c.loja), '[[:space:]]+', ' ', 'g'))
    )
    SELECT string_agg(
               format('%s: %s [%s, %s)',
                      r.nome,
                      coalesce(l.nome, '<sem loja>'),
                      v.vigencia_inicio,
                      coalesce(v.vigencia_fim::text, 'aberta')),
               '; ' ORDER BY r.nome, v.vigencia_inicio
           )
      INTO v_conflitos
      FROM resolvidas r
      JOIN public.consultor_vigencia v
        ON v.nome_normalizado = r.nn
       AND coalesce(v.vigencia_fim, DATE '9999-12-31') > r.admissao
      LEFT JOIN public.lojas l ON l.id = v.loja_id
     WHERE NOT (
         v.loja_id = r.loja_id
         AND v.vigencia_fim IS NULL
         AND v.vigencia_inicio >= r.admissao
     );

    IF v_conflitos IS NOT NULL THEN
        RAISE EXCEPTION
            'Migration 102: vigencia conflitante; revisar antes de aplicar: %',
            v_conflitos;
    END IF;
END
$$;

WITH correcoes(nome, loja, admissao) AS (
    VALUES
        ('KASSIANE FONSECA FELICIO', 'HELP LARANJEIRAS', DATE '2026-08-25'),
        ('PRISCILA MARCIANA TRANCOSO CORREA DOS SANTOS',
         'HELP CAXIAS CENTRO', DATE '2026-08-11')
),
resolvidas AS (
    SELECT
        c.*,
        l.id AS loja_id,
        upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g')) AS nn
    FROM correcoes c
    JOIN public.lojas l
      ON upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g')) =
         upper(regexp_replace(btrim(c.loja), '[[:space:]]+', ' ', 'g'))
)
UPDATE public.consultor_vigencia v
   SET nome = r.nome,
       vigencia_inicio = r.admissao,
       origem = 'MANUAL'
  FROM resolvidas r
 WHERE v.nome_normalizado = r.nn
   AND v.loja_id = r.loja_id
   AND v.vigencia_fim IS NULL
   AND v.vigencia_inicio >= r.admissao;

WITH correcoes(nome, loja, admissao) AS (
    VALUES
        ('KASSIANE FONSECA FELICIO', 'HELP LARANJEIRAS', DATE '2026-08-25'),
        ('PRISCILA MARCIANA TRANCOSO CORREA DOS SANTOS',
         'HELP CAXIAS CENTRO', DATE '2026-08-11')
),
resolvidas AS (
    SELECT
        c.*,
        l.id AS loja_id,
        upper(regexp_replace(btrim(c.nome), '[[:space:]]+', ' ', 'g')) AS nn
    FROM correcoes c
    JOIN public.lojas l
      ON upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g')) =
         upper(regexp_replace(btrim(c.loja), '[[:space:]]+', ' ', 'g'))
)
INSERT INTO public.consultor_vigencia (
    nome, loja_id, vigencia_inicio, vigencia_fim, origem
)
SELECT r.nome, r.loja_id, r.admissao, NULL, 'MANUAL'
FROM resolvidas r
WHERE NOT EXISTS (
    SELECT 1
    FROM public.consultor_vigencia v
    WHERE v.nome_normalizado = r.nn
      AND v.loja_id = r.loja_id
      AND v.vigencia_inicio = r.admissao
      AND v.vigencia_fim IS NULL
);

DO $$
DECLARE
    v_incorretas TEXT;
BEGIN
    WITH esperado(nome, loja, admissao) AS (
        VALUES
            ('KASSIANE FONSECA FELICIO', 'HELP LARANJEIRAS', DATE '2026-08-25'),
            ('PRISCILA MARCIANA TRANCOSO CORREA DOS SANTOS',
             'HELP CAXIAS CENTRO', DATE '2026-08-11')
    ),
    contagem AS (
        SELECT
            e.nome,
            count(v.id) FILTER (
                WHERE upper(regexp_replace(btrim(l.nome), '[[:space:]]+', ' ', 'g')) =
                      upper(regexp_replace(btrim(e.loja), '[[:space:]]+', ' ', 'g'))
                  AND v.vigencia_inicio = e.admissao
                  AND v.vigencia_fim IS NULL
                  AND v.origem = 'MANUAL'
            ) AS corretas,
            count(v.id) FILTER (
                WHERE v.vigencia_inicio < DATE '9999-12-31'
                  AND coalesce(v.vigencia_fim, DATE '9999-12-31') > e.admissao
            ) AS posteriores
        FROM esperado e
        LEFT JOIN public.consultor_vigencia v
          ON v.nome_normalizado = upper(regexp_replace(
                 btrim(e.nome), '[[:space:]]+', ' ', 'g'))
        LEFT JOIN public.lojas l ON l.id = v.loja_id
        GROUP BY e.nome
    )
    SELECT string_agg(format('%s (corretas=%s, posteriores=%s)',
                             nome, corretas, posteriores), '; ')
      INTO v_incorretas
      FROM contagem
     WHERE corretas <> 1 OR posteriores <> 1;

    IF v_incorretas IS NOT NULL THEN
        RAISE EXCEPTION
            'Migration 102: pos-condicao das admissoes falhou: %', v_incorretas;
    END IF;
END
$$;

COMMIT;

-- Verificacao operacional:
-- SELECT v.nome, l.nome AS loja, v.vigencia_inicio, v.vigencia_fim, v.origem
-- FROM public.consultor_vigencia v
-- LEFT JOIN public.lojas l ON l.id = v.loja_id
-- WHERE v.nome_normalizado IN (
--     'KASSIANE FONSECA FELICIO',
--     'PRISCILA MARCIANA TRANCOSO CORREA DOS SANTOS'
-- )
-- ORDER BY v.nome_normalizado, v.vigencia_inicio;
