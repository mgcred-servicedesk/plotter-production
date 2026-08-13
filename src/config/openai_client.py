"""
Cliente OpenAI para o chat de IA do dashboard.

Espelha src/config/supabase_client.py: mesma ordem de leitura de
credenciais (st.secrets -> .env), mesmo padrao de singleton.

Prioridade de leitura das credenciais:
1. st.secrets (Streamlit Cloud — secrets.toml)
2. Variaveis de ambiente / .env (desenvolvimento local)
"""
import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()


def _get_secret(section: str, key: str, fallback: str = "") -> str:
    """Le credencial de st.secrets (Cloud) ou .env (local)."""
    try:
        import streamlit as st

        return st.secrets[section][key]
    except Exception:
        return os.getenv(key, fallback)


OPENAI_API_KEY: str = _get_secret("openai", "OPENAI_API_KEY")
OPENAI_MODEL: str = _get_secret(
    "openai", "OPENAI_MODEL", fallback="gpt-4.1-mini"
)

_client: Any | None = None


def get_openai_client() -> Any:
    """
    Retorna instancia singleton do cliente OpenAI.

    Raises:
        ValueError: Se OPENAI_API_KEY nao estiver configurado ou se o
            pacote openai nao estiver instalado.
    """
    global _client

    if _client is not None:
        return _client

    if not OPENAI_API_KEY:
        raise ValueError(
            "OPENAI_API_KEY deve estar configurado "
            "(st.secrets['openai'] ou .env) para usar o chat de IA."
        )

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ValueError(
            "Pacote 'openai' nao encontrado no ambiente. "
            "Adicione a dependencia para usar provider OpenAI."
        ) from exc

    _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client
