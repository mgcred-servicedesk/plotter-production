# 2026-09-23 — Erro do provider primário mascarado pelo fallback

**Agente:** Claude Code
**Tipo:** bugfix
**Arquivos tocados:** `src/dashboard/chat_ia/agent.py`,
`tests/test_chat_ia_agent.py`, `.env`, `.env.example`,
`src/config/openrouter_client.py`

## Objetivo

Primeiro uso real da aba depois da integração OpenRouter
([2026-09-23-chat-ia-openrouter.md](2026-09-23-chat-ia-openrouter.md)):
a tela pedia `ANTHROPIC_API_KEY` mesmo com a OpenRouter configurada.

## O que foi feito

- **Diagnóstico**: a OpenRouter devolvia `429` —
  `qwen/qwen3.8-27b:free is temporarily rate-limited upstream`,
  `limit_source: upstream_provider_shared_pool`. A chave e a integração
  estavam corretas; o tier `:free` é que estava sem cota.
- **`responder` devolve a mensagem do provider PRIMÁRIO**, não a da
  última tentativa. Com a cadeia `["openrouter", "anthropic"]` e só a
  OpenRouter configurada, o `unavailable` da Anthropic sobrescrevia o
  `api_error` real da OpenRouter.
- **`429` ganhou tratamento próprio** em `_rodar_loop_provider`: cita o
  modelo e manda trocar no seletor, em vez do genérico "tente novamente
  em instantes".
- `OPENROUTER_MODEL` passou de `qwen/qwen3.8-27b:free` para
  `qwen/qwen3.8-flash` no `.env`, no `.env.example` e no fallback do
  client.
- 2 testes de regressão, ambos confirmados por sabotagem.

## Decisões não óbvias

- **A mensagem do primário, não a do último** — o admin configurou UM
  provider; ser mandado configurar outro aponta a investigação para o
  lugar errado. O fallback continua sendo tentado e logado; ele só não
  fala pela falha alheia.
- **`getattr(exc, "status_code", None)` em vez de capturar
  `RateLimitError`** — o agent é agnóstico de SDK de propósito; importar
  o tipo de exceção da OpenAI reintroduziria o acoplamento que o
  histórico canônico eliminou. Anthropic e OpenAI expõem `status_code` do
  mesmo jeito.
- **Distinguir 429 não é cosmético** — "tente novamente em instantes"
  para um modelo cronicamente sem cota manda insistir num caminho que
  não vai abrir.
- **Premissa revista**: o `:free` foi escolhido em 23/09 ciente do risco
  de fila; o risco se materializou no primeiro uso. A alternativa BYOK
  (chave upstream própria em openrouter.ai/settings/integrations) ficou
  registrada mas não foi adotada.

## Validação

- E2E real contra a OpenRouter com `qwen/qwen3.8-flash`: laço completo
  (`tool_use` -> dispatch -> `tool_result` -> resposta), argumentos
  corretos em `comparar_entidades`, resposta ancorada no retorno da tool.
- `1324 testes` passando; `ruff check` limpo.

## Pendências / follow-ups

- [ ] Configurar `st.secrets["openrouter"]` no Streamlit Cloud (o `.env`
      cobre só o local).
- [ ] Rollout além de admin segue pendente desde 2026-08-13.

## Referências

- Progresso anterior:
  [2026-09-23-chat-ia-openrouter.md](2026-09-23-chat-ia-openrouter.md)
