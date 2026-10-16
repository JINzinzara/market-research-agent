"""Exercise real workflow paths, frozen responses, and evaluation sensitivity."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from market_agent.evaluate import check_case, evaluate
from market_agent.records import ReplayMismatch, RunStore
from market_agent.runtime import ResearchRequest, baseline_plan, planner_schema, replay_run, run_research
from market_agent.schema import ResearchResult


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_demo_and_replay_never_use_live_transport(self):
        with patch.object(httpx.AsyncHTTPTransport, "handle_async_request", side_effect=AssertionError("network forbidden")):
            for scenario, status in [("none", "completed"), ("eth_timeout", "partial"), ("all_timeout", "error")]:
                with self.subTest(scenario=scenario):
                    record = await run_research(ResearchRequest(question="BTC ETH BNB 7d", scenario=scenario))
                    self.assertEqual(record["result"]["status"], status)
                    self.assertEqual(record["metrics"]["http_calls"], 3)
                    self.assertEqual(record["metrics"]["network_attempts"], 0)
                    ResearchResult.model_validate_json(json.dumps(record["result"]))
                    replay = await replay_run(record)
                    self.assertTrue(replay["comparison"]["same_result"])
                    self.assertEqual(replay["replay_of"], record["run_id"])
                    self.assertEqual(replay["metrics"]["network_attempts"], 0)

    async def test_replay_rejects_wrong_parameters_and_unused_responses(self):
        record = await run_research(ResearchRequest(question="BTC 7d"))
        wrong = deepcopy(record)
        wrong["http"][0]["url"] += "&surprise=1"
        with self.assertRaises(ReplayMismatch):
            await replay_run(wrong)
        unused = deepcopy(record)
        unused["http"].append(deepcopy(unused["http"][0]))
        with self.assertRaises(ReplayMismatch):
            await replay_run(unused)
        missing = deepcopy(record); missing["http"] = []
        with self.assertRaises(ReplayMismatch):
            await replay_run(missing)

    async def test_second_collection_round_only_retries_documents(self):
        record = await run_research(ResearchRequest(question="캔들 문서"))
        self.assertEqual(record["metrics"]["collection_rounds"], 2)
        self.assertEqual(record["metrics"]["http_calls"], 0)
        self.assertEqual(len(record["trace"]), 2)
        self.assertTrue(record["result"]["sources"])
        unknown = await run_research(ResearchRequest(question="문서 zzzunknown"))
        self.assertEqual(unknown["result"]["sources"], [])
        self.assertEqual(unknown["metrics"]["collection_rounds"], 1)

    async def test_rate_limit_stops_remaining_symbol_requests(self):
        record = await run_research(ResearchRequest(question="BTC ETH BNB 7d", scenario="eth_rate_limit"))
        self.assertEqual(record["result"]["status"], "partial")
        self.assertEqual(record["metrics"]["http_calls"], 2)
        self.assertEqual([failure["type"] for failure in record["failures"]], ["HTTPStatusError", "SkippedAfterRateLimit"])
        self.assertTrue((await replay_run(record))["comparison"]["same_result"])

    async def test_model_planner_records_usage_without_reasoning(self):
        plan = baseline_plan("BTC 7d").model_dump()
        response = {"model": "qwen3:8b", "done": True,
                    "message": {"role": "assistant", "content": json.dumps(plan), "thinking": "private thought"}}
        with patch("market_agent.runtime.httpx.AsyncHTTPTransport", return_value=httpx.MockTransport(
            lambda request: httpx.Response(200, json=response))):
            record = await run_research(ResearchRequest(question="BTC 7d", planner="ollama"))
        self.assertEqual(record["result"]["status"], "completed")
        self.assertEqual(record["metrics"]["llm_calls"], 1)
        self.assertEqual(record["metrics"]["live_llm_calls"], 1)
        self.assertIsNone(record["metrics"]["usage"][0]["eval_count"])
        self.assertNotIn("private thought", json.dumps(record))
        replay = await replay_run(record)
        self.assertTrue(replay["comparison"]["same_result"])
        self.assertEqual(replay["metrics"]["live_llm_calls"], 0)
        self.assertEqual(replay["metrics"]["replayed_http_calls"], 2)

    async def test_model_cannot_silently_change_requested_symbols(self):
        response = {"done": True, "message": {"content": json.dumps({
            "action": "research", "symbols": ["ETHUSDT"], "period": "7d"})}}
        with patch("market_agent.runtime.httpx.AsyncHTTPTransport", return_value=httpx.MockTransport(
            lambda request: httpx.Response(200, json=response))):
            record = await run_research(ResearchRequest(question="BTC 7d", planner="ollama"))
        self.assertEqual(record["result"]["status"], "error")
        self.assertEqual(record["metrics"]["http_calls"], 1)
        self.assertEqual(record["result"]["sources"], [])

    async def test_model_contract_exposes_null_message_and_still_rejects_invalid_output(self):
        requests = []
        def handler(request):
            requests.append(json.loads(request.content))
            plan = baseline_plan("BTC 7d").model_dump()
            plan["message"] = "Missing symbol or period: clarify."
            return httpx.Response(200, json={"done": True, "message": {"content": json.dumps(plan)}})
        with patch("market_agent.runtime.httpx.AsyncHTTPTransport", return_value=httpx.MockTransport(handler)):
            record = await run_research(ResearchRequest(question="BTC 7d", planner="ollama"))
        self.assertEqual(requests[0]["format"]["properties"]["message"], {"type": "null"})
        self.assertEqual(requests[0]["format"]["properties"]["action"]["enum"], ["research"])
        self.assertEqual(record["result"]["status"], "error")
        self.assertIn("ValidationError", record["result"]["answer"])
        self.assertEqual(record["metrics"]["http_calls"], 1)

    async def test_model_symbol_order_is_not_a_plan_error(self):
        response = {"done": True, "message": {"content": json.dumps({
            "action": "research", "symbols": ["ETHUSDT", "BTCUSDT"], "period": "7d"})}}
        with patch("market_agent.runtime.httpx.AsyncHTTPTransport", return_value=httpx.MockTransport(
            lambda request: httpx.Response(200, json=response))):
            record = await run_research(ResearchRequest(question="BTC ETH 7d", planner="ollama"))
        self.assertEqual(record["result"]["status"], "completed")

    async def test_twenty_development_cases_and_oracle_catches_mutation(self):
        report = await evaluate()
        self.assertEqual(report["total"], 20)
        self.assertEqual(report["passed"], 20)
        case = report["cases"][0]
        wrong = deepcopy(case["run"])
        source = next(source for source in wrong["result"]["sources"] if source["kind"] == "market")
        data = json.loads(source["content"]); data["return_pct"] = "999"
        source["content"] = json.dumps(data)
        self.assertIn("incorrect percentage for BTCUSDT", check_case(case["expected"], wrong))


class InputAndStoreTests(unittest.TestCase):
    def test_request_rejects_invalid_modes_and_times(self):
        for changes in [{"question": " "}, {"as_of": "2026-10-16T00:00:00"}, {"as_of": 1792108800},
                        {"as_of": "2026-10-12T00:00:00Z"}, {"mode": "live", "scenario": "eth_timeout"},
                        {"question": 123}, {"extra": "bad"}]:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                ResearchRequest.model_validate({"question": "BTC 7d", **changes})

    def test_parser_does_not_change_rolling_or_mixed_periods(self):
        for question in ["BTC rolling 24h", "BTC 최근 24시간", "BTC 7d 24h", "BTC 2026-10-01", "BTC 30d",
                         "BTC 17일", "BTC 21일", "BTC 7일 1개월", "BTC 2시간"]:
            self.assertEqual(baseline_plan(question).action, "clarify")
        self.assertEqual(baseline_plan("BTCUSDT와 ETHUSDT 7일").symbols, ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(baseline_plan("BTC SOLUSDT 7일").action, "unsupported")

    def test_atomic_write_preserves_old_record_on_serialization_error(self):
        run_id = "0c3ec222-c5b7-4af1-a038-698106ac3d32"
        record = {"run_id": run_id, "format_version": 1}
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory))
            store.save(record)
            with self.assertRaises(TypeError):
                store.save({**record, "bad": object()})
            self.assertEqual(store.get(run_id), record)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)
            with self.assertRaises(ValueError):
                store.get("../outside")
