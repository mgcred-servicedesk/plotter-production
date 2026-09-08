# 2026-09-03 (b) — Fatia (0–100%) em vez de índice na loja e na região

**Agente:** Claude Code
**Tipo:** regra de negócio (decisão de produto do usuário)
**Arquivos tocados:** `src/dashboard/kpis/produtividade.py`,
`src/dashboard/tabs/gestao_consultores.py`, `tests/test_kpis_produtividade.py`,
`tests/test_tabs_gestao_presets.py`, `docs/agents/business-rules.md`
**Commit(s):** (não commitado)

## Objetivo

Continuação de
[2026-09-03-semantica-dos-percentuais-performance-time.md](2026-09-03-semantica-dos-percentuais-performance-time.md).
O usuário pediu leitura mais fácil: um universo de **até 100%**, por
proporcionalidade, mostrando o destaque do indivíduo sobre loja, região e rede.

## Decisão do usuário (revoga parte da entrada anterior)

Duas escolhas feitas com os números na mão:

1. **Base do share: a TAXA (R$/dia)**, não o dinheiro.
2. **Loja e região viram fatia; a rede segue como comparação** (índice).

## O que foi feito

- `% da loja` e `% da regiao` passam a ser **fatia**:
  `taxa ÷ Σ taxas do grupo × 100`. Somam 100% no grupo, vivem em 0–100%.
- `% da carteira` → **`vs. media da carteira`**. O `vs.` no cabeçalho separa as
  duas leituras: três colunas em "%" com dois significados era a confusão que
  esta sub-visão veio desfazer.
- A legenda calcula e publica a **fatia justa** (`100 ÷ n`) de cada tamanho de
  loja e de cada região presentes no escopo — dinâmica, não texto fixo.
- Ordenação: "Menor % da loja" → **"Menor fatia da loja"**; "Menor % da
  carteira" → **"Mais abaixo da media da carteira"**.
- `Na loja` mantida: dá a fatia justa de graça (`100 ÷ n`) e ordena sem escala.

## Decisões não óbvias

- **A fatia é da taxa porque a fatia do dinheiro reimportaria o viés que este
  módulo existe para remover.** As duas somam 100% e concordam quase sempre
  (1 loja de 48 muda de ordem interna; diferença mediana 0,0 p.p.), mas
  divergem até 34,2 p.p. exatamente sobre mês parcial. ILUARA BORGES CABRAL
  (HELP CASCADURA, 5 dias de 21, **melhor R$/dia da loja**): 63,2% pela taxa
  contra 29,0% pelo dinheiro.
- **O share resolve o teto mas move o problema para o ponto neutro**, que passa
  a ser `100 ÷ n` (50% numa loja de dois, 25% numa de quatro; 3,0% a 25,0% nas
  regiões). Por isso a fatia justa é impressa — sem ela o número não se
  interpreta sozinho. Foi o trade-off aceito conscientemente.
- **Fatia na rede foi medida e descartada:** justa 0,82%, máximo 2,76% em 122
  pessoas. Some como leitura de destaque.
- **O corte do slider NÃO migrou para a fatia.** Continua em
  `vs. media da carteira`, a única coluna com o mesmo ponto neutro para todo
  mundo: "até 40%" seria severo numa loja de dois e generoso numa de quatro.
- **Fatia de grupo sem produção é ausente, nunca 0%.** HELP LARANJEIRAS em
  09/2026 (2 pessoas, R$ 0) fica com `NaN` nas duas pessoas — e elas continuam
  sobrevivendo ao corte e abrindo a lista em "Menor fatia da loja", que era o
  fix do achado 2 da entrada anterior.
- **Quem está sozinho na loja marca 100% — e agora isso é verdade.** No índice
  antigo 100% significava "na média de si mesmo" e não dizia nada; na fatia,
  significa "sou toda a produtividade da minha loja".

## Verificação ponta a ponta (banco real)

| Checagem | 08/2026 | 09/2026 |
|---|---|---|
| fatias somam 100% por loja | 48/48 | **47/48** ¹ |
| fatias somam 100% por região | 5/5 | 5/5 |
| fatias fora de 0–100% | 0 | 0 |
| maior fatia == `"1 de N"` | 48/48 lojas | 48/48 lojas |
| sem fatia de loja (`NaN`) | 0 | 2 (HELP LARANJEIRAS) |

¹ A exceção é HELP LARANJEIRAS, onde ninguém vendeu: a fatia é **ausente** nas
duas pessoas, e a soma do grupo dá 0 por ser soma de `NaN`. Comportamento
correto, não divergência.

Acima da fatia justa da própria loja: 59 de 122 (08/2026), 53 de 121 (09/2026).

**704 testes passando** (23 novos no total das duas entradas), `ruff` limpo.

## Pendências / follow-ups

Herdadas da entrada anterior, todas de pé:

- [ ] Ticket médio e share nos Critérios seguem na média aritmética.
- [ ] `variacao_ultima_competencia` casa o mês anterior pelo nome de exibição.
- [ ] O numerador é R$ pago — um segundo eixo em quantidade mediria *throughput*.
- [ ] Base é **vínculo, não presença** (férias e afastamento não descem).

Nova:

- [ ] A métrica `prod_dia` na sub-visão **Critérios** continua com limiares
      relativos por média/percentil, sem noção de fatia. Se a leitura de fatia
      pegar, avaliar expor `BASE_FATIA` lá também.

## Referências

- Entrada anterior desta sessão:
  [2026-09-03-semantica-dos-percentuais-performance-time.md](2026-09-03-semantica-dos-percentuais-performance-time.md)
- Regra atualizada: [business-rules.md](../business-rules.md) — "Fatia e
  comparação — duas perguntas, dois pontos neutros"
