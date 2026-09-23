"""
Testes do roteamento de provider do chat de IA
(``src/config/chat_ia_provider.py``).

As constantes do módulo são lidas **no import** (``st.secrets`` -> ``.env``),
então cada teste sobrescreve as que precisa via ``monkeypatch.setattr`` no
namespace do módulo — nunca dependendo do ``.env`` da máquina que roda a
suíte.
"""
import pytest

import src.config.chat_ia_provider as provider_mod
from src.config.chat_ia_provider import (
    PROVIDERS_COM_CATALOGO,
    _normalizar_provider,
    _proximo_provider,
    providers_para_tentativa,
)


@pytest.mark.unit
class TestNormalizarProvider:
    def test_aceita_os_tres_providers_suportados(self):
        assert _normalizar_provider("openrouter") == "openrouter"
        assert _normalizar_provider("anthropic") == "anthropic"
        assert _normalizar_provider("openai") == "openai"

    def test_valor_invalido_cai_no_fallback_em_vez_de_propagar(self):
        assert _normalizar_provider("gemini") == "openrouter"
        assert _normalizar_provider("") == "openrouter"
        assert _normalizar_provider("openai ") == "openai"


@pytest.mark.unit
class TestProximoProvider:
    def test_nunca_devolve_o_proprio_primario(self):
        for primario in ("openrouter", "anthropic", "openai"):
            assert _proximo_provider(primario) != primario

    def test_segue_a_ordem_de_preferencia_declarada(self):
        # _ORDEM_FALLBACK = (openrouter, anthropic, openai)
        assert _proximo_provider("openrouter") == "anthropic"
        assert _proximo_provider("anthropic") == "openrouter"
        assert _proximo_provider("openai") == "openrouter"


@pytest.mark.unit
class TestProvidersParaTentativa:
    def _configurar(self, monkeypatch, *, modo, fallback, por_perfil=None):
        monkeypatch.setattr(provider_mod, "CHAT_IA_FALLBACK_MODE", modo)
        monkeypatch.setattr(
            provider_mod, "CHAT_IA_FALLBACK_PROVIDER", fallback
        )
        monkeypatch.setattr(
            provider_mod, "CHAT_IA_PROVIDER_DEFAULT", "openrouter"
        )
        monkeypatch.setattr(
            provider_mod, "CHAT_IA_PROVIDER_POR_PERFIL", por_perfil or {}
        )

    def test_friendly_error_nao_tenta_segundo_provider(self, monkeypatch):
        self._configurar(
            monkeypatch, modo="friendly_error", fallback="anthropic"
        )
        assert providers_para_tentativa("admin") == ["openrouter"]

    def test_retry_same_provider_repete_o_mesmo(self, monkeypatch):
        self._configurar(
            monkeypatch,
            modo="retry_same_provider_once",
            fallback="anthropic",
        )
        assert providers_para_tentativa("admin") == [
            "openrouter",
            "openrouter",
        ]

    def test_switch_provider_usa_o_fallback_configurado(self, monkeypatch):
        self._configurar(
            monkeypatch, modo="switch_provider_once", fallback="anthropic"
        )
        assert providers_para_tentativa("admin") == [
            "openrouter",
            "anthropic",
        ]

    def test_fallback_igual_ao_primario_nao_vira_tentativa_repetida(
        self, monkeypatch,
    ):
        """Com fallback == primário, ``switch_provider_once`` precisa
        trocar de provider de verdade — senão a estratégia vira um
        ``retry_same_provider_once`` disfarçado, e uma chave ausente
        falharia duas vezes pelo mesmo motivo."""
        for primario in ("openrouter", "anthropic", "openai"):
            self._configurar(
                monkeypatch,
                modo="switch_provider_once",
                fallback=primario,
                por_perfil={"admin": primario},
            )
            cadeia = providers_para_tentativa("admin")
            assert cadeia[0] == primario
            assert cadeia[1] != primario

    def test_perfil_sem_mapeamento_cai_no_default(self, monkeypatch):
        self._configurar(
            monkeypatch,
            modo="friendly_error",
            fallback="anthropic",
            por_perfil={"admin": "anthropic"},
        )
        assert providers_para_tentativa("consultor") == ["openrouter"]
        assert providers_para_tentativa(None) == ["openrouter"]


@pytest.mark.unit
class TestProvidersComCatalogo:
    def test_so_a_openrouter_aceita_escolha_de_modelo_em_runtime(self):
        """Providers diretos usam modelo fixo da configuração: um id de
        gateway (``qwen/...``) não existe na API deles."""
        assert PROVIDERS_COM_CATALOGO == frozenset({"openrouter"})
