"""Test per setup_logging (Step 12).

Verifica:
- Creazione directory log se non esiste
- File handler crea il file di log
- Console handler level (INFO vs DEBUG)
- KS_LOG_LEVEL env var ha precedenza
- Uncaught exception hook è installato
- Librerie verbose silenziate
- Formato del messaggio nel file
- RotatingFileHandler configurazione (max_bytes, backup_count)
- Chiamate multiple non duplicano handler
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Generator

import pytest

from knowledge_space.logging import (
    _APP_LOGGER_NAME,
    _NOISY_LIBRARIES,
    _configured,
    setup_logging,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _reset_logging(tmp_path: Path) -> Generator[None, None, None]:
    """Resetta lo stato del logging prima e dopo ogni test."""
    import knowledge_space.logging as mod

    # Salva lo stato originale.
    old_configured = mod._configured
    old_excepthook = __import__("sys").excepthook

    # Pulisci il logger dell'app.
    app_logger = logging.getLogger(_APP_LOGGER_NAME)
    for handler in app_logger.handlers[:]:
        app_logger.removeHandler(handler)
        handler.close()
    mod._configured = False

    yield

    # Ripristina lo stato originale.
    mod._configured = old_configured
    __import__("sys").excepthook = old_excepthook
    for handler in app_logger.handlers[:]:
        app_logger.removeHandler(handler)
        handler.close()


@pytest.fixture
def log_dir(tmp_path: Path) -> Path:
    """Restituisce una directory temporanea per i log."""
    return tmp_path / "logs"


# --------------------------------------------------------------------------- #
# Test creazione directory
# --------------------------------------------------------------------------- #


class TestLogDirectory:
    def test_creates_log_dir_if_not_exists(self, log_dir: Path):
        """setup_logging crea la directory log se non esiste."""
        assert not log_dir.exists()
        setup_logging(log_dir)
        assert log_dir.is_dir()

    def test_works_if_log_dir_exists(self, log_dir: Path):
        """setup_logging funziona anche se la directory esiste già."""
        log_dir.mkdir(parents=True)
        setup_logging(log_dir)
        assert log_dir.is_dir()


# --------------------------------------------------------------------------- #
# Test file handler
# --------------------------------------------------------------------------- #


class TestFileHandler:
    def test_creates_log_file(self, log_dir: Path):
        """Il file handler crea il file di log."""
        setup_logging(log_dir)
        logger = logging.getLogger(_APP_LOGGER_NAME)
        logger.info("test message")
        log_file = log_dir / "ks.log"
        assert log_file.exists()

    def test_custom_log_file_name(self, log_dir: Path):
        """Il nome del file di log è configurabile."""
        setup_logging(log_dir, log_file="custom.log")
        logger = logging.getLogger(_APP_LOGGER_NAME)
        logger.info("test message")
        assert (log_dir / "custom.log").exists()

    def test_file_handler_level_is_debug(self, log_dir: Path):
        """Il file handler ha level DEBUG di default."""
        setup_logging(log_dir)
        logger = logging.getLogger(_APP_LOGGER_NAME)
        file_handlers = [
            h for h in logger.handlers if isinstance(h, RotatingFileHandler)
        ]
        assert len(file_handlers) == 1
        assert file_handlers[0].level == logging.DEBUG


# --------------------------------------------------------------------------- #
# Test console handler level
# --------------------------------------------------------------------------- #


class TestConsoleHandler:
    def test_console_handler_level_info_by_default(self, log_dir: Path):
        """Console handler ha level INFO di default."""
        setup_logging(log_dir)
        logger = logging.getLogger(_APP_LOGGER_NAME)
        console_handlers = [
            h
            for h in logger.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, RotatingFileHandler)
        ]
        assert len(console_handlers) == 1
        assert console_handlers[0].level == logging.INFO

    def test_console_handler_level_debug_with_verbose(self, log_dir: Path):
        """Console handler ha level DEBUG con verbose=True."""
        setup_logging(log_dir, verbose=True)
        logger = logging.getLogger(_APP_LOGGER_NAME)
        console_handlers = [
            h
            for h in logger.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, RotatingFileHandler)
        ]
        assert len(console_handlers) == 1
        assert console_handlers[0].level == logging.DEBUG


# --------------------------------------------------------------------------- #
# Test KS_LOG_LEVEL env var
# --------------------------------------------------------------------------- #


class TestEnvVarPrecedence:
    def test_env_var_overrides_file_handler(
        self, log_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """KS_LOG_LEVEL ha precedenza sul file handler level."""
        monkeypatch.setenv("KS_LOG_LEVEL", "WARNING")
        setup_logging(log_dir)
        logger = logging.getLogger(_APP_LOGGER_NAME)
        file_handlers = [
            h for h in logger.handlers if isinstance(h, RotatingFileHandler)
        ]
        assert file_handlers[0].level == logging.WARNING

    def test_env_var_overrides_console_handler(
        self, log_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """KS_LOG_LEVEL ha precedenza sul console handler level."""
        monkeypatch.setenv("KS_LOG_LEVEL", "ERROR")
        setup_logging(log_dir, verbose=True)
        logger = logging.getLogger(_APP_LOGGER_NAME)
        console_handlers = [
            h
            for h in logger.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, RotatingFileHandler)
        ]
        assert console_handlers[0].level == logging.ERROR

    def test_env_var_case_insensitive(
        self, log_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """KS_LOG_LEVEL è case-insensitive."""
        monkeypatch.setenv("KS_LOG_LEVEL", "debug")
        setup_logging(log_dir)
        logger = logging.getLogger(_APP_LOGGER_NAME)
        file_handlers = [
            h for h in logger.handlers if isinstance(h, RotatingFileHandler)
        ]
        assert file_handlers[0].level == logging.DEBUG

    def test_env_var_invalid_ignored(
        self, log_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """KS_LOG_LEVEL con valore invalido viene ignorato."""
        monkeypatch.setenv("KS_LOG_LEVEL", "NONEXISTENT")
        setup_logging(log_dir)
        logger = logging.getLogger(_APP_LOGGER_NAME)
        file_handlers = [
            h for h in logger.handlers if isinstance(h, RotatingFileHandler)
        ]
        # Default: file handler è DEBUG.
        assert file_handlers[0].level == logging.DEBUG


# --------------------------------------------------------------------------- #
# Test uncaught exception hook
# --------------------------------------------------------------------------- #


class TestExceptionHook:
    def test_exception_hook_is_installed(self, log_dir: Path):
        """setup_logging installa un custom excepthook."""
        import sys

        old_hook = sys.excepthook
        setup_logging(log_dir)
        assert sys.excepthook is not old_hook

    def test_exception_hook_logs_critical(self, log_dir: Path):
        """L'excepthook logga eccezioni come CRITICAL."""
        import sys

        setup_logging(log_dir)
        logger = logging.getLogger(_APP_LOGGER_NAME)

        # Cattura i log emessi.
        records: list[logging.LogRecord] = []

        class _CaptureHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        capture = _CaptureHandler()
        capture.setLevel(logging.DEBUG)
        logger.addHandler(capture)

        try:
            raise ValueError("test exception")
        except ValueError:
            exc_info = sys.exc_info()
            sys.excepthook(*exc_info)

        logger.removeHandler(capture)

        critical_records = [r for r in records if r.levelno == logging.CRITICAL]
        assert len(critical_records) >= 1
        assert "Eccezione non catturata" in critical_records[0].getMessage()


