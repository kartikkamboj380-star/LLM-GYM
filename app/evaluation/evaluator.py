"""Dataset evaluation, model comparison, and reproducible report generation."""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from app.providers.base import AIProvider, Message


@dataclass(frozen=True)
class EvaluationCase:
    id: str
    prompt: str
    expected: str
    match: str = "exact"
    case_sensitive: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "EvaluationCase":
        if not all(isinstance(data.get(field), str) and data[field].strip() for field in ("id", "prompt", "expected")):
            raise ValueError("Every evaluation case needs non-empty id, prompt, and expected strings")
        match = data.get("match", "exact")
        if match not in {"exact", "contains", "regex"}:
            raise ValueError("Evaluation match must be exact, contains, or regex")
        if match == "regex":
            re.compile(data["expected"])
        return cls(data["id"], data["prompt"], data["expected"], match, bool(data.get("case_sensitive", False)))

    def passes(self, response: str) -> bool:
        actual_value = response.strip()
        expected_value = self.expected.strip()
        if not self.case_sensitive:
            actual_value = actual_value.casefold()
            expected_value = expected_value.casefold()
        if self.match == "exact":
            return actual_value == expected_value
        if self.match == "contains":
            return expected_value in actual_value
        flags = 0 if self.case_sensitive else re.IGNORECASE
        return re.search(self.expected, response, flags) is not None


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    latency_ms: float
    response: str = ""
    error: str | None = None


def load_dataset(path: str | Path) -> list[EvaluationCase]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("Evaluation dataset must be a non-empty JSON array")
    cases = [EvaluationCase.from_dict(item) for item in data]
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Evaluation case IDs must be unique")
    return cases


def evaluate_provider(provider: AIProvider, cases: Iterable[EvaluationCase]) -> dict:
    results = []
    for case in cases:
        started = time.perf_counter()
        try:
            response = provider.generate([Message(role="user", content=case.prompt)])
            elapsed = (time.perf_counter() - started) * 1000
            results.append(CaseResult(case.id, case.passes(response.content), round(elapsed, 3), response.content))
        except Exception as exc:
            # One failed request should not discard the rest of a comparison report.
            elapsed = (time.perf_counter() - started) * 1000
            results.append(CaseResult(case.id, False, round(elapsed, 3), error=type(exc).__name__))
    case_list = list(results)
    passed = sum(result.passed for result in case_list)
    total = len(case_list)
    return {
        "provider": provider.name,
        "total": total,
        "passed": passed,
        "accuracy": round(passed / total, 4) if total else 0,
        "average_latency_ms": round(sum(result.latency_ms for result in case_list) / total, 3) if total else 0,
        "cases": [asdict(result) for result in case_list],
    }


def compare_providers(providers: list[AIProvider], cases: list[EvaluationCase]) -> dict:
    if not providers:
        raise ValueError("At least one provider is required")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "dataset_size": len(cases),
        "results": [evaluate_provider(provider, cases) for provider in providers],
    }


def markdown_report(report: dict) -> str:
    lines = [
        "# LLM-GYM model evaluation",
        "",
        f"Generated: {report['generated_at']}  ",
        f"Dataset size: {report['dataset_size']}",
        "",
        "| Provider | Passed | Total | Accuracy | Average latency (ms) |",
        "|---|---:|---:|---:|---:|",
    ]
    for result in report["results"]:
        lines.append(
            f"| {result['provider']} | {result['passed']} | {result['total']} | "
            f"{result['accuracy']:.1%} | {result['average_latency_ms']:.3f} |"
        )
    lines.extend(["", "## Case details", ""])
    for result in report["results"]:
        lines.extend(["", f"### {result['provider']}", "", "| Case | Result | Latency (ms) | Error |", "|---|---|---:|---|"])
        for case in result["cases"]:
            lines.append(
                f"| {case['case_id']} | {'PASS' if case['passed'] else 'FAIL'} | "
                f"{case['latency_ms']:.3f} | {case.get('error') or ''} |"
            )
    lines.extend(["", "Latency includes local processing and, for external providers, network time. No fine-tuning is performed.", ""])
    return "\n".join(lines)
