"""Evaluation denominators, failure latency, and missing model usage remain honest."""

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from market_agent.evaluate import case_checks, evaluate, save_report, summarize_runs


class EvaluationTests(unittest.IsolatedAsyncioTestCase):
    async def test_dimensions_count_expected_numbers_not_only_present_sources(self):
        report = await evaluate()
        self.assertEqual(report["dimensions"]["status"], {"passed": 20, "total": 20})
        self.assertEqual(report["summary"]["live_llm_calls"], 0)
        self.assertEqual(report["summary"]["tokens"]["input"]["total"], 0)
        case = deepcopy(report["cases"][0])
        case["run"]["result"]["sources"] = []
        checks = case_checks(case["expected"], case["run"])
        numeric = [check for check in checks if check["metric"] == "numerical_return"]
        self.assertEqual(len(numeric), 1)
        self.assertFalse(numeric[0]["passed"])


class UsageTests(unittest.TestCase):
    def test_markdown_output_cannot_overwrite_raw_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.md"
            path.write_text("existing report")
            with self.assertRaisesRegex(ValueError, "json"):
                save_report({}, path)
            self.assertEqual(path.read_text(), "existing report")

    def test_failed_runs_count_toward_latency_and_missing_usage_is_unknown(self):
        records = [
            {"metrics": {"duration_ms": 100, "http_calls": 1, "network_attempts": 1,
                         "live_llm_calls": 1, "usage": [{"prompt_eval_count": 12, "eval_count": 3}]}},
            {"metrics": {"duration_ms": 900, "http_calls": 1, "network_attempts": 1,
                         "live_llm_calls": 1, "usage": []}},
        ]
        summary = summarize_runs(records)
        self.assertEqual(summary["latency_ms"]["sum"], 1000)
        self.assertEqual(summary["latency_ms"]["mean"], 500)
        self.assertIsNone(summary["tokens"]["input"]["total"])
        self.assertEqual(summary["tokens"]["input"]["observed_total"], 12)
        self.assertEqual(summary["tokens"]["input"]["missing_calls"], 1)
        self.assertIsNone(summary["operating_cost_usd"])

    def test_replayed_usage_is_not_new_model_usage(self):
        record = {"metrics": {"duration_ms": 1, "http_calls": 1, "network_attempts": 0,
                              "live_llm_calls": 0, "usage": [{"prompt_eval_count": 100, "eval_count": 50}]}}
        summary = summarize_runs([record])
        self.assertEqual(summary["live_llm_calls"], 0)
        self.assertEqual(summary["tokens"]["input"]["total"], 0)
