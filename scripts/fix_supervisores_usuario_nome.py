"""
Corrige registros de supervisores onde os campos `usuario`
(login) e `nome` (exibição) foram salvos invertidos.

Critério de detecção: registros com perfil 'supervisor' onde
`usuario` contém espaços (formato de nome de loja) e `nome`
não contém espaços (formato de login com ponto).

Uso:
    # Dry-run — mostra o que seria alterado sem gravar
    python scripts/fix_supervisores_usuario_nome.py

    # Aplica a correção no banco
    python scripts/fix_supervisores_usuario_nome.py --aplicar
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.supabase_client import get_supabase_client


def _invertido(usuario: str, nome: str) -> bool:
    """Retorna True se os campos parecem estar trocados."""
    usuario_parece_nome = " " in usuario  # ex: "HELP CASCADURA"
    nome_parece_login = " " not in nome and "." in nome  # ex: "help.cascadura"
    return usuario_parece_nome and nome_parece_login


def fix_supervisores(aplicar: bool = False):
    client = get_supabase_client()

    resp = (
        client
        .table("usuarios")
        .select("id, usuario, nome, perfil")
        .eq("perfil", "supervisor")
        .eq("ativo", True)
        .execute()
    )

    registros = resp.data or []

    afetados = [r for r in registros if _invertido(r["usuario"], r["nome"])]

    if not afetados:
        print("Nenhum registro com campos invertidos encontrado.")
        return

    print(f"{'DRY-RUN' if not aplicar else 'APLICANDO'} — {len(afetados)} registro(s) afetado(s):\n")
    print(f"{'usuario (atual)':<35} {'nome (atual)':<35} {'→ usuario':<35} {'→ nome'}")
    print("-" * 140)

    for r in afetados:
        print(
            f"{r['usuario']:<35} {r['nome']:<35}"
            f" → {r['nome']:<35} {r['usuario']}"
        )

    if not aplicar:
        print("\nRode com --aplicar para gravar as alterações.")
        return

    print()
    erros = 0
    for r in afetados:
        try:
            (
                client
                .table("usuarios")
                .update({"usuario": r["nome"], "nome": r["usuario"]})
                .eq("id", r["id"])
                .execute()
            )
            print(f"[OK] {r['nome']} (era: {r['usuario']})")
        except Exception as e:
            print(f"[ERRO] {r['usuario']}: {e}")
            erros += 1

    print(
        f"\n{len(afetados) - erros}/{len(afetados)} registros corrigidos."
        + (f" {erros} erro(s)." if erros else "")
    )


if __name__ == "__main__":
    aplicar = "--aplicar" in sys.argv
    fix_supervisores(aplicar=aplicar)
