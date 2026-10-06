"""Study a project or a GitHub repository for durable decisions and lessons.

Owner decision 2026-10-06: Claude reads a project's documents (the /study
command), the owner approves the extracted list once, and the items are
written as memories of that project with their source. Each study records the
commit it saw, so the next run only looks at what changed since.

A GitHub repository is cloned read-only into the runtime cache and registered
as its own project labelled ``ext:<owner>/<repo>`` without capture, so its
items reach other projects only as labelled cross-project references.
"""

from __future__ import annotations

import re
import shutil
import subprocess  # nosec B404 - fixed git argv, no shell
from datetime import datetime, timezone
from pathlib import Path

STUDIES_FILE = 'studies.json'
CACHE_DIR = 'study-cache'
CLONE_DEPTH = 200
MAX_COMMITS_LISTED = 50
MAX_TEXT_CHARS = 1200
ITEM_TYPES = frozenset({'decision', 'lesson'})
DOC_SUFFIXES = ('.md', '.markdown', '.rst', '.txt', '.adoc')
_GITHUB = re.compile(r'^(?:https://github\.com/|git@github\.com:)([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$')


def _runtime_root(vault):
    from .storage import RuntimeConfig
    return RuntimeConfig(vault).root


def resolve_target(vault, target):
    """Describe a study target: an enrolled project folder or a GitHub URL."""
    match = _GITHUB.match(str(target).strip())
    if match:
        owner, repo = match.groups()
        slug = f'{owner}/{repo}'.lower()
        return {'key': f'github:{slug}', 'label': f'ext:{slug}', 'external': True,
                'url': f'https://github.com/{owner}/{repo}.git',
                'root': _runtime_root(vault) / CACHE_DIR / f'{owner}__{repo}'.lower()}
    from brain_eleven.projects.registry import ProjectRegistry
    root = Path(target).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f'Not a folder or GitHub URL: {target}')
    # A sub-folder of an enrolled project (e.g. the git repo inside a vault
    # folder) belongs to that project; its own folder is what gets read.
    registry = ProjectRegistry(vault)
    project = next((found for found in (registry.resolve(folder) for folder in (root, *root.parents)) if found), None)
    if project is None:
        raise ValueError('Project is not enrolled; run: python -m brain_eleven project add <folder>')
    return {'key': f"project:{project['project_id']}", 'label': project['project_label'], 'external': False,
            'root': root, 'project_id': project['project_id']}


def _git(root, *args, timeout=120):
    git = shutil.which('git')
    if not git:
        raise ValueError('git is not installed')
    result = subprocess.run([git, '-C', str(root), *args], capture_output=True, text=True,  # nosec B603
                            encoding='utf-8', errors='replace', timeout=timeout)
    if result.returncode != 0:
        raise ValueError(f"git {args[0]} failed: {result.stderr.strip()[:200]}")
    return result.stdout


def _sync_clone(info):
    """Clone or refresh the read-only copy of an external repository."""
    root = info['root']
    if not (root / '.git').is_dir():
        root.parent.mkdir(parents=True, exist_ok=True)
        _git(root.parent, 'clone', '--depth', str(CLONE_DEPTH), '--no-tags', info['url'], str(root), timeout=600)
        return
    _git(root, 'fetch', '--depth', str(CLONE_DEPTH), '--no-tags', 'origin', 'HEAD', timeout=600)
    _git(root, 'checkout', '--detach', '--force', 'FETCH_HEAD')


def _studies(vault):
    from .storage import read_json
    document = read_json(_runtime_root(vault) / STUDIES_FILE, {}) or {}
    return dict(document.get('studies') or {}) if isinstance(document, dict) else {}


