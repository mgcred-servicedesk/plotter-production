"""
Módulo de autenticação do dashboard.

Gerencia login, logout, sessão e validação de credenciais
usando bcrypt para hash de senhas.

Armazenamento: tabela ``usuarios`` no Supabase (PostgreSQL).
Escopos de acesso são armazenados na tabela
``usuario_escopos``.
"""

import logging
from typing import Optional

import bcrypt
import streamlit as st

from src.config.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# Perfis disponíveis e suas descrições
PERFIS = {
    "admin": "Administrador — acesso total",
    "gestor": "Gestor — visão global das operações",
    "gerente_comercial": "Gerente Comercial — acesso por região",
    "supervisor": "Supervisor — acesso por loja",
}


# ── helpers internos ──────────────────────────────────


def _supabase():
    """Atalho para obter o cliente Supabase."""
    return get_supabase_client()


def _carregar_escopo(usuario_id: str) -> list[str]:
    """
    Carrega nomes do escopo (regioes ou lojas) de um
    usuario a partir de ``usuario_escopos``.
    """
    resp = (
        _supabase()
        .table("usuario_escopos")
        .select("regiao_id, loja_id, regioes(nome), lojas(nome)")
        .eq("usuario_id", usuario_id)
        .execute()
    )
    escopo: list[str] = []
    for row in resp.data or []:
        if row.get("regioes") and row["regioes"].get("nome"):
            escopo.append(row["regioes"]["nome"])
        elif row.get("lojas") and row["lojas"].get("nome"):
            escopo.append(row["lojas"]["nome"])
    return escopo


def _salvar_escopos(
    usuario_id: str,
    perfil: str,
    escopo: list[str],
) -> None:
    """
    Salva escopos de um usuario na tabela
    ``usuario_escopos``.

    Para gerente_comercial: busca regioes por nome.
    Para supervisor: busca lojas por nome.
    """
    # Limpa escopos anteriores
    (
        _supabase()
        .table("usuario_escopos")
        .delete()
        .eq("usuario_id", usuario_id)
        .execute()
    )

    if not escopo or perfil == "admin":
        return

    if perfil == "gerente_comercial":
        resp = (
            _supabase()
            .table("regioes")
            .select("id, nome")
            .in_("nome", escopo)
            .execute()
        )
        registros = [
            {
                "usuario_id": usuario_id,
                "regiao_id": r["id"],
            }
            for r in (resp.data or [])
        ]
    elif perfil == "supervisor":
        resp = (
            _supabase().table("lojas").select("id, nome").in_("nome", escopo).execute()
        )
        registros = [
            {
                "usuario_id": usuario_id,
                "loja_id": r["id"],
            }
            for r in (resp.data or [])
        ]
    else:
        return

    if registros:
        (_supabase().table("usuario_escopos").insert(registros).execute())


# ── hash de senhas ────────────────────────────────────


def gerar_hash_senha(senha: str) -> str:
    """Gera hash bcrypt para uma senha."""
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_senha(senha: str, hash_senha: str) -> bool:
    """Verifica se a senha corresponde ao hash."""
    return bcrypt.checkpw(senha.encode("utf-8"), hash_senha.encode("utf-8"))


# ── autenticação ──────────────────────────────────────


def autenticar(usuario: str, senha: str) -> Optional[dict]:
    """
    Autentica um usuário.

    Returns:
        Dados do usuário se credenciais válidas, None caso
        contrário.
    """
    resp = (
        _supabase()
        .table("usuarios")
        .select("id, usuario, nome, perfil, senha_hash, ativo")
        .eq("usuario", usuario)
        .eq("ativo", True)
        .limit(1)
        .execute()
    )

    if not resp.data:
        return None

    u = resp.data[0]

    if not verificar_senha(senha, u["senha_hash"]):
        return None

    escopo = _carregar_escopo(u["id"])

    return {
        "id": u["id"],
        "usuario": u["usuario"],
        "nome": u["nome"],
        "perfil": u["perfil"],
        "escopo": escopo,
    }


def usuario_logado() -> Optional[dict]:
    """Retorna dados do usuário logado ou None."""
    return st.session_state.get("usuario_logado")


def fazer_logout() -> None:
    """Remove sessão do usuário."""
    for chave in ["usuario_logado", "visualizar_como"]:
        st.session_state.pop(chave, None)


