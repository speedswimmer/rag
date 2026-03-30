"""Document backup — creates tar.gz snapshots of the dokumente/ directory."""

import logging
import tarfile
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


def create_snapshot(docs_dir: Path, backup_dir: Path, keep_days: int = 30) -> Path:
    """Create a timestamped tar.gz of docs_dir, rotate backups older than keep_days."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_path = backup_dir / f"dokumente-{timestamp}.tar.gz"

    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(docs_dir, arcname="dokumente")

    logger.info("Snapshot created: %s", archive_path.name)
    _rotate(backup_dir, keep_days)
    return archive_path


def _rotate(backup_dir: Path, keep_days: int) -> None:
    """Delete snapshots older than keep_days days."""
    cutoff = datetime.now() - timedelta(days=keep_days)
    for f in backup_dir.glob("dokumente-*.tar.gz"):
        if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
            f.unlink()
            logger.info("Removed old backup: %s", f.name)


def get_last_backup(backup_dir: Path) -> dict | None:
    """Return info about the most recent backup, or None if none exist."""
    if not backup_dir.exists():
        return None
    files = sorted(backup_dir.glob("dokumente-*.tar.gz"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        return None
    f = files[0]
    return {
        "name": f.name,
        "size_kb": round(f.stat().st_size / 1024, 1),
        "mtime": f.stat().st_mtime,
        "count": len(files),
    }