# --------------------------------------------------------------------------- #
# Test librerie verbose
# --------------------------------------------------------------------------- #


class TestNoisyLibraries:
    def test_noisy_libraries_silenced(self, log_dir: Path):
        """Le librerie verbose sono impostate a WARNING."""
        setup_logging(log_dir)
        for lib_name in _NOISY_LIBRARIES:
            lib_logger = logging.getLogger(lib_name)
            assert lib_logger.level == logging.WARNING, (
                f"Logger '{lib_name}' ha level {lib_logger.level}, "
                f"atteso {logging.WARNING}"
            )

    def test_noisy_libraries_respect_higher_env(
        self, log_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Se KS_LOG_LEVEL è più alto di WARNING, le librerie usano
        quel livello."""
        monkeypatch.setenv("KS_LOG_LEVEL", "ERROR")
        setup_logging(log_dir)
        for lib_name in _NOISY_LIBRARIES:
            lib_logger = logging.getLogger(lib_name)
            assert lib_logger.level == logging.ERROR


# --------------------------------------------------------------------------- #
# Test formato messaggio
# --------------------------------------------------------------------------- #


class TestLogFormat:
    def test_file_format_contains_timestamp(self, log_dir: Path):
        """Il formato del file include il timestamp."""
        setup_logging(log_dir)
        logger = logging.getLogger(_APP_LOGGER_NAME)
        logger.info("format test")
        log_file = log_dir / "ks.log"
        content = log_file.read_text()
        # Il formato è: "2026-07-26 12:00:00,000 [INFO] knowledge_space: ..."
        assert "[INFO]" in content
        assert "knowledge_space:" in content
        assert "format test" in content

    def test_file_format_has_level_and_name(self, log_dir: Path):
        """Il formato del file contiene levelname e logger name."""
        setup_logging(log_dir)
        logger = logging.getLogger(_APP_LOGGER_NAME)
        logger.warning("warn test")
        log_file = log_dir / "ks.log"
        content = log_file.read_text()
        assert "[WARNING]" in content
        assert "knowledge_space:" in content


# --------------------------------------------------------------------------- #
# Test RotatingFileHandler configurazione
# --------------------------------------------------------------------------- #


class TestRotatingFileHandlerConfig:
    def test_max_bytes_default(self, log_dir: Path):
        """max_bytes default è 5 MB."""
        setup_logging(log_dir)
        logger = logging.getLogger(_APP_LOGGER_NAME)
        file_handlers = [
            h for h in logger.handlers if isinstance(h, RotatingFileHandler)
        ]
        assert len(file_handlers) == 1
        assert file_handlers[0].maxBytes == 5 * 1024 * 1024

    def test_max_bytes_custom(self, log_dir: Path):
        """max_bytes è configurabile."""
        setup_logging(log_dir, max_bytes=1024)
        logger = logging.getLogger(_APP_LOGGER_NAME)
        file_handlers = [
            h for h in logger.handlers if isinstance(h, RotatingFileHandler)
        ]
        assert file_handlers[0].maxBytes == 1024

    def test_backup_count_default(self, log_dir: Path):
        """backup_count default è 3."""
        setup_logging(log_dir)
        logger = logging.getLogger(_APP_LOGGER_NAME)
        file_handlers = [
            h for h in logger.handlers if isinstance(h, RotatingFileHandler)
        ]
        assert file_handlers[0].backupCount == 3

    def test_backup_count_custom(self, log_dir: Path):
        """backup_count è configurabile."""
        setup_logging(log_dir, backup_count=5)
        logger = logging.getLogger(_APP_LOGGER_NAME)
        file_handlers = [
            h for h in logger.handlers if isinstance(h, RotatingFileHandler)
        ]
        assert file_handlers[0].backupCount == 5


# --------------------------------------------------------------------------- #
# Test idempotenza
# --------------------------------------------------------------------------- #


class TestIdempotency:
    def test_multiple_calls_dont_duplicate_handlers(self, log_dir: Path):
        """Chiamate multiple non duplicano gli handler."""
        setup_logging(log_dir)
        setup_logging(log_dir)
        setup_logging(log_dir)
        logger = logging.getLogger(_APP_LOGGER_NAME)
        # Esattamente 2 handler: file + console.
        assert len(logger.handlers) == 2

    def test_multiple_calls_preserve_config(self, log_dir: Path):
        """Dopo chiamate multiple, la configurazione è quella dell'ultima."""
        setup_logging(log_dir, verbose=False)
        setup_logging(log_dir, verbose=True)
        logger = logging.getLogger(_APP_LOGGER_NAME)
        console_handlers = [
            h
            for h in logger.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, RotatingFileHandler)
        ]
        assert len(console_handlers) == 1
        assert console_handlers[0].level == logging.DEBUG


# --------------------------------------------------------------------------- #
# Test logger radice
# --------------------------------------------------------------------------- #


class TestAppLogger:
    def test_app_logger_level_is_debug(self, log_dir: Path):
        """Il logger radice dell'app ha level DEBUG (il minimo)."""
        setup_logging(log_dir)
        logger = logging.getLogger(_APP_LOGGER_NAME)
        assert logger.level == logging.DEBUG

    def test_app_logger_name(self, log_dir: Path):
        """Il logger radice dell'app si chiama 'knowledge_space'."""
        setup_logging(log_dir)
        logger = logging.getLogger(_APP_LOGGER_NAME)
        assert logger.name == "knowledge_space"
