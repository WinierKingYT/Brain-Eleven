"""Deterministic content-free W-09A report orchestration."""
from __future__ import annotations
import argparse, hashlib, json, tempfile
from pathlib import Path
from typing import Any
from evals.baseline import BaselineContextProvider
from evals.compiler_v2_provider import CompilerV2ContextProvider
from evals.fixture_generator import build_vault
from evals.w09a.evaluation import CORPUS_ROOT, FIXTURE, candidate_fingerprint, corpus_fingerprint, load_public_tasks, source_fingerprint
from .metrics import metric_summary

def _hash(obj): return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()

def run_report(*, split="public", k=10, seed=0, provider="v1", root=CORPUS_ROOT, fixture=FIXTURE):
    if split not in {"public","holdout"}: raise ValueError("invalid split")
    tasks=load_public_tasks(root=root, fixture_path=fixture, split=split)
    if split=="holdout" and root.resolve()!=CORPUS_ROOT.resolve(): raise ValueError("holdout root mismatch")
    adapter=BaselineContextProvider() if provider=="v1" else CompilerV2ContextProvider() if provider=="v2" else None
    if adapter is None: return {"evaluation_status":"unavailable","quality":"unavailable","measurement":"incomplete","promotion":"blocked","reason_code":"PROVIDER_UNSUPPORTED"}
    with tempfile.TemporaryDirectory(prefix="w09a-") as temp:
        vault=build_vault(__import__('evals.schema',fromlist=['load_fixture']).load_fixture(fixture),Path(temp),seed=seed)
        candidate_ids=tuple(vault.memory_ids); rows=[]; statuses=[]
        for task in tasks:
            answerability=getattr(task,"answerability",None)
            if isinstance(answerability,dict) and answerability.get("status")=="NO": statuses.append("excluded_answerability"); continue
            try:
                result=adapter.select(task,vault.root)
                selected=tuple(i.id for i in result.selected_items)
                m=metric_summary(selected,task.required,task.useful,task.required,k=k)
                rows.append({"task_id":task.task_id,"selected_count":m.selected_count,"precision":m.precision,"recall":m.recall,"f1":m.f1,"mrr":m.mrr,"mandatory_recall":m.mandatory_recall,"noise_ratio":m.noise_ratio,"token_waste":m.token_waste})
            except Exception: statuses.append("invalid")
        quality="measured" if rows else "unavailable"
        return {"schema_version":1,"split":split,"provider_id":adapter.provider_id,"provider_config_id":adapter.provider_id+"@1","seed":seed,"k":k,"normalization":"ordered_unique_first_k","tie_breaking":"provider_order","corpus_fingerprint":corpus_fingerprint(root,split=split),"source_fingerprint":source_fingerprint(),"candidate_fingerprint":candidate_fingerprint(vault.root),"case_ids":[t.task_id for t in tasks],"case_count":len(tasks),"rows":rows,"statuses":statuses,"evaluation_status":"verified" if quality=="measured" else "invalid","quality":quality,"measurement":"complete" if not statuses else "incomplete","promotion":"blocked" if statuses or quality!="measured" else "eligible","report_hash":_hash(rows)}

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--split",choices=("public","holdout"),default="public"); p.add_argument("--provider",choices=("v1","v2"),default="v1"); p.add_argument("--output",type=Path,required=True); a=p.parse_args(argv)
    report=run_report(split=a.split,provider=a.provider); a.output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf-8"); return 0

if __name__ == "__main__": raise SystemExit(main())
