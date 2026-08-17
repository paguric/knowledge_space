"""Test per le strategie LLM (Step 6-bis).

Copia dalla specifica ``docs/91a-roadmap-fase1-ingestione.md`` § Step 6-bis
e ``docs/75-llm.md``:

- ``mock/echo`` restituisce l'ultimo messaggio utente (verifica interfaccia).
- ``mock/fixed`` restituisce "Risposta mock".
- ``llm_factory("mock/fixed")`` → restituisce strategy, ``generate()`` funziona.
- ``llm_factory("sconosciuto")`` → errore.
- ``llm_factory("openai/gpt-4o-mini")`` senza ``OPENAI_API_KEY`` → errore
  all'istanziazione.

Estensioni: registry, metadati discoverable, abbreviazioni, caching,
:class:`OpenAICompatibleLLM` (endpoint formato OpenAI: LM Studio,
OpenRouter, OpenAI, generico), fallback API key mancante,
``clear_llm_cache``.

Nessuna dipendenza HTTP: il client ``openai`` è mockato via
``monkeypatch.setattr(openai, "OpenAI", ...)``.
"""

from __future__ import annotations

from typing import List

import pytest

from knowledge_base.strategies import llm_registry
from knowledge_base.strategies.llm import (
    LLMConnectionError,
    MissingAPIKeyError,
    MockEchoLLM,
    MockFixedLLM,
    OpenAICompatibleLLM,
    ProviderNotImplementedError,
    UnknownLLMModelError,
    clear_llm_cache,
    llm_factory,
)


# --------------------------------------------------------------------------- #
# Fixture: cache pulita tra i test per evitare leak di istanze mock.
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_llm_cache()
    yield
    clear_llm_cache()


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #


class TestLLMRegistry:
    def test_all_models_registered(self):
        names = set(llm_registry.list_names())
        # 2 mock + 5 stub non-OpenAI + 1 (lm-studio/auto) = 8
        assert len(names) == 8

    @pytest.mark.parametrize(
        "model",
        [
            "mock/echo", "mock/fixed",
            "lm-studio/auto",
            "anthropic/claude-3.5-haiku", "anthropic/claude-3.5-sonnet",
            "anthropic/claude-4-opus",
            "google/gemini-2.0-flash",
            "cohere/command-r-plus",
        ],
    )
    def test_model_registered(self, model):
        assert llm_registry.contains(model)

    def test_get_metadata_unknown_raises(self):
        with pytest.raises(KeyError, match="non registrato"):
            llm_registry.get_metadata("does/not-exist")

    def test_get_factory_unknown_raises(self):
        with pytest.raises(KeyError, match="non registrato"):
            llm_registry.get_factory("does/not-exist")

    def test_mock_models_have_factory(self):
        assert llm_registry.get_factory("mock/echo") is not None
        assert llm_registry.get_factory("mock/fixed") is not None

    def test_openai_compatible_models_have_factory(self):
        """I modelli OpenAI-compatibili registrati hanno una factory concreta."""
        for name in ["lm-studio/auto"]:
            assert llm_registry.get_factory(name) is not None

    def test_non_openai_models_no_factory(self):
        """Provider non OpenAI-compatibili restano stub (factory=None)."""
        for name in [
            "anthropic/claude-3.5-haiku",
            "google/gemini-2.0-flash", "cohere/command-r-plus",
        ]:
            assert llm_registry.get_factory(name) is None


# --------------------------------------------------------------------------- #
# Metadati discoverable
# --------------------------------------------------------------------------- #


