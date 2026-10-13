"""Recorded Python statistical-tool calls; no R subprocess or LLM arithmetic."""
from __future__ import annotations

import json
from pathlib import Path
import re
import uuid

from . import settings
from .tools import StatToolError, execute


def run_stat_tool(task: str, request: dict, tag: str) -> dict:
    """Execute one read-only tool call and retain immutable input/output JSON.

    Unique filenames also avoid collisions when diagnostic tasks run in parallel.
    Expected data problems return a status; unexpected tool failures raise
    StatToolError and have an error result in the audit directory.
    """
    io_dir = Path(settings.OUTPUT_DIR) / "stat_io"
    safe_tag = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(tag))[:100] or "request"
    safe_task = re.sub(r"[^A-Za-z0-9_-]+", "_", str(task))[:40]
    stem = f"{safe_tag}_{safe_task}_{uuid.uuid4().hex[:12]}"
    try:
        serialized = json.dumps(request, indent=2, ensure_ascii=False, allow_nan=False)
        io_dir.mkdir(parents=True, exist_ok=True)
        (io_dir / f"{stem}_request.json").write_text(serialized, encoding="utf-8")
    except (OSError, ValueError, TypeError) as error:
        raise StatToolError(f"Cannot record strict-JSON statistical request: {error}") from error
    result_path = io_dir / f"{stem}_result.json"
    try:
        result = execute(task, request)
    except Exception as error:
        result_path.write_text(json.dumps({"status": "tool_error", "task": task, "reason": str(error)},
                                         indent=2, allow_nan=False), encoding="utf-8")
        if isinstance(error, StatToolError):
            raise
        raise StatToolError(f"Statistical task {task!r} failed: {error}") from error
    try:
        result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    except (OSError, ValueError, TypeError) as error:
        raise StatToolError(f"Cannot record strict-JSON statistical result: {error}") from error
    return result
