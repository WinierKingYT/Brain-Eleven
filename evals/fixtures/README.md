# Synthetic vault fixtures

Fixtures describe a small canonical-memory subset with stable synthetic IDs.
They are deliberately separate from production vaults so the evaluation system
cannot read a user's real memory while running in CI.

`phase15-contract.json` is the first fixture. The deterministic generator can
build it into a fresh local vault without touching a real vault:

```powershell
python -m evals.fixture_generator evals/fixtures/phase15-contract.json C:\temp\brain-eleven-eval --seed 17 --noise-count 50
```

The target must be new or empty. The output contains canonical memory plus a
fixture manifest; derived graph, cache, and bootstrap state are intentionally
absent so later packages can prove that they rebuild correctly.