class TestLLMMetadata:
    @pytest.mark.parametrize(
        "model,provider,ctx,requires_api,streaming,json_",
        [
            ("mock/echo",               "mock",     4096,    False, True,  True),
            ("mock/fixed",              "mock",     4096,    False, True,  True),
            ("lm-studio/auto",          "lm-studio", 32768,  False, True,  True),
            ("anthropic/claude-3.5-haiku",  "anthropic", 200000, True, True, True),
            ("anthropic/claude-3.5-sonnet", "anthropic", 200000, True, True, True),
            ("anthropic/claude-4-opus",     "anthropic", 200000, True, True, True),
            ("google/gemini-2.0-flash",     "google",   1000000, True, True, True),
            ("cohere/command-r-plus",       "cohere",   128000,  True, True, True),
        ],
    )
    def test_metadata_complete(
        self, model, provider, ctx, requires_api, streaming, json_
    ):
        md = llm_registry.get_metadata(model)
        assert md.model_name == model
        assert md.provider == provider
        assert md.context_window == ctx
        assert md.requires_api is requires_api
        assert md.supports_streaming is streaming
        assert md.supports_json is json_

    def test_remote_providers_require_api(self):
        for name in llm_registry.list_names():
            md = llm_registry.get_metadata(name)
            if md.provider in ("openai-compatible", "anthropic", "google", "cohere"):
                assert md.requires_api is True

    def test_local_providers_do_not_require_api(self):
        for name in llm_registry.list_names():
            md = llm_registry.get_metadata(name)
            if md.provider in ("lm-studio", "mock"):
                assert md.requires_api is False


# --------------------------------------------------------------------------- #
# MockEchoLLM — restituisce l'ultimo messaggio utente
# --------------------------------------------------------------------------- #


class TestMockEchoLLM:
    def test_generate_returns_last_user_message(self):
        llm = MockEchoLLM()
        messages = [
            {"role": "system", "content": "Sei un assistente."},
            {"role": "user", "content": "Qual è la capitale della Francia?"},
        ]
        out = llm.generate(messages)
        assert out == "Qual è la capitale della Francia?"

    def test_generate_picks_last_user_when_multiple(self):
        llm = MockEchoLLM()
        messages = [
            {"role": "user", "content": "prima domanda"},
            {"role": "assistant", "content": "risposta"},
            {"role": "user", "content": "seconda domanda"},
        ]
        assert llm.generate(messages) == "seconda domanda"

    def test_generate_empty_when_no_user_message(self):
        llm = MockEchoLLM()
        assert llm.generate([{"role": "system", "content": "solo sistema"}]) == ""

    def test_generate_empty_when_messages_empty(self):
        llm = MockEchoLLM()
        assert llm.generate([]) == ""

    def test_stream_yields_tokens_split_on_spaces(self):
        llm = MockEchoLLM()
        messages = [{"role": "user", "content": "ciao mondo test"}]
        tokens = list(llm.stream(messages))
        assert tokens == ["ciao ", "mondo ", "test "]

    def test_stream_empty_input_yields_empty_token(self):
        """L'iteratore deve emettere almeno un token (contratto)."""
        llm = MockEchoLLM()
        tokens = list(llm.stream([{"role": "user", "content": ""}]))
        assert tokens == [""]

    def test_metadata_default_when_not_passed(self):
        llm = MockEchoLLM()
        assert llm.name == "mock/echo"
        assert llm.metadata.provider == "mock"
        assert llm.metadata.context_window == 4096
        assert llm.metadata.supports_streaming is True
        assert llm.metadata.supports_json is True

    def test_generate_passes_through_params_ignored(self):
        """I parametri opzionali (max_tokens, temperature) sono accettati
        ma non hanno effetto sul mock: l'interfaccia è rispettata."""
        llm = MockEchoLLM()
        messages = [{"role": "user", "content": "domanda"}]
        out = llm.generate(messages, max_tokens=256, temperature=0.7)
        assert out == "domanda"


# --------------------------------------------------------------------------- #
# MockFixedLLM — restituisce "Risposta mock"
# --------------------------------------------------------------------------- #


class TestMockFixedLLM:
    def test_generate_returns_fixed_string(self):
        llm = MockFixedLLM()
        messages = [
            {"role": "system", "content": "qualunque cosa"},
            {"role": "user", "content": "qualunque domanda"},
        ]
        assert llm.generate(messages) == "Risposta mock"

    def test_generate_ignores_messages_content(self):
        llm = MockFixedLLM()
        assert llm.generate([]) == "Risposta mock"
        assert llm.generate([{"role": "user", "content": "xyz"}]) == "Risposta mock"

    def test_stream_yields_single_token(self):
        llm = MockFixedLLM()
        tokens = list(llm.stream([{"role": "user", "content": "x"}]))
        assert tokens == ["Risposta mock"]

    def test_metadata_default(self):
        llm = MockFixedLLM()
        assert llm.name == "mock/fixed"
        assert llm.metadata.provider == "mock"
        assert llm.metadata.supports_json is True


