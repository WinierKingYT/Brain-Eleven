#!/usr/bin/env bash
# Brain-Eleven SessionEnd hook: bounded capture hand-off only.
#
# PRE-02 intentionally keeps this convenience hook fast. It parses only the
# bounded hook event, resolves existing project identity read-only, and writes
# one durable local queue job. Transcript reading, extraction, validation,
# context compilation and all canonical writes happen outside this hook.

set -u

HOOK_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VAULT_PATH="${BRAIN_ELEVEN_VAULT:-${VAULT_DIR:-$(cd "$HOOK_DIR/../.." && pwd)}}"
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
QUEUE_SCRIPT="$VAULT_PATH/scripts/capture_queue.py"
PYTHON_BIN="${PYTHON:-python3}"

log() { printf '[Brain-Eleven SessionEnd] %s\n' "$1" >&2; }

if [ ! -f "$QUEUE_SCRIPT" ]; then
    log "capture queue is unavailable; no event was queued"
    exit 0
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    PYTHON_BIN="python"
fi
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    log "Python is unavailable; no event was queued"
    exit 0
fi

if ! PYTHONIOENCODING=utf-8 "$PYTHON_BIN" "$QUEUE_SCRIPT" enqueue-hook \
    --vault "$VAULT_PATH" \
    --event-type SESSION_END \
    --project-root "$PROJECT_ROOT" >/dev/null; then
    # Do not echo untrusted hook stdin, transcript locations, or prompt data.
    log "capture event was not queued; continuing safely"
    exit 0
fi

log "capture event queued"
exit 0
