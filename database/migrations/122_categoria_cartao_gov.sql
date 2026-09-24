-- =====================================================
-- Migracao 122: categoria CARTAO_GOV (Cartao Gov)
-- Data: 2026-09-24
-- Depende de: schema.sql (categorias_produto), 013 (categoria_pts_id)
--
-- Pedido da operacao (2026-09-24): cadastrar uma linha de pontuacao
-- para "Cartao Gov", porque o SAQUE no cartao Gov pontua DIFERENTE do
-- saque convencional. A planilha de pontuacao ja tem a linha
-- (1 real = 1 ponto); o import falhava com
--   Produto invalido: "CARTAO GOV"
-- porque a categoria nao existe nem aqui nem no mapa do importador.
--
--
-- POR QUE 'Emissao igual ao CARTAO' E MESMO ASSIM TEM LINHA DE PTS
-- ----------------------------------------------------------------
-- Parece contraditorio: `conta_pontuacao = false` e, ao mesmo tempo,
-- uma linha em `pontuacao`. Nao e — e exatamente o desenho do CARTAO
-- de hoje, e o motivo esta na 013.
--
-- O CARTAO tem `conta_pontuacao = false` (emissao nao pontua) e ainda
-- assim tem linha de PTS todo mes (2,5 em 05-09/2026). A linha existe
-- porque SAQUE e SAQUE_BENEFICIO apontam `categoria_pts_id -> CARTAO`:
-- eles NAO pontuam pelo proprio codigo, pontuam pelo do cartao. A
-- categoria e a FONTE do valor, nao a consumidora.
--
-- CARTAO_GOV nasce no mesmo papel: fonte de PTS para o saque Gov, com
-- taxa propria. O flag nao herda pelo alias — o comentario da coluna e
-- explicito ("O flag conta_pontuacao do contrato continua sendo o da
-- propria categoria"), entao `false` aqui nao zera quem consumir.
--
--
-- A UNIDADE: PTS E POR REAL, NAO POR CONTRATO
-- --------------------------------------------
-- `pontos = VALOR x PTS` (src/dashboard/kpis/pontuacao.py, regra em
-- business-rules.md). E o `mapa_pontos` le a coluna `pontos` DIRETO,
-- sem dividir por `producao` (consolidacao.py:215-219) — `producao` e
-- documental, nao entra na conta.
--
-- Logo "1 real = 1 ponto" e a linha `producao = 1, pontos = 1.0`, no
-- mesmo formato das 9 linhas que ja existem por competencia. Cuidado
-- ao preencher a planilha: `PRODUCAO = 1000 / PONTOS = 1000` NAO e
-- "1 por real" — daria PTS = 1000 por real.
--
--
-- ESCOLHAS, E O QUE ELAS AFETAM
-- ------------------------------
--   codigo            CARTAO_GOV       chave de negocio, casa com o
--                                      mapa do importador (angry-man)
--   nome              Cartao Gov       sem acento, como 'Cartao',
--                                      'Consig BMG' (convencao da tabela)
--   grupo_dashboard   NULL             o comentario da coluna manda NULL
--                                      para "produtos especiais (emissao,
--                                      seguros, super conta)"
--   grupo_meta        EMISSAO          mesma meta do CARTAO. PREMISSA:
--                                      Gov divide a meta de emissao com o
--                                      cartao comum. Se tiver meta propria,
--                                      trocar ANTES de aplicar
--   conta_valor       false            emissao nao soma valor (igual CARTAO)
--   conta_pontuacao   false            nao pontua por si; e fonte de alias
--   categoria_pts_id  NULL             linha PROPRIA, nao alias de outro —
--                                      e o ponto do pedido: taxa distinta
--   ordem             16               proximo livre (o maior hoje e 15).
--                                      Nao reordena ninguem: inserir em 14
--                                      exigiria empurrar BMG_MED e
--                                      SEGURO_VIDA, mudanca nao pedida
--
--
-- O QUE ESTA MIGRATION *NAO* FAZ — LER ANTES DE ESPERAR EFEITO
-- ------------------------------------------------------------
-- Ela destrava o IMPORT. Ela NAO faz o saque Gov pontuar diferente.
-- Faltam duas peças, e nenhuma delas cabe aqui:
--
-- 1) O mapa do importador (outro repo, precisa deploy):
--    angry-man/src/services/import-pontuacao.ts, PRODUTO_TO_CATEGORIA
--      'CARTÃO GOV': 'CARTAO_GOV',
--      'CARTAO GOV': 'CARTAO_GOV',
--    O importador da UPPERCASE no valor da planilha antes de procurar,
--    e depois exige a categoria no banco — por isso ESTA migration vem
--    PRIMEIRO. Na ordem inversa o erro so troca de texto para
--    'Categoria "CARTAO_GOV" nao encontrada em categorias_produto'.
--
-- 2) Quem CONSOME o alias. Medido em 2026-09-24: dos 33 produtos com
--    "GOV" em `produtos`, ZERO sao emissao de cartao — sao
--    CONSIG_BMG (21), SAQUE_BENEFICIO (5), SAQUE (5), PORTABILIDADE (2).
--    Os saques Gov estao HOJE dentro de SAQUE / SAQUE_BENEFICIO, que
--    aliasam para CARTAO (2,5). Enquanto ninguem apontar para
--    CARTAO_GOV, a linha fica inerte: importada, guardada, e sem efeito
--    em numero nenhum.
--
--    Para o saque Gov pontuar a 1,0 seria preciso uma categoria propria
--    (ex. SAQUE_GOV com `categoria_pts_id -> CARTAO_GOV`) e remapear
--    aqueles produtos para ela. Isso MUDA PONTOS HISTORICOS dos
--    contratos Gov ja pagos, entao e decisao separada, com medicao
--    antes — nao entra de carona nesta.
--
-- Executar no Supabase SQL Editor.
-- =====================================================


