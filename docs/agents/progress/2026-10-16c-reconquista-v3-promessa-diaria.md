# 2026-10-16 — Reconquista V3: Promessas saem da Promessa Diária do banco

**Agente:** Claude Code (orquestrador + subagentes; esta entrada: `biz-rules`, ST-09)
**Tipo:** feature (cross-repo: Numeros_venda + angry-man)
**Arquivos tocados:**
- Numeros_venda:
  - `database/migrations/137_reconquista_promessa.sql` (**aplicada** no Supabase pelo usuário em 2026-10-16)
  - `src/dashboard/kpis/reconquista.py`
  - `src/dashboard/loaders.py`
  - `src/dashboard/ui/kpi_cards_reforma.py`
  - `src/dashboard/tabs/analiticos.py`
  - testes (escritos em paralelo por outro subagente)
  - docs: `business-rules.md`, `data-layer.md`, `architecture.md`, `ui-components.md`
- angry-man:
  - `src/services/import-reconquista-promessa.ts` (novo)
  - `src/services/import-registry.ts`
  - `src/lib/supabase.ts`
  - `supabase/functions/reconquista-rpc/index.ts`
  - `docs/importacao.md`
  - teste vitest
**Commit(s):** — (não commitado)

## Objetivo

A partir da apuração de 09/2026, o card **Promessas** da Reconquista passa
a ser a contagem do arquivo **Promessa Diária** do banco
(`Promessa_diaria.xlsx`, aba `Export`), pelo mês de `dt_promessa`. Antes
disso, o legado do export fica intocado. Entra uma sub-aba analítica
"Promessa Diária".

## O que foi feito

- **Migration 137**:
  - tabela `reconquista_promessa`, por `periodo_id`, ADE única por período;
  - deny explícito para anon/authenticated + REVOKE, igual à 127;
  - view `v_reconquista_promessa` (`security_invoker`), com os mesmos
    nomes de loja/região/consultor da liga;
  - RPC `fn_importar_reconquista_promessa(p_periodo_id, p_rows)`,
    set-based, só `service_role`.
- **Regras** (`kpis/reconquista.py`): `_PROMESSA_V3_INICIO`, estados
  `PROMESSA_*`, `promessa_v3_vigente`, `totais_promessa`,
  `marcar_efetivada`, `promessas_por_loja`, `promessas_por_consultor`.
- **Loader** (`carregar_reconquista`): `_promessa_periodo` (global, TTL
  10min), `_liga_desde` para o badge, `totais["promessa_status"]`, frames
  `promessas`, `promessas_por_loja`, `promessas_por_consultor`.
- **Card**: valor = elegíveis do mês, sem variação vs mês anterior,
  subtexto com retorno INSS, já efetivadas e não elegíveis; "—" + aviso
  sem import ou com erro.
- **Analítico**: sub-aba "Promessa Diária" entre Liga e Por Loja, com
  métricas, filtros, detalhe com badge, quebras por loja e consultor e CSV.
- **angry-man**: card "Reconquista — Promessa Diária" com período
  obrigatório; RPC registrada no `RPC_ENDPOINT_MAP` e na Edge Function.
- **Migration verificada após aplicar**: objetos criados, RLS ligado, RPC
  só para `service_role`, 0 colunas LGPD.

## Decisões não óbvias

- **Contagem = `elegivel = true`, fluxo.** `PROMESSA` e `FDR E PROMESSA`
  contam (FDR = Fim De Relacionamento). Entram todas as promessas feitas no
  mês, inclusive as que depois efetivaram. `retorno_inss` não filtra: só
  vira insight.
- **Período = mês de `dt_promessa`, sem defasagem.** Mesmo racional da
  liga: a defasagem do export deslocaria a promessa de mês.
- **Flag desconhecida rejeita, não vira ELEGIVEL.** No export, NULL =
  ELEGIVEL era um interim. Aqui a flag é a própria conta, então um default
  inventaria promessas.
- **Duplicata bloqueia o import inteiro, sem `ON CONFLICT DO NOTHING`.**
  "Ficar a primeira" esconderia um arquivo inconsistente. Lote vazio
  também é recusado: com DELETE + INSERT ele apagaria o período em
  silêncio, e "não importada" já é um estado explícito do dashboard.
- **RPC recusa chave fora da lista fechada.** É a barreira de LGPD: um
  importador que passe a enviar `nu_matricula` falha alto, em vez de a
  coluna ser descartada em silêncio.
- **RPC set-based**, como a 134, e `elegivel` derivado na RPC (não no
  importador), para a regra ter uma fonte só.
- **Supervisor pelo cadastro, não pela coluna do arquivo.** Caso real:
  ERICA CRISTINA MARINS DA SILVA ROSA vem como supervisora no arquivo, mas
  não está no cadastro, então conta como consultora. Supervisor fica fora
  só da visão por consultor; na loja conta e é listado. Sem cadastro, a
  quebra por consultor é `None` (aviso), nunca montada com supervisores.
