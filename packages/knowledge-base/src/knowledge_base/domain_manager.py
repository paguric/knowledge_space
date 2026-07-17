"""Logica operativa sui domini.

Il :class:`DomainManager` opera sul modello :class:`Workspace` manipolandone
la lista di :class:`Domain` e persistendo il risultato tramite
``WorkspaceConfig``. Come il :class:`WorkspaceManager`, non conosce nÃ© il
nome dell'app nÃ© i path XDG: riceve una funzione ``config_path_for``.

Convenzione ``auto_generate`` (da note utente): una cartella **figlia
diretta** del workspace che contiene sotto-cartelle diventa un **dominio**
(col nome della cartella principale); le cartelle **foglia** del suo
sottoalbero (a qualsiasi profonditÃ  ) diventano basi registrate in quel
dominio. Le cartelle figlie dirette del workspace giÃ  foglia rimangono
basi standalone (nessun dominio).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, List, Optional

from knowledge_base.models import Domain, KnowledgeBase, Workspace
from knowledge_base.persistence import WorkspaceConfig

ConfigPathFor = Callable[[Path], Path]


class DomainManager:
    """Operazioni sui domini di un workspace."""

    def __init__(self, config_path_for: ConfigPathFor) -> None:
        self._config_path_for = config_path_for

    def _config(self, workspace_path: Path) -> WorkspaceConfig:
        return WorkspaceConfig(
            config_path=self._config_path_for(Path(workspace_path)),
            workspace_path=Path(workspace_path),
        )

    def _save(self, workspace: Workspace) -> None:
        from knowledge_base.models import WorkspaceConfigData

        self._config(workspace.path).save(
            WorkspaceConfigData(
                version=1,
                domains=workspace.domains,
                bases=workspace.bases,
            )
        )

    # ..................................................................... #
    # Finders
    # ..................................................................... #

    def _find(self, workspace: Workspace, name: str) -> Optional[Domain]:
        for d in workspace.domains:
            if d.name == name:
                return d
        return None

    # ..................................................................... #
    # CRUD
    # ..................................................................... #

    def create(
        self,
        workspace: Workspace,
        name: str,
        base_names: Optional[List[str]] = None,
    ) -> Domain:
        """Crea un nuovo dominio. Solleva ``ValueError`` se esiste giÃ ."""
        if self._find(workspace, name) is not None:
            raise ValueError(f"Domain '{name}' esiste giÃ  nel workspace")
        domain = Domain(name=name, base_names=list(base_names or []))
        workspace.domains.append(domain)
        self._save(workspace)
        return domain

    def delete(self, workspace: Workspace, name: str) -> bool:
        """Rimuove un dominio per nome. Restituisce ``True`` se esisteva."""
        for i, d in enumerate(workspace.domains):
            if d.name == name:
                del workspace.domains[i]
                self._save(workspace)
                return True
        return False

    def activate(self, workspace: Workspace, name: str) -> bool:
        """Attiva un dominio. Restituisce ``False`` se non esiste."""
        d = self._find(workspace, name)
        if d is None:
            return False
        d.active = True
        self._save(workspace)
        return True

    def deactivate(self, workspace: Workspace, name: str) -> bool:
        """Disattiva un dominio. Restituisce ``False`` se non esiste."""
        d = self._find(workspace, name)
        if d is None:
            return False
        d.active = False
        self._save(workspace)
        return True

    def add_base(self, workspace: Workspace, domain_name: str, base_name: str) -> bool:
        """Aggiunge una base a un dominio. Restituisce ``False`` se il
        dominio non esiste o la base Ã¨ giÃ  presente."""
        d = self._find(workspace, domain_name)
        if d is None:
            return False
        if base_name in d.base_names:
            return False
        d.base_names.append(base_name)
        self._save(workspace)
        return True

    def remove_base(self, workspace: Workspace, domain_name: str, base_name: str) -> bool:
        """Rimuove una base da un dominio. Restituisce ``False`` se il
        dominio non esiste o la base non Ã¨ presente."""
        d = self._find(workspace, domain_name)
        if d is None:
            return False
        if base_name not in d.base_names:
            return False
        d.base_names.remove(base_name)
        self._save(workspace)
        return True

    # ..................................................................... #
    # Auto-generazione dalla struttura di cartelle
    # ..................................................................... #

    def auto_generate(self, workspace: Workspace) -> Workspace:
        """Genera domini e basi dalla struttura delle cartelle del workspace.

        Regole (da specifica utente):

        - Una cartella **figlia diretta** del workspace che contiene
          sotto-cartelle diventa un **dominio** (col nome della cartella).
        - Tutte le cartelle **foglia** del suo sottoalbero (a qualsiasi
          profonditÃ  ) diventano **basi** registrate in quel dominio.
        - Le cartelle figlie dirette del workspace che sono giÃ  foglia
          (senza sotto-cartelle) restano **basi standalone** (nessun dominio).

        I nomi delle basi sono path relativi al workspace con separatori
        ``/`` (per supportare il nesting). I domini giÃ  esistenti non
        vengono sovrascritti: le nuove basi discovered vengono unite ai
        loro ``base_names``.
        """
        ws_path = workspace.path
        if not ws_path.is_dir():
            return workspace

        domain_bases: dict[str, set[str]] = {}

        def _collect_leaves(root: Path) -> list[Path]:
            """Restituisce le cartelle foglia (senza sotto-cartelle non
            nascoste) del sottoalbero di ``root``, depth-first."""
            leaves: list[Path] = []
            stack = [root]
            while stack:
                cur = stack.pop()
                try:
                    subdirs = [
                        p for p in cur.iterdir()
                        if p.is_dir() and not p.name.startswith(".")
                    ]
                except OSError:
                    continue
                if not subdirs:
                    leaves.append(cur)
                else:
                    stack.extend(subdirs)
            return leaves

        for entry in ws_path.iterdir():
            if not entry.is_dir() or entry.name.startswith("."):
                continue

            subdirs = [
                p for p in entry.iterdir()
                if p.is_dir() and not p.name.startswith(".")
            ]
            if not subdirs:
                # figlia diretta foglia → base standalone
                base_name = entry.name
                if base_name not in workspace.bases:
                    workspace.bases[base_name] = KnowledgeBase(path=entry)
            else:
                # figlia diretta con sotto-cartelle → dominio
                domain_name = entry.name
                domain_bases.setdefault(domain_name, set())
                for leaf in _collect_leaves(entry):
                    rel = os.path.relpath(leaf, ws_path)
                    base_name = rel.replace(os.sep, "/")
                    if base_name not in workspace.bases:
                        workspace.bases[base_name] = KnowledgeBase(path=leaf)
                    domain_bases[domain_name].add(base_name)

        # merge nei domini esistenti
        existing = {d.name: d for d in workspace.domains}
        for name, base_names in domain_bases.items():
            if not base_names:
                continue
            if name in existing:
                for bn in sorted(base_names):
                    if bn not in existing[name].base_names:
                        existing[name].base_names.append(bn)
            else:
                workspace.domains.append(
                    Domain(name=name, base_names=sorted(base_names))
                )

        self._save(workspace)
        return workspace