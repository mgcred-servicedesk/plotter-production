"""
Testes do laço de tool-use manual (``src/dashboard/chat_ia/agent.py``).

Nunca chamamos a API real da Anthropic: ``get_anthropic_client`` (e,
quando necessário, ``construir_dispatch``) são substituídos via
monkeypatch no namespace de ``chat_ia.agent`` — mesma técnica de
``tests/test_chat_ia_tools.py``. As respostas fake usam
``types.SimpleNamespace`` para simular os content blocks do SDK
(``.type`` + ``.text``/``.name``/``.input``/``.id``), já que o código
só lê esses atributos, nunca métodos do SDK real.
"""
import json
import types
from unittest.mock import Mock

import pandas as pd
import pytest

import src.dashboard.chat_ia.agent as agent_mod
from src.dashboard.chat_ia.agent import MAX_TURNOS, responder
from src.dashboard.chat_ia.tools import ChatContext


def _contexto_dummy() -> ChatContext:
    """Contexto mínimo — irrelevante nos testes que mockam
    ``construir_dispatch`` por completo."""
    return ChatContext(
        df=pd.DataFrame(),
        df_metas=pd.DataFrame(),
        df_sup=pd.DataFrame(),
        df_analise=pd.DataFrame(),
        df_cancelados=pd.DataFrame(),
        kpis={},
        kpis_qtd={},
        kpis_analise={},
        kpis_cancel={},
        medias={},
        mes=3,
        ano=2026,
        dia_atual=15,
        du_decorridos=10,
        role="gerente",
    )


def _bloco_texto(texto: str):
    return types.SimpleNamespace(type="text", text=texto)


def _bloco_tool_use(nome: str, entrada: dict, id_: str):
    return types.SimpleNamespace(
        type="tool_use", name=nome, input=entrada, id=id_,
    )


def _resposta(stop_reason: str, content: list):
    return types.SimpleNamespace(stop_reason=stop_reason, content=content)


def _fake_client(*respostas):
    """Cliente fake cujo ``.messages.create`` devolve ``respostas`` em
    sequência (uma por chamada), via ``Mock(side_effect=...)``."""
    client = types.SimpleNamespace()
    client.messages = types.SimpleNamespace(
        create=Mock(side_effect=list(respostas)),
    )
    return client


def _forcar_cadeia_provider(monkeypatch, providers):
    monkeypatch.setattr(
        agent_mod,
        "providers_para_tentativa",
        lambda perfil: providers,
    )


@pytest.mark.unit
class TestResponderSequenciaToolUseEndTurn:
    def test_dispatch_chamado_com_input_correto_e_historico_completo(
        self, monkeypatch,
    ):
        _forcar_cadeia_provider(monkeypatch, ["anthropic"])

        tool_mock = Mock(return_value={"ok": True})
        monkeypatch.setattr(
            agent_mod, "construir_dispatch",
            lambda contexto: {"minha_tool": tool_mock},
        )

        resposta_tool_use = _resposta(
            "tool_use",
            [_bloco_tool_use("minha_tool", {"x": 1}, "toolu_abc")],
        )
        resposta_final = _resposta(
            "end_turn", [_bloco_texto("Resposta final.")]
        )
        client = _fake_client(resposta_tool_use, resposta_final)
        monkeypatch.setattr(agent_mod, "get_anthropic_client", lambda: client)

        texto, novo_historico = responder(
            "pergunta teste", _contexto_dummy(), [],
        )

        tool_mock.assert_called_once_with({"x": 1})
        assert texto == "Resposta final."
        assert client.messages.create.call_count == 2

        # Histórico completo: user, assistant(tool_use), user(tool_result),
        # assistant(final) — nunca termina em tool_use sem tool_result.
        assert len(novo_historico) == 4
        assert novo_historico[0] == {
            "role": "user",
            "content": "pergunta teste",
        }
        assert novo_historico[1]["role"] == "assistant"
        assert novo_historico[1]["content"] == [
            {
                "type": "tool_use",
                "id": "toolu_abc",
                "name": "minha_tool",
                "input": {"x": 1},
            }
        ]
        assert novo_historico[3]["role"] == "assistant"
        assert novo_historico[3]["content"] == [
            {"type": "text", "text": "Resposta final."}
        ]

        tool_results = novo_historico[2]["content"]
        assert novo_historico[2]["role"] == "user"
        assert len(tool_results) == 1
        assert tool_results[0]["type"] == "tool_result"
        assert tool_results[0]["tool_use_id"] == "toolu_abc"
        assert tool_results[0]["is_error"] is False
        assert json.loads(tool_results[0]["content"]) == {"ok": True}