-- ===========================================
-- 1. Guarda: nao duplicar, nao sobrescrever
-- ===========================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.categorias_produto
                WHERE codigo = 'CARTAO_GOV') THEN
        RAISE EXCEPTION
            'CARTAO_GOV ja existe. Esta migration e de criacao; '
            'para ALTERAR atributos, crie uma nova migration com UPDATE.';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM public.categorias_produto
                    WHERE codigo = 'CARTAO') THEN
        RAISE EXCEPTION
            'CARTAO nao encontrado — a tabela nao esta no estado medido. '
            'Revise antes de aplicar.';
    END IF;
END $$;


-- ===========================================
-- 2. A categoria
-- ===========================================

INSERT INTO public.categorias_produto (
    codigo, nome, grupo_dashboard, grupo_meta,
    conta_valor, conta_pontuacao, categoria_pts_id, ordem, ativo
) VALUES (
    'CARTAO_GOV', 'Cartao Gov', NULL, 'EMISSAO',
    false, false, NULL, 16, true
);

-- ===========================================
-- 3. Verificacao — rodar DEPOIS
-- ===========================================
--
-- 1) A categoria existe e esta como esperado:
--
--    SELECT codigo, nome, grupo_dashboard, grupo_meta,
--           conta_valor, conta_pontuacao, categoria_pts_id, ordem, ativo
--      FROM categorias_produto WHERE codigo = 'CARTAO_GOV';
--
-- 2) Nada mudou nas outras 15 (esperado: 16 linhas, 15 anteriores intactas):
--
--    SELECT count(*) FROM categorias_produto;              -- 16
--    SELECT count(*) FROM categorias_produto WHERE ativo;  -- 16
--
-- 3) A RPC de pontuacao NAO deve mostrar CARTAO_GOV ainda — ela filtra
--    `COALESCE(pt_direta.pontos, pt_alias.pontos) IS NOT NULL`, e nao
--    existe linha em `pontuacao` antes do import:
--
--    SELECT categoria_codigo FROM obter_pontuacao_periodo(9, 2026)
--     ORDER BY 1;
--    -- esperado: as MESMAS 9 de antes, sem CARTAO_GOV
--
-- 4) Depois do deploy do angry-man e do upload da planilha, a linha
--    aparece e o PTS e o esperado:
--
--    SELECT categoria_codigo, pontos, producao
--      FROM obter_pontuacao_periodo(9, 2026)
--     WHERE categoria_codigo = 'CARTAO_GOV';
--    -- esperado: pontos = 1.0 (1 real = 1 ponto), producao = 1
--
-- 5) E o total de pontos da rede NAO pode se mover so por isso — nenhum
--    contrato aponta para CARTAO_GOV, e conta_pontuacao = false.
--    Comparar o KPI de pontos de 09/2026 antes/depois do import.
