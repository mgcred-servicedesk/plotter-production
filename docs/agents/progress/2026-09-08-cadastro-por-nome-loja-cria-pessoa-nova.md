# 2026-09-08 — Contrato com filial errada cria pessoa nova (caso JOYCE / HELP ALCANTARA)

**Agente:** Claude Code
**Tipo:** bugfix / research
**Arquivos tocados:**
`database/migrations/109_vigencia_transferencia_joyce_largo_segunda_feira.sql`,
`database/migrations/110_promocao_hugo_supervisor_madureira.sql`,
`database/migrations/111_mizael_retorno_rio_comprido.sql`,
`database/migrations/112_troca_carolina_thais_pavuna_mesquita.sql`
**Commit(s):** (não commitado — migrations **não aplicadas**)

## Objetivo

O usuário reportou que JOYCE ANNY DA SILVA FOCHT DE JESUS aparecia associada a
HELP ALCANTARA, loja onde nunca trabalhou. Encontrar o erro.

## O que foi feito

Diagnóstico, sem alteração de dado. A cadeia medida no banco em 2026-09-08:

1. **Origem** — 5 ADEs digitadas sob a filial HELP ALCANTARA para ela
   (2 em 02/09, 3 em 03/09), contra 163 contratos em HELP CASCADURA de
   05 a 08/2026.
2. **O ETL de contratos criou a pessoa.** `uq_consultores_nome_loja` é
   **(nome, loja_id)**, então o par inédito (JOYCE, ALCANTARA) **inseriu** uma
   linha nova em vez de reconhecer que JOYCE já existia em CASCADURA. Prova:
   cadastro criado 03/09 15:24:06, primeiro contrato ALCANTARA gravado
   15:24:12 — 6 segundos depois, mesmo lote.
3. **Não foi o RH.** `consultor_vigencia` tinha **0 linhas `origem='ETL'`**
   (265 `BACKFILL_PRODUCAO`, 124 `BACKFILL_CENSURADO`, 9 `MANUAL`, 1 `PISO`) —
   o `fn_headcount_replace` (094/095), única porta do HC_Colaboradores, nunca
   rodou. Não havia transferência declarada.
4. **O desempate promoveu a linha errada.** `_colapsar_cadastro_recente`
   (`loaders.py`) e o `DISTINCT ON (nome_normalizado) … ORDER BY updated_at
   DESC` do SQL escolhem o `updated_at` mais recente: 03/09 venceu 11/08, e
   ALCANTARA virou a loja dela em tudo que lê `consultores` como foto
   (`carregar_consultores_ativos` → sidebar, RLS, universo, chat IA).

**Durante a análise a origem foi reimportada** (04/09 18:50): os 5 contratos
passaram para HELP LARGO DA SEGUNDA FEIRA e um **terceiro** cadastro foi criado
para a loja certa. O usuário confirmou a regra: **a partir de 01/09/2026 ela é
de HELP LARGO DA SEGUNDA FEIRA; antes disso, de HELP CASCADURA.**

Migration **109** escrita (não aplicada): fecha a janela de CASCADURA em
2026-09-01 e abre a de LARGO DA SEGUNDA FEIRA na mesma data, ambas `MANUAL`.

## Decisões não óbvias

- **A proteção de "digitação avulsa" da 087 não alcança este caso.** A regra da
  loja dominante só discrimina quando há **duas lojas no mesmo mês**. Em
  09/2026 os únicos contratos da JOYCE eram os 5 de ALCANTARA — `n_lojas = 1`,
  dominante por unanimidade. A regra não enxerga que o mês anterior inteiro foi
  CASCADURA, então um rebuild do backfill teria fechado CASCADURA e aberto
  ALCANTARA sozinho.
- **`origem = 'MANUAL'` nas duas janelas imuniza a correção**, porque o rebuild
  apaga só `origem LIKE 'BACKFILL%'`. Marcar só a janela nova apagaria o
  histórico anterior a 09/2026 num rebuild.
- **Fronteira em 01/09 (regra declarada), não 02/09 (primeiro contrato)** —
  mesmo critério das 106/107: declarado vence inferido. Usar 02/09 tiraria dela
  o 1º dia útil por inferência.
- **A migration corrige o ledger, não o cadastro.** O cadastro órfão
  (JOYCE, HELP ALCANTARA) ficou de fora de propósito: apagar exige instrução
  explícita e `usuario_escopos.consultor_id` é `ON DELETE CASCADE`.
- **Não há sinal nos dados que separe erro de transferência real.** JOYCE e
  HUGO SANTOS BENTO DA SILVA têm forma idêntica (parou de vender em A, começou
  em B no 1º dia útil do mês); CAROLINA PEREIRA CUSTODIO e THAIS EUFRASIO
  MARTINS têm mês partido entre duas lojas, que é transferência real. O único
  fato que condenou o caso da JOYCE veio da operação — e o do HUGO, que tinha a
  **mesma** assinatura, era legítimo: ele virou supervisor de MADUREIRA em
  01/09. A assinatura não decide nada.
