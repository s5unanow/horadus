from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path


def env_default(
    name: str,
    default: str,
    *,
    getenv: Callable[[str], str | None],
) -> str:
    value = getenv(name)
    if value is None:
        return default
    normalized = value.strip()
    return normalized or default


def dotenv_default(
    name: str,
    *,
    dotenv_loader: Callable[..., Mapping[str, object | None]],
    env_path: str = ".env",
) -> str | None:
    value = dotenv_loader(env_path).get(name)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def config_default(
    name: str,
    default: str,
    *,
    getenv: Callable[[str], str | None],
    dotenv_lookup: Callable[[str], str | None],
) -> str:
    value = getenv(name)
    if value is not None:
        normalized = value.strip()
        if normalized:
            return normalized
    dotenv_value = dotenv_lookup(name)
    if dotenv_value is not None:
        return dotenv_value
    return default


def read_secret_file(path_value: str | None) -> str | None:
    if path_value is None:
        return None
    try:
        secret = Path(path_value).expanduser().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return secret or None


def default_api_key(
    *,
    config_lookup: Callable[[str, str], str],
    secret_reader: Callable[[str | None], str | None],
) -> str:
    direct_value = config_lookup("API_KEY", "")
    if direct_value:
        return direct_value
    secret_path = config_lookup("API_KEY_FILE", "")
    return secret_reader(secret_path) or ""


def default_embedding_model(*, config_lookup: Callable[[str, str], str]) -> str:
    return config_lookup("EMBEDDING_MODEL", "text-embedding-3-small")


def default_agent_base_url(*, config_lookup: Callable[[str, str], str]) -> str:
    host = config_lookup("API_HOST", "127.0.0.1")
    port = config_lookup("API_PORT", "8000")
    return f"http://{host}:{port}"
