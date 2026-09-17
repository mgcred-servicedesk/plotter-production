# 2026-09-17 — Campanhas: RLS só no analítico

**Agente:** Claude Code
**Tipo:** fix (escopo de RLS)
**Arquivos tocados:** `src/dashboard/pages/campanhas.py`,
`tests/test_kpis_campanha.py`

> Continua [2026-09-16c](2026-09-16c-campanha-condicoes-premiacao.md).

## Decisão (usuário, 17/09/2026)

> "no dashboard de campanha é importante manter os rankings e posições
> sem o filtro pelo RLS. O RLS deverá atuar apenas nos analíticos de
> produção da campanha."

## O que mudou

- `_render_painel` **não** aplica mais `aplicar_rls`. Termômetro, cards,
  condições, famílias e rankings usam o frame da rede inteira para
  qualquer perfil.
- Nova `tabela_analitico(df)` aplica `aplicar_rls` **dentro dela** — o
  recorte fica junto do único bloco com linha crua, para nenhum caminho
  montar o analítico sem ele. Fail-closed herdado: sem perfil, vazio.

## Por que o estado anterior estava errado além da preferência

Com o RLS antes de tudo, um supervisor via a **própria loja** contra a
meta de R$ 75 mi, e `contemplacao` apurava as condições com a produção
recortada — o degrau exibido nunca bateria para ele, mesmo com a rede
batendo. Um consultor se via em 1º de um ranking de uma linha. Meta,
cascata e posição só têm sentido na rede.

## Premissa a validar

**Consultor também vê o ranking completo** (nomes, valor, pontos e
média/DU de todos). Segue a palavra da decisão ("rankings e posições
sem filtro"), sem exceção por perfil. Se consultor deveria ver só a
própria posição, é mudança pequena — mas é outra decisão.

## Verificação

`TestRlsSoNoAnalitico` (7 testes): analítico recortado por supervisor,
gerente, sem perfil e admin; painel renderizado com perfil restrito
mostrando rankings e famílias da rede **e**, na mesma página, o
analítico recortado. Duas sabotagens pegas: RLS de volta no painel (3
falhas) e analítico sem RLS (5 falhas). Suíte: 1270 passam.
