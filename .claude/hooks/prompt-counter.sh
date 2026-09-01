#!/usr/bin/env bash
# Record a durable checkpoint marker every 15 submitted prompts.
# Hook failures must not interrupt the user's prompt flow.

set -u

HOOK_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VAULT_PATH="${BRAIN_ELEVEN_VAULT:-${VAULT_DIR:-$(cd "$HOOK_DIR/../.." && pwd)}}"
COUNTER_SCRIPT="$VAULT_PATH/scripts/prompt-counter.py"
PYTHON_BIN="${PYTHON:-python3}"

if [ ! -f "$COUNTER_SCRIPT" ]; then
    echo "ℹ️  Prompt counter unavailable; skipping checkpoint"
    exit 0
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    PYTHON_BIN="python"
fi

if ! PYTHONIOENCODING=utf-8 "$PYTHON_BIN" "$COUNTER_SCRIPT" --vault "$VAULT_PATH"; then
    echo "⚠️  Prompt counter failed; continuing without a checkpoint"
fi

exit 0
