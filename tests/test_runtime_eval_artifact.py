"""The PRE-13 quality command always leaves bounded machine-readable evidence."""

from __future__ import annotations

import json


def test_runtime_eval_writes_content_free_failure_artifact(tmp_path, monkeypatch):
    from evals import runtime_eval

    monkeypatch.setattr(runtime_eval, "run", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("private detail")))
    report_path = tmp_path / "holdout.json"

    assert runtime_eval.main(["--suite", "holdout", "--report", str(report_path)]) == 1

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "ERROR"
    assert report["error_code"] == "RUNTIME_EVALUATION_FAILED"
    assert report["measurement"] == "unavailable"
    assert report["case_count"] == 0
    assert "private detail" not in report_path.read_text(encoding="utf-8")
