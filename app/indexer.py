"""Smart indexing — tracks file hashes/mtime to avoid unnecessary rebuilds."""

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Config

logger = logging.getLogger(__name__)


class IndexManager:
    def __init__(self, config: "Config"):
        self.config = config
        self._meta: dict = self._load_meta()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_changes(self) -> bool:
        """Return True if any document was added, removed, or modified."""
        current_files = self._scan_docs()

        # Detect removals
        stored_paths = set(self._meta.keys())
        current_paths = set(current_files.keys())
        if stored_paths != current_paths:
            logger.info(
                "Index change: files added/removed (stored=%d, current=%d)",
                len(stored_paths),
                len(current_paths),
            )
            return True

        # Detect modifications
        for path, info in current_files.items():
            stored = self._meta.get(path)
            if stored is None:
                return True
            # Fast path: size + mtime match → skip SHA-256
            if (
                stored.get("size") == info["size"]
                and stored.get("mtime") == info["mtime"]
            ):
                continue
            # Slow path: compute hash
            if self._sha256(Path(path)) != stored.get("sha256"):
                logger.info("Index change: %s modified", path)
                return True

        return False

    def update_meta(self) -> None:
        """Recompute and persist metadata for all current documents."""
        current_files = self._scan_docs()
        new_meta: dict = {}
        for path, info in current_files.items():
            new_meta[path] = {
                "size": info["size"],
                "mtime": info["mtime"],
                "sha256": self._sha256(Path(path)),
            }
        self._meta = new_meta
        self._save_meta()
        logger.info("Index metadata updated (%d files)", len(new_meta))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _scan_docs(self) -> dict:
        """Return {str(path): {size, mtime}} for every supported document."""
        result = {}
        for ext in self.config.allowed_extensions:
            for p in self.config.docs_dir.glob(f"**/*.{ext}"):
                stat = p.stat()
                result[str(p)] = {
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                }
        return result

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def _load_meta(self) -> dict:
        try:
            with open(self.config.index_meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_meta(self) -> None:
        with open(self.config.index_meta_path, "w", encoding="utf-8") as f:
            json.dump(self._meta, f, indent=2)
