# 2026-07-30 — Gestão: período personalizado (intervalo livre de datas)

**Agente:** Claude Code
**Tipo:** feature
**Arquivos tocados:** `app.py`, `src/dashboard/loaders.py`,
`src/dashboard/tabs/gestao_consultores.py`,
`tests/test_loaders_intervalo.py`, `tests/test_tabs_gestao_presets.py`
**Commit(s):** (pendente)

## Objetivo

Continuação de [2026-07-30-gestao-ondas-2-e-3](2026-07-30-gestao-ondas-2-e-3.md)
(migration 064 já aplicada no Supabase pelo usuário). Permitir que a aba
apure um intervalo livre de datas (X→Y), **inclusive cobrindo meses
anteriores** ao selecionado na sidebar.

## O que foi feito

- **`carregar_contratos_pagos_intervalo(ini, fim, campo)`**: compõe os
  períodos mensais **já cacheados** por `carregar_contratos_pagos` e
  filtra pelo intervalo. Sem query nova, sem cache próprio (não manter
  segunda cópia dos mesmos contratos — Supabase em Nano).
- **`meses_do_intervalo`** e **`filtrar_por_intervalo`**: helpers puros,
  testáveis sem Supabase.
- **UI**: toggle "Periodo personalizado (ignora o mes da sidebar)",
  seletor de intervalo e seletor do campo de data (pagamento/cadastro).
- **Aviso permanente** quando ativo, dizendo a faixa, o campo e quantos
  meses foram varridos — o número na tela deixou de ser o do mês da
  sidebar e isso não pode ser silencioso.
- **Preset** guarda o intervalo (datas ISO absolutas).
- 26 testes novos; suíte completa em 339 passando, `ruff` limpo.

## Decisões não óbvias

- **A composição por período é exata para PAGAMENTO — e só para ele.**
  `contratos.periodo_id` é derivado de `data_status_pagamento`
  (`schema.sql:364`), então nenhum contrato pago dentro da faixa mora
  fora dos meses da faixa. É o que permite compor meses cacheados em vez
  de criar uma query por data.
- **Por CADASTRO a garantia não vale, e o código compensa.** Contrato
  digitado em maio e pago em julho vive no período de julho. Por isso
  `meses_do_intervalo(..., CAMPO_CADASTRO)` varre de `data_ini` até o
  **mês corrente**, não até `data_fim`. Ainda assim não alcança o que
  for pago depois de hoje — a aba diz isso explicitamente.
- **Teto de 12 meses (`MAX_MESES_INTERVALO`).** O Supabase está em
  compute Nano; varrer ano e meio de contratos derruba a instância antes
  de responder. Preferimos recusar com mensagem a entregar timeout.
- **RLS fica em `app.py`, não na aba.** A aba só escolhe datas; o
  callback injetado aplica `aplicar_rls` + filtros da sidebar sobre o
  resultado. Um intervalo personalizado não pode virar porta para ver o
  que o mês selecionado não mostraria.
- **`% da meta` indisponível no intervalo.** Meta é mensal e não
  descreve faixa livre. Zerar `df_metas` faz a base cair no contrato de
  segurança que já existia (critério ignorado + aviso), sem código novo.
- **`_motivo_meta_indisponivel`** passou a explicar a razão real, na
  ordem em que ela cai (período > nível > pack). Antes o aviso dava
  sempre a razão do pack — mandar o gestor investigar a coisa errada é
  pior do que não avisar.
- **Preset guarda datas absolutas.** Reaplicado noutro mês, volta com as
  mesmas datas — previsível. Faixa móvel ("últimos 30 dias") ficou como
  evolução; seria o análogo temporal das bases relativas de critério.

## Pendências / follow-ups

