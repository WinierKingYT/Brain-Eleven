"""Behavior of the content-free documentation integrity checker."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_documentation_integrity import (
    ACTIVE_AND_ARCHIVED_COPY,
    ARCHIVE_FILE_UNLISTED,
    ARCHIVE_INDEX_ENTRY_MISSING,
    AUTHORITY_PATH_MISSING,
    LINK_CASE_MISMATCH,
    LINK_TARGET_MISSING,
    main,
    run_checks,
)


ROOT = Path(__file__).resolve().parents[1]

INDEX = """# docs/history

| Group | Files |
|---|---|
| Plans | `PLAN-ONE`, `PLAN-TWO` |
| Older | `weakness/` |
"""


def build(tmp_path: Path, files: dict[str, str]) -> Path:
    for relative, text in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return tmp_path


def codes(findings) -> list[str]:
    return [finding.code for finding in findings]


def test_the_current_repository_passes():
    assert run_checks(ROOT) == []


def test_a_missing_relative_link_target_fails_with_file_and_line(tmp_path):
    root = build(tmp_path, {"A.md": "intro\n\nsee [the plan](GONE.md) here\n"})

    findings = run_checks(root)

    assert [(f.code, f.path, f.line, f.target) for f in findings] == [
        (LINK_TARGET_MISSING, "A.md", 3, "GONE.md")
    ]


def test_existing_targets_directories_fragments_and_titles_pass(tmp_path):
    root = build(tmp_path, {
        "A.md": '[b](B.md#section) [dir](docs/) [t](B.md "title") ![img](docs/pic.png?raw=1)\n',
        "B.md": "b\n",
        "docs/pic.png": "x",
    })

    assert run_checks(root) == []


def test_reference_style_definitions_are_checked(tmp_path):
    root = build(tmp_path, {"A.md": "text [label]\n\n[label]: MISSING.md\n"})

    assert codes(run_checks(root)) == [LINK_TARGET_MISSING]


def test_external_anchor_and_mail_links_are_not_local_paths(tmp_path):
    root = build(tmp_path, {
        "A.md": "[a](https://example.invalid/x) [b](http://example.invalid) [c](#section) "
                "[d](mailto:someone@example.invalid) [e](<https://example.invalid/y>)\n",
    })

    assert run_checks(root) == []


def test_links_inside_code_are_not_checked(tmp_path):
    root = build(tmp_path, {
        "A.md": "```\n[fenced](NOPE.md)\n```\n\n~~~md\n[tilde](NOPE.md)\n~~~\n\n"
                "and inline `[code](NOPE.md)` too\n",
    })

    assert run_checks(root) == []


def test_a_link_whose_case_differs_from_the_file_fails_on_every_platform(tmp_path):
    root = build(tmp_path, {"A.md": "[b](readme.md)\n", "Readme.md": "r\n"})

    assert codes(run_checks(root)) == [LINK_CASE_MISMATCH]


def test_archived_history_files_are_immutable_provenance_and_not_checked(tmp_path):
    root = build(tmp_path, {
        "docs/history/README.md": INDEX,
        "docs/history/PLAN-ONE.md": "[old](MOVED-AWAY.md)\n",
        "docs/history/PLAN-TWO.md": "x\n",
        "docs/history/weakness/W.md": "[old](MOVED-AWAY.md)\n",
    })

    assert run_checks(root) == []


def test_a_missing_authority_target_fails(tmp_path):
    root = build(tmp_path, {
        "DOCUMENTATION-AUTHORITY.md": "| `GONE.md` | CURRENT |\n| `HERE.md` | CURRENT |\n",
        "HERE.md": "x\n",
    })

    findings = run_checks(root)

    assert [(f.code, f.path, f.line, f.target) for f in findings] == [
        (AUTHORITY_PATH_MISSING, "DOCUMENTATION-AUTHORITY.md", 1, "GONE.md")
    ]


def test_authority_targets_may_live_in_the_archive_and_globs_and_generic_names_are_skipped(tmp_path):
    root = build(tmp_path, {
        "DOCUMENTATION-AUTHORITY.md": "| `PLAN-ONE.md` | archived |\n| `docs/history/weakness/**` | glob |\n"
                                      "| `WEAKNESS-*.md` | glob |\nApplicable `AGENTS.md` files are instructions.\n",
        "docs/history/README.md": INDEX,
        "docs/history/PLAN-ONE.md": "x\n",
        "docs/history/PLAN-TWO.md": "x\n",
        "docs/history/weakness/W.md": "x\n",
    })

    assert run_checks(root) == []


def test_an_archive_index_entry_without_a_file_fails(tmp_path):
    root = build(tmp_path, {
        "docs/history/README.md": INDEX,
        "docs/history/PLAN-ONE.md": "x\n",
        "docs/history/weakness/W.md": "x\n",
    })

    findings = run_checks(root)

    assert [(f.code, f.path, f.target) for f in findings] == [
        (ARCHIVE_INDEX_ENTRY_MISSING, "docs/history/README.md", "PLAN-TWO")
    ]
    assert findings[0].line == 5


def test_an_archived_file_missing_from_the_index_fails(tmp_path):
    root = build(tmp_path, {
        "docs/history/README.md": INDEX,
        "docs/history/PLAN-ONE.md": "x\n",
        "docs/history/PLAN-TWO.md": "x\n",
        "docs/history/UNLISTED.md": "x\n",
        "docs/history/weakness/W.md": "x\n",
        "docs/history/extra-dir/F.md": "x\n",
    })

    findings = run_checks(root)

    assert sorted((f.code, f.target) for f in findings) == [
        (ARCHIVE_FILE_UNLISTED, "UNLISTED.md"),
        (ARCHIVE_FILE_UNLISTED, "extra-dir/"),
    ]


def test_a_file_that_is_both_active_at_the_root_and_archived_fails(tmp_path):
    root = build(tmp_path, {
        "PLAN-ONE.md": "active\n",
        "docs/history/README.md": INDEX,
        "docs/history/PLAN-ONE.md": "archived\n",
        "docs/history/PLAN-TWO.md": "x\n",
        "docs/history/weakness/W.md": "x\n",
        "README.md": "root readme\n",
    })

    findings = run_checks(root)

    assert [(f.code, f.target) for f in findings] == [(ACTIVE_AND_ARCHIVED_COPY, "PLAN-ONE.md")]


def test_personal_vault_notes_and_unscoped_directories_are_out_of_scope(tmp_path):
    root = build(tmp_path, {
        "A.md": "ok\n",
        "notes vault/N.md": "[[wikilink]] and [broken](NOPE.md)\n",
        "src/README.md": "[broken](NOPE.md)\n",
    })

    assert run_checks(root) == []


def test_output_is_content_free_and_the_exit_code_reflects_the_result(tmp_path, capsys):
    secret = "PRIVATE-SENTENCE-THAT-MUST-NOT-APPEAR"
    root = build(tmp_path, {"A.md": f"{secret} [x](GONE.md) {secret}\n"})

    assert main(["--root", str(root)]) == 1
    failing = capsys.readouterr().out
    assert "A.md:1: MARKDOWN_LINK_TARGET_MISSING GONE.md" in failing
    assert secret not in failing
    assert "FAIL" in failing

    clean = build(tmp_path / "clean", {"A.md": "fine\n"})
    assert main(["--root", str(clean)]) == 0
    assert "PASS" in capsys.readouterr().out


def test_a_missing_root_is_a_usage_error_not_a_pass(tmp_path, capsys):
    assert main(["--root", str(tmp_path / "does-not-exist")]) == 2
    assert "not a directory" in capsys.readouterr().err


@pytest.mark.parametrize("bad", ["broken\x00name.md"])
def test_unreadable_or_odd_link_targets_do_not_crash_the_checker(tmp_path, bad):
    root = build(tmp_path, {"A.md": f"[x]({bad})\n[y](%ZZ.md)\n"})

    run_checks(root)
