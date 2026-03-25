"""
Cliente Supabase para acesso ao banco de dados.

Centraliza a conexão com o Supabase, reutilizada por
todos os módulos que precisam acessar o banco.

Prioridade de leitura das credenciais:
1. st.secrets (Streamlit Cloud — secrets.toml)
2. Variáveis de ambiente / .env (desenvolvimento local)
"""
import os

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()


def _get_secret(section: str, key: str, fallback: str = "") -> str:
    """Lê credencial de st.secrets (Cloud) ou .env (local)."""
    try:
        import streamlit as st
        return st.secrets[section][key]
    except Exception:
        return os.getenv(key, fallback)


SUPABASE_URL: str = _get_secret("database", "SUPABASE_URL")
SUPABASE_KEY: str = _get_secret("database", "SUPABASE_KEY")

_client: Client | None = None


def get_supabase_client() -> Client:
    """
    Retorna instância singleton do cliente Supabase.

    Raises:
        ValueError: Se SUPABASE_URL ou SUPABASE_KEY não
            estiverem configurados no .env.
    """
    global _client

    if _client is not None:
        return _client

    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError(
            "SUPABASE_URL e SUPABASE_KEY devem estar "
            "configurados no arquivo .env"
        )

    _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client