# --------------------------------------------------------------------------- #
# llm_factory — casi della specifica
# --------------------------------------------------------------------------- #


class TestLLMFactory:
    def test_factory_returns_mock_fixed_strategy(self):
        """Spec: ``llm_factory("mock/fixed")`` → restituisce strategy,
        ``generate()`` funziona."""
        strat = llm_factory("mock/fixed")
        assert strat.name == "mock/fixed"
        out = strat.generate([{"role": "user", "content": "ciao"}])
        assert out == "Risposta mock"

    def test_factory_returns_mock_echo_strategy(self):
        strat = llm_factory("mock/echo")
        assert strat.name == "mock/echo"
        out = strat.generate([{"role": "user", "content": "echo this"}])
        assert out == "echo this"

    def test_factory_unknown_model_raises(self):
        """Spec: ``llm_factory("sconosciuto")`` → errore."""
        with pytest.raises(UnknownLLMModelError, match="sconosciuto"):
            llm_factory("sconosciuto")

    def test_factory_openai_compatible_without_api_key_raises_missing_key(
        self, monkeypatch
    ):
        """Spec: ``llm_factory("openai-compatible/gpt-4o-mini")`` senza
        ``OPENAI_COMPATIBLE_API_KEY`` → errore all'istanziazione."""
        monkeypatch.delenv("OPENAI_COMPATIBLE_API_KEY", raising=False)
        with pytest.raises(MissingAPIKeyError, match="OpenAI-compatibile") as exc:
            llm_factory("openai-compatible/gpt-4o-mini")
        assert exc.value.env_var == "OPENAI_COMPATIBLE_API_KEY"

    @pytest.mark.parametrize(
        "model, env_var, display",
        [
            ("anthropic/claude-3.5-haiku", "ANTHROPIC_API_KEY", "Anthropic"),
            ("google/gemini-2.0-flash",    "GEMINI_API_KEY",    "Google"),
            ("cohere/command-r-plus",       "COHERE_API_KEY",    "Cohere"),
        ],
    )
    def test_factory_remote_providers_without_api_key(
        self, model, env_var, display, monkeypatch
    ):
        monkeypatch.delenv(env_var, raising=False)
        with pytest.raises(MissingAPIKeyError, match=display) as exc:
            llm_factory(model)
        assert exc.value.env_var == env_var

    def test_factory_openai_compatible_with_api_key_istanzia(self, monkeypatch):
        """Con la API key presente, ``openai-compatible/gpt-4o-mini``
        istanzia un :class:`OpenAICompatibleLLM` (nessuna rete all'init)."""
        monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "test-key")
        monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", "https://api.openai.com/v1")
        strat = llm_factory("openai-compatible/gpt-4o-mini")
        assert isinstance(strat, OpenAICompatibleLLM)
        assert strat.name == "openai-compatible/gpt-4o-mini"
        assert strat._base_url == "https://api.openai.com/v1"

    def test_factory_lm_studio_auto_istanzia(self):
        """``lm-studio/auto`` istanzia senza chiave né rete."""
        strat = llm_factory("lm-studio/auto")
        assert isinstance(strat, OpenAICompatibleLLM)
        assert strat.name == "lm-studio/auto"

    def test_factory_lm_studio_model_dinamico(self):
        """Prefisso dinamico: ``lm-studio/<modello>`` non registrato viene
        costruito al volo."""
        strat = llm_factory("lm-studio/Qwen2.5-7B-Instruct")
        assert isinstance(strat, OpenAICompatibleLLM)
        assert strat.name == "lm-studio/Qwen2.5-7B-Instruct"
        assert strat.metadata.provider == "lm-studio"

    def test_factory_openai_compatible_senza_env_raises(self, monkeypatch):
        """Prefisso generico senza chiave → MissingAPIKeyError."""
        monkeypatch.delenv("OPENAI_COMPATIBLE_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_COMPATIBLE_BASE_URL", raising=False)
        with pytest.raises(MissingAPIKeyError, match="OpenAI-compatibile") as exc:
            llm_factory("openai-compatible/gpt-4o-mini")
        assert exc.value.env_var == "OPENAI_COMPATIBLE_API_KEY"

    def test_factory_openai_compatible_con_env_istanzia(self, monkeypatch):
        monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "ck")
        monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", "https://openrouter.ai/api/v1")
        strat = llm_factory("openai-compatible/deepseek/deepseek-chat")
        assert isinstance(strat, OpenAICompatibleLLM)
        assert strat._base_url == "https://openrouter.ai/api/v1"
        assert strat.name == "openai-compatible/deepseek/deepseek-chat"
        assert strat.metadata.provider == "openai-compatible"

    def test_factory_lm_studio_auto_istanzia(self):
        """``lm-studio/auto`` istanzia senza chiave né rete."""
        strat = llm_factory("lm-studio/auto")
        assert isinstance(strat, OpenAICompatibleLLM)
        assert strat.name == "lm-studio/auto"

    def test_factory_lm_studio_model_dinamico(self):
        """Prefisso dinamico: ``lm-studio/<modello>`` non registrato viene
        costruito al volo."""
        strat = llm_factory("lm-studio/Qwen2.5-7B-Instruct")
        assert isinstance(strat, OpenAICompatibleLLM)
        assert strat.name == "lm-studio/Qwen2.5-7B-Instruct"
        assert strat.metadata.provider == "lm-studio"

    def test_factory_prefissi_non_previsti_raises(self):
        """Prefissi non supportati (es. openrouter/) → UnknownLLMModelError."""
        with pytest.raises(UnknownLLMModelError):
            llm_factory("openrouter/deepseek/deepseek-chat")
        with pytest.raises(UnknownLLMModelError):
            llm_factory("openai/gpt-4o-mini")

    def test_factory_non_openai_provider_raises_not_implemented(self, monkeypatch):
        """Provider non OpenAI-compatibili: con chiave presente sollevano
        ``ProviderNotImplementedError``."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        with pytest.raises(ProviderNotImplementedError, match="anthropic"):
            llm_factory("anthropic/claude-3.5-haiku")


# --------------------------------------------------------------------------- #
# llm_factory — abbreviazioni
# --------------------------------------------------------------------------- #


class TestLLMFactoryAbbreviations:
    @pytest.mark.parametrize(
        "abbrev, resolved",
        [
            ("fast", "openai-compatible/gpt-4o-mini"),
            ("cheap", "openai-compatible/gpt-4o-mini"),
            ("quality", "openai-compatible/gpt-4o"),
            ("local", "lm-studio/auto"),
        ],
    )
    def test_abbreviation_resolves_to_provider(self, abbrev, resolved, monkeypatch):
        """Le abbreviazioni risolvono al modello reale."""
        if resolved.startswith("openai-compatible/"):
            # Per remote: assicuriamoci che l'API key sia assente → MissingAPIKeyError
            monkeypatch.delenv("OPENAI_COMPATIBLE_API_KEY", raising=False)
            with pytest.raises(MissingAPIKeyError):
                llm_factory(abbrev)
        else:
            # local → lm-studio/auto: istanzia senza rete
            strat = llm_factory(abbrev)
            assert isinstance(strat, OpenAICompatibleLLM)
            assert strat.name == "lm-studio/auto"


# --------------------------------------------------------------------------- #
# llm_factory — caching
# --------------------------------------------------------------------------- #


class TestLLMFactoryCaching:
    def test_factory_caches_mock_instance(self):
        """Spec 75-llm.md: caching, stessa strategy per stesso model_name."""
        first = llm_factory("mock/fixed")
        second = llm_factory("mock/fixed")
        assert first is second

    def test_factory_caches_echo_instance(self):
        first = llm_factory("mock/echo")
        second = llm_factory("mock/echo")
        assert first is second

    def test_factory_distinct_models_distinct_instances(self):
        echo = llm_factory("mock/echo")
        fixed = llm_factory("mock/fixed")
        assert echo is not fixed
        assert echo.name == "mock/echo"
        assert fixed.name == "mock/fixed"

    def test_clear_cache_invalidates(self):
        first = llm_factory("mock/fixed")
        clear_llm_cache()
        second = llm_factory("mock/fixed")
        assert first is not second

    def test_failure_does_not_cache(self, monkeypatch):
        """Se la factory solleva un errore, l'istanza non viene cached:
        una seconda chiamata deve ridare l'errore (non un finto hit)."""
        monkeypatch.delenv("OPENAI_COMPATIBLE_API_KEY", raising=False)
        with pytest.raises(MissingAPIKeyError):
            llm_factory("openai-compatible/gpt-4o-mini")
        with pytest.raises(MissingAPIKeyError):
            llm_factory("openai-compatible/gpt-4o-mini")


