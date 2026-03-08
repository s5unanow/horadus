from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from src.core import logging_setup as logging_setup_module

pytestmark = pytest.mark.unit


def test_configure_logging_uses_console_renderer_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    basic_config = MagicMock()
    configure = MagicMock()
    console_renderer = MagicMock(return_value="console-renderer")
    json_renderer = MagicMock(return_value="json-renderer")
    make_filtering = MagicMock(return_value="wrapper")
    logger_factory = MagicMock(return_value="factory")

    monkeypatch.setattr(logging_setup_module.settings, "LOG_FORMAT", "console")
    monkeypatch.setattr(logging_setup_module.settings, "RUNTIME_PROFILE", "default")
    monkeypatch.setattr(logging_setup_module.settings, "AGENT_MODE", False)
    monkeypatch.setattr(logging_setup_module.settings, "LOG_LEVEL", "warning")
    monkeypatch.setattr(logging_setup_module.logging, "basicConfig", basic_config)
    monkeypatch.setattr(logging_setup_module.structlog, "configure", configure)
    monkeypatch.setattr(logging_setup_module.structlog.dev, "ConsoleRenderer", console_renderer)
    monkeypatch.setattr(logging_setup_module.structlog.processors, "JSONRenderer", json_renderer)
    monkeypatch.setattr(
        logging_setup_module.structlog,
        "make_filtering_bound_logger",
        make_filtering,
    )
    monkeypatch.setattr(logging_setup_module.structlog.stdlib, "LoggerFactory", logger_factory)

    logging_setup_module.configure_logging()

    basic_config.assert_called_once_with(level=logging.WARNING, format="%(message)s")
    console_renderer.assert_called_once_with()
    json_renderer.assert_not_called()
    make_filtering.assert_called_once_with(logging.WARNING)
    logger_factory.assert_called_once_with()
    assert configure.call_args.kwargs["wrapper_class"] == "wrapper"
    assert configure.call_args.kwargs["logger_factory"] == "factory"


def test_configure_logging_defaults_to_json_renderer_and_info_for_unknown_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    basic_config = MagicMock()
    configure = MagicMock()
    console_renderer = MagicMock(return_value="console-renderer")
    json_renderer = MagicMock(return_value="json-renderer")
    make_filtering = MagicMock(return_value="wrapper")
    logger_factory = MagicMock(return_value="factory")

    monkeypatch.setattr(logging_setup_module.settings, "LOG_FORMAT", "json")
    monkeypatch.setattr(logging_setup_module.settings, "RUNTIME_PROFILE", "default")
    monkeypatch.setattr(logging_setup_module.settings, "AGENT_MODE", False)
    monkeypatch.setattr(logging_setup_module.settings, "LOG_LEVEL", "custom")
    monkeypatch.setattr(logging_setup_module.logging, "basicConfig", basic_config)
    monkeypatch.setattr(logging_setup_module.structlog, "configure", configure)
    monkeypatch.setattr(logging_setup_module.structlog.dev, "ConsoleRenderer", console_renderer)
    monkeypatch.setattr(logging_setup_module.structlog.processors, "JSONRenderer", json_renderer)
    monkeypatch.setattr(
        logging_setup_module.structlog,
        "make_filtering_bound_logger",
        make_filtering,
    )
    monkeypatch.setattr(logging_setup_module.structlog.stdlib, "LoggerFactory", logger_factory)

    logging_setup_module.configure_logging()

    basic_config.assert_called_once_with(level=logging.INFO, format="%(message)s")
    console_renderer.assert_not_called()
    json_renderer.assert_called_once_with()
    make_filtering.assert_called_once_with(logging.INFO)
    assert configure.call_args.kwargs["wrapper_class"] == "wrapper"
