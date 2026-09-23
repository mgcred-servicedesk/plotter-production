"""
Aba Assistente de IA — conversa sobre os KPIs do periodo selecionado.

Esta aba **so** renderiza a conversa. Quem responde e o
``chat_ia/agent.py`` (laco de tool-use), sobre as tools de
``chat_ia/tools.py`` — que apenas reusam funcoes ja validadas de
``kpis/*.py`` sobre os frames pos-RLS carregados em ``app.py``. O
modelo nunca calcula KPI sozinho.

Contrato do tab renderer (docs/agents/ui-components.md): recebe tudo
pronto (aqui, empacotado num ``ChatContext``), nao executa query e nao
aplica RLS.
"""
import logging

import streamlit as st
import streamlit_antd_components as sac

from src.config.chat_ia_provider import (
    PROVIDERS_COM_CATALOGO,
    provider_por_perfil,
)
from src.config.openrouter_client import (
    OPENROUTER_MODEL,
    listar_modelos_com_tools,
)
from src.dashboard.chat_ia import agent
from src.dashboard.chat_ia.tools import ChatContext
from src.dashboard.rls import _obter_perfil_efetivo

logger = logging.getLogger(__name__)

# Estado desta aba (dono: este modulo).
CHAVE_HISTORICO = "chat_ia_historico"
CHAVE_ESCOPO = "chat_ia_chave"
CHAVE_AVISO = "chat_ia_aviso"
# Modelo escolhido no seletor. Deliberadamente FORA das tres chaves
# acima: e preferencia de quem usa, nao conteudo derivado do recorte de
# dados — trocar de mes nao deve desfazer a escolha de modelo.
CHAVE_MODELO = "chat_ia_modelo"


def limpar_cache_chat_ia() -> None:
    """Invalida a conversa desta aba.

    As tres chaves sao privadas DESTE modulo — quem dispara um refresh
    global (o botao "Atualizar Dados", na sidebar) nao deve conhece-las
    pelo nome (mesmo raciocinio de
    ``tabs/produtos.py::limpar_cache_comparativos``).

    ``_chave_escopo`` (abaixo) ja reinicia a conversa sozinha quando
    mes/perfil/filtros mudam, mas nao cobre "Atualizar Dados" clicado
    para o MESMO periodo/filtro — dado novo chegou no banco, o escopo
    nao mudou, e o historico antigo (com numeros agora desatualizados)
    sobreviveria sem este hook.

    Nao precisa reexecutar nada: a proxima renderizacao encontra as
    chaves ausentes e comeca uma conversa nova.
    """
    st.session_state.pop(CHAVE_HISTORICO, None)
    st.session_state.pop(CHAVE_ESCOPO, None)
    st.session_state.pop(CHAVE_AVISO, None)


@st.cache_data(ttl=3600, show_spinner=False)
def _catalogo_modelos() -> list[dict[str, str]]:
    """Catalogo de modelos da OpenRouter com tool calling.

    TTL de 1h: o catalogo muda em escala de dias, e esta aba
    rerenderiza a cada mensagem do chat — sem cache seria uma
    requisicao HTTP por interacao.

    A excecao sobe de proposito (``st.cache_data`` nao guarda falha):
    quem chama transforma em aviso na tela. Devolver lista vazia aqui
    apareceria como "nenhum modelo disponivel", que e uma falha de rede
    disfarcada de resposta valida.
    """
    return listar_modelos_com_tools()


def _render_seletor_modelo(contexto: ChatContext) -> str | None:
    """Seletor de modelo, quando o provider do perfil tem catalogo.

    Devolve o id escolhido, ou ``None`` para o agent seguir com o
    modelo da configuracao. Providers diretos (Anthropic/OpenAI) nao
    tem catalogo publico aqui e usam modelo fixo — nesse caso a aba nao
    mostra seletor nenhum.
    """
    if provider_por_perfil(contexto.role) not in PROVIDERS_COM_CATALOGO:
        return None

    try:
        catalogo = _catalogo_modelos()
    except Exception:
        logger.exception(
            "Chat IA: falha ao carregar o catalogo de modelos da OpenRouter"
        )
        st.warning(
            "Nao consegui carregar a lista de modelos da OpenRouter. "
            f"Seguindo com o modelo configurado ({OPENROUTER_MODEL})."
        )
        return None

    ids = [modelo["id"] for modelo in catalogo]
    rotulos = {modelo["id"]: modelo["nome"] for modelo in catalogo}

    escolha_atual = st.session_state.get(CHAVE_MODELO)
    if escolha_atual in ids:
        indice = ids.index(escolha_atual)
    else:
        # Escolha ausente ou fora do catalogo atual (modelo saiu do ar
        # ou perdeu tool calling). Limpa ANTES de instanciar o widget:
        # o selectbox levanta se o valor em session_state nao estiver
        # em `options`, e a chave de um widget nao pode ser alterada
        # depois que ele existe.
        st.session_state.pop(CHAVE_MODELO, None)
        if OPENROUTER_MODEL in ids:
            indice = ids.index(OPENROUTER_MODEL)
        else:
            indice = 0
            st.warning(
                f"O modelo configurado ({OPENROUTER_MODEL}) nao esta no "
                "catalogo de modelos com tool calling da OpenRouter. "
                f"Usando {ids[0]} — revise OPENROUTER_MODEL."
            )

    coluna, _ = st.columns([2, 1])
    with coluna:
        escolhido = st.selectbox(
            "Modelo (OpenRouter)",
            options=ids,
            index=indice,
            key=CHAVE_MODELO,
            format_func=lambda id_: f"{rotulos.get(id_, id_)} · {id_}",
            help=(
                "Somente modelos com tool calling: o assistente responde "
                "atraves das tools do dashboard, nunca calculando por "
                "conta propria."
            ),
        )
    st.caption(f"{len(ids)} modelos com tool calling disponiveis.")
    return escolhido


