"""
Dashboard interativo de vendas — MGCred.

Entrypoint principal para deploy no Streamlit Cloud.
Consome dados diretamente do banco Supabase (PostgreSQL),
via views v_* e RPCs (ex.: obter_pontuacao_periodo).
Autocontido: nao depende dos modulos de KPI antigos
(kpi_dashboard.py, kpi_analiticos.py) nem dos loaders
de planilha (column_mapper.py, pontuacao_loader.py).

Frontend: streamlit-antd-components para navegacao,
tabelas via st.dataframe, CSS design system customizado.
"""

import logging
import sys
import warnings
from datetime import date, datetime
from pathlib import Path
from typing import Callable, NamedTuple

import pandas as pd
import streamlit as st
import streamlit_antd_components as sac

sys.path.insert(0, str(Path(__file__).parent))

from src.dashboard.auth import (
    tela_login,
    usuario_logado,
)
from src.dashboard.chat_ia.tools import ChatContext
from src.dashboard.components.tables import exibir_tabela
from src.dashboard.kpis.gerais import (
    calcular_kpis_analise,
    limpar_cache_kpis,
    obter_kpis_gerais_periodo,
    obter_kpis_pipeline_periodo,
    obter_kpis_qtd_periodo,
    obter_medias_organizacao_periodo,
    obter_medias_periodo,
    obter_metas_prod_diarias_periodo,
    peso_headcount_escopo,
    serie_diaria_pago,
)
from src.dashboard.pages.config import render_pagina_config
from src.dashboard.pages.dashboard_pontuacao import (
    render_dashboard_pontuacao,
    render_diagnostico_pontuacao,
)
from src.dashboard.pages.detalhes_cards import render_drilldown_card
from src.dashboard.loaders import (
    carregar_consultores_ativos,
    carregar_contratos_pagos_intervalo,
    carregar_headcount_ponderado,
    carregar_vinculos_consultores,
    consolidar_dados,
    carregar_universo_lojas,
    carregar_metas_produto_consultor,
    carregar_pagamentos_online,
    carregar_periodo_dashboard,
    carregar_pontuacao_efetiva,
    carregar_reconquista,
)
from src.dashboard.permissions import pode_ver
from src.dashboard.rls import (
    aplicar_rls,
    aplicar_rls_metas,
)
from src.dashboard.tabs.analiticos import render_tab_analiticos
from src.dashboard.tabs.chat_ia import limpar_cache_chat_ia, render_tab_chat_ia
from src.dashboard.tabs.detalhes import render_tab_detalhes
from src.dashboard.tabs.em_analise import render_tab_em_analise
from src.dashboard.tabs.evolucao import render_tab_evolucao
from src.dashboard.tabs.gestao_consultores import render_tab_gestao
from src.dashboard.tabs.pagamentos_online import render_tab_pagamentos_online
from src.dashboard.tabs.produtos import (
    limpar_cache_comparativos,
    render_tab_produtos,
)
from src.dashboard.tabs.rankings import render_tab_rankings
from src.dashboard.tabs.regioes import render_tab_regioes
from src.dashboard.ui.header import (
    render_header,
    render_status_bar,
)
from src.dashboard.ui.kpi_cards import (  # noqa: F401  (re-exports: criar_cards_metas_produto, criar_cards_qtd_produto)
    criar_cards_indicadores_principais,
    criar_cards_metas_produto,
    criar_cards_qtd_produto,
)
from src.dashboard.ui.kpi_cards_reforma import render_kpis_reforma
from src.dashboard.ui.prioridades_acao import render_prioridades_acao
from src.dashboard.ui.resumo_executivo import render_resumo_executivo
from src.dashboard.ui.sidebar import (
    aplicar_filtros_ui,
    filtrar_metas_ui,
    render_periodo,
    render_sidebar_filtros_perfil,
    render_sidebar_usuario,
    render_sidebar_visualizar_como,
    render_theme_toggle,
)
from src.dashboard.ui.skeleton import render_skeleton
from src.dashboard.ui.theme import (
    aplicar_tema,
    carregar_estilos_customizados,
    get_theme,
    ocultar_widgets_nativos,
    render_overlay_fresh_login,
)
from src.dashboard.ui.theme_claro_avancado import aplicar_tema_claro_avancado
from src.shared.dias_uteis import calcular_dias_uteis

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*ScriptRunContext.*")

logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Dashboard de Vendas - MGCred",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ══════════════════════════════════════════════════════
# Helpers de main() — blocos coesos extraidos
# ══════════════════════════════════════════════════════


