#!/usr/bin/env python3
"""Adversarial coverage for the deterministic canonical capture safety gate."""

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from capture_safety import (  # noqa: E402
    CaptureSafetyError,
    POLICY_NAME,
    evaluate_capture,
)
from remember import remember  # noqa: E402


def _load_script(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "content",
    [
        "OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz123456",
        "github_token=ghp_abcdefghijklmnopqrstuvwxyz1234567890",
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345",
        'DATABASE_PASSWORD="correct-horse-battery-staple"',
        "-----BEGIN PRIVATE KEY-----\nvery-secret-material\n-----END PRIVATE KEY-----",
        "Cookie: session=abcdefghijklmnopqrstuvwxyz0123456789",
        "api_key=not-a-real-but-secret-looking-value",
        "postgresql://brain:secret-password@db.example.test:5432/brain",
    ],
)
def test_structural_secret_evidence_is_rejected(content):
    result = evaluate_capture(content)

    assert result.accepted is False
    assert result.reason == "potential_secret"
    assert result.policy == POLICY_NAME


def test_transcript_and_large_payloads_are_rejected():
    transcript = "\n".join(
        [
            "User: " + "A" * 100,
            "Assistant: " + "B" * 100,
            "User: " + "C" * 100,
            "Assistant: " + "D" * 100,
        ]
    )

    assert evaluate_capture(transcript).reason == "transcript_like"
    assert evaluate_capture("x" * 6001).reason == "payload_too_large"
    assert evaluate_capture("\n".join(["line"] * 81)).reason == "too_many_lines"


@pytest.mark.parametrize(
    "content",
    [
        "Token budgeting should reserve context for tool results.",
        "Password reset architecture needs rate limiting and audit logs.",
        "GitHub token rotation should be documented as an operational rule.",
    ],
)
def test_security_discussion_without_credential_structure_is_allowed(content):
    result = evaluate_capture(content)

    assert result.accepted is True
    assert result.to_dict() == {"accepted": True, "reason": "", "policy": POLICY_NAME}


def test_remember_rejects_before_project_registration_or_persistence(tmp_path):
    vault = tmp_path / "vault"
    project_root = tmp_path / "client-project"
    (vault / ".claude").mkdir(parents=True)
    project_root.mkdir()

    result = remember(
        type_="decision",
        content="Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345",
        vault_path=vault,
        project_root=project_root,
    )

    assert result == {"accepted": False, "reason": "potential_secret", "policy": POLICY_NAME}
    assert not (vault / ".claude" / "project-registry.json").exists()
    assert not (vault / ".claude" / "validated-memory.json").exists()


def test_validator_and_batch_compiler_cannot_persist_unsafe_content(tmp_path):
    vault = tmp_path / "vault"
    (vault / ".claude").mkdir(parents=True)
    validator_module = _load_script("capture_safety_validator", "memory-validator.py")
    validator = validator_module.MemoryValidator(str(vault))

    with pytest.raises(CaptureSafetyError) as exc:
        validator.validate_single("decision", "password = hunter2-secret")
    assert exc.value.result.to_dict() == {
        "accepted": False,
        "reason": "potential_secret",
        "policy": POLICY_NAME,
    }
    with pytest.raises(CaptureSafetyError):
        validator.append_validated(
            validator_module.ValidatedMemory(
                type="decision",
                content="password = hunter2-secret",
            )
        )
    with pytest.raises(CaptureSafetyError):
        validator.validate_single_and_append(
            type_="decision",
            content="Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345",
        )
    assert not (vault / ".claude" / "validated-memory.json").exists()

    (vault / ".claude" / "compiled-memory.json").write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "type": "observation",
                        "content": "Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345",
                        "confidence": 0.9,
                        "source": "test",
                        "timestamp": datetime.now().isoformat(),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    validator.save_output()
    stored = (vault / ".claude" / "validated-memory.json").read_text(encoding="utf-8")

    assert "abcdefghijklmnopqrstuvwxyz012345" not in stored
    assert json.loads(stored)["summary"]["safety_rejected"] == 1
