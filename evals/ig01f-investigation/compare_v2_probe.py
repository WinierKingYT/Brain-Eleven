"""Read-only A/B probe: does IG01-F's V2 arm change if the missing
retrieval_decision_v2 + context_density_v2 selection stage is wired in,
exactly as brain_eleven.runtime.context.compile_task does it, instead of
calling ContextCompilerV2.compile() bare (CompilerV2ContextProvider's actual
current behavior)?

Never writes to the ig01f-naive-baseline branch. Only reads its frozen
DEV+VALIDATION projection (never holdout) and its own evaluation code.

This script depends on `evals/ig01f/*` and `evals/compiler_v2_provider.py`,
which exist on branch `ig/ig01f-naive-baseline`, not on `master`. Run it
from a checkout (or worktree) of that branch, e.g.:

    git worktree add -q --detach /tmp/ig01f_wt origin/ig/ig01f-naive-baseline
    cd /tmp/ig01f_wt
    python /path/to/evals/ig01f-investigation/compare_v2_probe.py

It writes its output next to itself (`raw_comparison.json` in this
script's own directory), so it works regardless of which checkout it is
invoked from.
"""
import json
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

OUTPUT_DIR = Path(__file__).resolve().parent

# Resolves evals.ig01f / evals.compiler_v2_provider / etc. against the
# current working directory, which must be the root of a checkout of
# `ig/ig01f-naive-baseline` (see module docstring for the exact command).
sys.path.insert(0, str(Path.cwd()))

from evals.ig01f.measure import _load, _write_vault, _bounded  # noqa: E402
from evals.compiler_v2_provider import CompilerV2ContextProvider  # noqa: E402
from evals.contracts import NormalizedEvaluationResult, SelectedContextItem  # noqa: E402
from evals.ig01c.metrics import evaluate_retrieval_case  # noqa: E402
from evals.router_provider import RouterContextProvider  # noqa: E402

from authority import AuthorityOptions, AuthorityResolver  # noqa: E402
from context_router import ContextRouter, RoutingOptions  # noqa: E402
from context_compiler_v2 import BudgetContract, CompilationOptions, CompilationRequest, ContextCompilerV2  # noqa: E402
from context_compiler_v2.adapters import CompilerEvidenceAdapter  # noqa: E402
from context_compiler_v2.safety import contains_secret  # noqa: E402
from context_compiler_v2.tokenizer import ConservativeTokenEstimator  # noqa: E402
from context_density_v2 import ContextDensityEngine, DensityOptions  # noqa: E402
from retrieval_decision_v2 import DecisionOptions, RetrievalDecisionEngine  # noqa: E402
from retrieval_decision_v2.models import NeedPlan  # noqa: E402
from brain_eleven.memory import MemoryStore  # noqa: E402
from brain_eleven.runtime.task_state_context import TaskStateComposer  # noqa: E402


class CorrectedV2Provider:
    """Same evaluation contract as CompilerV2ContextProvider, but wires
    RetrievalDecisionEngine + ContextDensityEngine before ContextCompilerV2,
    exactly as brain_eleven/runtime/context.py's compile_task does for the
    real (non-evaluation) V2-compat path. No production file changed."""

    provider_id = "context_compiler_v2_corrected"

    def select(self, task, vault_path):
        vault = Path(vault_path)
        if task.project_id is None:
            context = TaskStateComposer(vault, vault / "compiler-v2-global").compose(task.prompt)
            routing = RoutingOptions(scope_mode="GLOBAL_ONLY")
        else:
            root = RouterContextProvider._ensure_project(vault, task.project_id)
            context = TaskStateComposer(vault, root).compose(task.prompt)
            routing = RoutingOptions()
        router = ContextRouter(vault).route(context, routing)
        authority = AuthorityResolver(vault).resolve(
            context, router,
            AuthorityOptions(scope_mode=routing.scope_mode, selected_project_ids=routing.selected_project_ids,
                              include_global=routing.include_global, history_mode=routing.history_mode),
        )
        adapter = CompilerEvidenceAdapter(vault)
        snapshot = adapter.snapshot(context, authority)
        estimator = ConservativeTokenEstimator()
        texts = {item.resolution.candidate_id: item.text for item in snapshot.candidates if not contains_secret(item.text)}
        decision = RetrievalDecisionEngine().select(
            context, router, authority,
            options=DecisionOptions(max_selected=len(router.candidates)), candidate_texts=texts,
        )
        decision = replace(decision, input_revisions=dict(authority.input_revisions))
        decision = replace(decision, need_plan=NeedPlan(tuple(n for n in decision.need_plan.needs if n.kind != "task")))
        selected = tuple(
            replace(item, estimated_tokens=estimator.estimate(texts[item.candidate_id]).count)
            for item in decision.selected if item.candidate_id in texts
        )
        decision = replace(decision, selected=selected)
        density = ContextDensityEngine().select(decision, options=DensityOptions(max_selected=20), candidate_texts=texts)
        if density.status not in {"SUCCESS", "DEGRADED", "EMPTY"}:
            return NormalizedEvaluationResult(
                task_id=task.task_id, provider_id=self.provider_id, selected_items=(),
                source_memory_revision=MemoryStore(vault).load()["revision"], project_id=task.project_id,
                retrieval_scope="default" if task.project_id is not None else "global",
                capabilities={"scope_isolation": "supported", "lifecycle_filtering": "supported",
                              "task_aware_ranking": "supported", "authority_resolution": "supported",
                              "conflict_resolution": "supported", "token_budgeting": "supported"},
            )
        bundle = ContextCompilerV2(vault).compile(
            CompilationRequest(context, authority, BudgetContract(2048, minimum_headroom_tokens=128), selection=density),
            CompilationOptions(cache_enabled=False),
        )
        if bundle.status not in {"SUCCESS", "DEGRADED", "EMPTY"}:
            raise RuntimeError(f"corrected compiler failed for {task.task_id}: {bundle.status}: {bundle.error}")
        records = {r.get("memory_id"): r for r in MemoryStore(vault).load().get("validated_memory", []) if isinstance(r, dict) and r.get("memory_id")}
        selected_items = []
        for item in bundle.selected:
            if item.source_type != "memory":
                continue
            record = records.get(item.candidate_id)
            if record is None:
                raise RuntimeError(f"corrected compiler returned unknown memory: {item.candidate_id}")
            selected_items.append(SelectedContextItem(
                id=item.candidate_id, source_type="memory", project_id=record.get("project_id") or None,
                memory_type=record["type"], status=record["status"], content=record["content"], score=0.0,
            ))
        revision = bundle.input_revisions.get("memory")
        return NormalizedEvaluationResult(
            task_id=task.task_id, provider_id=self.provider_id, selected_items=tuple(selected_items),
            source_memory_revision=revision if isinstance(revision, int) and not isinstance(revision, bool) else 0,
            project_id=task.project_id, retrieval_scope="default" if task.project_id is not None else "global",
            capabilities={"scope_isolation": "supported", "lifecycle_filtering": "supported",
                          "task_aware_ranking": "supported", "authority_resolution": "supported",
                          "conflict_resolution": "supported", "token_budgeting": "supported"},
        )


