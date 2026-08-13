"""
Cliente Anthropic (Claude) para o chat de IA do dashboard.

Espelha src/config/supabase_client.py: mesma ordem de leitura de
credenciais (st.secrets -> .env), mesmo padrao de singleton.

Prioridade de leitura das credenciais:
1. st.secrets (Streamlit Cloud — secrets.toml)
2. Variaveis de ambiente / .env (desenvolvimento local)
"""
import os

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()


def _get_secret(section: str, key: str, fallback: str = "") -> str:
    """Le credencial de st.secrets (Cloud) ou .env (local)."""
    try:
        import streamlit as st
        return st.secrets[section][key]
    except Exception:
        return os.getenv(key, fallback)


ANTHROPIC_API_KEY: str = _get_secret("anthropic", "ANTHROPIC_API_KEY")
ANTHROPIC_MODEL: str = _get_secret(
    "anthropic", "ANTHROPIC_MODEL", fallback="claude-sonnet-5"
)

_client: Anthropic | None = None


def get_anthropic_client() -> Anthropic:
    """
    Retorna instancia singleton do cliente Anthropic.

    Raises:
        ValueError: Se ANTHROPIC_API_KEY nao estiver configurado.
    """
    global _client

    if _client is not None:
        return _client

    if not ANTHROPIC_API_KEY:
        raise ValueError(
            "ANTHROPIC_API_KEY deve estar configurado "
            "(st.secrets['anthropic'] ou .env) para usar o chat de IA."
        )

    _client = Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client
