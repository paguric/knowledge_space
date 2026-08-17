"""Strategie LLM: interfaccia comune per tutti i modelli linguistici.

Definisce :class:`LLMStrategy` (Protocol in ``__init__.py``) e un registry
di modelli supportati (mock + provider OpenAI-compatibili). Ogni
componente che usa un LLM sceglie il modello nel proprio parametro TOML
(nessuna sezione ``[llm]`` globale); la :func:`llm_factory` istanzia la
strategy corrispondente con caching.

**Due soli prefissi per gli endpoint OpenAI-compatibili**
(:class:`OpenAICompatibleLLM`):

- ``lm-studio/<modello>`` — LM Studio locale (``auto`` = rileva il primo
  modello caricato);
- ``openai-compatible/<modello>`` — qualunque endpoint che espone l'API
  chat completions in formato OpenAI (OpenRouter, OpenAI, vLLM, ...),
  configurato via ``OPENAI_COMPATIBLE_BASE_URL`` e
  ``OPENAI_COMPATIBLE_API_KEY``.

Provider non OpenAI-compatibili (``anthropic/``, ``google/``,
``cohere/``) restano registrati nei metadati ma la factory solleva
:class:`ProviderNotImplementedError`.

Le chiavi API non vanno mai nei TOML: solo env var (stessa regola di
``[embedding]``).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from typing import Any, Dict, List, Optional, Tuple

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
    """Sollevata dalla factory per provider non OpenAI-compatibili.

    Provider che non espongono l'API chat completions in formato OpenAI
    (anthropic, google, cohere) restano stub nei metadati: la factory
    solleva questo errore.
    """

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(
            f"Provider '{provider}' non ancora implementato: espone un'API "
            f"non compatibile con il formato OpenAI. Disponibili: provider "
            f"OpenAI-compatibili (lm-studio/, openai-compatible/) "
            f"e mock/*."
        )


class LLMConnectionError(RuntimeError):
    """Errore di connessione o chiamata a un endpoint OpenAI-compatibile."""


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


class OpenAICompatibleLLM(BaseLLM):
    """LLM via endpoint OpenAI-compatibile (LM Studio, OpenRouter, OpenAI, ...).

    Un'unica implementazione per ogni servizio che espone l'API chat
    completions in formato OpenAI: cambiano solo ``base_url`` e
    ``api_key``. Il client ``openai`` è inizializzato lazy.

    Args:
        metadata: metadati del modello.
        base_url: URL base dell'endpoint (es. ``http://localhost:1234/v1``).
        api_key: chiave API (per LM Studio va bene un segnaposto).
        model_name: nome modello da usare nelle chiamate; ``"auto"``
            (o ``None``) → rileva il primo modello caricato dall'endpoint
            (GET /v1/models).
    """

    def __init__(
        self,
        metadata: LLMMetadata,
        base_url: str,
        api_key: str,
        model_name: Optional[str] = None,
        **params: Any,
    ) -> None:
        super().__init__(**params)
        self.name = metadata.model_name
        self.metadata = metadata
        self._base_url = base_url
        self._api_key = api_key
        self._model_name = model_name or "auto"
        self._client: Any = None  # lazy
        self._resolved_model: Optional[str] = None

    # ..................................................................... #
    # Client
    # ..................................................................... #

    def _get_client(self) -> Any:
        """Inizializza (lazy) il client OpenAI-compatibile."""
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise LLMConnectionError(
                    "Il pacchetto 'openai' non è installato. "
                    "Eseguire: uv sync"
                ) from exc
            self._client = OpenAI(
                base_url=self._base_url,
                api_key=self._api_key,
                # Timeout esplicito: senza, una chiamata appesa (rate
                # limit/rete) pende per 10 minuti in silenzio.
                timeout=120.0,
            )
        return self._client

    def _extra_body(self) -> Dict[str, Any]:
        """Campi extra del payload: per OpenRouter disabilita il
        reasoning — il router free instrada spesso verso modelli
        reasoning, che consumano i token nel reasoning e restituiscono
        ``content`` vuoto (chunk saltati, risposte lentissime)."""
        if "openrouter.ai" in self._base_url:
            return {"reasoning": {"enabled": False}}
        return {}

    def _resolve_model(self) -> str:
        """Ritorna il model_name da usare; con ``auto`` rileva il primo
        modello caricato sull'endpoint."""
        if self._resolved_model:
            return self._resolved_model
        if self._model_name not in ("auto", None):
            self._resolved_model = self._model_name
            return self._resolved_model

        client = self._get_client()
        try:
            models = client.models.list()
            names = [m.id for m in getattr(models, "data", [])]
        except Exception as exc:
            raise LLMConnectionError(
                f"Impossibile contattare l'endpoint {self._base_url} "
                f"per l'auto-detect del modello: {exc}"
            ) from exc
        if not names:
            raise LLMConnectionError(
                f"Endpoint {self._base_url} raggiunto ma nessun modello "
                f"caricato: carica un modello in LM Studio e riprova"
            )
        self._resolved_model = names[0]
        logger.info(
            "Auto-detect LLM: %s (da %s)", self._resolved_model, self._base_url
        )
        return self._resolved_model

    # ..................................................................... #
    # LLMStrategy
    # ..................................................................... #

    def generate(
        self,
        messages: List[Dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> str:
        client = self._get_client()
        model = self._resolve_model()
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **self._extra_body(),
            )
        except Exception as exc:
            raise LLMConnectionError(
                f"Chiamata LLM fallita ({self._base_url}, modello '{model}'): "
                f"{exc}"
            ) from exc
        content = getattr(
            getattr(getattr(response, "choices", [{}])[0], "message", None),
            "content",
            None,
        )
        return content or ""

    def stream(
        self,
        messages: List[Dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> Iterator[str]:
        client = self._get_client()
        model = self._resolve_model()
        try:
            stream = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
                **self._extra_body(),
            )
        except Exception as exc:
            raise LLMConnectionError(
                f"Chiamata LLM fallita ({self._base_url}, modello '{model}'): "
                f"{exc}"
            ) from exc
        for chunk in stream:
            if not getattr(chunk, "choices", None):
                continue
            delta = getattr(chunk.choices[0], "delta", None)
            content = getattr(delta, "content", None)
            if content:
                yield content


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
    "fast": "openai-compatible/gpt-4o-mini",
    "cheap": "openai-compatible/gpt-4o-mini",
    "quality": "openai-compatible/gpt-4o",
    "local": "lm-studio/auto",
}


# --------------------------------------------------------------------------- #
# Chiavi API / base URL: env var per provider
# --------------------------------------------------------------------------- #


_API_KEY_ENV: Dict[str, str] = {
    "openai-compatible": "OPENAI_COMPATIBLE_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GEMINI_API_KEY",
    "cohere": "COHERE_API_KEY",
}

# Nome display per i messaggi d'errore (coerente con embedding.py:
# MissingAPIKeyError("OpenAI", ...) anziché il provider lowercase).
_PROVIDER_DISPLAY: Dict[str, str] = {
    "openai-compatible": "endpoint OpenAI-compatibile",
    "lm-studio": "LM Studio",
    "anthropic": "Anthropic",
    "google": "Google",
    "cohere": "Cohere",
}

_BASE_URL_ENV: Dict[str, str] = {
    "lm-studio": "LM_STUDIO_BASE_URL",
    "openai-compatible": "OPENAI_COMPATIBLE_BASE_URL",
}

_DEFAULT_BASE_URLS: Dict[str, str] = {
    "lm-studio": "http://localhost:1234/v1",
    "openai-compatible": "http://localhost:1234/v1",
}


# --------------------------------------------------------------------------- #
# Tabella modelli + registrazione
# --------------------------------------------------------------------------- #


_MOCK_MODELS: List[Dict[str, Any]] = [
    {"model_name": "mock/echo"},
    {"model_name": "mock/fixed"},
]

_REMOTE_MODELS: List[Dict[str, Any]] = [
    # Provider non OpenAI-compatibili: solo stub (factory=None).
    {"model_name": "anthropic/claude-3.5-haiku",   "provider": "anthropic", "context_window": 200000,  "supports_streaming": True,  "supports_json": True},
    {"model_name": "anthropic/claude-3.5-sonnet",  "provider": "anthropic", "context_window": 200000,  "supports_streaming": True,  "supports_json": True},
    {"model_name": "anthropic/claude-4-opus",      "provider": "anthropic", "context_window": 200000,  "supports_streaming": True,  "supports_json": True},
    {"model_name": "google/gemini-2.0-flash",      "provider": "google",    "context_window": 1000000, "supports_streaming": True,  "supports_json": True},
    {"model_name": "cohere/command-r-plus",         "provider": "cohere",    "context_window": 128000,  "supports_streaming": True,  "supports_json": True},
]

# Modelli registrati con factory: endpoint OpenAI-compatibili.
# ``lm-studio/auto`` rileva il primo modello caricato (GET /v1/models).
# Gli altri endpoint (OpenRouter, OpenAI, ...) si usano col prefisso
# dinamico ``openai-compatible/<modello>`` + env var.
_OPENAI_COMPATIBLE_MODELS: List[Dict[str, Any]] = [
    {"model_name": "lm-studio/auto",               "provider": "lm-studio", "context_window": 32768,  "supports_streaming": True,  "supports_json": True},
]


def _register_mock(entry: Dict[str, Any]) -> None:
    model_name = entry["model_name"]
    md = _make_mock_metadata(model_name)

    cls = {"mock/echo": MockEchoLLM, "mock/fixed": MockFixedLLM}[model_name]

    def _factory(_cls=cls, _md=md) -> LLMStrategy:
        return _cls(metadata=_md)

    llm_registry.register(model_name, md, factory=_factory)


def _register_remote(entry: Dict[str, Any]) -> None:
    """Registra provider non OpenAI-compatibili come stub (factory=None)."""
    md = LLMMetadata(
        model_name=entry["model_name"],
        provider=entry["provider"],
        context_window=entry["context_window"],
        requires_api=True,
        supports_streaming=entry["supports_streaming"],
        supports_json=entry["supports_json"],
    )
    # Solo metadati (factory=None): la factory solleverà
    # ProviderNotImplementedError (previa validazione API key).
    llm_registry.register(entry["model_name"], md, factory=None)


def _register_openai_compatible(entry: Dict[str, Any]) -> None:
    """Registra un modello su endpoint OpenAI-compatibile con factory.

    La factory risolve ``base_url`` (env con default) e ``api_key``
    (env; per LM Studio un segnaposto) e istanzia
    :class:`OpenAICompatibleLLM`.
    """
    md = LLMMetadata(
        model_name=entry["model_name"],
        provider=entry["provider"],
        context_window=entry["context_window"],
        requires_api=entry["provider"] != "lm-studio",
        supports_streaming=entry["supports_streaming"],
        supports_json=entry["supports_json"],
    )
    provider = entry["provider"]
    model_id = entry["model_name"].partition("/")[2]

    def _factory(_md=md, _provider=provider, _model_id=model_id) -> LLMStrategy:
        base_url = os.environ.get(
            _BASE_URL_ENV.get(_provider, ""), _DEFAULT_BASE_URLS[_provider]
        )
        api_key = os.environ.get(_API_KEY_ENV.get(_provider, ""), "lm-studio")
        return OpenAICompatibleLLM(
            metadata=_md,
            base_url=base_url,
            api_key=api_key,
            model_name=_model_id,
        )

    llm_registry.register(entry["model_name"], md, factory=_factory)


for _entry in _MOCK_MODELS:
    _register_mock(_entry)

for _entry in _REMOTE_MODELS:
    _register_remote(_entry)

for _entry in _OPENAI_COMPATIBLE_MODELS:
    _register_openai_compatible(_entry)


# --------------------------------------------------------------------------- #
# Cache istanze (per model_name: stessa strategy per stesso model_name)
# --------------------------------------------------------------------------- #


_LLM_CACHE: Dict[str, LLMStrategy] = {}


def clear_llm_cache() -> None:
    """Pulisce la cache delle istanze LLM (utility per test)."""
    _LLM_CACHE.clear()


# --------------------------------------------------------------------------- #
# Prefissi dinamici: modelli non registrati singolarmente
# --------------------------------------------------------------------------- #


_DYNAMIC_PREFIXES: Tuple[str, ...] = (
    "lm-studio/",
    "openai-compatible/",
)


def _build_dynamic_llm(model_name: str) -> LLMStrategy:
    """Costruisce un :class:`OpenAICompatibleLLM` per un modello con
    prefisso dinamico non registrato nel registry (es.
    ``lm-studio/Qwen2.5-7B-Instruct``,
    ``openai-compatible/gpt-4o-mini`` per OpenRouter/OpenAI/vLLM)."""
    provider, _, model_id = model_name.partition("/")
    if provider == "lm-studio":
        api_key = "lm-studio"  # segnaposto, LM Studio non la verifica
    else:
        env_var = _API_KEY_ENV[provider]
        api_key = os.environ.get(env_var)
        if not api_key:
            raise MissingAPIKeyError(_PROVIDER_DISPLAY[provider], env_var)

    base_url = os.environ.get(
        _BASE_URL_ENV.get(provider, ""), _DEFAULT_BASE_URLS[provider]
    )
    md = LLMMetadata(
        model_name=model_name,
        provider=provider,
        context_window=32768,
        requires_api=provider != "lm-studio",
        supports_streaming=True,
        supports_json=True,
    )
    return OpenAICompatibleLLM(
        metadata=md,
        base_url=base_url,
        api_key=api_key,
        model_name=model_id,
    )


# --------------------------------------------------------------------------- #
# Factory pubblica
# --------------------------------------------------------------------------- #


def llm_factory(model_name: str) -> LLMStrategy:
    """Istantia la :class:`LLMStrategy` associata a ``model_name``.

    Risolve le abbreviazioni (``fast``, ``cheap``, ``quality``, ``local``)
    prima di cercare nel registry. Mantiene una cache (per ``model_name``
    risolto): stessa strategy per stesso model_name, vedi
    ``docs/75-llm.md`` § Integrazione con AppContext.

    Casi supportati:

    - ``mock/*`` → istanze mock;
    - modelli registrati con factory (``lm-studio/auto``) →
      :class:`OpenAICompatibleLLM` (con validazione API key se richiesta);
    - prefissi dinamici (``lm-studio/<modello>``,
      ``openai-compatible/<modello>``) → :class:`OpenAICompatibleLLM`
      costruito al volo;
    - stub non OpenAI-compatibili (``anthropic/``, ``google/``,
      ``cohere/``) → :class:`MissingAPIKeyError` se manca la chiave,
      altrimenti :class:`ProviderNotImplementedError`.

    Args:
        model_name: identificatore del modello (es. ``"mock/fixed"``,
            ``"lm-studio/auto"``, ``"openai-compatible/gpt-4o-mini"``).

    Raises:
        UnknownLLMModelError: se ``model_name`` (e la sua abbreviazione
            risolta) non è riconosciuto.
        MissingAPIKeyError: se il provider richiede API key e la env var
            è assente.
    """
    resolved = _ABBREVIATIONS.get(model_name, model_name)

    if resolved in _LLM_CACHE:
        return _LLM_CACHE[resolved]

    if llm_registry.contains(resolved):
        md = llm_registry.get_metadata(resolved)
        factory = llm_registry.get_factory(resolved)

        if factory is not None:
            if md.requires_api:
                env_var = _API_KEY_ENV.get(md.provider)
                if env_var and not os.environ.get(env_var):
                    raise MissingAPIKeyError(
                        _PROVIDER_DISPLAY.get(md.provider, md.provider),
                        env_var,
                    )
            instance = factory()  # type: ignore[misc]
            _LLM_CACHE[resolved] = instance
            return instance

        # Stub non OpenAI-compatibili: convalida API key prima, così
        # l'errore è coerente (errore all'istanziazione se la key manca).
        if md.requires_api:
            env_var = _API_KEY_ENV.get(md.provider)
            if env_var and not os.environ.get(env_var):
                raise MissingAPIKeyError(
                    _PROVIDER_DISPLAY.get(md.provider, md.provider), env_var
                )
        raise ProviderNotImplementedError(md.provider)

    # Prefissi dinamici non registrati singolarmente
    for prefix in _DYNAMIC_PREFIXES:
        if resolved.startswith(prefix):
            instance = _build_dynamic_llm(resolved)
            _LLM_CACHE[resolved] = instance
            return instance

    raise UnknownLLMModelError(model_name)