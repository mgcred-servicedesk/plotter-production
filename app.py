"""
Dashboard interativo de vendas — MGCred.

Entrypoint principal para deploy no Streamlit Cloud.
Consome dados diretamente do banco Supabase (PostgreSQL),
usando categorias_produto, v_pontuacao_efetiva e views.
Autocontido: nao depende dos modulos de KPI antigos
(kpi_dashboard.py, kpi_analiticos.py) nem dos loaders
de planilha (column_mapper.py, pontuacao_loader.py).

Frontend: streamlit-antd-components para navegacao,
tabelas via st.dataframe, CSS design system customizado.
"""

import sys
import warnings
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit_antd_components as sac

sys.path.insert(0, str(Path(__file__).parent))

from src.config.settings import NOMES_DISPLAY_PRODUTO
from src.dashboard.auth import (
    fazer_logout,
    tela_login,
    usuario_logado,
)
from src.dashboard.components.tables import exibir_tabela
from src.dashboard.kpis.gerais import (
    calcular_kpis_gerais,
    calcular_kpis_analise,
    calcular_kpis_cancelados,
    calcular_kpis_qtd_produtos,
    calcular_medias_du_por_nivel,
    calcular_metas_produto_diarias,
)
from src.dashboard.loaders import (
    carregar_categorias,
    carregar_consultores_cadastro,
    carregar_contratos_cancelados,
    carregar_contratos_em_analise,
    carregar_lojas_regioes,
    carregar_metas_consultor,
    carregar_metas_produto,
    carregar_pontuacao_efetiva,
    carregar_ultimo_periodo,
    consolidar_dados,
)
from src.dashboard.permissions import pode_ver
from src.dashboard.rls import (
    aplicar_rls,
    aplicar_rls_metas,
    aplicar_rls_supervisores,
    obter_regioes_permitidas,
)
from src.dashboard.tabs.analiticos import render_tab_analiticos
from src.dashboard.tabs.consultor import render_tab_consultor
from src.dashboard.tabs.detalhes import render_tab_detalhes
from src.dashboard.tabs.em_analise import render_tab_em_analise
from src.dashboard.tabs.evolucao import render_tab_evolucao
from src.dashboard.tabs.produtos import render_tab_produtos
from src.dashboard.tabs.rankings import render_tab_rankings
from src.dashboard.tabs.regioes import render_tab_regioes
from src.dashboard.ui.header import (
    render_header,
    render_status_bar,
)
from src.dashboard.ui.kpi_cards import (
    criar_cards_indicadores_principais,
    criar_cards_metas_produto,
    criar_cards_qtd_produto,
)
from src.dashboard.ui.skeleton import render_skeleton
from src.dashboard.ui.theme import (
    aplicar_tema,
    carregar_estilos_customizados,
    get_theme,
    get_theme_mode,
    set_theme_mode,
)
from src.dashboard.user_mgmt import render_pagina_usuarios
from src.dashboard.feriados_mgmt import render_pagina_feriados
from src.shared.dias_uteis import calcular_dias_uteis

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*ScriptRunContext.*")

