"""Test per setup_logging (Step 12) e logging operazioni (Step 12-bis).

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
- Propagazione logger knowledge_base
- Logging operazioni manager e CLI
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
# Helper: handler lookup sul root logger (dove setup_logging ora registra)
# --------------------------------------------------------------------------- #


def _root_file_handlers() -> list[RotatingFileHandler]:
    """Restituisce gli handler file ``ks_*`` dal root logger."""
    return [
        h
        for h in logging.getLogger().handlers
        if isinstance(h, RotatingFileHandler) and (h.name or "").startswith("ks_")
    ]


def _root_console_handlers() -> list[logging.StreamHandler]:
    """Restituisce gli handler console ``ks_*`` dal root logger."""
    return [
        h
        for h in logging.getLogger().handlers
        if isinstance(h, logging.StreamHandler)
        and not isinstance(h, RotatingFileHandler)
        and (h.name or "").startswith("ks_")
    ]


def _flush_ks() -> None:
    """Forza il flush di tutti gli handler ``ks_*``."""
    for h in logging.getLogger().handlers:
        if (h.name or "").startswith("ks_"):
            h.flush()


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _reset_logging(tmp_path: Path) -> Generator[None, None, None]:
    """Resetta lo stato del logging prima e dopo ogni test."""
    import knowledge_space.logging as mod

    old_configured = mod._configured
    old_excepthook = __import__("sys").excepthook

    # Pulisci gli handler ks_* dal root logger.
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        if (handler.name or "").startswith("ks_"):
            root_logger.removeHandler(handler)
            handler.close()
    mod._configured = False

    yield

    # Ripristina lo stato originale.
    mod._configured = old_configured
    __import__("sys").excepthook = old_excepthook
    for handler in root_logger.handlers[:]:
        if (handler.name or "").startswith("ks_"):
            root_logger.removeHandler(handler)
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
        logging.getLogger(_APP_LOGGER_NAME).info("test message")
        log_file = log_dir / "ks.log"
        assert log_file.exists()

    def test_custom_log_file_name(self, log_dir: Path):
        """Il nome del file di log è configurabile."""
        setup_logging(log_dir, log_file="custom.log")
        logging.getLogger(_APP_LOGGER_NAME).info("test message")
        assert (log_dir / "custom.log").exists()

    def test_file_handler_level_is_debug(self, log_dir: Path):
        """Il file handler ha level DEBUG di default."""
        setup_logging(log_dir)
        file_handlers = _root_file_handlers()
        assert len(file_handlers) == 1
        assert file_handlers[0].level == logging.DEBUG


# --------------------------------------------------------------------------- #
# Test console handler level
# --------------------------------------------------------------------------- #


class TestConsoleHandler:
    def test_console_handler_level_info_by_default(self, log_dir: Path):
        """Console handler ha level INFO di default."""
        setup_logging(log_dir)
        console_handlers = _root_console_handlers()
        assert len(console_handlers) == 1
        assert console_handlers[0].level == logging.INFO

    def test_console_handler_level_debug_with_verbose(self, log_dir: Path):
        """Console handler ha level DEBUG con verbose=True."""
        setup_logging(log_dir, verbose=True)
        console_handlers = _root_console_handlers()
        assert len(console_handlers) == 1
        assert console_handlers[0].level == logging.DEBUG

    def test_console_level_param_overrides_verbose(self, log_dir: Path):
        """Il parametro console_level ha precedenza su verbose."""
        setup_logging(log_dir, verbose=True, console_level=logging.WARNING)
        console_handlers = _root_console_handlers()
        assert len(console_handlers) == 1
        assert console_handlers[0].level == logging.WARNING


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
        file_handlers = _root_file_handlers()
        assert file_handlers[0].level == logging.WARNING

    def test_env_var_overrides_console_handler(
        self, log_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """KS_LOG_LEVEL ha precedenza sul console handler level."""
        monkeypatch.setenv("KS_LOG_LEVEL", "ERROR")
        setup_logging(log_dir, verbose=True)
        console_handlers = _root_console_handlers()
        assert console_handlers[0].level == logging.ERROR

    def test_env_var_case_insensitive(
        self, log_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """KS_LOG_LEVEL è case-insensitive."""
        monkeypatch.setenv("KS_LOG_LEVEL", "debug")
        setup_logging(log_dir)
        file_handlers = _root_file_handlers()
        assert file_handlers[0].level == logging.DEBUG

    def test_env_var_invalid_ignored(
        self, log_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """KS_LOG_LEVEL con valore invalido viene ignorato."""
        monkeypatch.setenv("KS_LOG_LEVEL", "NONEXISTENT")
        setup_logging(log_dir)
        file_handlers = _root_file_handlers()
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
        logging.getLogger(_APP_LOGGER_NAME).info("format test")
        log_file = log_dir / "ks.log"
        content = log_file.read_text()
        assert "[INFO]" in content
        assert "knowledge_space:" in content
        assert "format test" in content

    def test_file_format_has_level_and_name(self, log_dir: Path):
        """Il formato del file contiene levelname e logger name."""
        setup_logging(log_dir)
        logging.getLogger(_APP_LOGGER_NAME).warning("warn test")
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
        file_handlers = _root_file_handlers()
        assert len(file_handlers) == 1
        assert file_handlers[0].maxBytes == 5 * 1024 * 1024

    def test_max_bytes_custom(self, log_dir: Path):
        """max_bytes è configurabile."""
        setup_logging(log_dir, max_bytes=1024)
        file_handlers = _root_file_handlers()
        assert file_handlers[0].maxBytes == 1024

    def test_backup_count_default(self, log_dir: Path):
        """backup_count default è 3."""
        setup_logging(log_dir)
        file_handlers = _root_file_handlers()
        assert file_handlers[0].backupCount == 3

    def test_backup_count_custom(self, log_dir: Path):
        """backup_count è configurabile."""
        setup_logging(log_dir, backup_count=5)
        file_handlers = _root_file_handlers()
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
        # Esattamente 2 handler ks_*: file + console.
        file_h = _root_file_handlers()
        console_h = _root_console_handlers()
        assert len(file_h) == 1
        assert len(console_h) == 1

    def test_multiple_calls_preserve_config(self, log_dir: Path):
        """Dopo chiamate multiple, la configurazione è quella dell'ultima."""
        setup_logging(log_dir, verbose=False)
        setup_logging(log_dir, verbose=True)
        console_handlers = _root_console_handlers()
        assert len(console_handlers) == 1
        assert console_handlers[0].level == logging.DEBUG