- **Badge pela liga GLOBAL, antes do RLS.** A liga pode atribuir a
  efetivação a outra loja. Cruzar com a liga já recortada daria falso
  "não efetivada" para o gerente. O cruzamento só expõe booleano + mês.
- **Falha da liga ⇒ badge "indisponível", nunca "não efetivada".**
  `promessas_efetivadas = None`, filtro "Efetivada" desabilitado.
- **`_liga_desde` lê período a período.** Em `v_reconquista_liga` o
  `co_adesao` é único só por período. Um keyset multi-período pularia
  linhas na virada de página, justamente o período mais antigo da ADE,
  que define `efetivada_ref`. Cada período reaproveita o cache de
  `_liga_periodo`, então o mês selecionado não custa request novo.
- **`efetivadas` → `promessas_efetivadas`** (`_totais_promessa_no_card`).
  Sem o rename, o `totais.update` sobrescreveria `totais["efetivadas"]`,
  a contagem da liga que alimenta o card de Efetivadas, o acelerador e a
  faixa agregada.
- **% com ponto no card** (`:.1f`), seguindo o padrão do módulo:
  `_card_contexto` troca "," por "." no card inteiro.
- **Constante própria `_PROMESSA_V3_INICIO`**, separada de `_LIGA_INICIO`,
  embora hoje coincidam: são regras diferentes e podem se separar. O card
  tem um ramo defensivo para esse caso.
- **"Clientes na esteira" e a coluna Promessas de Por Loja seguem do
  export neste ciclo.** Decisão do usuário: escopo fechado no card e na
  sub-aba nova.

**Números de referência** (arquivo lido em 16/10/2026, antes do import):

| Período | Linhas | Elegíveis | Não elegíveis | Retorno entre elegíveis | FDR E PROMESSA | sem_consultor esperado |
|---|---|---|---|---|---|---|
| 09/2026 | 161 | 153 | 8 | 151 aceitos, 2 não aceitos | 77 | 3 |
| 10/2026 (até 15/10) | 55 | 42 | 13 | 10 aceitos, 32 pendentes | 0 | 1 |

- `descartadas` esperadas: 55 no import de 09/2026, 161 no de 10/2026.
- 50 das 216 ADEs não existem no export; 0 cruzam com a liga de 09/2026.
- O dashboard antigo mostrava 49 (set) e 86 (out) pelo export.
- `sem_consultor`: LETICIA VIEIRA GOMES @50151 (sem cadastro), LETICIA
  GONCALVES DA COSTA @49889 (2 ADEs; cadastrada em 49886) e ERICA @49820
  (sem cadastro).

## Pendências / follow-ups

- [ ] Redeploy da Edge Function `reconquista-rpc` (angry-man) com a nova
      RPC na lista de permitidas.
- [ ] Release do angry-man com o card "Reconquista — Promessa Diária".
- [ ] Importar 09/2026 e 10/2026.
- [ ] Validação pós-import contra a tabela acima (inseridos, elegíveis,
      descartadas, sem_loja = 0, sem_consultor) e conferência do card.
- [ ] Hardening: `REVOKE` dos grants padrão do Supabase para
      anon/authenticated nas views `v_reconquista_liga` (desde a 127) e
      `v_reconquista_promessa`. Hoje é inócuo (`security_invoker` +
      tabela com deny/REVOKE). Exige migration nova.
- [ ] Rotular "(export)" o bloco "Clientes na esteira" e a coluna
      Promessas de Por Loja.
- [ ] Pré-existente: o acelerador ainda derruba o bloco Reconquista se
      `carregar_supervisores` falhar (a Promessa V3 já trata a falha à
      parte).
- [ ] Pré-existente: falha de
      `tests/test_kpis_gerais.py::TestObterMediasPeriodo::test_cache_e_dict_com_as_chaves_de_medias_du_por_nivel`,
      sem relação com esta entrega.
- [ ] Doc fora de escopo corrigido de passagem: `ui-components.md` ainda
      citava o escopo "Fim de relacionamento · mês" do Detalhamento,
      removido em 02/10/2026.

## Patterns criados ou atualizados

- Nenhum. O desenho de estados (`*_FORA/OK/NAO_IMPORTADA/ERRO`, vazio
  decidido antes do RLS) repete a liga e o Prestamista. Vale avaliar um
  pattern "fonte por período com estado explícito" se aparecer uma quarta.

## Referências

- Contrato aprovado pelo usuário em 2026-10-16 (Reconquista V3 / Promessa
  Diária).
- Docs: [business-rules.md § Promessa Diária](../business-rules.md#promessa-diária--promessas-a-partir-de-092026-v3),
  [data-layer.md](../data-layer.md), [2026-10-02 — liga](2026-10-02-reconquista-liga-apuracao-oficial.md).
