"""
Loop agnostico de provider com tool-use manual para o chat de IA.

O modelo NUNCA calcula KPI sozinho: so pode chamar as tools definidas
em chat_ia/tools.py, que reusam funcoes ja validadas de kpis/*.py sobre
dados pos-RLS. Este modulo so orquestra a conversa (chamar a API,
despachar tool_use, devolver tool_result) — nenhuma logica de negocio
mora aqui.

Laco manual (sem runner beta de SDK): sao so 4 tools fixas, e o laco
manual da um ponto unico e explicito para logar/gatear cada tool_use
antes de executar.
"""
import json
import logging
from typing import Any, Callable

from src.config.anthropic_client import (
    ANTHROPIC_MODEL,
    get_anthropic_client,
)
from src.config.chat_ia_provider import providers_para_tentativa
from src.config.openai_client import OPENAI_MODEL, get_openai_client
from src.dashboard.chat_ia.tools import (
    TOOLS_SCHEMA,
    ChatContext,
    construir_dispatch,
)

logger = logging.getLogger(__name__)

MAX_TURNOS = 6
MAX_TOKENS = 2048

SYSTEM_PROMPT = (
    "Você é o assistente de dados do dashboard comercial da MGCred. "
    "Responda em português do Brasil, de forma objetiva, sempre com base "
    "no resultado das tools disponíveis — nunca invente números nem "
    "calcule você mesmo. Os dados já respeitam o perfil e o período "
    "selecionados pelo usuário no dashboard: não é preciso perguntar "
    "qual loja/consultor/período, a menos que a pergunta seja ambígua. "
    "Quando uma tool retornar 'variacao_pct' nulo ou status "
    "'nova'/'descontinuada', não invente um percentual — diga "
    "explicitamente que não há histórico de comparação para aquele caso. "
    "Se a pergunta pedir uma comparação de período que as tools não "
    "suportam (qualquer período além do mês anterior ou do mesmo mês do "
    "ano anterior), diga que essa comparação não está disponível em vez "
    "de aproximar. Quando o resultado indicar produção de supervisor "
    "embutida, mencione essa ressalva em vez de atribuí-la a um "
    "consultor."
)


OPENAI_TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"],
        },
    }
    for tool in TOOLS_SCHEMA
]


def _normalizar_conteudo(conteudo: Any) -> list[dict]:
    """Converte ``content`` heterogeneo em blocos ``dict`` canonicos."""
    if isinstance(conteudo, str):
        return [{"type": "text", "text": conteudo}]

    blocos: list[dict] = []
    for bloco in conteudo or []:
        if isinstance(bloco, dict):
            tipo = bloco.get("type")
            if tipo == "text":
                blocos.append(
                    {"type": "text", "text": bloco.get("text", "")}
                )
            elif tipo == "tool_use":
                blocos.append(
                    {
                        "type": "tool_use",
                        "id": bloco.get("id"),
                        "name": bloco.get("name"),
                        "input": bloco.get("input") or {},
                    }
                )
            elif tipo == "tool_result":
                blocos.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": bloco.get("tool_use_id"),
                        "content": bloco.get("content", ""),
                        "is_error": bool(bloco.get("is_error")),
                    }
                )
            continue

        tipo = getattr(bloco, "type", None)
        if tipo == "text":
            blocos.append({"type": "text", "text": getattr(bloco, "text", "")})
        elif tipo == "tool_use":
            blocos.append(
                {
                    "type": "tool_use",
                    "id": getattr(bloco, "id", None),
                    "name": getattr(bloco, "name", None),
                    "input": getattr(bloco, "input", None) or {},
                }
            )
    return blocos


def _mensagens_para_anthropic(mensagens: list[dict]) -> list[dict]:
    """Traduz o historico canonico para payload da Messages API."""
    payload: list[dict] = []
    for mensagem in mensagens:
        role = mensagem.get("role")
        conteudo = mensagem.get("content")

        if isinstance(conteudo, str):
            payload.append({"role": role, "content": conteudo})
            continue

        blocos_payload: list[dict] = []
        for bloco in _normalizar_conteudo(conteudo):
            tipo = bloco.get("type")
            if tipo == "text":
                blocos_payload.append(
                    {"type": "text", "text": bloco.get("text", "")}
                )
            elif tipo == "tool_use":
                blocos_payload.append(
                    {
                        "type": "tool_use",
                        "id": bloco.get("id"),
                        "name": bloco.get("name"),
                        "input": bloco.get("input") or {},
                    }
                )
            elif tipo == "tool_result":
                blocos_payload.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": bloco.get("tool_use_id"),
                        "content": bloco.get("content", ""),
                        "is_error": bool(bloco.get("is_error")),
                    }
                )

        payload.append({"role": role, "content": blocos_payload})
    return payload


