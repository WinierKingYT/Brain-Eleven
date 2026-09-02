"""Tests for the truthful SessionEnd run-result contract."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import session_pipeline as pipeline  # noqa: E402


def _write_writer(path: Path) -> None:
    path.write_text(
        """
import json
import sys
from pathlib import Path

artifact = Path(sys.argv[1])
artifact.parent.mkdir(parents=True, exist_ok=True)
artifact.write_text(json.dumps({"generated_by_run": sys.argv[2]}), encoding="utf-8")
""".strip(),
        encoding="utf-8",
    )


def test_step_requires_a_fresh_lineage_matching_artifact(tmp_path):
    artifact = tmp_path / ".claude" / "compiled-memory.json"
    writer = tmp_path / "writer.py"
    _write_writer(writer)
    spec = pipeline.StepSpec(
        "memory_compiler",
        [sys.executable, str(writer), str(artifact), "run_test"],
        artifact,
    )

    result = pipeline._run_step(spec, tmp_path, "run_test")

    assert result["status"] == pipeline.SUCCESS
    assert result["artifact_created_this_run"] is True
    assert result["source_memory_revision"] == 0
    assert result["produced_memory_revision"] == 0


def test_step_never_treats_an_existing_stale_artifact_as_success(tmp_path):
    artifact = tmp_path / ".claude" / "compiled-memory.json"
    artifact.parent.mkdir()
    artifact.write_text(json.dumps({"generated_by_run": "run_old"}), encoding="utf-8")
    no_op = tmp_path / "no_op.py"
    no_op.write_text("print('no artifact written')", encoding="utf-8")
    spec = pipeline.StepSpec(
        "memory_compiler",
        [sys.executable, str(no_op)],
        artifact,
    )

    result = pipeline._run_step(spec, tmp_path, "run_test")

    assert result["status"] == pipeline.DEGRADED
    assert result["artifact_created_this_run"] is False
    assert "did not create a fresh artifact" in result["error"]


def test_pipeline_skips_canonical_and_context_steps_after_compiler_failure(tmp_path, monkeypatch):
    calls = []

    def fake_run(spec, _vault, run_id):
        calls.append(spec.name)
        if spec.name == "memory_compiler":
            return {
                "step": spec.name,
                "run_id": run_id,
                "status": pipeline.DEGRADED,
                "source_memory_revision": 0,
                "produced_memory_revision": 0,
                "artifact": str(spec.artifact),
                "artifact_created_this_run": False,
                "error": "simulated compiler failure",
            }
        return {
            "step": spec.name,
            "run_id": run_id,
            "status": pipeline.SUCCESS,
            "source_memory_revision": 0,
            "produced_memory_revision": 0,
            "artifact": str(spec.artifact),
            "artifact_created_this_run": True,
            "error": None,
        }

    monkeypatch.setattr(pipeline, "_run_step", fake_run)
    result = pipeline.run_pipeline(tmp_path, tmp_path, sys.executable, run_id="run_test")

    assert calls == ["memory_compiler", "post_session_maintenance"]
    assert result["status"] == pipeline.DEGRADED
    assert result["steps"][1]["status"] == pipeline.SKIPPED
    assert result["steps"][2]["status"] == pipeline.SKIPPED
    history = tmp_path / ".claude" / "session-runs" / "run_test.json"
    assert json.loads(history.read_text(encoding="utf-8"))["run_id"] == "run_test"


def test_pipeline_marks_validator_failure_as_failed(tmp_path, monkeypatch):
    def fake_run(spec, _vault, run_id):
        status = pipeline.FAILED if spec.name == "memory_validator" else pipeline.SUCCESS
        return {
            "step": spec.name,
            "run_id": run_id,
            "status": status,
            "source_memory_revision": 0,
            "produced_memory_revision": 0,
            "artifact": str(spec.artifact),
            "artifact_created_this_run": status == pipeline.SUCCESS,
            "error": "simulated canonical write failure" if status == pipeline.FAILED else None,
        }

    monkeypatch.setattr(pipeline, "_run_step", fake_run)
    result = pipeline.run_pipeline(tmp_path, tmp_path, sys.executable, run_id="run_test")

    assert result["status"] == pipeline.FAILED
    assert result["steps"][1]["status"] == pipeline.FAILED
    assert result["steps"][2]["status"] == pipeline.SKIPPED
    assert json.loads((tmp_path / ".claude" / "session-run-result.json").read_text(encoding="utf-8"))["status"] == pipeline.FAILED
