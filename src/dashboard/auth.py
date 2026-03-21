"""
Módulo de autenticação do dashboard.

Gerencia login, logout, sessão e validação de credenciais
usando bcrypt para hash de senhas.
"""
import json
from pathlib import Path
from typing import Optional

import bcrypt
import streamlit as st

ARQUIVO_USUARIOS = Path("configuracao/usuarios.json")

# Perfis disponíveis e suas descrições
PERFIS = {
    "admin": "Administrador — acesso total",
    "gerente_comercial": "Gerente Comercial — acesso por região",
    "supervisor": "Supervisor — acesso por loja",
}


def _carregar_usuarios() -> list[dict]:
    """Carrega lista de usuários do arquivo JSON."""
    if not ARQUIVO_USUARIOS.exists():
        return []
    with open(ARQUIVO_USUARIOS, "r", encoding="utf-8") as f:
        dados = json.load(f)
    return dados.get("usuarios", [])


def _salvar_usuarios(usuarios: list[dict]) -> None:
    """Salva lista de usuários no arquivo JSON."""
    with open(ARQUIVO_USUARIOS, "w", encoding="utf-8") as f:
        json.dump(
            {"usuarios": usuarios}, f,
            ensure_ascii=False, indent=2,
        )


def gerar_hash_senha(senha: str) -> str:
    """Gera hash bcrypt para uma senha."""
    return bcrypt.hashpw(
        senha.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")


def verificar_senha(senha: str, hash_senha: str) -> bool:
    """Verifica se a senha corresponde ao hash."""
    return bcrypt.checkpw(
        senha.encode("utf-8"), hash_senha.encode("utf-8")
    )


def autenticar(usuario: str, senha: str) -> Optional[dict]:
    """
    Autentica um usuário.

    Returns:
        Dados do usuário se credenciais válidas, None caso
        contrário.
    """
    usuarios = _carregar_usuarios()
    for u in usuarios:
        if (
            u["usuario"] == usuario
            and u.get("ativo", True)
            and verificar_senha(senha, u["senha_hash"])
        ):
            return {
                "usuario": u["usuario"],
                "nome": u["nome"],
                "perfil": u["perfil"],
                "escopo": u.get("escopo", []),
            }
    return None


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
                use_column_width=True,
            )
            usuario = st.text_input(
                "Usuario", placeholder="Digite seu usuario",
            )
            senha = st.text_input(
                "Senha", type="password",
                placeholder="Digite sua senha",
            )
            submit = st.form_submit_button(
                "Entrar", use_container_width=True,
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
    usuarios = _carregar_usuarios()

    if any(u["usuario"] == usuario for u in usuarios):
        return False, f"Usuario '{usuario}' ja existe."

    if perfil not in PERFIS:
        return False, f"Perfil '{perfil}' invalido."

    if perfil != "admin" and not escopo:
        return (
            False,
            "Informe o escopo (regioes ou lojas) para "
            "este perfil.",
        )

    usuarios.append({
        "usuario": usuario,
        "nome": nome,
        "perfil": perfil,
        "escopo": escopo,
        "senha_hash": gerar_hash_senha(senha),
        "ativo": True,
    })

    _salvar_usuarios(usuarios)
    return True, f"Usuario '{usuario}' criado com sucesso."


def alterar_senha(
    usuario: str, senha_atual: str, nova_senha: str,
) -> tuple[bool, str]:
    """
    Altera senha de um usuário.

    Returns:
        Tupla (sucesso, mensagem).
    """
    usuarios = _carregar_usuarios()

    for u in usuarios:
        if u["usuario"] == usuario:
            if not verificar_senha(senha_atual, u["senha_hash"]):
                return False, "Senha atual incorreta."
            u["senha_hash"] = gerar_hash_senha(nova_senha)
            _salvar_usuarios(usuarios)
            return True, "Senha alterada com sucesso."

    return False, "Usuario nao encontrado."


def listar_usuarios() -> list[dict]:
    """Retorna lista de usuários (sem hash de senha)."""
    usuarios = _carregar_usuarios()
    return [
        {
            "usuario": u["usuario"],
            "nome": u["nome"],
            "perfil": u["perfil"],
            "escopo": u.get("escopo", []),
            "ativo": u.get("ativo", True),
        }
        for u in usuarios
    ]


def alternar_ativo(usuario: str) -> tuple[bool, str]:
    """Ativa/desativa um usuário."""
    usuarios = _carregar_usuarios()

    for u in usuarios:
        if u["usuario"] == usuario:
            u["ativo"] = not u.get("ativo", True)
            _salvar_usuarios(usuarios)
            status = "ativado" if u["ativo"] else "desativado"
            return True, f"Usuario '{usuario}' {status}."

    return False, "Usuario nao encontrado."


def resetar_senha(
    usuario: str, nova_senha: str,
) -> tuple[bool, str]:
    """Reseta senha de um usuário (admin only)."""
    usuarios = _carregar_usuarios()

    for u in usuarios:
        if u["usuario"] == usuario:
            u["senha_hash"] = gerar_hash_senha(nova_senha)
            _salvar_usuarios(usuarios)
            return (
                True,
                f"Senha de '{usuario}' resetada.",
            )

    return False, "Usuario nao encontrado."