# --------------------------------------------------------------------------- #
# OpenAICompatibleLLM — endpoint formato OpenAI (LM Studio, OpenRouter, ...)
# --------------------------------------------------------------------------- #


class _FakeOpenAIClient:
    """Client finto che registra gli argomenti e restituisce risposte
    deterministiche: nessuna rete nei test."""

    def __init__(
        self, response: str = "Risposta di test", model_names=None, error=None
    ):
        self.response = response
        self.model_names = ["modello-locale"] if model_names is None else model_names
        self.error = error
        self.last_kwargs = None
        self.base_url = None
        self.api_key = None
        self.chat = _FakeChat(self)
        self.models = _FakeModels(self)


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeDelta:
    def __init__(self, content):
        self.content = content


class _FakeStreamChoice:
    def __init__(self, content):
        self.delta = _FakeDelta(content)


class _FakeStreamChunk:
    def __init__(self, content):
        self.choices = [_FakeStreamChoice(content)] if content is not None else []


class _FakeModel:
    def __init__(self, mid):
        self.id = mid


class _FakeModelsList:
    def __init__(self, names):
        self.data = [_FakeModel(n) for n in names]


class _FakeCompletions:
    def __init__(self, client):
        self._client = client

    def create(self, **kwargs):
        self._client.last_kwargs = kwargs
        if self._client.error:
            raise RuntimeError(self._client.error)
        if kwargs.get("stream"):
            parts = self._client.response.split(" ")
            return iter([_FakeStreamChunk(p + " ") for p in parts if p])
        return _FakeResponse(self._client.response)


