#!/bin/bash
# .claude/hooks/session-end.sh
# Brain-Eleven Session End: Extract memory from Daily + Validate + Bootstrap
#
# Pipeline: Daily.md → Memory Compiler → Memory Validator → context-bootstrap.json
# Ready for: SessionStart hook to load and display

set -e

BRAIN_ELEVEN_PATH="${HOME}/Documents/Brain-Eleven"
TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")

# Colors
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    echo -e "${BLUE}[Brain-Eleven SessionEnd]${NC} $1" >&2
}

log_ok() {
    echo -e "${GREEN}✓${NC} $1" >&2
}

log_warn() {
    echo -e "${YELLOW}⚠${NC} $1" >&2
}

# ============================================================================
# Verify vault exists
# ============================================================================
if [ ! -d "$BRAIN_ELEVEN_PATH" ]; then
    log_warn "Brain-Eleven vault not found"
    exit 0
fi

log "Starting session end extraction..."

# ============================================================================
# Step 1: Memory Compiler
# ============================================================================
COMPILER_SCRIPT="${BRAIN_ELEVEN_PATH}/scripts/memory-compiler.py"
COMPILED_JSON="${BRAIN_ELEVEN_PATH}/.claude/compiled-memory.json"

if [ -f "$COMPILER_SCRIPT" ]; then
    log "Running Memory Compiler..."
    PYTHONIOENCODING=utf-8 python3 "$COMPILER_SCRIPT" > /dev/null 2>&1 || true

    if [ -f "$COMPILED_JSON" ]; then
        log_ok "Memory Compiler complete"
        CANDIDATE_COUNT=$(grep -c '"type"' "$COMPILED_JSON" 2>/dev/null || echo "0")
        log "  → $CANDIDATE_COUNT candidates extracted"
    else
        log_warn "Compiler output missing"
    fi
else
    log_warn "Memory Compiler script not found"
fi

# ============================================================================
# Step 2: Memory Validator
# ============================================================================
VALIDATOR_SCRIPT="${BRAIN_ELEVEN_PATH}/scripts/memory-validator.py"
VALIDATED_JSON="${BRAIN_ELEVEN_PATH}/.claude/validated-memory.json"

if [ -f "$VALIDATOR_SCRIPT" ]; then
    log "Running Memory Validator..."
    PYTHONIOENCODING=utf-8 python3 "$VALIDATOR_SCRIPT" > /dev/null 2>&1 || true

    if [ -f "$VALIDATED_JSON" ]; then
        log_ok "Memory Validator complete"
        APPROVED=$(grep -c '"is_approved": true' "$VALIDATED_JSON" 2>/dev/null || echo "0")
        log "  → $APPROVED memories approved"
    else
        log_warn "Validator output missing"
    fi
else
    log_warn "Memory Validator script not found"
fi

# ============================================================================
# Step 3: Context Compiler (bootstrap for next session)
# ============================================================================
CONTEXT_COMPILER="${BRAIN_ELEVEN_PATH}/scripts/context-compiler.py"
CONTEXT_BOOTSTRAP="${BRAIN_ELEVEN_PATH}/.claude/context-bootstrap.json"

if [ -f "$CONTEXT_COMPILER" ]; then
    log "Compiling context bootstrap..."
    PYTHONIOENCODING=utf-8 python3 "$CONTEXT_COMPILER" > /dev/null 2>&1 || true

    if [ -f "$CONTEXT_BOOTSTRAP" ]; then
        log_ok "Context bootstrap ready"
    else
        log_warn "Context bootstrap not generated"
    fi
else
    log_warn "Context Compiler script not found"
fi

# ============================================================================
# Step 4: Log session end
# ============================================================================
HOOK_LOG="${BRAIN_ELEVEN_PATH}/.claude/hook-execution.log"
mkdir -p "$(dirname "$HOOK_LOG")"

cat >> "$HOOK_LOG" <<EOF
[SessionEnd] $TIMESTAMP
- Memory Compiler: $([ -f "$COMPILED_JSON" ] && echo "OK ($CANDIDATE_COUNT candidates)" || echo "FAILED")
- Memory Validator: $([ -f "$VALIDATED_JSON" ] && echo "OK ($APPROVED approved)" || echo "FAILED")
- Context Bootstrap: $([ -f "$CONTEXT_BOOTSTRAP" ] && echo "OK" || echo "FAILED")
- Ready for: SessionStart

EOF

log_ok "Session end processing complete"

echo ""
echo "=== Session End Summary ==="
echo ""
echo "✓ Memory extracted: $CANDIDATE_COUNT candidates"
echo "✓ Memory validated: $APPROVED approved"
echo "✓ Context compiled: ready for next session"
echo ""
echo "Next session will load bootstrap automatically."
echo ""

exit 0
