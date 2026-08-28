#!/bin/bash
# Brain-Eleven SessionStart Hook
# Load context bootstrap from prior session + recent memories
# Called at: SessionStart event

set -e

VAULT_PATH="$HOME/Documents/Brain-Eleven"
SCRIPTS_DIR="$VAULT_PATH/scripts"
COMPANION_DIR="$VAULT_PATH/🔮 Companion"

echo "📚 Brain-Eleven SessionStart Bootstrap"
echo "========================================"

# Step 1: Check for prior session context
echo ""
echo "1️⃣  Loading prior session context..."

if [ -f "$COMPANION_DIR/Last Session.md" ]; then
    SESSION_SIZE=$(wc -l < "$COMPANION_DIR/Last Session.md")
    if [ "$SESSION_SIZE" -gt 10 ]; then
        echo "   ✅ Found prior session ($(grep -c '^-' "$COMPANION_DIR/Last Session.md" 2>/dev/null || echo '0') decisions/lessons)"
        head -3 "$COMPANION_DIR/Last Session.md" | sed 's/^/      /'
    fi
else
    echo "   ℹ️  No prior session (first session or clean start)"
fi

# Step 2: Load validated memories (if validator has run)
echo ""
echo "2️⃣  Loading validated memories..."

if [ -f "$VAULT_PATH/.claude/validated-memory.json" ]; then
    # Simple file-size check (more reliable than JSON parsing in bash)
    MEM_SIZE=$(wc -c < "$VAULT_PATH/.claude/validated-memory.json" 2>/dev/null || echo "0")
    if [ "$MEM_SIZE" -gt 1000 ]; then
        echo "   ✅ Memory store loaded ($(du -h "$VAULT_PATH/.claude/validated-memory.json" | cut -f1))"
    fi
else
    echo "   ℹ️  No validated memories yet (Memory Validator not run)"
fi

# Step 3: Load Open Loops
echo ""
echo "3️⃣  Loading open loops..."

if [ -f "$COMPANION_DIR/Open Loops.md" ]; then
    LOOPS=$(grep -c '^\- \[' "$COMPANION_DIR/Open Loops.md" 2>/dev/null || echo "0")
    echo "   📍 Open loops: $LOOPS"
    grep '^\- \[.' "$COMPANION_DIR/Open Loops.md" 2>/dev/null | head -3 | sed 's/^/      /'
fi

# Step 4: Display ready status
echo ""
echo "========================================"
echo "✅ SessionStart bootstrap complete"
echo ""
echo "Available:"
echo "  📖 Last Session (.../Last Session.md)"
echo "  🎯 Open Loops (.../Open Loops.md)"
echo "  💾 Memory Store (.claude/validated-memory.json)"
echo ""
echo "Next:"
echo "  - Review prior decisions and lessons"
echo "  - Check for superseded or resolved memories"
echo "  - Update Daily.md at session end"
echo ""
