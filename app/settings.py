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


_DEFAULT_SYSTEM_PROMPT = (
    "Du bist ein hilfreicher Assistent, der Fragen ausschließlich anhand der "
    "bereitgestellten Dokumente beantwortet.\n\n"
    "Antworte immer in derselben Sprache, in der die Frage gestellt wurde.\n\n"
    "Beginne deine Antwort NIE mit Formulierungen wie 'Basierend auf', "
    "'Laut den Dokumenten', 'Den bereitgestellten Informationen zufolge', "
    "'Aus den Unterlagen', 'Gemäß' oder ähnlichen einleitenden Floskeln. "
    "Beantworte die Frage direkt, als würdest du das Wissen einfach kennen. "
    "Falls die Antwort nicht im Kontext enthalten ist, teile das dem Nutzer klar mit."
)


def get_system_prompt() -> str:
    """Return system prompt: settings.json → default."""
    prompt = _load().get("system_prompt", "").strip()
    return prompt if prompt else _DEFAULT_SYSTEM_PROMPT


def save_system_prompt(prompt: str) -> None:
    settings = _load()
    settings["system_prompt"] = prompt.strip()
    _save(settings)
    logger.info("System prompt updated (%d chars)", len(prompt.strip()))


def _load() -> dict:
    try:
        with open(_SETTINGS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(settings: dict) -> None:
    with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
