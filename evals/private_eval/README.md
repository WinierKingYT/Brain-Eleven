# Private real-use evaluation

`evals/private_eval/` contains only the versioned, content-free evaluator and
telemetry contracts. Real task annotations and reports belong under the
gitignored `evals/private/` directory.

Records may contain stable task/project/memory identifiers and one of
`required`, `helpful`, `noise`, or `forbidden` labels. They must not contain
prompts, memory text, transcripts, secrets, or free-form notes.

Examples:

```powershell
python -m evals.private_eval annotate --path evals/private/case-001.json --case-id case-001 --task-id task-001 --memory-id mem-001 --label required
python -m evals.private_eval score --path evals/private/case-001.json --selected-id mem-001
python -m evals.private_eval validate --root evals/private
python -m evals.private_eval usage --vault . --memory-id mem-001 --event selected
```

Usage telemetry is derived and non-authoritative. It records observable
retrieved/selected/rendered/reference/feedback events only; it never infers a
model's hidden `used_count` and cannot change memory truth, scope, lifecycle,
or ranking policy.
