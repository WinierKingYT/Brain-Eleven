#!/bin/bash
# Brain-Eleven SessionEnd hook: run the structured pipeline contract.
#
# The hook itself remains best-effort so it never blocks a Claude session from
# ending. Its status messages are nevertheless derived from this invocation's
# run-result document, never from a stale artifact left by an earlier run.

set -e

HOOK_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BRAIN_ELEVEN_PATH="${BRAIN_ELEVEN_VAULT:-$(cd "$HOOK_DIR/../.." && pwd)}"
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
RUNNER_SCRIPT="$BRAIN_ELEVEN_PATH/scripts/session_pipeline.py"
RESULT_FILE="$BRAIN_ELEVEN_PATH/.claude/session-run-result.json"
HOOK_LOG="$BRAIN_ELEVEN_PATH/.claude/hook-execution.log"

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${BLUE}[Brain-Eleven SessionEnd]${NC} $1" >&2; }
log_ok() { echo -e "${GREEN}✓${NC} $1" >&2; }
log_warn() { echo -e "${YELLOW}⚠${NC} $1" >&2; }

if [ ! -d "$BRAIN_ELEVEN_PATH" ]; then
    log_warn "Brain-Eleven vault not found; no pipeline was run"
    exit 0
fi

if [ ! -f "$RUNNER_SCRIPT" ]; then
    log_warn "Session pipeline runner not found; no pipeline was run"
    exit 0
fi

log "Running lineage-aware session pipeline..."
if ! RUN_OUTPUT=$(PYTHONIOENCODING=utf-8 python3 "$RUNNER_SCRIPT" \
    --vault "$BRAIN_ELEVEN_PATH" \
    --project-root "$PROJECT_ROOT" \
    --python python3 2>&1); then
    log_warn "Pipeline runner failed before it could persist a run result"
    printf '%s\n' "$RUN_OUTPUT" >&2
    exit 0
fi

if ! PIPELINE_RUN_ID=$(PYTHONIOENCODING=utf-8 python3 - "$RUN_OUTPUT" <<'PYEOF'
import json
import sys

try:
    output = json.loads(sys.argv[1])
    run_id = output["run_id"]
except (IndexError, KeyError, TypeError, ValueError) as exc:
    print(f"invalid runner output: {exc}", file=sys.stderr)
    raise SystemExit(1)

if not isinstance(run_id, str) or not run_id:
    print("invalid runner output: run_id is missing", file=sys.stderr)
    raise SystemExit(1)

print(run_id)
PYEOF
); then
    log_warn "Pipeline runner returned no valid run identity; refusing any prior result"
    printf '%s\n' "$RUN_OUTPUT" >&2
    exit 0
fi

if [ ! -f "$RESULT_FILE" ]; then
    log_warn "Pipeline runner returned without a run result; treating all steps as unknown"
    exit 0
fi

SUMMARY=$(PYTHONIOENCODING=utf-8 python3 - "$RESULT_FILE" "$PIPELINE_RUN_ID" <<'PYEOF'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        result = json.load(handle)
    expected_run_id = sys.argv[2]
    run_id = result["run_id"]
    status = result["status"]
    steps = result["steps"]
    if run_id != expected_run_id:
        raise ValueError(
            f"result run_id {run_id!r} does not match runner run_id {expected_run_id!r}"
        )
    if status not in {"SUCCESS", "DEGRADED", "FAILED"}:
        raise ValueError(f"unknown pipeline status: {status!r}")
    if not isinstance(steps, list):
        raise TypeError("result steps must be a list")
except (OSError, ValueError, KeyError, TypeError) as exc:
    print(f"INVALID_RESULT\t{exc}")
    raise SystemExit(0)

print(f"RUN\t{run_id}\t{status}")
for step in steps:
    print(
        "STEP\t{step}\t{status}\t{exit_code}\t{fresh}\t{error}".format(
            step=step.get("step", "unknown"),
            status=step.get("status", "UNKNOWN"),
            exit_code=step.get("exit_code", ""),
            fresh=step.get("artifact_created_this_run", False),
            error=step.get("error") or "",
        )
    )
PYEOF
)

if [[ "$SUMMARY" == INVALID_RESULT* ]]; then
    log_warn "Run result is unreadable; no step is reported as successful"
    printf '%s\n' "$SUMMARY" >&2
    exit 0
fi

mkdir -p "$(dirname "$HOOK_LOG")"
printf '[SessionEnd] %s\n%s\n\n' "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "$SUMMARY" >> "$HOOK_LOG"

while IFS=$'\t' read -r record name status exit_code fresh error; do
    if [ "$record" = "RUN" ]; then
        RUN_ID="$name"
        PIPELINE_STATUS="$status"
        continue
    fi
    [ "$record" = "STEP" ] || continue
    if [ "$status" = "SUCCESS" ]; then
        log_ok "$name succeeded (fresh artifact: $fresh)"
    else
        log_warn "$name: $status${error:+ — $error}"
    fi
done <<< "$SUMMARY"

case "${PIPELINE_STATUS:-UNKNOWN}" in
    SUCCESS) log_ok "Session pipeline complete: $RUN_ID" ;;
    DEGRADED) log_warn "Session pipeline degraded: $RUN_ID (see session-run-result.json)" ;;
    FAILED) log_warn "Session pipeline failed safely: $RUN_ID (see session-run-result.json)" ;;
    *) log_warn "Session pipeline produced an unknown result state" ;;
esac

exit 0
