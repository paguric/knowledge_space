"""Strategie LLM: interfaccia comune per tutti i modelli linguistici.

Definisce :class:`LLMStrategy` (Protocol in ``__init__.py``) e un registry
di modelli supportati (mock + provider remoti/locali). Ogni componente che
usa un LLM sceglie il modello nel proprio parametro TOML (nessuna sezione
``[llm]`` globale); la :func:`llm_factory` istanzia la strategy
corrispondente con caching.

In **Fase 1A (F0)**: solo i mock sono istanziabili. I provider remoti
(``openai/``, ``anthropic/``, ``google/``, ``cohere/``) e locali
(``ollama/``, ``llamacpp/``, ``vllm/``) sono registrati nei metadati (per
discoverability) ma la factory solleva errore:

- se il provider richiede API key e la env var è assente →
  :class:`MissingAPIKeyError` (errore all'istanziazione, come da spec);
- altrimenti → :class:`ProviderNotImplementedError` (le implementazioni
  reali arrivano in Fase 1B/1C, vedi ``docs/75-llm.md`` § F0).

Le chiavi API non vanno mai nei TOML: solo env var (stessa regola di
``[embedding]``).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from typing import Any, Dict, List, Optional

from knowledge_base.strategies import (
    LLMMetadata,
    LLMRegistry,
    LLMStrategy,
    llm_registry,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Eccezioni
# --------------------------------------------------------------------------- #


class MissingAPIKeyError(RuntimeError):
    """Sollevata quando una strategy remota non trova l'API key nell'env.

    Spec Step 6-bis: la chiave mancante genera errore all'istanziazione
    (non a runtime), così la configurazione errata è rilevata subito.
    """

    def __init__(self, provider: str, env_var: str) -> None:
        self.provider = provider
        self.env_var = env_var
        super().__init__(
            f"API key per {provider} non trovata. "
            f"Impostare la variabile d'ambiente {env_var}."
        )


class UnknownLLMModelError(KeyError):
    """Sollevata quando ``llm_factory`` riceve un model name non registrato."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        available = ", ".join(llm_registry.list_names()) or "(nessuno)"
        super().__init__(
            f"LLM '{model_name}' non registrato. Disponibili: {available}"
        )


class ProviderNotImplementedError(NotImplementedError):
    """Sollevata dalla factory per provider non ancora implementati.

    In Fase 1A (F0) i provider remoti/locali sono solo stub nei metadati:
    la factory solleva questo errore per segnalare che l'implementazione
    concreta arriverà in Fase 1B/1C.
    """

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(
            f"Provider '{provider}' non ancora implementato in Fase 1A "
            f"(solo mock/* sono istanziabili). Le implementazioni reali "
            f"arrivano in Fase 1B/1C (vedi docs/75-llm.md § F0)."
        )


# --------------------------------------------------------------------------- #
# Classe base
# --------------------------------------------------------------------------- #


class BaseLLM:
    """Base comune: espone ``name`` e ``metadata``. Le sottoclassi
    implementano :meth:`generate` e :meth:`stream`."""

    name: str = ""
    metadata: LLMMetadata

    def __init__(self, **params: Any) -> None:
        self.params = params


