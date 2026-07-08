# 2026-07-08 — Universo de consultores: dedup por updated_at + exclusão Vai e Vem

**Agente:** Claude Code
**Tipo:** bugfix + feature (regra de negócio)
**Arquivos tocados:** `src/dashboard/loaders.py`, `src/dashboard/kpis/gerais.py`,
`src/dashboard/kpis/pontuacao.py`, `src/dashboard/kpis/rankings.py`,
`src/dashboard/ui/prioridades_acao.py`, `tests/test_loaders.py`,
`tests/test_kpis_gerais.py`, `tests/test_kpis_pontuacao.py`,
`tests/test_kpis_rankings.py`, `tests/test_ui_prioridades_acao.py` (novo),
`docs/agents/business-rules.md`
**Commit(s):** (não commitado nesta sessão)

## Objetivo

Usuário reportou que a listagem de consultores zerados não batia com o RH
(112 ativos, 105 com contrato em julho). Investigação encontrou 42 zerados
na visão global — inflados por cadastro duplicado/obsoleto — e revelou a
regra do Vai e Vem (setor de digitação backoffice, fora de rankings/médias).

## O que foi feito

- Loaders de consultores: colapso de nomes duplicados no registro de
  `updated_at` mais recente (desligamento novo vence `Ativo (a)` antigo) e
  filtro de status por **prefixo** `ativo` (substring aceitaria `Inativo (a)`).
- Nova regra: `LOJAS_BACKOFFICE = {"VAI E VEM"}` + `excluir_lojas_backoffice`
  em `kpis/gerais.py`, aplicados no eixo consultor de rankings/zerados
  (`_preparar`, universos, `listar_sem_producao`) e nas médias por nível
  (valor e pontos) e médias da organização (granularidade supervisor/consultor).
- Cancelados e em análise **não** passam pelo filtro (regra do usuário).
- Testes novos nos 4 arquivos de teste; suíte completa 255 passed; ruff limpo.
- Validação com dados reais de julho/2026: universo sem supervisores caiu de
  145 → 127; zerados de 42 → 23; média por consultor conta 105 (bate com o
  número do usuário).

## Decisões não óbvias

- **Exclusão por LOJA, não por região** — região `ALEXANDRE` = DIGITAL +
  VAI E VEM, e DIGITAL conta nas métricas (confirmado pelo usuário).
- **Loja VAI E VEM segue no ranking/zerados de lojas** — usuário só pediu o
  eixo consultor; comportamento documentado em teste.
- **Filtro no nível dos KPIs, não no loader** — `carregar_consultores_ativos`
  continua global (Amos/Carla seguem em selects de cadastro/Visualizar Como).
- **Status vazio conta como ativo** — preserva linhas legadas sem status
  (comportamento anterior mantido).
- **112 vs 105 do usuário**: no df pago de julho, 112 = produtores distintos
  incluindo supervisores; 105 = sem os 7 supervisores que produziram. A
  diferença de 7 não eram zerados.

## Pendências / follow-ups

- [x] Aceleradores por consultor: regra estendida a pedido do usuário —
  `excluir_lojas_backoffice` em `calcular_aceleradores_consultor`
  (`ui/prioridades_acao.py`), com testes em `test_ui_prioridades_acao.py`.
- [x] Erica Cristina (Ativo mais recente que Licenciado): usuário confirmou
  que ela retornou da licença — cadastro correto.
- [x] Carga do HC_colaboradores rodou em 2026-07-08 17:25 — universo
  reconciliado: 161 = 47 supervisores + 2 Vai e Vem + 110 consultores RH
  + 2 órfãos. Zerados globais (código novo): 10.
- [ ] 2 órfãos `Ativo (a)` restantes (não tocados pela carga — corrigir
  status no cadastro): **TAIS DA SILVA BARRETO** (Caxias Centro, updated
  04/2026) e **HELOISA HELENA MARIA CARLOS** (Caxias Guanabara, updated
  03/2026). Varredura global (todas as regiões, universo de 161) confirmou
  que são os ÚNICOS casos. UPDATE bloqueado pelo classificador de
  permissões — SQL entregue ao usuário p/ rodar no SQL Editor (2 linhas,
  status='Desligado (a)' + updated_at=now()).
- [x] Reflexo automático dos uploads do angry-man: TTLs de cadastro
  reduzidos — `carregar_consultores_cadastro`/`carregar_consultores_ativos`
  86400→1800 e `carregar_supervisores` 21600→1800. Upload reflete em até
  30min (ou na hora via Limpar cache/Gestão).
- [x] Tabela `supervisores` com 5 nomes desligados (Alana Souza, Leonardo
  Meyer, Michele Tinoco, Talita Pinto, Thais Rebello) — usuário confirmou
  desligamento na planilha de supervisores de 2026-07-08. **Sem ação**: a
  tabela não tem coluna status (nome/loja_id/regiao_id), os nomes não
  aparecem em nenhuma superfície da UI nem no headcount, e mantê-los é
  necessário p/ excluir a produção histórica deles (meses passados) dos
  rankings de consultores. NÃO deletar as linhas. Risco só se algum for
  recontratado como consultor (exclusão por nome esconderia a pessoa) —
  aí seria caso de vigência temporal, como loja_regiao_vigencia.
- [ ] Dashboard local rodando desde 12:47 (antes do fix e da carga) —
  reiniciar o `streamlit run` para servir código novo + dados frescos.
- [ ] `contar_consultores` e visões de prioridades/aceleradores por **loja**
  não filtram backoffice — só relevante no caso raro de contrato pago não
  remanejado; fora do escopo por decisão do usuário (eixo consultor apenas).

## Referências

- Docs consultados: [business-rules.md](../business-rules.md),
  [data-layer.md](../data-layer.md)
