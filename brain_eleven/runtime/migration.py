"""Explicit, resumable receipt-schema migration with immutable local backups."""
from brain_eleven.memory import MemoryStore
from brain_eleven.state import StateStore
from brain_eleven.infrastructure.locking import file_lock, memory_store_lock
from .storage import write_json, read_json, identity, now
from pathlib import Path


def migrate(vault):
    root = Path(vault) / '.brain-eleven' / 'runtime' / 'migration'
    memory, state = MemoryStore(vault), StateStore(vault)
    # One lock order for migration and rollback. Normal stores never acquire
    # both locks, so no reverse-order dependency is introduced.
    with memory_store_lock(vault), file_lock(state.path):
        for store, version, name in ((memory, 3, 'memory'), (state, 2, 'state')):
            document = store._read_unlocked()
            if document['schema_version'] == version:
                continue
            backup = root / (name + '.json')
            original = {'existed': store.path.exists(), 'document': document}
            if not backup.exists():
                write_json(backup, original)
            document['schema_version'] = version
            document['operation_receipts'] = {}
            store._write_unlocked(document)
        result = {'schema_version': 1, 'migrated_at': now(), 'memory_revision': memory.revision(), 'state_revision': state._read_unlocked()['store_revision']}
        write_json(root / 'manifest.json', result)
        return result


def rollback(vault):
    from .storage import RuntimeConfig
    if RuntimeConfig(vault).load()['mode'] != 'OFF':
        raise ValueError('Stop runtime writes before migration rollback')
    root = Path(vault) / '.brain-eleven' / 'runtime' / 'migration'
    memory, state = MemoryStore(vault), StateStore(vault)
    with memory_store_lock(vault), file_lock(state.path):
        pairs = [(memory, read_json(root / 'memory.json')), (state, read_json(root / 'state.json'))]
        for store, saved in pairs:
            if saved is None:
                raise ValueError('Migration backup missing')
            current = store._read_unlocked()
            if current.get('operation_receipts'):
                raise ValueError('Canonical operations exist; rollback would discard evidence')
            comparable = dict(current)
            comparable.pop('operation_receipts', None)
            comparable['schema_version'] = saved['document']['schema_version']
            if comparable != saved['document']:
                raise ValueError('Canonical changes exist; use reviewed backup restore')
        for store, saved in pairs:
            if saved['existed']:
                store._write_unlocked(saved['document'])
            elif store.path.exists():
                store.path.unlink()
        return {'status': 'ROLLED_BACK'}
