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

import os
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
        if any(name in {'.', '..'} or name.endswith('.') or name.startswith('-') for name in (owner, repo)):
            raise ValueError(f'Not a valid GitHub repository: {target}')
        slug = f'{owner}/{repo}'.lower()
        return {'key': f'github:{slug}', 'label': f'ext:{slug}', 'external': True,
                'url': f'https://github.com/{owner}/{repo}.git',
                # '+' cannot occur in GitHub names, so owner/repo map to one folder.
                'root': _runtime_root(vault) / CACHE_DIR / f'{owner}+{repo}'.lower()}
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
    # project_root is the enrolled folder; when the target is a sub-folder the
    # owner is shown that attribution before anything is written (review 2026-10-06).
    return {'key': f"project:{project['project_id']}", 'label': project['project_label'], 'external': False,
            'root': root, 'project_id': project['project_id'], 'project_root': Path(project['root'])}


# A studied repo is untrusted: its own config must not run anything (fsmonitor,
# external diff or textconv drivers, hooks, credential prompts).
_SAFE_GIT = ('-c', 'core.fsmonitor=false', '-c', f'core.hooksPath={os.devnull}', '-c', 'diff.external=',
             '-c', 'core.sshCommand=', '-c', 'protocol.file.allow=never')
SHA = re.compile(r'^[0-9a-f]{40}$')


def _git(root, *args, timeout=120):
    git = shutil.which('git')
    if not git:
        raise ValueError('git is not installed')
    env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_ASKPASS': ''}
    try:
        result = subprocess.run([git, *_SAFE_GIT, '-C', str(root), *args], capture_output=True, text=True,  # nosec B603
                                encoding='utf-8', errors='replace', timeout=timeout, env=env)
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f'git {args[0]} timed out') from exc
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
    if not info['external'] and Path(info['project_root']).resolve() != Path(root).resolve():
        report['project_root'] = str(info['project_root'])  # a sub-folder: show the owner this attribution
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
    changed = [line for line in _git(root, 'diff', '--no-ext-diff', '--no-textconv', '--name-only', span, '--').splitlines()
               if line.strip()]
    report['mode'] = 'INCREMENTAL'
    report['changed_docs'] = [path for path in changed if path.lower().endswith(DOC_SUFFIXES)]
    report['changed_files'] = len(changed)
    report['commits'] = _git(root, 'log', '--no-decorate', '--oneline', f'-{MAX_COMMITS_LISTED}', span, '--').splitlines()
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
    _check_commit(commit, required=False)
    info = resolve_target(vault, target)
    if info['external']:
        if not info['root'].is_dir():
            raise ValueError('Run study status first: the repository is not cloned yet')
        # Registered so its memories have a project; never added to the capture scope.
        project = ProjectRegistry(vault).register(info['root'], project_label=info['label'])
        info['project_id'] = project['project_id']
        info['project_root'] = info['root']
    written, failed = [], []
    for item in cleaned:
        content = f"{item['text']} (kaynak: {info['label']} {item['source']})"
        result = remember(item['type'], content, vault_path=vault, project_root=info['project_root'],
                          scope='project', project_id=info['project_id'], project=info['label'])
        ok = isinstance(result, dict) and result.get('status') in {'created', 'duplicate_returned_existing'}
        (written if ok else failed).append(item['source'])
    # Only a complete write marks the study done; otherwise the next run reads it again.
    if not failed:
        _record(vault, info, commit, len(written))
    return {'target': info['key'], 'project_id': info['project_id'], 'written': len(written), 'failed': failed,
            'recorded': not failed}


def _check_commit(commit, *, required):
    if commit is None and not required:
        return
    if not isinstance(commit, str) or not SHA.match(commit):
        raise ValueError('--commit must be the full 40-character commit id from study status')


def mark(vault, target, *, commit):
    """Record that the target was studied up to ``commit`` without writing items."""
    _check_commit(commit, required=True)
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
                                'project_id': info['project_id'], 'root': str(info['root']),
                                'written': int(previous.get('written') or 0) + written}
        write_json(path, {'studies': studies})


def pending_studies(vault):
    """Enrolled local projects with commits since their last study, for the owner notice.

    Runs off the prompt path (with the owner counts). External repositories
    are skipped: checking them needs the network.
    """
    from brain_eleven.projects.registry import ProjectRegistry
    roots = {p['project_id']: p.get('root') for p in ProjectRegistry(vault).list_projects()}
    due = []
    for key, entry in sorted(_studies(vault).items()):
        if not key.startswith('project:') or not isinstance(entry, dict) or not entry.get('commit'):
            continue
        root = Path(entry.get('root') or roots.get(entry.get('project_id')) or '')
        if not str(root) or not (root / '.git').exists():
            continue
        try:
            count = int(_git(root, 'rev-list', '--count', f"{entry['commit']}..HEAD", timeout=20).strip() or 0)
        except (ValueError, OSError):
            continue  # history rewritten or repo moved: nothing reliable to say
        if count:
            due.append({'project_id': entry.get('project_id'), 'label': entry.get('label'), 'new_commits': count})
    return due
