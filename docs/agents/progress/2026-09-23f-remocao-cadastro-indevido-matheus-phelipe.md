# 2026-09-23 — Remoção do cadastro indevido de MATHEUS PHELIPE BANDEIRA DA SILVA

**Agente:** Claude Code
**Tipo:** bugfix (dado, não código)
**Arquivos tocados:** `database/migrations/121_remover_cadastro_indevido_matheus_phelipe.sql`
**Commit(s):** —

## Objetivo

Checar se havia menção a MATHEUS PHELIPE BANDEIRA DA SILVA no banco e, confirmada
a importação indevida (pessoa fora da rede há muito tempo, cadastro criado por ADE
errada do extrator do banco), removê-la sem efeito colateral.

## O que foi feito

- Varredura por nome em `consultores`, `supervisores`, `consultor_vigencia`,
  `supervisor_vigencia`, `consultor_afastamento`, `usuarios`, `usuario_escopos`,
  `reconquista`, `contratos` (como consultor **e** como cliente) e nos dois
  snapshots JSON. Achado em 3 lugares: cadastro, janela de vigência e
  `produtividade_individual_snapshot` 08/2026.
- Confirmado **zero produção** em qualquer status e qualquer mês.
- Migration 121 entregue (não aplicada): bloco de guarda + `DELETE` no ledger +
  `DELETE` no cadastro + queries de verificação + rematerialização obrigatória.

## Decisões não óbvias

- **Por que `DELETE` e não fechar a janela?** Fechar afirma "esteve na loja de
  20/08 até X" e mantém peso no denominador de 08/2026 — o oposto do fato
  declarado. O `CHECK chk_cv_vigencia_ordem` (fim > início) nem permite janela de
  duração zero: para "nunca existiu", o caminho é remover a linha. Fechar continua
  sendo o certo para desligamento de verdade — a 100/115 já cobre esse caso.

- **Por que dois `DELETE` e o do ledger primeiro?** `consultor_vigencia` não tem FK
  para `consultores` (match por `nome_normalizado`), então **não cascateia**.
  Como `fn_headcount_ponderado` (091) lê só o ledger e nunca
  `consultores.status`, apagar só o cadastro tiraria o nome da tela e deixaria o
  peso intacto — o sintoma some, o número mente. Ledger primeiro faz uma
  interrupção no meio cair no lado seguro (cadastro sem janela é detectável pela
  116 em `sem_janela_aberta`; janela sem cadastro não é).

- **Cascata de FK medida, não assumida:** as 4 FKs para `consultores(id)` somam
  **0 linhas** dele (`contratos` SET NULL, `reconquista` SET NULL,
  `usuario_escopos` CASCADE; `reconquista_snapshot` nem existe mais — 031).
  É o que torna o `DELETE` admissível: não há histórico a preservar.

- **Origem confirmada pela operação:** o extrator do banco mandou uma **ADE errada**
  na relação de produção, e veio junto um **contrato antigo**, da época em que a
  pessoa ainda era da rede. O ETL de contratos gravou a linha e, ao fazê-lo, criou
  o cadastro — `uq_consultores_nome_loja` é (nome, loja_id), então par inédito
  INSERE em vez de reconhecer quem já não está na rede. Mesma mecânica de 109
  (JOYCE) e 118 (LIVIA); muda só o veredito.

- **A sequência está nos timestamps** e explica por que hoje não há contrato algum
  apontando para ele: `20/08 15:22` ETL grava a ADE errada → cadastro criado;
  depois a ADE é corrigida na origem e a linha sai de `contratos`; `20/08 20:42` a
  086 roda o backfill e o cadastro, agora sem produção, recebe janela de **piso**.
  Medido: zero contratos gravados na janela 15:00–15:40 de 20/08 e zero contratos
  com `data_cadastro` < 01/08/2026 gravados naquele dia. **A correção do lado da
  produção já aconteceu** — ficou para trás o cadastro e o peso que a 086 lhe deu
  cinco horas depois.

- **Por isso ele é a única `BACKFILL_PISO` do ledger** (1 de 415 — 251
  BACKFILL_PRODUCAO, 121 BACKFILL_CENSURADO, 37 MANUAL, 5 ETL): o piso só dá janela
  a cadastro **sem** produção, e ele era o único cadastro órfão existente no
  instante exato em que a 086 rodou.

- **Assumimos que a operação está certa sobre o vínculo.** A forma dos dados não
  distingue "importado por engano" de "admitido e ainda não vendeu" — igual ao par
  JOYCE (109) / LIVIA (118). Só a operação decide; por isso o veredito é
  declarado, e a migration aborta se aparecer qualquer vínculo.

- **Divergência de superfície é esperada até rematerializar.** Este repo recalcula
  `fn_headcount_ponderado` ao vivo (TTL 30min) inclusive para meses históricos,
  então 08/2026 muda sozinho. O Caderno (bereshit) serve JSONB congelado em 02/09
  e **não** muda. Entre aplicar e rematerializar as duas superfícies discordam de
  agosto — o aviso da 080 valendo literalmente.

## Efeito numérico — previsto x VERIFICADO (migration aplicada 2026-09-23)