def status(vault, target, *, sync=True):
    """What to read: FULL (never studied), INCREMENTAL (changed docs since), or UP_TO_DATE."""
    info = resolve_target(vault, target)
    if info['external'] and sync:
        _sync_clone(info)
    root = info['root']
    head = None
    if (root / '.git').exists():
        head = _git(root, 'rev-parse', 'HEAD').strip()
    last = _studies(vault).get(info['key']) or {}
    report = {'target': info['key'], 'label': info['label'], 'root': str(root), 'external': info['external'],
              'head': head, 'last_commit': last.get('commit'), 'last_at': last.get('at'),
              'mode': 'FULL', 'changed_docs': [], 'commits': []}
    if not last.get('commit') or not head:
        return report
    if last['commit'] == head:
        report['mode'] = 'UP_TO_DATE'
        return report
    try:
        _git(root, 'cat-file', '-e', f"{last['commit']}^{{commit}}")
    except ValueError:
        return report  # history rewritten or beyond the shallow clone: study fully again
    span = f"{last['commit']}..{head}"
    changed = [line for line in _git(root, 'diff', '--name-only', span).splitlines() if line.strip()]
    report['mode'] = 'INCREMENTAL'
    report['changed_docs'] = [path for path in changed if path.lower().endswith(DOC_SUFFIXES)]
    report['changed_files'] = len(changed)
    report['commits'] = _git(root, 'log', '--oneline', f'-{MAX_COMMITS_LISTED}', span).splitlines()
    return report


def _validate(items):
    if not isinstance(items, list) or not items:
        raise ValueError('Items must be a non-empty list')
    cleaned = []
    for item in items:
        if not isinstance(item, dict) or item.get('type') not in ITEM_TYPES:
            raise ValueError("Each item needs type 'decision' or 'lesson'")
        text = ' '.join(str(item.get('text') or '').split())
        source = ' '.join(str(item.get('source') or '').split())
        if not text or len(text) > MAX_TEXT_CHARS or not source:
            raise ValueError('Each item needs a text (at most 1200 characters) and a source')
        cleaned.append({'type': item['type'], 'text': text, 'source': source[:200]})
    return cleaned


def write(vault, target, items, *, commit=None):
    """Write owner-approved items as memories of the target project and record the study."""
    from brain_eleven.memory.capture import remember
    from brain_eleven.projects.registry import ProjectRegistry

    cleaned = _validate(items)
    info = resolve_target(vault, target)
    if info['external']:
        if not info['root'].is_dir():
            raise ValueError('Run study status first: the repository is not cloned yet')
        # Registered so its memories have a project; never added to the capture scope.
        project = ProjectRegistry(vault).register(info['root'], project_label=info['label'])
        info['project_id'] = project['project_id']
    written, failed = [], []
    for item in cleaned:
        content = f"{item['text']} (kaynak: {info['label']} {item['source']})"
        result = remember(item['type'], content, vault_path=vault, project_root=info['root'],
                          scope='project', project_id=info['project_id'], project=info['label'])
        ok = isinstance(result, dict) and result.get('status') in {'created', 'duplicate_returned_existing'}
        (written if ok else failed).append(item['source'])
    _record(vault, info, commit, len(written))
    return {'target': info['key'], 'project_id': info['project_id'], 'written': len(written), 'failed': failed}


def mark(vault, target, *, commit):
    """Record that the target was studied up to ``commit`` without writing items."""
    if not commit:
        raise ValueError('mark needs --commit')
    info = resolve_target(vault, target)
    if info['external']:
        from brain_eleven.projects.registry import ProjectRegistry
        if not info['root'].is_dir():
            raise ValueError('Run study status first: the repository is not cloned yet')
        info['project_id'] = ProjectRegistry(vault).register(info['root'], project_label=info['label'])['project_id']
    _record(vault, info, commit, 0)
    return {'target': info['key'], 'commit': commit}


def _record(vault, info, commit, written):
    from .storage import runtime_file_lock, write_json
    path = _runtime_root(vault) / STUDIES_FILE
    with runtime_file_lock(path):
        studies = _studies(vault)
        previous = studies.get(info['key']) or {}
        studies[info['key']] = {'commit': commit or previous.get('commit'),
                                'at': datetime.now(timezone.utc).isoformat(), 'label': info['label'],
                                'project_id': info['project_id'],
                                'written': int(previous.get('written') or 0) + written}
        write_json(path, {'studies': studies})