- [ ] **Faixa móvel no preset** ("últimos N dias", "mês anterior
      fechado"): datas absolutas envelhecem, e presets de período são
      justamente os que o gestor quer reusar todo mês.
- [ ] Medir o custo real de um intervalo de 6–12 meses no Nano antes de
      divulgar a função para todos os gestores. O teto de 12 é um chute
      conservador, não uma medição.
- [ ] O modo cadastro não alcança contrato pago no futuro. Se isso
      incomodar na prática, a saída é uma query por `data_cadastro`
      direto na view (aí sim sem passar por `periodo_id`).
- [ ] Sem `st.form`, mudar uma data recarrega a aba inteira — agora com
      custo de N meses. Candidato natural a `st.form` na próxima rodada.

## Patterns criados ou atualizados

Nenhum.

---

## Adendo — atalhos em pt-BR (mesma data)

O calendário do `st.date_input` é **inglês-only e não há caminho
suportado para traduzi-lo**. Verificado no pacote instalado, não de
memória:

- `st.date_input` não expõe locale (params: `label, value, min_value,
  max_value, key, help, on_change, args, kwargs, format, disabled,
  label_visibility, width, bind`); `streamlit/config.py` não tem opção
  de idioma.
- `index.dkY5s53S.js` embute o objeto de locale do Datepicker do
  BaseWeb com o texto cravado: `quickSelectLabel: "Choose a date
  range"`, `quickSelectPlaceholder: "None"`, `previousMonth`,
  `nextMonth`, `pastWeek`…
- `useIntlLocale.Cu_M7zeK.js` embute **um único** locale do date-fns,
  `code: "en-US"` — origem do "June" do dropdown e do "Su Mo Tu…".
  Nenhum outro locale nem import dinâmico nos bundles.
- CSS não resolve: o popover não tem `data-testid` (só `stDateInput` e
  `stDateInputField`, no campo), e o nome do mês é conteúdo de texto
  dentro de um dropdown — CSS não seleciona por conteúdo.

**Decisão:** em vez de hackear o calendário, reduzir a dependência
dele. Atalhos em português (`Mes atual`, `Mes anterior`, `Ultimos 30
dias`, `Ultimos 3 meses`, `Ano ate agora`) preenchem as datas, e o
aviso do período passou a escrever a faixa por extenso ("de 1º de junho
de 2026 a 30 de junho de 2026"). O calendário segue em inglês para a
faixa irregular, que passa a ser exceção.

### Decisões não óbvias do adendo

- **Atalhos são `st.button`, não `sac.segmented`.** Segmented se
  comporta como rádio: manteria a faixa selecionada e sobrescreveria
  uma edição manual das datas a cada rerun. Atalho é ação de uma vez.
- **Gravam direto na chave do widget, sem o rodeio de rerun** usado
  pelos presets: os botões renderizam ANTES do `date_input` na mesma
  função, então a escrita acontece antes da instanciação — que é o
  padrão suportado pelo Streamlit.
- **"Ultimos 30 dias" conta hoje** como um dos 30 (29 dias para trás).
  **"Ultimos 3 meses"** são 3 meses corridos incluindo o corrente (1º
  dia de 2 meses atrás → hoje), não 90 dias. Ambos com teste.
- **Teste de invariante**: nenhum atalho pode gerar faixa que o loader
  recusaria por `MAX_MESES_INTERVALO`.
- **`MESES_PT` foi para `src/config/settings.py`.** `header.py` e
  `app.py` mantêm cópias locais — não migrei para não misturar limpeza
  não relacionada nesta entrega. Follow-up abaixo.

### Follow-ups do adendo

- [ ] Migrar `_MESES_PT` de `src/dashboard/ui/header.py` e o dict inline
      de `app.py:714` para `MESES_PT` em settings (3 cópias hoje).
- [ ] Se o Streamlit passar a aceitar locale no `date_input`, remover os
      atalhos é opcional — eles ganharam valor próprio, independente do
      idioma.

---

## Adendo 2 — aceleradores como critério e remoção de "Ano até agora"

**Arquivos:** `src/dashboard/kpis/gerais.py`,
`src/dashboard/kpis/rankings.py`, `src/dashboard/kpis/gestao.py`,
`src/dashboard/tabs/gestao_consultores.py`,
`tests/test_gestao_consultores.py`, `tests/test_tabs_gestao_presets.py`

### O que foi feito

- **"Ano ate agora" removido** dos atalhos. Em dezembro varreria 12
  meses num clique — exatamente a consulta que o compute Nano não
  aguenta. Faixas longas seguem possíveis pelo calendário, mas deixam
  de ser acidente.
- **`mascaras_aceleradores` centralizada em `kpis/gerais.py`** e
  consumida por `rankings.py` (que a tinha inline) e pela Gestão.
- **Aceleradores viraram colunas de critério na Gestão** — BMG Med,
  Vida Familiar, Emissão e Super Conta —, sempre em quantidade de
  contratos, seja qual for a métrica dos produtos.
- 20 testes novos; suíte completa em 366 passando, `ruff` limpo.

### Decisões não óbvias

- **Aceleradores são contados FORA do filtro `VALOR > 0`.** Eles chegam
  da consolidação com valor zerado (emissão e seguros), então contá-los
  sobre `df_v` devolveria zero sempre. A matriz passou a guardar
  `df_todos` (só com supervisores excluídos) para isso.
- **Bug real encontrado pelos testes: quem só vendia acelerador não
  aparecia.** A identificação das entidades saía de `df_v`, então um
  consultor cujas únicas linhas têm `VALOR = 0` sumia da apuração
  inteira. Agora sai de `df_todos`. Efeito colateral desejado: com o
  universo do RH desligado, esses consultores passam a aparecer
  zerados em vez de não existir.
- **Acelerador NÃO entra no `Total`.** Somar contratos de seguro com
  reais de CLT não produz número com significado. Fica em colunas
  próprias, depois do Total.
- **A lacuna virou duas.** `calcular_lacuna` ganhou `apenas=`, e a aba
  calcula uma lacuna por unidade (`Falta p/ limiar` na métrica dos
  produtos, `Falta acelerador (qtd)` em contratos). Sem isso a coluna
  somaria R$ com contratos — há teste fixando que a soma indevida daria
  `5001.0`.
- **Base "% da meta" escondida para acelerador**, não só ignorada:
  oferecer um caminho que o filtro depois descarta é pior do que não
  oferecer. Se vier de um preset antigo, cai no aviso — e
  `_motivo_meta_indisponivel` agora reconhece o caso e dá a razão certa.
- **Passo e teto próprios** nos controles de acelerador (passo 1, teto
  padrão 2 contratos). O step de 1.000 dos produtos seria inutilizável.

### Follow-ups

- [ ] Aceleradores não respeitam `conta_pontuacao`/pontuação — são
      contagem pura, como nos rankings. Se a gestão pedir "peso" por
      acelerador, aí sim entra a tabela de pontuação.
- [ ] O universo do RH continua governando só o nível consultor; nos
      demais níveis, entidade sem nenhum contrato no período não
      aparece. Vale decidir se loja/região zeradas devem entrar.

### Adendo 2b — Super Conta: acelerador que também é produto

Verificação levantada pelo usuário. **O comportamento já estava
correto**; o que faltava era torná-lo explícito e travado por teste.

`PRODUTOS_DASHBOARD['CNC'] = ['CNC', 'SUPER_CONTA']` e a consolidação
registra: *"Super Conta: CNC com subtipo especifico — conta valor/pontos
como CNC e tambem e contado como producao Super Conta"*
(`loaders.py:1634`). Na Gestão isso significa:

- o **valor** de uma proposta Super Conta é somado em **CNC** — e no
  `Total`, quando CNC está selecionado;
- a coluna de acelerador acrescenta só a **contagem**, e nunca entra no
  `Total`;
- portanto **não há dupla contagem de dinheiro nem valor perdido**.

Confirmado nas duas formas em que a base traz o registro: `categoria_codigo
= SUPER_CONTA` e `categoria_codigo = CNC` com `SUBTIPO = 'SUPER CONTA'`
(inclusive com sujeira de caixa/espaço).

**Mudanças:**

- `mascaras_aceleradores` passou a preferir a flag canônica
  `is_super_conta` (derivada na consolidação), com fallback por
  `SUBTIPO` para df parcial. Antes recalculava sempre — duas derivações
  da mesma regra, candidatas a divergir.
- 6 testes de regressão travando: valor em CNC, Total contado uma vez,
  contagem separada, comportamento em métrica de quantidade,
  precedência da flag canônica e preservação do valor ao filtrar pelo
  acelerador.
- UI: `ACEL_SUPER_CONTA` ganhou legenda própria no bloco de critério
  ("o valor destas propostas continua somado em CNC"), e o help do
  multiselect diz o mesmo. Sem isso, dá para achar que filtrar por Super
  Conta tira o dinheiro dela do CNC.
