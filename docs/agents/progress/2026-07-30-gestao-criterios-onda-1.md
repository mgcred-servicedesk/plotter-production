# 2026-07-30 — Gestão: universo do RH, limiares inclusivos e novos operadores (Onda 1)

**Agente:** Claude Code
**Tipo:** feature + bugfix
**Arquivos tocados:** `app.py`, `src/dashboard/kpis/gestao.py`,
`src/dashboard/tabs/gestao_consultores.py`,
`tests/test_gestao_consultores.py`
**Commit(s):** (pendente)

## Objetivo

Revisar os filtros avançados da aba Gestão e ampliar a flexibilidade de
acompanhamentos personalizados. A revisão apontou 13 itens; o usuário
aprovou a **Onda 1** (itens 1, 2, 3, 5, 9, 12).

## O que foi feito

- **Universo do RH.** `vendas_mix_por_consultor` aceita `df_universo`
  (de `carregar_consultores_ativos`). Consultor ativo sem nenhum
  pagamento no período entra zerado. Toggle na UI, ligado por padrão.
- **Limiares inclusivos.** `Menor que` (`<`) virou `Até (≤)`. Antes,
  "menor que 15.000" e "entre 0 e 15.000" davam listas diferentes para
  quem tinha exatamente 15.000.
- **Novos operadores:** `A partir de (≥)`, `Sem venda (= 0)`,
  `Com venda (> 0)`, além de `Até` e `Entre`.
- **`Total` como critério de primeira classe** no multiselect —
  `filtrar_por_criterios` já suportava, faltava expor.
- **Região/Loja determinísticas.** Trocado o `("REGIAO", "first")`
  (dependente da ordem das linhas) pela loja de **maior volume** no
  período; e, quando o consultor está no cadastro, pelo próprio
  cadastro (`REGIAO_ATUAL`).
- **Saída acionável.** Resumo com nº de consultores + % do universo,
  produção do grupo e coluna `Falta p/ limiar` (`calcular_lacuna`).
- **`Total` sempre visível** no foco por produto (antes era ocultado).
- 14 testes novos; suíte completa em 288 passando, `ruff` limpo.

## Decisões não óbvias

- **`REGIAO_ATUAL` manda, não a região da venda.** Decisão do usuário:
  a aba lista *pessoas* (a quem o consultor responde hoje), não
  contratos. Diverge da leitura point-in-time de
  [`loja_regiao_vigencia`](../data-layer.md) usada nas somas por região
  — divergência intencional e restrita a esta aba.
- **Quem produziu mas não está no cadastro é mantido** (desligado que
  vendeu no mês), com Loja/Região vindas do contrato. Apuração de
  produção não pode perder valor pago.
- **`_norm_nome` importado de `kpis/rankings.py`** em vez de
  reescrito. É um `_private` cruzando módulos — aceito de propósito:
  se as duas superfícies divergirem no que consideram "o mesmo
  consultor", Gestão e Rankings passam a discordar sobre quem é zerado.
  Se um terceiro consumidor aparecer, promover para `src/shared/`.
- **Universo passa por `_aplicar_filtros_ui`** em `app.py`, ao
  contrário do que Rankings faz. Gestão é uma listagem que precisa
  respeitar a seleção de loja da sidebar, senão traria consultor de
  loja que o usuário filtrou.
- **Modo `zero` não gera lacuna.** "Sair de sem venda" não tem alvo em
  R$ — qualquer valor positivo serve.
- **Alias `menor` preservado** em `filtrar_por_criterios` (agora
  inclusivo), para não quebrar chamadas existentes.
- **Universo excluindo Vai e Vem** espelha `listar_sem_producao`. Sem
  isso, ao ligar o universo, os consultores de backoffice entrariam
  todos zerados e poluiriam qualquer critério de baixa produção.

## Pendências / follow-ups

- [ ] **Onda 2** (flexibilidade): combinação E / OU / "pelo menos N";
      dimensões além de valor (qtd de contratos, ticket médio, % do
      mix); critérios relativos (% da meta, média da região, percentil);
      nível de agregação (loja / supervisor / região).
- [ ] **Onda 3**: presets de critério nomeados e compartilháveis —
      exige decisão de persistência (session_state × JSON em
      `configuracao/` × tabela Supabase com RLS).
- [ ] **Item 4 da revisão, em aberto:** a coluna `Total` soma apenas os
      5 grupos do MIX. Confirmar contra `categorias_produto` se existe
      categoria ativa com `conta_valor=true` fora do MIX — se existir, o
      rótulo `Total` induz erro e precisa virar `Total MIX`.
- [ ] **Item 13:** sem `st.form`, cada `number_input` refaz a agregação
      inteira. Irrelevante em ~112 consultores; revisitar se a Onda 2
      aumentar o custo por rerun.

## Patterns criados ou atualizados

Nenhum.
