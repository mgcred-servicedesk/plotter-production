# 2026-08-21 — bereshit adaptado ao headcount ponderado (contrato v1.7)

**Agente:** Claude Code
**Tipo:** feature (cross-repo: `bereshit`) + docs (`angry-man`)
**Arquivos tocados:**
no `bereshit`: `src/data/report-types.ts`, `src/data/report-contract.ts`,
`src/data/report-demo.ts`, `src/domain/reporting.ts`,
`src/domain/report-quality.ts`, `src/domain/report-csv.ts`,
`src/app/productivity-explorer.tsx`, `src/app/page.tsx`, 4 arquivos de teste,
`database/CONTRATO.md`, `docs/CONTRATO_DADOS_V1.md`;
no `angry-man`: `docs/headcount.md` (novo), `CLAUDE.md`, `docs/schema.md`
**Commit(s):** —

## Objetivo

Documentar no `angry-man` o *porquê* das mudanças de headcount, para o agente
de lá evoluir em sincronia. Depois, verificar se o `bereshit` está adequado à
092 — e, não estando, adequá-lo.

## O bereshit não estava adequado, e falhava em silêncio

O parser usa whitelist de chaves, então `weightedHeadcount` e
`countedInRegistry` chegavam no payload e eram **descartados sem erro, sem log
e sem linha perdida**. Os 81 testes passavam. Um falso verde que duraria até a
primeira rematerialização.

Três defeitos, todos medidos antes de tocar em código:

**1. O painel de qualidade passaria a acusar divergência inexistente.**
`report-quality.ts` somava `activeConsultants + excluídos` contra
`activeRegistered`. A 092 tornou `activeConsultants` point-in-time; a
identidade fecha agora sobre `countedInRegistry`.

| competência | identidade antiga | com `countedInRegistry` |
|---|---|---|
| 07/2025 | 152 vs 168 → WARN | 168 vs 168 → OK |
| 03/2026 | 172 vs 168 → WARN | 168 vs 168 → OK |
| 06/2026 | 178 vs 168 → WARN | 168 vs 168 → OK |
| 07/2026 | 168 vs 168 → OK | 168 vs 168 → OK |

07/2026 passava por coincidência: é o único mês em que os dois números batem.

**2. A média da rede somava cabeças enquanto cada loja dividia por peso.**
`productivityBenchmark` produzia uma referência incomparável com as barras que
ela atravessa — lojas apareceriam acima ou abaixo de uma média que não é a
média delas.

**3. A tela ficaria internamente inconsistente.** 13 das 48 lojas de 07/2026
têm peso ≠ cabeças; quem dividisse à mão o que está na própria tela erraria até
**31,9%** (HELP CAXIAS PRES. VARGAS: 110.530,17 publicado contra 75.289,47).

## HELP LARANJEIRAS — a patologia no caso extremo

O usuário reportou que o Caderno mostrava Laranjeiras **sem consultor** em
07/2026, o que contraria o que se sabe da operação. Investigado:

| | snapshot publicado (18/08) | ao vivo com a 092 |
|---|---|---|
| `activeConsultants` | **0** | 2 |
| `productivity` | **0** | 104.231,69 |
| posição | 48ª (última) | 20ª |

A loja produziu R$ 208.463,37 no mês. Ela é a **única** com zero no snapshot; ao
vivo não sobra nenhuma.

A causa é composta, e nenhuma parte dela é bug novo:

- **4 das 6 pessoas** ganharam, em agosto, uma linha de cadastro mais recente em
  **outra loja** — WILMAR → DIGITAL (11/08), MIZAEL → RIO COMPRIDO (13/08),
  VICTOR e CAMILLY → COPACABANA (11/08). A regra "cadastro mais recente por
  nome" (073/085) atribuiu as quatro às lojas de agosto, inclusive em julho.
- **As outras 2** (PAMELA, GABRIELE) são supervisoras e saem por regra.

Sobrou zero. É a foto-do-presente apagando uma loja inteira de um mês em que ela
operou — e conecta com o achado anterior de HELP COPACABANA (+150% a +400%):
VICTOR e CAMILLY são exatamente as pessoas que inflavam COPACABANA no passado.
A mesma transferência, vista dos dois lados.