def _select(provider, row):
    task = SimpleNamespace(task_id=row["case_id"], project_id=row["project_id"], prompt=row["task_text"])
    with tempfile.TemporaryDirectory(prefix="ig01f-probe-") as directory:
        vault = Path(directory) / "vault"
        _write_vault(vault, row)
        result = _bounded(provider.select(task, vault))
        return [item.id for item in result.selected_items]


def main():
    rows = _load("dev") + _load("validation")
    existing = CompilerV2ContextProvider()
    corrected = CorrectedV2Provider()
    agg = {"existing": [], "corrected": []}
    per_phenomenon = {"existing": {}, "corrected": {}}
    failures = []
    for i, row in enumerate(rows):
        case = {
            "case_id": row["case_id"], "required_ids": row.get("required_ids", []),
            "useful_ids": row.get("useful_ids", row.get("acceptable_ids", [])),
            "forbidden_ids": row.get("forbidden_ids", []), "mandatory_ids": row.get("mandatory_ids", []),
        }
        phenomenon = row.get("phenomenon") or row.get("category") or "unknown"
        for label, provider in (("existing", existing), ("corrected", corrected)):
            try:
                ids = _select(provider, row)
            except Exception as exc:  # noqa: BLE001
                failures.append((label, row["case_id"], str(exc)[:200]))
                continue
            metrics = evaluate_retrieval_case(case, ids)
            agg[label].append(metrics)
            per_phenomenon[label].setdefault(phenomenon, []).append(metrics)
        if (i + 1) % 20 == 0:
            print(f"...{i + 1}/{len(rows)}", file=sys.stderr)

    def macro_f1(rows_):
        vals = []
        for r in rows_:
            f1 = r["metrics"].get("f1")
            if isinstance(f1, dict) and not f1.get("not_applicable"):
                vals.append(f1["value"])
        return sum(vals) / len(vals) if vals else None

    print("=== aggregate macro F1 ===")
    for label in ("existing", "corrected"):
        print(label, "n=", len(agg[label]), "macro_f1=", macro_f1(agg[label]))

    print("\n=== per-phenomenon macro F1 (existing vs corrected) ===")
    phenomena = sorted(set(per_phenomenon["existing"]) | set(per_phenomenon["corrected"]))
    for p in phenomena:
        e = macro_f1(per_phenomenon["existing"].get(p, []))
        c = macro_f1(per_phenomenon["corrected"].get(p, []))
        print(f"{p:30s} existing={e!s:>8.8} corrected={c!s:>8.8}")

    if failures:
        print(f"\n=== {len(failures)} failures ===")
        for label, cid, msg in failures[:10]:
            print(label, cid, msg)

    with open(OUTPUT_DIR / "raw_comparison.json", "w", encoding="utf-8") as f:
        json.dump({"existing": agg["existing"], "corrected": agg["corrected"]}, f)


if __name__ == "__main__":
    main()
