# 2026-09-15 — Emissão: critério único por `TIPO_PRODUTO`

**Agente:** Claude Code
**Tipo:** mudança de regra de negócio (decisão do usuário) + refactor
**Arquivos tocados:** `src/dashboard/kpis/{consolidacao,detalhes_cards,gerais,produtos}.py`,
`src/dashboard/tabs/{em_analise,produtos}.py`, `src/config/settings.py`,
`tests/test_criterio_emissao.py` (novo) + 4 arquivos de teste,
`docs/agents/{business-rules,README}.md`

## Objetivo

Fechar a divergência aberta em
[2026-09-15c](2026-09-15c-analiticos-criterios-e-emissao.md): "Emissão"
tinha dois critérios no código.

## A investigação no dado

Todas as consultas foram rodadas pelo usuário no SQL Editor, uma por vez.

1. **A primeira consulta voltou vazia, por erro meu.** Filtrei pagos por
   `data_status_pagamento`, mas o dashboard filtra por `periodo_id`.
2. Com o filtro por período: não há nenhuma emissão paga de junho a
   setembro de 2026. As únicas linhas `CARTÃO` são saque pelo cartão.
3. Em Análise e Cancelados, pelas RPCs do dashboard: também nenhuma
   emissão.
4. Histórico por mês: cerca de 530 a 610 emissões por mês até abril de
   2026, 100 em maio, **zero desde junho**. O usuário confirmou que é
   **pausa burocrática, e não produto descontinuado**.
5. **Só as linhas em que os critérios discordam, em toda a base:**
   3 propostas, todas de operação de cartão com produto de SAQUE (1 paga
   em abr/2025 e 2 não pagas em dez/2025).

## Decisão

**O usuário escolheu `TIPO_PRODUTO`**, e não a minha recomendação
(`TIPO OPER.`). Antes de implementar, levantei o risco uma vez: a zeragem
por operação veio do commit `292ab90`, feito para o caso "Pré-Adesão de
produto CONSIG". A consulta 5 mostrou que esse caso não existe mais na
base, e que as divergências restantes são saque, que é produção com
valor. A escolha se sustenta, e o Caderno já usava o produto.

## O que foi feito

- `consolidacao.eh_emissao(df)`: o único critério. Normaliza texto, é
  segura para coluna toda nula e, sem a coluna, devolve tudo falso.
- Seis superfícies passam a chamá-la: a flag e a zeragem na consolidação,
  `aplicar_conta_valor` (análise e cancelados), `mascaras_aceleradores`,
  o card de quantidade em análise (`emissao_analise`), o contador da aba
  Em Análise e a aba Produtos (`_mask_subtab` ganhou o critério
  `emissao`, e `col_dig_emissao` passa a valer para a coluna Análise).
- Na aba Produtos, a operação continua como **dimensão de exibição**
  (colunas "Cartão Benefício" e "Venda Pré-Adesão"), sempre restrita a
  produto de emissão.
- **Removido, com confirmação do usuário:**
  `detalhes_cards.TIPOS_OPER_EMISSAO`, que ficou sem uso, e o import
  órfão de `PRODUTOS_EMISSAO` em `kpis/produtos.py`, que já estava órfão
  antes, escondido por `noqa`.

## Efeito nos números

Hoje não muda nada, porque não há emissão desde junho. No histórico, só
as 3 propostas: +1 contrato de saque em abr/2025, com valor e pontos, e
-1 emissão; as 2 de dez/2025 viram saque em análise e cancelados.
Nenhum request novo ao Supabase e nenhuma migration.

## Testes

- `tests/test_criterio_emissao.py`: um frame com as formas reais de
  proposta (emissão normal, cartão com SAQUE BENEFICIO, Pré-Adesão com
  SAQUE e um controle) passa pelas seis superfícies, e todas precisam
  concordar. Mais uma catraca textual: os literais de operação só podem
  aparecer em `tabs/produtos.py`, como dimensão.
- 9 testes antigos codificavam a regra por operação e foram atualizados
  no **dado de entrada**, mantendo a intenção de cada um. Renomeei os que
  diziam "tipo_oper" como critério.

| Sabotagem (volta ao critério por operação) | Testes que quebram |
|---|---|
| flag da consolidação | 7 |
| `aplicar_conta_valor` sem a cláusula de emissão | 3 |
| card de quantidade em análise | 2 |
| `mascaras_aceleradores` | 2 |
| contador da aba Em Análise | 1: **só a catraca textual** |
| sub-aba ignora `emissao` | 4 |

**Lacuna consciente:** a aba Em Análise é render puro. Ela está protegida
contra a volta do critério antigo (pelos literais), mas não contra uma
terceira forma de errar.

Suíte: 1.122 → 1.138, ruff limpo.
