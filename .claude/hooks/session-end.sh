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
PYTHON_NATIVE=0

log() { printf '[Brain-Eleven SessionEnd] %s\n' "$1" >&2; }

if [ ! -f "$QUEUE_SCRIPT" ]; then
    log "capture queue is unavailable; no event was queued"
    exit 0
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    case "$PYTHON_BIN" in
        [A-Za-z]:\\*)
            PYTHON_NATIVE=1
            _drive="${PYTHON_BIN:0:1}"
            _rest="${PYTHON_BIN:2}"
            _rest="${_rest//\\//}"
            if [ -f "/mnt/${_drive,,}${_rest}" ]; then
                PYTHON_BIN="/mnt/${_drive,,}${_rest}"
            elif [ -f "/${_drive,,}${_rest}" ]; then
                PYTHON_BIN="/${_drive,,}${_rest}"
            fi
            ;;
    esac
fi
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    PYTHON_BIN="python"
fi
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    log "Python is unavailable; no event was queued"
    exit 0
fi

VAULT_ARG="$VAULT_PATH"
PROJECT_ROOT_ARG="$PROJECT_ROOT"
if [ "$PYTHON_NATIVE" -eq 1 ]; then
    _native_path() {
        case "$1" in
            /mnt/[A-Za-z]/*)
                _drive="${1:5:1}"
                _tail="${1:6}"
                _tail="${_tail//\\//}"
                printf '%s:%s' "${_drive^^}" "$_tail"
                ;;
            *) printf '%s' "$1" ;;
        esac
    }
    VAULT_ARG="$(_native_path "$VAULT_PATH")"
    PROJECT_ROOT_ARG="$(_native_path "$PROJECT_ROOT")"
fi
QUEUE_SCRIPT_ARG="$VAULT_ARG/scripts/capture_queue.py"

if ! PYTHONIOENCODING=utf-8 "$PYTHON_BIN" "$QUEUE_SCRIPT_ARG" enqueue-hook \
    --vault "$VAULT_ARG" \
    --event-type SESSION_END \
    --project-root "$PROJECT_ROOT_ARG" >/dev/null; then
    # Do not echo untrusted hook stdin, transcript locations, or prompt data.
    log "capture event was not queued; continuing safely"
    exit 0
fi

log "capture event queued"
exit 0