class _FakeChat:
    def __init__(self, client):
        self.completions = _FakeCompletions(client)


class _FakeModels:
    def __init__(self, client):
        self._client = client

    def list(self):
        return _FakeModelsList(self._client.model_names)


def _patch_openai(monkeypatch, client):
    """Sostituisce ``openai.OpenAI`` con una factory che restituisce il
    client finto (registrando base_url/api_key)."""
    import openai

    def _factory(base_url=None, api_key=None, timeout=None):
        client.base_url = base_url
        client.api_key = api_key
        return client

    monkeypatch.setattr(openai, "OpenAI", _factory)
    return client


class TestOpenAICompatibleLLM:
    def _make(self, **kwargs):
        from knowledge_base.strategies import LLMMetadata

        md = LLMMetadata(
            model_name="lm-studio/auto",
            provider="lm-studio",
            context_window=32768,
            requires_api=False,
            supports_streaming=True,
            supports_json=True,
        )
        params = {
            "base_url": "http://localhost:1234/v1",
            "api_key": "lm-studio",
        }
        params.update(kwargs)
        return OpenAICompatibleLLM(metadata=md, **params)

    def test_generate_chiama_endpoint_e_ritorna_testo(self, monkeypatch):
        client = _patch_openai(monkeypatch, _FakeOpenAIClient("Ciao!"))
        llm = self._make(model_name="qwen2.5")
        out = llm.generate(
            [{"role": "user", "content": "saluta"}], max_tokens=50, temperature=0.3
        )
        assert out == "Ciao!"
        assert client.last_kwargs["model"] == "qwen2.5"
        assert client.last_kwargs["max_tokens"] == 50
        assert client.last_kwargs["temperature"] == 0.3
        assert client.base_url == "http://localhost:1234/v1"
        assert client.api_key == "lm-studio"

    def test_generate_openrouter_disabilita_reasoning(self, monkeypatch):
        """Per endpoint OpenRouter il payload include
        reasoning.enabled=false via extra_body (il router free instrada
        verso modelli reasoning che altrimenti consumano i token nel
        reasoning e restituiscono content vuoto)."""
        client = _patch_openai(monkeypatch, _FakeOpenAIClient("JSON"))
        llm = self._make(
            model_name="m", base_url="https://openrouter.ai/api/v1"
        )
        out = llm.generate([{"role": "user", "content": "x"}])
        assert out == "JSON"
        assert client.last_kwargs.get("extra_body") == {
            "reasoning": {"enabled": False}
        }

    def test_generate_senza_openrouter_niente_extra_body(self, monkeypatch):
        """Endpoint non OpenRouter: nessun campo extra nel payload."""
        client = _patch_openai(monkeypatch, _FakeOpenAIClient("OK"))
        llm = self._make(model_name="m")
        llm.generate([{"role": "user", "content": "x"}])
        assert client.last_kwargs.get("extra_body") is None

    def test_generate_auto_detect_usa_primo_modello(self, monkeypatch):
        client = _patch_openai(
            monkeypatch, _FakeOpenAIClient("ok", model_names=["qwen2.5-7b"])
        )
        llm = self._make()  # model_name None → auto
        out = llm.generate([{"role": "user", "content": "x"}])
        assert out == "ok"
        assert client.last_kwargs["model"] == "qwen2.5-7b"

    def test_auto_detect_nessun_modello_raises(self, monkeypatch):
        _patch_openai(monkeypatch, _FakeOpenAIClient(model_names=[]))
        llm = self._make()
        with pytest.raises(LLMConnectionError, match="nessun modello"):
            llm.generate([{"role": "user", "content": "x"}])

    def test_errore_chiamata_diventa_llm_connection_error(self, monkeypatch):
        _patch_openai(monkeypatch, _FakeOpenAIClient(error="boom"))
        llm = self._make(model_name="m")
        with pytest.raises(LLMConnectionError, match="Chiamata LLM fallita"):
            llm.generate([{"role": "user", "content": "x"}])

    def test_stream_yields_tokens(self, monkeypatch):
        _patch_openai(monkeypatch, _FakeOpenAIClient("ciao mondo"))
        llm = self._make(model_name="m")
        tokens = list(llm.stream([{"role": "user", "content": "x"}]))
        assert tokens == ["ciao ", "mondo "]
        assert llm._client.last_kwargs["stream"] is True

    def test_metadata_di_istanza_factory_lm_studio(self):
        strat = llm_factory("lm-studio/auto")
        assert strat.metadata.provider == "lm-studio"
        assert strat.metadata.requires_api is False
        assert strat._base_url == "http://localhost:1234/v1"


