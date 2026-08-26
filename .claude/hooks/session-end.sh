#!/bin/bash
# SessionEnd hook: Daily yazısını mem0'a gönder

VAULT_DIR="${VAULT_DIR:-$HOME/Documents/Brain-Eleven}"
STATE_DIR="$VAULT_DIR/.claude/hooks/.state"
mkdir -p "$STATE_DIR"

TODAY=$(date +%Y-%m-%d)
DAILY_FILE="$VAULT_DIR/🔮 850-Companion/Daily/$TODAY.md"

# Daily dosyası varsa ve boş değilse
if [ -f "$DAILY_FILE" ] && [ -s "$DAILY_FILE" ]; then
  echo "✓ Daily özeti hazırlanıyor: $TODAY"

  # Daily içeriğini oku (frontmatter'ı atla)
  DAILY_TEXT=$(sed '1,/^---$/d; 1,/^---$/d' "$DAILY_FILE" | sed '/^$/d' | head -c 500)

  # mem0'a gönder (arka planda)
  if command -v claude >/dev/null 2>&1; then
    (
      sleep 1
      claude -p "Add to mem0 (brain-eleven-core scope): Daily summary for $TODAY: $DAILY_TEXT" 2>/dev/null
    ) &
    touch "$STATE_DIR/last-session-$TODAY"
    echo "[$(date +%Y-%m-%d\ %H:%M:%S)] SessionEnd: Daily queued for mem0" >> "$STATE_DIR/session-end.log"
  else
    echo "claude CLI not found, marking session only"
    touch "$STATE_DIR/last-session-$TODAY"
  fi
else
  echo "⚠ Daily dosyası eksik veya boş: $DAILY_FILE"
fi