def _mensagens_para_openai(mensagens: list[dict]) -> list[dict]:
    """Traduz o historico canonico para payload da Chat Completions API."""
    payload: list[dict] = []
    for mensagem in mensagens:
        role = mensagem.get("role")
        conteudo = mensagem.get("content")

        if isinstance(conteudo, str):
            payload.append({"role": role, "content": conteudo})
            continue

        blocos = _normalizar_conteudo(conteudo)

        if role == "assistant":
            textos = [
                b.get("text", "")
                for b in blocos
                if b.get("type") == "text"
            ]
            tool_calls = []
            for bloco in blocos:
                if bloco.get("type") != "tool_use":
                    continue
                tool_calls.append(
                    {
                        "id": bloco.get("id"),
                        "type": "function",
                        "function": {
                            "name": bloco.get("name"),
                            "arguments": json.dumps(
                                bloco.get("input") or {},
                                ensure_ascii=False,
                            ),
                        },
                    }
                )

            payload_assistant: dict[str, Any] = {
                "role": "assistant",
                "content": "\n".join(textos),
            }
            if tool_calls:
                payload_assistant["tool_calls"] = tool_calls
            payload.append(payload_assistant)
            continue

        tool_results = [b for b in blocos if b.get("type") == "tool_result"]
        if tool_results:
            for bloco in tool_results:
                payload.append(
                    {
                        "role": "tool",
                        "tool_call_id": bloco.get("tool_use_id"),
                        "content": bloco.get("content", ""),
                    }
                )
            continue

        textos_user = [
            b.get("text", "")
            for b in blocos
            if b.get("type") == "text"
        ]
        if textos_user:
            payload.append({"role": "user", "content": "\n".join(textos_user)})

    return payload


def _chamar_provider_anthropic(
    client: Any,
    model: str,
    mensagens: list[dict],
) -> tuple[list[dict], bool]:
    """Executa uma rodada no provider Anthropic."""
    resposta = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        tools=TOOLS_SCHEMA,
        messages=_mensagens_para_anthropic(mensagens),
    )

    blocos = _normalizar_conteudo(resposta.content)
    return blocos, resposta.stop_reason == "tool_use"


def _chamar_provider_openai(
    client: Any,
    model: str,
    mensagens: list[dict],
) -> tuple[list[dict], bool]:
    """Executa uma rodada no provider OpenAI.

    A Chat Completions API nao tem parametro `system` separado (ao
    contrario da Anthropic): o prompt de sistema entra como a primeira
    mensagem do array, com role "system".
    """
    payload = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *_mensagens_para_openai(mensagens),
    ]
    resposta = client.chat.completions.create(
        model=model,
        max_tokens=MAX_TOKENS,
        messages=payload,
        tools=OPENAI_TOOLS_SCHEMA,
    )

    mensagem = resposta.choices[0].message
    blocos: list[dict] = []

    if mensagem.content:
        blocos.append({"type": "text", "text": mensagem.content})

    for tool_call in mensagem.tool_calls or []:
        argumentos = tool_call.function.arguments or "{}"
        try:
            entrada = json.loads(argumentos)
        except Exception:
            entrada = {}
        blocos.append(
            {
                "type": "tool_use",
                "id": tool_call.id,
                "name": tool_call.function.name,
                "input": entrada,
            }
        )

    return blocos, bool(mensagem.tool_calls)


def _resolver_provider(
    provider: str,
) -> tuple[
    Callable[[], Any],
    str,
    Callable[[Any, str, list[dict]], tuple[list[dict], bool]],
]:
    """Resolve client getter, modelo e caller do provider."""
    if provider == "anthropic":
        return (
            get_anthropic_client,
            ANTHROPIC_MODEL,
            _chamar_provider_anthropic,
        )
    if provider == "openai":
        return get_openai_client, OPENAI_MODEL, _chamar_provider_openai
    raise ValueError(f"provider de chat IA nao suportado: {provider}")


def _mensagem_configuracao(provider: str, detalhe: str) -> str:
    """Mensagem amigavel para provider indisponivel/configuracao invalida."""
    if provider == "anthropic":
        return (
            "O chat de IA não está configurado (falta a chave da API). "
            "Peça a um administrador para configurar ANTHROPIC_API_KEY."
        )
    if provider == "openai":
        return (
            "O chat de IA não está configurado para OpenAI. "
            "Peça a um administrador para configurar OPENAI_API_KEY."
        )
    return (
        "O chat de IA não está configurado para o provider selecionado. "
        f"Detalhe técnico: {detalhe}"
    )


