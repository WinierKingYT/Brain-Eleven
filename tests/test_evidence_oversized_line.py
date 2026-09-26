"""A single transcript line over the 2 MB read window is skipped, not fatal."""

import json

from brain_eleven.runtime.evidence import read_increment
from tests.test_pre13_runtime import _native_path, runtime  # noqa: F401  (fixture)


def _user(text):
    return {'type': 'user', 'message': {'role': 'user', 'content': text}}


def test_oversized_line_is_skipped_and_reading_continues(runtime, tmp_path):  # noqa: F811
    vault, project = runtime
    huge = {'type': 'attachment', 'data': 'x' * (3 * 1024 * 1024)}
    path = _native_path(tmp_path, vault, 'claude', 's', [_user('Before.'), huge, _user('We decided to use SQLite.')])

    seen, cursor, oversized = [], None, 0
    for _ in range(10):
        stats = {}
        batch, cursor = read_increment(vault, path, 'claude', 's', project, '2026-09-26T00:00:00Z', cursor, stats=stats)
        seen += [m.content for m in batch.messages]
        oversized += stats.get('oversized_lines', 0)
        if not cursor['has_more']:
            break
    assert seen == ['Before.', 'We decided to use SQLite.']
    assert oversized == 1 and cursor['offset'] == path.stat().st_size


def test_unfinished_oversized_line_waits_without_moving(runtime, tmp_path):  # noqa: F811
    vault, project = runtime
    path = _native_path(tmp_path, vault, 'claude', 's', [_user('Before.')])
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'type': 'attachment', 'data': 'x' * (3 * 1024 * 1024)}))  # no newline yet
    batch, cursor = read_increment(vault, path, 'claude', 's', project, '2026-09-26T00:00:00Z')
    start = cursor['offset']
    batch, cursor = read_increment(vault, path, 'claude', 's', project, '2026-09-26T00:00:00Z', cursor)
    assert not batch.messages and cursor['offset'] == start and not cursor['has_more']
