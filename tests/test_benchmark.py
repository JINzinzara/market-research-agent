"""Fixture-based harness checks; these are not real-model benchmark scores."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from market_agent.benchmark import (QUALITY_FIELDS, Review, load_benchmark, run_benchmark,
                                    score_reviews, source_coverage)
from market_agent.runtime import ResearchRequest
from test_web_research import RESPONSE


class BenchmarkTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_runner_checkpoints_real_mode_without_exposing_references_to_model(self):
        requests = []
        def handler(request):
            body = json.loads(request.content)
            requests.append(body)
            self.assertNotIn("reference_answer", body["input"])
            self.assertNotIn("reference_urls", body["input"])
            return httpx.Response(200, json=RESPONSE)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            with patch.dict("os.environ", {"OPENAI_API_KEY": "unit-test-secret"}), patch(
                "market_agent.runtime.httpx.AsyncHTTPTransport", return_value=httpx.MockTransport(handler)
            ):
                report = await run_benchmark(limit=2, checkpoint=path)
            self.assertEqual(len(requests), 2)
            self.assertTrue(report["complete"])
            self.assertEqual(report["event_groups"], 1)
            self.assertEqual(report["operational_completed"], 2)
            self.assertEqual(report["quality"]["answer_correct"]["reviewed"], 0)
            self.assertIsNone(report["quality"]["answer_correct"]["rate_all_cases"])
            self.assertNotIn("passed", report)
            for row in report["cases"]:
                self.assertEqual(row["run"]["request"]["mode"], "live")
                self.assertTrue(row["run"]["request"]["web"])
                self.assertEqual(row["run"]["documents"], [])
            reviews = json.loads(path.with_suffix(".reviews.json").read_text())
            self.assertEqual(len(reviews["reviews"]), 2)
            self.assertEqual(reviews["report_sha256"], sha256(path.read_bytes()).hexdigest())
            self.assertTrue(path.with_suffix(".md").exists())
            reviews["reviews"][0].update(reviewer="Synthetic test reviewer", notes="Fixture-only scoring test.",
                                          **dict.fromkeys(QUALITY_FIELDS, True))
            path.with_suffix(".reviews.json").write_text(json.dumps(reviews))
            scored = score_reviews(path, path.with_suffix(".reviews.json"), Path(directory) / "scored.json")
            self.assertEqual(scored["quality"]["answer_correct"]["passed"], 1)
            self.assertIsNone(scored["quality"]["answer_correct"]["rate_all_cases"])
            with self.assertRaisesRegex(ValueError, "human reviews"):
                await run_benchmark(limit=2, checkpoint=path)
            reviews["report_sha256"] = "not-the-original-report"
            path.with_suffix(".reviews.json").write_text(json.dumps(reviews))
            with self.assertRaisesRegex(ValueError, "different report"):
                score_reviews(path, path.with_suffix(".reviews.json"), Path(directory) / "bad.json")

    async def test_missing_key_and_invalid_budgets_never_call_network(self):
        with patch.dict("os.environ", {}, clear=True), patch.object(
            httpx.AsyncHTTPTransport, "handle_async_request", side_effect=AssertionError("no network")
        ):
            with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY"):
                await run_benchmark(limit=1)
            for kwargs in ({"limit": 0}, {"limit": 999}, {"repeats": 0}, {"repeats": True}):
                with self.assertRaises(ValueError):
                    await run_benchmark(**kwargs)

    async def test_provider_rate_limit_stops_the_batch_without_calling_other_cases(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "unit-test-secret"}), patch(
            "market_agent.runtime.httpx.AsyncHTTPTransport", return_value=httpx.MockTransport(
                lambda request: httpx.Response(429, json={"error": "test rate limit"}))
        ):
            report = await run_benchmark(limit=2)
        self.assertEqual((report["total"], report["planned_total"]), (1, 2))
        self.assertFalse(report["complete"])
        self.assertEqual(report["summary"]["live_llm_calls"], 1)
        self.assertIn("stop_reason", report)
        self.assertEqual(report["quality"]["answer_correct"]["total"], 2)


class BenchmarkDataTests(unittest.TestCase):
    def test_pilot_is_paired_real_document_data_and_live_is_the_default(self):
        data = load_benchmark()
        self.assertEqual(len(data["cases"]), 12)
        groups = {}
        for case in data["cases"]:
            groups.setdefault(case["event_id"], set()).add(case["language"])
            self.assertTrue(all(url.startswith("https://") for url in case["reference_urls"]))
        self.assertEqual(len(groups), 6)
        self.assertTrue(all(languages == {"ko", "en"} for languages in groups.values()))
        default = ResearchRequest(question="Find the official policy release")
        self.assertEqual((default.mode, default.planner, default.web), ("live", "openai", True))

    def test_reference_url_coverage_is_exact_and_distinct_from_claim_support(self):
        cited = "https://www.example.org/release?utm_source=test#table"
        consulted = "https://example.org/second"
        record = {"result": {"sources": [{"source_id": "web-1", "url": cited}], "source_ids": ["web-1"]},
                  "llm_responses": [{"output": [{"type": "web_search_call", "action": {
                      "sources": [{"url": consulted}]}}]}]}
        case = {"reference_urls": ["https://example.org/release", consulted, "https://example.org/release-else"]}
        result = source_coverage(case, record)
        self.assertEqual((result["consulted_hits"], result["cited_hits"], result["gold_urls"]), (2, 1, 3))

    def test_semantic_grades_require_reviewer_and_evidence_notes(self):
        with self.assertRaises(ValueError):
            Review(evaluation_id="one", run_id="test", answer_correct=True)

    def test_duplicate_dataset_ids_are_rejected(self):
        data = load_benchmark()
        data["cases"].append(deepcopy(data["cases"][0]))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "unique"):
                load_benchmark(path)