def _texto_final(blocos: list[dict]) -> str:
    partes = [
        bloco.get("text", "")
        for bloco in blocos
        if bloco.get("type") == "text"
    ]
    texto = "\n".join(partes).strip()
    return texto or "Não consegui gerar uma resposta para essa pergunta."


def _executar_tool_seguro(
    dispatch: dict, nome: str, entrada: dict, tool_use_id: str
) -> dict:
    """Executa uma tool sem nunca deixar exceção/stack trace vazar."""
    funcao = dispatch.get(nome)
    if funcao is None:
        logger.error(
            "Chat IA: tool desconhecida solicitada pelo modelo: %s",
            nome,
        )
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": json.dumps({"erro": f"tool desconhecida: {nome}"}),
            "is_error": True,
        }
    try:
        resultado = funcao(entrada)
    except Exception:
        logger.exception("Chat IA: falha ao executar tool %s", nome)
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": json.dumps(
                {"erro": "falha interna ao executar a consulta"}
            ),
            "is_error": True,
        }

    is_error = bool(isinstance(resultado, dict) and resultado.get("erro"))
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": json.dumps(resultado, ensure_ascii=False, default=str),
        "is_error": is_error,
    }


def _rodar_loop_provider(
    provider: str,
    pergunta: str,
    dispatch: dict,
    historico: list[dict],
) -> tuple[str, str, list[dict]]:
    """
    Executa o loop de tool-use para um provider.

    Returns:
        status: ``ok`` | ``unavailable`` | ``api_error`` | ``turn_limit``
        mensagem: resposta final amigavel
        historico_resultante: historico atualizado em ``ok``
    """
    try:
        get_client, model, chamar_provider = _resolver_provider(provider)
        client = get_client()
    except ValueError as exc:
        logger.warning(
            "Chat IA: provider indisponivel provider=%s detalhe=%s",
            provider,
            exc,
        )
        return (
            "unavailable",
            _mensagem_configuracao(provider, str(exc)),
            historico,
        )

    mensagens = [*historico, {"role": "user", "content": pergunta}]

    for _ in range(MAX_TURNOS):
        try:
            blocos_resposta, pediu_tool = chamar_provider(
                client,
                model,
                mensagens,
            )
        except Exception:
            logger.exception(
                "Chat IA: falha na chamada da API provider=%s",
                provider,
            )
            return (
                "api_error",
                "Não consegui falar com o assistente agora. Tente novamente "
                "em instantes.",
                historico,
            )

        mensagens = [
            *mensagens,
            {"role": "assistant", "content": blocos_resposta},
        ]

        if not pediu_tool:
            return "ok", _texto_final(blocos_resposta), mensagens

        blocos_tool = [
            bloco
            for bloco in blocos_resposta
            if bloco.get("type") == "tool_use"
        ]
        tool_results = [
            _executar_tool_seguro(
                dispatch,
                bloco.get("name"),
                bloco.get("input") or {},
                bloco.get("id"),
            )
            for bloco in blocos_tool
        ]
        mensagens = [*mensagens, {"role": "user", "content": tool_results}]

    logger.warning(
        "Chat IA: limite de %d turnos atingido provider=%s",
        MAX_TURNOS,
        provider,
    )
    return (
        "turn_limit",
        "Não consegui concluir a análise dentro do limite de passos. "
        "Tente reformular a pergunta de forma mais específica.",
        historico,
    )


def responder(
    pergunta: str, contexto: ChatContext, historico: list[dict]
) -> tuple[str, list[dict]]:
    """Responde ``pergunta`` usando o histórico e os dados de ``contexto``.

    Retorna ``(texto_da_resposta, novo_historico)``. Em qualquer erro
    (API indisponível, limite de turnos), devolve uma mensagem amigável
    e o histórico ORIGINAL — nunca grava uma conversa terminando em
    ``tool_use`` sem o ``tool_result`` correspondente.
    """
    dispatch = construir_dispatch(contexto)
    tentativas = providers_para_tentativa(contexto.role)

    ultimo_texto = (
        "Não consegui falar com o assistente agora. "
        "Tente novamente em instantes."
    )

    for idx, provider in enumerate(tentativas):
        status, texto, novo_historico = _rodar_loop_provider(
            provider=provider,
            pergunta=pergunta,
            dispatch=dispatch,
            historico=historico,
        )

        if status == "ok":
            return texto, novo_historico

        ultimo_texto = texto

        if status == "turn_limit":
            return texto, historico

        if idx < len(tentativas) - 1:
            logger.warning(
                "Chat IA: tentativa falhou provider=%s status=%s. "
                "Tentando fallback...",
                provider,
                status,
            )

    return ultimo_texto, historico
