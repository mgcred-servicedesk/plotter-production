"""
Script para criar o usuario admin inicial no Supabase.

Uso:
    python scripts/seed_admin.py

Requer SUPABASE_URL e SUPABASE_KEY configurados no .env.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.supabase_client import get_supabase_client
from src.dashboard.auth import gerar_hash_senha


def seed_admin():
    """Cria usuario admin se nao existir."""
    client = get_supabase_client()

    # Verifica se ja existe
    resp = (
        client
        .table("usuarios")
        .select("id")
        .eq("usuario", "admin")
        .limit(1)
        .execute()
    )

    if resp.data:
        print("Usuario 'admin' ja existe. Nenhuma acao tomada.")
        return

    senha_padrao = "mgcred2026"
    hash_senha = gerar_hash_senha(senha_padrao)

    client.table("usuarios").insert({
        "usuario": "admin",
        "nome": "Administrador",
        "perfil": "admin",
        "senha_hash": hash_senha,
        "ativo": True,
    }).execute()

    print("Usuario 'admin' criado com sucesso.")
    print(f"Senha inicial: {senha_padrao}")
    print("IMPORTANTE: Altere a senha no primeiro acesso.")


if __name__ == "__main__":
    seed_admin()
