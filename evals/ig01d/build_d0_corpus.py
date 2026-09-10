"""Build the versioned, multilingual public retrieval corpus used by R3 D0.

The source material is restricted to the public DEV and TEST splits from
``corpus-v2``.  Each selected source task is rendered into three explicit
language strata.  The generated cases keep the source expectation labels but
use distinct task identities, so the probe can measure multilingual query
matching without touching HOLDOUT or production data.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT / "evals" / "corpus-v2"
TARGET_ROOT = ROOT / "evals" / "ig01d" / "public" / "ig-r3-d0-v1"
TARGET_PATH = TARGET_ROOT / "retrieval.jsonl"
METADATA_PATH = TARGET_ROOT / "metadata.json"
MANIFEST_PATH = TARGET_ROOT / "manifest.json"
SOURCE_COUNT = 40
LANGUAGES = ("en", "tr", "tr-en")


def _source_files() -> list[Path]:
    files = sorted(
        [*SOURCE_ROOT.joinpath("dev").glob("p15_*.json"),
         *SOURCE_ROOT.joinpath("test").glob("p15_*.json")],
        key=lambda path: path.as_posix(),
    )
    if len(files) < SOURCE_COUNT:
        raise RuntimeError("public corpus-v2 does not contain enough DEV/TEST cases")
    # Spread the sample over the stable source ordering and avoid selecting
    # any HOLDOUT path. This is a deterministic public-synthetic derivation.
    positions = [round(index * (len(files) - 1) / (SOURCE_COUNT - 1)) for index in range(SOURCE_COUNT)]
    return [files[position] for position in positions]


def _source_category(path: Path) -> str:
    match = re.match(r"p15_(?:v2_)?(.+?)_\d+\.json$", path.name)
    return match.group(1) if match else "relevance"


def _scenario(path: Path) -> str:
    match = re.search(r"_(\d+)\.json$", path.name)
    return match.group(1) if match else "0"


def _project(document: dict[str, Any]) -> str:
    return str((document.get("task") or {}).get("project_id") or "global")


def _english(category: str, project: str, scenario: str) -> str:
    templates = {
        "authority_future": "Record the future authority decision case for {project} scenario {scenario}.",
        "global_project": "Combine global engineering rules with {project} decisions for scenario {scenario}.",
        "noise": "Find essential context from a noise-heavy {project} vault scenario {scenario}.",
        "persistence": "How should Markdown and SQLite write ordering work in the Quick Note capture flow?",
        "project_isolation": "Retrieve only {project} context for isolation scenario {scenario}.",
        "relevance": "Select the reliable persistence rule for {project} relevance scenario {scenario}.",
        "conflict": "Select the non-conflicting current decision for {project} scenario {scenario}.",
        "lifecycle": "Use active {project} state while excluding completed lifecycle records {scenario}.",
        "supersession": "Resolve the authoritative replacement rule for {project} scenario {scenario}.",
        "ambiguity": "Answer only from global policy while the current project is ambiguous in case {scenario}.",
        "authority_traps": "Evaluate the authority traps decision in {project} scope; do not use foreign context.",
        "duplicate_semantics": "Select only active {project} context for the duplicate semantics evaluation case.",
        "malicious_input": "Select only active {project} context for the malicious input evaluation case.",
        "same_domain_wrong_project": "Evaluate the same-domain wrong-project decision in {project} scope; do not use foreign context.",
        "resolved_lifecycle": "Select a safe active decision for {project} while excluding resolved lifecycle records.",
        "basic_relevance": "Select only active {project} context for the basic relevance evaluation case.",
        "lexical_traps": "Select only active {project} context for the lexical traps evaluation case.",
        "cross_phase_traps": "Select only active {project} context for the cross-phase traps evaluation case.",
        "secret_forbidden": "Select only active {project} context while excluding forbidden secrets.",
        "state_relevance": "Select only active {project} context for the state relevance evaluation case.",
    }
    template = templates.get(category, "Select the relevant active context for {project} case {scenario}.")
    return template.format(project=project, scenario=scenario)


def _turkish(category: str, project: str, scenario: str) -> str:
    templates = {
        "authority_future": "{project} projesinin {scenario} numaralı gelecek yetki kararını kaydet.",
        "global_project": "Global mühendislik kurallarını {project} kararlarıyla birleştir; senaryo {scenario}.",
        "noise": "Gürültülü {project} kasasının {scenario} senaryosundan gerekli bağlamı bul.",
        "persistence": "Quick Note kaydetme akışında Markdown ve SQLite yazma sıralaması nasıl olmalı?",
        "project_isolation": "İzolasyon senaryosu {scenario} için yalnızca {project} bağlamını getir.",
        "relevance": "{project} için {scenario} numaralı önem senaryosunda güvenilir kalıcılık kuralını seç.",
        "conflict": "{project} için {scenario} numaralı çakışmayan güncel kararı seç.",
        "lifecycle": "Tamamlanmış yaşam döngüsü kayıtlarını dışarıda bırakarak {project} için aktif durumu kullan; kayıt {scenario}.",
        "supersession": "{project} için {scenario} numaralı yetkili yerine geçme kuralını çöz.",
        "ambiguity": "Mevcut proje belirsizken {scenario} numaralı vakada yalnızca global politikadan cevap ver.",
        "authority_traps": "Yabancı bağlamı kullanmadan {project} kapsamındaki yetki tuzakları kararını değerlendir.",
        "duplicate_semantics": "{project} için duplicate semantics değerlendirmesinde yalnızca aktif bağlamı seç.",
        "malicious_input": "{project} için kötü niyetli girdi değerlendirmesinde yalnızca aktif bağlamı seç.",
        "same_domain_wrong_project": "Yabancı proje bağlamını kullanmadan {project} kapsamındaki aynı alan yanlış proje kararını değerlendir.",
        "resolved_lifecycle": "Çözülmüş yaşam döngüsü kayıtlarını dışarıda bırakarak {project} için güvenli aktif kararı seç.",
        "basic_relevance": "{project} için temel önem değerlendirmesinde yalnızca aktif bağlamı seç.",
        "lexical_traps": "{project} için lexical traps değerlendirmesinde yalnızca aktif bağlamı seç.",
        "cross_phase_traps": "{project} için fazlar arası tuzaklar değerlendirmesinde yalnızca aktif bağlamı seç.",
        "secret_forbidden": "Yasak sırları dışarıda bırakarak {project} için yalnızca aktif bağlamı seç.",
        "state_relevance": "{project} için durum önem değerlendirmesinde yalnızca aktif bağlamı seç.",
    }
    template = templates.get(category, "{project} için {scenario} numaralı vakada ilgili aktif bağlamı seç.")
    return template.format(project=project, scenario=scenario)


def _mixed(category: str, project: str, scenario: str) -> str:
    return _english(category, project, scenario).removesuffix(".") + "; yabancı proje bağlamını kullanma."


def _render(category: str, project: str, scenario: str, language: str) -> str:
    if language == "en":
        return _english(category, project, scenario)
    if language == "tr":
        return _turkish(category, project, scenario)
    return _mixed(category, project, scenario)


def build() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    metadata: dict[str, dict[str, Any]] = {}
    source_ids: list[str] = []
    for source_path in _source_files():
        source = json.loads(source_path.read_text(encoding="utf-8"))
        source_id = str(source["task_id"])
        source_ids.append(source_id)
        category = _source_category(source_path)
        project = _project(source)
        scenario = _scenario(source_path)
        for language in LANGUAGES:
            row = deepcopy(source)
            row["task_id"] = f"ig-r3-d0-{language}-{source_id}"
            row["task"]["prompt"] = _render(category, project, scenario, language)
            metadata[row["task_id"]] = {
                "language": language,
                "source_corpus": "corpus-v2",
                "source_split": source_path.parent.name,
                "source_case_id": source_id,
                "variant": language,
                "synthetic": True,
            }
            rows.append(row)
    manifest = {
        "schema_version": 1,
        "corpus_version": "ig-r3-d0-v1",
        "dataset_class": "PUBLIC_SYNTHETIC",
        "source_corpus": "corpus-v2",
        "source_splits": ["dev", "test"],
        "holdout_included": False,
        "source_case_count": len(source_ids),
        "case_count": len(rows),
        "language_counts": {language: len(source_ids) for language in LANGUAGES},
        "languages": list(LANGUAGES),
        "source_case_ids_sha256": hashlib.sha256("\n".join(source_ids).encode("utf-8")).hexdigest(),
        "generator": "evals/ig01d/build_d0_corpus.py",
    }
    return rows, metadata, manifest


def main() -> int:
    rows, metadata, manifest = build()
    TARGET_ROOT.mkdir(parents=True, exist_ok=True)
    TARGET_PATH.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(TARGET_PATH), "case_count": len(rows), "language_counts": manifest["language_counts"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
