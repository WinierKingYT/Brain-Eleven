"""Windows containment behaviour of the no-follow backup source reader (SRT-00).

The path-normalisation tests use ``ntpath`` and run on every platform.  The
file-system tests exercise the real ``CreateFileW`` / ``GetFinalPathNameByHandleW``
handle on a Windows runner; they are skipped elsewhere because no other
platform has those primitives, not to hide a Windows failure.
"""

import os
import subprocess

import pytest

from memory_backup import (  # noqa: E402
    MemoryBackupError,
    _read_source_file,
    _windows_normalise_final_path,
    _windows_path_within,
)

windows_only = pytest.mark.skipif(
    os.name != "nt", reason="requires the real Windows handle and file system"
)


@pytest.mark.parametrize(
    ("final_path", "expected"),
    [
        ("\\\\?\\C:\\vault\\.claude\\x.json", "C:\\vault\\.claude\\x.json"),
        ("\\\\?\\UNC\\srv\\share\\vault\\x.json", "\\\\srv\\share\\vault\\x.json"),
        ("C:\\vault\\.claude\\x.json", "C:\\vault\\.claude\\x.json"),
        ("\\\\srv\\share\\vault", "\\\\srv\\share\\vault"),
    ],
)
def test_final_path_prefixes_are_normalised_without_corrupting_unc(final_path, expected):
    assert _windows_normalise_final_path(final_path) == expected


@pytest.mark.parametrize(
    ("root", "candidate", "expected"),
    [
        ("C:\\v\\.claude", "C:\\v\\.claude\\validated-memory.json", True),
        ("C:\\v\\.claude", "c:\\V\\.CLAUDE\\validated-memory.json", True),
        ("C:\\v\\.claude\\", "C:\\v\\.claude\\validated-memory.json", True),
        ("C:\\v\\.claude", "C:\\v\\.claude", True),
        ("C:\\v\\.claude", "C:\\v\\.claude-escape\\validated-memory.json", False),
        ("C:\\v\\.claude", "C:\\v\\other.json", False),
        ("C:\\v\\.claude", "D:\\v\\.claude\\validated-memory.json", False),
        ("\\\\srv\\share\\v", "\\\\srv\\share\\v\\x.json", True),
        ("\\\\srv\\share\\v", "\\\\srv\\share\\v-escape\\x.json", False),
        ("\\\\srv\\share\\v", "\\\\other\\share\\v\\x.json", False),
        ("C:\\v\\.claude", "\\\\srv\\share\\v\\x.json", False),
    ],
)
def test_windows_containment_is_component_wise_and_case_insensitive(root, candidate, expected):
    assert _windows_path_within(root, candidate) is expected


def _vault_root(tmp_path, name="Vault With Spaces"):
    root = tmp_path / name / ".claude"
    root.mkdir(parents=True)
    return root


def _short_form(path):
    import ctypes

    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, len(buffer))
    return buffer.value if length else None


def _make_junction(link, target):
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("directory junction creation is unavailable on this runner")


@windows_only
def test_regular_file_is_read_and_handle_is_released(tmp_path):
    root = _vault_root(tmp_path)
    source = root / "validated-memory.json"
    source.write_bytes(b"payload")

    assert _read_source_file(source, root) == b"payload"

    # A directory containing a still-open handle cannot be renamed on Windows.
    root.rename(root.parent / ".claude-renamed")


@windows_only
def test_root_casing_difference_is_not_an_escape(tmp_path):
    root = _vault_root(tmp_path)
    source = root / "validated-memory.json"
    source.write_bytes(b"payload")
    swapped = type(root)(str(root).swapcase())

    assert _read_source_file(source, swapped) == b"payload"


@windows_only
def test_unicode_and_spaced_paths_are_contained(tmp_path):
    root = _vault_root(tmp_path, name="Kasa Belleği ünlü")
    source = root / "hafıza.json"
    source.write_bytes(b"payload")

    assert _read_source_file(source, root) == b"payload"


@windows_only
def test_eight_dot_three_root_is_not_reported_as_an_escape(tmp_path):
    root = _vault_root(tmp_path, name="A Deliberately Long Vault Directory Name")
    source = root / "long-named-canonical-memory.json"
    source.write_bytes(b"payload")
    short_root = _short_form(root)
    if not short_root or short_root.lower() == str(root).lower():
        pytest.skip("8.3 short names are not enabled for this volume")

    assert _read_source_file(type(root)(short_root) / source.name, type(root)(short_root)) == b"payload"


@windows_only
def test_junction_that_leaves_the_root_is_rejected(tmp_path):
    root = _vault_root(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "validated-memory.json").write_bytes(b"secret")
    _make_junction(root / "link", outside)

    with pytest.raises(MemoryBackupError) as caught:
        _read_source_file(root / "link" / "validated-memory.json", root)

    assert caught.value.code == "BACKUP_FINAL_PATH_OUTSIDE_ROOT"
    assert "secret" not in str(caught.value)
    assert str(outside) not in str(caught.value)


@windows_only
def test_junction_as_the_source_itself_is_a_reparse_point_refusal(tmp_path):
    root = _vault_root(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    _make_junction(root / "link", outside)

    with pytest.raises(MemoryBackupError) as caught:
        _read_source_file(root / "link", root)

    assert caught.value.code == "BACKUP_SOURCE_REPARSE_POINT"
