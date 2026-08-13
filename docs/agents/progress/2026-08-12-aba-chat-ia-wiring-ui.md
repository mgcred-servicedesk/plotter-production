# 2026-08-12 — Aba "Assistente IA": UI e wiring

**Agente:** Claude Code (subagente `ui-dash`)
**Tipo:** feature
**Arquivos tocados:** `src/dashboard/tabs/chat_ia.py` (novo), `app.py`,
`src/dashboard/permissions.py`

## Objetivo

Expor no dashboard o chat de IA (Claude com tool-use sobre as funcoes de
KPI ja existentes): criar o tab renderer, montar o `ChatContext` em
`app.py` e liberar a chave de permissao. O `chat_ia/tools.py` e o
`chat_ia/agent.py` ja existiam prontos.

## O que foi feito

- `tabs/chat_ia.py` com `render_tab_chat_ia(contexto)`: divider `sac`,
  historico em `st.chat_message`, `st.chat_input` e spinner no padrao
  `:shimmer[...]` da casa.
- `app.py`: `chat_context` inicia `None` fora do bloco
  `if pode_ver("cards_gerenciais", role):` e so e preenchido dentro
  dele (onde `kpis_analise`, `kpis_cancel`, `medias` e `kpis_qtd`
  existem). Entrada nova no `registro_abas` trata `None` com `st.info`.
- `permissions.py`: chave `tab_chat_ia`, `True` para os cinco perfis.

## Decisoes nao obvias

- **A UI nao acrescenta a pergunta ao historico antes de chamar
  `responder`.** O briefing pedia isso, mas `agent.responder` ja monta
  `[*historico, {"role": "user", "content": pergunta}]` internamente e
  devolve o historico completo — pre-acrescentar duplicaria a pergunta
  no payload da Messages API e na tela. O codigo e a fonte da verdade.
- **Chave de validade da conversa tem SEIS componentes, nao cinco.** O
  briefing listava `(mes, ano, role, lojas, consultor)`; usamos os
  mesmos seis de `_chave_kpis` / `_chave_mes_comparativo`, incluindo o
  **escopo do perfil efetivo**. Sem ele, um admin em "Visualizar Como"
  alternando entre dois gerentes de mesmo `role` mantinha na tela texto
  calculado para o escopo do outro — exatamente o vazamento que a
  invalidacao existe para impedir. Segue o precedente de
  `tabs/produtos.py` (`_obter_perfil_efetivo()` lido dentro da aba).
- **Erro do agent vira `st.warning` separado, nao turno de conversa.**
  `responder` devolve o historico ORIGINAL quando falha (API ausente,
  rede, limite de turnos), entao o texto amigavel nao entra no
  historico. A aba detecta pelo tamanho (`len(novo) > turnos_antes`) e
  guarda o texto em `chat_ia_aviso`, limpo no proximo sucesso e no
  reset de escopo. Sem isso a pergunta sumiria sem explicacao.
- **O aviso de "conversa reiniciada" so aparece se havia conversa.**
  Comparar a chave contra `session_state` vazio dispararia o aviso na
  primeira visita a aba.
- **Icone `smart_toy`** (Material Symbols, validado em
  `ALL_MATERIAL_ICONS`) — `forum` le como forum de discussao.

## Pendencias / follow-ups

- [ ] "Atualizar Dados" (`_limpar_caches_periodo`) nao limpa a conversa.
      O escopo nao mudou, entao nao ha vazamento — mas os numeros
      citados em respostas antigas ficam desatualizados. Se for para
      limpar, o dono do estado e `tabs/chat_ia.py` e deve expor uma
      funcao de limpeza chamada por `app.py` (padrao de
      `limpar_cache_comparativos`).
- [ ] Docstring de `permissions.py` nao documenta `tab_gestao` (lacuna
      pre-existente, nao tocada aqui para nao misturar escopo).

## Referencias

- Docs consultados: [ui-components.md](../ui-components.md),
  [conventions.md](../conventions.md), [rpi-workflow.md](../rpi-workflow.md)
