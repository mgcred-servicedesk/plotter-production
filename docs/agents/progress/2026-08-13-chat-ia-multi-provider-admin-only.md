# 2026-08-13 — Chat IA multi-provider (admin-only no lançamento)

**Agente:** Windsurf
**Tipo:** feature
**Arquivos tocados:** `src/dashboard/chat_ia/agent.py`, `src/dashboard/tabs/chat_ia.py`, `src/dashboard/permissions.py`, `src/config/openai_client.py`, `src/config/chat_ia_provider.py`, `tests/test_chat_ia_agent.py`, `requirements.txt`

## Objetivo

Desacoplar o chat de IA do provider Anthropic, habilitar arquitetura
agnóstica para OpenAI/Claude com fallback configurável, e manter rollout
inicial somente para admin (demais perfis com estado "Em breve").

## O que foi feito

- `agent.py` foi refatorado para runtime agnóstico com loop manual de
  tool-use preservado, mantendo `tools.py` como única fonte de cálculo
  de KPI.
- Adicionados adapters de chamada para Anthropic e OpenAI, com
  normalização para um histórico canônico em blocos `dict` (`text`,
  `tool_use`, `tool_result`).
- Incluído roteamento por perfil e cadeia de fallback via
  `src/config/chat_ia_provider.py`.
- Criado `src/config/openai_client.py` com leitura de credenciais no
  padrão do projeto (`st.secrets` -> `.env`) e singleton.
- `tabs/chat_ia.py` agora aplica gate `admin-only`; não-admin recebe
  aviso "Em breve" e não executa chamada ao LLM.
- `permissions.py` manteve a aba visível para todos os perfis, com
  comentário atualizado para refletir rollout progressivo.
- `tests/test_chat_ia_agent.py` atualizado para histórico canônico e
  para controle explícito da cadeia de providers; incluído teste de
  fallback entre providers.
- `requirements.txt` recebeu `openai>=1.109.1`.

## Decisões não óbvias

- **Aba visível para todos, uso só admin** — em vez de ocultar a aba por
  perfil, manteve-se visibilidade para comunicar roadmap dentro da
  própria interface.
- **Fallback separado da seleção por perfil** — provider principal vem
  do perfil; estratégia de fallback (`friendly_error`,
  `retry_same_provider_once`, `switch_provider_once`) é decisão isolada
  em chave própria.
- **Histórico canônico no agent** — a UI deixou de depender da forma
  nativa de um SDK específico, reduzindo acoplamento sem alterar a
  renderização existente.

## Pendências / follow-ups

- [ ] Definir mapeamento final de provider por perfil para quando o
      rollout deixar de ser admin-only.
- [ ] Validar em ambiente com credenciais reais o fluxo OpenAI
      (chat.completions + tool calling), além da cobertura unitária.

## Referências

- Docs consultados: [README.md](../README.md),
  [architecture.md](../architecture.md),
  [conventions.md](../conventions.md),
  [ui-components.md](../ui-components.md)
