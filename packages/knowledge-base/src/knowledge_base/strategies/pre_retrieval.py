"""Strategie di pre-retrieval: espansione testuale delle query.

Ogni strategia riceve una lista di query e produce varianti espanse.
Stadi concatenati: ogni stadio riceve le query del precedente.

Strategie:
- ``identity``: no-op, restituisce le query invariate.
- ``multi_query``: genera N sotto-query con LLM (``requires_llm=True``).
- ``step_back``: genera domanda astratta con LLM (``requires_llm=True``).
- ``least_to_most``: decompone in sottoproblemi con LLM (``requires_llm=True``).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from knowledge_base.strategies import (
    LLMStrategy,
    PreRetrievalStrategy,
    pre_retrieval_registry,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Classe base
# --------------------------------------------------------------------------- #


class BasePreRetrieval:
    """Base comune per strategie di pre-retrieval."""

    name: str = ""
    requires_llm: bool = False

    def __init__(self, **params: Any) -> None:
        self.params = params

    def expand(self, queries: List[str]) -> List[str]:
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# identity — no-op
# --------------------------------------------------------------------------- #


class IdentityPreRetrieval(BasePreRetrieval):
    """No-op: restituisce le query invariate."""

    name = "identity"
    requires_llm = False

    def expand(self, queries: List[str]) -> List[str]:
        return list(queries)


# --------------------------------------------------------------------------- #
# multi_query — genera N sotto-query con LLM
# --------------------------------------------------------------------------- #


class MultiQueryPreRetrieval(BasePreRetrieval):
    """Genera N sotto-query diverse a partire dalla query originale.

    Richiede un LLM per generare le varianti. Il prompt chiede al
    modello di generare ``n`` riformulazioni della query, ciascuna su
    una riga separata.

    In Fase 1B con LLM mock (``mock/echo``), le sotto-query sono
    varianti deterministiche derivate dalla query originale.
    """

    name = "multi_query"
    requires_llm = True

    def __init__(
        self,
        llm: LLMStrategy,
        n: int = 3,
        **params: Any,
    ) -> None:
        super().__init__(**params)
        self.llm = llm
        self.n = n

    def expand(self, queries: List[str]) -> List[str]:
        expanded: List[str] = []
        for query in queries:
            expanded.append(query)
            variants = self._generate_variants(query)
            expanded.extend(variants)
        return expanded

    def _generate_variants(self, query: str) -> List[str]:
        """Genera varianti della query usando l'LLM."""
        prompt = (
            f"Genera {self.n} riformulazioni diverse della seguente domanda, "
            f"ciascuna su una riga separata. Non numerare le righe.\n\n"
            f"Domanda: {query}"
        )
        messages = [{"role": "user", "content": prompt}]
        response = self.llm.generate(messages, max_tokens=512, temperature=0.7)
        variants = _parse_lines(response, max_lines=self.n)
        logger.info(
            "multi_query: %d riformulazioni da LLM: %s", len(variants), variants
        )
        return variants


# --------------------------------------------------------------------------- #
# step_back — genera domanda astratta con LLM
# --------------------------------------------------------------------------- #


class StepBackPreRetrieval(BasePreRetrieval):
    """Genera una domanda più astratta/generale a partire dalla query.

    Tecnica Step-Back prompting: la domanda astratta aiuta il retrieval
    a recuperare contesto più ampio. Richiede LLM.
    """

    name = "step_back"
    requires_llm = True

    def __init__(self, llm: LLMStrategy, **params: Any) -> None:
        super().__init__(**params)
        self.llm = llm

    def expand(self, queries: List[str]) -> List[str]:
        expanded: List[str] = []
        for query in queries:
            expanded.append(query)
            abstract = self._generate_abstract(query)
            if abstract:
                expanded.append(abstract)
        return expanded

    def _generate_abstract(self, query: str) -> str:
        """Genera una domanda più astratta usando l'LLM."""
        prompt = (
            "Data la seguente domanda, genera una domanda più astratta e "
            "generale che catturi il concetto sottostante. Rispondi solo con "
            "la domanda, senza spiegazioni.\n\n"
            f"Domanda: {query}"
        )
        messages = [{"role": "user", "content": prompt}]
        response = self.llm.generate(messages, max_tokens=256, temperature=0.3)
        return response.strip()


# --------------------------------------------------------------------------- #
# least_to_most — decompone in sottoproblemi con LLM
# --------------------------------------------------------------------------- #


class LeastToMostPreRetrieval(BasePreRetrieval):
    """Decompone la query in sotto-problemi sequenziali.

    Tecnica Least-to-Most prompting: la domanda complessa viene divisa
    in sotto-domande più semplici, ciascuna recuperabile separatamente.
    Richiede LLM.
    """

    name = "least_to_most"
    requires_llm = True

    def __init__(
        self,
        llm: LLMStrategy,
        max_subquestions: int = 5,
        **params: Any,
    ) -> None:
        super().__init__(**params)
        self.llm = llm
        self.max_subquestions = max_subquestions

    def expand(self, queries: List[str]) -> List[str]:
        expanded: List[str] = []
        for query in queries:
            expanded.append(query)
            subquestions = self._decompose(query)
            expanded.extend(subquestions)
        return expanded

    def _decompose(self, query: str) -> List[str]:
        """Decompone la query in sotto-domande usando l'LLM."""
        prompt = (
            f"Decompone la seguente domanda in al massimo "
            f"{self.max_subquestions} sotto-domande più semplici e "
            f"sequenziali. Ogni sotto-domanda deve essere auto-consistente "
            f"e recuperabile indipendentemente. Rispondi con una sotto-domanda "
            f"per riga, senza numerazione.\n\n"
            f"Domanda: {query}"
        )
        messages = [{"role": "user", "content": prompt}]
        response = self.llm.generate(messages, max_tokens=512, temperature=0.3)
        return _parse_lines(response, max_lines=self.max_subquestions)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _parse_lines(text: str, max_lines: int = 5) -> List[str]:
    """Estrae righe non vuote dal testo dell'LLM, limitandole a max_lines."""
    lines = [
        line.strip()
        for line in text.strip().splitlines()
        if line.strip()
    ]
    # Rimuovi numerazione (es. "1. ", "2. ")
    cleaned = []
    for line in lines[:max_lines]:
        line = re.sub(r"^\d+[\.\)]\s*", "", line)
        if line:
            cleaned.append(line)
    return cleaned


# --------------------------------------------------------------------------- #
# Registrazione all'avvio
# --------------------------------------------------------------------------- #

pre_retrieval_registry.register("identity", IdentityPreRetrieval)
pre_retrieval_registry.register("multi_query", MultiQueryPreRetrieval)
pre_retrieval_registry.register("step_back", StepBackPreRetrieval)
pre_retrieval_registry.register("least_to_most", LeastToMostPreRetrieval)
