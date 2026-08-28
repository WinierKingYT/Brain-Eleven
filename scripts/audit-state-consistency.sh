#!/bin/bash
# scripts/audit-state-consistency.sh
# Brain-Eleven State Audit: Verify consistency across configuration files

set -e

VAULT_PATH="$HOME/Documents/Brain-Eleven"
CLAUDE_HOME="$HOME/.claude"
TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Audit results
ISSUES=0
WARNINGS=0
OK=0

print_header() {
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo -e "${BLUE}🔍 Brain-Eleven State Consistency Audit${NC}"
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo "Audit time: $TIMESTAMP"
    echo ""
}

check_ok() {
    echo -e "${GREEN}✓${NC} $1"
    ((OK++))
}

check_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
    ((WARNINGS++))
}

check_fail() {
    echo -e "${RED}❌${NC} $1"
    ((ISSUES++))
}

print_section() {
    echo ""
    echo -e "${BLUE}─── $1 ───${NC}"
}

# ============================================================================
# CHECK 1: Hook Configuration Consistency
# ============================================================================
print_section "1. Hook Configuration Consistency"

if [ ! -f "$CLAUDE_HOME/settings.json" ]; then
    check_fail "settings.json not found at $CLAUDE_HOME/settings.json"
else
    # Check autoSave setting
    AUTO_SAVE=$(grep -o '"autoSave":\s*[^,}]*' "$CLAUDE_HOME/settings.json" | grep -o 'true\|false' || echo "NOT_FOUND")

    if [ "$AUTO_SAVE" = "true" ]; then
        check_ok "settings.json: autoSave = true (hooks ENABLED)"
        HOOKS_ENABLED_SETTINGS=true
    else
        check_warn "settings.json: autoSave = $AUTO_SAVE (hooks may be DISABLED)"
        HOOKS_ENABLED_SETTINGS=false
    fi
fi

# Check CLAUDE.md statement
if [ ! -f "$VAULT_PATH/CLAUDE.md" ]; then
    check_fail "CLAUDE.md not found at $VAULT_PATH/CLAUDE.md"
else
    if grep -q "Hooks: Atlandı\|hooks.*skipped\|hooks.*disabled" "$VAULT_PATH/CLAUDE.md"; then
        check_warn "CLAUDE.md: Hooks marked as SKIPPED (contradicts settings.json?)"
        HOOKS_ENABLED_CLAUDE=false
    elif grep -q "Hooks.*aktif\|hooks.*enabled\|autoSave.*true" "$VAULT_PATH/CLAUDE.md"; then
        check_ok "CLAUDE.md: Hooks marked as ENABLED"
        HOOKS_ENABLED_CLAUDE=true
    else
        check_warn "CLAUDE.md: Hook status unclear"
    fi
fi

# Cross-check
if [ "$HOOKS_ENABLED_SETTINGS" != "$HOOKS_ENABLED_CLAUDE" ]; then
    check_fail "MISMATCH: settings.json and CLAUDE.md disagree on hook status"
    echo "   → settings.json: $HOOKS_ENABLED_SETTINGS"
    echo "   → CLAUDE.md: $HOOKS_ENABLED_CLAUDE"
    echo "   ACTION: Align both to 'enabled' state"
else
    if [ "$HOOKS_ENABLED_SETTINGS" = "true" ]; then
        check_ok "settings.json ↔ CLAUDE.md: Consistent (ENABLED)"
    else
        check_warn "settings.json ↔ CLAUDE.md: Consistent but DISABLED"
    fi
fi

# ============================================================================
# CHECK 2: Hook Files Existence
# ============================================================================
print_section "2. Hook Files"

HOOKS_DIR="$CLAUDE_HOME/hooks"
if [ ! -d "$HOOKS_DIR" ]; then
    check_fail "Hooks directory not found: $HOOKS_DIR"
else
    check_ok "Hooks directory exists: $HOOKS_DIR"

    # Required hooks
    REQUIRED_HOOKS=(
        "session-start.sh:SessionStart"
        "prompt-counter.sh:Every 15 prompts"
        "session-end.sh:SessionEnd"
        "pre-compact.sh:PreCompact"
    )

    for hook_info in "${REQUIRED_HOOKS[@]}"; do
        IFS=':' read -r hook_file hook_desc <<< "$hook_info"

        if [ -f "$HOOKS_DIR/$hook_file" ]; then
            check_ok "$hook_file ($hook_desc)"
        else
            check_fail "$hook_file ($hook_desc) — MISSING"
        fi
    done
fi

# ============================================================================
# CHECK 3: mem0 Configuration
# ============================================================================
print_section "3. mem0 Configuration"

MEM0_AUTH="$HOME/.mem0/auth.json"
MEM0_CONFIG_SETUP="$VAULT_PATH/docs/mem0-setup.md"

if [ -f "$MEM0_AUTH" ]; then
    check_ok "mem0 auth configured"
