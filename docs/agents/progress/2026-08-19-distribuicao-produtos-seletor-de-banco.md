# 2026-08-19 — Distribuição de Produtos: toggle BMG/Help vira seletor de banco

**Agente:** Claude Code
**Tipo:** feature
**Arquivos tocados:** `src/dashboard/kpis/produtos.py`,
`src/dashboard/tabs/analiticos.py`, `tests/test_kpis_produtos.py`,
`tests/test_tabs_analiticos.py`, `docs/agents/business-rules.md`
**Commit(s):** (a commitar)

## Objetivo

Em Analíticos → Distribuição de Produtos existia a flag booleana "Somente
BMG/Help". O usuário pediu para trocar por exibição **Todos ou por banco**
(selecionando o banco desejado), por flexibilidade do resumo.

## O que foi feito

- `st.toggle("Somente BMG/Help")` → `st.selectbox("Banco", …)` com
  `Todos` (padrão) | `BMG/Help` (preset composto) | um item por banco
  presente no frame (`_selecionar_banco`, `analiticos.py`).
- Camada KPI generalizada: `somente_bmg_help: bool` → `bancos:
  Optional[Sequence[str]]` em `calcular_distribuicao_produtos` e
  `calcular_distribuicao_produtos_por_loja`. `None`/vazio = sem recorte.
- `_mask_banco_bmg_help(df)` → `_mask_banco(df, bancos)` — mesma
  assinatura que o `_mask_banco` já existente em `tabs/produtos.py`.
- Novos helpers públicos em `kpis/produtos.py`: `canonizar_banco`,
  `opcoes_banco`, `BANCOS_BMG_HELP`.
- Cobertura: 10 testes novos de canonização/opções + AppTest real do
  selectbox (6 casos, incluindo o guard de cascata). Suíte: 600 passando.
- `business-rules.md` § "Reuso em Distribuição de Produtos" reescrita.

## Decisões não óbvias

- **Por que o preset "BMG/Help" continua na lista?** Tirar seria
  regressão para quem já usa o recorte. Ele não é um banco — é o par que
  a régua de comissionamento de CLT/Consignado trata junto —, mas
  convive com opções atômicas na mesma lista de propósito.
- **Por que as abas CLT/Consignado (`tabs/produtos.py`) NÃO mudaram?**
  Lá BMG/Help é regra de negócio (o banco distingue a régua de
  comissionamento); o binário é a pergunta certa. Na Distribuição, que
  cobre todos os grupos, banco é só dimensão de análise. A divergência
  entre as duas superfícies passou a ser **deliberada e documentada**.
- **Por que opções canônicas e não valores crus?** A base não é uniforme
  (`BMG` × `BANCO BMG`, `C6` × `C6 BANK`, `ITAÚ` × `BANCO ITAÚ`). Sem
  canonizar, o mesmo banco viraria duas opções partindo a produção ao
  meio. O `_BANCO_ALIAS` só formaliza equivalências **já declaradas** no
  codebase (`_BANCOS_BMG_HELP` e `_PORTAB_BANCO_TO_CONSIG` do
  `loaders.py`) — não inventa nenhuma.
- **`ITAU-360` ficou fora do mapa de alias de propósito.** É canal
  próprio na base; fundir com `ITAU` seria decisão de negócio, não de
  normalização. Se um dia for para fundir, é escolha do usuário.
- **`BANCOS_BMG_HELP` é derivado, não escrito à mão.**
  `tuple(sorted({canonizar_banco(b) for b in _BANCOS_BMG_HELP}))` — a
  tupla-fonte continua literalmente idêntica à de `tabs/produtos.py`,
  então a nota de sincronização entre os dois arquivos segue válida.
- **Chave de sessão nova (`dist_prod_banco`).** A antiga
  `dist_prod_bmg_help` guardava `bool`; reusar o nome num selectbox
  quebraria toda sessão já aberta.
- **`somente_bmg_help` foi removido, não deprecado** — autorizado pelo
  usuário. Só `analiticos.py` chamava essas funções, então não havia
  outro consumidor a preservar.

## Pendências / follow-ups

- [ ] Validar em produção se a lista de bancos que aparece na
      Distribuição bate com a expectativa do usuário (a `_BANCO_ALIAS`
      cobre as variantes conhecidas hoje; se a base trouxer grafia nova,
      ela aparece como opção própria em vez de fundir).
- [ ] Decidir se `ITAU-360` deve fundir com `ITAU` (hoje: não funde).

## Referências

- Docs consultados:
  [business-rules.md](../business-rules.md) § 'Flag "Somente BMG/Help"',
  [progress/2026-08-06](2026-08-06-plano-clt-consignado-emissao-seguros.md)
  (ST-01, inventário real dos valores de `BANCO`),
  [progress/2026-08-13](2026-08-13-distribuicao-produtos-clt-consignado-toggle-banco.md)
  (origem do toggle que este trabalho substitui).
