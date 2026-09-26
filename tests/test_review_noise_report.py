"""Review-queue noise report: grouping, acceptance rate, no content leakage."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from review_noise_report import load_items, report  # noqa: E402


def test_groups_by_reason_and_computes_acceptance_rate(tmp_path):
    root = tmp_path / ".brain-eleven" / "runtime" / "review"
    root.mkdir(parents=True)
    rows = [("MODEL_PROPOSAL", "ACCEPTED", "assistant"), ("MODEL_PROPOSAL", "REJECTED", "assistant"),
            ("MODEL_PROPOSAL", "REJECTED", "assistant"), ("LOW_EVIDENCE_COMMITMENT", "PENDING", "user")]
    for i, (reason, status, role) in enumerate(rows):
        (root / f"rev_{i:064x}.json").write_text(json.dumps({
            "status": status, "reason": reason, "project_id": "p",
            "candidate": {"candidate_type": "MEMORY", "memory_type": "decision", "content": "secret words " * i},
            "source": {"client": "claude", "role": role}}), encoding="utf-8")
    result = report(load_items(tmp_path))
    assert result["totals"]["total"] == 4
    assert result["by"]["reason"]["MODEL_PROPOSAL"]["acceptance_rate"] == 0.333
    assert result["by"]["reason"]["LOW_EVIDENCE_COMMITMENT"]["acceptance_rate"] is None
    assert result["by"]["source_role"]["assistant"]["total"] == 3
    assert "secret" not in json.dumps(result)
