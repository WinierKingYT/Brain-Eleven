"""Deterministic, offline evaluation contracts for Brain-Eleven."""

from .baseline import (
    BASELINE_CAPABILITIES,
    BASELINE_PROVIDER_ID,
    BaselineAdapterError,
    BaselineContextProvider,
    normalize_context_compiler_output,
)
from .contracts import (
    EvaluationResultContractError,
    NormalizedEvaluationResult,
    SelectedContextItem,
)
from .metrics import (
    CaseEvaluation,
    CaseMetrics,
    EvaluationMetricError,
    evaluate_selection,
)
from .reporting import (
    EVALUATION_REPORT_SCHEMA_VERSION,
    EVALUATION_REPORT_TYPE,
    REGRESSION_COMPARISON_TYPE,
    EvaluationReportError,
    build_evaluation_report,
    compare_evaluation_reports,
    read_evaluation_report,
    write_evaluation_report,
)
from .schema import (
    CorpusValidationError,
    GoldenTask,
    VaultFixture,
    load_fixture,
    load_tasks,
    validate_fixture_documents,
    validate_task_documents,
)
from .fixture_generator import (
    FixtureGenerationError,
    GeneratedVault,
    build_vault,
    build_vault_from_path,
)

__all__ = [
    "BASELINE_CAPABILITIES",
    "BASELINE_PROVIDER_ID",
    "BaselineAdapterError",
    "BaselineContextProvider",
    "CorpusValidationError",
    "CaseEvaluation",
    "CaseMetrics",
    "EvaluationResultContractError",
    "EvaluationMetricError",
    "EvaluationReportError",
    "EVALUATION_REPORT_SCHEMA_VERSION",
    "EVALUATION_REPORT_TYPE",
    "FixtureGenerationError",
    "GoldenTask",
    "GeneratedVault",
    "NormalizedEvaluationResult",
    "REGRESSION_COMPARISON_TYPE",
    "SelectedContextItem",
    "VaultFixture",
    "build_vault",
    "build_vault_from_path",
    "build_evaluation_report",
    "compare_evaluation_reports",
    "evaluate_selection",
    "load_fixture",
    "load_tasks",
    "normalize_context_compiler_output",
    "read_evaluation_report",
    "validate_fixture_documents",
    "validate_task_documents",
    "write_evaluation_report",
]
