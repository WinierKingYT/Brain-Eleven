#!/usr/bin/env python3
"""Check that the repository's Markdown documentation still points at real files.

Four checks run over the documentation set (root ``*.md`` plus ``docs/``,
``evals/`` and ``templates/``; the personal vault notes use wikilinks and are
out of scope):

* relative Markdown link targets exist, with the exact letter case;
* ``.md`` paths cited in the authority documents exist at the root or in the
  archive;
* ``docs/history/README.md`` lists exactly what is archived;
* no file is both active at the root and archived.

Files under ``docs/history/`` are immutable provenance and are never link
checked: a stale path written inside one is kept as it was.

Output names only a file, a line, a stable code and the referenced path. It
never prints document text, so it is safe in CI logs.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess  # nosec B404 - fixed no-shell Git metadata command only.
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence
from urllib.parse import unquote


LINK_TARGET_MISSING = "MARKDOWN_LINK_TARGET_MISSING"
LINK_CASE_MISMATCH = "MARKDOWN_LINK_CASE_MISMATCH"
AUTHORITY_PATH_MISSING = "AUTHORITY_PATH_MISSING"
ARCHIVE_INDEX_ENTRY_MISSING = "ARCHIVE_INDEX_ENTRY_MISSING"
ARCHIVE_FILE_UNLISTED = "ARCHIVE_FILE_UNLISTED"
ACTIVE_AND_ARCHIVED_COPY = "ACTIVE_AND_ARCHIVED_COPY"

DOCUMENTATION_DIRECTORIES = ("docs/", "evals/", "templates/")
ARCHIVE_DIRECTORY = "docs/history"
ARCHIVE_INDEX = "docs/history/README.md"
AUTHORITY_DOCUMENTS = (
    "DOCUMENTATION-AUTHORITY.md",
    "PROJECT-STATUS.md",
    "ENGINEERING-WEAK-POINTS-AUDIT.md",
)
# Names used in prose ("applicable AGENTS.md files") rather than as paths that
# must exist in this repository.
GENERIC_MARKDOWN_NAMES = frozenset({"AGENTS.md"})

_FENCE_OPEN = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_FENCE_CLOSE = re.compile(r"^\s{0,3}(`{3,}|~{3,})\s*$")
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_INLINE_LINK = re.compile(
    r"!?\[[^\]\n]*\]\(\s*(<[^>\n]*>|[^)\s]+)(?:\s+(?:\"[^\"\n]*\"|'[^'\n]*'))?\s*\)"
)
_REFERENCE_DEFINITION = re.compile(r"^\s{0,3}\[[^\]\n]+\]:\s*(<[^>\n]*>|\S+)")
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_CITED_MARKDOWN = re.compile(r"`([A-Za-z0-9_][A-Za-z0-9_./-]*\.md)`")
_BACKTICKED = re.compile(r"`([^`\n]+)`")


@dataclass(frozen=True)
class Finding:
    """One problem, identified by file and line, never by document content."""

    code: str
    path: str
    line: int
    target: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.code} {self.target}"


def _read_lines(path: Path) -> list[str]:
    try:
        text = path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return []
    return text.replace("\r\n", "\n").split("\n")


def _mask_code(lines: Sequence[str], *, inline: bool) -> list[str]:
    """Blank fenced code (and optionally inline code), keeping line numbers."""
    masked: list[str] = []
    fence: Optional[tuple[str, int]] = None
    for line in lines:
        if fence is None:
            opening = _FENCE_OPEN.match(line)
            if opening:
                fence = (opening.group(1)[0], len(opening.group(1)))
                masked.append("")
            else:
                masked.append(_INLINE_CODE.sub("", line) if inline else line)
            continue
        masked.append("")
        closing = _FENCE_CLOSE.match(line)
        if closing and closing.group(1)[0] == fence[0] and len(closing.group(1)) >= fence[1]:
            fence = None
    return masked


def _tracked_markdown(root: Path) -> Optional[list[Path]]:
    git = shutil.which("git")
    if git is None or not (root / ".git").exists():
        return None
    try:
        result = subprocess.run(  # nosec B603 - fixed no-shell Git invocation.
            [git, "-c", "core.quotepath=off", "ls-files", "-z", "--", "*.md"],
            cwd=root,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    names = result.stdout.decode("utf-8", errors="replace").split("\0")
    return [root / name for name in names if name]


def documentation_files(root: Path) -> list[Path]:
    """Return the Markdown files in scope, excluding the immutable archive."""
    candidates = _tracked_markdown(root)
    if candidates is None:
        candidates = list(root.glob("*.md"))
        for directory in DOCUMENTATION_DIRECTORIES:
            candidates.extend((root / directory).rglob("*.md"))
    files: list[Path] = []
    for path in candidates:
        relative = path.relative_to(root).as_posix()
        in_scope = "/" not in relative or relative.startswith(DOCUMENTATION_DIRECTORIES)
        if in_scope and not relative.startswith(ARCHIVE_DIRECTORY + "/") and path.is_file():
            files.append(path)
    return sorted(set(files))


def _link_targets(line: str) -> Iterable[str]:
    for match in _INLINE_LINK.finditer(line):
        yield match.group(1)
    definition = _REFERENCE_DEFINITION.match(line)
    if definition:
        yield definition.group(1)


def _local_target(raw: str) -> Optional[str]:
    """Return the file part of a link, or None for anchors and external URLs."""
    target = raw.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    if not target or target.startswith("#") or _SCHEME.match(target):
        return None
    target = unquote(target.split("#", 1)[0].split("?", 1)[0])
    return target or None


def _exact_state(root: Path, path: Path) -> str:
    """Return ``ok``, ``missing`` or ``case`` (exists only under another case)."""
    try:
        relative = path.relative_to(root)
    except ValueError:
        try:
            return "ok" if path.exists() else "missing"
        except (OSError, ValueError):
            return "missing"
    current = root
    for part in relative.parts:
        try:
            names = os.listdir(current)
        except (OSError, ValueError):
            return "missing"
        if part in names:
            current = current / part
            continue
        if any(name.casefold() == part.casefold() for name in names):
            return "case"
        return "missing"
    return "ok"


def _resolve(root: Path, document: Path, target: str) -> Path:
    base = root if target.startswith("/") else document.parent
    return Path(os.path.normpath(base / target.lstrip("/")))


def check_links(root: Path, files: Iterable[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for document in files:
        relative = document.relative_to(root).as_posix()
        for number, line in enumerate(_mask_code(_read_lines(document), inline=True), start=1):
            for raw in _link_targets(line):
                target = _local_target(raw)
                if target is None:
                    continue
                state = _exact_state(root, _resolve(root, document, target))
                if state == "missing":
                    findings.append(Finding(LINK_TARGET_MISSING, relative, number, target))
                elif state == "case":
                    findings.append(Finding(LINK_CASE_MISMATCH, relative, number, target))
    return findings


def check_authority_citations(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    archive = root / ARCHIVE_DIRECTORY
    for name in AUTHORITY_DOCUMENTS:
        document = root / name
        if not document.is_file():
            continue
        seen: set[str] = set()
        for number, line in enumerate(_mask_code(_read_lines(document), inline=False), start=1):
            for token in _CITED_MARKDOWN.findall(line):
                if token in seen or token in GENERIC_MARKDOWN_NAMES:
                    continue
                seen.add(token)
                locations = (root / token, archive / token, archive / "weakness" / token)
                if not any(_exact_state(root, location) == "ok" for location in locations):
                    findings.append(Finding(AUTHORITY_PATH_MISSING, name, number, token))
    return findings


def _index_entries(index: Path) -> list[tuple[int, str]]:
    entries: list[tuple[int, str]] = []
    for number, line in enumerate(_read_lines(index), start=1):
        if line.startswith("|"):
            entries.extend((number, token) for token in _BACKTICKED.findall(line))
    return entries


def _entry_exists(root: Path, archive: Path, token: str) -> bool:
    if token.endswith("/"):
        return _exact_state(root, archive / token.rstrip("/")) == "ok" and (archive / token.rstrip("/")).is_dir()
    return any(_exact_state(root, archive / name) == "ok" for name in (token, token + ".md"))


def check_archive_index(root: Path) -> list[Finding]:
    index = root / ARCHIVE_INDEX
    archive = root / ARCHIVE_DIRECTORY
    if not index.is_file():
        return []
    entries = _index_entries(index)
    listed = {token for _, token in entries}
    findings = [
        Finding(ARCHIVE_INDEX_ENTRY_MISSING, ARCHIVE_INDEX, number, token)
        for number, token in entries
        if not _entry_exists(root, archive, token)
    ]
    for child in sorted(os.listdir(archive)):
        if child == "README.md" or child.startswith("."):
            continue
        path = archive / child
        if path.is_dir():
            if child + "/" not in listed:
                findings.append(Finding(ARCHIVE_FILE_UNLISTED, ARCHIVE_INDEX, 0, child + "/"))
        elif child not in listed and child.removesuffix(".md") not in listed:
            findings.append(Finding(ARCHIVE_FILE_UNLISTED, ARCHIVE_INDEX, 0, child))
    return findings


def check_active_archived_duplicates(root: Path) -> list[Finding]:
    archive = root / ARCHIVE_DIRECTORY
    if not archive.is_dir():
        return []
    active = {path.name for path in root.glob("*.md")}
    return [
        Finding(ACTIVE_AND_ARCHIVED_COPY, path.relative_to(root).as_posix(), 0, path.name)
        for path in sorted(archive.rglob("*.md"))
        if path.name != "README.md" and path.name in active
    ]


def _run(root: Path) -> tuple[list[Finding], int]:
    files = documentation_files(root)
    findings = [
        *check_links(root, files),
        *check_authority_citations(root),
        *check_archive_index(root),
        *check_active_archived_duplicates(root),
    ]
    findings.sort(key=lambda item: (item.path, item.line, item.code, item.target))
    return findings, len(files)


def run_checks(root: Path | str) -> list[Finding]:
    """Return every finding for the documentation under ``root``."""
    return _run(Path(root).resolve())[0]


def _configure_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Content-free documentation integrity check")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root")
    arguments = parser.parse_args(argv)
    _configure_utf8_output()
    if not arguments.root.is_dir():
        print("documentation integrity: root is not a directory", file=sys.stderr)
        return 2
    findings, checked = _run(arguments.root.resolve())
    for finding in findings:
        print(finding.render())
    verdict = "FAIL" if findings else "PASS"
    print(f"documentation integrity: {verdict} ({len(findings)} finding(s), {checked} file(s) checked)")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
