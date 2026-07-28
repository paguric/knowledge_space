"""Watcher filesystem per workspace.

Modulo dedicato al monitoraggio degli eventi filesystem sui workspace.
Usa ``watchdog`` per intercettare creazioni/modifiche/cancellazioni
di cartelle e sincronizzare il modello col filesystem.

.. note::

    La classe :class:`WorkspaceWatcher` è definita in
    :mod:`knowledge_base.workspace_manager` per mantenere la coesione
    con il manager. Questo modulo ri-exporta il simbolo per compatibilità
    con le importazioni dal percorso dedicato.
"""

from knowledge_base.workspace_manager import WorkspaceWatcher

__all__ = ["WorkspaceWatcher"]
