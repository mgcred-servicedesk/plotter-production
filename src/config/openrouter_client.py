"""
Cliente OpenRouter para o chat de IA do dashboard.

A OpenRouter e compativel com a API da OpenAI (mesmo formato de
``chat.completions`` e de tool calling), entao reusamos o SDK ``openai``
apontando ``base_url`` para o gateway. Consequencia pratica: o adapter
``_chamar_provider_openai`` de ``chat_ia/agent.py`` serve os dois
providers sem nenhuma linha nova de tool-use.

Espelha src/config/openai_client.py: mesma ordem de leitura de
credenciais (st.secrets -> .env), mesmo padrao de singleton.

Prioridade de leitura das credenciais:
1. st.secrets (Streamlit Cloud - secrets.toml)
2. Variaveis de ambiente / .env (desenvolvimento local)
"""
import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

# O catalogo e uma chamada de UI: se demorar, a aba inteira trava
# esperando. Timeout curto e proposital - o chamador cai no modelo
# configurado e avisa na tela.
TIMEOUT_CATALOGO_S: float = 10.0


def _get_secret(section: str, key: str, fallback: str = "") -> str:
    """Le credencial de st.secrets (Cloud) ou .env (local)."""
    try:
        import streamlit as st

        return st.secrets[section][key]
    except Exception:
        return os.getenv(key, fallback)


OPENROUTER_API_KEY: str = _get_secret("openrouter", "OPENROUTER_API_KEY")
OPENROUTER_MODEL: str = _get_secret(
    "openrouter", "OPENROUTER_MODEL", fallback="qwen/qwen3.8-flash"
)

# Identificacao opcional da app nos rankings da OpenRouter. Nao e
# credencial e nao altera o roteamento - so aparece no painel deles.
OPENROUTER_APP_TITLE: str = _get_secret(
    "openrouter", "OPENROUTER_APP_TITLE", fallback="MGCred Dashboard"
)
OPENROUTER_APP_URL: str = _get_secret("openrouter", "OPENROUTER_APP_URL")

_client: Any | None = None


def get_openrouter_client() -> Any:
    """
    Retorna instancia singleton do cliente OpenRouter.

    Raises:
        ValueError: Se OPENROUTER_API_KEY nao estiver configurado ou se
            o pacote openai (usado como SDK compativel) nao estiver
            instalado.
    """
    global _client

    if _client is not None:
        return _client

    if not OPENROUTER_API_KEY:
        raise ValueError(
            "OPENROUTER_API_KEY deve estar configurado "
            "(st.secrets['openrouter'] ou .env) para usar o chat de IA."
        )

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ValueError(
            "Pacote 'openai' nao encontrado no ambiente. "
            "A OpenRouter usa o SDK da OpenAI como cliente compativel."
        ) from exc

    headers = {"X-Title": OPENROUTER_APP_TITLE}
    if OPENROUTER_APP_URL:
        headers["HTTP-Referer"] = OPENROUTER_APP_URL

    _client = OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        default_headers=headers,
    )
    return _client


def listar_modelos_com_tools() -> list[dict[str, str]]:
    """Catalogo de modelos da OpenRouter que suportam tool calling.

    O filtro ``supported_parameters=tools`` nao e refinamento estetico:
    o chat so responde atraves do laco de tool-use de
    ``chat_ia/agent.py``, e um modelo sem tool calling devolveria texto
    inventado em vez de KPI - exatamente o que o SYSTEM_PROMPT proibe.

    Endpoint publico: nao envia a chave de API, que nao e necessaria
    aqui e nao tem por que trafegar numa chamada de catalogo.

    Returns:
        Lista de ``{"id", "nome"}`` ordenada por ``id`` (o prefixo do id
        e o provedor, entao a ordem alfabetica ja agrupa por familia).

    Raises:
        Exception: qualquer falha de rede/resposta sobe para o chamador.
            Devolver lista vazia aqui viraria "nenhum modelo disponivel"
            na tela - uma falha de rede disfarcada de catalogo vazio.
    """
    import httpx

    resposta = httpx.get(
        f"{OPENROUTER_BASE_URL}/models",
        params={"supported_parameters": "tools"},
        timeout=TIMEOUT_CATALOGO_S,
    )
    resposta.raise_for_status()

    modelos = []
    for modelo in resposta.json().get("data") or []:
        identificador = modelo.get("id")
        if not identificador:
            continue
        modelos.append(
            {
                "id": identificador,
                "nome": modelo.get("name") or identificador,
            }
        )

    if not modelos:
        raise ValueError(
            "OpenRouter respondeu sem nenhum modelo com tool calling."
        )

    return sorted(modelos, key=lambda m: m["id"])
