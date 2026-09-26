"""Source-drift check for active memories (roadmap step 6).

A memory is captured from a transcript, which never changes. What goes stale
is the project it talks about: a record naming ``CLAUDE.md`` or
``scripts/worker.py`` can become wrong once that file changes. This module
finds active project memories that name a file in their project root and
flags them ``stale_candidate`` when that file changed after the memory was
written, or no longer exists.

The result is derived and non-canonical (``runtime/staleness.json``); the
memory store is only changed when a person retires a record through the
existing ``RESOLVE_EXISTING`` truth operation. "Still valid" is recorded as
an acknowledgement bound to the file's change time, so the flag returns if
the file changes again.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess

from .storage import RuntimeConfig, read_json, write_json, now

# Repository-relative file names as people write them in notes: optional
# directories, a name, and a known source/document extension.
_PATH = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)*[\w.-]+\.(?:py|md|json|jsonl|toml|js|ts|tsx|css|html|yml|yaml|sh|ps1|txt|cfg|ini))\b")


def _parse_time(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def referenced_paths(content):
    return sorted({match.strip('./') for match in _PATH.findall(content or '')})


def _file_changed_at(root, relative):
    """Last change time of a project file: its last commit, or mtime if uncommitted/not git."""
    path = root / relative
    if not path.is_file():
        return None
    committed = None
    try:
        output = subprocess.run(['git', '-C', str(root), 'log', '-1', '--format=%cI', '--', relative],
                                capture_output=True, text=True, timeout=5,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout.strip()
        committed = _parse_time(output)
    except (OSError, subprocess.SubprocessError):
        committed = None
    try:
        dirty = subprocess.run(['git', '-C', str(root), 'status', '--porcelain', '--', relative],
                               capture_output=True, text=True, timeout=5,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        dirty = ''
    if committed is None or dirty:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return committed


def _acks_path(vault):
    return RuntimeConfig(vault).root / 'staleness-acks.json'


def scan(vault):
    """Return and persist the stale_candidate list for all active project memories."""
    from brain_eleven.memory import MemoryStore
    from brain_eleven.projects.registry import ProjectRegistry

    roots = {p['project_id']: Path(str(p.get('root', ''))) for p in ProjectRegistry(vault).list_projects()}
    acks = read_json(_acks_path(vault), {}) or {}
    stale = []
    checked = 0
    for memory in MemoryStore(vault).load()['validated_memory']:
        if str(memory.get('status') or 'active') != 'active':
            continue
        root = roots.get(memory.get('project_id'))
        written = _parse_time(memory.get('timestamp'))
        if root is None or not root.is_dir() or written is None:
            continue
        for relative in referenced_paths(memory.get('content', '')):
            # Only names that resolve inside this project count; a bare
            # "notes.md" that never existed here is not evidence of drift.
            candidate = root / relative
            if not candidate.exists() and not (root / relative.split('/')[0]).exists():
                continue
            checked += 1
            changed = _file_changed_at(root, relative)
            if changed is None:
                reason, changed_at = 'SOURCE_MISSING', None
            elif changed > written:
                reason, changed_at = 'SOURCE_CHANGED', changed.isoformat()
            else:
                continue
            ack = acks.get(memory['memory_id'], {}).get(relative)
            if ack is not None and ack == changed_at:
                continue
            stale.append({'memory_id': memory['memory_id'], 'project_id': memory.get('project_id'),
                          'content': memory.get('content', ''), 'path': relative, 'reason': reason,
                          'memory_written_at': memory.get('timestamp'), 'source_changed_at': changed_at})
    result = {'scanned_at': now(), 'references_checked': checked, 'stale_candidates': stale}
    write_json(RuntimeConfig(vault).root / 'staleness.json', result)
    return result


def acknowledge(vault, memory_id, path):
    """Record that a person confirmed the memory is still valid for the file's current version."""
    current = next((x for x in scan(vault)['stale_candidates']
                    if x['memory_id'] == memory_id and x['path'] == path), None)
    if current is None:
        raise ValueError('Not a current stale candidate')
    acks = read_json(_acks_path(vault), {}) or {}
    acks.setdefault(memory_id, {})[path] = current['source_changed_at']
    write_json(_acks_path(vault), acks)
    return {'status': 'ACKNOWLEDGED', 'memory_id': memory_id, 'path': path}


def retire(vault, memory_id, note=''):
    """Resolve a stale memory through the truth engine's RESOLVE_EXISTING operation."""
    from brain_eleven.memory import MemoryStore
    from brain_eleven.memory.truth import MemoryTruthEngine

    memory = next((x for x in MemoryStore(vault).load()['validated_memory']
                   if x.get('memory_id') == memory_id and str(x.get('status') or 'active') == 'active'), None)
    if memory is None:
        raise ValueError('Active memory not found')
    candidate = {'candidate_id': 'stale_' + memory_id, 'content': memory['content'],
                 'memory_type': memory.get('type') or 'observation', 'scope': memory.get('scope') or 'project',
                 'project_id': memory.get('project_id', ''), 'operation': 'RESOLVE_EXISTING',
                 'target_memory_id': memory_id, 'resolved_by': 'human-staleness-review',
                 'note': (note or 'Source changed; retired in staleness review.')[:280]}
    result = MemoryTruthEngine(vault).process([candidate], commit=True).to_dict()
    after = next((x for x in MemoryStore(vault).load()['validated_memory'] if x.get('memory_id') == memory_id), {})
    if str(after.get('status')) != 'resolved':
        raise ValueError('Memory was not retired: ' + str(result.get('status')))
    return {'status': 'RETIRED', 'memory_id': memory_id}
