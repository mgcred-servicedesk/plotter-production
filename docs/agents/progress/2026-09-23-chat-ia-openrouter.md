# 2026-09-23 — Chat IA via OpenRouter (chave única + seletor de modelo)

**Agente:** Claude Code
**Tipo:** feature
**Arquivos tocados:** `src/config/openrouter_client.py` (novo),
`src/config/chat_ia_provider.py`, `src/dashboard/chat_ia/agent.py`,
`src/dashboard/tabs/chat_ia.py`, `tests/test_chat_ia_agent.py`,
`tests/test_chat_ia_provider.py` (novo), `.env.example`, `requirements.txt`

## Objetivo

Revisar a aba Assistente de IA e passar a aceitar chave e modelos da
OpenRouter, com o modelo escolhível na própria aba.

## O que foi feito

- **`openrouter_client.py`**: singleton do SDK `openai` com
  `base_url=https://openrouter.ai/api/v1`, no mesmo padrão de leitura de
  credenciais dos demais clients (`st.secrets` -> `.env`), mais
  `listar_modelos_com_tools()` (GET público em `/models`, filtro
  `supported_parameters=tools`, timeout de 10s).
- **`chat_ia_provider.py`**: `openrouter` entra em `_PROVIDERS_VALIDOS` e
  vira o default (provider e fallback). O flip binário de fallback deu
  lugar a `_ORDEM_FALLBACK` + `_proximo_provider`. Nova constante
  `PROVIDERS_COM_CATALOGO`.
- **`agent.py`**: ramo `openrouter` em `_resolver_provider` **reusando**
  `_chamar_provider_openai`; ramo em `_mensagem_configuracao`; `responder`
  e `_rodar_loop_provider` ganharam o parâmetro `modelo`.
- **`tabs/chat_ia.py`**: seletor de modelo (365 modelos com tool calling
  no catálogo em 23/09), cacheado 1h por `st.cache_data`, renderizado só
  quando o provider do perfil tem catálogo.
- Ambiente: `openai` (já declarado em `requirements.txt`) estava **ausente
  do `.venv`** e foi instalado; `httpx` passou de transitivo a declarado.

## Decisões não óbvias

- **OpenRouter reusa o adapter da OpenAI, não ganha um próprio** — o
  gateway fala Chat Completions. Zero linha nova de tool-use; o que muda é
  só `base_url` + modelo. Um adapter dedicado seria duplicação pura.
- **Override de modelo só vale para `PROVIDERS_COM_CATALOGO`** — um id de
  gateway (`qwen/qwen3.8-27b:free`) não existe na API direta da Anthropic
  nem da OpenAI; repassá-lo no fallback viraria 404 em vez de resposta.
  A constante é a fonte única lida pelo agent (aplica) e pela aba (mostra
  o seletor).
- **Catálogo filtrado por `supported_parameters=tools`** — não é filtro
  estético: o chat só responde pelo laço de tool-use, e um modelo sem tool
  calling produziria número inventado, exatamente o que o `SYSTEM_PROMPT`
  proíbe.
- **`CHAVE_MODELO` fora de `_chave_escopo` e de `limpar_cache_chat_ia`** —
  modelo é preferência de quem usa, não recorte de dados. Trocar de mês
  reinicia a conversa (fronteira de segurança), mas não desfaz a escolha
  de modelo.
- **Falha de catálogo avisa na tela e cai no modelo configurado** —
  `listar_modelos_com_tools` levanta em vez de devolver lista vazia; lista
  vazia apareceria como "nenhum modelo disponível", falha de rede
  disfarçada de resposta válida.
- **O flip binário antigo não estava incorreto** — com três providers ele
  só não conseguia *expressar* preferência. A troca por `_ORDEM_FALLBACK`
  é de expressividade, não correção de bug.
- **Premissa: `qwen/qwen3.8-27b:free` como padrão** — escolha do usuário,
  ciente de que o tier free da OpenRouter tem rate limit e fila.

## Pendências / follow-ups

- [ ] Configurar `OPENROUTER_API_KEY` no `.env` (e em `st.secrets` no
      Cloud). **Nenhuma chave de LLM existe hoje** em `.env`/`.env.toml`:
      até então a aba respondia "não está configurado" para todo mundo.
- [ ] Validar o fluxo E2E com chave real: tool calling do Qwen3.8 nas 4
      tools e comportamento sob rate limit do tier `:free`.
- [ ] Rollout além de admin continua pendente (gate em `tabs/chat_ia.py`
      inalterado) — segue o follow-up de 2026-08-13.

## Referências

- Progresso anterior:
  [2026-08-13-chat-ia-multi-provider-admin-only.md](2026-08-13-chat-ia-multi-provider-admin-only.md)
- Docs consultados: [conventions.md](../conventions.md),
  [ui-components.md](../ui-components.md)
