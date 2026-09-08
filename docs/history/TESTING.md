# Brain-Eleven Test Suite

## Overview

Regression test suite for Brain-Eleven v3 memory system. Tests cover:

- Memory Compiler (extraction, parsing, deduplication)
- Memory Validator (conflict detection, quality scoring, persistence)
- Memory Lifecycle (resolve/supersede, ULID lookup, provenance)
- Data integrity (atomic writes, migration, backup)

## Quick Start

### Install Dependencies

```bash
pip install pytest
```

### Run All Tests

```bash
pytest tests/ -v
```

### Run Specific Test File

```bash
pytest tests/test_memory_compiler.py -v
pytest tests/test_memory_validator.py -v
pytest tests/test_memory_lifecycle.py -v
```

### Run Specific Test Class

```bash
pytest tests/test_memory_compiler.py::TestMemoryCompiler -v
```

### Run Specific Test

```bash
pytest tests/test_memory_compiler.py::TestMemoryCompiler::test_extract_multi_date_entries -v
```

## Test Coverage

### Memory Compiler Tests

- **Multi-date parsing**: Parse Daily.md with multiple date entries
- **Source ID generation**: Verify date-aware source_id format
- **Extraction accuracy**: Test decision, lesson, open_loop extraction
- **Deduplication**: Remove identical candidates
- **Quality validation**: Filter low-quality entries
- **Edge cases**: Empty Daily, malformed sections, special characters

### Memory Validator Tests

- **Candidate loading**: Load from compiled-memory.json
- **Conflict detection**: Cross-history contradiction detection
- **Fingerprint consistency**: SHA256-based dedup key
- **Merge operations**: Preserve lifecycle status from prior
- **Quality scoring**: Novelty calculation and thresholds
- **Atomic persistence**: Temp-validate-rename pattern
- **Edge cases**: First run (no prior), corrupted JSON

### Memory Lifecycle Tests

- **Active memory listing**: Filter by status
- **Resolve by ULID**: Immutable ID lookup
- **Supersede operations**: Create provenance links
- **Provenance tracing**: Follow supersession chains
- **Atomic saves**: Backup creation and JSON validation
- **Legacy compatibility**: Integer ID fallback
- **Error handling**: Non-existent memory handling

## Test Fixtures

Tests use temporary vault structures in pytest's `tmp_path`:

```
test-vault/
├── 🔮 Companion/
│   └── Daily.md (multi-date sample)
├── 🗂️ Proje Notları/
│   └── Kararlar/
└── .claude/
    ├── compiled-memory.json
    └── validated-memory.json
```

## Expected Results

All tests should pass with no warnings:

```
tests/test_memory_compiler.py::TestMemoryCompiler::test_extract_multi_date_entries PASSED
tests/test_memory_compiler.py::TestMemoryCompiler::test_source_id_format PASSED
...
======================== 30+ passed in 2.34s ========================
```

## Performance Baselines

Current performance targets (on development machine):

| Operation | Target | Actual |
|-----------|--------|--------|
| Parse 23 Daily entries | < 2s | ~0.1s |
| Extract 5 candidates | < 1s | ~0.05s |
| Conflict detection (5 new vs 1 prior) | < 1s | ~0.02s |
| Quality scoring (5 candidates) | < 1s | ~0.05s |
| Atomic write (40KB JSON) | < 1s | ~0.1s |

## Continuous Integration

To integrate with CI/CD:

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - run: pip install pytest
      - run: pytest tests/ -v
```

## Adding New Tests

### Template

```python
class TestNewFeature:
    """Test suite for new feature"""

    def test_basic_functionality(self, temp_vault, sample_data):
        """Test basic behavior"""
        # Arrange
        manager = SomeManager(str(temp_vault))

        # Act
        result = manager.do_something()

        # Assert
        assert result == expected
```

### Guidelines

- Use fixtures for setup (temp_vault, sample_data)
- Follow AAA pattern (Arrange, Act, Assert)
- Test happy path + edge cases
- Use descriptive test names
- Add docstrings explaining what's tested

## Troubleshooting

### Import Errors

If tests fail with import errors:

```bash
# Add scripts to path in tests/__init__.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
```

### File Not Found Errors

Tests create temporary vaults in `tmp_path`. If a test assumes a specific file structure, ensure the fixture creates it:

```python
@pytest.fixture
def sample_daily_multi_date(temp_vault):
    daily_file = temp_vault / "🔮 Companion" / "Daily.md"
    daily_file.write_text(content)
    return daily_file
```

### Encoding Issues

Use `encoding='utf-8'` explicitly:

```python
file.write_text(content, encoding='utf-8')
with open(file, encoding='utf-8') as f:
    data = json.load(f)
```

## Next Steps

1. **Run full test suite**: `pytest tests/ -v`
2. **Aim for 80%+ coverage**: `pytest --cov=scripts tests/`
3. **Add CI/CD pipeline**: Set up GitHub Actions
4. **Performance profiling**: Track regression in performance baselines
5. **Continuous testing**: Run tests before each commit

---

**Last Updated:** 2026-08-29  
**Test Count:** 30+ tests across 3 modules  
**Estimated Runtime:** ~2-3 seconds  
**Coverage Target:** 80%+
