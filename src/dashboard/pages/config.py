"""
Pagina de configuracao — pagina dedicada.

Substitui o dashboard inteiro quando ``mostrar_config`` esta ativo em
``st.session_state`` (flag escrita pelo botao Config/Usuarios da
sidebar). Roda **antes** da carga de contratos: nenhum dado de periodo e
consultado aqui, apenas os cadastros de loja/regiao/consultor que
alimentam os selects de criacao de usuario.

Branch por perfil: admin ve gerenciamento de usuarios e de feriados;
demais perfis veem apenas "Minha Conta" (``render_pagina_usuarios`` sem
argumentos ja restringe o conteudo a alteracao de senha — o gating de
permissao mora la, nao aqui).
"""

import streamlit as st
import streamlit_antd_components as sac

from src.dashboard.auth import usuario_logado
from src.dashboard.feriados_mgmt import render_pagina_feriados
from src.dashboard.loaders import (
    carregar_consultores_cadastro,
    carregar_lojas_regioes,
)
from src.dashboard.user_mgmt import render_pagina_usuarios


def render_pagina_config() -> None:
    """Renderiza a pagina de configuracao.

    Inclui o botao de voltar, que apaga ``mostrar_config`` e faz rerun.
    O chamador (``app.py``) e responsavel por encerrar o render do
    dashboard apos esta chamada (``return``).
    """
    if st.button("← Voltar ao Dashboard"):
        st.session_state["mostrar_config"] = False
        st.rerun()

    user = usuario_logado()
    lojas_cfg, regioes_cfg = carregar_lojas_regioes()
    consultores_cfg = carregar_consultores_cadastro()

    if user and user["perfil"] == "admin":
        sac.divider(
            label="Gerenciamento de Usuarios",
            icon="people-fill",
            align="left",
            color="blue",
        )
        render_pagina_usuarios(
            regioes=regioes_cfg,
            lojas=lojas_cfg,
            consultores=consultores_cfg,
        )

        sac.divider(
            label="Gerenciamento de Feriados",
            icon="calendar2-event-fill",
            align="left",
            color="blue",
        )
        render_pagina_feriados()
    else:
        sac.divider(
            label="Minha Conta",
            icon="person-gear",
            align="left",
            color="blue",
        )
        render_pagina_usuarios()