class _AbaNav(NamedTuple):
    """Entrada do registro de abas da navegacao principal.

    Carrega os metadados da aba **e** como renderiza-la, para que exista
    uma fonte de verdade so: antes, a lista de metadados e o ``if/elif``
    de despacho eram duas listas paralelas das mesmas nove abas, e a aba
    nova tinha que ser lembrada nos dois lugares.

    NamedTuple pelo mesmo motivo de ``DadosPeriodo`` (loaders): tres dos
    quatro campos sao ``str``, entao posicao sozinha e fragil demais — e
    a construcao continua tao curta quanto a tupla que substituiu.

    Campos:
        permissao: chave em ``permissions.MATRIZ`` (gate de perfil).
        rotulo: texto da aba. E tambem a chave de despacho — e o que
            ``st.pills`` devolve.
        icone: nome do Material Symbol (``:material/<nome>:``).
        render: callable de aridade zero (closure sobre os dados ja
            carregados em ``main()``). So a da aba selecionada roda.
    """

    permissao: str
    rotulo: str
    icone: str
    render: Callable[[], None]


def _limpar_caches_periodo() -> None:
    """Limpeza disparada pelo botao "Atualizar Dados" da sidebar.

    Composta AQUI porque cada cache pertence a um modulo diferente e
    ninguem sozinho conhece o conjunto: ``main()`` e quem orquestra os
    quatro. Cada modulo dono expoe a propria funcao de limpeza — a
    alternativa (a sidebar dar ``pop`` nas chaves pelo nome) ja custou
    um bugfix quando um par de chaves novo nasceu num modulo e nao foi
    lembrado no botao.

    ``_periodo_carregado`` e estado do proprio ``main()`` (controla o
    skeleton da primeira carga do periodo), por isso e a unica chave
    removida aqui pelo nome.
    """
    st.cache_data.clear()
    limpar_cache_kpis(st.session_state)
    limpar_cache_comparativos()
    limpar_cache_chat_ia()
    st.session_state.pop("_periodo_carregado", None)


def _render_aviso_pontuacao_fallback(df_pontos: pd.DataFrame) -> None:
    """Expander avisando quando ha categorias com pontuacao de fallback."""
    if df_pontos.empty:
        return
    fallbacks = df_pontos[df_pontos["is_fallback"] == True]  # noqa
    if fallbacks.empty:
        return
    with st.expander(
        "Info: Pontuacao usando dados de periodo anterior (fallback)",
        expanded=False,
    ):
        st.info(
            "Algumas categorias estao usando pontuacao de um "
            "periodo anterior pois o periodo atual nao tem dados."
        )
        exibir_tabela(
            fallbacks[
                ["categoria_codigo", "pontos", "periodo_origem"]
            ].rename(
                columns={
                    "categoria_codigo": "Categoria",
                    "pontos": "Pontos",
                    "periodo_origem": "Origem",
                }
            )
        )


# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════


