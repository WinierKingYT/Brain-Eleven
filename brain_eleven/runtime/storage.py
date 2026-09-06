"""Small local operational stores, separate from canonical memory and state."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


def identity(prefix, *values):
    return prefix + hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


class RuntimeConfig:
    def __init__(self, vault):
        self.vault = Path(vault).resolve()
        self.root = self.vault / '.brain-eleven' / 'runtime'
        self.path = self.root / 'config.json'

    def load(self):
        value = read_json(self.path, {'schema_version': 1, 'mode': 'OFF', 'project_ids': [], 'local_model': None})
        if not isinstance(value, dict) or value.get('schema_version') != 1 or value.get('mode') not in {'OFF', 'SHADOW', 'CANARY', 'ACTIVE'}:
            raise ValueError('Invalid runtime configuration')
        if not isinstance(value.get('project_ids'), list) or not all(isinstance(x, str) and x for x in value['project_ids']):
            raise ValueError('Invalid runtime project scope')
        model = value.get('local_model')
        if model is not None and (not isinstance(model, dict) or set(model) != {'url', 'model'} or not all(isinstance(x, str) and x for x in model.values())):
            raise ValueError('Invalid local model configuration')
        return value

    def set_mode(self, mode):
        if mode not in {'OFF', 'SHADOW', 'CANARY', 'ACTIVE'}:
            raise ValueError('Invalid rollout mode')
        value = self.load()
        if mode == 'CANARY':
            from brain_eleven.memory import MemoryStore
            from brain_eleven.state import StateStore
            if MemoryStore(self.vault).load()['schema_version'] != 3 or StateStore(self.vault).load()['schema_version'] != 2 or not value['project_ids']:
                raise ValueError('Install and migrate the opted-in canary project first')
            from evals.runtime_eval import run
            report = run('holdout')
            write_json(self.root / 'canary-quality.json', report)
            if report['status'] != 'PASS':
                raise ValueError('Independent holdout quality gates failed; remain in SHADOW')
        if mode == 'ACTIVE':
            from .graduation import verify
            verify(self.vault)
        value['mode'] = mode
        write_json(self.path, value)
        return value
