"""The browser uses these same endpoints; no server or external network needed."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

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
        response = await self.client.post("/api/research", json={"question": "BTC ETH 7d", "scenario": "eth_timeout"})
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
        record = (await self.client.post("/api/research", json={"question": "BTC 7d"})).json()
        record["http"][0]["url"] += "&unexpected=1"
        (self.path / "runs" / f"{record['run_id']}.json").write_text(json.dumps(record))
        response = await self.client.post(f"/api/runs/{record['run_id']}/replay")
        self.assertEqual(response.status_code, 409)

    async def test_evaluation_preserves_full_raw_results(self):
        response = await self.client.post("/api/evaluate")
        self.assertEqual(response.status_code, 200)
        report = response.json()
        self.assertEqual(report["passed"], 20)
        self.assertEqual(len(report["cases"]), 20)
        self.assertTrue((self.path / "evaluation.json").exists())
        self.assertTrue((self.path / "evaluation.md").exists())
        self.assertEqual(report["dimensions"]["status"], {"passed": 20, "total": 20})
        self.assertEqual((await self.client.get("/api/runs")).json(), [])