def main():
    """Funcao principal do dashboard."""
    carregar_estilos_customizados()
    aplicar_tema()

    # Camada complementar Aurora — só no modo claro,
    # SEMPRE depois de aplicar_tema() (sobrescreve tokens).
    if get_theme() == "light":
        aplicar_tema_claro_avancado()

    # ── Autenticacao ──────────────────────────────
    if not tela_login():
        return

    # Oculta widgets nativos do Streamlit (deploy, animação, menu ⋮)
    # apenas para não-admins. O motivo de esconder os widgets um a um,
    # e nao o header inteiro, esta no docstring de ocultar_widgets_nativos.
    _perfil_logado = (usuario_logado() or {}).get("perfil")
    if _perfil_logado != "admin":
        ocultar_widgets_nativos()

    # Overlay de transição para login recém-efetuado. A flag e consumida
    # aqui (pop): o overlay some sozinho por animação CSS, sem rerun.
    if st.session_state.pop("_fresh_login", False):
        _user = usuario_logado()
        _nome = (_user.get("nome", "").split()[0]) if _user else ""
        render_overlay_fresh_login(_nome)

    with st.sidebar:
        # ── Logo ocupa toda a largura ──
        logo = (
            "assets/logo-grayscale.png"
            if get_theme() == "dark"
            else "assets/logotipo-mg-cred.png"
        )
        st.image(logo, width="stretch")

        # ── Theme mode toggle 3-state (light/system/dark) ──
        render_theme_toggle()

        render_sidebar_usuario()

        # ── Periodo (colapsavel) ──────────────────────
        ano, mes = render_periodo(on_refresh=_limpar_caches_periodo)

    # ── Toggle Vendas ⇄ Pontuacao (state-driven) ──────
    # Decide a view ANTES do header para que o titulo acompanhe
    # a selecao do usuario.
    _view = st.session_state.get("dashboard_view", "vendas")
    if _view == "pontuacao":
        render_header(
            mes=mes,
            ano=ano,
            titulo="Dashboard de Pontuação",
            subtitulo="Apuração de pontuação e atingimento - MGCred",
        )
    else:
        render_header(mes=mes, ano=ano)

    # Segmented control logo abaixo do header — centralizado.
    _toggle_cols = st.columns([3, 4, 3])
    with _toggle_cols[1]:
        _sel = sac.segmented(
            items=[
                sac.SegmentedItem(
                    label="Dashboard de Vendas",
                    icon="bar-chart-fill",
                ),
                sac.SegmentedItem(
                    label="Dashboard de Pontuação",
                    icon="award-fill",
                ),
            ],
            index=1 if _view == "pontuacao" else 0,
            align="center",
            color="blue",
            key="sel_dashboard_view",
        )
    _nova_view = "pontuacao" if _sel == "Dashboard de Pontuação" else "vendas"
    if _nova_view != _view:
        st.session_state["dashboard_view"] = _nova_view
        st.rerun()

    # ── Config: renderiza sem carregar contratos ──────
    if st.session_state.get("mostrar_config"):
        render_pagina_config()
        return

    # ── Dashboard: carrega contratos apenas aqui ──────
    try:
        # Skeleton + status sao exibidos apenas na primeira carga
        # do periodo (cache miss). Em interacoes subsequentes (mudar
        # filtro, trocar de aba) os loaders cacheados respondem em
        # ms e o skeleton/status causariam apenas flicker visual.
        _chave_carga = (mes, ano)
        _eh_primeira = (
            st.session_state.get("_periodo_carregado") != _chave_carga
        )

        _is_admin = (usuario_logado() or {}).get("perfil") == "admin"

        if _eh_primeira:
            skeleton_ph = st.empty()
            with skeleton_ph:
                render_skeleton()
            _status_obj = st.status(
                ":shimmer[Carregando dados...]", expanded=False
            )
            _status_obj.__enter__()
        else:
            skeleton_ph = None
            _status_obj = None

        def _upd_status(label: str) -> None:
            if _status_obj is not None:
                _status_obj.update(label=f":shimmer[{label}]")

        # Carga do periodo: o loader reporta cada etapa via callback e
        # devolve os frames ja normalizados (regras do pipeline + nomes
        # de display). A UI de progresso (skeleton/status) fica aqui.
        (
            df,
            df_metas,
            df_sup,
            categorias,
            df_metas_produto,
            df_analise,
            df_cancelados,
        ) = carregar_periodo_dashboard(mes, ano, on_progress=_upd_status)

        if _status_obj is not None:
            _status_obj.update(label="Dados carregados", state="complete")
            _status_obj.__exit__(None, None, None)
            _status_obj.empty()
            skeleton_ph.empty()
            st.session_state["_periodo_carregado"] = _chave_carga

        _n_cancel_admin = len(df_cancelados) if _is_admin else 0

        # ── Diagnostico de pontuacao (admin) ─────
        # O expander e ferramenta de suporte: so aparece se a
        # consolidacao gravou diagnostico E o usuario e admin.
        diag = st.session_state.get("_diag_pontuacao")
        if diag and _is_admin:
            render_diagnostico_pontuacao(diag)

        # Calcular dias uteis do periodo (para usar nos KPIs)
        hoje = datetime.now()
        dia_ref = hoje.day if (ano == hoje.year and mes == hoje.month) else 1
        _, du_decorridos, _ = calcular_dias_uteis(ano, mes, dia_ref)

        if df.empty and df_analise.empty and df_cancelados.empty:
            st.warning("Nenhum dado encontrado para o periodo selecionado.")
            return

        if df.empty:
            st.info(
                "Nenhum contrato pago no periodo. Exibindo apenas propostas em analise."
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

        # ── Snapshots pre-RLS para heatmap comparativo ──
        # Aliases simples: aplicar_rls retorna novos DataFrames
        # filtrados, entao os originais nao sao mutados pela
        # cadeia abaixo. Evita .copy() de DataFrames grandes
        # em todo rerun.
        df_full = df
        df_metas_full = df_metas
        df_metas_produto_full = df_metas_produto
        df_sup_full = df_sup

        # Médias da organização são calculadas após resolver o perfil
        # efetivo (ver bloco de KPIs abaixo), pois dependem do nível
        # do perfil para definir a granularidade do agrupamento.

        # ── Sidebar fase 1: Visualizar Como (admin/gestor) ──
        # Renderizado ANTES do aplicar_rls para que a mudanca de
        # perfil simulado entre em vigor no mesmo rerun (sem precisar
        # de st.rerun() explicito). Usa df_full (pre-RLS) para listar
        # todas as regioes/lojas/consultores disponiveis.
        with st.sidebar:
            render_sidebar_visualizar_como(df_full)

        # ── Perfil efetivo (resolvido APOS Visualizar Como) ──
        from src.dashboard.rls import _obter_perfil_efetivo

        perfil_efetivo = _obter_perfil_efetivo()
        role = perfil_efetivo["perfil"] if perfil_efetivo else None

        # ── Drill-down dos cards de contexto (fail-closed) ──
        # Le o query param `?card=<key>` UMA vez por navegacao e o
        # consome (clear). So promove a `card_page` se o perfil pode ver
        # o drill-down dos cards E a key e uma das quatro validas; param
        # forjado por perfil sem acesso (supervisor/consultor) e ignorado
        # (nao deixa estado pendurado). O roteamento em si ocorre adiante,
        # ja com os dados carregados.
        _CARDS_VALIDOS = {
            "em_analise",
            "cancelados",
            "media_consultor",
            "media_loja",
        }
        _card_param = st.query_params.get("card")
        if _card_param is not None:
            if pode_ver("cards_drilldown", role) and _card_param in _CARDS_VALIDOS:
                st.session_state["card_page"] = _card_param
            st.query_params.clear()

        # ── RLS: filtrar dados por perfil ─────────
        # df_sup NAO e recortado por escopo: a lista de supervisores so
        # serve para EXCLUSAO em metricas consultor-level (nunca e
        # exibida). Recorta-la deixava escapar supervisor cujo cadastro
        # em `supervisores` aponta outra loja/regiao (ex.: remanejamento
        # ainda nao refletido) — ele aparecia como consultor na regiao
        # visualizada. A exclusao deve usar sempre a lista global.
        df = aplicar_rls(df)
        df_metas = aplicar_rls_metas(df_metas, df)
        df_metas_produto = aplicar_rls_metas(df_metas_produto, df)
        if not df_analise.empty:
            df_analise = aplicar_rls(df_analise)
        if not df_cancelados.empty:
            df_cancelados = aplicar_rls(df_cancelados)

        # Calcular dias uteis (usar data atual se df vazio)
        if not df.empty:
            ultima_data = df["DATA"].max()
            dia_atual = ultima_data.day if hasattr(ultima_data, "day") else None
            ultima_atualizacao = (
                df["CREATED_AT"].max()
                if "CREATED_AT" in df.columns
                else None
            )
        else:
            ultima_data = None
            ultima_atualizacao = None
            dia_atual = datetime.now().day
        _, du_decorridos, _ = calcular_dias_uteis(ano, mes, dia_atual)

        # Data de referencia da apuracao: ULTIMO DIA COM DADO na
        # competencia — a mesma que resolve `du_decorridos` acima. Vai
        # para o denominador individual de produtividade, que sem ela
        # contaria o mes inteiro contra a producao de hoje. Sem dado no
        # periodo nao ha referencia: `None` deixa a competencia
        # inteira, e o numerador zerado ja diz o que precisa.
        data_ref_apuracao = (
            date(ano, mes, dia_atual) if ultima_data is not None else None
        )

        # ── Dados filtrados (RLS ja aplicado) ─────────
        # Aliases: aplicar_filtros_ui (abaixo) ja retorna novos
        # DataFrames com .copy() interno, entao manter referencias
        # aqui e suficiente.
        df_f = df
        df_metas_f = df_metas
        df_metas_prod_f = df_metas_produto
        df_sup_f = df_sup
        df_analise_f = df_analise
        df_cancelados_f = df_cancelados

        # ── Sidebar fase 2: Filtros granulares (gerente/supervisor) ──
        # Renderizado APOS o RLS porque os filtros granulares de Loja
        # e Consultor devem listar apenas o escopo permitido.
        with st.sidebar:
            render_sidebar_filtros_perfil(df_f, df_sup_f, role or "")

        # ── Aplicar filtros granulares de UI (pos-RLS) ─
        _ui_lojas = st.session_state.get("ui_filtro_lojas") or []
        _ui_cons = st.session_state.get("ui_filtro_consultor") or ""
        if _ui_lojas or _ui_cons:
            df_f = aplicar_filtros_ui(df_f)
            df_analise_f = aplicar_filtros_ui(df_analise_f)
            df_cancelados_f = aplicar_filtros_ui(df_cancelados_f)
            df_metas_f = filtrar_metas_ui(df_metas_f, df_f)
            df_metas_prod_f = filtrar_metas_ui(df_metas_prod_f, df_f)

        # ── Denominador PONDERADO do headcount (migration 091) ─
        # Mesma fonte do `weightedHeadcount` do Caderno, para que os dois
        # parem de responder numeros diferentes a "quantos consultores
        # dividem esta producao".
        #
        # O escopo sai do FILTRO, nunca da producao: `aplicar_rls` +
        # `aplicar_filtros_ui` recortam por perfil e por loja, e uma loja
        # dentro do escopo continua no denominador mesmo sem contrato no
        # periodo — que e o vies inteiro que este denominador corrige.
        # `aplicar_filtros_ui` so filtra CONSULTOR quando a coluna existe,
        # e este frame e por loja; o caso de consultor selecionado e
        # tratado dentro de `peso_headcount_escopo`, que devolve None.
        _df_headcount = aplicar_filtros_ui(
            aplicar_rls(carregar_headcount_ponderado(mes, ano))
        )
        peso_headcount = peso_headcount_escopo(_df_headcount, _ui_cons)

        render_status_bar(
            len(df_f),
            ultima_data,
            "Todas",
            num_em_analise=len(df_analise_f),
            num_cancelados=_n_cancel_admin,
            ultima_atualizacao=ultima_atualizacao,
        )

        # ── Aviso de pontuacao com fallback ───────
        df_pontos = carregar_pontuacao_efetiva(mes, ano)
        # Mapa categoria_codigo -> PTS, reusado pela pagina de Pontuacao
        # para calcular pontos em df_analise/df_cancelados.
        mapa_pontos: dict = (
            dict(
                zip(
                    df_pontos["categoria_codigo"],
                    df_pontos["pontos"].astype(float),
                )
            )
            if not df_pontos.empty
            else {}
        )
        _render_aviso_pontuacao_fallback(df_pontos)

        # ── Meta MIX por consultor: troca df_metas_prod_f ─
        # Ativa quando o perfil nativo é consultor OU quando outro perfil
        # filtrou até um consultor específico via filtro granular de UI.
        _consultor_selecionado = bool(st.session_state.get("ui_filtro_consultor"))
        if role == "consultor" or _consultor_selecionado:
            _mpc = carregar_metas_produto_consultor(mes, ano)
            _mpc = filtrar_metas_ui(_mpc, df_f)
            if not _mpc.empty:
                df_metas_prod_f = _mpc

        # ── KPIs gerais (memoizados em session_state) ─────
        # A cadeia de calculo vive em kpis/gerais.py, hoje quebrada em
        # seis funcoes `obter_*_periodo` independentes (uma por grupo de
        # KPI). Todas compartilham a MESMA chave de cache, e essa chave e
        # a fronteira entre perfis: mexer nela muda quem ve o que — ver a
        # docstring de `_chave_kpis`.
        #
        # So o grupo "gerais" e pedido AQUI, porque e o unico de que os
        # dois early-returns logo abaixo precisam (a view de pontuacao
        # recebe `kpis`; o drill-down de card le `kpis['du_total']`). Os
        # outros cinco grupos ficam adiante, no bloco "KPIs restantes".
        #
        # Frames de trabalho vao POS-RLS+filtros.
        kpis = obter_kpis_gerais_periodo(
            session_state=st.session_state,
            mes=mes,
            ano=ano,
            role=role,
            perfil_efetivo=perfil_efetivo,
            df=df_f,
            df_metas=df_metas_f,
            df_metas_produto=df_metas_prod_f,
            dia_atual=dia_atual,
            df_sup=df_sup_f,
        )

        # ── Dispatch: Dashboard de Pontuacao ──────────
        # Quando o toggle esta em 'pontuacao', renderizamos apenas a
        # pagina de pontuacao (cards + prioridades em pontos) e
        # encerramos. Nao mostramos os cards de vendas nem as tabs.
        if st.session_state.get("dashboard_view") == "pontuacao":
            render_dashboard_pontuacao(
                kpis=kpis,
                df=df_f,
                df_analise=df_analise_f,
                df_cancelados=df_cancelados_f,
                df_metas_produto=df_metas_prod_f,
                df_sup=df_sup_f,
                mapa_pontos=mapa_pontos,
                du_decorridos=du_decorridos,
                perfil=role,
                peso_headcount=peso_headcount,
            )
            return

        # Reconquista: apuração mensal por dt_fim_relacionamento
        # com defasagem de 1 mês (TTL 10min, RLS aplicada no
        # loader). Carregada uma vez e reusada tanto pelo bloco
        # resumido do header quanto pela sub-aba de Analiticos.
        try:
            dados_reconquista = carregar_reconquista(mes, ano)
        except Exception:
            logger.exception("Falha ao carregar Reconquista")
            dados_reconquista = None

        # Contexto do chat de IA. Nasce None e so e preenchido dentro do
        # bloco `cards_gerenciais` abaixo, que e onde os grupos de KPI
        # que ele carrega (pipeline, medias, quantidades) sao calculados.
        # Hoje a matriz libera esse bloco aos cinco perfis, mas isso e
        # estado da matriz, nao garantia estrutural: se ela mudar, a aba
        # avisa que nao ha contexto em vez de estourar NameError.
        chat_context = None

        # Consultor nao ve cards gerenciais; sua aba
        # renderiza os cards pessoais
        if pode_ver("cards_gerenciais", role):
            # ── Drill-down: pagina de detalhe de um card ──────
            # Quando `card_page` esta setado (promovido pelo read
            # fail-closed acima), renderiza so a pagina de detalhe
            # correspondente (botao de voltar + dispatch vivem no
            # modulo) e encerra aqui, pulando cards e tabs — espelhando
            # o padrao do modo Config.
            _card_page = st.session_state.get("card_page")
            if _card_page:
                render_drilldown_card(
                    _card_page,
                    df=df_f,
                    df_analise=df_analise_f,
                    df_cancelados=df_cancelados_f,
                    df_sup=df_sup_f,
                    du_decorridos=du_decorridos,
                    du_total=kpis.get("du_total", 0),
                    mes=mes,
                    ano=ano,
                    perfil=role,
                )
                return

            # ── KPIs restantes (memoizados em session_state) ──
            # Deliberadamente DEPOIS dos dois `return` acima (view de
            # pontuacao e drill-down de card): nenhum dos dois consome
            # estes grupos, entao calcula-los antes fazia esses caminhos
            # pagarem pipeline, medias, metas por produto e KPIs de
            # quantidade a toa. Quebrar `obter_kpis_periodo` em uma
            # funcao por grupo (ISP) foi o que tornou o adiamento
            # possivel — juntas, elas eram uma chamada indivisivel.
            #
            # Frames de trabalho vao POS-RLS+filtros; os `*_full` sao
            # pre-RLS de proposito (comparativo da organizacao / exclusao
            # de supervisores) e deles nao sai nenhuma linha para a tela,
            # so agregados — ver as docstrings das duas funcoes que os
            # recebem.
            kpis_analise, kpis_cancel = obter_kpis_pipeline_periodo(
                session_state=st.session_state,
                mes=mes,
                ano=ano,
                role=role,
                perfil_efetivo=perfil_efetivo,
                df=df_f,
                df_analise=df_analise_f,
                df_cancelados=df_cancelados_f,
                du_decorridos=du_decorridos,
            )
            medias = obter_medias_periodo(
                session_state=st.session_state,
                mes=mes,
                ano=ano,
                role=role,
                perfil_efetivo=perfil_efetivo,
                df=df_f,
                du_decorridos=du_decorridos,
                df_sup=df_sup_f,
                peso_headcount=peso_headcount,
            )
            medias_organizacao = obter_medias_organizacao_periodo(
                session_state=st.session_state,
                mes=mes,
                ano=ano,
                role=role,
                perfil_efetivo=perfil_efetivo,
                df_full=df_full,
                du_decorridos=du_decorridos,
                df_sup_full=df_sup_full,
            )
            metas_prod_diarias = obter_metas_prod_diarias_periodo(
                session_state=st.session_state,
                mes=mes,
                ano=ano,
                role=role,
                perfil_efetivo=perfil_efetivo,
                df=df_f,
                df_metas=df_metas_f,
                df_metas_produto=df_metas_prod_f,
                df_sup=df_sup_f,
                dia_atual=dia_atual,
                du_decorridos=du_decorridos,
            )
            kpis_qtd = obter_kpis_qtd_periodo(
                session_state=st.session_state,
                mes=mes,
                ano=ano,
                role=role,
                perfil_efetivo=perfil_efetivo,
                df=df_f,
                df_metas=df_metas_f,
                df_metas_produto=df_metas_prod_f,
                df_sup=df_sup_f,
                df_analise=df_analise_f,
                df_full=df_full,
                df_sup_full=df_sup_full,
                dia_atual=dia_atual,
                du_decorridos=du_decorridos,
            )
            # Sem cache: calculo puro e barato sobre um frame ja em
            # memoria (ver docstring de `serie_diaria_pago`).
            daily_pago = serie_diaria_pago(df_f)

            # Contexto do assistente de IA: so frames POS-RLS+filtros e
            # os KPIs ja calculados acima. Nenhum `*_full` entra aqui —
            # as tools fecham sobre este contexto e herdariam o escopo
            # pre-RLS (ver docstring de ChatContext).
            chat_context = ChatContext(
                df=df_f,
                df_metas=df_metas_f,
                df_sup=df_sup_f,
                df_analise=df_analise_f,
                df_cancelados=df_cancelados_f,
                kpis=kpis,
                kpis_qtd=kpis_qtd,
                kpis_analise=kpis_analise,
                kpis_cancel=kpis_cancel,
                medias=medias,
                mes=mes,
                ano=ano,
                dia_atual=dia_atual,
                du_decorridos=du_decorridos,
                role=role,
            )

            # KPIs Principais Reformulados
            # (3 principais + contexto + MIX + Aceleradores
            # + Reconquista + Média/Projeção)
            render_kpis_reforma(
                kpis=kpis,
                kpis_analise=kpis_analise,
                kpis_cancel=kpis_cancel,
                medias=medias,
                metas_produto=metas_prod_diarias,
                kpis_qtd=kpis_qtd,
                daily_pago=daily_pago,
                medias_organizacao=medias_organizacao,
                perfil=role,
                reconquista=dados_reconquista,
                mes=mes,
                ano=ano,
            )

            # Resumo Executivo comentado (após KPIs visuais)
            render_resumo_executivo(
                kpis=kpis,
                kpis_analise=kpis_analise,
                kpis_cancel=kpis_cancel,
                metas_produto=metas_prod_diarias,
            )

            # NOVA REFORMA UX/UI: Bloco 3 - Prioridades de Ação
            render_prioridades_acao(
                metas_produto=metas_prod_diarias,
                df=df_f,
                df_metas_produto=df_metas_prod_f,
                kpis=kpis,
                perfil=role,
                df_sup=df_sup_f,
                du_decorridos=du_decorridos,
                categorias=categorias,
                df_analise=df_analise_f,
            )

        # ── Navegacao principal ───────────────────

        # Rankings e Gestao preparam dados antes de chamar o renderer com
        # statements (atribuicao, def aninhado), o que lambda nao aceita:
        # entram no registro como funcao nomeada. As outras sete cabem
        # numa expressao e entram como lambda ali mesmo.

        def _render_rankings() -> None:
            # Universos de ativos p/ a visao de controle (sem producao).
            # Carregam global e passam pelo aplicar_rls (gerente enxerga
            # so a propria regiao via REGIAO_ATUAL; fail-closed). A aba
            # so os usa para admin/gestor/gerente_comercial.
            _univ_lojas = aplicar_rls(carregar_universo_lojas(mes, ano))
            _univ_cons = aplicar_rls(carregar_consultores_ativos())
            render_tab_rankings(
                df_full,
                df_metas_full,
                df_sup_full,
                df_scope=df_f,
                perfil=role,
                df_lojas_univ=_univ_lojas,
                df_cons_univ=_univ_cons,
            )

        def _render_gestao() -> None:
            # Universo de consultores ATIVOS: sem ele a aba so enxerga
            # quem produziu, e um criterio "ate R$ X" perde quem vendeu
            # nada. Passa pelo mesmo recorte de df_f — aplicar_rls
            # (perfil) e os filtros granulares da sidebar — para que a
            # lista nao traga consultor de loja que o usuario filtrou.
            _univ_cons_gestao = aplicar_filtros_ui(
                aplicar_rls(carregar_consultores_ativos())
            )
            # Metas por produto de escopo CONSULTOR (alvo individual de
            # cada consultor da loja): sustentam a base "% da meta" nos
            # criterios. Ausentes, a base e ignorada com aviso na aba.
            _metas_gestao = filtrar_metas_ui(
                carregar_metas_produto_consultor(mes, ano), df_f
            )

            def _carregar_intervalo_gestao(ini, fim, campo):
                """Contratos pagos num intervalo livre, no escopo do usuario.

                A aba so escolhe as datas; o recorte de seguranca fica
                aqui, igual ao de df_f: aplicar_rls (perfil) primeiro,
                filtros granulares da sidebar depois. Um intervalo
                personalizado nao pode ser porta para ver o que o mes
                selecionado nao mostraria.
                """
                bruto, aviso = carregar_contratos_pagos_intervalo(
                    ini, fim, campo
                )
                if bruto.empty:
                    return bruto, aviso
                return aplicar_filtros_ui(aplicar_rls(bruto)), aviso

            # Denominador INDIVIDUAL da sub-visao de performance: dias
            # uteis de vinculo por pessoa (ledger consultor_vigencia).
            # Passa pelo MESMO recorte de df_f — o escopo sai do
            # filtro, nunca da producao —, para que numerador e
            # denominador nunca respondam por populacoes diferentes.
            _vinculos_gestao = aplicar_filtros_ui(
                aplicar_rls(
                    carregar_vinculos_consultores(
                        mes, ano, data_ref_apuracao
                    )
                )
            )

            def _carregar_competencia_gestao(m: int, a: int):
                """Producao, vinculos e supervisores de UMA competencia.

                Alimenta a serie historica da sub-visao de performance.
                Usa a consolidacao (nao os contratos crus) para que o
                numerador de meses anteriores siga as MESMAS regras de
                VALOR do mes na tela. Mesmo recorte de seguranca de
                df_f: aplicar_rls (perfil) e depois os filtros
                granulares da sidebar.
                """
                bruto, _, sup_comp = consolidar_dados(m, a)
                if bruto.empty:
                    return bruto, pd.DataFrame(), sup_comp
                return (
                    aplicar_filtros_ui(aplicar_rls(bruto)),
                    aplicar_filtros_ui(
                        aplicar_rls(carregar_vinculos_consultores(m, a))
                    ),
                    sup_comp,
                )

            render_tab_gestao(
                df_f,
                df_sup_f,
                _univ_cons_gestao,
                _metas_gestao,
                _carregar_intervalo_gestao,
                df_vinculos=_vinculos_gestao,
                mes=mes,
                ano=ano,
                carregar_competencia=_carregar_competencia_gestao,
            )

        # Registro unico das abas: permissao + rotulo + icone + render na
        # MESMA entrada. Acrescentar uma aba e acrescentar uma linha aqui
        # (mais a chave em permissions.MATRIZ) — nao ha mais um if/elif
        # de despacho para manter em sincronia com a lista de metadados.
        # Cada `render` fecha sobre os dados ja carregados acima e so a da
        # aba selecionada executa, entao os loaders proprios de uma aba
        # continuam pagos apenas por quem a abre (render lazy do st.pills).
        # Icones sao Material Symbols (:material/<nome>:), nao Bootstrap:
        # a navegacao usa st.pills, que renderiza markdown no rotulo.
        registro_abas = (
            _AbaNav(
                "tab_produtos",
                "Produtos",
                "sell",
                # Os dois meses de comparacao (anterior e YoY) sao
                # carregados dentro da propria aba: sao lazy — so ela os
                # consome — e o cache deles vive junto de quem os usa
                # (tabs/produtos.py).
                lambda: render_tab_produtos(
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
                ),
            ),
            _AbaNav(
                "tab_regioes",
                "Regioes",
                "map",
                lambda: render_tab_regioes(
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
                ),
            ),
            _AbaNav(
                "tab_rankings_lojas",
                "Rankings",
                "emoji_events",
                _render_rankings,
            ),
            _AbaNav(
                "tab_analiticos",
                "Analiticos",
                "bar_chart",
                lambda: render_tab_analiticos(
                    df_f,
                    df_sup_f,
                    df_analise_f,
                    df_cancelados_f,
                    perfil=role,
                    reconquista=dados_reconquista,
                ),
            ),
            _AbaNav(
                "tab_evolucao",
                "Evolucao",
                "trending_up",
                lambda: render_tab_evolucao(
                    df_f,
                    ano,
                    mes,
                    kpis,
                ),
            ),
            _AbaNav(
                "tab_em_analise",
                "Em Analise",
                "schedule",
                lambda: render_tab_em_analise(df_analise_f, df_sup_f),
            ),
            _AbaNav(
                "tab_detalhes",
                "Detalhes",
                "table_chart",
                lambda: render_tab_detalhes(df_f),
            ),
            _AbaNav(
                "tab_pagamentos_online",
                "Pagamentos Online",
                "bolt",
                lambda: render_tab_pagamentos_online(
                    carregar_pagamentos_online()
                ),
            ),
            _AbaNav(
                "tab_gestao",
                "Gestao",
                "filter_alt",
                _render_gestao,
            ),
            # `chat_context` so existe se o bloco `cards_gerenciais`
            # rodou. Sem ele a aba avisa, em vez de quebrar.
            _AbaNav(
                "tab_chat_ia",
                "Assistente IA",
                "smart_toy",
                lambda: (
                    render_tab_chat_ia(chat_context)
                    if chat_context is not None
                    else st.info(
                        "Assistente de IA nao disponivel para o seu perfil."
                    )
                ),
            ),
        )

        # Abas conforme a matriz de permissoes.
        rotulos_visiveis = [
            aba.rotulo for aba in registro_abas if pode_ver(aba.permissao, role)
        ]
        icones_aba = {aba.rotulo: aba.icone for aba in registro_abas}
        renders_aba = {aba.rotulo: aba.render for aba in registro_abas}

        if not rotulos_visiveis:
            st.warning("Nenhuma aba disponivel para seu perfil.")
            return

        # Navegacao em st.pills (nao sac.tabs): o button group nativo tem
        # flex-wrap, entao as abas quebram em varias linhas quando nao
        # cabem na largura, em vez de sumirem. O sac.tabs roda dentro de
        # um iframe e o CSS da propria lib esconde o botao de overflow
        # (.ant-tabs-nav-more{display:none}), tornando as abas que
        # transbordam inacessiveis em telas estreitas.
        # `required=True` impede desselecionar e cair sem nenhuma aba.
        tab = st.pills(
            "Navegacao principal",
            options=rotulos_visiveis,
            default=rotulos_visiveis[0],
            required=True,
            format_func=lambda r: f":material/{icones_aba[r]}: {r}",
            label_visibility="collapsed",
            key="nav_principal",
        )

        # Despacho pelo rotulo devolvido pelo st.pills. Sem `else`: rotulo
        # fora do registro nao renderiza nada, como no if/elif anterior
        # (inalcancavel — as options vem do proprio registro).
        _render_aba = renders_aba.get(tab)
        if _render_aba is not None:
            _render_aba()

    except Exception:
        logger.exception("Erro inesperado no main()")
        st.error(
            "Erro inesperado. Tente recarregar a página ou contate o suporte."
        )


if __name__ == "__main__":
    main()
