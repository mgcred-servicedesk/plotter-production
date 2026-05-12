# 2026-05-12 — Alias de pontuação por categoria (migração 013)

**Agente:** Claude Code
**Tipo:** feature (DB/RPC) + docs
**Arquivos tocados:** `database/migrations/013_categoria_pts_alias.sql` (novo), `database/schema.sql` (atualizado)
**Commit(s):** (a fechar — migração pendente de aplicação no Supabase)

## Objetivo

Resolver o gap de 2.101.178 pts no Dashboard de Pontuação em
05/2026 e o tipo de incidente que o causou (categorias com
`conta_pontuacao=true` sem entrada manual em `pontuacao` no mês →
contratos vão a 0 pts).

## Origem do problema

A regra negocial em `Tabelas.xlsx` (coluna `PRODUTO PTS`) indica
que algumas categorias **buscam** sua pontuação via outra:

| Categoria | PRODUTO PTS (alvo) | PTS |
|---|---|---:|
| SAQUE | CARTÃO | 2,5 |
| SAQUE_BENEFICIO | CARTÃO | 2,5 |
| SUPER_CONTA | CNC | 5,0 |

Mas no banco a tabela `pontuacao` exige **uma linha por
categoria por período**. Toda virada de mês alguém precisava
duplicar manualmente as linhas espelhadas. Em 05/2026 isso não
foi feito para SAQUE/SAQUE_BENEFICIO/SUPER_CONTA → 294 contratos
ficaram com pontos=0.

## O que foi feito

- Nova coluna `categorias_produto.categoria_pts_id` (FK opcional
  para si mesma) — declara "use a pontuação da categoria X".
- Backfill via UPDATE: SAQUE→CARTAO, SAQUE_BENEFICIO→CARTAO,
  SUPER_CONTA→CNC.
- RPC `obter_pontuacao_periodo` reescrita:
  - Driver passou a ser `categorias_produto` (não `pontuacao`).
  - LEFT JOIN duplo: `pt_direta` (entrada direta) e `pt_alias`
    (entrada da categoria apontada por `categoria_pts_id`).
  - `COALESCE(pt_direta, pt_alias)` → linha direta tem prioridade,
    permitindo override pontual por período.
  - Preserva o fallback temporal (whole-period back-off de até
    24 meses).
  - `is_fallback` continua sinalizando **apenas o fallback
    temporal** — alias não é fallback.
- `schema.sql` atualizado para refletir a versão final.
- Validação SQL incluída no fim da migração (consulta o estado
  da RPC após aplicar).

## Decisões não óbvias

- **PORTABILIDADE não recebe alias.** Em `Tabelas.xlsx` ela
  aponta para 4 alvos com PTS diferentes (CONSIG / CONSIG BMG /
  CONSIG C6 = 1,0; CONSIG Itau = 0,5). A granularidade real é
  por `Tabela`, não por categoria — o alias por categoria não
  representa isso fielmente. Mantemos lookup direto; o operacional
  continua inserindo a linha por mês. Se virar problema recorrente,
  reabrir.
- **Linha direta tem prioridade sobre alias.** Isso é
  intencional: permite cadastrar uma linha em `pontuacao` para
  SAQUE num mês específico com PTS diferente de CARTAO sem
  precisar remover o alias.
- **`is_fallback` mantém semântica estrita.** Não usamos esse
  flag para sinalizar uso de alias — alias é estrutural, não
  fallback. Se quisermos expor "esta linha veio do alias" em
  algum futuro, deveria ser um campo separado (`via_alias`,
  `categoria_origem`).
- **`conta_pontuacao` continua sendo o da categoria do contrato**,
  não do alias. Importante: CARTAO tem `conta_pontuacao=false`,
  mas SAQUE tem `conta_pontuacao=true`. O contrato SAQUE
  apenas **lê o PTS** de CARTAO via alias; a regra "zerar pontos
  quando `conta_pontuacao=false`" continua olhando o flag do
  contrato (SAQUE → não zera). Comportamento preservado.
- **Não tocamos `consolidar_dados`/`carregar_pontuacao_efetiva`.**
  A migração é transparente para o cliente: o `df_pontos`
  agora vem com as linhas adicionais (SAQUE, SAQUE_BENEFICIO,
  SUPER_CONTA) com `pontos` herdadas — sem nenhuma mudança de
  código Python.

## Reversão

```sql
-- Restaurar RPC para versão pre-013 (copiar bloco de
-- schema.sql do commit imediatamente anterior à 013):
CREATE OR REPLACE FUNCTION obter_pontuacao_periodo(...) ... ;

-- Remover índice e coluna:
DROP INDEX IF EXISTS idx_categorias_produto_pts_id;
ALTER TABLE categorias_produto DROP COLUMN IF EXISTS categoria_pts_id;
```

## Pendências / follow-ups

- [x] Aplicar a migração no Supabase (usuário) e validar com
      a consulta de validação dentro do arquivo SQL.
      **Aplicado em 2026-05-12. Pontuação de saque confirmada no dashboard.**
- [x] Após aplicar, clicar **"Atualizar Dados"** no sidebar do
      dashboard para invalidar cache de 6h — concluído.
- [ ] Avaliar uma UI admin para gerenciar `categoria_pts_id`
      (hoje só via SQL direto). Não é bloqueante.
- [ ] PORTABILIDADE precisa ainda de cadastro manual a cada
      mês até decidirmos um caminho granular (por `Tabela`,
      possivelmente via produtos.tabela → pts diretamente,
      ignorando a categoria — mudança maior).

## Referências

- Migração: [database/migrations/013_categoria_pts_alias.sql](../../../database/migrations/013_categoria_pts_alias.sql)
- Schema atualizado: [database/schema.sql](../../../database/schema.sql) — busque `categoria_pts_id` e `obter_pontuacao_periodo`
- Tabelas.xlsx — coluna `PRODUTO PTS`
- Progresso relacionado: [2026-05-12-dashboard-pontuacao.md](2026-05-12-dashboard-pontuacao.md)
