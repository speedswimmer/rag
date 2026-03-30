#!/usr/bin/env python3
"""Standalone backup script — run via cron to create daily snapshots.

Cron example (daily at 02:00):
    0 2 * * * /home/jarvis/rag/venv/bin/python /home/jarvis/rag/backup_cron.py >> /home/jarvis/rag/backup.log 2>&1
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.backup import create_snapshot
from app.config import Config

cfg = Config()
path = create_snapshot(cfg.docs_dir, cfg.backup_dir, cfg.backup_keep_days)
print(f"Backup created: {path}")