HELP SANTA CRUZ PREZUNIC, DU=21. A loja **não** foi tocada pela carga de HC das
20:48 (nenhum dos 8 fechados é dela), então a queda abaixo é inteiramente do DELETE:

| | 08/2026 | 09/2026 |
|---|---|---|
| Peso da loja | 2,4524 → **1,9524** | 3,0000 → **2,0000** |
| Queda | **0,5000** (previ 0,3810 — errado) | 1,0000 (previsão exata) |
| Cabeças | 3 → 2 | 3 → 2 |
| Produtiv./dia-cabeça | R$ 3.993,98 → **R$ 5.016,82** (+25,6%) | R$ 1.629,72 → R$ 2.444,57 (+50,0%) |

Produção inalterada (117 contratos / R$ 205.691,72 em agosto), como previsto.

### Por que a previsão de agosto errou — o piso de 50% da 091

Derivei 0,3810 de `consideredWorkingDays: 8` do
`produtividade_individual_snapshot`, que usa a base `ELIGIBLE_LINK_DAYS`. **Não é a
base da `fn_headcount_ponderado`.** A 091 classifica a redução e só dá fração pura
a quem tem procedência:

```sql
declarado := origem IN ('ETL','MANUAL')  OR afastamento  OR supervisor
-- reducao declarada -> fracao pura
-- reducao inferida  -> greatest(0.5, dias/du)   <- piso de 50%
```

`BACKFILL_PISO` **não** está em `('ETL','MANUAL')` → redução inferida → peso
`greatest(0.5, 8/21)` = **0,5000**. O nome da origem é o próprio mecanismo: a 086
dá a janela, a 091 lhe aplica o piso. Setembro bateu exato porque lá
`dias >= du` → `frac = 1,0`, sem piso envolvido.

**Lição:** para prever efeito no denominador, ler a regra da 091 — nunca derivar do
`consideredWorkingDays` do snapshot de produtividade. São bases diferentes, e para
origem inferida com poucos dias a diferença chega a 31%.

## Carga de HC concorrente (2026-09-23 20:48) — NÃO é efeito desta migration

Entre a medição (17:30) e a aplicação, uma carga de HC rodou e **fechou 8 janelas**
de gente marcada `Desligado (a)`, com `vigencia_fim` retroativo em jul/ago
(`consultor_vigencia`: origem BACKFILL_PRODUCAO 251→244, ETL 5→12). Decompondo a
queda do peso da rede:

| Competência | Rede antes → depois | do DELETE | da carga HC |
|---|---|---|---|
| 08/2026 | 116,4761 → 108,5951 | 0,5000 | **7,3810** |
| 09/2026 | 121,7618 → 112,7618 | 1,0000 | **8,0000** |

Ninguém da loja do MATHEUS está entre os 8 — as duas causas são disjuntas.
É exatamente o cenário que a 095 anteviu: desligamento retroativo mexe em
competência histórica.

## Pendências / follow-ups

- [x] ~~Aplicar a 121 e rodar as verificações.~~ **Feito 2026-09-23:** 10/11 checagens
      OK. A única fora foi o peso previsto de 08/2026 — previsão minha errada (piso de
      50%), não falha da migration. Cadastro e janela confirmados removidos; detector
      116 inalterado (3 divergências / 4 órfãos); produção intacta.
- [ ] **A seção 4 da 121 tem dois números falsificados pela aplicação** (`esperado: peso
      2,0714` em 08/2026, e o peso de rede). A migration está aplicada e é imutável, então
      a correção mora aqui, não lá. Quem reler a 121 deve vir a este registro.
- [ ] Rematerializar: `fn_materializar_caderno(8, 2026)` e `(9, 2026)`. **Agora é bem
      maior do que só esta remoção**: com as 8 janelas fechadas retroativamente, agosto
      move ~7,9 de peso em várias lojas, não 0,5 numa. Conferir loja a loja antes de
      republicar o Caderno.
- [ ] Decidir explicitamente o que fazer com `produtividade_individual_snapshot`
      08/2026, que carrega o nome dele em 6 lugares (1 mensal + 2 semanais, todos
      com `paidEffective` 0): regerar ou aceitar de forma declarada que é uma foto
      de 02/09. Não deixar por omissão.
- [x] ~~Confirmar a origem do registro.~~ **Resolvido (2026-09-23):** ADE errada do
      extrator do banco, com contrato antigo na relação. O `HC_Colaboradores`
      **não** é a origem e não precisa ser mexido — `fn_headcount_replace` (095)
      nunca viu esse nome.
- [ ] Risco de recriação: se o extrator repetir a ADE errada, o cadastro volta pelo
      mesmo caminho. Não requer guarda nova — a 116 passa a acusá-lo em
      `sem_janela_aberta` (cadastro novo, ainda sem janela). Vale olhar o detector
      depois da próxima carga.

## Referências

- Docs consultados: [data-layer.md](../data-layer.md), [business-rules.md](../business-rules.md)
- Migrations relacionadas: 080 (snapshot congelado), 086/087 (ledger de vigência),
  091 (headcount ponderado), 095 (guardas do HC), 116 (detector de vínculo),
  119 (admissões — operação inversa), 100/115 (desligamento fecha janela)
