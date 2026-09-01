"""Ensure repository hooks locate their vault without a host-specific HOME path."""

from pathlib import Path


ROOT = Path(__file__).parent.parent
HOOKS = ROOT / ".claude" / "hooks"


def test_local_hooks_resolve_vault_from_their_own_location():
    for name in ("session-start.sh", "session-end.sh", "pre-compact.sh", "prompt-counter.sh"):
        hook = (HOOKS / name).read_text(encoding="utf-8")
        assert 'BASH_SOURCE[0]' in hook
        assert 'cd "$HOOK_DIR/../.."' in hook
        assert '$HOME/Documents/Brain-Eleven' not in hook
