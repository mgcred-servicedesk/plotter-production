"""
Página de gerenciamento de usuários (admin only).

Permite criar, ativar/desativar e resetar senhas.
Também permite que qualquer usuário altere a própria senha.
"""
import pandas as pd
import streamlit as st

from src.dashboard.auth import (
    PERFIS,
    alterar_senha,
    alternar_ativo,
    criar_usuario,
    listar_usuarios,
    resetar_senha,
    usuario_logado,
)


def _render_alterar_minha_senha():
    """Formulário para alterar a própria senha."""
    st.subheader("Alterar Minha Senha")

    with st.form("form_alterar_senha"):
        senha_atual = st.text_input(
            "Senha atual", type="password",
        )
        nova_senha = st.text_input(
            "Nova senha", type="password",
        )
        confirmar = st.text_input(
            "Confirmar nova senha", type="password",
        )
        submit = st.form_submit_button("Alterar Senha")

    if submit:
        if not senha_atual or not nova_senha:
            st.error("Preencha todos os campos.")
            return
        if nova_senha != confirmar:
            st.error("As senhas nao conferem.")
            return
        if len(nova_senha) < 6:
            st.error("A senha deve ter pelo menos 6 caracteres.")
            return

        user = usuario_logado()
        ok, msg = alterar_senha(
            user["usuario"], senha_atual, nova_senha,
        )
        if ok:
            st.success(msg)
        else:
            st.error(msg)


def _render_lista_usuarios():
    """Exibe lista de usuários com ações."""
    st.subheader("Usuarios Cadastrados")

    usuarios = listar_usuarios()

    if not usuarios:
        st.info("Nenhum usuario cadastrado.")
        return

    df = pd.DataFrame(usuarios)
    df.columns = [
        "Usuario", "Nome", "Perfil", "Escopo", "Ativo",
    ]

    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
    )

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Ativar/Desativar Usuario**")
        nomes_usuario = [u["usuario"] for u in usuarios]
        usuario_sel = st.selectbox(
            "Selecionar usuario",
            nomes_usuario,
            key="sel_ativar",
        )
        if st.button("Alternar Status"):
            ok, msg = alternar_ativo(usuario_sel)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    with col2:
        st.markdown("**Resetar Senha**")
        usuario_reset = st.selectbox(
            "Selecionar usuario",
            nomes_usuario,
            key="sel_reset",
        )
        nova_senha_reset = st.text_input(
            "Nova senha", type="password",
            key="input_reset_senha",
        )
        if st.button("Resetar"):
            if not nova_senha_reset:
                st.error("Informe a nova senha.")
            elif len(nova_senha_reset) < 6:
                st.error(
                    "A senha deve ter pelo menos 6 caracteres."
                )
            else:
                ok, msg = resetar_senha(
                    usuario_reset, nova_senha_reset,
                )
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)


def _render_criar_usuario(regioes: list[str], lojas: list[str]):
    """Formulário para criar novo usuário."""
    st.subheader("Criar Novo Usuario")

    with st.form("form_criar_usuario"):
        col1, col2 = st.columns(2)

        with col1:
            novo_usuario = st.text_input(
                "Usuario (login)",
                placeholder="nome.sobrenome",
            )
            novo_nome = st.text_input(
                "Nome completo",
                placeholder="Nome Sobrenome",
            )
            nova_senha = st.text_input(
                "Senha inicial", type="password",
            )

        with col2:
            perfil = st.selectbox(
                "Perfil",
                list(PERFIS.keys()),
                format_func=lambda x: PERFIS[x],
            )

            escopo = []
            if perfil == "gerente_comercial":
                escopo = st.multiselect(
                    "Regioes de acesso",
                    regioes,
                )
            elif perfil == "supervisor":
                escopo = st.multiselect(
                    "Lojas de acesso",
                    lojas,
                )

        submit = st.form_submit_button(
            "Criar Usuario", width="stretch",
        )

    if submit:
        if not novo_usuario or not novo_nome or not nova_senha:
            st.error("Preencha todos os campos obrigatorios.")
            return
        if len(nova_senha) < 6:
            st.error("A senha deve ter pelo menos 6 caracteres.")
            return

        ok, msg = criar_usuario(
            novo_usuario, novo_nome, nova_senha,
            perfil, escopo,
        )
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)


def render_pagina_usuarios(
    regioes: list[str] = None,
    lojas: list[str] = None,
):
    """
    Renderiza pagina de gerenciamento de usuarios.

    Admin vê tudo; outros perfis veem apenas 'Alterar Senha'.
    """
    user = usuario_logado()
    if not user:
        return

    if user["perfil"] == "admin":
        tab1, tab2, tab3 = st.tabs([
            "Usuarios", "Criar Usuario", "Minha Senha",
        ])

        with tab1:
            _render_lista_usuarios()

        with tab2:
            _render_criar_usuario(
                regioes or [], lojas or [],
            )

        with tab3:
            _render_alterar_minha_senha()
    else:
        _render_alterar_minha_senha()