def _chave_escopo(contexto: ChatContext) -> tuple:
    """Chave de validade da conversa.

    **Fronteira de seguranca entre perfis**, pelo mesmo motivo de
    ``_chave_kpis`` (kpis/gerais.py) e ``_chave_mes_comparativo``
    (tabs/produtos.py): o historico vive em ``session_state`` e carrega
    numeros de UM recorte de dados. Se o recorte muda e a conversa
    fica, texto calculado para o escopo anterior segue na tela.

    Sao os mesmos seis componentes, na mesma ordem: periodo
    (``mes``/``ano``), ``perfil`` efetivo (ja considera "Visualizar
    como"), ``escopo`` do perfil efetivo, filtro granular de lojas
    (ordenado, para que a mesma selecao em ordem diferente nao invalide
    a conversa a toa) e filtro granular de consultor.

    Alterar esta funcao muda quem ve o que — nao e ajuste cosmetico.
    """
    perfil = _obter_perfil_efetivo()
    return (
        contexto.mes,
        contexto.ano,
        perfil["perfil"] if perfil else None,
        tuple(perfil.get("escopo", []) if perfil else []),
        tuple(sorted(st.session_state.get("ui_filtro_lojas") or [])),
        st.session_state.get("ui_filtro_consultor") or "",
    )


def _texto_do_conteudo(conteudo) -> str:
    """Extrai so os blocos de texto do ``content`` canônico do chat.

    O historico e heterogeneo: a mensagem do usuario e ``str``, a do
    assistente e a lista de blocos normalizados do provider e o retorno
    de tool e uma lista de ``dict``.
    Blocos que nao sao texto (``tool_use``, ``tool_result``,
    ``thinking``) nao tem o que mostrar no chat e sao ignorados.
    """
    if isinstance(conteudo, str):
        return conteudo.strip()

    partes = []
    for bloco in conteudo or []:
        if isinstance(bloco, dict):
            if bloco.get("type") == "text":
                partes.append(bloco.get("text") or "")
        elif getattr(bloco, "type", None) == "text":
            partes.append(getattr(bloco, "text", "") or "")
    return "\n".join(p for p in partes if p).strip()


def _render_historico(historico: list) -> None:
    """Desenha cada turno com texto visivel como uma bolha de chat.

    Turnos sem texto (a mensagem ``user`` que carrega apenas os
    ``tool_result``) sao pulados: renderiza-los criaria bolhas vazias.
    """
    for mensagem in historico:
        papel = mensagem.get("role")
        if papel not in ("user", "assistant"):
            continue
        texto = _texto_do_conteudo(mensagem.get("content"))
        if not texto:
            continue
        with st.chat_message(papel):
            st.markdown(texto)


def render_tab_chat_ia(contexto: ChatContext) -> None:
    """Renderiza o chat com o assistente de IA."""
    sac.divider(
        label="Assistente de IA",
        icon="chat-dots",
        align="left",
        color="blue",
    )

    if contexto.role != "admin":
        st.info(
            "Em breve: o Assistente de IA multiagente estará disponível "
            "para este perfil."
        )
        st.caption(
            "Recurso novo (Beta), o chat está em fase de teste apenas para "
            "administradores."
        )
        return

    # Invalidacao ANTES de qualquer render: trocar de mes/perfil/filtro
    # nao pode deixar na tela resposta calculada para o escopo anterior.
    chave = _chave_escopo(contexto)
    reiniciou = False
    if st.session_state.get(CHAVE_ESCOPO) != chave:
        reiniciou = bool(st.session_state.get(CHAVE_HISTORICO))
        st.session_state[CHAVE_HISTORICO] = []
        st.session_state[CHAVE_AVISO] = None
        st.session_state[CHAVE_ESCOPO] = chave

    if reiniciou:
        st.info(
            "Conversa reiniciada: o periodo, o perfil ou os filtros "
            "mudaram, e as respostas anteriores valiam para o recorte "
            "antigo."
        )

    modelo = _render_seletor_modelo(contexto)

    historico = st.session_state[CHAVE_HISTORICO]
    _render_historico(historico)

    if not historico:
        st.caption(
            "Exemplos: *quais lojas cresceram em relacao ao mes "
            "anterior?* · *quais consultores tiveram queda de "
            "producao?* · *como estamos indo esse mes?*"
        )

    aviso = st.session_state.get(CHAVE_AVISO)
    if aviso:
        st.warning(aviso)

    pergunta = st.chat_input("Pergunte sobre o desempenho do período...")
    if not pergunta:
        return

    # O historico NAO recebe a pergunta aqui: `responder` ja a acrescenta
    # (`[*historico, {"role": "user", ...}]`) e devolve o historico
    # completo. Acrescentar antes duplicaria a pergunta na conversa.
    turnos_antes = len(historico)
    with st.spinner(":shimmer[Analisando...]"):
        texto, novo_historico = agent.responder(
            pergunta, contexto, historico, modelo=modelo
        )

    st.session_state[CHAVE_HISTORICO] = novo_historico
    # `responder` devolve o historico ORIGINAL quando nao conseguiu
    # responder (chave de API ausente, erro de rede, limite de turnos):
    # nesse caso o texto amigavel nao entra na conversa e precisa ser
    # exibido a parte — senao a pergunta sumiria sem explicacao alguma.
    st.session_state[CHAVE_AVISO] = (
        None if len(novo_historico) > turnos_antes else texto
    )
    st.rerun()
