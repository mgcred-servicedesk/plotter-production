"""
Configuracao de provider do chat de IA por perfil.

Centraliza roteamento de provider/modelo e estrategia de fallback, com
leitura de configuracao em st.secrets (Cloud) e .env (local).
"""
import os

from dotenv import load_dotenv

load_dotenv()

_PROVIDERS_VALIDOS = {"anthropic", "openai", "openrouter"}

# Ordem de preferencia para escolher um fallback quando a chave
# CHAT_IA_FALLBACK_PROVIDER aponta para o MESMO provider primario.
# Com tres providers nao da mais para "inverter" um par: a escolha
# precisa ser declarada em algum lugar, e e aqui.
_ORDEM_FALLBACK: tuple[str, ...] = ("openrouter", "anthropic", "openai")

# Providers cujo modelo pode ser escolhido em runtime (a OpenRouter
# publica um catalogo; Anthropic e OpenAI diretas usam o modelo fixo
# da configuracao). Consumido pelo agent (aplica o override) e pela
# aba (decide se mostra o seletor) - uma fonte so para os dois.
PROVIDERS_COM_CATALOGO: frozenset[str] = frozenset({"openrouter"})

_MODOS_FALLBACK_VALIDOS = {
    "friendly_error",
    "retry_same_provider_once",
    "switch_provider_once",
}


def _get_secret(section: str, key: str, fallback: str = "") -> str:
    """Le credencial de st.secrets (Cloud) ou .env (local)."""
    try:
        import streamlit as st

        return st.secrets[section][key]
    except Exception:
        return os.getenv(key, fallback)


def _normalizar_provider(valor: str, fallback: str = "openrouter") -> str:
    provider = (valor or "").strip().lower()
    if provider in _PROVIDERS_VALIDOS:
        return provider
    return fallback


def _normalizar_modo_fallback(
    valor: str, fallback: str = "friendly_error"
) -> str:
    modo = (valor or "").strip().lower()
    if modo in _MODOS_FALLBACK_VALIDOS:
        return modo
    return fallback


CHAT_IA_PROVIDER_DEFAULT: str = _normalizar_provider(
    _get_secret("chat_ia", "CHAT_IA_PROVIDER_DEFAULT", fallback="openrouter")
)

CHAT_IA_PROVIDER_POR_PERFIL: dict[str, str] = {
    "admin": _normalizar_provider(
        _get_secret(
            "chat_ia",
            "CHAT_IA_PROVIDER_ADMIN",
            fallback=CHAT_IA_PROVIDER_DEFAULT,
        ),
        fallback=CHAT_IA_PROVIDER_DEFAULT,
    ),
    "gestor": _normalizar_provider(
        _get_secret(
            "chat_ia",
            "CHAT_IA_PROVIDER_GESTOR",
            fallback=CHAT_IA_PROVIDER_DEFAULT,
        ),
        fallback=CHAT_IA_PROVIDER_DEFAULT,
    ),
    "gerente_comercial": _normalizar_provider(
        _get_secret(
            "chat_ia",
            "CHAT_IA_PROVIDER_GERENTE_COMERCIAL",
            fallback=CHAT_IA_PROVIDER_DEFAULT,
        ),
        fallback=CHAT_IA_PROVIDER_DEFAULT,
    ),
    "supervisor": _normalizar_provider(
        _get_secret(
            "chat_ia",
            "CHAT_IA_PROVIDER_SUPERVISOR",
            fallback=CHAT_IA_PROVIDER_DEFAULT,
        ),
        fallback=CHAT_IA_PROVIDER_DEFAULT,
    ),
    "consultor": _normalizar_provider(
        _get_secret(
            "chat_ia",
            "CHAT_IA_PROVIDER_CONSULTOR",
            fallback=CHAT_IA_PROVIDER_DEFAULT,
        ),
        fallback=CHAT_IA_PROVIDER_DEFAULT,
    ),
}

CHAT_IA_FALLBACK_MODE: str = _normalizar_modo_fallback(
    _get_secret(
        "chat_ia", "CHAT_IA_FALLBACK_MODE", fallback="switch_provider_once"
    )
)

CHAT_IA_FALLBACK_PROVIDER: str = _normalizar_provider(
    _get_secret(
        "chat_ia", "CHAT_IA_FALLBACK_PROVIDER", fallback="openrouter"
    ),
    fallback="openrouter",
)


def _proximo_provider(primario: str) -> str:
    """Primeiro provider de ``_ORDEM_FALLBACK`` diferente do primario."""
    for candidato in _ORDEM_FALLBACK:
        if candidato != primario:
            return candidato
    return primario


def provider_por_perfil(perfil: str | None) -> str:
    """Resolve provider preferencial para o perfil informado."""
    if not perfil:
        return CHAT_IA_PROVIDER_DEFAULT
    return CHAT_IA_PROVIDER_POR_PERFIL.get(perfil, CHAT_IA_PROVIDER_DEFAULT)


def providers_para_tentativa(perfil: str | None) -> list[str]:
    """Retorna cadeia de tentativa segundo estrategia de fallback."""
    primario = provider_por_perfil(perfil)

    if CHAT_IA_FALLBACK_MODE == "friendly_error":
        return [primario]

    if CHAT_IA_FALLBACK_MODE == "retry_same_provider_once":
        return [primario, primario]

    if CHAT_IA_FALLBACK_MODE == "switch_provider_once":
        fallback = CHAT_IA_FALLBACK_PROVIDER
        if fallback == primario:
            fallback = _proximo_provider(primario)
        return [primario, fallback]

    return [primario]