st.set_page_config(
    page_title="Dashboard de Vendas - MGCred",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ══════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════


def _render_theme_toggle() -> None:
    """Segmented 3-state: light / system / dark.

    Renderiza tres botoes horizontais estilo macOS. O
    botao correspondente ao ``theme_mode`` atual recebe
    ``type='primary'``. Ao clicar, persiste via
    ``set_theme_mode`` e rerun.
    """
    current = get_theme_mode()
    opcoes = [
        ("light", ":material/light_mode:", "Claro"),
        ("system", ":material/computer:", "Sistema"),
        ("dark", ":material/dark_mode:", "Escuro"),
    ]
    st.markdown(
        '<div class="mg-theme-seg-wrapper"></div>',
        unsafe_allow_html=True,
    )
    cols = st.columns(3, gap="small")
    for col, (mode, icon, label) in zip(cols, opcoes):
        with col:
            btype = "primary" if current == mode else "secondary"
            if st.button(
                icon,
                key=f"theme_mode_{mode}",
                help=f"Tema {label}",
                type=btype,
                width="stretch",
            ):
                if mode != current:
                    set_theme_mode(mode)
                    st.rerun()


def _render_sidebar_usuario():
    """Informacoes do usuario e logout."""
    user = usuario_logado()
    if not user:
        return

    # Mapa de perfil -> classe CSS do badge
    _badge_map = {
        "admin": ("mg-badge-admin", "Admin"),
        "gestor": ("mg-badge-gestor", "Gestor"),
        "gerente_comercial": ("mg-badge-gerente", "Gerente"),
        "supervisor": ("mg-badge-supervisor", "Supervisor"),
    }
    badge_cls, badge_lbl = _badge_map.get(
        user["perfil"], ("mg-badge-admin", user["perfil"])
    )

    # Iniciais do usuario para avatar
    partes = user["nome"].split()
    iniciais = (
        (partes[0][0] + partes[-1][0]).upper()
        if len(partes) > 1
        else partes[0][:2].upper()
    )

    escopo_html = ""
    if (
        user["perfil"] not in ("admin", "gestor")
        and user.get("escopo")
    ):
        escopo_txt = ", ".join(user["escopo"])
        escopo_html = (
            f'<div class="mg-user-escopo">{escopo_txt}</div>'
        )

    st.markdown(
        f'<div class="mg-sidebar-user">'
        f'<div class="mg-avatar">{iniciais}</div>'
        f'<div class="mg-user-info">'
        f'<div class="mg-user-name">{user["nome"]}</div>'
        f'<span class="mg-badge {badge_cls}">{badge_lbl}</span>'
        f"{escopo_html}"
        f"</div></div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="mg-sidebar-actions"></div>',
        unsafe_allow_html=True,
    )
    col_cfg, col_sair = st.columns(2)

    with col_cfg:
        icon = ":material/settings:"
        label = "Config"
        if user["perfil"] == "admin":
            icon = ":material/group:"
            label = "Usuários"
        if st.button(
            f"{icon} {label}",
            width="stretch",
        ):
            st.session_state["mostrar_config"] = not st.session_state.get(
                "mostrar_config", False
            )
            st.rerun()

    with col_sair:
        if st.button(
            ":material/logout: Sair",
            width="stretch",
        ):
            fazer_logout()
            st.rerun()


def _render_sidebar_visualizar_como(df_full):
    """Seletor 'Visualizar como' para admin.

    Recebe df_full (pre-RLS) para que as opcoes de regiao/loja/
    consultor reflitam sempre o universo completo, independente
    do escopo simulado atual.
    """
    user = usuario_logado()
    if not user or user["perfil"] != "admin":
        return

    sac.divider(
        label="Visualizar Como",
        icon="eye-fill",
        align="center",
        color="gray",
    )

    opcoes = [
        "Admin (padrao)",
        "Gerente Comercial",
        "Supervisor",
        "Consultor",
    ]
    sel = st.selectbox(
        "Simular perfil",
        opcoes,
        key="sel_visualizar_perfil",
    )

    _anterior = st.session_state.get("visualizar_como")

    if sel == "Admin (padrao)":
        st.session_state.pop("visualizar_como", None)
    elif sel == "Gerente Comercial":
        regioes = (
            sorted(df_full["REGIAO"].dropna().unique().tolist())
            if "REGIAO" in df_full.columns
            else []
        )
        escopo = st.multiselect(
            "Regioes",
            regioes,
            key="sel_visualizar_regioes",
        )
        if escopo:
            st.session_state["visualizar_como"] = {
                "perfil": "gerente_comercial",
                "escopo": escopo,
            }
        else:
            st.session_state.pop("visualizar_como", None)
    elif sel == "Supervisor":
        lojas = (
            sorted(df_full["LOJA"].dropna().unique().tolist())
            if "LOJA" in df_full.columns
            else []
        )
        escopo = st.multiselect(
            "Lojas",
            lojas,
            key="sel_visualizar_lojas",
        )
        if escopo:
            st.session_state["visualizar_como"] = {
                "perfil": "supervisor",
                "escopo": escopo,
            }
        else:
            st.session_state.pop("visualizar_como", None)
    elif sel == "Consultor":
        consultores = (
            sorted(df_full["CONSULTOR"].dropna().unique().tolist())
            if "CONSULTOR" in df_full.columns
            else []
        )
        sel_cons = st.selectbox(
            "Consultor",
            [""] + consultores,
            key="sel_visualizar_consultor",
            help="Digite parte do nome para filtrar.",
        )
        if sel_cons:
            st.session_state["visualizar_como"] = {
                "perfil": "consultor",
                "escopo": [sel_cons],
            }
        else:
            st.session_state.pop("visualizar_como", None)

    # Forca rerun imediato quando o perfil simulado muda,
    # garantindo que o RLS use o novo escopo no mesmo ciclo.
    if st.session_state.get("visualizar_como") != _anterior:
        st.rerun()


# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════


def main():
    """Funcao principal do dashboard."""
    carregar_estilos_customizados()
    aplicar_tema()

    # ── Autenticacao ──────────────────────────────
    if not tela_login():
        return

    with st.sidebar:
        # ── Logo ocupa toda a largura ──
        logo = (
            "assets/logo-grayscale.png"
            if get_theme() == "dark"
            else "assets/logotipo-mg-cred.png"
        )
        st.image(logo, width="stretch")

        # ── Theme mode toggle 3-state (light/system/dark) ──
        _render_theme_toggle()

        _render_sidebar_usuario()

        # ── Periodo (colapsavel) ──────────────────────
        with st.expander(
            ":material/calendar_month: Período",
            expanded=True,
        ):
            _anos = [2024, 2025, 2026]
            if "periodo_padrao_carregado" not in st.session_state:
                _ultimo = carregar_ultimo_periodo()
                if _ultimo:
                    st.session_state["ano_padrao"] = _ultimo["ano"]
                    st.session_state["mes_padrao"] = _ultimo["mes"]
                else:
                    from datetime import datetime as _dt
                    _hoje = _dt.now()
                    st.session_state["ano_padrao"] = _hoje.year
                    st.session_state["mes_padrao"] = _hoje.month
                st.session_state["periodo_padrao_carregado"] = True

            _ano_padrao = st.session_state.get("ano_padrao", 2026)
            _mes_padrao = st.session_state.get("mes_padrao", 1)
            _idx_ano = (
                _anos.index(_ano_padrao)
                if _ano_padrao in _anos
                else len(_anos) - 1
            )

            ano = st.selectbox("Ano", _anos, index=_idx_ano)
            mes = st.selectbox(
                "Mes",
                list(range(1, 13)),
                index=_mes_padrao - 1,
                format_func=lambda x: {
                    1: "Janeiro",
                    2: "Fevereiro",
                    3: "Marco",
                    4: "Abril",
                    5: "Maio",
                    6: "Junho",
                    7: "Julho",
                    8: "Agosto",
                    9: "Setembro",
                    10: "Outubro",
                    11: "Novembro",
                    12: "Dezembro",
                }[x],
            )

            with st.expander(
                ":material/info: Legenda",
                expanded=False,
            ):
                st.caption("**DU**: Dias Úteis")
                st.caption("**Meta Prata**: Meta principal")
                st.caption("**Meta Ouro**: Meta desafio")

            # ── Botao para forcar atualizacao do cache ──
            if st.button(
                ":material/refresh: Atualizar Dados",
                help=(
                    "Limpa o cache e recarrega todos os dados "
                    "do banco. Use quando souber que os dados "
                    "foram atualizados recentemente."
                ),
                key="btn_refresh_cache",
                width="stretch",
            ):
                st.cache_data.clear()
                st.rerun()

    render_header(mes=mes, ano=ano)

    # ── Config: renderiza sem carregar contratos ──────
    if st.session_state.get("mostrar_config"):
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
        return

    # ── Dashboard: carrega contratos apenas aqui ──────
    try:
        skeleton_ph = st.empty()
        skeleton_ph.container()
        with skeleton_ph:
            render_skeleton()

        _is_admin = (
            usuario_logado() or {}
        ).get("perfil") == "admin"

        with st.status(
            "Carregando dados...", expanded=False
        ) as _status:
            _status.update(label="Carregando contratos pagos...")
            df, df_metas, df_sup = consolidar_dados(mes, ano)

            _status.update(label="Carregando categorias e metas...")
            categorias = carregar_categorias()
            df_metas_produto = carregar_metas_produto(mes, ano)

            _status.update(label="Carregando pipeline em analise...")
            df_analise = carregar_contratos_em_analise(mes, ano)

            # Zerar VALOR de produtos que nao contam
            # valor (emissoes de cartao, seguros)
            if (
                not df_analise.empty
                and "conta_valor" in df_analise.columns
            ):
                df_analise.loc[
                    df_analise["conta_valor"] == False,  # noqa
                    "VALOR",
                ] = 0
            # Zerar emissoes por TIPO OPER. (Venda Pre-Adesao
            # com produto CONSIG nao tem conta_valor=false)
            if (
                not df_analise.empty
                and "TIPO OPER." in df_analise.columns
            ):
                df_analise.loc[
                    df_analise["TIPO OPER."].isin(
                        ["CARTÃO BENEFICIO", "Venda Pré-Adesão"]
                    ),
                    "VALOR",
                ] = 0

            _status.update(label="Carregando cancelados...")
            df_cancelados = carregar_contratos_cancelados(
                mes, ano
            )
            if (
                not df_cancelados.empty
                and "conta_valor" in df_cancelados.columns
            ):
                df_cancelados.loc[
                    df_cancelados["conta_valor"] == False,  # noqa
                    "VALOR",
                ] = 0
            if (
                not df_cancelados.empty
                and "TIPO OPER." in df_cancelados.columns
            ):
                df_cancelados.loc[
                    df_cancelados["TIPO OPER."].isin(
                        ["CARTÃO BENEFICIO", "Venda Pré-Adesão"]
                    ),
                    "VALOR",
                ] = 0
            # Aplicar filtro de 30 dias para analise e cancelados
            from datetime import datetime, timedelta

            data_corte = datetime.now() - timedelta(days=30)

            if not df_analise.empty and "DATA_CADASTRO" in df_analise.columns:
                df_analise = df_analise[
                    df_analise["DATA_CADASTRO"] >= data_corte
                ].copy()

            if not df_cancelados.empty and \
                    "DATA_CADASTRO" in df_cancelados.columns:
                df_cancelados = df_cancelados[
                    df_cancelados["DATA_CADASTRO"] >= data_corte
                ].copy()

            if _is_admin:
                n_pagos = len(df)
                n_analise = len(df_analise)
                n_cancel = len(df_cancelados)
                _status.update(
                    label=(
                        f"Dados carregados — "
                        f"{n_pagos:,} pagos · "
                        f"{n_analise:,} em analise · "
                        f"{n_cancel:,} cancelados"
                    ).replace(",", "."),
                    state="complete",
                )
            else:
                _status.update(
                    label="Dados carregados",
                    state="complete",
                )

        # Limpar skeleton apos carregamento
        skeleton_ph.empty()

        # ── Nomes de display: renomear grupo_dashboard ─
        # Substitui chaves internas (ex: 'PACK') pelo label
        # amigavel antes de qualquer calculo ou renderizacao.
        # Aplica em todos os DFs que expoe grupo_dashboard.
        def _aplicar_nomes_display(frame: pd.DataFrame) -> pd.DataFrame:
            if frame.empty or "grupo_dashboard" not in frame.columns:
                return frame
            return frame.assign(
                grupo_dashboard=frame["grupo_dashboard"].replace(
                    NOMES_DISPLAY_PRODUTO
                )
            )

        df = _aplicar_nomes_display(df)
        categorias = categorias.copy()
        if "grupo_dashboard" in categorias.columns:
            categorias["grupo_dashboard"] = categorias[
                "grupo_dashboard"
            ].replace(NOMES_DISPLAY_PRODUTO)
        df_analise = _aplicar_nomes_display(df_analise)
        df_cancelados = _aplicar_nomes_display(df_cancelados)

        # ── Diagnostico de pontuacao ─────────────
        diag = st.session_state.get("_diag_pontuacao")
        if diag and _is_admin:
            with st.expander(
                f"Diagnostico de pontuacao — "
                f"{diag['com_pontos_mapeados']}/{diag['total_contratos']} "
                f"contratos com pontos",
                expanded=False,
            ):
                c1, c2, c3 = st.columns(3)
                c1.metric("Total contratos", diag["total_contratos"])
                c2.metric("Sem categoria", diag["sem_categoria"])
                c3.metric("Com pontos", diag["com_pontos_mapeados"])

                st.markdown("**Categorias nos contratos:**")
                st.code(
                    ", ".join(
                        c for c in diag["categorias_no_contrato"] if c
                    )
                    or "(vazio)",
                )

                st.markdown("**Categorias na pontuacao (RPC):**")
                st.code(
                    ", ".join(diag["categorias_na_pontuacao"]) or "(vazio)",
                )

                st.markdown("**Mapa de pontos:**")
                st.json(diag["mapa_pontos"])

                # Tipos sem categoria (não mapeados pelo fallback)
                tipos_sem_cat = diag.get("tipos_sem_categoria", [])
                if tipos_sem_cat:
                    st.warning(
                        f"**{diag['sem_categoria']} contratos sem categoria** "
                        f"— TIPO_PRODUTO nao mapeado:"
                    )
                    st.dataframe(
                        pd.DataFrame(tipos_sem_cat),
                        width="stretch",
                        hide_index=True,
                    )

                # Categorias sem match
                cats_contrato = {
                    c for c in diag["categorias_no_contrato"] if c
                }
                cats_pontuacao = set(diag["categorias_na_pontuacao"])
                sem_match = sorted(cats_contrato - cats_pontuacao)
                if sem_match:
                    st.warning(
                        f"**{len(sem_match)} categorias sem pontuacao:** "
                        + ", ".join(sem_match)
                    )

        # Calcular dias uteis do periodo (para usar nos KPIs)
        from datetime import datetime
        hoje = datetime.now()
        dia_ref = hoje.day if (ano == hoje.year and mes == hoje.month) else 1
        _, du_decorridos, _ = calcular_dias_uteis(ano, mes, dia_ref)

        if df.empty and df_analise.empty and df_cancelados.empty:
            st.warning("Nenhum dado encontrado para o periodo selecionado.")
            return

        if df.empty:
            st.info(
                "Nenhum contrato pago no periodo. "
                "Exibindo apenas propostas em analise."
            )
            df_analise = aplicar_rls(df_analise)
            # Sem contratos pagos, mostrar apenas card de analise
            kpis_analise = calcular_kpis_analise(
                df_analise, pd.DataFrame(), du_decorridos
            )
            kpis_vazio = {
                "total_vendas": 0,
                "projecao": 0,
                "meta_diaria_pts": 0,
                "media_du": 0,
                "media_du_pontos": 1,
            }
            criar_cards_indicadores_principais(
                kpis_vazio,
                kpis_analise,
                {
                    "valor_cancelados": 0,
                    "qtd_cancelados": 0,
                    "indice_perda": 0,
                },
                {"media_du_loja": 0, "media_du_consultor": 0},
            )
            render_tab_em_analise(df_analise, df_sup)
            return

        # ── Copias pre-RLS para heatmap comparativo ──
        df_full = df.copy()
        df_metas_produto_full = df_metas_produto.copy()

        # ── Dados do mês anterior (pre-RLS, evolução) ─
        mes_ant = mes - 1 if mes > 1 else 12
        ano_ant = ano if mes > 1 else ano - 1
        try:
            df_ant_full, _, _ = consolidar_dados(mes_ant, ano_ant)
            df_ant_full = _aplicar_nomes_display(df_ant_full)
        except Exception:
            df_ant_full = pd.DataFrame()
        du_dec_ant = calcular_dias_uteis(
            ano_ant, mes_ant, 1
        )[0]

        # ── RLS: filtrar dados por perfil ─────────
        df = aplicar_rls(df)
        df_metas = aplicar_rls_metas(df_metas, df)
        df_metas_produto = aplicar_rls_metas(df_metas_produto, df)
        df_sup = aplicar_rls_supervisores(df_sup, df)
        if not df_analise.empty:
            df_analise = aplicar_rls(df_analise)
        if not df_cancelados.empty:
            df_cancelados = aplicar_rls(df_cancelados)

        # Calcular dias uteis (usar data atual se df vazio)
        if not df.empty:
            ultima_data = df["DATA"].max()
            dia_atual = ultima_data.day if hasattr(ultima_data, "day") else None
        else:
            dia_atual = datetime.now().day
        _, du_decorridos, _ = calcular_dias_uteis(ano, mes, dia_atual)

        # ── Regioes permitidas pelo RLS ───────────
        regioes_todas = ["Todas"]
        if "REGIAO" in df.columns:
            regioes_todas += sorted(df["REGIAO"].unique().tolist())
        regioes_disp = obter_regioes_permitidas(
            regioes_todas,
        )

        with st.sidebar:
            _render_sidebar_visualizar_como(df_full)

            if regioes_disp:
                with st.expander(
                    ":material/filter_alt: Filtros Globais",
                    expanded=True,
                ):
                    filtro_regiao = st.selectbox(
                        "Regiao",
                        regioes_disp,
                        help="Filtrar dados por regiao",
                    )
            else:
                filtro_regiao = "Todas"

        df_f = df.copy()
        df_metas_f = df_metas.copy()
        df_metas_prod_f = df_metas_produto.copy()
        df_sup_f = df_sup.copy()
        df_analise_f = df_analise.copy()
        df_cancelados_f = df_cancelados.copy()

        if filtro_regiao != "Todas" and "REGIAO" in df.columns:
            df_f = df_f[df_f["REGIAO"] == filtro_regiao]
            lojas_r = df_f["LOJA"].unique()
            df_metas_f = df_metas_f[df_metas_f["LOJA"].isin(lojas_r)]
            if not df_metas_prod_f.empty:
                df_metas_prod_f = df_metas_prod_f[df_metas_prod_f["LOJA"].isin(lojas_r)]
            if "REGIAO" in df_sup.columns:
                df_sup_f = df_sup_f[df_sup_f["REGIAO"] == filtro_regiao]
            if not df_analise_f.empty and "REGIAO" in df_analise_f.columns:
                df_analise_f = df_analise_f[df_analise_f["REGIAO"] == filtro_regiao]
            if not df_cancelados_f.empty and "REGIAO" in df_cancelados_f.columns:
                df_cancelados_f = df_cancelados_f[df_cancelados_f["REGIAO"] == filtro_regiao]

        render_status_bar(
            len(df_f),
            ultima_data,
            filtro_regiao,
            num_em_analise=len(df_analise_f),
        )

        # ── Aviso de pontuacao com fallback ───────
        df_pontos = carregar_pontuacao_efetiva(mes, ano)
        if not df_pontos.empty:
            fallbacks = df_pontos[
                df_pontos["is_fallback"] == True  # noqa
            ]
            if not fallbacks.empty:
                with st.expander(
                    "Info: Pontuacao usando dados de periodo anterior (fallback)",
                    expanded=False,
                ):
                    st.info(
                        "Algumas categorias estao "
                        "usando pontuacao de um "
                        "periodo anterior pois o "
                        "periodo atual nao tem dados."
                    )
                    exibir_tabela(
                        fallbacks[
                            [
                                "categoria_codigo",
                                "pontos",
                                "periodo_origem",
                            ]
                        ].rename(
                            columns={
                                "categoria_codigo": "Categoria",
                                "pontos": "Pontos",
                                "periodo_origem": "Origem",
                            }
                        )
                    )

        # ── Calculos de KPIs ─────────────────────
        kpis = calcular_kpis_gerais(
            df_f,
            df_metas_f,
            df_metas_prod_f,
            ano,
            mes,
            dia_atual,
            df_sup_f,
        )

        kpis_analise = calcular_kpis_analise(
            df_analise_f,
            df_f,
            du_decorridos,
        )

        kpis_cancel = calcular_kpis_cancelados(
            df_cancelados_f,
            df_f,
            df_analise_f,
        )

        medias = calcular_medias_du_por_nivel(
            df_f,
            du_decorridos,
            df_sup_f,
        )

        metas_prod_diarias = calcular_metas_produto_diarias(
            df_f,
            df_metas_prod_f,
            kpis.get("du_total", 0),
            du_decorridos,
        )

        kpis_qtd = calcular_kpis_qtd_produtos(
            df_f,
            df_analise_f,
            df_metas_prod_f,
            kpis.get("du_total", 0),
            du_decorridos,
        )

        # ── Perfil efetivo (para gating de UI) ────
        from src.dashboard.rls import _obter_perfil_efetivo
        perfil_efetivo = _obter_perfil_efetivo()
        role = (
            perfil_efetivo["perfil"]
            if perfil_efetivo
            else None
        )

        # Serie diaria de valor pago (para sparkline do
        # card hero). Agrega sem custo extra de query:
        # df_f ja esta carregado/filtrado.
        daily_pago = None
        if "DATA" in df_f.columns and not df_f.empty:
            df_com_data = df_f.dropna(subset=["DATA"])
            if not df_com_data.empty:
                serie = (
                    df_com_data.groupby(
                        df_com_data["DATA"].dt.date
                    )["VALOR"]
                    .sum()
                    .sort_index()
                )
                if len(serie) >= 2:
                    daily_pago = serie.tolist()

        # Consultor nao ve cards gerenciais; sua aba
        # renderiza os cards pessoais
        if pode_ver("cards_gerenciais", role):
            criar_cards_indicadores_principais(
                kpis,
                kpis_analise,
                kpis_cancel,
                medias,
                daily_pago=daily_pago,
            )
            criar_cards_metas_produto(metas_prod_diarias)
            criar_cards_qtd_produto(kpis_qtd)

        # ── Navegacao principal ───────────────────

        # Monta abas conforme a matriz de permissoes
        abas_disponiveis = [
            ("tab_consultor", "Meu Dashboard", "speedometer2"),
            ("tab_produtos", "Produtos", "tags-fill"),
            ("tab_regioes", "Regioes", "map-fill"),
            ("tab_rankings_lojas", "Rankings", "trophy-fill"),
            ("tab_analiticos", "Analiticos", "bar-chart-fill"),
            ("tab_evolucao", "Evolucao", "graph-up-arrow"),
            ("tab_em_analise", "Em Analise", "clock-history"),
            ("tab_detalhes", "Detalhes", "table"),
        ]
        tab_items = [
            sac.TabsItem(label=rotulo, icon=icone)
            for chave, rotulo, icone in abas_disponiveis
            if pode_ver(chave, role)
        ]

        if not tab_items:
            st.warning(
                "Nenhuma aba disponivel para seu perfil."
            )
            return

        tab = sac.tabs(
            items=tab_items,
            align="center",
            variant="outline",
        )

        if tab == "Meu Dashboard":
            # Escopo do consultor (nome vindo do escopo)
            escopo = (
                perfil_efetivo.get("escopo", [])
                if perfil_efetivo
                else []
            )
            consultor_nome = escopo[0] if escopo else ""
            loja_consultor = None
            if (
                not df_f.empty
                and "LOJA" in df_f.columns
                and not df_f["LOJA"].isna().all()
            ):
                loja_consultor = df_f["LOJA"].iloc[0]
            elif (
                consultor_nome
                and not df_full.empty
                and "CONSULTOR" in df_full.columns
            ):
                sub = df_full[
                    df_full["CONSULTOR"] == consultor_nome
                ]
                if not sub.empty and "LOJA" in sub.columns:
                    loja_consultor = sub["LOJA"].iloc[0]

            metas_cons = (
                carregar_metas_consultor(
                    mes, ano, loja_consultor,
                )
                if loja_consultor
                else {"meta_prata": 0.0, "meta_ouro": 0.0}
            )

            render_tab_consultor(
                df_meu=df_f,
                df_analise_meu=df_analise_f,
                df_cancelados_meu=df_cancelados_f,
                df_full=df_full,
                metas_consultor=metas_cons,
                consultor_nome=consultor_nome,
                ano=ano,
                mes=mes,
                dia_atual=dia_atual,
            )
        elif tab == "Produtos":
            render_tab_produtos(
                df_f,
                df_metas_prod_f,
                categorias,
                ano,
                mes,
                dia_atual,
                df_sup_f,
                df_analise=df_analise_f,
                du_total=kpis.get("du_total", 0),
                du_decorridos=du_decorridos,
                df_full=df_full,
                df_metas_produto_full=df_metas_produto_full,
                df_ant=df_ant_full,
                du_dec_ant=du_dec_ant,
            )
        elif tab == "Regioes":
            render_tab_regioes(
                df_f,
                df_metas_f,
                ano,
                mes,
                dia_atual,
                df_sup_f,
                df_metas_prod_f,
                categorias,
                df_full,
                df_metas_produto_full,
            )
        elif tab == "Rankings":
            render_tab_rankings(
                df_f,
                df_metas_f,
                df_sup_f,
                du_decorridos,
            )
        elif tab == "Analiticos":
            render_tab_analiticos(
                df_f, df_sup_f, df_analise_f,
                df_cancelados_f,
            )
        elif tab == "Evolucao":
            render_tab_evolucao(
                df_f,
                ano,
                mes,
                kpis,
            )
        elif tab == "Em Analise":
            render_tab_em_analise(df_analise_f, df_sup_f)
        elif tab == "Detalhes":
            render_tab_detalhes(df_f)

    except Exception as e:
        st.error(f"Erro inesperado: {e}")
        st.exception(e)


if __name__ == "__main__":
    main()
