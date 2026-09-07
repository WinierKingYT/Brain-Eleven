# Brain-Eleven

Brain-Eleven is a local, privacy-first second-brain system with revisioned
canonical memory, project-scoped state, safe retrieval, and a non-injecting
context compiler.

The repository is currently in **Intelligence Graduation IG-00**. Phase 20 is
**FROZEN and LOCKED**; the existing V2 path remains shadow-only until the
evaluation and real-use gates in `INTELLIGENCE-GRADUATION.md` pass.

## Local checks

Use the repository virtual environment for repeatable checks:

```powershell
.venv\Scripts\python.exe -m pytest tests -m "not integration and not graduation" -q
.venv\Scripts\python.exe -m pytest tests -m "integration or graduation" -q
```

The API exposes `/health` when started through the supported local deployment
configuration. The API is a consumer of canonical memory; it is not a second
write authority.

Read `PROJECT-STATUS.md`, `RUNTIME-DATAFLOW.md`, and
`DOCUMENTATION-AUTHORITY.md` before relying on older phase documents.
