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
import streamlit as st
import streamlit_antd_components as sac

from src.dashboard.chat_ia import agent
from src.dashboard.chat_ia.tools import ChatContext
from src.dashboard.rls import _obter_perfil_efetivo

# Estado desta aba (dono: este modulo).
CHAVE_HISTORICO = "chat_ia_historico"
CHAVE_ESCOPO = "chat_ia_chave"
CHAVE_AVISO = "chat_ia_aviso"


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
            pergunta, contexto, historico
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
