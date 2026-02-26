"""
Audit & Replay Layer — Full event logging.

Every AI action is explainable and auditable.

Logs every step:
  1. Original prompt
  2. Input guard decision
  3. LLM output
  4. Proposed action(s)
  5. Policy evaluation result(s)
  6. Execution result

Storage: append-only JSON-lines (.jsonl) file.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.schemas.action import AuditEvent

logger = logging.getLogger(__name__)

DEFAULT_AUDIT_DIR = Path(os.getenv("GUARDRAIL_AUDIT_DIR", "audit_logs"))


class AuditLogger:
    """
    Append-only audit event logger.

    Writes structured JSON-lines to a file per day.
    Every event is immutable once written.
    """

    def __init__(self, audit_dir: Path = DEFAULT_AUDIT_DIR) -> None:
        self._audit_dir = audit_dir
        self._audit_dir.mkdir(parents=True, exist_ok=True)

    def _get_log_path(self) -> Path:
        """Get the log file path for today."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._audit_dir / f"audit_{today}.jsonl"

    def log_event(self, event: AuditEvent) -> None:
        """Append one audit event to the log."""
        log_path = self._get_log_path()
        try:
            line = event.model_dump_json() + "\n"
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line)
            logger.debug(
                "Audit event logged: session=%s request=%s",
                event.session_id, event.request_id,
            )
        except Exception:
            logger.exception("Failed to write audit event")

    def get_session_trail(self, session_id: str) -> list[AuditEvent]:
        """
        Retrieve all audit events for a session.

        Scans all log files (may be slow for large histories).
        """
        events: list[AuditEvent] = []
        if not self._audit_dir.exists():
            return events

        for log_file in sorted(self._audit_dir.glob("audit_*.jsonl")):
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            if data.get("session_id") == session_id:
                                events.append(AuditEvent(**data))
                        except (json.JSONDecodeError, TypeError, ValueError):
                            continue
            except Exception:
                logger.exception("Failed to read audit file: %s", log_file)

        return events

    def get_recent_events(self, limit: int = 50) -> list[AuditEvent]:
        """Get the most recent audit events across all sessions."""
        events: list[AuditEvent] = []
        if not self._audit_dir.exists():
            return events

        # Read from newest file
        log_files = sorted(self._audit_dir.glob("audit_*.jsonl"), reverse=True)
        for log_file in log_files:
            if len(events) >= limit:
                break
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                for line in reversed(lines):
                    if len(events) >= limit:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        events.append(AuditEvent(**data))
                    except (json.JSONDecodeError, TypeError, ValueError):
                        continue
            except Exception:
                logger.exception("Failed to read audit file: %s", log_file)

        return events

    def get_stats(self) -> dict[str, Any]:
        """Get audit log statistics."""
        if not self._audit_dir.exists():
            return {"total_files": 0, "total_events": 0}

        log_files = list(self._audit_dir.glob("audit_*.jsonl"))
        total_events = 0
        for log_file in log_files:
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    total_events += sum(1 for line in f if line.strip())
            except Exception:
                continue

        return {
            "total_files": len(log_files),
            "total_events": total_events,
            "audit_dir": str(self._audit_dir),
        }
