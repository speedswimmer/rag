"""Persistent app settings stored in settings.json (user-editable via Admin UI)."""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_SETTINGS_PATH = Path(__file__).parent.parent / "settings.json"


def get_app_name() -> str:
    """Return app name: settings.json → APP_NAME env var → default."""
    name = _load().get("app_name", "").strip()
    if name:
        return name
    return os.getenv("APP_NAME", "RAG System")


def save_app_name(name: str) -> None:
    settings = _load()
    settings["app_name"] = name.strip()
    _save(settings)
    logger.info("App name updated to: %s", name)


def _load() -> dict:
    try:
        with open(_SETTINGS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(settings: dict) -> None:
    with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
