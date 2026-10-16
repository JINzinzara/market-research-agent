"""Price, interval, and evidence-boundary checks independent of a live exchange."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal, getcontext
import json
from pathlib import Path
import sys
import tempfile
import unittest

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from market_agent.fixtures import DEMO_AS_OF, demo_transport
from market_agent.schema import Source
from market_agent.tools import (DAY_MS, build_bm25, calculate_return, fetch_market_data,
                                load_documents, market_window, search_documents, tokenize)


class CalculationTests(unittest.TestCase):
    def test_percentage_uses_decimal_and_preserves_context(self):
        original = getcontext().prec
        self.assertEqual(calculate_return(Decimal("100"), Decimal("110")), Decimal("10"))
        self.assertEqual(calculate_return(Decimal("200"), Decimal("180")), Decimal("-10"))
        self.assertEqual(calculate_return(Decimal("0.1"), Decimal("0.11")), Decimal("10"))
        self.assertEqual(getcontext().prec, original)

    def test_prices_must_be_positive_finite_decimals(self):
        for value in [Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("Infinity"), 1.0]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                calculate_return(value, Decimal("100"))
            with self.subTest(value=value), self.assertRaises(ValueError):
                calculate_return(Decimal("100"), value)

    def test_window_converts_timezone_before_midnight(self):
        local = datetime(2026, 10, 16, 8, 59, tzinfo=timezone(timedelta(hours=9)))
        start, end = market_window(local, "7d")
        self.assertEqual(start.isoformat(), "2026-10-08T00:00:00+00:00")
        self.assertEqual(end.isoformat(), "2026-10-15T00:00:00+00:00")
        with self.assertRaises(ValueError):
            market_window(datetime(2026, 10, 16), "7d")
        with self.assertRaises(ValueError):
            market_window(DEMO_AS_OF, "30d")


class MarketTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_http_window_and_original_prices(self):
        transport = demo_transport()
        requests = []
        async def handler(request):
            requests.append(request)
            return await transport.handle_async_request(request)
        async with httpx.AsyncClient(base_url="https://data-api.binance.vision",
                                     transport=httpx.MockTransport(handler)) as client:
            source = await fetch_market_data(client, "BTCUSDT", "7d", as_of=DEMO_AS_OF)
        params = requests[0].url.params
        start, end = market_window(DEMO_AS_OF, "7d")
        self.assertEqual(int(params["startTime"]), int(start.timestamp() * 1000))
        self.assertEqual(int(params["endTime"]), int(end.timestamp() * 1000) - 1)
        self.assertEqual(params["interval"], "1d")
        self.assertEqual(params["timeZone"], "0")
        self.assertEqual(params["limit"], "7")
        data = json.loads(source.content)
        self.assertEqual(data["open"], "100")
        self.assertEqual(data["return_pct"], "10.0")
        self.assertEqual(data["display_return_pct"], "10.00")
        self.assertEqual(len(data["candles"]), 7)

    async def test_malformed_candles_cannot_become_evidence(self):
        start = int((DEMO_AS_OF - timedelta(days=1)).timestamp() * 1000)
        row = [start, "100", "110", "99", "105", "1", start + DAY_MS - 1, "1", 1, "1", "1", "0"]
        cases = [[], [row, row], [row[:-1]], {"error": "bad payload"}]
        for index, value in [(0, start + 1), (0, True), (6, start + DAY_MS), (1, "0"),
                             (1, "NaN"), (1, "bad"), (1, 100), (2, "90"), (3, "106")]:
            changed = list(row); changed[index] = value; cases.append([changed])
        for payload in cases:
            with self.subTest(payload=payload):
                async with httpx.AsyncClient(base_url="https://example.com", transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json=payload))) as client:
                    with self.assertRaises(ValueError):
                        await fetch_market_data(client, "BTCUSDT", "24h", as_of=DEMO_AS_OF)

    async def test_429_propagates_without_retry(self):
        async with httpx.AsyncClient(base_url="https://example.com", transport=demo_transport("eth_rate_limit")) as client:
            with self.assertRaises(httpx.HTTPStatusError):
                await fetch_market_data(client, "ETHUSDT", "7d", as_of=DEMO_AS_OF)


class DocumentTests(unittest.TestCase):
    def test_empty_and_no_overlap_return_no_evidence(self):
        self.assertEqual(search_documents("UTC", build_bm25([]), top_k=2), [])
        self.assertEqual(tokenize("UTC 1d / 완료된 일봉"), ["utc", "1d", "완료된", "일봉"])
        docs = load_documents(Path(__file__).resolve().parents[1] / "src/market_agent/data/documents.json")
        self.assertEqual(search_documents("zzznomatch", build_bm25(docs), top_k=2), [])
        found = search_documents("klines UTC", build_bm25(docs), top_k=2)
        self.assertEqual(found[0].source_id, "doc-klines")
        with self.assertRaises(ValueError):
            search_documents(" ", build_bm25(docs), top_k=2)
        with self.assertRaises(ValueError):
            search_documents("UTC", build_bm25(docs), top_k=0)

    def test_corpus_rejects_duplicate_ids_and_market_sources(self):
        source = {"source_id": "one", "kind": "document", "title": "Doc", "url": "https://example.com",
                  "content": "API", "retrieved_at": "2026-10-16T00:00:00Z"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corpus.json"
            for data in [[source, source], [{**source, "kind": "market"}], {"sources": []}]:
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    load_documents(path)