def tela_login() -> bool:
    """
    Renderiza tela de login.

    Returns:
        True se o usuário está autenticado, False caso
        contrário.
    """
    if usuario_logado():
        return True

    st.markdown(
        """
        <div style="text-align: center; padding: 2rem 0 1rem;">
            <h1 style="font-size: 2rem; font-weight: 800;">
                Dashboard de Vendas
            </h1>
            <p style="opacity: 0.6;">
                Acesso restrito — insira suas credenciais
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 1.5, 1])

    with col2:
        with st.form("login_form"):
            st.image(
                "assets/logotipo-mg-cred.png",
                width="stretch",
            )
            usuario = st.text_input(
                "Usuario",
                placeholder="Digite seu usuario",
            )
            senha = st.text_input(
                "Senha",
                type="password",
                placeholder="Digite sua senha",
            )
            submit = st.form_submit_button(
                "Entrar",
                use_container_width=True,
            )

        if submit:
            if not usuario or not senha:
                st.error("Preencha usuario e senha.")
                return False

            dados = autenticar(usuario, senha)
            if dados:
                st.session_state["usuario_logado"] = dados
                st.rerun()
            else:
                st.error("Usuario ou senha invalidos.")
                return False

    return False


# ── CRUD de usuários ──────────────────────────────────


def criar_usuario(
    usuario: str,
    nome: str,
    senha: str,
    perfil: str,
    escopo: list[str],
) -> tuple[bool, str]:
    """
    Cria novo usuário.

    Returns:
        Tupla (sucesso, mensagem).
    """
    if perfil not in PERFIS:
        return False, f"Perfil '{perfil}' invalido."

    if perfil not in ("admin", "gestor") and not escopo:
        return (
            False,
            "Informe o escopo (regioes ou lojas) para este perfil.",
        )

    # Verifica duplicidade
    existe = (
        _supabase()
        .table("usuarios")
        .select("id")
        .eq("usuario", usuario)
        .limit(1)
        .execute()
    )
    if existe.data:
        return False, f"Usuario '{usuario}' ja existe."

    resp = (
        _supabase()
        .table("usuarios")
        .insert(
            {
                "usuario": usuario,
                "nome": nome,
                "perfil": perfil,
                "senha_hash": gerar_hash_senha(senha),
                "ativo": True,
            }
        )
        .execute()
    )

    novo_id = resp.data[0]["id"]
    _salvar_escopos(novo_id, perfil, escopo)

    return True, f"Usuario '{usuario}' criado com sucesso."


def alterar_senha(
    usuario: str,
    senha_atual: str,
    nova_senha: str,
) -> tuple[bool, str]:
    """
    Altera senha de um usuário.

    Returns:
        Tupla (sucesso, mensagem).
    """
    resp = (
        _supabase()
        .table("usuarios")
        .select("id, senha_hash")
        .eq("usuario", usuario)
        .limit(1)
        .execute()
    )

    if not resp.data:
        return False, "Usuario nao encontrado."

    u = resp.data[0]

    if not verificar_senha(senha_atual, u["senha_hash"]):
        return False, "Senha atual incorreta."

    (
        _supabase()
        .table("usuarios")
        .update({"senha_hash": gerar_hash_senha(nova_senha)})
        .eq("id", u["id"])
        .execute()
    )

    return True, "Senha alterada com sucesso."


def listar_usuarios() -> list[dict]:
    """Retorna lista de usuários (sem hash de senha)."""
    resp = (
        _supabase()
        .table("usuarios")
        .select("id, usuario, nome, perfil, ativo")
        .order("nome")
        .execute()
    )

    resultado = []
    for u in resp.data or []:
        escopo = _carregar_escopo(u["id"])
        resultado.append(
            {
                "usuario": u["usuario"],
                "nome": u["nome"],
                "perfil": u["perfil"],
                "escopo": escopo,
                "ativo": u["ativo"],
            }
        )
    return resultado


def alternar_ativo(usuario: str) -> tuple[bool, str]:
    """Ativa/desativa um usuário."""
    resp = (
        _supabase()
        .table("usuarios")
        .select("id, ativo")
        .eq("usuario", usuario)
        .limit(1)
        .execute()
    )

    if not resp.data:
        return False, "Usuario nao encontrado."

    u = resp.data[0]
    novo_status = not u["ativo"]

    (
        _supabase()
        .table("usuarios")
        .update({"ativo": novo_status})
        .eq("id", u["id"])
        .execute()
    )

    status = "ativado" if novo_status else "desativado"
    return True, f"Usuario '{usuario}' {status}."


def resetar_senha(
    usuario: str,
    nova_senha: str,
) -> tuple[bool, str]:
    """Reseta senha de um usuário (admin only)."""
    resp = (
        _supabase()
        .table("usuarios")
        .select("id")
        .eq("usuario", usuario)
        .limit(1)
        .execute()
    )

    if not resp.data:
        return False, "Usuario nao encontrado."

    (
        _supabase()
        .table("usuarios")
        .update({"senha_hash": gerar_hash_senha(nova_senha)})
        .eq("id", resp.data[0]["id"])
        .execute()
    )

    return True, f"Senha de '{usuario}' resetada."
