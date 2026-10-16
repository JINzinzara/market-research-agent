"""The browser uses these same endpoints; no server or external network needed."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from market_agent.api import create_app


class APITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(self.path)), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        self.directory.cleanup()

    async def test_page_and_assets_are_packaged(self):
        for url, content in [("/", "Show your work."), ("/app.js", "/api/research"), ("/app.css", "@media")]:
            response = await self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertIn(content, response.text)

    async def test_research_history_and_replay(self):
        response = await self.client.post("/api/research", json={"mode": "demo", "planner": "baseline", "web": False, "question": "BTC ETH 7d", "scenario": "eth_timeout"})
        self.assertEqual(response.status_code, 200)
        record = response.json()
        self.assertEqual(record["result"]["status"], "partial")
        replay = await self.client.post(f"/api/runs/{record['run_id']}/replay")
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["comparison"]["same_result"])
        history = (await self.client.get("/api/runs")).json()
        self.assertEqual(len(history), 2)
        self.assertEqual((await self.client.get(f"/api/runs/{record['run_id']}")).json(), record)
        self.assertEqual((await self.client.get("/api/runs/not-a-uuid")).status_code, 404)

    async def test_validation_and_replay_mismatch(self):
        for body in [{"question": " "}, {"question": "BTC 7d", "mode": "live", "scenario": "all_timeout"}]:
            self.assertEqual((await self.client.post("/api/research", json=body)).status_code, 422)
        record = (await self.client.post("/api/research", json={"mode": "demo", "planner": "baseline", "web": False, "question": "BTC 7d"})).json()
        record["http"][0]["url"] += "&unexpected=1"
        (self.path / "runs" / f"{record['run_id']}.json").write_text(json.dumps(record))
        response = await self.client.post(f"/api/runs/{record['run_id']}/replay")
        self.assertEqual(response.status_code, 409)

    async def test_live_evaluation_missing_key_is_explicit_and_never_uses_demo(self):
        with patch.dict("os.environ", {}, clear=True):
            response = await self.client.post("/api/evaluate")
        self.assertEqual(response.status_code, 400)
        self.assertIn("OPENAI_API_KEY", response.json()["detail"])
        self.assertEqual((await self.client.get("/api/runs")).json(), [])

    async def test_status_reports_current_contract_without_exposing_credentials(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "unit-test-secret"}):
            response = await self.client.get("/api/status")
        self.assertEqual(response.json()["api_contract"], "research-live-v1")
        self.assertTrue(response.json()["openai_key_configured"])
        self.assertNotIn("unit-test-secret", response.text)
        schema = (await self.client.get("/openapi.json")).json()
        props = schema["components"]["schemas"]["ResearchRequest"]["properties"]
        self.assertIn("web", props)
        self.assertEqual(props["mode"]["default"], "live")
        self.assertEqual(response.headers["cache-control"], "no-store")

    async def test_live_benchmark_endpoint_preserves_runs_and_review_template(self):
        from test_web_research import RESPONSE
        with patch.dict("os.environ", {"OPENAI_API_KEY": "unit-test-secret"}), patch(
            "market_agent.runtime.httpx.AsyncHTTPTransport", return_value=httpx.MockTransport(
                lambda request: httpx.Response(200, json=RESPONSE))
        ):
            response = await self.client.post("/api/evaluate", json={"limit": 2})
        self.assertEqual(response.status_code, 200)
        report = response.json()
        self.assertEqual(report["total"], 2)
        self.assertIsNone(report["quality"]["answer_correct"]["rate_all_cases"])
        self.assertTrue((self.path / "research-benchmark.reviews.json").exists())
        self.assertEqual(len((await self.client.get("/api/runs")).json()), 2)
        info = (await self.client.get("/api/benchmark")).json()
        self.assertEqual((info["case_count"], info["event_groups"]), (12, 6))
