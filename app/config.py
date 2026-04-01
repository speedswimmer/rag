"""Central configuration — loaded from environment / .env file."""

import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()


def _get_version() -> str:
    """Read version from latest git tag (e.g. 'v0.8' -> '0.8')."""
    try:
        out = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out.lstrip("v")
    except Exception:
        return "dev"


APP_VERSION = _get_version()


@dataclass
class Config:
    # Paths
    base_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent)
    docs_dir: Path = field(default=None)
    chroma_dir: Path = field(default=None)
    index_meta_path: Path = field(default=None)
    backup_dir: Path = field(default=None)
    backup_keep_days: int = 7

    # Models
    embedding_model: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
    )
    llm_model: str = field(
        default_factory=lambda: os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")
    )

    # Flask
    secret_key: str = field(
        default_factory=lambda: os.getenv("SECRET_KEY", "change-me-in-production")
    )
    max_content_length: int = 50 * 1024 * 1024  # 50 MB

    # Upload
    allowed_extensions: frozenset = field(
        default_factory=lambda: frozenset({"pdf", "txt", "docx", "md"})
    )

    # RAG
    chunk_size: int = 1000
    chunk_overlap: int = 200
    retrieval_k: int = 10
    llm_max_tokens: int = 2048
    llm_temperature: float = 0.3

    def __post_init__(self):
        if self.docs_dir is None:
            self.docs_dir = self.base_dir / "dokumente"
        if self.chroma_dir is None:
            self.chroma_dir = self.base_dir / "chroma_db"
        if self.index_meta_path is None:
            self.index_meta_path = self.base_dir / "index_meta.json"
        if self.backup_dir is None:
            self.backup_dir = self.base_dir / "backups"

        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_dir.mkdir(parents=True, exist_ok=True)

        if self.secret_key == "change-me-in-production":
            logger.warning("SECRET_KEY ist nicht gesetzt — bitte in der .env-Datei konfigurieren")

    def allowed_file(self, filename: str) -> bool:
        return (
            "." in filename
            and filename.rsplit(".", 1)[1].lower() in self.allowed_extensions
        )
