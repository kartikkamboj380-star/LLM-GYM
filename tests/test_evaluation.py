import json
import tempfile
import unittest
from pathlib import Path

from app.evaluation import EvaluationCase, compare_providers, evaluate_provider, load_dataset, markdown_report
from app.providers.base import AIProvider, ChatResponse


class StubProvider(AIProvider):
    def __init__(self, name="stub", answer="Paris"):
        self.name = name
        self.answer = answer

    def generate(self, messages, system_prompt=None):
        return ChatResponse(self.answer, self.name)


class FailingProvider(AIProvider):
    name = "failing"

    def generate(self, messages, system_prompt=None):
        raise RuntimeError("sensitive details must not enter report")


class EvaluationTests(unittest.TestCase):
    def test_match_strategies(self):
        self.assertTrue(EvaluationCase("1", "p", "Paris").passes("paris"))
        self.assertTrue(EvaluationCase("2", "p", "capital is Paris", "contains").passes("The capital is Paris, France"))
        self.assertTrue(EvaluationCase("3", "p", r"\b\d{4}\b", "regex").passes("It was 2026"))

    def test_evaluation_and_markdown_report(self):
        cases = [EvaluationCase("capital", "Capital of France?", "Paris")]
        result = evaluate_provider(StubProvider(), cases)
        self.assertEqual(1, result["accuracy"])
        report = compare_providers([StubProvider(), StubProvider("other", "London")], cases)
        markdown = markdown_report(report)
        self.assertIn("| stub | 1 | 1 | 100.0%", markdown)
        self.assertIn("| other | 0 | 1 | 0.0%", markdown)

    def test_provider_failure_is_contained_and_sanitized(self):
        result = evaluate_provider(FailingProvider(), [EvaluationCase("1", "p", "x")])
        self.assertEqual("RuntimeError", result["cases"][0]["error"])
        self.assertNotIn("sensitive", str(result))

    def test_dataset_validation_and_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            path.write_text(json.dumps([{"id": "one", "prompt": "Say one", "expected": "one", "match": "contains"}]))
            self.assertEqual("one", load_dataset(path)[0].id)
            path.write_text("[]")
            with self.assertRaises(ValueError):
                load_dataset(path)


if __name__ == "__main__":
    unittest.main()
