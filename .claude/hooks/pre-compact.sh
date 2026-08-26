#!/bin/bash
# PreCompact hook: Derleme günlüğünü güncelle

VAULT_DIR="${VAULT_DIR:-$HOME/Documents/Brain-Eleven}"

# Haftalık özet: dersler + kararlar + thread'ler
echo "✓ Derlenme günlüğü güncelleniyor"

# Bu blok çok spesifik olabilir - şimdilik log tutal
echo "[$(date +%Y-%m-%d)] Compaction: Derler + Kararlar + Threads" >> "$VAULT_DIR/.claude/hooks/.state/compile.log"