> **Nenhuma validação de payload detecta isso.** `activeConsultants: 0` é um
> número perfeitamente válido. A única defesa é o Caderno ser republicado sob a
> 092. Registrado em `docs/CONTRATO_DADOS_V1.md` do bereshit como o caso
> concreto da seção 092.

## Decisões não óbvias

- **Campos novos são opcionais, e a ausência é declarada.**
  `diagnostics.missingWeightedHeadcount` sinaliza competência ainda não
  republicada, no mesmo padrão que `missingGoldGoals` já usava. Sem isso a tela
  misturaria dois regimes sem dizer qual está lendo — que é o defeito original
  em nova forma.

- **A queda para cabeças é por LINHA, não global.** Uma competência pré-092 não
  tem peso nenhum, e basta ser consistente dentro dela. Global, uma competência
  parcialmente republicada misturaria bases.

- **Peso 0 é preservado, nunca tratado como ausente.** Zero é legítimo — toda a
  loja afastada o mês inteiro. Confundir com ausência faria a loja cair no
  fallback e voltar a dividir por gente que não estava lá. Coberto por teste.

- **`gente_mes` entrou no export CSV.** Sem a coluna, quem abrisse a planilha
  dividiria pago por `consultores_ativos` e concluiria que o relatório está
  errado — exatamente o que a coluna existe para impedir.

- **A coluna só aparece quando o peso DIFERE da contagem.** Onde os dois são
  iguais, a coluna extra sugere uma distinção que não há.

- **O demo tem `activeConsultants` ≠ `countedInRegistry` de propósito.** Se
  fossem iguais no fixture, um código que lesse o campo errado passaria em todos
  os testes.

## Verificação

`tsc --noEmit` limpo · `eslint` limpo · **90 testes passando** (eram 81; 9 novos)
· `next build` completo. O teste que quebrou na transição foi exatamente o que
codificava a identidade antiga — fez o trabalho dele.

## Documentação do angry-man

Criado `docs/headcount.md` (301 linhas): o porquê, não só o como — foto vs.
ledger, os três ledgers ortogonais, R2/R3, a regra de precedência, os dois bugs
medidos (ERICA e HELOINA), por que `SKIP` existe, por que reabrir vigência não é
efeito colateral de upload. Registrado na tabela de referência do `CLAUDE.md`.

`CLAUDE.md` ganhou a seção **"Este projeto não é dono do schema"** — migrations
moram no `Numeros_venda`, nunca criar sobrecarga de RPC, RPC nova exige **dois**
registros (`RPC_ENDPOINT_MAP` + whitelist da Edge Function) e o redeploy da
função. `docs/schema.md` ganhou os cinco ledgers e a tabela de RPCs de escrita.

## Pendências / follow-ups

- [ ] **Ordem de deploy, agora com número:** bereshit **primeiro**,
      rematerialização **depois**. Invertido, o painel acusa WARNING falso em
      3 das 4 competências verificadas e a produtividade não confere na tela.
- [ ] A árvore do bereshit tem a evolução de UI/UX não commitada junto destas
      mudanças (decisão do usuário em 2026-08-21). Separar no commit se quiser
      diffs isolados.
- [ ] Migration 094 segue pendente de aplicação (ver
      [progress do angry-man](2026-08-21-angry-man-headcount-etl.md)).
- [ ] Redeploy da Edge Function `reconquista-rpc` — whitelist alterada.
- [ ] Passo Python (`carregar_consultores_ativos` com `PESO`) segue pendente.

## Referências

- [progress/2026-08-21-angry-man-headcount-etl.md](2026-08-21-angry-man-headcount-etl.md)
- [progress/2026-08-21-caderno-headcount-ponderado.md](2026-08-21-caderno-headcount-ponderado.md)
- [docs/HEADCOUNT_ETL.md](../../HEADCOUNT_ETL.md)
- `bereshit/database/CONTRATO.md` — histórico do contrato agregado (v1.7)
