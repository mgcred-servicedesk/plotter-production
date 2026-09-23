# 2026-09-23 — Tools marcam o Vai e Vem como backoffice

**Agente:** Claude Code
**Tipo:** feature
**Arquivos tocados:** `src/dashboard/chat_ia/tools.py`,
`tests/test_chat_ia_tools.py`

## Objetivo

O assistente listou `VAI E VEM` junto de lojas reais, como loja zerada.
Ele não tem como deduzir dos números que aquilo é o setor de digitação
do backoffice.

## Diagnóstico

Não era filtro faltando. Por
[business-rules.md](../business-rules.md) ("Lojas de backoffice"), no
eixo **loja** o Vai e Vem aparece **por regra** — `LOJAS_BACKOFFICE` /
`excluir_lojas_backoffice` atuam no eixo **consultor**. O dado estava
certo; faltava o agente saber o que ele significa.

## O que foi feito

- `_eh_backoffice` (match normalizado, igual a
  `excluir_lojas_backoffice`) e `_nota_backoffice` em `tools.py`, sobre
  a constante `LOJAS_BACKOFFICE` de `kpis/gerais.py` — **fonte única**,
  sem redeclarar o literal.
- `ranking_periodo` e `comparar_entidades`: linha da entidade de
  backoffice ganha `"natureza": "backoffice"`.
- Os três (com `listar_sem_producao`) anexam `nota_backoffice`
  (`entidades` + `observacao`) **só quando** alguma entra no resultado.
- 4 testes novos.

## Decisões não óbvias

- **Marca no payload, não no `SYSTEM_PROMPT`** — mesmo princípio do
  `truncado` (23/09c): a tool diz a verdade, o modelo não infere. Custa
  token só onde muda a leitura, e não some quando o prompt crescer.
  Colar `business-rules.md` no prompt custaria ~16k tokens × até 6
  rodadas **por pergunta**.
- **Campo ausente quando não se aplica** — `natureza` só existe na linha
  marcada, e `nota_backoffice` só no resultado que a contém. Um campo
  `"natureza": "normal"` em toda linha seria ruído puro.
- **Escopo: só o Vai e Vem** — DIGITAL (sem meta em nenhum escopo, 0% de
  atingimento esperado) e os "números intencionais" (metas SAQUE/FGTS
  zeradas, emissão de cartão pausada) ficaram de fora até aparecerem no
  uso real.

## Validação

- E2E real (OpenRouter, Supabase blindado) com o Vai e Vem **liderando**
  o ranking: o modelo reportou o dado, explicou a natureza, citou o
  repasse ao consultor e avisou para não comparar com lojas de venda.
- Sabotagens: match sem normalização (1 falha), nota sempre presente
  (2 falhas).
- `1332 testes` passando; `ruff check` limpo.

## Não era bug (verificado)

- `comparar_entidades` **não** passa `entidades_excluir` a
  `calcular_evolucao_por_entidade` — e está certo: a função já exclui
  backoffice no eixo consultor internamente, e no eixo loja a linha
  fica por regra (paridade com `calcular_ranking_lojas`).
- O Vai e Vem sumir de um ranking com produção zero é o filtro de
  produção do próprio ranking, não a regra de backoffice. Com produção,
  ele aparece e vem marcado. Doc e código conferem.

## Pendências / follow-ups

- [ ] Se DIGITAL causar leitura errada no uso real (0% de atingimento
      por não ter meta em nenhum escopo), aplicar o mesmo mecanismo.
- [ ] Segue aberto de 23/09c: nenhuma tool filtra por faixa de valor.

## Referências

- Regra: [business-rules.md](../business-rules.md) — "Lojas de
  backoffice (Vai e Vem)"
- Progresso anterior:
  [2026-09-23c-chat-ia-ranking-truncado-em-silencio.md](2026-09-23c-chat-ia-ranking-truncado-em-silencio.md)
