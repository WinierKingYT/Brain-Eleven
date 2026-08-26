#!/bin/bash
# PreCompact hook: Dersler + Kararlar'ı compile et, hafta özetini mem0'a gönder

VAULT_DIR="${VAULT_DIR:-$HOME/Documents/Brain-Eleven}"
STATE_DIR="$VAULT_DIR/.claude/hooks/.state"
mkdir -p "$STATE_DIR"

WEEK=$(date +%Y-W%V)
COMPILE_LOG="$STATE_DIR/compile.log"

echo "✓ Derlenme günlüğü güncelleniyor"

# Dersler sayısı
LESSON_COUNT=$(find "$VAULT_DIR/🗂️ Proje Notları/Dersler" -name "*.md" | wc -l)

# Kararlar sayısı
DECISION_COUNT=$(find "$VAULT_DIR/🗂️ Proje Notları/Kararlar" -name "*.md" | wc -l)

# Haftalık özet
SUMMARY="Week $WEEK: $LESSON_COUNT lessons, $DECISION_COUNT decisions compiled"
echo "[$WEEK] Compaction: $SUMMARY" >> "$COMPILE_LOG"

# mem0'a hafta özetini gönder (opsiyonel)
if command -v claude >/dev/null 2>&1; then
  (
    sleep 2
    claude -p "Add to mem0 (brain-eleven-core): $SUMMARY. Brain-Eleven weekly compilation: reviewed all lessons and strategic decisions." 2>/dev/null
  ) &
fi

echo "[$(date +%Y-%m-%d\ %H:%M:%S)] PreCompact: Compilation logged, $LESSON_COUNT + $DECISION_COUNT items" >> "$COMPILE_LOG"
