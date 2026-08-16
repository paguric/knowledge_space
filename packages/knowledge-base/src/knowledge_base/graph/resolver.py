"""Entity resolution: dedup entità estratte (rete di sicurezza).

Il prompt di estrazione chiede già dedup per nome; ``ExactMatchResolver``
fonde le entità rimaste con lo stesso ``(name normalizzato, label)`` e
rimappa gli archi sui nomi canonici.

Un solo resolver, nessuna dipendenza esterna (niente spaCy).
"""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class ExactMatchResolver:
    """Fonde entità con lo stesso nome (case-insensitive, strip) e label.

    ``resolve(nodes, edges)`` restituisce ``(nodi_dedup, archi)``: i nodi
    duplicati collassano sul primo nome incontrato (canonical); gli archi
    con source/target duplicati vengono rimappati al canonical.
    """

    def resolve(
        self,
        nodes: List[Dict[str, str]],
        edges: List[Dict[str, str]],
    ) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
        """Dedup per coppia (name normalizzato, label normalizzato)."""
        canonical: Dict[Tuple[str, str], str] = {}
        deduped: List[Dict[str, str]] = []
        seen_names: set = set()

        for node in nodes:
            name = (node.get("name") or "").strip()
            label = (node.get("label") or "").strip().lower()
            key = (name.lower(), label)
            if key in canonical:
                # duplicato: tieni solo il canonical
                continue
            canonical[key] = name
            if (name, label) not in seen_names:
                seen_names.add((name, label))
                deduped.append({"name": name, "label": node.get("label", "").strip()})

        remapped: List[Dict[str, str]] = []
        for edge in edges:
            source = (edge.get("source") or "").strip()
            target = (edge.get("target") or "").strip()
            new_edge = dict(edge)
            # Rimappa ai nomi canonici (per nome+label nota non basta il
            # nome: l'arco non ha label → prova il match per nome solo).
            src_key = _lookup_name(canonical, source)
            tgt_key = _lookup_name(canonical, target)
            if src_key is not None:
                new_edge["source"] = src_key
            if tgt_key is not None:
                new_edge["target"] = tgt_key
            remapped.append(new_edge)

        return deduped, remapped


def _lookup_name(canonical: Dict[Tuple[str, str], str], name: str) -> str | None:
    """Cerca il nome canonical per un nome dato (senza label)."""
    n = name.lower()
    for (key_name, _label), canon in canonical.items():
        if key_name == n:
            return canon
    return None