@pytest.mark.unit
class TestResponderLimiteDeTurnos:
    def test_para_exatamente_em_max_turnos_com_historico_original(
        self, monkeypatch,
    ):
        _forcar_cadeia_provider(monkeypatch, ["anthropic"])

        tool_mock = Mock(return_value={"ok": True})
        monkeypatch.setattr(
            agent_mod, "construir_dispatch",
            lambda contexto: {"minha_tool": tool_mock},
        )

        # Toda resposta pede a mesma tool de novo — nunca fecha o turno.
        respostas = [
            _resposta(
                "tool_use",
                [_bloco_tool_use("minha_tool", {"n": i}, f"toolu_{i}")],
            )
            for i in range(MAX_TURNOS)
        ]
        client = _fake_client(*respostas)
        monkeypatch.setattr(agent_mod, "get_anthropic_client", lambda: client)

        historico_original = [
            {"role": "user", "content": "oi"},
            {"role": "assistant", "content": "olá!"},
        ]

        texto, novo_historico = responder(
            "pergunta sem fim", _contexto_dummy(), historico_original,
        )

        # Não trava nem itera além do limite.
        assert client.messages.create.call_count == MAX_TURNOS
        assert tool_mock.call_count == MAX_TURNOS
        assert "limite" in texto.lower()
        # Histórico ORIGINAL, não o parcial (que terminaria em tool_use
        # sem o assistant final correspondente).
        assert novo_historico is historico_original


@pytest.mark.unit
class TestResponderToolComExcecao:
    def test_tool_result_com_is_error_sem_vazar_stack_trace(
        self, monkeypatch,
    ):
        _forcar_cadeia_provider(monkeypatch, ["anthropic"])

        def _tool_com_falha(entrada):
            raise RuntimeError("stack trace secreta")

        monkeypatch.setattr(
            agent_mod, "construir_dispatch",
            lambda contexto: {"minha_tool": _tool_com_falha},
        )

        resposta_tool_use = _resposta(
            "tool_use", [_bloco_tool_use("minha_tool", {}, "toolu_x")],
        )
        resposta_final = _resposta(
            "end_turn", [_bloco_texto("Ok, tratei o erro.")],
        )
        client = _fake_client(resposta_tool_use, resposta_final)
        monkeypatch.setattr(agent_mod, "get_anthropic_client", lambda: client)

        texto, novo_historico = responder("pergunta", _contexto_dummy(), [])

        # Loop continua normalmente até o end_turn seguinte.
        assert texto == "Ok, tratei o erro."
        assert client.messages.create.call_count == 2

        tool_results = novo_historico[2]["content"]
        assert tool_results[0]["is_error"] is True
        conteudo = json.loads(tool_results[0]["content"])
        assert conteudo == {"erro": "falha interna ao executar a consulta"}
        assert "RuntimeError" not in tool_results[0]["content"]
        assert "stack trace secreta" not in tool_results[0]["content"]


@pytest.mark.unit
class TestResponderClienteIndisponivel:
    def test_value_error_devolve_mensagem_amigavel_sem_chamar_api(
        self, monkeypatch,
    ):
        _forcar_cadeia_provider(monkeypatch, ["anthropic"])

        def _sem_chave():
            raise ValueError("ANTHROPIC_API_KEY ausente")

        monkeypatch.setattr(agent_mod, "get_anthropic_client", _sem_chave)

        dispatch_mock = Mock()
        monkeypatch.setattr(agent_mod, "construir_dispatch", dispatch_mock)

        historico_original = [{"role": "user", "content": "oi"}]

        texto, novo_historico = responder(
            "pergunta", _contexto_dummy(), historico_original,
        )

        assert "ANTHROPIC_API_KEY" in texto
        assert novo_historico is historico_original
        dispatch_mock.assert_called_once()


@pytest.mark.unit
class TestResponderToolDesconhecida:
    def test_tool_use_name_fora_do_dispatch_nao_lanca(self, monkeypatch):
        _forcar_cadeia_provider(monkeypatch, ["anthropic"])

        monkeypatch.setattr(
            agent_mod, "construir_dispatch", lambda contexto: {},
        )

        resposta_tool_use = _resposta(
            "tool_use",
            [_bloco_tool_use("tool_desconhecida", {}, "toolu_y")],
        )
        resposta_final = _resposta(
            "end_turn", [_bloco_texto("Não encontrei essa ferramenta.")],
        )
        client = _fake_client(resposta_tool_use, resposta_final)
        monkeypatch.setattr(agent_mod, "get_anthropic_client", lambda: client)

        texto, novo_historico = responder("pergunta", _contexto_dummy(), [])

        assert texto == "Não encontrei essa ferramenta."
        assert client.messages.create.call_count == 2

        tool_results = novo_historico[2]["content"]
        assert tool_results[0]["is_error"] is True
        assert tool_results[0]["tool_use_id"] == "toolu_y"
        assert json.loads(tool_results[0]["content"]) == {
            "erro": "tool desconhecida: tool_desconhecida",
        }


@pytest.mark.unit
class TestResponderFallbackEntreProviders:
    def test_faz_fallback_para_provider_seguinte_quando_primeiro_indisponivel(
        self, monkeypatch,
    ):
        _forcar_cadeia_provider(monkeypatch, ["openai", "anthropic"])

        monkeypatch.setattr(
            agent_mod,
            "get_openai_client",
            Mock(side_effect=ValueError("OPENAI_API_KEY ausente")),
        )

        resposta_final = _resposta(
            "end_turn", [_bloco_texto("Resposta fallback.")]
        )
        client = _fake_client(resposta_final)
        monkeypatch.setattr(agent_mod, "get_anthropic_client", lambda: client)

        texto, novo_historico = responder("pergunta", _contexto_dummy(), [])

        assert texto == "Resposta fallback."
        assert client.messages.create.call_count == 1
        assert novo_historico[-1]["content"] == [
            {"type": "text", "text": "Resposta fallback."}
        ]