- **Supervisor NÃO perde a janela de consultor** (medido: as 47 janelas de
  supervisão abertas pertencem a 47 pessoas, e todas as 47 têm
  `consultor_vigencia` aberta na própria loja). A exclusão dos rankings é feita
  na LEITURA, por `_fetch_vinculos_consultores` filtrando
  `carregar_supervisores` — nunca pela ausência da janela. Por isso a 110 fecha
  BANGU **e abre** MADUREIRA para o HUGO, em vez de só fechar.
- **O ETL de contratos não é sempre culpado.** No caso do HUGO ele acertou a
  loja; o que faltou foi o **papel**, que nenhuma das duas tabelas de cadastro
  registra. É um terceiro modo de falha, além de "foto velha" (MIZAEL) e
  "ledger velho" (JOYCE).
- **A regra automática da 087 erraria o caso da CAROLINA** — motivo pelo qual a
  112 é `MANUAL` e não espera o backfill. Dentro de 09/2026 as janelas de dias
  dela se sobrepõem (PAVUNA 01–03/09, MESQUITA 03/09), e mês com sobreposição
  cai na cláusula da "loja dominante": PAVUNA levaria o mês inteiro (8
  contratos contra 6) e a transferência sumiria. A 087 documenta a sobreposição
  como discriminador de digitação avulsa quando a minoria é ínfima — mas ela
  não distingue isso de **um avulso caindo no próprio dia da virada**.
- **O corte de 03/09 é também o mais barato para o diagnóstico de origem.** Ele
  deixa 1 contrato da CAROLINA fora da vigência (PAVUNA em 03/09), mas esse
  contrato está `CANCELADO / NÃO PAGO`, logo `paid_effective = 0` e
  `fn_contar_pagamentos_sem_vinculo_origem` não o conta. Cortar em 04/09
  deixaria os 6 de MESQUITA sem vínculo — seis em vez de zero.

## Divergência foto × ledger — medida em 2026-09-08

`consultores` (foto, vencedor do dedup por `updated_at`) contra a janela aberta
de `consultor_vigencia`, sobre 123 ativos não-supervisores. **5 divergências, e
nenhum ativo sem janela aberta:**

| Pessoa | Foto | Ledger | Veredito da operação | Migration |
|---|---|---|---|---|
| JOYCE ANNY DA S. F. DE JESUS | LARGO DA SEGUNDA FEIRA | CASCADURA | foto (transferiu 01/09) | 109 |
| HUGO SANTOS BENTO DA SILVA | MADUREIRA | BANGU | foto (**promovido** 01/09) | 110 |
| MIZAEL BARBOSA NETO | RIO COMPRIDO | LARANJEIRAS | **ledger** (volta só em 04/09) | 111 |
| CAROLINA PEREIRA CUSTODIO | MESQUITA | PAVUNA | foto (trocou 03/09) | 112 |
| THAIS EUFRASIO MARTINS | PAVUNA | MESQUITA | foto (trocou 03/09) | 112 |

**MIZAEL é o falso positivo instrutivo, e continua sendo mesmo depois da 111.**
Até 03/09 o ledger dele estava certo (`MANUAL`, migration 103 — voltara a
LARANJEIRAS em 25/08) e a **foto** é que mentia: o ETL criou o cadastro de RIO
COMPRIDO durante a cobertura temporária de agosto e nunca o moveu de volta. De
04/09 em diante os dois concordam — mas **por coincidência**, porque o cadastro
continua sendo o mesmo resíduo de 13/08, não porque algo foi corrigido.

**Um detector não consegue dizer qual lado está errado.** Nas 5 linhas acima a
foto acerta 4 vezes e erra 1, e nada nos dados separa os casos: só a operação.
Por isso a proposta é diagnóstico, não bloqueio.

## Pendências / follow-ups

- [ ] Aplicar as migrations **109 → 110 → 111 → 112** no Supabase, nessa ordem
      (o usuário aplica; checklist no cabeçalho de cada arquivo). As quatro são
      independentes entre si — a ordem é só a numeração.
- [ ] **BARBARA DE SOUZA PECANHA** entra no denominador de consultores de
      MADUREIRA a partir de 09/2026 (efeito da 110), com zero produção desde
      08/2026. Se ela foi desligada e não apenas devolvida à consultoria, falta
      fechar a `consultor_vigencia` dela com a data real.
- [ ] **Bug sistêmico** — contrato sozinho ainda cria pessoa em loja nova.
      Proposta: função de diagnóstico `foto × ledger` no espírito da 105/095
      (faz o número aparecer; agir continua sendo ato explícito). **Não
      construída** — aguarda decisão.
- [ ] `fn_contar_pagamentos_sem_vinculo_origem` marcava **35 em 09/2026** e
      **17 em 08/2026** (os 17 são o caso ILUARA, cuja migration 106 **não está
      aplicada** — ILUARA ainda tem os 17 contratos de 18/08).

## Referências

- Docs consultados: [business-rules.md](../business-rules.md),
  [data-layer.md](../data-layer.md)
- Migrations: 086, 087 (backfill e loja dominante), 094/095
  (`fn_headcount_replace`), 105 (validação de origem), 106/107 (precedentes de
  reatribuição)
- Entradas relacionadas:
  [2026-09-02-reatribuicao-producao-iluara-patricia.md](2026-09-02-reatribuicao-producao-iluara-patricia.md),
  [2026-09-02-victor-pagamento-pos-transferencia.md](2026-09-02-victor-pagamento-pos-transferencia.md)
