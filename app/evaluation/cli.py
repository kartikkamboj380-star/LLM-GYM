"""Run an evaluation dataset against configured providers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import Settings, load_env_file
from app.providers import create_provider

from .evaluator import compare_providers, load_dataset, markdown_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, help="JSON evaluation dataset")
    parser.add_argument("--providers", default="mock", help="Comma-separated provider IDs")
    parser.add_argument("--output", default="data/evaluation.md", help=".md or .json report path")
    args = parser.parse_args()
    load_env_file()
    settings = Settings.from_env()
    cases = load_dataset(args.dataset)
    providers = [create_provider(name.strip(), settings) for name in args.providers.split(",") if name.strip()]
    report = compare_providers(providers, cases)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() == ".json":
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        output.write_text(markdown_report(report), encoding="utf-8")
    print(f"Wrote {output}")
    for result in report["results"]:
        print(f"{result['provider']}: {result['passed']}/{result['total']} ({result['accuracy']:.1%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
