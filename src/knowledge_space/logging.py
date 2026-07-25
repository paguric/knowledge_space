"""Logging su file — Step 12 della roadmap.

``setup_logging()`` configura:
- **File handler**: ``RotatingFileHandler`` su ``<log_dir>/ks.log``
  (5 MB × 3 backup), level DEBUG.
- **Console handler**: ``StreamHandler``, level INFO di default,
  DEBUG con ``--verbose``.
- **``KS_LOG_LEVEL`` env var**: se impostata, ha precedenza su tutto
  (file e console).
- **Uncaught exception hook**: logga eccezioni non catturate come
  CRITICAL prima di ``sys.exit(1)``.
- **Silenzio librerie verbose**: imposta level WARNING per
  ``chromadb``, ``sentence_transformers``, ``urllib3``,
  ``httpx``, ``httpcore``, ``watchdog``.

``setup_logging()`` è idempotente: chiamate multiple non duplicano
handler. Usa ``logging.getLogger("knowledge_space")`` come logger
radice dell'app.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# Logger radice dell'applicazione.
_APP_LOGGER_NAME = "knowledge_space"

# Livello di default per l'handler di console.
_CONSOLE_DEFAULT_LEVEL = logging.INFO

# Livello di default per l'handler su file.
_FILE_DEFAULT_LEVEL = logging.DEBUG

# Formato per l'handler su file (include timestamp completo).
_FILE_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

# Formato per l'handler di console (più semplice).
_CONSOLE_FORMAT = "[%(levelname)s] %(name)s: %(message)s"

# Librerie verbose da silenziare.
_NOISY_LIBRARIES = [
    "chromadb",
    "sentence_transformers",
    "urllib3",
    "httpx",
    "httpcore",
    "watchdog",
]

# Indicatore per verificare se ``setup_logging`` è già stato chiamato.
_configured = False


def setup_logging(
    log_dir: Path,
    verbose: bool = False,
    log_file: str = "ks.log",
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
) -> None:
    """Configura il logging per Knowledge Space.

    Args:
        log_dir: Directory dove scrivere il file di log
            (es. ``RuntimePaths.state_home / "logs"``).
        verbose: Se ``True``, console handler a DEBUG; altrimenti INFO.
        log_file: Nome del file di log (default ``ks.log``).
        max_bytes: Dimensione massima del file di log prima del rotate
            (default 5 MB).
        backup_count: Numero di backup da mantenere (default 3).
    """
    global _configured

    # Idempotenza: se già configurato, rimuovi gli handler precedenti
    # prima di riconfigurare.
    if _configured:
        _reset_handlers()

    # Crea la directory di log se non esiste.
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / log_file

    # Determina i livelli dai parametri e dall'env var.
    env_level = _parse_env_level()
    console_level = env_level if env_level is not None else (
        logging.DEBUG if verbose else _CONSOLE_DEFAULT_LEVEL
    )
    file_level = env_level if env_level is not None else _FILE_DEFAULT_LEVEL

    # Logger radice dell'app.
    app_logger = logging.getLogger(_APP_LOGGER_NAME)
    app_logger.setLevel(logging.DEBUG)  # il minimo del logger è sempre DEBUG

    # File handler.
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(file_level)
    file_handler.setFormatter(logging.Formatter(_FILE_FORMAT))
    file_handler.set_name("ks_file")
    app_logger.addHandler(file_handler)

    # Console handler.
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(logging.Formatter(_CONSOLE_FORMAT))
    console_handler.set_name("ks_console")
    app_logger.addHandler(console_handler)

    # Silenzia le librerie verbose.
    _silence_noisy_libraries(env_level)

    # Installa l'uncaught exception hook.
    _install_exception_hook()

    _configured = True


def _reset_handlers() -> None:
    """Rimuove tutti gli handler dal logger dell'app per garantire
    l'idempotenza."""
    app_logger = logging.getLogger(_APP_LOGGER_NAME)
    for handler in app_logger.handlers[:]:
        app_logger.removeHandler(handler)
        handler.close()


def _parse_env_level() -> Optional[int]:
    """Parsa la variabile d'ambiente ``KS_LOG_LEVEL``.

    Restituisce il livello numerico corrispondente, oppure ``None`` se
    la variabile non è impostata o contiene un valore non valido.
    """
    import os

    value = os.environ.get("KS_LOG_LEVEL")
    if value is None:
        return None
    level = logging.getLevelName(value.upper())
    if isinstance(level, int):
        return level
    return None


def _silence_noisy_libraries(env_level: Optional[int]) -> None:
    """Imposta level WARNING per le librerie verbose.

    Se ``KS_LOG_LEVEL`` è impostata, le librerie verbose usano comunque
    almeno WARNING (non vengono abbassate sotto WARNING).
    """
    for lib_name in _NOISY_LIBRARIES:
        lib_logger = logging.getLogger(lib_name)
        # Se l'env var è impostata e richiede un livello più alto,
        # usa quello; altrimenti WARNING.
        if env_level is not None and env_level > logging.WARNING:
            lib_logger.setLevel(env_level)
        else:
            lib_logger.setLevel(logging.WARNING)


def _install_exception_hook() -> None:
    """Installa un hook che logga eccezioni non catturate come CRITICAL
    prima di terminare il processo."""

    def _excepthook(exc_type, exc_value, exc_tb):
        if exc_type is KeyboardInterrupt:
            # Non loggare KeyboardInterrupt.
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger = logging.getLogger(_APP_LOGGER_NAME)
        logger.critical(
            "Eccezione non catturata",
            exc_info=(exc_type, exc_value, exc_tb),
        )
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook
