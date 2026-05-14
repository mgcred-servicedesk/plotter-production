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
    "consultor": "Consultor — acesso aos próprios dados",
}


# ── helpers internos ──────────────────────────────────


def _supabase():
    """Atalho para obter o cliente Supabase."""
    return get_supabase_client()


def _carregar_escopo(usuario_id: str) -> list[str]:
    """
    Carrega nomes do escopo (regioes, lojas ou consultores)
    de um usuario a partir de ``usuario_escopos``.
    """
    resp = (
        _supabase()
        .table("usuario_escopos")
        .select(
            "regiao_id, loja_id, consultor_id, "
            "regioes(nome), lojas(nome), consultores(nome)"
        )
        .eq("usuario_id", usuario_id)
        .execute()
    )
    escopo: list[str] = []
    for row in resp.data or []:
        if row.get("regioes") and row["regioes"].get("nome"):
            escopo.append(row["regioes"]["nome"])
        elif row.get("lojas") and row["lojas"].get("nome"):
            escopo.append(row["lojas"]["nome"])
        elif row.get("consultores") and row["consultores"].get("nome"):
            escopo.append(row["consultores"]["nome"])
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
            _supabase()
            .table("lojas")
            .select("id, nome")
            .in_("nome", escopo)
            .execute()
        )
        registros = [
            {
                "usuario_id": usuario_id,
                "loja_id": r["id"],
            }
            for r in (resp.data or [])
        ]
    elif perfil == "consultor":
        resp = (
            _supabase()
            .table("consultores")
            .select("id, nome")
            .in_("nome", escopo)
            .execute()
        )
        registros = [
            {
                "usuario_id": usuario_id,
                "consultor_id": r["id"],
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

    # CSS específico da tela de login
    st.markdown(
        """
        <style>
        /* Ocultar sidebar, header e iframe de tema */
        [data-testid="stSidebar"],
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="stHeader"] {
            display: none !important;
        }
        iframe[height="0"] {
            display: none !important;
        }

        /* Centralizar verticalmente o container */
        .main .block-container {
            display: flex !important;
            flex-direction: column !important;
            justify-content: center !important;
            min-height: 92vh !important;
        }

        /* Formulario como card */
        [data-testid="stForm"] {
            background: var(--mg-secondary-bg, #ffffff);
            border: 1px solid var(--mg-card-border,
                rgba(26,26,46,0.08));
            border-radius: 14px;
            padding: 1.5rem 1.75rem 1.25rem;
            box-shadow:
                0 4px 24px var(--mg-shadow,
                    rgba(26,26,46,0.06)),
                0 1px 4px var(--mg-shadow,
                    rgba(26,26,46,0.04));
        }

        /* Labels dos inputs */
        [data-testid="stForm"]
            [data-testid="stTextInput"] label {
            font-size: 0.8rem !important;
            font-weight: 600 !important;
            color: var(--mg-text-secondary,
                rgba(26,26,46,0.65)) !important;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }

        /* Botao Entrar */
        [data-testid="stForm"]
            .stFormSubmitButton > button {
            background: var(--mg-primary, #2563eb)
                !important;
            color: #ffffff !important;
            border: none !important;
            border-radius: 10px !important;
            padding: 0.6rem 1.5rem !important;
            font-weight: 700 !important;
            font-size: 0.9rem !important;
            letter-spacing: 0.02em;
            transition: opacity 0.2s ease,
                transform 0.15s ease !important;
            margin-top: 0.25rem;
        }

        [data-testid="stForm"]
            .stFormSubmitButton > button:hover {
            opacity: 0.88 !important;
            transform: translateY(-1px) !important;
            background: var(--mg-primary, #2563eb)
                !important;
            color: #ffffff !important;
        }

        /* Logo */
        .login-logo {
            text-align: center;
            margin-bottom: 0.25rem;
        }
        .login-logo img {
            max-width: 180px;
            height: auto;
        }

        /* Subtitulo */
        .login-subtitle {
            text-align: center;
            color: var(--mg-text-secondary,
                rgba(26,26,46,0.65)) !important;
            font-size: 0.82rem;
            margin-bottom: 1rem;
            font-weight: 400;
        }

        /* Rodape */
        .login-footer {
            text-align: center;
            color: var(--mg-text-secondary,
                rgba(26,26,46,0.65)) !important;
            font-size: 0.7rem;
            margin-top: 1.25rem;
            opacity: 0.6;
        }

        /* Responsivo: mobile */
        @media (max-width: 480px) {
            [data-testid="stForm"] {
                padding: 1.25rem 1.25rem 1rem;
                border-radius: 12px;
            }
            .login-logo img {
                max-width: 150px;
            }
        }

        /* Overlay de transicao pos-login */
        .login-transition-overlay {
            position: fixed;
            inset: 0;
            background: var(--mg-secondary-bg, #f8faff);
            z-index: 9999;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 0.75rem;
            animation: lt-fadein 0.25s ease;
        }
        @keyframes lt-fadein {
            from { opacity: 0; }
            to   { opacity: 1; }
        }
        .login-transition-check {
            width: 56px;
            height: 56px;
            background: #22c55e;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #fff;
            font-size: 1.5rem;
            font-weight: 700;
            box-shadow: 0 4px 16px rgba(34,197,94,0.3);
        }
        .login-transition-name {
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--mg-text, #1a1a2e);
            margin: 0;
        }
        .login-transition-loading {
            font-size: 0.82rem;
            color: var(--mg-text-secondary,
                rgba(26,26,46,0.55));
            margin: 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    import base64
    from pathlib import Path

    is_dark = st.session_state.get("theme", "light") == "dark"
    logo_path = Path(
        "assets/logo-grayscale.png"
        if is_dark
        else "assets/logotipo-mg-cred.png"
    )
    logo_b64 = ""
    if logo_path.exists():
        logo_b64 = base64.b64encode(
            logo_path.read_bytes()
        ).decode()

    # Colunas para centralizar (nativo Streamlit)
    _, col_center, _ = st.columns([1.2, 1, 1.2])

    with col_center:
        # Logo + subtítulo
        header_html = ""
        if logo_b64:
            header_html += (
                '<div class="login-logo">'
                '<img src="data:image/png;base64,'
                f'{logo_b64}" alt="MGCred">'
                "</div>"
            )
        header_html += (
            '<p class="login-subtitle">'
            "Acesso restrito &mdash; "
            "insira suas credenciais"
            "</p>"
        )
        st.markdown(
            header_html, unsafe_allow_html=True,
        )

        # Formulário
        with st.form("login_form"):
            usuario = st.text_input(
                "Usuário",
                placeholder="Digite seu usuário",
            )
            senha = st.text_input(
                "Senha",
                type="password",
                placeholder="Digite sua senha",
            )
            submit = st.form_submit_button(
                "Entrar",
                width="stretch",
            )

        # Rodapé
        st.markdown(
            '<p class="login-footer">'
            "&copy; 2026 MGCred &mdash; "
            "Dashboard de Vendas"
            "</p>",
            unsafe_allow_html=True,
        )

        if submit:
            usuario = usuario.strip()
            senha = senha.strip()
            if not usuario or not senha:
                st.error("Preencha usuário e senha.")
                return False

            with st.spinner("Verificando credenciais..."):
                dados = autenticar(usuario, senha)

            if dados:
                st.session_state["usuario_logado"] = dados
                st.session_state["_fresh_login"] = True
                st.rerun()
            else:
                st.error("Usuário ou senha inválidos.")
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
    _invalidar_cache_usuarios()

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


def editar_usuario(
    usuario: str,
    novo_perfil: str,
    novo_escopo: list[str],
) -> tuple[bool, str]:
    """
    Atualiza perfil e escopo de um usuário existente.

    Returns:
        Tupla (sucesso, mensagem).
    """
    if novo_perfil not in PERFIS:
        return False, f"Perfil '{novo_perfil}' invalido."

    if novo_perfil not in ("admin", "gestor") and not novo_escopo:
        return (
            False,
            "Informe o escopo (regioes, lojas ou consultor) para este perfil.",
        )

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

    usuario_id = resp.data[0]["id"]

    (
        _supabase()
        .table("usuarios")
        .update({"perfil": novo_perfil})
        .eq("id", usuario_id)
        .execute()
    )

    _salvar_escopos(usuario_id, novo_perfil, novo_escopo)
    _invalidar_cache_usuarios()

    return True, f"Usuario '{usuario}' atualizado com sucesso."


@st.cache_data(ttl=300, show_spinner=False)
def listar_usuarios() -> list[dict]:
    """Retorna lista de usuários (sem hash de senha).

    Faz 2 queries em batch (em vez de N+1): uma para ``usuarios`` e
    outra para ``usuario_escopos`` com expansion das tabelas relacionadas.
    Resultado cacheado por 5 min; mutacoes (criar/editar/ativar/resetar)
    invalidam via :func:`_invalidar_cache_usuarios`.
    """
    resp = (
        _supabase()
        .table("usuarios")
        .select("id, usuario, nome, perfil, ativo")
        .order("nome")
        .execute()
    )
    usuarios_raw = resp.data or []

    # Batch fetch de todos os escopos em uma unica query.
    # Antes: N queries (uma por usuario) -> agora: 1 query.
    resp_escopos = (
        _supabase()
        .table("usuario_escopos")
        .select(
            "usuario_id, regiao_id, loja_id, consultor_id, "
            "regioes(nome), lojas(nome), consultores(nome)"
        )
        .execute()
    )

    # Agrupa escopos por usuario_id em Python.
    escopos_por_usuario: dict[str, list[str]] = {}
    for row in resp_escopos.data or []:
        nome = None
        if row.get("regioes") and row["regioes"].get("nome"):
            nome = row["regioes"]["nome"]
        elif row.get("lojas") and row["lojas"].get("nome"):
            nome = row["lojas"]["nome"]
        elif row.get("consultores") and row["consultores"].get("nome"):
            nome = row["consultores"]["nome"]
        if nome:
            escopos_por_usuario.setdefault(row["usuario_id"], []).append(nome)

    return [
        {
            "usuario": u["usuario"],
            "nome": u["nome"],
            "perfil": u["perfil"],
            "escopo": escopos_por_usuario.get(u["id"], []),
            "ativo": u["ativo"],
        }
        for u in usuarios_raw
    ]


def _invalidar_cache_usuarios() -> None:
    """Invalida o cache de :func:`listar_usuarios`.

    Deve ser chamada apos qualquer mutacao em ``usuarios`` ou
    ``usuario_escopos`` (criar, editar, ativar/desativar, resetar senha).
    """
    try:
        listar_usuarios.clear()
    except Exception:
        pass


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

    _invalidar_cache_usuarios()
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

    # Cache de listar_usuarios nao depende do hash de senha, mas
    # mantemos invalidacao por consistencia (caso o cache passe a
    # incluir mais campos no futuro).
    _invalidar_cache_usuarios()
    return True, f"Senha de '{usuario}' resetada."