class MockEchoLLM(BaseLLM):
    """LLM mock che restituisce l'ultimo messaggio utente.

    Utile nei test per verificare che l'interfaccia è rispettata e per
    debuggare il plumbing della pipeline (la risposta è deterministica e
    contiene la query originale).
    """

    def __init__(self, metadata: Optional[LLMMetadata] = None, **params: Any) -> None:
        super().__init__(**params)
        self.name = "mock/echo"
        self.metadata = metadata or _make_mock_metadata("mock/echo")

    def generate(
        self,
        messages: List[Dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> str:
        return _last_user_message(messages)

    def stream(
        self,
        messages: List[Dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> Iterator[str]:
        # Token-by-token frammentando sugli spazi (preserva le parole).
        text = _last_user_message(messages)
        for token in text.split():
            yield token + " "
        # Input vuoto: almeno un yield per rispettare il contratto.
        if not text:
            yield ""


class MockFixedLLM(BaseLLM):
    """LLM mock che restituisce sempre ``"Risposta mock"``.

    Utile nei test in cui si vuole solo verificare il passaggio del testo
    di output senza dipendenza dal contenuto dei messaggi.
    """

    _FIXED = "Risposta mock"

    def __init__(self, metadata: Optional[LLMMetadata] = None, **params: Any) -> None:
        super().__init__(**params)
        self.name = "mock/fixed"
        self.metadata = metadata or _make_mock_metadata("mock/fixed")

    def generate(
        self,
        messages: List[Dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> str:
        return self._FIXED

    def stream(
        self,
        messages: List[Dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> Iterator[str]:
        # Restituisce l'intera frase come singolo token: l'iteratore
        # soddisfa il contratto senza complicare il mock.
        yield self._FIXED


def _make_mock_metadata(model_name: str) -> LLMMetadata:
    return LLMMetadata(
        model_name=model_name,
        provider="mock",
        context_window=4096,
        requires_api=False,
        supports_streaming=True,
        supports_json=True,
    )


def _last_user_message(messages: List[Dict[str, str]]) -> str:
    """Estrae il contenuto dell'ultimo messaggio con role='user'."""
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            return str(msg.get("content", ""))
    return ""


# --------------------------------------------------------------------------- #
# Abbreviazioni (overrideabili in init registry, spec 75-llm.md)
# --------------------------------------------------------------------------- #


_ABBREVIATIONS: Dict[str, str] = {
    "fast": "openai/gpt-4o-mini",
    "cheap": "openai/gpt-4o-mini",
    "quality": "openai/gpt-4o",
    "local": "ollama/llama3.1",
}


# --------------------------------------------------------------------------- #
# Chiavi API / base URL: env var per provider
# --------------------------------------------------------------------------- #


_API_KEY_ENV: Dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GEMINI_API_KEY",
    "cohere": "COHERE_API_KEY",
}

# Nome display per i messaggi d'errore (coerente con embedding.py:
# MissingAPIKeyError("OpenAI", ...) anziché il provider lowercase).
_PROVIDER_DISPLAY: Dict[str, str] = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google",
    "cohere": "Cohere",
    "ollama": "Ollama",
    "llamacpp": "llama.cpp",
    "vllm": "vLLM",
}

_BASE_URL_ENV: Dict[str, str] = {
    "ollama": "OLLAMA_BASE_URL",
    "llamacpp": "LLAMACPP_BASE_URL",
    "vllm": "VLLM_BASE_URL",
}

_DEFAULT_BASE_URLS: Dict[str, str] = {
    "ollama": "http://localhost:11434/v1",
    "llamacpp": "http://localhost:8080/v1",
    "vllm": "http://localhost:8000/v1",
}


# --------------------------------------------------------------------------- #
# Tabella modelli + registrazione
# --------------------------------------------------------------------------- #


_MOCK_MODELS: List[Dict[str, Any]] = [
    {"model_name": "mock/echo"},
    {"model_name": "mock/fixed"},
]

_REMOTE_MODELS: List[Dict[str, Any]] = [
    {"model_name": "openai/gpt-4o",                "provider": "openai",    "context_window": 128000,  "supports_streaming": True,  "supports_json": True},
    {"model_name": "openai/gpt-4o-mini",           "provider": "openai",    "context_window": 128000,  "supports_streaming": True,  "supports_json": True},
    {"model_name": "openai/gpt-4.1",               "provider": "openai",    "context_window": 1000000, "supports_streaming": True,  "supports_json": True},
    {"model_name": "openai/o3-mini",               "provider": "openai",    "context_window": 200000,  "supports_streaming": True,  "supports_json": True},
    {"model_name": "anthropic/claude-3.5-haiku",   "provider": "anthropic", "context_window": 200000,  "supports_streaming": True,  "supports_json": True},
    {"model_name": "anthropic/claude-3.5-sonnet",  "provider": "anthropic", "context_window": 200000,  "supports_streaming": True,  "supports_json": True},
    {"model_name": "anthropic/claude-4-opus",      "provider": "anthropic", "context_window": 200000,  "supports_streaming": True,  "supports_json": True},
    {"model_name": "google/gemini-2.0-flash",      "provider": "google",    "context_window": 1000000, "supports_streaming": True,  "supports_json": True},
    {"model_name": "cohere/command-r-plus",         "provider": "cohere",    "context_window": 128000,  "supports_streaming": True,  "supports_json": True},
]

_LOCAL_MODELS: List[Dict[str, Any]] = [
    {"model_name": "ollama/llama3.1",     "provider": "ollama",    "context_window": 8192,  "supports_streaming": True,  "supports_json": False},
    {"model_name": "ollama/mistral-nemo", "provider": "ollama",    "context_window": 32768, "supports_streaming": True,  "supports_json": True},
    {"model_name": "llamacpp/llama-7b",   "provider": "llamacpp", "context_window": 4096,  "supports_streaming": True,  "supports_json": False},
    {"model_name": "vllm/mistral-nemo",   "provider": "vllm",     "context_window": 32768, "supports_streaming": True,  "supports_json": True},
]


def _register_mock(entry: Dict[str, Any]) -> None:
    model_name = entry["model_name"]
    md = _make_mock_metadata(model_name)

    cls = {"mock/echo": MockEchoLLM, "mock/fixed": MockFixedLLM}[model_name]

    def _factory(_cls=cls, _md=md) -> LLMStrategy:
        return _cls(metadata=_md)

    llm_registry.register(model_name, md, factory=_factory)


def _register_remote(entry: Dict[str, Any]) -> None:
    md = LLMMetadata(
        model_name=entry["model_name"],
        provider=entry["provider"],
        context_window=entry["context_window"],
        requires_api=True,
        supports_streaming=entry["supports_streaming"],
        supports_json=entry["supports_json"],
    )
    # In Fase 1A: solo metadati (factory=None). La factory solleverà
    # ProviderNotImplementedError (previa validazione API key).
    llm_registry.register(entry["model_name"], md, factory=None)


def _register_local(entry: Dict[str, Any]) -> None:
    md = LLMMetadata(
        model_name=entry["model_name"],
        provider=entry["provider"],
        context_window=entry["context_window"],
        requires_api=False,
        supports_streaming=entry["supports_streaming"],
        supports_json=entry["supports_json"],
    )
    # In Fase 1A: solo metadati (factory=None).
    llm_registry.register(entry["model_name"], md, factory=None)


for _entry in _MOCK_MODELS:
    _register_mock(_entry)

for _entry in _REMOTE_MODELS:
    _register_remote(_entry)

for _entry in _LOCAL_MODELS:
    _register_local(_entry)


# --------------------------------------------------------------------------- #
# Cache istanze (per model_name: stessa strategy per stesso model_name)
# --------------------------------------------------------------------------- #


_LLM_CACHE: Dict[str, LLMStrategy] = {}


def clear_llm_cache() -> None:
    """Pulisce la cache delle istanze LLM (utility per test)."""
    _LLM_CACHE.clear()


# --------------------------------------------------------------------------- #
# Factory pubblica
# --------------------------------------------------------------------------- #


def llm_factory(model_name: str) -> LLMStrategy:
    """Istantia la :class:`LLMStrategy` associata a ``model_name``.

    Risolve le abbreviazioni (``fast``, ``cheap``, ``quality``, ``local``)
    prima di cercare nel registry. Mantiene una cache (per ``model_name``
    risolto): stessa strategy per stesso model_name, vedi
    ``docs/75-llm.md`` § Integrazione con AppContext.

    In **Fase 1A (F0)** sono istanziabili solo i mock; i provider
    remoti/locali sollevano:

    - :class:`MissingAPIKeyError` se il provider richiede API key e la
      env var è assente (errore all'istanziazione, non a runtime);
    - :class:`ProviderNotImplementedError` altrimenti (l'implementazione
      concreta arriva in Fase 1B/1C).

    Args:
        model_name: identificatore del modello (es. ``"mock/fixed"``,
            ``"openai/gpt-4o-mini"``, abbreviazione ``"fast"``).

    Raises:
        UnknownLLMModelError: se ``model_name`` (e la sua abbreviazione
            risolta) non è registrato.
    """
    resolved = _ABBREVIATIONS.get(model_name, model_name)

    if resolved in _LLM_CACHE:
        return _LLM_CACHE[resolved]

    if not llm_registry.contains(resolved):
        raise UnknownLLMModelError(model_name)

    md = llm_registry.get_metadata(resolved)

    if md.provider == "mock":
        factory = llm_registry.get_factory(resolved)
        instance = factory()  # type: ignore[misc]
        _LLM_CACHE[resolved] = instance
        return instance

    # Provider non-mock: in Fase 1A sono tutti stub. Convalida API key
    # prima, così l'errore è coerente col comportamento della spec
    # (errore all'istanziazione se la key manca).
    if md.requires_api:
        env_var = _API_KEY_ENV.get(md.provider)
        if env_var and not os.environ.get(env_var):
            raise MissingAPIKeyError(
                _PROVIDER_DISPLAY.get(md.provider, md.provider), env_var
            )

    raise ProviderNotImplementedError(md.provider)