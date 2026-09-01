#!/usr/bin/env python3
"""Persist a lightweight Session hook prompt counter and checkpoint marker."""

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Union


STATE_SCHEMA_VERSION = 1
DEFAULT_CHECKPOINT_INTERVAL = 15


class PromptCounterError(RuntimeError):
    """Raised when a prompt-counter state file cannot be safely used."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        Path(temporary_name).replace(path)
    except OSError as exc:
        raise PromptCounterError(f"Cannot persist prompt counter state: {path}") from exc
    finally:
        temporary = Path(temporary_name)
        if temporary.exists():
            temporary.unlink()


def _load_state(path: Path) -> Dict:
    if not path.exists():
        return {"schema_version": STATE_SCHEMA_VERSION, "count": 0, "updated_at": None}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PromptCounterError(f"Cannot read prompt counter state: {path}") from exc
    if not isinstance(state, dict) or state.get("schema_version") != STATE_SCHEMA_VERSION:
        raise PromptCounterError("Unsupported prompt counter state schema")
    count = state.get("count")
    if not isinstance(count, int) or count < 0:
        raise PromptCounterError("Prompt counter state has an invalid count")
    return state


def record_prompt(
    vault_path: Union[str, Path],
    checkpoint_interval: int = DEFAULT_CHECKPOINT_INTERVAL,
    now: Optional[str] = None,
) -> Dict:
    """Record one prompt and create an idempotent checkpoint every N prompts."""
    if not isinstance(checkpoint_interval, int) or checkpoint_interval <= 0:
        raise ValueError("checkpoint_interval must be a positive integer")

    vault = Path(vault_path)
    state_path = vault / ".claude" / "prompt-counter-state.json"
    state = _load_state(state_path)
    timestamp = now or _utc_now()
    count = state["count"] + 1
    checkpoint_due = count % checkpoint_interval == 0
    checkpoint_path = None

    if checkpoint_due:
        checkpoint_path = vault / ".claude" / "checkpoints" / f"prompt-{count:06d}.md"
        if not checkpoint_path.exists():
            _atomic_write_text(
                checkpoint_path,
                "# Prompt Checkpoint\n\n"
                f"- Prompt count: {count}\n"
                f"- Recorded at: {timestamp}\n"
                "- Review and update the current Daily note if a durable decision or open loop emerged.\n",
            )

    state.update(
        schema_version=STATE_SCHEMA_VERSION,
        count=count,
        updated_at=timestamp,
        last_checkpoint_at=timestamp if checkpoint_due else state.get("last_checkpoint_at"),
    )
    _atomic_write_text(state_path, json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    return {
        "count": count,
        "checkpoint_created": checkpoint_due,
        "checkpoint_path": str(checkpoint_path) if checkpoint_path else None,
        "state_path": str(state_path),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Record a Brain-Eleven prompt checkpoint")
    parser.add_argument("--vault", default=str(Path.home() / "Documents/Brain-Eleven"))
    parser.add_argument("--interval", type=int, default=DEFAULT_CHECKPOINT_INTERVAL)
    args = parser.parse_args(argv)

    result = record_prompt(args.vault, args.interval)
    if result["checkpoint_created"]:
        print(f"Prompt {result['count']} recorded; checkpoint created: {result['checkpoint_path']}")
    else:
        print(f"Prompt {result['count']} recorded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
