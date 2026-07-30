# 2026-07-30 — Gestão: eixos de leitura, critérios relativos e presets (Ondas 2 e 3)

**Agente:** Claude Code
**Tipo:** feature
**Arquivos tocados:** `app.py`, `src/dashboard/kpis/gestao.py`,
`src/dashboard/tabs/gestao_consultores.py`, `src/dashboard/loaders.py`,
`database/migrations/064_gestao_presets.sql`,
`tests/test_gestao_consultores.py`, `tests/test_tabs_gestao_presets.py`
**Commit(s):** (pendente)

## Objetivo

Continuação de [2026-07-30-gestao-criterios-onda-1](2026-07-30-gestao-criterios-onda-1.md).
Entregar as ondas 2 (flexibilidade) e 3 (presets) e fechar o item 4,
que o usuário resolveu: **a coluna `Total` deve somar apenas os
produtos do critério**, não o MIX inteiro.

## O que foi feito

- **Item 4 — `Total` segue o critério.** `construir_tabela` recebe
  `produtos_total`; a aba passa a seleção do multiselect. `Total`
  responde "quanto no que estou olhando". Caption sob o multiselect
  mostra a composição (`Total = CLT + CNC`). Sem seleção, volta ao MIX.
- **Métricas:** valor pago, quantidade de contratos, ticket médio e
  share no mix. Ticket e share são recalculados após qualquer
  agregação — nunca somados nem promediados.
- **Níveis:** Consultor, Loja, Supervisor e Região. A apuração nasce
  sempre por consultor e é rolada para cima: um caminho de cálculo só.
- **Combinação:** E, OU e "pelo menos N critérios".
- **Bases de comparação** por critério: valor absoluto, % da média do
  grupo, % da média da região, percentil do grupo e % da meta.
- **Presets** (`gestao_presets`, migration 064): salvar, aplicar,
  excluir e compartilhar o recorte inteiro em jsonb.
- 27 testes novos (46 no arquivo de KPI + 6 de presets); suíte completa
  em 315 passando, `ruff` limpo.

## Decisões não óbvias

- **Critério irresolúvel é IGNORADO, nunca "ninguém atende".** Um
  filtro `% da meta` sobre produto sem meta zeraria a lista sem
  explicação. `diagnosticar_criterios` devolve os rótulos ignorados e a
  aba avisa. Este é o comportamento de segurança do módulo — qualquer
  base nova deve seguir o mesmo contrato (`_resolver_limiar` → `None`).
- **`% da meta` só existe no nível Consultor e fora do pack.** A meta
  de escopo CONSULTOR é gravada por LOJA (alvo individual de quem
  trabalha ali), então o casamento exige uma loja por linha. E a meta
  `FGTS_ANT_BENEF_13` é **conjunta**: rachá-la em três seria inventar
  número. Os três rótulos do pack ficam sem meta de propósito.
- **Bases relativas leem PERCENTUAL, não valor.** "50% da média",
  "percentil 20", "80% da meta". Um teto fixo em R$ envelhece a cada
  mês; um relativo não — é o que dá vida longa a um preset.
- **Share usa o mesmo escopo do `Total` exibido.** As fatias somam o
  Total que está na tela; se o share olhasse o MIX inteiro enquanto o
  Total olha a seleção, os números da mesma linha não fechariam.
- **Preset é aplicado no run seguinte** (`_gestao_preset_pendente`).
  Streamlit proíbe escrever em `session_state[k]` depois que o widget
  de chave `k` foi instanciado, e o botão "Aplicar" só é clicado depois
  que a aba inteira renderizou. Escrever direto levantava
  `StreamlitAPIException`.
- **`config` em jsonb, sem colunas por eixo.** Os eixos da aba ainda
  estão crescendo; preset antigo sem uma chave cai no default do widget
  em vez de quebrar.
- **RLS da 064 não protege nada hoje — e está documentado assim.** O
  dashboard conecta com service_role (BYPASSRLS), então o recorte "cada
  um vê os seus" é client-side (`carregar_presets_gestao` filtra por
  `usuario_id`; `excluir_preset_gestao` filtra no DELETE). As policies
  são fail-closed e valem para acesso futuro com chave anon. Um preset
  guarda limiares e nomes de produto — nenhum dado pessoal.
- **`usuario_id` validado como UUID** antes de entrar no filtro `or_`
  do PostgREST, que é montado por interpolação de string.
- **Nível Supervisor usa o cadastro de supervisores para AGRUPAR**, uso
  novo: até aqui `df_sup` só servia para excluir. Loja sem supervisor
  cadastrado cai em `(sem supervisor)` em vez de sumir.

## Pendências / follow-ups

- [ ] **Aplicar a migration 064 no Supabase.** Até lá a barra de
      presets mostra "Presets indisponiveis" e o resto da aba funciona
      normalmente.
- [ ] Validar com um gestor se `Total` seguindo o critério é a leitura
      esperada em todas as telas da aba (mudança de semântica em
      relação à onda 1, onde `Total` era sempre o MIX).
- [ ] Sem `st.form`, cada `number_input` refaz a agregação inteira.
      Agora há mais eixos e a matriz por consultor é maior (valor +
      qtd por produto); medir com ~112 consultores antes de decidir.
- [ ] `_norm_nome` segue importado de `kpis/rankings.py`. Com o nível
      Supervisor, o módulo ganhou um terceiro uso do normalizador —
      candidato a promoção para `src/shared/`.

## Patterns criados ou atualizados

Nenhum.
