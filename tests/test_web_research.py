"""Synthetic provider responses test the integration, not real news accuracy."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from market_agent.api import create_app
from market_agent.evaluate import summarize_runs
from market_agent.fixtures import demo_transport
from market_agent.llm import usage_metadata
from market_agent.runtime import ResearchRequest, replay_run, run_research
from market_agent.web_research import call_web_research, parse_web_research

NOW = datetime(2026, 10, 16, tzinfo=timezone.utc)
TEXT = "테스트 보도입니다. <news>\n\n테스트 공식 발표입니다. <macro>"
ANNOTATIONS = [
    {"type": "url_citation", "url": "https://news.example.org/test", "title": "Synthetic news fixture",
     "start_index": TEXT.index("<news>"), "end_index": TEXT.index("<news>") + 6},
    {"type": "url_citation", "url": "https://www.federalreserve.gov/test-fixture.htm", "title": "Synthetic macro fixture",
     "start_index": TEXT.index("<macro>"), "end_index": len(TEXT)},
]
RESPONSE = {"status": "completed", "model": "gpt-6-astra", "output": [
    {"type": "reasoning", "summary": [{"text": "private reasoning fixture"}]},
    {"type": "web_search_call", "status": "completed", "action": {"type": "search", "queries": ["test news macro"],
     "sources": [{"url": row["url"], "title": row["title"]} for row in ANNOTATIONS]}},
    {"type": "web_search_call", "status": "completed", "action": {"type": "open_page", "url": ANNOTATIONS[1]["url"]}},
    {"type": "message", "content": [{"type": "output_text", "text": TEXT, "annotations": ANNOTATIONS}]},
], "usage": {"input_tokens": 100, "output_tokens": 30, "input_tokens_details": {"cached_tokens": 0}}}


def web_request(question="최근 Fed 금리 결정과 관련 뉴스를 조사해줘"):
    return ResearchRequest(question=question, mode="live", planner="openai", web=True, as_of=NOW)


class WebParserTests(unittest.TestCase):
    def test_preserves_claims_and_uses_only_provider_citations(self):
        raw = deepcopy(RESPONSE)
        block = raw["output"][-1]["content"][0]
        block["text"] += " https://invented.example.org/not-a-provider-citation"
        text, sources = parse_web_research(raw, retrieved_at=NOW)
        self.assertIn("테스트 보도입니다.", text)
        self.assertIn("[web-1]", text)
        self.assertIn("[web-2]", text)
        self.assertEqual([str(source.url) for source in sources], [row["url"] for row in ANNOTATIONS])
        self.assertTrue(all(not json.loads(source.content)["full_text_fetched_by_app"] for source in sources))

    def test_deduplicates_urls_and_preserves_citation_spans(self):
        raw = deepcopy(RESPONSE)
        raw["output"][-1]["content"][0]["annotations"][1]["url"] = ANNOTATIONS[0]["url"]
        text, sources = parse_web_research(raw, retrieved_at=NOW)
        self.assertEqual(len(sources), 1)
        self.assertEqual(text.count("[web-1]"), 2)
        self.assertIn("테스트 공식 발표입니다.", text)

    def test_rejects_incomplete_output_or_absent_completed_search(self):
        for change in ("incomplete", "no_search", "failed_search", "no_citations"):
            raw = deepcopy(RESPONSE)
            if change == "incomplete": raw["status"] = "incomplete"
            if change == "no_search": raw["output"] = raw["output"][-1:]
            if change == "failed_search": raw["output"][1]["status"] = "failed"
            if change == "no_citations": raw["output"][-1]["content"][0]["annotations"] = []
            with self.subTest(change=change), self.assertRaises((ValueError, RuntimeError)):
                parse_web_research(raw, retrieved_at=NOW)

    def test_rejects_unsafe_urls_and_invalid_annotation_ranges(self):
        for change in ({"url": "javascript:alert(1)"}, {"url": "https://user:secret@example.org"},
                       {"start_index": -1}, {"end_index": len(TEXT) + 1},
                       {"start_index": True}, {"title": None}):
            raw = deepcopy(RESPONSE)
            raw["output"][-1]["content"][0]["annotations"][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                parse_web_research(raw, retrieved_at=NOW)

    def test_rejects_malformed_annotations_instead_of_crashing(self):
        for value in (None, {}, [None]):
            raw = deepcopy(RESPONSE)
            raw["output"][-1]["content"][0]["annotations"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_web_research(raw, retrieved_at=NOW)

    def test_web_fee_is_not_reported_as_a_complete_text_only_cost(self):
        usage = usage_metadata(RESPONSE, "openai")
        self.assertEqual(usage["web_tool_calls"], 2)
        self.assertEqual(usage["web_search_calls"], 1)
        self.assertIsNone(usage["estimated_api_cost_usd"])
        self.assertGreater(usage["estimated_text_api_cost_usd"], 0)


class WebWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def run_fixture(self, request, *, response=RESPONSE, status=200):
        calls = []
        market = demo_transport("none")
        async def handler(incoming):
            calls.append(incoming)
            if incoming.url.host == "data-api.binance.vision":
                return await market.handle_async_request(incoming)
            self.assertEqual(incoming.url.host, "api.openai.com")
            self.assertEqual(incoming.headers["authorization"], "Bearer unit-test-secret")
            return httpx.Response(status, json=response)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "unit-test-secret"}), patch(
            "market_agent.runtime.httpx.AsyncHTTPTransport", return_value=httpx.MockTransport(handler)
        ):
            record = await run_research(request)
        return record, calls

    async def test_hosted_search_contract_requires_live_search_and_all_source_metadata(self):
        def handler(request):
            body = json.loads(request.content)
            self.assertEqual(body["tools"], [{"type": "web_search", "external_web_access": True}])
            self.assertEqual(body["tool_choice"], "required")
            self.assertEqual(body["include"], ["web_search_call.action.sources"])
            self.assertEqual(body["max_tool_calls"], 3)
            self.assertFalse(body["store"])
            self.assertNotIn("text", body)
            self.assertIn("2026-10-16", body["input"])
            return httpx.Response(200, json=RESPONSE)
        async with httpx.AsyncClient(base_url="https://api.openai.com", transport=httpx.MockTransport(handler)) as client:
            self.assertEqual(await call_web_research(client, "test question", as_of=NOW), RESPONSE)

    async def test_news_and_macro_only_request_bypasses_price_scope_gate(self):
        record, calls = await self.run_fixture(web_request())
        self.assertEqual(record["result"]["status"], "completed")
        self.assertEqual(len(calls), 1)
        self.assertEqual(record["plan"]["symbols"], [])
        self.assertEqual(record["metrics"]["citation_count"], 2)
        self.assertEqual(record["metrics"]["web_search_calls"], 1)
        self.assertEqual(record["metrics"]["web_tool_calls"], 2)
        self.assertEqual(record["metrics"]["live_llm_calls"], 1)
        self.assertIsNone(summarize_runs([record])["estimated_external_llm_api_cost_usd"])
        self.assertNotIn("unit-test-secret", json.dumps(record))
        self.assertNotIn("private reasoning fixture", json.dumps(record))

    async def test_prices_and_web_evidence_share_a_report_and_replay_twice_without_network(self):
        record, calls = await self.run_fixture(web_request("BTC 7d 관련 뉴스와 거시 자료를 조사해줘"))
        self.assertEqual(record["result"]["status"], "completed")
        self.assertEqual(len(calls), 2)
        self.assertEqual(record["result"]["source_ids"], ["market-BTCUSDT", "web-1", "web-2"])
        self.assertIn("BTCUSDT:", record["result"]["answer"])
        self.assertIn("[web-2]", record["result"]["answer"])
        with patch.dict("os.environ", {}, clear=True), patch.object(
            httpx.AsyncHTTPTransport, "handle_async_request", side_effect=AssertionError("no network")
        ):
            first = await replay_run(record)
            second = await replay_run(first)
        for replay in (first, second):
            self.assertTrue(replay["comparison"]["same_result"])
            self.assertEqual(replay["metrics"]["live_llm_calls"], 0)
            self.assertEqual(replay["metrics"]["network_attempts"], 0)

    async def test_search_failure_preserves_successful_price_evidence(self):
        record, _ = await self.run_fixture(web_request("BTC 7d 뉴스"), response={"error": "unavailable"}, status=503)
        self.assertEqual(record["result"]["status"], "partial")
        self.assertEqual(record["result"]["source_ids"], ["market-BTCUSDT"])
        self.assertEqual(record["failures"][0]["symbol"], "web")
        self.assertIn("뉴스·거시경제 결론은 제시하지 않습니다", record["result"]["answer"])

    async def test_no_citations_or_incomplete_output_never_becomes_a_successful_web_report(self):
        for change in ("no_citations", "incomplete"):
            raw = deepcopy(RESPONSE)
            if change == "no_citations": raw["output"][-1]["content"][0]["annotations"] = []
            else: raw.update(status="incomplete", output=[])
            record, _ = await self.run_fixture(web_request(), response=raw)
            self.assertEqual(record["result"]["status"], "error")
            self.assertEqual(record["metrics"]["citation_count"], 0)
            self.assertEqual(record["metrics"]["usage"][0]["output_tokens"], 30)
            self.assertIsNone(record["metrics"]["usage"][0]["estimated_api_cost_usd"])

    async def test_causal_question_keeps_inference_limit_even_with_cited_news(self):
        record, _ = await self.run_fixture(web_request("왜 BTC 7d 가격이 변했는지 뉴스를 조사해줘"))
        self.assertEqual(record["result"]["status"], "insufficient_evidence")
        self.assertIn("인과관계를 입증하지 않습니다", record["result"]["answer"])

    async def test_missing_key_stops_before_any_external_network(self):
        with patch.dict("os.environ", {}, clear=True), patch.object(
            httpx.AsyncHTTPTransport, "handle_async_request", side_effect=AssertionError("no network")
        ):
            record = await run_research(web_request())
        self.assertEqual(record["result"]["status"], "error")
        self.assertEqual(record["metrics"]["http_calls"], 0)

    async def test_api_accepts_web_requests_and_stores_replayable_citations(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(Path(directory))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                with patch.dict("os.environ", {"OPENAI_API_KEY": "unit-test-secret"}), patch(
                    "market_agent.runtime.httpx.AsyncHTTPTransport", return_value=httpx.MockTransport(
                        lambda request: httpx.Response(200, json=RESPONSE))
                ):
                    response = await client.post("/api/research", json=web_request().model_dump(mode="json"))
                self.assertEqual(response.status_code, 200)
                record = response.json()
                self.assertEqual(record["result"]["status"], "completed")
                replay = await client.post(f"/api/runs/{record['run_id']}/replay")
                self.assertTrue(replay.json()["comparison"]["same_result"])


class WebRequestTests(unittest.TestCase):
    def test_web_requests_require_an_explicit_live_openai_choice(self):
        for changes in ({}, {"mode": "live"}, {"planner": "openai"}, {"mode": "live", "planner": "ollama"}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                ResearchRequest(question="Fed news", web=True, **changes)
        self.assertTrue(web_request().web)