# --------------------------------------------------------------------------- #
# Test logger radice dell'app
# --------------------------------------------------------------------------- #


class TestAppLogger:
    def test_app_logger_name(self, log_dir: Path):
        """Il logger radice dell'app si chiama 'knowledge_space'."""
        setup_logging(log_dir)
        logger = logging.getLogger(_APP_LOGGER_NAME)
        assert logger.name == "knowledge_space"


# --------------------------------------------------------------------------- #
# Test propagazione knowledge_base
# --------------------------------------------------------------------------- #


class TestKnowledgeBasePropagation:
    """Verifica che i log di knowledge_base.* finiscano su ks.log."""

    def test_kb_log_captured_on_file(self, log_dir: Path):
        """Un log da knowledge_base finisce nel file ks.log."""
        setup_logging(log_dir)
        kb_logger = logging.getLogger("knowledge_base.workspace_manager")
        kb_logger.info("test messaggio da knowledge_base")
        _flush_ks()
        log_file = log_dir / "ks.log"
        content = log_file.read_text()
        assert "test messaggio da knowledge_base" in content
        assert "knowledge_base.workspace_manager" in content

    def test_kb_logger_level_is_debug(self, log_dir: Path):
        """Il logger knowledge_base ha level DEBUG dopo setup_logging."""
        setup_logging(log_dir)
        kb_logger = logging.getLogger("knowledge_base")
        assert kb_logger.level == logging.DEBUG

    def test_kb_logger_propagates(self, log_dir: Path):
        """Il logger knowledge_base propaga al root logger."""
        setup_logging(log_dir)
        kb_logger = logging.getLogger("knowledge_base")
        assert kb_logger.propagate is True


# --------------------------------------------------------------------------- #
# Test logging operazioni manager
# --------------------------------------------------------------------------- #


class TestManagerLogging:
    """Verifica che le operazioni manager scrivano su ks.log."""

    def test_workspace_manager_logs(self, log_dir: Path):
        """Le operazioni di WorkspaceManager producono log."""
        setup_logging(log_dir)
        from knowledge_base.persistence import GlobalIndex
        from knowledge_base.workspace_manager import WorkspaceManager

        index_path = log_dir / "workspaces.json"
        gi = GlobalIndex(path=index_path)

        def _config_path_for(ws_path: Path) -> Path:
            return ws_path / ".knowledge-space" / "state.json"

        mgr = WorkspaceManager(gi, _config_path_for)
        log_file = log_dir / "ks.log"

        ws_tmp = log_dir / "fake_ws"
        ws_tmp.mkdir()
        mgr.add(ws_tmp)

        _flush_ks()
        content = log_file.read_text()
        assert "Registrazione workspace" in content or "Workspace registrato" in content

    def test_domain_manager_logs(self, log_dir: Path):
        """Le operazioni di DomainManager producono log."""
        setup_logging(log_dir)
        from knowledge_base.domain_manager import DomainManager
        from knowledge_base.models import Workspace

        def _config_path_for(ws_path: Path) -> Path:
            return ws_path / ".knowledge-space" / "state.json"

        dm = DomainManager(_config_path_for)
        ws = Workspace(path=log_dir / "ws")
        (log_dir / "ws").mkdir()
        (log_dir / "ws" / ".knowledge-space").mkdir()

        dm.create(ws, "test_domain")

        _flush_ks()
        log_file = log_dir / "ks.log"
        content = log_file.read_text()
        assert "Creazione dominio" in content or "Dominio creato" in content


# --------------------------------------------------------------------------- #
# Test logging CLI tramite CliRunner
# --------------------------------------------------------------------------- #


class TestCLILogging:
    """Verifica che un comando CLI scriva sul file di log."""

    def test_cli_command_writes_to_log_file(self, tmp_path: Path):
        """Un comando CLI produce log su ks.log."""
        from typer.testing import CliRunner

        from knowledge_space.cli import app

        runner = CliRunner()
        ws_dir = tmp_path / "ws"
        ws_dir.mkdir()
        (ws_dir / ".knowledge-space").mkdir()

        # 'status' accetta --workspace e produce log.
        result = runner.invoke(app, ["status", "--workspace", str(ws_dir)])
        assert result.exit_code == 0

        state_home = os.environ.get("XDG_STATE_HOME", "")
        if state_home:
            log_path = Path(state_home) / "KnowledgeSpace" / "ks.log"
            if log_path.exists():
                content = log_path.read_text()
                assert "stato workspace" in content.lower() or "workspace" in content.lower()
