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
provider locali stub, fallback API key mancante per altri provider remoti,
``clear_llm_cache``.

Nessuna dipendenza HTTP: in Fase 1A (F0) i provider remoti/locali sono
solo stub (registry + metadati), non istanziabili.
"""

from __future__ import annotations

from typing import List

import pytest

from knowledge_base.strategies import llm_registry
from knowledge_base.strategies.llm import (
    MissingAPIKeyError,
    MockEchoLLM,
    MockFixedLLM,
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
        # 2 mock + 9 remoti + 4 locali = 15
        assert len(names) == 15

    @pytest.mark.parametrize(
        "model",
        [
            "mock/echo", "mock/fixed",
            "openai/gpt-4o", "openai/gpt-4o-mini", "openai/gpt-4.1",
            "openai/o3-mini",
            "anthropic/claude-3.5-haiku", "anthropic/claude-3.5-sonnet",
            "anthropic/claude-4-opus",
            "google/gemini-2.0-flash",
            "cohere/command-r-plus",
            "ollama/llama3.1", "ollama/mistral-nemo",
            "llamacpp/llama-7b", "vllm/mistral-nemo",
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

    def test_remote_models_no_factory_in_fase_1a(self):
        """In Fase 1A i provider remoti sono stub (factory=None)."""
        for name in [
            "openai/gpt-4o", "anthropic/claude-3.5-haiku",
            "google/gemini-2.0-flash", "cohere/command-r-plus",
        ]:
            assert llm_registry.get_factory(name) is None

    def test_local_models_no_factory_in_fase_1a(self):
        """In Fase 1A i provider locali sono stub (factory=None)."""
        for name in ["ollama/llama3.1", "llamacpp/llama-7b", "vllm/mistral-nemo"]:
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
            ("openai/gpt-4o",           "openai",   128000,  True,  True,  True),
            ("openai/gpt-4o-mini",      "openai",   128000,  True,  True,  True),
            ("openai/gpt-4.1",          "openai",   1000000, True,  True,  True),
            ("openai/o3-mini",          "openai",   200000,  True,  True,  True),
            ("anthropic/claude-3.5-haiku",  "anthropic", 200000, True, True, True),
            ("anthropic/claude-3.5-sonnet", "anthropic", 200000, True, True, True),
            ("anthropic/claude-4-opus",     "anthropic", 200000, True, True, True),
            ("google/gemini-2.0-flash",     "google",   1000000, True, True, True),
            ("cohere/command-r-plus",       "cohere",   128000,  True, True, True),
            ("ollama/llama3.1",         "ollama",   8192,    False, True,  False),
            ("ollama/mistral-nemo",     "ollama",   32768,   False, True,  True),
            ("llamacpp/llama-7b",       "llamacpp", 4096,    False, True,  False),
            ("vllm/mistral-nemo",       "vllm",     32768,   False, True,  True),
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
            if md.provider in ("openai", "anthropic", "google", "cohere"):
                assert md.requires_api is True

    def test_local_providers_do_not_require_api(self):
        for name in llm_registry.list_names():
            md = llm_registry.get_metadata(name)
            if md.provider in ("ollama", "llamacpp", "vllm", "mock"):
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

    def test_factory_openai_without_api_key_raises_missing_key(self, monkeypatch):
        """Spec: ``llm_factory("openai/gpt-4o-mini")`` senza
        ``OPENAI_API_KEY`` → errore all'istanziazione."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(MissingAPIKeyError, match="OpenAI") as exc:
            llm_factory("openai/gpt-4o-mini")
        assert exc.value.provider == "OpenAI"
        assert exc.value.env_var == "OPENAI_API_KEY"

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

    def test_factory_openai_with_api_key_raises_not_implemented(self, monkeypatch):
        """In Fase 1A anche con la API key presente il provider è stub:
        la factory solleva ``ProviderNotImplementedError``."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        with pytest.raises(ProviderNotImplementedError, match="openai"):
            llm_factory("openai/gpt-4o-mini")

    def test_factory_local_provider_raises_not_implemented_without_key_check(self):
        """Provider locali non richiedono API key: la factory solleva
        direttamente ``ProviderNotImplementedError``."""
        with pytest.raises(ProviderNotImplementedError, match="ollama"):
            llm_factory("ollama/llama3.1")
        with pytest.raises(ProviderNotImplementedError, match="llamacpp"):
            llm_factory("llamacpp/llama-7b")
        with pytest.raises(ProviderNotImplementedError, match="vllm"):
            llm_factory("vllm/mistral-nemo")


# --------------------------------------------------------------------------- #
# llm_factory — abbreviazioni
# --------------------------------------------------------------------------- #


class TestLLMFactoryAbbreviations:
    @pytest.mark.parametrize(
        "abbrev, resolved",
        [
            ("fast", "openai/gpt-4o-mini"),
            ("cheap", "openai/gpt-4o-mini"),
            ("quality", "openai/gpt-4o"),
            ("local", "ollama/llama3.1"),
        ],
    )
    def test_abbreviation_resolves_to_provider(self, abbrev, resolved, monkeypatch):
        """Le abbreviazioni risolvono al modello reale; in Fase 1A
        sollevano l'errore atteso del provider (non UnknownLLMModelError)."""
        # Per remote: assicuriamoci che l'API key sia assente → MissingAPIKeyError
        if resolved.startswith("openai/"):
            monkeypatch.delenv("OPENAI_API_KEY", raising=False)
            with pytest.raises(MissingAPIKeyError):
                llm_factory(abbrev)
        else:
            # local
            with pytest.raises(ProviderNotImplementedError):
                llm_factory(abbrev)


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
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(MissingAPIKeyError):
            llm_factory("openai/gpt-4o-mini")
        with pytest.raises(MissingAPIKeyError):
            llm_factory("openai/gpt-4o-mini")


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