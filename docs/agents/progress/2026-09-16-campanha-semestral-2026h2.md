# 2026-09-16 — Campanha Semestral 2026-H2 (aba própria)

**Agente:** Claude Code
**Tipo:** feature + research
**Arquivos tocados:** `app.py`, `src/dashboard/kpis/campanha.py` (novo),
`src/dashboard/tabs/campanha.py` (novo), `src/dashboard/loaders.py`,
`src/dashboard/permissions.py`, `tests/test_kpis_campanha.py` (novo)
**Commit(s):** (branch `feat/campanha-semestral-2026h2`)

## Objetivo

Acompanhar a Campanha Semestral 2026-H2 (01/07 a 31/12/2026, meta de
R$ 75 mi em valor) **sem afetar o dashboard de vendas**. A pergunta
original era Power BI × dashboard Streamlit novo.

## O que foi feito

- Aba **Campanha** no `app.py` (entrypoint único preservado), com janela
  própria — não obedece ao seletor de mês da sidebar.
- `kpis/campanha.py`: regras da campanha isoladas das regras de produção.
- `loaders.carregar_consolidado_intervalo`: consolida mês a mês e soma.
- Suíte com 35 testes; 4 sabotagens verificadas antes do commit.

## Decisões não óbvias

- **Streamlit, não Power BI — e o motivo inverte a intuição.** O
  acoplamento que importa não é código, é o Supabase Nano. A aba compõe
  os meses **já cacheados** por `consolidar_dados`, então carga marginal
  ≈ zero; o Power BI seria um leitor novo e independente varrendo
  `contratos` a cada refresh, disputando o Disk IO Budget que a
  migration 054 existe para proteger. Um projeto Streamlit separado era
  a pior opção: paga a carga dobrada *e* duplica loaders e RLS.

- **Power BI sobre as views produziria número errado.** Medido em
  16/09/2026: 3.665 dos 13.566 pagos da janela (27%) chegam da view com
  `categoria_codigo` NULL — e são exatamente `ANT. DE BENEF.` (2.882) e
  `CLT` (783), **duas das cinco famílias elegíveis**, R$ 4,19 mi. Só
  `_preencher_categoria_fallback` (Python, migration 061) as recupera.
  Power BI lendo `v_contratos_dashboard` direto mostraria a campanha
  ~19% menor, sem erro na tela.

- **Consolidar mês a mês, não concatenar e pontuar de uma vez.** O
  multiplicador `PTS` vem de `obter_pontuacao_periodo(mes, ano)` e muda
  por competência; pontuar o semestre com a tabela de um mês só daria o
  número errado para os outros cinco.

- **Não usar o wrapper público `consolidar_dados`.** Ele escreve o
  diagnóstico de pontuação em `st.session_state`; chamar seis vezes
  sobrescreveria o diagnóstico do período selecionado pelo do último mês
  da campanha — a campanha mexendo no dashboard de vendas pela porta dos
  fundos. `carregar_consolidado_intervalo` chama os wrappers cacheados
  diretamente e descarta o `diag`.

- **Super Conta conta como CNC** (decisão do usuário) — na produção e no
  desempate. São R$ 3,73 mi / 1.586 contratos: a diferença entre 29,1% e
  34,0% da meta.

- **Sem snapshot; a apuração sempre reflete a base atual** (decisão do
  usuário). Contrato pago e depois cancelado sai da base no próximo
  import e deixa a campanha sozinho — por isso **não há** regra de
  exclusão de cancelado no código. Custo aceito: ranking já divulgado
  pode mudar.

- **Ritmo em dias corridos, não dias úteis.** A campanha foi declarada
  por datas de calendário e a meta é um total do semestre, não uma média
  diária. `calcular_dias_uteis` continua sendo a regra do dashboard de
  vendas — outro número, outra pergunta.

- **Dois fail-open corrigidos durante os testes.** `filtrar_elegiveis` e
  `filtrar_janela` devolviam o frame inteiro quando faltava a coluna de
  recorte — somaria SAQUE e emissão na campanha. Agora negam.

- **Bug de pandas com coluna toda-NaT.** Em coluna 100% `NaT`, o
  `.dt.date` devolve `datetime64` em vez de `object` e a comparação com
  `date` levanta `TypeError` — a aba quebraria em vez de dizer "sem
  dados". `filtrar_janela` compara em `Timestamp`, e o limite superior
  virou `< fim + 1 dia` para não descartar pagamento de 31/12 com hora.

## Pendências / follow-ups

- [ ] **CNC_13 antes de novembro.** Está **fora** da campanha: o usuário
      nomeou cinco famílias e `CNC_13` é categoria própria
      (`grupo_meta = FGTS_ANT_BENEF_13`). Em 16/09/2026 não havia nenhum
      contrato CNC_13 na janela, **mas 13º é produto de nov/dez, dentro
      da campanha**. Confirmar e, se entrar, acrescentar `"CNC_13"` à
      família CNC em `kpis/campanha.py`. `test_cnc_13_nao_entra_sem_decisao`
      falha de propósito se alguém mudar sem registrar.
- [ ] **Cache global compartilhado.** O botão "Atualizar Dados" faz
      `st.cache_data.clear()` (`app.py`) e derruba também os seis meses
      da campanha, para todas as sessões. Com a campanha no ar isso ficou
      mais caro. O padrão de limpeza cirúrgica já existe
      (`loaders.CACHES_DE_CALENDARIO`, `feriados_mgmt`) — avaliar.
- [ ] **Power BI como fase 2**, se virar requisito organizacional:
      tabela-fato escrita por este mesmo `kpis/campanha.py`, lida pelo
      Power BI. Nunca Power BI recalculando sobre as views.
- [ ] `v_contratos_cancelados` estoura `statement_timeout` (57014) ao
      filtrar por `data_status_banco` — sem índice para esse filtro.
      Não bloqueia a campanha (que não consulta cancelados), mas é
      armadilha para quem tentar.

## Referências

- Docs consultados: [data-layer.md](../data-layer.md), [rls.md](../rls.md),
  [business-rules.md](../business-rules.md), [conventions.md](../conventions.md)
- Migrations relevantes: `001` (views), `054` (work_mem/Nano), `061`
  (categoria CLT/ANT. DE BENEF.), `067` (valor_consolidado), `080`
  (precedente de materialização), `093` (RLS deny / chave service_role)
