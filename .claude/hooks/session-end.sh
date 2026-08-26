#!/bin/bash
# SessionEnd hook: Daily yazısını çekle, hafıza motoruna gönder

VAULT_DIR="${VAULT_DIR:-$HOME/Documents/Brain-Eleven}"
STATE_DIR="$VAULT_DIR/.claude/hooks/.state"
mkdir -p "$STATE_DIR"

TODAY=$(date +%Y-%m-%d)
DAILY_FILE="$VAULT_DIR/🔮 850-Companion/Daily/$TODAY.md"

# Daily dosyası varsa ve boş değilse, özet hazırla
if [ -f "$DAILY_FILE" ] && [ -s "$DAILY_FILE" ]; then
  echo "✓ Daily özeti hazırlanıyor: $TODAY"
  # Claude'a göndermek istiyorsan buraya özet prompt'u ekle
  # claude -p "Summarize $DAILY_FILE for memory"
  touch "$STATE_DIR/last-session-$TODAY"
else
  echo "Daily dosyası eksik veya boş"
fi
