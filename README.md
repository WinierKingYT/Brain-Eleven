# Brain-Eleven

Brain-Eleven is a local, privacy-first second-brain system with revisioned
canonical memory, project-scoped state, safe retrieval, and a non-injecting
context compiler.

The repository has closed **Intelligence Graduation IG01-C**. Phase 20 is
**FROZEN and LOCKED**; the existing V2 path remains shadow-only until the
evaluation and real-use gates in `INTELLIGENCE-GRADUATION.md` pass. IG01-C's
production-independent evaluator, anti-gaming controls and safety report are
closed with independent `SHIP`. IG01-D baseline measurement is the next
bounded package but is not started in this turn. Production intelligence
tuning, V2 promotion and Phase 20 work remain closed until the later packages
pass their independent gates.

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
