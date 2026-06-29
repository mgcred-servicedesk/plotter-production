# 2026-06-29 — Desmembrar PACK em colunas nos detalhes (Em Análise + Cancelados)

## Contexto

Nas páginas de detalhe (cards de contexto), o grupo `grupo_dashboard='PACK'`
aparecia como uma única coluna. Na "Digitação do Último Dia" mostrava o termo
cru `PACK`; nas demais tabelas, o label amigável `FGTS/Ant. Ben./CNC 13o`
(via `NOMES_DISPLAY_PRODUTO`). Pedido: separar o pack em colunas por produto
(FGTS / Antecipação / 13o) para melhor leitura de volume, nas 3 tabelas
("Digitação do Último Dia", "Análise por Produto", "Cancelados por Produto").

## Diagnóstico

- O rename `PACK → FGTS/Ant. Ben./CNC 13o` (`_aplicar_nomes_display` em
  `app.py`) só atinge `df`, `categorias`, `df_analise`, `df_cancelados`. O
  `df_digitacao_detalhe` passa direto para a página → mostrava `PACK` cru.
- `df_analise` / `df_cancelados` carregam `categoria_codigo` (FGTS, ANT_BENEF,
  CNC_13) → split possível 100% client-side.
- A RPC `obter_digitacao_diaria_detalhe` (migration 038) **pré-agregava** por
  `grupo_dashboard`, sem expor `categoria_codigo` → split dessa tabela exigiu
  nova migration.

## Decisões

- **Escopo:** split nas 3 tabelas (escolha do usuário), incluindo a migration
  de banco.
- **Rótulos:** `FGTS | Antecipação | 13o` (escolha do usuário; chaveados por
  `categoria_codigo`).
- **Estratégia:** dimensão derivada `PRODUTO_DETALHADO` (helper puro
  `adicionar_produto_detalhado` em `src/dashboard/kpis/detalhes_cards.py`).
  Linhas do pack viram o rótulo granular; o resto mantém `grupo_dashboard`
  (com `NOMES_DISPLAY_PRODUTO` como rede de segurança p/ `PACK` residual). Os
  pivots continuam genéricos — a página passa a coluna derivada.
- **Backward-safe:** enquanto a migration 041 não rodar no Supabase,
  `categoria_codigo` chega `None` na digitação detalhe e o helper cai no
  fallback `grupo_dashboard` (label amigável) — sem quebra. Após aplicar, a
  digitação também desmembra.

## Arquivos

- `database/migrations/041_fn_digitacao_diaria_detalhe_categoria.sql` (NOVA) —
  `DROP` + `CREATE OR REPLACE` da RPC, adiciona `categoria_codigo` (= `cp.codigo`)
  ao retorno e ao `GROUP BY`. **Pendente de aplicação manual no Supabase.**
- `src/dashboard/loaders.py` — `_fetch_digitacao_diaria_detalhe` carrega
  `categoria_codigo`.
- `src/dashboard/kpis/detalhes_cards.py` — `PACK_SPLIT_LABELS`,
  `COL_PRODUTO_DETALHADO`, `adicionar_produto_detalhado`.
- `src/dashboard/pages/detalhes_cards.py` — as 3 tabelas pivotam em
  `PRODUTO_DETALHADO`. "Por Banco" inalterado.
- `tests/test_kpis_detalhes_cards.py` — `TestAdicionarProdutoDetalhado` (8 casos).

## Validação

- `ruff check` nos arquivos tocados: OK.
- `pytest tests/`: 206 passed.

## Adendo — ocultar colunas de valor zeradas

Pedido seguinte: a coluna `OUTROS` (sempre R$ 0,00) só ocupa espaço, e a
"Digitação do Último Dia" deveria mostrar só colunas com valor.

- **Diagnóstico:** `OUTROS` = bucket de `grupo_dashboard` NULL (emissões/
  seguros), que têm `conta_valor=False` → VALOR sempre zerado nos pivots de
  valor. Logo a coluna é permanentemente zero.
- **Solução:** helper puro `ocultar_colunas_zeradas(pivot, linha)` em
  `kpis/detalhes_cards.py` — descarta colunas de valor todas-zero, preserva
  sempre `linha` e `Total`. Como as colunas removidas são todas-zero, os
  `Total` por linha não mudam.
- **Aplicação:** no choke point `_exibir_pivot` (`pages/detalhes_cards.py`),
  então vale **uniformemente** para os 5 pivots (Análise produto+banco,
  Cancelados produto+banco, Digitação do Último Dia). Resolve OUTROS e o
  "só colunas com valor" da Digitação de uma vez.
- **Testes:** `TestOcultarColunasZeradas` (5 casos). Suíte: 211 passed.

## Follow-ups

- Aplicar a migration 041 no Supabase SQL Editor (sem isso, a "Digitação do
  Último Dia" segue como 1 coluna com label amigável — as outras 2 já separam).
- Ordenação das colunas segue alfabética (convenção do pivot) → FGTS /
  Antecipação / 13o ficam intercalados com CLT/CNC/etc. Se quiser agrupá-los,
  é mudança de ordenação separada.