else
    check_warn "mem0 auth missing (status: planned/partial)"
    if [ -f "$MEM0_CONFIG_SETUP" ]; then
        if grep -q "Status: Hazırlanıyor\|Status: Planning" "$MEM0_CONFIG_SETUP"; then
            check_warn "mem0-setup.md indicates: 'Preparing (auth pending)'"
        fi
    fi
fi

# ============================================================================
# CHECK 4: Memory Freshness (Last Session)
# ============================================================================
print_section "4. Memory Freshness"

LAST_SESSION_FILE="$VAULT_PATH/🔮 Companion/Last Session.md"

if [ ! -f "$LAST_SESSION_FILE" ]; then
    check_fail "Last Session.md not found"
else
    check_ok "Last Session.md exists"

    # Check if it's been updated
    LAST_MODIFIED=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M" "$LAST_SESSION_FILE" 2>/dev/null || echo "N/A")

    if [ "$LAST_MODIFIED" = "N/A" ]; then
        check_warn "Could not determine last modification time"
    else
        check_ok "Last Session updated: $LAST_MODIFIED"

        # Check if it still says "Genesis"
        if grep -q "Session: 2026-08-27 (Genesis)" "$LAST_SESSION_FILE"; then
            check_warn "Last Session.md still at Genesis (no actual session memory yet)"
        fi
    fi
fi

# ============================================================================
# CHECK 5: Open Loops & Threads
# ============================================================================
print_section "5. Memory Structures"

OPEN_LOOPS_FILE="$VAULT_PATH/🔮 Companion/Açık Döngüler.md"
THREADS_FILE="$VAULT_PATH/🔮 Companion/Threads.md"
DAILY_FILE="$VAULT_PATH/🔮 Companion/Daily.md"

for file_info in "Open Loops:$OPEN_LOOPS_FILE" "Threads:$THREADS_FILE" "Daily:$DAILY_FILE"; do
    IFS=':' read -r file_name file_path <<< "$file_info"

    if [ -f "$file_path" ]; then
        LINE_COUNT=$(wc -l < "$file_path" | xargs)
        check_ok "$file_name exists ($LINE_COUNT lines)"
    else
        check_fail "$file_name not found: $file_path"
    fi
done

# ============================================================================
# CHECK 6: Vault Structure
# ============================================================================
print_section "6. Vault Structure"

# Check main directories
VAULT_DIRS=(
    "🔮 Companion:Companion space"
    "🧠 Brain-Eleven:Decision notes"
    "🗂️ Proje Notları:Project notes"
)

for dir_info in "${VAULT_DIRS[@]}"; do
    IFS=':' read -r dir_name dir_desc <<< "$dir_info"

    if [ -d "$VAULT_PATH/$dir_name" ]; then
        check_ok "$dir_name ($dir_desc)"
    else
        check_fail "$dir_name not found"
    fi
done

# ============================================================================
# SUMMARY
# ============================================================================
print_section "Summary"

TOTAL=$((OK + WARNINGS + ISSUES))
echo "Results: $TOTAL checks"
echo -e "  ${GREEN}✓ OK: $OK${NC}"
echo -e "  ${YELLOW}⚠ Warnings: $WARNINGS${NC}"
echo -e "  ${RED}❌ Issues: $ISSUES${NC}"

echo ""
if [ $ISSUES -eq 0 ]; then
    echo -e "${GREEN}✅ No critical issues found${NC}"
    if [ $WARNINGS -gt 0 ]; then
        echo -e "${YELLOW}⚠ But $WARNINGS warnings to review${NC}"
    fi
    EXIT_CODE=0
else
    echo -e "${RED}❌ $ISSUES critical issues need attention${NC}"
    EXIT_CODE=1
fi

echo ""
echo -e "${BLUE}────────────────────────────────────────${NC}"

# ============================================================================
# RECOMMENDATIONS
# ============================================================================
if [ $ISSUES -gt 0 ] || [ $WARNINGS -gt 0 ]; then
    echo ""
    echo -e "${YELLOW}Recommended next steps:${NC}"

    if [ "$HOOKS_ENABLED_SETTINGS" != "$HOOKS_ENABLED_CLAUDE" ]; then
        echo "1. Align hooks configuration:"
        echo "   • Set autoSave=true in settings.json"
        echo "   • Update CLAUDE.md to reflect enabled state"
    fi

    if [ ! -f "$HOOKS_DIR/session-start.sh" ]; then
        echo "2. Create missing session-start.sh hook"
    fi

    if [ ! -f "$HOME/.mem0/auth.json" ]; then
        echo "3. Configure mem0 authentication"
    fi

    if grep -q "Genesis" "$LAST_SESSION_FILE" 2>/dev/null; then
        echo "4. Update Last Session.md with actual session context"
    fi
fi

exit $EXIT_CODE
