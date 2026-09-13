"""W-09A corpus loading, fingerprints, safety gates, and report-safe rows."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any, Iterable, Mapping
from evals.schema import load_fixture, load_tasks
from .metrics import metric_summary

ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = ROOT / "evals" / "corpus-v2"
FIXTURE = ROOT / "evals" / "fixtures" / "phase15-contract.json"
SOURCE_GLOBS = ("evals/baseline.py", "evals/compiler_v2_provider.py", "evals/fixture_generator.py", "evals/metrics.py", "evals/reporting.py", "evals/run.py", "evals/schema.py", "evals/fixtures/phase15-contract.json", "scripts/context-compiler.py", "scripts/task_state_context.py", "brain_eleven/memory/**/*.py", "brain_eleven/state/**/*.py", "brain_eleven/projects/**/*.py", "authority/**/*.py", "context_router/**/*.py", "context_compiler_v2/**/*.py", "evals/w09a/**/*.py", "tests/test_w09a_retrieval_evaluation.py")

def _framed(parts: Iterable[tuple[str, bytes]]) -> str:
    h=hashlib.sha256()
    for name, data in sorted(parts):
        nb=name.encode(); h.update(len(nb).to_bytes(8,"big")); h.update(nb); h.update(len(data).to_bytes(8,"big")); h.update(data)
    return h.hexdigest()

def _files(paths: Iterable[Path], root: Path):
    for p in sorted(set(paths), key=lambda x: x.as_posix()):
        if p.is_file() and p.suffix == ".py": yield p.relative_to(root).as_posix(), p.read_bytes().replace(b"\r\n", b"\n")

def source_fingerprint(root: Path = ROOT) -> str:
    paths=[]
    for pattern in SOURCE_GLOBS: paths.extend(root.glob(pattern))
    return _framed(_files(paths, root))

def corpus_fingerprint(root: Path = CORPUS_ROOT, *, split: str = "public") -> str:
    paths=[root/"manifest.json"] + [p for suite in (("dev","test") if split=="public" else ("holdout",)) for p in (root/suite).glob("*.json")]
    return _framed((p.relative_to(ROOT).as_posix(), p.read_bytes().replace(b"\r\n",b"\n")) for p in sorted(paths))

def load_public_tasks(*, root: Path = CORPUS_ROOT, fixture_path: Path = FIXTURE, split: str = "public"):
    if split not in {"public", "holdout"}: raise ValueError("split must be public or holdout")
    suites=("dev","test") if split=="public" else ("holdout",)
    return load_tasks([p for suite in suites for p in sorted((root/suite).glob("*.json"))], load_fixture(fixture_path))

def evaluate_selection(task: Any, selected_ids: Iterable[str], *, k: int, candidate_ids: Iterable[str] | None = None, candidate_metadata: Mapping[str, Mapping[str, Any]] | None = None, token_counts: Mapping[str,int] | None = None) -> dict[str, Any]:
    selected=tuple(selected_ids); candidates=tuple(candidate_ids if candidate_ids is not None else selected)
    if len(candidates)!=len(set(candidates)) or any(x not in candidates for x in task.required+task.useful+task.forbidden): raise ValueError("invalid candidate or expected ID set")
    if any(x not in candidates for x in selected): raise ValueError("selected ID is outside candidate pool")
    m=metric_summary(selected, task.required, task.useful, task.required, k=k, token_counts=token_counts)
    meta=candidate_metadata or {}
    wrong=forbidden=superseded=resolved=0
    for item in selected:
        row=meta.get(item,{})
        if task.project_id and row.get("project_id") not in (None, task.project_id): wrong+=1
        if item in task.forbidden: forbidden+=1
        if str(row.get("status","")).lower() == "superseded": superseded+=1
        if str(row.get("status","")).lower() == "resolved": resolved+=1
    return {"task_id":task.task_id,"selected_count":m.selected_count,"precision":m.precision,"recall":m.recall,"f1":m.f1,"mrr":m.mrr,"mandatory_recall":m.mandatory_recall,"noise_ratio":m.noise_ratio,"token_waste":m.token_waste,"safety":{"wrong_project_leakage":wrong,"forbidden_leakage":forbidden,"superseded_leakage":superseded,"resolved_leakage":resolved}}