# --------------------------------------------------------------------------- #
# Coerenza interfaccia (Protocol)
# --------------------------------------------------------------------------- #


class TestLLMStrategyProtocol:
    def test_mock_implements_protocol(self):
        """Le istanze mock soddisfano l'interfaccia ``LLMStrategy``:
        ``name``, ``metadata``, ``generate()``, ``stream()``."""
        for strat in [MockEchoLLM(), MockFixedLLM()]:
            assert hasattr(strat, "name")
            assert hasattr(strat, "metadata")
            assert callable(getattr(strat, "generate"))
            assert callable(getattr(strat, "stream"))
            # generate ritorna str, stream ritorna iterabile
            out = strat.generate([{"role": "user", "content": "x"}])
            assert isinstance(out, str)
            tokens = strat.stream([{"role": "user", "content": "x"}])
            assert iter(tokens) is iter(tokens)  # iterabile
            assert isinstance(next(tokens), str)

    def test_factory_returns_satisfy_protocol(self):
        for name in ["mock/echo", "mock/fixed"]:
            strat = llm_factory(name)
            assert isinstance(strat.metadata.model_name, str)
            assert isinstance(strat.metadata.provider, str)
            assert isinstance(strat.metadata.context_window, int)
            assert isinstance(strat.metadata.requires_api, bool)