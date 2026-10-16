"""OpenAI transport, strict schema, missing usage, and secret-free replay checks."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from market_agent.evaluate import evaluate, summarize_runs
from market_agent.llm import call_openai, openai_output_text, usage_metadata
from market_agent.runtime import ResearchRequest, planner_schema, replay_run, run_research

PLAN = {"action": "research", "symbols": ["BTCUSDT"], "period": "7d",
        "document_query": "klines UTC", "message": None}
RESPONSE = {"model": "gpt-6-astra", "status": "completed", "output": [
    {"type": "reasoning", "summary": [{"text": "private reasoning"}]},
    {"type": "message", "content": [{"type": "output_text", "text": json.dumps(PLAN)}]},
], "usage": {"input_tokens": 1000, "output_tokens": 50,
             "input_tokens_details": {"cached_tokens": 100},
             "output_tokens_details": {"reasoning_tokens": 10}}}


class OpenAITests(unittest.IsolatedAsyncioTestCase):
    async def test_transport_uses_required_strict_fields_without_mutating_schema(self):
        schema = planner_schema()
        before = deepcopy(schema)
        def handler(request):
            self.assertEqual(str(request.url), "https://api.openai.com/v1/responses")
            body = json.loads(request.content)
            self.assertEqual(body["model"], "gpt-6-astra")
            self.assertFalse(body["store"])
            self.assertEqual(body["reasoning"], {"effort": "low"})
            self.assertEqual(body["max_output_tokens"], 1024)
            output = body["text"]["format"]
            self.assertTrue(output["strict"])
            self.assertEqual(set(output["schema"]["required"]), set(schema["properties"]))
            self.assertTrue(all("default" not in value for value in output["schema"]["properties"].values()))
            return httpx.Response(200, json=RESPONSE)
        async with httpx.AsyncClient(base_url="https://api.openai.com", transport=httpx.MockTransport(handler)) as client:
            raw = await call_openai(client, [{"role": "user", "content": "BTC 7d"}], schema)
            self.assertEqual(raw, RESPONSE)
            self.assertEqual(json.loads(openai_output_text(raw)), PLAN)
        self.assertEqual(schema, before)

    async def test_record_and_replay_never_persist_key_or_reasoning(self):
        def handler(request):
            self.assertEqual(request.headers["authorization"], "Bearer unit-test-secret")
            return httpx.Response(200, json=RESPONSE)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "unit-test-secret"}), patch(
            "market_agent.runtime.httpx.AsyncHTTPTransport", return_value=httpx.MockTransport(handler)
        ):
            record = await run_research(ResearchRequest(question="BTC 7d", planner="openai"))
        self.assertEqual(record["result"]["status"], "completed")
        self.assertEqual(record["metadata"]["model"], "gpt-6-astra")
        self.assertNotIn("unit-test-secret", json.dumps(record))
        self.assertNotIn("private reasoning", json.dumps(record))
        self.assertAlmostEqual(summarize_runs([record])["estimated_external_llm_api_cost_usd"], 0.0116)
        with patch.dict("os.environ", {}, clear=True), patch.object(
            httpx.AsyncHTTPTransport, "handle_async_request", side_effect=AssertionError("no network")
        ):
            replay = await replay_run(record)
        self.assertTrue(replay["comparison"]["same_result"])
        self.assertEqual(summarize_runs([replay])["tokens"]["output"]["total"], 0)

    async def test_incomplete_output_remains_failure_with_observed_tokens(self):
        response = {**RESPONSE, "status": "incomplete", "output": []}
        with patch.dict("os.environ", {"OPENAI_API_KEY": "unit-test-secret"}), patch(
            "market_agent.runtime.httpx.AsyncHTTPTransport", return_value=httpx.MockTransport(
                lambda request: httpx.Response(200, json=response))
        ):
            record = await run_research(ResearchRequest(question="BTC 7d", planner="openai"))
        self.assertEqual(record["result"]["status"], "error")
        self.assertEqual(record["metrics"]["http_calls"], 1)
        self.assertEqual(record["metrics"]["usage"][0]["output_tokens"], 50)

    async def test_missing_key_stops_before_paid_network_call(self):
        with patch.dict("os.environ", {}, clear=True), patch.object(
            httpx.AsyncHTTPTransport, "handle_async_request", side_effect=AssertionError("no network")
        ):
            record = await run_research(ResearchRequest(question="BTC 7d", planner="openai"))
            self.assertEqual(record["result"]["status"], "error")
            self.assertEqual(record["metrics"]["http_calls"], 0)
            with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY"):
                await evaluate("openai")


class CostTests(unittest.TestCase):
    def test_pricing_uses_cache_hits_and_does_not_double_count_reasoning(self):
        usage = usage_metadata(RESPONSE, "openai")
        self.assertAlmostEqual(usage["estimated_api_cost_usd"], 0.0116)
        self.assertEqual(usage["reasoning_tokens"], 10)
        missing = usage_metadata({}, "openai")
        self.assertIsNone(missing["input_tokens"])
        self.assertIsNone(missing["estimated_api_cost_usd"])
