"""
Cliente Supabase para acesso ao banco de dados.

Centraliza a conexão com o Supabase, reutilizada por
todos os módulos que precisam acessar o banco.
"""
import os

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

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
