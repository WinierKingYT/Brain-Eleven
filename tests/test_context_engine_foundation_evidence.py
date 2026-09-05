"""Truthfulness checks for the Context Engine Foundation V1 manifest."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import context_engine_foundation_evidence as foundation_evidence  # noqa: E402
from context_engine_foundation_evidence import (  # noqa: E402
    FoundationEvidenceError,
    REQUIRED_GRADUATION_TESTS,
    build_manifest,
)


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _current_sha() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip()


def _phase(phase: str, sha: str) -> dict:
    invariants = {
        "15": {"forbidden_context": 0},
        "16": {"wrong_project_state_leakage": 0, "lost_state_updates": 0},
        "17": {"canonical_write": 0},
        "18": {"canonical_write": 0},
        "19": {"canonical_write": 0, "nondeterminism": 0},
    }[phase]
    return {"phase": phase, "status": "PASS", "head_sha": sha, "invariants": invariants}


def _junit(path: Path, skipped_case: str = "") -> None:
    cases = "".join(
        f'<testcase name="{name}">{"<skipped />" if name == skipped_case else ""}</testcase>'
        for name in sorted(REQUIRED_GRADUATION_TESTS)
    )
    path.write_text(f"<testsuite>{cases}</testsuite>", encoding="utf-8")


def test_foundation_manifest_requires_one_revision_bound_passing_chain(tmp_path):
    sha = _current_sha()
    junit = tmp_path / "graduation.xml"
    _junit(junit)
    paths = {str(phase): tmp_path / f"phase{phase}.json" for phase in range(15, 20)}
    for phase, path in paths.items():
        _write(path, _phase(phase, sha))

    manifest = build_manifest(junit=junit, phase_paths=paths, root=ROOT)

    assert manifest["status"] == "PASS"
    assert manifest["hard_invariants"]["lost_updates"] == 0
    assert manifest["review_status"] == "PENDING_INDEPENDENT_REVIEW"


def test_foundation_manifest_refuses_a_phase_evidence_sha_from_another_revision(tmp_path):
    sha = _current_sha()
    junit = tmp_path / "graduation.xml"
    _junit(junit)
    paths = {str(phase): tmp_path / f"phase{phase}.json" for phase in range(15, 20)}
    for phase, path in paths.items():
        _write(path, _phase(phase, "deadbeef" if phase == "18" else sha))

    with pytest.raises(FoundationEvidenceError, match="current revision"):
        build_manifest(junit=junit, phase_paths=paths, root=ROOT)


def test_foundation_manifest_refuses_a_skipped_required_graduation_test(tmp_path):
    sha = _current_sha()
    junit = tmp_path / "graduation.xml"
    _junit(junit, skipped_case=sorted(REQUIRED_GRADUATION_TESTS)[0])
    paths = {str(phase): tmp_path / f"phase{phase}.json" for phase in range(15, 20)}
    for phase, path in paths.items():
        _write(path, _phase(phase, sha))

    with pytest.raises(FoundationEvidenceError, match="required passing test"):
        build_manifest(junit=junit, phase_paths=paths, root=ROOT)


def test_foundation_evidence_cli_writes_only_revision_bound_metadata(tmp_path, monkeypatch, capsys):
    sha = _current_sha()
    junit = tmp_path / "graduation.xml"
    _junit(junit)
    paths = {str(phase): tmp_path / f"phase{phase}.json" for phase in range(15, 20)}
    for phase, path in paths.items():
        _write(path, _phase(phase, sha))
    monkeypatch.setattr(foundation_evidence, "_git_sha", lambda _root: sha)
    output = tmp_path / "foundation.json"

    assert foundation_evidence.main(
        [
            "--junit", str(junit), "--phase15", str(paths["15"]), "--phase16", str(paths["16"]),
            "--phase17", str(paths["17"]), "--phase18", str(paths["18"]), "--phase19", str(paths["19"]),
            "--output", str(output), "--root", str(ROOT),
        ]
    ) == 0

    assert json.loads(output.read_text(encoding="utf-8"))["git_sha"] == sha
    assert "private memory" not in capsys.readouterr().out
