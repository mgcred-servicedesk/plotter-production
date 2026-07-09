# 2026-07-09 — Supervisor aparecendo como consultor (exclusão global)

**Agente:** Claude Code
**Tipo:** fix (regra de negócio / RLS client-side)
**Arquivos tocados:** `app.py`, `src/dashboard/tabs/produtos.py`
**Commit(s):** (ver git log deste dia)

## Objetivo

Relato: em algumas lojas o supervisor saía como consultor (caso
CRISTINA DE ARAUJO RIBEIRO PEREIRA em HELP BANGU) após o rodízio
recente de supervisores entre lojas.

## Diagnóstico

Dois defeitos independentes, expostos pelo rodízio:

1. **Recorte do frame de supervisores antes da exclusão** (`app.py`):
   `aplicar_rls_supervisores` filtrava a lista por escopo
   (gerente_comercial → região; supervisor → loja) ANTES de ela ser
   usada como lista de exclusão em métricas consultor-level. Com o
   registro da Cristina em `supervisores` ainda apontando a loja/
   região antiga (HELP CAMPO GRANDE CALCADAO / ROBSON), quem via a
   região GLENDA recebia a lista sem ela — e os 2 contratos digitados
   por ela em HELP BANGU apareciam como de consultora. Admin/gestor
   não viam o bug (lista completa). Rankings também não (já recebia
   `df_sup_full`). Reproduzido e comprovado com dados reais de jul.
2. **Exclusão morta na aba Produtos** (`tabs/produtos.py`,
   `_render_produto_regional`): checava `"CONSULTOR" in
   df_sup.columns`, mas `carregar_supervisores()` devolve a coluna
   `SUPERVISOR` — o no-op silencioso fazia supervisores aparecerem
   nas tabelas regionais/por-loja de produtos para TODOS os perfis.

## O que foi feito

- `app.py`: o frame de supervisores **não é mais recortado** por
  escopo (removidas as 2 chamadas de `aplicar_rls_supervisores` e o
  import). A lista serve exclusivamente para EXCLUSÃO — nenhum
  consumidor a exibe (auditados: sidebar subselect, kpis gerais,
  médias por nível, pontuação, detalhes de cards, prioridades de
  ação, produtos, regiões, analíticos, em análise, gestão) — logo a
  lista global é a correta em qualquer visão.
- `tabs/produtos.py`: coluna corrigida para `SUPERVISOR` (+ dropna).
- Verificação: simulação da visão gerente GLENDA — antes 2 contratos
  vazavam, depois 0; 259 testes verdes; ruff limpo.

## Decisões não óbvias

- **`aplicar_rls_supervisores` (rls.py) ficou sem chamador** — NÃO
  removida (regra do projeto: nunca apagar unilateralmente). Se a
  decisão for manter exclusão sempre global, pode ser dropada em
  follow-up.
- Exclusão por lista global não vaza dados: os nomes de supervisores
  nunca são renderizados; só filtram linhas para fora.
- A correção de código torna o dashboard robusto a cadastro
  desatualizado, mas **não substitui** a correção do dado na origem.

## Divergências de cadastro encontradas (corrigir na origem/angry-man)

Rodízio não refletido na tabela `supervisores` (registro → real):

- CRISTINA DE ARAUJO RIBEIRO PEREIRA: CAMPO GRANDE CALCADAO (ROBSON)
  → HELP BANGU (GLENDA) — 2 contratos em jul na Bangu.
- ISABELE DA SILVA TRINDADE DE SOUZA: HELP BANGU (GLENDA) →
  HELP SANTA CRUZ PREZUNIC (ROBSON) — 1 contrato em jul.
- TAMIRIS DA CONCEICAO ARRUDA: HELP SANTA CRUZ PREZUNIC (ROBSON) →
  HELP CAMPO GRANDE CALCADAO (ROBSON) — 1 contrato em jul.
- LUCIANA DE OLIVEIRA SOUZA ↔ TIAGO FELIPE RIBEIRO: trocaram
  (LARGO DA SEGUNDA FEIRA ↔ RIO COMPRIDO), registros não trocados.
- MONICA OLIVEIRA DOS SANTOS DA HORA: **duplicada** em `supervisores`
  (HELP PAVUNA e HELP VILAR DOS TELES, ambas SANDRA) — uma é resto.

Obs.: 47 dos 52 supervisores também constam como "consultor ativo"
em `consultores` (roster do RH lista todo mundo) — é o esperado; a
exclusão por nome existe exatamente para isso.

## Pendências / follow-ups

- [ ] Usuário: corrigir alocação dos supervisores na planilha/cadastro
      que alimenta o angry-man (lista acima) + remover a linha
      duplicada da MONICA. UPDATE manual no banco é revertido pelo
      upsert integral do ETL a cada import.
- [ ] Decidir destino de `aplicar_rls_supervisores` (sem chamadores).
- [ ] Possível melhoria: normalizar comparação em
      `excluir_supervisores` (strip/upper) como produtos.py faz —
      hoje o match é exato e funciona porque ETL uniformiza.

## Referências

- Regra: [business-rules.md](../business-rules.md) — "Exclusão de supervisores"
- RLS client-side: [rls.md](../rls.md)

## Continuação (mesma sessão) — migration 062

Usuário decidiu conciliar `supervisores` com o roster do RH. Criada
`database/migrations/062_conciliar_supervisores_rh.sql`: DELETE do
par (nome, loja antiga) + INSERT do par correto com `ON CONFLICT
(nome, loja_id) DO NOTHING` para os 5 remanejados + DELETE da
duplicata da MONICA (VILAR DOS TELES; PAVUNA já estava correta).

Decisão não óbvia: **DELETE+INSERT em vez de UPDATE** — o
`importSupervisores` do angry-man (configuracao/Supervisores.xlsx,
upsert `onConflict nome,loja_id`) nunca remove o par antigo em
remanejamento (origem da duplicata da MONICA); se a planilha for
corrigida/importada antes da migration, o par novo já existe e um
UPDATE violaria `uq_supervisores_nome_loja`. O padrão adotado é
idempotente e independe da ordem.

Pendências adicionais:

- [ ] Usuário: corrigir as 5 lojas em `configuracao/Supervisores.xlsx`
      (angry-man) ANTES do próximo import — senão os pares antigos
      são re-inseridos.
- [ ] angry-man: importSupervisores deveria remover pares ausentes
      da planilha (replace-style, como pagamentos_online) para o
      problema não voltar a cada rodízio.
